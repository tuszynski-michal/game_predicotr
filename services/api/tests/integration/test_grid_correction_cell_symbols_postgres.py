"""Operator symbols of a grid correction approve exact current crops (D-488)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from game_predictor_api.domain.image_grid_reviews import ImageGridReviewError
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.image_symbol_review_repository import (
    SqlAlchemyGridCorrectionSymbolRepository,
)
from game_predictor_api.storage.partial_board_reconciliation_repository import (
    PartialBoardReconciliationRepository,
)
from sqlalchemy import Engine
from test_partial_board_reconciliation_postgres import _manifest, _rows, _seed_board, _upgrade
from test_symbol_source_visibility_migration import database  # noqa: F401

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Set GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 for isolated PostgreSQL tests.",
)


def test_operator_symbols_approve_only_the_selected_current_crops(
    database: Engine,  # noqa: F811
    tmp_path: Path,
) -> None:
    _upgrade(database)
    root = tmp_path / "grid-correction-symbols"
    game_id, symbol_id, review_item_id, _ = _seed_board(database, root)
    sessions = create_session_factory(database)
    with game_storage_scope(game_id), sessions() as session:
        manifest = _manifest(
            PartialBoardReconciliationRepository(session, source_roots=[root]).snapshot_board(
                game_id, 62287
            ),
            game_id,
        )
    with game_storage_scope(game_id), sessions() as session, session.begin():
        PartialBoardReconciliationRepository(session, source_roots=[root]).apply_board(
            manifest, 62287
        )

    # Cell 2 is partially visible, cell 5 fully visible; both keep real pixels.
    with game_storage_scope(game_id), sessions() as session, session.begin():
        before = {
            row.cell_index: (row.revision, row.review_state) for row in _rows(session, game_id)
        }
        repository = SqlAlchemyGridCorrectionSymbolRepository(session)
        changed = repository.assign(
            game_id=game_id,
            review_item_id=review_item_id,
            symbol_id_by_cell_index={2: symbol_id, 5: symbol_id},
            actor="grid-correction-test",
        )
        assert changed == 2
        replayed = repository.assign(
            game_id=game_id,
            review_item_id=review_item_id,
            symbol_id_by_cell_index={2: symbol_id, 5: symbol_id},
            actor="grid-correction-test",
        )
        assert replayed == 0

    with game_storage_scope(game_id), sessions() as session:
        rows = {row.cell_index: row for row in _rows(session, game_id)}
        for index in (2, 5):
            assert rows[index].review_state == "approved"
            assert rows[index].assignment_source == "human"
            assert rows[index].assigned_symbol_id == symbol_id
            assert (
                rows[index].approved_rendered_pixel_checksum_sha256
                == rows[index].rendered_pixel_checksum_sha256
            )
        assert rows[2].quality_issue == "partial_visibility"
        # The suggestions of the correction screen read the same current crops:
        # the two cells without source pixels are not offered.
        suggestions = {
            index: (stored_symbol_id, origin)
            for index, stored_symbol_id, origin in SqlAlchemyGridCorrectionSymbolRepository(
                session
            ).current_symbols(game_id=game_id, review_item_id=review_item_id)
        }
        assert sorted(suggestions) == list(range(2, 15))
        assert suggestions[2] == suggestions[5] == (symbol_id, "assigned")
        assert all(
            origin == "predicted"
            for index, (_, origin) in suggestions.items()
            if index not in (2, 5)
        )
        untouched = set(rows) - {2, 5}
        assert {index: (rows[index].revision, rows[index].review_state) for index in untouched} == {
            index: before[index] for index in untouched
        }

    # "Cannot tell" reopens an approved crop as unreadable instead of guessing.
    with game_storage_scope(game_id), sessions() as session, session.begin():
        unknown = SqlAlchemyGridCorrectionSymbolRepository(session).assign(
            game_id=game_id,
            review_item_id=review_item_id,
            symbol_id_by_cell_index={5: None},
            actor="grid-correction-test",
        )
        assert unknown == 1
    with game_storage_scope(game_id), sessions() as session:
        rows = {row.cell_index: row for row in _rows(session, game_id)}
        assert rows[5].review_state == "pending"
        assert rows[5].quality_issue == "unreadable"
        assert rows[5].assignment_source == "human"
        assert rows[2].review_state == "approved"

    # A cell without source pixels has no crop to approve: nothing is skipped.
    with game_storage_scope(game_id), sessions() as session:
        with pytest.raises(ImageGridReviewError) as error:
            SqlAlchemyGridCorrectionSymbolRepository(session).assign(
                game_id=game_id,
                review_item_id=review_item_id,
                symbol_id_by_cell_index={0: symbol_id, 6: symbol_id},
                actor="grid-correction-test",
            )
        assert error.value.code == "IMAGE_GRID_REVIEW_SYMBOL_CELL_UNAVAILABLE"
        session.rollback()
    with game_storage_scope(game_id), sessions() as session:
        rows = {row.cell_index: row for row in _rows(session, game_id)}
        assert rows[6].review_state == before[6][1]
