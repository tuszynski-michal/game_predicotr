"""Typed boundaries for production mobile snapshot generation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol
from uuid import UUID

from game_predictor_worker.payouts.readiness import PayoutCompletenessRepository


@dataclass(frozen=True, slots=True)
class SnapshotGameSelection:
    dataset_version_id: UUID
    rules_version_id: UUID
    algorithm_version: str


@dataclass(frozen=True, slots=True)
class ProductionSnapshotSpec:
    release_version: str
    created_at: datetime
    games: tuple[SnapshotGameSelection, ...]


@dataclass(frozen=True, slots=True)
class SnapshotSymbol:
    mobile_code: int
    code: str
    name: str
    is_wildcard: bool
    display_order: int
    image_asset_key: str | None


@dataclass(frozen=True, slots=True)
class SnapshotGameSource:
    game_id: UUID
    game_code: str
    game_name: str
    dataset_version_id: UUID
    dataset_version: int
    rules_version_id: UUID
    rules_version: int
    algorithm_version: str
    rows: int
    columns: int
    spin_cost: int
    signature_cell_width: int
    layout_count: int
    symbols: tuple[SnapshotSymbol, ...]


@dataclass(frozen=True, slots=True)
class SnapshotLayout:
    sequence_number: int
    signature: str
    payout: int


@dataclass(frozen=True, slots=True)
class ProductionSnapshotGameResult:
    mobile_game_id: int
    game_id: UUID
    game_code: str
    dataset_version_id: UUID
    dataset_version: int
    rules_version_id: UUID
    rules_version: int
    rows: int
    columns: int
    signature_cell_width: int
    symbol_count: int
    layout_count: int


@dataclass(frozen=True, slots=True)
class ProductionSnapshotResult:
    database_path: Path
    release_version: str
    created_at: str
    schema_version: int
    algorithm_version: str
    game_count: int
    symbol_count: int
    layout_count: int
    logical_content_sha256: str
    snapshot_file_sha256: str
    games: tuple[ProductionSnapshotGameResult, ...]


class ProductionSnapshotRepository(PayoutCompletenessRepository, Protocol):
    def load_snapshot_game(
        self,
        selection: SnapshotGameSelection,
    ) -> SnapshotGameSource | None: ...

    def list_snapshot_layout_batch(
        self,
        selection: SnapshotGameSelection,
        *,
        after_sequence_number: int,
        limit: int,
    ) -> Sequence[SnapshotLayout]: ...
