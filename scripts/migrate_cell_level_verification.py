"""D-462 data migration (TASK-0728): read-only preview, then a reviewed apply.

Run from the repository root with services/api/src on PYTHONPATH.

  preview --game-id ID --output PATH
      One REPEATABLE READ READ ONLY transaction; writes an immutable manifest.
  apply --preview PATH --preview-sha256 SHA --output PATH [--limit N]
        [--after-review-item-id ID]
      Separate data authorization. One transaction per board; a board whose
      current plan differs from the manifest is reported as `drift` and left
      unchanged; a repeated apply reports `already_applied`.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.cell_level_verification_migration import (
    CellLevelMigrationError,
    validate_manifest,
)
from game_predictor_api.domain.image_reviews import (
    ImageReviewConflictError,
    ImageReviewNotFoundError,
)
from game_predictor_api.domain.image_symbol_reviews import SymbolCellReviewError
from game_predictor_api.storage.cell_level_verification_migration_repository import (
    DEFAULT_BATCH_SIZE,
    CellLevelMigrationInvariantError,
    CellLevelVerificationMigrationRepository,
)
from game_predictor_api.storage.database import create_database_engine, create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

REPORT_EVERY = 250


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    preview = sub.add_parser("preview", help="Read-only manifest of every board action")
    preview.add_argument("--game-id", type=UUID, required=True)
    preview.add_argument("--output", type=Path, required=True)
    preview.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    apply = sub.add_parser("apply", help="Apply a reviewed manifest (separate authorization)")
    apply.add_argument("--preview", type=Path, required=True)
    apply.add_argument("--preview-sha256", required=True)
    apply.add_argument("--output", type=Path, required=True)
    apply.add_argument("--limit", type=int, default=None, help="Boards in this run (default: all)")
    apply.add_argument("--after-review-item-id", type=UUID, default=None)
    return parser.parse_args()


def write_report(path: Path, report: dict[str, Any], *, exclusive: bool = False) -> None:
    """Write atomically; `exclusive` refuses an existing file (immutable preview)."""

    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if exclusive:
        try:
            with path.open("x", encoding="utf-8") as handle:
                handle.write(content)
        except FileExistsError as error:
            raise CellLevelMigrationError(
                "CELL_MIGRATION_OUTPUT_EXISTS", "Use a new path for each immutable preview."
            ) from error
        return
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def run_preview(args: argparse.Namespace) -> int:
    if args.output.exists():
        raise CellLevelMigrationError(
            "CELL_MIGRATION_OUTPUT_EXISTS", "Use a new path for each immutable preview."
        )
    settings = ApiSettings.from_environment()
    sessions = create_session_factory(create_database_engine(settings))
    with game_storage_scope(args.game_id), sessions.begin() as session:
        session.connection().execute(
            text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        )
        session.connection().execute(text("SET LOCAL statement_timeout = '120s'"))
        manifest = CellLevelVerificationMigrationRepository(session).preview(
            args.game_id,
            generated_at=datetime.now(UTC).isoformat(),
            batch_size=args.batch_size,
        )
    write_report(args.output, manifest, exclusive=True)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "previewSha256": manifest["previewSha256"],
                "counts": manifest["counts"],
                "notes": {code: len(ids) for code, ids in manifest["notes"].items()},
            }
        )
    )
    return 0


def run_apply(args: argparse.Namespace) -> int:
    if args.preview.resolve() == args.output.resolve() or args.output.exists():
        raise CellLevelMigrationError(
            "CELL_MIGRATION_OUTPUT_INVALID",
            "Each apply run needs a new report path; it never overwrites a preview or report.",
        )
    manifest = json.loads(args.preview.read_text(encoding="utf-8"))
    game_id, plans = validate_manifest(manifest)
    if manifest["previewSha256"] != args.preview_sha256:
        raise CellLevelMigrationError(
            "CELL_MIGRATION_SCOPE_INVALID", "Apply requires the exact preview checksum."
        )
    if args.limit is not None and args.limit < 1:
        raise CellLevelMigrationError("CELL_MIGRATION_LIMIT_INVALID", "The limit must be >= 1.")
    settings = ApiSettings.from_environment()
    sessions = create_session_factory(create_database_engine(settings))
    with game_storage_scope(game_id), sessions.begin() as session:
        CellLevelVerificationMigrationRepository(session).require_ready_game(game_id)
    selected = [
        plan
        for plan in plans
        if args.after_review_item_id is None
        or str(plan.review_item_id) > str(args.after_review_item_id)
    ]
    if args.limit is not None:
        selected = selected[: args.limit]
    results: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "previewSha256": manifest["previewSha256"],
        "gameId": str(game_id),
        "startedAt": datetime.now(UTC).isoformat(),
        "selectedBoards": len(selected),
        "results": results,
    }
    try:
        for index, plan in enumerate(selected, start=1):
            try:
                with game_storage_scope(game_id), sessions.begin() as session:
                    session.connection().execute(text("SET LOCAL lock_timeout = '10s'"))
                    session.connection().execute(text("SET LOCAL statement_timeout = '120s'"))
                    result = CellLevelVerificationMigrationRepository(session).apply_board(
                        game_id, plan
                    )
            except CellLevelMigrationInvariantError as error:
                report["fatal"] = {
                    "reviewItemId": str(plan.review_item_id),
                    "code": error.code,
                    "message": str(error),
                }
                raise
            except DBAPIError as error:
                # E.g. a lock timeout: stop, name the board; resume from lastReviewItemId.
                report["fatal"] = {
                    "reviewItemId": str(plan.review_item_id),
                    "code": "DATABASE_ERROR",
                    "message": str(error.orig)[:500],
                }
                raise
            except (
                CellLevelMigrationError,
                SymbolCellReviewError,
                ImageReviewConflictError,
                ImageReviewNotFoundError,
            ) as error:
                result = {
                    "reviewItemId": str(plan.review_item_id),
                    "result": "failed",
                    "code": getattr(error, "code", type(error).__name__),
                    "message": str(error),
                }
            results.append(result)
            if index % REPORT_EVERY == 0:
                write_report(args.output, report | {"summary": summary(results)})
    finally:
        report["finishedAt"] = datetime.now(UTC).isoformat()
        report["summary"] = summary(results)
        report["lastReviewItemId"] = results[-1]["reviewItemId"] if results else None
        write_report(args.output, report)
    print(json.dumps({"output": str(args.output), "summary": report["summary"]}))
    # Drift or failed boards need a new preview; the run itself is complete.
    return 1 if report["summary"].get("drift") or report["summary"].get("failed") else 0


def summary(results: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        counts[result["result"]] = counts.get(result["result"], 0) + 1
    counts["rechecked"] = sum(int(result.get("rechecked", 0)) for result in results)
    counts["reopened"] = sum(1 for result in results if result.get("reopened"))
    counts["closed"] = sum(1 for result in results if result.get("closed"))
    counts["closeMissed"] = sum(
        1 for result in results if result.get("expectedClose") and not result.get("closed")
    )
    return counts


def main() -> int:
    args = arguments()
    try:
        return run_preview(args) if args.command == "preview" else run_apply(args)
    except CellLevelMigrationError as error:
        print(json.dumps({"error": error.code, "message": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
