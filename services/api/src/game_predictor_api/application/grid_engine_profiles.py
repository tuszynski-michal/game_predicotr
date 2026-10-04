"""Read-only listing of the grid engine profiles and the state of their models."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from game_predictor_api.domain.grid_engine_profiles import (
    GRID_ENGINE_PROFILES,
    GridEngineModelState,
    GridEngineModelVersion,
    GridEngineProfile,
)


class GridEngineModelInspector(Protocol):
    def inspect(self, version: GridEngineModelVersion) -> GridEngineModelState: ...


@dataclass(frozen=True, slots=True)
class GridEngineProfileView:
    profile: GridEngineProfile
    model: GridEngineModelState


class GridEngineProfileService:
    def __init__(
        self,
        inspector: GridEngineModelInspector,
        profiles: Sequence[GridEngineProfile] = GRID_ENGINE_PROFILES,
    ) -> None:
        self._inspector = inspector
        self._profiles = tuple(profiles)

    def list_profiles(self) -> list[GridEngineProfileView]:
        return [
            GridEngineProfileView(profile=profile, model=self._inspector.inspect(profile.current))
            for profile in self._profiles
        ]


__all__ = ["GridEngineModelInspector", "GridEngineProfileService", "GridEngineProfileView"]
