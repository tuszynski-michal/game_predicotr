"""Transactional persistence for symbol-model iterations and their jobs."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from game_predictor_worker.symbols.training_dataset import (
    CLASS_STRATIFIED_SPLIT_POLICY_VERSION,
    CLASS_STRATIFIED_SPLIT_SEED,
    SPLIT_ORDER,
    SplitName,
    TrainingDatasetConfig,
    build_class_stratified_source_assignments,
)
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from game_predictor_api.application.symbol_model_iterations import SymbolModelIterationRepository
from game_predictor_api.domain.jobs import (
    Job,
    JobConflictError,
    JobNotFoundError,
    JobType,
    create_job,
)
from game_predictor_api.domain.symbol_model_iterations import (
    SymbolModelIteration,
    SymbolModelIterationStatus,
    SymbolTrainingConfiguration,
)
from game_predictor_api.storage.job_repository import job_from_record, job_record_from_domain
from game_predictor_api.storage.models import (
    GameModel,
    JobModel,
    SourceImageModel,
    SymbolModelIterationModel,
    VerifiedTrainingCohortCellModel,
    VerifiedTrainingCohortItemModel,
    VerifiedTrainingCohortModel,
)

_ACTIVE = (
    SymbolModelIterationStatus.CREATED.value,
    SymbolModelIterationStatus.DATASET_BUILD.value,
    SymbolModelIterationStatus.TRAINING.value,
    SymbolModelIterationStatus.TRAINED.value,
    SymbolModelIterationStatus.EVALUATING.value,
)


def _cohort_source_checksums(session: Session, cohort_id: UUID) -> tuple[str, ...]:
    """Return source families for both legacy-board and individual-cell cohorts."""

    legacy_checksums = session.scalars(
        select(VerifiedTrainingCohortItemModel.source_checksum_sha256).where(
            VerifiedTrainingCohortItemModel.cohort_id == cohort_id
        )
    ).all()
    cell_checksums = session.scalars(
        select(SourceImageModel.checksum_sha256)
        .join(
            VerifiedTrainingCohortCellModel,
            VerifiedTrainingCohortCellModel.source_image_id == SourceImageModel.id,
        )
        .where(VerifiedTrainingCohortCellModel.cohort_id == cohort_id)
    ).all()
    return tuple(sorted(set(legacy_checksums).union(cell_checksums)))


def _cohort_source_symbol_counts(session: Session, cohort_id: UUID) -> dict[str, dict[str, int]]:
    """Return immutable symbol incidence for each source family in a cohort."""

    counts: defaultdict[str, Counter[str]] = defaultdict(Counter)
    legacy_rows = session.execute(
        select(
            VerifiedTrainingCohortItemModel.source_checksum_sha256,
            VerifiedTrainingCohortItemModel.board_manifest,
        ).where(VerifiedTrainingCohortItemModel.cohort_id == cohort_id)
    ).all()
    for source_checksum, raw_manifest in legacy_rows:
        if not isinstance(raw_manifest, Mapping):
            continue
        raw_cells = raw_manifest.get("cells")
        if not isinstance(raw_cells, list):
            continue
        for raw_cell in raw_cells:
            if not isinstance(raw_cell, Mapping):
                continue
            symbol_code = raw_cell.get("symbolCode")
            if isinstance(symbol_code, str) and symbol_code:
                counts[str(source_checksum)][symbol_code] += 1
    cell_rows = session.execute(
        select(
            SourceImageModel.checksum_sha256,
            VerifiedTrainingCohortCellModel.symbol_code,
        )
        .join(
            VerifiedTrainingCohortCellModel,
            VerifiedTrainingCohortCellModel.source_image_id == SourceImageModel.id,
        )
        .where(VerifiedTrainingCohortCellModel.cohort_id == cohort_id)
    ).all()
    for source_checksum, symbol_code in cell_rows:
        counts[str(source_checksum)][str(symbol_code)] += 1
    return {
        source: dict(sorted(symbol_counts.items()))
        for source, symbol_counts in sorted(counts.items())
    }


class SqlAlchemySymbolModelIterationRepository(SymbolModelIterationRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_training(
        self,
        *,
        game_id: UUID,
        cohort_id: UUID,
        idempotency_key: UUID,
        configuration: SymbolTrainingConfiguration,
    ) -> tuple[SymbolModelIteration, Job, bool]:
        if self._session.get(GameModel, game_id) is None:
            raise JobNotFoundError("GAME_NOT_FOUND", "Game does not exist.")
        cohort = self._session.get(VerifiedTrainingCohortModel, cohort_id)
        if cohort is None:
            raise JobNotFoundError("TRAINING_COHORT_NOT_FOUND", "Training cohort does not exist.")
        if cohort.game_id != game_id:
            raise JobConflictError(
                "TRAINING_COHORT_GAME_MISMATCH", "Cohort belongs to another game."
            )
        model_payload = configuration.to_payload()
        source_symbol_counts = _cohort_source_symbol_counts(self._session, cohort_id)
        prior_assignments: dict[str, SplitName] = {}
        prior_rows = self._session.scalars(
            select(SymbolModelIterationModel)
            .where(SymbolModelIterationModel.game_id == game_id)
            .order_by(SymbolModelIterationModel.iteration_number.desc())
        ).all()
        for prior in prior_rows:
            raw_dataset = prior.configuration_payload.get("dataset")
            if isinstance(raw_dataset, dict):
                if raw_dataset.get("splitPolicyVersion") != CLASS_STRATIFIED_SPLIT_POLICY_VERSION:
                    continue
                raw = raw_dataset.get("sourceAssignments")
                if isinstance(raw, dict):
                    prior_assignments = {
                        str(source): cast(SplitName, split_name)
                        for source, split in raw.items()
                        if (split_name := str(split)) in SPLIT_ORDER
                    }
                    break
        assignments = build_class_stratified_source_assignments(
            source_symbol_counts,
            existing=prior_assignments,
        )
        dataset_payload = TrainingDatasetConfig(
            seed=CLASS_STRATIFIED_SPLIT_SEED,
            split_policy_version=CLASS_STRATIFIED_SPLIT_POLICY_VERSION,
            source_assignments=assignments,
        ).to_dict()
        payload = {**model_payload, "dataset": dataset_payload}
        configuration_fingerprint = _payload_checksum(payload)
        prior_with_configuration = self._session.scalar(
            select(SymbolModelIterationModel).where(
                SymbolModelIterationModel.game_id == game_id,
                SymbolModelIterationModel.cohort_id == cohort_id,
                SymbolModelIterationModel.configuration_fingerprint == configuration_fingerprint,
            )
        )
        if prior_with_configuration is not None and prior_with_configuration.status in {
            SymbolModelIterationStatus.FAILED.value,
            SymbolModelIterationStatus.CANCELLED.value,
        }:
            # A failed terminal attempt must remain auditable, but must not make
            # the owner re-use its broken job when explicitly starting again.
            payload = {**payload, "retryNonce": str(idempotency_key)}
            configuration_fingerprint = _payload_checksum(payload)
        job = create_job(
            JobType.SYMBOL_TRAINING,
            game_id=game_id,
            input_payload={
                "schema_version": 2,
                "cohort_id": str(cohort_id),
                "cohort_checksum_sha256": cohort.manifest_checksum_sha256,
                "configuration": payload,
                "configuration_fingerprint": configuration_fingerprint,
                "idempotency_key": str(idempotency_key),
            },
        )
        prior_job_record = self._session.scalar(
            select(JobModel).where(JobModel.input_key == job.input_key)
        )
        if prior_job_record is not None:
            prior_iteration = self._session.scalar(
                select(SymbolModelIterationModel).where(
                    SymbolModelIterationModel.job_id == prior_job_record.id
                )
            )
            if prior_iteration is None:
                raise JobConflictError(
                    "SYMBOL_TRAINING_PERSISTENCE_CONFLICT", "Training job has no iteration."
                )
            return _to_domain(prior_iteration), job_from_record(prior_job_record), False
        active = self._session.scalar(
            select(SymbolModelIterationModel.id)
            .where(
                SymbolModelIterationModel.game_id == game_id,
                SymbolModelIterationModel.status.in_(_ACTIVE),
            )
            .limit(1)
        )
        if active is not None:
            raise JobConflictError(
                "SYMBOL_TRAINING_ALREADY_ACTIVE",
                "A heavy symbol training job is already active for this game.",
            )
        number = (
            int(
                self._session.scalar(
                    select(
                        func.coalesce(func.max(SymbolModelIterationModel.iteration_number), 0)
                    ).where(SymbolModelIterationModel.game_id == game_id)
                )
                or 0
            )
            + 1
        )
        now = datetime.now(UTC)
        record = SymbolModelIterationModel(
            id=uuid4(),
            game_id=game_id,
            cohort_id=cohort_id,
            job_id=job.id,
            iteration_number=number,
            status=SymbolModelIterationStatus.CREATED.value,
            configuration_fingerprint=configuration_fingerprint,
            configuration_payload=payload,
            last_completed_epoch=0,
            partial_metrics={},
            created_at=now,
            updated_at=now,
        )
        self._session.add(job_record_from_domain(job))
        self._session.add(record)
        try:
            self._session.flush()
        except IntegrityError as error:
            raise JobConflictError(
                "SYMBOL_TRAINING_PERSISTENCE_CONFLICT",
                "The training command conflicts with persisted state; retry it.",
            ) from error
        return _to_domain(record), job, True

    def get(self, *, game_id: UUID, iteration_id: UUID) -> SymbolModelIteration | None:
        record = self._session.scalar(
            select(SymbolModelIterationModel).where(
                SymbolModelIterationModel.id == iteration_id,
                SymbolModelIterationModel.game_id == game_id,
            )
        )
        return None if record is None else _to_domain(record)

    def list(self, *, game_id: UUID, limit: int) -> tuple[SymbolModelIteration, ...]:
        records = self._session.scalars(
            select(SymbolModelIterationModel)
            .where(SymbolModelIterationModel.game_id == game_id)
            .order_by(SymbolModelIterationModel.iteration_number.desc())
            .limit(limit)
        ).all()
        return tuple(_to_domain(record) for record in records)


def _to_domain(record: SymbolModelIterationModel) -> SymbolModelIteration:
    return SymbolModelIteration(
        id=record.id,
        game_id=record.game_id,
        cohort_id=record.cohort_id,
        job_id=record.job_id,
        iteration_number=record.iteration_number,
        status=SymbolModelIterationStatus(record.status),
        configuration_fingerprint=record.configuration_fingerprint,
        configuration_payload=dict(record.configuration_payload),
        dataset_manifest_checksum_sha256=record.dataset_manifest_checksum_sha256,
        dataset_manifest_relative_path=record.dataset_manifest_relative_path,
        checkpoint_checksum_sha256=record.checkpoint_checksum_sha256,
        checkpoint_relative_path=record.checkpoint_relative_path,
        gate_configuration_fingerprint=record.gate_configuration_fingerprint,
        gate_configuration_payload=(
            None
            if record.gate_configuration_payload is None
            else dict(record.gate_configuration_payload)
        ),
        candidate_manifest_checksum_sha256=record.candidate_manifest_checksum_sha256,
        candidate_manifest_relative_path=record.candidate_manifest_relative_path,
        gate_report_checksum_sha256=record.gate_report_checksum_sha256,
        gate_report_relative_path=record.gate_report_relative_path,
        gate_metrics=dict(record.gate_metrics),
        rejection_reasons=tuple(record.rejection_reasons),
        last_completed_epoch=record.last_completed_epoch,
        partial_metrics=dict(record.partial_metrics),
        error_code=record.error_code,
        error_message=record.error_message,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


__all__ = ["SqlAlchemySymbolModelIterationRepository"]


def _payload_checksum(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
