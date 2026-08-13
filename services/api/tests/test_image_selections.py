from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.application.image_imports import ImageFolderSelectionService
from game_predictor_api.application.image_selections import ImageSelectionService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.image_selections import (
    IMAGE_SELECTION_ORDERING_POLICY,
    ImageSelectionCandidate,
    ImageSelectionCandidateDecision,
    ImageSelectionConflictError,
    ImageSelectionError,
    ImageSelectionExecutionMode,
    ImageSelectionGroup,
    ImageSelectionGroupStatus,
    ImageSelectionManualDecision,
    ImageSelectionManualResolution,
    ImageSelectionRun,
    ImageSelectionSequenceDirection,
    safe_relative_path,
    validate_candidate,
    validate_image_selection_group,
)
from game_predictor_api.domain.jobs import Job, JobStatus, JobType
from game_predictor_api.main import create_app
from game_predictor_worker.images.selection.contracts import (
    CandidateDecision,
    CandidateResult,
    ImageQualityMetrics,
    ImageSelectionResult,
    ImageSelectionSource,
    SelectionGroupResult,
    SelectionGroupStatus,
    SelectorCheckpoint,
    SequenceRange,
)
from game_predictor_worker.images.selection.manifest import DEFAULT_SELECTOR_MANIFEST
from game_predictor_worker.images.selection.output import CuratedImageOutputPublisher
from PIL import Image


class MemoryImageSelectionRepository:
    def __init__(self, game_id: UUID) -> None:
        self.game_id = game_id
        self.runs: dict[UUID, ImageSelectionRun] = {}
        self.groups: list[ImageSelectionGroup] = []
        self.candidates: list[ImageSelectionCandidate] = []
        self.manual_decisions: list[ImageSelectionManualDecision] = []
        self.handoff_run_ids: set[UUID] = set()

    def game_exists(self, game_id: UUID) -> bool:
        return game_id == self.game_id

    def find_run_by_identity(
        self,
        *,
        game_id: UUID,
        input_manifest_sha256: str,
        selector_fingerprint: str,
        sequence_direction: ImageSelectionSequenceDirection,
        first_sequence_number: int | None,
    ) -> ImageSelectionRun | None:
        return next(
            (
                run
                for run in self.runs.values()
                if run.game_id == game_id
                and run.execution_mode is ImageSelectionExecutionMode.FULL
                and run.input_manifest_sha256 == input_manifest_sha256
                and run.selector_fingerprint == selector_fingerprint
                and run.sequence_direction is sequence_direction
                and run.first_sequence_number == first_sequence_number
            ),
            None,
        )

    def find_recovery_run(
        self,
        *,
        source_run_id: UUID,
        selector_fingerprint: str,
        source_snapshot_sha256: str,
    ) -> ImageSelectionRun | None:
        return next(
            (
                run
                for run in self.runs.values()
                if run.execution_mode is ImageSelectionExecutionMode.RANGE_RECOVERY
                and run.source_run_id == source_run_id
                and run.selector_fingerprint == selector_fingerprint
                and run.source_snapshot_sha256 == source_snapshot_sha256
            ),
            None,
        )

    def recovery_snapshot(self, run_id: UUID) -> tuple[str, int, int, int]:
        groups = sorted(
            (group for group in self.groups if group.run_id == run_id),
            key=lambda group: group.group_order,
        )
        problem = [
            group for group in groups if group.status is ImageSelectionGroupStatus.RANGE_REQUIRED
        ]
        payload = [
            (group.group_order, group.status.value, group.range_start, group.range_end)
            for group in groups
        ]
        checksum = hashlib.sha256(
            json.dumps(payload, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        problem_ids = {group.id for group in problem}
        candidate_count = sum(
            candidate.run_id == run_id and candidate.group_id in problem_ids
            for candidate in self.candidates
        )
        block_count = sum(
            index == 0
            or problem[index - 1].group_order + 1 != group.group_order
            for index, group in enumerate(problem)
        )
        return checksum, len(problem), candidate_count, block_count

    def has_handoff(self, run_id: UUID) -> bool:
        return run_id in self.handoff_run_ids

    def add_run(self, run: ImageSelectionRun) -> tuple[ImageSelectionRun, bool]:
        existing = (
            self.find_run_by_identity(
                game_id=run.game_id,
                input_manifest_sha256=run.input_manifest_sha256,
                selector_fingerprint=run.selector_fingerprint,
                sequence_direction=run.sequence_direction,
                first_sequence_number=run.first_sequence_number,
            )
            if run.execution_mode is ImageSelectionExecutionMode.FULL
            else self.find_recovery_run(
                source_run_id=run.source_run_id or UUID(int=0),
                selector_fingerprint=run.selector_fingerprint,
                source_snapshot_sha256=run.source_snapshot_sha256 or "",
            )
        )
        if existing is not None:
            return existing, False
        self.runs[run.id] = run
        return run, True

    def get_run(self, run_id: UUID) -> ImageSelectionRun | None:
        return self.runs.get(run_id)

    def list_runs(
        self,
        *,
        game_id: UUID,
        offset: int,
        limit: int,
    ) -> Sequence[ImageSelectionRun]:
        values = sorted(
            (run for run in self.runs.values() if run.game_id == game_id),
            key=lambda run: (run.created_at, str(run.id)),
            reverse=True,
        )
        return tuple(values[offset : offset + limit])

    def get_run_sequence_range(self, run_id: UUID) -> tuple[int, int] | None:
        ranges = [
            (group.range_start, group.range_end)
            for group in self.groups
            if group.run_id == run_id
            and group.range_start is not None
            and group.range_end is not None
        ]
        if not ranges:
            return None
        return min(value[0] for value in ranges), max(value[1] for value in ranges)

    def save_run(self, run: ImageSelectionRun) -> ImageSelectionRun:
        self.runs[run.id] = run
        return run

    def invalidate_output(self, run_id: UUID) -> ImageSelectionRun:
        run = self.runs[run_id]
        invalidated = replace(
            run,
            output_manifest_sha256=None,
            output_manifest_relative_path=None,
        )
        self.runs[run_id] = invalidated
        return invalidated

    def get_job_for_update(self, job_id: UUID) -> Job | None:
        return next(
            (run.job for run in self.runs.values() if run.job.id == job_id),
            None,
        )

    def save_job(self, job: Job) -> Job:
        for run_id, run in self.runs.items():
            if run.job.id == job.id:
                self.runs[run_id] = replace(run, job=job)
                return job
        raise AssertionError("job missing")

    def list_groups(
        self,
        *,
        run_id: UUID,
        status: ImageSelectionGroupStatus | None,
        after_group_order: int,
        limit: int,
    ) -> Sequence[ImageSelectionGroup]:
        values = (
            group
            for group in self.groups
            if group.run_id == run_id
            and group.group_order > after_group_order
            and (status is None or group.status is status)
        )
        return tuple(sorted(values, key=lambda group: group.group_order))[:limit]

    def add_group(self, group: ImageSelectionGroup) -> ImageSelectionGroup:
        self.groups.append(group)
        return group

    def add_candidate(
        self,
        candidate: ImageSelectionCandidate,
    ) -> ImageSelectionCandidate:
        self.candidates.append(candidate)
        return candidate

    def get_group(self, *, run_id: UUID, group_id: UUID) -> ImageSelectionGroup | None:
        return next(
            (group for group in self.groups if group.run_id == run_id and group.id == group_id),
            None,
        )

    def get_candidate(self, *, run_id: UUID, candidate_id: UUID) -> ImageSelectionCandidate | None:
        return next(
            (
                candidate
                for candidate in self.candidates
                if candidate.run_id == run_id and candidate.id == candidate_id
            ),
            None,
        )

    def list_candidates(
        self,
        *,
        run_id: UUID,
        group_id: UUID,
        limit: int,
    ) -> Sequence[ImageSelectionCandidate]:
        values = (
            candidate
            for candidate in self.candidates
            if candidate.run_id == run_id and candidate.group_id == group_id
        )
        return tuple(sorted(values, key=lambda candidate: candidate.order_index))[:limit]

    def find_candidate_by_checksum(
        self, *, run_id: UUID, group_id: UUID, checksum_sha256: str
    ) -> ImageSelectionCandidate | None:
        return next(
            (
                candidate
                for candidate in self.candidates
                if candidate.run_id == run_id
                and candidate.group_id == group_id
                and candidate.checksum_sha256 == checksum_sha256
                and "manual_upload" in candidate.reason_codes
            ),
            None,
        )

    def next_candidate_order(self, run_id: UUID) -> int:
        orders = [item.order_index for item in self.candidates if item.run_id == run_id]
        return max(orders, default=-1) + 1

    def get_manual_decision(self, idempotency_key: UUID) -> ImageSelectionManualDecision | None:
        return next(
            (item for item in self.manual_decisions if item.idempotency_key == idempotency_key),
            None,
        )

    def list_manual_decisions(self, *, run_id: UUID) -> Sequence[ImageSelectionManualDecision]:
        return tuple(item for item in self.manual_decisions if item.run_id == run_id)

    def next_manual_revision(self, *, run_id: UUID, group_id: UUID) -> int:
        revisions = [
            item.revision
            for item in self.manual_decisions
            if item.run_id == run_id and item.group_id == group_id
        ]
        return max(revisions, default=0) + 1

    def save_manual_decision(
        self,
        *,
        group: ImageSelectionGroup,
        decision: ImageSelectionManualDecision,
    ) -> tuple[ImageSelectionGroup, ImageSelectionManualDecision]:
        for index, existing in enumerate(self.groups):
            if existing.id == group.id and existing.run_id == group.run_id:
                self.groups[index] = group
                break
        for index, candidate in enumerate(self.candidates):
            if candidate.run_id != group.run_id or candidate.group_id != group.id:
                continue
            expected = candidate.decision
            if decision.resolution is ImageSelectionManualResolution.SELECTED_IMAGE:
                expected = (
                    ImageSelectionCandidateDecision.SELECTED_MANUAL
                    if candidate.id == decision.candidate_id
                    else (
                        ImageSelectionCandidateDecision.ELIGIBLE
                        if candidate.decision is ImageSelectionCandidateDecision.SELECTED_MANUAL
                        else candidate.decision
                    )
                )
            elif decision.resolution is ImageSelectionManualResolution.RANGE_CONFIRMED:
                expected = (
                    ImageSelectionCandidateDecision.SELECTED_AUTOMATIC
                    if candidate.id == decision.candidate_id
                    else (
                        ImageSelectionCandidateDecision.ELIGIBLE
                        if candidate.decision
                        is ImageSelectionCandidateDecision.SELECTED_AUTOMATIC
                        else candidate.decision
                    )
                )
            self.candidates[index] = ImageSelectionCandidate(
                id=candidate.id,
                run_id=candidate.run_id,
                group_id=candidate.group_id,
                order_index=candidate.order_index,
                source_relative_path=candidate.source_relative_path,
                checksum_sha256=candidate.checksum_sha256,
                width=candidate.width,
                height=candidate.height,
                quality_metrics=candidate.quality_metrics,
                range_confidence=candidate.range_confidence,
                reason_codes=candidate.reason_codes,
                decision=expected,
                created_at=candidate.created_at,
            )
        self.manual_decisions.append(decision)
        return group, decision


class FakeAttestedPhotoSelection:
    def create_image_selection_run(
        self,
        service: ImageSelectionService,
        *,
        game_id: UUID,
        selection_token: str,
        selector_fingerprint: str,
        sequence_direction: ImageSelectionSequenceDirection,
        first_sequence_number: int | None,
    ) -> tuple[ImageSelectionRun, bool]:
        assert selection_token == "s" * 32
        return service.create_run(
            game_id=game_id,
            source_selection_id=UUID("00000000-0000-0000-0000-000000000151"),
            input_manifest_sha256="1" * 64,
            selector_fingerprint=selector_fingerprint,
            sequence_direction=sequence_direction,
            first_sequence_number=first_sequence_number,
        )


def _group(
    run_id: UUID,
    group_order: int,
    *,
    status: ImageSelectionGroupStatus = ImageSelectionGroupStatus.COLLECTING,
) -> ImageSelectionGroup:
    now = datetime(2026, 8, 2, tzinfo=UTC)
    return ImageSelectionGroup(
        id=uuid4(),
        run_id=run_id,
        group_order=group_order,
        range_start=None,
        range_end=None,
        fingerprint_sha256=None,
        board_count_consensus=None,
        status=status,
        selected_candidate_id=None,
        created_at=now,
        updated_at=now,
    )


def _manual_candidate(
    run_id: UUID,
    group_id: UUID,
    order_index: int,
) -> ImageSelectionCandidate:
    return ImageSelectionCandidate(
        id=uuid4(),
        run_id=run_id,
        group_id=group_id,
        order_index=order_index,
        source_relative_path=f"manual/{order_index}.jpg",
        checksum_sha256=f"{order_index + 1:064x}",
        width=1280,
        height=720,
        quality_metrics={"displayName": f"manual-{order_index}.jpg"},
        range_confidence=None,
        reason_codes=("manual_upload",),
        decision=ImageSelectionCandidateDecision.ELIGIBLE,
        created_at=datetime(2026, 8, 3, tzinfo=UTC),
    )


def test_create_run_is_idempotent_for_game_manifest_and_selector() -> None:
    game_id = uuid4()
    repository = MemoryImageSelectionRepository(game_id)
    service = ImageSelectionService(repository)

    first, first_created = service.create_run(
        game_id=game_id,
        source_selection_id=uuid4(),
        input_manifest_sha256="a" * 64,
        selector_fingerprint="b" * 64,
    )
    repeated, repeated_created = service.create_run(
        game_id=game_id,
        source_selection_id=uuid4(),
        input_manifest_sha256="a" * 64,
        selector_fingerprint="b" * 64,
    )

    assert first_created is True
    assert repeated_created is False
    assert repeated.id == first.id
    assert first.job.job_type is JobType.IMAGE_SELECTION
    assert first.ordering_policy == IMAGE_SELECTION_ORDERING_POLICY
    assert first.job.input_payload == {
        "schema_version": 1,
        "source_selection_id": str(first.source_selection_id),
        "input_manifest_sha256": "a" * 64,
        "selector_fingerprint": "b" * 64,
        "contract_version": 1,
        "sequence_direction": "ascending",
        "first_sequence_number": None,
        "execution_mode": "full",
        "source_run_id": None,
        "source_snapshot_sha256": None,
    }


def test_run_history_and_staged_candidate_preview_are_available_after_restart(
    tmp_path: Path,
) -> None:
    game_id = uuid4()
    source_selection_id = uuid4()
    browser_upload_root = tmp_path / "staging"
    source_root = browser_upload_root / "browser-selections" / str(source_selection_id)
    source_root.mkdir(parents=True)
    image_path = source_root / "00000001.jpg"
    Image.new("RGB", (120, 80), (240, 180, 20)).save(image_path, format="JPEG")
    content = image_path.read_bytes()
    repository = MemoryImageSelectionRepository(game_id)
    service = ImageSelectionService(
        repository,
        browser_upload_root=browser_upload_root,
    )
    run, _created = service.create_run(
        game_id=game_id,
        source_selection_id=source_selection_id,
        input_manifest_sha256="a" * 64,
        selector_fingerprint=DEFAULT_SELECTOR_MANIFEST.fingerprint,
    )
    group = replace(
        _group(run.id, 0, status=ImageSelectionGroupStatus.MANUAL_REQUIRED),
        range_start=1,
        range_end=9,
    )
    candidate = ImageSelectionCandidate(
        id=uuid4(),
        run_id=run.id,
        group_id=group.id,
        order_index=0,
        source_relative_path="00000001.jpg",
        checksum_sha256=hashlib.sha256(content).hexdigest(),
        width=120,
        height=80,
        quality_metrics={"displayName": "camera-0001.jpg", "groupSourceCount": 1},
        range_confidence=None,
        reason_codes=("REPRESENTATIVE_RANGE_UNKNOWN",),
        decision=ImageSelectionCandidateDecision.ELIGIBLE,
        created_at=datetime(2026, 8, 9, tzinfo=UTC),
    )
    repository.groups.append(group)
    repository.candidates.append(candidate)
    client = TestClient(
        create_app(
            ApiSettings.from_environment(),
            image_selection_service_dependency=lambda: service,
        )
    )

    with client:
        history = client.get(
            "/api/v1/admin/image-selections",
            params={"gameId": str(game_id), "limit": 20},
        )
        preview = client.get(
            f"/api/v1/admin/image-selections/{run.id}/groups/{group.id}/candidates/{candidate.id}/file"
        )

    assert history.status_code == 200, history.text
    assert [item["id"] for item in history.json()["items"]] == [str(run.id)]
    assert history.json()["items"][0]["selectorVersion"] == "fast-image-selector-v10.11"
    assert history.json()["items"][0]["sequenceRangeStart"] == 1
    assert history.json()["items"][0]["sequenceRangeEnd"] == 9
    assert history.json()["nextOffset"] is None
    assert preview.status_code == 200, preview.text
    assert preview.content == content


def test_rerun_reuses_unchanged_browser_staging_and_is_idempotent(
    tmp_path: Path,
) -> None:
    game_id = uuid4()
    source_selection_id = uuid4()
    browser_upload_root = tmp_path / "staging"
    source_root = browser_upload_root / "browser-selections" / str(source_selection_id)
    source_root.mkdir(parents=True)
    manifest_content = b'{"files":[],"schemaVersion":1}'
    (source_root / "_browser_manifest.json").write_bytes(manifest_content)
    manifest_sha256 = hashlib.sha256(manifest_content).hexdigest()
    repository = MemoryImageSelectionRepository(game_id)
    service = ImageSelectionService(
        repository,
        browser_upload_root=browser_upload_root,
    )
    original, _created = service.create_run(
        game_id=game_id,
        source_selection_id=source_selection_id,
        input_manifest_sha256=manifest_sha256,
        selector_fingerprint="1" * 64,
        first_sequence_number=1,
    )

    rerun, created = service.rerun(
        run_id=original.id,
        selector_fingerprint="2" * 64,
    )
    repeated, repeated_created = service.rerun(
        run_id=original.id,
        selector_fingerprint="2" * 64,
    )

    assert created is True
    assert repeated_created is False
    assert repeated.id == rerun.id
    assert rerun.id != original.id
    assert rerun.source_selection_id == original.source_selection_id
    assert rerun.input_manifest_sha256 == original.input_manifest_sha256
    assert rerun.selector_fingerprint == "2" * 64
    assert original.selector_fingerprint == "1" * 64


def test_range_recovery_preview_and_creation_are_snapshot_idempotent(
    tmp_path: Path,
) -> None:
    game_id = uuid4()
    source_selection_id = uuid4()
    browser_upload_root = tmp_path / "staging"
    source_root = browser_upload_root / "browser-selections" / str(source_selection_id)
    source_root.mkdir(parents=True)
    manifest_content = b'{"files":[],"schemaVersion":1}'
    (source_root / "_browser_manifest.json").write_bytes(manifest_content)
    repository = MemoryImageSelectionRepository(game_id)
    service = ImageSelectionService(
        repository,
        browser_upload_root=browser_upload_root,
    )
    source, _ = service.create_run(
        game_id=game_id,
        source_selection_id=source_selection_id,
        input_manifest_sha256=hashlib.sha256(manifest_content).hexdigest(),
        selector_fingerprint="1" * 64,
        first_sequence_number=1,
    )
    source = replace(
        source,
        job=replace(source.job, status=JobStatus.WAITING_FOR_REVIEW),
    )
    repository.runs[source.id] = source
    group = _group(source.id, 0, status=ImageSelectionGroupStatus.RANGE_REQUIRED)
    candidate = _manual_candidate(source.id, group.id, 0)
    repository.groups.append(group)
    repository.candidates.append(candidate)

    client = TestClient(
        create_app(
            ApiSettings.from_environment(),
            image_selection_service_dependency=lambda: service,
        )
    )
    with client:
        preview_response = client.get(
            f"/api/v1/admin/image-selections/{source.id}/range-recovery-preview"
        )
        assert preview_response.status_code == 200, preview_response.text
        preview = preview_response.json()
        first = client.post(
            f"/api/v1/admin/image-selections/{source.id}/recover-ranges",
            json={"expectedSourceSnapshotSha256": preview["sourceSnapshotSha256"]},
        )
        repeated = client.post(
            f"/api/v1/admin/image-selections/{source.id}/recover-ranges",
            json={"expectedSourceSnapshotSha256": preview["sourceSnapshotSha256"]},
        )

    assert preview["problemGroupCount"] == 1
    assert preview["candidateCount"] == 1
    assert preview["blockCount"] == 1
    assert preview["selectorVersion"] == "fast-image-selector-v10.11"
    assert first.status_code == 200, first.text
    assert repeated.status_code == 200, repeated.text
    assert first.json()["created"] is True
    assert repeated.json()["created"] is False
    assert repeated.json()["run"]["id"] == first.json()["run"]["id"]
    assert first.json()["run"]["executionMode"] == "range_recovery"
    assert first.json()["run"]["sourceRunId"] == str(source.id)
    assert repository.runs[source.id] == source


def test_range_recovery_rejects_a_stale_preview(tmp_path: Path) -> None:
    game_id = uuid4()
    source_selection_id = uuid4()
    browser_upload_root = tmp_path / "staging"
    source_root = browser_upload_root / "browser-selections" / str(source_selection_id)
    source_root.mkdir(parents=True)
    manifest_content = b'{"files":[],"schemaVersion":1}'
    (source_root / "_browser_manifest.json").write_bytes(manifest_content)
    repository = MemoryImageSelectionRepository(game_id)
    service = ImageSelectionService(repository, browser_upload_root=browser_upload_root)
    source, _ = service.create_run(
        game_id=game_id,
        source_selection_id=source_selection_id,
        input_manifest_sha256=hashlib.sha256(manifest_content).hexdigest(),
        selector_fingerprint="1" * 64,
        first_sequence_number=1,
    )
    repository.runs[source.id] = replace(
        source,
        job=replace(source.job, status=JobStatus.WAITING_FOR_REVIEW),
    )
    repository.groups.append(
        _group(source.id, 0, status=ImageSelectionGroupStatus.RANGE_REQUIRED)
    )
    stale = service.preview_range_recovery(source.id)
    repository.groups[0] = replace(repository.groups[0], range_start=1, range_end=9)

    with pytest.raises(ImageSelectionConflictError) as raised:
        service.recover_ranges(
            run_id=source.id,
            expected_source_snapshot_sha256=stale.source_snapshot_sha256,
        )

    assert raised.value.code == "IMAGE_SELECTION_RECOVERY_SOURCE_CHANGED"


def test_rerun_can_add_required_first_sequence_to_historical_run(tmp_path: Path) -> None:
    game_id = uuid4()
    source_selection_id = uuid4()
    browser_upload_root = tmp_path / "staging"
    source_root = browser_upload_root / "browser-selections" / str(source_selection_id)
    source_root.mkdir(parents=True)
    manifest_content = b'{"files":[],"schemaVersion":1}'
    (source_root / "_browser_manifest.json").write_bytes(manifest_content)
    repository = MemoryImageSelectionRepository(game_id)
    service = ImageSelectionService(repository, browser_upload_root=browser_upload_root)
    historical, _created = service.create_run(
        game_id=game_id,
        source_selection_id=source_selection_id,
        input_manifest_sha256=hashlib.sha256(manifest_content).hexdigest(),
        selector_fingerprint="1" * 64,
    )

    rerun, created = service.rerun(
        run_id=historical.id,
        selector_fingerprint="2" * 64,
        first_sequence_number=7300,
    )

    assert created is True
    assert rerun.first_sequence_number == 7300
    assert historical.first_sequence_number is None


@pytest.mark.parametrize("terminal_status", [JobStatus.CANCELLED, JobStatus.FAILED])
def test_rerun_requeues_existing_terminal_selector_run_from_checkpoint(
    tmp_path: Path,
    terminal_status: JobStatus,
) -> None:
    game_id = uuid4()
    source_selection_id = uuid4()
    browser_upload_root = tmp_path / "staging"
    source_root = browser_upload_root / "browser-selections" / str(source_selection_id)
    source_root.mkdir(parents=True)
    manifest_content = b'{"files":[],"schemaVersion":1}'
    (source_root / "_browser_manifest.json").write_bytes(manifest_content)
    manifest_sha256 = hashlib.sha256(manifest_content).hexdigest()
    repository = MemoryImageSelectionRepository(game_id)
    service = ImageSelectionService(
        repository,
        browser_upload_root=browser_upload_root,
    )
    original, _created = service.create_run(
        game_id=game_id,
        source_selection_id=source_selection_id,
        input_manifest_sha256=manifest_sha256,
        selector_fingerprint="2" * 64,
        first_sequence_number=1,
    )
    finished_at = datetime(2026, 8, 4, 15, 53, tzinfo=UTC)
    repository.runs[original.id] = replace(
        original,
        job=replace(
            original.job,
            status=terminal_status,
            stage="image_selection:scanning",
            progress_current=2_016,
            progress_total=32_079,
            checkpoint_payload={"schema_version": 1, "next_order_index": 2_016},
            finished_at=finished_at,
            cancel_requested_at=(finished_at if terminal_status is JobStatus.CANCELLED else None),
            error_code=(
                "IMAGE_SELECTION_SCAN_FAILED" if terminal_status is JobStatus.FAILED else None
            ),
            error_message=(
                "The selector stopped." if terminal_status is JobStatus.FAILED else None
            ),
        ),
    )

    resumed, created = service.rerun(
        run_id=original.id,
        selector_fingerprint="2" * 64,
    )

    assert created is False
    assert resumed.id == original.id
    assert resumed.job.status is JobStatus.CREATED
    assert resumed.job.progress_current == 2_016
    assert resumed.job.progress_total == 32_079
    assert resumed.job.checkpoint_payload == {
        "schema_version": 1,
        "next_order_index": 2_016,
    }
    assert resumed.job.finished_at is None
    assert resumed.job.cancel_requested_at is None
    assert resumed.job.error_code is None
    assert resumed.job.error_message is None


def test_rerun_rejects_missing_or_changed_browser_staging(tmp_path: Path) -> None:
    game_id = uuid4()
    source_selection_id = uuid4()
    browser_upload_root = tmp_path / "staging"
    repository = MemoryImageSelectionRepository(game_id)
    service = ImageSelectionService(
        repository,
        browser_upload_root=browser_upload_root,
    )
    original, _created = service.create_run(
        game_id=game_id,
        source_selection_id=source_selection_id,
        input_manifest_sha256="3" * 64,
        selector_fingerprint="4" * 64,
        first_sequence_number=1,
    )

    with pytest.raises(ImageSelectionConflictError) as missing:
        service.rerun(run_id=original.id, selector_fingerprint="5" * 64)

    source_root = browser_upload_root / "browser-selections" / str(source_selection_id)
    source_root.mkdir(parents=True)
    (source_root / "_browser_manifest.json").write_text("changed", encoding="utf-8")
    with pytest.raises(ImageSelectionConflictError) as changed:
        service.rerun(run_id=original.id, selector_fingerprint="5" * 64)

    assert missing.value.code == "IMAGE_SELECTION_SOURCE_MISSING"
    assert changed.value.code == "IMAGE_SELECTION_INPUT_MANIFEST_CHANGED"


def test_group_page_is_cursor_bounded_and_filterable() -> None:
    game_id = uuid4()
    repository = MemoryImageSelectionRepository(game_id)
    service = ImageSelectionService(repository)
    run, _created = service.create_run(
        game_id=game_id,
        source_selection_id=uuid4(),
        input_manifest_sha256="c" * 64,
        selector_fingerprint="d" * 64,
    )
    repository.groups.extend(
        [
            _group(run.id, 0),
            _group(run.id, 1, status=ImageSelectionGroupStatus.MANUAL_REQUIRED),
            _group(run.id, 2),
        ]
    )

    first_page = service.list_groups(
        run_id=run.id,
        status=None,
        after_group_order=-1,
        limit=2,
    )
    second_page = service.list_groups(
        run_id=run.id,
        status=None,
        after_group_order=first_page.next_after_group_order or 0,
        limit=2,
    )
    manual = service.list_groups(
        run_id=run.id,
        status=ImageSelectionGroupStatus.MANUAL_REQUIRED,
        after_group_order=-1,
        limit=10,
    )

    assert [item.group_order for item in first_page.items] == [0, 1]
    assert first_page.next_after_group_order == 1
    assert [item.group_order for item in second_page.items] == [2]
    assert second_page.next_after_group_order is None
    assert [item.group_order for item in manual.items] == [1]


def test_last_manual_decision_requeues_the_waiting_job_exactly_once() -> None:
    game_id = uuid4()
    repository = MemoryImageSelectionRepository(game_id)
    service = ImageSelectionService(repository)
    run, _created = service.create_run(
        game_id=game_id,
        source_selection_id=uuid4(),
        input_manifest_sha256="c" * 64,
        selector_fingerprint="d" * 64,
    )
    checkpoint = {"workflow": "image_selection", "next_order_index": 32}
    waiting_job = replace(
        run.job,
        status=JobStatus.WAITING_FOR_REVIEW,
        stage="image_selection:manual_review",
        progress_current=32,
        progress_total=32,
        review_count=2,
        checkpoint_payload=checkpoint,
    )
    repository.runs[run.id] = replace(run, job=waiting_job)
    first_group = _group(
        run.id,
        0,
        status=ImageSelectionGroupStatus.MANUAL_REQUIRED,
    )
    second_group = _group(
        run.id,
        1,
        status=ImageSelectionGroupStatus.MANUAL_REQUIRED,
    )
    first_candidate = _manual_candidate(run.id, first_group.id, 0)
    second_candidate = _manual_candidate(run.id, second_group.id, 1)
    repository.groups.extend((first_group, second_group))
    repository.candidates.extend((first_candidate, second_candidate))

    service.approve_manual_file(
        run_id=run.id,
        group_id=first_group.id,
        candidate_id=first_candidate.id,
        idempotency_key=uuid4(),
        range_start=1,
        range_end=9,
    )

    after_first = repository.get_run(run.id)
    assert after_first is not None
    assert after_first.job.status is JobStatus.WAITING_FOR_REVIEW

    final_idempotency_key = uuid4()
    service.approve_manual_file(
        run_id=run.id,
        group_id=second_group.id,
        candidate_id=second_candidate.id,
        idempotency_key=final_idempotency_key,
        range_start=10,
        range_end=18,
    )
    service.approve_manual_file(
        run_id=run.id,
        group_id=second_group.id,
        candidate_id=second_candidate.id,
        idempotency_key=final_idempotency_key,
        range_start=10,
        range_end=18,
    )

    resumed = repository.get_run(run.id)
    assert resumed is not None
    assert resumed.job.status is JobStatus.CREATED
    assert resumed.job.checkpoint_payload == checkpoint
    assert resumed.job.progress_current == 32
    assert resumed.job.review_count == 2
    assert len(repository.manual_decisions) == 2


def test_unknown_group_can_be_skipped_without_range_and_requeues_without_jpeg() -> None:
    game_id = uuid4()
    repository = MemoryImageSelectionRepository(game_id)
    service = ImageSelectionService(repository)
    run, _created = service.create_run(
        game_id=game_id,
        source_selection_id=uuid4(),
        input_manifest_sha256="e" * 64,
        selector_fingerprint="f" * 64,
    )
    waiting_job = replace(
        run.job,
        status=JobStatus.WAITING_FOR_REVIEW,
        stage="image_selection:manual_review",
        review_count=1,
    )
    repository.runs[run.id] = replace(run, job=waiting_job)
    group = _group(run.id, 0, status=ImageSelectionGroupStatus.MANUAL_REQUIRED)
    repository.groups.append(group)
    client = TestClient(
        create_app(
            ApiSettings.from_environment(),
            image_selection_service_dependency=lambda: service,
        )
    )
    key = uuid4()
    command = {"idempotencyKey": str(key)}

    with client:
        resolved = client.post(
            f"/api/v1/admin/image-selections/{run.id}/groups/{group.id}/continue-without-image",
            json=command,
        )
        replay = client.post(
            f"/api/v1/admin/image-selections/{run.id}/groups/{group.id}/continue-without-image",
            json=command,
        )

    assert resolved.status_code == 200, resolved.text
    assert replay.json() == resolved.json()
    assert resolved.json()["group"]["status"] == "missing_image"
    assert resolved.json()["group"]["selectedCandidateId"] is None
    assert resolved.json()["decision"]["resolution"] == "missing_image"
    assert resolved.json()["decision"]["candidateId"] is None
    assert resolved.json()["group"]["rangeStart"] is None
    assert resolved.json()["group"]["rangeEnd"] is None
    assert resolved.json()["decision"]["rangeStart"] is None
    assert resolved.json()["decision"]["rangeEnd"] is None
    assert repository.get_run(run.id).job.status is JobStatus.CREATED
    assert len(repository.manual_decisions) == 1


def test_manual_group_can_be_discarded_when_another_group_owns_the_same_range() -> None:
    game_id = uuid4()
    repository = MemoryImageSelectionRepository(game_id)
    service = ImageSelectionService(repository)
    run, _created = service.create_run(
        game_id=game_id,
        source_selection_id=uuid4(),
        input_manifest_sha256="d" * 64,
        selector_fingerprint="e" * 64,
    )
    repository.runs[run.id] = replace(
        run,
        job=replace(
            run.job,
            status=JobStatus.WAITING_FOR_REVIEW,
            stage="image_selection:manual_review",
            review_count=1,
        ),
    )
    existing = replace(
        _group(run.id, 0, status=ImageSelectionGroupStatus.AUTO_SELECTED),
        range_start=1,
        range_end=9,
    )
    duplicate = replace(
        _group(run.id, 1, status=ImageSelectionGroupStatus.MANUAL_REQUIRED),
        range_start=1,
        range_end=9,
    )
    repository.groups.extend((existing, duplicate))
    client = TestClient(
        create_app(
            ApiSettings.from_environment(),
            image_selection_service_dependency=lambda: service,
        )
    )
    key = uuid4()
    command = {
        "idempotencyKey": str(key),
        "rangeStart": 1,
        "rangeEnd": 9,
    }

    with client:
        discarded = client.post(
            f"/api/v1/admin/image-selections/{run.id}/groups/{duplicate.id}/discard-duplicate",
            json=command,
        )
        replay = client.post(
            f"/api/v1/admin/image-selections/{run.id}/groups/{duplicate.id}/discard-duplicate",
            json=command,
        )

    assert discarded.status_code == 200, discarded.text
    assert replay.json() == discarded.json()
    assert discarded.json()["group"]["status"] == "skipped_existing_range"
    assert discarded.json()["group"]["selectedCandidateId"] is None
    assert discarded.json()["decision"]["resolution"] == "duplicate_range"
    assert discarded.json()["decision"]["rangeStart"] == 1
    assert discarded.json()["decision"]["rangeEnd"] == 9
    assert repository.get_run(run.id).job.status is JobStatus.CREATED
    assert len(repository.manual_decisions) == 1


def test_manual_group_cannot_be_discarded_without_an_existing_range_owner() -> None:
    game_id = uuid4()
    repository = MemoryImageSelectionRepository(game_id)
    service = ImageSelectionService(repository)
    run, _created = service.create_run(
        game_id=game_id,
        source_selection_id=uuid4(),
        input_manifest_sha256="c" * 64,
        selector_fingerprint="f" * 64,
    )
    group = replace(
        _group(run.id, 0, status=ImageSelectionGroupStatus.MANUAL_REQUIRED),
        range_start=1,
        range_end=9,
    )
    repository.groups.append(group)
    client = TestClient(
        create_app(
            ApiSettings.from_environment(),
            image_selection_service_dependency=lambda: service,
        )
    )

    with client:
        rejected = client.post(
            f"/api/v1/admin/image-selections/{run.id}/groups/{group.id}/discard-duplicate",
            json={
                "idempotencyKey": str(uuid4()),
                "rangeStart": 1,
                "rangeEnd": 9,
            },
        )

    assert rejected.status_code == 409
    assert rejected.json()["code"] == "IMAGE_SELECTION_DUPLICATE_RANGE_NOT_FOUND"
    assert repository.groups[0].status is ImageSelectionGroupStatus.MANUAL_REQUIRED
    assert repository.manual_decisions == []


def test_range_queue_confirms_automatic_representative_without_reselecting_image() -> None:
    game_id = uuid4()
    repository = MemoryImageSelectionRepository(game_id)
    service = ImageSelectionService(repository)
    run, _created = service.create_run(
        game_id=game_id,
        source_selection_id=uuid4(),
        input_manifest_sha256="b" * 64,
        selector_fingerprint="c" * 64,
    )
    repository.runs[run.id] = replace(
        run,
        job=replace(
            run.job,
            status=JobStatus.WAITING_FOR_REVIEW,
            stage="image_selection:range_review",
            review_count=1,
        ),
    )
    group = _group(run.id, 0, status=ImageSelectionGroupStatus.RANGE_REQUIRED)
    candidate = replace(
        _manual_candidate(run.id, group.id, 0),
        decision=ImageSelectionCandidateDecision.SELECTED_AUTOMATIC,
    )
    group = replace(group, selected_candidate_id=candidate.id)
    repository.groups.append(group)
    repository.candidates.append(candidate)
    client = TestClient(
        create_app(
            ApiSettings.from_environment(),
            image_selection_service_dependency=lambda: service,
        )
    )
    command = {
        "idempotencyKey": str(uuid4()),
        "rangeStart": 55,
        "rangeEnd": 63,
    }

    with client:
        confirmed = client.post(
            f"/api/v1/admin/image-selections/{run.id}/groups/{group.id}/confirm-range",
            json=command,
        )
        replay = client.post(
            f"/api/v1/admin/image-selections/{run.id}/groups/{group.id}/confirm-range",
            json=command,
        )

    assert confirmed.status_code == 200, confirmed.text
    assert replay.json() == confirmed.json()
    assert confirmed.json()["group"]["status"] == "range_confirmed"
    assert confirmed.json()["group"]["selectedCandidateId"] == str(candidate.id)
    assert confirmed.json()["decision"]["resolution"] == "range_confirmed"
    assert repository.candidates[0].decision is ImageSelectionCandidateDecision.SELECTED_AUTOMATIC
    assert repository.get_run(run.id).job.status is JobStatus.CREATED


def test_range_queue_accepts_start_only_and_changes_representative() -> None:
    game_id = uuid4()
    repository = MemoryImageSelectionRepository(game_id)
    service = ImageSelectionService(repository)
    run, _ = service.create_run(
        game_id=game_id,
        source_selection_id=uuid4(),
        input_manifest_sha256="a" * 64,
        selector_fingerprint="c" * 64,
    )
    repository.runs[run.id] = replace(
        run,
        job=replace(run.job, status=JobStatus.WAITING_FOR_REVIEW, review_count=1),
    )
    group = _group(run.id, 0, status=ImageSelectionGroupStatus.RANGE_REQUIRED)
    automatic = replace(
        _manual_candidate(run.id, group.id, 0),
        decision=ImageSelectionCandidateDecision.SELECTED_AUTOMATIC,
    )
    replacement = _manual_candidate(run.id, group.id, 1)
    repository.groups.append(replace(group, selected_candidate_id=automatic.id))
    repository.candidates.extend((automatic, replacement))
    client = TestClient(
        create_app(
            ApiSettings.from_environment(),
            image_selection_service_dependency=lambda: service,
        )
    )

    with client:
        confirmed = client.post(
            f"/api/v1/admin/image-selections/{run.id}/groups/{group.id}/confirm-range",
            json={
                "candidateId": str(replacement.id),
                "idempotencyKey": str(uuid4()),
                "rangeStart": 7300,
            },
        )

    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["group"]["rangeStart"] == 7300
    assert confirmed.json()["group"]["rangeEnd"] == 7308
    assert confirmed.json()["group"]["selectedCandidateId"] == str(replacement.id)
    assert repository.candidates[0].decision is ImageSelectionCandidateDecision.ELIGIBLE
    assert (
        repository.candidates[1].decision
        is ImageSelectionCandidateDecision.SELECTED_AUTOMATIC
    )


@pytest.mark.parametrize(
    "origin",
    [
        ImageSelectionGroupStatus.MANUAL_REQUIRED,
        ImageSelectionGroupStatus.RANGE_REQUIRED,
    ],
)
def test_review_group_rejection_is_audited_and_restorable(
    origin: ImageSelectionGroupStatus,
) -> None:
    game_id = uuid4()
    repository = MemoryImageSelectionRepository(game_id)
    service = ImageSelectionService(repository)
    run, _created = service.create_run(
        game_id=game_id,
        source_selection_id=uuid4(),
        input_manifest_sha256="9" * 64,
        selector_fingerprint="8" * 64,
    )
    repository.runs[run.id] = replace(
        run,
        job=replace(run.job, status=JobStatus.WAITING_FOR_REVIEW, review_count=1),
    )
    group = _group(run.id, 0, status=origin)
    if origin is ImageSelectionGroupStatus.RANGE_REQUIRED:
        candidate = replace(
            _manual_candidate(run.id, group.id, 0),
            decision=ImageSelectionCandidateDecision.SELECTED_AUTOMATIC,
        )
        repository.candidates.append(candidate)
        group = replace(group, selected_candidate_id=candidate.id)
    repository.groups.append(group)
    client = TestClient(
        create_app(
            ApiSettings.from_environment(),
            image_selection_service_dependency=lambda: service,
        )
    )

    with client:
        rejected = client.post(
            f"/api/v1/admin/image-selections/{run.id}/groups/{group.id}/reject",
            json={"idempotencyKey": str(uuid4())},
        )
        restored = client.post(
            f"/api/v1/admin/image-selections/{run.id}/groups/{group.id}/restore",
            json={"idempotencyKey": str(uuid4())},
        )

    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["group"]["status"] == "rejected_by_user"
    assert rejected.json()["group"]["rejectionOriginStatus"] == origin.value
    assert rejected.json()["decision"]["resolution"] == "rejected_group"
    assert restored.status_code == 200, restored.text
    assert restored.json()["group"]["status"] == origin.value
    assert restored.json()["group"]["rejectionOriginStatus"] is None
    assert restored.json()["decision"]["resolution"] == "restored_group"


def test_domain_rejects_unsafe_paths_and_invalid_ranges() -> None:
    with pytest.raises(ImageSelectionError) as unsafe:
        safe_relative_path(r"C:\private\photo.jpg")
    with pytest.raises(ImageSelectionError) as invalid_range:
        validate_image_selection_group(
            group_order=0,
            range_start=9,
            range_end=1,
            fingerprint_sha256=None,
            board_count_consensus=None,
        )
    with pytest.raises(ImageSelectionError) as selected_without_group:
        validate_candidate(
            order_index=0,
            source_relative_path="staging/photo.jpg",
            checksum_sha256="e" * 64,
            width=100,
            height=100,
            range_confidence=0.8,
            decision=ImageSelectionCandidateDecision.SELECTED_AUTOMATIC,
            group_id=None,
        )

    assert unsafe.value.code == "IMAGE_SELECTION_PATH_UNSAFE"
    assert invalid_range.value.code == "IMAGE_SELECTION_RANGE_INVALID"
    assert selected_without_group.value.code == "IMAGE_SELECTION_CONFIGURATION_INVALID"


def test_image_selection_api_create_get_and_bounded_groups() -> None:
    game_id = uuid4()
    repository = MemoryImageSelectionRepository(game_id)
    service = ImageSelectionService(repository)
    client = TestClient(
        create_app(
            ApiSettings.from_environment(),
            image_selection_service_dependency=lambda: service,
            image_folder_selection_service_dependency=FakeAttestedPhotoSelection,
        )
    )
    payload = {
        "gameId": str(game_id),
        "selectionToken": "s" * 32,
        "contractVersion": 1,
        "sequenceDirection": "descending",
        "firstSequenceNumber": 7300,
    }

    with client:
        missing_anchor = client.post(
            "/api/v1/admin/image-selections",
            json={key: value for key, value in payload.items() if key != "firstSequenceNumber"},
        )
        created = client.post("/api/v1/admin/image-selections", json=payload)
        repeated = client.post("/api/v1/admin/image-selections", json=payload)
        run_id = UUID(created.json()["run"]["id"])
        repository.groups.extend([_group(run_id, 0), _group(run_id, 1), _group(run_id, 2)])
        fetched = client.get(f"/api/v1/admin/image-selections/{run_id}")
        groups = client.get(
            f"/api/v1/admin/image-selections/{run_id}/groups",
            params={"limit": 2},
        )
        missing = client.get(f"/api/v1/admin/image-selections/{uuid4()}")

    assert missing_anchor.status_code == 422
    assert created.status_code == 200
    assert created.json()["created"] is True
    assert created.json()["run"]["job"]["jobType"] == "image_selection"
    assert created.json()["run"]["sequenceDirection"] == "descending"
    assert created.json()["run"]["firstSequenceNumber"] == 7300
    assert repeated.status_code == 200
    assert repeated.json()["created"] is False
    assert repeated.json()["run"]["id"] == created.json()["run"]["id"]
    assert fetched.status_code == 200
    assert groups.status_code == 200
    assert [item["groupOrder"] for item in groups.json()["items"]] == [0, 1]
    assert groups.json()["nextAfterGroupOrder"] == 1
    assert missing.status_code == 404
    assert missing.json()["code"] == "IMAGE_SELECTION_NOT_FOUND"


def test_image_selection_api_reruns_existing_managed_staging(tmp_path: Path) -> None:
    game_id = uuid4()
    source_selection_id = uuid4()
    browser_upload_root = tmp_path / "staging"
    source_root = browser_upload_root / "browser-selections" / str(source_selection_id)
    source_root.mkdir(parents=True)
    manifest_content = b'{"files":[],"schemaVersion":1}'
    (source_root / "_browser_manifest.json").write_bytes(manifest_content)
    repository = MemoryImageSelectionRepository(game_id)
    service = ImageSelectionService(
        repository,
        browser_upload_root=browser_upload_root,
    )
    original, _created = service.create_run(
        game_id=game_id,
        source_selection_id=source_selection_id,
        input_manifest_sha256=hashlib.sha256(manifest_content).hexdigest(),
        selector_fingerprint="6" * 64,
        first_sequence_number=1,
    )
    client = TestClient(
        create_app(
            ApiSettings.from_environment(),
            image_selection_service_dependency=lambda: service,
        )
    )

    with client:
        rerun = client.post(f"/api/v1/admin/image-selections/{original.id}/rerun")
        repeated = client.post(f"/api/v1/admin/image-selections/{original.id}/rerun")

    assert rerun.status_code == 200, rerun.text
    assert rerun.json()["created"] is True
    assert rerun.json()["run"]["sourceSelectionId"] == str(source_selection_id)
    assert rerun.json()["run"]["id"] != str(original.id)
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["created"] is False
    assert repeated.json()["run"]["id"] == rerun.json()["run"]["id"]


def test_handoff_reverifies_output_is_idempotent_and_preserves_provenance(
    tmp_path: Path,
) -> None:
    game_id = uuid4()
    repository = MemoryImageSelectionRepository(game_id)
    artifact_root = tmp_path / "artifacts"
    service = ImageSelectionService(repository, artifact_root=artifact_root)
    run, _created = service.create_run(
        game_id=game_id,
        source_selection_id=uuid4(),
        input_manifest_sha256="1" * 64,
        selector_fingerprint="2" * 64,
    )
    source_root = tmp_path / "source"
    source_root.mkdir()
    source_path = source_root / "one.jpg"
    Image.new("RGB", (32, 24), (240, 180, 20)).save(source_path, format="JPEG")
    content = source_path.read_bytes()
    source = ImageSelectionSource(
        0,
        "photos/one.jpg",
        "one.jpg",
        hashlib.sha256(content).hexdigest(),
        len(content),
    )
    quality = ImageQualityMetrics(*(0.9 for _value in range(8)))
    candidate = CandidateResult(
        source=source,
        decision=CandidateDecision.SELECTED_AUTOMATIC,
        quality=quality,
        recognized_range=SequenceRange(1, 9, 0.98),
        reason_codes=(),
    )
    result = ImageSelectionResult(
        selector_version="fast-image-selector-v1",
        selector_fingerprint=run.selector_fingerprint,
        input_count=1,
        groups=(
            SelectionGroupResult(
                group_order=0,
                source_count=1,
                range=SequenceRange(1, 9, 0.98),
                fingerprint_sha256="3" * 64,
                board_count_consensus=9,
                status=SelectionGroupStatus.AUTO_SELECTED,
                selected_candidate=candidate,
                top_candidates=(candidate,),
            ),
        ),
        checkpoint=SelectorCheckpoint(1, run.selector_fingerprint, 1, 1, 1),
        scan_failure_count=0,
        verification_count=1,
    )
    published = CuratedImageOutputPublisher(artifact_root).publish(
        run_id=run.id,
        source_root=source_root,
        input_manifest_sha256=run.input_manifest_sha256,
        result=result,
    )
    published_entry = published.manifest.entries[0]
    legacy_file_name = "legacy-selected.jpg"
    published_image = published.output_directory / published_entry.output_relative_path
    legacy_image = published_image.with_name(legacy_file_name)
    published_image.replace(legacy_image)
    legacy_manifest = replace(
        published.manifest,
        entries=(
            replace(
                published_entry,
                output_relative_path=f"images/{legacy_file_name}",
            ),
        ),
    )
    (published.output_directory / "manifest.json").write_bytes(legacy_manifest.canonical_bytes)
    now = datetime(2026, 8, 3, tzinfo=UTC)
    repository.groups.append(
        ImageSelectionGroup(
            id=uuid4(),
            run_id=run.id,
            group_order=0,
            range_start=1,
            range_end=9,
            fingerprint_sha256="3" * 64,
            board_count_consensus=9,
            status=ImageSelectionGroupStatus.AUTO_SELECTED,
            selected_candidate_id=uuid4(),
            created_at=now,
            updated_at=now,
        )
    )
    service.record_output(
        run_id=run.id,
        manifest_sha256=legacy_manifest.checksum_sha256,
        manifest_relative_path=published.manifest_relative_path,
    )
    folder_service = ImageFolderSelectionService(lambda: None)
    client = TestClient(
        create_app(
            ApiSettings.from_environment(),
            image_selection_service_dependency=lambda: service,
            image_folder_selection_service_dependency=lambda: folder_service,
        )
    )

    with client:
        output = client.get(f"/api/v1/admin/image-selections/{run.id}/output")
        output_file = client.get(f"/api/v1/admin/image-selections/{run.id}/output/seq_1-9.jpg")
        first = client.post(f"/api/v1/admin/image-selections/{run.id}/handoff")
        repeated = client.post(f"/api/v1/admin/image-selections/{run.id}/handoff")

    assert output.status_code == 200, output.text
    assert output.json()["files"] == [
        {
            "checksumSha256": hashlib.sha256(content).hexdigest(),
            "fileName": "seq_1-9.jpg",
            "groupOrder": 0,
            "rangeEnd": 9,
            "rangeStart": 1,
            "reasonCodes": [],
            "selectionMethod": "automatic",
            "sizeBytes": len(content),
        }
    ]
    assert output_file.status_code == 200
    assert output_file.content == content
    assert first.status_code == 200, first.text
    assert repeated.status_code == 200
    assert repeated.json() == first.json()
    assert first.json()["selectionId"] == str(run.id)
    assert first.json()["gameId"] == str(game_id)
    assert first.json()["supportedFileCount"] == 1

    repository.groups.append(_group(run.id, 1, status=ImageSelectionGroupStatus.MANUAL_REQUIRED))
    with client:
        unresolved = client.post(f"/api/v1/admin/image-selections/{run.id}/handoff")
    repository.groups.pop()
    assert unresolved.status_code == 409
    assert unresolved.json()["code"] == "IMAGE_SELECTION_NOT_READY"

    selected_image = next((published.output_directory / "images").iterdir())
    selected_image.write_bytes(selected_image.read_bytes() + b"changed")
    with client:
        changed = client.post(f"/api/v1/admin/image-selections/{run.id}/handoff")
    assert changed.status_code == 409
    assert changed.json()["code"] == "IMAGE_SELECTION_MANIFEST_MISMATCH"


def test_range_free_output_is_exposed_and_handed_to_import_by_group_order(
    tmp_path: Path,
) -> None:
    game_id = uuid4()
    repository = MemoryImageSelectionRepository(game_id)
    artifact_root = tmp_path / "artifacts"
    service = ImageSelectionService(repository, artifact_root=artifact_root)
    run, _created = service.create_run(
        game_id=game_id,
        source_selection_id=uuid4(),
        input_manifest_sha256="4" * 64,
        selector_fingerprint="5" * 64,
    )
    source_root = tmp_path / "source"
    source_root.mkdir()
    source_path = source_root / "stored.jpg"
    Image.new("RGB", (32, 24), (20, 180, 240)).save(source_path, format="JPEG")
    content = source_path.read_bytes()
    source = ImageSelectionSource(
        7,
        "photos/original-name.jpg",
        source_path.name,
        hashlib.sha256(content).hexdigest(),
        len(content),
    )
    candidate = CandidateResult(
        source=source,
        decision=CandidateDecision.SELECTED_AUTOMATIC,
        quality=ImageQualityMetrics(*(0.8 for _value in range(8))),
        recognized_range=None,
        reason_codes=("RANGE_UNKNOWN",),
    )
    result = ImageSelectionResult(
        selector_version="fast-image-selector-v9",
        selector_fingerprint=run.selector_fingerprint,
        input_count=1,
        groups=(
            SelectionGroupResult(
                group_order=3,
                source_count=1,
                range=None,
                fingerprint_sha256="6" * 64,
                board_count_consensus=None,
                status=SelectionGroupStatus.AUTO_SELECTED,
                selected_candidate=candidate,
                top_candidates=(candidate,),
            ),
        ),
        checkpoint=SelectorCheckpoint(1, run.selector_fingerprint, 1, 1, 1),
        scan_failure_count=0,
        verification_count=0,
    )
    published = CuratedImageOutputPublisher(artifact_root).publish(
        run_id=run.id,
        source_root=source_root,
        input_manifest_sha256=run.input_manifest_sha256,
        result=result,
    )
    repository.groups.append(
        replace(
            _group(run.id, 3, status=ImageSelectionGroupStatus.AUTO_SELECTED),
            fingerprint_sha256="6" * 64,
            selected_candidate_id=uuid4(),
        )
    )
    service.record_output(
        run_id=run.id,
        manifest_sha256=published.manifest_sha256,
        manifest_relative_path=published.manifest_relative_path,
    )
    folder_service = ImageFolderSelectionService(lambda: None)
    client = TestClient(
        create_app(
            ApiSettings.from_environment(),
            image_selection_service_dependency=lambda: service,
            image_folder_selection_service_dependency=lambda: folder_service,
        )
    )

    with client:
        output = client.get(f"/api/v1/admin/image-selections/{run.id}/output")
        output_file = client.get(f"/api/v1/admin/image-selections/{run.id}/output/selection_3.jpg")
        handoff = client.post(f"/api/v1/admin/image-selections/{run.id}/handoff")

    assert output.status_code == 200, output.text
    assert output.json()["files"] == [
        {
            "checksumSha256": hashlib.sha256(content).hexdigest(),
            "fileName": "selection_3.jpg",
            "groupOrder": 3,
            "rangeEnd": None,
            "rangeStart": None,
            "reasonCodes": ["RANGE_UNKNOWN"],
            "selectionMethod": "automatic",
            "sizeBytes": len(content),
        }
    ]
    assert output_file.status_code == 200
    assert output_file.content == content
    assert handoff.status_code == 200, handoff.text
    assert handoff.json()["supportedFileCount"] == 1


def test_manual_jpeg_approval_is_idempotent_revisable_and_audited(
    tmp_path: Path,
) -> None:
    game_id = uuid4()
    repository = MemoryImageSelectionRepository(game_id)
    service = ImageSelectionService(repository, artifact_root=tmp_path / "artifacts")
    run, _created = service.create_run(
        game_id=game_id,
        source_selection_id=uuid4(),
        input_manifest_sha256="6" * 64,
        selector_fingerprint="7" * 64,
    )
    group = _group(run.id, 0, status=ImageSelectionGroupStatus.MANUAL_REQUIRED)
    repository.groups.append(group)
    client = TestClient(
        create_app(
            ApiSettings.from_environment(),
            image_selection_service_dependency=lambda: service,
        )
    )
    first_path = tmp_path / "first.jpg"
    second_path = tmp_path / "second.jpg"
    Image.new("RGB", (80, 60), (240, 180, 20)).save(first_path, format="JPEG")
    Image.new("RGB", (96, 72), (180, 20, 240)).save(second_path, format="JPEG")

    with client:
        uploaded = client.put(
            f"/api/v1/admin/image-selections/{run.id}/groups/{group.id}/manual-file",
            headers={
                "Content-Type": "application/octet-stream",
                "X-Image-File-Name": "first.jpg",
            },
            content=first_path.read_bytes(),
        )
        assert uploaded.status_code == 200, uploaded.text
        candidate_id = uploaded.json()["candidate"]["id"]
        group_candidates = client.get(
            f"/api/v1/admin/image-selections/{run.id}/groups/{group.id}/candidates"
        )
        missing_range = client.post(
            f"/api/v1/admin/image-selections/{run.id}/groups/{group.id}/approve",
            json={
                "candidateId": candidate_id,
                "idempotencyKey": str(uuid4()),
            },
        )
        idempotency_key = uuid4()
        command = {
            "candidateId": candidate_id,
            "idempotencyKey": str(idempotency_key),
            "rangeStart": 1,
            "rangeEnd": 9,
        }
        approved = client.post(
            f"/api/v1/admin/image-selections/{run.id}/groups/{group.id}/approve",
            json=command,
        )
        replay = client.post(
            f"/api/v1/admin/image-selections/{run.id}/groups/{group.id}/approve",
            json=command,
        )
        preview = client.get(
            f"/api/v1/admin/image-selections/{run.id}/groups/{group.id}/manual-files/{candidate_id}"
        )
        replacement = client.put(
            f"/api/v1/admin/image-selections/{run.id}/groups/{group.id}/manual-file",
            headers={
                "Content-Type": "application/octet-stream",
                "X-Image-File-Name": "second.jpeg",
            },
            content=second_path.read_bytes(),
        )
        corrected = client.post(
            f"/api/v1/admin/image-selections/{run.id}/groups/{group.id}/approve",
            json={
                "candidateId": replacement.json()["candidate"]["id"],
                "idempotencyKey": str(uuid4()),
                "rangeStart": 10,
                "rangeEnd": 18,
            },
        )

    assert uploaded.status_code == 200
    assert uploaded.json()["candidate"]["displayName"] == "first.jpg"
    assert group_candidates.status_code == 200
    assert group_candidates.json()["sourceCount"] == 1
    assert [item["displayName"] for item in group_candidates.json()["items"]] == ["first.jpg"]
    assert missing_range.status_code == 422
    assert missing_range.json()["code"] == "IMAGE_SELECTION_RANGE_REQUIRED"
    assert approved.status_code == 200
    assert approved.json()["group"]["status"] == "manually_selected"
    assert approved.json()["decision"]["revision"] == 1
    assert replay.status_code == 200
    assert replay.json() == approved.json()
    assert preview.status_code == 200
    assert preview.content == first_path.read_bytes()
    assert corrected.status_code == 200
    assert corrected.json()["decision"]["revision"] == 2
    assert corrected.json()["group"]["rangeStart"] == 10
    assert len(repository.manual_decisions) == 2
    decision_manifest = (
        tmp_path
        / "artifacts"
        / "data"
        / "working"
        / "is-manual"
        / run.id.hex[:12]
        / "manual-decisions.json"
    )
    assert decision_manifest.is_file()
    assert len(json.loads(decision_manifest.read_text())["decisions"]) == 2


def test_manual_gap_can_be_filled_after_publication_and_requeues_output_revision() -> None:
    game_id = uuid4()
    repository = MemoryImageSelectionRepository(game_id)
    service = ImageSelectionService(repository)
    run, _created = service.create_run(
        game_id=game_id,
        source_selection_id=uuid4(),
        input_manifest_sha256="6" * 64,
        selector_fingerprint="7" * 64,
    )
    finished_at = datetime(2026, 8, 9, 18, 0, tzinfo=UTC)
    published = replace(
        run,
        output_manifest_sha256="8" * 64,
        output_manifest_relative_path="data/exports/image-selections/manifest.json",
        job=replace(
            run.job,
            status=JobStatus.COMPLETED,
            stage="image_selection:ready_for_import",
            finished_at=finished_at,
            updated_at=finished_at,
        ),
    )
    repository.runs[run.id] = published
    group = replace(
        _group(run.id, 0, status=ImageSelectionGroupStatus.MISSING_IMAGE),
        range_start=1,
        range_end=9,
    )
    candidate = _manual_candidate(run.id, group.id, order_index=0)
    repository.groups.append(group)
    repository.candidates.append(candidate)

    approved = service.approve_manual_file(
        run_id=run.id,
        group_id=group.id,
        candidate_id=candidate.id,
        idempotency_key=uuid4(),
        range_start=1,
        range_end=9,
    )

    refreshed = repository.runs[run.id]
    assert approved.group.status is ImageSelectionGroupStatus.MANUALLY_SELECTED
    assert refreshed.output_manifest_sha256 is None
    assert refreshed.output_manifest_relative_path is None
    assert refreshed.job.status is JobStatus.CREATED
    assert refreshed.job.stage == "image_selection:manual_revision"
