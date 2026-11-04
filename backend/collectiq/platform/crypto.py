"""Envelope encryption: a per-workspace data key, wrapped by the deployment's master key (plan A9)."""

import base64
import binascii
import os
from collections.abc import Sequence
from typing import Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import connection

from .context import RequestContext

_VERSION = b"\x01"
_NONCE_BYTES = 12
_KEY_BYTES = 32


class DecryptionError(Exception):
    """The data was altered, or was sealed under another key, workspace or context."""


class CipherPort(Protocol):
    def encrypt(self, ctx: RequestContext, plaintext: bytes, aad: bytes = b"") -> bytes: ...

    def decrypt(self, ctx: RequestContext, ciphertext: bytes, aad: bytes = b"") -> bytes: ...

    def encrypt_many(
        self, ctx: RequestContext, plaintexts: Sequence[bytes], aads: Sequence[bytes]
    ) -> list[bytes]: ...


def _seal(key: bytes, plaintext: bytes, aad: bytes) -> bytes:
    nonce = os.urandom(_NONCE_BYTES)
    return nonce + AESGCM(key).encrypt(nonce, plaintext, aad)


def _open(key: bytes, sealed: bytes, aad: bytes) -> bytes:
    try:
        return AESGCM(key).decrypt(sealed[:_NONCE_BYTES], sealed[_NONCE_BYTES:], aad)
    except (InvalidTag, ValueError) as exc:
        raise DecryptionError("the data cannot be decrypted") from exc


class EnvelopeCipher:
    def __init__(self, master_key: str) -> None:
        try:
            decoded = base64.b64decode(master_key, validate=True)
        except binascii.Error as exc:
            raise ImproperlyConfigured("COLLECTIQ_MASTER_KEY must be base64") from exc
        if len(decoded) != _KEY_BYTES:
            raise ImproperlyConfigured("COLLECTIQ_MASTER_KEY must decode to 32 bytes")
        self._master_key = decoded

    def _data_key(self, ctx: RequestContext) -> bytes:
        if not connection.in_atomic_block:
            raise RuntimeError("the cipher reads its key inside the caller's tenant transaction")
        wrap_aad = str(ctx.workspace_id).encode()
        wrapped = _seal(self._master_key, os.urandom(_KEY_BYTES), wrap_aad)
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO workspace_keys (workspace_id, wrapped_key) VALUES (%s, %s)"
                " ON CONFLICT (workspace_id) DO NOTHING",
                [ctx.workspace_id, wrapped],
            )
            cursor.execute(
                "SELECT wrapped_key FROM workspace_keys WHERE workspace_id = %s", [ctx.workspace_id]
            )
            row = cursor.fetchone()
        return _open(self._master_key, bytes(row[0]), wrap_aad)

    @staticmethod
    def _aad(ctx: RequestContext, aad: bytes) -> bytes:
        # The UUID's fixed width keeps this unambiguous.
        return _VERSION + str(ctx.workspace_id).encode() + aad

    def encrypt(self, ctx: RequestContext, plaintext: bytes, aad: bytes = b"") -> bytes:
        return _VERSION + _seal(self._data_key(ctx), plaintext, self._aad(ctx, aad))

    def encrypt_many(
        self, ctx: RequestContext, plaintexts: Sequence[bytes], aads: Sequence[bytes]
    ) -> list[bytes]:
        """For a batch: the data key is fetched once, each value still gets its own nonce and binding."""
        key = self._data_key(ctx)
        return [
            _VERSION + _seal(key, text, self._aad(ctx, aad))
            for text, aad in zip(plaintexts, aads, strict=True)
        ]

    def decrypt(self, ctx: RequestContext, ciphertext: bytes, aad: bytes = b"") -> bytes:
        if not ciphertext.startswith(_VERSION):
            raise DecryptionError("the data cannot be decrypted")
        return _open(self._data_key(ctx), ciphertext[len(_VERSION) :], self._aad(ctx, aad))


def get_cipher() -> CipherPort:
    return EnvelopeCipher(settings.COLLECTIQ_MASTER_KEY)
