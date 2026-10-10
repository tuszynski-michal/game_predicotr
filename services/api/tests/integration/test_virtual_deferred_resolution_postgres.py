"""TASK-0790: deferred boards are resolved only through the virtual source path.

Runs on a dedicated ``*_test`` database only.  The game is provisioned through
the real partition lifecycle (so its rollout state is the new-game default),
the source image is a real file and the cells are rendered by the production
renderer.  The Reviewer endpoint ``manual-resolution`` is exercised through the
real application wiring and compared with the Admin source path.
"""

from __future__ import annotations

import hashlib
import os
import re
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import numpy as np
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from game_predictor_api.application.board_cell_geometry_pending import (
    BoardCellGeometryPendingService,
    ManagedBoardCellProcessingManifestStore,
)
from game_predictor_api.application.virtual_grid_geometry import (
    VirtualGridGeometryService,
    VirtualGridGeometrySourceCommand,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.board_cell_geometry_pending import (
    BoardCellGeometryPendingReason,
    BoardCellProcessingManifestV1,
)
from game_predictor_api.domain.image_reviews import ImageReviewGeometryPoint
from game_predictor_api.domain.jobs import JobConflictError
from game_predictor_api.domain.rules import RulesVersionStatus
from game_predictor_api.domain.symbol_model_snapshots import (
    cold_start_unclassified_symbol_snapshot,
)
from game_predictor_api.main import create_app
from game_predictor_api.storage import game_data_v2_manifest_v3 as manifest_v3
from game_predictor_api.storage import game_partition_lifecycle
from game_predictor_api.storage.board_cell_geometry_pending_repository import (
    SqlAlchemyBoardCellGeometryPendingRepository,
)
from game_predictor_api.storage.database import GameStorageSession
from game_predictor_api.storage.game_data_v2_manifest_v7 import CREATE_TABLES
from game_predictor_api.storage.game_partition_lifecycle import (
    GamePartitionLifecycleKind,
    GamePartitionLifecycleRepository,
)
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.image_geometry_completeness_state_repository import (
    SqlAlchemyImageGeometryCompletenessStateRepository,
)
from game_predictor_api.storage.models import (
    ImageBoardGeometryPendingModel,
    ImageBoardGeometryRevisionModel,
    ImageFileExecutionModel,
    ImageGeometryRolloutStateModel,
    ImageImportJobFileModel,
    ImagePipelineStageResultModel,
    ImageReviewItemModel,
    ImageSourceGeometryRevisionModel,
    JobModel,
    RecognizedBoardModel,
    RulesVersionModel,
    SourceImageModel,
)
from game_predictor_api.storage.virtual_grid_geometry_repository import (
    SqlAlchemyVirtualGridGeometryRepository,
)
from game_predictor_worker.images.normalization import CanonicalSourceLoader
from game_predictor_worker.images.pipeline_contract import (
    CellAssetRolloutMode,
    GeometryPipelineRolloutSnapshot,
    GeometryRolloutMode,
)
from game_predictor_worker.images.virtual_cell_extraction import VIRTUAL_CELL_RENDERER_VERSION
from PIL import Image
from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit isolated PostgreSQL tests only",
)

_ALEMBIC_INI = Path(__file__).resolve().parents[4] / "alembic.ini"
_PIPELINE = "b" * 64
_SOURCE_WIDTH = 620
_SOURCE_HEIGHT = 420
# A board cut by the left source edge: the two left columns are outside.
_PARTIAL_CORNERS = [
    {"x": -200, "y": 50},
    {"x": 300, "y": 50},
    {"x": 300, "y": 350},
    {"x": -200, "y": 350},
]
_PARTIAL_MASK = (0, 1, 5, 6, 10, 11)


@dataclass(frozen=True)
class _Database:
    engine: Engine
    config: Config
    url: str


@dataclass(frozen=True)
class _Seed:
    game_id: UUID
    import_job_id: UUID
    source_image_id: UUID
    pending_ids: tuple[UUID, ...]
    manifest_checksums: tuple[str, ...]


@pytest.fixture
def database() -> Iterator[_Database]:
    name = "game_predictor_task0760_" + uuid4().hex[:12] + "_test"
    assert re.fullmatch(r"game_predictor_task0760_[0-9a-f]{12}_test", name)
    url = make_url(ApiSettings.from_environment().owner_database_url)
    assert url.database != name
    maintenance = create_engine(
        url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 5, "options": "-c statement_timeout=10000"},
    )
    rendered = url.set(database=name).render_as_string(hide_password=False)
    engine = create_engine(url.set(database=name), connect_args={"connect_timeout": 5})
    config = Config(str(_ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", rendered.replace("%", "%%"))
    with maintenance.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    try:
        command.upgrade(config, "head")
        yield _Database(engine=engine, config=config, url=rendered)
    finally:
        engine.dispose()
        with maintenance.connect() as connection:
            active = -1
            for _attempt in range(50):
                active = connection.execute(
                    text("SELECT count(*) FROM pg_stat_activity WHERE datname=:name"),
                    {"name": name},
                ).scalar_one()
                if active == 0:
                    break
                time.sleep(0.1)
            assert active == 0, "Refusing DROP while a test connection remains"
            connection.exec_driver_sql(f'DROP DATABASE "{name}"')
        maintenance.dispose()


def _provision_game(engine: Engine, code: str) -> UUID:
    game_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                """INSERT INTO public.games (id, code, name, status, expected_layout_count)
                VALUES (:id, :code, :name, 'draft', 500000)"""
            ),
            {"id": game_id, "code": code, "name": code},
        )
    with Session(engine) as session, session.begin():
        operation_id = (
            GamePartitionLifecycleRepository(session)
            .start_or_resume(game_id=game_id, kind=GamePartitionLifecycleKind.PROVISION)
            .operation_id
        )
    # Headroom for the 66-table v3 lifecycle pinned by the 0133 migration test.
    for _ in range(len(CREATE_TABLES) + 8):
        with Session(engine) as session, session.begin():
            receipt = GamePartitionLifecycleRepository(session).run_next(operation_id)
        if receipt.status == "done":
            return game_id
    raise AssertionError("provisioning did not reach done")


def _factory(engine: Engine) -> sessionmaker[Session]:
    return cast(
        "sessionmaker[Session]",
        sessionmaker(bind=engine, class_=GameStorageSession, expire_on_commit=False),
    )


def _write_source(artifact_root: Path, relative_path: str, seed: int) -> Path:
    path = artifact_root / "data" / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    pixels = np.random.default_rng(seed).integers(
        0, 255, size=(_SOURCE_HEIGHT, _SOURCE_WIDTH, 3), dtype=np.uint8
    )
    Image.fromarray(pixels, mode="RGB").save(path, format="JPEG", quality=95)
    return path


def _seed(
    factory: sessionmaker[Session],
    game_id: UUID,
    artifact_root: Path,
    *,
    label: str,
    slot_count: int,
    expected_geometry_revision: int = 0,
    sequence_base: int = 100,
) -> _Seed:
    relative_path = f"originals/{label}.jpg"
    source_path = _write_source(artifact_root, relative_path, seed=len(label) * 31 + slot_count)
    checksum = hashlib.sha256(source_path.read_bytes()).hexdigest()
    loader = CanonicalSourceLoader()
    try:
        frame = loader.load(source_path, expected_source_checksum_sha256=checksum)
    finally:
        loader.clear()
    symbol_model = cold_start_unclassified_symbol_snapshot(("CYTRYNA", "WISNIA"))
    rollout = GeometryPipelineRolloutSnapshot(
        geometry_mode=GeometryRolloutMode.STRUCTURED_DEFAULT,
        cell_asset_mode=CellAssetRolloutMode.VIRTUAL_DEFAULT,
        rollout_revision=0,
        geometry_engine_version="task-0760-test-engine",
        virtual_renderer_version=VIRTUAL_CELL_RENDERER_VERSION,
        preprocessing_version="symbol-rgb-preprocessing-test",
    )
    key = hashlib.sha256(f"{label}-execution".encode()).hexdigest()
    quad = [
        {"x": 60.0, "y": 50.0},
        {"x": 560.0, "y": 50.0},
        {"x": 560.0, "y": 350.0},
        {"x": 60.0, "y": 350.0},
    ]
    now = datetime.now(UTC)
    with factory.begin() as session:
        session.add(
            ImageFileExecutionModel(
                file_execution_key=key,
                source_checksum_sha256=checksum,
                pipeline_fingerprint=_PIPELINE,
                checkpoint_payload={},
                status="waiting_for_review",
                review_required=True,
            )
        )
        session.add(
            ImagePipelineStageResultModel(
                file_execution_key=key,
                stage="board_detection",
                adapter_version="task-0760-board-detection",
                result_payload={
                    "boards": [
                        {"confidence": 0.7, "geometry": {"quad": quad}, "positionIndex": slot}
                        for slot in range(slot_count)
                    ]
                },
                created_at=now,
            )
        )
    with game_storage_scope(game_id), factory.begin() as session:
        job = JobModel(
            game_id=game_id,
            job_type="import",
            status="waiting_for_review",
            input_payload={
                "import_kind": "image_directory",
                "image_geometry_rollout": rollout.to_payload(),
                "pipeline_fingerprint": _PIPELINE,
                "schema_version": 5,
                "symbol_model": symbol_model.to_payload(),
            },
            input_key=uuid4().hex,
        )
        session.add(job)
        session.flush()
        session.add(
            ImageImportJobFileModel(
                job_id=job.id,
                file_execution_key=key,
                order_index=0,
                source_relative_path=relative_path,
                workflow_checkpoint_payload={},
                workflow_status="waiting_for_review",
                review_required=True,
            )
        )
        source = SourceImageModel(
            import_job_id=job.id,
            file_execution_key=key,
            relative_path=relative_path,
            checksum_sha256=checksum,
            width=frame.source.width,
            height=frame.source.height,
            raw_width=frame.raw_width,
            raw_height=frame.raw_height,
            oriented_width=frame.source.width,
            oriented_height=frame.source.height,
            exif_orientation=frame.source.exif_orientation,
            coordinate_space="exif-normalized-rgb-pixels-v1",
            normalized_pixel_checksum_sha256=frame.source.normalized_pixel_checksum_sha256,
            normalization_adapter_version=frame.source.normalization_adapter_version,
            status="waiting_for_review",
        )
        session.add(source)
        rules = session.scalar(
            select(RulesVersionModel).where(RulesVersionModel.game_id == game_id)
        )
        if rules is None:
            rules = RulesVersionModel(
                game_id=game_id,
                version=1,
                rows=3,
                columns=5,
                spin_cost=0,
                status=RulesVersionStatus.DRAFT,
                created_at=now,
                published_at=None,
            )
            session.add(rules)
        session.flush()
        board_geometries = [
            {
                "disposition": "needs_manual_review",
                "finalQuad": None,
                "initialQuad": quad,
                "positionIndex": slot,
                "sequenceNumber": sequence_base + slot,
            }
            for slot in range(slot_count)
        ]
        session.add(
            ImageSourceGeometryRevisionModel(
                game_id=game_id,
                source_image_id=source.id,
                topology_rules_version_id=rules.id,
                revision=0,
                sequence_range_start=sequence_base,
                sequence_range_end=sequence_base + slot_count - 1,
                active_board_slots=list(range(slot_count)),
                coordinate_space="exif-normalized-rgb-pixels-v1",
                source_checksum_sha256=checksum,
                normalized_pixel_checksum_sha256=frame.source.normalized_pixel_checksum_sha256,
                oriented_width=frame.source.width,
                oriented_height=frame.source.height,
                normalization_adapter_version=frame.source.normalization_adapter_version,
                global_initialization={},
                board_geometries=board_geometries,
                engine_kind="structured_opencv_v1",
                engine_version="task-0760-test-engine",
                geometry_source="auto",
                status="accepted",
                geometry_checksum_sha256=hashlib.sha256(f"{label}-geometry".encode()).hexdigest(),
                processing_time_ms=1,
                warnings=[],
                created_by="task-0760-test",
                created_at=now,
            )
        )
        session.flush()
        repository = SqlAlchemyBoardCellGeometryPendingRepository(session)
        pending_ids: list[UUID] = []
        checksums: list[str] = []
        for slot in range(slot_count):
            manifest = BoardCellProcessingManifestV1(
                game_id=game_id,
                import_job_id=job.id,
                source_image_id=source.id,
                source_checksum_sha256=checksum,
                source_relative_path=relative_path,
                position_index=slot,
                sequence_number=sequence_base + slot,
                pipeline_fingerprint_sha256=_PIPELINE,
                estimator_version="task-0760-estimator",
                estimator_fingerprint_sha256="2" * 64,
                cropper_version="task-0760-cropper",
                cropper_fingerprint_sha256="3" * 64,
                expected_geometry_revision=expected_geometry_revision,
                expected_review_resolution_revision=0,
            )
            pending, created = repository.defer(
                manifest=manifest,
                reason_code=BoardCellGeometryPendingReason.INCOMPLETE_LATTICE,
                manifest_relative_path=(
                    f"image-board-cell-processing-v1/{manifest.checksum_sha256}.json"
                ),
            )
            assert created is True
            pending_ids.append(pending.id)
            checksums.append(manifest.checksum_sha256)
        return _Seed(game_id, job.id, source.id, tuple(pending_ids), tuple(checksums))


def _corners() -> list[dict[str, int]]:
    return [{"x": 60, "y": 50}, {"x": 560, "y": 50}, {"x": 560, "y": 350}, {"x": 60, "y": 350}]


def _points() -> tuple[ImageReviewGeometryPoint, ...]:
    return tuple(ImageReviewGeometryPoint(x=point["x"], y=point["y"]) for point in _corners())


def _state(session: Session, pending_id: UUID) -> dict[str, Any]:
    """Persisted render state of one resolved deferred board."""

    pending = session.get(ImageBoardGeometryPendingModel, pending_id)
    assert pending is not None and pending.recognized_board_id is not None
    board = session.get(RecognizedBoardModel, pending.recognized_board_id)
    assert board is not None
    revision = session.scalar(
        select(ImageBoardGeometryRevisionModel).where(
            ImageBoardGeometryRevisionModel.recognized_board_id == board.id,
            ImageBoardGeometryRevisionModel.revision == board.geometry_revision,
        )
    )
    assert revision is not None
    manifest = session.execute(
        text(
            """SELECT manifest_checksum_sha256, cells, extractor_version
            FROM game_data_v2.board_render_manifests
            WHERE game_id = :game_id AND recognized_board_id = :board_id
              AND geometry_revision = :revision"""
        ),
        {"game_id": pending.game_id, "board_id": board.id, "revision": board.geometry_revision},
    ).one_or_none()
    # D-467 S5 (TASK-0759): the per-cell import record table no longer
    # exists, so no writer can add a record (-1 would mean it reappeared).
    observations = (
        0
        if session.execute(
            text("SELECT to_regclass('game_data_v2.cell_observations')")
        ).scalar_one()
        is None
        else -1
    )
    review_cells = session.execute(
        text(
            """SELECT cell_index, render_spec_checksum_sha256, asset_mode
            FROM game_data_v2.image_symbol_review_cells
            WHERE game_id = :game_id AND recognized_board_id = :board_id
            ORDER BY cell_index"""
        ),
        {"game_id": pending.game_id, "board_id": board.id},
    ).all()
    return {
        "pending_status": pending.status,
        "board_id": board.id,
        "asset_mode": board.asset_mode,
        "board_relative_path": board.board_relative_path,
        "geometry_revision": board.geometry_revision,
        "completeness_status": board.completeness_status,
        "unavailable_cell_indices": list(board.unavailable_cell_indices),
        "cells_prediction": board.cells_prediction,
        "revision_asset_mode": revision.asset_mode,
        "crop_artifacts": revision.crop_artifacts,
        "virtual_render_spec_checksum_sha256": revision.virtual_render_spec_checksum_sha256,
        "render_cells": [
            (cell["cellIndex"], cell["renderSpecChecksumSha256"])
            for cell in cast(list[dict[str, Any]], revision.virtual_render_spec["cells"])
        ],
        "manifest": None
        if manifest is None
        else {
            "checksum": manifest.manifest_checksum_sha256,
            "cells": [
                (cell["cellIndex"], cell["renderSpecChecksumSha256"])
                for cell in (
                    manifest.cells["cells"] if isinstance(manifest.cells, dict) else manifest.cells
                )
            ],
            "extractor_version": manifest.extractor_version,
        },
        "observations": observations,
        "review_cells": [(row.cell_index, row.render_spec_checksum_sha256) for row in review_cells],
        "review_cell_asset_modes": {row.asset_mode for row in review_cells},
        "review_item_id": pending.review_item_id,
    }


def _pending_service(session: Session, artifact_root: Path) -> BoardCellGeometryPendingService:
    # The same wiring as ``main.py``: one session for both repositories.
    return BoardCellGeometryPendingService(
        SqlAlchemyBoardCellGeometryPendingRepository(session),
        ManagedBoardCellProcessingManifestStore(artifact_root),
        virtual_geometry=VirtualGridGeometryService(
            SqlAlchemyVirtualGridGeometryRepository(session), artifact_root
        ),
    )


def test_new_game_starts_on_the_virtual_default_policy(database: _Database) -> None:
    game_id = _provision_game(database.engine, "task0760-default")
    with game_storage_scope(game_id), _factory(database.engine)() as session:
        state = session.get(ImageGeometryRolloutStateModel, game_id)
    assert state is not None
    assert (state.geometry_mode, state.cell_asset_mode, state.revision) == (
        "structured_lattice_v3",
        "virtual_default",
        0,
    )


def test_reviewer_resolution_writes_virtual_boards_through_the_application(
    database: _Database, tmp_path: Path
) -> None:
    artifact_root = tmp_path / "artifacts"
    game_id = _provision_game(database.engine, "task0760-reviewer")
    factory = _factory(database.engine)
    seed = _seed(factory, game_id, artifact_root, label="two-slot-source", slot_count=2)
    files_before = sorted(path for path in artifact_root.rglob("*") if path.is_file())
    app = create_app(
        ApiSettings.from_environment(
            {
                "GAME_PREDICTOR_DATABASE_URL": database.url,
                "GAME_PREDICTOR_ARTIFACT_ROOT": str(artifact_root),
            }
        )
    )
    base = (
        f"/api/v1/admin/games/{game_id}/image-imports/{seed.import_job_id}/"
        "board-cell-geometry-pending"
    )
    full_key = str(uuid4())
    full_command = {
        "corners": _corners(),
        "correctedBy": "task-0760-operator",
        "expectedGeometryRevision": 0,
        "expectedManifestChecksumSha256": seed.manifest_checksums[0],
        "expectedResolutionRevision": 0,
        "idempotencyKey": full_key,
    }
    partial_command = {
        **full_command,
        "corners": _PARTIAL_CORNERS,
        "expectedManifestChecksumSha256": seed.manifest_checksums[1],
        "idempotencyKey": str(uuid4()),
        "geometryQualification": {
            "completenessStatus": "pending_partial",
            "excludeFromGeometryTraining": True,
            "exclusionReason": "missing_pixels",
            "unavailableCellIndices": list(_PARTIAL_MASK),
            "version": "manual-geometry-qualification-v1",
        },
    }

    preview_command = {
        key: value
        for key, value in full_command.items()
        if key not in {"idempotencyKey", "correctedBy"}
    }
    try:
        with TestClient(app) as client:
            preview = client.post(
                f"{base}/{seed.pending_ids[0]}/geometry-preview", json=preview_command
            )
            resolved = client.post(
                f"{base}/{seed.pending_ids[0]}/manual-resolution", json=full_command
            )
            replay = client.post(
                f"{base}/{seed.pending_ids[0]}/manual-resolution", json=full_command
            )
            conflict = client.post(
                f"{base}/{seed.pending_ids[0]}/manual-resolution",
                json={**full_command, "corners": [{"x": 61, "y": 50}, *_corners()[1:]]},
            )
            partial = client.post(
                f"{base}/{seed.pending_ids[1]}/manual-resolution", json=partial_command
            )
    finally:
        app.state.database_engine.dispose()

    assert preview.status_code == 200, preview.text
    assert preview.headers["content-type"] == "image/png"
    assert preview.headers["x-board-cell-count"] == "15"
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["created"] is True
    assert resolved.json()["geometryRevision"] == 1
    assert resolved.json()["item"]["status"] == "resolved"
    assert replay.status_code == 200, replay.text
    assert replay.json()["created"] is False
    assert replay.json()["reviewItemId"] == resolved.json()["reviewItemId"]
    assert replay.json()["geometryRevision"] == 1
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IMAGE_BOARD_CELL_PENDING_IDEMPOTENCY_CONFLICT"
    assert partial.status_code == 200, partial.text
    assert partial.json()["created"] is True

    # TASK-0807 (D-484): one full and one partial board leave the image
    # incomplete, so neither board is cut into symbol cells until an operator
    # exception admits the image (the partial board has an approved
    # qualification, D-449).
    with game_storage_scope(game_id), factory() as session:
        assert _state(session, seed.pending_ids[0])["review_cells"] == []
        assert _state(session, seed.pending_ids[1])["review_cells"] == []
        source = session.get(SourceImageModel, seed.source_image_id)
        assert source is not None
        assert source.geometry_completeness_status == "geometry_incomplete"
    with game_storage_scope(game_id), factory.begin() as session:
        admitted = SqlAlchemyImageGeometryCompletenessStateRepository(session).set_exception(
            game_id, seed.source_image_id, reason="partial board", actor="task-0807"
        )
    assert admitted is not None and admitted.materialized_review_item_count == 2

    with game_storage_scope(game_id), factory() as session:
        full = _state(session, seed.pending_ids[0])
        part = _state(session, seed.pending_ids[1])
        source_revisions = session.scalars(
            select(ImageSourceGeometryRevisionModel.revision)
            .where(ImageSourceGeometryRevisionModel.source_image_id == seed.source_image_id)
            .order_by(ImageSourceGeometryRevisionModel.revision)
        ).all()
        review_item = session.get(ImageReviewItemModel, full["review_item_id"])

    for state in (full, part):
        assert state["pending_status"] == "resolved"
        assert state["asset_mode"] == state["revision_asset_mode"] == "virtual_source"
        assert state["board_relative_path"] is None and state["crop_artifacts"] is None
        assert state["geometry_revision"] == 1
        assert state["observations"] == 0
        assert state["manifest"] is not None
        assert state["manifest"]["cells"] == state["render_cells"]
        # Every board has 15 verification cells; unavailable ones have no render.
        assert [index for index, _checksum in state["review_cells"]] == list(range(15))
        assert [cell for cell in state["review_cells"] if cell[1] is not None] == state[
            "render_cells"
        ]
        assert state["review_cell_asset_modes"] <= {"virtual_source", "none"}
        prediction = cast(dict[str, Any], state["cells_prediction"])
        assert prediction["modelVersion"] == "cold-start-unclassified-v1"
        assert [(cell["rowIndex"], cell["columnIndex"]) for cell in prediction["cells"]] == [
            (index // 5, index % 5) for index, _checksum in state["render_cells"]
        ]
    assert [index for index, _ in full["render_cells"]] == list(range(15))
    assert [index for index, _ in part["render_cells"]] == [
        index for index in range(15) if index not in _PARTIAL_MASK
    ]
    assert full["review_cell_asset_modes"] == {"virtual_source"}
    assert part["completeness_status"] == "pending_partial"
    assert part["unavailable_cell_indices"] == list(_PARTIAL_MASK)
    # Each deferred slot appends one source revision from the latest one.
    assert source_revisions == [0, 1, 2]
    assert review_item is not None and review_item.status == "pending"
    # Rendering is metadata-only: no crop file is written.
    assert sorted(path for path in artifact_root.rglob("*") if path.is_file()) == files_before


def test_reviewer_and_admin_resolution_produce_the_same_render_state(
    database: _Database, tmp_path: Path
) -> None:
    artifact_root = tmp_path / "artifacts"
    game_id = _provision_game(database.engine, "task0760-identity")
    factory = _factory(database.engine)
    seed = _seed(factory, game_id, artifact_root, label="one-slot-source", slot_count=1)
    pending_id = seed.pending_ids[0]
    resolved_at = datetime(2026, 10, 1, 12, tzinfo=UTC)

    with game_storage_scope(game_id), factory() as session:
        reviewer = _pending_service(session, artifact_root).resolve_manual(
            pending_id,
            game_id=game_id,
            import_job_id=seed.import_job_id,
            expected_manifest_checksum_sha256=seed.manifest_checksums[0],
            idempotency_key=uuid4(),
            expected_geometry_revision=0,
            expected_resolution_revision=0,
            corners=_points(),
            corrected_by="reviewer-session:task-0760",
            resolved_at=resolved_at,
        )
        session.flush()
        reviewer_state = _state(session, pending_id)
        session.rollback()

    with game_storage_scope(game_id), factory() as session:
        source = session.get(SourceImageModel, seed.source_image_id)
        assert source is not None and source.oriented_width is not None
        assert source.oriented_height is not None
        admin = VirtualGridGeometryService(
            SqlAlchemyVirtualGridGeometryRepository(session), artifact_root
        ).save_source(
            game_id=game_id,
            import_job_id=seed.import_job_id,
            commands=(
                VirtualGridGeometrySourceCommand(
                    review_item_id=None,
                    pending_geometry_id=pending_id,
                    expected_geometry_revision=0,
                    expected_resolution_revision=0,
                    expected_source_checksum_sha256=source.checksum_sha256,
                    expected_source_width=source.oriented_width,
                    expected_source_height=source.oriented_height,
                    expected_grid_rows=3,
                    expected_grid_columns=5,
                    corners=_points(),
                ),
            ),
            idempotency_key=uuid4(),
            actor="local-admin",
            created_at=resolved_at,
        )
        session.flush()
        admin_state = _state(session, pending_id)
        session.commit()

    assert reviewer.created is True and admin.created is True
    for key in (
        "board_id",
        "asset_mode",
        "geometry_revision",
        "virtual_render_spec_checksum_sha256",
        "render_cells",
        "manifest",
        "review_cells",
        "cells_prediction",
        "observations",
    ):
        assert reviewer_state[key] == admin_state[key], key
    assert reviewer_state["manifest"] is not None
    assert reviewer_state["observations"] == 0


def test_resolved_deferred_board_refuses_another_command(
    database: _Database, tmp_path: Path
) -> None:
    artifact_root = tmp_path / "artifacts"
    game_id = _provision_game(database.engine, "task0760-conflict")
    factory = _factory(database.engine)
    seed = _seed(factory, game_id, artifact_root, label="conflict-source", slot_count=1)
    kwargs: dict[str, Any] = dict(
        game_id=game_id,
        import_job_id=seed.import_job_id,
        expected_manifest_checksum_sha256=seed.manifest_checksums[0],
        expected_geometry_revision=0,
        expected_resolution_revision=0,
        corners=_points(),
        corrected_by="reviewer-session:task-0760",
        resolved_at=datetime.now(UTC),
    )
    with game_storage_scope(game_id), factory.begin() as session:
        _pending_service(session, artifact_root).resolve_manual(
            seed.pending_ids[0], idempotency_key=uuid4(), **kwargs
        )
    with game_storage_scope(game_id), factory() as session:
        with pytest.raises(JobConflictError) as error:
            _pending_service(session, artifact_root).resolve_manual(
                seed.pending_ids[0], idempotency_key=uuid4(), **kwargs
            )
        session.rollback()
    assert error.value.code == "IMAGE_BOARD_CELL_PENDING_RESOLUTION_CONFLICT"


def _set_rollout(engine: Engine, game_id: UUID, geometry: str, assets: str, status: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """UPDATE game_data_v2.image_geometry_rollout_states
                SET geometry_mode = :geometry, cell_asset_mode = :assets,
                    backfill_status = :status
                WHERE game_id = :game_id"""
            ),
            {"geometry": geometry, "assets": assets, "status": status, "game_id": game_id},
        )


def _rollout_rows(engine: Engine) -> dict[UUID, tuple[str, str, int, str, str]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """SELECT game_id, geometry_mode, cell_asset_mode, revision, backfill_status,
                          updated_by
                FROM game_data_v2.image_geometry_rollout_states"""
            )
        ).all()
    return {row.game_id: tuple(row[1:]) for row in rows}


def test_migration_0133_moves_legacy_rollout_states_and_refuses_downgrade(
    database: _Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Upgrade and downgrade 0133 is refused, so reach 0132 on a fresh database.
    database.engine.dispose()
    with database.engine.begin() as connection:
        connection.exec_driver_sql("DROP SCHEMA IF EXISTS game_data_v2 CASCADE")
        connection.exec_driver_sql("DROP SCHEMA public CASCADE")
        connection.exec_driver_sql("CREATE SCHEMA public")
    command.upgrade(database.config, "0132_symbol_reference_images_cell_identity")
    # Current code provisions storage manifest v4 (TASK-0759); a game at 0132
    # is provisioned as the v3 lifecycle did.
    with monkeypatch.context() as patch:
        patch.setattr(game_partition_lifecycle, "VERSION", manifest_v3.VERSION)
        patch.setattr(game_partition_lifecycle, "CREATE_TABLES", manifest_v3.CREATE_TABLES)
        patch.setattr(game_partition_lifecycle, "DELETE_TABLES", manifest_v3.DELETE_TABLES)
        legacy_a = _provision_game(database.engine, "task0760-legacy-a")
        legacy_b = _provision_game(database.engine, "task0760-legacy-b")
        shadow = _provision_game(database.engine, "task0760-shadow")
        virtual = _provision_game(database.engine, "task0760-virtual")
    _set_rollout(database.engine, legacy_a, "legacy", "legacy_files", "not_started")
    _set_rollout(database.engine, legacy_b, "legacy", "legacy_files", "processing")
    _set_rollout(database.engine, shadow, "structured_shadow", "virtual_shadow", "ready")
    _set_rollout(database.engine, virtual, "structured_default", "virtual_default", "ready")
    before = _rollout_rows(database.engine)

    # An active validation backfill of a legacy state blocks the move.
    with pytest.raises(Exception, match="IMAGE_ENGINE_POLICY_MIGRATION_BUSY"):
        command.upgrade(database.config, "0133_virtual_only_import_policies")
    assert _rollout_rows(database.engine) == before
    _set_rollout(database.engine, legacy_b, "legacy", "legacy_files", "not_started")

    command.upgrade(database.config, "0133_virtual_only_import_policies")
    after = _rollout_rows(database.engine)
    actor = "system:migration-0133-virtual-only-import-policies"
    for game_id in (legacy_a, legacy_b, shadow):
        assert after[game_id] == (
            "structured_lattice_v3",
            "virtual_default",
            before[game_id][2] + 1,
            "not_started",
            actor,
        )
    assert after[virtual] == before[virtual]
    with database.engine.connect() as connection:
        definitions = connection.execute(
            text(
                """SELECT DISTINCT conname, pg_get_constraintdef(oid) FROM pg_constraint
                WHERE conname IN ('ck_image_geometry_rollout_states_geometry_mode',
                                  'ck_image_geometry_rollout_states_asset_mode')"""
            )
        ).all()
        defaults = connection.execute(
            text(
                """SELECT column_name, column_default FROM information_schema.columns
                WHERE table_schema = 'game_data_v2'
                  AND table_name = 'image_geometry_rollout_states'
                  AND column_name IN ('geometry_mode', 'cell_asset_mode')
                ORDER BY column_name"""
            )
        ).all()
    # Parent and every partition carry exactly the narrowed constraint.
    assert len(definitions) == 2
    assert all(
        "legacy" not in definition and "shadow" not in definition for _n, definition in definitions
    )
    assert [str(row.column_default).split("::")[0] for row in defaults] == [
        "'virtual_default'",
        "'structured_lattice_v3'",
    ]
    with pytest.raises(Exception, match="ck_image_geometry_rollout_states_geometry_mode"):
        _set_rollout(database.engine, virtual, "legacy", "virtual_default", "ready")

    with pytest.raises(Exception, match="IMAGE_ENGINE_POLICY_MIGRATION_IRREVERSIBLE"):
        command.downgrade(database.config, "0132_symbol_reference_images_cell_identity")
    with database.engine.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0133_virtual_only_import_policies"


def test_board_created_after_deferral_supersedes_the_deferred_slot(
    database: _Database, tmp_path: Path
) -> None:
    artifact_root = tmp_path / "artifacts"
    game_id = _provision_game(database.engine, "task0760-occupied")
    factory = _factory(database.engine)
    seed = _seed(factory, game_id, artifact_root, label="occupied-source", slot_count=2)
    with game_storage_scope(game_id), factory.begin() as session:
        geometry = session.scalar(
            select(ImageSourceGeometryRevisionModel).where(
                ImageSourceGeometryRevisionModel.source_image_id == seed.source_image_id
            )
        )
        assert geometry is not None
        session.add(
            RecognizedBoardModel(
                source_image_id=seed.source_image_id,
                position_index=1,
                sequence_number_raw="101",
                sequence_number=101,
                sequence_confidence=1.0,
                board_geometry={"source": "concurrent-import"},
                asset_mode="virtual_source",
                source_geometry_revision_id=geometry.id,
                geometry_engine_name="structured_opencv_v1",
                geometry_engine_version="task-0760-test-engine",
                geometry_checksum_sha256=geometry.geometry_checksum_sha256,
                cells_prediction={"cells": [], "modelVersion": "test"},
                board_confidence=1.0,
                pipeline_fingerprint=_PIPELINE,
                grid_rows=3,
                grid_columns=5,
                status="pending_review",
            )
        )
    with game_storage_scope(game_id), factory.begin() as session:
        result = _pending_service(session, artifact_root).resolve_manual(
            seed.pending_ids[1],
            game_id=game_id,
            import_job_id=seed.import_job_id,
            expected_manifest_checksum_sha256=seed.manifest_checksums[1],
            idempotency_key=uuid4(),
            expected_geometry_revision=0,
            expected_resolution_revision=0,
            corners=_points(),
            corrected_by="reviewer-session:task-0760",
            resolved_at=datetime.now(UTC),
        )
    assert result.created is False and result.geometry_revision is None
    assert result.pending.status.value == "superseded"
    with game_storage_scope(game_id), factory() as session:
        boards = session.scalars(
            select(RecognizedBoardModel).where(
                RecognizedBoardModel.source_image_id == seed.source_image_id
            )
        ).all()
        revisions = session.scalars(
            select(ImageSourceGeometryRevisionModel.revision).where(
                ImageSourceGeometryRevisionModel.source_image_id == seed.source_image_id
            )
        ).all()
    assert [board.position_index for board in boards] == [1]
    assert revisions == [0]


def _resolve_via_reviewer_endpoint(
    database: _Database,
    artifact_root: Path,
    seed: _Seed,
    *,
    expected_geometry_revision: int = 0,
) -> dict[str, Any]:
    app = create_app(
        ApiSettings.from_environment(
            {
                "GAME_PREDICTOR_DATABASE_URL": database.url,
                "GAME_PREDICTOR_ARTIFACT_ROOT": str(artifact_root),
            }
        )
    )
    path = (
        f"/api/v1/admin/games/{seed.game_id}/image-imports/{seed.import_job_id}/"
        f"board-cell-geometry-pending/{seed.pending_ids[0]}/manual-resolution"
    )
    try:
        with TestClient(app) as client:
            response = client.post(
                path,
                json={
                    "corners": _corners(),
                    "correctedBy": "task-0760-operator",
                    "expectedGeometryRevision": expected_geometry_revision,
                    "expectedManifestChecksumSha256": seed.manifest_checksums[0],
                    "expectedResolutionRevision": 0,
                    "idempotencyKey": str(uuid4()),
                },
            )
    finally:
        app.state.database_engine.dispose()
    assert response.status_code == 200, response.text
    return cast(dict[str, Any], response.json())


def _render_spec_revisions(session: Session, pending_id: UUID) -> set[object]:
    pending = session.get(ImageBoardGeometryPendingModel, pending_id)
    assert pending is not None and pending.recognized_board_id is not None
    revision = session.scalar(
        select(ImageBoardGeometryRevisionModel).where(
            ImageBoardGeometryRevisionModel.recognized_board_id == pending.recognized_board_id
        )
    )
    assert revision is not None
    return {
        cast(dict[str, Any], cell["renderSpec"]).get("geometryRevision")
        for cell in cast(list[dict[str, Any]], revision.virtual_render_spec["cells"])
    }


def test_manual_resolution_continues_the_canonical_crop_revision(
    database: _Database, tmp_path: Path
) -> None:
    """TASK-0702 handoff: a deferred board taking over a sequence continues its revision."""

    artifact_root = tmp_path / "artifacts"
    game_id = _provision_game(database.engine, "task0760-handoff")
    factory = _factory(database.engine)
    first = _seed(factory, game_id, artifact_root, label="first-import", slot_count=1)
    first_response = _resolve_via_reviewer_endpoint(database, artifact_root, first)
    assert first_response["geometryRevision"] == 1
    # D-543 (TASK-0971): another photo takes the sequence over only from a
    # rejected owner, so the first board is rejected before the handoff.
    from game_predictor_api.domain.image_reviews import ImageReviewAction
    from test_pending_slot_rejection_postgres import _items, _resolve_board

    _resolve_board(
        factory,
        first,
        _items(factory, first)[0],
        action=ImageReviewAction.REJECTED,
        reason="cropped",
    )
    second = _seed(factory, game_id, artifact_root, label="second-import-x", slot_count=1)

    second_response = _resolve_via_reviewer_endpoint(database, artifact_root, second)

    assert second_response["created"] is True
    assert second_response["geometryRevision"] == 2
    assert second_response["item"]["resolvedGeometryRevision"] == 2
    with game_storage_scope(game_id), factory() as session:
        state = _state(session, second.pending_ids[0])
        spec_revisions = _render_spec_revisions(session, second.pending_ids[0])
        cells = session.execute(
            text(
                """SELECT DISTINCT geometry_revision, recognized_board_id
                FROM game_data_v2.image_symbol_review_cells
                WHERE game_id = :game_id AND sequence_number = 100"""
            ),
            {"game_id": game_id},
        ).all()
    assert state["geometry_revision"] == 2
    assert state["manifest"] is not None and state["observations"] == 0
    assert spec_revisions == {2}
    # The sequence's current projection now belongs to the second board.
    assert [(row.geometry_revision, row.recognized_board_id) for row in cells] == [
        (2, state["board_id"])
    ]


def test_manual_resolution_uses_pending_revision_without_current_crops(
    database: _Database, tmp_path: Path
) -> None:
    artifact_root = tmp_path / "artifacts"
    game_id = _provision_game(database.engine, "task0760-no-crops")
    factory = _factory(database.engine)
    seed = _seed(
        factory,
        game_id,
        artifact_root,
        label="pinned-revision",
        slot_count=1,
        expected_geometry_revision=3,
    )

    response = _resolve_via_reviewer_endpoint(
        database, artifact_root, seed, expected_geometry_revision=3
    )

    assert response["geometryRevision"] == 4
    with game_storage_scope(game_id), factory() as session:
        state = _state(session, seed.pending_ids[0])
        spec_revisions = _render_spec_revisions(session, seed.pending_ids[0])
    assert state["geometry_revision"] == 4 and spec_revisions == {4}


def test_concurrent_resolutions_of_one_source_never_build_on_a_stale_revision(
    database: _Database, tmp_path: Path
) -> None:
    """Two slots of one source take different sequence locks; the source row serializes."""

    artifact_root = tmp_path / "artifacts"
    game_id = _provision_game(database.engine, "task0760-race")
    factory = _factory(database.engine)
    seed = _seed(factory, game_id, artifact_root, label="race-source", slot_count=2)

    def kwargs(slot: int) -> dict[str, Any]:
        return dict(
            game_id=game_id,
            import_job_id=seed.import_job_id,
            expected_manifest_checksum_sha256=seed.manifest_checksums[slot],
            idempotency_key=uuid4(),
            expected_geometry_revision=0,
            expected_resolution_revision=0,
            corners=_points(),
            corrected_by="reviewer-session:task-0760",
            resolved_at=datetime.now(UTC),
        )

    winner_session = factory()
    outcome: dict[str, object] = {}

    def loser() -> None:
        with game_storage_scope(game_id), factory() as session:
            try:
                _pending_service(session, artifact_root).resolve_manual(
                    seed.pending_ids[1], **kwargs(1)
                )
                session.commit()
                outcome["result"] = "committed"
            except Exception as error:  # noqa: BLE001 - the conflict is the assertion
                session.rollback()
                outcome["result"] = getattr(error, "code", repr(error))

    try:
        with game_storage_scope(game_id):
            _pending_service(winner_session, artifact_root).resolve_manual(
                seed.pending_ids[0], **kwargs(0)
            )
            winner_session.flush()
            # The winner holds the source row; the loser renders on revision 0
            # and then waits for the lock inside its repository transaction.
            thread = threading.Thread(target=loser)
            thread.start()
            thread.join(timeout=3)
            assert thread.is_alive(), "the loser must wait for the source lock"
            winner_session.commit()
            thread.join(timeout=60)
            assert not thread.is_alive()
    finally:
        winner_session.close()

    assert outcome["result"] == "IMAGE_GRID_REVIEW_REVISION_CONFLICT"
    with game_storage_scope(game_id), factory() as session:
        revisions = session.scalars(
            select(ImageSourceGeometryRevisionModel.revision)
            .where(ImageSourceGeometryRevisionModel.source_image_id == seed.source_image_id)
            .order_by(ImageSourceGeometryRevisionModel.revision)
        ).all()
        loser_pending = session.get(ImageBoardGeometryPendingModel, seed.pending_ids[1])
    assert revisions == [0, 1]
    assert loser_pending is not None and loser_pending.status == "pending"

    # A retry of the loser now builds on the winner's source revision.
    with game_storage_scope(game_id), factory.begin() as session:
        retry = _pending_service(session, artifact_root).resolve_manual(
            seed.pending_ids[1], **kwargs(1)
        )
    assert retry.created is True
    with game_storage_scope(game_id), factory() as session:
        latest = session.scalar(
            select(ImageSourceGeometryRevisionModel)
            .where(ImageSourceGeometryRevisionModel.source_image_id == seed.source_image_id)
            .order_by(ImageSourceGeometryRevisionModel.revision.desc())
            .limit(1)
        )
    assert latest is not None and latest.revision == 2
    assert [geometry.get("geometrySource") for geometry in latest.board_geometries] == [
        "manual",
        "manual",
    ]
