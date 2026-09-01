"""Application service for durable global semi-automatic selection runs."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Protocol
from uuid import UUID

from game_predictor_worker.semi_automatic_selection.engine import (
    grouping_policy_fingerprint,
)
from game_predictor_worker.semi_automatic_selection.range_only_ocr import (
    RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT,
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
    SemiAutomaticSelectionConflictError,
    SemiAutomaticSelectionDirection,
    SemiAutomaticSelectionError,
    SemiAutomaticSelectionNotFoundError,
    SemiAutomaticSelectionRange,
    SemiAutomaticSelectionRun,
    SemiAutomaticSelectionSourceManifest,
    acknowledge_manual_output,
    acknowledge_output,
    apply_range_status_transition,
    cancel_run,
    create_semi_automatic_selection_run,
    pause_run,
    resume_run,
    run_identity_key,
)

SEMI_AUTOMATIC_RECOGNIZER_FINGERPRINT = RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT
SEMI_AUTOMATIC_GROUPING_CONTRACT_FINGERPRINT = grouping_policy_fingerprint()


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
    ) -> None:
        self._repository = repository
        self._staging = staging
        self._enabled = enabled

    def capabilities(self) -> dict[str, object]:
        return {
            "enabled": self._enabled,
            "contractVersion": SEMI_AUTOMATIC_SELECTION_CONTRACT_VERSION,
            "rangeConvention": SEMI_AUTOMATIC_SELECTION_RANGE_CONVENTION,
            "fullRangeSize": SEMI_AUTOMATIC_SELECTION_FULL_RANGE_SIZE,
            "minimumSequenceNumber": 1,
            "maximumBoardsPerRange": SEMI_AUTOMATIC_SELECTION_FULL_RANGE_SIZE,
            "stagingPurpose": ImageSelectionPurpose.SEMI_AUTOMATIC_SELECTION.value,
            "recognizerFingerprint": SEMI_AUTOMATIC_RECOGNIZER_FINGERPRINT,
            "groupingPolicyFingerprint": SEMI_AUTOMATIC_GROUPING_CONTRACT_FINGERPRINT,
        }

    def create(
        self,
        *,
        upload_id: UUID,
        first_sequence_number: int,
        last_sequence_number: int,
        direction: SemiAutomaticSelectionDirection,
    ) -> tuple[SemiAutomaticSelectionRun, bool]:
        if not self._enabled:
            raise SemiAutomaticSelectionError(
                "SEMI_AUTOMATIC_SELECTION_DISABLED",
                "Semi-automatic image selection is disabled by the server rollout gate.",
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
            recognizer_fingerprint=SEMI_AUTOMATIC_RECOGNIZER_FINGERPRINT,
            grouping_policy_fingerprint=SEMI_AUTOMATIC_GROUPING_CONTRACT_FINGERPRINT,
        )
        existing = self._repository.find_by_identity(identity_key)
        if existing is not None:
            return existing, False
        run, ranges = create_semi_automatic_selection_run(
            source=source,
            first_sequence_number=first_sequence_number,
            last_sequence_number=last_sequence_number,
            direction=direction,
            recognizer_fingerprint=SEMI_AUTOMATIC_RECOGNIZER_FINGERPRINT,
            grouping_policy_fingerprint=SEMI_AUTOMATIC_GROUPING_CONTRACT_FINGERPRINT,
        )
        try:
            stored = self._repository.add(run, ranges, identity_key=identity_key)
            return stored, True
        except SemiAutomaticSelectionConflictError:
            concurrent = self._repository.find_by_identity(identity_key)
            if concurrent is None:
                raise
            return concurrent, False

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


__all__ = [
    "SEMI_AUTOMATIC_GROUPING_CONTRACT_FINGERPRINT",
    "SEMI_AUTOMATIC_RECOGNIZER_FINGERPRINT",
    "SemiAutomaticImageSelectionService",
    "SemiAutomaticSelectionRepository",
]
