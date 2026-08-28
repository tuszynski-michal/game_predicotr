from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock
from uuid import UUID

from game_predictor_api.domain.jobs import JobStatus
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
    _candidate_values,
    _payload_from_records,
)
from game_predictor_api.storage.models import (
    CellObservationModel,
    ImageReviewItemModel,
    JobModel,
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


def test_rebuild_writes_fast_documents_directly_from_candidates() -> None:
    session = MagicMock()
    repository = SqlAlchemyBoardSearchProjectionRepository(session)

    repository._rebuild_fast_documents(UUID(int=90))

    statement = session.execute.call_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect())).lower()
    assert "insert into image_board_search_fast_documents" in sql
    assert "image_board_search_candidates" in sql
    assert "image_board_search_documents" not in sql
