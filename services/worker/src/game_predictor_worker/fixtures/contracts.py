"""Immutable contracts for deterministic build-time fixtures."""

from __future__ import annotations

from dataclasses import dataclass

from game_predictor_worker.domain import (
    ForecastPeak,
    GameConfig,
    PaylineDefinition,
    PayoutRuleDefinition,
    PayoutSymbolDefinition,
)


@dataclass(frozen=True)
class GeneratedLayout:
    sequence_number: int
    cells: tuple[int, ...]
    signature: str
    payout_credits: int


@dataclass(frozen=True)
class DuplicateFixture:
    signature: str
    sequence_numbers: tuple[int, int]


@dataclass(frozen=True)
class UniquePrefixFixture:
    sequence_number: int
    cell_count: int
    signature_prefix: str


@dataclass(frozen=True)
class TargetGoldenFixture:
    code: str
    start_sequence_number: int
    expected_final_cumulative_payout: int
    expected_final_cumulative_cost: int
    expected_final_net_credits: int
    expected_positive_local_peaks: tuple[ForecastPeak, ...]


@dataclass(frozen=True)
class GeneratedGameFixture:
    seed: int
    game: GameConfig
    paylines: tuple[PaylineDefinition, ...]
    payout_symbols: tuple[PayoutSymbolDefinition, ...]
    payout_rules: tuple[PayoutRuleDefinition, ...]
    layouts: tuple[GeneratedLayout, ...]
    duplicate_fixtures: tuple[DuplicateFixture, ...]
    unique_prefix_fixture: UniquePrefixFixture
    target_golden_fixtures: tuple[TargetGoldenFixture, ...]


@dataclass(frozen=True)
class M1Fixture:
    fixture_version: str
    dataset_version: int
    rules_version: int
    algorithm_version: str
    games: tuple[GeneratedGameFixture, ...]


@dataclass(frozen=True)
class GameFixtureValidation:
    game_code: str
    layout_count: int
    duplicate_group_count: int
    unique_prefix_cell_count: int


@dataclass(frozen=True)
class FixtureValidationReport:
    fixture_fingerprint: str
    game_count: int
    layout_count: int
    games: tuple[GameFixtureValidation, ...]
