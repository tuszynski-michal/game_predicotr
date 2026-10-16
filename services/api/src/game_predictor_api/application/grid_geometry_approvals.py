"""Explicit canonical approval, separate from descriptive measurement verdicts."""

from typing import Any, Protocol
from uuid import UUID


class GeometryApprovalRepository(Protocol):
    def approve(
        self, game: UUID, job: UUID, review: UUID, command: dict[str, Any], actor: str
    ) -> dict[str, Any]: ...


class GridGeometryApprovalService:
    def __init__(self, repository: GeometryApprovalRepository) -> None:
        self.repository = repository

    def approve(
        self, game: UUID, job: UUID, review: UUID, command: dict[str, Any], actor: str
    ) -> dict[str, Any]:
        return self.repository.approve(game, job, review, command, actor)
