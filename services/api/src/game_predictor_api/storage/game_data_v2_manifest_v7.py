"""Frozen v7 ownership: the geometry correction revert audit (TASK-0966) and the
durable events of deferred-slot rejections (TASK-0970)."""

from game_predictor_api.storage.game_data_v2_manifest_v6 import (
    CATALOG,
    CONTROL_TABLES,
    DUAL_SCOPE,
    POST_V5_SHARED,
    SCHEMA,
    SHARED,
)
from game_predictor_api.storage.game_data_v2_manifest_v6 import GAME_TABLES as _V6_GAME_TABLES
from game_predictor_api.storage.game_data_v2_manifest_v6 import VERSION as PREVIOUS_VERSION

VERSION = "game-data-v2-manifest-v7"
# The audit of reverted grid-geometry corrections holds a snapshot of one
# game's deleted rows, so it lives in the game's partitioned store under RLS
# and is dropped with the game by the partition lifecycle.
# The slot events keep the idempotency identity of a rejection and its revert.
ADDED_GAME_TABLES = ("image_board_geometry_pending_events", "image_geometry_correction_reverts")
GAME_TABLES = tuple(sorted((*_V6_GAME_TABLES, *ADDED_GAME_TABLES)))
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
