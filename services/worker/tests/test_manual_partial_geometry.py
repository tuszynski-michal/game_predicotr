import hashlib
from dataclasses import replace
from uuid import UUID

import numpy as np
import pytest
from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.geometry_qualification import GeometryQualification
from game_predictor_api.domain.image_geometry_v2 import (
    ActiveBoardSlot,
    DirectCellRenderConfiguration,
    GeometryEngineKind,
    ImageGeometryContractError,
    SourceOccurrence,
    SourcePoint,
    SourceQuad,
    VirtualBoardGeometry,
    derive_virtual_cells,
    fully_unavailable_source_cell_indices,
    resolve_manual_geometry_qualification,
    unavailable_source_cell_indices,
)
from game_predictor_worker.images.normalization import CanonicalSourceLoader
from game_predictor_worker.images.virtual_cell_extraction import (
    VIRTUAL_CELL_INTERPOLATION_VERSION,
    VIRTUAL_CELL_RENDERER_VERSION,
    VirtualCellRenderer,
    render_persisted_virtual_cell_rgb,
)
from PIL import Image


def _quad(points):
    return SourceQuad(tuple(SourcePoint(x, y) for x, y in points))


@pytest.fixture
def frame(tmp_path):
    path = tmp_path / "source.jpg"
    Image.new("RGB", (300, 200), (140, 180, 220)).save(path)
    return CanonicalSourceLoader().load(
        path, expected_source_checksum_sha256=hashlib.sha256(path.read_bytes()).hexdigest()
    )


def _geometry(frame, quad, qualification):
    return VirtualBoardGeometry(
        source=frame.source,
        source_occurrence=SourceOccurrence(UUID(int=1), "a" * 64),
        slot=ActiveBoardSlot(1, 9, 0, 1),
        topology=BoardTopology(3, 5),
        topology_rules_version_id=UUID(int=2),
        geometry_revision=1,
        geometry_version="manual-source-geometry-partial-v2",
        engine_kind=GeometryEngineKind.MANUAL_V1,
        symbol_grid_quad=quad,
        geometry_qualification=qualification,
    )


def _configuration():
    return DirectCellRenderConfiguration(
        extractor_version=VIRTUAL_CELL_RENDERER_VERSION,
        preprocessing_version="rgb-v1",
        interpolation=VIRTUAL_CELL_INTERPOLATION_VERSION,
        output_width=32,
        output_height=32,
        padding_fraction=0.08,
    )


@pytest.mark.parametrize(
    "points,expected",
    [
        (((10, -20), (260, -20), (260, 130), (10, 130)), tuple(range(5))),
        (((10, 60), (260, 60), (260, 210), (10, 210)), tuple(range(10, 15))),
        (((-20, 20), (230, 20), (230, 170), (-20, 170)), (0, 5, 10)),
        (((70, 20), (320, 20), (320, 170), (70, 170)), (4, 9, 14)),
        (((-20, 20), (280, 20), (320, 170), (20, 170)), (0, 5, 9, 14)),
        (((-280, 0), (-30, 0), (-30, 150), (-280, 150)), tuple(range(15))),
    ],
)
def test_partially_visible_cells_render_but_fully_outside_cells_never_do(frame, points, expected):
    quad = _quad(points)
    mask = unavailable_source_cell_indices(quad, source=frame.source, topology=BoardTopology(3, 5))
    assert mask == expected
    fully = fully_unavailable_source_cell_indices(
        quad, source=frame.source, topology=BoardTopology(3, 5)
    )
    qualification = GeometryQualification("pending_partial", mask, True, "missing_pixels")
    geometry = _geometry(frame, quad, qualification)
    cells = derive_virtual_cells(geometry=geometry, configuration=_configuration())
    assert tuple(cell.cell_index for cell in cells) == tuple(i for i in range(15) if i not in fully)
    for cell in cells:
        assert cell.partially_visible == (cell.cell_index in mask)
    renders = VirtualCellRenderer().render(frame, cells)
    assert len(renders) == 15 - len(fully)
    for render in renders:
        replay = render_persisted_virtual_cell_rgb(
            frame,
            render_spec=render.render_spec,
            expected_render_spec_checksum_sha256=render.render_spec_checksum_sha256,
            expected_rendered_pixel_checksum_sha256=render.rendered_pixel_checksum_sha256,
            expected_cell_index=render.cell_index,
            expected_row_index=render.row_index,
            expected_column_index=render.column_index,
            expected_logical_cell_key_sha256=render.logical_cell_key_sha256,
            expected_logical_cell_key_v2_sha256=render.logical_cell_key_v2_sha256,
            expected_extractor_version=render.extractor_version,
        )
        assert np.array_equal(replay, render.rgb)


def test_automatic_mask_cannot_be_cleared_and_manual_mask_only_extends(frame):
    quad = _quad(((-10, -10), (260, 20), (280, 190), (0, 160)))
    automatic = unavailable_source_cell_indices(
        quad, source=frame.source, topology=BoardTopology(3, 5)
    )
    assert automatic
    manual = GeometryQualification("pending_partial", (14,), True, "missing_pixels")
    merged = resolve_manual_geometry_qualification(
        quad, source=frame.source, topology=BoardTopology(3, 5), qualification=manual
    )
    assert merged.unavailable_cell_indices == tuple(sorted(set(automatic) | {14}))
    with pytest.raises(ImageGeometryContractError, match="must remain unavailable"):
        _geometry(frame, quad, manual)
    with pytest.raises(ImageGeometryContractError, match="explicitly declared partial"):
        resolve_manual_geometry_qualification(
            quad,
            source=frame.source,
            topology=BoardTopology(3, 5),
            qualification=GeometryQualification(),
        )


def test_missing_decorative_frame_or_crop_padding_does_not_mark_visible_grid_partial(frame):
    # The human grid touches the left source edge. Any decorative margin to
    # its left is absent, but every proper cell is present in the photo.
    quad = _quad(((0, 20), (250, 20), (250, 170), (0, 170)))
    qualification = resolve_manual_geometry_qualification(
        quad,
        source=frame.source,
        topology=BoardTopology(3, 5),
        qualification=GeometryQualification(),
    )
    assert qualification.completeness_status == "complete"
    assert qualification.unavailable_cell_indices == ()
    assert not qualification.exclude_from_geometry_training
    cells = derive_virtual_cells(
        geometry=_geometry(frame, quad, qualification), configuration=_configuration()
    )
    assert len(VirtualCellRenderer().render(frame, cells)) == 15
    excluded = resolve_manual_geometry_qualification(
        quad,
        source=frame.source,
        topology=BoardTopology(3, 5),
        qualification=GeometryQualification("complete", (), True, "manual_exclusion"),
    )
    assert excluded.completeness_status == "complete" and excluded.unavailable_cell_indices == ()
    assert excluded.exclude_from_geometry_training


def test_historical_and_automatic_geometries_do_not_gain_outside_support(frame):
    quad = _quad(((-10, 10), (240, 10), (240, 160), (-10, 160)))
    with pytest.raises(ImageGeometryContractError):
        _geometry(frame, quad, None)
    partial = _geometry(
        frame, quad, GeometryQualification("pending_partial", (0, 5, 10), True, "missing_pixels")
    )
    with pytest.raises(ImageGeometryContractError, match="not an automatic geometry fallback"):
        replace(partial, engine_kind=GeometryEngineKind.STRUCTURED_OPENCV_V1)
    with pytest.raises(ImageGeometryContractError, match="at most one source"):
        replace(partial, symbol_grid_quad=_quad(((-301, 10), (-51, 10), (-51, 160), (-301, 160))))


@pytest.mark.parametrize(
    "points",
    [
        ((0, 0), (299, 10), (290, 199), (20, 190)),
        ((0, 10), (200, 0), (299, 199), (20, 170)),
    ],
)
def test_roundoff_at_supported_perspective_boundary_is_not_missing(frame, points):
    quad = _quad(points)
    qualification = resolve_manual_geometry_qualification(
        quad,
        source=frame.source,
        topology=BoardTopology(3, 5),
        qualification=GeometryQualification(),
    )
    assert qualification.unavailable_cell_indices == ()
    cells = derive_virtual_cells(
        geometry=_geometry(frame, quad, qualification), configuration=_configuration()
    )
    assert len(VirtualCellRenderer().render(frame, cells)) == 15
