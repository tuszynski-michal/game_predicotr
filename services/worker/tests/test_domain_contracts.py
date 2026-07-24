from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from game_predictor_worker.domain import (
    DomainValidationError,
    GameConfig,
    PaylineDefinition,
    PayoutRuleDefinition,
    SymbolDefinition,
    decode_signature,
    encode_signature,
    encode_signature_prefix,
    validate_board_prefix,
    validate_full_board,
    validate_game_config,
    validate_paylines,
    validate_payout_rules,
)

FIXTURE_PATH = (
    Path(__file__).parents[3] / "packages" / "domain-fixtures" / "domain-contract-cases.json"
)


def _load_fixture() -> Mapping[str, Any]:
    return cast(Mapping[str, Any], json.loads(FIXTURE_PATH.read_text(encoding="utf-8")))


def _game_from_fixture(data: Mapping[str, Any]) -> GameConfig:
    symbols = tuple(
        SymbolDefinition(
            mobile_code=symbol["mobileCode"],
            code=symbol["code"],
            name=symbol["name"],
            is_wildcard=symbol["isWildcard"],
            display_order=symbol["displayOrder"],
        )
        for symbol in data["symbols"]
    )
    return GameConfig(
        id=data["id"],
        code=data["code"],
        name=data["name"],
        rows=data["rows"],
        columns=data["columns"],
        spin_cost=data["spinCost"],
        signature_cell_width=data["signatureCellWidth"],
        symbols=symbols,
    )


def _assert_domain_error(expected_code: str, callback: Callable[[], object]) -> None:
    with pytest.raises(DomainValidationError) as captured:
        callback()
    assert captured.value.code == expected_code


def test_fixed_width_signature_golden_cases_encode_and_decode() -> None:
    codec = _load_fixture()["signatureCodec"]
    cell_width = codec["cellWidth"]

    for case in codec["fullCases"]:
        cells = tuple(case["cells"])
        signature = encode_signature(cells, cell_width)
        assert signature == case["expected"], case["name"]
        assert decode_signature(signature, cell_width, len(cells)) == cells

    assert codec["fullCases"][1]["expected"] != codec["fullCases"][2]["expected"]


def test_signature_prefix_golden_cases_are_deterministic() -> None:
    codec = _load_fixture()["signatureCodec"]

    for case in codec["prefixCases"]:
        assert (
            encode_signature_prefix(case["cells"], codec["cellWidth"])
            == case["expected"]
        ), case["name"]


def test_signature_codec_reports_stable_validation_codes() -> None:
    codec = _load_fixture()["signatureCodec"]

    for case in codec["invalidEncodeCases"]:
        if case.get("prefix") is True:
            _assert_domain_error(
                case["errorCode"],
                lambda case=case: encode_signature_prefix(
                    case["cells"], case["cellWidth"]
                ),
            )
        else:
            _assert_domain_error(
                case["errorCode"],
                lambda case=case: encode_signature(
                    case["cells"], case["cellWidth"]
                ),
            )

    for case in codec["invalidDecodeCases"]:
        _assert_domain_error(
            case["errorCode"],
            lambda case=case: decode_signature(
                case["signature"],
                case["cellWidth"],
                case.get("expectedCellCount"),
            ),
        )


def test_valid_shared_domain_configuration_passes_validation() -> None:
    validation = _load_fixture()["validation"]
    game = _game_from_fixture(validation["game"])
    paylines = tuple(
        PaylineDefinition(id=value["id"], row_path=tuple(value["rowPath"]))
        for value in validation["validPaylines"]
    )
    rules = tuple(
        PayoutRuleDefinition(
            symbol_mobile_code=value["symbolMobileCode"],
            match_length=value["matchLength"],
            payout_credits=value["payoutCredits"],
        )
        for value in validation["validPayoutRules"]
    )

    validate_game_config(game)
    validate_full_board(validation["fullBoard"], game)
    validate_board_prefix(validation["validPrefix"], game)
    validate_paylines(paylines, game)
    validate_payout_rules(rules, game)


def test_invalid_game_configuration_reports_shared_error_codes() -> None:
    validation = _load_fixture()["validation"]
    game = _game_from_fixture(validation["game"])
    field_mapping = {
        "rows": "rows",
        "spinCost": "spin_cost",
        "signatureCellWidth": "signature_cell_width",
    }

    for case in validation["invalidGamePatches"]:
        python_patch = {
            field_mapping[field_name]: value
            for field_name, value in case["patch"].items()
        }
        invalid_game = replace(game, **python_patch)
        _assert_domain_error(
            case["errorCode"],
            lambda invalid_game=invalid_game: validate_game_config(invalid_game),
        )


def test_invalid_board_prefixes_report_shared_error_codes() -> None:
    validation = _load_fixture()["validation"]
    game = _game_from_fixture(validation["game"])

    for case in validation["invalidPrefixes"]:
        _assert_domain_error(
            case["errorCode"],
            lambda case=case: validate_board_prefix(case["cells"], game),
        )


def test_invalid_full_boards_report_shared_error_codes() -> None:
    validation = _load_fixture()["validation"]
    game = _game_from_fixture(validation["game"])

    for case in validation["invalidFullBoards"]:
        _assert_domain_error(
            case["errorCode"],
            lambda case=case: validate_full_board(case["cells"], game),
        )


def test_invalid_paylines_report_shared_error_codes() -> None:
    validation = _load_fixture()["validation"]
    game = _game_from_fixture(validation["game"])

    for case in validation["invalidPaylines"]:
        paylines = tuple(
            PaylineDefinition(id=value["id"], row_path=tuple(value["rowPath"]))
            for value in case["paylines"]
        )
        _assert_domain_error(
            case["errorCode"],
            lambda paylines=paylines: validate_paylines(paylines, game),
        )


def test_invalid_payout_rules_report_shared_error_codes() -> None:
    validation = _load_fixture()["validation"]
    game = _game_from_fixture(validation["game"])

    for case in validation["invalidPayoutRules"]:
        rules = tuple(
            PayoutRuleDefinition(
                symbol_mobile_code=value["symbolMobileCode"],
                match_length=value["matchLength"],
                payout_credits=value["payoutCredits"],
            )
            for value in case["rules"]
        )
        _assert_domain_error(
            case["errorCode"],
            lambda rules=rules: validate_payout_rules(rules, game),
        )
