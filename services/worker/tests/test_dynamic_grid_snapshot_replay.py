"""Dynamic catalogue model pins survive durable preflight replay and activation changes."""

import hashlib
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from game_predictor_api.application.jobs import JobService
from game_predictor_api.domain.grid_engine_profiles import GridEngineModelError
from game_predictor_api.domain.grid_model_registry import historical_catalogue
from game_predictor_api.domain.jobs import JobStatus
from game_predictor_api.domain.neural_grid_proposal import NeuralGridSnapshot
from game_predictor_worker.images.neural_page_geometry_preflight import (
    NeuralPageGeometryPreflightHandler,
)
from test_neural_page_geometry_preflight import Context, Runner, job_fixture, result


def inference_candidate(root: Path) -> dict[str, object]:
    """Worker-owned fake inference files; no dependency on another suite's modules."""
    descriptor = deepcopy(historical_catalogue()[0])
    descriptor.update(
        familyId=str(uuid4()),
        familyCode="third_geometry",
        familyLabel="Third geometry",
        versionId=str(uuid4()),
        version="v2",
        admission="not_evaluated",
        baseVersionId=descriptor["versionId"],
        managedDirectory="models/grid-engine/third_geometry/v2",
    )
    directory = root / descriptor["managedDirectory"]
    directory.mkdir(parents=True)
    files = []
    for name in ("screen.onnx", "board.onnx", "bundle.json", "preset.json"):
        content = ("test-" + name).encode()
        (directory / name).write_bytes(content)
        files.append(
            {"name": name, "sha256": hashlib.sha256(content).hexdigest(), "sizeBytes": len(content)}
        )
    descriptor["files"] = files
    descriptor["trainingArtifacts"] = [
        file
        for file in descriptor["trainingArtifacts"]
        if file["name"] in {"checkpoint.pt", "weights.pt"}
    ] + [file for file in files if file["name"] in {"bundle.json", "preset.json"}]
    descriptor["inferenceManifest"].update(profile="third_geometry", version="v2", files=files)
    (directory / "manifest.json").write_text(
        json.dumps(descriptor["inferenceManifest"]), encoding="utf-8"
    )
    return descriptor


def test_catalogue_worker_replay_and_preflight_start_keep_pin_after_assignment_change(tmp_path):
    job, _ = job_fixture(tmp_path)
    descriptor = inference_candidate(tmp_path)
    pinned = NeuralGridSnapshot.from_catalogue(
        game_id=str(job.game_id),
        game_configuration="neural_grid_v3",
        expected_layout_count=500000,
        descriptor=descriptor,
    ).to_payload()
    job = replace(job, input_payload={**job.input_payload, "neural_grid_proposal": pinned})
    context = Context()
    NeuralPageGeometryPreflightHandler(artifact_root=tmp_path, runner=Runner([5, 4]))(context, job)
    manifest = result(tmp_path, context)
    assert manifest["neuralGridProposal"] == pinned
    completed = replace(
        job,
        status=JobStatus.COMPLETED,
        checkpoint_payload=context.checkpoints[-1]["checkpoint_payload"],
    )
    # A newly constructed service sees a different assignment. Neither reuse nor
    # import start is allowed to resolve that mutable version over the old pin.
    resolver = Mock()
    resolver.uses_neural_grid_pilot.return_value = True
    resolver.neural_snapshot_matches_game.side_effect = lambda **pins: pins[
        "snapshot"
    ].game_id == str(job.game_id)
    resolver.resolve_neural_grid_proposal.return_value = NeuralGridSnapshot.from_catalogue(
        game_id=str(job.game_id),
        game_configuration="neural_grid_v3",
        expected_layout_count=500000,
        descriptor=historical_catalogue()[1],
    ).to_payload()
    repository = Mock()
    repository.get_job.side_effect = (
        lambda identity: completed if identity == completed.id else None
    )
    fresh = JobService(repository, grid_profile_snapshot_resolver=resolver, artifact_root=tmp_path)
    checkpoint = completed.checkpoint_payload
    selection = UUID(job.input_payload["source_selection_id"])
    checksum = job.input_payload["source_manifest_sha256"]
    import_descriptor = {
        "preflightJobId": str(job.id),
        "relativePath": checkpoint["geometry_manifest_relative_path"],
        "checksumSha256": checkpoint["geometry_manifest_checksum_sha256"],
    }
    assert (
        fresh._neural_import_snapshot(
            game_id=job.game_id,
            selection_id=selection,
            source_manifest_sha256=checksum,
            descriptor=import_descriptor,
        )
        == pinned
    )
    assert (
        fresh._neural_preflight_snapshot(
            game_id=job.game_id,
            selection_id=selection,
            source_manifest_sha256=checksum,
            candidates=[completed],
            overrides={},
        )
        == pinned
    )
    resolver.resolve_neural_grid_proposal.assert_not_called()
    replay = Context()
    unused = Runner([])
    NeuralPageGeometryPreflightHandler(artifact_root=tmp_path, runner=unused)(replay, completed)
    assert unused.calls == 0
    assert result(tmp_path, replay) == manifest
    # Replay still checks old artifacts even when a newer assignment is healthy.
    (tmp_path / descriptor["managedDirectory"] / "board.onnx").unlink()
    with pytest.raises(GridEngineModelError):
        NeuralPageGeometryPreflightHandler(artifact_root=tmp_path, runner=Runner([]))(
            Context(), completed
        )
    with pytest.raises(GridEngineModelError):
        fresh._neural_import_snapshot(
            game_id=job.game_id,
            selection_id=selection,
            source_manifest_sha256=checksum,
            descriptor=import_descriptor,
        )
