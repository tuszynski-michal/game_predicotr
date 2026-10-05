"""Training RGB contract, frozen-catalogue safety and real audit regressions."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest
import torch
from game_predictor_worker.images.symbol_model_benchmark import SpatialSymbolCnn
from game_predictor_worker.symbols.audit_rgb_classifier import (
    AuditRgbClassifier,
    candidate_is_tentative,
    rgb_batch,
)
from PIL import Image

FIXTURES = Path(__file__).parent / "fixtures" / "grid-audit-rgb"
ROOT = Path(__file__).resolve().parents[3]


def _checkpoint(tmp_path: Path) -> tuple[Path, str]:
    path = tmp_path / "model.pt"
    torch.save(
        {"classCodes": ("SLIWKA", "ARBUZ"), "bestState": SpatialSymbolCnn(2).state_dict()}, path
    )
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def test_rgb_contract_preserves_background_foreground_and_channel_order() -> None:
    with Image.open(FIXTURES / "p00519.png") as image:
        crop = np.asarray(image.convert("RGB"))[0:64, 256:320].copy()[None]
    batch = rgb_batch(crop)
    expected = torch.from_numpy(crop.transpose(0, 3, 1, 2).astype(np.float32) / 127.5 - 1)
    assert torch.equal(batch, expected)
    assert not np.array_equal(crop[0, ..., 0], crop[0, ..., 2])


@pytest.mark.parametrize("shape", [(64, 64, 3), (1, 63, 64, 3), (1, 64, 64, 4)])
def test_invalid_crop_shape_is_refused(shape: tuple[int, ...]) -> None:
    with pytest.raises(ValueError, match="RGB uint8"):
        rgb_batch(np.zeros(shape, dtype=np.uint8))


def test_checkpoint_checksum_and_exact_class_order_are_required(tmp_path: Path) -> None:
    path, sha = _checkpoint(tmp_path)
    with pytest.raises(ValueError, match="checksum"):
        AuditRgbClassifier(path, "0" * 64, ("SLIWKA", "ARBUZ"))
    with pytest.raises(ValueError, match="catalogue"):
        AuditRgbClassifier(path, sha, ("ARBUZ", "SLIWKA"))
    with pytest.raises(ValueError, match="catalogue"):
        AuditRgbClassifier(path, sha, ("SLIWKA", "SLIWKA"))


def test_incompatible_spatial_checkpoint_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "incompatible.pt"
    torch.save({"classCodes": ("SLIWKA", "ARBUZ"), "bestState": {}}, path)
    with pytest.raises(ValueError, match="incompatible spatial state"):
        AuditRgbClassifier(path, hashlib.sha256(path.read_bytes()).hexdigest(), ("SLIWKA", "ARBUZ"))


def test_logits_are_advisory_with_stable_ties_and_invalid_output_refused(tmp_path: Path) -> None:
    path, sha = _checkpoint(tmp_path)
    classifier = AuditRgbClassifier(path, sha, ("SLIWKA", "ARBUZ"))
    classifier.network = Mock(return_value=torch.tensor([[1.0, 1.0], [1.0, 2.0]]))
    crops = np.zeros((2, 64, 64, 3), dtype=np.uint8)
    assert classifier.candidates(crops).tolist() == [0, 1]
    assert candidate_is_tentative(0, None)
    assert candidate_is_tentative(0, 1)
    assert not candidate_is_tentative(0, 0)
    classifier.network = Mock(return_value=torch.tensor([[float("nan"), 1.0], [1.0, 2.0]]))
    with pytest.raises(ValueError, match="invalid logits"):
        classifier.candidates(crops)


@pytest.fixture(scope="module")
def frozen_real_classifier() -> AuditRgbClassifier:
    metadata_path = ROOT / "artifacts/grid-audit-symbols-20261005/library.json"
    if not metadata_path.is_file():
        pytest.skip(
            "Real checkpoint is an operator-owned local artifact, not a test weight fixture."
        )
    metadata = json.loads(metadata_path.read_bytes())
    expectations = json.loads((FIXTURES / "expected.json").read_bytes())
    assert metadata["checkpointSha256"] == expectations["checkpointSha256"]
    return AuditRgbClassifier(
        Path(metadata["checkpointPath"]), metadata["checkpointSha256"], metadata["classCodes"]
    )


@pytest.mark.parametrize(
    "item", ["p00519", "p00523", "p00525", "p00527", "p00689", "p00796", "p00901", "p01019"]
)
def test_real_rgb_regression_matches_visually_checked_symbols(
    item: str, frozen_real_classifier: AuditRgbClassifier
) -> None:
    manifest = json.loads((FIXTURES / "expected.json").read_bytes())
    entry = manifest["boards"][item]
    content = (FIXTURES / (item + ".png")).read_bytes()
    assert hashlib.sha256(content).hexdigest() == entry["sha256"]
    with Image.open(FIXTURES / (item + ".png")) as image:
        rgb = np.asarray(image.convert("RGB"))
    crops = np.stack(
        [rgb[r * 64 : (r + 1) * 64, c * 64 : (c + 1) * 64] for r in range(3) for c in range(5)]
    )
    indices = frozen_real_classifier.candidates(crops)
    codes = [frozen_real_classifier.class_codes[index] for index in indices]
    # These are visual regression expectations, not operator-approved labels.
    assert codes == entry["codes"]
