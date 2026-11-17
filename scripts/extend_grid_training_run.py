"""Owner-only preview/apply for an explicitly approved 7200 -> 14400 second grant.

Does not cancel, resume, change a preset, create a run, or modify artifacts.
Run with the repository Python; checkpoint validation uses PyTorch on CPU.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

REPOSITORY = Path(__file__).resolve().parents[1]
for relative in ("services/api/src", "services/worker/src"):
    sys.path.insert(0, str(REPOSITORY / relative))

from game_predictor_api.config import ApiSettings  # noqa: E402
from game_predictor_api.storage.grid_training_cohort_artifacts import (  # noqa: E402
    GridCohortArtifactStore,
)
from game_predictor_worker.images.grid_training_child import canonical, sha256_bytes  # noqa: E402
from game_predictor_worker.training_core.gpu_lease import GpuLease, lease_path  # noqa: E402
from game_predictor_worker.training_core.grid_training_admission import (  # noqa: E402
    PRESETS,
)
from game_predictor_worker.training_core.run_budget_extension import (  # noqa: E402
    prepare_extension,
    verify_extension,
)
from sqlalchemy import Connection, Engine, create_engine, text  # noqa: E402

QUERY = """SELECT id::text,game_id::text,job_type::text,status::text,input_payload,
 checkpoint_payload,lease_owner,lease_token,lease_expires_at
 FROM public.jobs WHERE id=:id AND game_id=:game"""


def read_row(
    connection: Connection, run: UUID, game: UUID, *, lock: bool = False
) -> dict[str, Any]:
    value = (
        connection.execute(text(QUERY + (" FOR UPDATE" if lock else "")), {"id": run, "game": game})
        .mappings()
        .one()
    )
    return dict(value)


def quiescent(artifact_root: Path) -> None:
    if GpuLease(lease_path(artifact_root)).observe().state not in {"free", "stale"}:
        raise ValueError("GPU_NOT_QUIESCENT")


def checkpoint_pointer(row: dict[str, Any], artifact_root: Path, name: str) -> dict[str, Any]:
    """Rebuild the exact production binding before adopting an orphan pointer."""
    from game_predictor_worker.training_core.checkpoint import load_checkpoint
    from game_predictor_worker.training_core.grid_rescue_training import (
        TrainingExposure,
        require_recipe,
        selection_input,
    )
    from game_predictor_worker.training_core.grid_training import (
        PHOTO_CHECKPOINT_RULE,
        EarlyStopping,
        TrainingPlan,
    )

    inputs = row["input_payload"]
    run_dir = artifact_root / "grid-training/runs" / row["id"]
    directory = run_dir / "checkpoints"
    path = directory / name
    if (
        len(name) != 67
        or not name.endswith(".pt")
        or any(c not in "0123456789abcdef" for c in name[:64])
        or path.resolve().parent != directory.resolve()
        or not path.resolve().is_relative_to(artifact_root.resolve())
        or path.is_symlink()
        or path.is_junction()
    ):
        raise ValueError("CHECKPOINT_PATH_INVALID")
    spec_path = run_dir / "spec.json"
    if spec_path.stat().st_size > 1024 * 1024:
        raise ValueError("SPEC_TOO_LARGE")
    envelope = json.loads(spec_path.read_text(encoding="utf-8"))
    spec = envelope["payload"]
    if envelope["sha256"] != sha256_bytes(canonical(spec)):
        raise ValueError("SPEC_CHECKSUM_MISMATCH")
    if (
        spec["jobId"] != row["id"]
        or spec["cohort"]["gameId"] != row["game_id"]
        or spec["cohort"]["cohortId"] != inputs["cohort_id"]
        or spec["cohort"]["manifestSha256"] != inputs["cohort_manifest_sha256"]
        or spec["base"]["versionId"] != inputs["base_version_id"]
        or spec["preset"]
        != {"id": inputs["preset_id"], "fingerprint": inputs["preset_fingerprint"]}
        or spec["seed"] != inputs["seed"]
        or spec["plannedSteps"] != inputs["planned_steps"]
        or spec["attempt"] != row["checkpoint_payload"]["attempt"]
        or spec.get("joint") is not None
        or spec.get("gridOutputContract") is not None
        or spec.get("contentExperiment") is not None
        or spec["rescueRecipe"] != inputs["rescue_recipe"]
    ):
        raise ValueError("SPEC_INPUT_MISMATCH")
    manifest = GridCohortArtifactStore(artifact_root).read_json(
        spec["cohort"]["manifestPath"], spec["cohort"]["manifestSha256"]
    )
    selection = selection_input([(str(manifest["gameId"]), manifest["photoSplit"])])
    require_recipe(spec["rescueRecipe"], spec["base"]["presetSha256"], selection)
    binding = TrainingPlan.of(
        row["id"],
        spec["seed"],
        PRESETS[inputs["preset_id"]],
        spec["plannedSteps"],
        {
            "cohortManifestSha256": spec["cohort"]["manifestSha256"],
            "baseWeightsSha256": spec["base"]["weightsSha256"],
            "basePresetSha256": spec["base"]["presetSha256"],
            "mode": PRESETS[inputs["preset_id"]].mode,
            "selectionInput": selection,
            "rescueRecipe": spec["rescueRecipe"],
        },
    ).binding
    value = load_checkpoint(path, name[:64], expected_binding=binding)
    if value["schemaVersion"] != 2:
        raise ValueError("CHECKPOINT_VERSION_UNSUPPORTED")
    stored = value.get("bestState")
    if not isinstance(stored, dict) or "early" not in stored or "exposureCurrent" not in stored:
        raise ValueError("CHECKPOINT_RESUME_STATE_INVALID")
    policy = PRESETS[inputs["preset_id"]].early_stopping
    stopping = EarlyStopping(
        policy.direction,
        policy.patience,
        policy.min_delta,
        policy.min_evaluations,
        selection_rule=PHOTO_CHECKPOINT_RULE,
    )
    stopping.restore(stored["early"])
    TrainingExposure(spec["rescueRecipe"]).restore(stored["exposureCurrent"], value["globalStep"])
    return {"path": name, "sha256": name[:64], "step": value["globalStep"]}


def apply_preview(
    engine: Engine,
    game: UUID,
    run: UUID,
    preview: dict[str, Any],
    expected_sha: str,
    artifact_root: Path,
) -> dict[str, Any]:
    with engine.connect() as connection:
        row = read_row(connection, run, game)
    if not verify_extension(row, preview, expected_sha):
        return {"applied": False, "alreadyApplied": True, "runId": str(run)}
    quiescent(artifact_root)
    pointer = checkpoint_pointer(row, artifact_root, preview["payload"]["checkpoint"]["path"])
    if pointer != preview["payload"]["checkpoint"]:
        raise ValueError("CHECKPOINT_DRIFT")
    with engine.begin() as connection:
        connection.exec_driver_sql("SET LOCAL lock_timeout='5s'")
        connection.exec_driver_sql("SET LOCAL statement_timeout='10s'")
        current = read_row(connection, run, game, lock=True)
        if not verify_extension(current, preview, expected_sha):
            return {"applied": False, "alreadyApplied": True, "runId": str(run)}
        quiescent(artifact_root)
        connection.execute(
            text("""UPDATE public.jobs SET checkpoint_payload=CAST(:state AS jsonb),
          updated_at=now() WHERE id=:id AND game_id=:game"""),
            {"state": json.dumps(preview["payload"]["afterState"]), "id": run, "game": game},
        )
    return {
        "applied": True,
        "alreadyApplied": False,
        "runId": str(run),
        "maxSeconds": 14400,
        "checkpoint": pointer,
        "previewSha256": expected_sha,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-id", type=UUID, required=True)
    parser.add_argument("--run-id", type=UUID, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--preview", type=Path, required=True)
    parser.add_argument("--checkpoint")
    parser.add_argument("--reason")
    parser.add_argument("--apply-sha", help="Explicit approval of the exact preview bytes")
    args = parser.parse_args()
    engine = create_engine(
        ApiSettings.from_environment().owner_database_url,
        connect_args={"connect_timeout": 3, "options": "-c statement_timeout=10000"},
    )
    try:
        if args.apply_sha:
            preview = json.loads(args.preview.read_text(encoding="utf-8"))
            print(
                json.dumps(
                    apply_preview(
                        engine,
                        args.game_id,
                        args.run_id,
                        preview,
                        args.apply_sha,
                        args.artifact_root,
                    )
                ),
                flush=True,
            )
        else:
            if not args.checkpoint or not args.reason or args.preview.exists():
                parser.error("A new preview path, checkpoint and approval reason are required")
            with engine.connect() as connection, connection.begin():
                connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                row = read_row(connection, args.run_id, args.game_id)
            quiescent(args.artifact_root)
            pointer = checkpoint_pointer(row, args.artifact_root, args.checkpoint)
            preview = prepare_extension(
                row, pointer, at=datetime.now(UTC).isoformat(), reason=args.reason
            )
            args.preview.write_text(json.dumps(preview, indent=2), encoding="utf-8")
            print(
                json.dumps(
                    {
                        "previewSha256": preview["sha256"],
                        "runId": str(args.run_id),
                        "maxSeconds": 14400,
                        "checkpoint": pointer,
                        "stateChangesApplied": False,
                    }
                ),
                flush=True,
            )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
