"""Preview or apply the D-484 geometry completeness state of existing images.

TASK-0807. Every source image of the game whose
``source_images.geometry_completeness_evaluated_at`` is still ``NULL`` gets its
gate status (``geometry_complete`` / ``geometry_incomplete`` / ``NULL`` outside
the gate) from the domain classifier. Before an image is classified, its live
boards that point to an older source geometry revision are re-pointed to the
newest one when the newer revision repeats their geometry exactly (pointer
columns only: board, its current render manifest and its cells; crops,
checksums and decisions stay). Boards whose geometry differs are left alone and
listed with a reason. Nothing is materialized and nothing is deleted.

``--preview`` (default) is read-only: every transaction is ``READ ONLY`` and the
re-pointing is only simulated in the classification. ``--execute`` writes one
batch (at most 500 images) per committed transaction. Both modes keep a
checkpoint (cursor and accumulated counters) next to the reports, so a run
stopped by ``--max-seconds`` continues where it stopped; ``--restart`` starts
over. An executed batch is never counted twice: images evaluated by an earlier
run (or by the live pipeline) are skipped. The final summary is read from the
database (images per status, not evaluated, incomplete images that already
have cells).

Run with the API, workers and Reviewer of every checkout stopped
(``ai_docs/guides/LOCAL_OPERATION_GUIDE.md``, migration ``0139``).

Examples (repository root)::

    .venv\\Scripts\\python.exe scripts/backfill_image_geometry_completeness.py --game-id <uuid>
    .venv\\Scripts\\python.exe scripts/backfill_image_geometry_completeness.py --game-id <uuid> \\
        --execute --max-seconds 100
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from game_predictor_api.config import ApiSettings
from game_predictor_api.storage.database import (
    create_maintenance_database_engine,
    create_session_factory,
)
from game_predictor_api.storage.image_geometry_completeness_state_repository import (
    MAX_BACKFILL_BATCH_SIZE,
    BoardRepointDecision,
    GeometryCompletenessBackfillBatch,
    SourceImageGeometryCompletenessBackfill,
)
from game_predictor_api.storage.schema_readiness import (
    EXPECTED_ALEMBIC_HEAD,
    AlembicHeadMismatchError,
    database_alembic_revision,
)
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

REPORT_SCHEMA = "image-geometry-completeness-backfill-report-v1"
CHECKPOINT_SCHEMA = "image-geometry-completeness-backfill-checkpoint-v1"
MAX_LISTED_BOARDS = 200


def _arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-id", required=True, type=UUID)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--preview", action="store_true", help="Read-only plan (default).")
    action.add_argument("--execute", action="store_true", help="Write, one batch per commit.")
    parser.add_argument("--batch-size", type=int, default=MAX_BACKFILL_BATCH_SIZE)
    parser.add_argument("--max-seconds", type=float, default=100.0)
    parser.add_argument("--restart", action="store_true", help="Ignore the stored checkpoint.")
    parser.add_argument(
        "--report-dir",
        type=Path,
        help="Directory of the JSON reports and checkpoints (default: <artifact root>/"
        "data/exports/image-geometry-completeness/<game id>).",
    )
    arguments = parser.parse_args(argv)
    if not 1 <= arguments.batch_size <= MAX_BACKFILL_BATCH_SIZE:
        parser.error(f"--batch-size must be between 1 and {MAX_BACKFILL_BATCH_SIZE}")
    return arguments


def _require_schema(engine: Engine) -> None:
    found = database_alembic_revision(engine)
    if found != EXPECTED_ALEMBIC_HEAD:
        raise AlembicHeadMismatchError(found)


def _limits(session: Session, *, read_only: bool) -> None:
    connection = session.connection()
    if read_only:
        connection.execute(text("SET TRANSACTION READ ONLY"))
    connection.execute(text("SET LOCAL lock_timeout = '5s'"))
    connection.execute(text("SET LOCAL statement_timeout = '110s'"))


def _empty_totals() -> dict[str, Any]:
    return {
        "batches": 0,
        "images": 0,
        "statuses": {},
        "imageStates": {},
        "incompleteWithCells": 0,
        "repointedBoards": 0,
        "notRepointableBoards": 0,
        "notRepointableByReason": {},
        "notRepointable": [],
    }


def _checkpoint_path(report_dir: Path, action: str) -> Path:
    return report_dir / f"{action}-checkpoint.json"


def _read_checkpoint(report_dir: Path, action: str) -> tuple[UUID | None, dict[str, Any]]:
    path = _checkpoint_path(report_dir, action)
    if not path.is_file():
        return None, _empty_totals()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != CHECKPOINT_SCHEMA or payload.get("completed"):
        return None, _empty_totals()
    cursor = payload.get("lastSourceImageId")
    return (None if cursor is None else UUID(str(cursor))), dict(payload["totals"])


def _write_checkpoint(
    report_dir: Path,
    action: str,
    cursor: UUID | None,
    totals: dict[str, Any],
    *,
    completed: bool,
) -> None:
    path = _checkpoint_path(report_dir, action)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {
                "schema": CHECKPOINT_SCHEMA,
                "lastSourceImageId": None if cursor is None else str(cursor),
                "completed": completed,
                "totals": totals,
                "updatedAt": datetime.now(UTC).isoformat(),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    temporary.replace(path)


def _board(decision: BoardRepointDecision) -> dict[str, Any]:
    return {
        "recognizedBoardId": str(decision.recognized_board_id),
        "sourceImageId": str(decision.source_image_id),
        "reviewItemId": None if decision.review_item_id is None else str(decision.review_item_id),
        "positionIndex": decision.position_index,
        "fromRevision": decision.from_revision,
        "toRevision": decision.to_revision,
        "reasonCode": decision.reason_code,
    }


def _accumulate(totals: dict[str, Any], batch: GeometryCompletenessBackfillBatch) -> None:
    totals["batches"] += 1
    totals["images"] += batch.processed_image_count
    for key, counts in (
        ("statuses", batch.status_counts),
        ("imageStates", batch.image_state_counts),
    ):
        counter = Counter(totals[key])
        counter.update(counts)
        totals[key] = dict(sorted(counter.items()))
    totals["incompleteWithCells"] += batch.incomplete_with_cells_count
    totals["repointedBoards"] += batch.repointed_board_count
    totals["notRepointableBoards"] += len(batch.not_repointable)
    reasons = Counter(totals["notRepointableByReason"])
    reasons.update(str(decision.reason_code) for decision in batch.not_repointable)
    totals["notRepointableByReason"] = dict(sorted(reasons.items()))
    listed = list(totals["notRepointable"])
    for decision in batch.not_repointable:
        if len(listed) >= MAX_LISTED_BOARDS:
            break
        listed.append(_board(decision))
    totals["notRepointable"] = listed


def _run(
    factory: sessionmaker[Session],
    arguments: argparse.Namespace,
    report_dir: Path,
    *,
    apply: bool,
) -> dict[str, Any]:
    action = "execute" if apply else "preview"
    started = time.monotonic()
    cursor, totals = (
        (None, _empty_totals()) if arguments.restart else _read_checkpoint(report_dir, action)
    )
    completed = False
    while time.monotonic() - started < arguments.max_seconds:
        with factory() as session:
            _limits(session, read_only=not apply)
            batch = SourceImageGeometryCompletenessBackfill(session).next_batch(
                arguments.game_id,
                after_source_image_id=cursor,
                limit=arguments.batch_size,
                apply=apply,
            )
            if apply:
                session.commit()
            else:
                session.rollback()
        if batch.processed_image_count == 0:
            completed = True
            break
        cursor = batch.last_source_image_id
        _accumulate(totals, batch)
        if not batch.has_more:
            completed = True
            break
        _write_checkpoint(report_dir, action, cursor, totals, completed=False)
    _write_checkpoint(report_dir, action, cursor, totals, completed=completed)
    return {
        "totals": totals,
        "lastSourceImageId": None if cursor is None else str(cursor),
        "completed": completed,
        "elapsedSeconds": round(time.monotonic() - started, 3),
    }


def _summary(factory: sessionmaker[Session], game_id: UUID) -> dict[str, Any]:
    with factory() as session:
        _limits(session, read_only=True)
        summary = SourceImageGeometryCompletenessBackfill(session).summary(game_id)
        session.rollback()
    return {
        "statuses": dict(sorted(summary.status_counts.items())),
        "notEvaluated": summary.not_evaluated_count,
        "incompleteWithCells": summary.incomplete_with_cells_count,
    }


def _report_dir(settings: ApiSettings, arguments: argparse.Namespace) -> Path:
    if arguments.report_dir is not None:
        return Path(arguments.report_dir).resolve()
    return (
        settings.artifact_root
        / "data"
        / "exports"
        / "image-geometry-completeness"
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
        _require_schema(engine)
        factory = create_session_factory(engine)
        body = _run(factory, arguments, report_dir, apply=arguments.execute)
        body["databaseSummary"] = _summary(factory, arguments.game_id)
    finally:
        engine.dispose()
    report = {
        "schema": REPORT_SCHEMA,
        "action": action,
        "gameId": str(arguments.game_id),
        "generatedAt": datetime.now(UTC).isoformat(),
        **body,
    }
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = report_dir / f"{stamp}-{action}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({**report, "reportPath": str(path)}, indent=2, sort_keys=True))
    return 0 if report["completed"] else 3


if __name__ == "__main__":
    sys.exit(main())
