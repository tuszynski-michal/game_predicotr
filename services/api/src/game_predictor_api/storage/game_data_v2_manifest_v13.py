"""Frozen v13: retained geometry proposals and command outcomes.

Candidates and decision receipts reference retained target evidence. Source
cleanup detaches only v12 live links; whole-game lifecycle removes both tables.
"""

from game_predictor_api.storage.game_data_v2_manifest_v12 import (
    CATALOG,
    CONTROL_TABLES,
    DUAL_SCOPE,
    POST_V5_SHARED,
    SCHEMA,
    SHARED,
)
from game_predictor_api.storage.game_data_v2_manifest_v12 import GAME_TABLES as _V12_GAME_TABLES
from game_predictor_api.storage.game_data_v2_manifest_v12 import VERSION as PREVIOUS_VERSION

VERSION = "game-data-v2-manifest-v13"
ADDED_GAME_TABLES = (
    "grid_geometry_proposals",
    "grid_geometry_proposal_events",
)
GAME_TABLES = tuple(sorted((*_V12_GAME_TABLES, *ADDED_GAME_TABLES)))
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
