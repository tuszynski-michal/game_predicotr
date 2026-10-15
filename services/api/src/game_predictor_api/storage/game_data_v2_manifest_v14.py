"""Frozen v14: shared, retained geometry-recording identities and evidence."""

from game_predictor_api.storage.game_data_v2_manifest_v13 import (
    CATALOG,
    CREATE_TABLES,
    DELETE_TABLES,
    DUAL_SCOPE,
    GAME_TABLES,
    MIGRATE_TABLES,
    PARTITIONED_TABLES,
    POST_V5_SHARED,
    SCHEMA,
    SHARED,
)
from game_predictor_api.storage.game_data_v2_manifest_v13 import CONTROL_TABLES as _CONTROL
from game_predictor_api.storage.game_data_v2_manifest_v13 import VERSION as PREVIOUS_VERSION

VERSION = "game-data-v2-manifest-v14"
RECORDING_TABLES = (
    "recording_groups",
    "recording_occurrences",
    "recording_evidence",
    "recording_role_heads",
    "recording_commands",
)
CONTROL_TABLES = frozenset((*_CONTROL, *RECORDING_TABLES))


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
    "PREVIOUS_VERSION",
    "RECORDING_TABLES",
    "SCHEMA",
    "SHARED",
    "VERSION",
    "ownership",
]
