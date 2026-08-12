from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest
from game_predictor_api.domain.jobs import JobConflictError
from game_predictor_api.domain.symbol_model_snapshots import SymbolModelStorageRoot
from game_predictor_api.storage.models import (
    GameSymbolModelActivationModel,
    SymbolModelIterationModel,
)
from game_predictor_api.storage.symbol_model_snapshot_resolver import (
    SqlAlchemySymbolModelSnapshotResolver,
)


def _write_json(path: Path, value: object) -> str:
    content = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


class _Session:
    def __init__(
        self,
        activation: GameSymbolModelActivationModel | None,
        iteration: SymbolModelIterationModel | None,
    ) -> None:
        self.activation = activation
        self.iteration = iteration

    def scalar(self, _statement: object) -> GameSymbolModelActivationModel | None:
        return self.activation

    def get(self, _model: object, _identifier: object) -> SymbolModelIterationModel | None:
        return self.iteration


def _resolver_fixture(
    tmp_path: Path,
) -> tuple[SqlAlchemySymbolModelSnapshotResolver, Path, SymbolModelIterationModel]:
    artifact_root = tmp_path / "artifacts"
    onnx_path = artifact_root / "models" / "candidate.onnx"
    onnx_path.parent.mkdir(parents=True)
    onnx_path.write_bytes(b"candidate-onnx")
    onnx_checksum = hashlib.sha256(onnx_path.read_bytes()).hexdigest()
    classes_path = artifact_root / "models" / "classes.json"
    classes_checksum = _write_json(
        classes_path,
        {"classCodes": ["lemon", "seven"], "classIds": [uuid4().hex, uuid4().hex]},
    )
    calibration_path = artifact_root / "models" / "calibration.json"
    calibration_checksum = _write_json(
        calibration_path,
        {"temperature": 1.2, "version": "temperature-v1"},
    )
    manifest = {
        "artifacts": {
            "calibration": {
                "relativePath": "models/calibration.json",
                "sha256": calibration_checksum,
            },
            "classes": {
                "relativePath": "models/classes.json",
                "sha256": classes_checksum,
            },
            "onnx": {
                "relativePath": "models/candidate.onnx",
                "sha256": onnx_checksum,
            },
        },
        "classCodes": ["lemon", "seven"],
    }
    manifest_path = artifact_root / "models" / "manifest.json"
    manifest_checksum = _write_json(manifest_path, manifest)
    game_id = uuid4()
    iteration = SymbolModelIterationModel(
        id=uuid4(),
        game_id=game_id,
        cohort_id=uuid4(),
        job_id=uuid4(),
        iteration_number=1,
        status="candidate_ready",
        configuration_fingerprint="c" * 64,
        configuration_payload={"inputSize": 64},
        candidate_manifest_checksum_sha256=manifest_checksum,
        candidate_manifest_relative_path="models/manifest.json",
        gate_metrics={},
        rejection_reasons=[],
        last_completed_epoch=1,
        partial_metrics={},
    )
    activation = GameSymbolModelActivationModel(
        id=uuid4(),
        game_id=game_id,
        model_iteration_id=iteration.id,
        previous_model_iteration_id=None,
        action="activate",
        activation_number=1,
        actor="local-owner",
        reason=None,
        idempotency_key=uuid4(),
        command_sha256="d" * 64,
    )
    resolver = SqlAlchemySymbolModelSnapshotResolver(
        _Session(activation, iteration),  # type: ignore[arg-type]
        artifact_root=artifact_root,
    )
    return resolver, onnx_path, iteration


def test_resolver_returns_a_checksum_verified_active_candidate(tmp_path: Path) -> None:
    resolver, _onnx_path, iteration = _resolver_fixture(tmp_path)

    snapshot = resolver.resolve(game_id=iteration.game_id)

    assert snapshot.iteration_id == iteration.id
    assert snapshot.storage_root is SymbolModelStorageRoot.ARTIFACT
    assert snapshot.class_codes == ("lemon", "seven")
    assert snapshot.input_size == 64
    assert snapshot.temperature == 1.2
    assert snapshot.onnx_relative_path == "models/candidate.onnx"


def test_resolver_rejects_an_active_artifact_changed_after_activation(tmp_path: Path) -> None:
    resolver, onnx_path, iteration = _resolver_fixture(tmp_path)
    onnx_path.write_bytes(b"tampered")

    with pytest.raises(JobConflictError) as error:
        resolver.resolve(game_id=iteration.game_id)

    assert error.value.code == "SYMBOL_MODEL_ACTIVE_ARTIFACT_DRIFT"
