"""Frozen ownership policy for Alembic 0131 and later lifecycle consumers.

Version 3 adds exactly one game-owned partitioned table,
``board_render_manifests`` (D-467, TASK-0757), to the frozen v1 game set and
keeps the v2 classification of later public tables.  Do not edit this version
to add tables: add a migration and a new manifest version, as for v1.
"""

from __future__ import annotations

from game_predictor_api.storage.game_data_v2_manifest_v1 import (
    CATALOG,
    CONTROL_TABLES,
)
from game_predictor_api.storage.game_data_v2_manifest_v1 import DUAL_SCOPE as _DUAL_SCOPE
from game_predictor_api.storage.game_data_v2_manifest_v1 import GAME_TABLES as _V1_GAME_TABLES
from game_predictor_api.storage.game_data_v2_manifest_v1 import SCHEMA as _SCHEMA
from game_predictor_api.storage.game_data_v2_manifest_v1 import VERSION as V1_VERSION
from game_predictor_api.storage.game_data_v2_manifest_v2 import SHARED as _V2_SHARED

VERSION = "game-data-v2-manifest-v3"
PREVIOUS_VERSION = V1_VERSION
SCHEMA = _SCHEMA

ADDED_GAME_TABLES = ("board_render_manifests",)

SHARED = _V2_SHARED | frozenset(
    {
        "board_search_share_sessions",
        "board_search_share_audit_events",
        "board_search_share_query_events",
    }
)
GAME_TABLES = tuple(sorted({*_V1_GAME_TABLES, *ADDED_GAME_TABLES}))

PARTITIONED_TABLES = GAME_TABLES
CREATE_TABLES = GAME_TABLES
MIGRATE_TABLES = GAME_TABLES
DELETE_TABLES = GAME_TABLES
DUAL_SCOPE = _DUAL_SCOPE

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


def ownership(table: str) -> str:
    if table in CATALOG:
        return "catalog"
    if table in GAME_TABLES:
        return "game"
    if table in SHARED or table in CONTROL_TABLES:
        return "shared"
    raise ValueError(f"GAME_STORAGE_UNKNOWN_TABLE: {table}")
