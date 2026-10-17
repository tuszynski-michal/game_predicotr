"""Planned, confirmed runs that crop managed originals or delete cropped ones (D-562).

The API only records a run and queues its worker jobs. Planning (eligibility over
all games, an immutable manifest and a preview token) and execution happen in the
worker; execution starts only after the operator confirms the exact preview.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final, Literal, Protocol
from uuid import UUID, uuid4

from game_predictor_api.domain.jobs import JobConflictError

SourceCropRunKind = Literal["crop", "original_deletion"]
SOURCE_CROP_RUN_KINDS: Final = ("crop", "original_deletion")
# Kinds whose worker handler is registered; a preview of any other kind would
# queue a job that no worker claims and block every later run.
EXECUTABLE_RUN_KINDS: Final = ("crop",)
MAX_SCOPE_CHECKSUMS: Final = 500
MAX_SCOPE_LIMIT: Final = 1_000_000
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class SourceCropScope:
    """Which managed originals a run may consider; empty means all of them."""

    game_id: UUID | None = None
    only_checksums: tuple[str, ...] | None = None
    limit: int | None = None

    def __post_init__(self) -> None:
        if self.only_checksums is not None:
            if not 1 <= len(self.only_checksums) <= MAX_SCOPE_CHECKSUMS:
                raise JobConflictError(
                    "SOURCE_CROP_SCOPE_INVALID",
                    f"A checksum scope holds between 1 and {MAX_SCOPE_CHECKSUMS} originals.",
                )
            if any(_SHA256.fullmatch(value) is None for value in self.only_checksums) or len(
                set(self.only_checksums)
            ) != len(self.only_checksums):
                raise JobConflictError(
                    "SOURCE_CROP_SCOPE_INVALID",
                    "Scope checksums must be distinct lowercase SHA-256 values.",
                )
        if self.limit is not None and not 1 <= self.limit <= MAX_SCOPE_LIMIT:
            raise JobConflictError(
                "SOURCE_CROP_SCOPE_INVALID", "The run limit must be between 1 and 1000000."
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "gameId": None if self.game_id is None else str(self.game_id),
            "onlyChecksums": None if self.only_checksums is None else list(self.only_checksums),
            "limit": self.limit,
        }

    @classmethod
    def from_payload(cls, value: Mapping[str, object]) -> SourceCropScope:
        game = value.get("gameId")
        checksums = value.get("onlyChecksums")
        limit = value.get("limit")
        return cls(
            game_id=None if game is None else UUID(str(game)),
            only_checksums=(
                tuple(str(item) for item in checksums) if isinstance(checksums, list) else None
            ),
            limit=limit if isinstance(limit, int) and not isinstance(limit, bool) else None,
        )


@dataclass(frozen=True, slots=True)
class SourceCropRun:
    id: UUID
    kind: str
    status: str
    scope: SourceCropScope
    plan_job_id: UUID
    job_id: UUID | None
    manifest_checksum_sha256: str | None
    preview_token: str | None
    eligible_count: int
    excluded_count: int
    exclusion_counts: Mapping[str, int]
    candidate_bytes: int
    estimated_saved_bytes: int
    processed_count: int
    succeeded_count: int
    skipped_count: int
    failed_count: int
    saved_bytes: int
    checkpoint_index: int
    outcome_counts: Mapping[str, int]
    failures: Sequence[Mapping[str, object]] = field(default_factory=tuple)
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class SourceCropRunRepository(Protocol):
    def create_planning_run(
        self, *, run_id: UUID, kind: SourceCropRunKind, scope: SourceCropScope
    ) -> SourceCropRun: ...

    def start_run(
        self,
        *,
        run_id: UUID,
        expected_manifest_checksum_sha256: str,
        expected_preview_token: str,
    ) -> SourceCropRun: ...

    def get_run(self, run_id: UUID) -> SourceCropRun: ...

    def list_runs(self, *, limit: int) -> Sequence[SourceCropRun]: ...


class SourceCropRunService:
    """Plan, confirm and read crop and original-deletion runs."""

    def __init__(self, repository: SourceCropRunRepository) -> None:
        self._repository = repository

    def create_preview(self, *, kind: SourceCropRunKind, scope: SourceCropScope) -> SourceCropRun:
        if kind not in SOURCE_CROP_RUN_KINDS:
            raise JobConflictError("SOURCE_CROP_KIND_INVALID", "Unknown source crop run kind.")
        if kind not in EXECUTABLE_RUN_KINDS:
            raise JobConflictError(
                "SOURCE_CROP_KIND_UNSUPPORTED", "This run kind has no worker handler yet."
            )
        return self._repository.create_planning_run(run_id=uuid4(), kind=kind, scope=scope)

    def start(
        self,
        *,
        preview_id: UUID,
        manifest_checksum_sha256: str,
        preview_token: str,
        confirmed: bool,
        acknowledge_irreversible: bool,
    ) -> SourceCropRun:
        if not confirmed:
            raise JobConflictError(
                "SOURCE_CROP_CONFIRMATION_REQUIRED",
                "Starting a source crop run requires explicit confirmation of its preview.",
            )
        run = self._repository.get_run(preview_id)
        if run.kind == "original_deletion" and not acknowledge_irreversible:
            raise JobConflictError(
                "SOURCE_ORIGINAL_DELETION_ACKNOWLEDGEMENT_REQUIRED",
                "Deleting originals is irreversible and requires an explicit acknowledgement.",
            )
        return self._repository.start_run(
            run_id=preview_id,
            expected_manifest_checksum_sha256=manifest_checksum_sha256,
            expected_preview_token=preview_token,
        )

    def get(self, run_id: UUID) -> SourceCropRun:
        return self._repository.get_run(run_id)

    def list(self, *, limit: int = 10) -> Sequence[SourceCropRun]:
        if not 1 <= limit <= 50:
            raise JobConflictError("SOURCE_CROP_LIST_LIMIT_INVALID", "List 1 to 50 runs.")
        return self._repository.list_runs(limit=limit)


__all__ = [
    "MAX_SCOPE_CHECKSUMS",
    "SOURCE_CROP_RUN_KINDS",
    "SourceCropRun",
    "SourceCropRunKind",
    "SourceCropRunRepository",
    "SourceCropRunService",
    "SourceCropScope",
]
