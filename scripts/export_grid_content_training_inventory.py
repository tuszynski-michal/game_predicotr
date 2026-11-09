"""Export aggregate live/frozen counts for one cohort using a read-only transaction."""

import argparse
import json
import sys
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api/src"))
sys.path.insert(0, str(ROOT / "services/worker/src"))

from game_predictor_api.config import ApiSettings  # noqa: E402
from game_predictor_api.storage.database import create_database_engine  # noqa: E402
from game_predictor_api.storage.grid_cell_content import (  # noqa: E402
    SqlAlchemyGridCellContentRepository,
)
from game_predictor_api.storage.grid_content_training_inventory import (  # noqa: E402
    training_inventory,
)
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-id", type=UUID, required=True)
    parser.add_argument("--cohort-id", type=UUID, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    settings = ApiSettings.from_environment()
    engine = create_database_engine(settings)
    try:
        with Session(engine) as session, session.begin():
            session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
            session.execute(text("SET LOCAL statement_timeout='10s'"))
            repo = SqlAlchemyGridCellContentRepository(
                session, args.artifact_root or settings.artifact_root
            )
            report = training_inventory(repo, args.game_id, args.cohort_id, args.manifest_sha256)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Cohort inventory: {args.output}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
