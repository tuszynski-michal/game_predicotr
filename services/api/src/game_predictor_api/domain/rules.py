"""Framework-independent rules-version domain."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
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


@dataclass(frozen=True, slots=True)
class RulesPublicationIssue:
    code: str
    message: str
    details: dict[str, object]


@dataclass(frozen=True, slots=True)
class RulesPublicationReadiness:
    rules_version_id: UUID
    ready: bool
    issues: tuple[RulesPublicationIssue, ...]


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


def assess_rules_publication(
    rules_version: RulesVersion,
    *,
    paylines: Sequence[Payline],
    symbol_configurations: Sequence[RulesVersionSymbol],
    payout_rules: Sequence[PayoutRule],
    symbols: Mapping[UUID, RulesSymbolDefinition],
) -> RulesPublicationReadiness:
    """Return every deterministic blocker without changing domain state."""

    issues: list[RulesPublicationIssue] = []

    def add_issue(code: str, message: str, **details: object) -> None:
        issues.append(RulesPublicationIssue(code, message, details))

    if rules_version.status is not RulesVersionStatus.DRAFT:
        add_issue(
            "RULES_VERSION_NOT_DRAFT",
            "Only a draft rules version can be published.",
            rulesVersionId=str(rules_version.id),
            status=rules_version.status.value,
        )

    active_paylines = sorted(
        (payline for payline in paylines if payline.is_active),
        key=lambda payline: (payline.display_order, payline.code, str(payline.id)),
    )
    if not active_paylines:
        add_issue(
            "NO_ACTIVE_PAYLINES",
            "At least one active payline is required.",
        )
    for payline in active_paylines:
        if len(payline.row_path) != rules_version.columns:
            add_issue(
                "INVALID_ACTIVE_PAYLINE",
                "An active payline must contain one row for every column.",
                paylineId=str(payline.id),
            )
        elif any(not 0 <= row < rules_version.rows for row in payline.row_path):
            add_issue(
                "INVALID_ACTIVE_PAYLINE",
                "An active payline contains a row outside the rules grid.",
                paylineId=str(payline.id),
            )

    active_configurations = sorted(
        (configuration for configuration in symbol_configurations if configuration.is_active),
        key=lambda configuration: str(configuration.symbol_id),
    )
    if not active_configurations:
        add_issue(
            "NO_ACTIVE_RULE_SYMBOLS",
            "At least one active symbol configuration is required.",
        )

    configurations_by_symbol = {
        configuration.symbol_id: configuration for configuration in symbol_configurations
    }
    active_ordinary: list[RulesVersionSymbol] = []
    for configuration in active_configurations:
        symbol = symbols.get(configuration.symbol_id)
        if symbol is None or symbol.game_id != rules_version.game_id:
            add_issue(
                "INVALID_RULE_SYMBOL",
                "An active symbol does not belong to the rules version game.",
                symbolId=str(configuration.symbol_id),
            )
            continue
        if symbol.is_wildcard:
            if configuration.minimum_match_length is not None:
                add_issue(
                    "WILDCARD_MINIMUM_NOT_ALLOWED",
                    "A wildcard symbol cannot have minimumMatchLength.",
                    symbolId=str(configuration.symbol_id),
                )
            continue
        if (
            configuration.minimum_match_length is None
            or not 2 <= configuration.minimum_match_length <= rules_version.columns
        ):
            add_issue(
                "INVALID_MINIMUM_MATCH_LENGTH",
                "An active ordinary symbol needs a valid minimumMatchLength.",
                symbolId=str(configuration.symbol_id),
                columns=rules_version.columns,
            )
            continue
        active_ordinary.append(configuration)

    if not active_ordinary:
        add_issue(
            "NO_ACTIVE_ORDINARY_SYMBOLS",
            "At least one active ordinary symbol is required.",
        )

    active_payouts = sorted(
        (rule for rule in payout_rules if rule.is_active),
        key=lambda rule: (
            str(rule.symbol_id),
            rule.match_length,
            str(rule.id),
        ),
    )
    payouts_by_symbol: dict[UUID, list[PayoutRule]] = defaultdict(list)
    for rule in active_payouts:
        payouts_by_symbol[rule.symbol_id].append(rule)
        payout_configuration = configurations_by_symbol.get(rule.symbol_id)
        symbol = symbols.get(rule.symbol_id)
        if payout_configuration is None or not payout_configuration.is_active:
            add_issue(
                "PAYOUT_FOR_INACTIVE_SYMBOL",
                "An active payout belongs to an inactive or unconfigured symbol.",
                payoutRuleId=str(rule.id),
                symbolId=str(rule.symbol_id),
            )
            continue
        if symbol is None or symbol.game_id != rules_version.game_id:
            add_issue(
                "INVALID_RULE_SYMBOL",
                "An active payout belongs to a symbol outside the rules game.",
                payoutRuleId=str(rule.id),
                symbolId=str(rule.symbol_id),
            )
            continue
        if symbol.is_wildcard:
            add_issue(
                "WILDCARD_PAYOUT_NOT_ALLOWED",
                "A wildcard symbol cannot have active payout rules.",
                payoutRuleId=str(rule.id),
                symbolId=str(rule.symbol_id),
            )
            continue
        minimum = payout_configuration.minimum_match_length
        if minimum is None or not minimum <= rule.match_length <= rules_version.columns:
            add_issue(
                "INVALID_PAYOUT_MATCH_LENGTH",
                "An active payout length is outside the configured range.",
                payoutRuleId=str(rule.id),
                symbolId=str(rule.symbol_id),
                matchLength=rule.match_length,
            )
        if not 0 <= rule.payout_credits <= MAX_SPIN_COST:
            add_issue(
                "INVALID_PAYOUT_CREDITS",
                "An active payout value is outside the supported range.",
                payoutRuleId=str(rule.id),
                symbolId=str(rule.symbol_id),
            )

    for configuration in active_ordinary:
        minimum = configuration.minimum_match_length
        if minimum is None:
            continue
        rules = payouts_by_symbol.get(configuration.symbol_id, [])
        by_length: dict[int, list[PayoutRule]] = defaultdict(list)
        for rule in rules:
            by_length[rule.match_length].append(rule)
        duplicate_lengths = sorted(
            length for length, matches in by_length.items() if len(matches) > 1
        )
        if duplicate_lengths:
            add_issue(
                "DUPLICATE_ACTIVE_PAYOUT_RULE",
                "An ordinary symbol has duplicate active payout lengths.",
                symbolId=str(configuration.symbol_id),
                matchLengths=duplicate_lengths,
            )
        expected_lengths = range(minimum, rules_version.columns + 1)
        missing_lengths = [length for length in expected_lengths if length not in by_length]
        if missing_lengths:
            add_issue(
                "INCOMPLETE_PAYOUT_RULES",
                "An ordinary symbol needs a payout for every supported length.",
                symbolId=str(configuration.symbol_id),
                missingMatchLengths=missing_lengths,
            )
        ordered = [
            by_length[length][0] for length in expected_lengths if len(by_length[length]) == 1
        ]
        for previous, current in zip(ordered, ordered[1:], strict=False):
            if current.match_length != previous.match_length + 1:
                continue
            if current.payout_credits <= previous.payout_credits:
                add_issue(
                    "NON_INCREASING_PAYOUT",
                    "Payout credits must increase with every longer match.",
                    symbolId=str(configuration.symbol_id),
                    previousMatchLength=previous.match_length,
                    matchLength=current.match_length,
                )

    return RulesPublicationReadiness(
        rules_version_id=rules_version.id,
        ready=not issues,
        issues=tuple(issues),
    )
