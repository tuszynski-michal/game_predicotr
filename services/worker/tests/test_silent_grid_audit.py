from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from game_predictor_worker.vision_lab import silent_grid_audit as audit
from game_predictor_worker.vision_lab.neural_grid_data import LATTICE


def board(x: float, y: float, cell_w: float = 40.0, cell_h: float = 34.0) -> np.ndarray:
    """Axis-aligned 5 x 3 grid with its top-left corner at (x, y)."""

    return (LATTICE * np.array([cell_w, cell_h], np.float32) + np.array([x, y], np.float32)).astype(
        np.float32
    )


def page() -> list[np.ndarray]:
    return [board(100 + 260 * c, 80 + 170 * r) for r in range(3) for c in range(3)]


def test_identical_grids_are_within_tolerance() -> None:
    boards = page()
    results, unexplained = audit.compare_photo(boards, boards)
    assert [r["class"] for r in results] == [audit.WITHIN] * 9
    assert unexplained == []


@pytest.mark.parametrize(
    ("dx", "dy", "expected", "shift"),
    [
        (0.0, 34.0, audit.ROW_SHIFT, [0, 1]),
        (0.0, -34.0, audit.ROW_SHIFT, [0, -1]),
        (40.0, 0.0, audit.COLUMN_SHIFT, [1, 0]),
        (-40.0, 0.0, audit.COLUMN_SHIFT, [-1, 0]),
        (40.0, 34.0, audit.DIAGONAL_SHIFT, [1, 1]),
    ],
)
def test_period_shift_of_the_saved_grid_is_classified(
    dx: float, dy: float, expected: str, shift: list[int]
) -> None:
    network = page()
    saved = list(network)
    saved[2] = network[2] + np.array([dx, dy], np.float32)
    results, unexplained = audit.compare_photo(saved, network)
    assert results[2]["class"] == expected
    assert results[2]["shift"] == shift
    assert results[2]["shiftNme"] < 1e-4
    assert results[2]["nme"] > 0.1
    assert [r["class"] for i, r in enumerate(results) if i != 2] == [audit.WITHIN] * 8
    # The network board explained by the shift is not reported as a network-only board.
    assert unexplained == []


def test_scale_disagreement_and_unmatched_boards() -> None:
    network = page()
    saved = list(network)
    centre = network[4].mean(axis=0)
    saved[4] = (network[4] - centre) * 1.12 + centre  # 12% larger, not a whole-cell shift
    del saved[8]  # the network sees a board the saved data lacks
    network_missing = list(network[:7])  # the network misses board 7
    network_missing.append(network[8])
    saved_full = saved[:8]
    results, unexplained = audit.compare_photo(saved_full, network_missing)
    classes = [r["class"] for r in results]
    assert classes[4] == audit.SCALE_ROTATION
    assert results[4]["scaleRatio"] == pytest.approx(1 / 1.12, rel=1e-3)
    assert classes[7] == audit.SAVED_ONLY
    assert unexplained == [7]  # network[8] has no saved board


def test_slight_disagreement_is_not_a_shift() -> None:
    network = page()
    saved = list(network)
    saved[0] = network[0] + np.array([6.0, 0.0], np.float32)  # 0.15 cell, outside tolerance
    results, _ = audit.compare_photo(saved, network)
    assert results[0]["class"] == audit.SCALE_ROTATION
    assert results[0]["shift"] == [0, 0] or results[0]["shiftNme"] >= results[0]["nme"] * 0.5


def test_repair_jsonl_cuts_a_torn_line(tmp_path: Path) -> None:
    path = tmp_path / "network.jsonl"
    path.write_bytes(
        audit.dumps_line({"imageId": "a"}) + audit.dumps_line({"imageId": "b"}) + b'{"imageId": "c'
    )
    assert audit.repair_jsonl(path) == {"a", "b"}
    assert path.read_bytes().endswith(b"\n")
    assert audit.repair_jsonl(path) == {"a", "b"}


def test_compact_saved_groups_rows_per_photo(tmp_path: Path) -> None:
    def row(image: str, position: int, level: str) -> dict[str, object]:
        return {
            "sourceImageId": image,
            "recognizedBoardId": f"{image}-{position}",
            "gameId": audit.GAME_777,
            "importJobId": "job",
            "sourceChecksumSha256": "0" * 64,
            "sourceRelativePath": "originals/00/x.jpg",
            "orientedWidth": 10,
            "orientedHeight": 10,
            "expectedBoardsOnImage": 2,
            "positionIndex": position,
            "sequenceNumber": position + 1,
            "family": {"sourceDisplayName": "cut", "familyId": "f"},
            "label": {"level": level, "basis": "b", "approvalActor": None, "geometryRevision": 0},
            "geometry": {"quadSource": "q", "nodes": board(0, 0).tolist()},
            "symbolSignals": {"cells": 15, "humanDecidedCells": 3},
            "difficulty": {"pageRow": 0, "pageColumn": position},
        }

    candidates = tmp_path / "candidates.jsonl"
    candidates.write_bytes(
        b"".join(
            audit.dumps_line(r) for r in (row("a", 1, "S"), row("a", 0, "B"), row("b", 0, "G"))
        )
    )
    result = audit.compact_saved(candidates, tmp_path / "saved.jsonl", {"a": "training"})
    assert result == {"photos": 2, "boards": 3, "levels": {"B": 1, "G": 1, "S": 1}}
    photos = [json.loads(line) for line in (tmp_path / "saved.jsonl").read_text().splitlines()]
    assert [b["positionIndex"] for b in photos[0]["boards"]] == [0, 1]
    assert photos[0]["snapshotRole"] == "training" and photos[1]["snapshotRole"] is None
    with pytest.raises(ValueError, match="SILENT_GRID_SAVED_EXISTS"):
        audit.compact_saved(candidates, tmp_path / "saved.jsonl", {})


def test_review_store_persists_and_rejects_conflicts(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient
    from game_predictor_worker.vision_lab import silent_grid_review as review

    (tmp_path / "cases").mkdir()
    (tmp_path / "cases" / "p00001.jpg").write_bytes(b"jpg")
    items = [
        {"itemId": "p00001", "class": audit.ROW_SHIFT, "image": "cases/p00001.jpg"},
        {"itemId": "s00001", "class": audit.SAVED_ONLY, "image": "cases/s00001.jpg"},
    ]
    (tmp_path / "cases.json").write_text(json.dumps({"items": items}), encoding="utf-8")
    store = review.VerdictStore(tmp_path)
    store.decide("p00001", "network", 0)
    with pytest.raises(review.RevisionConflictError):
        store.decide("s00001", "saved", 0)
    store.decide("s00001", "unsure", 1)
    store.decide("s00001", None, 2)
    reloaded = review.VerdictStore(tmp_path)
    assert reloaded.revision == 3 and reloaded.verdicts == {"p00001": "network"}
    assert reloaded.summary()["byClass"] == {
        audit.ROW_SHIFT: {"network": 1},
        audit.SAVED_ONLY: {"open": 1},
    }
    client = TestClient(review.create_app(reloaded, 8107), base_url="http://127.0.0.1:8107")
    assert client.get("/cases/p00001.jpg").content == b"jpg"
    assert client.get("/cases/..%2Fcases.json").status_code == 404
    denied = client.post(
        "/api/verdicts", json={"itemId": "s00001", "verdict": "saved", "baseRevision": 3}
    )
    assert denied.status_code == 403  # no own origin
    accepted = client.post(
        "/api/verdicts",
        json={"itemId": "s00001", "verdict": "saved", "baseRevision": 3},
        headers={"Origin": "http://127.0.0.1:8107"},
    )
    assert accepted.status_code == 200 and accepted.json()["revision"] == 4
    (tmp_path / "cases.json").write_text(json.dumps({"items": items[:1]}), encoding="utf-8")
    with pytest.raises(ValueError, match="FOREIGN_CASES"):
        review.VerdictStore(tmp_path)
