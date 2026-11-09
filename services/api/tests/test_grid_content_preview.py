"""Exact saved geometry, production pins, source-wide blind protection and GET purity."""

from copy import deepcopy
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from game_predictor_api.api.grid_cell_content import create_grid_cell_content_router
from game_predictor_api.application.grid_cell_content import GridCellContentService
from game_predictor_api.domain.board_render_manifests import sha256_canonical_json
from game_predictor_api.domain.image_geometry_v2 import (
    SOURCE_SUPPORT_EPSILON,
    SourcePoint,
    SourceQuad,
)
from game_predictor_api.storage import grid_content_preview as module
from test_grid_cell_content import GAME, revision, target
from test_grid_cell_content_targets import fixture as content_fixture

fixture = content_fixture


def document():
    source = target(1).source
    nodes = [
        [20 + col * 10 + row * 0.17, 20 + row * 10 + col * 0.13]
        for row in range(4)
        for col in range(6)
    ]
    board = {
        "geometry_revision": 7,
        "geometry_checksum_sha256": "a" * 64,
        "position_index": 0,
        "board_geometry": {"latticeNodes": [{"x": x, "y": y} for x, y in nodes]},
        "geometry_engine_name": "manual",
    }
    cells = []
    for index in range(15):
        row, col = divmod(index, 5)
        quad = [
            nodes[row * 6 + col],
            nodes[row * 6 + col + 1],
            nodes[(row + 1) * 6 + col + 1],
            nodes[(row + 1) * 6 + col],
        ]
        # Deliberately different from the full field, supplied by the persisted renderer.
        footprint = [
            [x + (0.8 if j in (0, 3) else -0.8), y + (0.8 if j in (0, 1) else -0.8)]
            for j, (x, y) in enumerate(quad)
        ]
        spec = {
            "sourceChecksumSha256": source.sourceSha256,
            "normalizedPixelChecksumSha256": source.sourceRepresentativeSha256,
            "geometryRevision": 7,
            "boardSlot": 0,
            "cellIndex": index,
            "sourceQuad": SourceQuad(tuple(SourcePoint(x, y) for x, y in quad)).to_dict(),
            "paddedSourceQuad": SourceQuad(
                tuple(SourcePoint(x, y) for x, y in footprint)
            ).to_dict(),
            "configuration": {
                "extractorVersion": "production-v1",
                "preprocessingVersion": "legacy-v1",
                "interpolation": "opencv-inter-linear-v1",
                "outputWidth": 64,
                "outputHeight": 64,
                "paddingFraction": 0.08,
            },
        }
        cells.append(
            {
                "cellIndex": index,
                "renderSpec": spec,
                "renderSpecChecksumSha256": sha256_canonical_json(spec),
            }
        )
    payload = {"cells": cells}
    return (
        source,
        {
            "board": board,
            "renders": [
                {
                    "geometry_revision": 7,
                    "cells": payload,
                    "manifest_checksum_sha256": sha256_canonical_json(payload),
                }
            ],
        },
        nodes,
    )


def test_saved_24_nodes_and_production_footprints_are_preserved_without_regularizing():
    source, current, nodes = document()
    result = module.preview_document(source, current, GAME, "b" * 64)
    assert result["nodes"] == nodes
    assert result["geometryRevision"] == 7
    assert len(result["productionCells"]) == 15
    for entry, actual in zip(
        current["renders"][0]["cells"]["cells"], result["productionCells"], strict=True
    ):
        assert actual["quad"] == [[p["x"], p["y"]] for p in entry["renderSpec"]["paddedSourceQuad"]]
        assert actual["configuration"]["paddingFraction"] == 0.08
    assert result == module.preview_document(source, deepcopy(current), GAME, "b" * 64)


def test_missing_manifest_and_changed_nodes_preserve_labels_with_unavailable_crop_proof():
    source, current, nodes = document()
    current["renders"] = []
    value = module.preview_document(source, current, GAME, "b" * 64)
    assert value["nodes"] == nodes and value["productionCells"] == []
    assert value["reasonCodes"] == ["CONTENT_PRODUCTION_MANIFEST_UNAVAILABLE"]
    source, current, _ = document()
    current["board"]["board_geometry"]["latticeNodes"][7]["x"] += 1
    value = module.preview_document(source, current, GAME, "b" * 64)
    assert value["state"] == "unavailable"
    assert value["nodes"][7][0] == current["board"]["board_geometry"]["latticeNodes"][7]["x"]
    assert len(value["productionCells"]) == 11
    assert "CONTENT_PRODUCTION_CELL_UNAVAILABLE" in value["reasonCodes"]


def repin(current):
    manifest = current["renders"][0]
    for entry in manifest["cells"]["cells"]:
        entry["renderSpecChecksumSha256"] = sha256_canonical_json(entry["renderSpec"])
    manifest["manifest_checksum_sha256"] = sha256_canonical_json(manifest["cells"])


@pytest.mark.parametrize("left", [-5.0, -SOURCE_SUPPORT_EPSILON / 2])
def test_real_renderer_quad_shape_allows_partial_cells_and_source_epsilon(left):
    source, current, nodes = document()
    raw = current["renders"][0]["cells"]["cells"][0]["renderSpec"]["paddedSourceQuad"]
    raw[0]["x"] = raw[3]["x"] = left
    repin(current)
    result = module.preview_document(source, current, GAME, "b" * 64)
    assert result["state"] == "available" and result["nodes"] == nodes
    assert len(result["productionCells"]) == 15
    assert result["productionCells"][0]["quad"][0][0] == left
    assert ("CONTENT_PRODUCTION_FOOTPRINT_OUTSIDE_SOURCE" in result["reasonCodes"]) == (
        left < -SOURCE_SUPPORT_EPSILON
    )


@pytest.mark.parametrize(
    "problem",
    [
        "missing_config",
        "missing_spec",
        "malformed_quad",
        "source_drift",
        "checksum_drift",
        "duplicate",
    ],
)
def test_bad_cell_proof_preserves_saved_nodes_and_other_footprints(problem):
    source, current, nodes = document()
    entries = current["renders"][0]["cells"]["cells"]
    if problem == "missing_config":
        del entries[0]["renderSpec"]["configuration"]
    elif problem == "missing_spec":
        del entries[0]["renderSpec"]
    elif problem == "malformed_quad":
        entries[0]["renderSpec"]["sourceQuad"] = [{"x": 3}]
    elif problem == "source_drift":
        entries[0]["renderSpec"]["sourceChecksumSha256"] = "e" * 64
    elif problem == "duplicate":
        entries.append(deepcopy(entries[0]))
    for entry in entries:
        if "renderSpec" in entry:
            entry["renderSpecChecksumSha256"] = sha256_canonical_json(entry["renderSpec"])
    if problem == "checksum_drift":
        entries[0]["renderSpecChecksumSha256"] = "f" * 64
    current["renders"][0]["manifest_checksum_sha256"] = sha256_canonical_json(
        current["renders"][0]["cells"]
    )
    result = module.preview_document(source, current, GAME, "b" * 64)
    assert result["state"] == "unavailable" and result["nodes"] == nodes
    assert len(result["productionCells"]) == 14
    assert "CONTENT_PRODUCTION_CELL_UNAVAILABLE" in result["reasonCodes"]


def test_manifest_checksum_failure_does_not_block_ordinary_reference(fixture, monkeypatch):
    source, current, nodes = document()
    current["renders"][0]["manifest_checksum_sha256"] = "f" * 64
    approved = revision(target())
    legacy = {
        "annotation": approved.model_dump(mode="json"),
        "revision": 1,
        "contentReferenceSha256": approved.sha256,
    }
    monkeypatch.setattr(fixture.repo, "get", lambda *_args: deepcopy(legacy))
    monkeypatch.setattr(
        module,
        "ordinary_preview",
        lambda *_args: module.preview_document(source, current, GAME, "b" * 64),
    )
    result = fixture.repo.get_preview(GAME, source.sourceId, 0, fixture.cohort, "a" * 64)
    assert {k: v for k, v in result.items() if k != "ordinaryPreview"} == legacy
    assert result["annotation"]["reference"]["humanApproved"] is True
    assert result["ordinaryPreview"]["nodes"] == nodes
    assert result["ordinaryPreview"]["state"] == "unavailable"
    assert result["ordinaryPreview"]["productionCells"] == []


def test_source_last_pixel_epsilon_keeps_exact_quad_without_clamping():
    source, current, _ = document()
    raw = current["renders"][0]["cells"]["cells"][14]["renderSpec"]["paddedSourceQuad"]
    right = source.width - 1 + SOURCE_SUPPORT_EPSILON / 2
    raw[1]["x"] = raw[2]["x"] = right
    repin(current)
    result = module.preview_document(source, current, GAME, "b" * 64)
    assert result["state"] == "available" and result["reasonCodes"] == []
    assert result["productionCells"][14]["quad"][1][0] == right


def test_write_response_excludes_read_only_preview_from_its_contract():
    from game_predictor_api.schemas.grid_cell_content import ContentWriteResponse

    assert "ordinaryPreview" not in ContentWriteResponse.model_json_schema()["properties"]


@pytest.mark.parametrize("coordinate", [float("nan"), float("inf"), 10**9])
def test_invalid_nodes_are_unavailable(coordinate):
    source, current, _ = document()
    current["board"]["board_geometry"]["latticeNodes"][0]["x"] = coordinate
    result = module.preview_document(source, current, GAME, "b" * 64)
    assert result["state"] == "unavailable" and result["nodes"] is None


def test_protection_uses_pixel_identity_across_aliases_and_all_slots():
    calls = []
    repo = SimpleNamespace(session=SimpleNamespace(scalar=lambda q: calls.append(q) or GAME))
    source = target(1).source
    assert module.protected_source(repo, GAME, source)
    query = calls[0].compile().params
    assert {
        "targets": [{"source": {"sourceRepresentativeSha256": source.sourceRepresentativeSha256}}]
    } in query.values()
    assert "positionIndex" not in str(query) and "phase" not in str(calls[0])


def test_pinned_get_is_opt_in_and_protection_never_reads_geometry(fixture, monkeypatch):
    value = fixture
    source = UUID(value.sources[0]["sourceId"])
    monkeypatch.setattr(module, "protected_source", lambda *_args: True)
    monkeypatch.setattr(
        module, "_live_source", lambda *_args: pytest.fail("protected geometry read")
    )
    legacy = {"annotation": None, "revision": 3, "contentReferenceSha256": None}
    monkeypatch.setattr(value.repo, "get", lambda *_args: deepcopy(legacy))
    app = FastAPI()
    app.include_router(
        create_grid_cell_content_router(
            lambda: SimpleNamespace(grid_cell_content=GridCellContentService(value.repo))
        )
    )
    path = f"/admin/games/{GAME}/grid-quality-measurements/content-references/{source}/0"
    pins = {"cohortId": str(value.cohort), "manifestSha256": "a" * 64}
    with TestClient(app) as client:
        assert client.get(path).json() == legacy
        response = client.get(path, params=pins)
        assert response.status_code == 200
        result = response.json()["ordinaryPreview"]
        assert (
            result["state"] == "protected"
            and result["nodes"] is None
            and result["productionCells"] == []
        )
        assert "geometryRevision" not in result  # no hidden hints in a protected response
        assert client.get(path, params=pins).json() == response.json()
    assert not any(c[0] in {"write", "flush", "receipt"} for c in value.calls)


def test_control_role_never_exposes_other_slots_or_nodes(fixture, monkeypatch):
    source = UUID(fixture.sources[1]["sourceId"])
    monkeypatch.setattr(
        module, "protected_source", lambda *_args: pytest.fail("role protected first")
    )
    monkeypatch.setattr(module, "_live_source", lambda *_args: pytest.fail("control geometry read"))
    result = module.ordinary_preview(fixture.repo, GAME, source, 0, fixture.cohort, "a" * 64)
    assert result["state"] == "protected"
    assert result["reasonCodes"] == ["CONTENT_CONTROL_ROLE_PROTECTED"]
    assert result["nodes"] is None and result["productionCells"] == []


def test_alias_uuid_uses_the_same_protection_query():
    queries = []
    repo = SimpleNamespace(session=SimpleNamespace(scalar=lambda q: queries.append(q) or GAME))
    source = target(1).source
    alias = source.model_copy(update={"sourceId": GAME, "sourceSha256": "e" * 64})
    assert module.protected_source(repo, GAME, source)
    assert module.protected_source(repo, GAME, alias)
    assert queries[0].compile().params == queries[1].compile().params
