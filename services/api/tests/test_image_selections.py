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
    ImageSelectionError,
    ImageSelectionGroup,
    ImageSelectionGroupStatus,
    ImageSelectionManualDecision,
    ImageSelectionRun,
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
from game_predictor_worker.images.selection.output import CuratedImageOutputPublisher
from PIL import Image


class MemoryImageSelectionRepository:
    def __init__(self, game_id: UUID) -> None:
        self.game_id = game_id
        self.runs: dict[UUID, ImageSelectionRun] = {}
        self.groups: list[ImageSelectionGroup] = []
        self.candidates: list[ImageSelectionCandidate] = []
        self.manual_decisions: list[ImageSelectionManualDecision] = []

    def game_exists(self, game_id: UUID) -> bool:
        return game_id == self.game_id

    def find_run_by_identity(
        self,
        *,
        game_id: UUID,
        input_manifest_sha256: str,
        selector_fingerprint: str,
    ) -> ImageSelectionRun | None:
        return next(
            (
                run
                for run in self.runs.values()
                if run.game_id == game_id
                and run.input_manifest_sha256 == input_manifest_sha256
                and run.selector_fingerprint == selector_fingerprint
            ),
            None,
        )

    def add_run(self, run: ImageSelectionRun) -> tuple[ImageSelectionRun, bool]:
        existing = self.find_run_by_identity(
            game_id=run.game_id,
            input_manifest_sha256=run.input_manifest_sha256,
            selector_fingerprint=run.selector_fingerprint,
        )
        if existing is not None:
            return existing, False
        self.runs[run.id] = run
        return run, True

    def get_run(self, run_id: UUID) -> ImageSelectionRun | None:
        return self.runs.get(run_id)

    def save_run(self, run: ImageSelectionRun) -> ImageSelectionRun:
        self.runs[run.id] = run
        return run

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
            expected = (
                ImageSelectionCandidateDecision.SELECTED_MANUAL
                if candidate.id == decision.candidate_id
                else (
                    ImageSelectionCandidateDecision.ELIGIBLE
                    if candidate.decision is ImageSelectionCandidateDecision.SELECTED_MANUAL
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
    ) -> tuple[ImageSelectionRun, bool]:
        assert selection_token == "s" * 32
        return service.create_run(
            game_id=game_id,
            source_selection_id=UUID("00000000-0000-0000-0000-000000000151"),
            input_manifest_sha256="1" * 64,
            selector_fingerprint=selector_fingerprint,
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
    }


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
    }

    with client:
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

    assert created.status_code == 200
    assert created.json()["created"] is True
    assert created.json()["run"]["job"]["jobType"] == "image_selection"
    assert repeated.status_code == 200
    assert repeated.json()["created"] is False
    assert repeated.json()["run"]["id"] == created.json()["run"]["id"]
    assert fetched.status_code == 200
    assert groups.status_code == 200
    assert [item["groupOrder"] for item in groups.json()["items"]] == [0, 1]
    assert groups.json()["nextAfterGroupOrder"] == 1
    assert missing.status_code == 404
    assert missing.json()["code"] == "IMAGE_SELECTION_NOT_FOUND"


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
        first = client.post(f"/api/v1/admin/image-selections/{run.id}/handoff")
        repeated = client.post(f"/api/v1/admin/image-selections/{run.id}/handoff")

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
