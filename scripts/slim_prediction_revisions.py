"""Preview or execute the slimming and retention of symbol prediction revisions.

D-467 S8 (TASK-0794).  ``--mode slim`` (default) removes the copy of the render
specification from ``predictions[].virtualCell`` of every existing revision
after storing its pre-slimming v1 digest in ``legacy_predictions_sha256``
(reference-library manifests written before TASK-0794 keep working); the v2
digest of every revision is verified unchanged.  ``--mode retention`` deletes
the revisions of superseded review items without cells (never an
``apply-revert`` anchor, never a revision a cell points to).

``--preview`` (default) is read-only: every transaction is READ ONLY and the
slim preview estimates the saving on a sample.  ``--execute`` writes one batch
per committed transaction; a checkpoint file next to the reports keeps the
last committed ``id`` so a run stopped by ``--max-seconds`` or an error resumes
where it stopped (already processed revisions are skipped anyway).  The space
is reclaimed by ``VACUUM (FULL, ANALYZE)`` of the revision partition afterwards
(``ai_docs/guides/DATABASE_MAINTENANCE.md``).

Examples (repository root)::

    .venv\\Scripts\\python.exe scripts/slim_prediction_revisions.py --game-id <uuid> --preview
    .venv\\Scripts\\python.exe scripts/slim_prediction_revisions.py --game-id <uuid> \\
        --execute --max-seconds 100
    .venv\\Scripts\\python.exe scripts/slim_prediction_revisions.py --game-id <uuid> \\
        --mode retention --execute
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from game_predictor_api.config import ApiSettings
from game_predictor_api.storage.database import create_maintenance_database_engine
from game_predictor_api.storage.prediction_revision_slimming import (
    PredictionRevisionSlimError,
    delete_retention_batch,
    preview_retention,
    preview_slim,
    slim_batch,
)
from game_predictor_api.storage.schema_readiness import (
    EXPECTED_ALEMBIC_HEAD,
    AlembicHeadMismatchError,
    database_alembic_revision,
)
from sqlalchemy import Connection, Engine, text

REPORT_SCHEMA = "prediction-revision-slim-report-v1"
# The read-only preview may run before migration 0137 (no legacy column yet).
PREVIEW_ALEMBIC_HEADS = frozenset({EXPECTED_ALEMBIC_HEAD, "0136_drop_cell_render_spec"})


def _arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-id", required=True, type=UUID)
    parser.add_argument("--mode", choices=("slim", "retention"), default="slim")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--preview", action="store_true", help="Read-only plan (default).")
    action.add_argument("--execute", action="store_true", help="Write, one batch per commit.")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--max-seconds", type=float, default=100.0)
    parser.add_argument("--sample-size", type=int, default=500)
    parser.add_argument(
        "--report-dir",
        type=Path,
        help="Directory of the JSON reports and the checkpoint (default: <artifact root>/"
        "data/exports/prediction-revision-slim/<game id>).",
    )
    return parser.parse_args(argv)


def _require_schema(engine: Engine, *, execute: bool) -> None:
    found = database_alembic_revision(engine)
    allowed = {EXPECTED_ALEMBIC_HEAD} if execute else PREVIEW_ALEMBIC_HEADS
    if found not in allowed:
        raise AlembicHeadMismatchError(found)


def _read_only(connection: Connection) -> None:
    connection.execute(text("SET TRANSACTION READ ONLY"))
    connection.execute(text("SET LOCAL lock_timeout = '5s'"))
    connection.execute(text("SET LOCAL statement_timeout = '110s'"))


def _preview(engine: Engine, arguments: argparse.Namespace) -> dict[str, Any]:
    with engine.connect() as connection:
        _read_only(connection)
        if arguments.mode == "slim":
            plan = preview_slim(
                connection, game_id=arguments.game_id, sample_size=arguments.sample_size
            )
        else:
            plan = preview_retention(connection, game_id=arguments.game_id)
        connection.rollback()
    return {"plan": plan}


def _checkpoint_path(report_dir: Path) -> Path:
    return report_dir / "slim-checkpoint.json"


def _read_checkpoint(report_dir: Path) -> UUID | None:
    path = _checkpoint_path(report_dir)
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8")).get("lastId")
    return None if value is None else UUID(str(value))


def _write_checkpoint(report_dir: Path, last_id: UUID | None, *, completed: bool) -> None:
    path = _checkpoint_path(report_dir)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {
                "lastId": None if last_id is None else str(last_id),
                "completed": completed,
                "updatedAt": datetime.now(UTC).isoformat(),
            }
        ),
        encoding="utf-8",
    )
    temporary.replace(path)


def _execute_slim(
    engine: Engine, arguments: argparse.Namespace, report_dir: Path
) -> dict[str, Any]:
    started = time.monotonic()
    cursor = _read_checkpoint(report_dir)
    totals = {"batches": 0, "scanned": 0, "slimmed": 0, "alreadySlim": 0}
    bytes_before = 0
    bytes_after = 0
    completed = False
    error: dict[str, Any] | None = None
    while time.monotonic() - started < arguments.max_seconds:
        try:
            with engine.begin() as connection:
                connection.execute(text("SET LOCAL lock_timeout = '5s'"))
                connection.execute(text("SET LOCAL statement_timeout = '110s'"))
                batch = slim_batch(
                    connection,
                    game_id=arguments.game_id,
                    after_id=cursor,
                    batch_size=arguments.batch_size,
                )
        except PredictionRevisionSlimError as failure:
            error = {
                "code": failure.code,
                "message": str(failure),
                "revisionId": None if failure.revision_id is None else str(failure.revision_id),
            }
            break
        if batch.scanned == 0:
            completed = True
            break
        cursor = batch.last_id
        totals["batches"] += 1
        totals["scanned"] += batch.scanned
        totals["slimmed"] += batch.slimmed
        totals["alreadySlim"] += batch.already_slim
        bytes_before += batch.stored_bytes_before
        bytes_after += batch.stored_bytes_after
        _write_checkpoint(report_dir, cursor, completed=False)
    if completed:
        # A finished run starts from the beginning next time; nothing is left
        # unprocessed, so it only confirms that.
        _write_checkpoint(report_dir, None, completed=True)
    return {
        "totals": totals,
        "storedPredictionBytesBefore": bytes_before,
        "storedPredictionBytesAfter": bytes_after,
        "lastId": None if cursor is None else str(cursor),
        "completed": completed,
        "error": error,
        "elapsedSeconds": round(time.monotonic() - started, 3),
    }


def _execute_retention(engine: Engine, arguments: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    deleted = 0
    stored = 0
    batches = 0
    completed = False
    while time.monotonic() - started < arguments.max_seconds:
        with engine.begin() as connection:
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            connection.execute(text("SET LOCAL statement_timeout = '110s'"))
            batch = delete_retention_batch(
                connection, game_id=arguments.game_id, batch_size=arguments.batch_size
            )
        if batch.deleted == 0:
            completed = True
            break
        batches += 1
        deleted += batch.deleted
        stored += batch.stored_bytes
    return {
        "totals": {"batches": batches, "deleted": deleted},
        "storedPredictionBytesDeleted": stored,
        "completed": completed,
        "elapsedSeconds": round(time.monotonic() - started, 3),
    }


def _report_dir(settings: ApiSettings, arguments: argparse.Namespace) -> Path:
    if arguments.report_dir is not None:
        return Path(arguments.report_dir).resolve()
    return (
        settings.artifact_root
        / "data"
        / "exports"
        / "prediction-revision-slim"
        / str(arguments.game_id)
    )


def main(argv: list[str] | None = None) -> int:
    arguments = _arguments(argv)
    settings = ApiSettings.from_environment()
    action = "execute" if arguments.execute else "preview"
    report_dir = _report_dir(settings, arguments)
    report_dir.mkdir(parents=True, exist_ok=True)
    engine = create_maintenance_database_engine(settings)
    try:
        _require_schema(engine, execute=arguments.execute)
        if not arguments.execute:
            body = _preview(engine, arguments)
        elif arguments.mode == "slim":
            body = _execute_slim(engine, arguments, report_dir)
        else:
            body = _execute_retention(engine, arguments)
    finally:
        engine.dispose()
    report = {
        "schema": REPORT_SCHEMA,
        "mode": arguments.mode,
        "action": action,
        "gameId": str(arguments.game_id),
        "generatedAt": datetime.now(UTC).isoformat(),
        **body,
    }
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = report_dir / f"{stamp}-{arguments.mode}-{action}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({**report, "reportPath": str(path)}, indent=2, sort_keys=True))
    if action == "preview":
        return 0
    return 0 if report.get("completed") and not report.get("error") else 2


if __name__ == "__main__":
    sys.exit(main())
