from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock
from uuid import uuid4

from game_predictor_api.storage.image_review_repository import (
    SqlAlchemyOperationalImageReviewRepository,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session


class _Rows:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[object, ...]]:
        return self._rows


class _Session:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows = rows

    def execute(self, _statement: object) -> _Rows:
        return _Rows(self._rows)


def test_preview_protects_approved_geometry_and_separates_virtual_sources() -> None:
    source_ids = [uuid4() for _index in range(4)]
    current = {
        "geometryVersion": "board-cell-geometry-v19-test",
        "cropperVersion": "board-cell-crops-v19-test",
    }
    rows: list[tuple[object, ...]] = [
        (source_ids[0], "pending", {}, "legacy_file", 0),
        (source_ids[1], "pending", {}, "virtual_source", None),
        (source_ids[2], "pending", current, "legacy_file", None),
        (source_ids[3], "pending", {}, "legacy_file", None),
    ]
    repository = SqlAlchemyOperationalImageReviewRepository(
        cast(Session, cast(Any, _Session(rows)))
    )

    preview = repository.pending_grid_reinference_preview(
        uuid4(),
        geometry_version="board-cell-geometry-v19-test",
        cropper_version="board-cell-crops-v19-test",
        audit_report_checksum_sha256="a" * 64,
    )

    assert preview.pending_board_count == 4
    assert preview.protected_board_count == 1
    assert preview.unsupported_virtual_board_count == 1
    assert preview.current_v19_board_count == 1
    assert preview.recalculable_board_count == 1


def test_pending_symbol_reinference_count_includes_boards_with_pending_cells() -> None:
    session = MagicMock()
    session.scalar.return_value = 19380
    repository = SqlAlchemyOperationalImageReviewRepository(cast(Session, session))

    assert repository.pending_symbol_reinference_count(uuid4()) == 19380

    statement = session.scalar.call_args.args[0]
    query = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "image_symbol_review_cells.review_state = 'pending'" in query
    assert "image_review_items.status IN ('pending', 'accepted', 'corrected')" in query
