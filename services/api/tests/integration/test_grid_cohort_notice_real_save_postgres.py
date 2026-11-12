"""TASK-1195 / D-605: a genuine reviewer geometry save notifies the same cohorts.

One real ``save_review_item`` of a board covered by three cohorts runs as the
application role under RLS, once with the production v2 currentness trigger and
once with the v1 trigger reinstalled on the same 14 tables. Both runs roll back,
so they start from identical rows; the notices of both must be identical.
"""

from __future__ import annotations

import os
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from _application_role_database import application_role_database
from game_predictor_api.application.virtual_grid_geometry import VirtualGridGeometryService
from game_predictor_api.domain.geometry_qualification import GeometryQualification
from game_predictor_api.domain.image_geometry_v2 import SourceLatticeNodes, SourcePoint
from game_predictor_api.domain.image_reviews import ImageReviewGeometryPoint
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.grid_cohort_member_refs_migration import NOTICE_TABLES
from game_predictor_api.storage.models import SymbolModel
from game_predictor_api.storage.virtual_grid_geometry_repository import (
    SqlAlchemyVirtualGridGeometryRepository,
)
from sqlalchemy import text
from test_grid_cohort_member_refs_postgres import _cohort, _member, _scope
from test_grid_training_cohort_e2e_postgres import _nodes, _save_source
from test_virtual_deferred_resolution_postgres import _factory

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit disposable PostgreSQL and generated JPEGs only",
)


def _install(db, function: str) -> None:
    with db.owner_engine.begin() as connection:
        for table, kind in NOTICE_TABLES.items():
            connection.execute(
                text(f"DROP TRIGGER grid_cohort_currentness ON game_data_v2.{table}")
            )
            connection.execute(
                text(
                    "CREATE TRIGGER grid_cohort_currentness BEFORE INSERT OR UPDATE OR DELETE "
                    f"ON game_data_v2.{table} FOR EACH ROW EXECUTE FUNCTION "
                    f"game_data_v2.{function}('{kind}','{table}')"
                )
            )


def _save_and_collect(db, root: Path, game: UUID, job: UUID, source: UUID) -> Counter:
    with game_storage_scope(game), _factory(db.app_engine)() as session:
        session.begin()
        row = session.execute(
            text(
                "SELECT i.id,i.resolution_revision,b.geometry_revision "
                "FROM game_data_v2.image_review_items i "
                "JOIN game_data_v2.recognized_boards b "
                "ON b.game_id=i.game_id AND b.id=i.recognized_board_id "
                "WHERE b.game_id=:g AND b.source_image_id=:s AND b.position_index=0"
            ),
            {"g": game, "s": source},
        ).one()
        nodes = list(_nodes(0))
        nodes[8] = SourcePoint(nodes[8].x + 0.25, nodes[8].y)
        saved = VirtualGridGeometryService(
            SqlAlchemyVirtualGridGeometryRepository(session), root
        ).save_review_item(
            game_id=game,
            import_job_id=job,
            review_item_id=row.id,
            idempotency_key=uuid4(),
            expected_geometry_revision=row.geometry_revision,
            expected_resolution_revision=row.resolution_revision,
            corners=tuple(
                ImageReviewGeometryPoint(round(nodes[i].x), round(nodes[i].y))
                for i in (0, 5, 23, 18)
            ),
            lattice_nodes=SourceLatticeNodes(tuple(nodes)),
            # The seeded board carries a qualification; the reviewer resends it.
            geometry_qualification=GeometryQualification(),
            actor="fixture-human:1190",
            created_at=datetime.now(UTC),
        )
        assert saved.created
        session.flush()
        notices = Counter(
            tuple(str(value) for value in found)
            for found in session.execute(
                text(
                    "SELECT cohort_id,source_id,board_id,review_id,cell_id,document "
                    "FROM game_data_v2.grid_training_cohort_events "
                    "WHERE game_id=:g AND kind='currentness_notice'"
                ),
                {"g": game},
            )
        )
        session.rollback()
    return notices


def test_genuine_review_item_save_notifies_the_same_cohorts_with_v1_and_v2(tmp_path) -> None:
    root = tmp_path / "artifacts"
    with application_role_database("t1190save", ("save",)) as db:
        game = db.games["save"]
        with game_storage_scope(game), _factory(db.owner_engine).begin() as session:
            for index, code in enumerate(("CYTRYNA", "WISNIA"), 1):
                session.add(
                    SymbolModel(
                        game_id=game,
                        code=code,
                        name=code,
                        mobile_code=index,
                        display_order=index,
                        status="active",
                    )
                )
        source, _, job = _save_source(db, root, game, 1, 2, {})
        with db.owner_engine.connect() as connection:
            boards = connection.execute(
                text(
                    "SELECT b.id,i.id FROM game_data_v2.recognized_boards b "
                    "JOIN game_data_v2.image_review_items i "
                    "ON i.game_id=b.game_id AND i.recognized_board_id=b.id "
                    "WHERE b.game_id=:g AND b.source_image_id=:s ORDER BY b.position_index"
                ),
                {"g": game, "s": source},
            ).all()
            cells = connection.scalars(
                text(
                    "SELECT c.id FROM game_data_v2.image_symbol_review_cells c "
                    "JOIN game_data_v2.recognized_boards b "
                    "ON b.game_id=c.game_id AND b.id=c.recognized_board_id "
                    "WHERE b.game_id=:g AND b.source_image_id=:s AND b.position_index=0"
                ),
                {"g": game, "s": source},
            ).all()
        assert len(boards) == 2 and len(cells) == 15
        with db.app_engine.begin() as connection:
            _scope(connection, game)
            # Three cohorts: whole photo, saved board only, the other board only.
            whole, saved, other = (_cohort(connection, game) for _ in range(3))
            _member(
                connection,
                game,
                whole,
                source,
                0,
                [b for b, _ in boards],
                [r for _, r in boards],
                list(cells),
            )
            _member(connection, game, saved, source, 0, [boards[0][0]], [boards[0][1]], cells[:3])
            _member(connection, game, other, source, 0, [boards[1][0]], [boards[1][1]], [])
        v2 = _save_and_collect(db, root, game, job, source)
        _install(db, "grid_cohort_notice_v1")
        v1 = _save_and_collect(db, root, game, job, source)
        _install(db, "grid_cohort_notice_v2")
        assert sum(v2.values()) > 0
        assert v1 == v2
        notified = {key[0] for key in v2}
        # The source-level evidence reaches every cohort of the photo.
        assert notified == {str(whole), str(saved), str(other)}
