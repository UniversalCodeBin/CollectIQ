# Everything runs from the repository root. Recipes quote paths and use `cd` into subfolders because
# this project may live under a directory with spaces.
SHELL := /bin/bash
DB_IMAGE := docker.io/library/postgres:16-alpine
ARGS ?=

-include .env
export

.PHONY: env db-up db-down migrate seed dev api worker web test check e2e openapi

env:
	@python3 scripts/bootstrap_env.py

db-up: env
	@set -a; . ./.env; set +a; podman container exists collectiq-db || podman run -d --name collectiq-db --restart=unless-stopped -p 127.0.0.1:54329:5432 -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD="$$POSTGRES_PASSWORD" -e POSTGRES_DB=postgres -v collectiq_pgdata:/var/lib/postgresql/data $(DB_IMAGE) >/dev/null
	@podman start collectiq-db >/dev/null
	@for i in $$(seq 1 60); do podman exec collectiq-db pg_isready -q -U postgres && break; sleep 1; done
	@set -a; . ./.env; set +a; podman exec -i -e OWNER_PASSWORD="$$COLLECTIQ_OWNER_PASSWORD" -e APP_PASSWORD="$$COLLECTIQ_APP_PASSWORD" collectiq-db sh < deploy/postgres/init/01-roles.sh
	@echo "database ready on 127.0.0.1:54329"

db-down:
	@podman stop collectiq-db >/dev/null

migrate:
	cd backend && DJANGO_DB_ROLE=owner uv run python manage.py migrate

seed:
	cd backend && uv run python manage.py seed_sample

api:
	cd backend && uv run python manage.py runserver 127.0.0.1:8000

worker:
	cd backend && uv run python manage.py run_worker

web:
	cd frontend && npm run dev

dev:
	@trap 'kill 0' EXIT; (cd backend && uv run python manage.py runserver 127.0.0.1:8000) & (cd backend && uv run python manage.py run_worker) & (cd frontend && npm run dev) & wait

test:
	cd backend && uv run pytest $(ARGS)
	cd frontend && npm test

check:
	python3 scripts/run_check.py

e2e:
	cd frontend && npx playwright test $(ARGS)

openapi:
	cd backend && uv run python manage.py spectacular --file ../docs/api/openapi.generated.yaml --validate
	cd frontend && npm run gen:api
