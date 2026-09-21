"""Resolve the one active shared shape-geometry profile for new preflights."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from game_predictor_worker.images.shape_geometry_v2.preflight import (
    build_shape_geometry_v2_preflight_profile,
)

from game_predictor_api.domain.global_geometry_library import (
    SUPPORTED_GEOMETRY_FAMILY,
    GlobalGeometryLibraryError,
    GlobalGeometryProfileStatus,
    GlobalGeometryProfileWithEvidence,
    validate_global_geometry_profile_integrity,
)
from game_predictor_api.domain.jobs import JobConflictError


class GlobalGeometryProfileReader(Protocol):
    def list_active_profiles_with_evidence(
        self, *, geometry_family: str
    ) -> Sequence[GlobalGeometryProfileWithEvidence]: ...


class SqlAlchemyGlobalGeometryProfileSnapshotResolver:
    """Expose only a single compatible active profile as an immutable job input."""

    def __init__(self, repository: GlobalGeometryProfileReader) -> None:
        self._repository = repository

    def resolve(self) -> dict[str, object] | None:
        profiles = self._repository.list_active_profiles_with_evidence(
            geometry_family=SUPPORTED_GEOMETRY_FAMILY
        )
        active = tuple(
            stored
            for stored in profiles
            if stored.profile.status is GlobalGeometryProfileStatus.ACTIVE
        )
        if not active:
            return None
        if len(active) != 1:
            raise JobConflictError(
                "SHAPE_GEOMETRY_V2_ACTIVE_PROFILE_CONFLICT",
                "More than one active shared shape-geometry profile is available.",
            )
        try:
            validate_global_geometry_profile_integrity(active[0])
            return build_shape_geometry_v2_preflight_profile(active[0].profile)
        except (GlobalGeometryLibraryError, ValueError) as error:
            raise JobConflictError(
                "SHAPE_GEOMETRY_V2_ACTIVE_PROFILE_INVALID",
                "The active shared shape-geometry profile cannot be pinned to a preflight.",
            ) from error


__all__ = ["GlobalGeometryProfileReader", "SqlAlchemyGlobalGeometryProfileSnapshotResolver"]
