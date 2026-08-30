"""Fail-closed helpers for additive v2 persistence and bounded diagnostics."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from game_predictor_api.domain.image_symbol_reviews import (
    SymbolCellAssignmentSource,
    SymbolCellQualityIssue,
    SymbolCellReviewState,
)
from game_predictor_api.domain.symbol_verification_outcomes import (
    SymbolCellVerification,
    SymbolVerificationOutcomeError,
    project_legacy_verification,
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class AdditiveVirtualGeometryContractError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class V2RenderIdentity:
    logical_cell_key_v2: str
    render_identity_v2_sha256: str


@dataclass(frozen=True, slots=True)
class PersistedVerificationV2:
    outcome: str
    verified_symbol_id: UUID | None


def v2_render_identity_from_spec(value: object) -> V2RenderIdentity | None:
    """Read the checksummed v2 identity already embedded by TASK-0321."""

    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise AdditiveVirtualGeometryContractError(
            "IMAGE_V2_RENDER_SPEC_INVALID",
            "A virtual render specification must be an object.",
        )
    logical = value.get("logicalCellKeyV2Sha256")
    render = value.get("renderIdentityV2Sha256")
    if logical is None and render is None:
        return None
    if not isinstance(logical, str) or not _SHA256.fullmatch(logical):
        raise AdditiveVirtualGeometryContractError(
            "IMAGE_V2_LOGICAL_CELL_ID_INVALID",
            "The logical-cell-v2 identity is missing or invalid.",
        )
    if not isinstance(render, str) or not _SHA256.fullmatch(render):
        raise AdditiveVirtualGeometryContractError(
            "IMAGE_V2_RENDER_ID_INVALID",
            "The render-identity-v2 checksum is missing or invalid.",
        )
    return V2RenderIdentity(
        logical_cell_key_v2=logical,
        render_identity_v2_sha256=render,
    )


def verification_outcome_value(
    *,
    review_state: str,
    quality_issue: str | None,
    assigned_symbol_id: UUID | None,
    prediction_present: bool,
    assignment_source: str,
) -> PersistedVerificationV2:
    """Project one unambiguous persisted v1 state to outcome v2."""

    try:
        state = SymbolCellReviewState(review_state)
        quality = None if quality_issue is None else SymbolCellQualityIssue(quality_issue)
        source = SymbolCellAssignmentSource(assignment_source)
    except ValueError as error:
        raise AdditiveVirtualGeometryContractError(
            "SYMBOL_VERIFICATION_LEGACY_ENUM_INVALID",
            "The legacy symbol-cell state cannot be represented by outcome v2.",
        ) from error
    try:
        projected: SymbolCellVerification = project_legacy_verification(
            review_state=state,
            quality_issue=quality,
            assigned_symbol_id=assigned_symbol_id,
            prediction_present=prediction_present,
            assignment_source=source,
        )
        return PersistedVerificationV2(
            outcome=projected.outcome.value,
            verified_symbol_id=projected.verified_symbol_id,
        )
    except SymbolVerificationOutcomeError as error:
        raise AdditiveVirtualGeometryContractError(error.code, error.message) from error


def optional_verification_outcome_value(
    *,
    review_state: str,
    quality_issue: str | None,
    assigned_symbol_id: UUID | None,
    prediction_present: bool,
    assignment_source: str,
) -> PersistedVerificationV2 | None:
    """Keep ambiguous historical state nullable for the bounded report."""

    try:
        return verification_outcome_value(
            review_state=review_state,
            quality_issue=quality_issue,
            assigned_symbol_id=assigned_symbol_id,
            prediction_present=prediction_present,
            assignment_source=assignment_source,
        )
    except AdditiveVirtualGeometryContractError:
        return None


__all__ = [
    "AdditiveVirtualGeometryContractError",
    "PersistedVerificationV2",
    "V2RenderIdentity",
    "optional_verification_outcome_value",
    "v2_render_identity_from_spec",
    "verification_outcome_value",
]
