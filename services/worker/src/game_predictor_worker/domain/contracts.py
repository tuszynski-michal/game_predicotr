"""Immutable contracts shared by build-time domain algorithms."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SymbolDefinition:
    mobile_code: int
    code: str
    name: str
    is_wildcard: bool
    display_order: int


@dataclass(frozen=True)
class GameConfig:
    id: str
    code: str
    name: str
    rows: int
    columns: int
    spin_cost: int
    signature_cell_width: int
    symbols: tuple[SymbolDefinition, ...]


@dataclass(frozen=True)
class PaylineDefinition:
    id: str
    row_path: tuple[int, ...]


@dataclass(frozen=True)
class PayoutRuleDefinition:
    symbol_mobile_code: int
    match_length: int
    payout_credits: int


@dataclass(frozen=True)
class JokerInterpretation:
    cell_index: int
    as_symbol_mobile_code: int


@dataclass(frozen=True)
class PayoutMatch:
    symbol_mobile_code: int
    payline_id: str
    start_column: int
    matched_length: int
    matched_cells: tuple[int, ...]
    joker_cells: tuple[int, ...]
    payout_credits: int
    interpretation: tuple[JokerInterpretation, ...]


@dataclass(frozen=True)
class PayoutEvaluation:
    total_payout: int
    matches: tuple[PayoutMatch, ...]


@dataclass(frozen=True)
class SequencePayout:
    sequence_number: int
    payout_credits: int


@dataclass(frozen=True)
class ForecastInput:
    mobile_release_version: str
    snapshot_checksum: str
    dataset_version: int
    rules_version: int
    algorithm_version: str
    start_sequence_number: int
    layout_count: int
    spin_cost: int
    sequence_payouts: tuple[SequencePayout, ...]


@dataclass(frozen=True)
class ForecastPeak:
    spin_number: int
    sequence_number: int
    spin_payout: int
    cumulative_payout: int
    cumulative_cost: int
    net_credits: int


@dataclass(frozen=True)
class ForecastResult:
    mobile_release_version: str
    snapshot_checksum: str
    dataset_version: int
    rules_version: int
    algorithm_version: str
    start_sequence_number: int
    evaluated_spin_count: int
    spin_cost: int
    final_cumulative_payout: int
    final_cumulative_cost: int
    final_net_credits: int
    positive_local_peaks: tuple[ForecastPeak, ...]
