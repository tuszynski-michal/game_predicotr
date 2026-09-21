"""Read-only readiness projection for the game catalog's shared geometry choice."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from game_predictor_api.application.catalog import shape_geometry_clarification_readiness
from game_predictor_api.domain.catalog import (
    GameShapeGeometryConfiguration,
    ShapeGeometryReadiness,
    ShapeGeometryReadinessStatus,
    SharedShapeGeometryProfileReference,
)
from game_predictor_api.domain.global_geometry_library import (
    SUPPORTED_GEOMETRY_FAMILY,
    GlobalGeometryLibraryError,
    GlobalGeometryProfileStatus,
    GlobalGeometryProfileWithEvidence,
    validate_global_geometry_profile_integrity,
)


class GlobalGeometryReadinessReader(Protocol):
    def list_active_profiles_with_evidence(
        self, *, geometry_family: str
    ) -> Sequence[GlobalGeometryProfileWithEvidence]: ...


class GlobalShapeGeometryReadinessResolver:
    """Expose the only active shared profile without turning readiness into import approval."""

    def __init__(self, repository: GlobalGeometryReadinessReader) -> None:
        self._repository = repository

    def resolve(
        self, configuration: GameShapeGeometryConfiguration | None
    ) -> ShapeGeometryReadiness:
        if configuration is not GameShapeGeometryConfiguration.FRAMED_FULL_PAGE_V2:
            return shape_geometry_clarification_readiness(configuration)
        try:
            profiles = tuple(
                stored
                for stored in self._repository.list_active_profiles_with_evidence(
                    geometry_family=SUPPORTED_GEOMETRY_FAMILY
                )
                if stored.profile.status is GlobalGeometryProfileStatus.ACTIVE
            )
        except GlobalGeometryLibraryError:
            return _manual_review(
                configuration,
                "SHAPE_GEOMETRY_V2_ACTIVE_PROFILE_INVALID",
                "Aktywny wspólny profil geometrii jest niepoprawny i wymaga "
                "weryfikacji przed importem.",
            )
        if not profiles:
            return _manual_review(
                configuration,
                "SHAPE_GEOMETRY_V2_ACTIVE_PROFILE_REQUIRED",
                "Brak aktywnego wspólnego profilu geometrii; pierwszy import wymaga "
                "ręcznej korekty.",
            )
        if len(profiles) != 1:
            return _manual_review(
                configuration,
                "SHAPE_GEOMETRY_V2_ACTIVE_PROFILE_CONFLICT",
                "Wspólny profil geometrii ma konflikt wersji i wymaga weryfikacji przed importem.",
            )
        try:
            validate_global_geometry_profile_integrity(profiles[0])
        except GlobalGeometryLibraryError:
            return _manual_review(
                configuration,
                "SHAPE_GEOMETRY_V2_ACTIVE_PROFILE_INVALID",
                "Aktywny wspólny profil geometrii jest niepoprawny i wymaga "
                "weryfikacji przed importem.",
            )
        profile = profiles[0].profile
        return ShapeGeometryReadiness(
            configuration=configuration,
            status=ShapeGeometryReadinessStatus.READY_FOR_SHARED_PREFLIGHT,
            reason_code="SHAPE_GEOMETRY_V2_SHARED_PROFILE_READY",
            message=(
                "Wspólny profil geometrii jest gotowy do preflightu wymagającego "
                "ręcznego potwierdzenia."
            ),
            shared_profile=SharedShapeGeometryProfileReference(
                profile_id=profile.id,
                profile_number=profile.profile_number,
                profile_checksum_sha256=profile.profile_checksum_sha256,
            ),
        )


def _manual_review(
    configuration: GameShapeGeometryConfiguration,
    reason_code: str,
    message: str,
) -> ShapeGeometryReadiness:
    return ShapeGeometryReadiness(
        configuration=configuration,
        status=ShapeGeometryReadinessStatus.MANUAL_REVIEW_REQUIRED,
        reason_code=reason_code,
        message=message,
    )


__all__ = ["GlobalShapeGeometryReadinessResolver"]
