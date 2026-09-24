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
    PayoutSymbolDefinition,
    SymbolDefinition,
)
from game_predictor_worker.domain.payout import evaluate_payout, prepare_payout_evaluator

FIXTURE_PATH = (
    Path(__file__).parents[3] / "packages" / "domain-fixtures" / "payout-golden-cases.json"
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
        PaylineDefinition(id=value["id"], row_path=tuple(value["rowPath"])) for value in values
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


def _payout_symbols_from_fixture(
    values: Sequence[Mapping[str, Any]],
) -> tuple[PayoutSymbolDefinition, ...]:
    return tuple(
        PayoutSymbolDefinition(
            symbol_mobile_code=value["symbolMobileCode"],
            minimum_match_length=value["minimumMatchLength"],
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
        payline.id: payline for payline in _paylines_from_fixture(fixture["paylines"])
    }
    paylines = tuple(paylines_by_id[payline_id] for payline_id in case["paylineIds"])
    payout_symbols = _payout_symbols_from_fixture(fixture["payoutSymbols"])
    rules = _rules_from_fixture(fixture["payoutRules"])
    cells = tuple(cell for row in case["rows"] for cell in row)

    result = evaluate_payout(game, cells, paylines, payout_symbols, rules)

    assert case["manualCalculation"], "Golden case must document manual calculation."
    assert _serialize_result(result) == case["expected"]


def test_payout_evaluation_is_deterministic_and_does_not_mutate_inputs() -> None:
    fixture = _load_fixture()
    case = fixture["cases"][-1]
    game = _game_from_fixture(fixture["game"])
    paylines = _paylines_from_fixture(fixture["paylines"])
    payout_symbols = _payout_symbols_from_fixture(fixture["payoutSymbols"])
    rules = _rules_from_fixture(fixture["payoutRules"])
    cells = tuple(cell for row in case["rows"] for cell in row)
    original_inputs = (game, cells, paylines, payout_symbols, rules)

    first = evaluate_payout(game, cells, paylines, payout_symbols, rules)
    second = evaluate_payout(game, cells, paylines, payout_symbols, rules)

    assert first == second
    assert (game, cells, paylines, payout_symbols, rules) == original_inputs


@pytest.mark.parametrize(
    ("top_row", "expected_total", "expected_length"),
    (
        ((0, 1, 1, 1, 1), 0, None),
        ((1, 1, 0, 1, 1), 5, 2),
        ((1, 9, 0, 2, 2), 5, 2),
        ((1, 1, 1, 0, 2), 10, 3),
    ),
)
def test_payout_v3_stops_at_unknown_and_ignores_the_suffix(
    top_row: tuple[int, ...],
    expected_total: int,
    expected_length: int | None,
) -> None:
    fixture = _load_fixture()
    game = _game_from_fixture(fixture["game"])
    payline = _paylines_from_fixture(fixture["paylines"][:1])
    payout_symbols = _payout_symbols_from_fixture(fixture["payoutSymbols"])
    rules = _rules_from_fixture(fixture["payoutRules"])
    cells = (*top_row, *((2,) * 10))

    result = evaluate_payout(game, cells, payline, payout_symbols, rules)

    assert result.total_payout == expected_total
    assert (result.matches[0].matched_length if result.matches else None) == expected_length


def test_precomputing_rejects_duplicate_payout_rule() -> None:
    fixture = _load_fixture()
    game = _game_from_fixture(fixture["game"])
    payout_symbols = _payout_symbols_from_fixture(fixture["payoutSymbols"])
    rules = _rules_from_fixture(fixture["payoutRules"])
    cells = tuple(cell for row in fixture["cases"][0]["rows"] for cell in row)
    paylines = _paylines_from_fixture(fixture["paylines"][:1])

    _assert_domain_error(
        "duplicate_payout_rule",
        lambda: evaluate_payout(
            game,
            cells,
            paylines,
            payout_symbols,
            (*rules, rules[0]),
        ),
    )


def test_precomputing_rejects_duplicate_payline_path() -> None:
    fixture = _load_fixture()
    game = _game_from_fixture(fixture["game"])
    payout_symbols = _payout_symbols_from_fixture(fixture["payoutSymbols"])
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
            payout_symbols,
            rules,
        ),
    )


def test_precomputing_rejects_incomplete_payout_matrix() -> None:
    fixture = _load_fixture()
    game = _game_from_fixture(fixture["game"])
    payout_symbols = _payout_symbols_from_fixture(fixture["payoutSymbols"])
    rules = _rules_from_fixture(fixture["payoutRules"])[:-1]
    cells = tuple(cell for row in fixture["cases"][0]["rows"] for cell in row)
    paylines = _paylines_from_fixture(fixture["paylines"][:1])

    _assert_domain_error(
        "incomplete_payout_rules",
        lambda: evaluate_payout(game, cells, paylines, payout_symbols, rules),
    )


def test_precomputing_rejects_non_increasing_payout() -> None:
    fixture = _load_fixture()
    game = _game_from_fixture(fixture["game"])
    payout_symbols = _payout_symbols_from_fixture(fixture["payoutSymbols"])
    rules = list(_rules_from_fixture(fixture["payoutRules"]))
    rules[1] = replace(rules[1], payout_credits=rules[0].payout_credits)
    cells = tuple(cell for row in fixture["cases"][0]["rows"] for cell in row)
    paylines = _paylines_from_fixture(fixture["paylines"][:1])

    _assert_domain_error(
        "non_increasing_payout",
        lambda: evaluate_payout(
            game,
            cells,
            paylines,
            payout_symbols,
            tuple(rules),
        ),
    )


def test_precomputing_supports_board_wider_than_m1() -> None:
    fixture = _load_fixture()
    game = replace(_game_from_fixture(fixture["game"]), columns=6)
    cells = (1,) * (game.rows * game.columns)
    payline = PaylineDefinition(id="wide", row_path=(0, 0, 0, 0, 0, 0))
    payout_symbols = _payout_symbols_from_fixture(fixture["payoutSymbols"])
    rules = (
        *_rules_from_fixture(fixture["payoutRules"]),
        PayoutRuleDefinition(
            symbol_mobile_code=1,
            match_length=6,
            payout_credits=100,
        ),
        PayoutRuleDefinition(
            symbol_mobile_code=2,
            match_length=6,
            payout_credits=160,
        ),
        PayoutRuleDefinition(
            symbol_mobile_code=3,
            match_length=6,
            payout_credits=220,
        ),
    )

    result = evaluate_payout(game, cells, (payline,), payout_symbols, rules)

    assert result.total_payout == 100
    assert result.matches[0].start_column == 0
    assert result.matches[0].matched_length == 6


# --- PreparedPayoutEvaluator (TASK-0650) -----------------------------------
#
# `prepare_payout_evaluator` validates paylines and the payout configuration
# once; `PreparedPayoutEvaluator.evaluate` reuses the precomputed wildcard
# set, ordinary-symbol order and payout-by-length lookup for every call. It
# must be a drop-in equivalent of `evaluate_payout` for every board.


@pytest.mark.parametrize(
    "case",
    _load_fixture()["cases"],
    ids=lambda case: cast(Mapping[str, Any], case)["id"],
)
def test_prepared_evaluator_matches_evaluate_payout_for_every_golden_case(
    case: Mapping[str, Any],
) -> None:
    fixture = _load_fixture()
    game = _game_from_fixture(fixture["game"])
    paylines_by_id = {
        payline.id: payline for payline in _paylines_from_fixture(fixture["paylines"])
    }
    paylines = tuple(paylines_by_id[payline_id] for payline_id in case["paylineIds"])
    payout_symbols = _payout_symbols_from_fixture(fixture["payoutSymbols"])
    rules = _rules_from_fixture(fixture["payoutRules"])
    cells = tuple(cell for row in case["rows"] for cell in row)

    one_shot = evaluate_payout(game, cells, paylines, payout_symbols, rules)
    prepared = prepare_payout_evaluator(game, paylines, payout_symbols, rules).evaluate(cells)

    assert prepared == one_shot


def test_prepare_payout_evaluator_rejects_invalid_configuration_before_any_board() -> None:
    fixture = _load_fixture()
    game = _game_from_fixture(fixture["game"])
    payout_symbols = _payout_symbols_from_fixture(fixture["payoutSymbols"])
    incomplete_rules = _rules_from_fixture(fixture["payoutRules"])[:-1]
    paylines = _paylines_from_fixture(fixture["paylines"][:1])

    _assert_domain_error(
        "incomplete_payout_rules",
        lambda: prepare_payout_evaluator(game, paylines, payout_symbols, incomplete_rules),
    )


def test_prepared_evaluator_does_not_sum_shorter_and_longer_match_lengths() -> None:
    """Five A's on one payline pay only the length-5 rule, never 2+3+4+5."""

    fixture = _load_fixture()
    game = _game_from_fixture(fixture["game"])
    payout_symbols = _payout_symbols_from_fixture(fixture["payoutSymbols"])
    rules = _rules_from_fixture(fixture["payoutRules"])
    middle = _paylines_from_fixture(fixture["paylines"])[1]
    assert middle.id == "middle"
    cells = (0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0)
    evaluator = prepare_payout_evaluator(game, (middle,), payout_symbols, rules)

    result = evaluator.evaluate(cells)

    assert result.total_payout == 50
    assert len(result.matches) == 1
    assert result.matches[0].matched_length == 5


def test_prepared_evaluator_confirmed_prefix_pays_only_the_confirmed_length() -> None:
    """C,C,C,?,? pays the length-3 rule for C; the unknown suffix is never assumed."""

    fixture = _load_fixture()
    game = _game_from_fixture(fixture["game"])
    payout_symbols = _payout_symbols_from_fixture(fixture["payoutSymbols"])
    rules = _rules_from_fixture(fixture["payoutRules"])
    middle = _paylines_from_fixture(fixture["paylines"])[1]
    cells = (0, 0, 0, 0, 0, 3, 3, 3, 0, 0, 0, 0, 0, 0, 0)
    evaluator = prepare_payout_evaluator(game, (middle,), payout_symbols, rules)

    result = evaluator.evaluate(cells)

    assert result.total_payout == 30
    assert result.matches[0].matched_length == 3


def test_prepared_evaluator_does_not_skip_an_unknown_cell_inside_the_line() -> None:
    """C,C,?,C,C never wins as length 4 or 5: the unknown at index 2 stops the prefix."""

    fixture = _load_fixture()
    game = _game_from_fixture(fixture["game"])
    payout_symbols = _payout_symbols_from_fixture(fixture["payoutSymbols"])
    rules = _rules_from_fixture(fixture["payoutRules"])
    middle = _paylines_from_fixture(fixture["paylines"])[1]
    # C's minimum match length is 3, so a stopped 2-cell prefix cannot win either.
    cells = (0, 0, 0, 0, 0, 3, 3, 0, 3, 3, 0, 0, 0, 0, 0)
    evaluator = prepare_payout_evaluator(game, (middle,), payout_symbols, rules)

    result = evaluator.evaluate(cells)

    assert result.total_payout == 0
    assert result.matches == ()


def test_prepared_evaluator_never_pays_from_an_unknown_left_column() -> None:
    """?,C,C,C,C never wins: payout-v3 only ever evaluates a prefix from column 0."""

    fixture = _load_fixture()
    game = _game_from_fixture(fixture["game"])
    payout_symbols = _payout_symbols_from_fixture(fixture["payoutSymbols"])
    rules = _rules_from_fixture(fixture["payoutRules"])
    middle = _paylines_from_fixture(fixture["paylines"])[1]
    cells = (0, 0, 0, 0, 0, 0, 3, 3, 3, 3, 0, 0, 0, 0, 0)
    evaluator = prepare_payout_evaluator(game, (middle,), payout_symbols, rules)

    result = evaluator.evaluate(cells)

    assert result.total_payout == 0
    assert result.matches == ()


def test_prepared_evaluator_all_joker_prefix_never_wins() -> None:
    """J,J,?,?,? does not win, even though A's minimum match length is 2."""

    fixture = _load_fixture()
    game = _game_from_fixture(fixture["game"])
    payout_symbols = _payout_symbols_from_fixture(fixture["payoutSymbols"])
    rules = _rules_from_fixture(fixture["payoutRules"])
    middle = _paylines_from_fixture(fixture["paylines"])[1]
    cells = (0, 0, 0, 0, 0, 9, 9, 0, 0, 0, 0, 0, 0, 0, 0)
    evaluator = prepare_payout_evaluator(game, (middle,), payout_symbols, rules)

    result = evaluator.evaluate(cells)

    assert result.total_payout == 0
    assert result.matches == ()


def test_prepared_evaluator_joker_wraps_a_confirmed_prefix() -> None:
    """J,C,J,?,? pays the length-3 rule for C, with both jokers interpreted as C."""

    fixture = _load_fixture()
    game = _game_from_fixture(fixture["game"])
    payout_symbols = _payout_symbols_from_fixture(fixture["payoutSymbols"])
    rules = _rules_from_fixture(fixture["payoutRules"])
    middle = _paylines_from_fixture(fixture["paylines"])[1]
    cells = (0, 0, 0, 0, 0, 9, 3, 9, 0, 0, 0, 0, 0, 0, 0)
    evaluator = prepare_payout_evaluator(game, (middle,), payout_symbols, rules)

    result = evaluator.evaluate(cells)

    assert result.total_payout == 30
    assert len(result.matches) == 1
    match = result.matches[0]
    assert match.matched_length == 3
    assert match.symbol_mobile_code == 3
    assert {interpretation.cell_index for interpretation in match.interpretation} == {5, 7}


def test_prepared_evaluator_sums_two_independent_partial_paylines() -> None:
    """A confirmed win on one payline and another on a different payline both count."""

    fixture = _load_fixture()
    game = _game_from_fixture(fixture["game"])
    payout_symbols = _payout_symbols_from_fixture(fixture["payoutSymbols"])
    rules = _rules_from_fixture(fixture["payoutRules"])
    top, middle = _paylines_from_fixture(fixture["paylines"])[:2]
    # top: A,A,A,?,? (prefix length 3 -> payout 10); middle: C,C,C,?,? (payout 30).
    cells = (1, 1, 1, 0, 0, 3, 3, 3, 0, 0, 0, 0, 0, 0, 0)
    evaluator = prepare_payout_evaluator(game, (top, middle), payout_symbols, rules)

    result = evaluator.evaluate(cells)

    assert result.total_payout == 40
    assert {match.payline_id for match in result.matches} == {"top", "middle"}


@pytest.mark.parametrize("known_prefix_length", range(0, 6))
def test_partial_prefix_payout_is_a_confirmed_lower_bound_of_the_full_board(
    known_prefix_length: int,
) -> None:
    """A truncated, otherwise-unknown prefix never pays more than the full board.

    `payout-v3-unknown-prefix-stop` can only extend or end a prefix at the
    first unknown cell, and payout strictly increases with match length
    (D-247, `ALGORITHMS.md` §B); a confirmed shorter prefix is therefore
    always a safe lower bound on the true payout.
    """

    fixture = _load_fixture()
    game = _game_from_fixture(fixture["game"])
    payout_symbols = _payout_symbols_from_fixture(fixture["payoutSymbols"])
    rules = _rules_from_fixture(fixture["payoutRules"])
    top = _paylines_from_fixture(fixture["paylines"][:1])[0]
    full_line = (1, 1, 1, 1, 1)
    partial_line = full_line[:known_prefix_length] + (0,) * (5 - known_prefix_length)
    cells_full = (*full_line, *((0,) * 10))
    cells_partial = (*partial_line, *((0,) * 10))
    evaluator = prepare_payout_evaluator(game, (top,), payout_symbols, rules)

    full_result = evaluator.evaluate(cells_full)
    partial_result = evaluator.evaluate(cells_partial)

    assert partial_result.total_payout <= full_result.total_payout
