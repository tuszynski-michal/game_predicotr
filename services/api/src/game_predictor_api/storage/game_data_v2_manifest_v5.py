"""Frozen v5 ownership: add the opt-in geometry comparison history."""

from game_predictor_api.storage.game_data_v2_manifest_v4 import (
    CATALOG,
    CONTROL_TABLES,
    DUAL_SCOPE,
    SCHEMA,
    SHARED,
)
from game_predictor_api.storage.game_data_v2_manifest_v4 import GAME_TABLES as _V4_GAME_TABLES
from game_predictor_api.storage.game_data_v2_manifest_v4 import VERSION as PREVIOUS_VERSION

VERSION = "game-data-v2-manifest-v5"
ADDED_GAME_TABLES = ("image_geometry_shadow_results",)
GAME_TABLES = tuple(sorted((*_V4_GAME_TABLES, *ADDED_GAME_TABLES)))
PARTITIONED_TABLES = CREATE_TABLES = MIGRATE_TABLES = DELETE_TABLES = GAME_TABLES


def ownership(table: str) -> str:
    if table in CATALOG:
        return "catalog"
    if table in GAME_TABLES:
        return "game"
    if table in SHARED or table in CONTROL_TABLES:
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
    "PREVIOUS_VERSION",
    "SCHEMA",
    "SHARED",
    "VERSION",
    "ownership",
]
