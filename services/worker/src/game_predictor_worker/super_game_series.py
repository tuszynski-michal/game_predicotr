"""General-lane handler of the super game series derivation (TASK-0933, D-535).

The handler runs the API use case
:class:`game_predictor_api.application.super_game_series.SuperGameSeriesDerivation`
inside the game scope set by the job runtime.  Every batch is its own
transaction; only the final publication swaps the published series, so a
crash or restart leaves the published generation untouched and the next run
starts the generation over.  A candidate made stale by a concurrent input
change is rejected and one re-run stays queued; the job itself completes.
"""

from __future__ import annotations

from collections.abc import Callable

from game_predictor_api.application.super_game_series import (
    DerivationReport,
    SuperGameSeriesDerivation,
)
from game_predictor_api.domain.jobs import Job, JobType
from game_predictor_api.domain.super_game_series import SuperGameSeriesError
from game_predictor_api.storage.super_game_series_repository import (
    SqlAlchemySuperGameSeriesDerivationStore,
)
from sqlalchemy.orm import Session, sessionmaker

from game_predictor_worker.jobs.runtime import JobExecutionContext, JobHandlerError

_STAGE = "super_game_series_derive"
DerivationFactory = Callable[[], SuperGameSeriesDerivation]


def _report_payload(report: DerivationReport) -> dict[str, object]:
    return {
        "schema_version": 1,
        "workflow": _STAGE,
        "generation_id": str(report.generation_id),
        "status": report.status.value,
        "expected_input_version": report.expected_input_version,
        "current_input_version": report.current_input_version,
        "series_count": report.series_count,
        "trigger_board_count": report.trigger_board_count,
        "position_batch_count": report.position_batch_count,
        "inserted": report.inserted,
        "updated": report.updated,
        "removed": report.removed,
        "rerun_job_id": None if report.rerun_job_id is None else str(report.rerun_job_id),
    }


class SuperGameSeriesDeriveHandler:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        derivation_factory: DerivationFactory | None = None,
    ) -> None:
        self._derivation_factory = derivation_factory or (
            lambda: SuperGameSeriesDerivation(
                SqlAlchemySuperGameSeriesDerivationStore(session_factory)
            )
        )

    def __call__(self, context: JobExecutionContext, job: Job) -> None:
        if job.job_type is not JobType.SUPER_GAME_SERIES_DERIVE or job.game_id is None:
            raise JobHandlerError(
                "SUPER_GAME_SERIES_JOB_INVALID",
                "The super game series handler received another job type or no game.",
            )

        # Job progress counters must never decrease, so the final checkpoint
        # repeats the last reported position window instead of the series count.
        last_progress = {"current": 0, "total": 0}

        def progress(current: int, total: int, series_count: int) -> None:
            last_progress["current"] = max(last_progress["current"], current)
            last_progress["total"] = max(last_progress["total"], total)
            context.checkpoint(
                checkpoint_payload={
                    "schema_version": 1,
                    "workflow": _STAGE,
                    "positions_done": current,
                    "series_count": series_count,
                },
                stage=_STAGE,
                current=current,
                total=total,
                success_count=series_count,
                failure_count=0,
                review_count=0,
            )

        try:
            report = self._derivation_factory().derive(job.game_id, progress=progress)
        except SuperGameSeriesError as error:
            raise JobHandlerError(error.code, error.message) from error
        context.checkpoint(
            checkpoint_payload=_report_payload(report),
            stage=_STAGE,
            current=last_progress["current"],
            total=last_progress["total"],
            success_count=report.series_count,
            failure_count=0,
            review_count=0,
        )


__all__ = ["SuperGameSeriesDeriveHandler"]
