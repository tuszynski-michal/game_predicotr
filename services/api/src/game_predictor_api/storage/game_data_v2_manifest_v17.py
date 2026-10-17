"""Frozen v17: shared cohort notice watermarks and evaluation cohort proofs (TASK-0997)."""

from game_predictor_api.storage.game_data_v2_manifest_v16 import (
    ADDED_GAME_TABLES,
    CATALOG,
    CONTROL_TABLES,
    CREATE_TABLES,
    DELETE_TABLES,
    DUAL_SCOPE,
    GAME_TABLES,
    MIGRATE_TABLES,
    PARTITIONED_TABLES,
    POST_V5_SHARED,
    RECORDING_TABLES,
    SCHEMA,
)
from game_predictor_api.storage.game_data_v2_manifest_v16 import SHARED as _SHARED
from game_predictor_api.storage.game_data_v2_manifest_v16 import VERSION as PREVIOUS_VERSION

VERSION = "game-data-v2-manifest-v17"
# Shared rows carry game and cohort identities only, never game payload.
ADDED_SHARED = frozenset({"grid_model_cohort_notice_marks", "grid_model_evaluation_cohort_proofs"})
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
    "ADDED_GAME_TABLES",
    "ADDED_SHARED",
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
