"""Preview the fixed 70-board pilot; apply only after a separately authorized data step.

Run from the repository root with services/api/src on PYTHONPATH. Preview/audit
open read-only transactions and support schema 0125. Apply requires 0128 and
commits at most five boards, each together with its durable database receipt.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any
from uuid import UUID

from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.partial_board_reconciliation import (
    MAX_APPLY_BOARDS,
    MAX_AUDIT_BOARDS,
    PILOT_GAME_ID,
    ReconciliationError,
    validate_manifest,
)
from game_predictor_api.storage.database import create_database_engine, create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.partial_board_reconciliation_repository import (
    PartialBoardReconciliationRepository,
)
from sqlalchemy import text


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    preview = sub.add_parser("preview", help="Read-only preview of the exact 70 pilot boards")
    audit = sub.add_parser("audit", help="Read-only, bounded page for an explicitly selected game")
    apply = sub.add_parser(
        "apply", help="Apply an already reviewed preview (separate data authorization)"
    )
    counts = sub.add_parser("rebuild-counts", help="Resume bounded counts after all pilot receipts")
    for command in (preview, audit, apply, counts):
        command.add_argument("--output", type=Path, required=True)
        command.add_argument(
            "--source-root",
            type=Path,
            action="append",
            help="Managed data root; defaults to configured artifact_root/data",
        )
    audit.add_argument("--game-id", type=UUID, required=True)
    audit.add_argument("--after-sequence", type=int, default=0)
    audit.add_argument("--limit", type=int, choices=range(1, MAX_AUDIT_BOARDS + 1), default=25)
    for command in (apply, counts):
        command.add_argument("--preview", type=Path, required=True)
        command.add_argument("--preview-sha256", required=True)
    counts.add_argument("--limit-batches", type=int, choices=range(1, 4), default=1)
    counts.add_argument("--batch-size", type=int, default=5000, help="Records per batch: 1–10000")
    apply.add_argument("--after-sequence", type=int, default=0)
    apply.add_argument("--limit", type=int, choices=range(1, MAX_APPLY_BOARDS + 1), default=5)
    return parser.parse_args()


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    args = arguments()
    settings = ApiSettings.from_environment()
    engine = create_database_engine(settings)
    sessions = create_session_factory(engine)
    roots = args.source_root or [settings.artifact_root / "data"]
    try:
        if args.command in {"preview", "audit"} and args.output.exists():
            raise ReconciliationError(
                "RECONCILIATION_OUTPUT_EXISTS",
                "Use a new path for each immutable preview or audit.",
            )
        if args.command in {"preview", "audit"}:
            game_id = args.game_id if args.command == "audit" else PILOT_GAME_ID
            with game_storage_scope(game_id), sessions.begin() as session:
                session.connection().execute(
                    text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                )
                session.connection().execute(text("SET LOCAL statement_timeout = '15s'"))
                repository = PartialBoardReconciliationRepository(session, source_roots=roots)
                report = (
                    repository.preview(game_id)
                    if args.command == "preview"
                    else repository.audit_page(
                        game_id,
                        after_sequence=args.after_sequence,
                        limit=args.limit,
                    )
                )
        else:
            if args.preview.resolve() == args.output.resolve():
                raise ReconciliationError(
                    "RECONCILIATION_OUTPUT_INVALID",
                    "Apply output must not overwrite the immutable preview.",
                )
            manifest = json.loads(args.preview.read_text(encoding="utf-8"))
            validate_manifest(manifest)
            if (
                manifest["gameId"] != str(PILOT_GAME_ID)
                or manifest["previewSha256"] != args.preview_sha256
            ):
                raise ReconciliationError(
                    "RECONCILIATION_SCOPE_INVALID",
                    "Apply requires the exact pilot game and preview checksum.",
                )
            if args.command == "rebuild-counts":
                batches = []
                for _ in range(args.limit_batches):
                    with game_storage_scope(PILOT_GAME_ID), sessions.begin() as session:
                        result = PartialBoardReconciliationRepository(
                            session, source_roots=roots
                        ).rebuild_counts_batch(manifest, batch_size=args.batch_size)
                    batches.append(result)
                    if result["complete"]:
                        break
                report = {"previewSha256": manifest["previewSha256"], "batches": batches}
                write_report(args.output, report)
                print(json.dumps({"output": str(args.output), "complete": batches[-1]["complete"]}))
                return 0
            results: list[dict[str, Any]] = []
            skipped = [
                {key: board[key] for key in ("sequenceNumber", "code", "message")}
                for board in manifest["boards"]
                if board["sequenceNumber"] > args.after_sequence and board["status"] == "blocked"
            ]
            attempted = 0
            for board in manifest["boards"]:
                number = board["sequenceNumber"]
                if number <= args.after_sequence or board["status"] != "ready":
                    continue
                try:
                    with game_storage_scope(PILOT_GAME_ID), sessions.begin() as session:
                        result = PartialBoardReconciliationRepository(
                            session, source_roots=roots
                        ).apply_board(manifest, number)
                    results.append(result)
                    attempted += not result["replayed"]
                except Exception as error:
                    # The context manager has rolled back both projection and
                    # receipt. A later board can still be repaired independently.
                    results.append(
                        {
                            "sequenceNumber": number,
                            "status": "conflict",
                            "code": getattr(error, "code", "RECONCILIATION_APPLY_FAILED"),
                            "message": str(error)[:500],
                        }
                    )
                    attempted += 1
                if attempted >= args.limit:
                    break
            report = {
                "previewSha256": manifest["previewSha256"],
                "results": results,
                "attemptedBoards": attempted,
                "countRebuildExecuted": False,
                "skippedBlocked": skipped,
                "resumeAfterSequence": results[-1]["sequenceNumber"]
                if results
                else args.after_sequence,
            }
        write_report(args.output, report)
        print(
            json.dumps(
                {
                    "output": str(args.output),
                    "command": args.command,
                    "boards": len(report.get("boards", report.get("results", []))),
                    "previewSha256": report.get("previewSha256"),
                },
                ensure_ascii=False,
            )
        )
        return (
            2
            if report.get("skippedBlocked")
            or any(row.get("status") == "conflict" for row in report.get("results", []))
            else 0
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
