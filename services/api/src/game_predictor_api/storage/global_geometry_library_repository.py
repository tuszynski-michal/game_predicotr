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
    GlobalGeometryProfileStatus,
    GlobalGeometryProfileVersion,
    GlobalGeometryProfileWithEvidence,
    GlobalGeometryTopology,
    canonicalize_global_geometry_candidate,
    freeze_global_geometry_snapshot,
)
from game_predictor_api.storage.models import (
    GlobalGeometryEvidenceSampleModel,
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
        return tuple(
            GlobalGeometryProfileWithEvidence(
                profile=_profile(row),
                evidence=tuple(
                    GlobalGeometryEvidence(
                        source_game_ref=evidence.source_game_ref,
                        evidence_checksum_sha256=evidence.evidence_checksum_sha256,
                        evidence_payload=freeze_global_geometry_snapshot(
                            evidence.evidence_payload
                        ),
                    )
                    for evidence in self._session.scalars(
                        select(GlobalGeometryEvidenceSampleModel)
                        .where(GlobalGeometryEvidenceSampleModel.profile_id == row.id)
                        .order_by(GlobalGeometryEvidenceSampleModel.evidence_number.asc())
                    ).all()
                ),
            )
            for row in rows
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
