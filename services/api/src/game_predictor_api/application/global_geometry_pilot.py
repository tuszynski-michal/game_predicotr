"""Internal publication boundary for a validated shared-geometry G05 pilot."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from game_predictor_api.domain.global_geometry_library import (
    GlobalGeometryCandidate,
    GlobalGeometryProfileVersion,
)
from game_predictor_api.domain.global_geometry_qualification import (
    GlobalGeometryQualificationReport,
    GlobalGeometryQualificationResult,
)


class GlobalGeometryPilotRepository(Protocol):
    def create_candidate(
        self, *, candidate: GlobalGeometryCandidate, idempotency_key: UUID
    ) -> tuple[GlobalGeometryProfileVersion, bool]: ...

    def qualify_candidate(
        self,
        *,
        profile_id: UUID,
        report: GlobalGeometryQualificationReport | None,
        idempotency_key: UUID,
    ) -> tuple[GlobalGeometryQualificationResult, bool]: ...


@dataclass(frozen=True, slots=True)
class GlobalGeometryPilotPublication:
    profile: GlobalGeometryProfileVersion
    profile_created: bool
    qualification: GlobalGeometryQualificationResult
    qualification_created: bool


class GlobalGeometryPilotService:
    """Persist a prepared pilot in the existing public control plane only.

    The caller owns the public-session transaction.  This service intentionally
    has no game ID, game session, HTTP model, or import side effect.
    """

    def __init__(self, repository: GlobalGeometryPilotRepository) -> None:
        self._repository = repository

    def publish(
        self,
        *,
        candidate: GlobalGeometryCandidate,
        report: GlobalGeometryQualificationReport,
        candidate_idempotency_key: UUID,
        qualification_idempotency_key: UUID,
    ) -> GlobalGeometryPilotPublication:
        if candidate_idempotency_key == qualification_idempotency_key:
            raise ValueError("Pilot candidate and qualification idempotency keys must differ.")
        profile, profile_created = self._repository.create_candidate(
            candidate=candidate,
            idempotency_key=candidate_idempotency_key,
        )
        qualification, qualification_created = self._repository.qualify_candidate(
            profile_id=profile.id,
            report=report,
            idempotency_key=qualification_idempotency_key,
        )
        return GlobalGeometryPilotPublication(
            profile=profile,
            profile_created=profile_created,
            qualification=qualification,
            qualification_created=qualification_created,
        )


__all__ = [
    "GlobalGeometryPilotPublication",
    "GlobalGeometryPilotRepository",
    "GlobalGeometryPilotService",
]
