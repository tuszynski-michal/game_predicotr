from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from uuid import UUID

import pytest
from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.image_geometry_v2 import (
    ActiveBoardSlot,
    DirectCellRenderConfiguration,
    GeometryEngineKind,
    NormalizedSourceImage,
    SourceOccurrence,
    SourcePoint,
    SourceQuad,
    VirtualBoardGeometry,
    VirtualCell,
    derive_virtual_cells,
)
from game_predictor_api.storage.additive_virtual_geometry_contracts import (
    AdditiveVirtualGeometryContractError,
    derive_v2_render_identity_from_legacy_spec,
    optional_verification_outcome_value,
    v2_render_identity_from_spec,
    verification_outcome_value,
)
from game_predictor_api.storage.additive_virtual_geometry_diagnostics import (
    SqlAlchemyAdditiveVirtualGeometryDiagnostics,
)
from sqlalchemy.orm import Session

SYMBOL_ID = UUID("10000000-0000-0000-0000-000000000001")


def _legacy_render_spec() -> tuple[dict[str, object], VirtualCell]:
    topology = BoardTopology(rows=3, columns=5)
    geometry = VirtualBoardGeometry(
        source=NormalizedSourceImage(
            source_checksum_sha256="1" * 64,
            normalized_pixel_checksum_sha256="2" * 64,
            width=1000,
            height=800,
            exif_orientation=1,
            normalization_adapter_version="image-normalization-v2",
        ),
        source_occurrence=SourceOccurrence(
            import_job_id=UUID("10000000-0000-0000-0000-000000000010"),
            file_execution_key="3" * 64,
        ),
        slot=ActiveBoardSlot(
            range_start=10,
            range_end=18,
            position_index=0,
            sequence_number=10,
        ),
        topology=topology,
        topology_rules_version_id=UUID("10000000-0000-0000-0000-000000000020"),
        geometry_revision=0,
        geometry_version="structured-page-geometry-v1",
        engine_kind=GeometryEngineKind.STRUCTURED_OPENCV_V1,
        symbol_grid_quad=SourceQuad(
            corners=(
                SourcePoint(100, 100),
                SourcePoint(900, 100),
                SourcePoint(900, 700),
                SourcePoint(100, 700),
            )
        ),
    )
    configuration = DirectCellRenderConfiguration(
        extractor_version="virtual-cell-extractor-v1",
        preprocessing_version="rgb-v1",
        interpolation="linear",
        output_width=96,
        output_height=96,
        padding_fraction=0.05,
    )
    cell = derive_virtual_cells(geometry=geometry, configuration=configuration)[0]
    return (
        {
            "boardSlot": 0,
            "cellIndex": 0,
            "columnIndex": 0,
            "configuration": configuration.to_dict(),
            "geometryFingerprintSha256": geometry.geometry_fingerprint_sha256,
            "rowIndex": 0,
            "sourceQuad": cell.source_quad.to_dict(),
        },
        cell,
    )


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


def test_legacy_render_spec_derives_the_same_v2_identity_as_current_writer() -> None:
    render_spec, cell = _legacy_render_spec()

    identity = derive_v2_render_identity_from_legacy_spec(
        render_spec,
        import_job_id=cell.geometry.source_occurrence.import_job_id,
        file_execution_key=cell.geometry.source_occurrence.file_execution_key,
        topology_rules_version_id=cell.geometry.topology_rules_version_id,
        topology=cell.geometry.topology,
        board_slot=cell.geometry.slot.position_index,
        cell_index=cell.cell_index,
        row_index=cell.row_index,
        column_index=cell.column_index,
    )

    assert identity.logical_cell_key_v2 == cell.logical_id_v2_sha256
    assert identity.render_identity_v2_sha256 == cell.render_id_v2_sha256


def test_existing_v2_identity_must_match_immutable_legacy_inputs() -> None:
    render_spec, cell = _legacy_render_spec()
    render_spec["logicalCellKeyV2Sha256"] = "a" * 64
    render_spec["renderIdentityV2Sha256"] = "b" * 64

    with pytest.raises(AdditiveVirtualGeometryContractError) as raised:
        derive_v2_render_identity_from_legacy_spec(
            render_spec,
            import_job_id=cell.geometry.source_occurrence.import_job_id,
            file_execution_key=cell.geometry.source_occurrence.file_execution_key,
            topology_rules_version_id=cell.geometry.topology_rules_version_id,
            topology=cell.geometry.topology,
            board_slot=cell.geometry.slot.position_index,
            cell_index=cell.cell_index,
            row_index=cell.row_index,
            column_index=cell.column_index,
        )

    assert raised.value.code == "IMAGE_V2_RENDER_IDENTITY_MISMATCH"


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
