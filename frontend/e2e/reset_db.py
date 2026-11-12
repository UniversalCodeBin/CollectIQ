"""Recreates the e2e run's own database, mirroring backend/tests/conftest.py (owner role, no superuser)."""
import os

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

NAME = "collectiq_e2e"
assert conninfo_to_dict(os.environ["MIGRATION_DATABASE_URL"])["dbname"] == NAME
maintenance = os.environ["E2E_MAINTENANCE_DATABASE_URL"]
assert conninfo_to_dict(maintenance)["dbname"] != NAME
with psycopg.connect(maintenance, autocommit=True) as admin:
    admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(NAME)))
    admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(NAME)))
with psycopg.connect(make_conninfo(maintenance, dbname=NAME), autocommit=True) as owner:
    owner.execute(
        """
        REVOKE ALL ON SCHEMA public FROM PUBLIC;
        GRANT USAGE ON SCHEMA public TO collectiq_app;
        ALTER DEFAULT PRIVILEGES FOR ROLE collectiq_owner IN SCHEMA public
          GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO collectiq_app;
        ALTER DEFAULT PRIVILEGES FOR ROLE collectiq_owner IN SCHEMA public
          GRANT USAGE, SELECT ON SEQUENCES TO collectiq_app;
        """
    )
