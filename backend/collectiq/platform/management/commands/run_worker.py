"""The background worker. SIGTERM finishes the current job and exits; a lease covers a harder stop."""
import logging
import signal
import threading
from typing import Any

from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils.module_loading import autodiscover_modules

from collectiq.platform import jobs, outbox  # noqa: F401  (outbox registers its dispatch handler)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Claim and run background jobs."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--drain", action="store_true", help="Exit once no job is due.")
        parser.add_argument("--poll-seconds", type=float, default=2.0)
        parser.add_argument("--lease-seconds", type=int, default=jobs.DEFAULT_LEASE_SECONDS)

    def handle(self, *args: Any, **options: Any) -> None:
        autodiscover_modules("jobs")
        stopping = threading.Event()
        previous = {
            number: signal.signal(number, lambda *_: stopping.set())
            for number in (signal.SIGTERM, signal.SIGINT)
        }
        try:
            while not stopping.is_set():
                close_old_connections()
                try:
                    ran = jobs.run_once(options["lease_seconds"])
                except Exception:
                    # Most likely the database is away. The job's lease brings it back.
                    logger.exception("worker iteration failed")
                    ran = False
                if not ran:
                    if options["drain"]:
                        return
                    stopping.wait(options["poll_seconds"])
        finally:
            for number, handler in previous.items():
                signal.signal(number, handler)
