"""Versioned logical outcomes for one symbol-cell verification.

This module deliberately separates a verified catalog symbol from states that
have no logical symbol assignment.  The question mark used by clients is only
a presentation choice and never crosses this domain boundary as a symbol.

Persistence still uses the v1 combination of ``review_state``,
``quality_issue`` and ``assigned_symbol_id``.  ``project_legacy_verification``
is the fail-closed compatibility adapter until an additive schema correction is
designed after the ownership review.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from game_predictor_api.domain.image_symbol_reviews import (
    SymbolCellAssignmentSource,
    SymbolCellQualityIssue,
    SymbolCellReviewState,
)

SYMBOL_VERIFICATION_OUTCOME_CONTRACT_VERSION = "symbol-verification-outcome-v2"


class SymbolVerificationOutcome(StrEnum):
    """Mutually exclusive logical outcome of a symbol-cell workflow."""

    UNASSIGNED = "unassigned"
    UNKNOWN = "unknown"
    UNREADABLE = "unreadable"
    GRID_ISSUE = "grid_issue"
    REQUIRES_REVIEW = "requires_review"
    VERIFIED_SYMBOL = "verified_symbol"


class SymbolVerificationOutcomeError(ValueError):
    """Stable error raised when an outcome would be ambiguous or invalid."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class SymbolCellVerification:
    """A logical outcome and its optional real catalog-symbol identity.

    ``assigned_symbol_id`` is intentionally legal for exactly one outcome.
    Model predictions belong to prediction provenance and are never copied into
    this field merely because they are available.
    """

    outcome: SymbolVerificationOutcome
    assigned_symbol_id: UUID | None = None

    def __post_init__(self) -> None:
        if self.outcome is SymbolVerificationOutcome.VERIFIED_SYMBOL:
            if not isinstance(self.assigned_symbol_id, UUID):
                raise SymbolVerificationOutcomeError(
                    "SYMBOL_VERIFICATION_SYMBOL_REQUIRED",
                    "A verified-symbol outcome requires a real catalog symbol UUID.",
                )
            return
        if self.assigned_symbol_id is not None:
            raise SymbolVerificationOutcomeError(
                "SYMBOL_VERIFICATION_SYMBOL_FORBIDDEN",
                "Only a verified-symbol outcome may carry an assigned symbol UUID.",
            )

    @property
    def is_human_resolved(self) -> bool:
        """Whether the logical decision can close this cell for a board."""

        return self.outcome in {
            SymbolVerificationOutcome.UNREADABLE,
            SymbolVerificationOutcome.VERIFIED_SYMBOL,
        }

    @property
    def verified_symbol_id(self) -> UUID | None:
        """Return a training-label candidate, never a UI placeholder."""

        if self.outcome is SymbolVerificationOutcome.VERIFIED_SYMBOL:
            return self.assigned_symbol_id
        return None

    @classmethod
    def unassigned(cls) -> SymbolCellVerification:
        return cls(outcome=SymbolVerificationOutcome.UNASSIGNED)

    @classmethod
    def from_model_result(cls, *, has_prediction: bool) -> SymbolCellVerification:
        return cls(
            outcome=(
                SymbolVerificationOutcome.REQUIRES_REVIEW
                if has_prediction
                else SymbolVerificationOutcome.UNKNOWN
            )
        )

    @classmethod
    def unreadable(cls) -> SymbolCellVerification:
        return cls(outcome=SymbolVerificationOutcome.UNREADABLE)

    @classmethod
    def grid_issue(cls) -> SymbolCellVerification:
        return cls(outcome=SymbolVerificationOutcome.GRID_ISSUE)

    @classmethod
    def verified_symbol(cls, symbol_id: UUID) -> SymbolCellVerification:
        return cls(
            outcome=SymbolVerificationOutcome.VERIFIED_SYMBOL,
            assigned_symbol_id=symbol_id,
        )


def project_legacy_verification(
    *,
    review_state: SymbolCellReviewState,
    quality_issue: SymbolCellQualityIssue | None,
    assigned_symbol_id: UUID | None,
    prediction_present: bool,
    assignment_source: SymbolCellAssignmentSource,
) -> SymbolCellVerification:
    """Project one persisted v1 state into the explicit v2 contract.

    A pending model/backfill assignment is treated only as prediction
    provenance.  Suspicious human pending assignments and approved null labels
    without an unreadable decision are rejected so a later migration can report
    them rather than silently inventing meaning.
    """

    if not isinstance(prediction_present, bool):
        raise SymbolVerificationOutcomeError(
            "SYMBOL_VERIFICATION_PREDICTION_FLAG_INVALID",
            "prediction_present must be a boolean.",
        )

    if quality_issue is SymbolCellQualityIssue.GRID_ISSUE:
        if review_state is not SymbolCellReviewState.PENDING:
            raise SymbolVerificationOutcomeError(
                "SYMBOL_VERIFICATION_LEGACY_GRID_STATE_INVALID",
                "A legacy grid issue must remain pending.",
            )
        return SymbolCellVerification.grid_issue()

    if quality_issue is SymbolCellQualityIssue.UNREADABLE:
        if review_state is SymbolCellReviewState.APPROVED and assigned_symbol_id is not None:
            # The label is logically verified, while unreadable remains an
            # independent crop-quality fact in the legacy record.
            return SymbolCellVerification.verified_symbol(assigned_symbol_id)
        return SymbolCellVerification.unreadable()

    if review_state is SymbolCellReviewState.APPROVED:
        if assigned_symbol_id is None:
            raise SymbolVerificationOutcomeError(
                "SYMBOL_VERIFICATION_LEGACY_APPROVED_NULL_AMBIGUOUS",
                "An approved legacy cell without a symbol or unreadable evidence is ambiguous.",
            )
        return SymbolCellVerification.verified_symbol(assigned_symbol_id)

    if assigned_symbol_id is not None and (
        not prediction_present
        or assignment_source
        in {
            SymbolCellAssignmentSource.HUMAN,
            SymbolCellAssignmentSource.BOARD_DECISION,
        }
    ):
        raise SymbolVerificationOutcomeError(
            "SYMBOL_VERIFICATION_LEGACY_PENDING_ASSIGNMENT_AMBIGUOUS",
            "A pending assignment without matching model provenance requires migration review.",
        )

    return SymbolCellVerification.from_model_result(has_prediction=prediction_present)


__all__ = [
    "SYMBOL_VERIFICATION_OUTCOME_CONTRACT_VERSION",
    "SymbolCellVerification",
    "SymbolVerificationOutcome",
    "SymbolVerificationOutcomeError",
    "project_legacy_verification",
]
