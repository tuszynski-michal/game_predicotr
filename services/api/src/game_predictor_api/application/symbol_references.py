"""Use cases for approved symbol reference images.

The persistence implementation is added separately.  Keeping the port here
ensures the public picker path cannot inherit the legacy bootstrap semantics.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol
from uuid import UUID

from game_predictor_api.domain.catalog import CatalogConflictError, CatalogNotFoundError, Symbol
from game_predictor_api.domain.symbol_references import (
    ApprovedSymbolReferenceCandidate,
    ApprovedSymbolReferenceCandidatePage,
    SymbolReferenceImage,
    decode_approved_symbol_reference_cursor,
    encode_approved_symbol_reference_cursor,
    validate_reference_checksum,
)

MAX_APPROVED_SYMBOL_REFERENCE_PAGE_SIZE = 20


@dataclass(frozen=True, slots=True)
class StoredSymbolReferenceAsset:
    """The immutable, content-addressed copy prepared for persistence."""

    relative_path: str
    checksum_sha256: str


class SymbolReferenceArtifactStore(Protocol):
    def copy_candidate(
        self,
        *,
        game_id: UUID,
        symbol_id: UUID,
        candidate: ApprovedSymbolReferenceCandidate,
    ) -> StoredSymbolReferenceAsset: ...


class ApprovedSymbolReferenceRepository(Protocol):
    def game_exists(self, game_id: UUID) -> bool: ...

    def list_candidates(
        self,
        *,
        game_id: UUID,
        symbol_id: UUID,
        after_key: tuple[int, int, int, str] | None,
        limit: int,
    ) -> Sequence[ApprovedSymbolReferenceCandidate]: ...

    def get_candidate(
        self, *, game_id: UUID, symbol_id: UUID, observation_id: UUID
    ) -> ApprovedSymbolReferenceCandidate | None: ...

    def get_reference(self, *, game_id: UUID, symbol_id: UUID) -> SymbolReferenceImage | None: ...

    def select_reference(
        self,
        *,
        game_id: UUID,
        symbol_id: UUID,
        candidate: ApprovedSymbolReferenceCandidate,
        expected_checksum_sha256: str,
        selected_by: str,
        image_relative_path: str,
    ) -> Symbol: ...


class ApprovedSymbolReferenceService:
    def __init__(
        self,
        repository: ApprovedSymbolReferenceRepository,
        artifact_store: SymbolReferenceArtifactStore | None = None,
    ) -> None:
        self._repository = repository
        self._artifact_store = artifact_store

    def candidates(
        self,
        game_id: UUID,
        symbol_id: UUID,
        *,
        after_cursor: str | None,
        limit: int = MAX_APPROVED_SYMBOL_REFERENCE_PAGE_SIZE,
    ) -> ApprovedSymbolReferenceCandidatePage:
        self._require_game(game_id)
        if not 1 <= limit <= MAX_APPROVED_SYMBOL_REFERENCE_PAGE_SIZE:
            raise CatalogConflictError(
                "SYMBOL_REFERENCE_PAGE_INVALID",
                "The approved symbol reference candidate limit must be between 1 and 20.",
            )
        after_key = (
            decode_approved_symbol_reference_cursor(
                after_cursor, game_id=game_id, symbol_id=symbol_id
            )
            if after_cursor
            else None
        )
        rows = tuple(
            self._repository.list_candidates(
                game_id=game_id,
                symbol_id=symbol_id,
                after_key=after_key,
                limit=limit + 1,
            )
        )
        visible = rows[:limit]
        return ApprovedSymbolReferenceCandidatePage(
            items=visible,
            next_cursor=(
                encode_approved_symbol_reference_cursor(
                    game_id=game_id,
                    symbol_id=symbol_id,
                    key=visible[-1].cursor_key,
                )
                if len(rows) > limit and visible
                else None
            ),
        )

    def candidate(
        self, game_id: UUID, symbol_id: UUID, observation_id: UUID
    ) -> ApprovedSymbolReferenceCandidate:
        self._require_game(game_id)
        candidate = self._repository.get_candidate(
            game_id=game_id,
            symbol_id=symbol_id,
            observation_id=observation_id,
        )
        if candidate is None:
            raise CatalogNotFoundError(
                "SYMBOL_REFERENCE_CANDIDATE_NOT_FOUND",
                "The approved symbol reference candidate does not exist in this symbol scope.",
            )
        return candidate

    def reference(self, game_id: UUID, symbol_id: UUID) -> SymbolReferenceImage:
        self._require_game(game_id)
        reference = self._repository.get_reference(game_id=game_id, symbol_id=symbol_id)
        if reference is None:
            raise CatalogNotFoundError(
                "SYMBOL_REFERENCE_NOT_FOUND",
                "The symbol has no human-approved reference image.",
            )
        return reference

    def select(
        self,
        game_id: UUID,
        symbol_id: UUID,
        observation_id: UUID,
        *,
        expected_checksum_sha256: str,
        selected_by: str,
    ) -> Symbol:
        checksum = validate_reference_checksum(expected_checksum_sha256)
        actor = selected_by.strip()
        if not actor or len(actor) > 200:
            raise CatalogConflictError(
                "SYMBOL_REFERENCE_ACTOR_INVALID",
                "selectedBy must contain 1-200 non-whitespace characters.",
            )
        candidate = self.candidate(game_id, symbol_id, observation_id)
        if candidate.crop_checksum_sha256 != checksum:
            raise CatalogConflictError(
                "SYMBOL_REFERENCE_CANDIDATE_STALE",
                "The selected crop changed after it was loaded. Reload approved candidates.",
            )
        if self._artifact_store is None:
            raise CatalogConflictError(
                "SYMBOL_REFERENCE_STORAGE_UNAVAILABLE",
                "The approved symbol reference store is unavailable.",
            )
        stored_asset = self._artifact_store.copy_candidate(
            game_id=game_id,
            symbol_id=symbol_id,
            candidate=candidate,
        )
        if stored_asset.checksum_sha256 != checksum:
            raise CatalogConflictError(
                "SYMBOL_REFERENCE_ASSET_CHECKSUM_MISMATCH",
                "The copied symbol reference crop checksum does not match.",
            )
        return self._repository.select_reference(
            game_id=game_id,
            symbol_id=symbol_id,
            candidate=candidate,
            expected_checksum_sha256=checksum,
            selected_by=actor,
            image_relative_path=stored_asset.relative_path,
        )

    def _require_game(self, game_id: UUID) -> None:
        if not self._repository.game_exists(game_id):
            raise CatalogNotFoundError(
                "GAME_NOT_FOUND",
                "Game does not exist.",
                details={"gameId": str(game_id)},
            )


class ManagedSymbolReferenceArtifactStore:
    """Copies reviewed crop bytes into a content-addressed managed namespace."""

    def __init__(self, artifact_root: Path) -> None:
        self._artifact_root = artifact_root.resolve()
        self._data_root = (self._artifact_root / "data").resolve()

    def copy_candidate(
        self,
        *,
        game_id: UUID,
        symbol_id: UUID,
        candidate: ApprovedSymbolReferenceCandidate,
    ) -> StoredSymbolReferenceAsset:
        source = self._resolve_source(
            candidate.crop_relative_path,
            candidate.crop_checksum_sha256,
        )
        suffix = source.suffix.lower()
        relative_path = (
            f"data/symbol-references/{game_id}/{symbol_id}/"
            f"{candidate.crop_checksum_sha256}{suffix}"
        )
        destination = self._safe_destination(relative_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            self._assert_existing_destination(destination, candidate.crop_checksum_sha256)
            return StoredSymbolReferenceAsset(relative_path, candidate.crop_checksum_sha256)

        descriptor, temporary_name = tempfile.mkstemp(dir=destination.parent, prefix=".tmp-")
        temporary = Path(temporary_name)
        try:
            with source.open("rb") as input_file, os.fdopen(descriptor, "wb") as output_file:
                digest = hashlib.sha256()
                while chunk := input_file.read(1024 * 1024):
                    digest.update(chunk)
                    output_file.write(chunk)
                output_file.flush()
                os.fsync(output_file.fileno())
            if digest.hexdigest() != candidate.crop_checksum_sha256:
                raise CatalogConflictError(
                    "SYMBOL_REFERENCE_ASSET_CHECKSUM_MISMATCH",
                    "The approved symbol reference crop changed while it was being copied.",
                )
            try:
                os.link(temporary, destination)
            except FileExistsError:
                self._assert_existing_destination(destination, candidate.crop_checksum_sha256)
        finally:
            temporary.unlink(missing_ok=True)
        return StoredSymbolReferenceAsset(relative_path, candidate.crop_checksum_sha256)

    def _resolve_source(self, relative_value: str, checksum: str) -> Path:
        relative = _safe_relative_path(relative_value)
        candidate_paths = [(self._artifact_root / Path(*relative.parts)).resolve()]
        if relative.parts[0] != "data":
            candidate_paths.append((self._data_root / Path(*relative.parts)).resolve())
        source = next(
            (
                path
                for path in candidate_paths
                if path.is_relative_to(self._data_root)
                and path.is_file()
                and not path.is_symlink()
            ),
            None,
        )
        if source is None:
            raise CatalogNotFoundError(
                "SYMBOL_REFERENCE_ASSET_NOT_FOUND",
                "The approved symbol reference crop is unavailable.",
            )
        if source.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            raise CatalogConflictError(
                "SYMBOL_REFERENCE_ASSET_TYPE_INVALID",
                "The approved symbol reference crop must be a PNG or JPEG file.",
            )
        if _sha256_file(source) != checksum:
            raise CatalogConflictError(
                "SYMBOL_REFERENCE_ASSET_CHECKSUM_MISMATCH",
                "The approved symbol reference crop checksum does not match.",
            )
        return source

    def _safe_destination(self, relative_value: str) -> Path:
        relative = _safe_relative_path(relative_value)
        destination = (self._artifact_root / Path(*relative.parts)).resolve()
        if not destination.is_relative_to(self._data_root):
            raise CatalogConflictError(
                "SYMBOL_REFERENCE_ASSET_INVALID",
                "The symbol reference destination is outside managed storage.",
            )
        current = self._artifact_root
        for part in relative.parts:
            current /= part
            if current.is_symlink():
                raise CatalogConflictError(
                    "SYMBOL_REFERENCE_ASSET_INVALID",
                    "The symbol reference destination contains a symbolic link.",
                )
        return destination

    @staticmethod
    def _assert_existing_destination(path: Path, expected_checksum: str) -> None:
        if path.is_symlink() or not path.is_file() or _sha256_file(path) != expected_checksum:
            raise CatalogConflictError(
                "SYMBOL_REFERENCE_ASSET_COLLISION",
                "An existing symbol reference asset has different content.",
            )


def _safe_relative_path(value: str) -> PurePosixPath:
    relative = PurePosixPath(value)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise CatalogConflictError(
            "SYMBOL_REFERENCE_ASSET_INVALID",
            "The approved symbol reference crop path is unsafe.",
        )
    return relative


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "ApprovedSymbolReferenceRepository",
    "ApprovedSymbolReferenceService",
    "ManagedSymbolReferenceArtifactStore",
    "MAX_APPROVED_SYMBOL_REFERENCE_PAGE_SIZE",
    "StoredSymbolReferenceAsset",
    "SymbolReferenceArtifactStore",
]
