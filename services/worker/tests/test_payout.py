from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from game_predictor_worker.domain import (
    DomainValidationError,
    GameConfig,
    PaylineDefinition,
    PayoutEvaluation,
    PayoutRuleDefinition,
    SymbolDefinition,
)
from game_predictor_worker.domain.payout import evaluate_payout

FIXTURE_PATH = (
    Path(__file__).parents[3]
    / "packages"
    / "domain-fixtures"
    / "payout-golden-cases.json"
)


def _load_fixture() -> Mapping[str, Any]:
    return cast(Mapping[str, Any], json.loads(FIXTURE_PATH.read_text(encoding="utf-8")))


def _game_from_fixture(data: Mapping[str, Any]) -> GameConfig:
    return GameConfig(
        id=data["id"],
        code=data["code"],
        name=data["name"],
        rows=data["rows"],
        columns=data["columns"],
        spin_cost=data["spinCost"],
        signature_cell_width=data["signatureCellWidth"],
        symbols=tuple(
            SymbolDefinition(
                mobile_code=symbol["mobileCode"],
                code=symbol["code"],
                name=symbol["name"],
                is_wildcard=symbol["isWildcard"],
                display_order=symbol["displayOrder"],
            )
            for symbol in data["symbols"]
        ),
    )


def _paylines_from_fixture(
    values: Sequence[Mapping[str, Any]],
) -> tuple[PaylineDefinition, ...]:
    return tuple(
        PaylineDefinition(id=value["id"], row_path=tuple(value["rowPath"]))
        for value in values
    )


def _rules_from_fixture(
    values: Sequence[Mapping[str, Any]],
) -> tuple[PayoutRuleDefinition, ...]:
    return tuple(
        PayoutRuleDefinition(
            symbol_mobile_code=value["symbolMobileCode"],
            match_length=value["matchLength"],
            payout_credits=value["payoutCredits"],
        )
        for value in values
    )


def _serialize_result(result: PayoutEvaluation) -> dict[str, Any]:
    return {
        "totalPayout": result.total_payout,
        "matches": [
            {
                "symbolMobileCode": match.symbol_mobile_code,
                "paylineId": match.payline_id,
                "startColumn": match.start_column,
                "matchedLength": match.matched_length,
                "matchedCells": list(match.matched_cells),
                "jokerCells": list(match.joker_cells),
                "payoutCredits": match.payout_credits,
                "interpretation": [
                    {
                        "cellIndex": value.cell_index,
                        "asSymbolMobileCode": value.as_symbol_mobile_code,
                    }
                    for value in match.interpretation
                ],
            }
            for match in result.matches
        ],
    }


def _assert_domain_error(expected_code: str, callback: Callable[[], object]) -> None:
    with pytest.raises(DomainValidationError) as captured:
        callback()
    assert captured.value.code == expected_code


@pytest.mark.parametrize(
    "case",
    _load_fixture()["cases"],
    ids=lambda case: cast(Mapping[str, Any], case)["id"],
)
def test_payout_golden_cases(case: Mapping[str, Any]) -> None:
    fixture = _load_fixture()
    game = _game_from_fixture(fixture["game"])
    paylines_by_id = {
        payline.id: payline
        for payline in _paylines_from_fixture(fixture["paylines"])
    }
    paylines = tuple(paylines_by_id[payline_id] for payline_id in case["paylineIds"])
    rules = _rules_from_fixture(fixture["payoutRules"])
    cells = tuple(cell for row in case["rows"] for cell in row)

    result = evaluate_payout(game, cells, paylines, rules)

    assert case["manualCalculation"], "Golden case must document manual calculation."
    assert _serialize_result(result) == case["expected"]


def test_payout_evaluation_is_deterministic_and_does_not_mutate_inputs() -> None:
    fixture = _load_fixture()
    case = fixture["cases"][-1]
    game = _game_from_fixture(fixture["game"])
    paylines = _paylines_from_fixture(fixture["paylines"])
    rules = _rules_from_fixture(fixture["payoutRules"])
    cells = tuple(cell for row in case["rows"] for cell in row)
    original_inputs = (game, cells, paylines, rules)

    first = evaluate_payout(game, cells, paylines, rules)
    second = evaluate_payout(game, cells, paylines, rules)

    assert first == second
    assert (game, cells, paylines, rules) == original_inputs


def test_precomputing_rejects_duplicate_payout_rule() -> None:
    fixture = _load_fixture()
    game = _game_from_fixture(fixture["game"])
    rules = _rules_from_fixture(fixture["payoutRules"])
    cells = tuple(cell for row in fixture["cases"][0]["rows"] for cell in row)
    paylines = _paylines_from_fixture(fixture["paylines"][:1])

    _assert_domain_error(
        "duplicate_payout_rule",
        lambda: evaluate_payout(game, cells, paylines, (*rules, rules[0])),
    )


def test_precomputing_rejects_duplicate_payline_path() -> None:
    fixture = _load_fixture()
    game = _game_from_fixture(fixture["game"])
    rules = _rules_from_fixture(fixture["payoutRules"])
    cells = tuple(cell for row in fixture["cases"][0]["rows"] for cell in row)
    payline = _paylines_from_fixture(fixture["paylines"][:1])[0]
    duplicate_path = replace(payline, id="duplicate-top")

    _assert_domain_error(
        "duplicate_payline",
        lambda: evaluate_payout(
            game,
            cells,
            (payline, duplicate_path),
            rules,
        ),
    )


def test_precomputing_rejects_incomplete_payout_matrix() -> None:
    fixture = _load_fixture()
    game = _game_from_fixture(fixture["game"])
    rules = _rules_from_fixture(fixture["payoutRules"])[:-1]
    cells = tuple(cell for row in fixture["cases"][0]["rows"] for cell in row)
    paylines = _paylines_from_fixture(fixture["paylines"][:1])

    _assert_domain_error(
        "incomplete_payout_rules",
        lambda: evaluate_payout(game, cells, paylines, rules),
    )


def test_precomputing_rejects_non_increasing_payout() -> None:
    fixture = _load_fixture()
    game = _game_from_fixture(fixture["game"])
    rules = list(_rules_from_fixture(fixture["payoutRules"]))
    rules[1] = replace(rules[1], payout_credits=rules[0].payout_credits)
    cells = tuple(cell for row in fixture["cases"][0]["rows"] for cell in row)
    paylines = _paylines_from_fixture(fixture["paylines"][:1])

    _assert_domain_error(
        "non_increasing_payout",
        lambda: evaluate_payout(game, cells, paylines, tuple(rules)),
    )


def test_precomputing_rejects_board_wider_than_m1() -> None:
    fixture = _load_fixture()
    game = replace(_game_from_fixture(fixture["game"]), columns=6)
    cells = (1,) * (game.rows * game.columns)
    payline = PaylineDefinition(id="wide", row_path=(0, 0, 0, 0, 0, 0))
    rules = _rules_from_fixture(fixture["payoutRules"])

    _assert_domain_error(
        "unsupported_payout_board_width",
        lambda: evaluate_payout(game, cells, (payline,), rules),
    )
