#!/usr/bin/env bash
# Runs the backend for Playwright on its own port, database and mail folder, so it never disturbs `make dev`
# (and a `make dev` worker cannot take its jobs). The database is rebuilt for every run.
set -euo pipefail
cd "$(dirname "$0")/../.."
. frontend/e2e/env.sh
export EMAIL_BACKEND_KIND=file EMAIL_FILE_PATH=var/e2e-mail APP_BASE_URL=http://127.0.0.1:5183
cd backend
case "$1" in
  api)
    rm -rf ../var/e2e-mail
    uv run python ../frontend/e2e/reset_db.py
    DJANGO_DB_ROLE=owner uv run python manage.py migrate --noinput >/dev/null
    exec uv run python manage.py runserver --noreload 127.0.0.1:8100
    ;;
  worker)
    exec uv run python manage.py run_worker
    ;;
esac
