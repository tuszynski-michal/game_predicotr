"""Frozen v21: exact replacement plans and retained decision chronology (TASK-1127)."""

from game_predictor_api.storage.game_data_v2_manifest_v20 import (
    CATALOG,
    CONTROL_TABLES,
    DUAL_SCOPE,
    POST_V5_SHARED,
    RECORDING_TABLES,
    SCHEMA,
    SHARED,
)
from game_predictor_api.storage.game_data_v2_manifest_v20 import GAME_TABLES as _PREVIOUS
from game_predictor_api.storage.game_data_v2_manifest_v20 import VERSION as PREVIOUS_VERSION

__all__ = [
    "ADDED_GAME_TABLES",
    "CATALOG",
    "CONTROL_TABLES",
    "CREATE_TABLES",
    "DELETE_TABLES",
    "DUAL_SCOPE",
    "GAME_TABLES",
    "MIGRATE_TABLES",
    "PARTITIONED_TABLES",
    "POST_V5_SHARED",
    "RECORDING_TABLES",
    "PREVIOUS_VERSION",
    "SCHEMA",
    "SHARED",
    "VERSION",
    "ownership",
]

VERSION = "game-data-v2-manifest-v21"
ADDED_GAME_TABLES = (
    "source_replacement_batches",
    "source_replacement_entries",
    "source_replacement_slots",
    "source_replacement_retired",
    "source_replacement_commands",
    "symbol_readability_decisions",
    "source_replacement_sources",
)

GAME_TABLES = tuple(sorted((*_PREVIOUS, *ADDED_GAME_TABLES)))
PARTITIONED_TABLES = CREATE_TABLES = MIGRATE_TABLES = DELETE_TABLES = GAME_TABLES


def ownership(table: str) -> str:
    if table in CATALOG:
        return "catalog"
    if table in GAME_TABLES:
        return "game"
    if table in SHARED or table in CONTROL_TABLES or table in POST_V5_SHARED:
        return "shared"
    raise ValueError(f"GAME_STORAGE_UNKNOWN_TABLE: {table}")
