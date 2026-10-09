"""Preview or execute the permanent deletion of one archived V2 game.

The command is read-only unless ``--execute`` is given.  Execution drives the
existing resumable partition lifecycle (``GamePartitionLifecycleKind.DELETE``):
it drops the game's ``game_data_v2`` partitions one table per transaction and
then removes the catalog rows (symbols, rules, jobs, storage location, game).
It never touches files on disk; the preview lists the paths the game referenced.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from game_predictor_api.config import ApiSettings
from game_predictor_api.storage.database import create_owner_session_factory
from game_predictor_api.storage.game_data_v2_manifest_v6 import DELETE_TABLES, SCHEMA, VERSION
from game_predictor_api.storage.game_partition_lifecycle import (
    GamePartitionLifecycleError,
    GamePartitionLifecycleKind,
    GamePartitionLifecycleRepository,
    partition_name,
)
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

POLICY = "archived-v2-game-deletion-v1"
ACTIVE_JOB_STATUSES = ("created", "processing")
# Public tables the lifecycle finalization clears itself, in its own order.
LIFECYCLE_CLEARED = frozenset(
    {
        "game_storage_locations",
        "games",
        "jobs",
        "paylines",
        "payout_rules",
        "rules_version_symbols",
        "rules_versions",
        "symbols",
    }
)
_OWNER_PARENTS = ("games", "jobs", "symbols", "rules_versions")


class DeletionBlocked(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def confirmation_phrase(code: str, game_id: UUID) -> str:
    return f"DELETE GAME {code} {game_id}"


def preview_digest(preview: Mapping[str, object]) -> str:
    payload = {key: value for key, value in preview.items() if key != "previewSha256"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def collect_blockers(
    *,
    game_status: str,
    location: Mapping[str, object] | None,
    active_job_count: int,
    mobile_release_rows: int,
    uncovered_references: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    blockers: list[dict[str, object]] = []
    if game_status != "archived":
        blockers.append({"code": "GAME_NOT_ARCHIVED", "status": game_status})
    if (
        location is None
        or location["storeSchema"] != SCHEMA
        or location["manifestVersion"] != VERSION
        or location["status"] not in ("active", "deleting")
    ):
        blockers.append({"code": "GAME_STORAGE_LOCATION_INVALID", "location": location})
    if active_job_count:
        blockers.append({"code": "GAME_HAS_ACTIVE_JOBS", "count": active_job_count})
    if mobile_release_rows:
        blockers.append({"code": "GAME_IN_MOBILE_RELEASE", "count": mobile_release_rows})
    for reference in uncovered_references:
        blockers.append({"code": "GAME_HAS_UNCOVERED_REFERENCES", **reference})
    return blockers


def build_preview(session: Session, game_id: UUID) -> dict[str, object]:
    game = (
        session.execute(
            text("SELECT id, code, name, status FROM public.games WHERE id = :game_id"),
            {"game_id": game_id},
        )
        .mappings()
        .one_or_none()
    )
    if game is None:
        raise DeletionBlocked("GAME_NOT_FOUND", f"Game {game_id} does not exist.")
    location_row = (
        session.execute(
            text(
                """SELECT store_schema, generation, manifest_version, status
                FROM public.game_storage_locations WHERE game_id = :game_id"""
            ),
            {"game_id": game_id},
        )
        .mappings()
        .one_or_none()
    )
    location = (
        None
        if location_row is None
        else {
            "storeSchema": str(location_row["store_schema"]),
            "generation": int(location_row["generation"]),
            "manifestVersion": str(location_row["manifest_version"]),
            "status": str(location_row["status"]),
        }
    )
    jobs = {
        str(status): int(count)
        for status, count in session.execute(
            text(
                """SELECT status, count(*) FROM public.jobs
                WHERE game_id = :game_id GROUP BY status ORDER BY status"""
            ),
            {"game_id": game_id},
        )
    }
    partitions = _partition_row_counts(session, game_id)
    preview: dict[str, object] = {
        "policy": POLICY,
        "manifestVersion": VERSION,
        "game": {
            "id": str(game["id"]),
            "code": str(game["code"]),
            "name": str(game["name"]),
            "status": str(game["status"]),
        },
        "location": location,
        "catalog": {
            "symbols": _count(session, "symbols", game_id),
            "rulesVersions": _count(session, "rules_versions", game_id),
            "jobsByStatus": jobs,
        },
        "partitions": {
            "existing": len(partitions),
            "expected": len(DELETE_TABLES),
            "rowCounts": {table: rows for table, rows in partitions.items() if rows},
        },
        "filesLeftOnDisk": _referenced_files(session, game_id),
        "blockers": collect_blockers(
            game_status=str(game["status"]),
            location=location,
            active_job_count=sum(jobs.get(status, 0) for status in ACTIVE_JOB_STATUSES),
            mobile_release_rows=partitions.get("mobile_release_games", 0),
            uncovered_references=_uncovered_references(session, game_id),
        ),
    }
    preview["confirmation"] = confirmation_phrase(str(game["code"]), game_id)
    preview["previewSha256"] = preview_digest(preview)
    return preview


def execute_deletion(engine: Engine, game_id: UUID) -> dict[str, object]:
    sessions = create_owner_session_factory(engine)
    with sessions() as session, session.begin():
        receipt = GamePartitionLifecycleRepository(session).start_or_resume(
            game_id=game_id, kind=GamePartitionLifecycleKind.DELETE
        )
    for _ in range(len(DELETE_TABLES) + 2):
        if receipt.status == "done":
            break
        with sessions() as session:
            try:
                receipt = GamePartitionLifecycleRepository(session).run_next(receipt.operation_id)
                session.commit()
            except GamePartitionLifecycleError:
                # Drift is deliberately persisted as `blocked`; keep that diagnostic.
                session.commit()
                raise
    return {
        "operationId": str(receipt.operation_id),
        "status": receipt.status,
        "completedTables": len(receipt.completed_tables),
    }


def _count(session: Session, table: str, game_id: UUID) -> int:
    return int(
        session.execute(
            text(f'SELECT count(*) FROM public."{table}" WHERE game_id = :game_id'),
            {"game_id": game_id},
        ).scalar_one()
    )


def _partition_row_counts(session: Session, game_id: UUID) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in DELETE_TABLES:
        child = f'{SCHEMA}."{partition_name(game_id, table)}"'
        exists = session.execute(text("SELECT to_regclass(:child)"), {"child": child}).scalar_one()
        if exists is not None:
            counts[table] = int(session.execute(text(f"SELECT count(*) FROM {child}")).scalar_one())
    return counts


def _referenced_files(session: Session, game_id: UUID) -> dict[str, object]:
    rows = session.execute(
        text(
            """SELECT DISTINCT input_payload->>'source_directory',
                      input_payload->'page_geometry_manifest'->>'relativePath'
            FROM public.jobs WHERE game_id = :game_id"""
        ),
        {"game_id": game_id},
    ).all()
    return {
        "sourceDirectories": sorted({str(row[0]) for row in rows if row[0]}),
        "pageGeometryManifests": sorted({str(row[1]) for row in rows if row[1]}),
    }


def _uncovered_references(session: Session, game_id: UUID) -> list[dict[str, object]]:
    """Rows in public tables that would make the lifecycle's final DELETE fail."""

    constraints = session.execute(
        text(
            """SELECT child.relname, parent.relname, fk.conname,
                      array_length(fk.conkey, 1), attribute.attname
            FROM pg_constraint fk
            JOIN pg_class child ON child.oid = fk.conrelid
            JOIN pg_namespace child_schema ON child_schema.oid = child.relnamespace
            JOIN pg_class parent ON parent.oid = fk.confrelid
            JOIN pg_namespace parent_schema ON parent_schema.oid = parent.relnamespace
            JOIN pg_attribute attribute
              ON attribute.attrelid = child.oid AND attribute.attnum = fk.conkey[1]
            WHERE fk.contype = 'f' AND fk.confdeltype <> 'c'
              AND child_schema.nspname = 'public' AND parent_schema.nspname = 'public'
              AND parent.relname = ANY(:parents)
            ORDER BY child.relname, fk.conname"""
        ),
        {"parents": list(_OWNER_PARENTS)},
    ).all()
    found: list[dict[str, object]] = []
    for child, parent, name, width, column in constraints:
        if str(child) in LIFECYCLE_CLEARED:
            continue
        reference: dict[str, object] = {"table": str(child), "constraint": str(name)}
        if int(width) != 1:
            found.append({**reference, "reason": "composite foreign key is not supported"})
            continue
        owner = (
            ":game_id"
            if parent == "games"
            else f'(SELECT id FROM public."{parent}" WHERE game_id = :game_id)'
        )
        operator = "=" if parent == "games" else "IN"
        rows = int(
            session.execute(
                text(f'SELECT count(*) FROM public."{child}" WHERE "{column}" {operator} {owner}'),
                {"game_id": game_id},
            ).scalar_one()
        )
        if rows:
            found.append({**reference, "rows": rows})
    return found


def _has_running_delete(session: Session, game_id: UUID) -> bool:
    return (
        session.execute(
            text(
                """SELECT 1 FROM public.game_storage_lifecycle_operations
                WHERE game_id = :game_id AND operation_kind = 'delete' AND status = 'running'"""
            ),
            {"game_id": game_id},
        ).one_or_none()
        is not None
    )


def _engine(*, read_only: bool) -> Engine:
    options = "-c statement_timeout=30000"
    if read_only:
        options += " -c default_transaction_read_only=on"
    return create_engine(
        ApiSettings.from_environment().owner_database_url,
        connect_args={"connect_timeout": 5, "options": options},
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-id", type=UUID, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--expected-preview-sha256")
    parser.add_argument("--confirmation")
    arguments = parser.parse_args(argv)
    game_id: UUID = arguments.game_id

    result: dict[str, Any]
    try:
        with Session(_engine(read_only=True)) as session:
            preview = build_preview(session, game_id)
            resuming = _has_running_delete(session, game_id)
        if not arguments.execute:
            result = {"mode": "preview", **preview}
        else:
            if preview["blockers"]:
                raise DeletionBlocked("GAME_DELETION_BLOCKED", json.dumps(preview["blockers"]))
            if arguments.confirmation != preview["confirmation"]:
                raise DeletionBlocked(
                    "CONFIRMATION_MISMATCH", "Pass the exact confirmation from the preview."
                )
            # A resumed deletion has already dropped partitions, so its preview differs.
            if not resuming and arguments.expected_preview_sha256 != preview["previewSha256"]:
                raise DeletionBlocked(
                    "PREVIEW_CHANGED", "The game changed after the confirmed preview."
                )
            result = {"mode": "execute", "game": preview["game"]}
            result.update(execute_deletion(_engine(read_only=False), game_id))
    except DeletionBlocked as error:
        print(json.dumps({"error": error.code, "detail": error.detail}, ensure_ascii=False))
        return 1
    except GamePartitionLifecycleError as error:
        print(json.dumps({"error": error.code, "detail": error.message, **error.details}))
        return 1
    except OperationalError as error:
        # Lock or statement timeout: nothing of the failed step was committed.
        print(json.dumps({"error": "RETRYABLE_DATABASE_ERROR", "detail": str(error.orig)}))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
