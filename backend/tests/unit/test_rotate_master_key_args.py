"""Unit tests for rotate_master_key management command validation (no database)."""
import base64

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from collectiq.platform.management.commands.rotate_master_key import _decode_key


def test_decode_key_rejects_invalid_base64():
    with pytest.raises(CommandError, match="valid base64"):
        _decode_key("--test-key", "not-valid-base64!@#")


def test_decode_key_rejects_wrong_length():
    short_key = base64.b64encode(b"short").decode()
    with pytest.raises(CommandError, match="exactly 32 bytes"):
        _decode_key("--test-key", short_key)


def test_decode_key_accepts_valid_32_byte_key():
    valid = base64.b64encode(b"0" * 32).decode()
    assert _decode_key("--test-key", valid) == b"0" * 32


def test_command_rejects_identical_keys():
    same_key = base64.b64encode(b"A" * 32).decode()
    with pytest.raises(CommandError, match="cannot be identical"):
        call_command("rotate_master_key", new_key=same_key, old_key=same_key)
