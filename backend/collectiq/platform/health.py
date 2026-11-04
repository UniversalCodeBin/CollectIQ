"""Readiness: can this process reach the database with its schema in place. Says nothing else."""
from django.db import DatabaseError, connection


def check_ready() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.execute("SELECT 1 FROM background_jobs LIMIT 0")
    except DatabaseError:
        return False
    return True
