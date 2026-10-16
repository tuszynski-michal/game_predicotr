"""Owned PostgreSQL regression of proposal decisions through the real manual writer."""

from __future__ import annotations

import copy
import json
import os
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from _recording_capability_fixture import OwnedRecordingCapability
from alembic import command
from alembic.config import Config
from game_predictor_api.application.grid_reinference import digest
from game_predictor_api.config import ApiSettings
from game_predictor_api.storage import game_data_v2_manifest_v11 as v11
from game_predictor_api.storage import game_partition_lifecycle as lifecycle
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
)
from game_predictor_api.storage.database_roles import (
    ApplicationRoleSpec,
    provision_application_role,
)
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.grid_geometry_proposal_models import (
    GridGeometryProposalEventModel as Event,
)
from game_predictor_api.storage.grid_geometry_proposal_models import (
    GridGeometryProposalModel as Proposal,
)
from game_predictor_api.storage.grid_geometry_proposals import (
    SqlAlchemyGridGeometryProposalRepository,
)
from game_predictor_api.storage.grid_reinference import (
    SqlAlchemyGridReinferenceRepository,
    target_fence,
)
from game_predictor_api.storage.grid_reinference_models import (
    GridReinferenceOperationModel as Operation,
)
from game_predictor_api.storage.grid_reinference_models import GridReinferenceSourceModel as Source
from game_predictor_api.storage.grid_reinference_models import GridReinferenceTargetModel as Target
from game_predictor_api.storage.models import (
    ImageReviewItemModel,
    ImageSourceGeometryRevisionModel,
    ImageSymbolReviewCellModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
)
from game_predictor_worker.images.pipeline_store import SqlAlchemyImagePipelineStore
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool
from test_v3_engine_acceptance_postgres import execution
from test_virtual_deferred_resolution_postgres import _provision_game

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Owned disposable PostgreSQL only",
)


@pytest.fixture(scope="module")
def database():
    token = uuid4().hex[:12]
    name, role = f"game_predictor_task1013_{token}_test", f"task1013_{token}"
    url = make_url(ApiSettings.from_environment().owner_database_url)
    arguments = {"connect_timeout": 5, "options": "-c statement_timeout=30000"}
    maintenance = create_engine(
        url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
        connect_args=arguments,
    )
    engine = create_engine(url.set(database=name), connect_args=arguments)
    config = Config(str(Path(__file__).resolve().parents[4] / "alembic.ini"))
    config.set_main_option(
        "sqlalchemy.url",
        url.set(database=name).render_as_string(hide_password=False).replace("%", "%%"),
    )
    receipt = {
        "database": name,
        "role": role,
        "pythonPid": os.getpid(),
        "operatorDatabaseChanged": False,
    }
    destination = Path("artifacts/audits/TASK-1013_PG_RECEIPT.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    recording_capability_fixture = OwnedRecordingCapability.for_engine(engine)
    with maintenance.connect() as connection:
        receipt["owner"] = connection.scalar(text("SELECT current_user"))
        recording_capability_fixture.create_database(connection)
    destination.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    try:
        recording_capability_fixture.provision()
        command.upgrade(config, "0158_new_game_v3_bootstrap")
        with ExitStack() as stack:
            for field in ("CREATE_TABLES", "DELETE_TABLES", "VERSION"):
                stack.enter_context(patch.object(lifecycle, field, getattr(v11, field)))
            _provision_game(engine, "task1013-existing-v11")
        command.upgrade(config, "head")
        with engine.begin() as connection:
            recording_capability_fixture.create_runtime_role(connection, role)
            provision_application_role(
                connection, ApplicationRoleSpec(role_name=role, password=None, login=False)
            )
        yield SimpleNamespace(engine=engine, config=config, role=role)
    finally:
        engine.dispose()
        with maintenance.connect() as connection:
            owner = connection.scalar(
                text("SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=:name"),
                {"name": name},
            )
            pids = list(
                connection.scalars(
                    text("SELECT pid FROM pg_stat_activity WHERE datname=:name"), {"name": name}
                )
            )
            receipt.update(ownerBeforeCleanup=owner, pidsBeforeCleanup=pids)
            destination.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
            assert owner == receipt["owner"] and not pids, "Refuse unsafe fixture cleanup"
            recording_capability_fixture.drop_database(connection)
            receipt.update(
                databaseRemaining=connection.scalar(
                    text("SELECT count(*) FROM pg_database WHERE datname=:name"), {"name": name}
                ),
                roleRemaining=connection.scalar(
                    text("SELECT count(*) FROM pg_roles WHERE rolname=:role"), {"role": role}
                ),
                phase="cleaned",
            )
        destination.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        destination.with_name(f"TASK-1013_PG_{token}_RECEIPT.json").write_text(
            json.dumps(receipt, indent=2), encoding="utf-8"
        )
        maintenance.dispose()


def seed_proposal(database, tmp_path):
    from sqlalchemy import event
    from test_virtual_deferred_resolution_postgres import _factory

    def application_factory(engine):
        factory = _factory(engine)

        def role(_session, _transaction, connection):
            connection.exec_driver_sql(f'SET LOCAL ROLE "{database.role}"')

        event.listen(factory, "after_begin", role)
        return factory

    with patch("test_v3_engine_acceptance_postgres._factory", application_factory):
        game, factory, seed, candidate, stages = execution(database, tmp_path)
    with game_storage_scope(game):
        SqlAlchemyImagePipelineStore(factory).project_recognition(candidate, stage_results=stages)
    operation_id, target_id = uuid4(), uuid4()
    with game_storage_scope(game), factory.begin() as session:
        from game_predictor_api.storage.models import SymbolModel

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
        from game_predictor_api.domain.jobs import wait_for_review
        from game_predictor_api.storage.job_repository import apply_job_to_record, job_from_record

        job = session.get(JobModel, seed.import_job_id)
        domain_job = job_from_record(job)
        apply_job_to_record(
            job,
            wait_for_review(
                domain_job, lease_token=domain_job.lease_token, updated_at=datetime.now(UTC)
            ),
        )
        session.flush()
        SqlAlchemyBoardSearchProjectionRepository(session).reconcile_import_job(seed.import_job_id)
        boards = list(
            session.scalars(
                select(RecognizedBoardModel).order_by(RecognizedBoardModel.position_index)
            )
        )
        item = session.scalar(
            select(ImageReviewItemModel).where(
                ImageReviewItemModel.recognized_board_id == boards[0].id
            )
        )
        cell = session.scalar(
            select(ImageSymbolReviewCellModel)
            .where(ImageSymbolReviewCellModel.review_item_id == item.id)
            .limit(1)
        )
        cell.quality_issue, cell.review_state = "grid_issue", "pending"
        SqlAlchemyBoardSearchProjectionRepository(session).sync_review_item(item.id)
        session.flush()
        source = session.execute(
            text("SELECT to_jsonb(s) FROM source_images s WHERE id=:id"),
            {"id": seed.source_image_id},
        ).scalar_one()
        geometry = session.get(
            ImageSourceGeometryRevisionModel, boards[0].source_geometry_revision_id
        )
        repo = SqlAlchemyGridReinferenceRepository(session, tmp_path / "artifacts")
        snapshot = next(
            value
            for value in repo.source_targets(
                game, seed.source_image_id, {"categories": ["grid_issue", "all_automatic"]}
            )
            if value["positionIndex"] == 0
        )
        snapshot["source"] = source
        nodes = [
            {"x": value["x"] + 0.5, "y": value["y"]}
            for value in boards[0].board_geometry["latticeNodes"]
        ]
        result = {
            "schemaVersion": "grid-reinference-target-result-v1",
            "targetResultId": str(target_id),
            "operationId": str(operation_id),
            "sourceImageId": str(seed.source_image_id),
            "positionIndex": 0,
            "outcome": "proposal_ready",
            "frozenFenceSha256": digest(target_fence(snapshot)),
            "geometry": {
                "latticeNodes": nodes,
                "cellVisibility": ["full"] * 15,
                "structurallyValid": True,
            },
        }
        job = session.get(JobModel, seed.import_job_id)
        session.add(
            Operation(
                game_id=game,
                id=operation_id,
                idempotency_key=uuid4(),
                command_sha256="a" * 64,
                job_id=seed.import_job_id,
                document={"modelSnapshot": job.input_payload["neural_grid_proposal"]},
            )
        )
        session.flush()
        session.add(
            Source(
                game_id=game,
                operation_id=operation_id,
                ordinal=1,
                source_image_id=seed.source_image_id,
                live_source_image_id=seed.source_image_id,
                document={"source": source, "geometryContext": {"id": str(geometry.id)}},
            )
        )
        session.flush()
        session.add(
            Target(
                game_id=game,
                operation_id=operation_id,
                ordinal=11,
                source_ordinal=1,
                source_image_id=seed.source_image_id,
                position_index=0,
                target_result_id=target_id,
                snapshot=snapshot,
                fingerprint_sha256=digest(target_fence(snapshot)),
                outcome="proposal_ready",
                result=result,
            )
        )
        item_id = item.id
        counts = {
            table: session.scalar(text(f"SELECT count(*) FROM {table}"))
            for table in (
                "image_review_items",
                "recognized_boards",
                "source_images",
                "image_source_geometry_revisions",
                "image_geometry_rollout_states",
                "image_board_search_fast_documents",
            )
        }
        assert counts["image_board_search_fast_documents"] == 2, counts
    return game, factory, seed, item_id, target_id


@pytest.mark.parametrize("scenario", ["accept", "reject", "stale", "cleanup", "rollback", "edited"])
def test_commands_real_manual_save_and_restart(database, tmp_path, scenario):
    game, factory, seed, review, target = seed_proposal(database, tmp_path)
    root = tmp_path / "artifacts"

    def send(kind, payload, proposal=None):
        with game_storage_scope(game), factory.begin() as session:
            return SqlAlchemyGridGeometryProposalRepository(session, root).command(
                game, seed.import_job_id, review, proposal, kind, payload, "local-owner"
            )

    create = {"targetResultId": str(target), "idempotencyKey": str(uuid4())}
    with game_storage_scope(game), factory.begin() as session:
        repo = SqlAlchemyGridGeometryProposalRepository(session, root)
        assert len(repo.list_proposals(game, seed.import_job_id, review)["candidates"]) == 1
        old = session.scalar(
            select(RecognizedBoardModel).where(RecognizedBoardModel.position_index == 0)
        ).geometry_revision
    created = send("create", create)
    assert created.status == 200
    proposal = UUID(created.current["id"])
    assert send("create", create).receipt == created.receipt
    assert send("create", {**create, "idempotencyKey": str(uuid4())}).current["id"] == str(proposal)
    command_payload = {
        "idempotencyKey": str(uuid4()),
        "expectedProposalRevision": 1,
        "expectedGeometryRevision": old,
        "expectedResolutionRevision": created.current["candidate"]["expectedResolutionRevision"],
        "originalCandidateSha256": created.current["candidate"]["originalCandidateSha256"],
        "mode": "model",
    }
    if scenario == "reject":
        result = send(
            "reject", {"idempotencyKey": str(uuid4()), "expectedProposalRevision": 1}, proposal
        )
        assert result.current["state"] == "rejected"
    elif scenario in {"stale", "cleanup"}:
        with game_storage_scope(game), factory.begin() as session:
            if scenario == "cleanup":
                source = session.scalar(select(Source).where(Source.game_id == game))
                source.live_source_image_id = None
            else:
                cell = session.scalar(
                    select(ImageSymbolReviewCellModel)
                    .where(ImageSymbolReviewCellModel.review_item_id == review)
                    .limit(1)
                )
                cell.revision += 1
        result = send("accept", command_payload, proposal)
        assert result.status == 409 and result.current["state"] == "stale"
        assert send("accept", command_payload, proposal).receipt == result.receipt
        if scenario == "cleanup":
            refused = send("create", {**create, "idempotencyKey": str(uuid4())})
            assert refused.status == 409 and refused.current is None
    elif scenario == "rollback":
        original = SqlAlchemyGridGeometryProposalRepository._view

        def fail_after_write(self, row):
            if row.state == "accepted":
                raise RuntimeError("event response failure")
            return original(self, row)

        with (
            patch.object(SqlAlchemyGridGeometryProposalRepository, "_view", fail_after_write),
            pytest.raises(RuntimeError),
        ):
            send("accept", command_payload, proposal)
        with game_storage_scope(game), factory.begin() as session:
            assert session.get(Proposal, (game, proposal)).state == "pending"
            assert (
                session.scalar(
                    select(RecognizedBoardModel).where(RecognizedBoardModel.position_index == 0)
                ).geometry_revision
                == old
            )
        result = send("accept", command_payload, proposal)
        assert result.status == 200
    else:
        if scenario == "edited":
            geometry = copy.deepcopy(created.current["candidate"]["originalGeometry"])
            for point in geometry["latticeNodes"]:
                point["x"] += 0.25
            geometry["corners"] = [
                {
                    "x": round(geometry["latticeNodes"][index]["x"]),
                    "y": round(geometry["latticeNodes"][index]["y"]),
                }
                for index in (0, 5, 23, 18)
            ]
            command_payload.update(mode="edited", geometry=geometry)
        stale_command = send(
            "accept",
            {**command_payload, "idempotencyKey": str(uuid4()), "expectedProposalRevision": 9},
            proposal,
        )
        assert stale_command.status == 409 and stale_command.current["state"] == "pending"
        result = send("accept", command_payload, proposal)
        assert result.status == 200, result
        assert result.current["state"] == "accepted"
        assert send("accept", command_payload, proposal).receipt == result.receipt
        assert (
            send("accept", {**command_payload, "idempotencyKey": str(uuid4())}, proposal).status
            == 409
        )
    with game_storage_scope(game), factory.begin() as session:
        board = session.scalar(
            select(RecognizedBoardModel).where(RecognizedBoardModel.position_index == 0)
        )
        issue = session.scalar(
            select(ImageSymbolReviewCellModel.id)
            .where(
                ImageSymbolReviewCellModel.review_item_id == review,
                ImageSymbolReviewCellModel.quality_issue == "grid_issue",
            )
            .limit(1)
        )
        if scenario in {"accept", "edited", "rollback"}:
            assert board.geometry_revision == old + 1 and issue is None
            assert board.geometry_approved_by == "local-owner"
        else:
            assert board.geometry_revision == old and issue is not None
    if scenario == "accept":
        create_after_key = uuid4()
        replay_create = send("create", {**create, "idempotencyKey": str(create_after_key)})
        assert replay_create.status == 200 and replay_create.current["id"] == str(proposal)
        assert (
            replay_create.current["state"] == "accepted" and not replay_create.current["applicable"]
        )
        with game_storage_scope(game), factory.begin() as session:
            assert (
                session.scalar(
                    select(RecognizedBoardModel).where(RecognizedBoardModel.position_index == 0)
                ).geometry_revision
                == old + 1
            )
            assert (
                session.scalar(
                    select(Event.kind).where(
                        Event.game_id == game, Event.idempotency_key == create_after_key
                    )
                )
                == "command_completed"
            )


def write_automatic_sibling(factory, game, seed, root):
    from game_predictor_api.application.grid_reinference import ACCEPTANCE_POLICY
    from game_predictor_api.application.virtual_grid_geometry import (
        VirtualGridGeometryService,
        VirtualGridGeometrySourceCommand,
    )
    from game_predictor_api.domain.image_geometry_v2 import (
        AttestedSequenceRange,
        SourceLatticeNodes,
        SourcePoint,
    )
    from game_predictor_api.domain.image_reviews import ImageReviewGeometryPoint
    from game_predictor_api.domain.neural_grid_proposal import (
        NeuralGridSnapshot,
        build_neural_source_binding,
        build_neural_source_proposal,
        lattice_cell_quads,
        lattice_visibility,
    )
    from game_predictor_api.storage.virtual_grid_geometry_repository import (
        SqlAlchemyVirtualGridGeometryRepository,
    )

    with game_storage_scope(game), factory.begin() as session:
        repository = SqlAlchemyVirtualGridGeometryRepository(session)
        service = VirtualGridGeometryService(repository, root)
        rows = SqlAlchemyGridReinferenceRepository(session, root).source_targets(
            game, seed.source_image_id, {"categories": ["all_automatic"]}
        )
        sibling = rows[1]
        source = session.get(SourceImageModel, seed.source_image_id)
        nodes = [
            {"x": p["x"] + 1, "y": p["y"]}
            for p in sibling["board"]["board_geometry"]["latticeNodes"]
        ]
        command = VirtualGridGeometrySourceCommand(
            review_item_id=UUID(sibling["review"]["id"]),
            pending_geometry_id=None,
            expected_geometry_revision=sibling["board"]["geometry_revision"],
            expected_resolution_revision=sibling["review"]["resolution_revision"],
            expected_source_checksum_sha256=source.checksum_sha256,
            expected_source_width=source.oriented_width,
            expected_source_height=source.oriented_height,
            expected_grid_rows=3,
            expected_grid_columns=5,
            corners=tuple(
                ImageReviewGeometryPoint(round(nodes[i]["x"]), round(nodes[i]["y"]))
                for i in (0, 5, 23, 18)
            ),
            lattice_nodes=SourceLatticeNodes(tuple(SourcePoint(p["x"], p["y"]) for p in nodes)),
            expected_proposal_checksum_sha256=sibling["board"]["board_geometry"][
                "neuralProposalChecksumSha256"
            ],
        )
        prepared, _ = service._prepare_source(
            game_id=game,
            import_job_id=seed.import_job_id,
            commands=(command,),
            actor="system:grid-reinference",
            require_complete_source=False,
            automatic=True,
            predict=False,
        )
        pin = session.get(JobModel, seed.import_job_id).input_payload["neural_grid_proposal"]
        detections = []
        for index, row in enumerate(rows):
            current = nodes if index == 1 else row["board"]["board_geometry"]["latticeNodes"]
            quads = lattice_cell_quads(
                current, width=source.oriented_width, height=source.oriented_height
            )
            detections.append(
                {
                    "detectionId": str(index),
                    "score": 0.9,
                    "latticeNodes": current,
                    "cellQuads": [q.to_dict() for q in quads],
                    "cellVisibility": lattice_visibility(
                        quads, width=source.oriented_width, height=source.oriented_height
                    ),
                    "structurallyValid": True,
                    "reasonCodes": ["NEURAL_GRID_GATE_UNCALIBRATED"],
                }
            )
        proposal = build_neural_source_proposal(
            game_id=str(game),
            source_selection_id=str(seed.import_job_id),
            source_checksum_sha256=source.checksum_sha256,
            source_width=source.oriented_width,
            source_height=source.oriented_height,
            original_range=AttestedSequenceRange(start=100, end=101),
            snapshot=NeuralGridSnapshot.from_payload(pin),
            detections=detections,
        )
        binding = build_neural_source_binding(
            proposal,
            confirmed_range=AttestedSequenceRange(start=100, end=101),
            assignments=[{"positionIndex": i, "detectionId": str(i)} for i in range(2)],
        )
        repository.save_automatic_reinference_source(
            prepared=prepared,
            idempotency_key=uuid4(),
            created_at=datetime.now(UTC),
            proposal=proposal,
            binding=binding,
            model_snapshot=pin,
            acceptance_policy=ACCEPTANCE_POLICY,
        )


@pytest.mark.parametrize("rejected_history", [False, True])
def test_mixed_sibling_current_snapshot_is_preserved(database, tmp_path, rejected_history):
    game, factory, seed, review, target = seed_proposal(database, tmp_path)
    root = tmp_path / "artifacts"
    write_automatic_sibling(factory, game, seed, root)
    if rejected_history:
        with game_storage_scope(game), factory.begin() as session:
            sibling = session.scalar(
                select(RecognizedBoardModel).where(RecognizedBoardModel.position_index == 1)
            )
            sibling.status = "rejected"
            session.get(
                ImageSourceGeometryRevisionModel, sibling.source_geometry_revision_id
            ).status = "reverted"
            session.execute(
                text(
                    "DELETE FROM image_sequence_canonical "
                    "WHERE game_id=:game AND sequence_number=101"
                ),
                {"game": game},
            )

    def sibling_snapshot():
        with game_storage_scope(game), factory.begin() as session:
            sibling = session.scalar(
                select(RecognizedBoardModel).where(RecognizedBoardModel.position_index == 1)
            )
            cells = list(
                session.execute(
                    text(
                        "SELECT cell_index,rendered_pixel_checksum_sha256,review_state,"
                        "assigned_symbol_id,revision FROM image_symbol_review_cells "
                        "WHERE recognized_board_id=:id ORDER BY cell_index"
                    ),
                    {"id": sibling.id},
                )
            )
            owner = session.execute(
                text("SELECT to_jsonb(o) FROM image_sequence_canonical o WHERE sequence_number=101")
            ).scalar_one_or_none()
            return (
                sibling.status,
                copy.deepcopy(sibling.board_geometry),
                sibling.geometry_revision,
                sibling.approved_geometry_revision,
                cells,
                owner,
            )

    before = sibling_snapshot()
    with game_storage_scope(game), factory.begin() as session:
        target_board = session.scalar(
            select(RecognizedBoardModel).where(RecognizedBoardModel.position_index == 0)
        )
        sibling = session.scalar(
            select(RecognizedBoardModel).where(RecognizedBoardModel.position_index == 1)
        )
        assert target_board.source_geometry_revision_id != sibling.source_geometry_revision_id
        repo = SqlAlchemyGridGeometryProposalRepository(session, root)
        created = repo.command(
            game,
            seed.import_job_id,
            review,
            None,
            "create",
            {"targetResultId": str(target), "idempotencyKey": str(uuid4())},
            "local-owner",
        )
        assert created.status == 200
        proposal = UUID(created.current["id"])
        original = created.current["candidate"]
    with game_storage_scope(game), factory.begin() as session:
        result = SqlAlchemyGridGeometryProposalRepository(session, root).command(
            game,
            seed.import_job_id,
            review,
            proposal,
            "accept",
            {
                "idempotencyKey": str(uuid4()),
                "expectedProposalRevision": 1,
                "expectedGeometryRevision": original["expectedGeometryRevision"],
                "expectedResolutionRevision": original["expectedResolutionRevision"],
                "originalCandidateSha256": original["originalCandidateSha256"],
                "mode": "model",
            },
            "local-owner",
        )
        assert result.status == 200
    assert sibling_snapshot() == before


def test_real_source_cleanup_retains_proposal_and_error_receipt(database, tmp_path):
    from test_grid_reinference_postgres import cleanup_fixture

    game, factory, seed, review, target = seed_proposal(database, tmp_path)
    root = tmp_path / "artifacts"
    create = {"targetResultId": str(target), "idempotencyKey": str(uuid4())}
    with game_storage_scope(game), factory.begin() as session:
        created = SqlAlchemyGridGeometryProposalRepository(session, root).command(
            game, seed.import_job_id, review, None, "create", create, "local-owner"
        )
    proposal = UUID(created.current["id"])
    cleanup_fixture(database, factory, game, "range")
    with game_storage_scope(game), factory.begin() as session:
        repo = SqlAlchemyGridGeometryProposalRepository(session, root)
        replay = repo.command(
            game, seed.import_job_id, review, None, "create", create, "local-owner"
        )
        assert replay.receipt == created.receipt
        assert not replay.current["applicable"] and "SOURCE_MISSING" in replay.current["reasons"]
        refused_command = {**create, "idempotencyKey": str(uuid4())}
        refused = repo.command(
            game, seed.import_job_id, review, None, "create", refused_command, "local-owner"
        )
        assert refused.status == 409 and refused.current is None
        assert session.get(Proposal, (game, proposal)).document == created.current["candidate"]
    with game_storage_scope(game), factory.begin() as session:
        replay = SqlAlchemyGridGeometryProposalRepository(session, root).command(
            game, seed.import_job_id, review, None, "create", refused_command, "local-owner"
        )
        assert replay.status == 409 and replay.receipt == refused.receipt
        assert session.scalar(select(SourceImageModel.id)) is None
        assert len(list(session.scalars(select(Proposal)))) == 1


def test_discovery_skips_only_invalid_candidate(database, tmp_path):
    from game_predictor_api.domain.image_reviews import ImageReviewNotFoundError

    game, factory, seed, review, target_id = seed_proposal(database, tmp_path)
    root = tmp_path / "artifacts"
    bad_id = uuid4()
    with game_storage_scope(game), factory.begin() as session:
        original = session.scalar(select(Target).where(Target.target_result_id == target_id))
        malformed = copy.deepcopy(original.result)
        malformed.update(targetResultId=str(bad_id), positionIndex=1)
        malformed["geometry"]["latticeNodes"].pop()
        session.add(
            Target(
                game_id=game,
                operation_id=original.operation_id,
                ordinal=12,
                source_ordinal=1,
                source_image_id=original.source_image_id,
                position_index=1,
                target_result_id=bad_id,
                snapshot=copy.deepcopy(original.snapshot),
                fingerprint_sha256=original.fingerprint_sha256,
                outcome="proposal_ready",
                result=malformed,
            )
        )
    with game_storage_scope(game), factory.begin() as session:
        repo = SqlAlchemyGridGeometryProposalRepository(session, root)
        collection = repo.list_proposals(game, seed.import_job_id, review)
        assert [entry["targetResultId"] for entry in collection["candidates"]] == [str(target_id)]
        bad = session.scalar(select(Target).where(Target.target_result_id == bad_id))
        with pytest.raises(ImageReviewNotFoundError) as invalid:
            repo._candidate(bad)
        assert invalid.value.code == "GRID_PROPOSAL_RESULT_INVALID"
        refused = repo.command(
            game,
            seed.import_job_id,
            review,
            None,
            "create",
            {"targetResultId": str(bad_id), "idempotencyKey": str(uuid4())},
            "local-owner",
        )
        assert refused.status == 409 and refused.current is None
        created = repo.command(
            game,
            seed.import_job_id,
            review,
            None,
            "create",
            {"targetResultId": str(target_id), "idempotencyKey": str(uuid4())},
            "local-owner",
        )
        collection = repo.list_proposals(game, seed.import_job_id, review)
        assert collection["proposals"][0]["id"] == created.current["id"]
        assert collection["candidates"] == []


def test_pixels_same_path_and_path_receipt_scope(database, tmp_path):
    game, factory, seed, review, target = seed_proposal(database, tmp_path)
    root = tmp_path / "artifacts"
    create = {"targetResultId": str(target), "idempotencyKey": str(uuid4())}
    with game_storage_scope(game), factory.begin() as session:
        repo = SqlAlchemyGridGeometryProposalRepository(session, root)
        created = repo.command(
            game, seed.import_job_id, review, None, "create", create, "local-owner"
        )
        proposal = UUID(created.current["id"])
        wrong = repo.command(game, uuid4(), review, None, "create", create, "local-owner")
        assert (
            wrong.status == 409
            and wrong.current is None
            and wrong.receipt["code"] == "GRID_PROPOSAL_IDEMPOTENCY_CONFLICT"
        )
        wrong = repo.command(
            game, seed.import_job_id, uuid4(), None, "create", create, "local-owner"
        )
        assert wrong.status == 409 and wrong.current is None
        source = session.get(SourceImageModel, seed.source_image_id)
        path = root / "data" / source.relative_path
    path.write_bytes(path.read_bytes() + b"same-path-drift")
    payload = {
        "idempotencyKey": str(uuid4()),
        "expectedProposalRevision": 1,
        "expectedGeometryRevision": 0,
        "expectedResolutionRevision": created.current["candidate"]["expectedResolutionRevision"],
        "originalCandidateSha256": created.current["candidate"]["originalCandidateSha256"],
        "mode": "model",
    }
    with game_storage_scope(game), factory.begin() as session:
        result = SqlAlchemyGridGeometryProposalRepository(session, root).command(
            game, seed.import_job_id, review, proposal, "accept", payload, "local-owner"
        )
        assert result.status == 409 and result.current["state"] == "stale"
        assert (
            session.scalar(
                select(RecognizedBoardModel).where(RecognizedBoardModel.position_index == 0)
            ).geometry_revision
            == 0
        )
    with game_storage_scope(game), factory.begin() as session:
        replay = SqlAlchemyGridGeometryProposalRepository(session, root).command(
            game, seed.import_job_id, review, proposal, "accept", payload, "local-owner"
        )
        assert replay.receipt == result.receipt


def test_current_live_merge_rechecks_sibling_after_render(database, tmp_path):
    from game_predictor_api.domain.image_grid_reviews import ImageGridReviewError

    game, factory, seed, review, target = seed_proposal(database, tmp_path)
    root = tmp_path / "artifacts"
    with game_storage_scope(game), factory.begin() as session:
        repo = SqlAlchemyGridGeometryProposalRepository(session, root)
        candidate = repo._candidate(repo._target(game, target))
        from game_predictor_api.domain.image_reviews import ImageReviewGeometryPoint
        from game_predictor_api.schemas.image_reviews import (
            OperationalImageReviewGeometryPreviewCommand,
        )
        from game_predictor_api.schemas.source_lattice_geometry import to_source_lattice_nodes

        geometry = OperationalImageReviewGeometryPreviewCommand.model_validate(candidate)
        writer = repo.geometry_repository.save_virtual_geometry_revision

        def race(**kwargs):
            write_automatic_sibling(factory, game, seed, root)
            return writer(**kwargs)

        with (
            patch.object(repo.geometry_repository, "save_virtual_geometry_revision", race),
            pytest.raises(ImageGridReviewError) as failure,
        ):
            repo.geometry.save_review_item(
                game_id=game,
                import_job_id=seed.import_job_id,
                review_item_id=review,
                idempotency_key=uuid4(),
                expected_geometry_revision=0,
                expected_resolution_revision=geometry.expected_resolution_revision,
                corners=tuple(ImageReviewGeometryPoint(p.x, p.y) for p in geometry.corners),
                lattice_nodes=to_source_lattice_nodes(geometry.lattice_nodes),
                geometry_qualification=geometry.geometry_qualification.to_domain(),
                expected_proposal_checksum_sha256=geometry.expected_proposal_checksum_sha256,
                actor="local-owner",
                created_at=datetime.now(UTC),
            )
        assert failure.value.code == "IMAGE_GRID_REVIEW_REVISION_CONFLICT"
    with game_storage_scope(game), factory.begin() as session:
        assert (
            session.scalar(
                select(RecognizedBoardModel).where(RecognizedBoardModel.position_index == 0)
            ).geometry_revision
            == 0
        )
        assert (
            session.scalar(
                select(RecognizedBoardModel).where(RecognizedBoardModel.position_index == 1)
            ).geometry_revision
            == 1
        )


def test_two_game_rls_composite_reference_and_whole_game_lifecycle(database, tmp_path):
    from game_predictor_api.storage.game_partition_lifecycle import (
        CREATE_TABLES,
        GamePartitionLifecycleKind,
        GamePartitionLifecycleRepository,
    )
    from sqlalchemy.exc import DBAPIError
    from sqlalchemy.orm import Session

    game, factory, seed, review, target = seed_proposal(database, tmp_path / "a")
    root = tmp_path / "a" / "artifacts"
    with game_storage_scope(game), factory.begin() as session:
        created = SqlAlchemyGridGeometryProposalRepository(session, root).command(
            game,
            seed.import_job_id,
            review,
            None,
            "create",
            {"idempotencyKey": str(uuid4()), "targetResultId": str(target)},
            "local-owner",
        )
    proposal = UUID(created.current["id"])
    other, other_factory, other_seed, other_review, other_target = seed_proposal(
        database, tmp_path / "b"
    )
    children = {}
    with database.engine.begin() as connection:
        for scoped_game in (game, other):
            for table in ("grid_geometry_proposals", "grid_geometry_proposal_events"):
                child = lifecycle.partition_name(scoped_game, table)
                children[scoped_game, table] = child
                flags = connection.execute(
                    text(
                        "SELECT c.relrowsecurity, c.relforcerowsecurity, "
                        "(SELECT count(*) FROM pg_policy p WHERE p.polrelid=c.oid) "
                        "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                        "WHERE n.nspname='game_data_v2' AND c.relname=:child"
                    ),
                    {"child": child},
                ).one()
                assert tuple(flags) == (True, True, 1), (child, tuple(flags))
                connection.exec_driver_sql(
                    f'GRANT SELECT ON game_data_v2."{child}" TO "{database.role}"'
                )
    with game_storage_scope(other), other_factory.begin() as session:
        repo = SqlAlchemyGridGeometryProposalRepository(session, tmp_path / "b" / "artifacts")
        repo.reinference.bind(other)
        assert session.get(Proposal, (game, proposal)) is None
        assert session.scalar(select(Event.id).where(Event.game_id == game)) is None
        with pytest.raises(DBAPIError), session.begin_nested():
            session.add(
                Proposal(
                    game_id=other,
                    id=uuid4(),
                    target_result_id=target,
                    operation_id=uuid4(),
                    target_ordinal=11,
                    import_job_id=other_seed.import_job_id,
                    review_item_id=other_review,
                    state="pending",
                    revision=1,
                    document={},
                )
            )
            session.flush()
        created_other = repo.command(
            other,
            other_seed.import_job_id,
            other_review,
            None,
            "create",
            {"idempotencyKey": str(uuid4()), "targetResultId": str(other_target)},
            "local-owner",
        )
        assert created_other.status == 200
        for table in ("grid_geometry_proposals", "grid_geometry_proposal_events"):
            foreign_child, own_child = children[game, table], children[other, table]
            assert session.scalar(text(f'SELECT count(*) FROM game_data_v2."{foreign_child}"')) == 0
            assert session.scalar(text(f'SELECT count(*) FROM game_data_v2."{own_child}"')) == 1
    with Session(database.engine) as session, session.begin():
        operation = (
            GamePartitionLifecycleRepository(session)
            .start_or_resume(game_id=game, kind=GamePartitionLifecycleKind.DELETE)
            .operation_id
        )
    for _ in range(len(CREATE_TABLES) + 2):
        with Session(database.engine) as session, session.begin():
            result = GamePartitionLifecycleRepository(session).run_next(operation)
        if result.status == "done":
            break
    assert result.status == "done"
    with database.engine.connect() as connection:
        for table in (
            "grid_geometry_proposals",
            "grid_geometry_proposal_events",
            "grid_reinference_targets",
        ):
            assert (
                connection.scalar(
                    text(f"SELECT count(*) FROM game_data_v2.{table} WHERE game_id=:game"),
                    {"game": game},
                )
                == 0
            )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM game_data_v2.grid_geometry_proposals WHERE game_id=:game"
                ),
                {"game": other},
            )
            == 1
        )
