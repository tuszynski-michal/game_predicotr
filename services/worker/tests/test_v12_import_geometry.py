"""The V1.2 import consumes the inner grid, never the visible board frame."""

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
    derive_virtual_cells,
)
from game_predictor_worker.images.pipeline_execution import ImagePipelineExecutionError
from game_predictor_worker.images.qualified_manual_geometry import apply_v12_page_geometry


def _entry(count: int) -> dict[str, object]:
    frames = []
    grids = []
    for index in range(count):
        x, y = 20 + index % 3 * 120, 20 + index // 3 * 90
        frames.append(
            [
                {"x": x, "y": y},
                {"x": x + 100, "y": y},
                {"x": x + 100, "y": y + 70},
                {"x": x, "y": y + 70},
            ]
        )
        grids.append(
            [
                {"x": x + 8, "y": y + 12},
                {"x": x + 94, "y": y + 12},
                {"x": x + 94, "y": y + 66},
                {"x": x + 8, "y": y + 66},
            ]
        )
    return {
        "status": "registered",
        "registrationVersion": "contrast-frame-grid-v1.2",
        "imageWidth": 400,
        "imageHeight": 300,
        "boardFrameQuads": frames,
        "symbolGridQuads": grids,
        "quads": frames,
    }


@pytest.mark.parametrize("start,count", ((1, 9), (499996, 5)))
def test_v12_import_uses_inner_grid_for_every_active_board(start: int, count: int) -> None:
    entry = _entry(count)
    result = apply_v12_page_geometry(
        {}, entry, width=400, height=300, start=start, count=count, topology=BoardTopology(3, 5)
    )
    boards = result["boards"]
    assert len(boards) == count
    assert [board["sequenceNumber"] for board in boards] == list(range(start, start + count))
    for position, board in enumerate(boards):
        assert board["finalQuad"] == entry["symbolGridQuads"][position]
        assert board["symbolGridQuad"] == entry["symbolGridQuads"][position]
        assert board["boardFrameQuad"] == entry["boardFrameQuads"][position]
        assert board["disposition"] == "automatic"
    assert entry == _entry(count)


@pytest.mark.parametrize("corruption", ("missing_grid", "escaped_grid", "wrong_alias"))
def test_v12_import_rejects_incomplete_or_conflicting_pairs(corruption: str) -> None:
    entry = _entry(9)
    if corruption == "missing_grid":
        del entry["symbolGridQuads"]
    elif corruption == "escaped_grid":
        entry["symbolGridQuads"][0][0]["x"] = 0
    else:
        entry["quads"] = entry["symbolGridQuads"]
    with pytest.raises(ImagePipelineExecutionError) as error:
        apply_v12_page_geometry(
            {}, entry, width=400, height=300, start=1, count=9, topology=BoardTopology(3, 5)
        )
    assert error.value.code == "IMAGE_PAGE_GEOMETRY_INVALID"


def test_v12_grid_yields_fifteen_cells_inside_inner_bounds() -> None:
    board = apply_v12_page_geometry(
        {}, _entry(9), width=400, height=300, start=1, count=9, topology=BoardTopology(3, 5)
    )["boards"][0]
    grid = SourceQuad(tuple(SourcePoint(point["x"], point["y"]) for point in board["finalQuad"]))
    geometry = VirtualBoardGeometry(
        source=NormalizedSourceImage("a" * 64, "b" * 64, 400, 300, None, "test-v1"),
        source_occurrence=SourceOccurrence(UUID(int=1), "c" * 64),
        slot=ActiveBoardSlot(1, 9, 0, 1),
        topology=BoardTopology(3, 5),
        topology_rules_version_id=UUID(int=2),
        geometry_revision=0,
        geometry_version="contrast-frame-grid-v1.2",
        engine_kind=GeometryEngineKind.STRUCTURED_OPENCV_V1,
        symbol_grid_quad=grid,
    )
    cells = derive_virtual_cells(
        geometry=geometry,
        configuration=DirectCellRenderConfiguration("test-v1", "test-v1", "test-v1", 32, 32, 0.08),
    )
    assert len(cells) == 15
    assert min(point.x for cell in cells for point in cell.source_quad.corners) == 28
    assert max(point.x for cell in cells for point in cell.source_quad.corners) == 114
