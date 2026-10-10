"""Per-position game mode of a sequence range (TASK-0936, D-537).

A position lies in ``super`` mode when the published series generation covers
it as a spin of a series (``trigger + 1 … trigger + length``); every other
position, the trigger board included, is in ``base`` mode.  The projection is
built from the super game markers of TASK-0935, so the modes, the row markers
and the response-level ``superGameState`` come from one snapshot.

A ``super`` position costs the kind's free spin cost (``0`` for
``wild_super_spins``) and is evaluated with the kind's series board
evaluation; a ``base`` position costs the rules' ``spin_cost``.  A game without
a super game kind has no markers, so every position is ``base`` and costs the
same as before this projection existed.

Pure: no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from game_predictor_worker.domain.super_games import (
    SuperGameKindDefinition,
    get_super_game_kind,
    is_known_super_game_kind,
)

from game_predictor_api.domain.super_game_markers import SuperGameMarkerKind, SuperGameMarkers


class SequenceMode(StrEnum):
    BASE = "base"
    SUPER = "super"


@dataclass(frozen=True, slots=True)
class PositionMode:
    """The mode of one sequence position.

    ``super_symbol_code`` and ``remaining_spins`` (spins of the series left
    after this one) are set only in ``super`` mode; ``generation_fresh`` is the
    freshness of the series generation the mode comes from.
    """

    sequence_number: int
    mode: SequenceMode
    super_symbol_code: str | None
    remaining_spins: int | None
    spin_cost_credits: int
    generation_fresh: bool

    @property
    def is_super(self) -> bool:
        return self.mode is SequenceMode.SUPER


@dataclass(frozen=True, slots=True)
class SequenceModeProjection:
    """Modes of the positions of one read, derived from its markers."""

    markers: SuperGameMarkers
    spin_cost: int

    @property
    def kind(self) -> SuperGameKindDefinition | None:
        """The game's super game kind, or ``None`` without a series evaluation."""

        code = self.markers.kind_code
        if not is_known_super_game_kind(code):
            return None
        kind = get_super_game_kind(code)
        return kind if kind.evaluate_series_board is not None else None

    def at(self, sequence_number: int) -> PositionMode:
        marker = self.markers.marker(sequence_number)
        fresh = self.markers.state.fresh
        kind = self.kind
        if (
            kind is None
            or marker is None
            or marker.kind is not SuperGameMarkerKind.IN_SERIES
            or marker.spin_index is None
        ):
            return PositionMode(
                sequence_number=sequence_number,
                mode=SequenceMode.BASE,
                super_symbol_code=None,
                remaining_spins=None,
                spin_cost_credits=self.spin_cost,
                generation_fresh=fresh,
            )
        return PositionMode(
            sequence_number=sequence_number,
            mode=SequenceMode.SUPER,
            super_symbol_code=marker.super_symbol_code,
            remaining_spins=max(marker.series_length - marker.spin_index, 0),
            spin_cost_credits=kind.free_spin_cost,
            generation_fresh=fresh,
        )


__all__ = ["PositionMode", "SequenceMode", "SequenceModeProjection"]
