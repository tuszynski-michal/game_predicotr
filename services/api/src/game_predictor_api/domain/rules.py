"""Framework-independent rules-version domain."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final
from uuid import UUID

MAX_SPIN_COST = 2_147_483_647
MAX_DISPLAY_ORDER = 2_147_483_647
_PAYLINE_CODE_PATTERN: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class RulesVersionStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class RulesError(ValueError):
    """Stable rules failure translated by the HTTP boundary."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class RulesNotFoundError(RulesError):
    """Requested game or rules version does not exist."""


class RulesConflictError(RulesError):
    """Rules state or uniqueness prevents the requested operation."""


@dataclass(frozen=True, slots=True)
class RulesVersion:
    id: UUID
    game_id: UUID
    version: int
    rows: int
    columns: int
    spin_cost: int
    status: RulesVersionStatus
    created_at: datetime
    published_at: datetime | None


@dataclass(frozen=True, slots=True)
class Payline:
    id: UUID
    rules_version_id: UUID
    code: str
    name: str
    row_path: tuple[int, ...]
    display_order: int
    is_active: bool


@dataclass(frozen=True, slots=True)
class RulesSymbolDefinition:
    id: UUID
    game_id: UUID
    is_wildcard: bool


@dataclass(frozen=True, slots=True)
class RulesVersionSymbol:
    rules_version_id: UUID
    symbol_id: UUID
    minimum_match_length: int | None
    is_active: bool


@dataclass(frozen=True, slots=True)
class PayoutRule:
    id: UUID
    rules_version_id: UUID
    symbol_id: UUID
    match_length: int
    payout_credits: int
    is_active: bool


def validate_dimensions(rows: int, columns: int) -> tuple[int, int]:
    if not 1 <= rows <= 32767:
        raise RulesError(
            "INVALID_RULES_ROWS",
            "rows must be between 1 and 32767.",
            details={"field": "rows"},
        )
    if not 1 <= columns <= 32767:
        raise RulesError(
            "INVALID_RULES_COLUMNS",
            "columns must be between 1 and 32767.",
            details={"field": "columns"},
        )
    return rows, columns


def validate_spin_cost(spin_cost: int) -> int:
    if not 0 <= spin_cost <= MAX_SPIN_COST:
        raise RulesError(
            "INVALID_SPIN_COST",
            "spinCost must be between 0 and 2147483647.",
            details={"field": "spinCost"},
        )
    return spin_cost


def ensure_draft(rules_version: RulesVersion) -> None:
    if rules_version.status is not RulesVersionStatus.DRAFT:
        raise RulesConflictError(
            "RULES_VERSION_IMMUTABLE",
            "Only a draft rules version can be changed.",
            details={"rulesVersionId": str(rules_version.id)},
        )


def validate_payline_code(code: str) -> str:
    if not _PAYLINE_CODE_PATTERN.fullmatch(code):
        raise RulesError(
            "INVALID_PAYLINE_CODE",
            "Payline code must contain 1-64 letters, digits, underscores, or hyphens.",
            details={"field": "code"},
        )
    return code


def validate_payline_name(name: str) -> str:
    normalized = name.strip()
    if not normalized or len(normalized) > 200:
        raise RulesError(
            "INVALID_PAYLINE_NAME",
            "Payline name must contain 1-200 non-whitespace characters.",
            details={"field": "name"},
        )
    return normalized


def validate_payline_row_path(
    row_path: Sequence[int],
    *,
    rows: int,
    columns: int,
) -> tuple[int, ...]:
    normalized = tuple(row_path)
    if len(normalized) != columns:
        raise RulesError(
            "INVALID_PAYLINE_LENGTH",
            "rowPath must contain exactly one row for every column.",
            details={"field": "rowPath", "expectedColumns": columns},
        )
    invalid = next(
        (index for index, row in enumerate(normalized) if not 0 <= row < rows),
        None,
    )
    if invalid is not None:
        raise RulesError(
            "INVALID_PAYLINE_ROW",
            "Every rowPath value must identify an existing zero-based row.",
            details={
                "field": "rowPath",
                "column": invalid,
                "rows": rows,
            },
        )
    return normalized


def validate_payline_display_order(display_order: int) -> int:
    if not 0 <= display_order <= MAX_DISPLAY_ORDER:
        raise RulesError(
            "INVALID_PAYLINE_DISPLAY_ORDER",
            "displayOrder must be between 0 and 2147483647.",
            details={"field": "displayOrder"},
        )
    return display_order


def validate_minimum_match_length(
    minimum_match_length: int | None,
    *,
    columns: int,
    is_wildcard: bool,
) -> int | None:
    if is_wildcard:
        if minimum_match_length is not None:
            raise RulesError(
                "WILDCARD_MINIMUM_NOT_ALLOWED",
                "A wildcard symbol cannot have minimumMatchLength.",
                details={"field": "minimumMatchLength"},
            )
        return None
    if minimum_match_length is None or not 2 <= minimum_match_length <= columns:
        raise RulesError(
            "INVALID_MINIMUM_MATCH_LENGTH",
            "minimumMatchLength must be between 2 and the rules column count.",
            details={
                "field": "minimumMatchLength",
                "columns": columns,
            },
        )
    return minimum_match_length


def validate_payout_match_length(
    match_length: int,
    *,
    minimum_match_length: int,
    columns: int,
) -> int:
    if not minimum_match_length <= match_length <= columns:
        raise RulesError(
            "INVALID_PAYOUT_MATCH_LENGTH",
            "matchLength must be between the symbol minimum and rules column count.",
            details={
                "field": "matchLength",
                "minimumMatchLength": minimum_match_length,
                "columns": columns,
            },
        )
    return match_length


def validate_payout_credits(payout_credits: int) -> int:
    if not 0 <= payout_credits <= MAX_SPIN_COST:
        raise RulesError(
            "INVALID_PAYOUT_CREDITS",
            "payoutCredits must be between 0 and 2147483647.",
            details={"field": "payoutCredits"},
        )
    return payout_credits
