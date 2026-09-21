"""Internal application boundary for shared shape-geometry qualification."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from game_predictor_api.domain.global_geometry_qualification import (
    GlobalGeometryQualificationReport,
    GlobalGeometryQualificationResult,
)


class GlobalGeometryQualificationRepository(Protocol):
    def qualify_candidate(
        self,
        *,
        profile_id: UUID,
        report: GlobalGeometryQualificationReport | None,
        idempotency_key: UUID,
    ) -> tuple[GlobalGeometryQualificationResult, bool]: ...


class GlobalGeometryQualificationService:
    """Publish only a candidate that has passed the global deterministic gate."""

    def __init__(self, repository: GlobalGeometryQualificationRepository) -> None:
        self._repository = repository

    def qualify_candidate(
        self,
        *,
        profile_id: UUID,
        report: GlobalGeometryQualificationReport | None,
        idempotency_key: UUID,
    ) -> tuple[GlobalGeometryQualificationResult, bool]:
        return self._repository.qualify_candidate(
            profile_id=profile_id,
            report=report,
            idempotency_key=idempotency_key,
        )


__all__ = [
    "GlobalGeometryQualificationRepository",
    "GlobalGeometryQualificationService",
]
