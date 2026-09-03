"""Application service for durable global semi-automatic selection runs."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, cast
from uuid import UUID

from game_predictor_worker.semi_automatic_selection.engine import (
    grouping_policy_fingerprint,
)
from game_predictor_worker.semi_automatic_selection.five_anchor_range_runtime import (
    FIVE_ANCHOR_RECOGNIZER_CONTRACT_FINGERPRINT_V6,
)
from game_predictor_worker.semi_automatic_selection.middle_row_grouping import (
    five_anchor_grouping_policy_fingerprint,
)
from game_predictor_worker.semi_automatic_selection.range_only_ocr import (
    RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT,
    RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V2,
)

from game_predictor_api.application.image_imports import (
    BrowserImageSelectionService,
    ImageSelectionPurpose,
)
from game_predictor_api.domain.jobs import JobStatus, request_job_cancellation, requeue_job
from game_predictor_api.domain.semi_automatic_image_selections import (
    SEMI_AUTOMATIC_SELECTION_CONTRACT_VERSION,
    SEMI_AUTOMATIC_SELECTION_FULL_RANGE_SIZE,
    SEMI_AUTOMATIC_SELECTION_RANGE_CONVENTION,
    FilenameRangeVerificationReview,
    FilenameRangeVerificationReviewDecision,
    FilenameVerificationHistoryDeletion,
    SemiAutomaticSelectionConflictError,
    SemiAutomaticSelectionDirection,
    SemiAutomaticSelectionError,
    SemiAutomaticSelectionNotFoundError,
    SemiAutomaticSelectionRange,
    SemiAutomaticSelectionRun,
    SemiAutomaticSelectionRunStatus,
    SemiAutomaticSelectionSourceManifest,
    SemiAutomaticSelectionWorkflowMode,
    acknowledge_manual_output,
    acknowledge_output,
    apply_range_status_transition,
    cancel_run,
    classify_filename_range_verification,
    create_semi_automatic_selection_run,
    pause_run,
    resume_run,
    run_identity_key,
)

SEMI_AUTOMATIC_RECOGNIZER_FINGERPRINT = RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT
SEMI_AUTOMATIC_GROUPING_CONTRACT_FINGERPRINT = grouping_policy_fingerprint()
SEMI_AUTOMATIC_FILENAME_VERIFICATION_MODE = "filename_verification"
SEMI_AUTOMATIC_SELECTION_MODE = "selection"
SEMI_AUTOMATIC_DEFAULT_RECOGNIZER_VARIANT = "default_v3"
SEMI_AUTOMATIC_FIVE_ANCHOR_RECOGNIZER_VARIANT = "five_anchor_v6"
_LEGACY_FILENAME_VERIFICATION_RECOGNIZER_FINGERPRINTS = frozenset(
    {RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V2}
)
_SELECTION_RECOGNIZER_VARIANTS: dict[str, dict[str, object]] = {
    SEMI_AUTOMATIC_DEFAULT_RECOGNIZER_VARIANT: {
        "default": True,
        "experimental": False,
        "fingerprint": SEMI_AUTOMATIC_RECOGNIZER_FINGERPRINT,
        "label": "OCR zakresu v3 (domyślny)",
    },
    SEMI_AUTOMATIC_FIVE_ANCHOR_RECOGNIZER_VARIANT: {
        "default": False,
        "experimental": True,
        "fingerprint": FIVE_ANCHOR_RECOGNIZER_CONTRACT_FINGERPRINT_V6,
        "label": "OCR pięciu anchorów v6 (eksperymentalny)",
    },
}


def workflow_mode_for_recognizer_fingerprint(
    recognizer_fingerprint: str | None,
) -> SemiAutomaticSelectionWorkflowMode:
    """Classify version-one payloads without inferring from mutable job state."""

    if recognizer_fingerprint in _LEGACY_FILENAME_VERIFICATION_RECOGNIZER_FINGERPRINTS:
        return SemiAutomaticSelectionWorkflowMode.FILENAME_VERIFICATION
    return SemiAutomaticSelectionWorkflowMode.SELECTION


class SemiAutomaticSelectionRepository(Protocol):
    def find_by_identity(self, identity_key: str) -> SemiAutomaticSelectionRun | None: ...

    def add(
        self,
        run: SemiAutomaticSelectionRun,
        ranges: Sequence[SemiAutomaticSelectionRange],
        *,
        identity_key: str,
    ) -> SemiAutomaticSelectionRun: ...

    def get(
        self,
        run_id: UUID,
        *,
        for_update: bool = False,
    ) -> SemiAutomaticSelectionRun | None: ...

    def save(self, run: SemiAutomaticSelectionRun) -> SemiAutomaticSelectionRun: ...

    def list_runs(
        self,
        *,
        workflow_mode: SemiAutomaticSelectionWorkflowMode,
        offset: int,
        limit: int,
    ) -> tuple[tuple[SemiAutomaticSelectionRun, ...], int | None]: ...

    def get_filename_verification_reviews(
        self,
        run_id: UUID,
        source_indexes: Sequence[int],
    ) -> dict[int, FilenameRangeVerificationReview]: ...

    def save_filename_verification_review(
        self,
        review: FilenameRangeVerificationReview,
        *,
        expected_revision: int,
    ) -> FilenameRangeVerificationReview: ...

    def delete_completed_filename_verification_history(
        self,
        *,
        run_id: UUID,
        job_id: UUID,
    ) -> FilenameVerificationHistoryDeletion: ...

    def list_ranges(
        self,
        run_id: UUID,
        *,
        after_expected_index: int | None,
        limit: int,
    ) -> tuple[SemiAutomaticSelectionRange, ...]: ...

    def get_range_for_update(
        self,
        run_id: UUID,
        expected_index: int,
    ) -> SemiAutomaticSelectionRange | None: ...

    def save_range(self, item: SemiAutomaticSelectionRange) -> SemiAutomaticSelectionRange: ...

    def save_run_and_range(
        self,
        run: SemiAutomaticSelectionRun,
        item: SemiAutomaticSelectionRange,
    ) -> tuple[SemiAutomaticSelectionRun, SemiAutomaticSelectionRange]: ...


class SemiAutomaticImageSelectionService:
    def __init__(
        self,
        repository: SemiAutomaticSelectionRepository,
        staging: BrowserImageSelectionService,
        *,
        enabled: bool,
        artifact_root: Path | None = None,
    ) -> None:
        self._repository = repository
        self._staging = staging
        self._enabled = enabled
        self._artifact_root = None if artifact_root is None else artifact_root.resolve()

    def capabilities(self) -> dict[str, object]:
        return {
            "enabled": self._enabled,
            "filenameVerificationEnabled": True,
            "contractVersion": SEMI_AUTOMATIC_SELECTION_CONTRACT_VERSION,
            "rangeConvention": SEMI_AUTOMATIC_SELECTION_RANGE_CONVENTION,
            "fullRangeSize": SEMI_AUTOMATIC_SELECTION_FULL_RANGE_SIZE,
            "minimumSequenceNumber": 1,
            "maximumBoardsPerRange": SEMI_AUTOMATIC_SELECTION_FULL_RANGE_SIZE,
            "stagingPurpose": ImageSelectionPurpose.SEMI_AUTOMATIC_SELECTION.value,
            "recognizerFingerprint": SEMI_AUTOMATIC_RECOGNIZER_FINGERPRINT,
            "selectionRecognizerVariants": [
                {"id": variant, **values}
                for variant, values in _SELECTION_RECOGNIZER_VARIANTS.items()
            ],
            "filenameVerificationRecognizerFingerprint": (
                RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V2
            ),
            "groupingPolicyFingerprint": SEMI_AUTOMATIC_GROUPING_CONTRACT_FINGERPRINT,
        }

    def create(
        self,
        *,
        upload_id: UUID,
        first_sequence_number: int,
        last_sequence_number: int,
        direction: SemiAutomaticSelectionDirection,
        mode: str = SEMI_AUTOMATIC_SELECTION_MODE,
        recognizer_variant: str = SEMI_AUTOMATIC_DEFAULT_RECOGNIZER_VARIANT,
    ) -> tuple[SemiAutomaticSelectionRun, bool]:
        if mode == SEMI_AUTOMATIC_SELECTION_MODE and not self._enabled:
            raise SemiAutomaticSelectionError(
                "SEMI_AUTOMATIC_SELECTION_DISABLED",
                "Semi-automatic image selection is disabled by the server rollout gate.",
            )
        if mode not in {
            SEMI_AUTOMATIC_SELECTION_MODE,
            SEMI_AUTOMATIC_FILENAME_VERIFICATION_MODE,
        }:
            raise SemiAutomaticSelectionError(
                "SEMI_AUTOMATIC_SELECTION_MODE_INVALID",
                "The requested semi-automatic workflow mode is unsupported.",
            )
        if mode == SEMI_AUTOMATIC_FILENAME_VERIFICATION_MODE:
            if recognizer_variant != SEMI_AUTOMATIC_DEFAULT_RECOGNIZER_VARIANT:
                raise SemiAutomaticSelectionError(
                    "SEMI_AUTOMATIC_SELECTION_RECOGNIZER_VARIANT_INVALID",
                    "Filename verification does not support the selected recognizer variant.",
                )
            recognizer_fingerprint = RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V2
            grouping_policy = SEMI_AUTOMATIC_GROUPING_CONTRACT_FINGERPRINT
        else:
            variant = _SELECTION_RECOGNIZER_VARIANTS.get(recognizer_variant)
            if variant is None:
                raise SemiAutomaticSelectionError(
                    "SEMI_AUTOMATIC_SELECTION_RECOGNIZER_VARIANT_INVALID",
                    "The requested semi-automatic range recognizer variant is unsupported.",
                )
            recognizer_fingerprint = str(variant["fingerprint"])
            grouping_policy = (
                five_anchor_grouping_policy_fingerprint()
                if recognizer_variant == SEMI_AUTOMATIC_FIVE_ANCHOR_RECOGNIZER_VARIANT
                else SEMI_AUTOMATIC_GROUPING_CONTRACT_FINGERPRINT
            )
        ready = self._staging.get_ready_source_selection(
            upload_id,
            purpose=ImageSelectionPurpose.SEMI_AUTOMATIC_SELECTION,
        )
        source = SemiAutomaticSelectionSourceManifest(
            upload_id=ready.upload_id,
            display_name=ready.display_name,
            manifest_checksum_sha256=ready.manifest_checksum_sha256,
            source_fingerprint=ready.source_fingerprint,
            source_count=len(ready.sources),
            source_total_bytes=ready.total_bytes,
        )
        identity_key = run_identity_key(
            source=source,
            first_sequence_number=first_sequence_number,
            last_sequence_number=last_sequence_number,
            direction=direction,
            recognizer_fingerprint=recognizer_fingerprint,
            grouping_policy_fingerprint=grouping_policy,
        )
        existing = self._repository.find_by_identity(identity_key)
        if existing is not None:
            return existing, False
        run, ranges = create_semi_automatic_selection_run(
            source=source,
            first_sequence_number=first_sequence_number,
            last_sequence_number=last_sequence_number,
            direction=direction,
            workflow_mode=SemiAutomaticSelectionWorkflowMode(mode),
            recognizer_fingerprint=recognizer_fingerprint,
            grouping_policy_fingerprint=grouping_policy,
        )
        try:
            stored = self._repository.add(run, ranges, identity_key=identity_key)
            return stored, True
        except SemiAutomaticSelectionConflictError:
            concurrent = self._repository.find_by_identity(identity_key)
            if concurrent is None:
                raise
            return concurrent, False

    def list_filename_verification_items(
        self,
        run_id: UUID,
        *,
        after_source_index: int | None,
        limit: int,
    ) -> tuple[dict[str, object], ...]:
        run = self.get(run_id)
        if run.workflow_mode is not SemiAutomaticSelectionWorkflowMode.FILENAME_VERIFICATION:
            raise SemiAutomaticSelectionConflictError(
                "SEMI_AUTOMATIC_SELECTION_MODE_INVALID",
                "The run was not created for filename range verification.",
            )
        if limit < 1 or limit > 500:
            raise SemiAutomaticSelectionError(
                "SEMI_AUTOMATIC_SELECTION_PAGE_INVALID",
                "The verification page limit must be between 1 and 500.",
            )
        if self._artifact_root is None:
            raise SemiAutomaticSelectionError(
                "SEMI_AUTOMATIC_SELECTION_DIAGNOSTICS_UNAVAILABLE",
                "The range verification diagnostics store is unavailable.",
            )
        observations_path = (
            self._artifact_root
            / "exports"
            / "semi-automatic-selection"
            / str(run.id)
            / "observations.jsonl"
        ).resolve()
        expected_parent = (
            self._artifact_root / "exports" / "semi-automatic-selection" / str(run.id)
        ).resolve()
        if (
            observations_path.parent != expected_parent
            or self._artifact_root not in observations_path.parents
        ):
            raise SemiAutomaticSelectionError(
                "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
                "The verification diagnostics path is unsafe.",
            )
        committed = _committed_observation_count(run)
        if not observations_path.exists() or committed == 0:
            return ()
        first_index = 0 if after_source_index is None else after_source_index + 1
        if first_index >= committed:
            return ()
        items: list[dict[str, object]] = []
        try:
            with observations_path.open("r", encoding="utf-8") as source:
                for line_index, line in enumerate(source):
                    if line_index >= committed or len(items) >= limit:
                        break
                    if line_index < first_index:
                        continue
                    value = json.loads(line)
                    if not isinstance(value, dict) or value.get("sourceIndex") != line_index:
                        raise ValueError("non-contiguous observation")
                    items.append(
                        classify_filename_range_verification(cast(dict[str, object], value))
                    )
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
            raise SemiAutomaticSelectionError(
                "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
                "The committed filename verification diagnostics are invalid.",
            ) from error
        reviews = self._repository.get_filename_verification_reviews(
            run.id,
            [_filename_verification_source_index(item) for item in items],
        )
        return tuple(
            {
                **item,
                "reviewDecision": (
                    None
                    if (review := reviews.get(_filename_verification_source_index(item))) is None
                    else review.decision.value
                ),
                "reviewRevision": (None if review is None else review.revision),
            }
            for item in items
        )

    def list_runs(
        self,
        *,
        workflow_mode: SemiAutomaticSelectionWorkflowMode,
        offset: int,
        limit: int,
    ) -> tuple[tuple[SemiAutomaticSelectionRun, ...], int | None]:
        if offset < 0 or limit < 1 or limit > 100:
            raise SemiAutomaticSelectionError(
                "SEMI_AUTOMATIC_SELECTION_PAGE_INVALID",
                "The run history page is invalid.",
            )
        return self._repository.list_runs(
            workflow_mode=workflow_mode,
            offset=offset,
            limit=limit,
        )

    def decide_filename_verification(
        self,
        run_id: UUID,
        source_index: int,
        *,
        decision: FilenameRangeVerificationReviewDecision,
        expected_source_checksum_sha256: str,
        expected_revision: int,
    ) -> FilenameRangeVerificationReview:
        run = self.get(run_id)
        if run.workflow_mode is not SemiAutomaticSelectionWorkflowMode.FILENAME_VERIFICATION:
            raise SemiAutomaticSelectionConflictError(
                "SEMI_AUTOMATIC_SELECTION_MODE_INVALID",
                "The run was not created for filename range verification.",
            )
        if run.status not in {
            SemiAutomaticSelectionRunStatus.ANALYSIS_COMPLETE,
            SemiAutomaticSelectionRunStatus.REVIEW_MODE,
        }:
            raise SemiAutomaticSelectionConflictError(
                "SEMI_AUTOMATIC_SELECTION_NOT_REVIEWABLE",
                "Filename verification decisions are available only after analysis completes.",
            )
        ready = self._staging.get_ready_source_selection(
            run.source.upload_id,
            purpose=ImageSelectionPurpose.SEMI_AUTOMATIC_SELECTION,
        )
        if source_index < 0 or source_index >= len(ready.sources):
            raise SemiAutomaticSelectionNotFoundError(
                "SEMI_AUTOMATIC_SELECTION_SOURCE_NOT_FOUND",
                "The requested source does not exist.",
            )
        source = ready.sources[source_index]
        if source.checksum_sha256 != expected_source_checksum_sha256:
            raise SemiAutomaticSelectionConflictError(
                "SEMI_AUTOMATIC_SELECTION_SOURCE_CHANGED",
                "The reviewed source changed after it was loaded.",
            )
        observation_items = self.list_filename_verification_items(
            run.id,
            after_source_index=None if source_index == 0 else source_index - 1,
            limit=1,
        )
        if (
            len(observation_items) != 1
            or _filename_verification_source_index(observation_items[0]) != source_index
        ):
            raise SemiAutomaticSelectionConflictError(
                "SEMI_AUTOMATIC_SELECTION_SOURCE_NOT_FOUND",
                "The requested filename verification observation is unavailable.",
            )
        if observation_items[0].get("verificationStatus") == "verified":
            raise SemiAutomaticSelectionConflictError(
                "SEMI_AUTOMATIC_SELECTION_REVIEW_NOT_REQUIRED",
                "A filename verification decision is allowed only for an unreadable, "
                "mismatched, or invalid filename.",
            )
        existing = self._repository.get_filename_verification_reviews(
            run.id,
            [source_index],
        ).get(source_index)
        if (
            existing is not None
            and existing.decision is decision
            and existing.source_checksum_sha256 == source.checksum_sha256
        ):
            return existing
        if existing is not None and existing.revision != expected_revision:
            raise SemiAutomaticSelectionConflictError(
                "SEMI_AUTOMATIC_SELECTION_REVIEW_STALE",
                "The filename verification decision changed in another session.",
            )
        now = datetime.now(UTC)
        return self._repository.save_filename_verification_review(
            FilenameRangeVerificationReview(
                run_id=run.id,
                source_index=source_index,
                source_checksum_sha256=source.checksum_sha256,
                decision=decision,
                revision=0 if existing is None else existing.revision + 1,
                created_at=now if existing is None else existing.created_at,
                updated_at=now,
            ),
            expected_revision=0 if existing is None else expected_revision,
        )

    def delete_filename_verification_history(
        self,
        run_id: UUID,
    ) -> FilenameVerificationHistoryDeletion:
        """Remove only the compact, already-cleaned filename review history."""

        run = self._locked(run_id)
        if run.workflow_mode is not SemiAutomaticSelectionWorkflowMode.FILENAME_VERIFICATION:
            raise SemiAutomaticSelectionConflictError(
                "SEMI_AUTOMATIC_SELECTION_HISTORY_DELETE_MODE_INVALID",
                "Only filename verification history can be deleted here.",
            )
        if run.status is not SemiAutomaticSelectionRunStatus.COMPLETED:
            raise SemiAutomaticSelectionConflictError(
                "SEMI_AUTOMATIC_SELECTION_HISTORY_DELETE_NOT_COMPLETED",
                "Only a completed filename verification history entry can be deleted.",
            )
        if run.job.status is not JobStatus.COMPLETED:
            raise SemiAutomaticSelectionConflictError(
                "SEMI_AUTOMATIC_SELECTION_HISTORY_DELETE_JOB_ACTIVE",
                "The filename verification job is not terminal.",
            )
        if run.checkpoint.get("cleanup") != "completed":
            raise SemiAutomaticSelectionConflictError(
                "SEMI_AUTOMATIC_SELECTION_HISTORY_DELETE_CLEANUP_INCOMPLETE",
                "The filename verification working data has not been safely cleaned.",
            )
        return self._repository.delete_completed_filename_verification_history(
            run_id=run.id,
            job_id=run.job.id,
        )

    def get(self, run_id: UUID) -> SemiAutomaticSelectionRun:
        run = self._repository.get(run_id)
        if run is None:
            raise SemiAutomaticSelectionNotFoundError(
                "SEMI_AUTOMATIC_SELECTION_NOT_FOUND",
                "The semi-automatic selection run does not exist.",
            )
        return run

    def list_ranges(
        self,
        run_id: UUID,
        *,
        after_expected_index: int | None,
        limit: int,
    ) -> tuple[SemiAutomaticSelectionRange, ...]:
        self.get(run_id)
        if limit < 1 or limit > 500:
            raise SemiAutomaticSelectionError(
                "SEMI_AUTOMATIC_SELECTION_PAGE_INVALID",
                "The expected-range page limit must be between 1 and 500.",
            )
        return self._repository.list_ranges(
            run_id,
            after_expected_index=after_expected_index,
            limit=limit,
        )

    def pause(self, run_id: UUID) -> SemiAutomaticSelectionRun:
        run = self._locked(run_id)
        return self._repository.save(pause_run(run))

    def resume(self, run_id: UUID) -> SemiAutomaticSelectionRun:
        run = self._locked(run_id)
        resumed = resume_run(run)
        if resumed.job.status is JobStatus.WAITING_FOR_REVIEW:
            resumed = replace(resumed, job=requeue_job(resumed.job))
        return self._repository.save(resumed)

    def cancel(self, run_id: UUID) -> SemiAutomaticSelectionRun:
        run = self._locked(run_id)
        updated = cancel_run(run)
        job = request_job_cancellation(updated.job)
        return self._repository.save(replace(updated, job=job))

    def acknowledge_output(
        self,
        run_id: UUID,
        expected_index: int,
        *,
        expected_revision: int,
        expected_source_checksum_sha256: str,
        output_checksum_sha256: str,
        source_index: int | None = None,
    ) -> SemiAutomaticSelectionRange:
        run = self._locked(run_id)
        item = self._repository.get_range_for_update(run_id, expected_index)
        if item is None:
            raise SemiAutomaticSelectionNotFoundError(
                "SEMI_AUTOMATIC_SELECTION_RANGE_NOT_FOUND",
                "The expected range does not exist.",
            )
        if source_index is None:
            updated_item = acknowledge_output(
                item,
                expected_revision=expected_revision,
                expected_source_checksum_sha256=expected_source_checksum_sha256,
                output_checksum_sha256=output_checksum_sha256,
            )
        else:
            ready = self._staging.get_ready_source_selection(
                run.source.upload_id,
                purpose=ImageSelectionPurpose.SEMI_AUTOMATIC_SELECTION,
            )
            if source_index < 0 or source_index >= len(ready.sources):
                raise SemiAutomaticSelectionNotFoundError(
                    "SEMI_AUTOMATIC_SELECTION_SOURCE_NOT_FOUND",
                    "The requested staged source does not exist.",
                )
            source = ready.sources[source_index]
            if source.checksum_sha256 != expected_source_checksum_sha256:
                raise SemiAutomaticSelectionConflictError(
                    "SEMI_AUTOMATIC_SELECTION_SOURCE_CHANGED",
                    "The manually selected source changed after it was loaded.",
                )
            updated_item = acknowledge_manual_output(
                item,
                expected_revision=expected_revision,
                source_index=source.source_index,
                source_relative_path=source.relative_path,
                source_size_bytes=source.size_bytes,
                source_checksum_sha256=source.checksum_sha256,
                output_checksum_sha256=output_checksum_sha256,
            )
        updated_run = apply_range_status_transition(run, previous=item, current=updated_item)
        _, stored_item = self._repository.save_run_and_range(updated_run, updated_item)
        return stored_item

    def source_asset(
        self,
        run_id: UUID,
        source_index: int,
        *,
        expected_checksum_sha256: str,
    ) -> tuple[Path, str]:
        run = self.get(run_id)
        return self._staging.get_ready_source_asset(
            run.source.upload_id,
            purpose=ImageSelectionPurpose.SEMI_AUTOMATIC_SELECTION,
            source_index=source_index,
            expected_checksum_sha256=expected_checksum_sha256,
        )

    def _locked(self, run_id: UUID) -> SemiAutomaticSelectionRun:
        run = self._repository.get(run_id, for_update=True)
        if run is None:
            raise SemiAutomaticSelectionNotFoundError(
                "SEMI_AUTOMATIC_SELECTION_NOT_FOUND",
                "The semi-automatic selection run does not exist.",
            )
        return run


def _filename_verification_source_index(item: dict[str, object]) -> int:
    value = item.get("sourceIndex")
    if isinstance(value, bool) or not isinstance(value, int):
        raise SemiAutomaticSelectionError(
            "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
            "A filename verification item has an invalid source index.",
        )
    return value


def _committed_observation_count(run: SemiAutomaticSelectionRun) -> int:
    raw = run.checkpoint.get("observationCount")
    if isinstance(raw, int) and not isinstance(raw, bool):
        return max(0, min(raw, run.source.source_count))
    processed = run.counters.get("processedSources", 0)
    return max(0, min(processed, run.source.source_count))


__all__ = [
    "SEMI_AUTOMATIC_GROUPING_CONTRACT_FINGERPRINT",
    "SEMI_AUTOMATIC_DEFAULT_RECOGNIZER_VARIANT",
    "SEMI_AUTOMATIC_FIVE_ANCHOR_RECOGNIZER_VARIANT",
    "SEMI_AUTOMATIC_RECOGNIZER_FINGERPRINT",
    "SEMI_AUTOMATIC_FILENAME_VERIFICATION_MODE",
    "SEMI_AUTOMATIC_SELECTION_MODE",
    "SemiAutomaticImageSelectionService",
    "SemiAutomaticSelectionRepository",
    "workflow_mode_for_recognizer_fingerprint",
]
