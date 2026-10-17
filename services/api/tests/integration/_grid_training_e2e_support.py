"""TASK-0996 E2E support: a file-backed stand-in for cohort/catalogue reads and registration.

The jobs table, lane, lease and recovery are real PostgreSQL; the frozen cohort is the
generated TASK-0995 snapshot fixture and registration runs the real descriptor validation
and artifact inspection, persisted in a JSON file so several worker processes share it.
"""

from __future__ import annotations

import copy
import io
import json
import os
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from game_predictor_api.domain.grid_model_registry import historical_catalogue, validate_manifest
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.grid_model_registry import GridModelArtifactInspector
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

PRESET_FILE = (
    Path(__file__).resolve().parents[4]
    / "services/worker/src/game_predictor_worker/vision_lab/neural_grid_presets/D.json"
)


def base_descriptor(root: Path) -> dict[str, Any]:
    """A base version whose training-base holds fresh weights and the lab preset D."""
    import hashlib

    import torch
    from game_predictor_worker.training_core.neural_grid_network import NeuralGridNetwork

    descriptor = copy.deepcopy(historical_catalogue()[0])
    descriptor["managedDirectory"] = "models/grid-engine/grid_profile_777_v2/e2e-base"
    directory = root / descriptor["managedDirectory"] / "training-base"
    directory.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(0)
    stream = io.BytesIO()
    torch.save(NeuralGridNetwork(4).state_dict(), stream)
    (directory / "weights.pt").write_bytes(stream.getvalue())
    preset = PRESET_FILE.read_bytes()
    (directory / "preset.json").write_bytes(preset)
    for item in descriptor["trainingArtifacts"]:
        if item["name"] == "weights.pt":
            item.update(
                sha256=hashlib.sha256(stream.getvalue()).hexdigest(),
                sizeBytes=len(stream.getvalue()),
            )
        if item["name"] == "preset.json":
            item.update(sha256=hashlib.sha256(preset).hexdigest(), sizeBytes=len(preset))
    return descriptor


class FileStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.state = root / "e2e-store.json"

    def _load(self) -> dict[str, Any]:
        return json.loads(self.state.read_text(encoding="utf-8"))

    def cohort(self, game_id: UUID, cohort_id: UUID) -> dict[str, Any]:
        return self._load()["cohort"]

    def eligibility(self, game_id: UUID, cohort_id: UUID) -> dict[str, Any]:
        return {"qualification": "eligible", "reasons": []}

    def base_version(self, version_id: UUID) -> dict[str, Any]:
        return self._load()["base"]

    def register(self, key: UUID, payload: dict[str, Any]) -> dict[str, Any]:
        validate_manifest(payload)
        available, reason = GridModelArtifactInspector(self.root).inspect(payload)
        if not available:
            raise RuntimeError(reason)
        value = self._load()
        registered = value.setdefault("registered", {})
        if str(key) in registered:
            if registered[str(key)] != payload:
                raise RuntimeError("GRID_MODEL_IDEMPOTENCY_CONFLICT")
        else:
            registered[str(key)] = payload
            self.state.write_text(json.dumps(value), encoding="utf-8")
        return {"manifestSha256": "e2e"}


def worker(app_url: str, root: Path, python: str, lease_seconds: float) -> Any:
    from game_predictor_api.domain.jobs import JobExecutionSlot, JobType
    from game_predictor_worker.images.grid_training_handler import GridTrainingJobHandler
    from game_predictor_worker.jobs.runtime import LocalJobWorker
    from game_predictor_worker.jobs.store import SqlAlchemyWorkerJobStore

    repository = Path(__file__).resolve().parents[4]
    engine = create_engine(app_url, poolclass=NullPool)
    sources = [repository / "services/worker/src", repository / "services/api/src"]
    handler = GridTrainingJobHandler(
        FileStore(root),
        artifact_root=root,
        python=Path(python),
        pythonpath=os.pathsep.join(str(path) for path in sources),
        repository_root=repository,
        poll_seconds=2.0,
    )
    return LocalJobWorker(
        SqlAlchemyWorkerJobStore(create_session_factory(engine)),
        {JobType.GRID_TRAINING: handler},
        worker_id=f"e2e-{os.getpid()}",
        worker_version="e2e",
        execution_slot=JobExecutionSlot.GRID_TRAINING,
        lease_duration=timedelta(seconds=lease_seconds),
    )


if __name__ == "__main__":  # worker process of the crash scenario
    import sys

    result = worker(sys.argv[1], Path(sys.argv[2]), sys.argv[3], float(sys.argv[4])).run_once()
    print(result.value, flush=True)
