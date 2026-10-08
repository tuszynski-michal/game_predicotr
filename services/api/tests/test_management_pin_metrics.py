"""One numerical contract executed by Python and the existing TS chart helpers."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from game_predictor_api.domain.management_pin_metrics import approximate_win_pin_metrics

CASES = json.loads(
    (
        Path(__file__).resolve().parents[3]
        / "packages/domain-fixtures/management-pin-metric-cases.json"
    ).read_text(encoding="utf-8")
)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_chart_and_cached_metrics_share_golden_cases(case):
    result = SimpleNamespace(
        rules=SimpleNamespace(spin_cost=case["spinCost"]),
        evaluated_spin_count=case["evaluatedSpinCount"],
        rows=[
            SimpleNamespace(
                spin_number=row["spinNumber"],
                payout_credits=row["payoutCredits"],
                cumulative_payout_credits=row["cumulativePayoutCredits"],
                cumulative_balance_credits=row["cumulativeBalanceCredits"],
            )
            for row in case["rows"]
        ],
    )
    assert approximate_win_pin_metrics(result, case["spin"]) == (
        case["net"],
        case["required"],
        case["cash"],
    )
