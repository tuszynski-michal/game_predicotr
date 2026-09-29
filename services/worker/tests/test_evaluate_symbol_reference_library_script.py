from __future__ import annotations

import hashlib
import importlib.util
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from game_predictor_worker.images.normalization import rgb_pixel_checksum_sha256
from game_predictor_worker.images.virtual_cell_extraction import source_direct_warp_rgb
from PIL import Image

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location(
    "evaluate_symbol_reference_library_test_module",
    REPOSITORY_ROOT / "scripts" / "evaluate_symbol_reference_library.py",
)
assert _SPEC is not None and _SPEC.loader is not None
runner: Any = importlib.util.module_from_spec(_SPEC)
# Dataclasses resolve their module through sys.modules while the script executes.
sys.modules[_SPEC.name] = runner
_SPEC.loader.exec_module(runner)

QUAD = ((10.0, 10.0), (60.0, 10.0), (60.0, 60.0), (10.0, 60.0))


def _source(root: Path) -> tuple[str, str]:
    """Write one managed JPEG and return its checksum and the exact crop checksum."""

    rng = np.random.default_rng(7)
    pixels = rng.integers(0, 255, (80, 80, 3), dtype=np.uint8)
    staging = root / "staging.jpg"
    Image.fromarray(pixels).save(staging, format="JPEG", quality=95)
    checksum = hashlib.sha256(staging.read_bytes()).hexdigest()
    managed = root / "data" / "originals" / checksum[:2] / f"{checksum}.jpg"
    managed.parent.mkdir(parents=True)
    staging.replace(managed)
    with Image.open(managed) as image:
        decoded = np.asarray(image.convert("RGB"), dtype=np.uint8)
    crop = source_direct_warp_rgb(decoded, source_quad=QUAD, output_width=64, output_height=64)
    return checksum, rgb_pixel_checksum_sha256(crop)


def _cell(identifier: str, source: str, pixels: str) -> Any:
    return runner.Cell(
        id=identifier,
        import_job_id="import",
        sequence_number=1,
        cell_index=0,
        prediction_symbol_code="ARBUZ",
        prediction_confidence=0.7,
        rendered_pixel_checksum_sha256=pixels,
        source_checksum_sha256=source,
        padded_quad=QUAD,
        source_quad=QUAD,
        label="ARBUZ",
    )


def test_pixel_checksum_mismatch_is_excluded_and_counted(tmp_path: Path) -> None:
    source, pixels = _source(tmp_path)
    good = _cell("good", source, pixels)
    drifted = _cell("drifted", source, "0" * 64)

    cache, remaining = runner._render(
        [good, drifted],
        artifact_root=tmp_path,
        cache_path=tmp_path / "cache.npz",
        deadline=time.monotonic() + 60,
    )
    usable, excluded = runner._usable([good, drifted], cache)

    assert remaining == 0
    assert [cell.id for cell in usable] == ["good"]
    assert excluded == {"IMAGE_VIRTUAL_CELL_PIXEL_CHECKSUM_MISMATCH": 1}
    assert rgb_pixel_checksum_sha256(cache[runner._cache_key(good)]["crop"]) == pixels


def test_cache_resumes_without_rendering_again(tmp_path: Path) -> None:
    source, pixels = _source(tmp_path)
    cell = _cell("good", source, pixels)
    cache_path = tmp_path / "cache.npz"

    runner._render(
        [cell], artifact_root=tmp_path, cache_path=cache_path, deadline=time.monotonic() + 60
    )
    # A past deadline would stop any new rendering; the cached crop must still be returned.
    cache, remaining = runner._render(
        [cell], artifact_root=tmp_path, cache_path=cache_path, deadline=0.0
    )

    assert remaining == 0
    assert cache[runner._cache_key(cell)]["status"] == "ok"


def test_expired_budget_reports_remaining_crops(tmp_path: Path) -> None:
    source, pixels = _source(tmp_path)

    _cache, remaining = runner._render(
        [_cell("first", source, pixels), _cell("second", source, pixels)],
        artifact_root=tmp_path,
        cache_path=tmp_path / "cache.npz",
        deadline=0.0,
    )

    assert remaining == 2


def test_missing_original_is_an_error_and_is_not_cached(tmp_path: Path) -> None:
    cache_path = tmp_path / "cache.npz"

    with pytest.raises(runner.EvaluationError) as error:
        runner._render(
            [_cell("missing", "a" * 64, "0" * 64)],
            artifact_root=tmp_path,
            cache_path=cache_path,
            deadline=time.monotonic() + 60,
        )

    assert error.value.code == "SYMBOL_REFERENCE_SOURCE_UNAVAILABLE"
    assert not cache_path.exists()


def test_incomplete_render_spec_is_a_contract_error() -> None:
    row = {
        "id": "cell",
        "import_job_id": "import",
        "sequence_number": 1,
        "cell_index": 0,
        "prediction_symbol_code": "ARBUZ",
        "prediction_confidence": 0.7,
        "rendered_pixel_checksum_sha256": "0" * 64,
        "label": None,
        "render_spec": {"configuration": {"outputWidth": 64, "outputHeight": 64}},
    }

    with pytest.raises(runner.EvaluationError) as error:
        runner._cell(row)

    assert error.value.code == "SYMBOL_REFERENCE_RENDER_SPEC_INVALID"


def test_evaluation_excludes_the_cells_own_import() -> None:
    labels = np.array([0] * 7 + [1] * 7, dtype=np.int64)
    imports = np.array(["a"] * 7 + ["b"] * 7)
    descriptors = np.array([[1.0, 0.0]] * 7 + [[0.0, 1.0]] * 7, dtype=np.float32)

    proposals = runner._proposals(
        descriptors,
        descriptors,
        descriptors,
        descriptors,
        labels,
        class_count=2,
        exclusions=[imports == value for value in imports],
    )

    # With its own import removed, each cell only sees the other symbol's cells.
    assert [proposal.class_index for proposal in proposals] == [1] * 7 + [0] * 7
