"""Application service and repository port for the game catalog."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Protocol
from uuid import UUID

from game_predictor_api.domain.catalog import (
    DEFAULT_EXPECTED_LAYOUT_COUNT,
    NO_SUPER_GAME,
    CatalogConflictError,
    CatalogNotFoundError,
    Game,
    GameShapeGeometryConfiguration,
    GameStatus,
    ShapeGeometryReadiness,
    ShapeGeometryReadinessStatus,
    Symbol,
    SymbolStatus,
    SymbolUsageSummary,
    ensure_super_game_kind_allows_trigger,
    uses_framed_full_page_geometry,
    validate_display_order,
    validate_expected_layout_count,
    validate_image_path,
    validate_mobile_code,
    validate_name,
    validate_optional_name,
    validate_shape_geometry_configuration,
    validate_stable_code,
    validate_super_game_kind,
    validate_super_game_trigger_count,
)


class CatalogRepository(Protocol):
    def list_games(self) -> Sequence[Game]: ...

    def get_game(self, game_id: UUID) -> Game | None: ...

    def add_game(
        self,
        *,
        code: str,
        name: str,
        status: GameStatus,
        expected_layout_count: int,
        shape_geometry_configuration: GameShapeGeometryConfiguration,
        super_game_kind: str = NO_SUPER_GAME,
    ) -> Game: ...

    def save_game(self, game: Game) -> Game: ...

    def list_symbols(self, game_id: UUID) -> Sequence[Symbol]: ...

    def get_symbol(self, game_id: UUID, symbol_id: UUID) -> Symbol | None: ...

    def add_symbol(
        self,
        *,
        game_id: UUID,
        mobile_code: int,
        code: str,
        name: str,
        name_pl: str | None,
        name_en: str | None,
        image_path: str | None,
        is_wildcard: bool,
        display_order: int,
        status: SymbolStatus,
        super_game_trigger_count: int | None = None,
    ) -> Symbol: ...

    def save_symbol(self, symbol: Symbol) -> Symbol: ...

    def symbol_is_used_in_published_rules(self, symbol_id: UUID) -> bool:
        """Whether a published or archived rules version references the symbol."""
        ...

    def clear_draft_rule_minimums(self, symbol_id: UUID) -> None:
        """Set ``minimum_match_length = null`` in every draft rules version of the symbol."""
        ...

    def game_has_super_game_trigger_symbols(self, game_id: UUID) -> bool: ...

    def add_manual_symbol(
        self,
        *,
        game_id: UUID,
        name: str,
        is_wildcard: bool,
        super_game_trigger_count: int | None = None,
    ) -> Symbol: ...

    def symbol_usage_summary(
        self, *, game_id: UUID, symbol_id: UUID
    ) -> SymbolUsageSummary | None: ...

    def delete_unused_symbol(self, *, game_id: UUID, symbol_id: UUID) -> None: ...


class ShapeGeometryReadinessResolver(Protocol):
    def resolve(
        self, configuration: GameShapeGeometryConfiguration | None
    ) -> ShapeGeometryReadiness: ...


class DefaultShapeGeometryReadinessResolver:
    """Safe default used by focused catalog tests and deployments without G06."""

    def resolve(
        self, configuration: GameShapeGeometryConfiguration | None
    ) -> ShapeGeometryReadiness:
        if configuration is not None and uses_framed_full_page_geometry(configuration):
            return ShapeGeometryReadiness(
                configuration=configuration,
                status=ShapeGeometryReadinessStatus.MANUAL_REVIEW_REQUIRED,
                reason_code="SHAPE_GEOMETRY_V2_ACTIVE_PROFILE_REQUIRED",
                message=(
                    "Brak aktywnego wspólnego profilu geometrii; pierwszy import wymaga "
                    "ręcznej korekty."
                ),
            )
        return shape_geometry_clarification_readiness(configuration)


def shape_geometry_clarification_readiness(
    configuration: GameShapeGeometryConfiguration | None,
) -> ShapeGeometryReadiness:
    if configuration is None:
        return ShapeGeometryReadiness(
            configuration=GameShapeGeometryConfiguration.REQUIRES_CLARIFICATION,
            status=ShapeGeometryReadinessStatus.REQUIRES_CLARIFICATION,
            reason_code="SHAPE_GEOMETRY_CONFIGURATION_REQUIRED",
            message="Ustal format strony przed użyciem wspólnej geometrii.",
        )
    return ShapeGeometryReadiness(
        configuration=configuration,
        status=ShapeGeometryReadinessStatus.REQUIRES_CLARIFICATION,
        reason_code="SHAPE_GEOMETRY_FORMAT_REQUIRES_CLARIFICATION",
        message="Ten format strony wymaga doprecyzowania przed użyciem wspólnej geometrii.",
    )


class CatalogService:
    """Transactional use cases independent of HTTP and SQLAlchemy."""

    def __init__(
        self,
        repository: CatalogRepository,
        shape_geometry_readiness_resolver: ShapeGeometryReadinessResolver | None = None,
    ) -> None:
        self._repository = repository
        self._shape_geometry_readiness_resolver = (
            shape_geometry_readiness_resolver or DefaultShapeGeometryReadinessResolver()
        )

    def list_games(self) -> Sequence[Game]:
        return self._repository.list_games()

    def get_game(self, game_id: UUID) -> Game:
        game = self._repository.get_game(game_id)
        if game is None:
            raise CatalogNotFoundError(
                "GAME_NOT_FOUND",
                "Game does not exist.",
                details={"gameId": str(game_id)},
            )
        return game

    def shape_geometry_readiness(self, game: Game) -> ShapeGeometryReadiness:
        return self._shape_geometry_readiness_resolver.resolve(game.shape_geometry_configuration)

    def create_game(
        self,
        *,
        code: str,
        name: str,
        status: GameStatus,
        expected_layout_count: int = DEFAULT_EXPECTED_LAYOUT_COUNT,
        shape_geometry_configuration: GameShapeGeometryConfiguration = (
            GameShapeGeometryConfiguration.REQUIRES_CLARIFICATION
        ),
        super_game_kind: str = NO_SUPER_GAME,
    ) -> Game:
        return self._repository.add_game(
            code=validate_stable_code(code, field_name="code"),
            name=validate_name(name),
            status=status,
            expected_layout_count=validate_expected_layout_count(expected_layout_count),
            shape_geometry_configuration=validate_shape_geometry_configuration(
                shape_geometry_configuration
            ),
            super_game_kind=validate_super_game_kind(super_game_kind),
        )

    def update_game(
        self,
        game_id: UUID,
        *,
        name: str | None = None,
        status: GameStatus | None = None,
        expected_layout_count: int | None = None,
        shape_geometry_configuration: GameShapeGeometryConfiguration | None = None,
        super_game_kind: str | None = None,
    ) -> Game:
        game = self.get_game(game_id)
        validated_kind = (
            game.super_game_kind
            if super_game_kind is None
            else validate_super_game_kind(super_game_kind)
        )
        if (
            validated_kind == NO_SUPER_GAME
            and game.super_game_kind != NO_SUPER_GAME
            and self._repository.game_has_super_game_trigger_symbols(game_id)
        ):
            raise CatalogConflictError(
                "SUPER_GAME_KIND_IN_USE",
                "Remove the super game trigger role from every symbol before "
                "setting the super game kind to none.",
                details={"gameId": str(game_id), "field": "superGameKind"},
            )
        updated = replace(
            game,
            name=game.name if name is None else validate_name(name),
            status=game.status if status is None else status,
            expected_layout_count=(
                game.expected_layout_count
                if expected_layout_count is None
                else validate_expected_layout_count(expected_layout_count)
            ),
            shape_geometry_configuration=(
                game.shape_geometry_configuration
                if shape_geometry_configuration is None
                else validate_shape_geometry_configuration(shape_geometry_configuration)
            ),
            super_game_kind=validated_kind,
        )
        return self._repository.save_game(updated)

    def archive_game(self, game_id: UUID) -> Game:
        return self.update_game(game_id, status=GameStatus.ARCHIVED)

    def list_symbols(self, game_id: UUID) -> Sequence[Symbol]:
        self.get_game(game_id)
        return self._repository.list_symbols(game_id)

    def get_symbol(self, game_id: UUID, symbol_id: UUID) -> Symbol:
        self.get_game(game_id)
        symbol = self._repository.get_symbol(game_id, symbol_id)
        if symbol is None:
            raise CatalogNotFoundError(
                "SYMBOL_NOT_FOUND",
                "Symbol does not exist in this game.",
                details={"gameId": str(game_id), "symbolId": str(symbol_id)},
            )
        return symbol

    def create_symbol(
        self,
        game_id: UUID,
        *,
        mobile_code: int,
        code: str,
        name: str,
        image_path: str | None,
        is_wildcard: bool,
        display_order: int,
        status: SymbolStatus,
        name_pl: str | None = None,
        name_en: str | None = None,
        super_game_trigger_count: int | None = None,
    ) -> Symbol:
        game = self.get_game(game_id)
        ensure_super_game_kind_allows_trigger(game, super_game_trigger_count)
        return self._repository.add_symbol(
            game_id=game_id,
            mobile_code=validate_mobile_code(mobile_code),
            code=validate_stable_code(code, field_name="code"),
            name=validate_name(name),
            name_pl=validate_optional_name(name_pl, field_name="namePl"),
            name_en=validate_optional_name(name_en, field_name="nameEn"),
            image_path=validate_image_path(image_path),
            is_wildcard=is_wildcard,
            display_order=validate_display_order(display_order),
            status=status,
            super_game_trigger_count=validate_super_game_trigger_count(super_game_trigger_count),
        )

    def create_manual_symbol(
        self,
        game_id: UUID,
        *,
        name: str,
        is_wildcard: bool,
        super_game_trigger_count: int | None = None,
    ) -> Symbol:
        game = self.get_game(game_id)
        ensure_super_game_kind_allows_trigger(game, super_game_trigger_count)
        return self._repository.add_manual_symbol(
            game_id=game_id,
            name=validate_name(name),
            is_wildcard=is_wildcard,
            super_game_trigger_count=validate_super_game_trigger_count(super_game_trigger_count),
        )

    def update_symbol(
        self,
        game_id: UUID,
        symbol_id: UUID,
        *,
        name: str | None = None,
        name_pl: str | None = None,
        update_name_pl: bool = False,
        name_en: str | None = None,
        update_name_en: bool = False,
        image_path: str | None = None,
        update_image_path: bool = False,
        is_wildcard: bool | None = None,
        super_game_trigger_count: int | None = None,
        update_super_game_trigger_count: bool = False,
        display_order: int | None = None,
        status: SymbolStatus | None = None,
    ) -> Symbol:
        # Order (TASK-0931): the game and symbol exist -> the game's super game
        # kind -> published rules versions -> field values. A failure saves nothing.
        game = self.get_game(game_id)
        symbol = self.get_symbol(game_id, symbol_id)
        next_trigger_count = (
            super_game_trigger_count
            if update_super_game_trigger_count
            else symbol.super_game_trigger_count
        )
        if update_super_game_trigger_count:
            ensure_super_game_kind_allows_trigger(game, next_trigger_count)
        next_is_wildcard = symbol.is_wildcard if is_wildcard is None else is_wildcard
        role_changed = (
            next_is_wildcard != symbol.is_wildcard
            or next_trigger_count != symbol.super_game_trigger_count
        )
        if role_changed and self._repository.symbol_is_used_in_published_rules(symbol_id):
            raise CatalogConflictError(
                "SYMBOL_RULES_IDENTITY_IN_USE",
                "Symbol roles (Wild, super game trigger) cannot change after the symbol "
                "is used in a published rules version.",
                details={"symbolId": str(symbol_id)},
            )
        updated = replace(
            symbol,
            name=symbol.name if name is None else validate_name(name),
            name_pl=(
                symbol.name_pl
                if not update_name_pl
                else validate_optional_name(name_pl, field_name="namePl")
            ),
            name_en=(
                symbol.name_en
                if not update_name_en
                else validate_optional_name(name_en, field_name="nameEn")
            ),
            image_path=(
                symbol.image_path if not update_image_path else validate_image_path(image_path)
            ),
            is_wildcard=next_is_wildcard,
            super_game_trigger_count=validate_super_game_trigger_count(next_trigger_count),
            display_order=(
                symbol.display_order
                if display_order is None
                else validate_display_order(display_order)
            ),
            status=symbol.status if status is None else status,
        )
        saved = self._repository.save_symbol(updated)
        if role_changed and (saved.is_wildcard or saved.super_game_trigger_count is not None):
            # A Wild or trigger symbol has no line minimum (D-535). Draft rules
            # versions follow the new role in the same transaction; payout rules
            # stay untouched and publication readiness reports any leftover.
            self._repository.clear_draft_rule_minimums(symbol_id)
        return saved

    def archive_symbol(self, game_id: UUID, symbol_id: UUID) -> Symbol:
        return self.update_symbol(
            game_id,
            symbol_id,
            status=SymbolStatus.ARCHIVED,
        )

    def delete_symbol(self, game_id: UUID, symbol_id: UUID) -> None:
        self.get_game(game_id)
        usage = self._repository.symbol_usage_summary(game_id=game_id, symbol_id=symbol_id)
        if usage is None:
            raise CatalogNotFoundError(
                "SYMBOL_NOT_FOUND",
                "Symbol does not exist in this game.",
                details={"gameId": str(game_id), "symbolId": str(symbol_id)},
            )
        if not usage.is_unused:
            raise CatalogConflictError(
                "SYMBOL_DELETE_BLOCKED",
                "The symbol is still referenced and cannot be deleted.",
                details=usage.as_details(),
            )
        self._repository.delete_unused_symbol(game_id=game_id, symbol_id=symbol_id)
