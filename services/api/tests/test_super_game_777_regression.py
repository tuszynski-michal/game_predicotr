"""Byte-for-byte regression of a game without a super game kind (TASK-0936).

The per-position mode projection must not change anything for 777: a game with
``super_game_kind = none`` keeps the same approximate-win numbers, the same
frozen management payload and content digest, the same stored summary and the
same pin values as before the projection existed.

The expected constants were produced by running :func:`build_777_snapshot`
against the code of v1.7.279 (before TASK-0936) and against this code; both
printed the same values. The fixture is the v3 golden game of
``packages/domain-fixtures/payout-golden-cases.json`` (a 777-like game: no
trigger symbol, one Wild) with its golden boards placed on a wrapped range,
including partial and missing boards.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Collection
from pathlib import Path
from typing import Any
from uuid import UUID

from game_predictor_api.application.board_search_approximate_win import (
    BoardSearchApproximateWinService,
)
from game_predictor_api.domain.board_search_approximate_win import ApproximateWinDocument
from game_predictor_api.domain.rules import RulesVersionStatus
from game_predictor_api.domain.super_game_markers import NO_SUPER_GAME_STATE, SuperGameMarkers
from game_predictor_api.schemas.board_search_approximate_win import to_approximate_win_response
from game_predictor_api.storage.management_result_snapshots import (
    expand_result,
    freeze_result,
    pin_values,
)
from game_predictor_worker.domain.contracts import (
    PaylineDefinition,
    PayoutRuleDefinition,
    PayoutSymbolDefinition,
    SymbolDefinition,
)
from game_predictor_worker.payouts.contracts import RulesPayoutConfiguration
from test_board_search_approximate_win_api import MemoryBoardSearchApproximateWinRepository

_FIXTURE = Path(__file__).parents[3] / "packages" / "domain-fixtures" / "payout-golden-cases.json"
_GAME_ID = UUID(int=0x777)
_RULES_VERSION_ID = UUID(int=0x7771)
_SEQUENCE_LENGTH = 40
_START = 30
_SPIN_COUNT = 25
_PINS = [0, 1, 5, 9, 10, 17, 25, 30]

EXPECTED_CONTENT_SHA256 = "23623fe2657a53f1625a1527ddb6c306a61710e8f7de1961605a8f6a29b26338"
EXPECTED_CANONICAL_SHA256 = "5803ac3420c6f774716a45dfd69a6e3d2ec78a5b1c42ed0a0e4bcdc4d3402827"

# Keys the TASK-0936 response adds; the old response never had them.
_NEW_SUMMARY_KEYS = (
    "provisionalCount",
    "provisionalPayoutCredits",
    "superSpinRanges",
    "superSpinCost",
)
_NEW_ROW_KEYS = ("mode", "spinCostCredits")


class NoSuperGameMarkers:
    """What the marker repository returns for a game of kind ``none``."""

    def markers(self, game_id: UUID, positions: Collection[int]) -> SuperGameMarkers:
        return SuperGameMarkers(state=NO_SUPER_GAME_STATE)


def _configuration() -> RulesPayoutConfiguration:
    fixture = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    game = fixture["game"]
    return RulesPayoutConfiguration(
        rules_version_id=_RULES_VERSION_ID,
        rules_game_id=_GAME_ID,
        version=7,
        status=RulesVersionStatus.PUBLISHED,
        rows=game["rows"],
        columns=game["columns"],
        spin_cost=game["spinCost"],
        symbols=tuple(
            SymbolDefinition(
                mobile_code=symbol["mobileCode"],
                code=symbol["code"],
                name=symbol["name"],
                is_wildcard=symbol["isWildcard"],
                display_order=symbol["displayOrder"],
            )
            for symbol in game["symbols"]
        ),
        paylines=tuple(
            PaylineDefinition(id=payline["id"], row_path=tuple(payline["rowPath"]))
            for payline in fixture["paylines"]
        ),
        payout_symbols=tuple(
            PayoutSymbolDefinition(
                symbol_mobile_code=value["symbolMobileCode"],
                minimum_match_length=value["minimumMatchLength"],
            )
            for value in fixture["payoutSymbols"]
        ),
        payout_rules=tuple(
            PayoutRuleDefinition(
                symbol_mobile_code=value["symbolMobileCode"],
                match_length=value["matchLength"],
                payout_credits=value["payoutCredits"],
            )
            for value in fixture["payoutRules"]
        ),
    )


def _documents() -> tuple[ApproximateWinDocument, ...]:
    fixture = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    boards = [
        tuple(None if cell == 0 else cell for row in case["rows"] for cell in row)
        for case in fixture["cases"]
    ]
    documents: list[ApproximateWinDocument] = []
    for sequence_number in range(1, _SEQUENCE_LENGTH + 1):
        if sequence_number % 7 == 3:
            continue  # a missing board
        board = boards[sequence_number % len(boards)]
        if sequence_number % 5 == 0:
            # a partial board: the right part of the middle row is unknown
            board = tuple(None if index in (8, 9) else code for index, code in enumerate(board))
        documents.append(
            ApproximateWinDocument(
                sequence_number=sequence_number,
                status="accepted" if sequence_number % 2 else "pending",
                board_checksum_sha256=f"{sequence_number:0>64}",
                mobile_codes=board,
            )
        )
    return tuple(documents)


def _old_shape(response: dict[str, Any]) -> dict[str, Any]:
    old = dict(response)
    old["summary"] = {
        key: value for key, value in response["summary"].items() if key not in _NEW_SUMMARY_KEYS
    }
    old["rows"] = [
        {key: value for key, value in row.items() if key not in _NEW_ROW_KEYS}
        for row in response["rows"]
    ]
    return old


def build_777_snapshot() -> dict[str, Any]:
    """Everything a 777 stake save stores and every number it shows."""

    configuration = _configuration()
    repository = MemoryBoardSearchApproximateWinRepository(
        _GAME_ID,
        sequence_length=_SEQUENCE_LENGTH,
        configuration=configuration,
        documents=_documents(),
    )
    calculation = to_approximate_win_response(
        BoardSearchApproximateWinService(repository, NoSuperGameMarkers()).calculate(
            game_id=_GAME_ID,
            start_sequence_number=_START,
            requested_spin_count=_SPIN_COUNT,
        )
    )
    start = next(document for document in _documents() if document.sequence_number == _START)
    codes = {symbol.mobile_code: symbol.code for symbol in configuration.symbols}
    symbols = tuple(None if code is None else codes[code] for code in start.mobile_codes)
    digest, payload, summary = freeze_result(
        calculation, configuration, symbols, start.board_checksum_sha256
    )
    return {
        "digest": digest,
        "payload": payload,
        "summary": summary,
        "pins": pin_values(payload, _PINS),
        "response": _old_shape(calculation.model_dump(mode="json", by_alias=True)),
        "expanded": _old_shape(expand_result(payload).model_dump(mode="json", by_alias=True)),
    }


def _canonical(snapshot: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def test_777_frozen_payload_and_digest_are_byte_identical() -> None:
    snapshot = build_777_snapshot()
    assert snapshot["digest"] == EXPECTED_CONTENT_SHA256
    # TASK-0940 adds two computed pin fields, outside the frozen result payload.
    # Preserve the original byte-level assertion for every legacy field rather
    # than recording a new baseline for the old contract.
    compact_fields = {"requiredStakeCredits", "machineCashCredits"}
    legacy = {
        **snapshot,
        "pins": [
            {key: value for key, value in pin.items() if key not in compact_fields}
            for pin in snapshot["pins"]
        ],
    }
    assert _canonical(legacy) == EXPECTED_CANONICAL_SHA256
    assert (
        _canonical(snapshot) == "0cb8eaab254e5816d7fdfd5c96105f5a0d73d7e7b59a02c77a582fcd77b279eb"
    )


def test_777_payload_carries_no_super_game_keys_and_every_row_is_base_mode() -> None:
    snapshot = build_777_snapshot()
    payload = snapshot["payload"]
    assert "superSpinRanges" not in payload
    assert "superSpinCost" not in payload
    assert set(payload["calculation"]["summary"]) == {
        "recognizedPayoutCredits",
        "spinCostCredits",
        "balanceCredits",
    }
    expanded = expand_result(payload)
    assert expanded.rows
    assert {(row.mode, row.spin_cost_credits) for row in expanded.rows} == {("base", 10)}
    assert expanded.summary.provisional_count == 0
    assert expanded.summary.spin_cost_credits == expanded.evaluated_spin_count * 10


if __name__ == "__main__":  # pragma: no cover - used to record the constants
    result = build_777_snapshot()
    print(result["digest"], _canonical(result))
