#!/usr/bin/env bash
# Runs the backend for Playwright on its own port with its own mail folder, so it never disturbs `make dev`.
set -euo pipefail
cd "$(dirname "$0")/../.."
set -a
. ./.env
set +a
export EMAIL_BACKEND_KIND=file EMAIL_FILE_PATH=var/e2e-mail APP_BASE_URL=http://127.0.0.1:5183
cd backend
case "$1" in
  api)
    rm -rf ../var/e2e-mail
    DJANGO_DB_ROLE=owner uv run python manage.py migrate --noinput >/dev/null
    exec uv run python manage.py runserver --noreload 127.0.0.1:8100
    ;;
  worker)
    exec uv run python manage.py run_worker
    ;;
esac
