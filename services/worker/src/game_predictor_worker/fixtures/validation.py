"""Integrity validation and canonical fingerprinting for M1 fixtures."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from game_predictor_worker.domain import (
    DomainValidationError,
    encode_signature,
    evaluate_payout,
    validate_game_config,
    validate_paylines,
    validate_payout_configuration,
)
from game_predictor_worker.fixtures.contracts import (
    FixtureValidationReport,
    GameFixtureValidation,
    GeneratedGameFixture,
    M1Fixture,
)
from game_predictor_worker.fixtures.errors import (
    FixtureErrorCode,
    FixtureValidationError,
)
from game_predictor_worker.fixtures.generator import (
    M1_DUPLICATE_GROUP_COUNT,
    M1_LAYOUT_COUNT,
)


def _require_metadata(fixture: M1Fixture) -> None:
    if (
        not fixture.fixture_version.strip()
        or fixture.dataset_version < 1
        or fixture.rules_version < 1
        or not fixture.algorithm_version.strip()
    ):
        raise FixtureValidationError(
            FixtureErrorCode.FIXTURE_METADATA_ERROR,
            "Fixture versions must be non-empty and positive.",
        )


def _validate_game_contract(game_fixture: GeneratedGameFixture) -> None:
    try:
        validate_game_config(game_fixture.game)
        validate_paylines(game_fixture.paylines, game_fixture.game)
        validate_payout_configuration(
            game_fixture.payout_rules,
            game_fixture.payout_symbols,
            game_fixture.game,
        )
    except DomainValidationError as error:
        raise FixtureValidationError(
            FixtureErrorCode.GAME_CONFIG_ERROR,
            f"Invalid configuration for {game_fixture.game.code}: {error}",
        ) from error


def _validate_sequence(game_fixture: GeneratedGameFixture) -> None:
    actual = tuple(layout.sequence_number for layout in game_fixture.layouts)
    expected = tuple(range(1, M1_LAYOUT_COUNT + 1))
    if actual != expected:
        raise FixtureValidationError(
            FixtureErrorCode.SEQUENCE_INTEGRITY_ERROR,
            (
                f"{game_fixture.game.code} sequence must be exactly "
                f"1..{M1_LAYOUT_COUNT} without gaps or duplicates."
            ),
        )


def _validate_layouts(game_fixture: GeneratedGameFixture) -> None:
    for layout in game_fixture.layouts:
        try:
            expected_signature = encode_signature(
                layout.cells,
                game_fixture.game.signature_cell_width,
            )
        except DomainValidationError as error:
            raise FixtureValidationError(
                FixtureErrorCode.LAYOUT_INTEGRITY_ERROR,
                (
                    f"{game_fixture.game.code} layout {layout.sequence_number} "
                    f"contains invalid cells: {error}"
                ),
            ) from error
        if layout.signature != expected_signature:
            raise FixtureValidationError(
                FixtureErrorCode.SIGNATURE_INTEGRITY_ERROR,
                (
                    f"{game_fixture.game.code} layout {layout.sequence_number} "
                    "has a signature inconsistent with its cells."
                ),
            )
        try:
            expected_payout = evaluate_payout(
                game_fixture.game,
                layout.cells,
                game_fixture.paylines,
                game_fixture.payout_symbols,
                game_fixture.payout_rules,
            ).total_payout
        except DomainValidationError as error:
            raise FixtureValidationError(
                FixtureErrorCode.LAYOUT_INTEGRITY_ERROR,
                (
                    f"{game_fixture.game.code} layout {layout.sequence_number} "
                    f"contains invalid cells: {error}"
                ),
            ) from error
        if layout.payout_credits < 0 or layout.payout_credits != expected_payout:
            raise FixtureValidationError(
                FixtureErrorCode.PAYOUT_INTEGRITY_ERROR,
                (
                    f"{game_fixture.game.code} layout {layout.sequence_number} "
                    f"has payout {layout.payout_credits}; expected {expected_payout}."
                ),
            )


def _observed_duplicate_groups(
    game_fixture: GeneratedGameFixture,
) -> dict[str, tuple[int, ...]]:
    positions: defaultdict[str, list[int]] = defaultdict(list)
    for layout in game_fixture.layouts:
        positions[layout.signature].append(layout.sequence_number)
    return {
        signature: tuple(sequence_numbers)
        for signature, sequence_numbers in positions.items()
        if len(sequence_numbers) > 1
    }


def _validate_duplicates(game_fixture: GeneratedGameFixture) -> int:
    observed = _observed_duplicate_groups(game_fixture)
    declared = {
        duplicate.signature: duplicate.sequence_numbers
        for duplicate in game_fixture.duplicate_fixtures
    }
    if (
        len(declared) != M1_DUPLICATE_GROUP_COUNT
        or len(declared) != len(game_fixture.duplicate_fixtures)
        or observed != declared
        or any(len(sequence_numbers) != 2 for sequence_numbers in observed.values())
    ):
        raise FixtureValidationError(
            FixtureErrorCode.DUPLICATE_INTEGRITY_ERROR,
            (
                f"{game_fixture.game.code} must contain exactly "
                f"{M1_DUPLICATE_GROUP_COUNT} declared duplicate pairs and no others."
            ),
        )
    return len(observed)


def _validate_unique_prefix(game_fixture: GeneratedGameFixture) -> int:
    reference = game_fixture.unique_prefix_fixture
    if reference.sequence_number < 1 or reference.sequence_number > len(game_fixture.layouts):
        raise FixtureValidationError(
            FixtureErrorCode.PREFIX_INTEGRITY_ERROR,
            f"{game_fixture.game.code} unique-prefix sequence is out of range.",
        )
    layout = game_fixture.layouts[reference.sequence_number - 1]
    if (
        reference.cell_count < 1
        or reference.cell_count >= len(layout.cells)
        or reference.signature_prefix
        != layout.signature[: reference.cell_count * game_fixture.game.signature_cell_width]
    ):
        raise FixtureValidationError(
            FixtureErrorCode.PREFIX_INTEGRITY_ERROR,
            f"{game_fixture.game.code} unique-prefix metadata is inconsistent.",
        )
    matching_count = sum(
        candidate.signature.startswith(reference.signature_prefix)
        for candidate in game_fixture.layouts
    )
    if matching_count != 1:
        raise FixtureValidationError(
            FixtureErrorCode.PREFIX_INTEGRITY_ERROR,
            (
                f"{game_fixture.game.code} declared prefix resolves to "
                f"{matching_count} layouts instead of one."
            ),
        )
    return reference.cell_count


def _validate_target_golden_fixtures(
    game_fixture: GeneratedGameFixture,
) -> None:
    codes = tuple(golden.code for golden in game_fixture.target_golden_fixtures)
    if len(set(codes)) != len(codes) or any(not code.strip() for code in codes):
        raise FixtureValidationError(
            FixtureErrorCode.FIXTURE_METADATA_ERROR,
            f"{game_fixture.game.code} Target golden codes must be non-empty and unique.",
        )

    layout_count = len(game_fixture.layouts)
    for golden in game_fixture.target_golden_fixtures:
        if golden.start_sequence_number < 1 or golden.start_sequence_number > layout_count:
            raise FixtureValidationError(
                FixtureErrorCode.FIXTURE_METADATA_ERROR,
                f"{game_fixture.game.code} Target golden start is out of range.",
            )
        ordered_layouts = (
            game_fixture.layouts[golden.start_sequence_number :]
            + game_fixture.layouts[: golden.start_sequence_number - 1]
        )
        final_payout = sum(layout.payout_credits for layout in ordered_layouts)
        final_cost = len(ordered_layouts) * game_fixture.game.spin_cost
        if (
            len(ordered_layouts) != layout_count - 1
            or golden.expected_final_cumulative_payout != final_payout
            or golden.expected_final_cumulative_cost != final_cost
            or golden.expected_final_net_credits != final_payout - final_cost
        ):
            raise FixtureValidationError(
                FixtureErrorCode.FIXTURE_METADATA_ERROR,
                f"{game_fixture.game.code} Target golden totals are inconsistent.",
            )

        cumulative_payouts: list[int] = []
        cumulative_payout = 0
        for layout in ordered_layouts:
            cumulative_payout += layout.payout_credits
            cumulative_payouts.append(cumulative_payout)
        for peak in golden.expected_positive_local_peaks:
            if peak.spin_number < 1 or peak.spin_number > len(ordered_layouts):
                raise FixtureValidationError(
                    FixtureErrorCode.FIXTURE_METADATA_ERROR,
                    f"{game_fixture.game.code} Target golden peak is out of range.",
                )
            layout = ordered_layouts[peak.spin_number - 1]
            expected_cost = peak.spin_number * game_fixture.game.spin_cost
            expected_payout = cumulative_payouts[peak.spin_number - 1]
            if (
                peak.sequence_number != layout.sequence_number
                or peak.spin_payout != layout.payout_credits
                or peak.cumulative_payout != expected_payout
                or peak.cumulative_cost != expected_cost
                or peak.net_credits != expected_payout - expected_cost
                or peak.net_credits <= 0
            ):
                raise FixtureValidationError(
                    FixtureErrorCode.FIXTURE_METADATA_ERROR,
                    f"{game_fixture.game.code} Target golden peak is inconsistent.",
                )


def _symbol_payload(game_fixture: GeneratedGameFixture) -> list[dict[str, Any]]:
    return [
        {
            "mobile_code": symbol.mobile_code,
            "code": symbol.code,
            "name": symbol.name,
            "is_wildcard": symbol.is_wildcard,
            "display_order": symbol.display_order,
        }
        for symbol in game_fixture.game.symbols
    ]


def _game_payload(game_fixture: GeneratedGameFixture) -> Mapping[str, Any]:
    game = game_fixture.game
    return {
        "seed": game_fixture.seed,
        "game": {
            "id": game.id,
            "code": game.code,
            "name": game.name,
            "rows": game.rows,
            "columns": game.columns,
            "spin_cost": game.spin_cost,
            "signature_cell_width": game.signature_cell_width,
            "symbols": _symbol_payload(game_fixture),
        },
        "paylines": [
            {"id": payline.id, "row_path": list(payline.row_path)}
            for payline in game_fixture.paylines
        ],
        "payout_rules": [
            {
                "symbol_mobile_code": rule.symbol_mobile_code,
                "match_length": rule.match_length,
                "payout_credits": rule.payout_credits,
            }
            for rule in game_fixture.payout_rules
        ],
        "payout_symbols": [
            {
                "symbol_mobile_code": payout_symbol.symbol_mobile_code,
                "minimum_match_length": payout_symbol.minimum_match_length,
            }
            for payout_symbol in game_fixture.payout_symbols
        ],
        "layouts": [
            {
                "sequence_number": layout.sequence_number,
                "cells": list(layout.cells),
                "signature": layout.signature,
                "payout_credits": layout.payout_credits,
            }
            for layout in game_fixture.layouts
        ],
        "duplicate_fixtures": [
            {
                "signature": duplicate.signature,
                "sequence_numbers": list(duplicate.sequence_numbers),
            }
            for duplicate in game_fixture.duplicate_fixtures
        ],
        "unique_prefix_fixture": {
            "sequence_number": game_fixture.unique_prefix_fixture.sequence_number,
            "cell_count": game_fixture.unique_prefix_fixture.cell_count,
            "signature_prefix": game_fixture.unique_prefix_fixture.signature_prefix,
        },
        "target_golden_fixtures": [
            {
                "code": golden.code,
                "start_sequence_number": golden.start_sequence_number,
                "expected_final_cumulative_payout": (golden.expected_final_cumulative_payout),
                "expected_final_cumulative_cost": golden.expected_final_cumulative_cost,
                "expected_final_net_credits": golden.expected_final_net_credits,
                "expected_positive_local_peaks": [
                    {
                        "spin_number": peak.spin_number,
                        "sequence_number": peak.sequence_number,
                        "spin_payout": peak.spin_payout,
                        "cumulative_payout": peak.cumulative_payout,
                        "cumulative_cost": peak.cumulative_cost,
                        "net_credits": peak.net_credits,
                    }
                    for peak in golden.expected_positive_local_peaks
                ],
            }
            for golden in game_fixture.target_golden_fixtures
        ],
    }


def fixture_fingerprint(fixture: M1Fixture) -> str:
    """Return a stable SHA-256 over the logical fixture, not a SQLite file."""

    payload = {
        "fixture_version": fixture.fixture_version,
        "dataset_version": fixture.dataset_version,
        "rules_version": fixture.rules_version,
        "algorithm_version": fixture.algorithm_version,
        "games": [_game_payload(game) for game in fixture.games],
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return hashlib.sha256(canonical).hexdigest()


def validate_m1_fixture(fixture: M1Fixture) -> FixtureValidationReport:
    """Validate all invariants required before snapshot persistence."""

    _require_metadata(fixture)
    if len(fixture.games) != 3:
        raise FixtureValidationError(
            FixtureErrorCode.GAME_CONFIG_ERROR,
            "M1 fixture must contain exactly three games.",
        )
    game_codes = tuple(game_fixture.game.code for game_fixture in fixture.games)
    if game_codes != ("game-1", "game-2", "game-3"):
        raise FixtureValidationError(
            FixtureErrorCode.GAME_CONFIG_ERROR,
            "M1 game codes must be ordered as game-1, game-2, game-3.",
        )

    expected_symbol_counts = (10, 12, 11)
    reports: list[GameFixtureValidation] = []
    for game_fixture, expected_symbol_count in zip(
        fixture.games,
        expected_symbol_counts,
        strict=True,
    ):
        _validate_game_contract(game_fixture)
        game = game_fixture.game
        wildcard_count = sum(symbol.is_wildcard for symbol in game.symbols)
        expected_wildcard_count = 1 if game.code == "game-3" else 0
        if (
            game.rows != 3
            or game.columns != 5
            or game.spin_cost != 10
            or len(game.symbols) != expected_symbol_count
            or wildcard_count != expected_wildcard_count
            or len(game_fixture.layouts) != M1_LAYOUT_COUNT
        ):
            raise FixtureValidationError(
                FixtureErrorCode.GAME_CONFIG_ERROR,
                f"{game.code} does not match the accepted M1 mock configuration.",
            )
        _validate_sequence(game_fixture)
        _validate_layouts(game_fixture)
        duplicate_group_count = _validate_duplicates(game_fixture)
        unique_prefix_cell_count = _validate_unique_prefix(game_fixture)
        _validate_target_golden_fixtures(game_fixture)
        reports.append(
            GameFixtureValidation(
                game_code=game.code,
                layout_count=len(game_fixture.layouts),
                duplicate_group_count=duplicate_group_count,
                unique_prefix_cell_count=unique_prefix_cell_count,
            )
        )

    return FixtureValidationReport(
        fixture_fingerprint=fixture_fingerprint(fixture),
        game_count=len(fixture.games),
        layout_count=sum(len(game.layouts) for game in fixture.games),
        games=tuple(reports),
    )
