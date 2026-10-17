"""Bounded restricted-session references and publication/GC transaction guards."""

from __future__ import annotations

import hashlib
import time
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import Result, text
from sqlalchemy.orm import Session

from game_predictor_api.domain.grid_training_cohorts import GridCohortError
from game_predictor_api.domain.storage_retention import (
    CohortAssetReferenceState,
    cohort_asset_path_identity,
)
from game_predictor_api.storage.game_data_v2_manifest_v18 import (
    ADDED_GAME_TABLES,
    GAME_TABLES,
    VERSION,
)
from game_predictor_api.storage.game_partition_lifecycle import partition_name
from game_predictor_api.storage.game_storage_routing import GameStorageIntent, GameStorageRouter

ASSET_GUARD_NAMESPACE = 0x47504348


class AssetDeadline(Protocol):
    def check(self, session: Session | None = None) -> None: ...


class CohortAssetDeadline:
    def __init__(self) -> None:
        self.end = time.monotonic() + 60

    def check(self, session: Session | None = None) -> None:
        remaining = self.end - time.monotonic()
        if remaining <= 0:
            raise GridCohortError(
                "GRID_COHORT_ASSET_TIMEOUT", "Asset operation budget expired.", 503
            )
        if session is not None:
            session.execute(
                text("SELECT pg_catalog.set_config('statement_timeout', :timeout, true)"),
                {"timeout": str(max(1, min(30_000, int(remaining * 1000))))},
            )


def cohort_asset_guard_key(game: UUID, cohort: UUID) -> tuple[int, int]:
    value = f"grid-cohort-assets-v1:{str(game).lower()}:{str(cohort).lower()}".encode("ascii")
    return ASSET_GUARD_NAMESPACE, int.from_bytes(
        hashlib.sha256(value).digest()[:4], "big", signed=True
    )


def acquire_cohort_asset_guard(
    session: Session,
    game: UUID,
    cohort: UUID,
    exclusive: bool = False,
    deadline: AssetDeadline | None = None,
) -> None:
    if session.get_bind().dialect.name != "postgresql":
        raise GridCohortError(
            "GRID_COHORT_ASSET_UNRESOLVED", "A PostgreSQL runtime guard is required.", 503
        )
    if deadline is None:
        deadline = session.info.setdefault("grid_cohort_asset_deadline", CohortAssetDeadline())
    deadline.check(session)
    session.execute(text("SELECT pg_catalog.set_config('lock_timeout', '5s', true)"))
    namespace, key = cohort_asset_guard_key(game, cohort)
    function = "pg_advisory_xact_lock" if exclusive else "pg_advisory_xact_lock_shared"
    session.execute(
        text(f"SELECT pg_catalog.{function}(CAST(:namespace AS integer), CAST(:key AS integer))"),
        {"namespace": namespace, "key": key},
    )
    deadline.check(session)


def parse_cohort_asset_path(relative: str) -> tuple[UUID, UUID] | None:
    return cohort_asset_path_identity(relative)


def _unresolved() -> CohortAssetReferenceState:
    return CohortAssetReferenceState(False, None, True)


def _execute(session: Session, statement: str, parameters: dict[str, object]) -> Result[Any]:
    deadline = session.info.get("grid_cohort_asset_deadline")
    if deadline is not None:
        deadline.check(session)
    return session.execute(text(statement), parameters)


def _deleted_game_reference(session: Session, game: UUID) -> CohortAssetReferenceState:
    # Missing routing alone is never permission. Read a real completed receipt
    # and verify absence of catalog, routing and all six exact own partitions.
    if _execute(
        session, "SELECT EXISTS(SELECT 1 FROM public.games WHERE id=:game)", {"game": game}
    ).scalar_one():
        return _unresolved()
    row = (
        _execute(
            session,
            """SELECT operation_kind,status,manifest_version,next_table_index,
        completed_tables,updated_at FROM public.game_storage_lifecycle_operations
        WHERE game_id=:game ORDER BY created_at DESC,id DESC LIMIT 1""",
            {"game": game},
        )
        .mappings()
        .one_or_none()
    )
    if (
        row is None
        or row["operation_kind"] != "delete"
        or row["status"] != "done"
        or row["manifest_version"] != VERSION
        or row["next_table_index"] != len(GAME_TABLES)
        or not isinstance(row["completed_tables"], list)
        or set(row["completed_tables"]) != set(GAME_TABLES)
        or len(row["completed_tables"]) != len(GAME_TABLES)
        or not isinstance(row["updated_at"], datetime)
        or row["updated_at"].tzinfo is None
    ):
        return _unresolved()
    for table in ADDED_GAME_TABLES:
        present = _execute(
            session,
            "SELECT pg_catalog.to_regclass(:name)",
            {"name": f"game_data_v2.{partition_name(game, table)}"},
        ).scalar_one()
        if present is not None:
            return _unresolved()
    # Repeat routing absence after receipt/partition proof in this transaction.
    if _execute(
        session,
        "SELECT EXISTS(SELECT 1 FROM public.game_storage_locations WHERE game_id=:game)",
        {"game": game},
    ).scalar_one():
        return _unresolved()
    return CohortAssetReferenceState(False, row["updated_at"])


def read_cohort_asset_reference(
    session: Session, game: UUID, cohort: UUID, relative: str
) -> CohortAssetReferenceState:
    if parse_cohort_asset_path(relative) != (game, cohort):
        return _unresolved()
    route = _execute(
        session,
        "SELECT status FROM public.game_storage_locations WHERE game_id=:game",
        {"game": game},
    ).scalar_one_or_none()
    if route is None:
        return _deleted_game_reference(session, game)
    if route != "active":
        return _unresolved()
    # Hold the existing game deletion/write fence after the asset guard. No
    # owner/source locks are taken, and only this game's RLS data is read.
    GameStorageRouter().bind(session, game, intent=GameStorageIntent.WRITE)
    row = (
        _execute(
            session,
            """SELECT c.manifest_path,c.created_at,
        (SELECT max(e.created_at) FROM game_data_v2.grid_training_cohort_events e
          WHERE e.game_id=:game AND e.cohort_id=:cohort) AS last_event,
        EXISTS(SELECT 1 FROM game_data_v2.grid_training_cohort_pages p
          WHERE p.game_id=:game AND p.cohort_id=:cohort
            AND (jsonb_typeof(p.document->'assets') IS DISTINCT FROM 'array'
              OR jsonb_array_length(p.document->'assets')>9
              OR EXISTS(SELECT 1 FROM jsonb_array_elements(
                CASE WHEN jsonb_typeof(p.document->'assets')='array'
                THEN p.document->'assets' ELSE '[]'::jsonb END) a
                WHERE jsonb_typeof(a) IS DISTINCT FROM 'object'
                  OR jsonb_typeof(a->'path') IS DISTINCT FROM 'string'
                  OR jsonb_typeof(a->'sha256') IS DISTINCT FROM 'string'
                  OR jsonb_typeof(a->'bytes') IS DISTINCT FROM 'number'))) AS invalid_assets,
        EXISTS(SELECT 1 FROM game_data_v2.grid_training_cohort_pages p
          WHERE p.game_id=:game AND p.cohort_id=:cohort
            AND (p.path=:path OR p.document->'assets' @>
              jsonb_build_array(jsonb_build_object('path',CAST(:path AS text))))) AS page_ref
        FROM game_data_v2.grid_training_cohorts c
        WHERE c.game_id=:game AND c.id=:cohort""",
            {"game": game, "cohort": cohort, "path": relative},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return CohortAssetReferenceState(False, None)
    anchor = row["last_event"] or row["created_at"]
    if row["invalid_assets"] or not isinstance(anchor, datetime) or anchor.tzinfo is None:
        return _unresolved()
    return CohortAssetReferenceState(
        bool(row["page_ref"] or row["manifest_path"] == relative), anchor
    )
