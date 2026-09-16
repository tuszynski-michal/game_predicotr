from __future__ import annotations

import hashlib
import json
from collections import Counter
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
    CLASS_STRATIFIED_SPLIT_POLICY_VERSION,
    SplitName,
    TrainingDatasetConfig,
    TrainingSymbol,
    build_balanced_source_assignments,
    build_class_stratified_source_assignments,
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
        if index < 6:
            split = "train"
        elif index < 8:
            split = "validation"
        elif index < 10:
            split = "test"
        else:
            split = "regression"
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
        "splits": [
            {"name": "train"},
            {"name": "validation"},
            {"name": "test"},
            {"name": "regression"},
        ],
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

    with pytest.raises(JobHandlerError, match=r"required split\(s\): validation, test, regression"):
        SymbolTrainingJobHandler(store, candidate_builder=_candidate_builder)(context, context.job)

    assert store.updates[-1]["status"] is SymbolModelIterationStatus.FAILED
    assert source_checksums == {
        path: hashlib.sha256(path.read_bytes()).hexdigest() for path in source_checksums
    }


def test_balanced_assignments_repair_an_incomplete_historical_split() -> None:
    sources = tuple(hashlib.sha256(f"source-{index}".encode()).hexdigest() for index in range(4))
    broken: dict[str, SplitName] = {source: "train" for source in sources}

    assignments = build_balanced_source_assignments(sources, existing=broken)

    assert {split for _source, split in assignments} == {
        "train",
        "validation",
        "test",
        "regression",
    }


def test_class_stratified_assignments_cover_every_symbol_without_source_leakage() -> None:
    codes = ("ARBUZ", "CYTRYNA", "POMARANCZ", "SIEDEM", "SLIWKA", "STAR", "WINOGRON", "WISNIA")
    # Anonymized class incidence from the rejected 768-sample iteration.  The
    # former v2 hash put a source containing only ARBUZ/SIEDEM into test.
    raw_profiles = (
        {"SIEDEM": 7, "ARBUZ": 4},
        {
            "SLIWKA": 14,
            "CYTRYNA": 1,
            "ARBUZ": 3,
            "WISNIA": 7,
            "POMARANCZ": 8,
            "STAR": 6,
            "SIEDEM": 6,
            "WINOGRON": 7,
        },
        {
            "SLIWKA": 9,
            "CYTRYNA": 4,
            "ARBUZ": 4,
            "WISNIA": 21,
            "POMARANCZ": 6,
            "STAR": 7,
            "SIEDEM": 5,
            "WINOGRON": 8,
        },
        {"ARBUZ": 5, "WINOGRON": 13, "SIEDEM": 7},
        {"SIEDEM": 6, "ARBUZ": 5},
        {"SLIWKA": 10, "ARBUZ": 6, "POMARANCZ": 4, "STAR": 3, "SIEDEM": 9, "WINOGRON": 12},
        {
            "SLIWKA": 11,
            "CYTRYNA": 3,
            "ARBUZ": 2,
            "WISNIA": 12,
            "POMARANCZ": 6,
            "STAR": 6,
            "SIEDEM": 7,
            "WINOGRON": 7,
        },
        {"SIEDEM": 6, "ARBUZ": 4},
        {"SIEDEM": 6, "ARBUZ": 6},
        {
            "SLIWKA": 4,
            "CYTRYNA": 2,
            "ARBUZ": 4,
            "WISNIA": 17,
            "POMARANCZ": 5,
            "STAR": 4,
            "SIEDEM": 7,
            "WINOGRON": 9,
        },
        {
            "SLIWKA": 17,
            "ARBUZ": 4,
            "WISNIA": 11,
            "POMARANCZ": 4,
            "STAR": 7,
            "SIEDEM": 9,
            "WINOGRON": 12,
        },
        {
            "SLIWKA": 10,
            "CYTRYNA": 5,
            "ARBUZ": 6,
            "WISNIA": 14,
            "POMARANCZ": 4,
            "STAR": 4,
            "SIEDEM": 5,
            "WINOGRON": 10,
        },
        {
            "SLIWKA": 17,
            "CYTRYNA": 4,
            "ARBUZ": 3,
            "WISNIA": 4,
            "POMARANCZ": 4,
            "STAR": 7,
            "SIEDEM": 4,
            "WINOGRON": 9,
        },
        {
            "SLIWKA": 16,
            "CYTRYNA": 5,
            "ARBUZ": 8,
            "WISNIA": 13,
            "POMARANCZ": 13,
            "STAR": 6,
            "SIEDEM": 3,
            "WINOGRON": 9,
        },
        {
            "SLIWKA": 13,
            "CYTRYNA": 3,
            "ARBUZ": 4,
            "WISNIA": 8,
            "POMARANCZ": 4,
            "STAR": 8,
            "SIEDEM": 7,
            "WINOGRON": 6,
        },
        {"ARBUZ": 3, "WINOGRON": 9, "SIEDEM": 11},
        {"SIEDEM": 6, "ARBUZ": 1},
        {
            "SLIWKA": 9,
            "CYTRYNA": 5,
            "ARBUZ": 3,
            "WISNIA": 8,
            "POMARANCZ": 2,
            "STAR": 9,
            "SIEDEM": 6,
            "WINOGRON": 7,
        },
        {
            "SLIWKA": 6,
            "ARBUZ": 7,
            "WISNIA": 10,
            "POMARANCZ": 6,
            "STAR": 9,
            "SIEDEM": 6,
            "WINOGRON": 10,
        },
    )
    profiles = {
        hashlib.sha256(f"source-{index}".encode()).hexdigest(): profile
        for index, profile in enumerate(raw_profiles)
    }

    assignments = dict(build_class_stratified_source_assignments(profiles))

    assert len(assignments) == 19
    assert set(assignments.values()) == {"train", "validation", "test", "regression"}
    for split in ("train", "validation", "test", "regression"):
        covered = {
            code
            for source, assigned in assignments.items()
            if assigned == split
            for code in profiles[source]
        }
        assert covered == set(codes)
    assert Counter(assignments.values()) == Counter(
        {"train": 12, "validation": 3, "test": 2, "regression": 2}
    )


def test_class_stratified_assignments_are_deterministic_and_stable_when_extended() -> None:
    initial = {
        hashlib.sha256(f"stable-{index}".encode()).hexdigest(): {"A": 2, "B": 3}
        for index in range(8)
    }
    first = dict(build_class_stratified_source_assignments(initial))
    repeated = dict(build_class_stratified_source_assignments(initial))
    extended = {
        **initial,
        **{
            hashlib.sha256(f"new-{index}".encode()).hexdigest(): {"A": 1, "B": 1}
            for index in range(4)
        },
    }

    grown = dict(build_class_stratified_source_assignments(extended, existing=first))

    assert repeated == first
    assert all(grown[source] == split for source, split in first.items())


def test_v3_training_rejects_missing_test_class_before_first_epoch(tmp_path: Path) -> None:
    cohort_checksum = hashlib.sha256(b"cohort-v3-incomplete").hexdigest()
    artifact = _artifact(tmp_path, cohort_checksum)
    for sample in artifact.manifest["samples"]:
        if sample["split"] == "test" and sample["symbolCode"] == "B":
            sample["split"] = "train"
    spec = _IterationSpec(
        iteration_id=uuid4(),
        game_id=uuid4(),
        game_code="fixture",
        cohort_id=uuid4(),
        cohort_checksum=cohort_checksum,
        configuration=TrainingConfig(epochs=2, batch_size=4, input_size=16),
        configuration_fingerprint=hashlib.sha256(b"v3-incomplete-config").hexdigest(),
        iteration_number=1,
        dataset_config=TrainingDatasetConfig(
            split_policy_version=CLASS_STRATIFIED_SPLIT_POLICY_VERSION
        ),
    )
    store = FakeTrainingStore(tmp_path, artifact, spec)
    context = FakeContext(_job(spec))

    SymbolTrainingJobHandler(
        store,
        candidate_builder=lambda **_values: pytest.fail("candidate gate must not run"),
    )(context, context.job)

    assert store.updates[-1]["status"] is SymbolModelIterationStatus.REJECTED
    assert store.updates[-1]["rejection_reasons"] == (
        "SYMBOL_TRAINING_EVALUATION_CLASS_COVERAGE_INSUFFICIENT",
    )
    assert store.updates[-1]["gate_metrics"] == {
        "missingClassCoverage": {"test": ["B"]},
        "splitPolicyVersion": CLASS_STRATIFIED_SPLIT_POLICY_VERSION,
        "trainingStarted": False,
    }
    assert not list((tmp_path / "data" / "models").glob("**/epoch-*.pt"))
