from .base import *  # noqa: F403

DEBUG = False  # the SPA renders problem+json; Django's debug pages would leak internals
SESSION_COOKIE_SECURE = False  # http://localhost only
CSRF_COOKIE_SECURE = False
