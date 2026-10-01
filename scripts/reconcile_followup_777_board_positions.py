"""Preview/apply the six explicitly authorized 777 boards with durable receipts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.partial_board_reconciliation import (
    FOLLOWUP_777_SEQUENCES,
    PILOT_GAME_ID,
    build_manifest,
    validate_manifest,
)
from game_predictor_api.storage.database import (
    create_maintenance_database_engine,
    create_session_factory,
)
from game_predictor_api.storage.game_storage_routing import (
    GameStorageIntent,
    GameStorageRouter,
    game_storage_scope,
)
from game_predictor_api.storage.partial_board_reconciliation_repository import (
    PartialBoardReconciliationRepository,
)
from sqlalchemy import text


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("preview", "apply"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--preview", type=Path)
    parser.add_argument("--preview-sha256")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists; choose a new path.")
    if args.command == "apply" and (args.preview is None or args.preview_sha256 is None):
        parser.error("Apply requires --preview and --preview-sha256.")

    settings = ApiSettings.from_environment()
    engine = create_maintenance_database_engine(settings)
    sessions = create_session_factory(engine)
    roots = [settings.artifact_root / "data"]
    try:
        if args.command == "preview":
            with game_storage_scope(PILOT_GAME_ID), sessions.begin() as session:
                session.connection().execute(
                    text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                )
                session.connection().execute(text("SET LOCAL statement_timeout = '15s'"))
                repo = PartialBoardReconciliationRepository(session, source_roots=roots)
                location = GameStorageRouter().bind(
                    session, PILOT_GAME_ID, intent=GameStorageIntent.READ
                )
                boards = [repo.snapshot_board(PILOT_GAME_ID, n) for n in FOLLOWUP_777_SEQUENCES]
                report = build_manifest(
                    game_id=PILOT_GAME_ID,
                    boards=boards,
                    storage_generation=location.generation,
                    sequences=FOLLOWUP_777_SEQUENCES,
                )
            if any(board["status"] != "ready" for board in report["boards"]):
                parser.error("Every board must have a ready preview.")
        else:
            assert args.preview is not None and args.preview_sha256 is not None
            report = json.loads(args.preview.read_text(encoding="utf-8"))
            validate_manifest(report)
            if (
                report["gameId"] != str(PILOT_GAME_ID)
                or report["sequences"] != list(FOLLOWUP_777_SEQUENCES)
                or report["previewSha256"] != args.preview_sha256
            ):
                parser.error("Preview scope or checksum differs from the six authorized boards.")
            results = []
            for number in FOLLOWUP_777_SEQUENCES:
                with game_storage_scope(PILOT_GAME_ID), sessions.begin() as session:
                    result = PartialBoardReconciliationRepository(
                        session, source_roots=roots
                    ).apply_board(report, number)
                results.append(result)
            report = {"previewSha256": args.preview_sha256, "results": results}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    "output": str(args.output),
                    "boards": len(report.get("boards", report.get("results", []))),
                    "previewSha256": report["previewSha256"],
                }
            )
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
