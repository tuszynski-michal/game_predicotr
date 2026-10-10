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


# --- Second round (TASK-0814) ---------------------------------------------------------

FIRST_ROUND_FILES = ("sample.json", "history.jsonl", "decisions.json")


def first_round_state(output: Path) -> dict[str, bytes]:
    files = {name: (output / name).read_bytes() for name in FIRST_ROUND_FILES}
    files.update({f"crops/{p.name}": p.read_bytes() for p in sorted((output / "crops").iterdir())})
    return files


def judged_first_round(tmp_path: Path) -> tuple[Path, list[str]]:
    output, _data = prepared(tmp_path)
    store = review.ReviewStore(output)
    ids = [str(item["itemId"]) for item in store.sample["items"]]
    for revision, (item_id, decision) in enumerate(
        zip(ids, ["bad", "good", "unreadable", "bad", "good", "bad"], strict=True)
    ):
        store.decide(item_id, decision, revision)
    return output, ids


def test_round2_selection_frozen_and_never_overwritten(tmp_path: Path) -> None:
    output, ids = judged_first_round(tmp_path)
    before = first_round_state(output)
    round_two = review.prepare_round2(output, ("bad",), log=lambda _m: None)
    assert round_two["itemIds"] == [ids[0], ids[3], ids[5]]
    assert first_round_state(output) == before  # preparing only reads the first round
    with pytest.raises(ValueError, match="ROUND2_EXISTS"):
        review.prepare_round2(output, ("bad", "unreadable"), log=lambda _m: None)
    # Later first-round changes do not change the frozen set.
    store = review.ReviewStore(output)
    store.decide(ids[0], "good", store.revision)
    assert review.Round2Store(output).round["itemIds"] == round_two["itemIds"]
    # Forcing supersedes (keeps the old file) and picks up "unreadable" too.
    forced = review.prepare_round2(output, ("bad", "unreadable"), force=True, log=lambda _m: None)
    assert forced["itemIds"] == [ids[2], ids[3], ids[5]]
    assert list(output.glob("round2.json.superseded-*"))
    with pytest.raises(ValueError, match="INCLUDE_INVALID"):
        review.prepare_round2(output, ("unreadable",), force=True, log=lambda _m: None)


def test_round2_empty_selection_stops(tmp_path: Path) -> None:
    output, _data = prepared(tmp_path)
    with pytest.raises(ValueError, match="ROUND2_EMPTY"):
        review.prepare_round2(output, ("bad",), log=lambda _m: None)
    assert not (output / "round2.json").exists()


def test_round2_decisions_undo_resume_and_first_round_untouched(tmp_path: Path) -> None:
    output, ids = judged_first_round(tmp_path)
    review.prepare_round2(output, ("bad",), log=lambda _m: None)
    before = first_round_state(output)
    store = review.Round2Store(output)
    first, second, third = ids[0], ids[3], ids[5]
    store.decide(first, "slight", 0)
    store.decide(second, "good", 1)
    store.decide(second, None, 2)
    store.decide(third, "unreadable", 3)
    with pytest.raises(review.RevisionConflictError):
        store.decide(third, "bad", 3)
    with pytest.raises(KeyError):
        store.decide(ids[1], "bad", 4)  # not a round-two item
    with pytest.raises(ValueError, match="DECISION_INVALID"):
        store.decide(third, "maybe", 4)
    resumed = review.Round2Store(output)
    assert resumed.decisions == {first: "slight", third: "unreadable"} and resumed.revision == 4
    decisions = json.loads((output / "round2-decisions.json").read_bytes())
    assert decisions["decisions"] == resumed.decisions and decisions["revision"] == 4
    history = (output / "round2-history.jsonl").read_bytes().splitlines()
    assert [json.loads(line)["decision"] for line in history] == [
        "slight",
        "good",
        None,
        "unreadable",
    ]
    with (output / "round2-history.jsonl").open("ab") as stream:
        stream.write(b'{"revision": 5, "item')
    assert review.Round2Store(output).revision == 4  # torn line dropped
    review.Round2Store(output).write_summary()
    assert first_round_state(output) == before


def test_round2_combined_summary_strict_and_loose() -> None:
    items = [
        {"itemId": f"{i}", "level": "S" if i < 6 else "B", "imageId": "x", "recognizedBoardId": "y"}
        for i in range(10)
    ]
    first = {"0": "bad", "1": "bad", "2": "bad", "3": "good", "4": "unreadable", "6": "bad"}
    first.update({"7": "good", "8": "good"})  # "5" and "9" have no first-round grade
    frozen = {"0": "bad", "1": "bad", "2": "bad", "6": "bad"}
    summary = review.summarize_combined(
        items, first, frozen, {"0": "slight", "1": "good", "2": "bad"}
    )
    s, b = summary["levels"]["S"], summary["levels"]["B"]
    assert (s["good"], s["slight"], s["bad"], s["unreadable"]) == (2, 1, 1, 1)
    assert s["firstRoundUndecided"] == 1 and s["judged"] == 4
    assert s["looseRate"] == 0.25 and s["strictRate"] == 0.5
    low, high = review.wilson_interval(2, 4) or (0.0, 0.0)
    assert s["strictWilson95"] == [low, high]
    # Round-two item 6 is pending: it keeps its frozen first-round grade "bad".
    assert b["round2Pending"] == 1 and b["bad"] == 1 and b["good"] == 2
    assert b["looseRate"] == 1 / 3 and b["strictRate"] == 1 / 3
    assert summary["firstRoundUndecided"] == 2 and summary["round2Decided"] == 3
    assert [i["itemId"] for i in summary["slightItems"]] == ["0"]
    assert [i["itemId"] for i in summary["badItems"]] == ["2", "6"]


def test_round2_api_page_and_report(tmp_path: Path) -> None:
    output, ids = judged_first_round(tmp_path)
    review.prepare_round2(output, ("bad",), log=lambda _m: None)
    store = review.Round2Store(output)
    client = TestClient(review.create_round2_app(store, 8104), base_url="http://127.0.0.1:8104")
    page = client.get("/").text
    assert "runda druga" in page and "lekko nacięta" in page and 'decide("slight")' in page
    assert "lekko" not in review.PAGE  # the first-round page is unchanged
    state = client.get("/api/state").json()
    assert [item["itemId"] for item in state["items"]] == [ids[0], ids[3], ids[5]]
    assert "level" not in state["items"][0]
    assert client.get("/" + state["items"][0]["crop"]).status_code == 200
    outside = Path(review.ReviewStore(output).items[ids[1]]["crop"]).name
    assert client.get(f"/crops/{outside}").status_code == 404
    body = {"itemId": ids[0], "decision": "slight", "baseRevision": 0}
    assert client.post("/api/decisions", json=body).status_code == 403
    headers = {"Origin": "http://127.0.0.1:8104"}
    assert client.post("/api/decisions", json=body, headers=headers).status_code == 200
    assert client.post("/api/decisions", json=body, headers=headers).status_code == 409
    foreign = {"itemId": ids[1], "decision": "bad", "baseRevision": 1}
    assert client.post("/api/decisions", json=foreign, headers=headers).status_code == 404
    assert client.get("/api/summary").json()["round2Decided"] == 1
    wrong_host = TestClient(review.create_round2_app(store, 8104), base_url="http://127.0.0.1:8103")
    assert wrong_host.get("/api/state").status_code == 403
    report = review.Round2Store(output).write_summary()
    assert json.loads((output / "round2-summary.json").read_bytes())["levels"] == report["levels"]


def test_round2_cli_prepare_and_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output, _ids = judged_first_round(tmp_path)
    review.main(["round2-prepare", "--review", str(output), "--include", "bad-unreadable"])
    assert len(json.loads((output / "round2.json").read_bytes())["itemIds"]) == 4
    with pytest.raises(ValueError, match="ROUND2_EXISTS"):
        review.main(["round2-prepare", "--review", str(output)])
    capsys.readouterr()
    review.main(["round2-report", "--review", str(output)])
    assert json.loads(capsys.readouterr().out)["round2Items"] == 4
