"""Use cases and persistence port for symbol catalog bootstrap."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from game_predictor_api.domain.catalog import (
    CatalogConflictError,
    CatalogNotFoundError,
    Symbol,
    validate_name,
)
from game_predictor_api.domain.symbol_bootstrap import (
    SymbolBootstrapCandidate,
    SymbolBootstrapDefinition,
    SymbolBootstrapObservation,
    SymbolBootstrapRun,
    SymbolBootstrapStatus,
    SymbolImageCandidate,
    SymbolImageCandidatePage,
    automatic_definitions,
    build_symbol_candidates,
    decode_symbol_candidate_cursor,
    encode_symbol_candidate_cursor,
    validate_expected_symbol_count,
    validate_manual_definitions,
)


class SymbolBootstrapRepository(Protocol):
    def game_exists(self, game_id: UUID) -> bool: ...

    def game_has_symbols(self, game_id: UUID) -> bool: ...

    def list_observations(self, game_id: UUID) -> Sequence[SymbolBootstrapObservation]: ...

    def get_latest_run(self, game_id: UUID) -> SymbolBootstrapRun | None: ...

    def get_run(self, game_id: UUID, run_id: UUID) -> SymbolBootstrapRun | None: ...

    def add_run(
        self,
        *,
        game_id: UUID,
        expected_symbol_count: int,
        source_state_sha256: str,
        status: SymbolBootstrapStatus,
        candidates: tuple[SymbolBootstrapCandidate, ...],
        created_by: str,
        created_at: datetime,
    ) -> SymbolBootstrapRun: ...

    def apply_run(
        self,
        run: SymbolBootstrapRun,
        definitions: tuple[SymbolBootstrapDefinition, ...],
        *,
        applied_at: datetime,
    ) -> SymbolBootstrapRun: ...

    def list_image_candidates(
        self,
        *,
        game_id: UUID,
        symbol_id: UUID,
        after_key: tuple[float, str, str] | None,
        limit: int,
    ) -> Sequence[SymbolImageCandidate]: ...

    def get_image_candidate(
        self, *, game_id: UUID, symbol_id: UUID, observation_id: UUID
    ) -> SymbolImageCandidate | None: ...

    def get_selected_image_candidate(
        self, *, game_id: UUID, symbol_id: UUID
    ) -> SymbolImageCandidate | None: ...

    def select_image_candidate(
        self,
        *,
        game_id: UUID,
        symbol_id: UUID,
        candidate: SymbolImageCandidate,
        name: str,
    ) -> Symbol: ...


class SymbolBootstrapService:
    def __init__(self, repository: SymbolBootstrapRepository) -> None:
        self._repository = repository

    def latest(self, game_id: UUID) -> SymbolBootstrapRun | None:
        self._require_game(game_id)
        return self._repository.get_latest_run(game_id)

    def get(self, game_id: UUID, run_id: UUID) -> SymbolBootstrapRun:
        self._require_game(game_id)
        run = self._repository.get_run(game_id, run_id)
        if run is None:
            raise CatalogNotFoundError(
                "SYMBOL_BOOTSTRAP_NOT_FOUND",
                "Symbol bootstrap run does not exist.",
                details={"bootstrapId": str(run_id)},
            )
        return run

    def start(
        self,
        game_id: UUID,
        *,
        expected_symbol_count: int,
        created_by: str,
    ) -> SymbolBootstrapRun:
        self._require_game(game_id)
        expected = validate_expected_symbol_count(expected_symbol_count)
        actor = _actor(created_by)
        source_state, candidates = build_symbol_candidates(
            tuple(self._repository.list_observations(game_id))
        )
        latest = self._repository.get_latest_run(game_id)
        if (
            latest is not None
            and latest.source_state_sha256 == source_state
            and latest.expected_symbol_count == expected
        ):
            return latest
        if self._repository.game_has_symbols(game_id):
            raise CatalogConflictError(
                "SYMBOL_BOOTSTRAP_CATALOG_NOT_EMPTY",
                "Symbol bootstrap requires an empty game catalog.",
            )
        definitions = automatic_definitions(candidates, expected)
        run = self._repository.add_run(
            game_id=game_id,
            expected_symbol_count=expected,
            source_state_sha256=source_state,
            status=(SymbolBootstrapStatus.READY if definitions else SymbolBootstrapStatus.CONFLICT),
            candidates=candidates,
            created_by=actor,
            created_at=datetime.now(UTC),
        )
        return (
            self._repository.apply_run(run, definitions, applied_at=datetime.now(UTC))
            if definitions
            else run
        )

    def resolve(
        self,
        game_id: UUID,
        run_id: UUID,
        *,
        definitions: tuple[SymbolBootstrapDefinition, ...],
    ) -> SymbolBootstrapRun:
        self._require_game(game_id)
        run = self.get(game_id, run_id)
        validated = validate_manual_definitions(
            run.candidates,
            run.expected_symbol_count,
            definitions,
        )
        if run.status is SymbolBootstrapStatus.APPLIED:
            if run.resolution == validated:
                return run
            raise CatalogConflictError(
                "SYMBOL_BOOTSTRAP_ALREADY_APPLIED",
                "The symbol bootstrap run was already applied with another resolution.",
            )
        if run.status is not SymbolBootstrapStatus.CONFLICT:
            raise CatalogConflictError(
                "SYMBOL_BOOTSTRAP_STATE_INVALID",
                "Only a conflicting bootstrap can be resolved manually.",
            )
        if self._repository.game_has_symbols(game_id):
            raise CatalogConflictError(
                "SYMBOL_BOOTSTRAP_CATALOG_NOT_EMPTY",
                "Symbol bootstrap requires an empty game catalog.",
            )
        return self._repository.apply_run(
            run,
            validated,
            applied_at=datetime.now(UTC),
        )

    def image_candidates(
        self,
        game_id: UUID,
        symbol_id: UUID,
        *,
        after_cursor: str | None,
        limit: int = 10,
    ) -> SymbolImageCandidatePage:
        self._require_game(game_id)
        if not 1 <= limit <= 10:
            raise CatalogConflictError(
                "SYMBOL_IMAGE_PAGE_INVALID",
                "Symbol image candidate limit must be between 1 and 10.",
            )
        after_key = (
            decode_symbol_candidate_cursor(after_cursor, game_id=game_id, symbol_id=symbol_id)
            if after_cursor
            else None
        )
        rows = tuple(
            self._repository.list_image_candidates(
                game_id=game_id,
                symbol_id=symbol_id,
                after_key=after_key,
                limit=limit + 1,
            )
        )
        visible = rows[:limit]
        return SymbolImageCandidatePage(
            items=visible,
            next_cursor=(
                encode_symbol_candidate_cursor(
                    game_id=game_id,
                    symbol_id=symbol_id,
                    key=visible[-1].cursor_key,
                )
                if len(rows) > limit and visible
                else None
            ),
        )

    def image_candidate(
        self, game_id: UUID, symbol_id: UUID, observation_id: UUID
    ) -> SymbolImageCandidate:
        self._require_game(game_id)
        candidate = self._repository.get_image_candidate(
            game_id=game_id,
            symbol_id=symbol_id,
            observation_id=observation_id,
        )
        if candidate is None:
            raise CatalogNotFoundError(
                "SYMBOL_IMAGE_CANDIDATE_NOT_FOUND",
                "The symbol image candidate does not exist in this symbol scope.",
            )
        return candidate

    def select_image_candidate(
        self, game_id: UUID, symbol_id: UUID, observation_id: UUID, *, name: str
    ) -> Symbol:
        candidate = self.image_candidate(game_id, symbol_id, observation_id)
        return self._repository.select_image_candidate(
            game_id=game_id,
            symbol_id=symbol_id,
            candidate=candidate,
            name=validate_name(name),
        )

    def selected_image_candidate(self, game_id: UUID, symbol_id: UUID) -> SymbolImageCandidate:
        self._require_game(game_id)
        candidate = self._repository.get_selected_image_candidate(
            game_id=game_id,
            symbol_id=symbol_id,
        )
        if candidate is None:
            raise CatalogNotFoundError(
                "SYMBOL_IMAGE_NOT_FOUND",
                "The symbol has no available reference image.",
            )
        return candidate

    def _require_game(self, game_id: UUID) -> None:
        if not self._repository.game_exists(game_id):
            raise CatalogNotFoundError(
                "GAME_NOT_FOUND",
                "Game does not exist.",
                details={"gameId": str(game_id)},
            )


def _actor(value: str) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > 200:
        raise CatalogConflictError(
            "SYMBOL_BOOTSTRAP_ACTOR_INVALID",
            "createdBy must contain 1-200 non-whitespace characters.",
        )
    return normalized


__all__ = ["SymbolBootstrapRepository", "SymbolBootstrapService"]
