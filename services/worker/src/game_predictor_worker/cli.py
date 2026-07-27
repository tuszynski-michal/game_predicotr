"""Windows-friendly command line entry point for the local job worker."""

from __future__ import annotations

import argparse
import os
import socket
from collections.abc import Sequence
from datetime import timedelta

from game_predictor_api.config import ApiSettings
from game_predictor_api.storage.database import (
    create_database_engine,
    create_session_factory,
)

from game_predictor_worker.jobs.runtime import LocalJobWorker
from game_predictor_worker.jobs.store import SqlAlchemyWorkerJobStore

WORKER_VERSION = "worker-v1"


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local durable job worker.")
    parser.add_argument(
        "--poll",
        action="store_true",
        help="Continue polling instead of performing one claim attempt.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="Seconds between empty polling attempts.",
    )
    parser.add_argument(
        "--lease-seconds",
        type=int,
        default=60,
        help="Lease duration renewed by heartbeat/checkpoint.",
    )
    parser.add_argument(
        "--worker-id",
        default=f"{socket.gethostname()}-{os.getpid()}",
        help="Diagnostic owner stored with the lease.",
    )
    options = parser.parse_args(arguments)
    if not 5 <= options.lease_seconds <= 3600:
        parser.error("--lease-seconds must be between 5 and 3600.")
    if options.poll_interval <= 0:
        parser.error("--poll-interval must be positive.")

    settings = ApiSettings.from_environment()
    engine = create_database_engine(settings)
    store = SqlAlchemyWorkerJobStore(create_session_factory(engine))
    worker = LocalJobWorker(
        store,
        {},
        worker_id=options.worker_id,
        worker_version=WORKER_VERSION,
        lease_duration=timedelta(seconds=options.lease_seconds),
    )
    try:
        if options.poll:
            worker.run_forever(
                should_stop=lambda: False,
                poll_interval_seconds=options.poll_interval,
            )
            return 0
        result = worker.run_once()
        print(result.value)
        return 0
    except KeyboardInterrupt:
        return 130
    finally:
        engine.dispose()
