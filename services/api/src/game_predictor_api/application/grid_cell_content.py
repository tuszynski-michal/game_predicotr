"""Application port for independent annotations and blind source-only sessions."""

from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from game_predictor_api.schemas.grid_cell_content import (
    ContentBlindWrite,
    ContentSamplingPreview,
    ContentSessionAdvance,
    ContentSessionCreate,
    ContentWriteCommand,
)


class ContentRepository(Protocol):
    def list_targets(
        self, game: UUID, cohort: UUID, manifest: str, limit: int, offset: int
    ) -> dict[str, Any]: ...
    def target_source_asset(
        self, game: UUID, cohort: UUID, manifest: str, source: UUID
    ) -> Path: ...
    def sampling_preview(self, game: UUID, command: ContentSamplingPreview) -> dict[str, Any]: ...
    def list_sessions(self, game: UUID, limit: int = 20) -> dict[str, Any]: ...
    def get(self, game: UUID, source: UUID, position: int) -> dict[str, Any]: ...
    def get_preview(
        self, game: UUID, source: UUID, position: int, cohort: UUID, manifest: str
    ) -> dict[str, Any]: ...
    def write(self, game: UUID, command: ContentWriteCommand, actor: str) -> dict[str, Any]: ...
    def create_session(
        self, game: UUID, command: ContentSessionCreate, actor: str
    ) -> dict[str, Any]: ...
    def get_session(self, game: UUID, identifier: UUID) -> dict[str, Any]: ...
    def blind_write(
        self, game: UUID, identifier: UUID, command: ContentBlindWrite, actor: str
    ) -> dict[str, Any]: ...
    def advance(
        self, game: UUID, identifier: UUID, command: ContentSessionAdvance, actor: str
    ) -> dict[str, Any]: ...
    def source_asset(self, game: UUID, identifier: UUID, source: UUID) -> Path: ...
    def readiness(self, game: UUID, cohort: UUID, manifest: str) -> dict[str, Any]: ...


class GridCellContentService:
    def __init__(self, repository: ContentRepository) -> None:
        self.repository = repository
