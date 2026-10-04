"""TASK-0840: the grid-audit board reader on a real, disposable ``*_test`` database."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from game_predictor_api.application.grid_audit_proposals import (
    FileGridAuditProposalStore,
    GridAuditProposalService,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.grid_audit_proposals import (
    GridAuditImportStatus,
    GridAuditProposalItem,
    GridAuditQueueStatus,
    proposal_grid_from_nodes,
)
from game_predictor_api.domain.image_grid_reviews import (
    ImageGridReviewListFilter,
    ImageGridReviewView,
)
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.grid_audit_board_reader import SqlAlchemyGridAuditBoardReader
from game_predictor_api.storage.image_grid_review_repository import (
    SqlAlchemyImageGridReviewRepository,
)
from game_predictor_api.storage.models import RecognizedBoardModel, SourceImageModel
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from test_partial_board_reconciliation_postgres import _seed_board

from scripts import import_grid_audit_proposals as importer

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Set GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 for isolated PostgreSQL tests.",
)


@pytest.fixture
def database() -> Iterator[Engine]:
    """Only this uniquely named ``*_test`` database is created and dropped."""

    name = f"game_predictor_task0840_{uuid4().hex[:12]}_test"
    url = make_url(ApiSettings.from_environment().owner_database_url)
    maintenance = create_engine(
        url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 5},
    )
    engine = create_engine(url.set(database=name), connect_args={"connect_timeout": 5})
    with maintenance.connect() as connection:
        connection.execute(text("SET statement_timeout='10s'"))
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        config = Config(str(Path(__file__).resolve().parents[4] / "alembic.ini"))
        config.set_main_option(
            "sqlalchemy.url",
            url.set(database=name).render_as_string(hide_password=False).replace("%", "%%"),
        )
        command.upgrade(config, "head")
        yield engine
    finally:
        engine.dispose()
        with maintenance.connect() as connection:
            connection.execute(text("SET statement_timeout='10s'"))
            connection.execute(text(f'DROP DATABASE "{name}"'))
        maintenance.dispose()


def _nodes() -> list[list[float]]:
    return [[100.0 + column * 50, 50.0 + row * 40] for row in range(4) for column in range(6)]


def test_reader_reports_revision_and_review_item_like_the_correction_queue(
    database: Engine, tmp_path: Path
) -> None:
    game_id, _symbol_id, _review_id, board_id = _seed_board(database, tmp_path / "seed")
    sessions = create_session_factory(database)
    with game_storage_scope(game_id), sessions() as session:
        board = session.get(RecognizedBoardModel, board_id)
        assert board is not None
        source = session.get(SourceImageModel, board.source_image_id)
        assert source is not None
        revision = board.geometry_revision
        reader = SqlAlchemyGridAuditBoardReader(session)
        states = reader.board_states(game_id=game_id, board_ids=[board_id, uuid4()])
        assert list(states) == [board_id]
        assert states[board_id].geometry_revision == revision
        assert states[board_id].current_review_item is True

        item = GridAuditProposalItem(
            ordinal=0,
            item_id="p00001",
            verdict_source="operator",
            audit_class="row_shift",
            level="S",
            human_decided_cells=0,
            recognized_board_id=board_id,
            source_image_id=board.source_image_id,
            import_job_id=UUID(int=1),
            sequence_number=62287,
            position_index=board.position_index,
            audit_geometry_revision=revision,
            import_geometry_revision=revision,
            import_status=GridAuditImportStatus.PROPOSAL,
            proposal=proposal_grid_from_nodes(_nodes()),
        )
        # The review item comes from the correction queue's own read of the
        # photo; the seeded board has no board-search document, so neither
        # that read nor the audit reader treats it as a current queue entry.
        listed = SqlAlchemyImageGridReviewRepository(session).list_grid_reviews(
            review_filter=ImageGridReviewListFilter(
                game_id=game_id,
                view=ImageGridReviewView.ALL,
                import_job_id=None,
                source_image_id=board.source_image_id,
            ),
            after_key=None,
            before_key=None,
            limit=100,
        )
        expected = next(
            (entry for entry in listed.items if entry.recognized_board_id == board_id), None
        )
        assert reader.review_item(game_id=game_id, item=item) == expected

        root = tmp_path / "artifacts"
        content = importer.document_bytes(
            audit_id="audit",
            game_id=game_id,
            created_at="2026-10-04T00:00:00+00:00",
            items=[item],
            sources={},
            verification={},
        )
        importer.write_artifact(
            root / "grid-audit-proposals" / str(game_id) / "audit",
            content,
            audit_id="audit",
            game_id=game_id,
            created_at="2026-10-04T00:00:00+00:00",
            items=1,
        )
        service = GridAuditProposalService(FileGridAuditProposalStore(root), reader)
        page = service.queue(game_id=game_id, after_ordinal=None, limit=1)
        assert page.counts.open == 1
        view = service.proposal(game_id=game_id, item_id="p00001")
        if expected is None:
            assert view.entry.status is GridAuditQueueStatus.REMOVED
            assert view.proposal is None
        else:
            assert view.entry.status is GridAuditQueueStatus.OPEN
            assert view.proposal == item.proposal
        # The reader never writes.
        assert not session.new and not session.dirty
        session.rollback()
