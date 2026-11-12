"""Re-seals workspace data keys under a new master key (COLLECTIQ_MASTER_KEY rotation).

FILE GUIDE: CollectIQ uses envelope encryption (crypto.py): each workspace has a data key
stored in `workspace_keys` wrapped by `COLLECTIQ_MASTER_KEY`. Data at rest is encrypted with
the workspace data key, so rotating the master key requires only re-sealing the wrapped data keys
in `workspace_keys`, preserving all existing encrypted records without data re-encryption.

Usage:
    DJANGO_DB_ROLE=owner python manage.py rotate_master_key \
        --new-key <base64-32-byte-key> [--old-key <key>] [--dry-run]
"""

import base64
import binascii
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from psycopg.conninfo import make_conninfo

from collectiq.platform.crypto import _KEY_BYTES, _open, _seal

from .schedule_nightly import _workspace_ids


def _decode_key(name: str, key_str: str) -> bytes:
    try:
        decoded = base64.b64decode(key_str, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise CommandError(f"{name} must be valid base64") from exc
    if len(decoded) != _KEY_BYTES:
        raise CommandError(f"{name} must decode to exactly 32 bytes")
    return decoded


@contextmanager
def _owner_cursor() -> Iterator[tuple[Any, Callable[[], None]]]:
    """Yields a cursor and commit callback that has UPDATE privileges on workspace_keys."""
    owner_url = os.environ.get("MIGRATION_DATABASE_URL")
    db_role = os.environ.get("DJANGO_DB_ROLE", "app")

    if owner_url and db_role != "owner":
        # Connect directly with owner credentials to obtain UPDATE rights on workspace_keys
        target_db = settings.DATABASES["default"].get("NAME")
        conn_str = make_conninfo(owner_url, dbname=target_db) if target_db else owner_url
        with psycopg.connect(conn_str) as conn:
            with conn.cursor() as cur:
                yield cur, conn.commit
    else:
        # Django connection is already using the owner role
        with connection.cursor() as cur:
            yield cur, lambda: None


class Command(BaseCommand):
    help = "Re-seal workspace data keys from an old master key to a new master key."

    def add_arguments(self, parser):
        parser.add_argument(
            "--new-key",
            required=True,
            help="The new 32-byte base64-encoded COLLECTIQ_MASTER_KEY.",
        )
        parser.add_argument(
            "--old-key",
            default=None,
            help=(
                "The old 32-byte base64-encoded COLLECTIQ_MASTER_KEY "
                "(defaults to settings.COLLECTIQ_MASTER_KEY)."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate the rotation and verify unwrap/wrap without writing changes to the database.",
        )

    def handle(self, *args, **options):
        new_key_str = options["new_key"]
        old_key_str = options["old_key"] or settings.COLLECTIQ_MASTER_KEY
        dry_run = options["dry_run"]

        if not old_key_str:
            raise CommandError("No old master key provided or found in settings.COLLECTIQ_MASTER_KEY.")

        old_key = _decode_key("--old-key", old_key_str)
        new_key = _decode_key("--new-key", new_key_str)

        if old_key == new_key:
            raise CommandError("The new master key cannot be identical to the old master key.")

        workspace_ids = _workspace_ids()
        self.stdout.write(
            f"Rotating master key across {len(workspace_ids)} workspace(s) (dry_run={dry_run})..."
        )

        rotated_count = 0
        skipped_count = 0

        with _owner_cursor() as (cursor, commit_fn):
            for ws_id in workspace_ids:
                wrap_aad = str(ws_id).encode()

                cursor.execute("SELECT set_config('app.workspace_id', %s, true)", [str(ws_id)])
                cursor.execute(
                    "SELECT wrapped_key FROM workspace_keys WHERE workspace_id = %s",
                    [ws_id],
                )
                row = cursor.fetchone()

                if not row or not row[0]:
                    skipped_count += 1
                    continue

                old_wrapped = bytes(row[0])
                data_key = _open(old_key, old_wrapped, wrap_aad)
                new_wrapped = _seal(new_key, data_key, wrap_aad)

                # Verify round-trip unwrap with the new key before committing
                verified_data_key = _open(new_key, new_wrapped, wrap_aad)
                if verified_data_key != data_key:
                    raise CommandError(f"Verification failed for workspace {ws_id}: re-sealed key mismatch.")

                if not dry_run:
                    cursor.execute("SELECT set_config('app.workspace_id', %s, true)", [str(ws_id)])
                    cursor.execute(
                        "UPDATE workspace_keys SET wrapped_key = %s WHERE workspace_id = %s",
                        [new_wrapped, ws_id],
                    )

                rotated_count += 1

            if not dry_run:
                commit_fn()

        status_msg = "DRY RUN COMPLETE" if dry_run else "ROTATION COMPLETE"
        self.stdout.write(
            self.style.SUCCESS(
                f"{status_msg}: {rotated_count} workspace key(s) re-sealed, {skipped_count} skipped."
            )
        )
