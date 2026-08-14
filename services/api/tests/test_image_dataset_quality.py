from __future__ import annotations

from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from game_predictor_api.application.image_reviews import (
    OperationalImageReviewRepository,
    OperationalImageReviewService,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.image_reviews import (
    ImageDatasetCompleteness,
    ImageSequenceSourceCandidate,
    ImageSequenceSourceSelection,
)
from game_predictor_api.main import create_app


class QualityRepository(OperationalImageReviewRepository):
    def __init__(self) -> None:
        self.game_id = uuid4()
        self.first = uuid4()
        self.second = uuid4()
        self.override_id: UUID | None = None
        self.revision = 0

    def expected_layout_count(self, game_id: UUID) -> int | None:
        return 120 if game_id == self.game_id else None

    def dataset_completeness(
        self,
        game_id: UUID,
    ) -> ImageDatasetCompleteness | None:
        if game_id != self.game_id:
            return None
        return ImageDatasetCompleteness(
            game_id=game_id,
            expected_layout_count=120,
            accepted_board_count=22,
            unique_sequence_count=20,
            missing_sequence_count=100,
            duplicate_sequence_count=2,
            out_of_range_sequence_count=0,
            missing_sequence_numbers=tuple(range(21, 121)),
            missing_sequence_numbers_truncated=False,
            manual_override_count=int(self.override_id is not None),
        )

    def sequence_source_selection(
        self,
        game_id: UUID,
        sequence_number: int,
    ) -> ImageSequenceSourceSelection | None:
        if game_id != self.game_id or sequence_number != 7:
            return None
        selected_id = self.override_id or self.first
        return ImageSequenceSourceSelection(
            game_id=game_id,
            sequence_number=sequence_number,
            candidates=tuple(
                ImageSequenceSourceCandidate(
                    review_item_id=review_item_id,
                    recognized_board_id=uuid4(),
                    import_job_id=uuid4(),
                    sequence_number=sequence_number,
                    source_checksum_sha256=("a" if rank == 1 else "b") * 64,
                    source_relative_path=f"source-{rank}.jpg",
                    width=1920 if rank == 1 else 1280,
                    height=1080 if rank == 1 else 720,
                    board_confidence=0.95 if rank == 1 else 0.85,
                    sequence_confidence=0.9 if rank == 1 else 0.8,
                    geometry_revision=0,
                    automatic_rank=rank,
                    quality_score=0.9425 if rank == 1 else 0.7514,
                    selected=review_item_id == selected_id,
                    selected_manually=(
                        self.override_id is not None and review_item_id == self.override_id
                    ),
                )
                for rank, review_item_id in ((1, self.first), (2, self.second))
            ),
            manual_override_review_item_id=self.override_id,
            override_revision=self.revision,
        )

    def append_source_override(
        self,
        *,
        game_id: UUID,
        sequence_number: int,
        review_item_id: UUID | None,
        selected_by: str,
    ) -> None:
        assert game_id == self.game_id
        assert sequence_number == 7
        assert selected_by == "local-owner"
        self.override_id = review_item_id
        self.revision += 1


def _client(repository: QualityRepository) -> TestClient:
    return TestClient(
        create_app(
            ApiSettings.from_environment({}),
            image_review_service_dependency=lambda: OperationalImageReviewService(repository),
        )
    )


def test_completeness_is_exact_and_missing_sample_is_bounded() -> None:
    repository = QualityRepository()
    response = _client(repository).get(
        f"/api/v1/admin/image-review-items/dataset-completeness/{repository.game_id}"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["expectedLayoutCount"] == 120
    assert body["uniqueSequenceCount"] == 20
    assert body["completionPercentage"] == 16.6667
    assert len(body["missingSequenceNumbers"]) == 100


def test_source_override_preserves_automatic_rank_and_can_be_cleared() -> None:
    repository = QualityRepository()
    client = _client(repository)
    endpoint = f"/api/v1/admin/image-review-items/sequence-sources/{repository.game_id}/7"

    automatic = client.get(endpoint)
    assert automatic.status_code == 200
    assert automatic.json()["candidates"][0]["selected"] is True

    overridden = client.post(
        f"{endpoint}/override",
        json={"reviewItemId": str(repository.second), "selectedBy": "local-owner"},
    )
    assert overridden.status_code == 200
    assert overridden.json()["manualOverrideReviewItemId"] == str(repository.second)
    assert overridden.json()["candidates"][1]["selectedManually"] is True

    cleared = client.post(
        f"{endpoint}/override",
        json={"reviewItemId": None, "selectedBy": "local-owner"},
    )
    assert cleared.status_code == 200
    assert cleared.json()["manualOverrideReviewItemId"] is None
    assert cleared.json()["candidates"][0]["selected"] is True


def test_source_override_rejects_candidate_from_another_sequence() -> None:
    repository = QualityRepository()
    response = _client(repository).post(
        f"/api/v1/admin/image-review-items/sequence-sources/{repository.game_id}/7/override",
        json={"reviewItemId": str(uuid4()), "selectedBy": "local-owner"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "IMAGE_SEQUENCE_SOURCE_CANDIDATE_INVALID"
