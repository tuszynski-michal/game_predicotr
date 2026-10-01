"""Preview or execute the conversion of ``legacy_file`` boards to ``virtual_source``.

D-467 S6 (TASK-0791).  Every remaining ``legacy_file`` board keeps its current
corners and qualification; its cells are rendered through the same path as a
manual virtual geometry save and persisted as a new ``virtual_source``
revision (TASK-0702 rule ``max(N, R) + 1``), with its render manifest and the
human decisions of its current cells carried over unchanged.

``--preview`` is read-only (every transaction is READ ONLY) and reports the
plan per source: boards, cells, decisions and problems; ``--render-sources N``
additionally renders the first N convertible sources in memory.  ``--execute``
converts one source per committed transaction, so a run interrupted by
``--max-seconds`` or an error is resumed by running it again (converted boards
are no longer ``legacy_file``).  A source with a problem is skipped, reported
and makes the exit code non-zero.

Examples (repository root)::

    .venv\\Scripts\\python.exe scripts/convert_legacy_boards_to_virtual.py \\
        --game-id <uuid> --preview --render-sources 3
    .venv\\Scripts\\python.exe scripts/convert_legacy_boards_to_virtual.py \\
        --game-id <uuid> --execute --max-seconds 100
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from game_predictor_api.application.legacy_board_conversion import (
    LegacyBoardConversionError,
    LegacyBoardConversionService,
    LegacyConversionSourcePlan,
)
from game_predictor_api.application.virtual_grid_geometry import VirtualGridGeometryService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.image_grid_reviews import ImageGridReviewError
from game_predictor_api.storage.database import create_database_engine, create_session_factory
from game_predictor_api.storage.schema_readiness import require_alembic_head
from game_predictor_api.storage.virtual_grid_geometry_repository import (
    SqlAlchemyVirtualGridGeometryRepository,
)
from sqlalchemy import text
from sqlalchemy.orm import Session

REPORT_SCHEMA = "legacy-board-conversion-report-v1"


def _arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-id", required=True, type=UUID)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--preview", action="store_true", help="Read-only plan (default).")
    mode.add_argument("--execute", action="store_true", help="Convert, one source per commit.")
    parser.add_argument(
        "--render-sources",
        type=int,
        default=0,
        help="Preview only: render this many convertible sources in memory (no writes).",
    )
    parser.add_argument("--max-seconds", type=float, default=None)
    parser.add_argument("--max-sources", type=int, default=None)
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Write the JSON report here (default: <artifact root>/data/exports/"
        "legacy-board-conversion/<game id>/<timestamp>.json).",
    )
    arguments = parser.parse_args(argv)
    if arguments.render_sources < 0 or (arguments.execute and arguments.render_sources):
        parser.error("--render-sources is a non-negative preview-only option")
    return arguments


def _service(session: Session, settings: ApiSettings) -> LegacyBoardConversionService:
    repository = SqlAlchemyVirtualGridGeometryRepository(session)
    return LegacyBoardConversionService(
        repository, VirtualGridGeometryService(repository, settings.artifact_root)
    )


def _plan_summary(plan: LegacyConversionSourcePlan) -> dict[str, Any]:
    return {
        "sourceImageId": str(plan.source_image_id),
        "boards": [
            {
                "recognizedBoardId": str(board.recognized_board_id),
                "reviewItemId": None if board.review_item_id is None else str(board.review_item_id),
                "sequenceNumber": board.sequence_number,
                "geometryRevision": board.geometry_revision,
                "sequenceGeometryRevision": board.sequence_geometry_revision,
                "nextGeometryRevision": board.next_geometry_revision,
                "ownedCellCount": board.owned_cell_count,
                "assignedCellCount": board.assigned_cell_count,
                "humanDecisionCellCount": board.human_decision_cell_count,
                "approvedCellCount": board.approved_cell_count,
                "problems": list(board.problems),
            }
            for board in plan.boards
        ],
    }


def _preview(settings: ApiSettings, arguments: argparse.Namespace) -> dict[str, Any]:
    engine = create_database_engine(settings)
    try:
        require_alembic_head(engine)
        factory = create_session_factory(engine)
        started = time.monotonic()
        totals: Counter[str] = Counter()
        problems: Counter[str] = Counter()
        sources: list[dict[str, Any]] = []
        rendered: list[dict[str, Any]] = []
        with factory() as session:
            session.execute(text("SET TRANSACTION READ ONLY"))
            service = _service(session, settings)
            source_ids = service.source_ids(arguments.game_id)
            for source_id in source_ids:
                plan = service.plan(game_id=arguments.game_id, source_image_id=source_id)
                totals["sources"] += 1
                totals["boards"] += len(plan.boards)
                for board in plan.boards:
                    totals["ownedCells"] += board.owned_cell_count
                    totals["assignedCells"] += board.assigned_cell_count
                    totals["humanDecisionCells"] += board.human_decision_cell_count
                    totals["approvedCells"] += board.approved_cell_count
                    if board.problems:
                        totals["boardsWithProblems"] += 1
                    if not board.has_source_context:
                        totals["boardsWithoutSourceContext"] += 1
                    for problem in board.problems:
                        problems[problem] += 1
                if plan.problems:
                    totals["sourcesWithProblems"] += 1
                sources.append(_plan_summary(plan))
                if (
                    arguments.render_sources
                    and len(rendered) < arguments.render_sources
                    and not plan.problems
                ):
                    render_started = time.monotonic()
                    prepared = service.render_check(plan)
                    rendered.append(
                        {
                            "sourceImageId": str(source_id),
                            "boards": len(prepared.entries),
                            "cells": sum(len(entry.cells) for entry in prepared.entries),
                            "sourceGeometryChecksumSha256": (
                                prepared.source_geometry_checksum_sha256
                            ),
                            "seconds": round(time.monotonic() - render_started, 3),
                        }
                    )
            session.rollback()
        return {
            "schema": REPORT_SCHEMA,
            "mode": "preview",
            "gameId": str(arguments.game_id),
            "generatedAt": datetime.now(UTC).isoformat(),
            "totals": dict(sorted(totals.items())),
            "problems": dict(sorted(problems.items())),
            "renderedSources": rendered,
            "sources": sources,
            "elapsedSeconds": round(time.monotonic() - started, 3),
        }
    finally:
        engine.dispose()


def _execute(settings: ApiSettings, arguments: argparse.Namespace) -> dict[str, Any]:
    engine = create_database_engine(settings)
    try:
        require_alembic_head(engine)
        factory = create_session_factory(engine)
        started = time.monotonic()
        totals: Counter[str] = Counter()
        failures: list[dict[str, Any]] = []
        converted: list[dict[str, Any]] = []
        with factory() as session:
            session.execute(text("SET TRANSACTION READ ONLY"))
            source_ids = _service(session, settings).source_ids(arguments.game_id)
            session.rollback()
        stopped_early = False
        for source_id in source_ids:
            if (
                arguments.max_sources is not None
                and totals["sourcesVisited"] >= arguments.max_sources
            ):
                stopped_early = True
                break
            if (
                arguments.max_seconds is not None
                and time.monotonic() - started >= arguments.max_seconds
            ):
                stopped_early = True
                break
            totals["sourcesVisited"] += 1
            with factory() as session:
                service = _service(session, settings)
                try:
                    result = service.convert_source(
                        game_id=arguments.game_id,
                        source_image_id=source_id,
                        created_at=datetime.now(UTC),
                    )
                    session.commit()
                except (LegacyBoardConversionError, ImageGridReviewError) as error:
                    session.rollback()
                    totals["sourcesFailed"] += 1
                    failures.append(
                        {
                            "sourceImageId": str(source_id),
                            "code": error.code,
                            "message": str(error),
                        }
                    )
                    continue
                except Exception:
                    session.rollback()
                    raise
            if not result.boards:
                totals["sourcesAlreadyVirtual"] += 1
                continue
            totals["sourcesConverted"] += 1
            totals["boardsConverted"] += len(result.boards)
            for board in result.boards:
                totals["cellsConverted"] += board.converted_cell_count
                totals["decisionCellsPreserved"] += board.preserved_decision_cell_count
                totals["renderManifestsWritten"] += int(board.render_manifest_written)
            converted.append(
                {
                    "sourceImageId": str(source_id),
                    "sourceGeometryRevisionId": str(result.source_geometry_revision_id),
                    "boards": [
                        {
                            "recognizedBoardId": str(board.recognized_board_id),
                            "reviewItemId": str(board.review_item_id),
                            "previousGeometryRevision": board.previous_geometry_revision,
                            "geometryRevision": board.geometry_revision,
                            "convertedCellCount": board.converted_cell_count,
                            "preservedDecisionCellCount": board.preserved_decision_cell_count,
                        }
                        for board in result.boards
                    ],
                }
            )
        remaining = len(source_ids) - totals["sourcesVisited"]
        return {
            "schema": REPORT_SCHEMA,
            "mode": "execute",
            "gameId": str(arguments.game_id),
            "generatedAt": datetime.now(UTC).isoformat(),
            "totals": dict(sorted(totals.items())),
            "sourcesPlanned": len(source_ids),
            "sourcesRemaining": remaining,
            "completed": remaining == 0 and not failures,
            "stoppedEarly": stopped_early,
            "failures": failures,
            "converted": converted,
            "elapsedSeconds": round(time.monotonic() - started, 3),
        }
    finally:
        engine.dispose()


def _report_path(settings: ApiSettings, arguments: argparse.Namespace, mode: str) -> Path:
    if arguments.report is not None:
        return Path(arguments.report).resolve()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return (
        settings.artifact_root
        / "data"
        / "exports"
        / "legacy-board-conversion"
        / str(arguments.game_id)
        / f"{stamp}-{mode}.json"
    )


def main(argv: list[str] | None = None) -> int:
    arguments = _arguments(argv)
    settings = ApiSettings.from_environment()
    mode = "execute" if arguments.execute else "preview"
    report = _execute(settings, arguments) if arguments.execute else _preview(settings, arguments)
    path = _report_path(settings, arguments, mode)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    printed = {key: value for key, value in report.items() if key not in {"sources", "converted"}}
    printed["reportPath"] = str(path)
    print(json.dumps(printed, indent=2, sort_keys=True))
    if mode == "preview":
        return 0 if report["totals"].get("boardsWithProblems", 0) == 0 else 2
    return 0 if report["completed"] else 2


if __name__ == "__main__":
    sys.exit(main())
