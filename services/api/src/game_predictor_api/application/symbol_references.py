"""Use cases for approved symbol reference images.

The persistence implementation is added separately.  Keeping the port here
ensures the public picker path cannot inherit the legacy bootstrap semantics.
"""

from __future__ import annotations

from collections.abc import Sequence
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
    ) -> Symbol: ...


class ApprovedSymbolReferenceService:
    def __init__(self, repository: ApprovedSymbolReferenceRepository) -> None:
        self._repository = repository

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
        return self._repository.select_reference(
            game_id=game_id,
            symbol_id=symbol_id,
            candidate=candidate,
            expected_checksum_sha256=checksum,
            selected_by=actor,
        )

    def _require_game(self, game_id: UUID) -> None:
        if not self._repository.game_exists(game_id):
            raise CatalogNotFoundError(
                "GAME_NOT_FOUND",
                "Game does not exist.",
                details={"gameId": str(game_id)},
            )


__all__ = [
    "ApprovedSymbolReferenceRepository",
    "ApprovedSymbolReferenceService",
    "MAX_APPROVED_SYMBOL_REFERENCE_PAGE_SIZE",
]
