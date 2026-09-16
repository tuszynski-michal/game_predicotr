from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

from game_predictor_worker.semi_automatic_selection.contracts import (
    RangeEvidenceResult,
    RangeEvidenceStatus,
    SemiAutomaticSelectionRange,
    SemiAutomaticSelectionSource,
)

_SCRIPT = Path(__file__).parents[3] / "scripts" / "run_middle_row_range_ocr_v4_acceptance.py"
_SPEC = importlib.util.spec_from_file_location("middle_row_v4_acceptance", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


def _evidence(
    index: int,
    *,
    observed: SemiAutomaticSelectionRange | None,
) -> RangeEvidenceResult:
    return RangeEvidenceResult(
        source=SemiAutomaticSelectionSource(
            source_index=index,
            relative_path=f"source_{index:03d}.jpg",
            size_bytes=10,
            checksum_sha256=f"{index + 1:064x}",
        ),
        status=(
            RangeEvidenceStatus.EXACT_RANGE
            if observed is not None
            else RangeEvidenceStatus.RANGE_UNREADABLE
        ),
        observed_range=observed,
        expected_index=index if observed is not None else None,
        confidence=0.99 if observed is not None else None,
        reason_codes=("MIDDLE_ROW_TRIPLE_EXACT",) if observed else ("LOCAL_BLUR",),
    )


def test_quality_metrics_treat_ambiguous_and_unreadable_exact_as_false() -> None:
    expected = SemiAutomaticSelectionRange(10, 18)
    cases = (
        _MODULE.AcceptanceCase(
            0,
            0,
            "source_000.jpg",
            "1" * 64,
            10,
            _MODULE.HumanLabel("human_readable_exact", expected),
        ),
        _MODULE.AcceptanceCase(
            1,
            1,
            "source_001.jpg",
            "2" * 64,
            10,
            _MODULE.HumanLabel("unreadable", None),
        ),
        _MODULE.AcceptanceCase(
            2,
            2,
            "source_002.jpg",
            "3" * 64,
            10,
            _MODULE.HumanLabel("ambiguous", None),
        ),
    )
    metrics = _MODULE._quality_metrics(
        (
            (cases[0], _evidence(0, observed=expected)),
            (cases[1], _evidence(1, observed=None)),
            (cases[2], _evidence(2, observed=SemiAutomaticSelectionRange(19, 27))),
        )
    )

    assert metrics["correctExactObservations"] == 1
    assert metrics["falseExactCount"] == 1
    assert metrics["labelledFrames"] == 3
    assert metrics["readableFrameCoverage"] == 1.0
    assert metrics["unreadableUnknownRate"] == 1.0


def test_manifest_is_checksum_bound_and_does_not_infer_from_filename(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    root.mkdir()
    content = b"not-a-real-jpeg-for-manifest-validation"
    source = root / "camera_000001.jpg"
    source.write_bytes(content)
    checksum = hashlib.sha256(content).hexdigest()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "contract": _MODULE._MANIFEST_CONTRACT,
                "cases": [
                    {
                        "relativePath": source.name,
                        "sha256": checksum,
                        "humanLabel": {
                            "kind": "human_readable_exact",
                            "expectedRange": [21169, 21177],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    _, cases = _MODULE._load_manifest(
        manifest,
        source_root=root,
        inventory=(source,),
    )

    assert cases[0].relative_path == "camera_000001.jpg"
    assert cases[0].human_label.expected_range == SemiAutomaticSelectionRange(21169, 21177)
    source.write_bytes(content + b"changed")
    try:
        _MODULE._load_manifest(manifest, source_root=root, inventory=(source,))
    except ValueError as error:
        assert "checksum differs" in str(error)
    else:
        raise AssertionError("Changed source must invalidate the frozen manifest.")


def test_selected_metrics_require_complete_manual_review() -> None:
    selected = (
        {"relativePath": "a.jpg", "rangeStart": 1, "rangeEnd": 9},
        {"relativePath": "b.jpg", "rangeStart": 10, "rangeEnd": 18},
    )
    review = _MODULE.SelectedReview(
        relative_path="a.jpg",
        expected_range=SemiAutomaticSelectionRange(1, 9),
        correct_range=True,
        own_exact_proof_visible=True,
        near_evidence_midpoint=True,
    )

    partial = _MODULE._selected_metrics(selected, {"a.jpg": review})
    complete = _MODULE._selected_metrics(selected[:1], {"a.jpg": review})

    assert partial["allSelectedReviewed"] is False
    assert partial["selectedRangePrecision"] is None
    assert complete["allSelectedReviewed"] is True
    assert complete["selectedRangePrecision"] == 1.0
    assert complete["selectedFrameOwnProofRate"] == 1.0


def test_selected_metrics_require_review_range_to_match_selected_range() -> None:
    selected = ({"relativePath": "a.jpg", "rangeStart": 10, "rangeEnd": 18},)
    wrong_range = _MODULE.SelectedReview(
        relative_path="a.jpg",
        expected_range=SemiAutomaticSelectionRange(19, 27),
        correct_range=True,
        own_exact_proof_visible=True,
        near_evidence_midpoint=True,
    )

    metrics = _MODULE._selected_metrics(selected, {"a.jpg": wrong_range})

    assert metrics["allSelectedReviewed"] is True
    assert metrics["selectedRangePrecision"] == 0.0


def test_existing_report_can_receive_selected_review_without_reprocessing() -> None:
    payload = {
        "contract": _MODULE._REPORT_CONTRACT,
        "gateEvaluation": {
            "selectedOwnProofPassed": False,
            "selectedPrecisionPassed": False,
        },
        "grouping": {
            "selected": [{"relativePath": "a.jpg", "rangeStart": 10, "rangeEnd": 18}],
            "allSelectedReviewed": False,
            "selectedFrameOwnProofRate": None,
            "selectedRangePrecision": None,
        },
        "quality": {"exactPrecision": 1.0, "falseExactCount": 0},
        "results": [{"humanLabel": None}],
    }
    review = _MODULE.SelectedReview(
        relative_path="a.jpg",
        expected_range=SemiAutomaticSelectionRange(10, 18),
        correct_range=True,
        own_exact_proof_visible=True,
        near_evidence_midpoint=True,
    )

    updated = _MODULE._apply_selected_review(
        payload,
        selected_review_sha256="1" * 64,
        reviews={"a.jpg": review},
    )

    assert updated["gateEvaluation"]["selectedOwnProofPassed"] is True
    assert updated["gateEvaluation"]["selectedPrecisionPassed"] is True
    assert updated["selectedReviewSha256"] == "1" * 64
    assert updated["quality"]["falseExactCount"] is None
    assert updated["gateEvaluation"]["challengeOrGoldenPrecisionPassed"] is None


def test_window_cases_preserve_original_indexes_but_use_local_sample_indexes(
    tmp_path: Path,
) -> None:
    paths = []
    for index in range(5):
        path = tmp_path / f"camera_{index:06d}.jpg"
        path.write_bytes(bytes([index]))
        paths.append(path)

    cases = _MODULE._window_cases(paths, offset=2, limit=2)

    assert [item.sample_index for item in cases] == [0, 1]
    assert [item.source_index for item in cases] == [2, 3]
