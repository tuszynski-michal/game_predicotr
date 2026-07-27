"""Framework-independent contracts for payout batch orchestration."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from game_predictor_api.domain.datasets import DatasetVersionStatus
from game_predictor_api.domain.rules import RulesVersionStatus

from game_predictor_worker.domain.contracts import (
    GameConfig,
    PaylineDefinition,
    PayoutEvaluation,
    PayoutRuleDefinition,
    PayoutSymbolDefinition,
)


@dataclass(frozen=True, slots=True)
class PayoutSource:
    dataset_version_id: UUID
    rules_version_id: UUID
    game_id: UUID
    rules_game_id: UUID
    dataset_status: DatasetVersionStatus
    rules_status: RulesVersionStatus
    dataset_rows: int
    dataset_columns: int
    layout_count: int
    game: GameConfig
    paylines: tuple[PaylineDefinition, ...]
    payout_symbols: tuple[PayoutSymbolDefinition, ...]
    payout_rules: tuple[PayoutRuleDefinition, ...]


@dataclass(frozen=True, slots=True)
class PayoutLayout:
    sequence_number: int
    cells: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class CalculatedLayoutPayout:
    dataset_version_id: UUID
    rules_version_id: UUID
    sequence_number: int
    algorithm_version: str
    total_payout: int
    audit_path: str
    calculated_at: datetime


@dataclass(frozen=True, slots=True)
class AuditedPayout:
    layout: PayoutLayout
    evaluation: PayoutEvaluation


class PayoutStore(Protocol):
    def load_source(
        self,
        dataset_version_id: UUID,
        rules_version_id: UUID,
    ) -> PayoutSource | None: ...

    def list_layout_batch(
        self,
        dataset_version_id: UUID,
        *,
        after_sequence_number: int,
        limit: int,
    ) -> Sequence[PayoutLayout]: ...

    def upsert_payouts(
        self,
        payouts: Sequence[CalculatedLayoutPayout],
    ) -> None: ...


class PayoutAuditWriter(Protocol):
    def write_batch(
        self,
        source: PayoutSource,
        *,
        algorithm_version: str,
        payouts: Sequence[AuditedPayout],
    ) -> str: ...
