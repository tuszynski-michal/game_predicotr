"""Build or resume v0.9 topology and crop-provenance metadata for one game."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

from game_predictor_api.config import ApiSettings
from game_predictor_api.storage.database import create_database_engine, create_session_factory
from game_predictor_api.storage.v09_schema_backfill_repository import (
    SqlAlchemyV09SchemaBackfillRepository,
    V09SchemaBackfillError,
    V09SchemaBackfillValidation,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-id", type=UUID, required=True)
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--progress-every", type=int, default=10)
    return parser.parse_args()


def _default_checkpoint(game_id: UUID) -> Path:
    return Path(".runtime") / f"v09-schema-backfill-{game_id}.json"


def _read_checkpoint(path: Path, game_id: UUID) -> UUID | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("gameId") != str(game_id):
        raise ValueError("The checkpoint belongs to a different game.")
    board_id = payload.get("lastCommittedBoardId")
    return None if board_id is None else UUID(str(board_id))


def _write_checkpoint(path: Path, *, game_id: UUID, board_id: UUID | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(
            {
                "gameId": str(game_id),
                "lastCommittedBoardId": None if board_id is None else str(board_id),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    temporary.replace(path)


def _validation_value(validation: V09SchemaBackfillValidation) -> dict[str, Any]:
    return {
        "gameId": str(validation.game_id),
        "topologyRulesVersionId": (
            None
            if validation.topology_rules_version_id is None
            else str(validation.topology_rules_version_id)
        ),
        "boardCount": validation.board_count,
        "cellCount": validation.cell_count,
        "missingTopologyBoardCount": validation.missing_topology_board_count,
        "missingGeometryApprovalCount": validation.missing_geometry_approval_count,
        "inconsistentQualityCount": validation.inconsistent_quality_count,
        "missingApprovedCropCount": validation.missing_approved_crop_count,
        "ready": validation.ready,
    }


def main() -> int:
    arguments = _arguments()
    if not 1 <= arguments.batch_size <= 200:
        print("--batch-size must be between 1 and 200", file=sys.stderr)
        return 2
    if arguments.progress_every < 1:
        print("--progress-every must be positive", file=sys.stderr)
        return 2
    checkpoint_path = arguments.checkpoint or _default_checkpoint(arguments.game_id)
    try:
        after_board_id = _read_checkpoint(checkpoint_path, arguments.game_id)
        settings = ApiSettings.from_environment()
        factory = create_session_factory(create_database_engine(settings))
        processed = 0
        updated_boards = 0
        updated_cells = 0
        batch_number = 0
        print(
            json.dumps(
                {
                    "status": "running",
                    "gameId": str(arguments.game_id),
                    "checkpoint": str(checkpoint_path),
                    "resumingAfterBoardId": (
                        None if after_board_id is None else str(after_board_id)
                    ),
                },
                sort_keys=True,
            ),
            flush=True,
        )
        while True:
            with factory.begin() as session:
                step = SqlAlchemyV09SchemaBackfillRepository(session).backfill_next_batch(
                    arguments.game_id,
                    after_board_id=after_board_id,
                    batch_size=arguments.batch_size,
                )
            processed += step.processed_board_count
            updated_boards += step.updated_board_count
            updated_cells += step.updated_cell_count
            batch_number += 1
            after_board_id = step.next_board_id
            _write_checkpoint(
                checkpoint_path,
                game_id=arguments.game_id,
                board_id=after_board_id,
            )
            if batch_number % arguments.progress_every == 0 or not step.has_more:
                print(
                    json.dumps(
                        {
                            "status": "running",
                            "batch": batch_number,
                            "processedBoardCount": processed,
                            "updatedBoardCount": updated_boards,
                            "updatedCellCount": updated_cells,
                            "lastCommittedBoardId": (
                                None if after_board_id is None else str(after_board_id)
                            ),
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
            if not step.has_more:
                break
        with factory.begin() as session:
            validation = SqlAlchemyV09SchemaBackfillRepository(session).validate_game(
                arguments.game_id
            )
        if not validation.ready:
            # A concurrent legacy write may have inserted a lower UUID after the
            # cursor passed it. The next bounded run must rescan idempotently.
            _write_checkpoint(checkpoint_path, game_id=arguments.game_id, board_id=None)
    except (OSError, ValueError, V09SchemaBackfillError) as error:
        payload: dict[str, Any] = {
            "status": "failed",
            "error": str(error),
            "checkpoint": str(checkpoint_path),
        }
        if isinstance(error, V09SchemaBackfillError):
            payload["code"] = error.code
            payload["problemBoardIds"] = [str(board_id) for board_id in error.board_ids]
        print(json.dumps(payload, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": "ready" if validation.ready else "incomplete",
                "checkpoint": str(checkpoint_path),
                "processedBoardCount": processed,
                "updatedBoardCount": updated_boards,
                "updatedCellCount": updated_cells,
                "validation": _validation_value(validation),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if validation.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
