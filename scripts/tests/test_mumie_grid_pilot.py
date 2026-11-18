from __future__ import annotations

import json
import sys
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mumie_grid_pilot as pilot
from game_predictor_worker.geometry_core.inference import BoardDetection
from mumie_grid_pilot_review import choose_sources, frame_for, infer, score
from mumie_grid_pilot_sources import fresh_inventory

FULL_CELL = {"renderConfiguration": {"paddingFraction": 0}}


def sample_rows(count=100):
    return [
        {
            "id": str(i),
            "sha": f"{i + 1:064x}",
            "pix": f"{i + 200:064x}",
            "groups": ["session"],
            "aliases": [],
            "start": 9 * i + 1,
            "end": 9 * i + 9,
        }
        for i in range(count)
    ]


def test_sampling_precedes_detection_and_reserves_recording(tmp_path):
    rows = sample_rows()
    assert choose_sources(rows, set()) == choose_sources(list(reversed(rows)), set())
    rows[0]["pix"] = rows[1]["pix"]
    with pytest.raises(ValueError, match="99"):
        choose_sources(rows, set())
    with pytest.raises(ValueError, match="0 "):
        choose_sources(rows, {"session"})
    clock = SimpleNamespace(
        execute=lambda *a: SimpleNamespace(scalar_one=lambda: datetime.now(UTC))
    )
    with pilot.store(tmp_path) as ledger:
        with pytest.raises(ValueError, match="wcięcie 0%"):
            pilot.freeze(
                clock,
                ledger,
                "first",
                sample_rows(101),
                {"type": "folder"},
                {},
                {"renderConfiguration": {"paddingFraction": 0.08}},
            )
        result = pilot.freeze(
            clock, ledger, "first", sample_rows(101), {"type": "folder"}, {}, FULL_CELL
        )
        assert result["boards"] == 100 and result["protectedPhotos"] == 101
    with pilot.store(tmp_path) as restarted, pytest.raises(ValueError):
        pilot.freeze(
            clock, restarted, "another", sample_rows(101), {"type": "folder"}, {}, FULL_CELL
        )


def test_eval_is_paired_and_no_lost_or_unassessed_cells():
    present = {"state": "detected", "cells": [True] * 15}
    cards = [{"id": str(i), "A": present, "B": present} for i in range(100)]
    key = {c["id"]: ("A" if int(c["id"]) % 2 else "B") for c in cards}
    votes = {c["id"]: {"A": ["full"] * 15, "B": ["full"] * 15} for c in cards}
    for i in range(5):
        votes[str(i)][key[str(i)]][0] = "cut"
    assert score(cards, key, votes, True)["recommendActivation"]
    assert not score(cards, key, votes, False)["recommendActivation"]
    votes["12"]["A"][3] = "cut"
    report = score(cards, key, votes, True)
    assert (
        report["newClippedSymbols"] == 1
        and report["net"] == 4
        and not report["recommendActivation"]
    )
    cards[12]["A"] = {"state": "missing", "cells": []}
    votes["12"]["A"] = ["missing"] * 15
    report = score(cards, key, votes, True)
    assert report["boards"] == 100 and report["previouslyFullNowUnassessable"] == 15
    del votes["12"]
    with pytest.raises(ValueError):
        score(cards, key, votes, True)


def test_screen_grid_partial_binding_real_renderer_and_input(tmp_path):
    group = str(uuid4())
    src = tmp_path / "recording"
    src.mkdir()
    rgb = np.zeros((480, 720, 3), np.uint8)
    rgb[:, :, 0] = np.arange(720, dtype=np.uint16) % 255
    Image.fromarray(rgb).save(src / "seq_1-9.jpg")
    row = fresh_inventory(src, group)[0]
    frame = frame_for(row)
    context = {
        "topologyRulesVersionId": str(uuid4()),
        "renderConfiguration": {
            "paddingFraction": 0.0,
            "outputWidth": 64,
            "outputHeight": 64,
            "interpolation": "opencv-inter-linear-v1",
            "extractorVersion": "virtual-cell-renderer-source-direct-v4",
            "preprocessingVersion": "rgb-resize64-normalize-half-v1",
        },
    }
    detections = []
    for idx in [0, 1, 2, 3, 5, 6, 7, 8]:
        x, y = 30 + 230 * (idx % 3), 25 + 150 * (idx // 3)
        nodes = np.array(
            [[x + 24 * col, y + 25 * r] for r in range(4) for col in range(6)], np.float32
        )
        detections.append(BoardDetection(0.99, nodes[[0, 5, 23, 18]], nodes=nodes))
    engine = SimpleNamespace(
        analyse=lambda image: detections,
        settings=SimpleNamespace(
            board=SimpleNamespace(canvas=(320, 192), margin=0.1),
            screen=SimpleNamespace(long_side=768, pad_multiple=32),
        ),
    )
    missed = infer(
        engine, frame, {**row, "position": 4}, context, tmp_path / "missing", diagnostic=True
    )
    assert missed["state"] == "missing" and (tmp_path / "missing" / "screen-input.png").is_file()
    result = infer(
        engine, frame, {**row, "position": 5}, context, tmp_path / "found", diagnostic=True
    )
    assert result["cells"] == [True] * 15
    for name in ("geometry.png", "input.png", "screen-input.png", "14.png"):
        assert (tmp_path / "found" / name).is_file()
    assert Image.open(tmp_path / "found" / "14.png").size == (64, 64)


def test_a_missing_named_range_stops_freeze(tmp_path):
    Image.new("RGB", (80, 80)).save(tmp_path / "unknown.jpg")
    with pytest.raises(ValueError):
        fresh_inventory(tmp_path, str(uuid4()))


def test_blind_package_through_scoring_and_restart(tmp_path, monkeypatch):
    study = str(uuid4())
    base = {"active": "baseline-secret"}
    candidate = "candidate-secret"
    args = SimpleNamespace(
        root=tmp_path,
        artifacts=tmp_path,
        study=study,
        candidate=candidate,
        command="blind",
        votes=tmp_path / "votes.json",
    )
    now = SimpleNamespace(execute=lambda *a: SimpleNamespace(scalar_one=lambda: datetime.now(UTC)))
    with pilot.store(tmp_path) as ledger:
        pilot.freeze(now, ledger, study, sample_rows(), {"type": "imports"}, base, FULL_CELL)
    monkeypatch.setattr(pilot, "database", lambda: nullcontext(now))
    monkeypatch.setattr(pilot, "model", lambda conn: base)
    monkeypatch.setattr(pilot, "current", lambda conn, m: None)
    monkeypatch.setattr(
        pilot, "decision_evidence", lambda conn, m, v, artifacts: (v, True, "gate-id")
    )
    monkeypatch.setattr(pilot, "engine_for", lambda root, version: version)
    monkeypatch.setattr(
        pilot, "frame_for", lambda row: SimpleNamespace(rgb=np.zeros((8, 8, 3), np.uint8))
    )
    monkeypatch.setattr(
        pilot, "infer", lambda eng, frame, row, ctx, dest: {"state": "missing", "cells": []}
    )
    result = pilot.run(args)
    page = Path(result["package"])
    assert candidate not in page.read_text(encoding="utf8")
    assert base["active"] not in page.read_text(encoding="utf8")
    assert pilot.run(args)["package"] == str(page)
    args.candidate = "second-candidate"
    with pytest.raises(ValueError, match="kandydata"):
        pilot.run(args)
    public = json.loads((page.parent / "boards.json").read_text())
    votes = {card["id"]: {"A": ["missing"] * 15, "B": ["missing"] * 15} for card in public["cards"]}
    args.votes.write_text(json.dumps({"study": public["id"], "votes": votes}))
    args.command = "score"
    scored = pilot.run(args)
    assert scored["boards"] == scored["baseNeedsFix"] == scored["candidateNeedsFix"] == 100
    assert not scored["recommendActivation"] and pilot.run(args) == scored
    page.write_text("changed")
    with pytest.raises(ValueError, match="integralność"):
        pilot.run(args)
