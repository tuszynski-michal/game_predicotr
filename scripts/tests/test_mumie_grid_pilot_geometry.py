"""Tests for grid diagnosis with a known source and the production 15-field renderer."""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mumie_grid_pilot as pilot  # noqa: F401 (loads project source packages like the CLI)
from game_predictor_worker.geometry_core.preprocessing import transform_points

from scripts.mumie_grid_pilot_geometry import cell_sheet, cell_support, paired_geometry
from scripts.mumie_grid_pilot_review import frame_for
from scripts.mumie_grid_pilot_sources import fresh_inventory


def lattice():
    return np.asarray([(20 + 40 * x, 20 + 40 * y) for y in range(4) for x in range(6)], np.float32)


def test_separate_plane_translation_from_internal_deformation_under_perspective():
    target = lattice()
    shifted = target + [10, 0]
    warped = np.array([[1.3, 0.12, 23], [-0.13, 0.9, 37], [0.0011, -0.0007, 1]])
    for h in (np.eye(3), warped):
        fixed = transform_points(target, h)
        data = paired_geometry(transform_points(shifted, h), fixed)
        assert data["perimeter"] == pytest.approx(0.25, abs=1e-5)
        assert data["centre"] == pytest.approx(0.25, abs=1e-5)
        assert data["insideAfterCornerAlignment"] < 1e-5
        internal = target.copy()
        internal[8, 1] -= 12
        data = paired_geometry(transform_points(internal, h), fixed)
        assert data["insideAfterCornerAlignment"] == pytest.approx(0.3, abs=1e-5)
        assert data["perimeter"] < 1e-5
        assert paired_geometry(np.zeros((24, 2), np.float32), fixed) is None


def test_context_and_source_pixels_reveal_clipped_fields_on_edges_and_inside(tmp_path):
    rgb = np.zeros((160, 240, 3), np.uint8)
    for y in range(3):
        for x in range(5):
            left, top = 20 + 40 * x, 20 + 40 * y
            # Every synthetic symbol has a red left end and a blue right end.
            rgb[top + 13 : top + 27, left + 2 : left + 6] = [255, 0, 0]
            rgb[top + 13 : top + 27, left + 34 : left + 38] = [0, 0, 255]
    Image.fromarray(rgb).save(tmp_path / "seq_1-9.jpg", quality=98, subsampling=0)
    frame = frame_for(fresh_inventory(tmp_path, str(uuid4()))[0])
    context = {
        "topologyRulesVersionId": str(uuid4()),
        "sequenceRangeStart": 1,
        "sequenceRangeEnd": 9,
        "importJobId": str(uuid4()),
        "fileExecutionKey": "a" * 64,
        "renderConfiguration": {
            "extractorVersion": "virtual-cell-renderer-source-direct-v4",
            "preprocessingVersion": "rgb-resize64-normalize-half-v1",
            "interpolation": "opencv-inter-linear-v1",
            "paddingFraction": 0.0,
            "outputWidth": 64,
            "outputHeight": 64,
        },
    }
    target = {"positionIndex": 0, "sequenceNumber": 1}
    correct = lattice()
    previous = correct.reshape(4, 6, 2).copy()
    previous[:, 0, 0] += 10  # cuts the left edge of fields 1, 6 and 11
    previous[:, 2, 0] -= 10  # cuts the right edge of fields 2, 7 and 12

    def observations(nodes):
        sheet, details = cell_sheet(frame, nodes, target, context)
        assert len(details) == 15 and all(d["reason"] is None for d in details)
        raster = np.asarray(sheet)
        evidence = []
        for idx in range(15):
            row, col = divmod(idx, 5)
            tile = raster[row * 64 : (row + 1) * 64, col * 64 : (col + 1) * 64]
            red = (tile[:, :, 0] > 200) & (tile[:, :, 1] < 40) & (tile[:, :, 2] < 40)
            blue = (tile[:, :, 2] > 200) & (tile[:, :, 1] < 40) & (tile[:, :, 0] < 40)
            evidence.append((red.any(), blue.any()))
        return evidence, np.asarray(cell_support(details, correct))

    markers, coverage = observations(correct)
    assert markers == [(True, True)] * 15
    np.testing.assert_allclose(coverage, 1.0)
    markers, coverage = observations(previous.reshape(24, 2))
    assert all(markers[i] == (False, True) for i in (0, 5, 10))
    assert all(markers[i] == (True, False) for i in (1, 6, 11))
    np.testing.assert_allclose(coverage[[0, 1, 5, 6, 10, 11]], 0.75)
    # The same correct grid with a positive crop inset can also cut real marks.
    context["renderConfiguration"]["paddingFraction"] = 0.18
    markers, coverage = observations(correct)
    assert markers == [(False, False)] * 15
    np.testing.assert_allclose(coverage, (1 - 2 * 0.18) ** 2, atol=1e-6)
