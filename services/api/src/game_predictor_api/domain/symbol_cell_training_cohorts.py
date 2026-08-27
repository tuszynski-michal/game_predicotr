"""Deterministic selection of approved symbol crops for model training."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from uuid import UUID

from game_predictor_api.domain.image_reviews import ImageReviewConflictError

SYMBOL_CELL_TRAINING_COHORT_SCHEMA_VERSION = 2
SYMBOL_CELL_TRAINING_COHORT_DATASET_KIND = "verified-symbol-cell-training-cohort-v2"
DEFAULT_TARGET_SAMPLES_PER_SYMBOL = 1_000
DEFAULT_MAX_SAMPLES_PER_SYMBOL = 2_000
DEFAULT_MAX_SIMILARITY_COMPARISONS_PER_BAND = 32


@dataclass(frozen=True, slots=True)
class ApprovedSymbolCellCandidate:
    """One current, checksum-bound and human-approved training candidate."""

    cell_review_id: UUID
    review_item_id: UUID
    recognized_board_id: UUID
    source_image_id: UUID
    import_job_id: UUID
    assigned_symbol_id: UUID
    symbol_code: str
    sequence_number: int
    cell_index: int
    cell_revision: int
    geometry_revision: int
    crop_sample_id: str
    crop_relative_path: str
    crop_checksum_sha256: str
    source_checksum_sha256: str
    cropper_version: str
    prediction_symbol_code: str | None
    perceptual_hash_64: int
    mean_rgb: tuple[int, int, int]

    @property
    def is_human_correction(self) -> bool:
        return self.prediction_symbol_code != self.symbol_code


@dataclass(frozen=True, slots=True)
class SelectedSymbolCellSample:
    candidate: ApprovedSymbolCellCandidate
    selection_reason: str


@dataclass(frozen=True, slots=True)
class SymbolCellSelectionCoverage:
    symbol_code: str
    eligible_count: int
    exact_duplicate_count: int
    near_duplicate_count: int
    corrected_eligible_count: int
    selected_count: int
    selected_correction_count: int
    represented_source_count: int


@dataclass(frozen=True, slots=True)
class SymbolCellTrainingSelection:
    samples: tuple[SelectedSymbolCellSample, ...]
    coverage: tuple[SymbolCellSelectionCoverage, ...]


@dataclass(frozen=True, slots=True)
class SymbolCellSelectionConfig:
    target_samples_per_symbol: int = DEFAULT_TARGET_SAMPLES_PER_SYMBOL
    max_samples_per_symbol: int = DEFAULT_MAX_SAMPLES_PER_SYMBOL
    near_duplicate_hamming_distance: int = 4
    near_duplicate_color_distance: int = 24
    max_similarity_comparisons_per_band: int = DEFAULT_MAX_SIMILARITY_COMPARISONS_PER_BAND

    def validate(self) -> None:
        if self.target_samples_per_symbol <= 0:
            raise ValueError("target_samples_per_symbol must be positive")
        if self.max_samples_per_symbol < self.target_samples_per_symbol:
            raise ValueError("max_samples_per_symbol must be greater than or equal to the target")
        if not 0 <= self.near_duplicate_hamming_distance <= 64:
            raise ValueError("near_duplicate_hamming_distance must be between 0 and 64")
        if self.near_duplicate_color_distance < 0:
            raise ValueError("near_duplicate_color_distance cannot be negative")
        if self.max_similarity_comparisons_per_band <= 0:
            raise ValueError("max_similarity_comparisons_per_band must be positive")


def select_symbol_cell_training_samples(
    *,
    candidates: Iterable[ApprovedSymbolCellCandidate],
    active_symbol_codes: Sequence[str],
    config: SymbolCellSelectionConfig | None = None,
) -> SymbolCellTrainingSelection:
    """Select a bounded, diverse cohort without constructing an all-pairs matrix."""

    selection_config = config or SymbolCellSelectionConfig()
    selection_config.validate()
    ordered_symbols = tuple(dict.fromkeys(active_symbol_codes))
    active_symbols = frozenset(ordered_symbols)
    grouped: dict[str, list[ApprovedSymbolCellCandidate]] = defaultdict(list)
    for candidate in candidates:
        _validate_candidate(candidate, active_symbols=active_symbols)
        grouped[candidate.symbol_code].append(candidate)

    selected_samples: list[SelectedSymbolCellSample] = []
    coverage: list[SymbolCellSelectionCoverage] = []
    for symbol_code in ordered_symbols:
        symbol_candidates = tuple(grouped.get(symbol_code, ()))
        exact_unique, exact_duplicate_count = _deduplicate_exact(symbol_candidates)
        corrections = [candidate for candidate in exact_unique if candidate.is_human_correction]
        approvals = [candidate for candidate in exact_unique if not candidate.is_human_correction]
        selector = _BoundedNearDuplicateSelector(selection_config)

        selected_corrections = _select_source_diverse(
            corrections,
            selector=selector,
            remaining=selection_config.max_samples_per_symbol,
            reason="human_correction",
        )
        ordinary_limit = max(
            0,
            selection_config.target_samples_per_symbol - len(selected_corrections),
        )
        selected_approvals = _select_source_diverse(
            approvals,
            selector=selector,
            remaining=ordinary_limit,
            reason="diverse_approval",
        )
        selected = (*selected_corrections, *selected_approvals)
        selected_samples.extend(selected)
        coverage.append(
            SymbolCellSelectionCoverage(
                symbol_code=symbol_code,
                eligible_count=len(symbol_candidates),
                exact_duplicate_count=exact_duplicate_count,
                near_duplicate_count=selector.rejected_count,
                corrected_eligible_count=len(corrections),
                selected_count=len(selected),
                selected_correction_count=len(selected_corrections),
                represented_source_count=len(
                    {sample.candidate.source_image_id for sample in selected}
                ),
            )
        )
    return SymbolCellTrainingSelection(
        samples=tuple(selected_samples),
        coverage=tuple(coverage),
    )


def _validate_candidate(
    candidate: ApprovedSymbolCellCandidate,
    *,
    active_symbols: frozenset[str],
) -> None:
    if candidate.symbol_code not in active_symbols:
        raise ImageReviewConflictError(
            "SYMBOL_CELL_TRAINING_SYMBOL_INACTIVE",
            "A symbol-cell training candidate references an inactive symbol.",
        )
    if not 0 <= candidate.cell_index < 15 or candidate.sequence_number <= 0:
        raise ImageReviewConflictError(
            "SYMBOL_CELL_TRAINING_POSITION_INVALID",
            "A symbol-cell training candidate has an invalid board position.",
        )
    if candidate.cell_revision < 0 or candidate.geometry_revision < 0:
        raise ImageReviewConflictError(
            "SYMBOL_CELL_TRAINING_REVISION_INVALID",
            "A symbol-cell training candidate has an invalid revision.",
        )
    for checksum in (
        candidate.crop_checksum_sha256,
        candidate.source_checksum_sha256,
    ):
        if len(checksum) != 64 or any(
            character not in "0123456789abcdef" for character in checksum
        ):
            raise ImageReviewConflictError(
                "SYMBOL_CELL_TRAINING_CHECKSUM_INVALID",
                "A symbol-cell training candidate has an invalid checksum.",
            )
    if not 0 <= candidate.perceptual_hash_64 < 2**64:
        raise ImageReviewConflictError(
            "SYMBOL_CELL_TRAINING_DESCRIPTOR_INVALID",
            "A symbol-cell training candidate has an invalid visual descriptor.",
        )
    if any(channel < 0 or channel > 255 for channel in candidate.mean_rgb):
        raise ImageReviewConflictError(
            "SYMBOL_CELL_TRAINING_DESCRIPTOR_INVALID",
            "A symbol-cell training candidate has an invalid visual descriptor.",
        )


def _candidate_priority(candidate: ApprovedSymbolCellCandidate) -> tuple[object, ...]:
    return (
        candidate.sequence_number,
        candidate.cell_index,
        str(candidate.source_image_id),
        str(candidate.cell_review_id),
    )


def _deduplicate_exact(
    candidates: Sequence[ApprovedSymbolCellCandidate],
) -> tuple[tuple[ApprovedSymbolCellCandidate, ...], int]:
    by_checksum: dict[str, ApprovedSymbolCellCandidate] = {}
    for candidate in sorted(candidates, key=_candidate_priority):
        existing = by_checksum.get(candidate.crop_checksum_sha256)
        if existing is None or (candidate.is_human_correction and not existing.is_human_correction):
            by_checksum[candidate.crop_checksum_sha256] = candidate
    unique = tuple(sorted(by_checksum.values(), key=_candidate_priority))
    return unique, len(candidates) - len(unique)


def _select_source_diverse(
    candidates: Sequence[ApprovedSymbolCellCandidate],
    *,
    selector: _BoundedNearDuplicateSelector,
    remaining: int,
    reason: str,
) -> tuple[SelectedSymbolCellSample, ...]:
    if remaining <= 0:
        return ()
    by_source: dict[UUID, deque[ApprovedSymbolCellCandidate]] = defaultdict(deque)
    for candidate in sorted(candidates, key=_candidate_priority):
        by_source[candidate.source_image_id].append(candidate)
    source_ids = deque(sorted(by_source, key=str))
    selected: list[SelectedSymbolCellSample] = []
    while source_ids and len(selected) < remaining:
        source_id = source_ids.popleft()
        source_candidates = by_source[source_id]
        candidate = source_candidates.popleft()
        if selector.accept(candidate):
            selected.append(SelectedSymbolCellSample(candidate=candidate, selection_reason=reason))
        if source_candidates:
            source_ids.append(source_id)
    return tuple(selected)


class _BoundedNearDuplicateSelector:
    """LSH-backed near-duplicate gate with bounded comparisons per candidate."""

    def __init__(self, config: SymbolCellSelectionConfig) -> None:
        self._config = config
        self._bands: dict[tuple[int, int], deque[ApprovedSymbolCellCandidate]] = defaultdict(
            lambda: deque(maxlen=config.max_similarity_comparisons_per_band)
        )
        self.rejected_count = 0

    def accept(self, candidate: ApprovedSymbolCellCandidate) -> bool:
        compared: set[UUID] = set()
        for band_key in _perceptual_hash_bands(candidate.perceptual_hash_64):
            for existing in self._bands[band_key]:
                if existing.cell_review_id in compared:
                    continue
                compared.add(existing.cell_review_id)
                if _is_near_duplicate(candidate, existing, config=self._config):
                    self.rejected_count += 1
                    return False
        for band_key in _perceptual_hash_bands(candidate.perceptual_hash_64):
            self._bands[band_key].append(candidate)
        return True


def _perceptual_hash_bands(value: int) -> tuple[tuple[int, int], ...]:
    return tuple((index, (value >> (index * 16)) & 0xFFFF) for index in range(4))


def _is_near_duplicate(
    left: ApprovedSymbolCellCandidate,
    right: ApprovedSymbolCellCandidate,
    *,
    config: SymbolCellSelectionConfig,
) -> bool:
    if (left.perceptual_hash_64 ^ right.perceptual_hash_64).bit_count() > (
        config.near_duplicate_hamming_distance
    ):
        return False
    return sum(abs(a - b) for a, b in zip(left.mean_rgb, right.mean_rgb, strict=True)) <= (
        config.near_duplicate_color_distance
    )


__all__ = [
    "DEFAULT_MAX_SAMPLES_PER_SYMBOL",
    "DEFAULT_TARGET_SAMPLES_PER_SYMBOL",
    "SYMBOL_CELL_TRAINING_COHORT_DATASET_KIND",
    "SYMBOL_CELL_TRAINING_COHORT_SCHEMA_VERSION",
    "ApprovedSymbolCellCandidate",
    "SelectedSymbolCellSample",
    "SymbolCellSelectionConfig",
    "SymbolCellSelectionCoverage",
    "SymbolCellTrainingSelection",
    "select_symbol_cell_training_samples",
]
