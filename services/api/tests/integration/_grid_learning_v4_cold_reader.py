"""Read-only fresh-process probe of the owned v4 fixture; credentials arrive via stdin."""

import json
import sys
from uuid import UUID

from game_predictor_api.domain.grid_model_registry import descriptor_sha256
from game_predictor_api.storage.game_storage_routing import GameStorageIntent, GameStorageRouter
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

v = json.load(sys.stdin)
engine = create_engine(
    v.pop("url"), connect_args={"connect_timeout": 5, "options": "-c statement_timeout=10000"}
)
with Session(engine) as s:
    assert s.scalar(text("SELECT current_database()")).startswith("game_predictor_t1159v4_")
    GameStorageRouter().bind(s, UUID(v["game"]), intent=GameStorageIntent.READ)
    p = s.scalar(text("SELECT input_payload FROM public.jobs WHERE id=:id"), {"id": v["parent"]})
    pin = p["pins"]
    manifest = s.scalar(
        text(
            "SELECT manifest_sha256 FROM grid_training_cohorts WHERE game_id=:game AND id=:cohort"
        ),
        v,
    )
    r = s.scalar(text("SELECT input_payload FROM public.jobs WHERE id=:id"), {"id": v["run"]})
    result = {
        "policyVersion": pin["policyVersion"],
        "trainingMode": pin["trainingMode"],
        "validationAssignments": pin["validationAssignments"],
        "pinSha256": descriptor_sha256(pin),
        "manifestSha256": manifest,
        "runManifestSha256": r["cohort_manifest_sha256"],
        "plannedSteps": r["planned_steps"],
    }
    for label, kind, key in [
        ("parentCount", "grid_correction_learning", p["idempotency_key"]),
        ("trainingCount", "grid_training", r["idempotency_key"]),
        ("evaluationCount", "grid_model_evaluation", v["evaluationKey"]),
    ]:
        result[label] = s.scalar(
            text(
                "SELECT count(*) FROM public.jobs WHERE game_id=:game "
                "AND job_type=:kind AND input_payload->>'idempotency_key'=:key"
            ),
            {"game": v["game"], "kind": kind, "key": key},
        )
    print(json.dumps(result))
engine.dispose()
