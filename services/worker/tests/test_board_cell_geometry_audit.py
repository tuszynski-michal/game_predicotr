from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import numpy as np
import pytest
from game_predictor_worker.images.board_cell_geometry_audit import (
    AUDIT_VERSION,
    BoardCellGeometryAuditError,
    registered_pages,
    render_audit_contact_sheets,
    render_audit_overlays,
    run_board_cell_geometry_audit,
    select_audit_pages,
    write_content_addressed_audit,
)
from game_predictor_worker.images.board_cell_geometry_contract import (
    BoardCellGeometryEvidence,
    derive_board_cell_quads,
)
from game_predictor_worker.images.board_cell_geometry_estimator import (
    ESTIMATOR_VERSION,
    HOMOGRAPHY_VERSION,
    LOCATOR_VERSION,
    THRESHOLDS_VERSION,
    BoardCellGeometryEstimate,
)
from game_predictor_worker.images.geometry import Quad
from PIL import Image


def _source(path: Path, value: int) -> str:
    pixels = np.full((120, 200, 3), value, dtype=np.uint8)
    Image.fromarray(pixels, mode="RGB").save(path, format="JPEG", quality=95)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _page_entry(relative_path: str) -> dict[str, object]:
    quads = []
    for row in range(3):
        for column in range(3):
            left = 8 + column * 62
            top = 8 + row * 36
            quads.append(
                [
                    {"x": left, "y": top},
                    {"x": left + 54, "y": top},
                    {"x": left + 54, "y": top + 28},
                    {"x": left, "y": top + 28},
                ]
            )
    return {
        "quads": quads,
        "sourceRelativePath": relative_path,
        "status": "registered",
    }


def _manifest(entries: Mapping[str, object]) -> dict[str, object]:
    return {
        "entries": entries,
        "version": "page-geometry-preflight-v1",
    }


def _success_estimate() -> BoardCellGeometryEstimate:
    bounds = ((20.0, 20.0), (180.0, 20.0), (180.0, 100.0), (20.0, 100.0))
    slots = tuple((row, column) for row in range(3) for column in range(5))
    evidence = BoardCellGeometryEvidence(
        kind="automatic",
        estimator_version=ESTIMATOR_VERSION,
        thresholds_version=THRESHOLDS_VERSION,
        locator_version=LOCATOR_VERSION,
        homography_version=HOMOGRAPHY_VERSION,
        candidate_center_count=15,
        reliable_center_count=15,
        inlier_count=15,
        inlier_slots=slots,
        inlier_p95_residual_px=1.0,
        decision_checksum_sha256=None,
    )
    return BoardCellGeometryEstimate(
        status="estimated",
        lattice_bounds_quad=bounds,
        cells=derive_board_cell_quads(
            bounds,
            source_image_width=200,
            source_image_height=120,
        ),
        evidence=evidence,
        candidate_center_count=15,
        assigned_candidate_count=15,
        reliable_center_count=15,
        inlier_slots=slots,
        inlier_p95_residual_px=1.0,
        fallback_reason=None,
    )


def _failure_estimate() -> BoardCellGeometryEstimate:
    return BoardCellGeometryEstimate(
        status="needs_review",
        lattice_bounds_quad=None,
        cells=(),
        evidence=None,
        candidate_center_count=7,
        assigned_candidate_count=0,
        reliable_center_count=0,
        inlier_slots=(),
        inlier_p95_residual_px=None,
        fallback_reason="BOARD_CELL_GEOMETRY_AXIS_ASSIGNMENT_FAILED",
    )


def test_sample_is_stable_when_manifest_entry_order_changes(tmp_path: Path) -> None:
    first = _source(tmp_path / "seq_1-9.jpg", 30)
    second = _source(tmp_path / "seq_10-18.jpg", 60)
    third = _source(tmp_path / "seq_19-27.jpg", 90)
    entries = {
        first: _page_entry("seq_1-9.jpg"),
        second: _page_entry("seq_10-18.jpg"),
        third: _page_entry("seq_19-27.jpg"),
    }

    forward = select_audit_pages(registered_pages(_manifest(entries)), sample_size=2)
    reverse = select_audit_pages(
        registered_pages(_manifest(dict(reversed(tuple(entries.items()))))), sample_size=2
    )

    assert [page.source_checksum_sha256 for page in forward] == [
        page.source_checksum_sha256 for page in reverse
    ]


def test_audit_checks_sources_and_reports_each_board(tmp_path: Path) -> None:
    first = _source(tmp_path / "seq_1-9.jpg", 30)
    second = _source(tmp_path / "seq_10-18.jpg", 60)
    manifest_path = tmp_path / "page-manifest.json"
    manifest_path.write_text(
        json.dumps(
            _manifest(
                {
                    first: _page_entry("seq_1-9.jpg"),
                    second: _page_entry("seq_10-18.jpg"),
                }
            )
        ),
        encoding="utf-8",
    )

    def estimator(_image: np.ndarray, quad: Quad) -> BoardCellGeometryEstimate:
        return _success_estimate() if quad[0].x < 70 else _failure_estimate()

    audit = run_board_cell_geometry_audit(
        page_geometry_manifest_path=manifest_path,
        source_root=tmp_path,
        sample_size=2,
        estimator=estimator,
    )

    assert audit.document["version"] == AUDIT_VERSION
    assert audit.document["scope"] == {
        "boardCount": 18,
        "pageCount": 2,
        "registeredPageCount": 2,
    }
    assert audit.document["summary"] == {
        "estimatedBoardCount": 6,
        "fallbackReasonCounts": {"BOARD_CELL_GEOMETRY_AXIS_ASSIGNMENT_FAILED": 12},
        "needsReviewBoardCount": 12,
    }
    pages = cast(list[dict[str, object]], audit.document["pages"])
    assert len(pages) == 2
    assert all(len(cast(list[object], page["boards"])) == 9 for page in pages)
    assert str(tmp_path) not in json.dumps(audit.document)

    report_path = write_content_addressed_audit(audit, tmp_path / "reports")
    assert report_path.stem == audit.checksum_sha256
    assert write_content_addressed_audit(audit, tmp_path / "reports") == report_path
    overlays = render_audit_overlays(audit, tmp_path / "overlays")
    assert len(overlays) == 2
    assert all(Image.open(path).size == (200, 120) for path in overlays)
    sheets = render_audit_contact_sheets(audit, tmp_path / "sheets")
    assert len(sheets) == 1
    assert Image.open(sheets[0]).size == (1800, 1400)


def test_audit_rejects_source_checksum_drift(tmp_path: Path) -> None:
    checksum = _source(tmp_path / "seq_1-9.jpg", 30)
    manifest_path = tmp_path / "page-manifest.json"
    manifest_path.write_text(
        json.dumps(_manifest({checksum: _page_entry("seq_1-9.jpg")})),
        encoding="utf-8",
    )
    _source(tmp_path / "seq_1-9.jpg", 31)

    with pytest.raises(BoardCellGeometryAuditError) as caught:
        run_board_cell_geometry_audit(
            page_geometry_manifest_path=manifest_path,
            source_root=tmp_path,
            sample_size=1,
            estimator=lambda _image, _quad: _failure_estimate(),
        )

    assert caught.value.code == "BOARD_CELL_GEOMETRY_AUDIT_SOURCE_DRIFT"


def test_registered_page_requires_exact_attested_nine_board_range() -> None:
    checksum = "1" * 64
    entry = _page_entry("seq_1-8.jpg")

    with pytest.raises(BoardCellGeometryAuditError) as caught:
        registered_pages(_manifest({checksum: entry}))

    assert caught.value.code == "BOARD_CELL_GEOMETRY_AUDIT_SEQUENCE_RANGE_INVALID"


def test_registered_page_rejects_unsafe_path() -> None:
    checksum = "1" * 64
    entry = _page_entry("../seq_1-9.jpg")

    with pytest.raises(BoardCellGeometryAuditError) as caught:
        registered_pages(_manifest({checksum: entry}))

    assert caught.value.code == "BOARD_CELL_GEOMETRY_AUDIT_PATH_UNSAFE"
