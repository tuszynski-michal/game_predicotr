"""Registry of the super game kinds a game can select (D-535).

The order of :data:`SUPER_GAME_KINDS` is the order shown to the operator;
``none`` is always first and is the default of every game.
"""

from __future__ import annotations

from typing import Final

from game_predictor_worker.domain.super_games.definition import SuperGameKindDefinition
from game_predictor_worker.domain.super_games.wild_super_spins import WILD_SUPER_SPINS

NO_SUPER_GAME_KIND: Final = SuperGameKindDefinition(
    code="none",
    label="Brak",
    series_length=0,
    retrigger_extension=0,
    free_spin_cost=0,
)

SUPER_GAME_KINDS: Final[tuple[SuperGameKindDefinition, ...]] = (
    NO_SUPER_GAME_KIND,
    WILD_SUPER_SPINS,
)

_BY_CODE: Final = {kind.code: kind for kind in SUPER_GAME_KINDS}


def list_super_game_kinds() -> tuple[SuperGameKindDefinition, ...]:
    return SUPER_GAME_KINDS


def is_known_super_game_kind(code: str) -> bool:
    return code in _BY_CODE


def get_super_game_kind(code: str) -> SuperGameKindDefinition:
    """Return the registered kind or raise ``KeyError`` for an unknown code."""

    return _BY_CODE[code]
