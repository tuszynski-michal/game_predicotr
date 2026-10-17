"""TASK-1044: shared crop registry (migration 0167) and cross-game crop eligibility.

Runs on dedicated ``*_test`` databases only. Games are provisioned through the
real partition lifecycle, so sources and boards live in ``game_data_v2``.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from _application_role_database import (
    ALEMBIC_INI,
    ApplicationRoleDatabase,
    application_role_database,
)
from alembic import command
from alembic.config import Config
from game_predictor_api.domain.image_symbol_reviews import SymbolCellReviewAction
from game_predictor_api.domain.rules import RulesVersionStatus
from game_predictor_api.domain.source_crop import (
    PixelBox,
    ProtectedBox,
    SourceCropAttestation,
)
from game_predictor_api.domain.source_crop_eligibility import (
    CropBlobEligibility,
    CropExclusion,
    managed_original_relative_path,
)
from game_predictor_api.storage.database import GameStorageSession
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.models import (
    ImageBoardGeometryPendingModel,
    ImageFileExecutionModel,
    ImageSourceGeometryRevisionModel,
    JobModel,
    RecognizedBoardModel,
    RulesVersionModel,
    SourceImageModel,
)
from game_predictor_api.storage.source_image_crop_repository import SourceImageCropRepository
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from test_geometry_correction_revert_board_postgres import _board_game, _item, _mutate
from test_virtual_deferred_resolution_postgres import (
    _Database,
    database,  # noqa: F401  (pytest fixture)
)

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit isolated PostgreSQL tests only",
)

_FINGERPRINT = "b" * 64
_PIXELS = "c" * 64
_QUAD = [
    {"x": 100.0, "y": 60.0},
    {"x": 700.0, "y": 60.0},
    {"x": 700.0, "y": 420.0},
    {"x": 100.0, "y": 420.0},
]
_MANIFEST = "SELECT manifest_version FROM public.game_storage_locations WHERE game_id=:g"


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _factory(engine: Engine) -> sessionmaker[Session]:
    return cast(
        "sessionmaker[Session]",
        sessionmaker(bind=engine, class_=GameStorageSession, expire_on_commit=False),
    )


def _snapshot(engine: Engine) -> Session:
    return Session(engine.execution_options(isolation_level="REPEATABLE READ"))


def _eligibility(engine: Engine, **arguments: object) -> list[CropBlobEligibility]:
    with _snapshot(engine) as session, session.begin():
        return SourceImageCropRepository(session).eligibility(**arguments)  # type: ignore[arg-type]


def _seed_source(
    engine: Engine,
    game_id: UUID,
    checksum: str,
    *,
    import_status: str = "completed",
    approved: bool = True,
    revision_status: str = "accepted",
    pending_correction: bool = False,
    geometry_status: str = "geometry_complete",
    board_without_quads: bool = False,
) -> tuple[UUID, UUID]:
    """One source with one board (two when the second board has no quads)."""

    now = datetime.now(UTC)
    factory = _factory(engine)
    key = _sha(f"{game_id}:{checksum}")
    positions = [0, 1] if board_without_quads else [0]
    with factory.begin() as session:
        session.add(
            ImageFileExecutionModel(
                file_execution_key=key,
                source_checksum_sha256=checksum,
                # Executions are global: one per (checksum, pipeline) across games.
                pipeline_fingerprint=key,
                checkpoint_payload={},
                status="completed",
                review_required=False,
            )
        )
    with game_storage_scope(game_id), factory.begin() as session:
        job = JobModel(
            game_id=game_id,
            job_type="import",
            status=import_status,
            input_payload={"import_kind": "image_directory"},
            input_key=uuid4().hex,
        )
        session.add(job)
        session.flush()
        source = SourceImageModel(
            import_job_id=job.id,
            file_execution_key=key,
            relative_path=managed_original_relative_path(checksum),
            checksum_sha256=checksum,
            width=1080,
            height=589,
            raw_width=1080,
            raw_height=589,
            oriented_width=1080,
            oriented_height=589,
            exif_orientation=None,
            coordinate_space="exif-normalized-rgb-pixels-v1",
            normalization_adapter_version="normalization-test-v1",
            normalized_pixel_checksum_sha256=_PIXELS,
            status="completed",
            geometry_completeness_status=geometry_status,
            geometry_completeness_evaluated_at=now,
        )
        session.add(source)
        rules = RulesVersionModel(
            game_id=game_id,
            # One rules version per seeded source; versions are unique per game.
            version=uuid4().int % 1_000_000 + 1,
            rows=3,
            columns=5,
            spin_cost=0,
            status=RulesVersionStatus.DRAFT,
            created_at=now,
            published_at=None,
        )
        session.add(rules)
        session.flush()
        geometry = ImageSourceGeometryRevisionModel(
            game_id=game_id,
            source_image_id=source.id,
            topology_rules_version_id=rules.id,
            revision=0,
            sequence_range_start=1,
            sequence_range_end=len(positions),
            active_board_slots=positions,
            coordinate_space="exif-normalized-rgb-pixels-v1",
            source_checksum_sha256=checksum,
            normalized_pixel_checksum_sha256=_PIXELS,
            oriented_width=1080,
            oriented_height=589,
            normalization_adapter_version="normalization-test-v1",
            global_initialization={},
            board_geometries=[
                {"positionIndex": 0, "sourceQuad": _QUAD},
                *({"positionIndex": slot} for slot in positions[1:]),
            ],
            engine_kind="structured_opencv_v1",
            engine_version="structured-test-v1",
            geometry_source="auto",
            status=revision_status,
            geometry_checksum_sha256=_sha(f"{key}:geometry"),
            processing_time_ms=1,
            warnings=[],
            created_by="task-1044-test",
            created_at=now,
        )
        session.add(geometry)
        session.flush()
        first_board: RecognizedBoardModel | None = None
        for position in positions:
            board = RecognizedBoardModel(
                source_image_id=source.id,
                position_index=position,
                sequence_number_raw=str(position + 1),
                sequence_number=position + 1,
                sequence_confidence=1.0,
                board_geometry={"finalQuad": _QUAD} if position == 0 else {},
                asset_mode="virtual_source",
                source_geometry_revision_id=geometry.id,
                geometry_engine_name="structured_opencv_v1",
                geometry_engine_version="structured-test-v1",
                geometry_checksum_sha256=_sha(f"{key}:geometry"),
                cells_prediction={"cells": [], "modelVersion": "test"},
                board_confidence=1.0,
                pipeline_fingerprint=_FINGERPRINT,
                grid_rows=3,
                grid_columns=5,
                status="accepted",
                approved_geometry_revision=0 if approved else None,
                geometry_approved_at=now if approved else None,
                geometry_approved_by="task-1044-test" if approved else None,
            )
            session.add(board)
            session.flush()
            first_board = first_board or board
        if pending_correction:
            assert first_board is not None
            session.add(
                ImageBoardGeometryPendingModel(
                    game_id=game_id,
                    import_job_id=job.id,
                    source_image_id=source.id,
                    recognized_board_id=first_board.id,
                    sequence_number=1,
                    position_index=0,
                    source_checksum_sha256=checksum,
                    source_relative_path=managed_original_relative_path(checksum),
                    status="pending",
                    reason_code="residual_too_high",
                    processing_manifest_checksum_sha256=_sha(f"{key}:manifest"),
                    processing_manifest_relative_path="data/manifests/test.json",
                    pipeline_fingerprint_sha256=_FINGERPRINT,
                    expected_geometry_revision=0,
                    expected_review_resolution_revision=0,
                )
            )
        return source.id, job.id


def _without_foreign_keys(engine: Engine, statement: str, values: dict[str, object]) -> None:
    """Insert a row whose unrelated parents (staging, reinference) are not modelled.

    ``session_replication_role = replica`` skips FK triggers for this
    transaction only; CHECK constraints and the routing columns still apply.
    """

    with engine.begin() as connection:
        connection.exec_driver_sql("SET LOCAL session_replication_role = replica")
        connection.execute(text(statement), values)


def _config(db: ApplicationRoleDatabase) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option(
        "sqlalchemy.url", db.owner_url.render_as_string(hide_password=False).replace("%", "%%")
    )
    return config


def _attestation(checksum: str) -> SourceCropAttestation:
    return SourceCropAttestation(
        original_checksum_sha256=checksum,
        original_size_bytes=257_965,
        original_normalized_pixel_checksum_sha256=_PIXELS,
        original_width=1080,
        original_height=589,
        original_exif_orientation=None,
        crop_checksum_sha256=_sha("crop"),
        crop_size_bytes=190_000,
        crop_normalized_pixel_checksum_sha256=_sha("crop-pixels"),
        canvas_pixel_checksum_sha256=_sha("canvas"),
        crop_box=PixelBox(48, 0, 752, 480),
        raw_crop_box=PixelBox(48, 0, 752, 480),
        protected_box=ProtectedBox(100.0, 60.0, 700.0, 420.0),
        margin_px=50,
        imcu_width=8,
        imcu_height=8,
        edge_mismatch_pixels=0,
        tool_version="libjpeg-turbo version 3.2.0 (build 20260630)",
    )


def test_migration_registers_the_shared_table_and_guards_its_downgrade() -> None:
    with application_role_database("t1044m", ("a",)) as db:
        game = db.games["a"]
        with db.owner_engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                "0167_source_image_crops"
            )
            assert connection.scalar(text(_MANIFEST), {"g": game}) == "game-data-v2-manifest-v18"
            assert (
                connection.scalar(
                    text(
                        "SELECT ownership FROM public.game_storage_table_manifest "
                        "WHERE manifest_version='game-data-v2-manifest-v18' "
                        "AND table_name='source_image_crops'"
                    )
                )
                == "shared"
            )
        config = _config(db)
        command.downgrade(config, "0166_grid_model_evaluation")
        with db.owner_engine.connect() as connection:
            assert connection.scalar(text(_MANIFEST), {"g": game}) == "game-data-v2-manifest-v17"
            assert (
                connection.scalar(text("SELECT to_regclass('public.source_image_crops')")) is None
            )
        command.upgrade(config, "head")
        checksum = _sha("registered")
        with Session(db.owner_engine) as session, session.begin():
            SourceImageCropRepository(session).record_verified(
                _attestation(checksum),
                attestation_sha256=_sha("attestation"),
                job_id=None,
                verified_at=datetime.now(UTC),
            )
        with pytest.raises(Exception, match="SOURCE_IMAGE_CROPS_DOWNGRADE_HAS_HISTORY"):
            command.downgrade(config, "0166_grid_model_evaluation")


def test_registry_constraints_and_state_transition() -> None:
    with application_role_database("t1044r", ()) as db:
        checksum = _sha("state")
        verified_at = datetime.now(UTC)
        with Session(db.owner_engine) as session, session.begin():
            repository = SourceImageCropRepository(session)
            repository.record_verified(
                _attestation(checksum),
                attestation_sha256=_sha("attestation"),
                job_id=None,
                verified_at=verified_at,
            )
            repository.mark_original_deleted(
                checksum, deleted_at=verified_at + timedelta(seconds=1)
            )
        with Session(db.owner_engine) as session:
            row = SourceImageCropRepository(session).get(checksum)
            assert row is not None
            assert row.state == "original_deleted"
            assert row.crop_relative_path == f"originals-cropped/{checksum[:2]}/{checksum}.jpg"
            with pytest.raises(ValueError, match="SOURCE_IMAGE_CROP_NOT_VERIFIED"):
                SourceImageCropRepository(session).mark_original_deleted(
                    checksum, deleted_at=verified_at
                )

        def update(assignment: str) -> Callable[[Session], None]:
            def run(session: Session) -> None:
                session.execute(
                    text(
                        f"UPDATE public.source_image_crops SET {assignment} "
                        "WHERE original_checksum_sha256=:c"
                    ),
                    {"c": checksum},
                )

            return run

        for statement in (
            update("crop_relative_path='../x.jpg'"),
            update("crop_size_bytes=original_size_bytes"),
            update("state='verified'"),
            update("crop_box=ARRAY[NULL,NULL,NULL,NULL]::integer[]"),
            update("raw_crop_box=ARRAY[48,0,40,480]"),
            update("raw_crop_box=ARRAY[0,0,8,8]"),
            update("protected_box=ARRAY[700,60,100,420]::double precision[]"),
            update("protected_box=ARRAY[[1,2],[3,4]]::double precision[]"),
        ):
            with (
                Session(db.owner_engine) as session,
                pytest.raises(IntegrityError),
                session.begin(),
            ):
                statement(session)


def test_eligibility_reads_every_game_sharing_an_original() -> None:
    with application_role_database("t1044e", ("a", "b", "c")) as db:
        engine = db.owner_engine
        game_a, game_b, game_c = db.games["a"], db.games["b"], db.games["c"]
        eligible = _sha("eligible")
        shared = _sha("shared")
        pending = _sha("pending")
        unfinished = _sha("unfinished")
        unaccepted = _sha("unaccepted")
        incomplete = _sha("incomplete")
        half_quads = _sha("half-quads")
        excluded = _sha("page-excluded")
        proposed = _sha("proposed")
        busy = _sha("busy")
        _seed_source(engine, game_a, eligible)
        _seed_source(engine, game_a, shared)
        _seed_source(engine, game_b, shared, approved=False)
        _seed_source(engine, game_a, pending, pending_correction=True)
        _seed_source(engine, game_b, unfinished, import_status="waiting_for_review")
        _seed_source(engine, game_b, unaccepted, revision_status="needs_review")
        _seed_source(engine, game_b, incomplete, geometry_status="geometry_incomplete")
        _seed_source(engine, game_b, half_quads, board_without_quads=True)
        _seed_source(engine, game_b, excluded)
        _, proposed_import = _seed_source(engine, game_b, proposed)
        _seed_source(engine, game_c, busy)
        _without_foreign_keys(
            engine,
            "INSERT INTO game_data_v2.image_page_source_exclusions (id, game_id, "
            "browser_selection_id, geometry_preflight_job_id, source_manifest_checksum_sha256, "
            "geometry_manifest_checksum_sha256, source_checksum_sha256, source_relative_path, "
            "actor, decision_checksum_sha256) VALUES (:id, :owner, :selection, :preflight, "
            ":c1, :c2, :checksum, 'seq_1.jpg', 'task-1044-test', :c3)",
            {
                "id": uuid4(),
                "owner": game_b,
                "selection": uuid4(),
                "preflight": uuid4(),
                "c1": _sha("m1"),
                "c2": _sha("m2"),
                "checksum": excluded,
                "c3": _sha("m3"),
            },
        )
        _without_foreign_keys(
            engine,
            "INSERT INTO game_data_v2.grid_geometry_proposals (game_id, id, target_result_id, "
            "operation_id, target_ordinal, import_job_id, review_item_id, state, revision, "
            "document) VALUES (:owner, :id, :target, :operation, 0, :import_job, :item, "
            "'pending', 1, '{}'::jsonb)",
            {
                "owner": game_b,
                "id": uuid4(),
                "target": uuid4(),
                "operation": uuid4(),
                "import_job": proposed_import,
                "item": uuid4(),
            },
        )
        # A running image job in game c excludes its originals, not other games'.
        with game_storage_scope(game_c), _factory(engine).begin() as session:
            session.add(
                JobModel(
                    game_id=game_c,
                    job_type="image_grid_reinference",
                    status="created",
                    input_payload={},
                    input_key=uuid4().hex,
                )
            )

        results = {item.original_checksum_sha256: item for item in _eligibility(engine)}
        scoped = _eligibility(engine, scope_game=game_a)
        paged = _eligibility(engine, page_size=4)
        after = _eligibility(engine, after_checksum=paged[-1].original_checksum_sha256)
        only = _eligibility(engine, only_checksums=[shared])

        assert results[eligible].eligible
        assert results[eligible].protected_points
        assert results[eligible].game_ids == (game_a,)
        assert results[shared].exclusions == (CropExclusion.GEOMETRY_NOT_APPROVED,)
        assert set(results[shared].game_ids) == {game_a, game_b}
        expected = {
            pending: CropExclusion.PENDING_GEOMETRY_CORRECTION,
            unfinished: CropExclusion.IMPORT_NOT_COMPLETED,
            unaccepted: CropExclusion.SOURCE_REVISION_NOT_ACCEPTED,
            incomplete: CropExclusion.GEOMETRY_INCOMPLETE,
            half_quads: CropExclusion.BOARD_GEOMETRY_MISSING,
            excluded: CropExclusion.PAGE_SOURCE_EXCLUDED,
            proposed: CropExclusion.PENDING_GRID_PROPOSAL,
            busy: CropExclusion.ACTIVE_IMAGE_JOB,
        }
        for checksum, reason in expected.items():
            assert results[checksum].exclusions == (reason,), (reason, results[checksum])
        # Scoping to game a still judges the shared original against game b.
        assert {item.original_checksum_sha256 for item in scoped} == {eligible, shared, pending}
        assert next(i for i in scoped if i.original_checksum_sha256 == shared).exclusions
        assert len(paged) == 4 and len(after) == len(results) - 4
        assert [item.original_checksum_sha256 for item in only] == [shared]
        with (
            Session(engine) as session,
            session.begin(),
            pytest.raises(ValueError, match="SOURCE_CROP_ELIGIBILITY_SNAPSHOT_REQUIRED"),
        ):
            SourceImageCropRepository(session).eligibility()


def test_a_real_grid_issue_mark_excludes_the_original(
    database: _Database,  # noqa: F811  (the imported fixture)
    tmp_path: Path,
) -> None:
    factory, seed, _artifact_root = _board_game(database, tmp_path, "t1044g")
    with database.engine.connect() as connection:
        checksum = str(
            connection.scalar(
                text("SELECT checksum_sha256 FROM game_data_v2.source_images WHERE id=:s"),
                {"s": seed.source_image_id},
            )
        )

    def reasons() -> tuple[CropExclusion, ...]:
        (result,) = _eligibility(database.engine, only_checksums=[checksum])
        return result.exclusions

    assert CropExclusion.GRID_ISSUE not in reasons()
    _mutate(factory, seed, _item(factory, seed, 0), 0, SymbolCellReviewAction.MARK_GRID_ISSUE)
    assert CropExclusion.GRID_ISSUE in reasons()
