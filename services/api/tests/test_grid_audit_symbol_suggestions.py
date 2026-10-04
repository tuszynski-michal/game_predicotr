"""New symbols are bound to the audit preview and survive process recovery."""

from __future__ import annotations

import io
import json
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import numpy as np
import pytest
from fastapi.testclient import TestClient
from game_predictor_api.application.grid_audit_proposals import (
    FileGridAuditProposalStore,
    GridAuditProposalService,
)
from game_predictor_api.application.grid_audit_symbol_suggestions import (
    SYMBOL_SUGGESTIONS_SCHEMA,
    FileGridAuditSymbolSuggestionStore,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.grid_audit_proposals import GridAuditProposalError
from game_predictor_api.main import create_app
from game_predictor_api.schemas.grid_audit_proposals import to_grid_audit_proposal_response
from PIL import Image
from test_grid_audit_proposals import (
    GAME_ID,
    MemoryBoardReader,
    _http,
    _items,
    _review_item,
    _worklist_board,
    _write,
)

from scripts import recognize_grid_audit_symbols as recognition
from scripts.recognize_grid_audit_symbols import (
    completed,
    contact_sheet_crops,
    preview_command,
    publish,
)


def _suggestions(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    item = _items([_worklist_board(0)])[0]
    directory = _write(tmp_path, [item])
    manifest = json.loads((directory / "manifest.json").read_bytes())
    review = _review_item(item, 1)
    command = {
        "corners": [
            {"x": 100, "y": 50},
            {"x": 350, "y": 50},
            {"x": 350, "y": 170},
            {"x": 100, "y": 170},
        ],
        "geometryQualification": None,
        "expectedGeometryRevision": 1,
        "expectedResolutionRevision": 0,
        "expectedSourceChecksumSha256": "a" * 64,
        "expectedSourceWidth": 1200,
        "expectedSourceHeight": 900,
        "expectedGridRows": 3,
        "expectedGridColumns": 5,
    }
    document: dict[str, object] = {
        "schema": SYMBOL_SUGGESTIONS_SCHEMA,
        "algorithmVersion": "symbol-reference-library-v1",
        "gameId": str(GAME_ID),
        "auditId": manifest["auditId"],
        "auditSha256": manifest["sha256"],
        "itemId": item.item_id,
        "reviewItemId": str(review.review_item_id),
        "previewCommand": command,
        "generatedAt": "2026-10-05T08:00:00Z",
        "cells": [
            {"cellIndex": index, "symbolId": str(UUID(int=999)) if index == 0 else None}
            for index in range(15)
        ],
    }
    return directory / "symbol-suggestions", document


def test_http_returns_only_new_predictions_and_restart_recovers_artifact(tmp_path: Path) -> None:
    directory, document = _suggestions(tmp_path)
    item = _items([_worklist_board(0)])[0]
    base = f"/api/v1/admin/games/{GAME_ID}/grid-audit-proposals/p00000"
    assert (
        _http(tmp_path, {item.recognized_board_id: 1}).get(base).json()["symbolSuggestions"] is None
    )
    publish(directory, "p00000", document)
    for _ in range(2):
        # A fresh application/store must recover the same immutable file.
        response = _http(tmp_path, {item.recognized_board_id: 1}).get(base)
        assert response.status_code == 200
        suggestions = response.json()["symbolSuggestions"]
        assert suggestions["previewCommand"] == document["previewCommand"]
        assert len(suggestions["cells"]) == 15
        assert suggestions["cells"][0] == {
            "cellIndex": 0,
            "symbolId": str(UUID(int=999)),
            "origin": "predicted",
        }
        assert all(cell["symbolId"] is None for cell in suggestions["cells"][1:])
    changed = _http(tmp_path, {item.recognized_board_id: 2}).get(base).json()
    assert changed["symbolSuggestions"] is None
    assert changed["proposal"] is None
    assert completed(directory, "p00000", str(document["auditSha256"]), document["previewCommand"])


@pytest.mark.parametrize(
    "key,value",
    [
        ("expectedSourceChecksumSha256", "b" * 64),
        ("expectedResolutionRevision", 9),
        ("expectedSourceWidth", 42),
        ("expectedGridRows", 7),
    ],
)
def test_context_drift_never_returns_old_symbols(tmp_path: Path, key: str, value: object) -> None:
    directory, document = _suggestions(tmp_path)
    document["previewCommand"][key] = value
    publish(directory, "p00000", document)
    item = _items([_worklist_board(0)])[0]
    response = _http(tmp_path, {item.recognized_board_id: 1}).get(
        f"/api/v1/admin/games/{GAME_ID}/grid-audit-proposals/p00000"
    )
    assert response.json()["symbolSuggestions"] is None


def test_corrupt_or_duplicate_cells_are_refused(tmp_path: Path) -> None:
    directory, document = _suggestions(tmp_path)
    publish(directory, "p00000", document)
    path = directory / "p00000.json"
    path.write_bytes(path.read_bytes() + b" ")
    item = _items([_worklist_board(0)])[0]
    kwargs = {
        "game_id": GAME_ID,
        "audit_id": str(document["auditId"]),
        "audit_sha256": str(document["auditSha256"]),
        "item_id": "p00000",
        "review_item": _review_item(item, 1),
    }
    store = FileGridAuditSymbolSuggestionStore(tmp_path)
    with pytest.raises(GridAuditProposalError) as error:
        store.load(**kwargs)
    assert error.value.code == "GRID_AUDIT_SYMBOL_SUGGESTIONS_CHECKSUM_MISMATCH"
    document["cells"][1]["cellIndex"] = 0
    publish(directory, "p00000", document)
    with pytest.raises(GridAuditProposalError) as error:
        store.load(**kwargs)
    assert error.value.code == "GRID_AUDIT_SYMBOL_SUGGESTIONS_INVALID"


@pytest.mark.parametrize("checksum_error", [True, False])
def test_app_returns_stable_artifact_error_without_database_access(
    tmp_path: Path, checksum_error: bool
) -> None:
    directory, document = _suggestions(tmp_path)
    if not checksum_error:
        document["previewCommand"]["geometryQualification"] = {"version": "invalid"}
    publish(directory, "p00000", document)
    if checksum_error:
        path = directory / "p00000.json"
        path.write_bytes(path.read_bytes() + b" ")
    item = _items([_worklist_board(0)])[0]
    app = create_app(ApiSettings.from_environment({"GAME_PREDICTOR_ARTIFACT_ROOT": str(tmp_path)}))

    @app.get("/test-symbol-artifact")
    def read_artifact() -> object:
        service = GridAuditProposalService(
            FileGridAuditProposalStore(tmp_path),
            MemoryBoardReader({item.recognized_board_id: 1}),
            FileGridAuditSymbolSuggestionStore(tmp_path),
        )
        return to_grid_audit_proposal_response(
            game_id=GAME_ID, view=service.proposal(game_id=GAME_ID, item_id="p00000")
        )

    with TestClient(app) as client:
        response = client.get("/test-symbol-artifact")
    assert response.status_code == (409 if checksum_error else 422)
    assert response.json()["code"] == (
        "GRID_AUDIT_SYMBOL_SUGGESTIONS_CHECKSUM_MISMATCH"
        if checksum_error
        else "GRID_AUDIT_SYMBOL_SUGGESTIONS_INVALID"
    )


def test_lossless_preview_is_split_row_major_without_resampling() -> None:
    pixels = np.zeros((192, 320, 3), dtype=np.uint8)
    for index in range(15):
        row, column = divmod(index, 5)
        pixels[row * 64 : (row + 1) * 64, column * 64 : (column + 1) * 64] = index * 10
    output = io.BytesIO()
    Image.fromarray(pixels).save(output, format="PNG")
    crops = contact_sheet_crops(output.getvalue(), 3, 5)
    assert crops.shape == (15, 64, 64, 3)
    assert [int(crop[0, 0, 0]) for crop in crops] == list(range(0, 150, 10))
    with pytest.raises(ValueError, match="lossless"):
        contact_sheet_crops(output.getvalue(), 5, 3)


def test_preview_uses_proposal_clamped_like_reviewer_not_stored_grid() -> None:
    view = {
        "reviewItem": {
            "geometryRevision": 1,
            "resolutionRevision": 0,
            "sourceChecksumSha256": "a" * 64,
            "sourceWidth": 200,
            "sourceHeight": 100,
            "gridRows": 3,
            "gridColumns": 5,
        },
        "proposal": {
            "corners": [
                {"x": -2, "y": 10},
                {"x": 250, "y": 10},
                {"x": 250, "y": 120},
                {"x": -2, "y": 120},
            ]
        },
    }
    command = preview_command(view)
    assert command["corners"] == [
        {"x": 0, "y": 10},
        {"x": 199, "y": 10},
        {"x": 199, "y": 99},
        {"x": 0, "y": 99},
    ]
    assert command["geometryQualification"] is None


def test_cli_recovers_publish_without_acknowledgment_and_verifies_cursor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory, document = _suggestions(tmp_path)
    command = document["previewCommand"]
    arguments = Namespace(
        game_id=str(GAME_ID),
        game_code="7",
        api_base_url="http://127.0.0.1:8000",
        artifact_root=tmp_path,
        output_dir=tmp_path / "run",
        library_cache=tmp_path / "cache",
        max_seconds=80,
    )
    page = {
        "auditId": document["auditId"],
        "artifactSha256": document["auditSha256"],
        "counts": {"open": 1},
        "items": [{"itemId": "p00000", "ordinal": 0}],
        "nextAfterOrdinal": None,
    }
    view = {
        "reviewItem": {
            "reviewItemId": document["reviewItemId"],
            "importJobId": str(UUID(int=888)),
            **{
                key: command["expected" + key[0].upper() + key[1:]]
                for key in (
                    "geometryRevision",
                    "resolutionRevision",
                    "sourceChecksumSha256",
                    "sourceWidth",
                    "sourceHeight",
                    "gridRows",
                    "gridColumns",
                )
            },
        },
        "proposal": {"corners": command["corners"]},
    }

    def read(_base: str, path: str) -> object:
        if path.endswith("/symbols"):
            return [{"id": str(UUID(int=999)), "code": "SLIWKA", "status": "active"}]
        if path.endswith("/p00000"):
            return view
        return {**page, "items": []} if "afterOrdinal=0" in path else page

    model = SimpleNamespace(class_codes=("SLIWKA",), checkpoint_sha256="a" * 64)
    matrix = np.zeros((15, 1), dtype=np.float32)
    monkeypatch.setattr(recognition, "read_json", read)
    monkeypatch.setattr(recognition, "frozen_library", lambda *_: (model, matrix, matrix, matrix))
    renders = []

    def render(*_: object) -> bytes:
        renders.append(True)
        output = io.BytesIO()
        Image.new("RGB", (320, 192)).save(output, format="PNG")
        return output.getvalue()

    monkeypatch.setattr(recognition, "request", render)
    monkeypatch.setattr(recognition, "descriptor_matrix", lambda *_: (matrix, matrix))
    monkeypatch.setattr(recognition.reference, "_feature_maps", lambda *_: matrix)
    monkeypatch.setattr(recognition, "combined_descriptor", lambda *_: matrix)
    monkeypatch.setattr(recognition, "normalize_rows", lambda value: value)
    monkeypatch.setattr(recognition, "vote_batch", lambda *_, **__: [None] * 15)
    monkeypatch.setattr(
        recognition, "decide", lambda *_: SimpleNamespace(class_index=0, reason="unanimous")
    )

    def publish_then_lose_response(*args: object) -> None:
        publish(*args)
        raise RuntimeError("Lost publication acknowledgment")

    monkeypatch.setattr(recognition, "publish", publish_then_lose_response)
    with pytest.raises(RuntimeError, match="acknowledgment"):
        recognition.run(arguments)
    original = (directory / "p00000.json").read_bytes()
    assert not (arguments.output_dir / "cursor.json").exists()
    monkeypatch.setattr(recognition, "publish", publish)
    assert recognition.run(arguments) == 0
    assert recognition.run(arguments) == 0
    assert renders == [True]
    assert (directory / "p00000.json").read_bytes() == original
    assert json.loads((arguments.output_dir / "status.json").read_bytes())["counts"] == {
        "processed": 0,
        "recovered": 0,
        "confident": 0,
        "uncertain": 0,
        "changedMeanwhile": 0,
        "coveredOpenBoards": 1,
    }
    (directory / "p00000.manifest.json").unlink()
    with pytest.raises(ValueError, match="unrecognized boards"):
        recognition.run(arguments)
    assert json.loads((arguments.output_dir / "cursor.json").read_bytes())["afterOrdinal"] is None
