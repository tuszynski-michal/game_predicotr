"""Super game markers of board-search reads (TASK-0935, D-535).

Board search and the approximate-win range show which boards are part of a
super game series (the trigger board or a spin of the series).  The marker of
one position is derived from the *published generation* of the game's series:
a position is the trigger of the series that starts after it, or a spin of the
series whose range ``trigger … trigger + length`` contains it.  A position that
no published series covers has no marker and is in base mode *according to that
generation*; whether the generation still reflects the input is the separate
response-level :class:`SuperGameState`.

This module is pure: no I/O, no ORM.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from uuid import UUID

from game_predictor_api.domain.super_game_series import (
    RunVerification,
    SeriesCompleteness,
    SuperGameState,
)


class SuperGameMarkerKind(StrEnum):
    TRIGGER = "trigger"
    IN_SERIES = "in_series"


@dataclass(frozen=True, slots=True)
class SuperGameMarker:
    """The super game role of one sequence position.

    ``spin_index`` is the 1-based spin of the series (``position - trigger``,
    so a retrigger board is the spin it occupies) and ``None`` for the trigger.
    """

    kind: SuperGameMarkerKind
    series_id: UUID
    spin_index: int | None
    series_length: int
    super_symbol_code: str | None
    completeness: SeriesCompleteness
    run_verification: RunVerification


def marker_for_position(
    *,
    position: int,
    series_id: UUID,
    trigger_sequence_number: int,
    series_length: int,
    super_symbol_code: str | None,
    completeness: SeriesCompleteness,
    run_verification: RunVerification,
) -> SuperGameMarker | None:
    """The marker of ``position`` within one series, or ``None`` outside it.

    A series covers ``trigger … trigger + length`` (the trigger plus its spins).
    """

    offset = position - trigger_sequence_number
    if offset < 0 or offset > series_length:
        return None
    is_trigger = offset == 0
    return SuperGameMarker(
        kind=SuperGameMarkerKind.TRIGGER if is_trigger else SuperGameMarkerKind.IN_SERIES,
        series_id=series_id,
        spin_index=None if is_trigger else offset,
        series_length=series_length,
        super_symbol_code=super_symbol_code,
        completeness=completeness,
        run_verification=run_verification,
    )


# Without a super game kind (or a read path that has no series source) nothing
# was derived: always fresh, no markers.
NO_SUPER_GAME_STATE = SuperGameState(
    input_version=0, generation_input_version=None, has_super_game=False
)


@dataclass(frozen=True, slots=True)
class SuperGameMarkers:
    """Markers of a set of positions plus the freshness of the generation they
    come from, both read in one statement (one snapshot)."""

    state: SuperGameState
    by_position: Mapping[int, SuperGameMarker] = field(default_factory=lambda: MappingProxyType({}))
    kind_code: str = "none"
    """The game's ``super_game_kind`` read in the same statement (TASK-0936)."""

    def marker(self, position: int) -> SuperGameMarker | None:
        return self.by_position.get(position)


__all__ = [
    "NO_SUPER_GAME_STATE",
    "SuperGameMarker",
    "SuperGameMarkerKind",
    "SuperGameMarkers",
    "marker_for_position",
]
