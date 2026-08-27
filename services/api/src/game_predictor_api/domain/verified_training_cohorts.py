"""Cumulative, immutable training cohorts built from human review decisions."""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

from game_predictor_api.domain.image_review_cohorts import (
    build_verified_board_manifest,
)
from game_predictor_api.domain.image_reviews import (
    ImageReviewConflictError,
    ImageReviewItem,
    canonical_image_review_bytes,
)

VERIFIED_TRAINING_COHORT_SCHEMA_VERSION = 1
VERIFIED_TRAINING_COHORT_DATASET_KIND = "verified-training-cohort-v1"
MODEL_QUALITY_FIRST_ADVISORY_THRESHOLD = 100
MODEL_QUALITY_NEXT_ADVISORY_THRESHOLD = 1000
MODEL_QUALITY_LOW_SYMBOL_SAMPLE_THRESHOLD = 10
MODEL_QUALITY_LOW_SOURCE_THRESHOLD = 3


@dataclass(frozen=True, slots=True)
class VerifiedTrainingCohortSource:
    game_id: UUID
    manifest: Mapping[str, object]
    manifest_bytes: bytes
    manifest_checksum_sha256: str
    boards: tuple[Mapping[str, object], ...]
    resolved_layout_count: int
    cell_sample_count: int
    source_image_count: int
    pending_item_count: int
    rejected_item_count: int
    incomplete_item_count: int
    warnings: tuple[str, ...]
    dataset_kind: str = VERIFIED_TRAINING_COHORT_DATASET_KIND
    manifest_schema_version: int = VERIFIED_TRAINING_COHORT_SCHEMA_VERSION
    cells: tuple[Mapping[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class VerifiedTrainingReviewState:
    game_id: UUID
    review_item_id: UUID
    recognized_board_id: UUID
    source_image_id: UUID
    import_job_id: UUID
    source_order_index: int
    position_index: int
    status: str
    resolution_revision: int
    geometry_revision: int
    source_checksum_sha256: str
    board_checksum_sha256: str
    pipeline_fingerprint: str


@dataclass(frozen=True, slots=True)
class CumulativeVerifiedTrainingSnapshot:
    review_states: tuple[VerifiedTrainingReviewState, ...]
    resolved_items: tuple[ImageReviewItem, ...]


@dataclass(frozen=True, slots=True)
class VerifiedTrainingCohort:
    id: UUID
    game_id: UUID
    iteration_number: int
    manifest_schema_version: int
    manifest_checksum_sha256: str
    resolved_layout_count: int
    cell_sample_count: int
    source_image_count: int
    pending_item_count: int
    rejected_item_count: int
    incomplete_item_count: int
    artifact_relative_path: str
    created_by: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class VerifiedTrainingCohortSnapshot:
    cohort: VerifiedTrainingCohort
    item_checksums: frozenset[str]


@dataclass(frozen=True, slots=True)
class SymbolTrainingCoverage:
    symbol_code: str
    sample_count: int


@dataclass(frozen=True, slots=True)
class ModelQualityAdvisoryThreshold:
    layout_count: int
    reached: bool


@dataclass(frozen=True, slots=True)
class ModelQualitySummary:
    game_id: UUID
    active_model_version: str | None
    active_model_checksum_sha256: str | None
    latest_cohort: VerifiedTrainingCohort | None
    manifest_checksum_sha256: str
    resolved_layout_count: int
    new_verified_layout_count: int
    cell_sample_count: int
    source_image_count: int
    pending_item_count: int
    rejected_item_count: int
    incomplete_item_count: int
    protected_item_count: int
    symbol_coverage: tuple[SymbolTrainingCoverage, ...]
    advisory_thresholds: tuple[ModelQualityAdvisoryThreshold, ...]
    warnings: tuple[str, ...]
    active_heavy_job: bool
    can_freeze: bool


def build_verified_training_cohort_source(
    *,
    game_id: UUID,
    items: Sequence[ImageReviewItem],
    review_states: Sequence[VerifiedTrainingReviewState] | None = None,
) -> VerifiedTrainingCohortSource:
    """Build one deterministic snapshot of every review item belonging to a game."""

    ordered_items = tuple(
        sorted(
            items,
            key=lambda item: (
                str(item.import_job_id),
                item.source_order_index,
                item.position_index,
                str(item.id),
            ),
        )
    )
    states = (
        tuple(_review_state_from_item(item) for item in ordered_items)
        if review_states is None
        else tuple(review_states)
    )
    ordered_states = tuple(
        sorted(
            states,
            key=lambda state: (
                str(state.import_job_id),
                state.source_order_index,
                state.position_index,
                str(state.review_item_id),
            ),
        )
    )
    if any(item.game_id != game_id for item in ordered_items) or any(
        state.game_id != game_id for state in ordered_states
    ):
        raise ImageReviewConflictError(
            "VERIFIED_TRAINING_COHORT_GAME_MISMATCH",
            "A cumulative training cohort cannot contain review items from another game.",
        )
    items_by_id = {item.id: item for item in ordered_items}
    if len(items_by_id) != len(ordered_items):
        raise ImageReviewConflictError(
            "VERIFIED_TRAINING_COHORT_ITEM_DUPLICATE",
            "A cumulative training cohort cannot contain a review item more than once.",
        )

    boards: list[Mapping[str, object]] = []
    review_state: list[dict[str, object]] = []
    pending_count = 0
    rejected_count = 0
    incomplete_count = 0
    for state in ordered_states:
        exclusion_reason: str | None = None
        if state.status == "pending":
            pending_count += 1
            exclusion_reason = "pending"
        elif state.status == "rejected":
            rejected_count += 1
            exclusion_reason = "human_rejected"
        elif state.status == "superseded":
            rejected_count += 1
            exclusion_reason = "superseded_by_canonical_sequence"
        elif state.status in {"accepted", "corrected"}:
            item = items_by_id.get(state.review_item_id)
            if item is None or _review_state_from_item(item) != state:
                raise ImageReviewConflictError(
                    "VERIFIED_TRAINING_COHORT_RESOLVED_ITEM_MISSING",
                    "A resolved review state is missing its complete board projection.",
                )
            try:
                boards.append(build_verified_board_manifest(item))
            except ImageReviewConflictError as error:
                incomplete_count += 1
                exclusion_reason = error.code
        else:
            raise ImageReviewConflictError(
                "VERIFIED_TRAINING_COHORT_STATUS_INVALID",
                "A review item has an unsupported status.",
            )
        review_state.append(
            {
                "reviewItemId": str(state.review_item_id),
                "recognizedBoardId": str(state.recognized_board_id),
                "sourceImageId": str(state.source_image_id),
                "importJobId": str(state.import_job_id),
                "status": state.status,
                "resolutionRevision": state.resolution_revision,
                "geometryRevision": state.geometry_revision,
                "sourceChecksumSha256": state.source_checksum_sha256,
                "boardChecksumSha256": state.board_checksum_sha256,
                "pipelineFingerprint": state.pipeline_fingerprint,
                "included": exclusion_reason is None,
                "exclusionReason": exclusion_reason,
            }
        )

    ordered_boards = tuple(
        sorted(
            boards,
            key=lambda board: (
                cast(int, board["sequenceNumber"]),
                cast(str, board["importJobId"]),
                cast(int, board["sourceOrderIndex"]),
                cast(int, board["positionIndex"]),
                cast(str, board["reviewItemId"]),
            ),
        )
    )
    source_ids = {cast(str, board["sourceImageId"]) for board in ordered_boards}
    manifest: dict[str, object] = {
        "schemaVersion": VERIFIED_TRAINING_COHORT_SCHEMA_VERSION,
        "datasetKind": VERIFIED_TRAINING_COHORT_DATASET_KIND,
        "gameId": str(game_id),
        "counts": {
            "resolvedLayouts": len(ordered_boards),
            "cellSamples": sum(
                len(cast(Sequence[object], board["cells"])) for board in ordered_boards
            ),
            "sourceImages": len(source_ids),
            "pendingItems": pending_count,
            "rejectedItems": rejected_count,
            "incompleteItems": incomplete_count,
        },
        "reviewState": review_state,
        "boards": ordered_boards,
    }
    manifest_bytes = canonical_image_review_bytes(manifest)
    warnings: list[str] = []
    if len(ordered_boards) < 100:
        warnings.append("LOW_VERIFIED_LAYOUT_COVERAGE")
    if incomplete_count:
        warnings.append("INCOMPLETE_HUMAN_DECISIONS_EXCLUDED")
    return VerifiedTrainingCohortSource(
        game_id=game_id,
        manifest=manifest,
        manifest_bytes=manifest_bytes,
        manifest_checksum_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        boards=ordered_boards,
        resolved_layout_count=len(ordered_boards),
        cell_sample_count=sum(
            len(cast(Sequence[object], board["cells"])) for board in ordered_boards
        ),
        source_image_count=len(source_ids),
        pending_item_count=pending_count,
        rejected_item_count=rejected_count,
        incomplete_item_count=incomplete_count,
        warnings=tuple(warnings),
    )


def _review_state_from_item(item: ImageReviewItem) -> VerifiedTrainingReviewState:
    return VerifiedTrainingReviewState(
        game_id=item.game_id,
        review_item_id=item.id,
        recognized_board_id=item.recognized_board_id,
        source_image_id=item.source_image_id,
        import_job_id=item.import_job_id,
        source_order_index=item.source_order_index,
        position_index=item.position_index,
        status=item.status,
        resolution_revision=item.resolution_revision,
        geometry_revision=item.geometry_revision,
        source_checksum_sha256=item.source_checksum_sha256,
        board_checksum_sha256=item.board_checksum_sha256,
        pipeline_fingerprint=item.pipeline_fingerprint,
    )


def build_model_quality_summary(
    *,
    source: VerifiedTrainingCohortSource,
    active_symbol_codes: Sequence[str],
    latest_snapshot: VerifiedTrainingCohortSnapshot | None,
    active_heavy_job: bool,
) -> ModelQualitySummary:
    """Build one deterministic, game-scoped readiness projection."""

    current_checksums = {
        hashlib.sha256(canonical_image_review_bytes(dict(board))).hexdigest()
        for board in source.boards
    }
    previous_checksums = frozenset() if latest_snapshot is None else latest_snapshot.item_checksums
    symbol_counts: Counter[str] = Counter()
    for board in source.boards:
        for cell in cast(Sequence[Mapping[str, object]], board["cells"]):
            symbol_counts[cast(str, cell["symbolCode"])] += 1
    ordered_symbol_codes = tuple(
        dict.fromkeys((*active_symbol_codes, *sorted(symbol_counts))).keys()
    )
    symbol_coverage = tuple(
        SymbolTrainingCoverage(
            symbol_code=symbol_code,
            sample_count=symbol_counts[symbol_code],
        )
        for symbol_code in ordered_symbol_codes
    )
    warnings = list(source.warnings)
    if not ordered_symbol_codes:
        warnings.append("NO_ACTIVE_SYMBOLS")
    for coverage in symbol_coverage:
        if coverage.sample_count < MODEL_QUALITY_LOW_SYMBOL_SAMPLE_THRESHOLD:
            warnings.append(f"LOW_SYMBOL_COVERAGE:{coverage.symbol_code}")
    if source.source_image_count < MODEL_QUALITY_LOW_SOURCE_THRESHOLD:
        warnings.append("LOW_SOURCE_IMAGE_COVERAGE")
    if active_heavy_job:
        warnings.append("ACTIVE_HEAVY_JOB_BLOCKS_COHORT_FREEZE")
    return ModelQualitySummary(
        game_id=source.game_id,
        active_model_version=None,
        active_model_checksum_sha256=None,
        latest_cohort=None if latest_snapshot is None else latest_snapshot.cohort,
        manifest_checksum_sha256=source.manifest_checksum_sha256,
        resolved_layout_count=source.resolved_layout_count,
        new_verified_layout_count=len(current_checksums - previous_checksums),
        cell_sample_count=source.cell_sample_count,
        source_image_count=source.source_image_count,
        pending_item_count=source.pending_item_count,
        rejected_item_count=source.rejected_item_count,
        incomplete_item_count=source.incomplete_item_count,
        protected_item_count=(
            source.resolved_layout_count + source.rejected_item_count + source.incomplete_item_count
        ),
        symbol_coverage=symbol_coverage,
        advisory_thresholds=(
            ModelQualityAdvisoryThreshold(
                layout_count=MODEL_QUALITY_FIRST_ADVISORY_THRESHOLD,
                reached=(source.resolved_layout_count >= MODEL_QUALITY_FIRST_ADVISORY_THRESHOLD),
            ),
            ModelQualityAdvisoryThreshold(
                layout_count=MODEL_QUALITY_NEXT_ADVISORY_THRESHOLD,
                reached=(source.resolved_layout_count >= MODEL_QUALITY_NEXT_ADVISORY_THRESHOLD),
            ),
        ),
        warnings=tuple(dict.fromkeys(warnings)),
        active_heavy_job=active_heavy_job,
        can_freeze=source.resolved_layout_count > 0 and not active_heavy_job,
    )


def require_pending_model_prediction_target(
    *,
    status: str,
    resolution_revision: int,
    expected_resolution_revision: int,
    geometry_revision: int,
    expected_geometry_revision: int,
) -> None:
    """Protect every human-resolved item from automatic model writes."""

    if status != "pending":
        raise ImageReviewConflictError(
            "MODEL_PREDICTION_HUMAN_DECISION_PROTECTED",
            "Automatic predictions can only target a currently pending review item.",
        )
    if (
        resolution_revision != expected_resolution_revision
        or geometry_revision != expected_geometry_revision
    ):
        raise ImageReviewConflictError(
            "MODEL_PREDICTION_TARGET_STALE",
            "The review or geometry revision changed before the automatic prediction write.",
        )


__all__ = [
    "VERIFIED_TRAINING_COHORT_DATASET_KIND",
    "VERIFIED_TRAINING_COHORT_SCHEMA_VERSION",
    "CumulativeVerifiedTrainingSnapshot",
    "ModelQualityAdvisoryThreshold",
    "ModelQualitySummary",
    "SymbolTrainingCoverage",
    "VerifiedTrainingCohort",
    "VerifiedTrainingCohortSnapshot",
    "VerifiedTrainingCohortSource",
    "VerifiedTrainingReviewState",
    "build_model_quality_summary",
    "build_verified_training_cohort_source",
    "require_pending_model_prediction_target",
]
