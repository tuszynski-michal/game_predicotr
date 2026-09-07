from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from game_predictor_api.domain.board_search import (
    BoardSearchError,
    BoardSearchQueryCell,
    BoardSearchScope,
)
from game_predictor_api.domain.geometry_qualification import GeometryQualification
from game_predictor_api.domain.jobs import JobStatus
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
    _candidate_values,
    _payload_from_records,
)
from game_predictor_api.storage.models import (
    CellObservationModel,
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


def test_pending_projection_uses_latest_prediction_shape_and_order() -> None:
    item, board, source, job = _records(status="pending")
    observations = tuple(
        CellObservationModel(
            recognized_board_id=board.id,
            row_index=index // 5,
            column_index=index % 5,
            crop_relative_path=f"cells/{index}.jpg",
            crop_checksum_sha256=f"{index:064x}",
            cropper_version="v19",
            prediction={
                "symbolCode": "lemon" if index else "seven",
                "alternatives": [{"symbolCode": "bell"}],
            },
        )
        for index in range(15)
    )

    payload = _payload_from_records(
        item=item,
        board=board,
        source=source,
        job=job,
        observations=observations,
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
        observations=(),
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
        observations=(),
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
        observations=(),
        prediction_override=(),
    )

    assert payload is None


@pytest.mark.parametrize("missing", [(0, 5, 10), tuple(range(15))])
def test_qualified_pending_projection_preserves_every_logical_position(missing) -> None:
    item, board, source, job = _records(status="pending")
    board.geometry_revision = 0
    board.geometry_qualification = GeometryQualification(
        "pending_partial", missing, True, "missing_pixels"
    ).to_dict()
    board.completeness_status = "pending_partial"
    board.unavailable_cell_indices = list(missing)
    observations = [
        CellObservationModel(
            row_index=index // 5,
            column_index=index % 5,
            prediction={"symbolCode": f"symbol-{index}", "alternatives": []},
        )
        for index in range(15)
        if index not in missing
    ]
    payload = _payload_from_records(
        item=item,
        board=board,
        source=source,
        job=job,
        observations=observations,
        prediction_override=None,
    )
    assert payload is not None
    assert payload.candidate.primary_symbol_codes == tuple(
        None if i in missing else f"symbol-{i}" for i in range(15)
    )
    assert all(payload.candidate.alternative_symbol_codes[i] == () for i in missing)


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
        observations=(),
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
