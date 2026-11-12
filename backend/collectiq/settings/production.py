from .base import *  # noqa: F403
from .base import (  # noqa: E402
    AI_PROVIDER,
    COLLECTIQ_MASTER_KEY,
    EMAIL_BACKEND_KIND,
    SECRET_KEY,
    SMTP_FROM,
    SMTP_HOST,
)

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

if AI_PROVIDER == "fake":
    raise RuntimeError("AI_PROVIDER=fake is a test adapter and is refused in production.")
if "change-me" in (SECRET_KEY, COLLECTIQ_MASTER_KEY):
    raise RuntimeError("Replace the placeholder secrets before running in production.")
if EMAIL_BACKEND_KIND == "smtp" and not (SMTP_HOST and SMTP_FROM):
    raise RuntimeError("EMAIL_BACKEND_KIND=smtp needs SMTP_HOST and SMTP_FROM.")
