"""Code-defined super game kinds (D-535).

A super game kind is chosen per game (``games.super_game_kind``); its mechanics
live in code, one module per kind, registered in :mod:`.registry`. Adding a
kind means a new module, one registry entry and nothing else: the Admin API
exposes the registry, so the Admin UI never keeps its own copy of the list.
"""

from game_predictor_worker.domain.super_games.definition import (
    SeriesBoardEvaluation,
    SeriesBoardEvaluator,
    SeriesExpansion,
    SeriesPayoutKind,
    SuperGameKindDefinition,
)
from game_predictor_worker.domain.super_games.registry import (
    NO_SUPER_GAME_KIND,
    SUPER_GAME_KINDS,
    get_super_game_kind,
    is_known_super_game_kind,
    list_super_game_kinds,
)
from game_predictor_worker.domain.super_games.wild_super_spins import (
    WILD_SUPER_SPINS,
    WILD_SUPER_SPINS_CODE,
    evaluate_series_board,
)

__all__ = [
    "NO_SUPER_GAME_KIND",
    "SUPER_GAME_KINDS",
    "WILD_SUPER_SPINS",
    "WILD_SUPER_SPINS_CODE",
    "SeriesBoardEvaluation",
    "SeriesBoardEvaluator",
    "SeriesExpansion",
    "SeriesPayoutKind",
    "SuperGameKindDefinition",
    "evaluate_series_board",
    "get_super_game_kind",
    "is_known_super_game_kind",
    "list_super_game_kinds",
]
