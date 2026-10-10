"""Port of the super game markers read by board search and approximate win."""

from __future__ import annotations

from collections.abc import Collection
from typing import Protocol
from uuid import UUID

from game_predictor_api.domain.super_game_markers import SuperGameMarkers


class SuperGameMarkerSource(Protocol):
    """Markers of ``positions`` and the freshness of their generation.

    Implementations read the series and the derivation state of one game in a
    single snapshot, so a marker never pairs with the freshness of another
    generation.  A game without a super game kind yields no markers and a
    fresh state.
    """

    def markers(self, game_id: UUID, positions: Collection[int]) -> SuperGameMarkers: ...


__all__ = ["SuperGameMarkerSource"]
