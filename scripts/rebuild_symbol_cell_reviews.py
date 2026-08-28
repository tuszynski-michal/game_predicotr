"""Build or resume the checksum-bound symbol-cell review state for a game."""

from __future__ import annotations

import argparse
import json
import sys
import time
from uuid import UUID

from game_predictor_api.config import ApiSettings
from game_predictor_api.storage.database import create_database_engine, create_session_factory
from game_predictor_api.storage.image_symbol_review_repository import (
    SqlAlchemyImageSymbolReviewRepository,
    SymbolCellReviewBackfillReport,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-id", type=UUID, required=True)
    parser.add_argument("--batch-size", type=int, default=200)
    return parser.parse_args()


def _report_value(report: SymbolCellReviewBackfillReport) -> dict[str, object]:
    return {
        "gameId": str(report.game_id),
        "status": report.status,
        "processedReviewItemCount": report.processed_review_item_count,
        "cellCount": report.cell_count,
        "missingSequenceCount": report.missing_sequence_count,
        "invalidCropCount": report.invalid_crop_count,
        "invalidGeometryCount": report.invalid_geometry_count,
        "failureMessage": report.failure_message,
        "sampleProblemReviewItemIds": [
            str(review_item_id) for review_item_id in report.sample_problem_review_item_ids
        ],
    }


def main() -> int:
    arguments = _arguments()
    if not 1 <= arguments.batch_size <= 500:
        print("--batch-size must be between 1 and 500", file=sys.stderr)
        return 2
    settings = ApiSettings.from_environment()
    factory = create_session_factory(create_database_engine(settings))
    started = time.perf_counter()
    try:
        with factory.begin() as session:
            report = SqlAlchemyImageSymbolReviewRepository(session).start_or_resume_backfill(
                arguments.game_id
            )
        while report.status == "rebuilding":
            with factory.begin() as session:
                step = SqlAlchemyImageSymbolReviewRepository(session).backfill_next_batch(
                    arguments.game_id,
                    batch_size=arguments.batch_size,
                )
            report = step.report
            if not step.has_more:
                break
    except Exception as error:
        with factory.begin() as session:
            report = SqlAlchemyImageSymbolReviewRepository(session).mark_backfill_failed(
                arguments.game_id,
                error,
            )
    print(
        json.dumps(
            {
                "elapsedSeconds": round(time.perf_counter() - started, 3),
                "report": _report_value(report),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if report.status == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
