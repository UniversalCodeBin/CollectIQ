from .base import *  # noqa: F403
from .base import AI_PROVIDER, COLLECTIQ_MASTER_KEY, SECRET_KEY

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
