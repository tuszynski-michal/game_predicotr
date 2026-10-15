"""Frozen v9: public geometry catalogue; identical game partitions to v8."""

from game_predictor_api.storage.game_data_v2_manifest_v8 import (
    CATALOG as _CATALOG,
)
from game_predictor_api.storage.game_data_v2_manifest_v8 import (
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
from game_predictor_api.storage.game_data_v2_manifest_v8 import (
    SHARED as _SHARED,
)

VERSION = "game-data-v2-manifest-v9"
ADDED_CATALOG = frozenset({"game_grid_model_assignments", "game_grid_model_assignment_events"})
ADDED_SHARED = frozenset(
    {
        "grid_model_families",
        "grid_model_versions",
        "grid_model_registration_receipts",
        "grid_model_version_events",
    }
)
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
