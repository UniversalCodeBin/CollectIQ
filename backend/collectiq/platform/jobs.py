"""Background jobs on Postgres: leases, backoff with jitter, dead-lettering (TSD 624, 676, 1054, 1056).

A job carries IDs only. A handler runs in its workspace's tenant_tx, marks its job done in that same
transaction, and must be idempotent: a job can run again after a lost lease.
"""
import json
import logging
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection

from .context import RequestContext
from .db import tenant_tx
from .errors import ProblemError
from .logging import bind_correlation_id

logger = logging.getLogger(__name__)

Handler = Callable[[RequestContext, dict[str, Any]], None]

DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_LEASE_SECONDS = 300
_BACKOFF_BASE_SECONDS = 30
_BACKOFF_MAX_SECONDS = 3600
_MAX_ID_LENGTH = 128

_handlers: dict[str, Handler] = {}
_random = secrets.SystemRandom()


class UnknownJobKind(Exception):
    """No handler is registered for this kind in this process."""


class _LeaseLost(Exception):
    """Another worker owns the job now, so this attempt must leave no trace."""


@dataclass(frozen=True, slots=True)
class Job:
    id: UUID
    workspace_id: UUID
    kind: str
    payload: dict[str, Any]
    attempts: int
    max_attempts: int
    lease_token: UUID
    correlation_id: str


def job_handler(kind: str) -> Callable[[Handler], Handler]:
    def register(handler: Handler) -> Handler:
        if kind in _handlers:
            raise ValueError(f"a handler is already registered for {kind}")
        _handlers[kind] = handler
        return handler

    return register


def _is_id(value: object) -> bool:
    if isinstance(value, str):
        return len(value) <= _MAX_ID_LENGTH
    return value is None or isinstance(value, bool | int | UUID)


def require_ids_only(payload: Mapping[str, Any]) -> None:
    """Job and event rows outlive their purpose, so content and amounts stay in the tables they belong to."""
    for name, value in payload.items():
        items = value if isinstance(value, list | tuple) else [value]
        if not all(_is_id(item) for item in items):
            raise ValueError(f"job payloads carry IDs only, and {name} is not one")


def enqueue(
    ctx: RequestContext,
    kind: str,
    payload: Mapping[str, Any],
    dedupe_key: str | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> UUID:
    """Adds a job in the caller's transaction. A dedupe key holds for the job's lifetime, finished or not."""
    if not connection.in_atomic_block:
        raise RuntimeError("enqueue must run inside the transaction of the change it follows")
    require_ids_only(payload)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO background_jobs
              (workspace_id, kind, payload, dedupe_key, max_attempts, correlation_id)
            VALUES (%s, %s, %s::jsonb, %s, %s, %s)
            ON CONFLICT (workspace_id, kind, dedupe_key) WHERE dedupe_key IS NOT NULL DO NOTHING
            RETURNING id
            """,
            [
                ctx.workspace_id,
                kind,
                json.dumps(payload, cls=DjangoJSONEncoder),
                dedupe_key,
                max_attempts,
                ctx.correlation_id,
            ],
        )
        row = cursor.fetchone()
        if row is None:
            cursor.execute(
                "SELECT id FROM background_jobs WHERE workspace_id = %s AND kind = %s AND dedupe_key = %s",
                [ctx.workspace_id, kind, dedupe_key],
            )
            row = cursor.fetchone()
    return row[0]


def backoff_seconds(attempt: int) -> float:
    return min(_BACKOFF_BASE_SECONDS * 2 ** (attempt - 1), _BACKOFF_MAX_SECONDS) * _random.uniform(0.5, 1.0)


def claim(lease_seconds: int = DEFAULT_LEASE_SECONDS) -> Job | None:
    if connection.in_atomic_block:
        raise RuntimeError("a claim commits by itself, so the lease outlives any handler failure")
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM claim_background_job(%s)", [lease_seconds])
        row = cursor.fetchone()
    if row is None:
        return None
    job_id, workspace_id, kind, payload, attempts, max_attempts, lease_token, correlation_id = row
    return Job(
        job_id, workspace_id, kind, json.loads(payload), attempts, max_attempts, lease_token, correlation_id
    )


def _mark_done(job: Job) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE background_jobs SET status = 'DONE', lease_until = NULL, lease_token = NULL,"
            " last_error = NULL, updated_at = now() WHERE id = %s AND lease_token = %s",
            [job.id, job.lease_token],
        )
        if cursor.rowcount == 0:
            raise _LeaseLost


def _error_label(exc: Exception) -> str:
    # The class or code only: an exception's message can carry row data (INV-12).
    return exc.code if isinstance(exc, ProblemError) else type(exc).__name__


def _record_failure(ctx: RequestContext, job: Job, exc: Exception) -> None:
    dead = job.attempts >= job.max_attempts
    delay = 0.0 if dead else backoff_seconds(job.attempts)
    label = _error_label(exc)
    with tenant_tx(ctx), connection.cursor() as cursor:
        cursor.execute(
            "UPDATE background_jobs SET status = %s, run_at = now() + make_interval(secs => %s),"
            " lease_until = NULL, lease_token = NULL, last_error = %s, updated_at = now()"
            " WHERE id = %s AND lease_token = %s",
            ["DEAD_LETTER" if dead else "QUEUED", delay, label, job.id, job.lease_token],
        )
        applied = cursor.rowcount > 0
    if applied:
        logger.log(
            logging.ERROR if dead else logging.WARNING,
            "job dead-lettered" if dead else "job failed and will retry",
            extra={"job_id": str(job.id), "kind": job.kind, "attempts": job.attempts, "error": label},
        )


def run_job(job: Job) -> None:
    ctx = RequestContext(
        workspace_id=job.workspace_id,
        user_id=None,
        role=None,
        correlation_id=job.correlation_id,
        actor_type="SYSTEM",
    )
    with bind_correlation_id(job.correlation_id):
        try:
            with tenant_tx(ctx):
                handler = _handlers.get(job.kind)
                if handler is None:
                    raise UnknownJobKind
                handler(ctx, job.payload)
                _mark_done(job)
        except _LeaseLost:
            logger.warning("job lease lost", extra={"job_id": str(job.id), "kind": job.kind})
        except Exception as exc:
            _record_failure(ctx, job, exc)


def run_once(lease_seconds: int = DEFAULT_LEASE_SECONDS) -> bool:
    job = claim(lease_seconds)
    if job is None:
        return False
    run_job(job)
    return True
