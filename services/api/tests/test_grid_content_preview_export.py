"""The durable HTML uses current quads and never consumes archived overlay PNGs."""

import hashlib
import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest
from test_grid_content_preview import document

spec = importlib.util.spec_from_file_location(
    "content_preview_export",
    Path(__file__).resolve().parents[3] / "scripts/export_grid_content_preview.py",
)
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)


def record():
    source, current, nodes = document()
    cells = [
        {"state": "unknown", "quad": None, "boxInPreview": [[0, 0], [99, 0], [99, 99], [0, 99]]}
        for _ in range(15)
    ]
    cells[0] = {"state": "visible", "quad": [[25, 25], [30, 25], [30, 30], [25, 30]]}
    return {
        "target": {
            "source": source.model_dump(mode="json"),
            "role": "TRAIN",
            "displayName": "TRAIN photo",
            "positionIndex": 0,
            "sequenceNumber": 1,
        },
        "reference": {
            "revision": 3,
            "annotation": {
                "source": source.model_dump(mode="json"),
                "sequenceNumber": 1,
                "origin": "ai_proposal",
                "actor": "proposal-author",
                "approvedBy": None,
                "reference": {"positionIndex": 0, "humanApproved": False, "cells": cells},
            },
            "ordinaryPreview": {
                "version": "grid-content-ordinary-preview-v1",
                "state": "available",
                "nodes": nodes,
                "geometryRevision": 7,
                "productionCells": [],
            },
        },
        "asset": "source.jpg",
    }


def test_fourteen_null_quads_never_draw_ghost_outlines_or_old_overlay_files():
    data = record()
    page = exporter.preview_html([data])
    assert page.count("<polygon data-cell=") == 1
    assert 'data-cell="0"' in page and 'data-cell="1"' not in page
    assert "overlay-" not in page and "boxInPreview" not in page
    assert "ai_proposal" in page and "zatwierdzenie: nie" in page and "Obrysy: 1/15" in page
    assert "0/15" in page and "source.jpg" in page
    assert data == record()  # rendering is pure


def test_control_protected_and_stale_source_records_never_expose_hints():
    safe = record()
    for role in ("A", "B", "REGRESSION"):
        protected = deepcopy(safe)
        protected["target"]["role"] = role
        assert "<article>" not in exporter.preview_html([protected])
    protected = deepcopy(safe)
    protected["reference"]["ordinaryPreview"]["state"] = "protected"
    assert "<article>" not in exporter.preview_html([protected])
    stale = deepcopy(safe)
    stale["reference"]["annotation"]["sequenceNumber"] = 9
    assert "<polygon data-cell=" not in exporter.preview_html([stale])


def test_optional_unknown_fragment_has_an_explicit_state_without_a_full_symbol_claim():
    data = record()
    data["reference"]["annotation"]["reference"]["cells"][1]["quad"] = [
        [40, 25],
        [45, 25],
        [45, 30],
        [40, 30],
    ]
    page = exporter.preview_html([data])
    assert page.count("<polygon data-cell=") == 2
    assert 'data-cell="1" data-state="unknown"' in page
    assert "Pole 2: Nieznany — fragment" in page


def wire_export(monkeypatch, records, *, bad_asset_sha=False, oversized=False):
    """Exercise actual HTTP/file orchestration; every requested URL is recorded."""
    calls = []
    payloads = {}
    for index, item in enumerate(records):
        source = item["target"]["source"]
        source["sourceId"] = f"00000000-0000-0000-0000-{index + 1:012d}"
        content = f"source-{index}".encode()
        source["sourceSha256"] = hashlib.sha256(content).hexdigest()
        if bad_asset_sha:
            content += b"-drift"
        payloads[f"content-references/{source['sourceId']}/0"] = json.dumps(
            item["reference"]
        ).encode()
        payloads[f"content-targets/sources/{source['sourceId']}/asset"] = content
    payloads["content-targets"] = json.dumps(
        {"items": [item["target"] for item in records], "nextOffset": None}
    ).encode()

    class Response:
        def __init__(self, data):
            self.data = data

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, limit):
            assert limit == 32 * 1024 * 1024 + 1
            return b"x" * limit if oversized else self.data

    def urlopen(url, *, timeout):
        assert isinstance(url, str)  # urllib uses a GET for an URL with no data/body
        assert 0 < timeout <= 20
        suffix = url.split("/grid-quality-measurements/", 1)[1].split("?", 1)[0]
        calls.append(("GET", suffix, timeout))
        return Response(payloads[suffix])

    monkeypatch.setattr(exporter, "urlopen", urlopen)
    return calls


def test_real_export_omits_control_and_protected_sources_before_asset_download(
    tmp_path, monkeypatch
):
    records = [record() for _ in range(6)]
    for item, role in zip(
        records, ["A", "B", "REGRESSION", "TRAIN", "TRAIN", "TRAIN"], strict=True
    ):
        item["target"].update(role=role, state="ready")
    records[3]["reference"]["ordinaryPreview"]["state"] = "protected"
    # A damaged footprint is explicit, but ordinary labels/the rest of the page survive.
    records[5]["reference"]["ordinaryPreview"].update(
        state="unavailable", reasonCodes=["CONTENT_PRODUCTION_MANIFEST_CONFLICT"]
    )
    calls = wire_export(monkeypatch, records)
    output = tmp_path / "export"
    path = exporter.export("http://localhost/api/v1", "game", "cohort", "a" * 64, output, 50, 0)
    result = json.loads((output / "preview.json").read_text(encoding="utf-8"))
    assert len(result["records"]) == 2 and len(result["skipped"]) == 4
    for item in records[:4]:
        source_id = item["target"]["source"]["sourceId"]
        assert not (output / f"{source_id}.jpg").exists()
        assert not any(f"sources/{source_id}/asset" in url for _, url, _ in calls)
    assert len(list(output.glob("*.jpg"))) == 2
    assert all(method == "GET" for method, _, _ in calls)
    assert "CONTENT_PRODUCTION_MANIFEST_CONFLICT" in path.read_text(encoding="utf-8")
    assert "Dane wycinków są niespójne" in path.read_text(encoding="utf-8")


def test_real_export_rejects_wrong_asset_sha_before_writing_pixels(tmp_path, monkeypatch):
    item = record()
    item["target"]["state"] = "ready"
    wire_export(monkeypatch, [item], bad_asset_sha=True)
    output = tmp_path / "bad-sha"
    with pytest.raises(ValueError, match="frozen pin"):
        exporter.export("http://localhost/api/v1", "game", "cohort", "a" * 64, output, 50, 0)
    assert not list(output.glob("*.jpg"))


def test_nonprotected_missing_nodes_still_exports_current_annotation_and_image(
    tmp_path, monkeypatch
):
    item = record()
    item["target"]["state"] = "ready"
    item["reference"]["ordinaryPreview"].update(
        state="unavailable", nodes=None, reasonCodes=["CONTENT_SAVED_NODES_UNAVAILABLE"]
    )
    calls = wire_export(monkeypatch, [item])
    output = tmp_path / "missing-nodes"
    path = exporter.export("http://localhost/api/v1", "game", "cohort", "a" * 64, output, 50, 0)
    page = path.read_text(encoding="utf-8")
    assert len(list(output.glob("*.jpg"))) == 1
    assert '<polygon data-cell="0"' in page
    assert "<polyline " not in page
    assert "Brak zapisanej siatki i produkcyjnych wycinków" in page
    assert len(json.loads((output / "preview.json").read_bytes())["records"]) == 1
    assert any("/asset" in url for _, url, _ in calls)


def test_legacy_reference_without_preview_protection_cannot_export_pixels(tmp_path, monkeypatch):
    item = record()
    item["target"]["state"] = "ready"
    del item["reference"]["ordinaryPreview"]
    calls = wire_export(monkeypatch, [item])
    output = tmp_path / "old-api"
    exporter.export("http://localhost/api/v1", "game", "cohort", "a" * 64, output, 50, 0)
    assert not list(output.glob("*.jpg"))
    assert not any("/asset" in url for _, url, _ in calls)


def test_real_export_enforces_byte_and_total_time_limits(tmp_path, monkeypatch):
    calls = wire_export(monkeypatch, [], oversized=True)
    with pytest.raises(ValueError, match="byte size"):
        exporter.export(
            "http://localhost/api/v1", "game", "cohort", "a" * 64, tmp_path / "size", 50, 0
        )
    assert len(calls) == 1 and not (tmp_path / "size").exists()
    calls = wire_export(monkeypatch, [])
    ticks = iter([0, 111])
    monkeypatch.setattr(exporter, "monotonic", lambda: next(ticks))
    with pytest.raises(TimeoutError, match="110 seconds"):
        exporter.export(
            "http://localhost/api/v1", "game", "cohort", "a" * 64, tmp_path / "time", 50, 0
        )
    assert calls == [] and not (tmp_path / "time").exists()
    calls = wire_export(monkeypatch, [])
    ticks = iter([0, 1, 111])
    monkeypatch.setattr(exporter, "monotonic", lambda: next(ticks))
    with pytest.raises(TimeoutError, match="110 seconds"):
        exporter.export(
            "http://localhost/api/v1", "game", "cohort", "a" * 64, tmp_path / "slow", 50, 0
        )
    assert len(calls) == 1 and not (tmp_path / "slow").exists()
