from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
from game_predictor_worker.images.board_cell_geometry_audit import registered_pages
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
from game_predictor_worker.images.board_cell_geometry_shadow_benchmark import (
    SHADOW_MANIFEST_VERSION,
    ShadowStagingSpec,
    cell_geometry_error,
    render_content_addressed_shadow_gallery,
    run_board_cell_geometry_shadow_benchmark,
    select_cross_staging_pages,
    write_content_addressed_shadow_manifest,
)
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
    return {"quads": quads, "sourceRelativePath": relative_path, "status": "registered"}


def _specs(root: Path, *, pages_per_staging: int = 2) -> tuple[ShadowStagingSpec, ...]:
    specs: list[ShadowStagingSpec] = []
    for staging_index in range(6):
        label = f"stage-{staging_index}"
        folder = root / label
        folder.mkdir()
        entries: dict[str, object] = {}
        for page_index in range(pages_per_staging):
            start = 1 + (staging_index * 1000) + page_index * 9
            relative = f"{label}/seq_{start}-{start + 8}.jpg"
            checksum = _source(root / relative, 20 + staging_index * 10 + page_index)
            entries[checksum] = _page_entry(relative)
        manifest = {"entries": entries, "version": "page-geometry-preflight-v1"}
        content = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
        checksum = hashlib.sha256(content).hexdigest()
        path = root / f"{checksum}.json"
        path.write_bytes(content)
        specs.append(
            ShadowStagingSpec(
                label=label,
                manifest_path=path,
                manifest_checksum_sha256=checksum,
            )
        )
    return tuple(specs)


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
        cells=derive_board_cell_quads(bounds, source_image_width=200, source_image_height=120),
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
        candidate_center_count=4,
        assigned_candidate_count=0,
        reliable_center_count=0,
        inlier_slots=(),
        inlier_p95_residual_px=None,
        fallback_reason="BOARD_CELL_GEOMETRY_AXIS_ASSIGNMENT_FAILED",
    )


def test_cross_staging_sample_is_balanced_and_deterministic(tmp_path: Path) -> None:
    specs = _specs(tmp_path)
    staging_pages = []
    for spec in specs:
        payload = json.loads(spec.manifest_path.read_text(encoding="utf-8"))
        staging_pages.append((spec.label, spec.manifest_checksum_sha256, registered_pages(payload)))

    first = select_cross_staging_pages(staging_pages, pages_per_staging=1)
    second = select_cross_staging_pages(staging_pages, pages_per_staging=1)

    assert first == second
    assert len(first) == 6
    assert [page.staging_label for page in first] == [f"stage-{index}" for index in range(6)]


def test_shadow_manifest_requires_complete_cropper_success_and_is_stable(
    tmp_path: Path,
) -> None:
    specs = _specs(tmp_path, pages_per_staging=1)

    first = run_board_cell_geometry_shadow_benchmark(
        staging_specs=specs,
        source_root=tmp_path,
        pages_per_staging=1,
        expected_staging_count=6,
        estimator=lambda _image, _quad: _success_estimate(),
    )
    second = run_board_cell_geometry_shadow_benchmark(
        staging_specs=specs,
        source_root=tmp_path,
        pages_per_staging=1,
        expected_staging_count=6,
        estimator=lambda _image, _quad: _success_estimate(),
    )

    assert first.document == second.document
    assert first.checksum_sha256 == second.checksum_sha256
    assert first.document["version"] == SHADOW_MANIFEST_VERSION
    assert first.document["summary"]["automaticSuccessBoardCount"] == 54
    assert first.document["summary"]["deferredBoardCount"] == 0
    assert all(
        board["crop"]["cellCount"] == 15
        for page in first.document["pages"]
        for board in page["boards"]
    )
    manifest = write_content_addressed_shadow_manifest(first, tmp_path / "output")
    assert manifest.stem == first.checksum_sha256
    gallery = render_content_addressed_shadow_gallery(first, tmp_path / "output")
    assert gallery.is_file()


def test_shadow_manifest_quantizes_sub_millipixel_opencv_drift(tmp_path: Path) -> None:
    baseline = _success_estimate()
    specs = _specs(tmp_path, pages_per_staging=1)

    def shifted(amount: float) -> BoardCellGeometryEstimate:
        assert baseline.lattice_bounds_quad is not None
        bounds = tuple((x + amount, y + amount) for x, y in baseline.lattice_bounds_quad)
        return replace(
            baseline,
            lattice_bounds_quad=bounds,
            cells=derive_board_cell_quads(bounds, source_image_width=200, source_image_height=120),
        )

    first = run_board_cell_geometry_shadow_benchmark(
        staging_specs=specs,
        source_root=tmp_path,
        pages_per_staging=1,
        expected_staging_count=6,
        estimator=lambda _image, _quad: shifted(0.00004),
    )
    second = run_board_cell_geometry_shadow_benchmark(
        staging_specs=specs,
        source_root=tmp_path,
        pages_per_staging=1,
        expected_staging_count=6,
        estimator=lambda _image, _quad: shifted(-0.00004),
    )

    assert first.document == second.document
    assert first.checksum_sha256 == second.checksum_sha256


def test_shadow_failure_is_deferred_without_partial_cells(tmp_path: Path) -> None:
    benchmark = run_board_cell_geometry_shadow_benchmark(
        staging_specs=_specs(tmp_path, pages_per_staging=1),
        source_root=tmp_path,
        pages_per_staging=1,
        expected_staging_count=6,
        estimator=lambda _image, _quad: _failure_estimate(),
    )

    assert benchmark.document["summary"]["automaticSuccessBoardCount"] == 0
    assert benchmark.document["summary"]["deferredBoardCount"] == 54
    assert all(
        board["shadowStatus"] == "deferred" and board["crop"]["cellCount"] == 0
        for page in benchmark.document["pages"]
        for board in page["boards"]
    )


def test_challenge_geometry_detects_a_whole_slot_shift() -> None:
    manual = _success_estimate().cells
    shifted = tuple(
        type(cell)(
            row_index=cell.row_index,
            column_index=cell.column_index,
            quad=tuple((x + 32.0, y) for x, y in cell.quad),
        )
        for cell in manual
    )

    mean_error, max_error, catastrophic = cell_geometry_error(shifted, manual)

    assert mean_error == 32.0
    assert max_error == 32.0
    assert catastrophic is True
