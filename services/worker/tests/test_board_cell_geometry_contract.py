from __future__ import annotations

import json
import math
from collections import Counter
from copy import deepcopy
from pathlib import Path

import pytest
from game_predictor_worker.images.board_cell_geometry_contract import (
    BOARD_CELL_COORDINATE_SPACE,
    BOARD_CELL_CORNER_SEMANTICS,
    BOARD_CELL_COUNT,
    BOARD_CELL_GEOMETRY_MANIFEST_VERSION,
    BOARD_CELL_GEOMETRY_VERSION,
    BoardCellGeometryContractError,
    BoardCellGeometryManifestV1,
    load_board_cell_geometry_manifest,
    load_real_board_cell_geometry_corpus,
    parse_board_cell_geometry_manifest,
    write_content_addressed_manifest,
)
from game_predictor_worker.images.pipeline_contract import current_pipeline_manifest

ROOT = Path(__file__).resolve().parents[3]
DESCRIPTOR = ROOT / "ai_docs" / "quality" / "board-cell-geometry-v19-real-corpus.json"
SCHEMA = ROOT / "ai_docs" / "quality" / "board-cell-geometry-manifest-v1.schema.json"
REAL_CORPUS_MANIFEST_SHA256 = "45a82dbb0f86ca62646e1d680f2a0d9ea78a62f38b1d24b72be2ce50764aeb25"


def _manifest() -> BoardCellGeometryManifestV1:
    return load_real_board_cell_geometry_corpus(
        ROOT,
        DESCRIPTOR,
        verify_source_images=False,
    )


def test_real_corpus_reuses_only_complete_owner_reviewed_geometry() -> None:
    manifest = _manifest()

    assert manifest.purpose == "regression_corpus"
    assert len(manifest.entries) == 27
    assert len({entry.source_image_checksum_sha256 for entry in manifest.entries}) == 27
    assert Counter(entry.position_index for entry in manifest.entries) == Counter(
        {position: 3 for position in range(9)}
    )
    assert len({entry.source_group for entry in manifest.entries}) == 2
    assert [entry.source_order_index for entry in manifest.entries] == list(range(27))
    assert all(entry.evidence.kind == "human_reviewed" for entry in manifest.entries)
    assert all(entry.evidence.decision_checksum_sha256 for entry in manifest.entries)
    assert all(len(entry.cells) == BOARD_CELL_COUNT for entry in manifest.entries)
    assert manifest.checksum_sha256 == REAL_CORPUS_MANIFEST_SHA256
    assert all(
        [(cell.row_index, cell.column_index) for cell in entry.cells]
        == [(row, column) for row in range(3) for column in range(5)]
        for entry in manifest.entries
    )


def test_local_real_corpus_jpegs_match_the_pinned_manifest() -> None:
    representative_source = ROOT / "examples" / "imgs" / "5983122166590934317.jpg"
    if not representative_source.is_file():
        pytest.skip("The ignored local M5 source corpus is not present in this checkout.")

    verified = load_real_board_cell_geometry_corpus(ROOT, DESCRIPTOR)

    assert verified.checksum_sha256 == REAL_CORPUS_MANIFEST_SHA256


def test_manifest_is_canonical_round_trippable_and_content_addressed(tmp_path: Path) -> None:
    manifest = _manifest()
    parsed = load_board_cell_geometry_manifest(manifest.to_json_bytes())

    assert parsed == manifest
    assert parsed.to_json_bytes() == manifest.to_json_bytes()
    output = write_content_addressed_manifest(manifest, tmp_path)
    assert output.name == f"{manifest.checksum_sha256}.json"
    assert output.read_bytes() == manifest.to_json_bytes()
    assert write_content_addressed_manifest(manifest, tmp_path) == output

    output.write_bytes(b"drift")
    with pytest.raises(BoardCellGeometryContractError) as raised:
        write_content_addressed_manifest(manifest, tmp_path)
    assert raised.value.code == "BOARD_CELL_GEOMETRY_MANIFEST_COLLISION"


def test_perspective_quad_is_valid_without_source_image_right_angles() -> None:
    manifest = _manifest()
    quad = manifest.entries[0].lattice_bounds_quad
    top = (quad[1][0] - quad[0][0], quad[1][1] - quad[0][1])
    left = (quad[3][0] - quad[0][0], quad[3][1] - quad[0][1])
    cosine = (top[0] * left[0] + top[1] * left[1]) / (math.hypot(*top) * math.hypot(*left))

    assert abs(cosine) > 0.01
    assert parse_board_cell_geometry_manifest(manifest.to_dict()) == manifest


def test_manifest_rejects_a_cell_not_derived_from_the_lattice_bounds() -> None:
    payload = deepcopy(_manifest().to_dict())
    payload["entries"][0]["cells"][0]["quad"][0]["x"] += 1.0  # type: ignore[index]

    with pytest.raises(BoardCellGeometryContractError) as raised:
        parse_board_cell_geometry_manifest(payload)
    assert raised.value.code == "BOARD_CELL_GEOMETRY_CELL_DERIVATION_MISMATCH"


def test_manifest_rejects_a_crossed_lattice_bounds_quad() -> None:
    payload = deepcopy(_manifest().to_dict())
    quad = payload["entries"][0]["latticeBoundsQuad"]  # type: ignore[index]
    quad[1], quad[3] = quad[3], quad[1]  # type: ignore[index]

    with pytest.raises(BoardCellGeometryContractError) as raised:
        parse_board_cell_geometry_manifest(payload)
    assert raised.value.code == "BOARD_CELL_GEOMETRY_QUAD_INVALID"


def test_manifest_rejects_automatic_geometry_without_complete_ransac_evidence() -> None:
    payload = deepcopy(_manifest().to_dict())
    evidence = payload["entries"][0]["evidence"]  # type: ignore[index]
    evidence.update(  # type: ignore[union-attr]
        {
            "decisionChecksumSha256": None,
            "homographyVersion": "test-homography-v1",
            "kind": "automatic",
            "locatorVersion": "test-locator-v1",
        }
    )

    with pytest.raises(BoardCellGeometryContractError) as raised:
        parse_board_cell_geometry_manifest(payload)
    assert raised.value.code == "BOARD_CELL_GEOMETRY_AUTOMATIC_EVIDENCE_INSUFFICIENT"


def test_manifest_accepts_complete_versioned_automatic_evidence() -> None:
    payload = deepcopy(_manifest().to_dict())
    evidence = payload["entries"][0]["evidence"]  # type: ignore[index]
    evidence.update(  # type: ignore[union-attr]
        {
            "candidateCenterCount": 15,
            "decisionChecksumSha256": None,
            "homographyVersion": "test-homography-v1",
            "inlierCount": 15,
            "inlierP95ResidualPx": 2.5,
            "inlierSlots": [
                {"columnIndex": column, "rowIndex": row}
                for row in range(3)
                for column in range(5)
            ],
            "kind": "automatic",
            "locatorVersion": "test-locator-v1",
            "reliableCenterCount": 15,
        }
    )

    parsed = parse_board_cell_geometry_manifest(payload)

    assert parsed.entries[0].evidence.kind == "automatic"
    assert parsed.entries[0].evidence.inlier_count == 15


def test_real_corpus_descriptor_fails_closed_on_annotation_drift(tmp_path: Path) -> None:
    descriptor = json.loads(DESCRIPTOR.read_text(encoding="utf-8"))
    descriptor["annotationManifest"]["sha256"] = "0" * 64
    changed = tmp_path / "descriptor.json"
    changed.write_text(json.dumps(descriptor), encoding="utf-8")

    with pytest.raises(BoardCellGeometryContractError) as raised:
        load_real_board_cell_geometry_corpus(ROOT, changed)
    assert raised.value.code == "BOARD_CELL_GEOMETRY_ARTIFACT_DRIFT"


def test_documented_schema_and_runtime_contract_versions_are_identical() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    assert schema["properties"]["version"]["const"] == BOARD_CELL_GEOMETRY_MANIFEST_VERSION
    assert schema["properties"]["geometryVersion"]["const"] == BOARD_CELL_GEOMETRY_VERSION
    assert schema["properties"]["coordinateSpace"]["const"] == BOARD_CELL_COORDINATE_SPACE
    assert schema["properties"]["cornerSemantics"]["const"] == BOARD_CELL_CORNER_SEMANTICS


def test_task_two_does_not_activate_v19_in_the_pipeline() -> None:
    manifest = current_pipeline_manifest()

    assert (
        manifest["components"]["board_crops"]["adapterVersion"]
        == "board-cell-crops-v18-source-direct-validated-v1"
    )
