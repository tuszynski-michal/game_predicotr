"""A sibling exception never becomes a general pointer/checksum bypass."""

import copy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from game_predictor_api.storage.grid_quality_observations import geometry_approval_fence
from game_predictor_api.storage.grid_quality_repoint import unchanged_frozen_target


def example():
    game, source, before, after = (str(uuid4()) for _ in range(4))
    target = {
        "board": {
            "id": str(uuid4()),
            "source_image_id": source,
            "position_index": 1,
            "sequence_number": 102,
            "geometry_revision": 0,
            "source_geometry_revision_id": before,
            "geometry_checksum_sha256": "a" * 64,
            "board_geometry": {"latticeNodes": [{"x": 2, "y": 3}], "binding": "exact"},
        },
        "review": {"id": str(uuid4()), "status": "pending", "resolution_revision": 0},
        "cells": [
            {
                "id": str(uuid4()),
                "source_geometry_revision_id": before,
                "approved_source_geometry_revision_id": before,
                "crop_sample_id": "c" * 64,
                "revision": 1,
                "assigned_symbol_id": str(uuid4()),
                "assignment_source": "human",
            }
        ],
        "renders": [{"source_geometry_revision_id": before, "manifest_checksum_sha256": "d" * 64}],
        "owner": None,
        "foreignOwner": None,
    }
    frozen = geometry_approval_fence(target)
    current = copy.deepcopy(target)
    current["board"].update(source_geometry_revision_id=after, geometry_checksum_sha256="b" * 64)
    current["cells"][0].update(
        source_geometry_revision_id=after, approved_source_geometry_revision_id=after
    )
    current["renders"][0]["source_geometry_revision_id"] = after
    old = {
        "id": before,
        "game_id": game,
        "source_image_id": source,
        "geometry_checksum_sha256": "a" * 64,
        "status": "accepted",
        "source_checksum_sha256": "e" * 64,
        "normalized_pixel_checksum_sha256": "f" * 64,
        "board_geometries": [{"positionIndex": 1, "sequenceNumber": 102, "binding": "exact"}],
    }
    new = old | {
        "id": after,
        "geometry_checksum_sha256": "b" * 64,
        "geometry_source": "manual",
        "engine_kind": "manual_v1",
        "created_by": "human",
    }
    return game, source, frozen, current, old, new


def reader(old, new, parents):
    def execute(sql, params):
        if "SELECT r.id FROM image_board_geometry_revisions" in str(sql):
            return SimpleNamespace(scalar_one_or_none=lambda: parents[0] if parents else None)
        value = old if params["id"] == old["id"] else new
        return SimpleNamespace(scalar_one_or_none=lambda: value)

    return SimpleNamespace(connection=lambda: SimpleNamespace(execute=execute))


@pytest.mark.parametrize(
    "change",
    [
        "automatic",
        "missing_event",
        "source",
        "slot",
        "crop",
        "decision",
        "owner",
        "issue",
        "revision",
    ],
)
def test_repoint_requires_positive_manual_edge_and_every_protected_identity(change):
    game, source, frozen, current, old, new = example()
    parents = [old["id"]]
    if change == "automatic":
        new.update(geometry_source="auto", engine_kind="neural_grid_v1")
    elif change == "missing_event":
        parents = []
    elif change == "source":
        new["normalized_pixel_checksum_sha256"] = "0" * 64
    elif change == "slot":
        new["board_geometries"] = [{"positionIndex": 1, "sequenceNumber": 999}]
    elif change == "crop":
        current["cells"][0]["crop_sample_id"] = "0" * 64
    elif change == "decision":
        current["cells"][0]["assigned_symbol_id"] = str(uuid4())
    elif change == "owner":
        current["foreignOwner"] = {"id": str(uuid4())}
    elif change == "issue":
        current["cells"][0].update(quality_issue="grid_issue", review_state="pending")
    else:
        current["board"]["geometry_revision"] = 1
    assert not unchanged_frozen_target(reader(old, new, parents), game, source, frozen, current)


def test_proven_manual_repoint_only_normalizes_aggregate_references():
    game, source, frozen, current, old, new = example()
    assert unchanged_frozen_target(reader(old, new, [old["id"]]), game, source, frozen, current)
