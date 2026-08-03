"""Application boundary for durable image-selection runs."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from game_predictor_api.domain.image_selections import (
    IMAGE_SELECTION_GROUP_PAGE_MAX,
    ImageSelectionCandidate,
    ImageSelectionError,
    ImageSelectionGroup,
    ImageSelectionGroupPage,
    ImageSelectionGroupStatus,
    ImageSelectionNotFoundError,
    ImageSelectionRun,
    create_image_selection_run,
)


class ImageSelectionRepository(Protocol):
    def game_exists(self, game_id: UUID) -> bool: ...

    def find_run_by_identity(
        self,
        *,
        game_id: UUID,
        input_manifest_sha256: str,
        selector_fingerprint: str,
    ) -> ImageSelectionRun | None: ...

    def add_run(self, run: ImageSelectionRun) -> tuple[ImageSelectionRun, bool]: ...

    def get_run(self, run_id: UUID) -> ImageSelectionRun | None: ...

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


class ImageSelectionService:
    def __init__(self, repository: ImageSelectionRepository) -> None:
        self._repository = repository

    def create_run(
        self,
        *,
        game_id: UUID,
        source_selection_id: UUID,
        input_manifest_sha256: str,
        selector_fingerprint: str,
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
        )
        if existing is not None:
            return existing, False
        run = create_image_selection_run(
            game_id=game_id,
            source_selection_id=source_selection_id,
            input_manifest_sha256=input_manifest_sha256,
            selector_fingerprint=selector_fingerprint,
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


__all__ = [
    "ImageSelectionRepository",
    "ImageSelectionService",
]
