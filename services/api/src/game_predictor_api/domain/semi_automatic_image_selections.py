"""Domain contracts for game-independent semi-automatic image selection runs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from game_predictor_api.domain.jobs import Job, JobConflictError, JobError, JobType, create_job

SEMI_AUTOMATIC_SELECTION_CONTRACT_VERSION = 1
SEMI_AUTOMATIC_SELECTION_RANGE_CONVENTION = "seq-inclusive-v1"
SEMI_AUTOMATIC_SELECTION_FULL_RANGE_SIZE = 9
SEMI_AUTOMATIC_SELECTION_ORDERING_POLICY = "natural_relative_path_v1"
SEMI_AUTOMATIC_SELECTION_WORKFLOW = "semi_automatic_image_selection"


class SemiAutomaticSelectionDirection(StrEnum):
    ASCENDING = "ascending"
    DESCENDING = "descending"


class SemiAutomaticSelectionRunStatus(StrEnum):
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    ANALYSIS_COMPLETE = "analysis_complete"
    SYNCING_OUTPUT = "syncing_output"
    REVIEW_MODE = "review_mode"
    EDIT_SOURCE_MODE = "edit_source_mode"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SemiAutomaticSelectionRangeStatus(StrEnum):
    MISSING = "missing"
    AUTO_SELECTED = "auto_selected"
    OUTPUT_SYNCED = "output_synced"
    CONFLICT = "conflict"


class SemiAutomaticSelectionError(JobError):
    """Stable error for the semi-automatic selection HTTP boundary."""


class SemiAutomaticSelectionNotFoundError(SemiAutomaticSelectionError):
    """A run, source, or expected range does not exist."""


class SemiAutomaticSelectionConflictError(JobConflictError):
    """The requested mutation conflicts with durable run state."""


@dataclass(frozen=True, slots=True)
class SemiAutomaticSelectionSourceManifest:
    upload_id: UUID
    display_name: str
    manifest_checksum_sha256: str
    source_fingerprint: str
    source_count: int
    source_total_bytes: int

    def __post_init__(self) -> None:
        if not self.display_name.strip() or self.source_count < 1 or self.source_total_bytes < 1:
            raise ValueError("A source manifest requires non-empty staged JPEGs.")
        _require_sha256(self.manifest_checksum_sha256, "manifest checksum")
        _require_sha256(self.source_fingerprint, "source fingerprint")


@dataclass(frozen=True, slots=True)
class SemiAutomaticSelectionRange:
    id: UUID
    run_id: UUID
    expected_index: int
    range_start: int
    range_end: int
    status: SemiAutomaticSelectionRangeStatus
    source_index: int | None
    source_relative_path: str | None
    source_size_bytes: int | None
    source_checksum_sha256: str | None
    group_first_source_index: int | None
    group_last_source_index: int | None
    range_confidence: float | None
    selection_method: str | None
    output_checksum_sha256: str | None
    revision: int
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if self.expected_index < 0 or self.range_start < 1 or self.range_end < self.range_start:
            raise ValueError("An expected range has invalid bounds.")
        if self.range_end - self.range_start + 1 > SEMI_AUTOMATIC_SELECTION_FULL_RANGE_SIZE:
            raise ValueError("An expected range exceeds the full range size.")
        if self.revision < 0:
            raise ValueError("Range revision cannot be negative.")
        if self.range_confidence is not None and not 0 <= self.range_confidence <= 1:
            raise ValueError("Range confidence must be between zero and one.")
        if self.source_checksum_sha256 is not None:
            _require_sha256(self.source_checksum_sha256, "source checksum")
        if self.output_checksum_sha256 is not None:
            _require_sha256(self.output_checksum_sha256, "output checksum")


@dataclass(frozen=True, slots=True)
class SemiAutomaticSelectionRun:
    id: UUID
    job: Job
    source: SemiAutomaticSelectionSourceManifest
    first_sequence_number: int
    last_sequence_number: int
    direction: SemiAutomaticSelectionDirection
    range_convention: str
    full_range_size: int
    expected_ranges_fingerprint: str
    recognizer_fingerprint: str
    grouping_policy_fingerprint: str
    status: SemiAutomaticSelectionRunStatus
    checkpoint: dict[str, object]
    counters: dict[str, int]
    diagnostics_relative_path: str | None
    diagnostics_checksum_sha256: str | None
    revision: int
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if (
            self.job.game_id is not None
            or self.job.job_type is not JobType.SEMI_AUTOMATIC_IMAGE_SELECTION
        ):
            raise ValueError("A semi-automatic selection run requires a global dedicated job.")
        if self.first_sequence_number < 1 or self.last_sequence_number < self.first_sequence_number:
            raise ValueError("Run bounds must be positive and increasing.")
        if self.range_convention != SEMI_AUTOMATIC_SELECTION_RANGE_CONVENTION:
            raise ValueError("Run range convention is unsupported.")
        if self.full_range_size != SEMI_AUTOMATIC_SELECTION_FULL_RANGE_SIZE:
            raise ValueError("Run full range size is unsupported.")
        for value in (
            self.expected_ranges_fingerprint,
            self.recognizer_fingerprint,
            self.grouping_policy_fingerprint,
        ):
            _require_sha256(value, "run fingerprint")
        if self.diagnostics_checksum_sha256 is not None:
            _require_sha256(self.diagnostics_checksum_sha256, "diagnostics checksum")
        if self.revision < 0 or any(value < 0 for value in self.counters.values()):
            raise ValueError("Run revision and counters cannot be negative.")


def create_semi_automatic_selection_run(
    *,
    source: SemiAutomaticSelectionSourceManifest,
    first_sequence_number: int,
    last_sequence_number: int,
    direction: SemiAutomaticSelectionDirection,
    recognizer_fingerprint: str,
    grouping_policy_fingerprint: str,
    created_at: datetime | None = None,
) -> tuple[SemiAutomaticSelectionRun, tuple[SemiAutomaticSelectionRange, ...]]:
    if first_sequence_number < 1 or last_sequence_number < first_sequence_number:
        raise SemiAutomaticSelectionError(
            "SEMI_AUTOMATIC_SELECTION_BOUNDS_INVALID",
            "The requested sequence bounds are invalid.",
        )
    _require_sha256(recognizer_fingerprint, "recognizer fingerprint")
    _require_sha256(grouping_policy_fingerprint, "grouping policy fingerprint")
    now = created_at or datetime.now(UTC)
    run_id = uuid4()
    ranges = _expected_ranges(
        run_id=run_id,
        first_sequence_number=first_sequence_number,
        last_sequence_number=last_sequence_number,
        created_at=now,
    )
    expected_fingerprint = expected_ranges_fingerprint(ranges)
    payload: dict[str, object] = {
        "schema_version": 1,
        "selection_kind": SEMI_AUTOMATIC_SELECTION_WORKFLOW,
        "run_id": str(run_id),
        "source_upload_id": str(source.upload_id),
        "source_manifest_checksum_sha256": source.manifest_checksum_sha256,
        "source_fingerprint": source.source_fingerprint,
        "source_count": source.source_count,
        "first_sequence_number": first_sequence_number,
        "last_sequence_number": last_sequence_number,
        "direction": direction.value,
        "range_convention": SEMI_AUTOMATIC_SELECTION_RANGE_CONVENTION,
        "full_range_size": SEMI_AUTOMATIC_SELECTION_FULL_RANGE_SIZE,
        "expected_ranges_fingerprint": expected_fingerprint,
        "recognizer_fingerprint": recognizer_fingerprint,
        "grouping_policy_fingerprint": grouping_policy_fingerprint,
    }
    job = create_job(
        JobType.SEMI_AUTOMATIC_IMAGE_SELECTION,
        game_id=None,
        input_payload=payload,
        created_at=now,
    )
    return (
        SemiAutomaticSelectionRun(
            id=run_id,
            job=job,
            source=source,
            first_sequence_number=first_sequence_number,
            last_sequence_number=last_sequence_number,
            direction=direction,
            range_convention=SEMI_AUTOMATIC_SELECTION_RANGE_CONVENTION,
            full_range_size=SEMI_AUTOMATIC_SELECTION_FULL_RANGE_SIZE,
            expected_ranges_fingerprint=expected_fingerprint,
            recognizer_fingerprint=recognizer_fingerprint,
            grouping_policy_fingerprint=grouping_policy_fingerprint,
            status=SemiAutomaticSelectionRunStatus.READY,
            checkpoint={},
            counters={
                "expected": len(ranges),
                "autoSelected": 0,
                "outputSynced": 0,
                "conflicts": 0,
                "missing": len(ranges),
            },
            diagnostics_relative_path=None,
            diagnostics_checksum_sha256=None,
            revision=0,
            created_at=now,
            updated_at=now,
        ),
        ranges,
    )


def pause_run(
    run: SemiAutomaticSelectionRun,
    *,
    changed_at: datetime | None = None,
) -> SemiAutomaticSelectionRun:
    if run.status is SemiAutomaticSelectionRunStatus.PAUSED:
        return run
    if run.status not in {
        SemiAutomaticSelectionRunStatus.READY,
        SemiAutomaticSelectionRunStatus.RUNNING,
    }:
        _invalid_run_transition(run, SemiAutomaticSelectionRunStatus.PAUSED)
    return _with_status(run, SemiAutomaticSelectionRunStatus.PAUSED, changed_at)


def resume_run(
    run: SemiAutomaticSelectionRun,
    *,
    changed_at: datetime | None = None,
) -> SemiAutomaticSelectionRun:
    if run.status is not SemiAutomaticSelectionRunStatus.PAUSED:
        _invalid_run_transition(run, SemiAutomaticSelectionRunStatus.READY)
    return _with_status(run, SemiAutomaticSelectionRunStatus.READY, changed_at)


def cancel_run(
    run: SemiAutomaticSelectionRun,
    *,
    changed_at: datetime | None = None,
) -> SemiAutomaticSelectionRun:
    if run.status is SemiAutomaticSelectionRunStatus.CANCELLED:
        return run
    if run.status in {
        SemiAutomaticSelectionRunStatus.COMPLETED,
        SemiAutomaticSelectionRunStatus.FAILED,
    }:
        _invalid_run_transition(run, SemiAutomaticSelectionRunStatus.CANCELLED)
    return _with_status(run, SemiAutomaticSelectionRunStatus.CANCELLED, changed_at)


def acknowledge_output(
    item: SemiAutomaticSelectionRange,
    *,
    expected_revision: int,
    expected_source_checksum_sha256: str,
    output_checksum_sha256: str,
    changed_at: datetime | None = None,
) -> SemiAutomaticSelectionRange:
    _require_sha256(expected_source_checksum_sha256, "expected source checksum")
    _require_sha256(output_checksum_sha256, "output checksum")
    if item.revision != expected_revision:
        raise SemiAutomaticSelectionConflictError(
            "SEMI_AUTOMATIC_SELECTION_CURSOR_STALE",
            "The expected range changed after it was loaded.",
        )
    if item.status not in {
        SemiAutomaticSelectionRangeStatus.AUTO_SELECTED,
        SemiAutomaticSelectionRangeStatus.OUTPUT_SYNCED,
    } or item.source_checksum_sha256 is None:
        raise SemiAutomaticSelectionConflictError(
            "SEMI_AUTOMATIC_SELECTION_RANGE_NOT_SELECTED",
            "The expected range has no selected source to acknowledge.",
        )
    if item.source_checksum_sha256 != expected_source_checksum_sha256:
        raise SemiAutomaticSelectionConflictError(
            "SEMI_AUTOMATIC_SELECTION_SOURCE_CHANGED",
            "The selected source changed after it was loaded.",
        )
    if output_checksum_sha256 != item.source_checksum_sha256:
        raise SemiAutomaticSelectionConflictError(
            "SEMI_AUTOMATIC_SELECTION_OUTPUT_CHECKSUM_MISMATCH",
            "The local output differs from the selected source bytes.",
        )
    if (
        item.status is SemiAutomaticSelectionRangeStatus.OUTPUT_SYNCED
        and item.output_checksum_sha256 == output_checksum_sha256
    ):
        return item
    now = changed_at or datetime.now(UTC)
    return replace(
        item,
        status=SemiAutomaticSelectionRangeStatus.OUTPUT_SYNCED,
        output_checksum_sha256=output_checksum_sha256,
        revision=item.revision + 1,
        updated_at=now,
    )


def apply_range_status_transition(
    run: SemiAutomaticSelectionRun,
    *,
    previous: SemiAutomaticSelectionRange,
    current: SemiAutomaticSelectionRange,
) -> SemiAutomaticSelectionRun:
    """Keep durable run counters aligned with one range transition."""

    if previous.run_id != run.id or current.run_id != run.id or previous.id != current.id:
        raise ValueError("A range transition must belong to the supplied run.")
    if previous.status is current.status:
        return run
    counters = dict(run.counters)
    previous_key = _range_counter_key(previous.status)
    current_key = _range_counter_key(current.status)
    if counters.get(previous_key, 0) < 1:
        raise ValueError("Run counters do not contain the previous range state.")
    counters[previous_key] -= 1
    counters[current_key] = counters.get(current_key, 0) + 1
    return replace(
        run,
        counters=counters,
        revision=run.revision + 1,
        updated_at=current.updated_at,
    )


def expected_ranges_fingerprint(
    ranges: tuple[SemiAutomaticSelectionRange, ...],
) -> str:
    payload = [
        {"expectedIndex": item.expected_index, "start": item.range_start, "end": item.range_end}
        for item in ranges
    ]
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


def run_identity_key(
    *,
    source: SemiAutomaticSelectionSourceManifest,
    first_sequence_number: int,
    last_sequence_number: int,
    direction: SemiAutomaticSelectionDirection,
    recognizer_fingerprint: str,
    grouping_policy_fingerprint: str,
) -> str:
    payload = {
        "contractVersion": SEMI_AUTOMATIC_SELECTION_CONTRACT_VERSION,
        "direction": direction.value,
        "firstSequenceNumber": first_sequence_number,
        "fullRangeSize": SEMI_AUTOMATIC_SELECTION_FULL_RANGE_SIZE,
        "groupingPolicyFingerprint": grouping_policy_fingerprint,
        "lastSequenceNumber": last_sequence_number,
        "rangeConvention": SEMI_AUTOMATIC_SELECTION_RANGE_CONVENTION,
        "recognizerFingerprint": recognizer_fingerprint,
        "sourceFingerprint": source.source_fingerprint,
        "sourceManifestChecksumSha256": source.manifest_checksum_sha256,
        "sourceUploadId": str(source.upload_id),
    }
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


def _expected_ranges(
    *,
    run_id: UUID,
    first_sequence_number: int,
    last_sequence_number: int,
    created_at: datetime,
) -> tuple[SemiAutomaticSelectionRange, ...]:
    items: list[SemiAutomaticSelectionRange] = []
    start = first_sequence_number
    while start <= last_sequence_number:
        end = min(start + SEMI_AUTOMATIC_SELECTION_FULL_RANGE_SIZE - 1, last_sequence_number)
        items.append(
            SemiAutomaticSelectionRange(
                id=uuid4(),
                run_id=run_id,
                expected_index=len(items),
                range_start=start,
                range_end=end,
                status=SemiAutomaticSelectionRangeStatus.MISSING,
                source_index=None,
                source_relative_path=None,
                source_size_bytes=None,
                source_checksum_sha256=None,
                group_first_source_index=None,
                group_last_source_index=None,
                range_confidence=None,
                selection_method=None,
                output_checksum_sha256=None,
                revision=0,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        start = end + 1
    return tuple(items)


def _with_status(
    run: SemiAutomaticSelectionRun,
    status: SemiAutomaticSelectionRunStatus,
    changed_at: datetime | None,
) -> SemiAutomaticSelectionRun:
    return replace(
        run,
        status=status,
        revision=run.revision + 1,
        updated_at=changed_at or datetime.now(UTC),
    )


def _invalid_run_transition(
    run: SemiAutomaticSelectionRun,
    target: SemiAutomaticSelectionRunStatus,
) -> None:
    raise SemiAutomaticSelectionConflictError(
        "SEMI_AUTOMATIC_SELECTION_STATE_INVALID",
        f"A {run.status.value} run cannot transition to {target.value}.",
    )


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"The {label} must be a lowercase SHA-256 value.")


def _range_counter_key(status: SemiAutomaticSelectionRangeStatus) -> str:
    return {
        SemiAutomaticSelectionRangeStatus.MISSING: "missing",
        SemiAutomaticSelectionRangeStatus.AUTO_SELECTED: "autoSelected",
        SemiAutomaticSelectionRangeStatus.OUTPUT_SYNCED: "outputSynced",
        SemiAutomaticSelectionRangeStatus.CONFLICT: "conflicts",
    }[status]


__all__ = [
    "SEMI_AUTOMATIC_SELECTION_CONTRACT_VERSION",
    "SEMI_AUTOMATIC_SELECTION_FULL_RANGE_SIZE",
    "SEMI_AUTOMATIC_SELECTION_ORDERING_POLICY",
    "SEMI_AUTOMATIC_SELECTION_RANGE_CONVENTION",
    "SEMI_AUTOMATIC_SELECTION_WORKFLOW",
    "SemiAutomaticSelectionConflictError",
    "SemiAutomaticSelectionDirection",
    "SemiAutomaticSelectionError",
    "SemiAutomaticSelectionNotFoundError",
    "SemiAutomaticSelectionRange",
    "SemiAutomaticSelectionRangeStatus",
    "SemiAutomaticSelectionRun",
    "SemiAutomaticSelectionRunStatus",
    "SemiAutomaticSelectionSourceManifest",
    "acknowledge_output",
    "apply_range_status_transition",
    "cancel_run",
    "create_semi_automatic_selection_run",
    "expected_ranges_fingerprint",
    "pause_run",
    "resume_run",
    "run_identity_key",
]
