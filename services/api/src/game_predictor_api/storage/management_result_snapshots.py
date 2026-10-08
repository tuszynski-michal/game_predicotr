"""Versioned compact numeric snapshots; timestamps never affect semantic identity."""

import hashlib
import json
from dataclasses import asdict
from typing import Any

from game_predictor_worker.payouts.contracts import RulesPayoutConfiguration

from game_predictor_api.schemas.board_search_approximate_win import ApproximateWinResponse

ROW_FIELDS = (
    "spinNumber",
    "sequenceNumber",
    "payoutCredits",
    "cumulativePayoutCredits",
    "cumulativeCostCredits",
    "cumulativeBalanceCredits",
    "payoutKind",
    "boardStatus",
)


def json_value(value: object) -> Any:
    return json.loads(json.dumps(value, default=str, sort_keys=True))


def rules_snapshot(configuration: RulesPayoutConfiguration) -> Any:
    """JSON rules snapshot of a frozen result.

    `super_game_trigger_count` (TASK-0932) is kept only for trigger symbols,
    so snapshots and content digests of games without a trigger symbol stay
    byte-identical to those written before it existed.
    """

    snapshot = json_value(asdict(configuration))
    for symbol in snapshot["symbols"]:
        if symbol.get("super_game_trigger_count") is None:
            symbol.pop("super_game_trigger_count", None)
    return snapshot


def freeze_result(
    calculation: ApproximateWinResponse,
    configuration: RulesPayoutConfiguration,
    start_symbols: tuple[str | None, ...],
    start_checksum: str,
) -> tuple[str, dict[str, object], dict[str, object]]:
    expanded = calculation.model_dump(mode="json", by_alias=True)
    rows = expanded.pop("rows")
    payload: dict[str, object] = {
        "formatVersion": 1,
        "calculation": expanded,
        "rowFields": list(ROW_FIELDS),
        "rows": [[row[key] for key in ROW_FIELDS] for row in rows],
        "startSymbolCodes": list(start_symbols),
        "startBoardChecksumSha256": start_checksum,
        "rulesSnapshot": rules_snapshot(configuration),
    }
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    points = [(0, 0)]
    for row in calculation.rows:
        points.extend(
            [
                (row.spin_number, row.cumulative_balance_credits - row.payout_credits),
                (row.spin_number, row.cumulative_balance_credits),
            ]
        )
    points.append((calculation.evaluated_spin_count, calculation.summary.balance_credits))
    # Keep endpoints and each bucket's extremes, with at most 256 numeric points.
    if len(points) > 256:
        interior = points[1:-1]
        reduced = [points[0]]
        for index in range(127):
            first = index * len(interior) // 127
            last = (index + 1) * len(interior) // 127
            chunk = interior[first:last]
            low = min(range(len(chunk)), key=lambda position: chunk[position][1])
            high = max(range(len(chunk)), key=lambda position: chunk[position][1])
            reduced.extend(chunk[position] for position in sorted({low, high}))
        points = [*reduced, points[-1]]
    summary: dict[str, object] = {
        "summary": calculation.summary.model_dump(mode="json", by_alias=True),
        "startSymbolCodes": list(start_symbols),
        "evaluatedSpinCount": calculation.evaluated_spin_count,
        "spinCost": calculation.rules.spin_cost,
        "chartPoints": [
            {"spinNumber": spin, "balanceCredits": balance} for spin, balance in points
        ],
    }
    return digest, payload, summary


def pin_values(payload: dict[str, Any], pins: list[int]) -> list[dict[str, Any]]:
    """Exact numeric values at saved spins, independent of reduced preview polyline."""
    result = expand_result(payload)
    values = []
    for pin in pins:
        cumulative = 0
        for row in result.rows:
            if row.spin_number > pin:
                break
            cumulative = row.cumulative_payout_credits
        values.append(
            {
                "spinNumber": pin,
                "balanceCredits": cumulative - pin * result.rules.spin_cost,
                "available": pin <= result.evaluated_spin_count,
            }
        )
    return values


def expand_result(payload: dict[str, Any]) -> ApproximateWinResponse:
    if payload["formatVersion"] != 1 or tuple(payload["rowFields"]) != ROW_FIELDS:
        raise ValueError("Unsupported management result snapshot format.")
    return ApproximateWinResponse.model_validate(
        {
            **payload["calculation"],
            "rows": [dict(zip(ROW_FIELDS, row, strict=True)) for row in payload["rows"]],
        }
    )
