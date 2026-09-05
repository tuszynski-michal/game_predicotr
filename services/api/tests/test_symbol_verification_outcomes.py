from __future__ import annotations

from uuid import UUID

import pytest
from game_predictor_api.domain.image_symbol_reviews import (
    SymbolCellAssignmentSource,
    SymbolCellQualityIssue,
    SymbolCellReviewState,
)
from game_predictor_api.domain.symbol_verification_outcomes import (
    SymbolCellVerification,
    SymbolVerificationOutcome,
    SymbolVerificationOutcomeError,
    project_legacy_verification,
)

SYMBOL_ID = UUID("10000000-0000-0000-0000-000000000001")


def test_only_verified_symbol_can_carry_a_catalog_symbol_id() -> None:
    verified = SymbolCellVerification.verified_symbol(SYMBOL_ID)

    assert verified.outcome is SymbolVerificationOutcome.VERIFIED_SYMBOL
    assert verified.assigned_symbol_id == SYMBOL_ID
    assert verified.verified_symbol_id == SYMBOL_ID
    assert verified.is_human_resolved is True

    for outcome in SymbolVerificationOutcome:
        if outcome is SymbolVerificationOutcome.VERIFIED_SYMBOL:
            continue
        with pytest.raises(SymbolVerificationOutcomeError) as error:
            SymbolCellVerification(outcome=outcome, assigned_symbol_id=SYMBOL_ID)
        assert error.value.code == "SYMBOL_VERIFICATION_SYMBOL_FORBIDDEN"

    with pytest.raises(SymbolVerificationOutcomeError) as missing_error:
        SymbolCellVerification(outcome=SymbolVerificationOutcome.VERIFIED_SYMBOL)
    assert missing_error.value.code == "SYMBOL_VERIFICATION_SYMBOL_REQUIRED"


def test_unknown_and_unreadable_have_distinct_resolution_semantics() -> None:
    unassigned = SymbolCellVerification.unassigned()
    unknown = SymbolCellVerification.from_model_result(has_prediction=False)
    unreadable = SymbolCellVerification.unreadable()

    assert unassigned.outcome is SymbolVerificationOutcome.UNASSIGNED
    assert unassigned.is_human_resolved is False
    assert unassigned != unknown
    assert unknown.outcome is SymbolVerificationOutcome.UNKNOWN
    assert unknown.is_human_resolved is False
    assert unknown.verified_symbol_id is None
    assert unreadable.outcome is SymbolVerificationOutcome.UNREADABLE
    assert unreadable.is_human_resolved is True
    assert unreadable.verified_symbol_id is None


def test_model_prediction_requires_review_without_assigning_the_prediction() -> None:
    verification = SymbolCellVerification.from_model_result(has_prediction=True)

    assert verification == SymbolCellVerification(outcome=SymbolVerificationOutcome.REQUIRES_REVIEW)
    assert verification.assigned_symbol_id is None
    assert verification.is_human_resolved is False


def test_grid_issue_is_independent_from_symbol_readability() -> None:
    grid_issue = SymbolCellVerification.grid_issue()

    assert grid_issue.outcome is SymbolVerificationOutcome.GRID_ISSUE
    assert grid_issue != SymbolCellVerification.unreadable()
    assert grid_issue != SymbolCellVerification.from_model_result(has_prediction=True)
    assert grid_issue.is_human_resolved is False


@pytest.mark.parametrize(
    ("review_state", "quality_issue", "assigned_symbol_id", "prediction_present", "expected"),
    (
        (
            SymbolCellReviewState.PENDING,
            None,
            SYMBOL_ID,
            True,
            SymbolVerificationOutcome.REQUIRES_REVIEW,
        ),
        (
            SymbolCellReviewState.PENDING,
            None,
            None,
            False,
            SymbolVerificationOutcome.UNKNOWN,
        ),
        (
            SymbolCellReviewState.PENDING,
            SymbolCellQualityIssue.GRID_ISSUE,
            SYMBOL_ID,
            True,
            SymbolVerificationOutcome.GRID_ISSUE,
        ),
        (
            SymbolCellReviewState.PENDING,
            SymbolCellQualityIssue.UNREADABLE,
            SYMBOL_ID,
            True,
            SymbolVerificationOutcome.UNREADABLE,
        ),
        (
            SymbolCellReviewState.APPROVED,
            SymbolCellQualityIssue.UNREADABLE,
            None,
            False,
            SymbolVerificationOutcome.UNREADABLE,
        ),
        (
            SymbolCellReviewState.APPROVED,
            SymbolCellQualityIssue.UNREADABLE,
            SYMBOL_ID,
            False,
            SymbolVerificationOutcome.VERIFIED_SYMBOL,
        ),
        (
            SymbolCellReviewState.APPROVED,
            None,
            SYMBOL_ID,
            True,
            SymbolVerificationOutcome.VERIFIED_SYMBOL,
        ),
    ),
)
def test_legacy_projection_maps_unambiguous_states(
    review_state: SymbolCellReviewState,
    quality_issue: SymbolCellQualityIssue | None,
    assigned_symbol_id: UUID | None,
    prediction_present: bool,
    expected: SymbolVerificationOutcome,
) -> None:
    projected = project_legacy_verification(
        review_state=review_state,
        quality_issue=quality_issue,
        assigned_symbol_id=assigned_symbol_id,
        prediction_present=prediction_present,
        assignment_source=SymbolCellAssignmentSource.MODEL,
    )

    assert projected.outcome is expected
    assert projected.assigned_symbol_id == (
        SYMBOL_ID if expected is SymbolVerificationOutcome.VERIFIED_SYMBOL else None
    )


def test_legacy_approved_null_without_unreadable_evidence_is_ambiguous() -> None:
    with pytest.raises(SymbolVerificationOutcomeError) as error:
        project_legacy_verification(
            review_state=SymbolCellReviewState.APPROVED,
            quality_issue=None,
            assigned_symbol_id=None,
            prediction_present=False,
            assignment_source=SymbolCellAssignmentSource.HUMAN,
        )

    assert error.value.code == "SYMBOL_VERIFICATION_LEGACY_APPROVED_NULL_AMBIGUOUS"


def test_legacy_pending_human_assignment_is_ambiguous() -> None:
    with pytest.raises(SymbolVerificationOutcomeError) as error:
        project_legacy_verification(
            review_state=SymbolCellReviewState.PENDING,
            quality_issue=None,
            assigned_symbol_id=SYMBOL_ID,
            prediction_present=True,
            assignment_source=SymbolCellAssignmentSource.HUMAN,
        )

    assert error.value.code == "SYMBOL_VERIFICATION_LEGACY_PENDING_ASSIGNMENT_AMBIGUOUS"


def test_legacy_pending_model_assignment_without_prediction_is_ambiguous() -> None:
    with pytest.raises(SymbolVerificationOutcomeError) as error:
        project_legacy_verification(
            review_state=SymbolCellReviewState.PENDING,
            quality_issue=None,
            assigned_symbol_id=SYMBOL_ID,
            prediction_present=False,
            assignment_source=SymbolCellAssignmentSource.MODEL,
        )

    assert error.value.code == "SYMBOL_VERIFICATION_LEGACY_PENDING_ASSIGNMENT_AMBIGUOUS"


def test_question_mark_is_not_an_outcome_or_assigned_symbol() -> None:
    assert "?" not in {outcome.value for outcome in SymbolVerificationOutcome}
    with pytest.raises(SymbolVerificationOutcomeError) as error:
        SymbolCellVerification(  # type: ignore[arg-type]
            outcome=SymbolVerificationOutcome.VERIFIED_SYMBOL,
            assigned_symbol_id="?",
        )
    assert error.value.code == "SYMBOL_VERIFICATION_SYMBOL_REQUIRED"
