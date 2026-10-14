"""Frozen historical acceptance on one disposable PostgreSQL database under RLS."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.image_geometry_v2 import canonical_json_bytes
from game_predictor_api.domain.image_reviews import ImageReviewConflictError
from game_predictor_api.storage import game_data_v2_manifest_v7, game_partition_lifecycle
from game_predictor_api.storage import grid_engine_acceptance_repository as acceptance
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.grid_engine_acceptance_models import (
    HistoricalGridAcceptanceOperationModel as Operation,
)
from game_predictor_api.storage.grid_engine_acceptance_models import (
    HistoricalGridAcceptanceReceiptModel as Receipt,
)
from game_predictor_api.storage.models import (
    BoardRenderManifestModel,
    ImageReviewItemModel,
    ImageSequenceCanonicalModel,
    ImageSourceGeometryRevisionModel,
    ImageSymbolReviewCellModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
)
from game_predictor_worker.images.pipeline_store import SqlAlchemyImagePipelineStore
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from test_v3_engine_acceptance_postgres import execution
from test_virtual_deferred_resolution_postgres import _provision_game, _seed
from test_virtual_deferred_resolution_postgres import pytestmark as pytestmark


@pytest.fixture(scope="module")
def database():
    name = "game_predictor_task1008_" + uuid4().hex[:12] + "_test"
    url = make_url(ApiSettings.from_environment().owner_database_url)
    maintenance = create_engine(
        url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 5, "options": "-c statement_timeout=10000"},
    )
    engine = create_engine(url.set(database=name), connect_args={"connect_timeout": 5})
    rendered = url.set(database=name).render_as_string(hide_password=False)
    config = Config(str(Path(__file__).resolve().parents[4] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", rendered.replace("%", "%%"))
    receipt = Path("artifacts/task1008-postgres-receipt.json")
    receipt.parent.mkdir(exist_ok=True)
    receipt.write_text(
        json.dumps({"database": name, "created_by": "TASK-1008", "cleaned": False}),
        encoding="utf-8",
    )
    with maintenance.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    try:
        command.upgrade(config, "head")
        # A no-history down/up is verified before application-role use.
        command.downgrade(config, "0154_geometry_correction_revert")
        with patch.multiple(
            game_partition_lifecycle,
            CREATE_TABLES=game_data_v2_manifest_v7.CREATE_TABLES,
            DELETE_TABLES=game_data_v2_manifest_v7.DELETE_TABLES,
            VERSION=game_data_v2_manifest_v7.VERSION,
        ):
            _provision_game(engine, "task1008-migration-existing")
        command.upgrade(config, "head")
        yield SimpleNamespace(engine=engine, config=config, url=rendered)
    finally:
        engine.dispose()
        with maintenance.connect() as connection:
            active = connection.execute(
                text("SELECT count(*) FROM pg_stat_activity WHERE datname=:name"), {"name": name}
            ).scalar_one()
            assert active == 0, "Refusing to drop a database with open connections"
            connection.exec_driver_sql(f'DROP DATABASE "{name}"')
        maintenance.dispose()
        receipt.write_text(
            json.dumps({"database": name, "created_by": "TASK-1008", "cleaned": True}),
            encoding="utf-8",
        )


def historical(database, tmp_path, *, missing=False):
    game, factory, seed, candidate, stages = execution(database, tmp_path, missing=missing)
    root = tmp_path / "artifacts"
    with game_storage_scope(game), factory.begin() as session:
        job = session.get(JobModel, seed.import_job_id)
        job.input_payload = {
            key: value
            for key, value in job.input_payload.items()
            if key != "v3_engine_acceptance_policy_version"
        }
    with game_storage_scope(game):
        SqlAlchemyImagePipelineStore(factory).project_recognition(candidate, stage_results=stages)
    with game_storage_scope(game), factory.begin() as session:
        revision = session.scalar(
            select(ImageSourceGeometryRevisionModel)
            .order_by(ImageSourceGeometryRevisionModel.revision.desc())
            .limit(1)
        )
        evidence = revision.global_initialization["v3EngineAcceptance"]
        source = session.get(SourceImageModel, seed.source_image_id)
        job = session.get(JobModel, seed.import_job_id)
        selection = str(uuid4())
        manifest = {
            "gameId": str(game),
            "sourceSelectionId": selection,
            "sourceManifestChecksumSha256": "c" * 64,
            "entries": {
                source.checksum_sha256: {
                    "status": "review_required",
                    "neuralProposal": evidence["proposal"],
                    "neuralProposalBinding": evidence["binding"],
                }
            },
        }
        relative = "data/historical-" + uuid4().hex + ".json"
        (root / "data").mkdir(exist_ok=True)
        raw = canonical_json_bytes(manifest)
        (root / relative).write_bytes(raw)
        job.input_payload = {
            **job.input_payload,
            "source_selection_id": selection,
            "source_manifest_sha256": "c" * 64,
            "page_geometry_manifest": {
                "relativePath": relative,
                "checksumSha256": hashlib.sha256(raw).hexdigest(),
            },
        }
        # Manufacture the pre-1017 immutable representation, retaining its
        # original neural proposal and registered model version.
        structured = deepcopy(stages["board_cell_geometry"].payload["structuredGeometry"])
        structured["globalInitialization"].pop("v3EngineAcceptance")
        structured.pop("resultChecksumSha256")
        checksum = hashlib.sha256(canonical_json_bytes(structured)).hexdigest()
        revision.global_initialization = structured["globalInitialization"]
        revision.geometry_checksum_sha256 = checksum
        revision.created_by = "system:image-pipeline-v0.10"
        for board in session.scalars(select(RecognizedBoardModel)):
            board.geometry_checksum_sha256 = checksum
        job.status = "waiting_for_review"
        job.lease_owner = job.lease_token = job.lease_expires_at = job.heartbeat_at = None
        session.flush()
        acceptance.SqlAlchemyBoardSearchProjectionRepository(session).sync_review_items(
            tuple(session.scalars(select(ImageReviewItemModel.id)).all())
        )
        assert revision.status == "needs_review"
    return game, factory, seed, root


def call(factory, game, root, method, *args):
    with game_storage_scope(game), factory.begin() as session:
        # Integration conftest sets a real NOLOGIN/NOBYPASSRLS application role.
        role = (
            session.connection()
            .execute(text("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user"))
            .one()
        )
        assert role == (False, False)
        return getattr(acceptance.SqlAlchemyHistoricalAcceptanceRepository(session, root), method)(
            game, *args
        )


def prepared(factory, game, root):
    report = call(factory, game, root, "create", uuid4())
    for _ in range(10):
        if report.phase != "previewing":
            break
        report = call(
            factory, game, root, "preview_next", report.operation_id, report.preview_cursor
        )
    assert report.phase == "previewed"
    return report


def protected(factory, game, seed):
    with game_storage_scope(game), factory() as session:
        revision = session.scalar(
            select(ImageSourceGeometryRevisionModel)
            .order_by(ImageSourceGeometryRevisionModel.revision.desc())
            .limit(1)
        )
        boards = session.scalars(
            select(RecognizedBoardModel).order_by(RecognizedBoardModel.id)
        ).all()
        cells = session.scalars(
            select(ImageSymbolReviewCellModel).order_by(ImageSymbolReviewCellModel.id)
        ).all()
        renders = session.scalars(
            select(BoardRenderManifestModel).order_by(BoardRenderManifestModel.recognized_board_id)
        ).all()
        items = session.scalars(
            select(ImageReviewItemModel).order_by(ImageReviewItemModel.id)
        ).all()
        canonical = session.scalars(
            select(ImageSequenceCanonicalModel).order_by(
                ImageSequenceCanonicalModel.sequence_number
            )
        ).all()
        return (
            acceptance._hash(
                [
                    acceptance._record(revision, ("status",)),
                    [acceptance._record(board) for board in boards],
                    [acceptance._record(cell) for cell in cells],
                    [acceptance._record(render) for render in renders],
                    [acceptance._record(item) for item in items],
                    [acceptance._record(item) for item in canonical],
                ]
            ),
            revision.status,
            session.get(SourceImageModel, seed.source_image_id).geometry_completeness_status,
        )


def test_status_only_cold_replay_and_confirmation(database, tmp_path):
    game, factory, seed, root = historical(database, tmp_path)
    before = protected(factory, game, seed)
    report = prepared(factory, game, root)
    assert (report.source_count, report.revision_count, report.eligible_count) == (1, 1, 1), (
        report.preview_reasons
    )
    with pytest.raises(ImageReviewConflictError) as caught:
        call(factory, game, root, "run_next", report.operation_id, 0, uuid4())
    assert caught.value.code == "HISTORICAL_ACCEPTANCE_CONFIRMATION_REQUIRED"
    key, run_key = uuid4(), uuid4()
    call(factory, game, root, "confirm", report.operation_id, key)
    result = call(factory, game, root, "run_next", report.operation_id, 0, run_key)
    assert (result.phase, result.accepted_count, result.run_cursor) == ("done", 1, 1), (
        result.run_reasons
    )
    assert call(factory, game, root, "run_next", report.operation_id, 0, run_key) == result
    with pytest.raises(ImageReviewConflictError) as caught:
        call(factory, game, root, "run_next", report.operation_id, 0, uuid4())
    assert caught.value.code == "HISTORICAL_ACCEPTANCE_CURSOR_CONFLICT"
    after = protected(factory, game, seed)
    assert after == (before[0], "accepted", "geometry_complete")
    with game_storage_scope(game), factory() as session:
        assert len(session.scalars(select(Receipt)).all()) == 1
    with pytest.raises(ImageReviewConflictError) as caught:
        call(factory, game, root, "run_next", report.operation_id, 1, run_key)
    assert caught.value.code == "HISTORICAL_ACCEPTANCE_IDEMPOTENCY_CONFLICT"


def test_projection_failure_rolls_status_receipt_and_cursor_back(database, tmp_path, monkeypatch):
    game, factory, seed, root = historical(database, tmp_path)
    before = protected(factory, game, seed)
    report = prepared(factory, game, root)
    call(factory, game, root, "confirm", report.operation_id, uuid4())

    def fail(*_):
        raise RuntimeError("projection fault")

    with monkeypatch.context() as patches:
        patches.setattr(
            acceptance.SqlAlchemyBoardSearchProjectionRepository, "sync_review_items", fail
        )
        with pytest.raises(RuntimeError, match="projection fault"):
            call(factory, game, root, "run_next", report.operation_id, 0, uuid4())
    assert protected(factory, game, seed) == before
    with game_storage_scope(game), factory() as session:
        assert session.get(Operation, (game, report.operation_id)).run_cursor == 0
        assert not session.scalars(select(Receipt)).all()
    assert (
        call(factory, game, root, "run_next", report.operation_id, 0, uuid4()).accepted_count == 1
    )


@pytest.mark.parametrize("change", ["mixed_revision", "grid_issue", "snapshot", "owner"])
def test_frozen_drift_and_ambiguity_are_skipped(database, tmp_path, change):
    game, factory, seed, root = historical(database, tmp_path)
    report = prepared(factory, game, root)
    with game_storage_scope(game), factory.begin() as session:
        board = session.scalar(select(RecognizedBoardModel).limit(1))
        if change == "mixed_revision":
            board.geometry_checksum_sha256 = "d" * 64
        elif change == "grid_issue":
            cell = session.scalar(select(ImageSymbolReviewCellModel).limit(1))
            cell.quality_issue, cell.review_state = "grid_issue", "pending"
        elif change == "snapshot":
            job = session.get(JobModel, seed.import_job_id)
            job.input_payload = {**job.input_payload, "neural_grid_proposal": {"drift": True}}
        else:
            item = session.scalar(
                select(ImageReviewItemModel).where(
                    ImageReviewItemModel.recognized_board_id == board.id
                )
            )
            item.sequence_number = 9000
    before = protected(factory, game, seed)
    call(factory, game, root, "confirm", report.operation_id, uuid4())
    result = call(factory, game, root, "run_next", report.operation_id, 0, uuid4())
    assert result.accepted_count == 0
    assert result.skipped_count == 1
    assert result.run_reasons == {"HISTORICAL_FROZEN_REVISION_CONFLICT": 1}
    assert protected(factory, game, seed) == before


def test_partial_missing_positions_are_never_accepted(database, tmp_path):
    game, factory, seed, root = historical(database, tmp_path, missing=True)
    before = protected(factory, game, seed)
    report = prepared(factory, game, root)
    assert report.eligible_count == 0
    assert "V3_ACCEPTANCE_DEFERRED" in report.preview_reasons
    call(factory, game, root, "confirm", report.operation_id, uuid4())
    result = call(factory, game, root, "run_next", report.operation_id, 0, uuid4())
    assert result.skipped_count == 1 and result.accepted_count == 0
    assert protected(factory, game, seed) == before


def test_initial_mixed_cell_revision_and_late_source_are_explicitly_excluded(database, tmp_path):
    game, factory, seed, root = historical(database, tmp_path)
    with game_storage_scope(game), factory.begin() as session:
        old = session.scalar(
            select(ImageSourceGeometryRevisionModel)
            .order_by(ImageSourceGeometryRevisionModel.revision)
            .limit(1)
        )
        cell = session.scalar(select(ImageSymbolReviewCellModel).limit(1))
        assert old.id != cell.source_geometry_revision_id
        cell.source_geometry_revision_id = old.id
    created = call(factory, game, root, "create", uuid4())
    # A later source can have an arbitrary UUID; the persisted time anchor
    # excludes it before UUID pagination is applied.
    _seed(factory, game, root, label="late-source-" + uuid4().hex, slot_count=2)
    report = created
    for _ in range(10):
        if report.phase != "previewing":
            break
        report = call(
            factory, game, root, "preview_next", report.operation_id, report.preview_cursor
        )
    assert report.phase == "previewed"
    assert report.source_count == 1
    assert report.preview_reasons["HISTORICAL_MIXED_CELL_OR_RENDER_REVISION"] == 1
    assert report.eligible_count == 0


def test_operation_cannot_cross_game_and_legacy_7_is_excluded(database, tmp_path):
    from game_predictor_api.domain.image_reviews import ImageReviewNotFoundError

    game, factory, _seeded, root = historical(database, tmp_path)
    report = prepared(factory, game, root)
    foreign = _provision_game(database.engine, "task1008-foreign-" + uuid4().hex[:8])
    with pytest.raises(ImageReviewNotFoundError) as caught:
        call(factory, foreign, root, "report", report.operation_id)
    assert caught.value.code == "HISTORICAL_ACCEPTANCE_OPERATION_NOT_FOUND"
    legacy = _provision_game(database.engine, "7")
    with pytest.raises(ImageReviewConflictError) as caught:
        call(factory, legacy, root, "create", uuid4())
    assert caught.value.code == "HISTORICAL_ACCEPTANCE_LEGACY_GAME_EXCLUDED"
