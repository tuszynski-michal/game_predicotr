"""Capture current read-only TRAIN/A evidence and compare pinned production crops.

Run again with the same arguments/output for verified replay. A is metrics-only;
protected/unfinished blind sources are rejected before any image read.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api/src"))
sys.path.insert(0, str(ROOT / "services/worker/src"))

from game_predictor_api.config import ApiSettings  # noqa: E402
from game_predictor_api.storage.database import create_database_engine  # noqa: E402
from game_predictor_api.storage.production_crop_capture import capture  # noqa: E402
from game_predictor_worker.images.production_crop_comparison import run_comparison  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-id", type=UUID, required=True)
    parser.add_argument("--cohort-id", type=UUID, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--source-id", type=UUID, action="append", required=True)
    parser.add_argument("--grid-version", type=UUID)
    parser.add_argument("--lab-iteration", type=UUID)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    settings = ApiSettings.from_environment()
    artifact_root = args.artifact_root or settings.artifact_root
    db = create_database_engine(settings)
    try:
        with Session(db) as session, session.begin():
            session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
            snapshot, captured = capture(
                session,
                artifact_root=artifact_root,
                repository_root=args.repository_root,
                game=args.game_id,
                cohort=args.cohort_id,
                manifest_sha256=args.manifest_sha256,
                source_ids=args.source_id,
                grid_version=args.grid_version,
                lab_iteration=args.lab_iteration,
            )
            # Protection and currentness remain in the same read snapshot as pixel use.
            report = run_comparison(
                snapshot,
                captured,
                root=args.output,
                repository_root=args.repository_root,
                artifact_root=artifact_root,
            )
        print(f"Diagnostic comparison: {report['state']}; {args.output / 'report.json'}")
    finally:
        db.dispose()


if __name__ == "__main__":
    main()
