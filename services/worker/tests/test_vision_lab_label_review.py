from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from game_predictor_worker.vision_lab import label_review as review
from game_predictor_worker.vision_lab import production_split as split
from lab_production_fixtures import Dataset, standard_dataset


def prepared(tmp_path: Path, per_level: int = 3) -> tuple[Path, Dataset]:
    data = standard_dataset(tmp_path)
    output = tmp_path / "review"
    review.prepare_review(
        data.write(), data.artifacts, output, seed=5, per_level=per_level, log=lambda _m: None
    )
    return output, data


def test_label_review_sample_one_board_per_filtered_photo(tmp_path: Path) -> None:
    output, data = prepared(tmp_path)
    sample = json.loads((output / "sample.json").read_bytes())
    levels = [item["level"] for item in sample["items"]]
    assert levels.count("S") == 3 and levels.count("B") == 3
    images = [item["imageId"] for item in sample["items"]]
    assert len(set(images)) == len(images)
    assert not {"gold-full", "gold-mixed", "reject-filter", "reject-u", "reject-incomplete"} & set(
        images
    )
    item = sample["items"][0]
    assert len(item["cropNodes"]) == 24 and (output / item["crop"]).is_file()
    # Deterministic: the same seed gives the same sample in another directory.
    again = review.prepare_review(
        data.write(), data.artifacts, tmp_path / "other", seed=5, per_level=3, log=lambda _m: None
    )
    assert again["sampleId"] == sample["sampleId"]
    with pytest.raises(ValueError, match="ANOTHER_SAMPLE"):
        review.prepare_review(
            data.write(), data.artifacts, output, seed=6, per_level=3, log=lambda _m: None
        )


def test_label_review_insufficient_population_stops(tmp_path: Path) -> None:
    data = standard_dataset(tmp_path, families=1, per_level=2)
    with pytest.raises(ValueError, match="POPULATION_INSUFFICIENT"):
        review.prepare_review(
            data.write(), data.artifacts, tmp_path / "r", seed=1, per_level=3, log=lambda _m: None
        )


def test_label_review_decisions_persist_resume_and_undo(tmp_path: Path) -> None:
    output, _data = prepared(tmp_path)
    store = review.ReviewStore(output)
    first, second = (item["itemId"] for item in store.sample["items"][:2])
    store.decide(first, "bad", 0)
    store.decide(second, "good", 1)
    store.decide(second, None, 2)  # undo
    with pytest.raises(review.RevisionConflictError):
        store.decide(second, "good", 2)
    resumed = review.ReviewStore(output)
    assert resumed.decisions == {first: "bad"} and resumed.revision == 3
    decisions = json.loads((output / "decisions.json").read_bytes())
    assert decisions["decisions"] == {first: "bad"} and decisions["revision"] == 3
    history = (output / "history.jsonl").read_bytes().splitlines()
    assert [json.loads(line)["decision"] for line in history] == ["bad", "good", None]


def test_label_review_torn_history_line_is_dropped(tmp_path: Path) -> None:
    output, _data = prepared(tmp_path)
    store = review.ReviewStore(output)
    item = store.sample["items"][0]["itemId"]
    store.decide(item, "good", 0)
    with (output / "history.jsonl").open("ab") as stream:
        stream.write(b'{"revision": 2, "itemId"')
    resumed = review.ReviewStore(output)
    assert resumed.revision == 1 and resumed.decisions == {item: "good"}
    resumed.decide(item, "bad", 1)
    assert review.ReviewStore(output).decisions == {item: "bad"}


def test_label_review_summary_wilson_per_level(tmp_path: Path) -> None:
    low, high = review.wilson_interval(10, 100) or (0.0, 0.0)
    assert round(low, 4) == 0.0552 and round(high, 4) == 0.1744
    assert review.wilson_interval(0, 0) is None
    items = [
        {"itemId": f"{i}", "level": "S" if i < 4 else "B", "imageId": "x", "recognizedBoardId": "y"}
        for i in range(8)
    ]
    summary = review.summarize(items, {"0": "bad", "1": "good", "2": "unreadable", "4": "good"})
    assert summary["levels"]["S"]["badRate"] == 0.5 and summary["levels"]["S"]["unreadable"] == 1
    assert summary["levels"]["S"]["undecided"] == 1 and summary["levels"]["B"]["badRate"] == 0.0
    assert summary["levels"]["S"]["wilson95"] is not None and len(summary["badItems"]) == 1


def test_label_review_api_loopback_only_and_records(tmp_path: Path) -> None:
    output, _data = prepared(tmp_path)
    store = review.ReviewStore(output)
    client = TestClient(review.create_review_app(store, 8103), base_url="http://127.0.0.1:8103")
    assert "Przegląd etykiet" in client.get("/").text
    state = client.get("/api/state").json()
    assert "level" not in state["items"][0]  # blind review
    crop = client.get("/" + state["items"][0]["crop"])
    assert crop.status_code == 200 and crop.headers["content-type"] == "image/jpeg"
    assert client.get("/crops/..%2Fsample.json").status_code == 404
    body = {"itemId": state["items"][0]["itemId"], "decision": "bad", "baseRevision": 0}
    assert client.post("/api/decisions", json=body).status_code == 403  # no origin
    headers = {"Origin": "http://127.0.0.1:8103"}
    saved = client.post("/api/decisions", json=body, headers=headers)
    assert saved.status_code == 200 and saved.json()["revision"] == 1
    assert client.post("/api/decisions", json=body, headers=headers).status_code == 409
    other = TestClient(review.create_review_app(store, 8103), base_url="http://evil.example")
    assert other.get("/api/state").status_code == 403
    report = review.ReviewStore(output).write_summary()
    assert report["decided"] == 1
    assert json.loads((output / "summary.json").read_bytes())["levels"] == report["levels"]


def test_label_review_population_matches_filter(tmp_path: Path) -> None:
    data = standard_dataset(tmp_path)
    collector = split.ImageFactsCollector()
    for row in data.rows:
        collector.add(row)
    population = review.review_population(collector.images())
    assert len(population["S"]) == 28 and len(population["B"]) == 28
