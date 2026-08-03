"""Application boundary for durable image-selection runs."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol
from uuid import UUID

from game_predictor_worker.images.selection.contracts import SelectionContractError
from game_predictor_worker.images.selection.output import verify_curated_image_manifest

from game_predictor_api.domain.image_selections import (
    IMAGE_SELECTION_GROUP_PAGE_MAX,
    ImageSelectionCandidate,
    ImageSelectionConflictError,
    ImageSelectionError,
    ImageSelectionGroup,
    ImageSelectionGroupPage,
    ImageSelectionGroupStatus,
    ImageSelectionNotFoundError,
    ImageSelectionRun,
    create_image_selection_run,
    record_image_selection_output,
)


@dataclass(frozen=True, slots=True)
class ImageSelectionHandoffSource:
    run: ImageSelectionRun
    output_directory: Path
    supported_file_count: int


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

    def save_run(self, run: ImageSelectionRun) -> ImageSelectionRun: ...

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
    def __init__(
        self,
        repository: ImageSelectionRepository,
        *,
        artifact_root: Path | None = None,
    ) -> None:
        self._repository = repository
        self._artifact_root = None if artifact_root is None else artifact_root.resolve()

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
        expected_ranges = {
            (group.range_start, group.range_end)
            for group in groups
            if group.status
            in {
                ImageSelectionGroupStatus.AUTO_SELECTED,
                ImageSelectionGroupStatus.MANUALLY_SELECTED,
            }
        }
        manifest_ranges = {
            (entry.range_start, entry.range_end) for entry in manifest.entries
        }
        if expected_ranges != manifest_ranges:
            raise ImageSelectionConflictError(
                "IMAGE_SELECTION_MANIFEST_MISMATCH",
                "The curated output ranges differ from the durable group decisions.",
            )
        return ImageSelectionHandoffSource(
            run=run,
            output_directory=manifest_path.parent,
            supported_file_count=len(manifest.entries),
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

    def _managed_path(self, relative_path: str) -> Path:
        assert self._artifact_root is not None
        posix = PurePosixPath(relative_path)
        try:
            resolved = (
                self._artifact_root / Path(*posix.parts)
            ).resolve(strict=True)
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
    "ImageSelectionRepository",
    "ImageSelectionHandoffSource",
    "ImageSelectionService",
]
