"""One owned DB/source: real RLS reader, exact snapshot pins and a cold process."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from _application_role_database import application_role_database
from game_predictor_api.domain.grid_model_registry import descriptor_sha256
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.grid_cell_content import SqlAlchemyGridCellContentRepository
from game_predictor_api.storage.grid_quality_observations import read_source
from game_predictor_api.storage.grid_training_cohort_models import GridTrainingCohortModel
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from test_grid_training_cohort_e2e_postgres import _install_base, _save_source
from test_v3_engine_acceptance_postgres import current_partition_budget  # noqa: F401

from services.worker.tests.test_grid_cohort_dataset import SnapshotFixture

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1", reason="Owned disposable PG only"
)


def guarded_engine(url, expected):
    assert re.fullmatch(r"game_predictor_t1168targets_[0-9a-f]{12}_test", expected)
    assert make_url(url).database == expected if isinstance(url, str) else url.database == expected
    engine = create_engine(url, connect_args={"connect_timeout": 5})

    @event.listens_for(engine, "connect")
    def guard(connection, _record):
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database()")
            assert cursor.fetchone()[0] == expected
            cursor.execute("SET statement_timeout='10s'")
            cursor.execute("SET lock_timeout='5s'")
        connection.commit()

    return engine


COLD = r"""
import json,os,re
from pathlib import Path
from uuid import UUID
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.grid_cell_content import SqlAlchemyGridCellContentRepository
url,expected=os.environ['TEST_DATABASE_URL'],os.environ['TEST_DATABASE_NAME']
assert re.fullmatch(r'game_predictor_t1168targets_[0-9a-f]{12}_test',expected)
assert make_url(url).database==expected
engine=create_engine(url,connect_args={'connect_timeout':5})
with engine.connect() as connection:
 assert connection.scalar(text('SELECT current_database()'))==expected
game,cohort=UUID(os.environ['TEST_GAME']),UUID(os.environ['TEST_COHORT'])
with game_storage_scope(game),create_session_factory(engine)() as session:
 repo=SqlAlchemyGridCellContentRepository(session,Path(os.environ['TEST_ROOT']))
 page=repo.list_targets(game,cohort,os.environ['TEST_MANIFEST'],20,0)
 assert len(page['items'])==1 and page['items'][0]['state']=='ready'
 assert page['items'][0]['displayName']==os.environ['TEST_DISPLAY_NAME']
 assert repo.get(game,UUID(page['items'][0]['source']['sourceId']),0)['annotation'] is None
engine.dispose()
print('Cold explicit owned target reader PASS',flush=True)
"""

CLEAN = r"""
import os,re,json
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url
from game_predictor_api.config import ApiSettings
name,role,cap=os.environ['TEST_DATABASE_NAME'],os.environ['TEST_ROLE'],os.environ['TEST_CAPABILITY']
assert re.fullmatch(r'game_predictor_t1168targets_[0-9a-f]{12}_test',name)
engine=create_engine(make_url(ApiSettings.from_environment().owner_database_url).set(database='postgres'),connect_args={'connect_timeout':5})
with engine.connect() as connection:
 assert connection.scalar(text('SELECT current_database()'))=='postgres'
 counts=[connection.scalar(text('SELECT count(*) FROM pg_database WHERE datname=:n'),{'n':name}),
 connection.scalar(text('SELECT count(*) FROM pg_roles WHERE rolname IN (:r,:c)'),
 {'r':role,'c':cap})]
 assert counts==[0,0],counts
engine.dispose()
print('Fresh cleanup: 0 owned databases / 0 owned roles',flush=True)
"""


def test_real_target_reader_and_source_pin_survive_new_process(tmp_path):
    with application_role_database("t1168targets", ("content-target-reader",)) as owned:
        print("T1168 targets own database migrated", flush=True)
        expected = owned.owner_url.database
        owner, app = (
            guarded_engine(owned.owner_url, expected),
            guarded_engine(owned.app_url, expected),
        )
        db = replace(owned, owner_engine=owner, app_engine=app)
        environment = owned.subprocess_environment(
            TEST_DATABASE_NAME=expected,
            TEST_DATABASE_URL=owned.app_url.render_as_string(hide_password=False),
            TEST_ROLE=owned.role,
            TEST_CAPABILITY=owned.recording_capability.role,
        )
        try:
            game = db.games["content-target-reader"]
            _install_base(db, game)
            source, _checksums, _import = _save_source(db, tmp_path, game, 1, 1, {})
            print("T1168 targets one real source ready", flush=True)
            factory = create_session_factory(app)
            with game_storage_scope(game), factory() as session:
                repo = SqlAlchemyGridCellContentRepository(session, tmp_path)
                repo.bind(game)
                identity = read_source(session, game, source)
                logical_name = session.scalar(
                    text("""
                    SELECT f.source_relative_path FROM source_images s
                    JOIN image_import_job_files f
                      ON f.game_id=s.game_id AND f.job_id=s.import_job_id
                      AND f.file_execution_key=s.file_execution_key
                    WHERE s.game_id=:game AND s.id=:source
                    """),
                    {"game": game, "source": source},
                )
            assert identity is not None
            assert isinstance(logical_name, str) and logical_name.strip()
            expected_name = logical_name.replace("\\", "/").rsplit("/", 1)[-1]
            cohort = uuid4()
            fixture = SnapshotFixture(tmp_path)
            fixture.game, fixture.cohort = str(game), str(cohort)
            fixture.directory = f"data/grid-training-cohorts/{game}/{cohort}"
            frozen = fixture.source()
            frozen.update(
                sourceId=str(source), sourceIdentity=identity, purposeProofSha256="c" * 64
            )
            assert "logicalName" not in frozen and "logicalName" not in frozen["sourceIdentity"]
            frozen["targets"][0]["sequenceNumber"] = 110
            frozen["original"] = fixture.pin(
                f"{fixture.directory}/originals/pinned.jpg",
                (tmp_path / "data" / identity["relative_path"]).read_bytes(),
            )
            split = {
                "schemaVersion": "grid-correction-split-v4",
                "purposeCounts": {},
                "sources": [
                    {
                        "sourceId": str(source),
                        "representative": True,
                        "role": "TRAIN",
                        "purposeProofSha256": "c" * 64,
                        "eligibleBoards": 1,
                    }
                ],
            }
            split["sha256"] = descriptor_sha256(split)
            snapshot = fixture.publish(
                change=lambda manifest: manifest.update(
                    schemaVersion="application-grid-snapshot-v4",
                    policyVersion="application-grid-corrections-v4",
                    photoSplit=split,
                )
            )
            pin = fixture.manifest_pin
            with game_storage_scope(game), factory.begin() as session:
                repo = SqlAlchemyGridCellContentRepository(session, tmp_path)
                repo.bind(game, write=True)
                session.add(
                    GridTrainingCohortModel(
                        game_id=game,
                        id=cohort,
                        status="frozen",
                        document={},
                        summary={},
                        manifest_path=pin["path"],
                        manifest_sha256=pin["sha256"],
                        created_by="fixture",
                    )
                )
            with game_storage_scope(game), factory() as session:
                repo = SqlAlchemyGridCellContentRepository(session, tmp_path)
                page = repo.list_targets(game, cohort, pin["sha256"], 20, 0)
                assert page["items"][0]["sequenceNumber"] == 110
                assert page["items"][0]["state"] == "ready"
                assert page["items"][0]["displayName"] == expected_name
                assert "/" not in page["items"][0]["displayName"]
                assert "\\" not in page["items"][0]["displayName"]
                assert repo.get(game, source, 0)["annotation"] is None
                assert (
                    repo.target_source_asset(game, cohort, pin["sha256"], source).read_bytes()
                    == (tmp_path / "data" / identity["relative_path"]).read_bytes()
                )
            assert snapshot.manifest["cohortId"] == str(cohort)
            environment.update(
                TEST_GAME=str(game),
                TEST_COHORT=str(cohort),
                TEST_MANIFEST=pin["sha256"],
                TEST_ROOT=str(tmp_path),
                TEST_DISPLAY_NAME=expected_name,
            )
            subprocess.run([sys.executable, "-c", COLD], env=environment, timeout=30, check=True)
            receipt = {
                "database": expected,
                "game": str(game),
                "coldRead": True,
                "displayName": expected_name,
                "actualImportNameRead": True,
            }
        finally:
            app.dispose()
            owner.dispose()
    subprocess.run([sys.executable, "-c", CLEAN], env=environment, timeout=30, check=True)
    receipt.update(cleanupDatabases=0, cleanupRoles=0)
    Path("artifacts/TASK-1168_R2_API-pg-receipt.json").write_text(
        json.dumps(receipt, indent=2), encoding="utf-8"
    )
