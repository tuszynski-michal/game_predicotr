"""Worker handler of the super game series derivation (TASK-0933)."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from game_predictor_api.application.super_game_series import (
    DerivationReport,
    PublicationStatus,
)
from game_predictor_api.domain.jobs import JobType, create_job
from game_predictor_api.domain.super_game_series import SuperGameSeriesError
from game_predictor_worker.jobs.runtime import JobHandlerError
from game_predictor_worker.super_game_series import SuperGameSeriesDeriveHandler


class _Context:
    def __init__(self) -> None:
        self.checkpoints: list[dict[str, object]] = []

    def checkpoint(self, **values: object) -> None:
        self.checkpoints.append(values)


class _Derivation:
    def __init__(
        self, *, fail: bool = False, status: PublicationStatus = PublicationStatus.PUBLISHED
    ) -> None:
        self.fail = fail
        self.status = status
        self.game_ids: list[UUID] = []

    def derive(
        self, game_id: UUID, *, progress: Callable[[int, int, int], None] | None = None
    ) -> DerivationReport:
        self.game_ids.append(game_id)
        if self.fail:
            raise SuperGameSeriesError("GAME_NOT_FOUND", "Game does not exist.")
        assert progress is not None
        progress(5_000, 10_000, 2)
        progress(10_000, 10_000, 3)
        return DerivationReport(
            game_id=game_id,
            generation_id=uuid4(),
            status=self.status,
            expected_input_version=4,
            current_input_version=4 if self.status is PublicationStatus.PUBLISHED else 5,
            series_count=3,
            trigger_board_count=4,
            position_batch_count=2,
            inserted=3,
            updated=0,
            removed=0,
            rerun_job_id=None if self.status is PublicationStatus.PUBLISHED else uuid4(),
        )


def _job() -> object:
    return create_job(
        JobType.SUPER_GAME_SERIES_DERIVE,
        game_id=uuid4(),
        input_payload={"schema_version": 1, "reason": "manual", "request_id": str(uuid4())},
    )


def test_handler_reports_progress_and_final_generation() -> None:
    derivation = _Derivation()
    handler = SuperGameSeriesDeriveHandler(object(), derivation_factory=lambda: derivation)  # type: ignore[arg-type]
    context = _Context()
    job = _job()
    handler(context, job)  # type: ignore[arg-type]
    assert derivation.game_ids == [job.game_id]  # type: ignore[attr-defined]
    # Counters never decrease (JOB_PROGRESS_REGRESSION): the final checkpoint
    # keeps the last position window, the series count goes to success_count.
    assert [item["current"] for item in context.checkpoints] == [5_000, 10_000, 10_000]
    assert [item["total"] for item in context.checkpoints] == [10_000, 10_000, 10_000]
    assert context.checkpoints[-1]["success_count"] == 3
    currents = [int(item["current"]) for item in context.checkpoints]
    assert currents == sorted(currents)
    final = context.checkpoints[-1]["checkpoint_payload"]
    assert isinstance(final, dict)
    assert final["status"] == "published" and final["series_count"] == 3


def test_rejected_candidate_completes_the_job_with_rerun_reference() -> None:
    derivation = _Derivation(status=PublicationStatus.REJECTED)
    handler = SuperGameSeriesDeriveHandler(object(), derivation_factory=lambda: derivation)  # type: ignore[arg-type]
    context = _Context()
    handler(context, _job())  # type: ignore[arg-type]
    final = context.checkpoints[-1]["checkpoint_payload"]
    assert isinstance(final, dict)
    assert final["status"] == "rejected" and final["rerun_job_id"] is not None


def test_domain_error_fails_the_job_with_its_code() -> None:
    handler = SuperGameSeriesDeriveHandler(
        object(),  # type: ignore[arg-type]
        derivation_factory=lambda: _Derivation(fail=True),  # type: ignore[arg-type,return-value]
    )
    with pytest.raises(JobHandlerError) as error:
        handler(_Context(), _job())  # type: ignore[arg-type]
    assert error.value.code == "GAME_NOT_FOUND"


def test_handler_rejects_other_job_types() -> None:
    handler = SuperGameSeriesDeriveHandler(object(), derivation_factory=_Derivation)  # type: ignore[arg-type]
    other = create_job(JobType.STORAGE_INVENTORY, game_id=None, input_payload={"schema_version": 1})
    with pytest.raises(JobHandlerError):
        handler(_Context(), other)  # type: ignore[arg-type]
