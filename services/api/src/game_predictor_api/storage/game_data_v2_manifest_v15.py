"""Frozen v15: retained descriptive quality measurements and canonical approval receipts."""

from game_predictor_api.storage.game_data_v2_manifest_v14 import (
    CATALOG,
    CONTROL_TABLES,
    DUAL_SCOPE,
    POST_V5_SHARED,
    RECORDING_TABLES,
    SCHEMA,
    SHARED,
)
from game_predictor_api.storage.game_data_v2_manifest_v14 import GAME_TABLES as _PREVIOUS
from game_predictor_api.storage.game_data_v2_manifest_v14 import VERSION as PREVIOUS_VERSION

VERSION = "game-data-v2-manifest-v15"
ADDED_GAME_TABLES = (
    "grid_quality_measurements",
    "grid_quality_measurement_members",
    "grid_quality_measurement_judgments",
    "grid_quality_measurement_commands",
    "grid_geometry_approval_commands",
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
