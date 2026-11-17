"""Read-only preparation benchmark: actual grid-only readiness on existing corrections."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import UUID

REPOSITORY = Path(__file__).resolve().parents[1]
for relative in ("services/api/src", "services/worker/src"):
    sys.path.insert(0, str(REPOSITORY / relative))

from game_predictor_api.application.grid_correction_learning import (  # noqa: E402
    GridCorrectionLearningService,
)
from game_predictor_api.config import ApiSettings  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=UUID, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("OUTPUT_ALREADY_EXISTS")
    # Enforce database read-only even if a future preview implementation drifts.
    engine = create_engine(
        ApiSettings.from_environment().owner_database_url,
        connect_args={
            "connect_timeout": 5,
            "options": "-c default_transaction_read_only=on -c statement_timeout=110000",
        },
    )
    service = GridCorrectionLearningService(engine, sessionmaker(engine), args.artifact_root)
    print(
        "Preparing a grid-only preview in database READ ONLY mode; no job will be started",
        flush=True,
    )
    try:
        value = service.preview(
            args.game,
            {
                "trainingMode": "grid-only",
                "importJobIds": [],
                "exclusions": [],
                "policyVersion": "application-grid-corrections-v4",
                "validationAssignments": {},
                "historicalCohorts": [],
            },
        )
        with args.output.open("x", encoding="utf-8") as output:
            json.dump(value, output, indent=2)
        print(
            json.dumps(
                {
                    key: value.get(key)
                    for key in (
                        "trainingMode",
                        "canStart",
                        "roleCounts",
                        "partialTrainingPhotos",
                        "blockers",
                        "dataAvailability",
                    )
                }
            ),
            flush=True,
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
