from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from game_predictor_api.api.semi_automatic_image_selections import (
    create_semi_automatic_image_selections_router,
)
from game_predictor_api.application.image_imports import (
    BrowserImageSelectionService,
    ImageFolderSelectionService,
    ImageSelectionPurpose,
)
from game_predictor_api.application.semi_automatic_image_selections import (
    SemiAutomaticImageSelectionService,
)
from game_predictor_api.domain.jobs import (
    JobError,
    JobExecutionSlot,
    JobStatus,
    JobType,
    start_job,
    wait_for_review,
)
from game_predictor_api.domain.semi_automatic_image_selections import (
    SemiAutomaticSelectionDirection,
    SemiAutomaticSelectionRange,
    SemiAutomaticSelectionRangeStatus,
    SemiAutomaticSelectionRun,
    SemiAutomaticSelectionRunStatus,
)
from game_predictor_worker.jobs.runtime import GENERAL_JOB_TYPES as RUNTIME_GENERAL_JOB_TYPES
from game_predictor_worker.jobs.store import GENERAL_JOB_TYPES as STORE_GENERAL_JOB_TYPES
from PIL import Image


class MemorySemiAutomaticSelectionRepository:
    def __init__(self) -> None:
        self.runs: dict[UUID, SemiAutomaticSelectionRun] = {}
        self.identities: dict[str, UUID] = {}
        self.ranges: dict[tuple[UUID, int], SemiAutomaticSelectionRange] = {}

    def find_by_identity(self, identity_key: str) -> SemiAutomaticSelectionRun | None:
        run_id = self.identities.get(identity_key)
        return None if run_id is None else self.runs[run_id]

    def add(
        self,
        run: SemiAutomaticSelectionRun,
        ranges: Sequence[SemiAutomaticSelectionRange],
        *,
        identity_key: str,
    ) -> SemiAutomaticSelectionRun:
        if identity_key in self.identities:
            raise AssertionError("The service should resolve idempotency before inserting.")
        self.runs[run.id] = run
        self.identities[identity_key] = run.id
        self.ranges.update({(item.run_id, item.expected_index): item for item in ranges})
        return run

    def get(
        self,
        run_id: UUID,
        *,
        for_update: bool = False,
    ) -> SemiAutomaticSelectionRun | None:
        del for_update
        return self.runs.get(run_id)

    def save(self, run: SemiAutomaticSelectionRun) -> SemiAutomaticSelectionRun:
        self.runs[run.id] = run
        return run

    def list_ranges(
        self,
        run_id: UUID,
        *,
        after_expected_index: int | None,
        limit: int,
    ) -> tuple[SemiAutomaticSelectionRange, ...]:
        items = sorted(
            (item for (owner, _), item in self.ranges.items() if owner == run_id),
            key=lambda item: item.expected_index,
        )
        if after_expected_index is not None:
            items = [item for item in items if item.expected_index > after_expected_index]
        return tuple(items[:limit])

    def get_range_for_update(
        self,
        run_id: UUID,
        expected_index: int,
    ) -> SemiAutomaticSelectionRange | None:
        return self.ranges.get((run_id, expected_index))

    def save_range(self, item: SemiAutomaticSelectionRange) -> SemiAutomaticSelectionRange:
        self.ranges[(item.run_id, item.expected_index)] = item
        return item

    def save_run_and_range(
        self,
        run: SemiAutomaticSelectionRun,
        item: SemiAutomaticSelectionRange,
    ) -> tuple[SemiAutomaticSelectionRun, SemiAutomaticSelectionRange]:
        return self.save(run), self.save_range(item)


def _jpeg(color: tuple[int, int, int]) -> bytes:
    output = BytesIO()
    Image.new("RGB", (32, 24), color).save(output, format="JPEG")
    return output.getvalue()


def _ready_staging(tmp_path: Path) -> tuple[BrowserImageSelectionService, UUID, bytes]:
    selection_service = ImageFolderSelectionService(lambda: None)
    service = BrowserImageSelectionService(
        selection_service,
        tmp_path / "imports",
        max_bytes=1024 * 1024,
        photo_selection_max_bytes=1024 * 1024,
    )
    first = _jpeg((10, 20, 30))
    second = _jpeg((40, 50, 60))
    upload = service.begin(
        display_name="selection-source",
        expected_file_count=2,
        expected_total_bytes=len(first) + len(second),
        purpose=ImageSelectionPurpose.SEMI_AUTOMATIC_SELECTION,
        game_id=None,
    )
    service.upload_file(
        upload.upload_id,
        0,
        relative_path="selection-source/photo-1.jpg",
        content=first,
    )
    service.upload_file(
        upload.upload_id,
        1,
        relative_path="selection-source/photo-2.jpg",
        content=second,
    )
    service.finalize(upload.upload_id)
    return service, upload.upload_id, first


def test_global_staging_and_run_survive_service_recreation(tmp_path: Path) -> None:
    staging, upload_id, first_jpeg = _ready_staging(tmp_path)
    ready = staging.get_ready_source_selection(
        upload_id,
        purpose=ImageSelectionPurpose.SEMI_AUTOMATIC_SELECTION,
    )
    recreated_staging = BrowserImageSelectionService(
        ImageFolderSelectionService(lambda: None),
        tmp_path / "imports",
        max_bytes=1024 * 1024,
        photo_selection_max_bytes=1024 * 1024,
    )
    recreated_ready = recreated_staging.get_ready_source_selection(
        upload_id,
        purpose=ImageSelectionPurpose.SEMI_AUTOMATIC_SELECTION,
    )
    repository = MemorySemiAutomaticSelectionRepository()
    first_service = SemiAutomaticImageSelectionService(
        repository,
        recreated_staging,
        enabled=True,
    )
    run, created = first_service.create(
        upload_id=upload_id,
        first_sequence_number=1,
        last_sequence_number=23,
        direction=SemiAutomaticSelectionDirection.ASCENDING,
    )

    recreated_service = SemiAutomaticImageSelectionService(
        repository,
        recreated_staging,
        enabled=True,
    )
    duplicate, duplicate_created = recreated_service.create(
        upload_id=upload_id,
        first_sequence_number=1,
        last_sequence_number=23,
        direction=SemiAutomaticSelectionDirection.ASCENDING,
    )
    ranges = recreated_service.list_ranges(run.id, after_expected_index=None, limit=20)
    asset, name = recreated_service.source_asset(
        run.id,
        0,
        expected_checksum_sha256=ready.sources[0].checksum_sha256,
    )

    assert created is True
    assert duplicate_created is False
    assert duplicate.id == run.id
    assert run.job.game_id is None
    assert run.job.job_type is JobType.SEMI_AUTOMATIC_IMAGE_SELECTION
    assert recreated_ready.source_fingerprint == ready.source_fingerprint
    assert [(item.range_start, item.range_end) for item in ranges] == [(1, 9), (10, 18), (19, 23)]
    assert asset.read_bytes() == first_jpeg
    assert name == "photo-1.jpg"


def test_global_staging_rejects_game_scope_and_other_purpose(tmp_path: Path) -> None:
    service = BrowserImageSelectionService(
        ImageFolderSelectionService(lambda: None),
        tmp_path / "imports",
        max_bytes=1024 * 1024,
        photo_selection_max_bytes=1024 * 1024,
    )
    with pytest.raises(JobError) as scoped_error:
        service.begin(
            display_name="invalid",
            expected_file_count=1,
            expected_total_bytes=100,
            purpose=ImageSelectionPurpose.SEMI_AUTOMATIC_SELECTION,
            game_id=uuid4(),
        )
    assert scoped_error.value.code == "SEMI_AUTOMATIC_SELECTION_SOURCE_SCOPE_INVALID"

    _, upload_id, _ = _ready_staging(tmp_path / "other")
    other_service = BrowserImageSelectionService(
        ImageFolderSelectionService(lambda: None),
        tmp_path / "other" / "imports",
        max_bytes=1024 * 1024,
        photo_selection_max_bytes=1024 * 1024,
    )
    with pytest.raises(JobError) as purpose_error:
        other_service.get_ready_source_selection(
            upload_id,
            purpose=ImageSelectionPurpose.PHOTO_SELECTION,
        )
    assert purpose_error.value.code == "IMAGE_FOLDER_SELECTION_PURPOSE_INVALID"


def test_finalized_source_manifest_and_asset_are_checksum_bound(tmp_path: Path) -> None:
    staging, upload_id, _ = _ready_staging(tmp_path)
    ready = staging.get_ready_source_selection(
        upload_id,
        purpose=ImageSelectionPurpose.SEMI_AUTOMATIC_SELECTION,
    )
    repository = MemorySemiAutomaticSelectionRepository()
    service = SemiAutomaticImageSelectionService(repository, staging, enabled=True)
    run, _ = service.create(
        upload_id=upload_id,
        first_sequence_number=1,
        last_sequence_number=9,
        direction=SemiAutomaticSelectionDirection.ASCENDING,
    )

    with pytest.raises(JobError) as checksum_error:
        service.source_asset(run.id, 0, expected_checksum_sha256="0" * 64)
    assert checksum_error.value.code == "SEMI_AUTOMATIC_SELECTION_SOURCE_CHANGED"

    manifest_path = staging.get(upload_id).path / "_browser_manifest.json"
    manifest_path.write_bytes(manifest_path.read_bytes() + b" ")
    with pytest.raises(JobError) as manifest_error:
        staging.get_ready_source_selection(
            upload_id,
            purpose=ImageSelectionPurpose.SEMI_AUTOMATIC_SELECTION,
        )
    assert manifest_error.value.code == "SEMI_AUTOMATIC_SELECTION_SOURCE_CHANGED"
    assert len(ready.sources) == 2


def test_pause_resume_cancel_and_output_acknowledgement_are_durable(tmp_path: Path) -> None:
    staging, upload_id, _ = _ready_staging(tmp_path)
    repository = MemorySemiAutomaticSelectionRepository()
    service = SemiAutomaticImageSelectionService(repository, staging, enabled=True)
    run, _ = service.create(
        upload_id=upload_id,
        first_sequence_number=100,
        last_sequence_number=108,
        direction=SemiAutomaticSelectionDirection.DESCENDING,
    )

    paused = service.pause(run.id)
    resumed = service.resume(run.id)
    selected = replace(
        repository.ranges[(run.id, 0)],
        status=SemiAutomaticSelectionRangeStatus.AUTO_SELECTED,
        source_index=0,
        source_relative_path="selection-source/photo-1.jpg",
        source_size_bytes=staging.get_ready_source_selection(
            upload_id,
            purpose=ImageSelectionPurpose.SEMI_AUTOMATIC_SELECTION,
        ).sources[0].size_bytes,
        source_checksum_sha256=staging.get_ready_source_selection(
            upload_id,
            purpose=ImageSelectionPurpose.SEMI_AUTOMATIC_SELECTION,
        ).sources[0].checksum_sha256,
    )
    repository.save_range(selected)
    repository.save(
        replace(
            repository.runs[run.id],
            counters={
                "expected": 1,
                "autoSelected": 1,
                "outputSynced": 0,
                "conflicts": 0,
                "missing": 0,
            },
        )
    )
    acknowledged = service.acknowledge_output(
        run.id,
        0,
        expected_revision=0,
        expected_source_checksum_sha256=selected.source_checksum_sha256 or "",
        output_checksum_sha256=selected.source_checksum_sha256 or "",
    )
    cancelled = service.cancel(run.id)

    assert paused.status.value == "paused"
    assert resumed.status.value == "ready"
    assert acknowledged.status is SemiAutomaticSelectionRangeStatus.OUTPUT_SYNCED
    assert service.get(run.id).counters["outputSynced"] == 1
    assert cancelled.status.value == "cancelled"
    assert cancelled.job.status is JobStatus.CANCELLED
    assert service.get(run.id) == cancelled


def test_resume_requeues_a_paused_worker_checkpoint(tmp_path: Path) -> None:
    staging, upload_id, _ = _ready_staging(tmp_path)
    repository = MemorySemiAutomaticSelectionRepository()
    service = SemiAutomaticImageSelectionService(repository, staging, enabled=True)
    run, _ = service.create(
        upload_id=upload_id,
        first_sequence_number=1,
        last_sequence_number=9,
        direction=SemiAutomaticSelectionDirection.ASCENDING,
    )
    now = datetime.now(UTC)
    processing = start_job(
        run.job,
        worker_version="test-worker",
        worker_id="selection-worker",
        lease_token=uuid4(),
        lease_expires_at=now + timedelta(minutes=1),
        execution_slot=JobExecutionSlot.IMAGE_SELECTION,
        started_at=now,
    )
    assert processing.lease_token is not None
    waiting = wait_for_review(
        processing,
        lease_token=processing.lease_token,
        updated_at=now,
    )
    repository.save(
        replace(
            run,
            job=waiting,
            checkpoint={"phase": "scanning", "observationCount": 1},
            status=SemiAutomaticSelectionRunStatus.RUNNING,
        )
    )

    service.pause(run.id)
    resumed = service.resume(run.id)

    assert resumed.status.value == "ready"
    assert resumed.job.status is JobStatus.CREATED
    assert resumed.checkpoint == {"phase": "scanning", "observationCount": 1}


def test_api_exposes_capabilities_idempotent_create_and_ranges(tmp_path: Path) -> None:
    staging, upload_id, _ = _ready_staging(tmp_path)
    service = SemiAutomaticImageSelectionService(
        MemorySemiAutomaticSelectionRepository(), staging, enabled=True
    )
    app = FastAPI()
    app.include_router(
        create_semi_automatic_image_selections_router(lambda: service),
        prefix="/api/v1",
    )
    client = TestClient(app)
    payload = {
        "uploadId": str(upload_id),
        "firstSequenceNumber": 1,
        "lastSequenceNumber": 19,
        "direction": "ascending",
    }

    capabilities = client.get("/api/v1/admin/semi-automatic-image-selections/capabilities")
    created = client.post("/api/v1/admin/semi-automatic-image-selections", json=payload)
    duplicate = client.post("/api/v1/admin/semi-automatic-image-selections", json=payload)
    assert created.status_code == 200, created.text
    run_id = created.json()["run"]["id"]
    ranges = client.get(f"/api/v1/admin/semi-automatic-image-selections/{run_id}/ranges")

    assert capabilities.status_code == 200
    assert capabilities.json()["enabled"] is True
    assert created.json()["created"] is True
    assert created.json()["run"]["gameId"] is None
    assert duplicate.status_code == 200
    assert duplicate.json()["created"] is False
    assert ranges.status_code == 200
    assert [item["fileName"] for item in ranges.json()["items"]] == [
        "seq_1-9.jpg",
        "seq_10-18.jpg",
        "seq_19-19.jpg",
    ]


def test_semi_automatic_jobs_use_only_the_existing_selection_lane(tmp_path: Path) -> None:
    staging, upload_id, _ = _ready_staging(tmp_path)
    service = SemiAutomaticImageSelectionService(
        MemorySemiAutomaticSelectionRepository(), staging, enabled=True
    )
    run, _ = service.create(
        upload_id=upload_id,
        first_sequence_number=1,
        last_sequence_number=9,
        direction=SemiAutomaticSelectionDirection.ASCENDING,
    )

    now = datetime.now(UTC)
    leased = start_job(
        run.job,
        worker_version="test-worker",
        worker_id="selection-worker",
        lease_token=uuid4(),
        lease_expires_at=now + timedelta(minutes=1),
        execution_slot=JobExecutionSlot.IMAGE_SELECTION,
        started_at=now,
    )
    assert leased.execution_slot == 2
    assert JobType.SEMI_AUTOMATIC_IMAGE_SELECTION not in RUNTIME_GENERAL_JOB_TYPES
    assert JobType.SEMI_AUTOMATIC_IMAGE_SELECTION not in STORE_GENERAL_JOB_TYPES
    with pytest.raises(JobError) as wrong_lane:
        start_job(
            run.job,
            worker_version="test-worker",
            worker_id="general-worker",
            lease_token=uuid4(),
            lease_expires_at=now + timedelta(minutes=1),
            execution_slot=JobExecutionSlot.GENERAL,
            started_at=now,
        )
    assert wrong_lane.value.code == "INVALID_JOB_EXECUTION_SLOT"
