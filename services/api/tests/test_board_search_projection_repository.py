from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from game_predictor_api.domain.board_search import (
    BoardSearchCellDecision,
    BoardSearchCellEvidence,
    BoardSearchError,
    BoardSearchQueryCell,
    BoardSearchScope,
)
from game_predictor_api.domain.geometry_qualification import GeometryQualification
from game_predictor_api.domain.jobs import JobStatus
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
    _candidate_values,
    _cell_decision,
    _current_cell_decisions,
    _payload_from_records,
)
from game_predictor_api.storage.legacy_cell_observation_adapter import LegacyBaseCell
from game_predictor_api.storage.models import (
    GameModel,
    ImageBoardSearchProjectionStateModel,
    ImageReviewItemModel,
    JobModel,
    LegacyBoardSearchArchiveStateModel,
    RecognizedBoardModel,
    SourceImageModel,
)
from sqlalchemy.dialects import postgresql


def _records(
    *, status: str, resolved_value: dict[str, object] | None = None
) -> tuple[
    ImageReviewItemModel,
    RecognizedBoardModel,
    SourceImageModel,
    JobModel,
]:
    job = JobModel(id=UUID(int=1), game_id=UUID(int=2), status=JobStatus.WAITING_FOR_REVIEW)
    source = SourceImageModel(
        id=UUID(int=3),
        import_job_id=job.id,
        relative_path="seq_1-9.jpg",
        checksum_sha256="a" * 64,
        width=100,
        height=200,
    )
    board = RecognizedBoardModel(
        id=UUID(int=4),
        source_image_id=source.id,
        position_index=0,
        sequence_number_raw="1",
        sequence_number=1,
        sequence_confidence=1.0,
        board_geometry={},
        board_relative_path="boards/1.jpg",
        board_checksum_sha256="b" * 64,
        cells_prediction={},
        board_confidence=0.9,
        pipeline_fingerprint="c" * 64,
        asset_mode="legacy_file",
        status="pending_review",
    )
    item = ImageReviewItemModel(
        id=UUID(int=5),
        recognized_board_id=board.id,
        status=status,
        snapshot={},
        resolved_value=resolved_value,
        resolved_by=None if resolved_value is None else "operator",
        resolved_at=None,
        resolution_revision=0 if resolved_value is None else 1,
    )
    return item, board, source, job


def _import_predictions(
    board: RecognizedBoardModel, predictions: dict[int, dict[str, object]]
) -> None:
    """D-467: import predictions live in ``cells_prediction`` (one per cell)."""

    board.cells_prediction = {
        "cells": [
            {"rowIndex": index // 5, "columnIndex": index % 5, **prediction}
            for index, prediction in sorted(predictions.items())
        ],
        "modelVersion": "test-model",
    }


def test_pending_projection_uses_latest_prediction_shape_and_order() -> None:
    item, board, source, job = _records(status="pending")
    _import_predictions(
        board,
        {
            index: {
                "symbolCode": "lemon" if index else "seven",
                "alternatives": [{"symbolCode": "bell"}],
            }
            for index in range(15)
        },
    )

    payload = _payload_from_records(
        item=item,
        board=board,
        source=source,
        job=job,
        prediction_override=None,
    )

    assert payload is not None
    assert payload.candidate.sequence_number == 1
    assert payload.candidate.primary_symbol_codes[:2] == ("seven", "lemon")
    assert payload.candidate.alternative_symbol_codes[0] == ("bell",)
    assert payload.known_evidence_positions == tuple(str(index) for index in range(15))
    values = _candidate_values(payload, {"seven": 1, "lemon": 2, "bell": 3})
    assert cast(list[int | None], values["primary_symbol_mobile_codes"])[:2] == [1, 2]
    assert cast(list[int | None], values["alternative_rank_1_mobile_codes"])[:2] == [3, 3]


def test_pending_projection_overlays_current_cell_decisions() -> None:
    item, board, source, job = _records(status="pending")
    _import_predictions(
        board,
        {
            index: {"symbolCode": "seven", "alternatives": [{"symbolCode": "bell"}]}
            for index in range(15)
        },
    )

    payload = _payload_from_records(
        item=item,
        board=board,
        source=source,
        job=job,
        prediction_override=None,
        cell_decisions=(
            BoardSearchCellDecision(
                cell_index=0,
                evidence=BoardSearchCellEvidence.VERIFIED,
                symbol_code="lemon",
            ),
            BoardSearchCellDecision(cell_index=1, evidence=BoardSearchCellEvidence.WITHHELD),
        ),
    )

    assert payload is not None
    assert payload.candidate.status == "pending"
    assert payload.candidate.primary_symbol_codes[:3] == ("lemon", None, "seven")
    assert payload.candidate.alternative_symbol_codes[:3] == ((), (), ("bell",))
    assert "1" not in payload.known_evidence_positions
    values = _candidate_values(payload, {"seven": 1, "lemon": 2, "bell": 3})
    assert cast(list[int | None], values["primary_symbol_mobile_codes"])[:3] == [2, None, 1]


def test_resolved_projection_uses_human_symbols_and_discards_predictions() -> None:
    symbols = ["seven"] + ["lemon"] * 14
    item, board, source, job = _records(
        status="corrected",
        resolved_value={"sequenceNumber": 20, "symbolCodes": symbols},
    )

    payload = _payload_from_records(
        item=item,
        board=board,
        source=source,
        job=job,
        prediction_override=({"symbolCode": "wrong", "alternatives": [{"symbolCode": "seven"}]},)
        * 15,
    )

    assert payload is not None
    assert payload.candidate.sequence_number == 20
    assert payload.candidate.primary_symbol_codes == tuple(symbols)
    assert payload.candidate.alternative_symbol_codes == ((),) * 15
    assert payload.known_evidence_positions == tuple(str(index) for index in range(15))


def test_resolved_projection_preserves_unknown_as_missing_evidence() -> None:
    symbols: list[str | None] = ["seven", None, *(["lemon"] * 13)]
    item, board, source, job = _records(
        status="corrected",
        resolved_value={"sequenceNumber": 20, "symbolCodes": symbols},
    )

    payload = _payload_from_records(
        item=item,
        board=board,
        source=source,
        job=job,
        prediction_override=None,
    )

    assert payload is not None
    assert payload.candidate.primary_symbol_codes[1] is None
    assert "1" not in payload.known_evidence_positions
    values = _candidate_values(payload, {"seven": 1, "lemon": 2})
    assert cast(list[int | None], values["primary_symbol_mobile_codes"])[1] is None


def test_incomplete_pending_predictions_do_not_create_search_evidence() -> None:
    item, board, source, job = _records(status="pending")

    payload = _payload_from_records(
        item=item,
        board=board,
        source=source,
        job=job,
        prediction_override=(),
    )

    assert payload is None


@pytest.mark.parametrize("missing", [(0, 5, 10), tuple(range(15))])
def test_qualified_pending_projection_preserves_every_logical_position(missing) -> None:
    item, board, source, job = _records(status="pending")
    _as_virtual(board)
    board.geometry_revision = 0
    board.geometry_qualification = GeometryQualification(
        "pending_partial", missing, True, "missing_pixels"
    ).to_dict()
    board.completeness_status = "pending_partial"
    board.unavailable_cell_indices = list(missing)
    _import_predictions(
        board,
        {
            index: {"symbolCode": f"symbol-{index}", "alternatives": []}
            for index in range(15)
            if index not in missing
        },
    )
    payload = _payload_from_records(
        item=item,
        board=board,
        source=source,
        job=job,
        prediction_override=None,
    )
    assert payload is not None
    assert payload.candidate.primary_symbol_codes == tuple(
        None if i in missing else f"symbol-{i}" for i in range(15)
    )
    assert all(payload.candidate.alternative_symbol_codes[i] == () for i in missing)


def _as_virtual(board: RecognizedBoardModel) -> None:
    board.asset_mode = "virtual_source"
    board.board_relative_path = None
    board.board_checksum_sha256 = None
    board.geometry_checksum_sha256 = "d" * 64


def test_revision_zero_legacy_board_reads_base_cells_through_the_legacy_adapter() -> None:
    """D-467: only a revision-0 legacy board still uses its base observations."""

    item, board, source, job = _records(status="pending")
    board.geometry_revision = 0
    board.cells_prediction = {"cells": []}
    cells = tuple(
        LegacyBaseCell(
            row_index=index // 5,
            column_index=index % 5,
            crop_relative_path=f"cells/{index}.png",
            crop_checksum_sha256=f"{index:064x}",
            cropper_version="v19",
            prediction={"symbolCode": f"symbol-{index}", "alternatives": []},
        )
        for index in range(15)
    )
    payload = _payload_from_records(
        item=item,
        board=board,
        source=source,
        job=job,
        prediction_override=None,
        legacy_base_cells=cells,
    )
    assert payload is not None
    assert payload.candidate.primary_symbol_codes == tuple(f"symbol-{i}" for i in range(15))
    # Without base cells the legacy board has no search evidence.
    assert (
        _payload_from_records(
            item=item, board=board, source=source, job=job, prediction_override=None
        )
        is None
    )


def _partial_board(missing: tuple[int, ...], *, geometry_revision: int):
    item, board, source, job = _records(status="pending")
    board.geometry_revision = geometry_revision
    board.geometry_qualification = GeometryQualification(
        "pending_partial", missing, True, "missing_pixels"
    ).to_dict()
    board.completeness_status = "pending_partial"
    board.unavailable_cell_indices = list(missing)
    return item, board, source, job


def test_qualified_projection_ignores_observations_of_masked_positions() -> None:
    """TASK-0730: the worker observes all 15 positions before masking some."""

    missing = (4, 9, 14)
    item, board, source, job = _partial_board(missing, geometry_revision=0)
    _as_virtual(board)
    predictions: dict[int, dict[str, object]] = {
        index: {
            "symbolCode": f"symbol-{index}",
            "alternatives": [{"symbolCode": "other", "confidence": 0.1}],
        }
        for index in range(15)
    }
    _import_predictions(board, predictions)

    payload = _payload_from_records(
        item=item,
        board=board,
        source=source,
        job=job,
        prediction_override=None,
    )

    assert payload is not None
    # A board cut on the right keeps its visible left reels as evidence.
    assert payload.candidate.primary_symbol_codes == tuple(
        None if i in missing else f"symbol-{i}" for i in range(15)
    )
    assert all(payload.candidate.alternative_symbol_codes[i] == () for i in missing)
    assert payload.candidate.alternative_symbol_codes[0] == ("other",)
    # A visible position without an import prediction still fails closed.
    del predictions[0]
    _import_predictions(board, predictions)
    assert (
        _payload_from_records(
            item=item,
            board=board,
            source=source,
            job=job,
            prediction_override=None,
        )
        is None
    )


def test_qualified_legacy_revision_uses_its_own_current_crops() -> None:
    """TASK-0730: a manual legacy revision has crops, not a virtual manifest."""

    from game_predictor_api.storage.models import ImageBoardGeometryRevisionModel

    missing = (0, 5, 10)
    item, board, source, job = _partial_board(missing, geometry_revision=1)

    def revision_with_crops(indices: range | list[int]) -> ImageBoardGeometryRevisionModel:
        return ImageBoardGeometryRevisionModel(
            asset_mode="legacy_file",
            virtual_render_spec=None,
            crop_artifacts=[
                {
                    "rowIndex": index // 5,
                    "columnIndex": index % 5,
                    "cropChecksumSha256": f"{index + 100:064x}",
                }
                for index in indices
            ],
        )

    revision = revision_with_crops(range(15))
    _import_predictions(
        board, {index: {"symbolCode": f"symbol-{index}", "alternatives": []} for index in range(15)}
    )

    payload = _payload_from_records(
        item=item,
        board=board,
        source=source,
        job=job,
        prediction_override=None,
        geometry_revision=revision,
    )
    assert payload is not None
    assert payload.candidate.primary_symbol_codes == tuple(
        None if i in missing else f"symbol-{i}" for i in range(15)
    )
    # D-467: a visible position without a current revision crop is never
    # evidence (it replaces the former stale-observation comparison).
    assert (
        _payload_from_records(
            item=item,
            board=board,
            source=source,
            job=job,
            prediction_override=None,
            geometry_revision=revision_with_crops([i for i in range(15) if i != 7]),
        )
        is None
    )
    # Like an unqualified legacy board, a prediction revision overrides the
    # import predictions of visible positions only; masked ones stay unknown.
    overridden = _payload_from_records(
        item=item,
        board=board,
        source=source,
        job=job,
        prediction_override=[
            {"rowIndex": i // 5, "columnIndex": i % 5, "symbolCode": "new", "alternatives": []}
            for i in range(15)
        ],
        geometry_revision=revision,
    )
    assert overridden is not None
    assert overridden.candidate.primary_symbol_codes == tuple(
        None if i in missing else "new" for i in range(15)
    )
    # The legacy crop path never applies to a virtual-source board.
    board.asset_mode = "virtual_source"
    assert (
        _payload_from_records(
            item=item,
            board=board,
            source=source,
            job=job,
            prediction_override=None,
            geometry_revision=revision,
        )
        is None
    )


def test_qualified_revised_projection_never_reuses_original_pixel_predictions() -> None:
    from game_predictor_api.storage.models import ImageBoardGeometryRevisionModel

    item, board, source, job = _records(status="pending")
    board.geometry_revision = 2
    board.geometry_qualification = GeometryQualification(
        "pending_partial", (0,), True, "missing_pixels"
    ).to_dict()
    board.completeness_status, board.unavailable_cell_indices = "pending_partial", [0]
    revision = ImageBoardGeometryRevisionModel(
        virtual_render_spec={
            "cells": [
                {"cellIndex": i, "renderSpecChecksumSha256": f"{i:064x}"} for i in range(1, 15)
            ]
        }
    )
    predictions = [
        {
            "rowIndex": i // 5,
            "columnIndex": i % 5,
            "symbolCode": "old",
            "alternatives": [],
            "virtualCell": {"renderSpecChecksumSha256": "f" * 64},
        }
        for i in range(15)
    ]
    predictions[7]["virtualCell"] = {"renderSpecChecksumSha256": f"{7:064x}"}
    payload = _payload_from_records(
        item=item,
        board=board,
        source=source,
        job=job,
        prediction_override=predictions,
        geometry_revision=revision,
    )
    assert payload is not None
    assert payload.candidate.primary_symbol_codes == (None,) * 7 + ("old",) + (None,) * 7


def test_rebuild_writes_fast_documents_directly_from_candidates() -> None:
    session = MagicMock()
    repository = SqlAlchemyBoardSearchProjectionRepository(session)

    repository._rebuild_fast_documents(UUID(int=90))

    statement = session.execute.call_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect())).lower()
    assert "insert into image_board_search_fast_documents" in sql
    assert "image_board_search_candidates" in sql
    assert "image_board_search_documents" not in sql


def _search_session(*, archive_status: str | None) -> MagicMock:
    session = MagicMock()

    def get(model: object, _identity: object) -> object | None:
        if model is GameModel:
            return object()
        if model is LegacyBoardSearchArchiveStateModel:
            return None if archive_status is None else SimpleNamespace(status=archive_status)
        if model is ImageBoardSearchProjectionStateModel:
            return SimpleNamespace(
                status="ready",
                candidate_count=1,
                document_count=1,
                skipped_review_item_count=0,
                failure_message=None,
                game_id=UUID(int=2),
            )
        raise AssertionError(f"Unexpected model lookup: {model}")

    session.get.side_effect = get
    symbols = MagicMock()
    symbols.tuples.return_value = [("cherry", 1)]
    results = MagicMock()
    results.all.return_value = []
    session.execute.side_effect = [symbols, results]
    return session


def test_ready_archive_search_does_not_join_operational_review_tables() -> None:
    session = _search_session(archive_status="ready")
    repository = SqlAlchemyBoardSearchProjectionRepository(session)

    assert (
        repository.search(
            game_id=UUID(int=2),
            query=(BoardSearchQueryCell(0, "cherry"),),
            scope=BoardSearchScope.ALL_SEARCHABLE,
            limit=10,
        )
        == ()
    )

    sql = str(session.execute.call_args_list[1].args[0].compile(dialect=postgresql.dialect()))
    assert "legacy_board_search_archive_documents" in sql
    assert "image_board_search_fast_documents" not in sql
    assert "image_review_items" not in sql
    assert "recognized_boards" not in sql


def test_missing_archive_preserves_operational_fast_document_search() -> None:
    session = _search_session(archive_status=None)
    repository = SqlAlchemyBoardSearchProjectionRepository(session)

    assert (
        repository.search(
            game_id=UUID(int=2),
            query=(BoardSearchQueryCell(0, "cherry"),),
            scope=BoardSearchScope.ALL_SEARCHABLE,
            limit=10,
        )
        == ()
    )

    sql = str(session.execute.call_args_list[1].args[0].compile(dialect=postgresql.dialect()))
    assert "image_board_search_fast_documents" in sql
    assert "legacy_board_search_archive_documents" not in sql


def test_partial_archive_fails_closed_instead_of_falling_back() -> None:
    session = _search_session(archive_status="building")
    repository = SqlAlchemyBoardSearchProjectionRepository(session)

    with pytest.raises(BoardSearchError) as error:
        repository.search(
            game_id=UUID(int=2),
            query=(BoardSearchQueryCell(0, "cherry"),),
            scope=BoardSearchScope.ALL_SEARCHABLE,
            limit=10,
        )
    assert error.value.code == "BOARD_SEARCH_ARCHIVE_INCOMPLETE"
    session.execute.assert_not_called()


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        # A verified cell is exact evidence, including a logical `?`.
        (dict(review_state="approved", symbol_code="lemon"), ("verified", "lemon")),
        (
            dict(review_state="approved", quality_issue="blurry", symbol_code="bell"),
            ("verified", "bell"),
        ),
        (dict(review_state="approved", quality_issue="unreadable"), ("verified", None)),
        # R10: an approval of other pixels than the current ones is no evidence.
        (dict(review_state="approved", symbol_code="lemon", approval_pixels_changed=True), None),
        # Reported pending problems withhold the model suggestion.
        (dict(quality_issue="grid_issue"), ("withheld", None)),
        (dict(quality_issue="unreadable"), ("withheld", None)),
        (dict(quality_issue="partial_visibility"), ("withheld", None)),
        (dict(quality_issue="blurry"), None),
        (dict(), None),
        # Without source pixels only an approved logical `outside` is evidence.
        (
            dict(
                review_state="approved",
                symbol_code="seven",
                has_source_pixels=False,
                is_outside=True,
            ),
            ("verified", "seven"),
        ),
        (dict(has_source_pixels=False, is_outside=True), ("withheld", None)),
        (
            dict(
                review_state="approved",
                symbol_code="seven",
                has_source_pixels=False,
                is_outside=True,
                approval_pixels_changed=True,
            ),
            ("withheld", None),
        ),
        (
            dict(review_state="approved", symbol_code="seven", has_source_pixels=False),
            ("withheld", None),
        ),
    ],
)
def test_cell_decision_classifies_current_rows_for_pending_search(
    state: dict[str, object], expected: tuple[str, str | None] | None
) -> None:
    arguments: dict[str, object] = {
        "cell_index": 4,
        "review_state": "pending",
        "quality_issue": None,
        "has_source_pixels": True,
        "is_outside": False,
        "approval_pixels_changed": False,
        "symbol_code": None,
    }
    arguments.update(state)

    decision = _cell_decision(**arguments)  # type: ignore[arg-type]

    if expected is None:
        assert decision is None
    else:
        assert decision is not None
        assert decision.cell_index == 4
        assert (decision.evidence.value, decision.symbol_code) == expected


def test_current_cell_decisions_ignore_foreign_boards_and_stale_revisions() -> None:
    item, board, source, job = _records(status="pending")
    board.geometry_revision = 2
    other_board = UUID(int=99)

    def row(cell_index: int, recognized_board_id: UUID, geometry_revision: int) -> tuple:
        return (
            item.id,
            recognized_board_id,
            cell_index,
            "approved",
            None,
            True,
            "full",
            geometry_revision,
            "legacy_file",
            "c" * 64,
            "c" * 64,
            None,
            None,
            "lemon",
        )

    session = MagicMock()
    session.execute.return_value.tuples.return_value = [
        row(0, board.id, 2),
        row(1, other_board, 2),
        row(2, board.id, 1),
    ]

    decisions = _current_cell_decisions(session, ((item, board, source, job),))

    assert [decision.cell_index for decision in decisions[item.id]] == [0]


def test_current_cell_decisions_skip_resolved_items_without_querying() -> None:
    item, board, source, job = _records(
        status="corrected",
        resolved_value={"sequenceNumber": 1, "symbolCodes": ["seven"] * 15},
    )
    session = MagicMock()

    assert _current_cell_decisions(session, ((item, board, source, job),)) == {}
    session.execute.assert_not_called()
