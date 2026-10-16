"""Descriptive measurement commands, independent of geometry and symbol writers."""

from typing import Any, Protocol
from uuid import UUID


class GridQualityRepository(Protocol):
    def capture(self, game: UUID, command: dict[str, Any], actor: str) -> dict[str, Any]: ...
    def assess(
        self, game: UUID, measurement: UUID, command: dict[str, Any], actor: str
    ) -> dict[str, Any]: ...
    def get(self, game: UUID, measurement: UUID) -> dict[str, Any]: ...
    def list_measurements(self, game: UUID, cursor: UUID | None, limit: int) -> dict[str, Any]: ...


class GridQualityMeasurementService:
    def __init__(self, repository: GridQualityRepository) -> None:
        self.repository = repository

    def capture(self, game: UUID, command: dict[str, Any], actor: str) -> dict[str, Any]:
        return self.repository.capture(game, command, actor)

    def assess(
        self, game: UUID, measurement: UUID, command: dict[str, Any], actor: str
    ) -> dict[str, Any]:
        return self.repository.assess(game, measurement, command, actor)
