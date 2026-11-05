"""WSGI entry point for the production API server."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "collectiq.settings.production")

application = get_wsgi_application()
