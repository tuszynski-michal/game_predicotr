"""Frozen v6 ownership: add the super game series tables (TASK-0933, D-535)."""

from game_predictor_api.storage.game_data_v2_manifest_v5 import (
    CATALOG,
    CONTROL_TABLES,
    DUAL_SCOPE,
    POST_V5_SHARED,
    SCHEMA,
    SHARED,
)
from game_predictor_api.storage.game_data_v2_manifest_v5 import GAME_TABLES as _V5_GAME_TABLES
from game_predictor_api.storage.game_data_v2_manifest_v5 import VERSION as PREVIOUS_VERSION

VERSION = "game-data-v2-manifest-v6"
# All four tables hold data of exactly one game (series, their audit, the
# derivation input counter and the working rows of an unpublished generation),
# so they live in the game's partitioned store under RLS and are dropped with
# the game by the partition lifecycle.
ADDED_GAME_TABLES = (
    "super_game_derivation_state",
    "super_game_series",
    "super_game_series_audit_events",
    "super_game_series_generation_rows",
)
GAME_TABLES = tuple(sorted((*_V5_GAME_TABLES, *ADDED_GAME_TABLES)))
PARTITIONED_TABLES = CREATE_TABLES = MIGRATE_TABLES = DELETE_TABLES = GAME_TABLES


def ownership(table: str) -> str:
    if table in CATALOG:
        return "catalog"
    if table in GAME_TABLES:
        return "game"
    if table in SHARED or table in CONTROL_TABLES or table in POST_V5_SHARED:
        return "shared"
    raise ValueError(f"GAME_STORAGE_UNKNOWN_TABLE: {table}")


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
    "PREVIOUS_VERSION",
    "SCHEMA",
    "SHARED",
    "VERSION",
    "ownership",
]
