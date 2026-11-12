"""Integration test for master key rotation against PostgreSQL."""
import base64
import os
import uuid
from io import StringIO

import psycopg
import pytest
from django.conf import settings
from django.core.management import call_command

from collectiq.platform.context import RequestContext
from collectiq.platform.crypto import EnvelopeCipher
from collectiq.platform.db import tenant_tx
from tests.support import owner_workspace

pytestmark = pytest.mark.usefixtures("pg")


def test_rotate_master_key_reseals_workspace_keys(owner_db: psycopg.Connection) -> None:
    old_master_key = settings.COLLECTIQ_MASTER_KEY
    new_master_key = base64.b64encode(os.urandom(32)).decode()

    _, ws_str = owner_workspace(owner_db, "rot-test@example.test")
    ws_id = uuid.UUID(ws_str)

    ctx = RequestContext(
        workspace_id=ws_id,
        user_id=None,
        role="OWNER",
        correlation_id="rot-test",
        actor_type="SYSTEM",
    )

    old_cipher = EnvelopeCipher(old_master_key)
    plaintext = b"super-sensitive-token-payload"

    with tenant_tx(ctx):
        ciphertext = old_cipher.encrypt(ctx, plaintext)

    # 1. Test Dry Run: ciphertext stays decryptable by old cipher
    out = StringIO()
    call_command(
        "rotate_master_key", new_key=new_master_key, old_key=old_master_key, dry_run=True, stdout=out
    )
    assert "DRY RUN COMPLETE" in out.getvalue()

    with tenant_tx(ctx):
        assert old_cipher.decrypt(ctx, ciphertext) == plaintext

    # 2. Test Real Rotation: re-seals wrapped keys
    out_real = StringIO()
    call_command("rotate_master_key", new_key=new_master_key, old_key=old_master_key, stdout=out_real)
    assert "ROTATION COMPLETE" in out_real.getvalue()

    # 3. Verify that new cipher decrypts the same ciphertext without re-encrypting the data!
    new_cipher = EnvelopeCipher(new_master_key)
    with tenant_tx(ctx):
        assert new_cipher.decrypt(ctx, ciphertext) == plaintext
