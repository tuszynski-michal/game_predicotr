"""Validation-only registration of already-qualified immutable lab candidates."""

from pathlib import Path
from typing import TypedDict
from uuid import UUID

from game_predictor_api.domain.jobs import Job, JobConflictError
from game_predictor_api.storage.lab_symbol_candidate_import_repository import (
    SqlAlchemyLabSymbolCandidateImportRepository,
)
from sqlalchemy.orm import Session, sessionmaker

from game_predictor_worker.jobs.runtime import JobExecutionContext, JobHandlerError


class _PublicationArguments(TypedDict):
    game_id: UUID
    job_id: UUID
    lease_owner: str
    lease_token: UUID
    artifact_root: Path


class LabSymbolCandidateImportHandler:
    def __init__(self, sessions: sessionmaker[Session], artifact_root: Path) -> None:
        self._sessions = sessions
        self._root = artifact_root.absolute()

    def __call__(self, context: JobExecutionContext, job: Job) -> None:
        if job.game_id is None or job.lease_owner is None:
            raise JobHandlerError(
                "LAB_IMPORT_INPUT_INVALID", "Import requires a game and worker lease."
            )
        context.checkpoint(
            checkpoint_payload={"schema_version": 1, "workflow": "symbol_model_lab_import"},
            stage="lab_candidate_validation",
            current=0,
            total=1,
            success_count=0,
            failure_count=0,
            review_count=0,
        )
        arguments: _PublicationArguments = dict(
            game_id=job.game_id,
            job_id=job.id,
            lease_owner=job.lease_owner,
            lease_token=context.lease_token,
            artifact_root=self._root,
        )
        try:
            with self._sessions.begin() as session:
                SqlAlchemyLabSymbolCandidateImportRepository(session).publish(
                    **arguments,
                    status="evaluating",
                )
            context.heartbeat()
            with self._sessions.begin() as session:
                SqlAlchemyLabSymbolCandidateImportRepository(session).publish(**arguments)
        except JobConflictError as error:
            if error.code != "LAB_IMPORT_LEASE_LOST":
                with self._sessions.begin() as session:
                    SqlAlchemyLabSymbolCandidateImportRepository(session).publish(
                        **arguments,
                        status="failed",
                        error_code=error.code,
                        error_message=str(error),
                    )
            raise JobHandlerError(error.code, str(error)) from error
        context.checkpoint(
            checkpoint_payload={
                "schema_version": 1,
                "workflow": "symbol_model_lab_import",
                "candidateReady": True,
            },
            stage="lab_candidate_ready",
            current=1,
            total=1,
            success_count=1,
            failure_count=0,
            review_count=0,
        )
