"""Fail-closed helpers for additive v2 persistence and bounded diagnostics."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.image_geometry_v2 import (
    VIRTUAL_CELL_LOGICAL_ID_V2_VERSION,
    VIRTUAL_CELL_RENDER_ID_V2_VERSION,
    SourceOccurrence,
    board_topology_fingerprint_sha256,
    canonical_json_bytes,
)
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


def derive_v2_render_identity_from_legacy_spec(
    value: object,
    *,
    import_job_id: UUID,
    file_execution_key: str,
    topology_rules_version_id: UUID,
    topology: BoardTopology,
    board_slot: int,
    cell_index: int,
    row_index: int,
    column_index: int,
) -> V2RenderIdentity:
    """Derive v2 identity without decoding or re-rendering historical pixels.

    The historical render specification already pins geometry, render
    configuration and the source-space quad.  Occurrence and topology are read
    from immutable relational context instead of being guessed from file
    content.  If a newer spec already carries v2 values, they must match the
    independently derived result exactly.
    """

    if not isinstance(value, Mapping):
        raise AdditiveVirtualGeometryContractError(
            "IMAGE_V2_RENDER_SPEC_INVALID",
            "A virtual render specification must be an object.",
        )
    expected_coordinates = {
        "boardSlot": board_slot,
        "cellIndex": cell_index,
        "rowIndex": row_index,
        "columnIndex": column_index,
    }
    if any(value.get(name) != expected for name, expected in expected_coordinates.items()):
        raise AdditiveVirtualGeometryContractError(
            "IMAGE_V2_RENDER_SPEC_COORDINATES_MISMATCH",
            "The historical render specification does not match its persisted cell.",
        )
    topology.validate_coordinates(
        cell_index=cell_index,
        row_index=row_index,
        column_index=column_index,
    )
    occurrence = SourceOccurrence(
        import_job_id=import_job_id,
        file_execution_key=file_execution_key,
    )
    topology_fingerprint = board_topology_fingerprint_sha256(
        topology_rules_version_id=topology_rules_version_id,
        topology=topology,
    )
    _require_optional_match(
        value,
        "sourceOccurrenceIdSha256",
        occurrence.identity_sha256,
        "IMAGE_V2_SOURCE_OCCURRENCE_MISMATCH",
    )
    _require_optional_match(
        value,
        "topologyFingerprintSha256",
        topology_fingerprint,
        "IMAGE_V2_TOPOLOGY_FINGERPRINT_MISMATCH",
    )
    geometry_fingerprint = _require_sha256(
        value.get("geometryFingerprintSha256"),
        code="IMAGE_V2_GEOMETRY_FINGERPRINT_INVALID",
    )
    configuration = value.get("configuration")
    source_quad = value.get("sourceQuad")
    if not isinstance(configuration, Mapping) or not isinstance(source_quad, list):
        raise AdditiveVirtualGeometryContractError(
            "IMAGE_V2_RENDER_SPEC_INCOMPLETE",
            "The historical render specification lacks configuration or source quad.",
        )
    logical = hashlib.sha256(
        canonical_json_bytes(
            {
                "boardSlot": board_slot,
                "cellIndex": cell_index,
                "columnIndex": column_index,
                "contractVersion": VIRTUAL_CELL_LOGICAL_ID_V2_VERSION,
                "rowIndex": row_index,
                "sourceOccurrenceIdSha256": occurrence.identity_sha256,
                "topologyFingerprintSha256": topology_fingerprint,
            }
        )
    ).hexdigest()
    render = hashlib.sha256(
        canonical_json_bytes(
            {
                "configuration": dict(configuration),
                "contractVersion": VIRTUAL_CELL_RENDER_ID_V2_VERSION,
                "geometryFingerprintSha256": geometry_fingerprint,
                "logicalCellIdV2Sha256": logical,
                "sourceQuad": source_quad,
            }
        )
    ).hexdigest()
    persisted = v2_render_identity_from_spec(value)
    derived = V2RenderIdentity(
        logical_cell_key_v2=logical,
        render_identity_v2_sha256=render,
    )
    if persisted is not None and persisted != derived:
        raise AdditiveVirtualGeometryContractError(
            "IMAGE_V2_RENDER_IDENTITY_MISMATCH",
            "The persisted v2 render identity differs from its immutable inputs.",
        )
    return derived


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


def _require_optional_match(
    value: Mapping[object, object],
    field: str,
    expected: str,
    code: str,
) -> None:
    actual = value.get(field)
    if actual is not None and actual != expected:
        raise AdditiveVirtualGeometryContractError(
            code,
            f"The persisted {field} differs from immutable relational context.",
        )


def _require_sha256(value: object, *, code: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise AdditiveVirtualGeometryContractError(
            code,
            "The historical render specification contains an invalid SHA-256 value.",
        )
    return value


__all__ = [
    "AdditiveVirtualGeometryContractError",
    "PersistedVerificationV2",
    "V2RenderIdentity",
    "derive_v2_render_identity_from_legacy_spec",
    "optional_verification_outcome_value",
    "v2_render_identity_from_spec",
    "verification_outcome_value",
]
