"""Feedback evaluation must preserve pixels and keep test labels outside references."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from scripts.evaluate_grid_audit_feedback import (
    evaluate,
    is_bulk_approval,
    metrics,
    read_snapshot,
    reference_candidates,
    safe_improvement,
    split_rows,
)
from scripts.recognize_grid_audit_symbols import write_json


def _row(index: int, source: str, pixels: str, label: str = "SLIWKA") -> dict:
    return {
        "id": str(index),
        "render_spec": {"sourceChecksumSha256": source},
        "rendered_pixel_checksum_sha256": pixels,
        "label": label,
    }


@pytest.mark.parametrize(
    "action, operation_id, expected",
    [
        ("approve", "batch-operation", True),
        ("approve", None, False),
        ("reassign", "manual-operation", False),
    ],
)
def test_bulk_approvals_are_excluded_but_manual_decisions_remain(
    action: str,
    operation_id: object,
    expected: bool,
) -> None:
    assert is_bulk_approval(action, operation_id) == expected


def test_all_cells_from_one_photo_keep_the_same_split() -> None:
    rows = [_row(i, "same-photo", str(i)) for i in range(15)]
    splits, retained = split_rows(rows)
    assert len(set(splits)) == 1
    assert retained == list(range(15))
    assert split_rows(list(reversed(rows)))[0] == list(reversed(splits))


def test_exact_duplicate_pixels_never_cross_splits() -> None:
    rows = [_row(i, f"photo-{i}", "identical-crop") for i in range(100)]
    splits, retained = split_rows(rows)
    assert len(set(splits)) == 3
    assert {splits[i] for i in retained} == {"train"}


def test_conflicting_labels_for_identical_pixels_are_excluded() -> None:
    rows = [_row(0, "one", "pixels", "SLIWKA"), _row(1, "two", "pixels", "ARBUZ")]
    assert split_rows(rows)[1] == []


def test_reference_votes_use_three_distinct_photos() -> None:
    # Three very close crops from one photo cannot outvote two other photos.
    queries = np.array([[1.0, 0.0]], dtype=np.float32)
    bank = np.array([[1.0, 0.0], [0.999, 0.0], [0.998, 0.0], [0.97, 0.0], [0.96, 0.0]])
    labels = np.array([1, 1, 1, 0, 0])
    result = reference_candidates(queries, bank, labels, ["a", "a", "a", "b", "c"], np.array([0]))
    assert result["references-3-0.95"].tolist() == [0]
    assert result["nearest-0.98"].tolist() == [1]


def test_reference_consensus_threshold_is_enforced() -> None:
    queries = np.array([[1.0, 0.0]])
    bank = np.array([[0.97, 0.0], [0.96, 0.0], [0.94, 0.0]])
    result = reference_candidates(
        queries, bank, np.array([1, 1, 1]), ["a", "b", "c"], np.array([0])
    )
    assert result["references-3-0.9"].tolist() == [1]
    assert result["references-3-0.95"].tolist() == [0]
    assert result["references-3-0.98"].tolist() == [0]


def test_snapshot_can_be_recovered_and_corruption_is_refused(tmp_path: Path) -> None:
    value = {"rows": [{"label": "SLIWKA"}]}
    digest = write_json(tmp_path / "snapshot.json", value)
    write_json(tmp_path / "snapshot.manifest.json", {"sha256": digest})
    assert read_snapshot(tmp_path) == value
    (tmp_path / "snapshot.json").write_text(json.dumps({"rows": []}))
    assert hashlib.sha256((tmp_path / "snapshot.json").read_bytes()).hexdigest() != digest
    with pytest.raises(ValueError, match="checksum differs"):
        read_snapshot(tmp_path)


def test_report_counts_errors_by_actual_class() -> None:
    result = metrics(np.array([0, 0, 1]), np.array([1, 0, 1]), ("SLIWKA", "ARBUZ"))
    assert result["errors"] == 1
    assert result["perClass"]["SLIWKA"] == {"cells": 2, "errors": 1}
    assert result["perClass"]["ARBUZ"] == {"cells": 1, "errors": 0}


def test_invalid_reference_dimensions_are_refused() -> None:
    with pytest.raises(ValueError, match="inconsistent"):
        reference_candidates(
            np.zeros((1, 2)), np.zeros((0, 2)), np.array([], dtype=np.int64), [], np.array([0])
        )
    with pytest.raises(ValueError, match="equally sized"):
        metrics(np.array([0, 1]), np.array([0]), ("SLIWKA", "ARBUZ"))


def test_lower_total_error_cannot_hide_lemon_regression() -> None:
    baseline = {
        "cells": 956,
        "errors": 21,
        "perClass": {
            "CYTRYNA": {"cells": 243, "errors": 2},
            "WINOGRON": {"cells": 118, "errors": 9},
        },
    }
    candidate = {
        "cells": 956,
        "errors": 18,
        "perClass": {
            "CYTRYNA": {"cells": 243, "errors": 5},
            "WINOGRON": {"cells": 118, "errors": 4},
        },
    }
    assert not safe_improvement(baseline, candidate)
    candidate["perClass"]["CYTRYNA"]["errors"] = 2
    assert safe_improvement(baseline, candidate)
    candidate["perClass"]["CYTRYNA"]["cells"] = 242
    assert not safe_improvement(baseline, candidate)


def test_missing_symbol_in_independent_split_stops_evaluation(tmp_path: Path) -> None:
    rows = [_row(i, f"photo-{i}", str(i)) for i in range(100)]
    snapshot = {"rows": rows, "model": {"classCodes": ["SLIWKA", "ARBUZ"]}}
    digest = write_json(tmp_path / "snapshot.json", snapshot)
    write_json(tmp_path / "snapshot.manifest.json", {"sha256": digest})
    np.savez(tmp_path / "features.npz", features=np.ones((100, 2)), logits=np.ones((100, 2)))
    write_json(
        tmp_path / "features.manifest.json",
        {
            "sha256": hashlib.sha256((tmp_path / "features.npz").read_bytes()).hexdigest(),
            "snapshotSha256": digest,
        },
    )
    with pytest.raises(ValueError, match="Every active symbol"):
        evaluate(tmp_path)
