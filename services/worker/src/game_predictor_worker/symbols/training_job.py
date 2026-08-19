"""Durable, resumable training handler for the selected spatial symbol model."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from time import monotonic
from typing import Any, cast
from uuid import UUID

import torch
from game_predictor_api.application.verified_training_datasets import VerifiedTrainingDatasetService
from game_predictor_api.domain.jobs import Job, JobType
from game_predictor_api.domain.symbol_model_iterations import SymbolModelIterationStatus
from game_predictor_api.storage.models import SymbolModelIterationModel
from game_predictor_api.storage.training_dataset_catalog_repository import (
    SqlAlchemyTrainingDatasetCatalogRepository,
)
from game_predictor_api.storage.verified_training_cohort_repository import (
    SqlAlchemyVerifiedTrainingCohortRepository,
)
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from torch import Tensor, nn

from game_predictor_worker.images.symbol_classifier import (
    ClassifierSample,
    PreparedTrainingData,
    SymbolClassifierError,
    TrainingConfig,
    set_deterministic_runtime,
)
from game_predictor_worker.images.symbol_model_benchmark import (
    SPATIAL_VARIANT,
    BenchmarkTensorDataset,
    build_benchmark_model,
    evaluate_benchmark_model,
)
from game_predictor_worker.jobs.runtime import JobExecutionContext, JobHandlerError
from game_predictor_worker.symbols.candidate_gate import (
    SymbolCandidateGateResult,
    build_symbol_candidate,
)
from game_predictor_worker.symbols.training_dataset import TrainingDatasetConfig

TRAINING_WORKFLOW = "symbol_training"
CHECKPOINT_SCHEMA_VERSION = 1
TRAINING_RUNTIME_VERSION = "durable-spatial-training-v1"
CANDIDATE_STAGE_COUNT = 5

CandidateBuilder = Callable[..., SymbolCandidateGateResult]


@dataclass(frozen=True, slots=True)
class _IterationSpec:
    iteration_id: UUID
    game_id: UUID
    game_code: str
    cohort_id: UUID
    cohort_checksum: str
    configuration: TrainingConfig
    configuration_fingerprint: str
    iteration_number: int
    dataset_config: TrainingDatasetConfig = TrainingDatasetConfig()


class SymbolTrainingJobStore:
    def __init__(self, session_factory: sessionmaker[Session], artifact_root: Path) -> None:
        self._session_factory = session_factory
        self.artifact_root = artifact_root.resolve()

    def load_spec(self, job: Job) -> _IterationSpec:
        if job.job_type is not JobType.SYMBOL_TRAINING or job.game_id is None:
            raise JobHandlerError("SYMBOL_TRAINING_JOB_INVALID", "Job is not symbol training.")
        with self._session_factory() as session:
            record = session.scalar(
                select(SymbolModelIterationModel).where(SymbolModelIterationModel.job_id == job.id)
            )
            if record is None:
                raise JobHandlerError(
                    "SYMBOL_TRAINING_ITERATION_MISSING", "Training iteration is missing."
                )
            cohort_id = _uuid(job.input_payload.get("cohort_id"), "cohort_id")
            fingerprint = _sha(
                job.input_payload.get("configuration_fingerprint"), "configuration_fingerprint"
            )
            cohort_checksum = _sha(
                job.input_payload.get("cohort_checksum_sha256"), "cohort_checksum_sha256"
            )
            if (
                record.game_id != job.game_id
                or record.cohort_id != cohort_id
                or record.configuration_fingerprint != fingerprint
                or _configuration_fingerprint(record.configuration_payload) != fingerprint
                or job.input_payload.get("configuration") != record.configuration_payload
            ):
                raise JobHandlerError(
                    "SYMBOL_TRAINING_INPUT_DRIFT", "Persisted iteration differs from job input."
                )
            catalog = SqlAlchemyTrainingDatasetCatalogRepository(session).get(
                game_id=record.game_id
            )
            if catalog is None:
                raise JobHandlerError(
                    "SYMBOL_TRAINING_GAME_MISSING", "Training game is unavailable."
                )
            config = _training_config(record.configuration_payload)
            dataset_config = _dataset_config(record.configuration_payload.get("dataset"))
            return _IterationSpec(
                iteration_id=record.id,
                game_id=record.game_id,
                game_code=catalog.game_code,
                cohort_id=record.cohort_id,
                cohort_checksum=cohort_checksum,
                configuration=config,
                configuration_fingerprint=fingerprint,
                iteration_number=record.iteration_number,
                dataset_config=dataset_config,
            )

    def build_dataset(self, spec: _IterationSpec, progress: Any) -> Any:
        with self._session_factory() as session:
            service = VerifiedTrainingDatasetService(
                SqlAlchemyVerifiedTrainingCohortRepository(session),
                SqlAlchemyTrainingDatasetCatalogRepository(session),
                artifact_root=self.artifact_root,
            )
            return service.build(
                cohort_id=spec.cohort_id,
                config=spec.dataset_config,
                progress_callback=progress,
            )

    def update(
        self,
        iteration_id: UUID,
        *,
        status: SymbolModelIterationStatus,
        dataset_checksum: str | None = None,
        dataset_path: str | None = None,
        checkpoint_checksum: str | None = None,
        checkpoint_path: str | None = None,
        epoch: int | None = None,
        metrics: Mapping[str, object] | None = None,
        gate_configuration_fingerprint: str | None = None,
        gate_configuration_payload: Mapping[str, object] | None = None,
        candidate_manifest_checksum: str | None = None,
        candidate_manifest_path: str | None = None,
        gate_report_checksum: str | None = None,
        gate_report_path: str | None = None,
        gate_metrics: Mapping[str, object] | None = None,
        rejection_reasons: tuple[str, ...] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        updated_at: datetime,
    ) -> None:
        with self._session_factory() as session, session.begin():
            record = session.scalar(
                select(SymbolModelIterationModel)
                .where(SymbolModelIterationModel.id == iteration_id)
                .with_for_update()
            )
            if record is None:
                raise JobHandlerError(
                    "SYMBOL_TRAINING_ITERATION_MISSING", "Training iteration disappeared."
                )
            record.status = status.value
            if dataset_checksum is not None:
                record.dataset_manifest_checksum_sha256 = dataset_checksum
                record.dataset_manifest_relative_path = dataset_path
            if checkpoint_checksum is not None:
                record.checkpoint_checksum_sha256 = checkpoint_checksum
                record.checkpoint_relative_path = checkpoint_path
            if epoch is not None:
                if epoch < record.last_completed_epoch:
                    raise JobHandlerError(
                        "SYMBOL_TRAINING_EPOCH_REGRESSION", "Training epoch cannot decrease."
                    )
                record.last_completed_epoch = epoch
            if metrics is not None:
                record.partial_metrics = dict(metrics)
            if gate_configuration_fingerprint is not None:
                record.gate_configuration_fingerprint = gate_configuration_fingerprint
                record.gate_configuration_payload = dict(gate_configuration_payload or {})
            if candidate_manifest_checksum is not None:
                record.candidate_manifest_checksum_sha256 = candidate_manifest_checksum
                record.candidate_manifest_relative_path = candidate_manifest_path
            if gate_report_checksum is not None:
                record.gate_report_checksum_sha256 = gate_report_checksum
                record.gate_report_relative_path = gate_report_path
            if gate_metrics is not None:
                record.gate_metrics = dict(gate_metrics)
            if rejection_reasons is not None:
                record.rejection_reasons = list(rejection_reasons)
            record.error_code = error_code
            record.error_message = error_message
            record.updated_at = updated_at

    def fail_job(self, job_id: UUID, *, code: str, message: str, updated_at: datetime) -> None:
        with self._session_factory() as session, session.begin():
            record = session.scalar(
                select(SymbolModelIterationModel)
                .where(SymbolModelIterationModel.job_id == job_id)
                .with_for_update()
            )
            if record is None:
                return
            record.status = SymbolModelIterationStatus.FAILED.value
            record.error_code = code
            record.error_message = message
            record.updated_at = updated_at


class SymbolTrainingJobHandler:
    def __init__(
        self,
        store: SymbolTrainingJobStore,
        *,
        candidate_builder: CandidateBuilder = build_symbol_candidate,
    ) -> None:
        self._store = store
        self._candidate_builder = candidate_builder

    def __call__(self, context: JobExecutionContext, job: Job) -> None:
        try:
            spec = self._store.load_spec(job)
        except Exception as error:
            code = str(getattr(error, "code", "SYMBOL_TRAINING_INPUT_FAILED"))
            message = str(getattr(error, "message", str(error)))
            self._store.fail_job(job.id, code=code, message=message, updated_at=context.now())
            if isinstance(error, JobHandlerError):
                raise
            raise JobHandlerError(code, message) from error
        try:
            self._run(context, spec)
        except Exception as error:
            if context.job.status.value == "cancelled":
                self._store.update(
                    spec.iteration_id,
                    status=SymbolModelIterationStatus.CANCELLED,
                    updated_at=context.now(),
                )
                raise
            code = getattr(error, "code", "SYMBOL_TRAINING_FAILED")
            message = getattr(error, "message", str(error)) or "Symbol training failed."
            self._store.update(
                spec.iteration_id,
                status=SymbolModelIterationStatus.FAILED,
                error_code=str(code),
                error_message=str(message),
                updated_at=context.now(),
            )
            if isinstance(error, JobHandlerError):
                raise
            raise JobHandlerError(str(code), str(message)) from error

    def _run(self, context: JobExecutionContext, spec: _IterationSpec) -> None:
        config_payload = _configuration_payload(spec.configuration)
        config_payload["dataset"] = spec.dataset_config.to_dict()
        input_fingerprint = _input_fingerprint(spec, config_payload)
        model_root = (
            self._store.artifact_root / "data" / "models" / spec.game_code / str(spec.iteration_id)
        )
        _write_immutable_json(
            model_root / "configuration" / f"{spec.configuration_fingerprint}.json",
            {
                "configuration": config_payload,
                "configurationFingerprint": spec.configuration_fingerprint,
                "cohortChecksumSha256": spec.cohort_checksum,
                "runtimeVersion": TRAINING_RUNTIME_VERSION,
            },
        )
        self._store.update(
            spec.iteration_id,
            status=SymbolModelIterationStatus.DATASET_BUILD,
            updated_at=context.now(),
        )
        _dataset_stage_checkpoint(context, input_fingerprint, spec)
        last_heartbeat = monotonic()

        def dataset_progress(current: int, total: int) -> None:
            nonlocal last_heartbeat
            if monotonic() - last_heartbeat >= 20:
                context.heartbeat()
                last_heartbeat = monotonic()

        dataset = self._store.build_dataset(spec, dataset_progress)
        if dataset.cohort_checksum_sha256 != spec.cohort_checksum:
            raise JobHandlerError(
                "SYMBOL_TRAINING_COHORT_DRIFT", "Built dataset uses another cohort."
            )
        data = _prepared_data(self._store.artifact_root, dataset)
        source_family_count = int(getattr(dataset, "source_family_count", 4))
        if source_family_count < 4:
            self._store.update(
                spec.iteration_id,
                status=SymbolModelIterationStatus.REJECTED,
                gate_metrics={
                    "sourceFamilyCount": source_family_count,
                    "trainingPossible": bool(data.train and data.validation),
                },
                rejection_reasons=("SYMBOL_TRAINING_INDEPENDENT_SOURCE_COVERAGE_INSUFFICIENT",),
                updated_at=context.now(),
            )
            return
        total = spec.configuration.epochs + CANDIDATE_STAGE_COUNT
        self._store.update(
            spec.iteration_id,
            status=SymbolModelIterationStatus.TRAINING,
            dataset_checksum=dataset.manifest_checksum_sha256,
            dataset_path=dataset.manifest_relative_path,
            updated_at=context.now(),
        )
        state = _load_resume_state(context.job.checkpoint_payload, model_root, input_fingerprint)
        if state is None:
            _checkpoint_context(
                context,
                input_fingerprint=input_fingerprint,
                dataset_checksum=dataset.manifest_checksum_sha256,
                epoch=0,
                total=total,
                checkpoint_path=None,
                checkpoint_checksum=None,
                metrics={},
            )
        result = _train_epochs(
            context=context,
            store=self._store,
            spec=spec,
            data=data,
            dataset_checksum=dataset.manifest_checksum_sha256,
            input_fingerprint=input_fingerprint,
            model_root=model_root,
            state=state,
        )
        self._store.update(
            spec.iteration_id,
            status=SymbolModelIterationStatus.TRAINED,
            checkpoint_checksum=result[1],
            checkpoint_path=result[0],
            epoch=spec.configuration.epochs,
            metrics=result[2],
            updated_at=context.now(),
        )
        self._store.update(
            spec.iteration_id,
            status=SymbolModelIterationStatus.EVALUATING,
            updated_at=context.now(),
        )
        candidate_steps = {
            "onnx_export": spec.configuration.epochs + 2,
            "calibration": spec.configuration.epochs + 3,
            "evaluation": spec.configuration.epochs + 4,
            "manifest": spec.configuration.epochs + 5,
        }

        def candidate_stage(name: str) -> None:
            current = candidate_steps.get(name)
            if current is None:
                raise JobHandlerError(
                    "SYMBOL_CANDIDATE_STAGE_INVALID", f"Unknown candidate stage: {name}."
                )
            _candidate_stage_checkpoint(
                context,
                input_fingerprint=input_fingerprint,
                dataset_checksum=dataset.manifest_checksum_sha256,
                checkpoint_path=result[0],
                checkpoint_checksum=result[1],
                metrics=result[2],
                training_epoch=spec.configuration.epochs,
                stage=name,
                current=current,
                total=total,
            )

        candidate = self._candidate_builder(
            artifact_root=self._store.artifact_root,
            candidate_root=model_root / "candidate",
            checkpoint_path=self._store.artifact_root / "data" / result[0],
            checkpoint_checksum=result[1],
            data=data,
            training_config=spec.configuration,
            stage=candidate_stage,
            heartbeat=context.heartbeat,
        )
        self._store.update(
            spec.iteration_id,
            status=(
                SymbolModelIterationStatus.CANDIDATE_READY
                if candidate.passed
                else SymbolModelIterationStatus.REJECTED
            ),
            gate_configuration_fingerprint=candidate.configuration_fingerprint,
            gate_configuration_payload=candidate.configuration_payload,
            candidate_manifest_checksum=candidate.manifest_checksum_sha256,
            candidate_manifest_path=candidate.manifest_relative_path,
            gate_report_checksum=candidate.report_checksum_sha256,
            gate_report_path=candidate.report_relative_path,
            gate_metrics=candidate.metrics,
            rejection_reasons=candidate.rejection_reasons,
            updated_at=context.now(),
        )


def _train_epochs(
    *,
    context: JobExecutionContext,
    store: SymbolTrainingJobStore,
    spec: _IterationSpec,
    data: PreparedTrainingData,
    dataset_checksum: str,
    input_fingerprint: str,
    model_root: Path,
    state: Mapping[str, object] | None,
) -> tuple[str, str, dict[str, object]]:
    config = spec.configuration
    set_deterministic_runtime(config.seed)
    model = build_benchmark_model(SPATIAL_VARIANT, len(data.class_codes))
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay
    )
    start_epoch = 1
    history: list[dict[str, object]] = []
    best_key: tuple[float, float, float, int] | None = None
    best_state: Mapping[str, Tensor] | None = None
    best_epoch = 0
    if state is not None:
        model.load_state_dict(cast(Mapping[str, Tensor], state["modelState"]))
        optimizer.load_state_dict(cast(dict[str, Any], state["optimizerState"]))
        start_epoch = int(cast(int, state["epoch"])) + 1
        history = [
            dict(cast(Mapping[str, object], row)) for row in cast(list[object], state["history"])
        ]
        best_state = cast(Mapping[str, Tensor] | None, state.get("bestState"))
        best_epoch = int(cast(int, state.get("bestEpoch", 0)))
        raw_key = state.get("bestKey")
        if isinstance(raw_key, list | tuple) and len(raw_key) == 4:
            best_key = tuple(float(value) for value in raw_key)  # type: ignore[assignment]
    counts = Counter(sample.class_index for sample in data.train)
    if len(counts) != len(data.class_codes) or not data.validation:
        raise JobHandlerError(
            "SYMBOL_TRAINING_SPLIT_INCOMPLETE",
            "Train must contain every class and validation must not be empty.",
        )
    weights = torch.tensor(
        [len(data.train) / counts[index] for index in range(len(data.class_codes))],
        dtype=torch.float32,
    )
    criterion = nn.CrossEntropyLoss(weight=weights / weights.mean())
    dataset = BenchmarkTensorDataset(data.train, config.input_size, augment=False, seed=config.seed)
    for epoch in range(start_epoch, config.epochs + 1):
        dataset.set_epoch(epoch)
        generator = torch.Generator(device="cpu")
        generator.manual_seed(config.seed + epoch)
        loader = torch.utils.data.DataLoader(
            dataset, batch_size=config.batch_size, shuffle=True, generator=generator, num_workers=0
        )
        model.train()
        loss_total = 0.0
        sample_total = 0
        heartbeat_at = monotonic()
        for inputs, targets in loader:
            optimizer.zero_grad(set_to_none=True)
            logits = model(inputs)
            loss = criterion(logits, targets)
            loss.backward()
            optimizer.step()
            loss_total += float(loss.item()) * len(targets)
            sample_total += len(targets)
            if monotonic() - heartbeat_at >= 20:
                context.heartbeat()
                heartbeat_at = monotonic()
        validation = evaluate_benchmark_model(model, data.validation, config, data.class_codes)
        row: dict[str, object] = {
            "epoch": epoch,
            "trainingLoss": round(loss_total / sample_total, 8),
            "validationAccuracy": round(validation.accuracy, 8),
            "validationLoss": round(validation.loss, 8),
            "validationMacroRecall": round(validation.macro_recall, 8),
        }
        history.append(row)
        key = (validation.macro_recall, validation.accuracy, -validation.loss, -epoch)
        if best_key is None or key > best_key:
            best_key, best_epoch, best_state = key, epoch, copy.deepcopy(model.state_dict())
        checkpoint = {
            "schemaVersion": 1,
            "runtimeVersion": TRAINING_RUNTIME_VERSION,
            "inputFingerprint": input_fingerprint,
            "epoch": epoch,
            "modelState": model.state_dict(),
            "optimizerState": optimizer.state_dict(),
            "bestState": best_state,
            "bestEpoch": best_epoch,
            "bestKey": best_key,
            "history": history,
            "classCodes": data.class_codes,
        }
        path, checksum = _write_torch_checkpoint(model_root, epoch, checkpoint)
        metrics = {"bestEpoch": best_epoch, "epochs": list(history), "latest": row}
        store.update(
            spec.iteration_id,
            status=SymbolModelIterationStatus.TRAINING,
            checkpoint_checksum=checksum,
            checkpoint_path=path,
            epoch=epoch,
            metrics=metrics,
            updated_at=context.now(),
        )
        try:
            _checkpoint_context(
                context,
                input_fingerprint=input_fingerprint,
                dataset_checksum=dataset_checksum,
                epoch=epoch,
                total=config.epochs + CANDIDATE_STAGE_COUNT,
                checkpoint_path=path,
                checkpoint_checksum=checksum,
                metrics=metrics,
            )
        except RuntimeError:
            if context.job.status.value == "cancelled":
                store.update(
                    spec.iteration_id,
                    status=SymbolModelIterationStatus.CANCELLED,
                    checkpoint_checksum=checksum,
                    checkpoint_path=path,
                    epoch=epoch,
                    metrics=metrics,
                    updated_at=context.now(),
                )
            raise
    if best_state is None:
        raise JobHandlerError("SYMBOL_TRAINING_NO_CHECKPOINT", "Training produced no checkpoint.")
    final = {
        "schemaVersion": 1,
        "runtimeVersion": TRAINING_RUNTIME_VERSION,
        "inputFingerprint": input_fingerprint,
        "epoch": config.epochs,
        "modelState": best_state,
        "optimizerState": optimizer.state_dict(),
        "bestState": best_state,
        "bestEpoch": best_epoch,
        "bestKey": best_key,
        "history": history,
        "classCodes": data.class_codes,
    }
    path, checksum = _write_torch_checkpoint(model_root, config.epochs, final, prefix="trained")
    metrics = {"bestEpoch": best_epoch, "epochs": history, "latest": history[-1]}
    _checkpoint_context(
        context,
        input_fingerprint=input_fingerprint,
        dataset_checksum=dataset_checksum,
        epoch=config.epochs + 1,
        total=config.epochs + CANDIDATE_STAGE_COUNT,
        checkpoint_path=path,
        checkpoint_checksum=checksum,
        metrics=metrics,
    )
    return path, checksum, metrics


def _prepared_data(root: Path, artifact: Any) -> PreparedTrainingData:
    rows = artifact.manifest.get("samples")
    symbols = artifact.manifest.get("symbols")
    if not isinstance(rows, list) or not isinstance(symbols, list):
        raise JobHandlerError("SYMBOL_TRAINING_DATASET_INVALID", "Dataset manifest is invalid.")
    pairs = sorted(
        (str(row["symbolCode"]), str(row["symbolId"])) for row in symbols if isinstance(row, dict)
    )
    indexes = {code: index for index, (code, _symbol_id) in enumerate(pairs)}
    split: dict[str, list[ClassifierSample]] = {
        "train": [],
        "validation": [],
        "test": [],
        "regression": [],
    }
    base = (
        root / "data" / "training" / artifact.manifest["gameCode"] / artifact.cohort_checksum_sha256
    )
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row["split"])
        if name not in split:
            continue
        code = str(row["symbolCode"])
        path = base.joinpath(*PurePosixPath(str(row["assetRelativePath"])).parts)
        split[name].append(
            ClassifierSample(
                sample_id=str(row["cropSampleId"]),
                asset_path=path,
                asset_checksum=str(row["cropChecksumSha256"]),
                source_image_checksum=str(row["sourceImageChecksumSha256"]),
                symbol_code=code,
                class_index=indexes[code],
            )
        )
    return PreparedTrainingData(
        dataset_sha256=artifact.manifest_checksum_sha256,
        split_sha256=hashlib.sha256(
            json.dumps(artifact.manifest.get("splits"), sort_keys=True).encode()
        ).hexdigest(),
        split_seed=str(artifact.manifest.get("seed")),
        class_codes=tuple(code for code, _ in pairs),
        class_ids=tuple(symbol_id for _, symbol_id in pairs),
        train=tuple(split["train"]),
        validation=tuple(split["validation"]),
        test=tuple(split["test"]),
        regression=tuple(split["regression"]),
    )


def _candidate_stage_checkpoint(
    context: JobExecutionContext,
    *,
    input_fingerprint: str,
    dataset_checksum: str,
    checkpoint_path: str,
    checkpoint_checksum: str,
    metrics: Mapping[str, object],
    training_epoch: int,
    stage: str,
    current: int,
    total: int,
) -> None:
    payload = {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "workflow": TRAINING_WORKFLOW,
        "input_fingerprint": input_fingerprint,
        "dataset_manifest_checksum_sha256": dataset_checksum,
        "last_completed_epoch": training_epoch,
        "checkpoint_relative_path": checkpoint_path,
        "checkpoint_checksum_sha256": checkpoint_checksum,
        "metrics": dict(metrics),
        "candidate_stage": stage,
    }
    context.checkpoint(
        checkpoint_payload=payload,
        stage=f"symbol_training:{stage}",
        current=current,
        total=total,
        success_count=0,
        failure_count=0,
        review_count=0,
    )


def _checkpoint_context(
    context: JobExecutionContext,
    *,
    input_fingerprint: str,
    dataset_checksum: str,
    epoch: int,
    total: int,
    checkpoint_path: str | None,
    checkpoint_checksum: str | None,
    metrics: Mapping[str, object],
) -> None:
    payload: dict[str, object] = {
        "schema_version": 1,
        "workflow": TRAINING_WORKFLOW,
        "input_fingerprint": input_fingerprint,
        "dataset_manifest_checksum_sha256": dataset_checksum,
        "last_completed_epoch": epoch,
        "metrics": dict(metrics),
    }
    if checkpoint_path is not None:
        payload.update(
            {
                "checkpoint_relative_path": checkpoint_path,
                "checkpoint_checksum_sha256": checkpoint_checksum,
            }
        )
    context.checkpoint(
        checkpoint_payload=payload,
        stage="symbol_training:training",
        current=epoch,
        total=total,
        success_count=0,
        failure_count=0,
        review_count=0,
    )


def _dataset_stage_checkpoint(
    context: JobExecutionContext,
    input_fingerprint: str,
    spec: _IterationSpec,
) -> None:
    payload = context.job.checkpoint_payload or {
        "schema_version": 1,
        "workflow": TRAINING_WORKFLOW,
        "input_fingerprint": input_fingerprint,
        "cohort_checksum_sha256": spec.cohort_checksum,
        "last_completed_epoch": 0,
        "metrics": {},
    }
    context.checkpoint(
        checkpoint_payload=dict(payload),
        stage="symbol_training:dataset_build",
        current=context.job.progress_current,
        total=context.job.progress_total or spec.configuration.epochs + CANDIDATE_STAGE_COUNT,
        success_count=context.job.success_count,
        failure_count=context.job.failure_count,
        review_count=context.job.review_count,
    )


def _load_resume_state(
    payload: Mapping[str, object] | None, model_root: Path, input_fingerprint: str
) -> Mapping[str, object] | None:
    if not payload or payload.get("workflow") != TRAINING_WORKFLOW:
        return None
    if payload.get("input_fingerprint") != input_fingerprint:
        raise JobHandlerError(
            "SYMBOL_TRAINING_RETRY_INPUT_DRIFT", "Retry input fingerprint changed."
        )
    relative = payload.get("checkpoint_relative_path")
    expected = payload.get("checkpoint_checksum_sha256")
    if not isinstance(relative, str) or not isinstance(expected, str):
        return None
    path = model_root.parents[2].joinpath(*PurePosixPath(relative).parts)
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != expected:
        raise JobHandlerError("SYMBOL_TRAINING_CHECKPOINT_DRIFT", "Checkpoint checksum changed.")
    value = torch.load(path, map_location="cpu", weights_only=False)
    if not isinstance(value, Mapping) or value.get("inputFingerprint") != input_fingerprint:
        raise JobHandlerError("SYMBOL_TRAINING_CHECKPOINT_INVALID", "Checkpoint input is invalid.")
    return cast(Mapping[str, object], value)


def _write_torch_checkpoint(
    root: Path, epoch: int, value: Mapping[str, object], *, prefix: str = "epoch"
) -> tuple[str, str]:
    directory = root / "checkpoints"
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=directory, prefix=".tmp-", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        with temporary.open("wb") as writer:
            torch.save(dict(value), writer)
            writer.flush()
            os.fsync(writer.fileno())
        content = temporary.read_bytes()
        checksum = hashlib.sha256(content).hexdigest()
        destination = directory / f"{prefix}-{epoch:04d}-{checksum}.pt"
        if destination.exists() and destination.read_bytes() != content:
            raise JobHandlerError(
                "SYMBOL_TRAINING_ARTIFACT_CONFLICT", "Immutable checkpoint conflicts."
            )
        if not destination.exists():
            os.replace(temporary, destination)
        else:
            temporary.unlink(missing_ok=True)
        return destination.relative_to(root.parents[2]).as_posix(), checksum
    finally:
        temporary.unlink(missing_ok=True)


def _write_immutable_json(path: Path, value: object) -> None:
    content = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise JobHandlerError("SYMBOL_TRAINING_CONFIG_DRIFT", "Configuration artifact changed.")
        return
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".tmp-", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _configuration_payload(config: TrainingConfig) -> dict[str, object]:
    return {
        "architectureVersion": "spatial-symbol-cnn-v1",
        "variant": "spatial",
        "seed": config.seed,
        "epochs": config.epochs,
        "batchSize": config.batch_size,
        "learningRate": config.learning_rate,
        "weightDecay": config.weight_decay,
        "inputSize": config.input_size,
    }


def _training_config(value: Mapping[str, object]) -> TrainingConfig:
    try:
        config = TrainingConfig(
            seed=_integer(value["seed"]),
            epochs=_integer(value["epochs"]),
            batch_size=_integer(value["batchSize"]),
            learning_rate=_number(value["learningRate"]),
            weight_decay=_number(value["weightDecay"]),
            input_size=_integer(value["inputSize"]),
        )
        config.validate()
        return config
    except (KeyError, TypeError, ValueError, SymbolClassifierError) as error:
        raise JobHandlerError(
            "SYMBOL_TRAINING_CONFIG_INVALID", "Persisted training config is invalid."
        ) from error


def _dataset_config(value: object) -> TrainingDatasetConfig:
    if value is None:
        return TrainingDatasetConfig()
    if not isinstance(value, Mapping):
        raise JobHandlerError(
            "SYMBOL_TRAINING_DATASET_CONFIG_INVALID", "Dataset config is invalid."
        )
    try:
        ratios = value.get("splitRatiosBasisPoints", {})
        if not isinstance(ratios, Mapping):
            raise TypeError("split ratios")
        raw_assignments = value.get("sourceAssignments", {})
        if not isinstance(raw_assignments, Mapping):
            raise TypeError("source assignments")
        assignments = tuple(
            sorted(
                (str(source), str(split))
                for source, split in raw_assignments.items()
                if str(split) in {"train", "validation", "test", "regression"}
            )
        )
        config = TrainingDatasetConfig(
            seed=str(value["seed"]),
            split_policy_version=str(value["splitPolicyVersion"]),
            transformation_version=str(value["transformationVersion"]),
            train_basis_points=int(ratios["train"]),
            validation_basis_points=int(ratios["validation"]),
            test_basis_points=int(ratios["test"]),
            regression_basis_points=int(ratios["regression"]),
            source_assignments=assignments,  # type: ignore[arg-type]
        )
        config.split_ratios()
        return config
    except (KeyError, TypeError, ValueError) as error:
        raise JobHandlerError(
            "SYMBOL_TRAINING_DATASET_CONFIG_INVALID", "Dataset config is invalid."
        ) from error


def _integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise TypeError("Expected an integer value.")
    return int(value)


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise TypeError("Expected a number value.")
    return float(value)


def _input_fingerprint(spec: _IterationSpec, config: Mapping[str, object]) -> str:
    content = json.dumps(
        {
            "cohortChecksumSha256": spec.cohort_checksum,
            "configuration": config,
            "runtimeVersion": TRAINING_RUNTIME_VERSION,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(content).hexdigest()


def _configuration_fingerprint(value: Mapping[str, object]) -> str:
    content = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(content).hexdigest()


def _uuid(value: object, label: str) -> UUID:
    try:
        return UUID(str(value))
    except (ValueError, TypeError) as error:
        raise JobHandlerError("SYMBOL_TRAINING_JOB_INVALID", f"{label} is invalid.") from error


def _sha(value: object, label: str) -> str:
    text = str(value)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise JobHandlerError("SYMBOL_TRAINING_JOB_INVALID", f"{label} is invalid.")
    return text


__all__ = ["SymbolTrainingJobHandler", "SymbolTrainingJobStore"]
