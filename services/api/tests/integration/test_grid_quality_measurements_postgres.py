"""Small owned UUID fixture: real runtime/RLS capture, approval and retained evidence."""

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from _recording_capability_fixture import OwnedRecordingCapability
from alembic import command
from alembic.config import Config
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.image_reviews import ImageReviewConflictError
from game_predictor_api.storage.database_roles import (
    ApplicationRoleSpec,
    provision_application_role,
)
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.grid_geometry_approvals import (
    SqlAlchemyGridGeometryApprovalRepository,
)
from game_predictor_api.storage.grid_quality_measurements import (
    SqlAlchemyGridQualityMeasurementRepository,
)
from game_predictor_api.storage.grid_reinference_retention import detach_grid_source_links
from game_predictor_api.storage.models import GameModel
from game_predictor_api.storage.source_recording_permissions_v2 import recording_permission_errors
from game_predictor_worker.images.pipeline_store import SqlAlchemyImagePipelineStore
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import NullPool
from test_v3_engine_acceptance_postgres import execution
from test_virtual_deferred_resolution_postgres import _factory, _provision_game

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit owned disposable PostgreSQL only",
)


@pytest.fixture(scope="module")
def database():
    token = uuid4().hex[:12]
    name, role = f"game_predictor_task1009_{token}_test", f"task1009_{token}"
    url = make_url(ApiSettings.from_environment().owner_database_url)
    options = {"connect_timeout": 5, "options": "-c statement_timeout=30000"}
    maintenance = create_engine(
        url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
        connect_args=options,
    )
    engine = create_engine(url.set(database=name), poolclass=NullPool, connect_args=options)
    config = Config(str(Path(__file__).resolve().parents[4] / "alembic.ini"))
    config.set_main_option(
        "sqlalchemy.url", engine.url.render_as_string(hide_password=False).replace("%", "%%")
    )
    owned = OwnedRecordingCapability.for_engine(engine)
    receipt = {"database": name, "runtimeRole": role, "operatorDatabaseChanged": False}
    destination = Path(f"artifacts/audits/TASK-1009_PG_{token}.json")
    with maintenance.connect() as connection:
        owned.create_database(connection)
    try:
        owned.provision()
        command.upgrade(config, "0161_source_recording_groups")
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    text(
                        "SELECT to_regprocedure('public.resolve_own_groups("
                        "uuid,uuid[],uuid,integer,uuid,uuid)')"
                    )
                )
                is None
            )
        command.upgrade(config, "head")
        command.downgrade(config, "0161_source_recording_groups")
        command.upgrade(config, "head")
        with engine.begin() as connection:
            owned.create_runtime_role(connection, role)
            provision_application_role(
                connection, ApplicationRoleSpec(role_name=role, password=None, login=False)
            )
            assert recording_permission_errors(connection, role) == ()
        receipt["emptyDowngradeReupgrade"] = True
        yield SimpleNamespace(engine=engine, config=config, role=role)
    finally:
        engine.dispose()
        with maintenance.connect() as connection:
            receipt["idleBeforeCleanup"] = owned.wait_for_owned_database_idle(connection)
            assert receipt["idleBeforeCleanup"] == 0
            owned.drop_database(connection)
            receipt["databaseRemaining"] = connection.scalar(
                text("SELECT count(*) FROM pg_database WHERE datname=:name"), {"name": name}
            )
            receipt["runtimeRoleRemaining"] = connection.scalar(
                text("SELECT count(*) FROM pg_roles WHERE rolname=:role"), {"role": role}
            )
        receipt["phase"] = "cleaned"
        destination.write_text(json.dumps(receipt, indent=2))
        maintenance.dispose()


def seed(database, tmp_path, *, legacy=False, processing=False):
    def factory(engine):
        result = _factory(engine)

        def runtime(_session, _transaction, connection):
            connection.exec_driver_sql(f'SET LOCAL ROLE "{database.role}"')

        event.listen(result, "after_begin", runtime)
        return result

    with patch("test_v3_engine_acceptance_postgres._factory", factory):
        game, sessions, source, candidate, stages = execution(database, tmp_path, legacy=legacy)
    with game_storage_scope(game):
        SqlAlchemyImagePipelineStore(sessions).project_recognition(candidate, stage_results=stages)
    with game_storage_scope(game), sessions.begin() as session:
        session.get(GameModel, game).shape_geometry_configuration = "grid_profile_mumie_v1"
        if not processing:
            from game_predictor_api.domain.jobs import wait_for_review
            from game_predictor_api.storage.board_search_projection_repository import (
                SqlAlchemyBoardSearchProjectionRepository,
            )
            from game_predictor_api.storage.job_repository import (
                apply_job_to_record,
                job_from_record,
            )
            from game_predictor_api.storage.models import JobModel

            job = session.get(JobModel, source.import_job_id)
            domain_job = job_from_record(job)
            apply_job_to_record(
                job,
                wait_for_review(
                    domain_job, lease_token=domain_job.lease_token, updated_at=datetime.now(UTC)
                ),
            )
            session.flush()
            SqlAlchemyBoardSearchProjectionRepository(session).reconcile_import_job(
                source.import_job_id
            )
    return game, sessions, source, tmp_path / "artifacts"


def capture(sessions, game, root, hard):
    body = {
        "idempotencyKey": str(uuid4()),
        "seed": "frozen-seed",
        "sampleSize": 100,
        "hardSourceIds": [str(hard)],
    }
    with game_storage_scope(game), sessions.begin() as session:
        response = SqlAlchemyGridQualityMeasurementRepository(session, root).capture(
            game, body, "fixture-human"
        )
    return body, response


def test_runtime_capture_cold_replay_approval_and_retention(database, tmp_path, monkeypatch):
    game, sessions, source, root = seed(database, tmp_path)
    body, result = capture(sessions, game, root, source.source_image_id)
    view = result["current"]
    assert view["frozenPopulationCount"] == 1 and len(view["members"]) == 2
    member = next(value for value in view["members"] if value["sampleKind"] == "random")
    assert len(member["positions"]) == 9
    assert [value["original"]["available"] for value in member["positions"]] == [True, True] + [
        False
    ] * 7
    assert member["available"] and member["recordingStatus"] == "unresolved"
    assert view["report"]["random"]["axes"]["geometry"]["correctRate"] is None
    with game_storage_scope(game), sessions.begin() as session:
        replay = SqlAlchemyGridQualityMeasurementRepository(session, root).capture(
            game, body, "fixture-human"
        )
        assert replay["receipt"] == result["receipt"]
    child_code = """
import json,os,re
from pathlib import Path
from uuid import UUID
from sqlalchemy import create_engine,event
from sqlalchemy.orm import sessionmaker
from game_predictor_api.storage.database import GameStorageSession
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.grid_quality_measurements import (
    SqlAlchemyGridQualityMeasurementRepository,
)
engine=create_engine(os.environ['TASK1009_FIXTURE_URL'],connect_args={'connect_timeout':5})
role=os.environ['TASK1009_FIXTURE_ROLE']
assert re.fullmatch(r'task1009_[0-9a-f]{12}',role)
factory=sessionmaker(engine,class_=GameStorageSession)
def restricted(session,transaction,connection):
    connection.exec_driver_sql('SET LOCAL ROLE "'+role+'"')
event.listen(factory,'after_begin',restricted)
try:
    game=UUID(os.environ['TASK1009_GAME'])
    with game_storage_scope(game),factory.begin() as session:
        result=SqlAlchemyGridQualityMeasurementRepository(session,Path(os.environ['TASK1009_ROOT'])).capture(
            game,json.loads(os.environ['TASK1009_COMMAND']),'fixture-human')
        print(json.dumps({'receipt':result['receipt'],'manifestSha256':result['current']['manifestSha256']}))
finally:
    engine.dispose()
"""
    environment = os.environ.copy()
    repository_root = Path(__file__).resolve().parents[4]
    environment.update(
        TASK1009_FIXTURE_URL=database.engine.url.render_as_string(hide_password=False),
        TASK1009_FIXTURE_ROLE=database.role,
        TASK1009_GAME=str(game),
        TASK1009_ROOT=str(root),
        TASK1009_COMMAND=json.dumps(body),
        PYTHONPATH=os.pathsep.join(
            str(repository_root / part)
            for part in ("services/api/src", "services/worker/src", "services/test_support")
        ),
    )
    cold = subprocess.run(
        [sys.executable, "-c", child_code],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        cwd=repository_root,
    )
    assert cold.returncode == 0, cold.stdout + cold.stderr
    cold_result = json.loads(cold.stdout)
    assert cold_result["receipt"] == result["receipt"]
    assert cold_result["manifestSha256"] == view["manifestSha256"]
    position = member["positions"][0]
    assert position["approvalEligible"]
    approval = {
        "idempotencyKey": str(uuid4()),
        "measurementId": view["measurementId"],
        "sourceId": str(source.source_image_id),
        "sampleKind": "random",
        "positionIndex": 0,
        "manifestSha256": view["manifestSha256"],
        "targetSha256": position["targetSha256"],
    }

    def state(session):
        SqlAlchemyGridQualityMeasurementRepository(session, root).bind(game)
        return session.connection().execute(
            text(
                "SELECT to_jsonb(b)-'approved_geometry_revision'-'geometry_approved_at'"
                "-'geometry_approved_by' "
                "FROM recognized_boards b WHERE game_id=:game ORDER BY position_index"
            ),
            {"game": game},
        ).scalars().all(), session.connection().execute(
            text(
                "SELECT to_jsonb(c) FROM image_symbol_review_cells c WHERE game_id=:game "
                "ORDER BY id"
            ),
            {"game": game},
        ).scalars().all()

    with game_storage_scope(game), sessions.begin() as session:
        before = state(session)
    with game_storage_scope(game), sessions.begin() as session:
        approved = SqlAlchemyGridGeometryApprovalRepository(session, root).approve(
            game, source.import_job_id, UUID(position["reviewItemId"]), approval, "fixture-human"
        )
        assert approved["receipt"]["geometryRevision"] == 0
        assert state(session) == before
    with game_storage_scope(game), sessions.begin() as session:
        assert (
            SqlAlchemyGridGeometryApprovalRepository(session, root).approve(
                game,
                source.import_job_id,
                UUID(position["reviewItemId"]),
                approval,
                "fixture-human",
            )
            == approved
        )
        assert (
            session.connection().scalar(
                text(
                    "SELECT count(*) FROM image_board_geometry_review_events WHERE game_id=:game "
                    "AND action='approved'"
                ),
                {"game": game},
            )
            == 1
        )
    judgment = {
        "idempotencyKey": str(uuid4()),
        "sourceId": str(source.source_image_id),
        "sampleKind": "random",
        "expectedRevision": 0,
        "manifestSha256": view["manifestSha256"],
        "positions": [
            {
                "positionIndex": index,
                "geometry": "correct",
                "detection": "correct",
                "sequence": "correct",
            }
            for index in range(9)
        ],
        "unexpected": [],
    }
    with game_storage_scope(game), sessions() as session:
        with pytest.raises(ImageReviewConflictError, match="Missing original"):
            SqlAlchemyGridQualityMeasurementRepository(session, root).assess(
                game, UUID(view["measurementId"]), judgment, "fixture-human"
            )
        session.rollback()

    for item in judgment["positions"][2:]:
        item.update(geometry="not_assessable", detection="unknown", sequence="unknown")
    with game_storage_scope(game), sessions.begin() as session:
        assessed = SqlAlchemyGridQualityMeasurementRepository(session, root).assess(
            game, UUID(view["measurementId"]), judgment, "fixture-human"
        )
        assert assessed["current"]["report"]["random"]["fullyReviewedCount"] == 1
        assert assessed["current"]["report"]["random"]["completeCorrectCount"] == 0
    with game_storage_scope(game), sessions.begin() as session:
        repo = SqlAlchemyGridQualityMeasurementRepository(session, root)
        assert (
            repo.assess(game, UUID(view["measurementId"]), judgment, "fixture-human")["receipt"]
            == assessed["receipt"]
        )
        detach_grid_source_links(session, game, [source.source_image_id])
        retained = repo.get(game, UUID(view["measurementId"]))
        assert retained["manifestSha256"] == view["manifestSha256"]
        assert all(not value["available"] for value in retained["members"])
        assert retained["report"]["random"]["axes"]["geometry"]["correct"] == 2
    with game_storage_scope(game), sessions() as session:
        SqlAlchemyGridQualityMeasurementRepository(session, root).bind(game, write=True)
        with pytest.raises(DBAPIError, match="GRID_QUALITY_IMMUTABLE_HISTORY"):
            session.connection().execute(
                text(
                    "UPDATE grid_quality_measurement_members "
                    "SET live_source_image_id=source_id WHERE game_id=:game"
                ),
                {"game": game},
            )
        session.rollback()
    with pytest.raises(Exception, match="GRID_QUALITY_DOWNGRADE_HAS_HISTORY"):
        command.downgrade(database.config, "0161_source_recording_groups")
    with database.engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == "0162_grid_quality_measurements"
        )


def test_two_game_rls_private_denial_and_reprovision(database, tmp_path):
    from game_predictor_api.application.source_recording_groups import SourceRecordingGroupsService
    from game_predictor_api.schemas.source_recording_groups import SourceRecordingCommandRequest
    from game_predictor_api.storage.source_recording_groups import (
        SqlAlchemySourceRecordingRepository,
    )

    game, sessions, source, root = seed(database, tmp_path)
    _, result = capture(sessions, game, root, source.source_image_id)

    def registry(kind, **values):
        payload = SourceRecordingCommandRequest.model_validate(
            {"kind": kind, "idempotencyKey": str(uuid4()), **values}
        )
        with game_storage_scope(game), sessions.begin() as session:
            response = SourceRecordingGroupsService(
                SqlAlchemySourceRecordingRepository(session), root
            ).execute(game, payload, "fixture-human")
            assert response["statusCode"] == 200
            return response["group"]

    group = registry("prepare", selection={"sourceIds": [str(source.source_image_id)]})
    group = registry(
        "attach",
        groupId=group["id"],
        manifestId=group["manifestId"],
        pageIndex=0,
        expectedRevision=group["revision"],
    )
    with game_storage_scope(game), sessions.begin() as session:
        snapshot = SqlAlchemyGridQualityMeasurementRepository(session, root).get(
            game, UUID(result["current"]["measurementId"])
        )
        assert all(member["recordingStatus"] == "unresolved" for member in snapshot["members"])
    group = registry("complete", groupId=group["id"], expectedRevision=group["revision"])
    group = registry(
        "declare",
        groupId=group["id"],
        expectedRevision=group["revision"],
        independenceConfirmed=True,
    )
    other = _provision_game(database.engine, "task1009-other-" + uuid4().hex[:8])
    with database.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO game_data_v2.grid_quality_measurements "
                "(game_id,id,manifest_path,manifest_sha256,document) "
                "VALUES(:game,:id,'fixture-only',:sha,'{}'::jsonb)"
            ),
            {"game": other, "id": uuid4(), "sha": "a" * 64},
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM game_data_v2.grid_quality_measurements "
                    "WHERE game_id=:game"
                ),
                {"game": other},
            )
            == 1
        )
    with game_storage_scope(game), sessions.begin() as session:
        SqlAlchemyGridQualityMeasurementRepository(session, root).bind(game)
        connection = session.connection()
        assert (
            connection.scalar(
                text("SELECT count(*) FROM grid_quality_measurements WHERE game_id=:other"),
                {"other": other},
            )
            == 0
        )
        assert (
            connection.scalar(
                text(
                    "SELECT public.resolve_own_groups(CAST(:game AS uuid),NULL::uuid[],"
                    "NULL::uuid,1,NULL::uuid,"
                    "CAST(:source AS uuid))"
                ),
                {"game": game, "source": source.source_image_id},
            )["items"][0]["id"]
            == group["id"]
        )
        snapshot = SqlAlchemyGridQualityMeasurementRepository(session, root).get(
            game, UUID(result["current"]["measurementId"])
        )
        assert all(member["recordingStatus"] == "declared" for member in snapshot["members"])
    with game_storage_scope(game), sessions() as session:
        with pytest.raises(DBAPIError):
            session.connection().execute(text("SELECT * FROM public.recording_occurrences"))
        session.rollback()
    with database.engine.begin() as connection:
        provision_application_role(
            connection, ApplicationRoleSpec(role_name=database.role, password=None, login=False)
        )
        assert recording_permission_errors(connection, database.role) == ()


def test_unknown_original_producer_can_approve_frozen_current_and_projection_failure_rolls_back(
    database, tmp_path, monkeypatch
):
    from game_predictor_api.storage.board_search_projection_repository import (
        SqlAlchemyBoardSearchProjectionRepository,
    )

    game, sessions, source, root = seed(database, tmp_path, legacy=True)
    _, result = capture(sessions, game, root, source.source_image_id)
    view = result["current"]
    member = next(value for value in view["members"] if value["sampleKind"] == "random")
    position = member["positions"][0]
    assert not position["original"]["available"] and position["original"]["producer"] is None
    assert position["current"]["available"] and position["approvalEligible"]
    approval = {
        "idempotencyKey": str(uuid4()),
        "measurementId": view["measurementId"],
        "sourceId": str(source.source_image_id),
        "sampleKind": "random",
        "positionIndex": 0,
        "manifestSha256": view["manifestSha256"],
        "targetSha256": position["targetSha256"],
    }

    def broken_projection(*_args):
        raise RuntimeError("fixture-projection-rollback")

    with monkeypatch.context() as scoped:
        scoped.setattr(
            SqlAlchemyBoardSearchProjectionRepository, "sync_review_item", broken_projection
        )
        with (
            pytest.raises(RuntimeError, match="fixture-projection-rollback"),
            game_storage_scope(game),
            sessions.begin() as session,
        ):
            SqlAlchemyGridGeometryApprovalRepository(session, root).approve(
                game,
                source.import_job_id,
                UUID(position["reviewItemId"]),
                approval,
                "fixture-human",
            )
    with game_storage_scope(game), sessions.begin() as session:
        SqlAlchemyGridQualityMeasurementRepository(session, root).bind(game)
        assert (
            session.connection().scalar(
                text("SELECT count(*) FROM grid_geometry_approval_commands WHERE game_id=:game"),
                {"game": game},
            )
            == 0
        )
        assert (
            session.connection().scalar(
                text(
                    "SELECT approved_geometry_revision FROM recognized_boards "
                    "WHERE game_id=:game AND position_index=0"
                ),
                {"game": game},
            )
            is None
        )
        receipt = SqlAlchemyGridGeometryApprovalRepository(session, root).approve(
            game, source.import_job_id, UUID(position["reviewItemId"]), approval, "fixture-human"
        )
        assert receipt["receipt"]["kind"] == "approved_unchanged"
        current = SqlAlchemyGridQualityMeasurementRepository(session, root).get(
            game, UUID(view["measurementId"])
        )
        assert current["report"]["random"]["producerCoverage"]["provenPositionCount"] == 0
        assert current["report"]["random"]["axes"]["geometry"]["correctRate"] is None


def test_actual_browser_source_deletion_retains_measurement_and_capture_receipt(database, tmp_path):
    from game_predictor_api.storage.browser_staging_retention_repository import (
        SqlAlchemyBrowserStagingRetentionRepository,
    )
    from game_predictor_api.storage.models import JobModel, SourceImageModel
    from test_virtual_deferred_resolution_postgres import _seed

    game = _provision_game(database.engine, "task1009-retain-" + uuid4().hex[:8])
    sessions = _factory(database.engine)

    def restricted(_session, _transaction, connection):
        connection.exec_driver_sql(f'SET LOCAL ROLE "{database.role}"')

    event.listen(sessions, "after_begin", restricted)
    root = tmp_path / "artifacts"
    source = _seed(sessions, game, root, label="task1009-retention", slot_count=1)
    upload = uuid4()
    with game_storage_scope(game), sessions.begin() as session:
        session.get(GameModel, game).shape_geometry_configuration = "grid_profile_mumie_v1"
        job = session.get(JobModel, source.import_job_id)
        job.input_payload = {**job.input_payload, "source_selection_id": str(upload)}
    body, captured = capture(sessions, game, root, source.source_image_id)
    original = captured["current"]
    SqlAlchemyBrowserStagingRetentionRepository(sessions).discard_unused(
        upload_id=upload, game_id=game
    )
    with game_storage_scope(game), sessions.begin() as session:
        repo = SqlAlchemyGridQualityMeasurementRepository(session, root)
        repo.bind(game)
        assert session.get(SourceImageModel, source.source_image_id) is None
        replay = repo.capture(game, body, "fixture-human")
        assert replay["receipt"] == captured["receipt"]
        assert replay["current"]["manifestSha256"] == original["manifestSha256"]
        assert all(not member["available"] for member in replay["current"]["members"])
        assert all(
            member["unavailableReason"] == "SOURCE_UNAVAILABLE"
            for member in replay["current"]["members"]
        )


def test_real_geometry_writer_preserves_original_and_sibling_measurement(database, tmp_path):
    from game_predictor_api.application.virtual_grid_geometry import VirtualGridGeometryService
    from game_predictor_api.domain.geometry_qualification import GeometryQualification
    from game_predictor_api.domain.image_geometry_v2 import SourceLatticeNodes, SourcePoint
    from game_predictor_api.domain.image_reviews import ImageReviewGeometryPoint
    from game_predictor_api.storage.board_search_projection_repository import (
        SqlAlchemyBoardSearchProjectionRepository,
    )
    from game_predictor_api.storage.models import SymbolModel
    from game_predictor_api.storage.virtual_grid_geometry_repository import (
        SqlAlchemyVirtualGridGeometryRepository,
    )

    game, sessions, source, root = seed(database, tmp_path)
    with game_storage_scope(game), sessions.begin() as session:
        SqlAlchemyGridQualityMeasurementRepository(session, root).bind(game, write=True)
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
        session.flush()
        reviews = (
            session.connection()
            .scalars(text("SELECT id FROM image_review_items WHERE game_id=:game"), {"game": game})
            .all()
        )
        for review in reviews:
            SqlAlchemyBoardSearchProjectionRepository(session).sync_review_item(review)
    _, result = capture(sessions, game, root, source.source_image_id)
    before = result["current"]
    member = next(value for value in before["members"] if value["sampleKind"] == "random")
    changed, sibling = member["positions"][:2]
    judgments = [
        {
            "positionIndex": index,
            "geometry": "correct" if index < 2 else "not_assessable",
            "detection": "correct" if index < 2 else "unknown",
            "sequence": "correct" if index < 2 else "unknown",
        }
        for index in range(9)
    ]
    with game_storage_scope(game), sessions.begin() as session:
        SqlAlchemyGridQualityMeasurementRepository(session, root).assess(
            game,
            UUID(before["measurementId"]),
            {
                "idempotencyKey": str(uuid4()),
                "sourceId": str(source.source_image_id),
                "sampleKind": "random",
                "expectedRevision": 0,
                "manifestSha256": before["manifestSha256"],
                "positions": judgments,
                "unexpected": [],
            },
            "fixture-human",
        )
    nodes = [
        SourcePoint(point["x"] + 1, point["y"])
        for row in changed["current"]["nodes"]
        for point in row
    ]
    with game_storage_scope(game), sessions.begin() as session:
        SqlAlchemyGridQualityMeasurementRepository(session, root).bind(game, write=True)
        saved = VirtualGridGeometryService(
            SqlAlchemyVirtualGridGeometryRepository(
                session, source_snapshot_policy="current_live_slots"
            ),
            root,
        ).save_review_item(
            game_id=game,
            import_job_id=source.import_job_id,
            review_item_id=UUID(changed["reviewItemId"]),
            idempotency_key=uuid4(),
            expected_geometry_revision=0,
            expected_resolution_revision=0,
            corners=tuple(
                ImageReviewGeometryPoint(round(nodes[i].x), round(nodes[i].y))
                for i in (0, 5, 23, 18)
            ),
            lattice_nodes=SourceLatticeNodes(tuple(nodes)),
            geometry_qualification=GeometryQualification(),
            expected_proposal_checksum_sha256=changed["current"]["geometry"][
                "neuralProposalChecksumSha256"
            ],
            actor="fixture-human",
            created_at=datetime.now(UTC),
        )
        assert saved.created
    with game_storage_scope(game), sessions.begin() as session:
        current = SqlAlchemyGridQualityMeasurementRepository(session, root).get(
            game, UUID(before["measurementId"])
        )
        after_member = next(
            value for value in current["members"] if value["sampleKind"] == "random"
        )
        assert after_member["positions"][0]["original"] == changed["original"]
        assert after_member["positions"][1]["original"] == sibling["original"]
        assert after_member["judgments"] == judgments
        assert not after_member["positions"][0]["approvalEligible"]
        assert after_member["positions"][1]["approvalEligible"]
        assert after_member["positions"][0]["current"]["nodes"] != changed["current"]["nodes"]
    _, recaptured = capture(sessions, game, root, source.source_image_id)
    fresh = next(
        value for value in recaptured["current"]["members"] if value["sampleKind"] == "random"
    )
    assert (
        fresh["positions"][0]["original"]["producer"]["sourceRevisionId"]
        == changed["original"]["producer"]["sourceRevisionId"]
    )
    assert fresh["positions"][0]["original"]["nodes"] == changed["original"]["nodes"]
    assert fresh["positions"][1]["original"]["producer"] is None
    assert fresh["positions"][1]["original"]["reason"] == "PRODUCER_COVERAGE_GAP"
    assert fresh["positions"][1]["approvalEligible"]
    approval = {
        "idempotencyKey": str(uuid4()),
        "measurementId": before["measurementId"],
        "sourceId": str(source.source_image_id),
        "sampleKind": "random",
        "positionIndex": 1,
        "manifestSha256": before["manifestSha256"],
        "targetSha256": sibling["targetSha256"],
    }
    with game_storage_scope(game), sessions.begin() as session:
        receipt = SqlAlchemyGridGeometryApprovalRepository(session, root).approve(
            game, source.import_job_id, UUID(sibling["reviewItemId"]), approval, "fixture-human"
        )
        assert receipt["receipt"]["geometryRevision"] == 0
    approval.update(
        idempotencyKey=str(uuid4()), positionIndex=0, targetSha256=changed["targetSha256"]
    )
    with game_storage_scope(game), sessions() as session:
        with pytest.raises(ImageReviewConflictError, match="changed"):
            SqlAlchemyGridGeometryApprovalRepository(session, root).approve(
                game, source.import_job_id, UUID(changed["reviewItemId"]), approval, "fixture-human"
            )
        session.rollback()


def test_processing_import_is_measured_but_cannot_bypass_canonical_writer_eligibility(
    database, tmp_path
):
    from game_predictor_api.domain.image_grid_reviews import ImageGridReviewError
    from game_predictor_api.storage.virtual_grid_geometry_repository import (
        SqlAlchemyVirtualGridGeometryRepository,
    )

    game, sessions, source, root = seed(database, tmp_path, processing=True)
    _, result = capture(sessions, game, root, source.source_image_id)
    view = result["current"]
    member = next(value for value in view["members"] if value["sampleKind"] == "random")
    position = member["positions"][0]
    assert len(member["positions"]) == 9 and position["original"]["available"]
    assert not position["approvalEligible"]
    assert position["approvalBlocker"] == "IMAGE_GRID_REVIEW_ITEM_NOT_FOUND"
    with game_storage_scope(game), sessions() as session:
        SqlAlchemyGridQualityMeasurementRepository(session, root).bind(game)
        with pytest.raises(ImageGridReviewError, match="does not exist"):
            SqlAlchemyVirtualGridGeometryRepository(session).virtual_geometry_context(
                game_id=game,
                import_job_id=source.import_job_id,
                review_item_id=UUID(position["reviewItemId"]),
                pending_geometry_id=None,
            )
        session.rollback()

    approval = {
        "idempotencyKey": str(uuid4()),
        "measurementId": view["measurementId"],
        "sourceId": str(source.source_image_id),
        "sampleKind": "random",
        "positionIndex": 0,
        "manifestSha256": view["manifestSha256"],
        "targetSha256": position["targetSha256"],
    }
    with game_storage_scope(game), sessions() as session:
        with pytest.raises(ImageReviewConflictError, match="not eligible"):
            SqlAlchemyGridGeometryApprovalRepository(session, root).approve(
                game,
                source.import_job_id,
                UUID(position["reviewItemId"]),
                approval,
                "fixture-human",
            )
        session.rollback()


def test_concurrent_capture_key_returns_409_then_exact_replay_without_duplicate_manifest(
    database, tmp_path
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from fastapi.testclient import TestClient
    from game_predictor_api.application.grid_quality_measurements import (
        GridQualityMeasurementService,
    )
    from game_predictor_api.main import create_app
    from game_predictor_api.storage.database import assign_session_game

    game, sessions, source, root = seed(database, tmp_path)
    entered, release = Event(), Event()
    publications = []
    capture_snapshot = SqlAlchemyGridQualityMeasurementRepository._capture_snapshot

    def held_snapshot(repository, *arguments):
        publications.append(arguments[0])
        entered.set()
        assert release.wait(5), "Bounded concurrent request fixture did not release its winner"
        return capture_snapshot(repository, *arguments)

    def dependency():
        with sessions.begin() as session:
            assign_session_game(session, game)
            yield SimpleNamespace(
                grid_quality_measurements=GridQualityMeasurementService(
                    SqlAlchemyGridQualityMeasurementRepository(session, root)
                )
            )

    app = create_app(
        ApiSettings(
            host="127.0.0.1",
            port=8000,
            admin_origin="http://127.0.0.1:3000",
            artifact_root=root,
            database_url=database.engine.url.render_as_string(hide_password=False),
        ),
        image_review_service_dependency=dependency,
    )
    body = {
        "idempotencyKey": str(uuid4()),
        "seed": "concurrent-capture",
        "sampleSize": 1,
        "hardSourceIds": [str(source.source_image_id)],
    }
    path = f"/api/v1/admin/games/{game}/grid-quality-measurements/capture"

    def request():
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            return client.post(
                path,
                json=body,
                headers={"Origin": "http://127.0.0.1:3000", "X-Admin-Intent": "local-owner"},
            )

    with (
        patch.object(
            SqlAlchemyGridQualityMeasurementRepository, "_capture_snapshot", held_snapshot
        ),
        ThreadPoolExecutor(max_workers=2) as pool,
    ):
        first = pool.submit(request)
        try:
            assert entered.wait(5), "Winner did not reach its RR population snapshot"
            second = pool.submit(request).result(timeout=5)
            assert second.status_code == 409
            assert second.json()["code"] == "GRID_QUALITY_CAPTURE_BUSY"
        finally:
            release.set()
        first = first.result(timeout=30)
    assert first.status_code == 200
    replay = request()
    assert replay.status_code == 200
    assert replay.json()["receipt"] == first.json()["receipt"]
    assert replay.json()["current"]["manifestSha256"] == first.json()["current"]["manifestSha256"]
    assert len(publications) == 1
    assert len(list((root / "grid-quality/manifests").glob("*.json"))) == 1
    assert not list((root / "grid-quality/manifests").glob("*.staged"))
    with game_storage_scope(game), sessions.begin() as session:
        SqlAlchemyGridQualityMeasurementRepository(session, root).bind(game)
        for table in ("grid_quality_measurements", "grid_quality_measurement_commands"):
            assert (
                session.connection().scalar(
                    text(f"SELECT count(*) FROM {table} WHERE game_id=:game"), {"game": game}
                )
                == 1
            )
