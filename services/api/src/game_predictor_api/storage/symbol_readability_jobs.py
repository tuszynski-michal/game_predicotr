"""Synchronize quality run state with the existing durable job lifecycle."""

from sqlalchemy import text
from sqlalchemy.orm import Session

from game_predictor_api.domain.jobs import Job, JobStatus, JobType
from game_predictor_api.storage.game_storage_routing import GameStorageIntent, GameStorageRouter


def synchronize_readability_job(session: Session, job: Job, *, recovery: bool = False) -> None:
    if job.job_type is not JobType.SYMBOL_READABILITY or job.game_id is None:
        return
    GameStorageRouter().bind(session, job.game_id, intent=GameStorageIntent.WRITE)
    table = (
        "symbol_readability_models"
        if job.input_payload.get("action") == "fit"
        else "symbol_readability_runs"
    )
    if recovery:
        session.execute(
            text(
                f"UPDATE {table} SET status='created',error_code=NULL,error_message=NULL "
                "WHERE game_id=:game AND job_id=:job AND status<>'completed'"
            ),
            {"game": job.game_id, "job": job.id},
        )
    elif job.status in {JobStatus.FAILED, JobStatus.CANCELLED}:
        session.execute(
            text(
                f"UPDATE {table} SET status=:status,error_code=:code,error_message=:message "
                "WHERE game_id=:game AND job_id=:job"
            ),
            {
                "game": job.game_id,
                "job": job.id,
                "status": job.status.value,
                "code": job.error_code,
                "message": job.error_message,
            },
        )
