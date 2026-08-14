"""Pure payout completeness report and reusable snapshot gate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from game_predictor_api.domain.datasets import DatasetVersionStatus
from game_predictor_api.domain.rules import RulesVersionStatus

PAYOUT_DIAGNOSTIC_LIMIT = 100
SUPPORTED_PAYOUT_ALGORITHM = "payout-v2"


@dataclass(frozen=True, slots=True)
class PayoutCompletenessFacts:
    dataset_version_id: UUID
    rules_version_id: UUID
    algorithm_version: str
    dataset_game_id: UUID
    rules_game_id: UUID
    dataset_status: DatasetVersionStatus
    rules_status: RulesVersionStatus
    dataset_rows: int
    dataset_columns: int
    rules_rows: int
    rules_columns: int
    layout_count: int
    payout_count: int
    missing_payout_count: int
    missing_sequence_numbers: tuple[int, ...]
    missing_sequences_truncated: bool
    missing_audit_count: int


@dataclass(frozen=True, slots=True)
class PayoutReadinessIssue:
    code: str
    message: str
    details: dict[str, object]


@dataclass(frozen=True, slots=True)
class PayoutReadinessReport:
    dataset_version_id: UUID
    rules_version_id: UUID
    algorithm_version: str
    ready: bool
    layout_count: int
    payout_count: int
    missing_payout_count: int
    missing_sequence_numbers: tuple[int, ...]
    missing_sequences_truncated: bool
    missing_audit_count: int
    issues: tuple[PayoutReadinessIssue, ...]


class PayoutCompletenessRepository(Protocol):
    def get_completeness_facts(
        self,
        dataset_version_id: UUID,
        rules_version_id: UUID,
        algorithm_version: str,
    ) -> PayoutCompletenessFacts | None: ...


class PayoutReadinessError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        report: PayoutReadinessReport | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.report = report


class PayoutReadinessService:
    def __init__(self, repository: PayoutCompletenessRepository) -> None:
        self._repository = repository

    def assess(
        self,
        dataset_version_id: UUID,
        rules_version_id: UUID,
        algorithm_version: str,
    ) -> PayoutReadinessReport:
        facts = self._repository.get_completeness_facts(
            dataset_version_id,
            rules_version_id,
            algorithm_version,
        )
        if facts is None:
            raise PayoutReadinessError(
                "PAYOUT_SOURCE_NOT_FOUND",
                "The payout dataset or rules version does not exist.",
            )
        return assess_payout_completeness(facts)

    def require(
        self,
        dataset_version_id: UUID,
        rules_version_id: UUID,
        algorithm_version: str,
    ) -> PayoutReadinessReport:
        report = self.assess(
            dataset_version_id,
            rules_version_id,
            algorithm_version,
        )
        if not report.ready:
            raise PayoutReadinessError(
                "PAYOUTS_NOT_READY",
                "The selected payout set is not ready for a snapshot.",
                report=report,
            )
        return report


def assess_payout_completeness(
    facts: PayoutCompletenessFacts,
) -> PayoutReadinessReport:
    issues: list[PayoutReadinessIssue] = []

    def add_issue(code: str, message: str, **details: object) -> None:
        issues.append(PayoutReadinessIssue(code, message, details))

    if facts.algorithm_version != SUPPORTED_PAYOUT_ALGORITHM:
        add_issue(
            "UNSUPPORTED_PAYOUT_ALGORITHM",
            f"Only {SUPPORTED_PAYOUT_ALGORITHM} is supported.",
            algorithmVersion=facts.algorithm_version,
        )
    if facts.dataset_status is not DatasetVersionStatus.PUBLISHED:
        add_issue(
            "PAYOUT_DATASET_NOT_PUBLISHED",
            "Payout readiness requires a published dataset.",
            status=facts.dataset_status.value,
        )
    if facts.rules_status is not RulesVersionStatus.PUBLISHED:
        add_issue(
            "PAYOUT_RULES_NOT_PUBLISHED",
            "Payout readiness requires published rules.",
            status=facts.rules_status.value,
        )
    if facts.dataset_game_id != facts.rules_game_id:
        add_issue(
            "PAYOUT_GAME_MISMATCH",
            "The payout dataset and rules must belong to the same game.",
            datasetGameId=str(facts.dataset_game_id),
            rulesGameId=str(facts.rules_game_id),
        )
    if facts.dataset_rows != facts.rules_rows or facts.dataset_columns != facts.rules_columns:
        add_issue(
            "PAYOUT_DIMENSIONS_MISMATCH",
            "The payout dataset and rules dimensions must match.",
            datasetRows=facts.dataset_rows,
            datasetColumns=facts.dataset_columns,
            rulesRows=facts.rules_rows,
            rulesColumns=facts.rules_columns,
        )
    if facts.payout_count != facts.layout_count:
        add_issue(
            "PAYOUT_COUNT_MISMATCH",
            "Every layout must have exactly one payout for the selected versions.",
            expectedCount=facts.layout_count,
            actualCount=facts.payout_count,
        )
    if facts.missing_payout_count:
        add_issue(
            "MISSING_LAYOUT_PAYOUTS",
            "Some layouts do not have a payout for the selected versions.",
            issueCount=facts.missing_payout_count,
            sequenceNumbers=list(facts.missing_sequence_numbers),
            truncated=facts.missing_sequences_truncated,
        )
    if facts.missing_audit_count:
        add_issue(
            "MISSING_PAYOUT_AUDIT",
            "Some selected payouts do not reference a structural audit.",
            issueCount=facts.missing_audit_count,
        )

    return PayoutReadinessReport(
        dataset_version_id=facts.dataset_version_id,
        rules_version_id=facts.rules_version_id,
        algorithm_version=facts.algorithm_version,
        ready=not issues,
        layout_count=facts.layout_count,
        payout_count=facts.payout_count,
        missing_payout_count=facts.missing_payout_count,
        missing_sequence_numbers=facts.missing_sequence_numbers,
        missing_sequences_truncated=facts.missing_sequences_truncated,
        missing_audit_count=facts.missing_audit_count,
        issues=tuple(issues),
    )
