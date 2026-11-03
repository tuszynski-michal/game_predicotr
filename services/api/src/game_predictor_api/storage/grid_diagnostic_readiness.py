"""Budgeted metadata-only qualification through the existing human-evidence reader."""

from __future__ import annotations

import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, event, text
from sqlalchemy.orm import Session

from game_predictor_api.domain.grid_training_cohorts import GridCohortError

from .game_storage_routing import GameStorageIntent, GameStorageRouter
from .grid_training_cohort_evidence import GridCohortEvidenceReader

SOURCE_SELECTION = """
SELECT source_image_id, count(*) AS nominal_boards
FROM recognized_boards
WHERE game_id=:game AND source_image_id IS NOT NULL
AND (CAST(:after AS uuid) IS NULL OR source_image_id > CAST(:after AS uuid))
AND approved_geometry_revision=geometry_revision
AND geometry_approved_by IS NOT NULL AND geometry_approved_at IS NOT NULL
AND geometry_approved_by NOT LIKE 'system:%' AND geometry_approved_by NOT LIKE 'worker:%'
GROUP BY source_image_id ORDER BY source_image_id LIMIT :limit
"""


def summarize_capture(capture: dict[str, Any]) -> dict[str, Any]:
    """Count qualified labels, not the reader's deliberately unassigned role."""
    positions = capture["positions"]
    qualified = sum(position["label"] is not None for position in positions)
    return {
        "sourceId": capture["sourceId"],
        "sourceSha256": capture["source"]["checksum_sha256"],
        "normalizedPixelSha256": capture["source"]["normalized_pixel_checksum_sha256"],
        "captureSha256": capture["captureSha256"],
        "qualifiedHumanBoards": qualified,
        "fullyHumanAnnotated": len(positions) == 9 and qualified == 9,
        "excludedPositionReasons": dict(
            Counter(position["reason"] for position in positions if position["reason"] is not None)
        ),
        "roleEligibility": "not_evaluated",
        "screenEligible": None,
        "accessPurpose": "readiness_metadata_only",
        "usedForModelDesign": False,
    }


def read_readiness(
    engine: Engine,
    game_id: UUID,
    artifact_root: Path,
    *,
    max_sources: int = 250,
    after_source_id: UUID | None = None,
    timeout_seconds: float = 60,
) -> dict[str, Any]:
    """Read one explicit keyset budget; partial pages never claim full readiness.

    Increasing max_sources or continuing after nextSourceId is an explicit caller
    choice. A SQL/deadline failure produces no success report. No role/ledger writes
    occur, and no image is decoded. Approval manifest metadata may be verified by
    the canonical evidence reader.
    """
    if type(max_sources) is not int or max_sources < 1 or not 0 < timeout_seconds <= 120:
        raise ValueError("DIAGNOSTIC_READ_BUDGET_INVALID")
    started = datetime.now(UTC).isoformat()
    deadline = time.monotonic() + timeout_seconds
    with engine.connect() as connection, Session(bind=connection) as session:
        session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        session.execute(text("SET LOCAL lock_timeout='2s'"))

        def bounded_statement(
            conn: Any,
            cursor: Any,
            statement: str,
            parameters: Any,
            context: Any,
            executemany: bool,
        ) -> None:
            remaining = int((deadline - time.monotonic()) * 1000)
            if remaining < 1:
                raise TimeoutError("DIAGNOSTIC_READ_BUDGET_EXHAUSTED")
            cursor.execute(f"SET LOCAL statement_timeout={min(remaining, 8000)}")

        event.listen(connection, "before_cursor_execute", bounded_statement)
        try:
            GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.READ)
            rows = list(
                session.execute(
                    text(SOURCE_SELECTION),
                    {
                        "game": game_id,
                        "after": str(after_source_id) if after_source_id else None,
                        "limit": max_sources + 1,
                    },
                ).mappings()
            )
            more = len(rows) > max_sources
            selected = rows[:max_sources]
            reader = GridCohortEvidenceReader(session, artifact_root)
            sources = []
            rejected = []
            for ordinal, row in enumerate(selected):
                try:
                    capture = reader.capture(
                        game_id,
                        UUID(str(row["source_image_id"])),
                        ordinal,
                        {"role": None, "qualification": "unresolved", "reasonCodes": []},
                        "grid-only",
                    )
                except GridCohortError as error:
                    if error.code not in {
                        "SOURCE_REPLACEMENT_RETIRED",
                        "GRID_COHORT_SOURCE_REMOVED",
                    }:
                        raise
                    rejected.append(
                        {
                            "sourceId": str(row["source_image_id"]),
                            "code": error.code,
                            "nominalHumanBoards": row["nominal_boards"],
                        }
                    )
                else:
                    summary = summarize_capture(capture)
                    summary["nominalHumanBoards"] = row["nominal_boards"]
                    sources.append(summary)
                if time.monotonic() > deadline:
                    raise TimeoutError("DIAGNOSTIC_READ_BUDGET_EXHAUSTED")
            reasons: Counter[str] = Counter()
            for source in sources:
                reasons.update(source["excludedPositionReasons"])
            return {
                "schemaVersion": "grid-diagnostic-readiness-v1",
                "gameId": str(game_id),
                "startedAt": started,
                "finishedAt": datetime.now(UTC).isoformat(),
                "status": "partial" if more or after_source_id else "complete",
                "populationComplete": not more and after_source_id is None,
                "pageComplete": not more,
                "budget": {"maxSources": max_sources, "timeoutSeconds": timeout_seconds},
                "afterSourceId": str(after_source_id) if after_source_id else None,
                "nextSourceId": str(selected[-1]["source_image_id"]) if more else None,
                "selectedSourceCount": len(selected),
                "sourceCount": len(sources),
                "nominalHumanBoards": sum(row["nominal_boards"] for row in selected),
                "qualifiedHumanBoards": sum(s["qualifiedHumanBoards"] for s in sources),
                "fullyHumanAnnotatedPhotos": sum(s["fullyHumanAnnotated"] for s in sources),
                "screenEligiblePhotos": None,
                "roleEligibility": "not_evaluated",
                "excludedPositionReasons": dict(reasons),
                "sources": sources,
                "rejectedSources": rejected,
                "diagnosticUse": [],
                "ledgerModified": False,
                "limitations": [
                    "Population contains only sources with nominal current human approval; "
                    "it is not the entire image library.",
                    "Counts describe this bounded read only, not training permission.",
                    "Metadata readiness access does not constitute model-design use.",
                    "Roles, copies, buffers and ancestry have not been requalified.",
                    "Continuation pages are not a single simultaneous population snapshot.",
                ],
            }
        finally:
            event.remove(connection, "before_cursor_execute", bounded_statement)
            session.rollback()
