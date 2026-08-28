from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from game_predictor_api.domain.jobs import Job, JobStatus, JobType, create_job
from game_predictor_api.domain.symbol_model_iterations import SymbolModelIterationStatus
from game_predictor_worker.images.symbol_classifier import TrainingConfig
from game_predictor_worker.jobs.runtime import JobHandlerError
from game_predictor_worker.symbols.candidate_gate import (
    SymbolCandidateGateConfiguration,
    SymbolCandidateGateResult,
    build_symbol_candidate,
)
from game_predictor_worker.symbols.training_dataset import (
    TrainingDatasetConfig,
    TrainingSymbol,
    build_balanced_source_assignments,
    build_cumulative_training_dataset,
)
from game_predictor_worker.symbols.training_job import (
    SymbolTrainingJobHandler,
    _IterationSpec,
)
from PIL import Image


class FakeTrainingStore:
    def __init__(self, root: Path, artifact: object, spec: _IterationSpec) -> None:
        self.artifact_root = root
        self.artifact = artifact
        self.spec = spec
        self.updates: list[dict[str, object]] = []

    def load_spec(self, _job: Job) -> _IterationSpec:
        return self.spec

    def build_dataset(self, _spec: _IterationSpec, progress: object) -> object:
        return self.artifact

    def update(self, _iteration_id: UUID, **values: object) -> None:
        self.updates.append(values)


class FakeContext:
    def __init__(self, job: Job, *, cancel_at_epoch: int | None = None) -> None:
        self.job = job
        self.cancel_at_epoch = cancel_at_epoch
        self.heartbeats = 0
        self.stages: list[str] = []

    def now(self) -> datetime:
        return datetime.now(UTC)

    def heartbeat(self) -> None:
        self.heartbeats += 1

    def checkpoint(self, **values: object) -> None:
        payload = values["checkpoint_payload"]
        assert isinstance(payload, dict)
        stage = str(values["stage"])
        self.stages.append(stage)
        self.job = replace(
            self.job,
            checkpoint_payload=payload,
            progress_current=int(values["current"]),
            progress_total=int(values["total"]),
            stage=stage,
        )
        if self.cancel_at_epoch == payload.get("last_completed_epoch"):
            self.job = replace(self.job, status=JobStatus.CANCELLED)
            raise RuntimeError("cancelled")


def _candidate_builder(**values: object) -> SymbolCandidateGateResult:
    stage = values["stage"]
    assert callable(stage)
    for name in ("onnx_export", "calibration", "evaluation", "manifest"):
        stage(name)
    checksum = hashlib.sha256(b"candidate").hexdigest()
    return SymbolCandidateGateResult(
        passed=True,
        rejection_reasons=(),
        configuration_fingerprint=checksum,
        configuration_payload={"gateVersion": "test"},
        manifest_checksum_sha256=checksum,
        manifest_relative_path="models/fixture/candidate/manifest.json",
        report_checksum_sha256=checksum,
        report_relative_path="models/fixture/candidate/report.json",
        onnx_checksum_sha256=checksum,
        onnx_relative_path="models/fixture/candidate/model.onnx",
        metrics={"status": "candidate_ready"},
    )


def _artifact(root: Path, cohort_checksum: str) -> object:
    samples: list[dict[str, object]] = []
    base = root / "data" / "training" / "fixture" / cohort_checksum
    for index in range(12):
        code = "A" if index % 2 == 0 else "B"
        split = "train" if index < 8 else "validation"
        relative = f"assets/{index:02d}.png"
        path = base / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (20, 20), (255, 40, 40) if code == "A" else (40, 40, 255)).save(path)
        content = path.read_bytes()
        samples.append(
            {
                "assetRelativePath": relative,
                "cropChecksumSha256": hashlib.sha256(content).hexdigest(),
                "cropSampleId": hashlib.sha256(f"sample-{index}".encode()).hexdigest(),
                "sourceImageChecksumSha256": hashlib.sha256(f"source-{index}".encode()).hexdigest(),
                "split": split,
                "symbolCode": code,
            }
        )
    manifest = {
        "gameCode": "fixture",
        "seed": "test-seed",
        "samples": samples,
        "splits": [{"name": "train"}, {"name": "validation"}],
        "symbols": [
            {"symbolCode": "A", "symbolId": "symbol-a"},
            {"symbolCode": "B", "symbolId": "symbol-b"},
        ],
    }
    return SimpleNamespace(
        cohort_checksum_sha256=cohort_checksum,
        manifest=manifest,
        manifest_checksum_sha256=hashlib.sha256(b"manifest").hexdigest(),
        manifest_relative_path="training/fixture/manifest.json",
    )


def _job(spec: _IterationSpec) -> Job:
    return create_job(
        JobType.SYMBOL_TRAINING,
        game_id=spec.game_id,
        input_payload={
            "schema_version": 1,
            "cohort_id": str(spec.cohort_id),
            "cohort_checksum_sha256": spec.cohort_checksum,
            "configuration": {},
            "configuration_fingerprint": spec.configuration_fingerprint,
            "idempotency_key": str(uuid4()),
        },
    )


def _v2_artifact(root: Path) -> tuple[object, str]:
    cells: list[dict[str, object]] = []
    source_checksums: list[str] = []
    data_root = root / "data"
    for source_index in range(8):
        source_checksum = hashlib.sha256(f"v2-source-{source_index}".encode()).hexdigest()
        source_checksums.append(source_checksum)
        for cell_index, code in enumerate(("A", "B")):
            image_path = data_root / "working" / "v2" / f"{source_index}-{code}.png"
            image_path.parent.mkdir(parents=True, exist_ok=True)
            Image.new(
                "RGB",
                (20, 20),
                (240, 20 + source_index, 20) if code == "A" else (20, 20 + source_index, 240),
            ).save(image_path)
            content = image_path.read_bytes()
            crop_checksum = hashlib.sha256(content).hexdigest()
            cells.append(
                {
                    "cellIndex": cell_index,
                    "cellReviewId": f"cell-{source_index}-{code}",
                    "cellRevision": 1,
                    "cropChecksumSha256": crop_checksum,
                    "cropRelativePath": image_path.relative_to(data_root).as_posix(),
                    "cropSampleId": hashlib.sha256(
                        f"v2-sample-{source_index}-{code}".encode()
                    ).hexdigest(),
                    "cropperVersion": "v19",
                    "geometryRevision": 0,
                    "importJobId": "v2-import",
                    "recognizedBoardId": f"v2-board-{source_index}",
                    "reviewItemId": f"v2-review-{source_index}",
                    "selectionReason": "diverse_approval",
                    "sequenceNumber": source_index + 1,
                    "source": {
                        "checksumSha256": source_checksum,
                        "relativePath": f"originals/{source_checksum}.jpg",
                    },
                    "sourceImageId": f"v2-source-image-{source_index}",
                    "symbolCode": code,
                }
            )
    cohort = {
        "cells": cells,
        "counts": {"cellSamples": len(cells), "sourceImages": 8},
        "datasetKind": "verified-symbol-cell-training-cohort-v2",
        "gameId": "00000000-0000-0000-0000-000000000001",
        "schemaVersion": 2,
    }
    content = (
        json.dumps(cohort, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode()
    cohort_checksum = hashlib.sha256(content).hexdigest()
    cohort_path = data_root / "training" / "v2-cohort.json"
    cohort_path.parent.mkdir(parents=True, exist_ok=True)
    cohort_path.write_bytes(content)
    artifact = build_cumulative_training_dataset(
        cohort_path=cohort_path,
        expected_cohort_checksum_sha256=cohort_checksum,
        artifact_root=root,
        game_code="fixture-v2",
        symbols=(
            TrainingSymbol(id="symbol-a", code="A"),
            TrainingSymbol(id="symbol-b", code="B"),
        ),
        config=TrainingDatasetConfig(
            source_assignments=build_balanced_source_assignments(source_checksums)
        ),
    )
    return artifact, cohort_checksum


def _real_candidate_builder(**values: object) -> SymbolCandidateGateResult:
    return build_symbol_candidate(
        **values,  # type: ignore[arg-type]
        configuration=SymbolCandidateGateConfiguration(
            minimum_accuracy=0,
            minimum_macro_recall=0,
            performance_repetitions=1,
        ),
    )


def test_v2_cell_cohort_completes_training_onnx_and_candidate_gate(
    tmp_path: Path,
) -> None:
    artifact, cohort_checksum = _v2_artifact(tmp_path)
    spec = _IterationSpec(
        iteration_id=uuid4(),
        game_id=uuid4(),
        game_code="fixture-v2",
        cohort_id=uuid4(),
        cohort_checksum=cohort_checksum,
        configuration=TrainingConfig(epochs=1, batch_size=4, input_size=16),
        configuration_fingerprint=hashlib.sha256(b"v2-config").hexdigest(),
        iteration_number=1,
    )
    store = FakeTrainingStore(tmp_path, artifact, spec)
    context = FakeContext(_job(spec))

    SymbolTrainingJobHandler(store, candidate_builder=_real_candidate_builder)(context, context.job)

    assert store.updates[-1]["status"] is SymbolModelIterationStatus.CANDIDATE_READY
    assert list((tmp_path / "data" / "models").glob("**/*.onnx"))
    assert context.job.progress_current == 6


def test_training_job_writes_immutable_epoch_checkpoints_and_does_not_change_inputs(
    tmp_path: Path,
) -> None:
    cohort_checksum = hashlib.sha256(b"cohort").hexdigest()
    spec = _IterationSpec(
        iteration_id=uuid4(),
        game_id=uuid4(),
        game_code="fixture",
        cohort_id=uuid4(),
        cohort_checksum=cohort_checksum,
        configuration=TrainingConfig(epochs=2, batch_size=4, input_size=16),
        configuration_fingerprint=hashlib.sha256(b"config").hexdigest(),
        iteration_number=1,
    )
    artifact = _artifact(tmp_path, cohort_checksum)
    source_checksums = {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (tmp_path / "data" / "training").rglob("*.png")
    }
    store = FakeTrainingStore(tmp_path, artifact, spec)
    context = FakeContext(_job(spec))

    SymbolTrainingJobHandler(store, candidate_builder=_candidate_builder)(context, context.job)

    assert store.updates[-1]["status"] is SymbolModelIterationStatus.CANDIDATE_READY
    assert context.job.progress_current == 7
    assert "symbol_training:dataset_build" in context.stages
    checkpoints = list((tmp_path / "data" / "models").rglob("*.pt"))
    assert len(checkpoints) == 3
    assert source_checksums == {
        path: hashlib.sha256(path.read_bytes()).hexdigest() for path in source_checksums
    }


def test_cancelled_training_keeps_checkpoint_and_retry_resumes_same_fingerprint(
    tmp_path: Path,
) -> None:
    cohort_checksum = hashlib.sha256(b"cohort").hexdigest()
    spec = _IterationSpec(
        iteration_id=uuid4(),
        game_id=uuid4(),
        game_code="fixture",
        cohort_id=uuid4(),
        cohort_checksum=cohort_checksum,
        configuration=TrainingConfig(epochs=2, batch_size=4, input_size=16),
        configuration_fingerprint=hashlib.sha256(b"config").hexdigest(),
        iteration_number=1,
    )
    store = FakeTrainingStore(tmp_path, _artifact(tmp_path, cohort_checksum), spec)
    first = FakeContext(_job(spec), cancel_at_epoch=1)
    try:
        SymbolTrainingJobHandler(store, candidate_builder=_candidate_builder)(first, first.job)
    except RuntimeError as error:
        assert str(error) == "cancelled"
    else:
        raise AssertionError("Expected controlled cancellation.")
    assert store.updates[-1]["status"] is SymbolModelIterationStatus.CANCELLED
    assert first.job.checkpoint_payload is not None
    retry_job = replace(first.job, status=JobStatus.CREATED)
    retry = FakeContext(retry_job)

    SymbolTrainingJobHandler(store, candidate_builder=_candidate_builder)(retry, retry.job)

    assert store.updates[-1]["status"] is SymbolModelIterationStatus.CANDIDATE_READY
    assert retry.job.progress_current == 7


def test_failed_training_preserves_input_crop_checksums(tmp_path: Path) -> None:
    cohort_checksum = hashlib.sha256(b"cohort").hexdigest()
    spec = _IterationSpec(
        iteration_id=uuid4(),
        game_id=uuid4(),
        game_code="fixture",
        cohort_id=uuid4(),
        cohort_checksum=cohort_checksum,
        configuration=TrainingConfig(epochs=2, batch_size=4, input_size=16),
        configuration_fingerprint=hashlib.sha256(b"config").hexdigest(),
        iteration_number=1,
    )
    artifact = _artifact(tmp_path, cohort_checksum)
    for sample in artifact.manifest["samples"]:
        sample["split"] = "train"
    source_checksums = {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (tmp_path / "data" / "training").rglob("*.png")
    }
    store = FakeTrainingStore(tmp_path, artifact, spec)
    context = FakeContext(_job(spec))

    with pytest.raises(JobHandlerError, match="validation must not be empty"):
        SymbolTrainingJobHandler(store, candidate_builder=_candidate_builder)(context, context.job)

    assert store.updates[-1]["status"] is SymbolModelIterationStatus.FAILED
    assert source_checksums == {
        path: hashlib.sha256(path.read_bytes()).hexdigest() for path in source_checksums
    }
