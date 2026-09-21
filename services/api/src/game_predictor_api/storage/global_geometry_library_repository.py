"""Public control-plane persistence for global shape-geometry candidates."""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from game_predictor_api.domain.global_geometry_library import (
    GlobalGeometryCandidate,
    GlobalGeometryEvidence,
    GlobalGeometryLibraryConflictError,
    GlobalGeometryLibraryError,
    GlobalGeometryProfileStatus,
    GlobalGeometryProfileVersion,
    GlobalGeometryProfileWithEvidence,
    GlobalGeometryTopology,
    canonicalize_global_geometry_candidate,
    freeze_global_geometry_snapshot,
    validate_global_geometry_profile_integrity,
)
from game_predictor_api.domain.global_geometry_qualification import (
    GlobalGeometryQualificationDecision,
    GlobalGeometryQualificationOutcome,
    GlobalGeometryQualificationReport,
    GlobalGeometryQualificationResult,
    evaluate_global_geometry_candidate,
    qualification_command_sha256,
    qualification_result_checksum_sha256,
    report_from_mapping,
)
from game_predictor_api.storage.models import (
    GlobalGeometryEvidenceSampleModel,
    GlobalGeometryProfileQualificationReceiptModel,
    GlobalGeometryProfileQualificationResultModel,
    GlobalGeometryProfileVersionModel,
    GlobalGeometryProfileWriteReceiptModel,
)


class SqlAlchemyGlobalGeometryLibraryRepository:
    """Store candidates without binding the session to any game data plane."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_candidate(
        self, *, candidate: GlobalGeometryCandidate, idempotency_key: UUID
    ) -> tuple[GlobalGeometryProfileVersion, bool]:
        candidate = canonicalize_global_geometry_candidate(candidate)
        command_sha256 = candidate.command_sha256()
        receipt = self._session.scalar(
            select(GlobalGeometryProfileWriteReceiptModel).where(
                GlobalGeometryProfileWriteReceiptModel.idempotency_key == idempotency_key
            )
        )
        if receipt is not None:
            if receipt.command_sha256 != command_sha256:
                raise GlobalGeometryLibraryConflictError(
                    "GLOBAL_GEOMETRY_IDEMPOTENCY_CONFLICT",
                    "The idempotency key was already used for another global geometry command.",
                )
            profile = self._session.get(GlobalGeometryProfileVersionModel, receipt.profile_id)
            if profile is None:
                raise GlobalGeometryLibraryConflictError(
                    "GLOBAL_GEOMETRY_RECEIPT_PROFILE_MISSING",
                    "The idempotency receipt references a missing global geometry profile.",
                )
            return _profile(profile), False

        profile = self._session.scalar(
            select(GlobalGeometryProfileVersionModel).where(
                GlobalGeometryProfileVersionModel.geometry_family == candidate.geometry_family,
                GlobalGeometryProfileVersionModel.profile_checksum_sha256
                == candidate.profile_checksum_sha256,
            )
        )
        created = profile is None
        try:
            if profile is None:
                profile = GlobalGeometryProfileVersionModel(
                    id=uuid4(),
                    status=GlobalGeometryProfileStatus.CANDIDATE.value,
                    geometry_family=candidate.geometry_family,
                    page_board_rows=candidate.topology.page_board_rows,
                    page_board_columns=candidate.topology.page_board_columns,
                    board_cell_rows=candidate.topology.board_cell_rows,
                    board_cell_columns=candidate.topology.board_cell_columns,
                    normalized_template=candidate.normalized_template,
                    frame_appearance=candidate.frame_appearance,
                    evidence_summary=candidate.evidence_summary,
                    profile_checksum_sha256=candidate.profile_checksum_sha256,
                )
                self._session.add(profile)
                self._session.flush()
                for evidence_number, evidence in enumerate(candidate.evidence, start=1):
                    self._session.add(
                        GlobalGeometryEvidenceSampleModel(
                            id=uuid4(),
                            profile_id=profile.id,
                            evidence_number=evidence_number,
                            source_game_ref=evidence.source_game_ref,
                            evidence_checksum_sha256=evidence.evidence_checksum_sha256,
                            evidence_payload=evidence.evidence_payload,
                        )
                    )
            self._session.add(
                GlobalGeometryProfileWriteReceiptModel(
                    id=uuid4(),
                    idempotency_key=idempotency_key,
                    command_sha256=command_sha256,
                    profile_id=profile.id,
                )
            )
            self._session.flush()
        except IntegrityError as error:
            raise GlobalGeometryLibraryConflictError(
                "GLOBAL_GEOMETRY_WRITE_CONFLICT",
                "The global geometry library changed concurrently; retry the command.",
            ) from error
        self._session.refresh(profile)
        return _profile(profile), created

    def list_profiles(
        self, *, geometry_family: str, limit: int
    ) -> tuple[GlobalGeometryProfileVersion, ...]:
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")
        rows = self._session.scalars(
            select(GlobalGeometryProfileVersionModel)
            .where(GlobalGeometryProfileVersionModel.geometry_family == geometry_family)
            .order_by(GlobalGeometryProfileVersionModel.profile_number.desc())
            .limit(limit)
        ).all()
        return tuple(_profile(row) for row in rows)

    def list_active_profiles_with_evidence(
        self, *, geometry_family: str
    ) -> tuple[GlobalGeometryProfileWithEvidence, ...]:
        """Read active profiles and evidence without a candidate-history window."""

        rows = self._session.scalars(
            select(GlobalGeometryProfileVersionModel)
            .where(
                GlobalGeometryProfileVersionModel.geometry_family == geometry_family,
                GlobalGeometryProfileVersionModel.status
                == GlobalGeometryProfileStatus.ACTIVE.value,
            )
            .order_by(GlobalGeometryProfileVersionModel.profile_number.desc())
        ).all()
        return tuple(self._profile_with_evidence(row) for row in rows)

    def qualify_candidate(
        self,
        *,
        profile_id: UUID,
        report: GlobalGeometryQualificationReport | None,
        idempotency_key: UUID,
    ) -> tuple[GlobalGeometryQualificationResult, bool]:
        """Write one immutable qualification and atomically publish only a passed candidate."""

        command_sha256 = qualification_command_sha256(profile_id=profile_id, report=report)
        existing = self._qualification_receipt_result(
            idempotency_key=idempotency_key,
            command_sha256=command_sha256,
        )
        if existing is not None:
            return existing, False

        candidate = self._session.scalar(
            select(GlobalGeometryProfileVersionModel)
            .where(GlobalGeometryProfileVersionModel.id == profile_id)
        )
        if candidate is None:
            raise GlobalGeometryLibraryConflictError(
                "GLOBAL_GEOMETRY_QUALIFICATION_CANDIDATE_NOT_FOUND",
                "The global geometry candidate does not exist.",
            )
        scoped_profiles = self._session.scalars(
            select(GlobalGeometryProfileVersionModel)
            .where(
                GlobalGeometryProfileVersionModel.geometry_family == candidate.geometry_family,
                GlobalGeometryProfileVersionModel.page_board_rows == candidate.page_board_rows,
                GlobalGeometryProfileVersionModel.page_board_columns
                == candidate.page_board_columns,
                GlobalGeometryProfileVersionModel.board_cell_rows == candidate.board_cell_rows,
                GlobalGeometryProfileVersionModel.board_cell_columns
                == candidate.board_cell_columns,
            )
            .order_by(GlobalGeometryProfileVersionModel.profile_number.asc())
            .with_for_update()
            .execution_options(populate_existing=True)
        ).all()
        candidate = next((profile for profile in scoped_profiles if profile.id == profile_id), None)
        if candidate is None:
            raise GlobalGeometryLibraryConflictError(
                "GLOBAL_GEOMETRY_QUALIFICATION_CANDIDATE_SCOPE_CONFLICT",
                "The global geometry candidate changed scope during qualification.",
            )
        existing = self._qualification_receipt_result(
            idempotency_key=idempotency_key,
            command_sha256=command_sha256,
        )
        if existing is not None:
            return existing, False
        if candidate.status != GlobalGeometryProfileStatus.CANDIDATE.value:
            raise GlobalGeometryLibraryConflictError(
                "GLOBAL_GEOMETRY_QUALIFICATION_CANDIDATE_NOT_AVAILABLE",
                "Only a current candidate profile can be qualified.",
            )
        active = [
            profile
            for profile in scoped_profiles
            if profile.status == GlobalGeometryProfileStatus.ACTIVE.value
        ]
        if len(active) > 1:
            raise GlobalGeometryLibraryConflictError(
                "GLOBAL_GEOMETRY_QUALIFICATION_ACTIVE_PROFILE_CONFLICT",
                "More than one active profile exists in the candidate scope.",
            )
        previous_active = active[0] if active else None
        stored_candidate = self._profile_with_evidence(candidate)
        previous_checksum = (
            None
            if previous_active is None
            else previous_active.profile_checksum_sha256
        )
        if previous_active is None:
            decision = evaluate_global_geometry_candidate(
                stored=stored_candidate,
                report=report,
                current_active_profile_checksum_sha256=None,
            )
        else:
            try:
                validate_global_geometry_profile_integrity(
                    self._profile_with_evidence(previous_active)
                )
            except GlobalGeometryLibraryError:
                decision = GlobalGeometryQualificationDecision(
                    GlobalGeometryQualificationOutcome.NOT_EVALUABLE,
                    ("GLOBAL_GEOMETRY_QUALIFICATION_PREVIOUS_ACTIVE_INVALID",),
                )
            else:
                decision = evaluate_global_geometry_candidate(
                    stored=stored_candidate,
                    report=report,
                    current_active_profile_checksum_sha256=previous_checksum,
                )

        if (
            decision.outcome is GlobalGeometryQualificationOutcome.PASSED
            and previous_active is not None
        ):
            # The partial unique index is immediate.  Flush the retirement first,
            # while keeping both writes in the caller's transaction.
            previous_active.status = GlobalGeometryProfileStatus.RETIRED.value
            self._flush_qualification()
            candidate.status = GlobalGeometryProfileStatus.ACTIVE.value
        elif decision.outcome is GlobalGeometryQualificationOutcome.PASSED:
            candidate.status = GlobalGeometryProfileStatus.ACTIVE.value
        elif decision.outcome is GlobalGeometryQualificationOutcome.REJECTED:
            candidate.status = GlobalGeometryProfileStatus.REJECTED.value

        result = GlobalGeometryProfileQualificationResultModel(
            id=uuid4(),
            profile_id=candidate.id,
            previous_active_profile_id=(
                None if previous_active is None else previous_active.id
            ),
            outcome=decision.outcome.value,
            reason_codes=list(decision.reason_codes),
            report_payload=None if report is None else report.as_dict(),
            qualification_checksum_sha256=qualification_result_checksum_sha256(
                profile_checksum_sha256=candidate.profile_checksum_sha256,
                previous_active_profile_checksum_sha256=previous_checksum,
                decision=decision,
                report=report,
            ),
        )
        receipt = GlobalGeometryProfileQualificationReceiptModel(
            id=uuid4(),
            idempotency_key=idempotency_key,
            command_sha256=command_sha256,
            result_id=result.id,
        )
        self._session.add(result)
        self._session.add(receipt)
        self._flush_qualification()
        self._session.refresh(result)
        return _qualification_result(
            result,
            profile_checksum_sha256=candidate.profile_checksum_sha256,
            previous_active_profile_checksum_sha256=previous_checksum,
        ), True

    def _flush_qualification(self) -> None:
        try:
            self._session.flush()
        except IntegrityError as error:
            raise GlobalGeometryLibraryConflictError(
                "GLOBAL_GEOMETRY_QUALIFICATION_WRITE_CONFLICT",
                "The global geometry qualification changed concurrently; retry the command.",
            ) from error

    def _qualification_receipt_result(
        self, *, idempotency_key: UUID, command_sha256: str
    ) -> GlobalGeometryQualificationResult | None:
        receipt = self._session.scalar(
            select(GlobalGeometryProfileQualificationReceiptModel).where(
                GlobalGeometryProfileQualificationReceiptModel.idempotency_key == idempotency_key
            )
        )
        if receipt is None:
            return None
        if receipt.command_sha256 != command_sha256:
            raise GlobalGeometryLibraryConflictError(
                "GLOBAL_GEOMETRY_QUALIFICATION_IDEMPOTENCY_CONFLICT",
                "The idempotency key was already used for another qualification command.",
            )
        result = self._session.get(GlobalGeometryProfileQualificationResultModel, receipt.result_id)
        if result is None:
            raise GlobalGeometryLibraryConflictError(
                "GLOBAL_GEOMETRY_QUALIFICATION_RECEIPT_RESULT_MISSING",
                "The qualification receipt references a missing result.",
            )
        profile = self._session.get(GlobalGeometryProfileVersionModel, result.profile_id)
        if profile is None:
            raise GlobalGeometryLibraryConflictError(
                "GLOBAL_GEOMETRY_QUALIFICATION_RESULT_PROFILE_MISSING",
                "The qualification result references a missing profile.",
            )
        previous = (
            None
            if result.previous_active_profile_id is None
            else self._session.get(
                GlobalGeometryProfileVersionModel, result.previous_active_profile_id
            )
        )
        if result.previous_active_profile_id is not None and previous is None:
            raise GlobalGeometryLibraryConflictError(
                "GLOBAL_GEOMETRY_QUALIFICATION_RESULT_PREVIOUS_PROFILE_MISSING",
                "The qualification result references a missing previous active profile.",
            )
        return _qualification_result(
            result,
            profile_checksum_sha256=profile.profile_checksum_sha256,
            previous_active_profile_checksum_sha256=(
                None if previous is None else previous.profile_checksum_sha256
            ),
        )

    def _profile_with_evidence(
        self, row: GlobalGeometryProfileVersionModel
    ) -> GlobalGeometryProfileWithEvidence:
        return GlobalGeometryProfileWithEvidence(
            profile=_profile(row),
            evidence=tuple(
                GlobalGeometryEvidence(
                    source_game_ref=evidence.source_game_ref,
                    evidence_checksum_sha256=evidence.evidence_checksum_sha256,
                    evidence_payload=freeze_global_geometry_snapshot(evidence.evidence_payload),
                )
                for evidence in self._session.scalars(
                    select(GlobalGeometryEvidenceSampleModel)
                    .where(GlobalGeometryEvidenceSampleModel.profile_id == row.id)
                    .order_by(GlobalGeometryEvidenceSampleModel.evidence_number.asc())
                ).all()
            ),
        )


def _profile(model: GlobalGeometryProfileVersionModel) -> GlobalGeometryProfileVersion:
    return GlobalGeometryProfileVersion(
        id=model.id,
        profile_number=model.profile_number,
        status=GlobalGeometryProfileStatus(model.status),
        geometry_family=model.geometry_family,
        topology=GlobalGeometryTopology(
            page_board_rows=model.page_board_rows,
            page_board_columns=model.page_board_columns,
            board_cell_rows=model.board_cell_rows,
            board_cell_columns=model.board_cell_columns,
        ),
        normalized_template=freeze_global_geometry_snapshot(model.normalized_template),
        frame_appearance=freeze_global_geometry_snapshot(model.frame_appearance),
        evidence_summary=freeze_global_geometry_snapshot(model.evidence_summary),
        profile_checksum_sha256=model.profile_checksum_sha256,
        created_at=model.created_at,
    )


def _qualification_result(
    model: GlobalGeometryProfileQualificationResultModel,
    *,
    profile_checksum_sha256: str,
    previous_active_profile_checksum_sha256: str | None,
) -> GlobalGeometryQualificationResult:
    try:
        outcome = GlobalGeometryQualificationOutcome(model.outcome)
        reason_codes = tuple(model.reason_codes)
        if not all(isinstance(code, str) for code in reason_codes):
            raise ValueError("reason codes must be text")
        report = (
            None
            if model.report_payload is None
            else report_from_mapping(dict(model.report_payload))
        )
        decision = GlobalGeometryQualificationDecision(outcome, reason_codes)
        if model.qualification_checksum_sha256 != qualification_result_checksum_sha256(
            profile_checksum_sha256=profile_checksum_sha256,
            previous_active_profile_checksum_sha256=previous_active_profile_checksum_sha256,
            decision=decision,
            report=report,
        ):
            raise ValueError("qualification result checksum differs from its stored payload")
    except (GlobalGeometryLibraryError, ValueError) as error:
        raise GlobalGeometryLibraryConflictError(
            "GLOBAL_GEOMETRY_QUALIFICATION_RESULT_INVALID",
            "A stored global geometry qualification result is invalid.",
        ) from error
    return GlobalGeometryQualificationResult(
        id=model.id,
        profile_id=model.profile_id,
        previous_active_profile_id=model.previous_active_profile_id,
        outcome=outcome,
        reason_codes=reason_codes,
        report=report,
        qualification_checksum_sha256=model.qualification_checksum_sha256,
        created_at=model.created_at,
    )
