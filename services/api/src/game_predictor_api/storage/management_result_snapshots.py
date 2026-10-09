"""Versioned compact numeric snapshots; timestamps never affect semantic identity.

Super game series (TASK-0936, D-537) extend format 1 only with optional summary
keys: ``provisionalCount``/``provisionalPayoutCredits`` and the free spins of
the range (``superSpinRanges``/``superSpinCost``). They are written only when
they carry information, so the payload and content digest of a game without a
super game kind (777) stay byte-identical to the ones written before.
"""

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


_PROVISIONAL_SUMMARY_FIELDS = ("provisionalCount", "provisionalPayoutCredits")
_SUPER_SPIN_SUMMARY_FIELDS = ("superSpinRanges", "superSpinCost")


def _compact_summary(summary: dict[str, Any]) -> dict[str, Any]:
    """The summary without the TASK-0936 fields that carry no information
    (zero provisional values, no free spins): absent before TASK-0936."""

    dropped: set[str] = set()
    if all(not summary.get(key) for key in _PROVISIONAL_SUMMARY_FIELDS):
        dropped.update(_PROVISIONAL_SUMMARY_FIELDS)
    if not summary.get("superSpinRanges"):
        dropped.update(_SUPER_SPIN_SUMMARY_FIELDS)
    return {key: value for key, value in summary.items() if key not in dropped}


def freeze_result(
    calculation: ApproximateWinResponse,
    configuration: RulesPayoutConfiguration,
    start_symbols: tuple[str | None, ...],
    start_checksum: str,
) -> tuple[str, dict[str, object], dict[str, object]]:
    expanded = calculation.model_dump(mode="json", by_alias=True)
    rows = expanded.pop("rows")
    # Frozen results are historical: neither the generation's freshness nor
    # row markers belong to their identity (TASK-0935).
    expanded.pop("superGameState", None)
    expanded["summary"] = _compact_summary(expanded["summary"])
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
        # A provisional payout is not part of the cumulative balance (D-537).
        paid = 0 if row.payout_kind == "provisional" else row.payout_credits
        points.extend(
            [
                (row.spin_number, row.cumulative_balance_credits - paid),
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
        "summary": _compact_summary(calculation.summary.model_dump(mode="json", by_alias=True)),
        "startSymbolCodes": list(start_symbols),
        "evaluatedSpinCount": calculation.evaluated_spin_count,
        "spinCost": calculation.rules.spin_cost,
        "chartPoints": [
            {"spinNumber": spin, "balanceCredits": balance} for spin, balance in points
        ],
    }
    return digest, payload, summary


def _super_spin_ranges(payload: dict[str, Any]) -> tuple[tuple[int, int], ...]:
    summary = payload["calculation"]["summary"]
    return tuple(
        (int(value["startSpin"]), int(value["endSpin"]))
        for value in summary.get("superSpinRanges", ())
    )


def _super_spin_cost(payload: dict[str, Any]) -> int:
    return int(payload["calculation"]["summary"].get("superSpinCost", 0))


def _super_spins_up_to(ranges: tuple[tuple[int, int], ...], spin: int) -> int:
    return sum(max(0, min(last, spin) - first + 1) for first, last in ranges)


def pin_values(payload: dict[str, Any], pins: list[int]) -> list[dict[str, Any]]:
    """Exact numeric values at saved spins, independent of reduced preview polyline.

    Spins inside a super game series cost the frozen ``superSpinCost`` instead
    of the rules' spin cost (TASK-0936)."""
    result = expand_result(payload)
    ranges = _super_spin_ranges(payload)
    super_cost = _super_spin_cost(payload)
    values = []
    for pin in pins:
        cumulative = 0
        for row in result.rows:
            if row.spin_number > pin:
                break
            cumulative = row.cumulative_payout_credits
        super_spins = _super_spins_up_to(ranges, pin)
        cost = (pin - super_spins) * result.rules.spin_cost + super_spins * super_cost
        values.append(
            {
                "spinNumber": pin,
                "balanceCredits": cumulative - cost,
                "available": pin <= result.evaluated_spin_count,
            }
        )
    return values


def expand_result(payload: dict[str, Any]) -> ApproximateWinResponse:
    """The frozen calculation; each row's mode and spin cost are derived from
    the frozen super spin ranges (every row is base mode without them)."""

    if payload["formatVersion"] != 1 or tuple(payload["rowFields"]) != ROW_FIELDS:
        raise ValueError("Unsupported management result snapshot format.")
    ranges = _super_spin_ranges(payload)
    super_cost = _super_spin_cost(payload)
    spin_cost = int(payload["calculation"]["rules"]["spinCost"])
    rows = []
    for values in payload["rows"]:
        row = dict(zip(ROW_FIELDS, values, strict=True))
        is_super = any(first <= row["spinNumber"] <= last for first, last in ranges)
        row["mode"] = "super" if is_super else "base"
        row["spinCostCredits"] = super_cost if is_super else spin_cost
        rows.append(row)
    return ApproximateWinResponse.model_validate({**payload["calculation"], "rows": rows})
