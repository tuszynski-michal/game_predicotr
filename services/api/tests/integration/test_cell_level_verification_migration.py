"""TASK-0728: the D-462 data migration previews and applies exactly (PostgreSQL)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from alembic import command
from game_predictor_api.application.image_symbol_review_mutations import (
    SymbolCellReviewMutationService,
)
from game_predictor_api.domain.cell_level_verification_migration import validate_manifest
from game_predictor_api.storage.cell_level_verification_migration_repository import (
    CellLevelMigrationInvariantError,
    CellLevelVerificationMigrationRepository,
)
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.image_symbol_review_repository import (
    _COUNT_SCOPE_ALL,
    SqlAlchemySymbolCellReviewMutationRepository,
    SymbolCellReviewWriteThroughCoordinator,
)
from game_predictor_api.storage.models import (
    ImageBoardSearchCandidateModel,
    ImageReviewItemModel,
    ImageSequenceCanonicalModel,
    ImageSymbolReviewCellModel,
    ImageSymbolReviewEventModel,
    ImageSymbolReviewStateModel,
    SymbolModel,
)
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker
from test_verified_cell_search_projection import (
    _cells,
    _database_url,
    _migration_config,
    _seed_pending_board,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Set GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 to run PostgreSQL integration tests.",
)

TEST_DATABASE_NAME = "game_predictor_cell_migration_test"
OTHER_PIXELS = "e" * 64


@pytest.fixture
def migration_database() -> Iterator[URL]:
    maintenance_engine = create_engine(
        _database_url("postgres"), isolation_level="AUTOCOMMIT", pool_pre_ping=True
    )
    identifier = f'"{TEST_DATABASE_NAME}"'
    try:
        with maintenance_engine.connect() as connection:
            connection.exec_driver_sql(f"DROP DATABASE IF EXISTS {identifier} WITH (FORCE)")
            connection.exec_driver_sql(f"CREATE DATABASE {identifier}")
        yield _database_url(TEST_DATABASE_NAME)
    finally:
        with maintenance_engine.connect() as connection:
            connection.exec_driver_sql(f"DROP DATABASE IF EXISTS {identifier} WITH (FORCE)")
        maintenance_engine.dispose()


def _review_id(session: Session, game_id: UUID, sequence_number: int) -> UUID:
    review_id = session.scalar(
        select(ImageReviewItemModel.id).where(
            ImageReviewItemModel.game_id == game_id,
            ImageReviewItemModel.sequence_number == sequence_number,
        )
    )
    assert review_id is not None
    return review_id


def _approve(session: Session, game_id: UUID, cell: ImageSymbolReviewCellModel) -> Any:
    return SymbolCellReviewMutationService(
        SqlAlchemySymbolCellReviewMutationRepository(session)
    ).approve(
        game_id=game_id,
        cell_review_id=cell.id,
        expected_revision=cell.revision,
        expected_geometry_revision=cell.geometry_revision,
        expected_crop_sample_id=cell.crop_sample_id,
        expected_crop_checksum_sha256=cell.crop_checksum_sha256,
        actor="symbol-cell-operator",
    )


def _approve_without_write_through(cell: ImageSymbolReviewCellModel, symbol_id: UUID) -> None:
    """A verification stored before D-462: no projection update, no closure."""

    cell.assigned_symbol_id = symbol_id
    cell.assignment_source = "human"
    cell.review_state = "approved"
    cell.approved_crop_sample_id = cell.crop_sample_id
    cell.approved_crop_checksum_sha256 = cell.crop_checksum_sha256
    cell.approved_geometry_revision = cell.geometry_revision
    cell.approved_asset_mode = cell.asset_mode
    cell.approved_source_geometry_revision_id = cell.source_geometry_revision_id
    cell.approved_render_spec_checksum_sha256 = cell.render_spec_checksum_sha256
    cell.approved_rendered_pixel_checksum_sha256 = cell.rendered_pixel_checksum_sha256
    cell.revision += 1


def _approve_other_pixels(cell: ImageSymbolReviewCellModel) -> None:
    """An approval of other pixels; a virtual approval is bound by its render."""

    cell.approved_crop_checksum_sha256 = OTHER_PIXELS
    cell.approved_rendered_pixel_checksum_sha256 = OTHER_PIXELS


def _approved_total(session: Session, game_id: UUID) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(ImageSymbolReviewCellModel)
            .where(
                ImageSymbolReviewCellModel.game_id == game_id,
                ImageSymbolReviewCellModel.review_state == "approved",
            )
        )
        or 0
    )


def _preview(session_factory: sessionmaker[Session], game_id: UUID) -> dict[str, Any]:
    with game_storage_scope(game_id), session_factory.begin() as session:
        session.connection().execute(
            text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        )
        return CellLevelVerificationMigrationRepository(session).preview(
            game_id, generated_at="2026-09-29T12:00:00+00:00", batch_size=2
        )


def _apply(
    session_factory: sessionmaker[Session], manifest: dict[str, Any]
) -> dict[UUID, dict[str, Any]]:
    game_id, plans = validate_manifest(manifest)
    results: dict[UUID, dict[str, Any]] = {}
    for plan in plans:
        with game_storage_scope(game_id), session_factory.begin() as session:
            results[plan.review_item_id] = CellLevelVerificationMigrationRepository(
                session
            ).apply_board(game_id, plan)
    return results


def _review_state(session: Session, game_id: UUID) -> tuple[int, str, int]:
    state = session.get(ImageSymbolReviewStateModel, game_id)
    assert state is not None
    # Each cell is counted in the all-cells scope and in its symbol scope.
    counts = state.count_projection.get(_COUNT_SCOPE_ALL, {})
    approved = int(counts.get("approved", 0)) if isinstance(counts, dict) else 0
    return state.catalog_revision, state.count_projection_status, approved


def test_preview_is_applied_exactly_once_and_never_verifies_a_cell(
    migration_database: URL,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command.upgrade(_migration_config(migration_database), "head")
    engine = create_engine(migration_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    now = datetime(2026, 9, 29, 12, tzinfo=UTC)

    try:
        seed = _seed_pending_board(session_factory, now, sibling_positions=(1, 2, 3, 4, 5))
        game_id = seed.game_id
        with game_storage_scope(game_id), session_factory() as session:
            first_symbol_id = session.scalar(
                select(SymbolModel.id).where(
                    SymbolModel.game_id == game_id, SymbolModel.code == "first"
                )
            )
            assert first_symbol_id is not None
            stale_pending = _review_id(session, game_id, 1)
            complete = _review_id(session, game_id, 2)
            stale_accepted = _review_id(session, game_id, 3)
            stale_document = _review_id(session, game_id, 4)
            model_only = _review_id(session, game_id, 5)
            virtual = _review_id(session, game_id, 6)

            # A: two verified cells; the second approval covers other pixels.
            for cell in _cells(session, stale_pending)[:2]:
                _approve(session, game_id, cell)
            # F: R10 compares a virtual board's rendered pixels.
            for cell in _cells(session, virtual)[:2]:
                _approve(session, game_id, cell)
            # C: a board resolved from 15 verifications, one on other pixels.
            for cell in _cells(session, stale_accepted):
                result = _approve(session, game_id, cell)
            assert result.board_status == "accepted"
            session.commit()

        with game_storage_scope(game_id), session_factory() as session:
            _approve_other_pixels(_cells(session, stale_pending)[1])
            _approve_other_pixels(_cells(session, stale_accepted)[2])
            # B: 15/15 verified before D-462, still waiting for grid approval.
            for cell in _cells(session, complete):
                _approve_without_write_through(cell, first_symbol_id)
            # D: a verification the search document never saw.
            _approve_without_write_through(_cells(session, stale_document)[0], first_symbol_id)
            session.commit()

        with game_storage_scope(game_id), session_factory() as session:
            # The crop checksum still matches; only the rendered pixels differ.
            _cells(session, virtual)[1].approved_rendered_pixel_checksum_sha256 = OTHER_PIXELS
            session.commit()

        manifest = _preview(session_factory, game_id)
        boards = {UUID(board["reviewItemId"]): board for board in manifest["boards"]}
        assert set(boards) == {stale_pending, complete, stale_accepted, stale_document, virtual}
        assert boards[virtual]["recheckCellIndices"] == [1]
        assert boards[virtual]["closeAction"] is None
        assert model_only not in boards
        assert boards[stale_pending]["recheckCellIndices"] == [1]
        assert boards[stale_pending]["closeAction"] is None
        assert boards[complete]["closeAction"] == "accepted"
        assert boards[complete]["refreshProjection"] is True
        assert boards[stale_accepted]["reopen"] is True
        assert boards[stale_accepted]["recheckCellIndices"] == [2]
        assert boards[stale_document] | {"fingerprint": None} == {
            "reviewItemId": str(stale_document),
            "sequenceNumber": 4,
            "status": "pending",
            "fingerprint": None,
            "reopen": False,
            "recheckCellIndices": [],
            "closeAction": None,
            "refreshProjection": True,
        }
        assert manifest["counts"]["recheckCells"] == 3
        assert manifest["counts"]["reopenBoards"] == 1
        assert manifest["counts"]["closeBoards"] == 1
        # The preview wrote nothing.
        assert _preview(session_factory, game_id)["previewSha256"] == manifest["previewSha256"]

        # An operator decision after the preview makes board A drift.
        with game_storage_scope(game_id), session_factory() as session:
            _approve(session, game_id, _cells(session, stale_pending)[3])
            session.commit()
            approved_before = _approved_total(session, game_id)
            catalog_before, count_status_before, approved_counted_before = _review_state(
                session, game_id
            )

        results = _apply(session_factory, manifest)
        assert results[stale_pending]["result"] == "drift"
        assert results[complete] | {"reviewItemId": None} == {
            "reviewItemId": None,
            "result": "applied",
            "reopened": False,
            "rechecked": 0,
            "closed": True,
            "expectedClose": True,
            "refreshedProjection": True,
        }
        assert results[stale_accepted]["reopened"] is True
        assert results[stale_accepted]["rechecked"] == 1
        assert results[stale_document]["result"] == "applied"
        assert results[virtual]["rechecked"] == 1

        with game_storage_scope(game_id), session_factory() as session:
            # Only the reviewed recheck removed approvals; nothing was verified.
            assert _approved_total(session, game_id) == approved_before - 2
            catalog_after, count_status_after, approved_counted_after = _review_state(
                session, game_id
            )
            assert catalog_after > catalog_before
            assert count_status_after == count_status_before
            assert count_status_before == "ready"
            assert approved_counted_after == approved_counted_before - 2
            virtual_cells = _cells(session, virtual)
            assert [cell.review_state for cell in virtual_cells[:2]] == ["approved", "pending"]
            assert virtual_cells[1].approved_rendered_pixel_checksum_sha256 == OTHER_PIXELS
            accepted = session.get(ImageReviewItemModel, complete)
            assert accepted is not None and accepted.status == "accepted"
            reopened = session.get(ImageReviewItemModel, stale_accepted)
            assert reopened is not None and reopened.status == "pending"
            assert (
                session.get(ImageSequenceCanonicalModel, {"game_id": game_id, "sequence_number": 3})
                is None
            )
            rechecked = _cells(session, stale_accepted)[2]
            assert rechecked.review_state == "pending"
            assert rechecked.assigned_symbol_id == first_symbol_id
            assert rechecked.assignment_source == "human"
            assert rechecked.approved_crop_checksum_sha256 == OTHER_PIXELS
            assert rechecked.verification_outcome == "requires_review"
            assert rechecked.verified_symbol_id_v2 is None
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ImageSymbolReviewEventModel)
                    .where(
                        ImageSymbolReviewEventModel.cell_review_id == rechecked.id,
                        ImageSymbolReviewEventModel.action == "geometry_invalidated",
                    )
                )
                == 1
            )
            document = session.get(ImageBoardSearchCandidateModel, stale_document)
            assert document is not None
            assert document.primary_symbol_codes[0] == "first"
            # Board A kept its approval of other pixels (drift, not applied).
            assert _cells(session, stale_pending)[1].review_state == "approved"

        # A repeated apply changes nothing.
        again = _apply(session_factory, manifest)
        assert {
            again[key]["result"] for key in (complete, stale_accepted, stale_document, virtual)
        } == {"already_applied"}
        assert again[stale_pending]["result"] == "drift"

        # A new preview only has board A left; applying it empties the preview.
        fresh = _preview(session_factory, game_id)
        assert [board["reviewItemId"] for board in fresh["boards"]] == [str(stale_pending)]
        assert _apply(session_factory, fresh)[stale_pending]["result"] == "applied"
        assert _preview(session_factory, game_id)["boards"] == []

        # A recheck that would leave an approval in place stops the whole run.
        with game_storage_scope(game_id), session_factory() as session:
            _approve(session, game_id, _cells(session, stale_document)[1])
            session.commit()
        with game_storage_scope(game_id), session_factory() as session:
            _approve_other_pixels(_cells(session, stale_document)[1])
            session.commit()
        broken = _preview(session_factory, game_id)
        assert [board["recheckCellIndices"] for board in broken["boards"]] == [[1]]
        monkeypatch.setattr(
            SymbolCellReviewWriteThroughCoordinator,
            "recheck_changed_pixel_approvals",
            lambda self, **kwargs: len(kwargs["cell_indices"]),
        )
        with pytest.raises(CellLevelMigrationInvariantError):
            _apply(session_factory, broken)
        with game_storage_scope(game_id), session_factory() as session:
            assert _cells(session, stale_document)[1].review_state == "approved"
    finally:
        engine.dispose()
