"""Catalogue pins across process boundaries, assignments, HTTP and worker replay."""

from __future__ import annotations

import json
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.application.jobs import JobService
from game_predictor_api.domain.grid_engine_profiles import (
    GridEngineModelError,
    grid_engine_manifest,
)
from game_predictor_api.domain.grid_model_registry import canonical_json, descriptor_sha256
from game_predictor_api.domain.jobs import JobConflictError
from game_predictor_api.domain.neural_grid_proposal import (
    NeuralGridProposalError,
    NeuralGridSnapshot,
)
from game_predictor_api.storage.grid_engine_model_store import ManagedGridEngineModelStore
from game_predictor_api.storage.grid_profile_snapshot_resolver import (
    SqlAlchemyGridProfileSnapshotResolver,
)
from game_predictor_api.storage.image_sequence_canonical_repository import (
    SqlAlchemyImageSequenceCanonicalRepository,
)
from game_predictor_api.storage.models import GameModel
from test_grid_model_registry import candidate
from test_jobs_domain import MemoryJobRepository


@pytest.fixture
def catalogue(tmp_path):
    descriptor = candidate(tmp_path)
    descriptor["inferenceManifest"]["profile"] = "third_geometry"
    (tmp_path / descriptor["managedDirectory"] / "manifest.json").write_text(
        json.dumps(descriptor["inferenceManifest"]), encoding="utf-8"
    )
    return descriptor


def snapshot(descriptor, game_id=None, configuration="neural_grid_v3"):
    return NeuralGridSnapshot.from_catalogue(
        game_id=str(game_id or uuid4()),
        game_configuration=configuration,
        expected_layout_count=500000,
        descriptor=descriptor,
    )


def resolver(descriptor, root, *, configuration="neural_grid_v3", code="new_game", game_id=None):
    game = SimpleNamespace(
        id=game_id or uuid4(),
        code=code,
        shape_geometry_configuration=configuration,
        expected_layout_count=500000,
    )
    session = Mock()
    session.get.side_effect = (
        lambda model, identity: game if model is GameModel and identity == game.id else None
    )
    repository = Mock()
    repository.assignment.return_value = (
        SimpleNamespace(version_id=UUID(descriptor["versionId"])),
        1,
    )
    repository.version.return_value = SimpleNamespace(
        id=UUID(descriptor["versionId"]),
        family_id=UUID(descriptor["familyId"]),
        version=descriptor["version"],
        manifest_json=canonical_json(descriptor),
        manifest_sha256=descriptor_sha256(descriptor),
    )
    return game, repository, SqlAlchemyGridProfileSnapshotResolver(session, root)


def test_third_family_roundtrip_immutable_and_new_process(catalogue, tmp_path):
    value = snapshot(catalogue)
    payload = value.to_payload()
    catalogue["familyLabel"] = "mutated caller"
    assert value.to_payload() == payload
    assert NeuralGridSnapshot.from_payload(payload) == value
    assert grid_engine_manifest(value.version) == payload["catalogueManifest"]["inferenceManifest"]
    assert (
        ManagedGridEngineModelStore(tmp_path).require(value.version)
        == tmp_path / payload["catalogueManifest"]["managedDirectory"]
    )
    stored = tmp_path / "job-snapshot.json"
    stored.write_text(json.dumps(payload), encoding="utf-8")
    program = """
import json,sys
from pathlib import Path
from game_predictor_api.domain.neural_grid_proposal import NeuralGridSnapshot
from game_predictor_api.storage.grid_engine_model_store import ManagedGridEngineModelStore
s=NeuralGridSnapshot.from_payload(json.loads(Path(sys.argv[1]).read_text(encoding='utf-8')))
ManagedGridEngineModelStore(Path(sys.argv[2])).require(s.version)
print(s.to_payload()['catalogueManifest']['versionId'])
"""
    result = subprocess.run(
        [sys.executable, "-u", "-c", program, str(stored), str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == payload["catalogueManifest"]["versionId"]


@pytest.mark.parametrize(
    "configuration", ["neural_grid_v3", "grid_profile_mumie_v1", "grid_profile_777_v2"]
)
def test_all_v3_formats_resolve_assignment_instead_of_static_current(
    catalogue, tmp_path, configuration
):
    game, repository, value = resolver(catalogue, tmp_path, configuration=configuration)
    with patch(
        "game_predictor_api.storage.grid_profile_snapshot_resolver.SqlAlchemyGridModelRegistryRepository",
        return_value=repository,
    ):
        pinned = value.resolve_neural_grid_proposal(game_id=game.id)
        assert pinned["catalogueManifest"]["familyCode"] == "third_geometry"
        assert pinned["gameConfiguration"] == configuration
        assert value.require_neural_grid_assignment(game_id=game.id)
        canonical = SqlAlchemyImageSequenceCanonicalRepository(value._session)
        assert canonical.uses_neural_grid_pilot(game.id)


def test_unassigned_and_corrupt_assignments_never_fallback(catalogue, tmp_path):
    game, repository, value = resolver(catalogue, tmp_path)
    with patch(
        "game_predictor_api.storage.grid_profile_snapshot_resolver.SqlAlchemyGridModelRegistryRepository",
        return_value=repository,
    ):
        repository.assignment.return_value = (None, 0)
        with pytest.raises(JobConflictError) as error:
            value.resolve_neural_grid_proposal(game_id=game.id)
        assert error.value.code == "GRID_MODEL_ASSIGNMENT_REQUIRED"
        repository.assignment.return_value = (SimpleNamespace(version_id=uuid4()), 1)
        repository.version.return_value.manifest_sha256 = "0" * 64
        with pytest.raises(JobConflictError) as error:
            value.resolve_neural_grid_proposal(game_id=game.id)
        assert error.value.code == "GRID_MODEL_REGISTRY_CORRUPT"


@pytest.mark.parametrize(
    "change", ["checksum", "topology", "preprocessing", "capabilities", "owner"]
)
def test_snapshot_fail_closed_on_corruption(catalogue, change):
    payload = snapshot(catalogue).to_payload()
    if change == "checksum":
        payload["catalogueManifestSha256"] = "0" * 64
    elif change == "owner":
        payload["gameId"] = "not-uuid"
    else:
        field, value = {
            "topology": ("topology", {}),
            "preprocessing": ("preprocessingVersion", "unknown"),
            "capabilities": ("capabilities", ["screen_detector"]),
        }[change]
        payload["catalogueManifest"][field] = value
        payload["catalogueManifestSha256"] = descriptor_sha256(payload["catalogueManifest"])
    with pytest.raises(NeuralGridProposalError):
        NeuralGridSnapshot.from_payload(payload)


@pytest.mark.parametrize("change", ["missing", "hash", "manifest"])
def test_pinned_file_loss_and_drift_do_not_choose_another_version(catalogue, tmp_path, change):
    value = snapshot(catalogue)
    target = (
        tmp_path
        / catalogue["managedDirectory"]
        / ("manifest.json" if change == "manifest" else "board.onnx")
    )
    if change == "missing":
        target.unlink()
    else:
        target.write_bytes(b"changed")
    with pytest.raises(GridEngineModelError):
        ManagedGridEngineModelStore(tmp_path).require(value.version)


def test_legacy_reader_keeps_historical_meaning_and_protects_game7(catalogue, tmp_path):
    from game_predictor_api.domain.grid_engine_profiles import GRID_ENGINE_PROFILES

    for profile in GRID_ENGINE_PROFILES:
        old = NeuralGridSnapshot.for_game(500000, profile.current).to_payload()
        assert old["contractVersion"] == "neural-grid-proposal-snapshot-v1"
        assert NeuralGridSnapshot.from_payload(old).to_payload() == old
    game, repository, value = resolver(
        catalogue, tmp_path, code="7", configuration="framed_full_page_v2"
    )
    assert not value.uses_neural_grid_pilot(game_id=game.id)
    assert value.resolve_neural_grid_proposal(game_id=game.id) is None
    repository.assignment.assert_not_called()


@pytest.mark.parametrize("contract", ["legacy", "catalogue"])
def test_public_http_payload_roundtrip_keeps_catalogue_pin(catalogue, tmp_path, contract):
    from game_predictor_api.config import ApiSettings
    from game_predictor_api.domain.jobs import JobType, create_job
    from game_predictor_api.main import create_app

    game_id = uuid4()
    payload = snapshot(catalogue, game_id=game_id).to_payload()
    if contract == "legacy":
        from game_predictor_api.domain.grid_engine_profiles import GRID_ENGINE_PROFILES

        payload = NeuralGridSnapshot.for_game(500000, GRID_ENGINE_PROFILES[0].current).to_payload()
    repository = MemoryJobRepository(game_id)
    job = create_job(
        JobType.VALIDATE,
        game_id=game_id,
        input_payload={
            "schema_version": 2,
            "validation_kind": "page_geometry_preflight",
            "preflight_policy_version": "page-geometry-preflight-v13-neural-mumie-pilot",
            "source_selection_id": str(uuid4()),
            "source_directory": str(tmp_path),
            "source_manifest_sha256": "b" * 64,
            "page_registration_profile": {},
            "page_geometry_overrides": {},
            "canonical_sequence_numbers": [],
            "neural_grid_proposal": payload,
        },
    )
    repository.add_job(job)
    service = JobService(repository, artifact_root=tmp_path)
    app = create_app(
        ApiSettings.from_environment({"GAME_PREDICTOR_IMPORT_ROOT": str(tmp_path)}),
        job_service_dependency=lambda: service,
    )
    response = TestClient(app).get(f"/api/v1/admin/jobs/{job.id}")
    assert response.status_code == 200
    assert response.json()["inputPayload"]["neuralGridProposal"] == payload
    from game_predictor_api.schemas.neural_grid_proposals import NeuralGridSnapshotContract
    from pydantic import TypeAdapter

    assert (
        TypeAdapter(NeuralGridSnapshotContract)
        .validate_python(payload)
        .model_dump(mode="json", by_alias=True)
        == payload
    )


def test_snapshot_ownership_matches_game_without_reading_current_assignment(catalogue, tmp_path):
    game, repository, value = resolver(catalogue, tmp_path)
    pinned = snapshot(catalogue, game_id=game.id)
    assert value.neural_snapshot_matches_game(game_id=game.id, snapshot=pinned)
    repository.assignment.assert_not_called()
    assert not value.neural_snapshot_matches_game(game_id=uuid4(), snapshot=pinned)
    game.shape_geometry_configuration = "grid_profile_mumie_v1"
    assert not value.neural_snapshot_matches_game(game_id=game.id, snapshot=pinned)


@pytest.mark.parametrize("field", ["id", "family_id", "version"])
def test_assignment_record_identity_must_match_descriptor(catalogue, tmp_path, field):
    game, repository, value = resolver(catalogue, tmp_path)
    setattr(
        repository.version.return_value, field, "wrong-version" if field == "version" else uuid4()
    )
    with (
        patch(
            "game_predictor_api.storage.grid_profile_snapshot_resolver.SqlAlchemyGridModelRegistryRepository",
            return_value=repository,
        ),
        pytest.raises(JobConflictError) as error,
    ):
        value.resolve_neural_grid_proposal(game_id=game.id)
    assert error.value.code == "GRID_MODEL_REGISTRY_CORRUPT"


def test_proposal_cannot_carry_another_games_catalogue_snapshot(catalogue):
    from game_predictor_api.domain.neural_grid_proposal import (
        proposal_checksum_sha256,
        validate_neural_source_proposal,
    )
    from test_neural_grid_proposal import proposal

    value = proposal()
    value["engineSnapshot"] = snapshot(catalogue).to_payload()
    value["proposalChecksumSha256"] = proposal_checksum_sha256(value)
    with pytest.raises(NeuralGridProposalError, match="another game"):
        validate_neural_source_proposal(value)


@pytest.mark.parametrize(
    "configuration", ["neural_grid_v3", "grid_profile_mumie_v1", "grid_profile_777_v2"]
)
def test_game7_with_v3_configuration_keeps_deliberate_classical_routing(
    catalogue, tmp_path, configuration
):
    game, repository, value = resolver(catalogue, tmp_path, configuration=configuration, code="7")
    service = JobService(Mock(), grid_profile_snapshot_resolver=value, artifact_root=tmp_path)
    with patch(
        "game_predictor_api.storage.grid_profile_snapshot_resolver.SqlAlchemyGridModelRegistryRepository",
        return_value=repository,
    ):
        assert value.neural_grid_profile(game_id=game.id) is None
        assert not service.uses_neural_grid_pilot(game_id=game.id)
        assert (
            service._neural_preflight_snapshot(
                game_id=game.id,
                selection_id=uuid4(),
                source_manifest_sha256="a" * 64,
                candidates=[],
                overrides={},
            )
            is None
        )
        assert (
            service._neural_import_snapshot(
                game_id=game.id,
                selection_id=uuid4(),
                source_manifest_sha256="a" * 64,
                descriptor=None,
            )
            is None
        )
    repository.assignment.assert_not_called()
    repository.version.assert_not_called()


def test_canonical_preflight_propagates_missing_v3_assignment(catalogue, tmp_path):
    from game_predictor_api.domain.image_sequence_canonical import ImageSequenceCanonicalService

    game, repository, value = resolver(catalogue, tmp_path)
    repository.assignment.return_value = (None, 0)
    canonical = SqlAlchemyImageSequenceCanonicalRepository(value._session)
    with (
        patch(
            "game_predictor_api.storage.grid_profile_snapshot_resolver.SqlAlchemyGridModelRegistryRepository",
            return_value=repository,
        ),
        pytest.raises(JobConflictError) as error,
    ):
        ImageSequenceCanonicalService(canonical).preflight(game_id=game.id)
    assert error.value.code == "GRID_MODEL_ASSIGNMENT_REQUIRED"
