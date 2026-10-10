"""Exact approved neural targets retain their interior and legacy export contract."""

from __future__ import annotations

import copy
import hashlib
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from game_predictor_api.domain.image_geometry_v2 import canonical_json_bytes
from game_predictor_worker.vision_lab import production_geometry as geometry
from game_predictor_worker.vision_lab import production_snapshot

from scripts import vision_lab_geometry_export as exporter


def _fixture(*, shift: float = 0.0):
    nodes = list(geometry.derive_grid_nodes(((100, 50), (600, 50), (600, 350), (100, 350))))
    nodes[7] = (nodes[7][0] + 2.123456789, nodes[7][1] + 7.987654321)
    nodes = [(x + shift, y) for x, y in nodes]
    raw_nodes = [{"x": x, "y": y} for x, y in nodes]
    quads = geometry.cell_quads_from_nodes(nodes)
    outer = [raw_nodes[index] for index in (0, 5, 23, 18)]
    render = {
        "latticeNodes": raw_nodes,
        "cells": [
            {"cellIndex": index, "renderSpec": {"sourceQuad": [{"x": x, "y": y} for x, y in quad]}}
            for index, quad in enumerate(quads)
        ],
    }
    board = {
        "id": uuid4(),
        "position_index": 0,
        "sequence_number": 101,
        "source_revision_id": uuid4(),
        "source_revision": 2,
        "manifest_present": True,
        "manifest_topology": {"rows": 3, "columns": 5},
        "grid_rows": 3,
        "grid_columns": 5,
        "manifest_coordinate_space": geometry.COORDINATE_SPACE,
        "manifest_cell_indices": list(range(15)),
        "manifest_cell_quads": [[{"x": x, "y": y} for x, y in quad] for quad in quads],
        "unavailable_cell_indices": [],
        "geometry_revision": 1,
        "approved_geometry_revision": 1,
        "geometry_approved_by": "local-admin",
        "geometry_approved_at": datetime.now(UTC),
        "revision_authors": [[1, "local-admin"]],
        "source_geometry_source": "manual",
        "source_status": "accepted",
        "source_created_by": "local-admin",
        "source_engine_kind": "manual_v1",
        "source_engine_version": "test-v1",
        "geometry_engine_name": "manual_v1",
        "geometry_engine_version": "test-v1",
        "geometry_checksum_sha256": "a" * 64,
        "manifest_extractor_version": "test-v1",
        "completeness_status": "complete",
        "geometry_qualification": None,
        "revision_corners": outer,
        "source_symbol_grid_quad": outer,
        "source_final_quad": outer,
        "board_symbol_grid_quad": outer,
        "source_lattice_nodes": raw_nodes,
        "revision_geometry": {"latticeNodes": raw_nodes},
        "revision_virtual_render_spec": render,
        "revision_render_checksum": hashlib.sha256(canonical_json_bytes(render)).hexdigest(),
    }
    image = {
        "id": uuid4(),
        "active_board_slots": [0],
        "width": 800,
        "height": 450,
        "import_job_id": uuid4(),
        "checksum_sha256": "b" * 64,
        "relative_path": "originals/test.jpg",
    }
    return image, board, nodes


def test_approved_exact_interior_is_exported_without_rounding_or_interpolation():
    image, board, nodes = _fixture()
    row = exporter._build_row(uuid4(), image, board, None, {})
    assert row["geometry"]["nodes"] == [list(point) for point in nodes]
    assert row["geometry"]["nodes"][7][0] == 202.123456789
    assert row["geometry"]["quadSource"] == "persisted_exact_lattice_v1"
    assert row["geometry"]["maxManifestDeviationPx"] == 0
    assert row["partial"]["cellVisibility"] == ["full"] * 15
    assert row["label"]["basis"] == "human_approval"


@pytest.mark.parametrize("approved", [0, None, 1])
def test_initial_source_lattice_approval_requires_no_recrop_but_must_be_current(approved):
    image, board, nodes = _fixture()
    board.update(
        geometry_revision=0,
        approved_geometry_revision=approved,
        revision_geometry=None,
        revision_virtual_render_spec=None,
        revision_authors=[],
    )
    if approved != 0:
        with pytest.raises(geometry.ProductionGeometryError) as error:
            exporter._build_row(uuid4(), image, board, None, {})
        assert error.value.code == geometry.EXCLUSION_HUMAN_APPROVAL_REQUIRED
    else:
        row = exporter._build_row(uuid4(), image, board, None, {})
        assert row["geometry"]["nodes"] == [list(point) for point in nodes]
        assert row["label"]["basis"] == "human_approval"


@pytest.mark.parametrize(
    "actor,approved",
    [("local-admin", None), ("local-admin", 0), ("system:grid-reverify-777-v1", 1)],
)
def test_saved_or_system_approved_neural_geometry_is_not_a_human_target(actor, approved):
    image, board, _ = _fixture()
    board.update(geometry_approved_by=actor, approved_geometry_revision=approved)
    with pytest.raises(geometry.ProductionGeometryError) as error:
        exporter._build_row(uuid4(), image, board, None, {})
    assert error.value.code == geometry.EXCLUSION_HUMAN_APPROVAL_REQUIRED


@pytest.mark.parametrize(
    "corruption",
    [
        "revision_missing",
        "render_missing",
        "both_missing",
        "all_missing",
        "checksum",
        "interior",
        "bad_count",
    ],
)
def test_damaged_exact_lattice_never_falls_back_to_good_outer_corners(corruption):
    image, board, _ = _fixture()
    board = copy.deepcopy(board)
    if corruption in {"revision_missing", "both_missing", "all_missing"}:
        board["revision_geometry"].pop("latticeNodes")
    if corruption in {"render_missing", "both_missing", "all_missing"}:
        board["revision_virtual_render_spec"].pop("latticeNodes")
    if corruption == "all_missing":
        board["source_lattice_nodes"] = None
    if corruption == "checksum":
        board["revision_render_checksum"] = "c" * 64
    if corruption in {"interior", "bad_count"}:
        nodes = board["revision_geometry"]["latticeNodes"]
        if corruption == "interior":
            nodes[7]["x"] += 4
        else:
            nodes.pop()
        board["revision_virtual_render_spec"]["latticeNodes"] = nodes
        board["revision_render_checksum"] = hashlib.sha256(
            canonical_json_bytes(board["revision_virtual_render_spec"])
        ).hexdigest()
    with pytest.raises(geometry.ProductionGeometryError):
        exporter._build_row(uuid4(), image, board, None, {})


def test_partial_exact_export_retains_visibility_and_masks_all_outside_cells():
    image, board, nodes = _fixture(shift=-450)
    board["completeness_status"] = "pending_partial"
    board["unavailable_cell_indices"] = [0, 5, 10]
    for key in ("manifest_cell_indices", "manifest_cell_quads"):
        board[key] = [value for index, value in enumerate(board[key]) if index not in {0, 5, 10}]
    row = exporter._build_row(uuid4(), image, board, None, {})
    assert row["geometry"]["nodes"] == [list(point) for point in nodes]
    assert (
        row["partial"]["cellVisibility"] == ["outside", "outside", "outside", "partial", "full"] * 3
    )
    assert row["partial"]["unavailableCellIndices"] == [0, 1, 2, 5, 6, 7, 10, 11, 12]
    assert row["partial"]["manifestMissingCellIndices"] == [0, 5, 10]
    snapshot = production_snapshot._slim_row(row)
    assert snapshot["cellVisibility"] == row["partial"]["cellVisibility"]
    assert snapshot["nodes"] == row["geometry"]["nodes"]
    assert snapshot["unavailableCellIndices"] == row["partial"]["unavailableCellIndices"]


def test_exact_export_rejects_sub_legacy_tolerance_manifest_quad_drift():
    image, board, _ = _fixture()
    board["manifest_cell_quads"][0][0]["x"] += 0.005
    with pytest.raises(geometry.ProductionGeometryError) as error:
        exporter._build_row(uuid4(), image, board, None, {})
    assert error.value.code == geometry.EXCLUSION_NODES_MISMATCH


def test_legacy_four_corner_row_retains_rounding_and_unapproved_label_behavior():
    image, board, _ = _fixture()
    nodes = geometry.derive_grid_nodes(((100.123456, 50), (600, 50), (600, 350), (100, 350)))
    quads = geometry.cell_quads_from_nodes(nodes)
    corners = [{"x": nodes[index][0], "y": nodes[index][1]} for index in (0, 5, 23, 18)]
    board.update(
        source_lattice_nodes=None,
        revision_geometry=None,
        revision_virtual_render_spec=None,
        approved_geometry_revision=None,
        revision_corners=corners,
        manifest_cell_quads=[[{"x": x, "y": y} for x, y in quad] for quad in quads],
    )
    row = exporter._build_row(uuid4(), image, board, None, {})
    assert row["geometry"]["nodes"] == [[round(x, 4), round(y, 4)] for x, y in nodes]
    assert row["label"]["basis"] == "human_saved_revision_unapproved"
    assert "cellVisibility" not in row["partial"]
    assert "cellVisibility" not in production_snapshot._slim_row(row)


def test_snapshot_rejects_outside_target_without_unavailable_mask():
    image, board, _ = _fixture()
    row = exporter._build_row(uuid4(), image, board, None, {})
    row["partial"]["cellVisibility"][0] = "outside"
    with pytest.raises(ValueError, match="CANDIDATE_LATTICE_VISIBILITY_INVALID"):
        production_snapshot._slim_row(row)


def test_valid_explicit_corner_conversion_retains_legacy_behavior():
    image, board, _ = _fixture()
    nodes = geometry.derive_grid_nodes(((100.123456, 50), (600, 50), (600, 350), (100, 350)))
    quads = geometry.cell_quads_from_nodes(nodes)
    board.update(
        source_lattice_nodes=None,
        revision_geometry={},
        revision_virtual_render_spec={"cells": []},
        revision_corners=[{"x": x, "y": y} for x, y in (nodes[0], nodes[5], nodes[23], nodes[18])],
        manifest_cell_quads=[[{"x": x, "y": y} for x, y in quad] for quad in quads],
    )
    board["revision_render_checksum"] = hashlib.sha256(
        canonical_json_bytes(board["revision_virtual_render_spec"])
    ).hexdigest()
    row = exporter._build_row(uuid4(), image, board, None, {})
    assert row["geometry"]["quadSource"] == "board_revision_corners"
    assert row["geometry"]["nodes"] == [[round(x, 4), round(y, 4)] for x, y in nodes]
