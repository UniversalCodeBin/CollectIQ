"""Database fixtures. Tests connect as the app role, so forced RLS applies to them.

The session creates `collectiq_test`, migrates it in a subprocess as the owner role, then Django
connects as `collectiq_app`. Tests that need no database never touch any of this.
"""
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

BACKEND = Path(__file__).resolve().parents[1]
TEST_DB = "collectiq_test"

# Mirrors deploy/postgres/init/01-roles.sh, which only prepares the `collectiq` database.
SCHEMA_GRANTS = """
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO collectiq_app;
ALTER DEFAULT PRIVILEGES FOR ROLE collectiq_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO collectiq_app;
ALTER DEFAULT PRIVILEGES FOR ROLE collectiq_owner IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO collectiq_app;
"""


def _owner_conninfo(dbname: str) -> str:
    return make_conninfo(os.environ["MIGRATION_DATABASE_URL"], dbname=dbname)


@pytest.fixture(scope="session")
def django_db_setup(django_db_blocker) -> None:  # replaces pytest-django's: no test-database cloning
    from django.conf import settings

    assert settings.DATABASES["default"]["NAME"] == TEST_DB
    maintenance_db = conninfo_to_dict(os.environ["MIGRATION_DATABASE_URL"])["dbname"]
    assert maintenance_db != TEST_DB, "MIGRATION_DATABASE_URL must point at the real database in .env"
    with psycopg.connect(_owner_conninfo(str(maintenance_db)), autocommit=True) as admin:
        admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(TEST_DB)))
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(TEST_DB)))
    with psycopg.connect(_owner_conninfo(TEST_DB), autocommit=True) as owner:
        owner.execute(SCHEMA_GRANTS)
    env = {**os.environ, "DJANGO_DB_ROLE": "owner", "DJANGO_SETTINGS_MODULE": "collectiq.settings.test"}
    done = subprocess.run(
        [sys.executable, "manage.py", "migrate", "--noinput"],
        cwd=BACKEND, env=env, capture_output=True, text=True, check=False,
    )
    assert done.returncode == 0, done.stdout[-2000:] + done.stderr[-2000:]


def _truncate_all() -> None:
    """Clean up as owner: the app role cannot truncate, and that is the point."""
    with psycopg.connect(_owner_conninfo(TEST_DB), autocommit=True) as owner:
        tables = [row[0] for row in owner.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename <> 'django_migrations'"
        )]
        if tables:
            names = sql.SQL(", ").join(sql.Identifier(table) for table in tables)
            owner.execute(sql.SQL("TRUNCATE {} CASCADE").format(names))


@pytest.fixture
def pg(django_db_setup, django_db_blocker) -> Iterator[None]:
    """Real commits as the app role. Use this, not `django_db`: its wrapping atomic would hide resets."""
    with django_db_blocker.unblock():
        yield
    _truncate_all()
