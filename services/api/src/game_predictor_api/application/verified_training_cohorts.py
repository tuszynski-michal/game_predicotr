"""Application boundary for cumulative verified training cohorts."""

from __future__ import annotations

import hashlib
import os
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol, cast
from uuid import UUID

from game_predictor_api.domain.image_review_cohorts import validate_cohort_actor
from game_predictor_api.domain.image_reviews import (
    ImageReviewConflictError,
    canonical_image_review_bytes,
)
from game_predictor_api.domain.symbol_cell_training_cohorts import (
    SYMBOL_CELL_TRAINING_COHORT_DATASET_KIND,
    SYMBOL_CELL_TRAINING_COHORT_SCHEMA_VERSION,
    ApprovedSymbolCellCandidate,
    build_symbol_cell_training_manifest,
    select_symbol_cell_training_samples,
)
from game_predictor_api.domain.verified_training_cohorts import (
    CumulativeVerifiedTrainingSnapshot,
    ModelQualitySummary,
    SymbolCellTrainingExclusionCounts,
    VerifiedTrainingCohort,
    VerifiedTrainingCohortSnapshot,
    VerifiedTrainingCohortSource,
    build_model_quality_summary,
    build_verified_training_cohort_source,
)


class VerifiedTrainingCohortSourceRepository(Protocol):
    def active_symbol_codes(self, game_id: UUID) -> Sequence[str]: ...

    def has_active_heavy_job(self, *, game_id: UUID) -> bool: ...

    def cumulative_verified_snapshot(
        self,
        *,
        game_id: UUID,
    ) -> CumulativeVerifiedTrainingSnapshot: ...

    def lock_cumulative_verified_snapshot(
        self,
        *,
        game_id: UUID,
    ) -> CumulativeVerifiedTrainingSnapshot: ...

    def lock_model_prediction_target(
        self,
        *,
        review_item_id: UUID,
        expected_resolution_revision: int,
        expected_geometry_revision: int,
    ) -> None: ...


class VerifiedTrainingCohortRepository(Protocol):
    def get(self, *, cohort_id: UUID) -> VerifiedTrainingCohort | None: ...

    def latest_snapshot(
        self,
        *,
        game_id: UUID,
    ) -> VerifiedTrainingCohortSnapshot | None: ...

    def find_by_idempotency(
        self,
        *,
        game_id: UUID,
        idempotency_key: UUID,
    ) -> tuple[VerifiedTrainingCohort, str] | None: ...

    def find_by_manifest(
        self,
        *,
        game_id: UUID,
        manifest_checksum_sha256: str,
    ) -> VerifiedTrainingCohort | None: ...

    def next_iteration(self, *, game_id: UUID) -> int: ...

    def save(
        self,
        *,
        source: VerifiedTrainingCohortSource,
        iteration_number: int,
        idempotency_key: UUID,
        command_sha256: str,
        artifact_relative_path: str,
        created_by: str,
    ) -> VerifiedTrainingCohort: ...


@dataclass(frozen=True, slots=True)
class SymbolCellTrainingSourceInventory:
    candidates: tuple[ApprovedSymbolCellCandidate, ...]
    exclusions: SymbolCellTrainingExclusionCounts


class SymbolCellTrainingSourceRepository(Protocol):
    def active_symbol_codes(self, game_id: UUID) -> Sequence[str]: ...

    def inventory(self, *, game_id: UUID, lock_game: bool) -> SymbolCellTrainingSourceInventory: ...


class VerifiedTrainingCohortArtifactStore:
    def __init__(self, artifact_root: Path) -> None:
        self._managed_root = artifact_root.resolve() / "data"

    def write(self, source: VerifiedTrainingCohortSource) -> str:
        if hashlib.sha256(source.manifest_bytes).hexdigest() != source.manifest_checksum_sha256:
            raise ImageReviewConflictError(
                "VERIFIED_TRAINING_COHORT_CHECKSUM_INVALID",
                "The training cohort manifest checksum does not match its bytes.",
            )
        relative = PurePosixPath(
            "training",
            source.game_id.hex,
            source.manifest_checksum_sha256,
            "cohort.json",
        )
        destination = self._managed_root.joinpath(*relative.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            self.verify(relative.as_posix(), source.manifest_checksum_sha256)
            return relative.as_posix()
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=destination.parent,
                prefix=".tmp-",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_name = handle.name
                handle.write(source.manifest_bytes)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, destination)
            temporary_name = None
        finally:
            if temporary_name is not None:
                Path(temporary_name).unlink(missing_ok=True)
        self.verify(relative.as_posix(), source.manifest_checksum_sha256)
        return relative.as_posix()

    def verify(self, artifact_relative_path: str, checksum: str) -> None:
        relative = PurePosixPath(artifact_relative_path)
        if relative.is_absolute() or ".." in relative.parts or "\\" in artifact_relative_path:
            raise ImageReviewConflictError(
                "VERIFIED_TRAINING_COHORT_ARTIFACT_UNSAFE",
                "The training cohort artifact path is unsafe.",
            )
        candidate = self._managed_root.joinpath(*relative.parts).resolve()
        if not candidate.is_relative_to(self._managed_root) or candidate.is_symlink():
            raise ImageReviewConflictError(
                "VERIFIED_TRAINING_COHORT_ARTIFACT_UNSAFE",
                "The training cohort artifact is outside managed storage.",
            )
        if not candidate.is_file():
            raise ImageReviewConflictError(
                "VERIFIED_TRAINING_COHORT_ARTIFACT_MISSING",
                "The immutable training cohort artifact is unavailable.",
            )
        digest = hashlib.sha256()
        with candidate.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        if digest.hexdigest() != checksum:
            raise ImageReviewConflictError(
                "VERIFIED_TRAINING_COHORT_ARTIFACT_CHANGED",
                "The immutable training cohort artifact checksum changed.",
            )


class VerifiedTrainingCohortService:
    def __init__(
        self,
        source_repository: VerifiedTrainingCohortSourceRepository,
        cohort_repository: VerifiedTrainingCohortRepository,
        artifact_store: VerifiedTrainingCohortArtifactStore,
        symbol_cell_source_repository: SymbolCellTrainingSourceRepository | None = None,
    ) -> None:
        self._source_repository = source_repository
        self._cohort_repository = cohort_repository
        self._artifact_store = artifact_store
        self._symbol_cell_source_repository = symbol_cell_source_repository

    def preview(self, *, game_id: UUID) -> VerifiedTrainingCohortSource:
        if self._symbol_cell_source_repository is not None:
            return self._symbol_cell_source(game_id=game_id, lock_game=False)
        snapshot = self._source_repository.cumulative_verified_snapshot(game_id=game_id)
        return build_verified_training_cohort_source(
            game_id=game_id,
            items=snapshot.resolved_items,
            review_states=snapshot.review_states,
        )

    def model_quality(self, *, game_id: UUID) -> ModelQualitySummary:
        source = self.preview(game_id=game_id)
        return build_model_quality_summary(
            source=source,
            active_symbol_codes=self._source_repository.active_symbol_codes(game_id),
            latest_snapshot=self._cohort_repository.latest_snapshot(game_id=game_id),
            active_heavy_job=self._source_repository.has_active_heavy_job(game_id=game_id),
        )

    def freeze(
        self,
        *,
        game_id: UUID,
        idempotency_key: UUID,
        created_by: str,
        expected_manifest_checksum_sha256: str,
    ) -> tuple[VerifiedTrainingCohort, bool]:
        actor = validate_cohort_actor(created_by)
        command_sha256 = hashlib.sha256(
            canonical_image_review_bytes(
                {
                    "gameId": str(game_id),
                    "createdBy": actor,
                    "expectedManifestChecksumSha256": expected_manifest_checksum_sha256,
                }
            )
        ).hexdigest()
        prior = self._cohort_repository.find_by_idempotency(
            game_id=game_id,
            idempotency_key=idempotency_key,
        )
        if prior is not None:
            cohort, prior_command_sha256 = prior
            if prior_command_sha256 != command_sha256:
                raise ImageReviewConflictError(
                    "VERIFIED_TRAINING_COHORT_IDEMPOTENCY_CONFLICT",
                    "The idempotency key already represents another freeze command.",
                )
            self._artifact_store.verify(
                cohort.artifact_relative_path,
                cohort.manifest_checksum_sha256,
            )
            return cohort, False

        if self._source_repository.has_active_heavy_job(game_id=game_id):
            raise ImageReviewConflictError(
                "VERIFIED_TRAINING_COHORT_HEAVY_JOB_ACTIVE",
                "Another heavy operation is active for this game.",
            )

        if self._symbol_cell_source_repository is None:
            snapshot = self._source_repository.lock_cumulative_verified_snapshot(game_id=game_id)
            source = build_verified_training_cohort_source(
                game_id=game_id,
                items=snapshot.resolved_items,
                review_states=snapshot.review_states,
            )
        else:
            source = self._symbol_cell_source(game_id=game_id, lock_game=True)
        if source.manifest_checksum_sha256 != expected_manifest_checksum_sha256:
            raise ImageReviewConflictError(
                "VERIFIED_TRAINING_COHORT_PREVIEW_STALE",
                "The verified training cohort changed after the preview; reload it.",
            )
        if source.resolved_layout_count == 0:
            raise ImageReviewConflictError(
                "VERIFIED_TRAINING_COHORT_EMPTY",
                "At least one current approved symbol crop is required.",
            )
        existing = self._cohort_repository.find_by_manifest(
            game_id=game_id,
            manifest_checksum_sha256=source.manifest_checksum_sha256,
        )
        if existing is not None:
            self._artifact_store.verify(
                existing.artifact_relative_path,
                existing.manifest_checksum_sha256,
            )
            return existing, False
        artifact_relative_path = self._artifact_store.write(source)
        return (
            self._cohort_repository.save(
                source=source,
                iteration_number=self._cohort_repository.next_iteration(game_id=game_id),
                idempotency_key=idempotency_key,
                command_sha256=command_sha256,
                artifact_relative_path=artifact_relative_path,
                created_by=actor,
            ),
            True,
        )

    def _symbol_cell_source(
        self, *, game_id: UUID, lock_game: bool
    ) -> VerifiedTrainingCohortSource:
        repository = self._symbol_cell_source_repository
        if repository is None:
            raise AssertionError("The symbol-cell source repository is not configured.")
        inventory = repository.inventory(game_id=game_id, lock_game=lock_game)
        selection = select_symbol_cell_training_samples(
            candidates=inventory.candidates,
            active_symbol_codes=repository.active_symbol_codes(game_id),
        )
        manifest, content, checksum = build_symbol_cell_training_manifest(
            game_id=game_id,
            selection=selection,
            exclusion_counts={
                "changedCrop": inventory.exclusions.changed_crop,
                "gridIssue": inventory.exclusions.grid_issue,
                "missingAsset": inventory.exclusions.missing_asset,
                "unknown": inventory.exclusions.unknown,
                "unreadable": inventory.exclusions.unreadable,
            },
        )
        represented_boards = {sample.candidate.recognized_board_id for sample in selection.samples}
        represented_sources = {sample.candidate.source_image_id for sample in selection.samples}
        warnings = tuple(
            f"LOW_SYMBOL_COVERAGE:{item.symbol_code}"
            for item in selection.coverage
            if item.selected_count < 10
        )
        return VerifiedTrainingCohortSource(
            game_id=game_id,
            manifest=manifest,
            manifest_bytes=content,
            manifest_checksum_sha256=checksum,
            boards=(),
            resolved_layout_count=len(represented_boards),
            cell_sample_count=len(selection.samples),
            source_image_count=len(represented_sources),
            pending_item_count=0,
            rejected_item_count=0,
            incomplete_item_count=0,
            warnings=warnings,
            dataset_kind=SYMBOL_CELL_TRAINING_COHORT_DATASET_KIND,
            manifest_schema_version=SYMBOL_CELL_TRAINING_COHORT_SCHEMA_VERSION,
            cells=tuple(cast(Sequence[Mapping[str, object]], manifest["cells"])),
            training_exclusions=inventory.exclusions,
        )

    def authorize_model_prediction_write(
        self,
        *,
        review_item_id: UUID,
        expected_resolution_revision: int,
        expected_geometry_revision: int,
    ) -> None:
        self._source_repository.lock_model_prediction_target(
            review_item_id=review_item_id,
            expected_resolution_revision=expected_resolution_revision,
            expected_geometry_revision=expected_geometry_revision,
        )


__all__ = [
    "VerifiedTrainingCohortArtifactStore",
    "VerifiedTrainingCohortRepository",
    "VerifiedTrainingCohortService",
    "VerifiedTrainingCohortSourceRepository",
    "SymbolCellTrainingSourceRepository",
    "SymbolCellTrainingSourceInventory",
]
