"""Application service and repository port for rules versions."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Never, Protocol
from uuid import UUID

from game_predictor_api.domain.rules import (
    Payline,
    RulesConflictError,
    RulesNotFoundError,
    RulesVersion,
    ensure_draft,
    validate_dimensions,
    validate_payline_code,
    validate_payline_display_order,
    validate_payline_name,
    validate_payline_row_path,
    validate_spin_cost,
)


class RulesRepository(Protocol):
    def game_exists(self, game_id: UUID) -> bool: ...

    def list_rules_versions(self, game_id: UUID) -> Sequence[RulesVersion]: ...

    def get_rules_version(self, rules_version_id: UUID) -> RulesVersion | None: ...

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
        rules_version = self.get_rules_version(rules_version_id)
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
        rules_version = self.get_rules_version(rules_version_id)
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
        rules_version = self.get_rules_version(rules_version_id)
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
