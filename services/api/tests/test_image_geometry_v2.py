from __future__ import annotations

from dataclasses import replace
from uuid import UUID

import pytest
from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.geometry_qualification import GeometryQualification
from game_predictor_api.domain.image_geometry_v2 import (
    AttestedSequenceRange,
    DirectCellRenderConfiguration,
    GeometryEngineKind,
    ImageGeometryContractError,
    NormalizedSourceImage,
    SourceOccurrence,
    SourcePoint,
    SourceQuad,
    VirtualBoardGeometry,
    VirtualCell,
    board_topology_fingerprint_sha256,
    derive_virtual_cells,
    fully_unavailable_source_cell_indices,
    parse_attested_sequence_range_filename,
    sequence_attestation_checksum_sha256,
)


def _source() -> NormalizedSourceImage:
    return NormalizedSourceImage(
        source_checksum_sha256="a" * 64,
        normalized_pixel_checksum_sha256="b" * 64,
        width=1600,
        height=1200,
        exif_orientation=6,
        normalization_adapter_version="image-normalization-v2-in-memory-source-v1",
    )


IMPORT_JOB_ID = UUID("10000000-0000-0000-0000-000000000001")
TOPOLOGY_RULES_VERSION_ID = UUID("10000000-0000-0000-0000-000000000002")


def _geometry(
    *,
    revision: int = 0,
    import_job_id: UUID = IMPORT_JOB_ID,
    topology_rules_version_id: UUID = TOPOLOGY_RULES_VERSION_ID,
) -> VirtualBoardGeometry:
    sequence_range = AttestedSequenceRange(start=73, end=77)
    return VirtualBoardGeometry(
        source=_source(),
        source_occurrence=SourceOccurrence(
            import_job_id=import_job_id,
            file_execution_key="c" * 64,
        ),
        slot=sequence_range.active_slots[4],
        topology=BoardTopology(rows=3, columns=5),
        topology_rules_version_id=topology_rules_version_id,
        geometry_revision=revision,
        geometry_version="virtual-board-geometry-v1",
        engine_kind=GeometryEngineKind.STRUCTURED_OPENCV_V1,
        symbol_grid_quad=SourceQuad(
            corners=(
                SourcePoint(220.0, 210.0),
                SourcePoint(1320.0, 170.0),
                SourcePoint(1370.0, 1000.0),
                SourcePoint(190.0, 940.0),
            )
        ),
    )


def _configuration() -> DirectCellRenderConfiguration:
    return DirectCellRenderConfiguration(
        extractor_version="virtual-source-direct-v1",
        preprocessing_version="symbol-cnn-rgb-v1",
        interpolation="INTER_LINEAR",
        output_width=64,
        output_height=64,
        padding_fraction=0.1,
    )


def _rectangular_source(width: int = 300, height: int = 180) -> NormalizedSourceImage:
    return NormalizedSourceImage(
        source_checksum_sha256="d" * 64,
        normalized_pixel_checksum_sha256="e" * 64,
        width=width,
        height=height,
        exif_orientation=1,
        normalization_adapter_version="image-normalization-v2-in-memory-source-v1",
    )


def _partial_visibility_geometry(*, x_shift: float) -> VirtualBoardGeometry:
    """A 3x5 axis-aligned grid over a 300x180 source, shifted left by ``x_shift``.

    Columns are 60px wide.  With ``x_shift=90``, column 0 (x in [-90,-30])
    has zero corners inside the source and column 1 (x in [-30,30]) has two
    of four corners inside — the same shape as a column trailing off the
    edge of a photographed board.
    """

    quad = SourceQuad(
        corners=(
            SourcePoint(0.0 - x_shift, 0.0),
            SourcePoint(299.0 - x_shift, 0.0),
            SourcePoint(299.0 - x_shift, 179.0),
            SourcePoint(0.0 - x_shift, 179.0),
        )
    )
    source = _rectangular_source()
    topology = BoardTopology(rows=3, columns=5)
    automatic = sorted(
        set(
            i
            for i in range(15)
            if any(
                point.x < 0.0 or point.x > source.width - 1
                for point in quad.cell_quad(
                    topology=topology, row_index=i // 5, column_index=i % 5
                ).corners
            )
        )
    )
    qualification = GeometryQualification(
        "pending_partial",
        tuple(automatic),
        True,
        "missing_pixels",
    )
    sequence_range = AttestedSequenceRange(start=1, end=5)
    return VirtualBoardGeometry(
        source=source,
        source_occurrence=SourceOccurrence(
            import_job_id=IMPORT_JOB_ID,
            file_execution_key="f" * 64,
        ),
        slot=sequence_range.active_slots[0],
        topology=topology,
        topology_rules_version_id=TOPOLOGY_RULES_VERSION_ID,
        geometry_revision=0,
        geometry_version="virtual-board-geometry-v1",
        engine_kind=GeometryEngineKind.MANUAL_V1,
        symbol_grid_quad=quad,
        geometry_qualification=qualification,
    )


def test_fully_unavailable_source_cell_indices_requires_every_corner_outside() -> None:
    geometry = _partial_visibility_geometry(x_shift=90.0)

    fully_unavailable = fully_unavailable_source_cell_indices(
        geometry.symbol_grid_quad, source=geometry.source, topology=geometry.topology
    )

    # Column 0 (indices 0, 5, 10) has zero corners inside the source.
    # Column 1 (indices 1, 6, 11) still has two corners inside and is not
    # fully unavailable, even though it is in the operator's mask.
    assert fully_unavailable == (0, 5, 10)


def test_derive_virtual_cells_keeps_partially_visible_cells_and_skips_fully_missing_ones() -> None:
    geometry = _partial_visibility_geometry(x_shift=90.0)

    cells = derive_virtual_cells(geometry=geometry, configuration=_configuration())

    assert [cell.cell_index for cell in cells] == [1, 2, 3, 4, 6, 7, 8, 9, 11, 12, 13, 14]
    assert {cell.cell_index for cell in cells if cell.partially_visible} == {1, 6, 11}
    assert all(not cell.partially_visible for cell in cells if cell.cell_index not in {1, 6, 11})


def test_virtual_cell_rejects_a_partially_visible_flag_on_a_fully_outside_quad() -> None:
    geometry = _partial_visibility_geometry(x_shift=90.0)

    with pytest.raises(ImageGeometryContractError) as raised:
        VirtualCell(
            geometry=geometry,
            configuration=_configuration(),
            cell_index=0,
            row_index=0,
            column_index=0,
            source_quad=geometry.symbol_grid_quad.cell_quad(
                topology=geometry.topology, row_index=0, column_index=0
            ),
            partially_visible=True,
        )

    assert raised.value.code == "IMAGE_GEOMETRY_QUAD_ENTIRELY_OUT_OF_BOUNDS"


def test_seq_range_maps_a_partial_final_page_to_the_row_major_prefix() -> None:
    parsed = parse_attested_sequence_range_filename("nested/SEQ_73-77.JPEG")

    assert parsed == AttestedSequenceRange(start=73, end=77)
    assert [
        (slot.position_index, slot.row_index, slot.column_index, slot.sequence_number)
        for slot in parsed.active_slots
    ] == [
        (0, 0, 0, 73),
        (1, 0, 1, 74),
        (2, 0, 2, 75),
        (3, 1, 0, 76),
        (4, 1, 1, 77),
    ]


def test_topology_and_attestation_snapshots_have_deterministic_distinct_checksums() -> None:
    topology = BoardTopology(rows=3, columns=5)
    topology_checksum = board_topology_fingerprint_sha256(
        topology_rules_version_id=TOPOLOGY_RULES_VERSION_ID,
        topology=topology,
    )
    attestation_checksum = sequence_attestation_checksum_sha256(
        sequence_range_start=73,
        sequence_range_end=77,
        active_board_slots=(0, 1, 2, 3, 4),
    )

    assert len(topology_checksum) == 64
    assert len(attestation_checksum) == 64
    assert topology_checksum != attestation_checksum

    with pytest.raises(ImageGeometryContractError) as raised:
        sequence_attestation_checksum_sha256(
            sequence_range_start=73,
            sequence_range_end=77,
            active_board_slots=(0, 1, 2, 4),
        )
    assert raised.value.code == "IMAGE_SEQUENCE_ATTESTATION_SLOTS_INVALID"


@pytest.mark.parametrize("filename", ("seq_4-3.jpg", "seq_1-10.jpg", "seq_0-8.jpg", "seq_1-9.png"))
def test_seq_range_rejects_invalid_or_non_attested_filenames(filename: str) -> None:
    with pytest.raises(ImageGeometryContractError) as raised:
        parse_attested_sequence_range_filename(filename)

    assert raised.value.code in {"IMAGE_SEQUENCE_FILENAME_INVALID", "IMAGE_SEQUENCE_RANGE_INVALID"}


def test_virtual_cells_are_projective_row_major_without_rectangle_constraints() -> None:
    geometry = _geometry()

    cells = derive_virtual_cells(geometry=geometry, configuration=_configuration())

    assert len(cells) == 15
    assert [(cell.cell_index, cell.row_index, cell.column_index) for cell in cells] == [
        (index, index // 5, index % 5) for index in range(15)
    ]
    assert cells[0].source_quad.corners[1].y != cells[0].source_quad.corners[0].y
    assert cells[-1].source_quad.corners[2].x != cells[-1].source_quad.corners[3].x


def test_virtual_cell_logical_identity_survives_a_new_geometry_revision() -> None:
    configuration = _configuration()
    initial = derive_virtual_cells(geometry=_geometry(revision=0), configuration=configuration)[7]
    recropped = derive_virtual_cells(geometry=_geometry(revision=1), configuration=configuration)[7]

    assert initial.logical_id_sha256 == recropped.logical_id_sha256
    assert initial.logical_id_v2_sha256 == recropped.logical_id_v2_sha256
    assert initial.render_id_sha256 != recropped.render_id_sha256
    assert initial.render_id_v2_sha256 != recropped.render_id_v2_sha256


def test_logical_cell_v2_distinguishes_equal_bytes_in_different_imports() -> None:
    configuration = _configuration()
    first = derive_virtual_cells(geometry=_geometry(), configuration=configuration)[7]
    second = derive_virtual_cells(
        geometry=_geometry(import_job_id=UUID("10000000-0000-0000-0000-000000000099")),
        configuration=configuration,
    )[7]

    assert first.logical_id_v1_sha256 == second.logical_id_v1_sha256
    assert first.logical_id_v2_sha256 != second.logical_id_v2_sha256


def test_logical_cell_v2_pins_topology_without_changing_v1() -> None:
    configuration = _configuration()
    first = derive_virtual_cells(geometry=_geometry(), configuration=configuration)[7]
    changed_topology = derive_virtual_cells(
        geometry=_geometry(topology_rules_version_id=UUID("10000000-0000-0000-0000-000000000099")),
        configuration=configuration,
    )[7]

    assert first.logical_id_v1_sha256 == changed_topology.logical_id_v1_sha256
    assert first.logical_id_v2_sha256 != changed_topology.logical_id_v2_sha256


def test_logical_cell_v1_golden_remains_compatible() -> None:
    cell = derive_virtual_cells(geometry=_geometry(), configuration=_configuration())[7]

    assert (
        cell.logical_id_v1_sha256
        == cell.logical_id_sha256
        == "87ff4d8a2f48bb030091bb9a95893dc37b8faa581a0dad6b080109fef5e1d866"
    )
    assert cell.render_id_v1_sha256 == cell.render_id_sha256


def test_source_occurrence_rejects_non_sha_execution_key() -> None:
    with pytest.raises(ImageGeometryContractError) as raised:
        replace(_geometry().source_occurrence, file_execution_key="not-a-checksum")

    assert raised.value.code == "IMAGE_SOURCE_OCCURRENCE_INVALID"


def test_source_quad_fails_closed_for_a_crossed_or_out_of_bounds_geometry() -> None:
    with pytest.raises(ImageGeometryContractError) as crossed:
        SourceQuad(
            corners=(
                SourcePoint(10.0, 10.0),
                SourcePoint(90.0, 90.0),
                SourcePoint(90.0, 10.0),
                SourcePoint(10.0, 90.0),
            )
        )
    assert crossed.value.code == "IMAGE_GEOMETRY_QUAD_INVALID"

    with pytest.raises(ImageGeometryContractError) as outside:
        VirtualBoardGeometry(
            source=_source(),
            source_occurrence=SourceOccurrence(
                import_job_id=IMPORT_JOB_ID,
                file_execution_key="c" * 64,
            ),
            slot=AttestedSequenceRange(start=1, end=1).active_slots[0],
            topology=BoardTopology(rows=3, columns=5),
            topology_rules_version_id=TOPOLOGY_RULES_VERSION_ID,
            geometry_revision=0,
            geometry_version="virtual-board-geometry-v1",
            engine_kind=GeometryEngineKind.MANUAL_V1,
            symbol_grid_quad=SourceQuad(
                corners=(
                    SourcePoint(-1.0, 10.0),
                    SourcePoint(80.0, 10.0),
                    SourcePoint(80.0, 80.0),
                    SourcePoint(10.0, 80.0),
                )
            ),
        )
    assert outside.value.code == "IMAGE_GEOMETRY_QUAD_OUT_OF_BOUNDS"
