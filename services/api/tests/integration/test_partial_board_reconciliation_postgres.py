"""Reconciliation receipts and operator decisions survive reconnects atomically."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from _virtual_board_fixtures import replace_virtual_geometry
from alembic import command
from alembic.config import Config
from game_predictor_api.application.catalog import CatalogService
from game_predictor_api.application.image_symbol_review_mutations import (
    SymbolCellReviewMutationService,
)
from game_predictor_api.domain.catalog import GameStatus, SymbolStatus
from game_predictor_api.domain.geometry_qualification import GeometryQualification
from game_predictor_api.domain.jobs import JobStatus
from game_predictor_api.domain.partial_board_reconciliation import (
    PILOT_SEQUENCES,
    ReconciliationError,
    blocked_board,
    build_manifest,
)
from game_predictor_api.storage.catalog_repository import SqlAlchemyCatalogRepository
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.image_symbol_review_repository import (
    SqlAlchemySymbolCellReviewMutationRepository,
    SymbolCellReviewWriteThroughCoordinator,
)
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.models import (
    ImageReviewItemModel,
    ImageSourceGeometryRevisionModel,
    ImageSymbolReviewCellModel,
    ImageSymbolReviewEventModel,
    ImageSymbolReviewStateModel,
    JobModel,
    PartialBoardReconciliationReceiptModel,
    RecognizedBoardModel,
)
from game_predictor_api.storage.partial_board_reconciliation_repository import (
    PartialBoardReconciliationRepository,
)
from game_predictor_worker.images.orchestration_store import SqlAlchemyImageBatchStore
from PIL import Image
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm.attributes import flag_modified
from test_image_batch_store import PIPELINE, _add_review_projection_source, _image_job
from test_symbol_source_visibility_migration import database  # noqa: F401

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Set GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 for isolated PostgreSQL tests.",
)


def _upgrade(engine: Engine) -> None:
    config = Config(str(Path(__file__).resolve().parents[4] / "alembic.ini"))
    config.set_main_option(
        "sqlalchemy.url", engine.url.render_as_string(hide_password=False).replace("%", "%%")
    )
    command.upgrade(config, "head")


def _seed_board(engine: Engine, root: Path) -> tuple[UUID, UUID, UUID, UUID]:
    """A current partial board has real source bytes, 15 revision-1 crops, no fastdoc."""
    root.mkdir(parents=True, exist_ok=True)
    path = root / "source.png"
    Image.new("RGB", (1920, 1080), (120, 80, 30)).save(path)
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    sessions = create_session_factory(engine)
    now = datetime.now(UTC)
    with sessions() as session:
        catalog = CatalogService(SqlAlchemyCatalogRepository(session))
        game = catalog.create_game(
            code=f"reconcile-{root.name}", name="Reconcile", status=GameStatus.ACTIVE
        )
        symbol = catalog.create_symbol(
            game.id,
            mobile_code=1,
            code="test",
            name="Test",
            image_path=None,
            is_wildcard=False,
            display_order=0,
            status=SymbolStatus.ACTIVE,
        )
        job = SqlAlchemyJobRepository(session).add_job(_image_job(game.id, PIPELINE, now))
        session.commit()
    execution = SqlAlchemyImageBatchStore(sessions).register_file(
        job.id,
        source_checksum_sha256=checksum,
        pipeline_fingerprint=PIPELINE,
        source_relative_path="source.png",
        order_index=0,
        registered_at=now,
    )
    with game_storage_scope(game.id), sessions() as session:
        review_id, board_id = _add_review_projection_source(
            session,
            job_id=job.id,
            file_execution_key=execution.file_execution_key,
            source_checksum=checksum,
            source_name="source.png",
            position_index=0,
            sequence_number=62287,
            status="pending",
            created_at=now,
        )
        session.get(JobModel, job.id).status = JobStatus.WAITING_FOR_REVIEW
        board = session.get(RecognizedBoardModel, board_id)
        board.completeness_status = "pending_partial"
        board.unavailable_cell_indices = [0, 1]
        board.geometry_qualification = GeometryQualification(
            "pending_partial",
            (0, 1),
            True,
            "missing_pixels",
            version="manual-geometry-qualification-v3",
            fully_unavailable_cell_indices=(0, 1),
        ).to_dict()
        board.board_geometry = {
            "cells": [
                {
                    "rowIndex": index // 5,
                    "columnIndex": index % 5,
                    "sourceQuad": [
                        {"x": x, "y": y}
                        for x, y in (
                            ((-20, 10), (-10, 10), (-10, 20), (-20, 20))
                            if index in (0, 1)
                            else ((-1, 10), (20, 10), (20, 20), (-1, 20))
                            if index == 2
                            else ((10, 10), (20, 10), (20, 20), (10, 20))
                        )
                    ],
                }
                for index in range(15)
            ]
        }
        # D-467 S6: a virtual board's visibility comes from its pinned source
        # geometry slot, and its partial revision renders only cells 2-14.
        source_geometry = session.get(
            ImageSourceGeometryRevisionModel, board.source_geometry_revision_id
        )
        slots = [dict(value) for value in source_geometry.board_geometries]
        slots[board.position_index] = {
            **slots[board.position_index],
            "cells": board.board_geometry["cells"],
        }
        source_geometry.board_geometries = slots
        flag_modified(source_geometry, "board_geometries")
        replace_virtual_geometry(
            session,
            game_id=game.id,
            review_item_id=review_id,
            board_id=board_id,
            variant="partial",
            cell_indices=tuple(range(2, 15)),
        )
        # Reproduce historical "ready" state with an incomplete cell projection.
        session.add(ImageSymbolReviewStateModel(game_id=game.id, status="ready"))
        session.commit()
    return game.id, symbol.id, review_id, board_id


def _manifest(snapshot: dict[str, object], game_id: UUID) -> dict[str, object]:
    return build_manifest(
        game_id=game_id,
        storage_generation=2,
        boards=[
            snapshot
            if sequence == 62287
            else blocked_board(sequence, "OWNER_MISSING", "Not part of this isolated fixture")
            for sequence in PILOT_SEQUENCES
        ],
    )


def _retry_in_new_process(
    engine: Engine, root: Path, manifest: dict[str, object]
) -> dict[str, object]:
    """A receipt must be sufficient after losing the original apply response."""
    manifest_path = root / "preview.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    repo_root = Path(__file__).resolve().parents[4]
    script = """
import json,sys
from pathlib import Path
from uuid import UUID
from sqlalchemy import create_engine
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.partial_board_reconciliation_repository import (
 PartialBoardReconciliationRepository,
)
url,root,path=sys.argv[1:]
manifest=json.loads(Path(path).read_text(encoding='utf-8'))
engine=create_engine(url,connect_args={'connect_timeout':5})
try:
 with game_storage_scope(UUID(manifest['gameId'])),create_session_factory(engine)() as session:
  with session.begin():
   result=PartialBoardReconciliationRepository(session,source_roots=[Path(root)]).apply_board(manifest,62287)
  print(json.dumps(result,default=str))
finally:
 engine.dispose()
"""
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        str(repo_root / part)
        for part in (".venv/Lib/site-packages", "services/api/src", "services/worker/src")
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            engine.url.render_as_string(hide_password=False),
            str(root),
            str(manifest_path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        env=environment,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _rows(session, game_id: UUID):
    return list(
        session.scalars(
            select(ImageSymbolReviewCellModel)
            .where(ImageSymbolReviewCellModel.game_id == game_id)
            .order_by(ImageSymbolReviewCellModel.cell_index)
        )
    )


def test_repair_preserves_humans_and_receipts_survive_new_process(
    database: Engine,  # noqa: F811
    tmp_path: Path,
) -> None:
    _upgrade(database)
    root = tmp_path / "human-retry"
    game_id, symbol_id, _, _ = _seed_board(database, root)
    sessions = create_session_factory(database)
    with game_storage_scope(game_id), sessions() as session:
        snapshot = PartialBoardReconciliationRepository(
            session, source_roots=[root]
        ).snapshot_board(game_id, 62287)
        manifest = _manifest(snapshot, game_id)
        assert not _rows(session, game_id)
    with game_storage_scope(game_id), sessions() as session, session.begin():
        PartialBoardReconciliationRepository(session, source_roots=[root]).apply_board(
            manifest, 62287
        )
    with game_storage_scope(game_id), sessions() as session, session.begin():
        rows = _rows(session, game_id)
        assert len(rows) == 15
        assert [row.source_visibility for row in rows] == ["outside", "outside", "partial"] + [
            "full"
        ] * 12
        assert all(
            row.crop_sample_id is None and row.crop_checksum_sha256 is None for row in rows[:2]
        )
        human = rows[0]
        service = SymbolCellReviewMutationService(
            SqlAlchemySymbolCellReviewMutationRepository(session)
        )
        service.reassign(
            game_id=game_id,
            cell_review_id=human.id,
            expected_revision=human.revision,
            expected_geometry_revision=human.geometry_revision,
            expected_crop_sample_id=None,
            expected_crop_checksum_sha256=None,
            target_symbol_id=symbol_id,
            actor="repair-test",
        )
        service.mark_unreadable(
            game_id=game_id,
            cell_review_id=human.id,
            expected_revision=human.revision,
            expected_geometry_revision=human.geometry_revision,
            expected_crop_sample_id=None,
            expected_crop_checksum_sha256=None,
            actor="repair-test",
        )
        session.flush()
        decision = (human.id, human.revision, human.assigned_symbol_id, human.quality_issue)
        event_count = session.scalar(
            select(func.count())
            .select_from(ImageSymbolReviewEventModel)
            .where(ImageSymbolReviewEventModel.cell_review_id == decision[0])
        )
        # Recreate a historical sparse projection without changing source geometry.
        session.execute(
            delete(ImageSymbolReviewCellModel).where(
                ImageSymbolReviewCellModel.id.in_([rows[1].id, rows[14].id])
            )
        )
    with game_storage_scope(game_id), sessions() as session:
        second = _manifest(
            PartialBoardReconciliationRepository(session, source_roots=[root]).snapshot_board(
                game_id, 62287
            ),
            game_id,
        )
    with game_storage_scope(game_id), sessions() as session, session.begin():
        PartialBoardReconciliationRepository(session, source_roots=[root]).apply_board(
            second, 62287
        )
    with game_storage_scope(game_id), sessions() as session:
        rows = _rows(session, game_id)
        assert len(rows) == 15
        assert (
            rows[0].id,
            rows[0].revision,
            rows[0].assigned_symbol_id,
            rows[0].quality_issue,
        ) == decision
        ids = [row.id for row in rows]
    assert _retry_in_new_process(database, root, manifest)["replayed"] is True
    assert _retry_in_new_process(database, root, second)["replayed"] is True
    with game_storage_scope(game_id), sessions() as session:
        rows = _rows(session, game_id)
        assert [row.id for row in rows] == ids
        assert (
            rows[0].id,
            rows[0].revision,
            rows[0].assigned_symbol_id,
            rows[0].quality_issue,
        ) == decision
        assert (
            session.scalar(
                select(func.count())
                .select_from(ImageSymbolReviewEventModel)
                .where(ImageSymbolReviewEventModel.cell_review_id == decision[0])
            )
            == event_count
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(PartialBoardReconciliationReceiptModel)
                .where(PartialBoardReconciliationReceiptModel.game_id == game_id)
            )
            == 2
        )
    invalid = json.loads(json.dumps(manifest))
    invalid["boards"][PILOT_SEQUENCES.index(62287)]["sourceVisibility"][0] = "full"
    with (
        pytest.raises(ReconciliationError, match="Preview input is invalid"),
        game_storage_scope(game_id),
        sessions() as session,
        session.begin(),
    ):
        PartialBoardReconciliationRepository(session, source_roots=[root]).apply_board(
            invalid, 62287
        )


def test_apply_failure_rolls_back_projection_and_can_retry(
    database: Engine,  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _upgrade(database)
    root = tmp_path / "rollback"
    game_id, _, _, _ = _seed_board(database, root)
    sessions = create_session_factory(database)
    with game_storage_scope(game_id), sessions() as session:
        manifest = _manifest(
            PartialBoardReconciliationRepository(session, source_roots=[root]).snapshot_board(
                game_id, 62287
            ),
            game_id,
        )
    original = SymbolCellReviewWriteThroughCoordinator.synchronize_for_backfill_reconciliation

    def fail_after_projection(self, **kwargs):
        original(self, **kwargs)
        self._session.flush()
        raise RuntimeError("injected after projection")

    with monkeypatch.context() as patch:
        patch.setattr(
            SymbolCellReviewWriteThroughCoordinator,
            "synchronize_for_backfill_reconciliation",
            fail_after_projection,
        )
        with (
            pytest.raises(RuntimeError, match="injected after projection"),
            game_storage_scope(game_id),
            sessions() as session,
            session.begin(),
        ):
            PartialBoardReconciliationRepository(session, source_roots=[root]).apply_board(
                manifest, 62287
            )
    with game_storage_scope(game_id), sessions() as session:
        assert not _rows(session, game_id)
        assert (
            session.scalar(
                select(func.count())
                .select_from(PartialBoardReconciliationReceiptModel)
                .where(PartialBoardReconciliationReceiptModel.game_id == game_id)
            )
            == 0
        )
    with game_storage_scope(game_id), sessions() as session, session.begin():
        PartialBoardReconciliationRepository(session, source_roots=[root]).apply_board(
            manifest, 62287
        )
    with game_storage_scope(game_id), sessions() as session:
        assert len(_rows(session, game_id)) == 15
        assert (
            session.scalar(
                select(func.count())
                .select_from(PartialBoardReconciliationReceiptModel)
                .where(PartialBoardReconciliationReceiptModel.game_id == game_id)
            )
            == 1
        )


@pytest.mark.parametrize("change", ["owner", "geometry", "source"])
def test_changed_preview_is_rejected_without_projection_or_receipt(
    database: Engine,  # noqa: F811
    tmp_path: Path,
    change: str,
) -> None:
    _upgrade(database)
    root = tmp_path / f"conflict-{change}"
    game_id, _, review_id, board_id = _seed_board(database, root)
    sessions = create_session_factory(database)
    with game_storage_scope(game_id), sessions() as session:
        manifest = _manifest(
            PartialBoardReconciliationRepository(session, source_roots=[root]).snapshot_board(
                game_id, 62287
            ),
            game_id,
        )
    if change == "source":
        Image.new("RGB", (1920, 1080), (255, 0, 0)).save(root / "source.png")
    else:
        with game_storage_scope(game_id), sessions() as session, session.begin():
            if change == "owner":
                session.get(ImageReviewItemModel, review_id).resolution_revision += 1
            else:
                session.get(RecognizedBoardModel, board_id).geometry_revision += 1
    with (
        pytest.raises(ReconciliationError),
        game_storage_scope(game_id),
        sessions() as session,
        session.begin(),
    ):
        PartialBoardReconciliationRepository(session, source_roots=[root]).apply_board(
            manifest, 62287
        )
    with game_storage_scope(game_id), sessions() as session:
        assert not _rows(session, game_id)
        assert (
            session.scalar(
                select(func.count())
                .select_from(PartialBoardReconciliationReceiptModel)
                .where(PartialBoardReconciliationReceiptModel.game_id == game_id)
            )
            == 0
        )
