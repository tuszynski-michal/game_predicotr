"""Pure, fail-closed quality ranking for EOF-finalized V7 occurrences."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from .contracts import SemiAutomaticSelectionRange
from .v7_configuration import V7BorderStyle
from .v7_occurrences import V7Occurrence, V7OccurrenceTracker
from .v7_range_proof import V7RangeProofKind

V7_QUALITY_RANKING_VERSION = "v7-quality-ranking-v1"
V7_FULL_PAGE_BOARD_COUNT = 9


class V7QualityError(ValueError):
    """A quality payload cannot safely participate in automatic selection."""


class V7SymbolContentLoss(StrEnum):
    NONE = "none"
    MINOR = "minor"
    MAJOR = "major"
    UNKNOWN = "unknown"


class V7BoardReadability(StrEnum):
    CLEAR = "clear"
    READABLE = "readable"
    UNREADABLE = "unreadable"
    UNKNOWN = "unknown"


class V7BoardVisibility(StrEnum):
    FULL = "full"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class V7BlurSeverity(StrEnum):
    NONE = "none"
    LIGHT = "light"
    HEAVY = "heavy"
    UNKNOWN = "unknown"


class V7OcclusionSeverity(StrEnum):
    NONE = "none"
    PARTIAL = "partial"
    SIGNIFICANT = "significant"
    UNKNOWN = "unknown"


class V7DecorationVisibility(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    MISSING = "missing"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


class V7CropEdge(StrEnum):
    TOP = "top"
    BOTTOM = "bottom"
    LEFT = "left"
    RIGHT = "right"


class V7QualityWarning(StrEnum):
    SYMBOL_CONTENT_LOSS = "symbol_content_loss"
    SYMBOL_VISIBILITY_UNKNOWN = "symbol_visibility_unknown"
    PARTIAL_VISIBILITY = "partial_visibility"
    VISIBILITY_UNKNOWN = "visibility_unknown"
    UNREADABLE_BOARD = "unreadable_board"
    READABILITY_UNKNOWN = "readability_unknown"
    BLUR = "blur"
    OCCLUSION = "occlusion"
    DECORATION_LOSS = "decoration_loss"
    DECORATION_UNKNOWN = "decoration_unknown"
    TOP_CROPPED = "top_cropped"
    BOTTOM_CROPPED = "bottom_cropped"
    LEFT_CROPPED = "left_cropped"
    RIGHT_CROPPED = "right_cropped"


@dataclass(frozen=True, slots=True)
class V7BoardQuality:
    """Measured, categorical quality of one declared 3×3 board position."""

    position_index: int
    symbol_content_loss: V7SymbolContentLoss
    readability: V7BoardReadability
    visibility: V7BoardVisibility
    blur: V7BlurSeverity
    occlusion: V7OcclusionSeverity
    decoration: V7DecorationVisibility
    cropped_edges: frozenset[V7CropEdge] = frozenset()

    def __post_init__(self) -> None:
        if (
            not 0 <= self.position_index < V7_FULL_PAGE_BOARD_COUNT
            or not isinstance(self.symbol_content_loss, V7SymbolContentLoss)
            or not isinstance(self.readability, V7BoardReadability)
            or not isinstance(self.visibility, V7BoardVisibility)
            or not isinstance(self.blur, V7BlurSeverity)
            or not isinstance(self.occlusion, V7OcclusionSeverity)
            or not isinstance(self.decoration, V7DecorationVisibility)
            or (
                self.visibility is V7BoardVisibility.UNKNOWN
                and self.symbol_content_loss
                in {V7SymbolContentLoss.NONE, V7SymbolContentLoss.MINOR}
            )
        ):
            raise V7QualityError("V7 board quality payload is invalid.")
        if any(not isinstance(edge, V7CropEdge) for edge in self.cropped_edges):
            raise V7QualityError("V7 board quality crop edges are invalid.")


@dataclass(frozen=True, slots=True)
class V7FrameQuality:
    """Quality measurements of every board on one source JPEG."""

    source_id: str
    source_index: int
    boards: tuple[V7BoardQuality, ...]

    def __post_init__(self) -> None:
        positions = tuple(item.position_index for item in self.boards)
        if (
            not self.source_id
            or self.source_index < 0
            or positions != tuple(range(V7_FULL_PAGE_BOARD_COUNT))
        ):
            raise V7QualityError("V7 frame quality must describe each 3x3 board once in order.")

    def summarize(self, border_style: V7BorderStyle) -> V7FrameQualitySummary:
        """Aggregate by the riskiest board; never average an impaired board away."""

        warnings: set[V7QualityWarning] = set()
        for board in self.boards:
            warnings.update(_warnings_for_board(board, border_style))
        return V7FrameQualitySummary(
            symbol_content_loss=max(
                _content_loss_penalty(item.symbol_content_loss) for item in self.boards
            ),
            readability=max(_readability_penalty(item.readability) for item in self.boards),
            visibility=max(_visibility_penalty(item.visibility) for item in self.boards),
            blur=max(_blur_penalty(item.blur) for item in self.boards),
            occlusion=max(_occlusion_penalty(item.occlusion) for item in self.boards),
            decoration=max(
                _decoration_penalty(item.decoration, border_style) for item in self.boards
            ),
            warnings=tuple(sorted(warnings, key=lambda item: item.value)),
        )


@dataclass(frozen=True, slots=True)
class V7FrameQualitySummary:
    """Lexicographic quality dimensions, where lower is always safer."""

    symbol_content_loss: int
    readability: int
    visibility: int
    blur: int
    occlusion: int
    decoration: int
    warnings: tuple[V7QualityWarning, ...]

    def __post_init__(self) -> None:
        if any(
            not 0 <= value <= 3
            for value in (
                self.symbol_content_loss,
                self.readability,
                self.visibility,
                self.blur,
                self.occlusion,
                self.decoration,
            )
        ):
            raise V7QualityError("V7 frame quality summary contains an invalid penalty.")

    @property
    def quality_key(self) -> tuple[int, int, int, int, int, int]:
        return (
            self.symbol_content_loss,
            self.readability,
            self.visibility,
            self.blur,
            self.occlusion,
            self.decoration,
        )

    @property
    def is_unreadable(self) -> bool:
        """Only a confirmed unreadable board uses the safety precedence below."""

        return self.readability == _readability_penalty(V7BoardReadability.UNREADABLE)


@dataclass(frozen=True, slots=True)
class V7RepresentativeSelection:
    """One final in-memory proposal for one expected range; never an output write."""

    expected_index: int
    sequence_range: SemiAutomaticSelectionRange
    occurrence_id: str
    source_id: str
    source_index: int
    proof_kinds: tuple[V7RangeProofKind, ...]
    quality: V7FrameQualitySummary
    occurrence_center_distance_numerator: int

    @property
    def rank_key(self) -> tuple[int, int, int, int, int, int, int, int, int, str]:
        return (
            # A whole page that cannot be read loses to a readable page with a
            # bounded minor crop. Ordinary readable/light blur still compares
            # after symbol-content loss, as does every other soft signal.
            int(self.quality.is_unreadable),
            *self.quality.quality_key,
            self.occurrence_center_distance_numerator,
            self.source_index,
            self.source_id,
        )


def rank_v7_representatives(
    tracker: V7OccurrenceTracker,
    frame_qualities: Iterable[V7FrameQuality],
    *,
    border_style: V7BorderStyle,
) -> tuple[V7RepresentativeSelection, ...]:
    """Choose one eligible candidate per range only after tracker EOF finalization.

    The tracker enforces source order and calls ``global_occurrences()``, which
    rejects invocation before EOF.  A quality sample becomes eligible only when
    its source is the strong proof source or a named support of a valid 3+3
    proof in that occurrence.  An unproved but beautiful neighbour is ignored.
    """

    occurrences = tracker.global_occurrences()
    quality_by_source = _quality_by_source(frame_qualities)
    candidates_by_expected_index: dict[int, list[V7RepresentativeSelection]] = {}
    for occurrence in occurrences:
        for source_id, proof_kinds in _eligible_source_proofs(occurrence).items():
            source_index = tracker.source_index_for(source_id)
            if source_index is None:
                raise V7QualityError("V7 occurrence proof refers to an unscanned source.")
            if not occurrence.first_source_index <= source_index <= occurrence.last_source_index:
                raise V7QualityError("V7 occurrence proof support is outside its occurrence.")
            quality = quality_by_source.get((source_id, source_index))
            if quality is None:
                raise V7QualityError("V7 eligible source has no frame quality measurement.")
            summary = quality.summarize(border_style)
            candidate = V7RepresentativeSelection(
                expected_index=occurrence.expected_index,
                sequence_range=occurrence.sequence_range,
                occurrence_id=occurrence.occurrence_id,
                source_id=source_id,
                source_index=source_index,
                proof_kinds=tuple(sorted(proof_kinds, key=lambda item: item.value)),
                quality=summary,
                occurrence_center_distance_numerator=abs(
                    2 * source_index - occurrence.first_source_index - occurrence.last_source_index
                ),
            )
            candidates_by_expected_index.setdefault(occurrence.expected_index, []).append(candidate)
    return tuple(
        min(candidates, key=lambda item: item.rank_key)
        for _, candidates in sorted(candidates_by_expected_index.items())
    )


def _quality_by_source(
    frame_qualities: Iterable[V7FrameQuality],
) -> dict[tuple[str, int], V7FrameQuality]:
    result: dict[tuple[str, int], V7FrameQuality] = {}
    for quality in frame_qualities:
        key = (quality.source_id, quality.source_index)
        if key in result:
            raise V7QualityError("V7 frame quality was measured more than once for one source.")
        result[key] = quality
    return result


def _eligible_source_proofs(
    occurrence: V7Occurrence,
) -> dict[str, set[V7RangeProofKind]]:
    result: dict[str, set[V7RangeProofKind]] = {}
    for proof in occurrence.proven_sources:
        source_ids: tuple[str, ...]
        if proof.proof_kind is V7RangeProofKind.STRONG_FIVE_LABEL:
            source_ids = (proof.source_id,)
        elif proof.proof_kind is V7RangeProofKind.MULTI_FRAME_THREE_PLUS_THREE:
            source_ids = proof.supporting_source_ids
        else:
            raise V7QualityError("V7 occurrence contains an ineligible proof kind.")
        for source_id in source_ids:
            result.setdefault(source_id, set()).add(proof.proof_kind)
    return result


def _warnings_for_board(
    board: V7BoardQuality,
    border_style: V7BorderStyle,
) -> set[V7QualityWarning]:
    result: set[V7QualityWarning] = set()
    if board.symbol_content_loss is not V7SymbolContentLoss.NONE:
        result.add(
            V7QualityWarning.SYMBOL_VISIBILITY_UNKNOWN
            if board.symbol_content_loss is V7SymbolContentLoss.UNKNOWN
            else V7QualityWarning.SYMBOL_CONTENT_LOSS
        )
    if board.visibility is V7BoardVisibility.PARTIAL:
        result.add(V7QualityWarning.PARTIAL_VISIBILITY)
    elif board.visibility is V7BoardVisibility.UNKNOWN:
        result.add(V7QualityWarning.VISIBILITY_UNKNOWN)
    if board.readability is V7BoardReadability.UNREADABLE:
        result.add(V7QualityWarning.UNREADABLE_BOARD)
    elif board.readability is V7BoardReadability.UNKNOWN:
        result.add(V7QualityWarning.READABILITY_UNKNOWN)
    if board.blur is not V7BlurSeverity.NONE:
        result.add(V7QualityWarning.BLUR)
    if board.occlusion is not V7OcclusionSeverity.NONE:
        result.add(V7QualityWarning.OCCLUSION)
    decoration_penalty = _decoration_penalty(board.decoration, border_style)
    if decoration_penalty:
        result.add(
            V7QualityWarning.DECORATION_UNKNOWN
            if decoration_penalty == 2
            else V7QualityWarning.DECORATION_LOSS
        )
    edge_warnings = {
        V7CropEdge.TOP: V7QualityWarning.TOP_CROPPED,
        V7CropEdge.BOTTOM: V7QualityWarning.BOTTOM_CROPPED,
        V7CropEdge.LEFT: V7QualityWarning.LEFT_CROPPED,
        V7CropEdge.RIGHT: V7QualityWarning.RIGHT_CROPPED,
    }
    result.update(edge_warnings[edge] for edge in board.cropped_edges)
    return result


def _content_loss_penalty(value: V7SymbolContentLoss) -> int:
    return {
        V7SymbolContentLoss.NONE: 0,
        V7SymbolContentLoss.MINOR: 1,
        V7SymbolContentLoss.UNKNOWN: 2,
        V7SymbolContentLoss.MAJOR: 3,
    }[value]


def _readability_penalty(value: V7BoardReadability) -> int:
    return {
        V7BoardReadability.CLEAR: 0,
        V7BoardReadability.READABLE: 1,
        V7BoardReadability.UNKNOWN: 2,
        V7BoardReadability.UNREADABLE: 3,
    }[value]


def _visibility_penalty(value: V7BoardVisibility) -> int:
    return {
        V7BoardVisibility.FULL: 0,
        V7BoardVisibility.PARTIAL: 1,
        V7BoardVisibility.UNKNOWN: 2,
    }[value]


def _blur_penalty(value: V7BlurSeverity) -> int:
    return {
        V7BlurSeverity.NONE: 0,
        V7BlurSeverity.LIGHT: 1,
        V7BlurSeverity.UNKNOWN: 2,
        V7BlurSeverity.HEAVY: 3,
    }[value]


def _occlusion_penalty(value: V7OcclusionSeverity) -> int:
    return {
        V7OcclusionSeverity.NONE: 0,
        V7OcclusionSeverity.PARTIAL: 1,
        V7OcclusionSeverity.UNKNOWN: 2,
        V7OcclusionSeverity.SIGNIFICANT: 3,
    }[value]


def _decoration_penalty(value: V7DecorationVisibility, border_style: V7BorderStyle) -> int:
    if value is V7DecorationVisibility.NOT_APPLICABLE:
        return 0 if border_style is V7BorderStyle.IRREGULAR_OR_NONE else 2
    return {
        V7DecorationVisibility.COMPLETE: 0,
        V7DecorationVisibility.PARTIAL: 1,
        V7DecorationVisibility.UNKNOWN: 2,
        V7DecorationVisibility.MISSING: 3,
    }[value]
