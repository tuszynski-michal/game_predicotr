"""Existing pages, atomic groups and lost-response replay in an owned test DB."""

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from uuid import uuid4

import pytest
from _application_role_database import application_role_database
from game_predictor_api.application import grid_training_cohort_commands as commands
from game_predictor_api.application.grid_training_cohorts import GridTrainingCohortService
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.grid_training_cohort_models import (
    GridTrainingCohortMemberModel as Member,
)
from game_predictor_api.storage.grid_training_cohort_models import GridTrainingCohortModel as Cohort
from game_predictor_api.storage.grid_training_cohort_models import (
    GridTrainingCohortPageModel as Page,
)
from game_predictor_api.storage.grid_training_cohort_repository import (
    SqlAlchemyGridTrainingCohortRepository as Repository,
)
from sqlalchemy.orm import Session

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Exact-owned disposable PostgreSQL only",
)


def test_legacy_pages_group_rollback_restart_and_replay(tmp_path):
    with application_role_database("t1242", ("throughput",)) as db:
        game, cohort_id = db.games["throughput"], uuid4()

        def service(session):
            return GridTrainingCohortService(Repository(session, tmp_path), tmp_path)

        frozen = {
            "used": False,
            "reasons": ["HUMAN_APPROVAL_REQUIRED"],
            "source": {},
            "positions": [],
            "screenEligible": False,
            "recording": {},
        }
        summary = {
            "previewSha256": "a" * 64,
            "roles": [
                {"role": role, "eligibleBoards": 0, "eligiblePhotos": 0, "eligibleFullPhotos": 0}
                for role in ("TRAIN", "VALIDATION", "REGRESSION")
            ],
            "reasonCounts": {},
        }
        summary["roles"][0].update(eligibleBoards=6, eligiblePhotos=2, eligibleFullPhotos=1)
        with game_storage_scope(game), Session(db.app_engine) as session, session.begin():
            app = service(session)
            app.repository.bind(game, write=True)
            row = Cohort(
                game_id=game,
                id=cohort_id,
                revision=7,
                status="preparing",
                created_by="fixture",
                document={
                    "sourceCount": 31,
                    "mode": "grid-only",
                    "familyId": str(uuid4()),
                    "baseVersionId": str(uuid4()),
                    "policyVersion": "fixture",
                },
                summary=summary,
            )
            session.add(row)
            session.flush()
            session.add_all(
                [
                    Member(
                        game_id=game,
                        cohort_id=cohort_id,
                        source_id=uuid4(),
                        ordinal=i,
                        role="TRAIN",
                        frozen={
                            **frozen,
                            "used": i < 2,
                            "positions": [{"label": {"position": p}} for p in range(3)]
                            if i < 2
                            else [],
                        },
                        live_source_image_id=None,
                    )
                    for i in range(31)
                ]
            )
            session.flush()
            row.status = "preview_ready"
            row.revision = 8
            session.flush()
            descriptor = app.artifacts.publish_json(game, cohort_id, {"legacy": True})
            session.add(
                Page(
                    game_id=game,
                    cohort_id=cohort_id,
                    kind="materialization",
                    page_index=0,
                    path=descriptor["path"],
                    sha256=descriptor["sha256"],
                    document={
                        **descriptor,
                        "sources": [
                            {
                                "role": "TRAIN",
                                "used": i < 2,
                                "boards": 3 if i < 2 else 0,
                                "full": i == 0,
                            }
                            for i in range(5)
                        ],
                    },
                )
            )
            row.status = "materializing"
            row.revision = 9
        old_path = app.artifacts.safe(descriptor["path"])
        old_bytes = old_path.read_bytes()
        body = {"cursor": 5, "expectedRevision": 9, "idempotencyKey": str(uuid4())}
        actual = commands._materialize
        attempts = []

        def interrupt(*args):
            actual(*args)
            attempts.append(True)
            if len(attempts) == 2:
                raise RuntimeError("lost process before commit")

        with (
            pytest.raises(RuntimeError, match="before commit"),
            patch.object(commands, "_materialize", interrupt),
            game_storage_scope(game),
            Session(db.app_engine) as session,
            session.begin(),
        ):
            service(session).command(
                game, cohort_id, "materialize-page", body, "owner", materialization_pages=4
            )
        with game_storage_scope(game), Session(db.app_engine) as session:
            app = service(session)
            header = app.get(game, cohort_id)
            assert header["revision"] == 9 and header["nextMaterializationCursor"] == 5
            assert len(list(app.repository.pages(game, cohort_id, "materialization"))) == 1
        notices = []

        def add_notice():
            from sqlalchemy import text

            with game_storage_scope(game), Session(db.app_engine) as session, session.begin():
                app = service(session)
                app.repository.bind(game, write=True)
                session.execute(text("SET LOCAL lock_timeout='5s'"))
                app.repository.event(game, cohort_id, "currentness_notice", {"fixture": "parallel"})
            return True

        with ThreadPoolExecutor(max_workers=1) as executor:

            def materialize_with_concurrent_notice(*args):
                actual(*args)
                if not notices:
                    # The group's header lock is still held. FK KEY SHARE must succeed now.
                    future = executor.submit(add_notice)
                    notices.append(future.result(timeout=2))

            with (
                patch.object(commands, "_materialize", materialize_with_concurrent_notice),
                game_storage_scope(game),
                Session(db.app_engine) as session,
                session.begin(),
            ):
                response = service(session).command(
                    game, cohort_id, "materialize-page", body, "owner", materialization_pages=4
                )
        assert notices == [True]
        assert response["cohort"]["revision"] == 13
        assert response["cohort"]["nextMaterializationCursor"] == 25
        with game_storage_scope(game), Session(db.app_engine) as session, session.begin():
            app = service(session)
            replay = app.command(game, cohort_id, "materialize-page", body, "owner")
            assert replay == response
            pages = list(app.repository.pages(game, cohort_id, "materialization"))
            assert [page.page_index for page in pages] == [0, 5, 10, 15, 20]
            row = app.repository.cohort(game, cohort_id)
            cached = app.repository.summary_view(row)
            assert cached["roles"][0]["materializedBoards"] == 6
            assert cached["roles"][0]["materializedPhotos"] == 2
            assert cached["roles"][0]["materializedFullPhotos"] == 1
            old_summary = dict(row.summary)
            row.summary = {
                key: value
                for key, value in old_summary.items()
                if key != "materializationProgressV1"
            }
            with session.no_autoflush:
                assert app.repository.summary_view(row) == cached
            session.rollback()
        assert old_path.read_bytes() == old_bytes
        # A new interpreter continues the exact cohort using its committed cursor/counters.
        probe = tmp_path / "read_after_restart.py"
        probe.write_text(
            """import json, os
from uuid import UUID, uuid4
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage import grid_training_cohort_repository as storage
from game_predictor_api.application.grid_training_cohorts import GridTrainingCohortService
engine=create_engine(os.environ['GAME_PREDICTOR_DATABASE_URL'])
g,c=UUID(os.environ['PROBE_GAME']),UUID(os.environ['PROBE_COHORT'])
root=Path(os.environ['PROBE_ROOT'])
with game_storage_scope(g), Session(engine) as session, session.begin():
 repo=storage.SqlAlchemyGridTrainingCohortRepository(session,root)
 service=GridTrainingCohortService(repo,root)
 before=service.get(g,c)
 assert before['revision']==13 and before['nextMaterializationCursor']==25
 body={'expectedRevision':13,'cursor':25,'idempotencyKey':str(uuid4())}
 result=service.command(g,c,'materialize-page',body,'fixture-restart')['cohort']
 print(json.dumps({'revision':result['revision'],'cursor':result['nextMaterializationCursor']}))
engine.dispose()
""",
            encoding="utf-8",
        )
        environment = db.subprocess_environment(
            GAME_PREDICTOR_DATABASE_URL=db.app_url.render_as_string(hide_password=False),
            PROBE_GAME=str(game),
            PROBE_COHORT=str(cohort_id),
            PROBE_ROOT=str(tmp_path),
        )
        result = subprocess.run(
            [sys.executable, str(probe)],
            env=environment,
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        )
        assert json.loads(result.stdout) == {"revision": 14, "cursor": 30}
        assert old_path.read_bytes() == old_bytes
