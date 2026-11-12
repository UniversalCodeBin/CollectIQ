"""Tests for session TTL and idle policy invariants (FR-155, B-04). No database."""
from datetime import timedelta

from django.conf import settings


def test_session_absolute_and_idle_policy_matches_prd_fr155():
    """Verify that absolute TTL is 12 hours and idle sensitive limit is 30 minutes."""
    assert settings.SESSION_ABSOLUTE_TTL == timedelta(hours=12)
    assert settings.SESSION_IDLE_SENSITIVE == timedelta(minutes=30)
