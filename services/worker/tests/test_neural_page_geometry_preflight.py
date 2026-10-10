from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest
from game_predictor_api.domain.catalog import GameShapeGeometryConfiguration
from game_predictor_api.domain.grid_engine_profiles import grid_engine_profile_for
from game_predictor_api.domain.image_geometry_v2 import AttestedSequenceRange
from game_predictor_api.domain.jobs import Job, JobType, create_job
from game_predictor_api.domain.neural_grid_proposal import (
    NEURAL_GRID_PREFLIGHT_POLICY_VERSION,
    NeuralGridSnapshot,
    build_neural_source_binding,
)
from game_predictor_worker.geometry_core.bounded_runtime import GeometryRuntimeError
from game_predictor_worker.geometry_core.inference import BoardDetection
from game_predictor_worker.images.neural_page_geometry_preflight import (
    NeuralPageGeometryPreflightHandler,
    validate_neural_page_manifest,
)
from game_predictor_worker.images.page_geometry_preflight import PageGeometryPreflightHandler
from game_predictor_worker.jobs.runtime import JobHandlerError
from PIL import Image


class Context:
    def __init__(self, *, stop_after: int | None = None) -> None:
        self.checkpoints: list[dict[str, object]] = []
        self.stop_after = stop_after

    def heartbeat(self) -> None:
        pass

    def checkpoint(self, **kwargs: object) -> None:
        if self.checkpoints:
            assert kwargs["current"] >= self.checkpoints[-1]["current"]  # type: ignore[operator]
            assert kwargs["review_count"] >= self.checkpoints[-1]["review_count"]  # type: ignore[operator]
        self.checkpoints.append(kwargs)
        if len(self.checkpoints) == self.stop_after:
            raise RuntimeError("lost checkpoint response")


class Models:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.calls = 0

    def require(self, _version: object) -> Path:
        self.calls += 1
        return self.root


class Runner:
    def __init__(self, counts: list[int], *, invalid: bool = False) -> None:
        self.counts = counts
        self.invalid = invalid
        self.calls = 0
        self.closed = False

    def run(self, *_args: object, **_kwargs: object) -> list[BoardDetection]:
        count = self.counts[self.calls]
        self.calls += 1
        found = []
        for index in range(count):
            left, top = (index % 3) * 140 + 10.125, (index // 3) * 100 + 10.375
            nodes = np.array(
                [
                    [left + column * 20.25, top + row * 20.125]
                    for row in range(4)
                    for column in range(6)
                ],
                np.float32,
            )
            nodes[8, 0] += 0.3125
            quad = nodes[[0, 5, 23, 18]]
            found.append(
                BoardDetection(score=0.9, screen_quad=quad, nodes=None if self.invalid else nodes)
            )
        return found

    def close(self) -> None:
        self.closed = True


def job_fixture(tmp_path: Path, *, files: int = 2, maximum: int = 500000) -> tuple[Job, list[str]]:
    selection = uuid4()
    staged = tmp_path / str(selection)
    staged.mkdir()
    entries = []
    checksums = []
    for index in range(files):
        source = staged / f"{index:08d}.jpg"
        Image.fromarray(np.full((300, 500, 3), 32 + index, dtype=np.uint8)).save(source)
        content = source.read_bytes()
        checksum = hashlib.sha256(content).hexdigest()
        checksums.append(checksum)
        entries.append(
            {
                "orderIndex": index,
                "relativePath": f"seq_{101 + index * 100}-{105 + index * 100}.jpg",
                "storedFileName": source.name,
                "sizeBytes": len(content),
                "checksumSha256": checksum,
            }
        )
    manifest = json.dumps(
        {
            "schemaVersion": 1,
            "purpose": "layout_import",
            "gameId": None,
            "orderingPolicy": "natural_relative_path_v1",
            "files": entries,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    (staged / "_browser_manifest.json").write_bytes(manifest)
    snapshot = NeuralGridSnapshot.for_game(
        maximum,
        grid_engine_profile_for(GameShapeGeometryConfiguration.GRID_PROFILE_MUMIE_V1).current,
    )
    return create_job(
        JobType.VALIDATE,
        game_id=uuid4(),
        input_payload={
            "schema_version": 2,
            "validation_kind": "page_geometry_preflight",
            "preflight_policy_version": NEURAL_GRID_PREFLIGHT_POLICY_VERSION,
            "source_selection_id": str(selection),
            "source_directory": str(staged),
            "source_manifest_sha256": hashlib.sha256(manifest).hexdigest(),
            "page_registration_profile": {
                "schemaVersion": 1,
                "policy": "page-registration-v1",
                "anchors": [],
            },
            "page_geometry_overrides": {},
            "canonical_sequence_numbers": [],
            "neural_grid_proposal": snapshot.to_payload(),
        },
    ), checksums


def result(root: Path, context: Context) -> dict[str, object]:
    checkpoint = context.checkpoints[-1]["checkpoint_payload"]
    return json.loads((root / checkpoint["geometry_manifest_relative_path"]).read_bytes())  # type: ignore[index,operator]


def test_mixed_folder_is_durable_review_without_fabricated_binding(tmp_path: Path) -> None:
    job, checksums = job_fixture(tmp_path)
    root = tmp_path / "artifacts"
    runner = Runner([5, 4])
    context = Context()
    handler = NeuralPageGeometryPreflightHandler(
        artifact_root=root, runner=runner, model_store=Models(root)
    )  # type: ignore[arg-type]
    handler(context, job)  # type: ignore[arg-type]
    manifest = result(root, context)
    assert manifest["registeredSourceCount"] == 0
    assert manifest["reviewRequiredSourceCount"] == 2
    first, second = [manifest["entries"][key] for key in checksums]  # type: ignore[index]
    assert first["status"] == "review_required"
    assert len(first["neuralProposalBinding"]["assignments"]) == 5
    assert second["status"] == "slot_binding_required"
    assert second["neuralProposalBinding"] is None
    assert runner.closed
    # Recreate the handler and job after a response loss. No inference is repeated.
    replay = Context()
    unused = Runner([])
    NeuralPageGeometryPreflightHandler(artifact_root=root, runner=unused, model_store=Models(root))(
        replay, replace(job, checkpoint_payload=context.checkpoints[-1]["checkpoint_payload"])
    )  # type: ignore[arg-type]
    assert unused.calls == 0
    assert (
        replay.checkpoints[-1]["checkpoint_payload"]["geometry_manifest_checksum_sha256"]
        == context.checkpoints[-1]["checkpoint_payload"]["geometry_manifest_checksum_sha256"]
    )  # type: ignore[index]


def test_checkpoint_written_before_lost_response_survives_restart(tmp_path: Path) -> None:
    job, _checksums = job_fixture(tmp_path)
    root = tmp_path / "artifacts"
    first = Runner([5])
    with pytest.raises(RuntimeError, match="lost checkpoint response"):
        NeuralPageGeometryPreflightHandler(
            artifact_root=root, runner=first, model_store=Models(root)
        )(Context(stop_after=1), job)  # type: ignore[arg-type]
    assert first.closed
    next_runner = Runner([4])
    context = Context()
    NeuralPageGeometryPreflightHandler(
        artifact_root=root, runner=next_runner, model_store=Models(root)
    )(context, job)  # type: ignore[arg-type]
    assert next_runner.calls == 1
    assert result(root, context)["sourceCount"] == 2


def test_source_timeout_is_durable_pending_and_does_not_block_later_sources(tmp_path: Path) -> None:
    class TimeoutFirst(Runner):
        def run(self, *args: object, **kwargs: object) -> list[BoardDetection]:
            if self.calls == 0:
                self.calls += 1
                raise GeometryRuntimeError("NEURAL_GRID_SOURCE_TIME_LIMIT", "source deadline")
            return super().run(*args, **kwargs)

    job, checksums = job_fixture(tmp_path)
    root = tmp_path / "artifacts"
    context = Context()
    runner = TimeoutFirst([0, 5])
    NeuralPageGeometryPreflightHandler(artifact_root=root, runner=runner, model_store=Models(root))(
        context, job
    )  # type: ignore[arg-type]
    manifest = result(root, context)
    timed_out, good = [manifest["entries"][checksum] for checksum in checksums]  # type: ignore[index]
    assert timed_out["status"] == "slot_binding_required"
    assert timed_out["reasonCode"] == "NEURAL_GRID_SOURCE_TIME_LIMIT"
    assert timed_out["neuralProposal"]["detections"] == []
    assert timed_out["neuralProposalBinding"] is None
    assert good["status"] == "review_required"
    assert len(good["neuralProposalBinding"]["assignments"]) == 5
    replay = Context()
    unused = Runner([])
    NeuralPageGeometryPreflightHandler(artifact_root=root, runner=unused, model_store=Models(root))(
        replay, replace(job, checkpoint_payload=context.checkpoints[-1]["checkpoint_payload"])
    )  # type: ignore[arg-type]
    assert unused.calls == 0 and result(root, replay) == manifest


@pytest.mark.parametrize(
    "code",
    [
        "NEURAL_GRID_STARTUP_TIME_LIMIT",
        "NEURAL_GRID_MODEL_SNAPSHOT_DRIFT",
        "NEURAL_GRID_RUNTIME_CLEANUP_FAILED",
    ],
)
def test_infrastructure_and_model_failures_still_abort_before_publication(
    tmp_path: Path, code: str
) -> None:
    class BrokenRunner(Runner):
        def run(self, *_args: object, **_kwargs: object) -> list[BoardDetection]:
            raise GeometryRuntimeError(code, "global failure")

    job, _ = job_fixture(tmp_path)
    root = tmp_path / "artifacts"
    context = Context()
    with pytest.raises(GeometryRuntimeError) as error:
        NeuralPageGeometryPreflightHandler(
            artifact_root=root, runner=BrokenRunner([]), model_store=Models(root)
        )(context, job)  # type: ignore[arg-type]
    assert error.value.code == code
    assert not list((root / "data" / "page-geometry-manifests").glob("*.json"))


def test_missing_middle_override_reuses_pinned_proposal_without_new_inference(
    tmp_path: Path,
) -> None:
    job, checksums = job_fixture(tmp_path, files=1)
    root = tmp_path / "artifacts"
    context = Context()
    NeuralPageGeometryPreflightHandler(
        artifact_root=root, runner=Runner([4]), model_store=Models(root)
    )(context, job)  # type: ignore[arg-type]
    proposal = result(root, context)["entries"][checksums[0]]["neuralProposal"]  # type: ignore[index]
    ids = [item["detectionId"] for item in proposal["detections"]]
    binding = build_neural_source_binding(
        proposal,
        confirmed_range=AttestedSequenceRange(start=101, end=105),
        assignments=[
            {"detectionId": identity, "positionIndex": position}
            for identity, position in zip(ids, [0, 1, 3, 4], strict=True)
        ],
    )
    checkpoint = context.checkpoints[-1]["checkpoint_payload"]
    new_job = create_job(
        JobType.VALIDATE,
        game_id=job.game_id,
        input_payload={
            **job.input_payload,
            "page_geometry_overrides": {checksums[0]: {"neuralProposalBinding": binding}},
            "base_page_geometry_manifest": {
                "manifestChecksumSha256": checkpoint["geometry_manifest_checksum_sha256"]
            },
        },
    )  # type: ignore[index]
    next_context = Context()
    unused = Runner([])
    NeuralPageGeometryPreflightHandler(artifact_root=root, runner=unused, model_store=Models(root))(
        next_context, new_job
    )  # type: ignore[arg-type]
    entry = result(root, next_context)["entries"][checksums[0]]  # type: ignore[index]
    assert entry["neuralProposalBinding"]["missingPositionIndexes"] == [2]
    assert entry["neuralProposalBinding"]["assignments"][2]["positionIndex"] == 3
    assert entry["neuralProposal"]["proposalChecksumSha256"] == proposal["proposalChecksumSha256"]
    assert unused.calls == 0


def test_invalid_detection_never_exposes_crops_and_drift_fails_closed(tmp_path: Path) -> None:
    job, checksums = job_fixture(tmp_path, files=1)
    root = tmp_path / "artifacts"
    context = Context()
    NeuralPageGeometryPreflightHandler(
        artifact_root=root, runner=Runner([5], invalid=True), model_store=Models(root)
    )(context, job)  # type: ignore[arg-type]
    manifest = result(root, context)
    entry = manifest["entries"][checksums[0]]  # type: ignore[index]
    assert entry["neuralProposalBinding"] is None
    assert all(item["cellQuads"] == [] for item in entry["neuralProposal"]["detections"])
    manifest["gameId"] = str(uuid4())
    with pytest.raises(JobHandlerError, match="incompatible"):
        validate_neural_page_manifest(
            manifest,
            game_id=str(job.game_id),
            source_selection_id=job.input_payload["source_selection_id"],
            source_manifest_sha256=job.input_payload["source_manifest_sha256"],
            snapshot=NeuralGridSnapshot.from_payload(job.input_payload["neural_grid_proposal"]),
        )  # type: ignore[arg-type]


def test_handler_dispatches_neural_path_without_classical_registrar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job, _checksums = job_fixture(tmp_path, files=1)
    calls = []
    monkeypatch.setattr(
        NeuralPageGeometryPreflightHandler,
        "__call__",
        lambda _self, _context, actual: calls.append(actual.id),
    )
    PageGeometryPreflightHandler(artifact_root=tmp_path / "artifacts")(Context(), job)  # type: ignore[arg-type]
    assert calls == [job.id]


def test_source_mutation_during_inference_is_rejected_before_publication(tmp_path: Path) -> None:
    job, _checksums = job_fixture(tmp_path, files=1)
    root = tmp_path / "artifacts"
    staged = Path(job.input_payload["source_directory"])

    class MutatingRunner(Runner):
        def run(self, *args: object, **kwargs: object) -> list[BoardDetection]:
            output = super().run(*args, **kwargs)
            Image.fromarray(np.full((300, 500, 3), 233, dtype=np.uint8)).save(
                staged / "00000000.jpg"
            )
            return output

    context = Context()
    runner = MutatingRunner([5])
    with pytest.raises(JobHandlerError, match="before manifest publication"):
        NeuralPageGeometryPreflightHandler(
            artifact_root=root, runner=runner, model_store=Models(root)
        )(context, job)  # type: ignore[arg-type]
    assert runner.closed
    assert not (root / "data" / "page-geometry-manifests").exists()


def test_schema7_managed_neural_clone_survives_missing_staging_and_rejects_manifest_drift(
    tmp_path: Path,
) -> None:
    from game_predictor_worker.images.source_ingestion import ManagedOriginalStore

    source_job, _checksums = job_fixture(tmp_path, files=1)
    root = tmp_path / "artifacts"
    store = ManagedOriginalStore(root)
    original = store.load_or_create_manifest(
        source_job, source_directory=Path(source_job.input_payload["source_directory"])
    )
    for item in original.originals:
        store.ensure_original(original, item)
    # New run refers to the verified managed inventory, not a client path.
    managed_job = create_job(
        JobType.IMPORT,
        game_id=source_job.game_id,
        input_payload={
            "schema_version": 7,
            "import_kind": "image_directory",
            "source_directory": str(tmp_path / "already-retained"),
            "managed_source_job_id": str(source_job.id),
            "managed_source_manifest_checksum_sha256": original.checksum_sha256,
            "neural_grid_proposal": source_job.input_payload["neural_grid_proposal"],
        },
    )
    cloned = store.load_or_create_manifest(
        managed_job, source_directory=tmp_path / "already-retained"
    )
    assert cloned.originals == original.originals
    assert json.loads(cloned.content)["reprocessedFromJobId"] == str(source_job.id)
    corrupted = create_job(
        JobType.IMPORT,
        game_id=source_job.game_id,
        input_payload={
            **managed_job.input_payload,
            "managed_source_manifest_checksum_sha256": "a" * 64,
        },
    )
    with pytest.raises(JobHandlerError, match="changed after reprocess creation"):
        store.load_or_create_manifest(corrupted, source_directory=tmp_path / "already-retained")


def test_managed_neural_exclusions_persist_across_clones_and_preflight(tmp_path: Path) -> None:
    from game_predictor_worker.images.source_ingestion import ManagedOriginalStore

    source_job, checksums = job_fixture(tmp_path)
    root = tmp_path / "artifacts"
    store = ManagedOriginalStore(root)
    original = store.load_or_create_manifest(
        source_job, source_directory=Path(source_job.input_payload["source_directory"])
    )
    for item in original.originals:
        store.ensure_original(original, item)
    exclusions = {
        checksums[0]: {
            "sourceRelativePath": "seq_101-105.jpg",
            "decisionChecksumSha256": "d" * 64,
        }
    }
    second = create_job(
        JobType.VALIDATE,
        game_id=source_job.game_id,
        input_payload={
            **source_job.input_payload,
            "source_directory": str(tmp_path / "retained"),
            "managed_source_job_id": str(source_job.id),
            "managed_source_manifest_checksum_sha256": original.checksum_sha256,
            "source_exclusions": exclusions,
        },
    )
    context = Context()
    runner = Runner([5])
    NeuralPageGeometryPreflightHandler(artifact_root=root, runner=runner, model_store=Models(root))(
        context, second
    )  # type: ignore[arg-type]
    assert runner.calls == 1
    assert list(result(root, context)["entries"]) == [checksums[1]]
    cloned = store.load_or_create_manifest(second, source_directory=tmp_path / "retained")
    assert len(cloned.originals) == 1
    # A later managed run retains the exclusion's verified provenance even
    # though that source is already absent from the previous active inventory.
    third = create_job(
        JobType.IMPORT,
        game_id=source_job.game_id,
        input_payload={
            **second.input_payload,
            "schema_version": 7,
            "import_kind": "image_directory",
            "managed_source_job_id": str(second.id),
            "managed_source_manifest_checksum_sha256": cloned.checksum_sha256,
        },
    )
    assert (
        store.load_or_create_manifest(third, source_directory=tmp_path / "retained").originals
        == cloned.originals
    )
    stale = create_job(
        JobType.IMPORT,
        game_id=source_job.game_id,
        input_payload={
            **third.input_payload,
            "source_exclusions": {
                checksums[0]: {
                    **exclusions[checksums[0]],
                    "sourceRelativePath": "different.jpg",
                }
            },
        },
    )
    with pytest.raises(JobHandlerError, match="differs from its inventory"):
        store.load_or_create_manifest(stale, source_directory=tmp_path / "retained")
