from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from uuid import UUID

import pytest
from game_predictor_api.storage.additive_virtual_geometry_contracts import (
    AdditiveVirtualGeometryContractError,
    optional_verification_outcome_value,
    v2_render_identity_from_spec,
    verification_outcome_value,
)
from game_predictor_api.storage.additive_virtual_geometry_diagnostics import (
    SqlAlchemyAdditiveVirtualGeometryDiagnostics,
)
from sqlalchemy.orm import Session

SYMBOL_ID = UUID("10000000-0000-0000-0000-000000000001")


def test_render_identity_v2_requires_both_checksummed_parts() -> None:
    identity = v2_render_identity_from_spec(
        {
            "logicalCellKeyV2Sha256": "a" * 64,
            "renderIdentityV2Sha256": "b" * 64,
        }
    )

    assert identity is not None
    assert identity.logical_cell_key_v2 == "a" * 64
    assert identity.render_identity_v2_sha256 == "b" * 64

    with pytest.raises(AdditiveVirtualGeometryContractError) as raised:
        v2_render_identity_from_spec({"logicalCellKeyV2Sha256": "a" * 64})
    assert raised.value.code == "IMAGE_V2_RENDER_ID_INVALID"


def test_model_suggestion_is_not_persisted_as_a_verified_symbol_v2() -> None:
    verification = verification_outcome_value(
        review_state="pending",
        quality_issue=None,
        assigned_symbol_id=SYMBOL_ID,
        prediction_present=True,
        assignment_source="model",
    )

    assert verification.outcome == "requires_review"
    assert verification.verified_symbol_id is None


def test_human_approval_persists_an_explicit_verified_symbol_v2() -> None:
    verification = verification_outcome_value(
        review_state="approved",
        quality_issue=None,
        assigned_symbol_id=SYMBOL_ID,
        prediction_present=True,
        assignment_source="human",
    )

    assert verification.outcome == "verified_symbol"
    assert verification.verified_symbol_id == SYMBOL_ID


def test_ambiguous_legacy_state_stays_nullable_for_diagnostics() -> None:
    verification = optional_verification_outcome_value(
        review_state="approved",
        quality_issue=None,
        assigned_symbol_id=None,
        prediction_present=False,
        assignment_source="human",
    )

    assert verification is None


class _DiagnosticSession:
    def __init__(self, batches: list[list[object]]) -> None:
        self._batches = iter(batches)

    def scalars(self, _statement: object) -> list[object]:
        return next(self._batches)


def test_bounded_diagnostics_separates_ready_and_ambiguous_history() -> None:
    ready_id = UUID("20000000-0000-0000-0000-000000000001")
    ambiguous_id = UUID("20000000-0000-0000-0000-000000000002")
    review_rows = [
        SimpleNamespace(
            id=ready_id,
            review_state="pending",
            quality_issue=None,
            assigned_symbol_id=SYMBOL_ID,
            prediction_symbol_code="cherry",
            assignment_source="model",
            asset_mode="legacy_file",
            render_spec=None,
        ),
        SimpleNamespace(
            id=ambiguous_id,
            review_state="approved",
            quality_issue=None,
            assigned_symbol_id=None,
            prediction_symbol_code=None,
            assignment_source="human",
            asset_mode="legacy_file",
            render_spec=None,
        ),
    ]
    session = _DiagnosticSession([[], [], review_rows, []])

    report = SqlAlchemyAdditiveVirtualGeometryDiagnostics(cast(Session, session)).inspect(limit=10)

    assert report.ready_count == 1
    assert report.ambiguous_count == 1
    assert report.truncated is False
    assert [sample.record_id for sample in report.samples] == [ready_id, ambiguous_id]
