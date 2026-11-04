"""Auth email goes through the job queue, so an outage retries and the request's response never changes.

The raw token is created here, at send time, so it is never stored in a job's payload.
"""
from typing import Any

from django.conf import settings

from collectiq.platform.context import RequestContext
from collectiq.platform.db import fetch_one
from collectiq.platform.email import send_email
from collectiq.platform.jobs import job_handler

from . import throttle, tokens
from .service import app_link


def _user(payload: dict[str, Any]) -> dict[str, Any] | None:
    if not payload.get("user_id"):
        return None
    return fetch_one(
        "SELECT id, email::text AS email, status, email_verified_at IS NOT NULL AS verified"
        " FROM users WHERE id = %s",
        [payload["user_id"]],
    )


def _send_verification(user: dict[str, Any]) -> None:
    token = tokens.issue(user["id"], tokens.VERIFY_EMAIL, settings.EMAIL_VERIFY_TTL)
    send_email(
        user["email"],
        "Confirm your email for CollectIQ",
        f"Confirm your email address:\n\n{app_link('/verify-email', token)}\n\n"
        "If you did not create this account, you can ignore this message.",
    )


@job_handler("identity.registration_email")
def registration_email(ctx: RequestContext, payload: dict[str, Any]) -> None:
    user = _user(payload)
    if user is None or not throttle.take_mail_slot(user["email"]):
        return
    if user["verified"]:
        send_email(
            user["email"],
            "Someone tried to register with your email",
            "This address already has a CollectIQ account, so no new one was created.\n\n"
            "If this was you, sign in or reset your password. If not, you can ignore this message.",
        )
    else:
        _send_verification(user)


@job_handler("identity.verification_email")
def verification_email(ctx: RequestContext, payload: dict[str, Any]) -> None:
    user = _user(payload)
    if user is None or user["verified"] or user["status"] == "DISABLED":
        return
    if throttle.take_mail_slot(user["email"]):
        _send_verification(user)


@job_handler("identity.password_reset_email")
def password_reset_email(ctx: RequestContext, payload: dict[str, Any]) -> None:
    user = _user(payload)
    if user is None or not user["verified"] or user["status"] == "DISABLED":
        return
    if not throttle.take_mail_slot(user["email"]):
        return
    token = tokens.issue(user["id"], tokens.PASSWORD_RESET, settings.PASSWORD_RESET_TTL)
    send_email(
        user["email"],
        "Reset your CollectIQ password",
        f"Choose a new password:\n\n{app_link('/reset-password', token)}\n\n"
        "This link works once and expires soon. If you did not ask for it, you can ignore this message.",
    )
