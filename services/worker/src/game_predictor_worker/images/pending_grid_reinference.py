"""Retired pending-only grid and crop refresh (D-467 S6, TASK-0796).

Both payload versions of ``image_grid_reinference`` wrote v19 crop files for
the former file-crop boards only (schema 1: re-detected page grid, schema 2: the
accepted v19 source-direct recrop).  Since D-467 S6 every recognized board is
``virtual_source`` (migration 0135) and manual geometry goes through the
virtual render path, so the job has no input it may write.  The handler stays
registered so a queued or replayed historical job ends with an explicit code
instead of ``JOB_HANDLER_NOT_REGISTERED`` or a silent no-op.
"""

from __future__ import annotations

from pathlib import Path

from game_predictor_api.domain.jobs import Job
from sqlalchemy.orm import Session, sessionmaker

from game_predictor_worker.jobs.runtime import JobExecutionContext, JobHandlerError


class PendingGridReinferenceHandler:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        artifact_root: Path,
    ) -> None:
        self._session_factory = session_factory
        self._artifact_root = artifact_root.resolve()

    def __call__(self, context: JobExecutionContext, job: Job) -> None:
        schema_version = job.input_payload.get("schema_version")
        if schema_version not in {1, 2}:
            raise JobHandlerError(
                "IMAGE_GRID_REINFERENCE_SCHEMA_UNSUPPORTED",
                "The pending grid reinference schema is unsupported.",
            )
        raise JobHandlerError(
            "IMAGE_GRID_REINFERENCE_LEGACY_UNSUPPORTED",
            "Pending grid reinference wrote v19 crop files for legacy boards only; "
            "every board is virtual_source (D-467 S6). Correct the grid manually.",
        )


__all__ = ["PendingGridReinferenceHandler"]
