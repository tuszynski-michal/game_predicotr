from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.application.image_selections import ImageSelectionService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.image_selections import (
    IMAGE_SELECTION_ORDERING_POLICY,
    ImageSelectionCandidate,
    ImageSelectionCandidateDecision,
    ImageSelectionError,
    ImageSelectionGroup,
    ImageSelectionGroupStatus,
    ImageSelectionRun,
    safe_relative_path,
    validate_candidate,
    validate_image_selection_group,
)
from game_predictor_api.domain.jobs import JobType
from game_predictor_api.main import create_app


class MemoryImageSelectionRepository:
    def __init__(self, game_id: UUID) -> None:
        self.game_id = game_id
        self.runs: dict[UUID, ImageSelectionRun] = {}
        self.groups: list[ImageSelectionGroup] = []
        self.candidates: list[ImageSelectionCandidate] = []

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
