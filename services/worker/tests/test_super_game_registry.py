"""TASK-0931: the code registry of super game kinds (D-535)."""

from __future__ import annotations

import pytest
from game_predictor_worker.domain.super_games import (
    NO_SUPER_GAME_KIND,
    WILD_SUPER_SPINS,
    get_super_game_kind,
    is_known_super_game_kind,
    list_super_game_kinds,
)


def test_super_game_registry_lists_none_first_and_wild_super_spins() -> None:
    assert [(kind.code, kind.label) for kind in list_super_game_kinds()] == [
        ("none", "Brak"),
        ("wild_super_spins", "Wild super spins"),
    ]
    assert NO_SUPER_GAME_KIND.has_super_game is False


def test_wild_super_spins_constants_match_the_accepted_plan() -> None:
    kind = get_super_game_kind("wild_super_spins")

    assert kind is WILD_SUPER_SPINS
    assert (kind.series_length, kind.retrigger_extension, kind.free_spin_cost) == (10, 10, 0)
    assert kind.has_super_game is True


def test_super_game_registry_rejects_unknown_codes() -> None:
    assert is_known_super_game_kind("none") is True
    assert is_known_super_game_kind("Wild super spins") is False
    with pytest.raises(KeyError):
        get_super_game_kind("free_spins")


def test_catalog_none_code_matches_the_registry() -> None:
    from game_predictor_api.domain.catalog import NO_SUPER_GAME

    assert NO_SUPER_GAME_KIND.code == NO_SUPER_GAME
