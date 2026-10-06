"""Game-serialized lab import receipts and lease-fenced immutable publication."""

from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from game_predictor_api.domain.jobs import (
    Job,
    JobConflictError,
    JobNotFoundError,
    JobStatus,
    JobType,
    create_job,
)
from game_predictor_api.domain.lab_symbol_candidate import LabSymbolCandidate
from game_predictor_api.domain.symbol_model_iterations import SymbolModelIteration
from game_predictor_api.storage.job_repository import job_from_record, job_record_from_domain
from game_predictor_api.storage.lab_symbol_candidate_validation import (
    require_candidate,
    require_catalog,
)
from game_predictor_api.storage.models import GameModel, JobModel, SymbolModelIterationModel
from game_predictor_api.storage.symbol_model_iteration_repository import _ACTIVE, _to_domain

LAB_IMPORT_KIND = "symbol_model_lab_import"


class SqlAlchemyLabSymbolCandidateImportRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def require_game(self, game_id: UUID) -> None:
        if self._session.get(GameModel, game_id) is None:
            raise JobNotFoundError("GAME_NOT_FOUND", "Game does not exist.")

    def require_catalog(self, candidate: LabSymbolCandidate) -> None:
        require_catalog(self._session, candidate)

    def start(
        self, *, game_id: UUID, fingerprint: str, idempotency_key: UUID, artifact_root: Path
    ) -> tuple[SymbolModelIteration, Job, bool]:
        game = self._session.scalar(
            select(GameModel).where(GameModel.id == game_id).with_for_update()
        )
        if game is None:
            raise JobNotFoundError("GAME_NOT_FOUND", "Game does not exist.")
        receipt = self._session.scalar(
            select(JobModel).where(
                JobModel.game_id == game_id,
                JobModel.job_type == JobType.VALIDATE,
                JobModel.input_payload["validation_kind"].as_string() == LAB_IMPORT_KIND,
                JobModel.input_payload["idempotency_key"].as_string() == str(idempotency_key),
            )
        )
        if receipt is not None:
            if receipt.input_payload.get("candidate_fingerprint") != fingerprint:
                raise JobConflictError(
                    "LAB_IMPORT_IDEMPOTENCY_CONFLICT", "Key belongs to another import."
                )
            iteration = self._session.scalar(
                select(SymbolModelIterationModel).where(
                    SymbolModelIterationModel.game_id == game_id,
                    SymbolModelIterationModel.job_id == receipt.id,
                )
            )
            if iteration is None:
                raise JobConflictError(
                    "LAB_IMPORT_RECEIPT_INVALID", "Import receipt has no iteration."
                )
            return _to_domain(iteration), job_from_record(receipt), False
        candidate = require_candidate(artifact_root, fingerprint, game_id)
        require_catalog(self._session, candidate)
        existing = self._session.scalar(
            select(SymbolModelIterationModel).where(
                SymbolModelIterationModel.game_id == game_id,
                SymbolModelIterationModel.origin_fingerprint == fingerprint,
            )
        )
        if existing is not None:
            # New keys cannot silently point at a different receipt.
            raise JobConflictError(
                "LAB_CANDIDATE_ALREADY_IMPORTED", "Candidate already has an import receipt."
            )
        active = self._session.scalar(
            select(SymbolModelIterationModel.id)
            .where(
                SymbolModelIterationModel.game_id == game_id,
                SymbolModelIterationModel.status.in_(_ACTIVE),
            )
            .limit(1)
        )
        if active is not None:
            raise JobConflictError(
                "SYMBOL_TRAINING_ALREADY_ACTIVE", "A model operation is active for this game."
            )
        identity = cast(dict[str, object], candidate.manifest["identity"])
        artifacts = cast(dict[str, dict[str, str]], candidate.manifest["artifacts"])
        job = create_job(
            JobType.VALIDATE,
            game_id=game_id,
            input_payload={
                "schema_version": 1,
                "validation_kind": LAB_IMPORT_KIND,
                "idempotency_key": str(idempotency_key),
                "candidate_fingerprint": fingerprint,
                "candidate_manifest_relative_path": candidate.manifest_relative_path,
                "candidate_manifest_checksum_sha256": candidate.manifest_sha256,
                "origin_manifest_relative_path": artifacts["origin"]["relativePath"],
                "origin_manifest_checksum_sha256": artifacts["origin"]["sha256"],
            },
        )
        number = (
            int(
                self._session.scalar(
                    select(
                        func.coalesce(func.max(SymbolModelIterationModel.iteration_number), 0)
                    ).where(SymbolModelIterationModel.game_id == game_id)
                )
                or 0
            )
            + 1
        )
        now = datetime.now(UTC)
        record = SymbolModelIterationModel(
            id=uuid4(),
            game_id=game_id,
            cohort_id=None,
            job_id=job.id,
            iteration_number=number,
            status="created",
            origin="lab_import",
            origin_fingerprint=fingerprint,
            origin_manifest_relative_path=artifacts["origin"]["relativePath"],
            origin_manifest_checksum_sha256=artifacts["origin"]["sha256"],
            configuration_fingerprint=fingerprint,
            configuration_payload=identity,
            last_completed_epoch=0,
            partial_metrics={},
            gate_metrics={},
            rejection_reasons=[],
            created_at=now,
            updated_at=now,
        )
        self._session.add(job_record_from_domain(job))
        self._session.add(record)
        self._session.flush()
        return _to_domain(record), job, True

    def publish(
        self,
        *,
        game_id: UUID,
        job_id: UUID,
        lease_owner: str,
        lease_token: UUID,
        artifact_root: Path,
        status: str = "candidate_ready",
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        game = self._session.scalar(
            select(GameModel.id)
            .where(GameModel.id == game_id)
            .with_for_update(read=True, key_share=True)
        )
        if game is None:
            raise JobNotFoundError("GAME_NOT_FOUND", "Game does not exist.")
        job = self._session.scalar(
            select(JobModel)
            .where(JobModel.id == job_id, JobModel.game_id == game_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        now = datetime.now(UTC)
        if (
            job is None
            or job.job_type != JobType.VALIDATE
            or job.status != JobStatus.PROCESSING
            or job.lease_owner != lease_owner
            or job.lease_token != lease_token
            or job.lease_expires_at is None
            or job.lease_expires_at <= now
            or job.cancel_requested_at is not None
            or job.input_payload.get("validation_kind") != LAB_IMPORT_KIND
        ):
            raise JobConflictError("LAB_IMPORT_LEASE_LOST", "Import lease is no longer current.")
        record = self._session.scalar(
            select(SymbolModelIterationModel)
            .where(
                SymbolModelIterationModel.job_id == job_id,
                SymbolModelIterationModel.game_id == game_id,
            )
            .with_for_update()
        )
        if (
            record is None
            or record.origin != "lab_import"
            or record.origin_fingerprint != job.input_payload.get("candidate_fingerprint")
        ):
            raise JobConflictError("LAB_IMPORT_BINDING_DRIFT", "Import iteration binding changed.")
        if status not in {"evaluating", "candidate_ready", "failed", "rejected"}:
            raise ValueError("Invalid lab import publication status.")
        if status in {"evaluating", "candidate_ready"}:
            candidate = require_candidate(artifact_root, record.origin_fingerprint or "", game_id)
            require_catalog(self._session, candidate)
            artifacts = cast(dict[str, dict[str, str]], candidate.manifest["artifacts"])
            if (
                job.input_payload.get("candidate_manifest_relative_path")
                != candidate.manifest_relative_path
                or job.input_payload.get("candidate_manifest_checksum_sha256")
                != candidate.manifest_sha256
                or record.origin_manifest_relative_path != artifacts["origin"]["relativePath"]
                or record.origin_manifest_checksum_sha256 != artifacts["origin"]["sha256"]
                or job.input_payload.get("origin_manifest_relative_path")
                != record.origin_manifest_relative_path
                or job.input_payload.get("origin_manifest_checksum_sha256")
                != record.origin_manifest_checksum_sha256
                or record.configuration_payload != candidate.manifest["identity"]
                or record.configuration_fingerprint != candidate.fingerprint
                or record.cohort_id is not None
            ):
                raise JobConflictError("LAB_IMPORT_BINDING_DRIFT", "Pinned candidate changed.")
            if status == "candidate_ready":
                record.candidate_manifest_relative_path = candidate.manifest_relative_path
                record.candidate_manifest_checksum_sha256 = candidate.manifest_sha256
                record.gate_report_relative_path = artifacts["gateReport"]["relativePath"]
                record.gate_report_checksum_sha256 = artifacts["gateReport"]["sha256"]
                record.gate_metrics = cast(dict[str, object], candidate.manifest["identity"])
        # A recovered worker may verify an already-published candidate but cannot
        # regress it to evaluating while its completion response was lost.
        if record.status != "candidate_ready":
            record.status = status
        record.error_code = error_code
        record.error_message = error_message
        record.updated_at = now
        self._session.flush()
