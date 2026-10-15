"""Frozen v12: reinference history with a detachable live-source reference.

Frozen source identities and target receipts survive confirmed source cleanup;
only the nullable live source link references the existing source partition.
"""

from game_predictor_api.storage.game_data_v2_manifest_v11 import (
    CATALOG,
    CONTROL_TABLES,
    DUAL_SCOPE,
    POST_V5_SHARED,
    SCHEMA,
    SHARED,
)
from game_predictor_api.storage.game_data_v2_manifest_v11 import GAME_TABLES as _V11_GAME_TABLES
from game_predictor_api.storage.game_data_v2_manifest_v11 import VERSION as PREVIOUS_VERSION

VERSION = "game-data-v2-manifest-v12"
ADDED_GAME_TABLES = (
    "grid_reinference_operations",
    "grid_reinference_sources",
    "grid_reinference_targets",
)
GAME_TABLES = tuple(sorted((*_V11_GAME_TABLES, *ADDED_GAME_TABLES)))
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
