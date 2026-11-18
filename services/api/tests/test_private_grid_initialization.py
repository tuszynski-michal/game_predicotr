"""Cold-start evidence, comparisons and private catalogue write admission."""

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from game_predictor_api.application.grid_model_registry import GridModelRegistryService
from game_predictor_api.domain.grid_model_registry import (
    GridModelRegistryError,
    canonical_json,
    descriptor_sha256,
    validate_manifest,
)
from game_predictor_api.schemas.grid_model_registry import GridModelManifest
from game_predictor_api.storage.grid_model_registry import GridModelArtifactInspector
from game_predictor_api.storage.grid_private_learning import weight_initialization
from test_grid_model_registry import candidate


def test_comparison_only_checks_the_servable_files(tmp_path):
    payload = candidate(tmp_path)
    base = tmp_path / payload["managedDirectory"]
    (base / "training-base" / "weights.pt").unlink()
    inspector = GridModelArtifactInspector(tmp_path)
    assert inspector.inspect(payload)[0] is False
    assert inspector.inspect_inference(payload)[0] is True
    (base / "board.onnx").write_bytes(b"altered")
    assert inspector.inspect_inference(payload) == (False, "GRID_MODEL_ARTIFACT_MISMATCH")


def test_independent_lineage_and_transport_require_matching_owner_and_proof(tmp_path):
    payload = candidate(tmp_path)
    game = uuid4()
    payload["cohortId"] = str(uuid4())
    pin = {"baseVersionId": payload["versionId"], "targetFamilyId": payload["familyId"]}
    version = SimpleNamespace(id=UUID(payload["versionId"]))
    registry = SimpleNamespace(version=lambda _: version, version_owner_game_id=lambda _: game)

    def verdict():
        version.manifest_json = canonical_json(payload)
        version.manifest_sha256 = pin["baseManifestSha256"] = descriptor_sha256(payload)
        return weight_initialization(registry, game, pin)

    assert verdict() == "from_scratch"
    payload["provenance"]["weightInitialization"] = "from_scratch"
    with pytest.raises(GridModelRegistryError, match="GRID_MODEL_MANIFEST_INVALID"):
        validate_manifest(payload)
    payload["provenance"]["independentGameId"] = str(game)
    assert validate_manifest(payload) == canonical_json(payload)
    assert (
        GridModelManifest.model_validate(payload).model_dump(mode="json", by_alias=True) == payload
    )
    assert verdict() == "assigned_weights"
    payload["provenance"]["weightInitialization"] = "assigned_weights"
    assert verdict() == "assigned_weights"
    registry.version_owner_game_id = lambda _: None
    assert verdict() == "from_scratch"
    registry.version_owner_game_id = lambda _: game
    payload["provenance"]["independentGameId"] = str(uuid4())
    assert verdict() == "from_scratch"
    with pytest.raises(GridModelRegistryError, match="GRID_MODEL_PRIVATE_WORKER_REQUIRED"):
        GridModelRegistryService(registry, GridModelArtifactInspector(tmp_path)).register(
            uuid4(), payload
        )
