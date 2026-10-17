"""Frozen v11: game creation receipts and family fork lineage; no new partitions."""

from game_predictor_api.storage.game_data_v2_manifest_v10 import CATALOG as _CATALOG
from game_predictor_api.storage.game_data_v2_manifest_v10 import (
    CONTROL_TABLES,
    CREATE_TABLES,
    DELETE_TABLES,
    DUAL_SCOPE,
    GAME_TABLES,
    MIGRATE_TABLES,
    PARTITIONED_TABLES,
    POST_V5_SHARED,
    SCHEMA,
)
from game_predictor_api.storage.game_data_v2_manifest_v10 import SHARED as _SHARED

VERSION = "game-data-v2-manifest-v11"
ADDED_CATALOG = frozenset({"game_create_receipts"})
ADDED_SHARED = frozenset({"grid_model_family_forks"})
CATALOG = _CATALOG | ADDED_CATALOG
SHARED = _SHARED | ADDED_SHARED


def ownership(table: str) -> str:
    if table in CATALOG:
        return "catalog"
    if table in GAME_TABLES:
        return "game"
    if table in SHARED or table in CONTROL_TABLES or table in POST_V5_SHARED:
        return "shared"
    raise ValueError(f"GAME_STORAGE_UNKNOWN_TABLE: {table}")


__all__ = [
    "CATALOG",
    "CONTROL_TABLES",
    "CREATE_TABLES",
    "DELETE_TABLES",
    "DUAL_SCOPE",
    "GAME_TABLES",
    "MIGRATE_TABLES",
    "PARTITIONED_TABLES",
    "POST_V5_SHARED",
    "SCHEMA",
    "SHARED",
    "VERSION",
    "ADDED_CATALOG",
    "ADDED_SHARED",
    "ownership",
]
