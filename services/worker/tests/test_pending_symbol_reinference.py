from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from game_predictor_api.domain.geometry_qualification import GeometryQualification
from game_predictor_api.storage.models import ImageBoardGeometryRevisionModel
from game_predictor_worker.images.pending_symbol_reinference import (
    PendingSymbolReinferenceHandler,
    _available_indices,
    _checkpoint_payload,
    _virtual_records,
)
from game_predictor_worker.jobs.runtime import JobHandlerError
from sqlalchemy.dialects import postgresql


def test_explicit_reinference_includes_qualified_pending_from_completed_import(tmp_path):
    session = MagicMock()
    session.execute.return_value.tuples.return_value.all.return_value = []
    factory = MagicMock()
    factory.return_value.__enter__.return_value = session
    handler = PendingSymbolReinferenceHandler(factory, tmp_path, tmp_path)
    assert handler._pending_rows(uuid4()) == []
    query = str(
        session.execute.call_args.args[0].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "geometry_qualification IS NOT NULL" in query
    assert "completed" in query and "waiting_for_review" in query
    assert "image_symbol_review_cells.review_state = 'pending'" in query
    assert "image_review_items.status IN ('pending', 'accepted', 'corrected')" in query
    assert "image_board_search_fast_documents" not in query


def test_pending_symbol_checkpoint_uses_the_runtime_schema() -> None:
    payload = _checkpoint_payload(processed=7, skipped=2)

    assert payload == {
        "schema_version": 1,
        "kind": "pending-symbol-reinference-v1",
        "processed": 7,
        "skippedConcurrentResolution": 2,
    }


def test_qualified_reinference_keeps_empty_slot_without_fake_records():
    qualification = GeometryQualification(
        "pending_partial", tuple(range(15)), True, "missing_pixels"
    )
    indices = _available_indices(qualification.to_dict())
    assert indices == ()
    revision = ImageBoardGeometryRevisionModel(
        asset_mode="virtual_source", virtual_render_spec={"cells": []}
    )
    assert _virtual_records(observations=[], revised=revision, expected_indices=indices) == []
    with pytest.raises(JobHandlerError):
        _virtual_records(observations=[], revised=revision)


def test_qualified_reinference_rejects_wrong_positions_with_same_count():
    cells = [
        {
            "cellIndex": i,
            "renderSpec": {"rowIndex": i // 5, "columnIndex": i % 5},
            "logicalCellKeySha256": "a" * 64,
            "logicalCellKeyV2Sha256": "b" * 64,
            "renderedPixelChecksumSha256": "c" * 64,
            "renderSpecChecksumSha256": "d" * 64,
            "extractorVersion": "renderer",
        }
        for i in range(1, 15)
    ]
    revision = ImageBoardGeometryRevisionModel(
        asset_mode="virtual_source", virtual_render_spec={"cells": cells}
    )
    assert (
        len(
            _virtual_records(
                observations=[], revised=revision, expected_indices=tuple(range(1, 15))
            )
        )
        == 14
    )
    with pytest.raises(JobHandlerError):
        _virtual_records(observations=[], revised=revision, expected_indices=tuple(range(14)))
