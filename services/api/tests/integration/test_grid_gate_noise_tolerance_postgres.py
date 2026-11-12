"""Gate v4 binding (D-604) on real SQL: exact pairs, grants and history guard."""

import json
import os
from uuid import uuid4

import pytest
from _application_role_database import application_role_database
from game_predictor_api.domain.grid_model_registry import canonical_json, descriptor_sha256
from game_predictor_api.storage.source_recording_permissions_v11 import recording_permission_errors
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_grid_correction_registry_postgres import scope
from test_grid_model_evaluation_bridge_postgres import _config
from test_production_cell_report_bind_postgres import seed

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit task-owned disposable PostgreSQL only",
)


def invoke(db, game, request):
    with Session(db.app_engine) as session, session.begin():
        scope(session, game)
        return session.scalar(
            text("SELECT public.recording_cohort_command_v8(:g,CAST(:q AS jsonb),'fixture:1188')"),
            {"g": game, "q": json.dumps(request)},
        )


def test_gate_v4_pairs_bind_only_through_the_new_function_and_history_survives():
    from alembic import command

    with application_role_database(
        "t1188gate", ("gate-v4",), revision="0185_grid_gate_noise_tolerance"
    ) as db:
        config = _config(db)
        # Empty downgrade is reversible; roles keep only the public wrapper grant.
        command.downgrade(config, "0184_effective_grid_material")
        command.upgrade(config, "0185_grid_gate_noise_tolerance")
        with db.owner_engine.connect() as connection:
            assert recording_permission_errors(connection, db.role) == ()
        game = next(iter(db.games.values()))
        original, request = seed(db, game)
        pairs = [
            ("v3", "grid-model-per-game-gate-v4", True),
            ("v5", "grid-model-per-game-gate-v4", True),
            ("v3", "grid-model-per-game-gate-v2", True),
            ("v4", "grid-model-per-game-gate-v4", False),
            ("v6", "grid-model-per-game-gate-v4", False),
        ]
        for schema, policy, allowed in pairs:
            identifier = uuid4()
            document = {
                **original,
                "schemaVersion": "grid-model-evaluation-read-" + schema,
                "policyVersion": policy,
            }
            with db.owner_engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO public.grid_model_evaluation_reports"
                        "(id,version_id,producer,report_json,report_sha256) VALUES(:i,:v,:p,:j,:s)"
                    ),
                    {
                        "i": identifier,
                        "v": original["versionId"],
                        "p": document["producer"],
                        "j": canonical_json(document),
                        "s": descriptor_sha256(document),
                    },
                )
            payload = {**request, "reportId": str(identifier), "idempotencyKey": str(uuid4())}
            if allowed:
                receipt = invoke(db, game, payload)
                assert receipt["reportSha256"] == descriptor_sha256(document)
                assert invoke(db, game, payload) == receipt
            else:
                with pytest.raises(DBAPIError, match="RECORDING_BINDING_INVALID"):
                    invoke(db, game, payload)
        with pytest.raises(RuntimeError, match="history prevents downgrade"):
            command.downgrade(config, "0184_effective_grid_material")
