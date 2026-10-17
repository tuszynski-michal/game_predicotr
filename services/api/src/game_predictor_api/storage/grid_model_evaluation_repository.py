"""Shared evaluation reports, cohort notice watermarks and proofs (TASK-0997, D-559).

Every query reads or appends ``public`` rows that carry identities only. Per-game reads
run in a session bound to that game; catalogue reads use a plain session, so no
statement ever names two game stores.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Uuid, column, func, select, table
from sqlalchemy.orm import Session

from game_predictor_api.domain.grid_model_evaluation import proof_state
from game_predictor_api.domain.grid_model_registry import GridModelRegistryError
from game_predictor_api.storage.grid_model_registry_models import (
    GameGridModelAssignmentModel,
    GridModelCohortNoticeMarkModel,
    GridModelEvaluationCohortProofModel,
    GridModelEvaluationReportModel,
)

_LOCATIONS = table(
    "game_storage_locations",
    column("game_id", Uuid),
    column("generation"),
    column("status"),
    schema="public",
)


def notice_count(session: Session, game_id: UUID, cohort_id: UUID) -> int:
    """Committed notices of one cohort; a later notice always raises this watermark."""
    return int(
        session.scalar(
            select(func.count())
            .select_from(GridModelCohortNoticeMarkModel)
            .where(
                GridModelCohortNoticeMarkModel.game_id == game_id,
                GridModelCohortNoticeMarkModel.cohort_id == cohort_id,
            )
        )
        or 0
    )


def latest_proofs(session: Session, report_id: UUID) -> dict[tuple[str, str], dict[str, Any]]:
    rows = session.scalars(
        select(GridModelEvaluationCohortProofModel)
        .where(GridModelEvaluationCohortProofModel.report_id == report_id)
        .order_by(
            GridModelEvaluationCohortProofModel.created_at,
            GridModelEvaluationCohortProofModel.notice_count,
        )
    )
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        latest[(str(row.game_id), str(row.cohort_id))] = {
            "manifestSha256": row.manifest_sha256,
            "noticeCount": row.notice_count,
            "storageGeneration": row.storage_generation,
            "createdAt": row.created_at.isoformat() if row.created_at else None,
        }
    return latest


def storage_location(session: Session, game_id: UUID) -> dict[str, Any] | None:
    """The game's shared storage location; deletion removes it after ``deleting``."""
    row = session.execute(
        select(_LOCATIONS.c.generation, _LOCATIONS.c.status).where(_LOCATIONS.c.game_id == game_id)
    ).one_or_none()
    return None if row is None else {"generation": int(row[0]), "status": str(row[1])}


def cohort_currentness(
    session: Session, report_id: UUID, cohorts: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    locations = {
        entry["gameId"]: storage_location(session, UUID(entry["gameId"])) for entry in cohorts
    }
    counts = {
        (entry["gameId"], entry["cohortId"]): notice_count(
            session, UUID(entry["gameId"]), UUID(entry["cohortId"])
        )
        for entry in cohorts
    }
    return proof_state(cohorts, latest_proofs(session, report_id), counts, locations)


def family_games(session: Session, family_id: UUID) -> set[str]:
    """Games whose current assignment trains in this family."""
    return {
        str(game)
        for game in session.scalars(
            select(GameGridModelAssignmentModel.game_id).where(
                GameGridModelAssignmentModel.training_family_id == family_id
            )
        )
    }


def append_proof(
    session: Session,
    *,
    report_id: UUID,
    game_id: UUID,
    cohort_id: UUID,
    manifest_sha256: str,
    count: int,
    storage_generation: int,
    bind_receipt_sha256: str,
    eligibility_sha256: str,
    actor: str,
) -> None:
    session.add(
        GridModelEvaluationCohortProofModel(
            id=uuid4(),
            report_id=report_id,
            game_id=game_id,
            cohort_id=cohort_id,
            manifest_sha256=manifest_sha256,
            notice_count=count,
            storage_generation=storage_generation,
            bind_receipt_sha256=bind_receipt_sha256,
            eligibility_sha256=eligibility_sha256,
            actor=actor,
        )
    )
    session.flush()


def report(session: Session, report_id: UUID) -> GridModelEvaluationReportModel | None:
    return session.get(GridModelEvaluationReportModel, report_id, populate_existing=True)


def store_report(
    session: Session,
    *,
    report_id: UUID,
    version_id: UUID,
    producer: str,
    report_json: str,
    report_sha256: str,
) -> GridModelEvaluationReportModel:
    """Idempotent append: the same identity must carry exactly the same bytes."""
    existing = report(session, report_id)
    if existing is not None:
        if (
            existing.report_json != report_json
            or existing.report_sha256 != report_sha256
            or existing.version_id != version_id
            or existing.producer != producer
        ):
            raise GridModelRegistryError(
                "GRID_EVALUATION_REPORT_CONFLICT", "A different report already uses this identity."
            )
        return existing
    row = GridModelEvaluationReportModel(
        id=report_id,
        version_id=version_id,
        producer=producer,
        report_json=report_json,
        report_sha256=report_sha256,
    )
    session.add(row)
    session.flush()
    return row
