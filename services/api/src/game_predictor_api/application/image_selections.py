"""Application boundary for durable image-selection runs."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Literal, Protocol
from uuid import UUID, uuid4

from game_predictor_worker.images.image_file import ImageFileError, read_jpeg_dimensions
from game_predictor_worker.images.selection.contracts import SelectionContractError
from game_predictor_worker.images.selection.output import verify_curated_image_manifest

from game_predictor_api.domain.image_selections import (
    IMAGE_SELECTION_GROUP_PAGE_MAX,
    ImageSelectionCandidate,
    ImageSelectionCandidateDecision,
    ImageSelectionConflictError,
    ImageSelectionError,
    ImageSelectionGroup,
    ImageSelectionGroupPage,
    ImageSelectionGroupStatus,
    ImageSelectionManualDecision,
    ImageSelectionNotFoundError,
    ImageSelectionRun,
    ImageSelectionSequenceDirection,
    create_image_selection_run,
    create_manual_decision,
    create_missing_image_decision,
    record_image_selection_output,
    safe_relative_path,
    validate_candidate,
)
from game_predictor_api.domain.jobs import (
    Job,
    JobStatus,
    reopen_completed_job_for_revision,
    requeue_job,
)

MAX_MANUAL_IMAGE_BYTES = 50 * 1024 * 1024
BROWSER_SELECTION_DIRECTORY = "browser-selections"
BROWSER_SELECTION_MANIFEST = "_browser_manifest.json"


def _public_output_file_name(
    output_relative_path: str,
    range_start: int | None,
    range_end: int | None,
) -> str:
    """Return the stable public name for current and historical manifests."""

    if range_start is not None and range_end is not None:
        return f"seq_{range_start}-{range_end}.jpg"
    return PurePosixPath(safe_relative_path(output_relative_path)).name


@dataclass(frozen=True, slots=True)
class ImageSelectionHandoffSource:
    run: ImageSelectionRun
    output_directory: Path
    supported_file_count: int


@dataclass(frozen=True, slots=True)
class ImageSelectionOutputFile:
    file_name: str
    group_order: int
    range_start: int | None
    range_end: int | None
    checksum_sha256: str
    size_bytes: int
    reason_codes: tuple[str, ...]
    selection_method: Literal["automatic", "manual"]


@dataclass(frozen=True, slots=True)
class ImageSelectionOutput:
    run_id: UUID
    manifest_sha256: str
    files: tuple[ImageSelectionOutputFile, ...]


@dataclass(frozen=True, slots=True)
class ManualImageSelectionFile:
    relative_path: str
    checksum_sha256: str
    size_bytes: int
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class ImageSelectionManualApproval:
    group: ImageSelectionGroup
    decision: ImageSelectionManualDecision


class ManualImageSelectionFileStore:
    """Managed JPEG copies and a canonical working decision manifest."""

    def __init__(self, artifact_root: Path) -> None:
        self._artifact_root = artifact_root.resolve()
        self._root = self._artifact_root / "data" / "working" / "is-manual"

    def save(
        self,
        *,
        run_id: UUID,
        group_id: UUID,
        display_name: str,
        content: bytes,
    ) -> ManualImageSelectionFile:
        normalized_name = Path(display_name).name
        if (
            not normalized_name
            or len(normalized_name) > 255
            or Path(normalized_name).suffix.casefold() not in {".jpg", ".jpeg"}
        ):
            raise ImageSelectionError(
                "IMAGE_SELECTION_MANUAL_FILE_INVALID",
                "Choose one JPEG file with a safe display name.",
            )
        if not 1 <= len(content) <= MAX_MANUAL_IMAGE_BYTES:
            raise ImageSelectionError(
                "IMAGE_SELECTION_MANUAL_FILE_INVALID",
                "The manual JPEG must be non-empty and no larger than 50 MB.",
            )
        checksum = hashlib.sha256(content).hexdigest()
        group_root = self._root / run_id.hex[:12] / group_id.hex[:12]
        group_root.mkdir(parents=True, exist_ok=True)
        target = group_root / f"{checksum[:32]}.jpg"
        if not target.exists():
            temporary = group_root / f".{uuid4().hex[:8]}.part"
            try:
                with temporary.open("xb") as output:
                    output.write(content)
                    output.flush()
                    os.fsync(output.fileno())
                width, height = read_jpeg_dimensions(temporary)
                try:
                    temporary.replace(target)
                except OSError:
                    if not target.exists():
                        raise
            except (OSError, ImageFileError) as error:
                temporary.unlink(missing_ok=True)
                raise ImageSelectionError(
                    "IMAGE_SELECTION_MANUAL_FILE_INVALID",
                    "The selected file is not a readable JPEG image.",
                ) from error
            temporary.unlink(missing_ok=True)
        if hashlib.sha256(target.read_bytes()).hexdigest() != checksum:
            raise ImageSelectionConflictError(
                "IMAGE_SELECTION_MANUAL_FILE_CHANGED",
                "The managed manual JPEG differs from the uploaded content.",
            )
        try:
            width, height = read_jpeg_dimensions(target)
        except ImageFileError as error:
            raise ImageSelectionConflictError(
                "IMAGE_SELECTION_MANUAL_FILE_CHANGED",
                "The managed manual JPEG is no longer readable.",
            ) from error
        relative_path = target.relative_to(self._artifact_root).as_posix()
        return ManualImageSelectionFile(
            relative_path=relative_path,
            checksum_sha256=checksum,
            size_bytes=target.stat().st_size,
            width=width,
            height=height,
        )

    def resolve(self, candidate: ImageSelectionCandidate) -> Path:
        relative = safe_relative_path(candidate.source_relative_path)
        expected_prefix = "data/working/is-manual/"
        if not relative.startswith(expected_prefix):
            raise ImageSelectionConflictError(
                "IMAGE_SELECTION_MANUAL_FILE_MISSING",
                "The candidate is not a managed manual JPEG.",
            )
        path = (self._artifact_root / Path(*PurePosixPath(relative).parts)).resolve(strict=True)
        if not path.is_relative_to(self._root) or not path.is_file():
            raise ImageSelectionConflictError(
                "IMAGE_SELECTION_MANUAL_FILE_MISSING",
                "The managed manual JPEG is missing or unsafe.",
            )
        if hashlib.sha256(path.read_bytes()).hexdigest() != candidate.checksum_sha256:
            raise ImageSelectionConflictError(
                "IMAGE_SELECTION_MANUAL_FILE_CHANGED",
                "The managed manual JPEG checksum changed.",
            )
        return path

    def write_decision_manifest(
        self,
        *,
        run_id: UUID,
        decisions: Sequence[ImageSelectionManualDecision],
    ) -> None:
        run_root = self._root / run_id.hex[:12]
        run_root.mkdir(parents=True, exist_ok=True)
        payload = {
            "contract": "image-selection-manual-decisions-v1",
            "decisions": [
                {
                    "candidateId": (None if item.candidate_id is None else str(item.candidate_id)),
                    "createdAt": item.created_at.isoformat(),
                    "groupId": str(item.group_id),
                    "idempotencyKey": str(item.idempotency_key),
                    "payloadSha256": item.payload_sha256,
                    "resolution": item.resolution.value,
                    "rangeEnd": item.range_end,
                    "rangeStart": item.range_start,
                    "revision": item.revision,
                }
                for item in sorted(
                    decisions,
                    key=lambda value: (str(value.group_id), value.revision),
                )
            ],
            "runId": str(run_id),
            "schemaVersion": 1,
        }
        content = json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        target = run_root / "manual-decisions.json"
        temporary = run_root / ".manual-decisions.json.part"
        with temporary.open("wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(target)


class ImageSelectionRepository(Protocol):
    def game_exists(self, game_id: UUID) -> bool: ...

    def find_run_by_identity(
        self,
        *,
        game_id: UUID,
        input_manifest_sha256: str,
        selector_fingerprint: str,
        sequence_direction: ImageSelectionSequenceDirection,
        first_sequence_number: int | None,
    ) -> ImageSelectionRun | None: ...

    def add_run(self, run: ImageSelectionRun) -> tuple[ImageSelectionRun, bool]: ...

    def get_run(self, run_id: UUID) -> ImageSelectionRun | None: ...

    def list_runs(
        self,
        *,
        game_id: UUID,
        offset: int,
        limit: int,
    ) -> Sequence[ImageSelectionRun]: ...

    def save_run(self, run: ImageSelectionRun) -> ImageSelectionRun: ...

    def invalidate_output(self, run_id: UUID) -> ImageSelectionRun: ...

    def list_groups(
        self,
        *,
        run_id: UUID,
        status: ImageSelectionGroupStatus | None,
        after_group_order: int,
        limit: int,
    ) -> Sequence[ImageSelectionGroup]: ...

    def add_group(self, group: ImageSelectionGroup) -> ImageSelectionGroup: ...

    def add_candidate(
        self,
        candidate: ImageSelectionCandidate,
    ) -> ImageSelectionCandidate: ...

    def get_group(self, *, run_id: UUID, group_id: UUID) -> ImageSelectionGroup | None: ...

    def get_candidate(
        self, *, run_id: UUID, candidate_id: UUID
    ) -> ImageSelectionCandidate | None: ...

    def list_candidates(
        self,
        *,
        run_id: UUID,
        group_id: UUID,
        limit: int,
    ) -> Sequence[ImageSelectionCandidate]: ...

    def find_candidate_by_checksum(
        self, *, run_id: UUID, group_id: UUID, checksum_sha256: str
    ) -> ImageSelectionCandidate | None: ...

    def next_candidate_order(self, run_id: UUID) -> int: ...

    def get_manual_decision(self, idempotency_key: UUID) -> ImageSelectionManualDecision | None: ...

    def list_manual_decisions(self, *, run_id: UUID) -> Sequence[ImageSelectionManualDecision]: ...

    def next_manual_revision(self, *, run_id: UUID, group_id: UUID) -> int: ...

    def save_manual_decision(
        self,
        *,
        group: ImageSelectionGroup,
        decision: ImageSelectionManualDecision,
    ) -> tuple[ImageSelectionGroup, ImageSelectionManualDecision]: ...

    def get_job_for_update(self, job_id: UUID) -> Job | None: ...

    def save_job(self, job: Job) -> Job: ...


class ImageSelectionService:
    def __init__(
        self,
        repository: ImageSelectionRepository,
        *,
        artifact_root: Path | None = None,
        browser_upload_root: Path | None = None,
        manual_file_store: ManualImageSelectionFileStore | None = None,
    ) -> None:
        self._repository = repository
        self._artifact_root = None if artifact_root is None else artifact_root.resolve()
        self._browser_upload_root = (
            None
            if browser_upload_root is None
            else browser_upload_root.resolve() / BROWSER_SELECTION_DIRECTORY
        )
        self._manual_file_store = manual_file_store or (
            None if artifact_root is None else ManualImageSelectionFileStore(artifact_root)
        )

    def create_run(
        self,
        *,
        game_id: UUID,
        source_selection_id: UUID,
        input_manifest_sha256: str,
        selector_fingerprint: str,
        sequence_direction: ImageSelectionSequenceDirection = (
            ImageSelectionSequenceDirection.ASCENDING
        ),
        first_sequence_number: int | None = None,
    ) -> tuple[ImageSelectionRun, bool]:
        if not self._repository.game_exists(game_id):
            raise ImageSelectionNotFoundError(
                "GAME_NOT_FOUND",
                "Game does not exist.",
                details={"gameId": str(game_id)},
            )
        existing = self._repository.find_run_by_identity(
            game_id=game_id,
            input_manifest_sha256=input_manifest_sha256,
            selector_fingerprint=selector_fingerprint,
            sequence_direction=sequence_direction,
            first_sequence_number=first_sequence_number,
        )
        if existing is not None:
            return existing, False
        run = create_image_selection_run(
            game_id=game_id,
            source_selection_id=source_selection_id,
            input_manifest_sha256=input_manifest_sha256,
            selector_fingerprint=selector_fingerprint,
            sequence_direction=sequence_direction,
            first_sequence_number=first_sequence_number,
        )
        return self._repository.add_run(run)

    def get_run(self, run_id: UUID) -> ImageSelectionRun:
        run = self._repository.get_run(run_id)
        if run is None:
            raise ImageSelectionNotFoundError(
                "IMAGE_SELECTION_NOT_FOUND",
                "Image selection run does not exist.",
                details={"runId": str(run_id)},
            )
        return run

    def list_runs(
        self,
        *,
        game_id: UUID,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[tuple[ImageSelectionRun, ...], int | None]:
        if offset < 0 or not 1 <= limit <= 100:
            raise ImageSelectionError(
                "IMAGE_SELECTION_CONFIGURATION_INVALID",
                "Run offset must be non-negative and limit must be between 1 and 100.",
            )
        if not self._repository.game_exists(game_id):
            raise ImageSelectionNotFoundError(
                "GAME_NOT_FOUND",
                "Game does not exist.",
                details={"gameId": str(game_id)},
            )
        values = tuple(
            self._repository.list_runs(
                game_id=game_id,
                offset=offset,
                limit=limit + 1,
            )
        )
        has_more = len(values) > limit
        return values[:limit], (offset + limit if has_more else None)

    def rerun(
        self,
        *,
        run_id: UUID,
        selector_fingerprint: str,
    ) -> tuple[ImageSelectionRun, bool]:
        source_run = self.get_run(run_id)
        if self._browser_upload_root is None:
            raise ImageSelectionConflictError(
                "IMAGE_SELECTION_SOURCE_REUSE_UNAVAILABLE",
                "The managed browser staging cannot be reused by this API process.",
            )
        source_root = (self._browser_upload_root / str(source_run.source_selection_id)).resolve()
        manifest = source_root / BROWSER_SELECTION_MANIFEST
        if (
            not source_root.is_relative_to(self._browser_upload_root)
            or not source_root.is_dir()
            or not manifest.is_file()
        ):
            raise ImageSelectionConflictError(
                "IMAGE_SELECTION_SOURCE_MISSING",
                "The previously uploaded image staging is no longer available.",
            )
        try:
            manifest_sha256 = hashlib.sha256(manifest.read_bytes()).hexdigest()
        except OSError as error:
            raise ImageSelectionConflictError(
                "IMAGE_SELECTION_SOURCE_MISSING",
                "The previously uploaded image staging cannot be read.",
            ) from error
        if manifest_sha256 != source_run.input_manifest_sha256:
            raise ImageSelectionConflictError(
                "IMAGE_SELECTION_INPUT_MANIFEST_CHANGED",
                "The previously uploaded image manifest has changed.",
            )
        rerun, created = self.create_run(
            game_id=source_run.game_id,
            source_selection_id=source_run.source_selection_id,
            input_manifest_sha256=source_run.input_manifest_sha256,
            selector_fingerprint=selector_fingerprint,
            sequence_direction=source_run.sequence_direction,
            first_sequence_number=source_run.first_sequence_number,
        )
        if created or rerun.job.status not in {
            JobStatus.CANCELLED,
            JobStatus.FAILED,
        }:
            return rerun, created

        locked_job = self._repository.get_job_for_update(rerun.job.id)
        if locked_job is None:
            raise ImageSelectionConflictError(
                "IMAGE_SELECTION_PERSISTENCE_CONFLICT",
                "The existing image-selection job could not be locked for restart.",
            )
        if locked_job.status in {JobStatus.CANCELLED, JobStatus.FAILED}:
            self._repository.save_job(requeue_job(locked_job))
        return self.get_run(rerun.id), False

    def list_groups(
        self,
        *,
        run_id: UUID,
        status: ImageSelectionGroupStatus | None,
        after_group_order: int,
        limit: int,
    ) -> ImageSelectionGroupPage:
        if after_group_order < -1 or not 1 <= limit <= IMAGE_SELECTION_GROUP_PAGE_MAX:
            raise ImageSelectionError(
                "IMAGE_SELECTION_CONFIGURATION_INVALID",
                "Group cursor must be at least -1 and limit must be between 1 and 100.",
            )
        self.get_run(run_id)
        values = tuple(
            self._repository.list_groups(
                run_id=run_id,
                status=status,
                after_group_order=after_group_order,
                limit=limit + 1,
            )
        )
        has_more = len(values) > limit
        items = values[:limit]
        return ImageSelectionGroupPage(
            items=items,
            next_after_group_order=(items[-1].group_order if has_more and items else None),
        )

    def list_group_candidates(
        self,
        *,
        run_id: UUID,
        group_id: UUID,
        limit: int = 20,
    ) -> Sequence[ImageSelectionCandidate]:
        if not 1 <= limit <= 500:
            raise ImageSelectionError(
                "IMAGE_SELECTION_CONFIGURATION_INVALID",
                "Candidate limit must be between 1 and 500.",
            )
        self.get_run(run_id)
        if self._repository.get_group(run_id=run_id, group_id=group_id) is None:
            raise ImageSelectionNotFoundError(
                "IMAGE_SELECTION_GROUP_NOT_FOUND",
                "Image selection group does not exist.",
                details={"groupId": str(group_id), "runId": str(run_id)},
            )
        return tuple(
            self._repository.list_candidates(
                run_id=run_id,
                group_id=group_id,
                limit=limit,
            )
        )

    def record_output(
        self,
        *,
        run_id: UUID,
        manifest_sha256: str,
        manifest_relative_path: str,
    ) -> ImageSelectionRun:
        run = record_image_selection_output(
            self.get_run(run_id),
            manifest_sha256=manifest_sha256,
            manifest_relative_path=manifest_relative_path,
        )
        return self._repository.save_run(run)

    def upload_manual_file(
        self,
        *,
        run_id: UUID,
        group_id: UUID,
        display_name: str,
        content: bytes,
    ) -> ImageSelectionCandidate:
        self.get_run(run_id)
        group = self._get_manual_group(run_id=run_id, group_id=group_id)
        if self._manual_file_store is None:
            raise ImageSelectionConflictError(
                "IMAGE_SELECTION_STORAGE_UNAVAILABLE",
                "Managed manual image storage is not configured.",
            )
        stored = self._manual_file_store.save(
            run_id=run_id,
            group_id=group.id,
            display_name=display_name,
            content=content,
        )
        existing = self._repository.find_candidate_by_checksum(
            run_id=run_id,
            group_id=group.id,
            checksum_sha256=stored.checksum_sha256,
        )
        if existing is not None:
            return existing
        candidate = ImageSelectionCandidate(
            id=uuid4(),
            run_id=run_id,
            group_id=group.id,
            order_index=self._repository.next_candidate_order(run_id),
            source_relative_path=stored.relative_path,
            checksum_sha256=stored.checksum_sha256,
            width=stored.width,
            height=stored.height,
            quality_metrics={
                "displayName": Path(display_name).name,
                "sizeBytes": stored.size_bytes,
                "source": "manual",
            },
            range_confidence=None,
            reason_codes=("manual_upload",),
            decision=ImageSelectionCandidateDecision.ELIGIBLE,
            created_at=datetime.now(UTC),
        )
        validate_candidate(
            order_index=candidate.order_index,
            source_relative_path=candidate.source_relative_path,
            checksum_sha256=candidate.checksum_sha256,
            width=candidate.width,
            height=candidate.height,
            range_confidence=candidate.range_confidence,
            decision=candidate.decision,
            group_id=candidate.group_id,
        )
        return self._repository.add_candidate(candidate)

    def approve_manual_file(
        self,
        *,
        run_id: UUID,
        group_id: UUID,
        candidate_id: UUID,
        idempotency_key: UUID,
        range_start: int | None,
        range_end: int | None,
    ) -> ImageSelectionManualApproval:
        run = self.get_run(run_id)
        locked_job = self._repository.get_job_for_update(run.job.id)
        if locked_job is None:
            raise ImageSelectionConflictError(
                "IMAGE_SELECTION_JOB_MISSING",
                "The image-selection job no longer exists.",
            )
        run = self.get_run(run_id)
        group = self._get_manual_group(run_id=run_id, group_id=group_id)
        candidate = self._repository.get_candidate(
            run_id=run_id,
            candidate_id=candidate_id,
        )
        if candidate is None:
            raise ImageSelectionNotFoundError(
                "IMAGE_SELECTION_CANDIDATE_NOT_FOUND",
                "The selected manual JPEG does not exist.",
            )
        existing = self._repository.get_manual_decision(idempotency_key)
        proposed_group, proposed = create_manual_decision(
            idempotency_key=idempotency_key,
            group=group,
            candidate=candidate,
            range_start=range_start,
            range_end=range_end,
            revision=(
                existing.revision
                if existing is not None
                else self._repository.next_manual_revision(
                    run_id=run_id,
                    group_id=group_id,
                )
            ),
        )
        if existing is not None:
            if existing.payload_sha256 != proposed.payload_sha256:
                raise ImageSelectionConflictError(
                    "IMAGE_SELECTION_IDEMPOTENCY_CONFLICT",
                    "The idempotency key was already used for another decision.",
                )
            replay_group = ImageSelectionGroup(
                id=group.id,
                run_id=group.run_id,
                group_order=group.group_order,
                range_start=existing.range_start,
                range_end=existing.range_end,
                fingerprint_sha256=group.fingerprint_sha256,
                board_count_consensus=group.board_count_consensus,
                status=ImageSelectionGroupStatus.MANUALLY_SELECTED,
                selected_candidate_id=existing.candidate_id,
                created_at=group.created_at,
                updated_at=existing.created_at,
            )
            self._resume_completed_manual_review(
                run_id=run_id,
                locked_job=locked_job,
            )
            return ImageSelectionManualApproval(replay_group, existing)
        for other in self._all_groups(run_id):
            if (
                other.id != group.id
                and other.status
                in {
                    ImageSelectionGroupStatus.AUTO_SELECTED,
                    ImageSelectionGroupStatus.MANUALLY_SELECTED,
                    ImageSelectionGroupStatus.MISSING_IMAGE,
                }
                and other.range_start == proposed_group.range_start
                and other.range_end == proposed_group.range_end
            ):
                raise ImageSelectionConflictError(
                    "IMAGE_SELECTION_RANGE_CONFLICT",
                    "Another selected group already uses this sequence range.",
                )
        saved_group, saved_decision = self._repository.save_manual_decision(
            group=proposed_group,
            decision=proposed,
        )
        if self._manual_file_store is not None:
            self._manual_file_store.write_decision_manifest(
                run_id=run_id,
                decisions=self._repository.list_manual_decisions(run_id=run_id),
            )
        self._reopen_published_run_after_manual_revision(
            run=run,
            locked_job=locked_job,
        )
        self._resume_completed_manual_review(
            run_id=run_id,
            locked_job=locked_job,
        )
        return ImageSelectionManualApproval(saved_group, saved_decision)

    def continue_without_image(
        self,
        *,
        run_id: UUID,
        group_id: UUID,
        idempotency_key: UUID,
        range_start: int | None,
        range_end: int | None,
    ) -> ImageSelectionManualApproval:
        run = self.get_run(run_id)
        locked_job = self._repository.get_job_for_update(run.job.id)
        if locked_job is None:
            raise ImageSelectionConflictError(
                "IMAGE_SELECTION_JOB_MISSING",
                "The image-selection job no longer exists.",
            )
        run = self.get_run(run_id)
        group = self._get_manual_group(run_id=run_id, group_id=group_id)
        existing = self._repository.get_manual_decision(idempotency_key)
        proposed_group, proposed = create_missing_image_decision(
            idempotency_key=idempotency_key,
            group=group,
            range_start=range_start,
            range_end=range_end,
            revision=(
                existing.revision
                if existing is not None
                else self._repository.next_manual_revision(
                    run_id=run_id,
                    group_id=group_id,
                )
            ),
        )
        if existing is not None:
            if existing.payload_sha256 != proposed.payload_sha256:
                raise ImageSelectionConflictError(
                    "IMAGE_SELECTION_IDEMPOTENCY_CONFLICT",
                    "The idempotency key was already used for another decision.",
                )
            replay_group = replace(
                group,
                range_start=existing.range_start,
                range_end=existing.range_end,
                status=ImageSelectionGroupStatus.MISSING_IMAGE,
                selected_candidate_id=None,
                updated_at=existing.created_at,
            )
            self._resume_completed_manual_review(
                run_id=run_id,
                locked_job=locked_job,
            )
            return ImageSelectionManualApproval(replay_group, existing)
        for other in self._all_groups(run_id):
            if (
                proposed_group.range_start is not None
                and other.id != group.id
                and other.status
                in {
                    ImageSelectionGroupStatus.AUTO_SELECTED,
                    ImageSelectionGroupStatus.MANUALLY_SELECTED,
                    ImageSelectionGroupStatus.MISSING_IMAGE,
                }
                and other.range_start == proposed_group.range_start
                and other.range_end == proposed_group.range_end
            ):
                raise ImageSelectionConflictError(
                    "IMAGE_SELECTION_RANGE_CONFLICT",
                    "Another resolved group already uses this sequence range.",
                )
        saved_group, saved_decision = self._repository.save_manual_decision(
            group=proposed_group,
            decision=proposed,
        )
        if self._manual_file_store is not None:
            self._manual_file_store.write_decision_manifest(
                run_id=run_id,
                decisions=self._repository.list_manual_decisions(run_id=run_id),
            )
        self._reopen_published_run_after_manual_revision(
            run=run,
            locked_job=locked_job,
        )
        self._resume_completed_manual_review(
            run_id=run_id,
            locked_job=locked_job,
        )
        return ImageSelectionManualApproval(saved_group, saved_decision)

    def get_manual_file(
        self,
        *,
        run_id: UUID,
        group_id: UUID,
        candidate_id: UUID,
    ) -> Path:
        self.get_run(run_id)
        candidate = self._repository.get_candidate(
            run_id=run_id,
            candidate_id=candidate_id,
        )
        if candidate is None or candidate.group_id != group_id:
            raise ImageSelectionNotFoundError(
                "IMAGE_SELECTION_CANDIDATE_NOT_FOUND",
                "The selected manual JPEG does not exist.",
            )
        if self._manual_file_store is None:
            raise ImageSelectionConflictError(
                "IMAGE_SELECTION_STORAGE_UNAVAILABLE",
                "Managed manual image storage is not configured.",
            )
        return self._manual_file_store.resolve(candidate)

    def get_candidate_file(
        self,
        *,
        run_id: UUID,
        group_id: UUID,
        candidate_id: UUID,
    ) -> tuple[Path, str]:
        run = self.get_run(run_id)
        candidate = self._repository.get_candidate(
            run_id=run_id,
            candidate_id=candidate_id,
        )
        if candidate is None or candidate.group_id != group_id:
            raise ImageSelectionNotFoundError(
                "IMAGE_SELECTION_CANDIDATE_NOT_FOUND",
                "The image-selection candidate JPEG does not exist.",
            )
        return self._resolve_candidate_path(run, candidate), str(
            candidate.quality_metrics.get("displayName")
            or Path(candidate.source_relative_path).name
        )

    def get_selected_group_file(
        self,
        *,
        run_id: UUID,
        group_id: UUID,
    ) -> tuple[Path, str]:
        run = self.get_run(run_id)
        group = self._repository.get_group(run_id=run_id, group_id=group_id)
        if (
            group is None
            or group.selected_candidate_id is None
            or group.range_start is None
            or group.range_end is None
            or group.status
            not in {
                ImageSelectionGroupStatus.AUTO_SELECTED,
                ImageSelectionGroupStatus.MANUALLY_SELECTED,
            }
        ):
            raise ImageSelectionNotFoundError(
                "IMAGE_SELECTION_GROUP_OUTPUT_NOT_READY",
                "The group does not have a selected JPEG with a sequence range yet.",
            )
        candidate = self._repository.get_candidate(
            run_id=run_id,
            candidate_id=group.selected_candidate_id,
        )
        if candidate is None or candidate.group_id != group.id:
            raise ImageSelectionNotFoundError(
                "IMAGE_SELECTION_CANDIDATE_NOT_FOUND",
                "The selected group JPEG does not exist.",
            )
        path = self._resolve_candidate_path(run, candidate)
        return path, f"seq_{group.range_start}-{group.range_end}.jpg"

    def _resolve_candidate_path(
        self,
        run: ImageSelectionRun,
        candidate: ImageSelectionCandidate,
    ) -> Path:
        if candidate.source_relative_path.startswith("data/working/is-manual/"):
            if self._manual_file_store is None:
                raise ImageSelectionConflictError(
                    "IMAGE_SELECTION_STORAGE_UNAVAILABLE",
                    "Managed manual image storage is not configured.",
                )
            return self._manual_file_store.resolve(candidate)
        else:
            if self._browser_upload_root is None:
                raise ImageSelectionConflictError(
                    "IMAGE_SELECTION_SOURCE_REUSE_UNAVAILABLE",
                    "The managed browser staging is unavailable.",
                )
            source_root = (self._browser_upload_root / str(run.source_selection_id)).resolve()
            relative_parts = PurePosixPath(candidate.source_relative_path).parts
            path = (source_root / Path(*relative_parts)).resolve()
            if not path.is_relative_to(source_root) or not path.is_file():
                raise ImageSelectionNotFoundError(
                    "IMAGE_SELECTION_CANDIDATE_NOT_FOUND",
                    "The selected group JPEG no longer exists in managed staging.",
                )
            return path

    def prepare_handoff(self, run_id: UUID) -> ImageSelectionHandoffSource:
        run = self.get_run(run_id)
        if (
            self._artifact_root is None
            or run.output_manifest_sha256 is None
            or run.output_manifest_relative_path is None
        ):
            raise ImageSelectionConflictError(
                "IMAGE_SELECTION_NOT_READY",
                "The image-selection run has no complete curated output.",
            )
        manifest_path = self._managed_path(run.output_manifest_relative_path)
        try:
            manifest = verify_curated_image_manifest(
                manifest_path.parent,
                expected_manifest_sha256=run.output_manifest_sha256,
                expected_run_id=run.id,
            )
        except (OSError, SelectionContractError) as error:
            raise ImageSelectionConflictError(
                "IMAGE_SELECTION_MANIFEST_MISMATCH",
                "The curated output manifest or one of its JPEG files changed.",
            ) from error
        if (
            manifest.input_manifest_sha256 != run.input_manifest_sha256
            or manifest.selector_fingerprint != run.selector_fingerprint
        ):
            raise ImageSelectionConflictError(
                "IMAGE_SELECTION_MANIFEST_MISMATCH",
                "The curated output provenance does not match the durable run.",
            )
        groups = self._all_groups(run_id)
        if not groups or any(
            group.status
            in {
                ImageSelectionGroupStatus.COLLECTING,
                ImageSelectionGroupStatus.MANUAL_REQUIRED,
            }
            for group in groups
        ):
            raise ImageSelectionConflictError(
                "IMAGE_SELECTION_NOT_READY",
                "Every non-duplicate group must be resolved before handoff.",
            )
        expected_groups = {
            group.group_order: (group.range_start, group.range_end)
            for group in groups
            if group.status
            in {
                ImageSelectionGroupStatus.AUTO_SELECTED,
                ImageSelectionGroupStatus.MANUALLY_SELECTED,
            }
        }
        manifest_groups = {
            entry.group_order: (entry.range_start, entry.range_end) for entry in manifest.entries
        }
        if expected_groups != manifest_groups:
            raise ImageSelectionConflictError(
                "IMAGE_SELECTION_MANIFEST_MISMATCH",
                "The curated output groups differ from the durable group decisions.",
            )
        return ImageSelectionHandoffSource(
            run=run,
            output_directory=manifest_path.parent,
            supported_file_count=len(manifest.entries),
        )

    def get_output(self, run_id: UUID) -> ImageSelectionOutput:
        source = self.prepare_handoff(run_id)
        assert source.run.output_manifest_sha256 is not None
        try:
            manifest = verify_curated_image_manifest(
                source.output_directory,
                expected_manifest_sha256=source.run.output_manifest_sha256,
                expected_run_id=source.run.id,
            )
        except (OSError, SelectionContractError) as error:
            raise ImageSelectionConflictError(
                "IMAGE_SELECTION_MANIFEST_MISMATCH",
                "The curated output manifest or one of its JPEG files changed.",
            ) from error
        return ImageSelectionOutput(
            run_id=source.run.id,
            manifest_sha256=manifest.checksum_sha256,
            files=tuple(
                ImageSelectionOutputFile(
                    file_name=_public_output_file_name(
                        entry.output_relative_path,
                        entry.range_start,
                        entry.range_end,
                    ),
                    group_order=entry.group_order,
                    range_start=entry.range_start,
                    range_end=entry.range_end,
                    checksum_sha256=entry.output_checksum_sha256,
                    size_bytes=entry.size_bytes,
                    reason_codes=entry.reason_codes,
                    selection_method=entry.selection_method,
                )
                for entry in manifest.entries
            ),
        )

    def get_output_file(self, run_id: UUID, file_name: str) -> Path:
        source = self.prepare_handoff(run_id)
        assert source.run.output_manifest_sha256 is not None
        assert source.run.output_manifest_relative_path is not None
        try:
            manifest = verify_curated_image_manifest(
                source.output_directory,
                expected_manifest_sha256=source.run.output_manifest_sha256,
                expected_run_id=source.run.id,
            )
        except (OSError, SelectionContractError) as error:
            raise ImageSelectionConflictError(
                "IMAGE_SELECTION_MANIFEST_MISMATCH",
                "The curated output manifest or one of its JPEG files changed.",
            ) from error
        for entry in manifest.entries:
            relative = PurePosixPath(entry.output_relative_path)
            if (
                _public_output_file_name(
                    entry.output_relative_path,
                    entry.range_start,
                    entry.range_end,
                )
                == file_name
            ):
                return self._managed_path(
                    str(PurePosixPath(source.run.output_manifest_relative_path).parent / relative)
                )
        raise ImageSelectionNotFoundError(
            "IMAGE_SELECTION_OUTPUT_FILE_NOT_FOUND",
            "The selected output JPEG does not exist.",
        )

    def _all_groups(self, run_id: UUID) -> tuple[ImageSelectionGroup, ...]:
        values: list[ImageSelectionGroup] = []
        after_group_order = -1
        while True:
            page = tuple(
                self._repository.list_groups(
                    run_id=run_id,
                    status=None,
                    after_group_order=after_group_order,
                    limit=IMAGE_SELECTION_GROUP_PAGE_MAX,
                )
            )
            values.extend(page)
            if len(page) < IMAGE_SELECTION_GROUP_PAGE_MAX:
                break
            after_group_order = page[-1].group_order
        return tuple(values)

    def _resume_completed_manual_review(
        self,
        *,
        run_id: UUID,
        locked_job: Job,
    ) -> None:
        if locked_job.status is not JobStatus.WAITING_FOR_REVIEW:
            return
        unresolved = {
            ImageSelectionGroupStatus.COLLECTING,
            ImageSelectionGroupStatus.MANUAL_REQUIRED,
        }
        if any(group.status in unresolved for group in self._all_groups(run_id)):
            return
        self._repository.save_job(requeue_job(locked_job))

    def _reopen_published_run_after_manual_revision(
        self,
        *,
        run: ImageSelectionRun,
        locked_job: Job,
    ) -> None:
        if run.output_manifest_sha256 is None:
            return
        if locked_job.status is not JobStatus.COMPLETED:
            raise ImageSelectionConflictError(
                "IMAGE_SELECTION_REVISION_CONFLICT",
                "A published selection can only be revised after its job completed.",
            )
        self._repository.invalidate_output(run.id)
        self._repository.save_job(reopen_completed_job_for_revision(locked_job))

    def _get_manual_group(self, *, run_id: UUID, group_id: UUID) -> ImageSelectionGroup:
        self.get_run(run_id)
        group = self._repository.get_group(run_id=run_id, group_id=group_id)
        if group is None:
            raise ImageSelectionNotFoundError(
                "IMAGE_SELECTION_GROUP_NOT_FOUND",
                "Image-selection group does not exist.",
            )
        if group.status not in {
            ImageSelectionGroupStatus.MANUAL_REQUIRED,
            ImageSelectionGroupStatus.MANUALLY_SELECTED,
            ImageSelectionGroupStatus.MISSING_IMAGE,
        }:
            raise ImageSelectionConflictError(
                "IMAGE_SELECTION_GROUP_NOT_MANUAL",
                "This group does not require a manual representative.",
            )
        return group

    def _managed_path(self, relative_path: str) -> Path:
        assert self._artifact_root is not None
        posix = PurePosixPath(relative_path)
        try:
            resolved = (self._artifact_root / Path(*posix.parts)).resolve(strict=True)
        except OSError as error:
            raise ImageSelectionConflictError(
                "IMAGE_SELECTION_MANIFEST_MISMATCH",
                "The curated output manifest is missing.",
            ) from error
        if not resolved.is_relative_to(self._artifact_root) or not resolved.is_file():
            raise ImageSelectionConflictError(
                "IMAGE_SELECTION_MANIFEST_MISMATCH",
                "The curated output manifest path is unsafe.",
            )
        return resolved


__all__ = [
    "ImageSelectionManualApproval",
    "ImageSelectionRepository",
    "ImageSelectionHandoffSource",
    "ImageSelectionService",
    "ManualImageSelectionFileStore",
]
