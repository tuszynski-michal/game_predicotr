"""TASK-0945: pure rules and the service contract of the geometry correction revert."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from game_predictor_api.application.geometry_correction_reverts import (
    GeometryCorrectionEntry,
    GeometryCorrectionRevertService,
)
from game_predictor_api.domain.geometry_correction_reverts import (
    BLOCKING_REASON_MESSAGES,
    GeometryCorrectionKind,
    RevertBlockingReason,
    RevertEligibilityFacts,
    evaluate_revert_eligibility,
    image_admission_blocks_revert,
    predicted_status_after_slot_revert,
    snapshot_checksum_sha256,
)
from game_predictor_api.domain.image_geometry_completeness import SourceImageGeometryStatus
from game_predictor_api.domain.image_reviews import ImageReviewError

INCOMPLETE = SourceImageGeometryStatus.GEOMETRY_INCOMPLETE
COMPLETE = SourceImageGeometryStatus.GEOMETRY_COMPLETE
EXCEPTION = SourceImageGeometryStatus.GEOMETRY_EXCEPTION

ELIGIBLE = RevertEligibilityFacts(
    kind=GeometryCorrectionKind.PENDING_SLOT,
    latest_board_revision=True,
    cas_matches=True,
    source_revision_newest_live=True,
    source_revision_shared=False,
    cells_changed_after_correction=False,
    review_resolved=False,
    sequence_ownership_changed=False,
    image_status_before=INCOMPLETE,
    image_status_after=INCOMPLETE,
    pinned=False,
    reopened_resolution=False,
    revert_supported=True,
)

# One violation per code of the plan's table, in the table's order.
VIOLATIONS: tuple[tuple[RevertBlockingReason, dict[str, Any]], ...] = (
    (RevertBlockingReason.NOT_LATEST, {"latest_board_revision": False}),
    (RevertBlockingReason.STALE, {"cas_matches": False}),
    (RevertBlockingReason.SOURCE_ADVANCED, {"source_revision_newest_live": False}),
    (RevertBlockingReason.SHARED_SOURCE_REVISION, {"source_revision_shared": True}),
    (RevertBlockingReason.CELLS_CHANGED, {"cells_changed_after_correction": True}),
    (RevertBlockingReason.RESOLVED, {"review_resolved": True}),
    (RevertBlockingReason.SEQUENCE_OWNERSHIP, {"sequence_ownership_changed": True}),
    (
        RevertBlockingReason.IMAGE_ADMITTED,
        {"image_status_before": COMPLETE, "image_status_after": INCOMPLETE},
    ),
    (RevertBlockingReason.PINNED, {"pinned": True}),
    (RevertBlockingReason.REOPENED_RESOLUTION, {"reopened_resolution": True}),
    (RevertBlockingReason.NOT_SUPPORTED, {"revert_supported": False}),
)


def test_an_unchanged_correction_is_revertable_with_or_without_cas() -> None:
    assert evaluate_revert_eligibility(ELIGIBLE) is None
    assert evaluate_revert_eligibility(replace(ELIGIBLE, cas_matches=None)) is None


@pytest.mark.parametrize(("reason", "change"), VIOLATIONS, ids=lambda value: str(value))
def test_every_blocking_code_refuses_on_its_own(
    reason: RevertBlockingReason, change: dict[str, Any]
) -> None:
    assert evaluate_revert_eligibility(replace(ELIGIBLE, **change)) is reason
    assert BLOCKING_REASON_MESSAGES[reason]


def test_the_first_failing_rule_of_the_table_wins() -> None:
    every = ELIGIBLE
    for _reason, change in VIOLATIONS:
        every = replace(every, **change)
    assert evaluate_revert_eligibility(every) is RevertBlockingReason.NOT_LATEST
    for index, (reason, _change) in enumerate(VIOLATIONS):
        facts = ELIGIBLE
        for _later, change in VIOLATIONS[index:]:
            facts = replace(facts, **change)
        assert evaluate_revert_eligibility(facts) is reason


def test_every_code_has_a_polish_message() -> None:
    assert set(BLOCKING_REASON_MESSAGES) == set(RevertBlockingReason)


@pytest.mark.parametrize(
    ("before", "after"),
    [(None, None), (INCOMPLETE, INCOMPLETE), (EXCEPTION, EXCEPTION), (COMPLETE, INCOMPLETE)],
)
def test_reopened_slot_keeps_an_exception_and_makes_a_complete_image_incomplete(
    before: SourceImageGeometryStatus | None, after: SourceImageGeometryStatus | None
) -> None:
    assert predicted_status_after_slot_revert(before) is after


def test_only_an_admitted_image_that_would_change_blocks_the_revert() -> None:
    assert image_admission_blocks_revert(COMPLETE, INCOMPLETE)
    assert image_admission_blocks_revert(EXCEPTION, INCOMPLETE)
    assert not image_admission_blocks_revert(EXCEPTION, EXCEPTION)
    assert not image_admission_blocks_revert(COMPLETE, COMPLETE)
    assert not image_admission_blocks_revert(INCOMPLETE, INCOMPLETE)
    assert not image_admission_blocks_revert(None, INCOMPLETE)


def test_snapshot_checksum_is_canonical() -> None:
    first = {"b": [1, {"y": "ż", "x": None}], "a": "2026-10-09T08:39:41.29291+00:00"}
    second = {"a": "2026-10-09T08:39:41.29291+00:00", "b": [1, {"x": None, "y": "ż"}]}
    assert snapshot_checksum_sha256(first) == snapshot_checksum_sha256(second)
    assert len(snapshot_checksum_sha256(first)) == 64
    assert snapshot_checksum_sha256(first) != snapshot_checksum_sha256({**first, "c": 0})


class _Repository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def list_recent(self, **kwargs: Any) -> tuple[GeometryCorrectionEntry, ...]:
        self.calls.append(("list_recent", kwargs))
        return ()

    def preview(self, **kwargs: Any) -> Any:
        self.calls.append(("preview", kwargs))
        return "preview"

    def revert(self, **kwargs: Any) -> Any:
        self.calls.append(("revert", kwargs))
        return "result"


def _revert(service: GeometryCorrectionRevertService, **overrides: Any) -> Any:
    values: dict[str, Any] = {
        "game_id": uuid4(),
        "import_job_id": uuid4(),
        "board_geometry_revision_id": uuid4(),
        "idempotency_key": uuid4(),
        "expected_geometry_revision": 1,
        "expected_resolution_revision": 0,
        "actor": "  reviewer-operator ",
        "reverted_at": datetime(2026, 10, 9, tzinfo=UTC),
    }
    values.update(overrides)
    return service.revert(**values)


def test_service_validates_requests_before_the_repository() -> None:
    repository = _Repository()
    service = GeometryCorrectionRevertService(repository)  # type: ignore[arg-type]
    game_id: UUID = uuid4()
    import_job_id: UUID = uuid4()
    assert service.list_recent(game_id=game_id, import_job_id=import_job_id) == ()
    assert repository.calls[-1][1]["limit"] == 20
    service.list_recent(game_id=game_id, import_job_id=import_job_id, limit=50)
    for limit in (0, 51, True):
        with pytest.raises(ImageReviewError, match="limit") as error:
            service.list_recent(game_id=game_id, import_job_id=import_job_id, limit=limit)
        assert error.value.code == "GEOMETRY_REVERT_REQUEST_INVALID"

    assert _revert(service) == "result"
    assert repository.calls[-1][1]["actor"] == "reviewer-operator"
    calls = len(repository.calls)
    for override in (
        {"actor": "   "},
        {"actor": "x" * 201},
        {"expected_geometry_revision": -1},
        {"expected_resolution_revision": True},
    ):
        with pytest.raises(ImageReviewError) as error:
            _revert(service, **override)
        assert error.value.code == "GEOMETRY_REVERT_REQUEST_INVALID"
    assert len(repository.calls) == calls


def test_entry_exposes_revertable_and_the_reason_message() -> None:
    entry = GeometryCorrectionEntry(
        board_geometry_revision_id=uuid4(),
        kind=GeometryCorrectionKind.BOARD_REVISION,
        recognized_board_id=uuid4(),
        review_item_id=uuid4(),
        pending_geometry_id=None,
        source_image_id=uuid4(),
        sequence_number=69004,
        position_index=0,
        created_at=datetime(2026, 10, 9, tzinfo=UTC),
        actor="reviewer-operator",
        geometry_revision=2,
        resolution_revision=0,
        blocking_reason=RevertBlockingReason.NOT_SUPPORTED,
    )
    assert entry.revertable is False
    assert (
        entry.blocking_reason_message
        == BLOCKING_REASON_MESSAGES[RevertBlockingReason.NOT_SUPPORTED]
    )
    assert replace(entry, blocking_reason=None).revertable is True
    assert replace(entry, blocking_reason=None).blocking_reason_message is None
