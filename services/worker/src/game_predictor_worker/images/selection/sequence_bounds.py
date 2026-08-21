"""Inclusive sequence bounds shared by image-selection transports and algorithms."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .contracts import SelectionContractError, SequenceRange

BOARD_GROUP_SIZE = 9
_DISPLAY_RANGE = re.compile(
    r"^\s*(?P<first>[1-9][0-9]*)\s*-\s*(?P<last>[1-9][0-9]*)(?:\s+new)?\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class SequenceBounds:
    """A complete inclusive layout interval with deterministic groups of nine."""

    first: int
    last: int
    direction: str = "ascending"
    group_size: int = BOARD_GROUP_SIZE

    def __post_init__(self) -> None:
        if self.first < 1 or self.last < 1 or self.group_size < 1:
            raise SelectionContractError(
                "IMAGE_SELECTION_SEQUENCE_BOUNDS_INVALID",
                "Sequence bounds and group size must be positive.",
            )
        if self.direction not in {"ascending", "descending"}:
            raise SelectionContractError(
                "IMAGE_SELECTION_DIRECTION_INVALID",
                "Sequence direction must be ascending or descending.",
            )
        if self.direction == "ascending" and self.last < self.first:
            raise SelectionContractError(
                "IMAGE_SELECTION_SEQUENCE_BOUNDS_INVALID",
                "An ascending sequence cannot end before it starts.",
            )
        if self.direction == "descending" and self.last > self.first:
            raise SelectionContractError(
                "IMAGE_SELECTION_SEQUENCE_BOUNDS_INVALID",
                "A descending sequence cannot end after it starts.",
            )

    @property
    def sequence_count(self) -> int:
        return abs(self.last - self.first) + 1

    @property
    def expected_group_count(self) -> int:
        return (self.sequence_count + self.group_size - 1) // self.group_size

    def range_for_group(self, group_index: int) -> SequenceRange:
        if not 0 <= group_index < self.expected_group_count:
            raise SelectionContractError(
                "IMAGE_SELECTION_GROUP_INDEX_INVALID",
                "The group index is outside the declared sequence bounds.",
            )
        offset = group_index * self.group_size
        if self.direction == "ascending":
            start = self.first + offset
            end = min(self.last, start + self.group_size - 1)
        else:
            end = self.first - offset
            start = max(self.last, end - self.group_size + 1)
        return SequenceRange(start=start, end=end, confidence=1.0)

    def group_index_for_range(self, value: SequenceRange) -> int | None:
        anchor = value.start if self.direction == "ascending" else value.end
        offset = anchor - self.first if self.direction == "ascending" else self.first - anchor
        if offset < 0 or offset % self.group_size != 0:
            return None
        index = offset // self.group_size
        if index >= self.expected_group_count:
            return None
        expected = self.range_for_group(index)
        return index if (value.start, value.end) == (expected.start, expected.end) else None


def parse_sequence_bounds_display_name(
    display_name: str,
    *,
    first_sequence_number: int,
    direction: str,
) -> SequenceBounds | None:
    """Parse a strict ``first - last`` folder label; unrelated labels stay valid."""

    match = _DISPLAY_RANGE.fullmatch(display_name)
    if match is None:
        return None
    lower = int(match.group("first"))
    upper = int(match.group("last"))
    if lower > upper:
        raise SelectionContractError(
            "IMAGE_SELECTION_SEQUENCE_BOUNDS_INVALID",
            "The numeric folder range must be ordered from lower to higher.",
        )
    expected_first = lower if direction == "ascending" else upper
    last = upper if direction == "ascending" else lower
    if first_sequence_number != expected_first:
        raise SelectionContractError(
            "IMAGE_SELECTION_SEQUENCE_BOUNDS_MISMATCH",
            "The first sequence number does not match the numeric folder range.",
        )
    return SequenceBounds(first_sequence_number, last, direction)


__all__ = [
    "BOARD_GROUP_SIZE",
    "SequenceBounds",
    "parse_sequence_bounds_display_name",
]
