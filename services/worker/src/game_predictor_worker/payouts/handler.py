"""Resumable versioned payout job handler."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from uuid import UUID

from game_predictor_api.domain.datasets import DatasetVersionStatus
from game_predictor_api.domain.jobs import Job, JobType
from game_predictor_api.domain.rules import RulesVersionStatus

from game_predictor_worker.domain.contracts import PayoutEvaluation
from game_predictor_worker.domain.errors import DomainValidationError
from game_predictor_worker.domain.payout import evaluate_payout, evaluate_payout_v2
from game_predictor_worker.jobs.runtime import (
    JobExecutionContext,
    JobHandlerError,
)
from game_predictor_worker.payouts.contracts import (
    AuditedPayout,
    CalculatedLayoutPayout,
    PayoutAuditWriter,
    PayoutLayout,
    PayoutSource,
    PayoutStore,
)

PAYOUT_ALGORITHM_VERSION = "payout-v3-unknown-prefix-stop"
LEGACY_PAYOUT_ALGORITHM_VERSION = "payout-v2"
SUPPORTED_PAYOUT_ALGORITHM_VERSIONS = frozenset(
    {LEGACY_PAYOUT_ALGORITHM_VERSION, PAYOUT_ALGORITHM_VERSION}
)
DEFAULT_PAYOUT_BATCH_SIZE = 1000


class PayoutBatchHandler:
    def __init__(
        self,
        store: PayoutStore,
        audit_writer: PayoutAuditWriter,
        *,
        batch_size: int = DEFAULT_PAYOUT_BATCH_SIZE,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive.")
        self._store = store
        self._audit_writer = audit_writer
        self._batch_size = batch_size
        self._clock = clock or (lambda: datetime.now(UTC))

    def __call__(self, context: JobExecutionContext, job: Job) -> None:
        dataset_id, rules_id, algorithm_version = _parse_job(job)
        source = self._store.load_source(dataset_id, rules_id)
        if source is None:
            raise JobHandlerError(
                "PAYOUT_SOURCE_NOT_FOUND",
                "The payout dataset or rules version does not exist.",
            )
        _validate_source(source, job, algorithm_version=algorithm_version)
        cursor, processed_count = _resume_position(
            job,
            source,
            algorithm_version=algorithm_version,
        )

        while cursor < source.layout_count:
            layouts = tuple(
                self._store.list_layout_batch(
                    source.dataset_version_id,
                    after_sequence_number=cursor,
                    limit=self._batch_size,
                )
            )
            _validate_layout_batch(
                layouts,
                after_sequence_number=cursor,
                layout_count=source.layout_count,
            )
            audited = tuple(
                AuditedPayout(
                    layout=layout,
                    evaluation=_evaluate(source, layout, algorithm_version=algorithm_version),
                )
                for layout in layouts
            )
            audit_path = self._audit_writer.write_batch(
                source,
                algorithm_version=algorithm_version,
                payouts=audited,
            )
            calculated_at = self._clock()
            self._store.upsert_payouts(
                tuple(
                    CalculatedLayoutPayout(
                        dataset_version_id=source.dataset_version_id,
                        rules_version_id=source.rules_version_id,
                        sequence_number=item.layout.sequence_number,
                        algorithm_version=algorithm_version,
                        total_payout=item.evaluation.total_payout,
                        audit_path=audit_path,
                        calculated_at=calculated_at,
                    )
                    for item in audited
                )
            )
            cursor = layouts[-1].sequence_number
            processed_count += len(layouts)
            context.checkpoint(
                checkpoint_payload={
                    "schema_version": 1,
                    "workflow": "payout",
                    "dataset_version_id": str(source.dataset_version_id),
                    "rules_version_id": str(source.rules_version_id),
                    "algorithm_version": algorithm_version,
                    "last_sequence_number": cursor,
                    "processed_count": processed_count,
                },
                stage="calculating_payouts",
                current=processed_count,
                total=source.layout_count,
                success_count=processed_count,
                failure_count=0,
                review_count=0,
            )


def _parse_job(job: Job) -> tuple[UUID, UUID, str]:
    if job.job_type is not JobType.PAYOUT:
        raise JobHandlerError(
            "INVALID_PAYOUT_JOB_TYPE",
            "The payout handler only accepts payout jobs.",
        )
    payload = job.input_payload
    if payload.get("schema_version") != 1:
        raise JobHandlerError(
            "UNSUPPORTED_PAYOUT_PAYLOAD_VERSION",
            "The payout job requires input payload schema version 1.",
        )
    try:
        dataset_id = UUID(str(payload["dataset_version_id"]))
        rules_id = UUID(str(payload["rules_version_id"]))
    except (KeyError, TypeError, ValueError) as error:
        raise JobHandlerError(
            "INVALID_PAYOUT_PAYLOAD",
            "The payout job requires valid dataset and rules version IDs.",
        ) from error
    algorithm_version = payload.get("algorithm_version")
    if (
        not isinstance(algorithm_version, str)
        or algorithm_version not in SUPPORTED_PAYOUT_ALGORITHM_VERSIONS
    ):
        raise JobHandlerError(
            "UNSUPPORTED_PAYOUT_ALGORITHM",
            "The requested payout algorithm is not supported.",
        )
    return dataset_id, rules_id, algorithm_version


def _validate_source(
    source: PayoutSource,
    job: Job,
    *,
    algorithm_version: str,
) -> None:
    if job.game_id is None or source.game_id != job.game_id or source.rules_game_id != job.game_id:
        raise JobHandlerError(
            "PAYOUT_GAME_MISMATCH",
            "The payout dataset, rules and job must belong to the same game.",
        )
    if source.dataset_status is not DatasetVersionStatus.PUBLISHED:
        raise JobHandlerError(
            "PAYOUT_DATASET_NOT_PUBLISHED",
            "Payout precomputation requires a published dataset.",
        )
    if source.rules_status is not RulesVersionStatus.PUBLISHED:
        raise JobHandlerError(
            "PAYOUT_RULES_NOT_PUBLISHED",
            "Payout precomputation requires published rules.",
        )
    if source.dataset_rows != source.game.rows or source.dataset_columns != source.game.columns:
        raise JobHandlerError(
            "PAYOUT_DIMENSIONS_MISMATCH",
            "The payout dataset and rules dimensions must match.",
        )
    if algorithm_version not in SUPPORTED_PAYOUT_ALGORITHM_VERSIONS:
        raise JobHandlerError(
            "UNSUPPORTED_PAYOUT_ALGORITHM",
            "The requested payout algorithm is not supported.",
        )
    if source.layout_count <= 0:
        raise JobHandlerError(
            "PAYOUT_DATASET_EMPTY",
            "Payout precomputation requires at least one layout.",
        )


def _resume_position(
    job: Job,
    source: PayoutSource,
    *,
    algorithm_version: str,
) -> tuple[int, int]:
    checkpoint = job.checkpoint_payload
    if checkpoint is None:
        return 0, 0
    expected = {
        "schema_version": 1,
        "workflow": "payout",
        "dataset_version_id": str(source.dataset_version_id),
        "rules_version_id": str(source.rules_version_id),
        "algorithm_version": algorithm_version,
    }
    if any(checkpoint.get(key) != value for key, value in expected.items()):
        raise JobHandlerError(
            "PAYOUT_CHECKPOINT_MISMATCH",
            "The payout checkpoint does not match the job input.",
        )
    cursor = checkpoint.get("last_sequence_number")
    processed = checkpoint.get("processed_count")
    if (
        isinstance(cursor, bool)
        or not isinstance(cursor, int)
        or isinstance(processed, bool)
        or not isinstance(processed, int)
        or cursor < 0
        or processed < 0
        or cursor != processed
        or cursor > source.layout_count
    ):
        raise JobHandlerError(
            "INVALID_PAYOUT_CHECKPOINT",
            "The payout checkpoint contains an invalid sequence cursor.",
        )
    return cursor, processed


def _validate_layout_batch(
    layouts: Sequence[PayoutLayout],
    *,
    after_sequence_number: int,
    layout_count: int,
) -> None:
    if not layouts:
        raise JobHandlerError(
            "PAYOUT_SEQUENCE_GAP",
            "The published dataset ended before its declared layout count.",
        )
    expected = after_sequence_number + 1
    for layout in layouts:
        if layout.sequence_number != expected:
            raise JobHandlerError(
                "PAYOUT_SEQUENCE_GAP",
                "The published dataset sequence is not continuous.",
            )
        if layout.sequence_number > layout_count:
            raise JobHandlerError(
                "PAYOUT_SEQUENCE_OUT_OF_RANGE",
                "The published dataset contains a sequence outside its declared range.",
            )
        expected += 1


def _evaluate(
    source: PayoutSource,
    layout: PayoutLayout,
    *,
    algorithm_version: str,
) -> PayoutEvaluation:
    try:
        evaluator = (
            evaluate_payout_v2
            if algorithm_version == LEGACY_PAYOUT_ALGORITHM_VERSION
            else evaluate_payout
        )
        return evaluator(
            source.game,
            layout.cells,
            source.paylines,
            source.payout_symbols,
            source.payout_rules,
        )
    except DomainValidationError as error:
        raise JobHandlerError(
            "PAYOUT_CONFIGURATION_INVALID",
            f"Payout configuration is invalid ({error.code}).",
        ) from error
