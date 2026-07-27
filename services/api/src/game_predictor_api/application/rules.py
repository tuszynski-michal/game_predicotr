"""Application service and repository port for rules versions."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Never, Protocol
from uuid import UUID

from game_predictor_api.domain.rules import (
    Payline,
    PayoutRule,
    RulesConflictError,
    RulesNotFoundError,
    RulesPublicationReadiness,
    RulesSymbolDefinition,
    RulesVersion,
    RulesVersionStatus,
    RulesVersionSymbol,
    assess_rules_publication,
    ensure_draft,
    validate_dimensions,
    validate_minimum_match_length,
    validate_payline_code,
    validate_payline_display_order,
    validate_payline_name,
    validate_payline_row_path,
    validate_payout_credits,
    validate_payout_match_length,
    validate_spin_cost,
)


class RulesRepository(Protocol):
    def game_exists(self, game_id: UUID) -> bool: ...

    def list_rules_versions(self, game_id: UUID) -> Sequence[RulesVersion]: ...

    def get_rules_version(self, rules_version_id: UUID) -> RulesVersion | None: ...

    def get_rules_version_for_update(
        self,
        rules_version_id: UUID,
    ) -> RulesVersion | None: ...

    def add_next_rules_version(
        self,
        *,
        game_id: UUID,
        rows: int,
        columns: int,
        spin_cost: int,
    ) -> RulesVersion | None: ...

    def save_rules_version(self, rules_version: RulesVersion) -> RulesVersion: ...

    def paylines_fit_dimensions(
        self,
        rules_version_id: UUID,
        *,
        rows: int,
        columns: int,
    ) -> bool: ...

    def list_paylines(self, rules_version_id: UUID) -> Sequence[Payline]: ...

    def get_payline(
        self,
        rules_version_id: UUID,
        payline_id: UUID,
    ) -> Payline | None: ...

    def find_payline_by_code(
        self,
        rules_version_id: UUID,
        code: str,
    ) -> Payline | None: ...

    def find_payline_by_row_path(
        self,
        rules_version_id: UUID,
        row_path: tuple[int, ...],
    ) -> Payline | None: ...

    def add_payline(
        self,
        *,
        rules_version_id: UUID,
        code: str,
        name: str,
        row_path: tuple[int, ...],
        display_order: int,
        is_active: bool,
    ) -> Payline: ...

    def save_payline(self, payline: Payline) -> Payline: ...

    def payout_configuration_fits_columns(
        self,
        rules_version_id: UUID,
        *,
        columns: int,
    ) -> bool: ...

    def get_rules_symbol_definition(
        self,
        symbol_id: UUID,
    ) -> RulesSymbolDefinition | None: ...

    def list_rules_version_symbols(
        self,
        rules_version_id: UUID,
    ) -> Sequence[RulesVersionSymbol]: ...

    def get_rules_version_symbol(
        self,
        rules_version_id: UUID,
        symbol_id: UUID,
    ) -> RulesVersionSymbol | None: ...

    def save_rules_version_symbol(
        self,
        rules_version_symbol: RulesVersionSymbol,
    ) -> RulesVersionSymbol: ...

    def archive_payout_rules_below(
        self,
        rules_version_id: UUID,
        symbol_id: UUID,
        minimum_match_length: int,
    ) -> None: ...

    def list_payout_rules(self, rules_version_id: UUID) -> Sequence[PayoutRule]: ...

    def get_payout_rule(
        self,
        rules_version_id: UUID,
        payout_rule_id: UUID,
    ) -> PayoutRule | None: ...

    def find_payout_rule(
        self,
        rules_version_id: UUID,
        symbol_id: UUID,
        match_length: int,
    ) -> PayoutRule | None: ...

    def add_payout_rule(
        self,
        *,
        rules_version_id: UUID,
        symbol_id: UUID,
        match_length: int,
        payout_credits: int,
        is_active: bool,
    ) -> PayoutRule: ...

    def save_payout_rule(self, payout_rule: PayoutRule) -> PayoutRule: ...


class RulesService:
    """Transactional rules-version use cases independent of HTTP and ORM."""

    def __init__(self, repository: RulesRepository) -> None:
        self._repository = repository

    def list_rules_versions(self, game_id: UUID) -> Sequence[RulesVersion]:
        self._ensure_game(game_id)
        return self._repository.list_rules_versions(game_id)

    def get_rules_version(self, rules_version_id: UUID) -> RulesVersion:
        rules_version = self._repository.get_rules_version(rules_version_id)
        if rules_version is None:
            raise RulesNotFoundError(
                "RULES_VERSION_NOT_FOUND",
                "Rules version does not exist.",
                details={"rulesVersionId": str(rules_version_id)},
            )
        return rules_version

    def create_rules_version(
        self,
        game_id: UUID,
        *,
        rows: int,
        columns: int,
        spin_cost: int,
    ) -> RulesVersion:
        validated_rows, validated_columns = validate_dimensions(rows, columns)
        rules_version = self._repository.add_next_rules_version(
            game_id=game_id,
            rows=validated_rows,
            columns=validated_columns,
            spin_cost=validate_spin_cost(spin_cost),
        )
        if rules_version is None:
            self._raise_game_not_found(game_id)
        return rules_version

    def update_rules_version(
        self,
        rules_version_id: UUID,
        *,
        rows: int | None = None,
        columns: int | None = None,
        spin_cost: int | None = None,
    ) -> RulesVersion:
        rules_version = self._get_locked_rules_version(rules_version_id)
        ensure_draft(rules_version)
        validated_rows, validated_columns = validate_dimensions(
            rules_version.rows if rows is None else rows,
            rules_version.columns if columns is None else columns,
        )
        if (
            validated_rows != rules_version.rows or validated_columns != rules_version.columns
        ) and not self._repository.paylines_fit_dimensions(
            rules_version_id,
            rows=validated_rows,
            columns=validated_columns,
        ):
            raise RulesConflictError(
                "RULES_DIMENSIONS_IN_USE",
                "Existing paylines are not valid for the requested dimensions.",
                details={"rulesVersionId": str(rules_version_id)},
            )
        if (
            validated_columns != rules_version.columns
            and not self._repository.payout_configuration_fits_columns(
                rules_version_id,
                columns=validated_columns,
            )
        ):
            raise RulesConflictError(
                "RULES_DIMENSIONS_IN_USE",
                "Existing symbol or payout configuration is not valid "
                "for the requested dimensions.",
                details={"rulesVersionId": str(rules_version_id)},
            )
        updated = replace(
            rules_version,
            rows=validated_rows,
            columns=validated_columns,
            spin_cost=(
                rules_version.spin_cost if spin_cost is None else validate_spin_cost(spin_cost)
            ),
        )
        return self._repository.save_rules_version(updated)

    def list_paylines(self, rules_version_id: UUID) -> Sequence[Payline]:
        self.get_rules_version(rules_version_id)
        return self._repository.list_paylines(rules_version_id)

    def get_payline(self, rules_version_id: UUID, payline_id: UUID) -> Payline:
        self.get_rules_version(rules_version_id)
        payline = self._repository.get_payline(rules_version_id, payline_id)
        if payline is None:
            raise RulesNotFoundError(
                "PAYLINE_NOT_FOUND",
                "Payline does not exist in this rules version.",
                details={
                    "rulesVersionId": str(rules_version_id),
                    "paylineId": str(payline_id),
                },
            )
        return payline

    def create_payline(
        self,
        rules_version_id: UUID,
        *,
        code: str,
        name: str,
        row_path: Sequence[int],
        display_order: int,
        is_active: bool,
    ) -> Payline:
        rules_version = self._get_locked_rules_version(rules_version_id)
        ensure_draft(rules_version)
        validated_code = validate_payline_code(code)
        validated_row_path = validate_payline_row_path(
            row_path,
            rows=rules_version.rows,
            columns=rules_version.columns,
        )
        self._ensure_unique_payline_code(rules_version_id, validated_code)
        self._ensure_unique_row_path(rules_version_id, validated_row_path)
        return self._repository.add_payline(
            rules_version_id=rules_version_id,
            code=validated_code,
            name=validate_payline_name(name),
            row_path=validated_row_path,
            display_order=validate_payline_display_order(display_order),
            is_active=is_active,
        )

    def update_payline(
        self,
        rules_version_id: UUID,
        payline_id: UUID,
        *,
        name: str | None = None,
        row_path: Sequence[int] | None = None,
        display_order: int | None = None,
        is_active: bool | None = None,
    ) -> Payline:
        rules_version = self._get_locked_rules_version(rules_version_id)
        ensure_draft(rules_version)
        payline = self.get_payline(rules_version_id, payline_id)
        validated_row_path = (
            payline.row_path
            if row_path is None
            else validate_payline_row_path(
                row_path,
                rows=rules_version.rows,
                columns=rules_version.columns,
            )
        )
        if validated_row_path != payline.row_path:
            self._ensure_unique_row_path(
                rules_version_id,
                validated_row_path,
                exclude_payline_id=payline_id,
            )
        updated = replace(
            payline,
            name=payline.name if name is None else validate_payline_name(name),
            row_path=validated_row_path,
            display_order=(
                payline.display_order
                if display_order is None
                else validate_payline_display_order(display_order)
            ),
            is_active=payline.is_active if is_active is None else is_active,
        )
        return self._repository.save_payline(updated)

    def archive_payline(
        self,
        rules_version_id: UUID,
        payline_id: UUID,
    ) -> Payline:
        return self.update_payline(
            rules_version_id,
            payline_id,
            is_active=False,
        )

    def list_rules_version_symbols(
        self,
        rules_version_id: UUID,
    ) -> Sequence[RulesVersionSymbol]:
        self.get_rules_version(rules_version_id)
        return self._repository.list_rules_version_symbols(rules_version_id)

    def update_rules_version_symbol(
        self,
        rules_version_id: UUID,
        symbol_id: UUID,
        *,
        minimum_match_length: int | None,
        is_active: bool,
    ) -> RulesVersionSymbol:
        rules_version = self._get_locked_rules_version(rules_version_id)
        ensure_draft(rules_version)
        symbol = self._get_rules_symbol_definition(rules_version, symbol_id)
        validated_minimum = validate_minimum_match_length(
            minimum_match_length,
            columns=rules_version.columns,
            is_wildcard=symbol.is_wildcard,
        )
        saved = self._repository.save_rules_version_symbol(
            RulesVersionSymbol(
                rules_version_id=rules_version_id,
                symbol_id=symbol_id,
                minimum_match_length=validated_minimum,
                is_active=is_active,
            )
        )
        if validated_minimum is not None:
            self._repository.archive_payout_rules_below(
                rules_version_id,
                symbol_id,
                validated_minimum,
            )
        return saved

    def list_payout_rules(self, rules_version_id: UUID) -> Sequence[PayoutRule]:
        self.get_rules_version(rules_version_id)
        return self._repository.list_payout_rules(rules_version_id)

    def get_payout_rule(
        self,
        rules_version_id: UUID,
        payout_rule_id: UUID,
    ) -> PayoutRule:
        self.get_rules_version(rules_version_id)
        payout_rule = self._repository.get_payout_rule(
            rules_version_id,
            payout_rule_id,
        )
        if payout_rule is None:
            raise RulesNotFoundError(
                "PAYOUT_RULE_NOT_FOUND",
                "Payout rule does not exist in this rules version.",
                details={
                    "rulesVersionId": str(rules_version_id),
                    "payoutRuleId": str(payout_rule_id),
                },
            )
        return payout_rule

    def create_payout_rule(
        self,
        rules_version_id: UUID,
        *,
        symbol_id: UUID,
        match_length: int,
        payout_credits: int,
        is_active: bool,
    ) -> PayoutRule:
        rules_version = self._get_locked_rules_version(rules_version_id)
        ensure_draft(rules_version)
        symbol = self._get_rules_symbol_definition(rules_version, symbol_id)
        configuration = self._get_rules_version_symbol(
            rules_version,
            symbol,
        )
        validated_match_length = self._validate_payout_length(
            rules_version,
            symbol,
            configuration,
            match_length,
        )
        existing = self._repository.find_payout_rule(
            rules_version_id,
            symbol_id,
            validated_match_length,
        )
        if existing is not None:
            raise RulesConflictError(
                "PAYOUT_RULE_ALREADY_EXISTS",
                "A payout rule for this symbol and matchLength already exists.",
                details={"existingPayoutRuleId": str(existing.id)},
            )
        return self._repository.add_payout_rule(
            rules_version_id=rules_version_id,
            symbol_id=symbol_id,
            match_length=validated_match_length,
            payout_credits=validate_payout_credits(payout_credits),
            is_active=is_active,
        )

    def update_payout_rule(
        self,
        rules_version_id: UUID,
        payout_rule_id: UUID,
        *,
        payout_credits: int | None = None,
        is_active: bool | None = None,
    ) -> PayoutRule:
        rules_version = self._get_locked_rules_version(rules_version_id)
        ensure_draft(rules_version)
        payout_rule = self.get_payout_rule(rules_version_id, payout_rule_id)
        if is_active is True:
            symbol = self._get_rules_symbol_definition(
                rules_version,
                payout_rule.symbol_id,
            )
            configuration = self._get_rules_version_symbol(
                rules_version,
                symbol,
            )
            self._validate_payout_length(
                rules_version,
                symbol,
                configuration,
                payout_rule.match_length,
            )
        updated = replace(
            payout_rule,
            payout_credits=(
                payout_rule.payout_credits
                if payout_credits is None
                else validate_payout_credits(payout_credits)
            ),
            is_active=payout_rule.is_active if is_active is None else is_active,
        )
        return self._repository.save_payout_rule(updated)

    def archive_payout_rule(
        self,
        rules_version_id: UUID,
        payout_rule_id: UUID,
    ) -> PayoutRule:
        return self.update_payout_rule(
            rules_version_id,
            payout_rule_id,
            is_active=False,
        )

    def get_publication_readiness(
        self,
        rules_version_id: UUID,
    ) -> RulesPublicationReadiness:
        return self._assess_publication(self.get_rules_version(rules_version_id))

    def publish_rules_version(self, rules_version_id: UUID) -> RulesVersion:
        rules_version = self._get_locked_rules_version(rules_version_id)
        ensure_draft(rules_version)
        readiness = self._assess_publication(rules_version)
        if not readiness.ready:
            raise RulesConflictError(
                "RULES_VERSION_NOT_READY",
                "Rules version has publication blockers.",
                details={
                    "rulesVersionId": str(rules_version_id),
                    "issues": [
                        {
                            "code": issue.code,
                            "message": issue.message,
                            "details": issue.details,
                        }
                        for issue in readiness.issues
                    ],
                },
            )
        return self._repository.save_rules_version(
            replace(
                rules_version,
                status=RulesVersionStatus.PUBLISHED,
                published_at=datetime.now(UTC),
            )
        )

    def archive_rules_version(self, rules_version_id: UUID) -> RulesVersion:
        rules_version = self._get_locked_rules_version(rules_version_id)
        if rules_version.status is RulesVersionStatus.ARCHIVED:
            return rules_version
        if rules_version.status is not RulesVersionStatus.PUBLISHED:
            raise RulesConflictError(
                "RULES_VERSION_NOT_PUBLISHED",
                "Only a published rules version can be archived.",
                details={"rulesVersionId": str(rules_version_id)},
            )
        return self._repository.save_rules_version(
            replace(rules_version, status=RulesVersionStatus.ARCHIVED)
        )

    def _assess_publication(
        self,
        rules_version: RulesVersion,
    ) -> RulesPublicationReadiness:
        configurations = self._repository.list_rules_version_symbols(
            rules_version.id
        )
        symbols = {
            configuration.symbol_id: symbol
            for configuration in configurations
            if (
                symbol := self._repository.get_rules_symbol_definition(
                    configuration.symbol_id
                )
            )
            is not None
        }
        return assess_rules_publication(
            rules_version,
            paylines=self._repository.list_paylines(rules_version.id),
            symbol_configurations=configurations,
            payout_rules=self._repository.list_payout_rules(rules_version.id),
            symbols=symbols,
        )

    def _get_locked_rules_version(self, rules_version_id: UUID) -> RulesVersion:
        rules_version = self._repository.get_rules_version_for_update(
            rules_version_id
        )
        if rules_version is None:
            raise RulesNotFoundError(
                "RULES_VERSION_NOT_FOUND",
                "Rules version does not exist.",
                details={"rulesVersionId": str(rules_version_id)},
            )
        return rules_version

    def _get_rules_symbol_definition(
        self,
        rules_version: RulesVersion,
        symbol_id: UUID,
    ) -> RulesSymbolDefinition:
        symbol = self._repository.get_rules_symbol_definition(symbol_id)
        if symbol is None:
            raise RulesNotFoundError(
                "SYMBOL_NOT_FOUND",
                "Symbol does not exist.",
                details={"symbolId": str(symbol_id)},
            )
        if symbol.game_id != rules_version.game_id:
            raise RulesConflictError(
                "SYMBOL_NOT_IN_RULES_GAME",
                "Symbol does not belong to the rules version game.",
                details={
                    "rulesVersionId": str(rules_version.id),
                    "symbolId": str(symbol_id),
                },
            )
        return symbol

    def _get_rules_version_symbol(
        self,
        rules_version: RulesVersion,
        symbol: RulesSymbolDefinition,
    ) -> RulesVersionSymbol:
        configuration = self._repository.get_rules_version_symbol(
            rules_version.id,
            symbol.id,
        )
        if configuration is None:
            raise RulesConflictError(
                "RULES_SYMBOL_NOT_CONFIGURED",
                "Configure the symbol minimum before adding payout rules.",
                details={
                    "rulesVersionId": str(rules_version.id),
                    "symbolId": str(symbol.id),
                },
            )
        return configuration

    @staticmethod
    def _validate_payout_length(
        rules_version: RulesVersion,
        symbol: RulesSymbolDefinition,
        configuration: RulesVersionSymbol,
        match_length: int,
    ) -> int:
        if symbol.is_wildcard or configuration.minimum_match_length is None:
            raise RulesConflictError(
                "WILDCARD_PAYOUT_NOT_ALLOWED",
                "A wildcard symbol cannot have payout rules.",
                details={"symbolId": str(symbol.id)},
            )
        return validate_payout_match_length(
            match_length,
            minimum_match_length=configuration.minimum_match_length,
            columns=rules_version.columns,
        )

    def _ensure_unique_payline_code(
        self,
        rules_version_id: UUID,
        code: str,
    ) -> None:
        existing = self._repository.find_payline_by_code(rules_version_id, code)
        if existing is not None:
            raise RulesConflictError(
                "PAYLINE_CODE_ALREADY_EXISTS",
                "A payline with this code already exists in the rules version.",
                details={"existingPaylineId": str(existing.id)},
            )

    def _ensure_unique_row_path(
        self,
        rules_version_id: UUID,
        row_path: tuple[int, ...],
        *,
        exclude_payline_id: UUID | None = None,
    ) -> None:
        existing = self._repository.find_payline_by_row_path(
            rules_version_id,
            row_path,
        )
        if existing is not None and existing.id != exclude_payline_id:
            raise RulesConflictError(
                "DUPLICATE_PAYLINE",
                "A payline with this rowPath already exists.",
                details={"existingPaylineId": str(existing.id)},
            )

    def _ensure_game(self, game_id: UUID) -> None:
        if not self._repository.game_exists(game_id):
            self._raise_game_not_found(game_id)

    @staticmethod
    def _raise_game_not_found(game_id: UUID) -> Never:
        raise RulesNotFoundError(
            "GAME_NOT_FOUND",
            "Game does not exist.",
            details={"gameId": str(game_id)},
        )
