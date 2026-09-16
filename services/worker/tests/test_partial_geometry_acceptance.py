"""Source-level acceptance of qualified manual slots, independent of detection."""

import pytest
from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.geometry_qualification import GeometryQualification
from game_predictor_api.domain.image_geometry_v2 import (
    SourceImageBounds,
    SourcePoint,
    SourceQuad,
    unavailable_source_cell_indices,
)
from game_predictor_worker.images.qualified_manual_geometry import apply_qualified_page_override


@pytest.mark.parametrize("start,count", ((1234, 9), (499996, 5)))
def test_partial_source_keeps_exact_filename_slots_including_terminal_short_range(start, count):
    quads, qualifications = [], []
    for index in range(count):
        left, top = -10 + (index % 3) * 100, 10 + (index // 3) * 60
        quad = SourceQuad(
            (
                SourcePoint(left, top),
                SourcePoint(left + 80, top + 3),
                SourcePoint(left + 78, top + 43),
                SourcePoint(left - 2, top + 40),
            )
        )
        mask = unavailable_source_cell_indices(
            quad, source=SourceImageBounds(300, 200), topology=BoardTopology(3, 5)
        )
        qualification = (
            GeometryQualification("pending_partial", mask, True, "missing_pixels")
            if mask
            else GeometryQualification()
        )
        quads.append(quad.to_dict())
        qualifications.append(qualification.to_dict())
    entry = {
        "status": "registered",
        "registrationVersion": "manual-page-geometry-override-v1",
        "quads": quads,
        "slotQualifications": qualifications,
    }
    result = apply_qualified_page_override(
        {}, entry, width=300, height=200, start=start, count=count, topology=BoardTopology(3, 5)
    )
    assert len(result["boards"]) == count
    assert [board["sequenceNumber"] for board in result["boards"]] == list(
        range(start, start + count)
    )
    assert [board["positionIndex"] for board in result["boards"]] == list(range(count))
    assert result["geometrySource"] == "manual"
    assert result["boards"][0]["unavailableCellIndices"] == [0, 5, 10]
    assert result["boards"][1]["unavailableCellIndices"] == []
    assert entry["slotQualifications"] == qualifications  # replay input remains immutable
    assert (
        apply_qualified_page_override(
            {}, entry, width=300, height=200, start=start, count=count, topology=BoardTopology(3, 5)
        )
        == result
    )
