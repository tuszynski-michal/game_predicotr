"""TASK-0882: populated partition migration and cold source-binding recovery."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from copy import deepcopy
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from _application_role_database import ALEMBIC_INI, application_role_database
from _virtual_board_fixtures import ensure_source_geometry
from alembic import command
from alembic.config import Config
from game_predictor_api.application.page_geometry_overrides import PageGeometryOverrideService
from game_predictor_api.domain.catalog import GameShapeGeometryConfiguration
from game_predictor_api.domain.grid_engine_profiles import grid_engine_profile_for
from game_predictor_api.domain.image_geometry_v2 import AttestedSequenceRange
from game_predictor_api.domain.jobs import JobConflictError, JobType, create_job
from game_predictor_api.domain.neural_grid_proposal import (
    NeuralGridSnapshot,
    build_neural_source_binding,
    build_neural_source_proposal,
    lattice_cell_quads,
    lattice_visibility,
)
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_storage_routing import GameStorageIntent, GameStorageRouter
from game_predictor_api.storage.job_repository import job_record_from_domain
from game_predictor_api.storage.models import ImageFileExecutionModel, SourceImageModel
from game_predictor_api.storage.page_geometry_override_repository import (
    SqlAlchemyPageGeometryOverrideRepository,
)
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit disposable PostgreSQL tests only.",
)


def _proposal(game_id: UUID) -> dict[str, object]:
    profile = grid_engine_profile_for(GameShapeGeometryConfiguration.GRID_PROFILE_MUMIE_V1)
    assert profile is not None
    detections = []
    for index in range(4):
        nodes = [
            {
                "x": 10.125 + index % 3 * 150 + column * 20.25,
                "y": 10.375 + index // 3 * 100 + row * 20.125,
            }
            for row in range(4)
            for column in range(6)
        ]
        nodes[8]["x"] += 0.3125
        quads = lattice_cell_quads(nodes, width=500, height=300)
        detections.append(
            {
                "detectionId": chr(97 + index),
                "score": 0.9,
                "latticeNodes": nodes,
                "cellQuads": [quad.to_dict() for quad in quads],
                "cellVisibility": lattice_visibility(quads, width=500, height=300),
                "structurallyValid": True,
                "reasonCodes": ["NEURAL_GRID_GATE_UNCALIBRATED"],
            }
        )
    return build_neural_source_proposal(
        game_id=str(game_id),
        source_selection_id=str(uuid4()),
        source_checksum_sha256="a" * 64,
        source_width=500,
        source_height=300,
        original_range=AttestedSequenceRange(101, 105),
        snapshot=NeuralGridSnapshot.for_game(500000, profile.current),
        detections=detections,
    )


def _geometry(engine, game_id: UUID, label: str) -> UUID:
    job = create_job(
        JobType.IMPORT, game_id=game_id, input_payload={"schema_version": 1, "fixture": label}
    )
    checksum = "b" * 64 if label == "legacy" else "c" * 64
    key = "d" * 64 if label == "legacy" else "e" * 64
    with create_session_factory(engine)() as session, session.begin():
        GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.WRITE)
        session.add(job_record_from_domain(job))
        session.add(
            ImageFileExecutionModel(
                file_execution_key=key,
                source_checksum_sha256=checksum,
                pipeline_fingerprint="f" * 64,
                checkpoint_payload={},
                status="waiting_for_review",
                review_required=True,
            )
        )
        session.flush()
        source = SourceImageModel(
            import_job_id=job.id,
            file_execution_key=key,
            relative_path=f"{label}.jpg",
            checksum_sha256=checksum,
            width=500,
            height=300,
            status="waiting_for_review",
        )
        session.add(source)
        session.flush()
        geometry = ensure_source_geometry(
            session,
            game_id=game_id,
            source=source,
            sequence_range_start=101,
            created_at=datetime.now(UTC),
        )
        return geometry.id


def _save(session, proposal, binding, expected):
    return PageGeometryOverrideService(
        SqlAlchemyPageGeometryOverrideRepository(session)
    ).save_neural_binding(
        game_id=UUID(proposal["gameId"]),
        source_checksum_sha256=proposal["sourceChecksumSha256"],
        image_width=500,
        image_height=300,
        proposal=proposal,
        binding=binding,
        actor="test-owner",
        expected_override_revision=expected,
    )


def test_0145_preserves_old_partitions_validates_binding_and_recovers_in_new_process():
    # The database starts at 0144 (not downgraded from head, which 0148-0150 forbid).
    with application_role_database(
        "t0882", ("mumie-pilot", "legacy777"), revision="0144_lab_symbol_candidate_registry"
    ) as database:
        assert database.owner_url.database.endswith("_test")
        assert database.owner_url.database != "game_predictor"
        game_id, legacy_id = database.games["mumie-pilot"], database.games["legacy777"]
        config = Config(str(ALEMBIC_INI))
        config.set_main_option(
            "sqlalchemy.url",
            database.owner_url.render_as_string(hide_password=False).replace("%", "%%"),
        )
        legacy_geometry = _geometry(database.owner_engine, legacy_id, "legacy")
        mumie_geometry = _geometry(database.owner_engine, game_id, "mumie")
        old_id = uuid4()
        quad = [
            [{"x": 10, "y": 10}, {"x": 100, "y": 10}, {"x": 100, "y": 100}, {"x": 10, "y": 100}]
        ]
        insert = text("""INSERT INTO game_data_v2.image_page_geometry_overrides
            (id,game_id,source_checksum_sha256,image_width,image_height,final_quads,
             revision,actor,decision_checksum_sha256)
            VALUES (:id,:game,:source,500,300,CAST(:quads AS jsonb),:revision,'test-owner',:sha)""")
        with database.owner_engine.begin() as connection:
            connection.execute(
                insert,
                {
                    "id": old_id,
                    "game": legacy_id,
                    "source": "9" * 64,
                    "quads": json.dumps(quad),
                    "revision": 1,
                    "sha": "8" * 64,
                },
            )
        command.upgrade(config, "0145_neural_page_geometry_binding")
        with database.owner_engine.connect() as connection:
            old = connection.execute(
                text("""SELECT final_quads, neural_proposal_binding
                FROM game_data_v2.image_page_geometry_overrides WHERE game_id=:game AND id=:id"""),
                {"game": legacy_id, "id": old_id},
            ).one()
            assert old == (quad, None)
            # ALTER parent must propagate the new nullable column to populated
            # children, rather than only working for newly provisioned games.
            children = (
                connection.execute(
                    text("""SELECT c.oid::regclass::text
                FROM pg_inherits i JOIN pg_class c ON c.oid=i.inhrelid
                WHERE i.inhparent='game_data_v2.image_page_geometry_overrides'::regclass""")
                )
                .scalars()
                .all()
            )
            assert len(children) >= 2
            for child in children:
                assert (
                    connection.scalar(
                        text("""SELECT count(*) FROM pg_attribute
                    WHERE attrelid=CAST(:child AS regclass) AND attname='neural_proposal_binding'
                    AND NOT attisdropped"""),
                        {"child": child},
                    )
                    == 1
                )
        with pytest.raises(IntegrityError), database.owner_engine.begin() as connection:
            connection.execute(
                insert,
                {
                    "id": uuid4(),
                    "game": legacy_id,
                    "source": "7" * 64,
                    "quads": "[]",
                    "revision": 1,
                    "sha": "6" * 64,
                },
            )
        value = _proposal(game_id)
        selected = build_neural_source_binding(
            value,
            confirmed_range=AttestedSequenceRange(101, 105),
            assignments=[
                {"detectionId": "a", "positionIndex": 0},
                {"detectionId": "b", "positionIndex": 1},
                {"detectionId": "c", "positionIndex": 3},
                {"detectionId": "d", "positionIndex": 4},
            ],
        )
        invalid = []
        for field, bad in [
            ("sourceSelectionId", None),
            ("originalRange", {}),
            ("confirmedRange", {}),
            ("assignments", [None]),
            ("assignments", [{"detectionId": "a", "positionIndex": 9}]),
            ("missingPositionIndexes", [None]),
            ("ignoredDetectionIds", [None]),
            ("sourceChecksumSha256", int("1" * 64)),
            ("proposalChecksumSha256", int("2" * 64)),
        ]:
            changed = deepcopy(selected)
            changed[field] = bad
            invalid.append(changed)
        for changed in invalid:
            with pytest.raises(IntegrityError), database.owner_engine.begin() as connection:
                connection.execute(
                    text("""INSERT INTO game_data_v2.image_page_geometry_overrides
                    (id,game_id,source_checksum_sha256,image_width,image_height,final_quads,
                     neural_proposal_binding,revision,actor,decision_checksum_sha256)
                    VALUES (:id,:game,:source,500,300,'[]',CAST(:binding AS jsonb),
                            99,'test-owner',:sha)"""),
                    {
                        "id": uuid4(),
                        "game": game_id,
                        "source": str(changed["sourceChecksumSha256"]),
                        "binding": json.dumps(changed),
                        "sha": "5" * 64,
                    },
                )
        with create_session_factory(database.app_engine)() as session, session.begin():
            first, created = _save(session, value, selected, 0)
            assert created and first.final_quads == ()
            assert first.neural_proposal_binding["missingPositionIndexes"] == [2]
        replacement = build_neural_source_binding(
            value, confirmed_range=AttestedSequenceRange(101, 105), assignments=[]
        )
        with create_session_factory(database.app_engine)() as session, session.begin():
            second, created = _save(session, value, replacement, 1)
            assert created and second.revision == 2
            with pytest.raises(JobConflictError) as stale:
                _save(
                    session,
                    value,
                    build_neural_source_binding(
                        value,
                        confirmed_range=AttestedSequenceRange(101, 105),
                        assignments=[{"detectionId": "a", "positionIndex": 0}],
                    ),
                    0,
                )
            assert stale.value.code == "IMAGE_PAGE_GEOMETRY_REVISION_CONFLICT"
        script = """
import json,sys
from uuid import UUID
from sqlalchemy import create_engine
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.application.page_geometry_overrides import PageGeometryOverrideService
from game_predictor_api.storage.page_geometry_override_repository import (
 SqlAlchemyPageGeometryOverrideRepository,
)
data=json.loads(sys.stdin.read())
engine=create_engine(data['url'],connect_args={'connect_timeout':5})
try:
 with create_session_factory(engine)() as session,session.begin():
  repository=SqlAlchemyPageGeometryOverrideRepository(session)
  service=PageGeometryOverrideService(repository)
  receipt,created=service.save_neural_binding(game_id=UUID(data['game']),
   source_checksum_sha256='a'*64,image_width=500,image_height=300,
   proposal=data['proposal'],binding=data['binding'],actor='test-owner',expected_override_revision=0)
  current=repository.get_current(game_id=UUID(data['game']),source_checksum_sha256='a'*64)
  print(json.dumps({'receipt':str(receipt.id),'created':created,'currentRevision':current.revision,
    'binding':receipt.neural_proposal_binding}))
finally:
 engine.dispose()
"""
        process = subprocess.run(
            [sys.executable, "-c", script],
            input=json.dumps(
                {
                    "url": database.app_url.render_as_string(hide_password=False),
                    "game": str(game_id),
                    "proposal": value,
                    "binding": selected,
                }
            ),
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        assert process.returncode == 0, "Cold source-binding receipt recovery failed."
        assert json.loads(process.stdout) == {
            "receipt": str(first.id),
            "created": False,
            "currentRevision": 2,
            "binding": selected,
        }
        with create_session_factory(database.app_engine)() as session, session.begin():
            assert (
                SqlAlchemyPageGeometryOverrideRepository(session).get_current(
                    game_id=legacy_id, source_checksum_sha256="a" * 64
                )
                is None
            )
        with (
            pytest.raises(DBAPIError, match="GAME_STORAGE_SCOPE_REQUIRED"),
            database.app_engine.connect() as connection,
        ):
            connection.scalar(
                text("SELECT count(*) FROM game_data_v2.image_page_geometry_overrides")
            )
        with database.owner_engine.begin() as connection:
            connection.execute(
                text("""UPDATE game_data_v2.image_source_geometry_revisions
                SET engine_kind='neural_grid_v1',status='needs_review'
                WHERE game_id=:game AND id=:id"""),
                {"game": game_id, "id": mumie_geometry},
            )
            assert (
                connection.scalar(
                    text("""SELECT engine_kind
                FROM game_data_v2.image_source_geometry_revisions
                WHERE game_id=:game AND id=:id"""),
                    {"game": legacy_id, "id": legacy_geometry},
                )
                == "structured_opencv_v1"
            )
        with pytest.raises(Exception, match="NEURAL_PAGE_GEOMETRY_DOWNGRADE_HAS_HISTORY"):
            command.downgrade(config, "0144_lab_symbol_candidate_registry")
        with database.owner_engine.connect() as connection:
            assert (
                connection.scalar(text("SELECT version_num FROM public.alembic_version"))
                == "0145_neural_page_geometry_binding"
            )
