from __future__ import annotations

from dataclasses import replace
from uuid import UUID

import pytest
from game_predictor_api.domain.datasets import DatasetVersionStatus
from game_predictor_api.domain.rules import RulesVersionStatus
from game_predictor_worker.payouts.readiness import (
    PayoutCompletenessFacts,
    PayoutReadinessError,
    PayoutReadinessService,
    assess_payout_completeness,
)

DATASET_ID = UUID("11111111-1111-4111-8111-111111111111")
RULES_ID = UUID("22222222-2222-4222-8222-222222222222")
GAME_ID = UUID("33333333-3333-4333-8333-333333333333")


class FakeCompletenessRepository:
    def __init__(self, facts: PayoutCompletenessFacts | None) -> None:
        self.facts = facts
        self.calls: list[tuple[UUID, UUID, str]] = []

    def get_completeness_facts(
        self,
        dataset_version_id: UUID,
        rules_version_id: UUID,
        algorithm_version: str,
    ) -> PayoutCompletenessFacts | None:
        self.calls.append(
            (dataset_version_id, rules_version_id, algorithm_version)
        )
        return self.facts


def _facts(**changes: object) -> PayoutCompletenessFacts:
    facts = PayoutCompletenessFacts(
        dataset_version_id=DATASET_ID,
        rules_version_id=RULES_ID,
        algorithm_version="payout-v2",
        dataset_game_id=GAME_ID,
        rules_game_id=GAME_ID,
        dataset_status=DatasetVersionStatus.PUBLISHED,
        rules_status=RulesVersionStatus.PUBLISHED,
        dataset_rows=3,
        dataset_columns=5,
        rules_rows=3,
        rules_columns=5,
        layout_count=500_000,
        payout_count=500_000,
        missing_payout_count=0,
        missing_sequence_numbers=(),
        missing_sequences_truncated=False,
        missing_audit_count=0,
    )
    return replace(facts, **changes)


def test_complete_exact_version_is_ready() -> None:
    report = assess_payout_completeness(_facts())

    assert report.ready is True
    assert report.layout_count == 500_000
    assert report.payout_count == 500_000
    assert report.issues == ()


def test_report_returns_every_version_status_and_integrity_blocker() -> None:
    other_game = UUID("44444444-4444-4444-8444-444444444444")
    report = assess_payout_completeness(
        _facts(
            algorithm_version="payout-v1",
            dataset_status=DatasetVersionStatus.ARCHIVED,
            rules_status=RulesVersionStatus.ARCHIVED,
            rules_game_id=other_game,
            rules_columns=4,
            payout_count=499_998,
            missing_payout_count=2,
            missing_sequence_numbers=(7, 400_001),
            missing_sequences_truncated=False,
            missing_audit_count=3,
        )
    )

    assert report.ready is False
    assert [issue.code for issue in report.issues] == [
        "UNSUPPORTED_PAYOUT_ALGORITHM",
        "PAYOUT_DATASET_NOT_PUBLISHED",
        "PAYOUT_RULES_NOT_PUBLISHED",
        "PAYOUT_GAME_MISMATCH",
        "PAYOUT_DIMENSIONS_MISMATCH",
        "PAYOUT_COUNT_MISMATCH",
        "MISSING_LAYOUT_PAYOUTS",
        "MISSING_PAYOUT_AUDIT",
    ]
    missing = report.issues[6]
    assert missing.details == {
        "issueCount": 2,
        "sequenceNumbers": [7, 400_001],
        "truncated": False,
    }


def test_report_preserves_bounded_sample_and_exact_counts() -> None:
    sample = tuple(range(1, 101))
    report = assess_payout_completeness(
        _facts(
            payout_count=499_800,
            missing_payout_count=200,
            missing_sequence_numbers=sample,
            missing_sequences_truncated=True,
        )
    )

    assert report.missing_payout_count == 200
    assert report.missing_sequence_numbers == sample
    assert report.missing_sequences_truncated is True


def test_service_requires_complete_report_and_preserves_it_on_error() -> None:
    facts = _facts(
        payout_count=499_999,
        missing_payout_count=1,
        missing_sequence_numbers=(123,),
    )
    repository = FakeCompletenessRepository(facts)
    service = PayoutReadinessService(repository)

    with pytest.raises(PayoutReadinessError) as captured:
        service.require(DATASET_ID, RULES_ID, "payout-v2")

    assert captured.value.code == "PAYOUTS_NOT_READY"
    assert captured.value.report is not None
    assert captured.value.report.missing_sequence_numbers == (123,)
    assert repository.calls == [(DATASET_ID, RULES_ID, "payout-v2")]


def test_service_reports_missing_source_with_stable_error() -> None:
    service = PayoutReadinessService(FakeCompletenessRepository(None))

    with pytest.raises(PayoutReadinessError) as captured:
        service.assess(DATASET_ID, RULES_ID, "payout-v2")

    assert captured.value.code == "PAYOUT_SOURCE_NOT_FOUND"
