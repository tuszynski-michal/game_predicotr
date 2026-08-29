from __future__ import annotations

from uuid import uuid4

import pytest
from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.image_geometry_v2 import (
    AttestedSequenceRange,
    DirectCellRenderConfiguration,
    GeometryEngineKind,
    ImageGeometryContractError,
    NormalizedSourceImage,
    SourcePoint,
    SourceQuad,
    VirtualBoardGeometry,
    derive_virtual_cells,
    parse_attested_sequence_range_filename,
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


def _geometry(*, revision: int = 0) -> VirtualBoardGeometry:
    sequence_range = AttestedSequenceRange(start=73, end=77)
    return VirtualBoardGeometry(
        source=_source(),
        slot=sequence_range.active_slots[4],
        topology=BoardTopology(rows=3, columns=5),
        topology_rules_version_id=uuid4(),
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
    assert initial.render_id_sha256 != recropped.render_id_sha256


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
            slot=AttestedSequenceRange(start=1, end=1).active_slots[0],
            topology=BoardTopology(rows=3, columns=5),
            topology_rules_version_id=uuid4(),
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
