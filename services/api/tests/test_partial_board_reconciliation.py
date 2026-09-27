"""Repair manifest integrity and adopted source geometry regressions."""

from copy import deepcopy
from uuid import uuid4

import pytest
from game_predictor_api.domain.board_topology import LEGACY_IMAGE_BOARD_TOPOLOGY
from game_predictor_api.domain.partial_board_reconciliation import (
    PILOT_SEQUENCES,
    ReconciliationError,
    blocked_board,
    build_manifest,
    digest,
    human_decisions,
    validate_manifest,
)
from game_predictor_api.storage.symbol_cell_source_visibility import (
    current_source_visibilities,
    pinned_visibility_geometry,
)


def _quad(left, right):
    return [
        {"x": left, "y": 10},
        {"x": right, "y": 10},
        {"x": right, "y": 80},
        {"x": left, "y": 80},
    ]


def _manifest():
    return build_manifest(
        game_id=uuid4(),
        storage_generation=2,
        boards=[blocked_board(number, "MISSING", "No owner") for number in PILOT_SEQUENCES],
    )


@pytest.mark.parametrize("change", ["hash", "order", "duplicates", "scope", "version"])
def test_manifest_rejects_corruption_or_changed_scope_even_with_recomputed_hash(change):
    value = _manifest()
    if change == "hash":
        value["previewSha256"] = "0" * 64
    else:
        if change == "order":
            value["boards"].reverse()
        elif change == "duplicates":
            value["boards"][1] = deepcopy(value["boards"][0])
        elif change == "scope":
            value["sequences"].append(1)
        else:
            value["schema"] = "future-unreviewed-version"
        value["previewSha256"] = digest({k: v for k, v in value.items() if k != "previewSha256"})
    with pytest.raises(ReconciliationError, match="Preview input"):
        validate_manifest(value)


def test_pinned_source_geometry_ignores_stale_board_quad():
    source = {
        "id": str(uuid4()),
        "checksum_sha256": "a" * 64,
        "oriented_width": 100,
        "oriented_height": 100,
    }
    revision = {
        "id": str(uuid4()),
        "source_image_id": source["id"],
        "source_checksum_sha256": source["checksum_sha256"],
        "oriented_width": 100,
        "oriented_height": 100,
        "geometry_checksum_sha256": "b" * 64,
        "board_geometries": [
            {"positionIndex": 0, "sequenceNumber": 60856, "finalQuad": _quad(-100, -10)}
        ],
    }
    board = {
        "asset_mode": "virtual_source",
        "source_geometry_revision_id": revision["id"],
        "geometry_checksum_sha256": "b" * 64,
        "position_index": 0,
        "sequence_number": 60856,
        "board_geometry": {"quad": _quad(10, 80)},
    }
    geometry = pinned_visibility_geometry(board=board, source=source, source_geometry=revision)
    assert (
        current_source_visibilities(
            geometry=geometry, width=100, height=100, topology=LEGACY_IMAGE_BOARD_TOPOLOGY
        )
        == ("outside",) * 15
    )
    future = dict(revision, id=str(uuid4()))
    with pytest.raises(ValueError, match="provenance"):
        pinned_visibility_geometry(board=board, source=source, source_geometry=future)
    revision["board_geometries"][0]["sequenceNumber"] += 1
    with pytest.raises(ValueError, match="sequence"):
        pinned_visibility_geometry(board=board, source=source, source_geometry=revision)

    revision["board_geometries"] = [
        {
            "positionIndex": 2,
            "sequenceNumber": 60856,
            "symbolGridQuad": None,
            "finalQuad": _quad(10, 80),
        }
    ]
    board["position_index"] = 2
    geometry = pinned_visibility_geometry(board=board, source=source, source_geometry=revision)
    assert geometry["latticeBoundsQuad"] == _quad(10, 80)
    revision["board_geometries"].append(dict(revision["board_geometries"][0]))
    with pytest.raises(ValueError, match="exactly one"):
        pinned_visibility_geometry(board=board, source=source, source_geometry=revision)


def test_legacy_uses_adopted_manual_cells_not_original_quad():
    board = {
        "asset_mode": "legacy_file",
        "geometry_revision": 2,
        "board_geometry": {"quad": _quad(10, 80)},
    }
    geometry = {"quad": _quad(-100, -10)}
    assert (
        pinned_visibility_geometry(
            board=board,
            source={},
            source_geometry=None,
            manual_geometry={"revision": 2, "geometry": geometry},
        )
        == geometry
    )
    with pytest.raises(ValueError, match="revision"):
        pinned_visibility_geometry(
            board=board,
            source={},
            source_geometry=None,
            manual_geometry={"revision": 1, "geometry": geometry},
        )


def test_human_digest_protects_label_and_quality_but_allows_visibility_badge():
    before = [
        {
            "id": "cell",
            "cell_index": 3,
            "assignment_source": "human",
            "assigned_symbol_id": "symbol",
            "review_state": "pending",
            "quality_issue": None,
        }
    ]
    partial = [dict(before[0], quality_issue="partial_visibility")]
    assert human_decisions(before) == human_decisions(partial)
    assert human_decisions(before) != human_decisions([dict(before[0], assigned_symbol_id="other")])
    assert human_decisions(before) != human_decisions([dict(before[0], quality_issue="unreadable")])
