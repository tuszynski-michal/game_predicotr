"""Export existing board coverage diagnostics using a read-only game-scoped snapshot.

Usage: .venv/Scripts/python.exe scripts/read_grid_diagnostics.py --game-id UUID --output PATH
No service is started, no projection is rebuilt and no operator data is written.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api/src"))
sys.path.insert(0, str(ROOT / "services/worker/src"))

from game_predictor_api.config import ApiSettings  # noqa: E402
from game_predictor_api.schemas.image_reviews import to_board_import_coverage_response  # noqa: E402
from game_predictor_api.storage.board_import_coverage_repository import (  # noqa: E402
    SqlAlchemyBoardImportCoverageRepository,
)
from game_predictor_api.storage.database import create_database_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-id", type=UUID, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    started_at = datetime.now(UTC)
    started = monotonic()
    engine = create_database_engine(ApiSettings.from_environment())
    try:
        with Session(bind=engine) as session:
            report = SqlAlchemyBoardImportCoverageRepository(session).board_import_coverage(
                arguments.game_id, view="missing", limit=1, include_diagnostics=True
            )
            if report is None:
                raise ValueError("Selected game does not exist")
            response = to_board_import_coverage_response(report).model_dump(
                mode="json", by_alias=True
            )
        output = {
            "snapshotStartedAt": started_at.isoformat(),
            "finishedAt": datetime.now(UTC).isoformat(),
            "elapsedSeconds": round(monotonic() - started, 3),
            "transaction": "REPEATABLE READ READ ONLY; game storage READ/RLS bound",
            "coverage": response,
        }
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(
            json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"Read-only diagnostics saved; elapsed {output['elapsedSeconds']}s")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
