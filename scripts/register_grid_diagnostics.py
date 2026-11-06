"""Stage metadata; execute only as an explicitly approved deployment operation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from uuid import UUID

from diagnose_full_board_input import read_json, write_json  # type: ignore[import-not-found]
from game_predictor_worker.geometry_core.diagnostic_registration import (
    require_registration,
    stage_registration,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    stage = commands.add_parser("stage")
    stage.add_argument("--game", type=UUID, required=True)
    stage.add_argument("--record", type=Path, action="append", required=True)
    stage.add_argument("--output", type=Path, required=True)
    execute = commands.add_parser("execute")
    execute.add_argument("--manifest", type=Path, required=True)
    execute.add_argument("--actor", required=True)
    execute.add_argument("--approved-deployment", action="store_true", required=True)
    args = parser.parse_args()
    if args.command == "stage":
        value = stage_registration(args.game, (read_json(path) for path in args.record))
        write_json(args.output, value)
        print(f"Staged {len(value['requests'])} records; no database writes.")
        return
    value = require_registration(read_json(args.manifest))
    from game_predictor_api.config import get_settings
    from game_predictor_api.storage.database import create_database_engine
    from game_predictor_api.storage.game_storage_routing import (
        GameStorageIntent,
        GameStorageRouter,
        game_storage_scope,
    )
    from sqlalchemy import text
    from sqlalchemy.orm import Session

    engine = create_database_engine(get_settings())
    try:
        with game_storage_scope(UUID(value["gameId"])), Session(engine) as session, session.begin():
            session.execute(text("SET LOCAL statement_timeout='10s'"))
            session.execute(text("SET LOCAL lock_timeout='3s'"))
            GameStorageRouter().bind(session, UUID(value["gameId"]), intent=GameStorageIntent.WRITE)
            for request in value["requests"]:
                session.execute(
                    text(
                        "SELECT public.recording_diagnostic_use_v1"
                        "(:game,CAST(:request AS jsonb),:actor)"
                    ),
                    {
                        "game": UUID(value["gameId"]),
                        "request": json.dumps(request),
                        "actor": args.actor,
                    },
                ).scalar_one()
        print(f"Registered {len(value['requests'])} record bindings atomically.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
