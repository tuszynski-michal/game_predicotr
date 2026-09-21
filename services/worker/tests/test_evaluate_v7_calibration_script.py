from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path

import pytest

FINGERPRINT = "b" * 64
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location(
    "evaluate_v7_calibration_test_module",
    REPOSITORY_ROOT / "scripts" / "evaluate_v7_calibration.py",
)
assert _SPEC is not None and _SPEC.loader is not None
runner = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(runner)


@dataclass(frozen=True, slots=True)
class _InventoryItem:
    case_id: str = "calibration_case"

    def as_dict(self) -> dict[str, object]:
        return {"caseId": self.case_id, "fingerprint": FINGERPRINT, "jpegCount": 5}


@dataclass(frozen=True, slots=True)
class _Manifest:
    cases: tuple[object, ...] = ()

    def fingerprint(self) -> str:
        return FINGERPRINT

    def freeze_inventory(self) -> tuple[_InventoryItem, ...]:
        return (_InventoryItem(),)


def _payload() -> dict[str, object]:
    geometry = []
    for source_index in range(5):
        checksum = f"{source_index + 1:064x}"
        source_id = f"calibration_case/source-{source_index}.jpg"
        for position_index in range(9):
            row, column = divmod(position_index, 3)
            geometry.append(
                {
                    "centerX": 0.2 + column * 0.25,
                    "centerY": 0.3 + row * 0.2,
                    "captureGroupId": f"capture-{source_index % 2}",
                    "cropAssessment": "contained",
                    "geometryFamilyId": "standard_3x3_numeric_labels_v1",
                    "positionIndex": position_index,
                    "sourceChecksumSha256": checksum,
                    "sourceId": source_id,
                    "split": "calibration",
                }
            )
    return {
        "acceptancePredictions": [],
        "acceptanceTruth": [],
        "geometryAnnotations": geometry,
        "geometryFamilyId": "standard_3x3_numeric_labels_v1",
        "manifestFingerprint": FINGERPRINT,
        "schemaVersion": 2,
    }


def test_evaluation_contract_checks_source_identity_and_remains_non_activating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _payload()
    expected_inventory = [_InventoryItem().as_dict()]
    monkeypatch.setattr(runner, "load_v7_corpus_manifest", lambda _path: _Manifest())
    monkeypatch.setattr(
        runner,
        "_frozen_inventory",
        lambda _path: (FINGERPRINT, tuple(expected_inventory)),
    )
    monkeypatch.setattr(runner, "_load_payload", lambda _path: payload)
    monkeypatch.setattr(
        runner,
        "_source_identities",
        lambda _manifest, _splits: {
            f"calibration_case/source-{source_index}.jpg": (
                "calibration_case",
                runner.V7CorpusSplit.CALIBRATION,
                f"{source_index + 1:064x}",
                "standard_3x3_numeric_labels_v1",
            )
            for source_index in range(5)
        },
    )

    report = runner.evaluate_annotation_payload(
        manifest_path=runner.Path("manifest.json"),
        inventory_path=runner.Path("inventory.json"),
        annotations_path=runner.Path("annotations.json"),
        selected_splits={runner.V7CorpusSplit.CALIBRATION},
    )

    assert report["geometry"]["status"] == "passed"
    assert report["acceptance"]["status"] == "not_evaluable"
    assert report["productionActivation"] == {
        "reason": "T12 acceptance plus an explicit activation decision are still required.",
        "status": "blocked",
    }


def test_evaluation_contract_rejects_a_holdout_case_mislabeled_as_calibration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _payload()
    payload["geometryAnnotations"] = []
    payload["acceptanceTruth"] = [
        {
            "automaticallyRecoverable": True,
            "bottomCropped": False,
            "caseId": "range-1-9",
            "corpusCaseId": "holdout_case",
            "eligibleAcceptableRepresentative": True,
            "evidenceSources": [
                {
                    "sourceChecksumSha256": "1" * 64,
                    "sourceId": "calibration_case/source-0.jpg",
                }
            ],
            "expectedRangeEnd": 9,
            "expectedRangeStart": 1,
            "split": "calibration",
            "topCropped": False,
        }
    ]
    payload["acceptancePredictions"] = [
        {
            "bottomWarning": False,
            "caseId": "range-1-9",
            "manualReview": False,
            "rangeOutcome": "not_selected",
            "representativeOutcome": "not_selected",
            "selectedSource": None,
            "topWarning": False,
        }
    ]
    expected_inventory = [_InventoryItem().as_dict()]
    monkeypatch.setattr(runner, "load_v7_corpus_manifest", lambda _path: _Manifest())
    monkeypatch.setattr(
        runner,
        "_frozen_inventory",
        lambda _path: (FINGERPRINT, tuple(expected_inventory)),
    )
    monkeypatch.setattr(runner, "_load_payload", lambda _path: payload)
    monkeypatch.setattr(
        runner,
        "_source_identities",
        lambda _manifest, _splits: {
            "calibration_case/source-0.jpg": (
                "calibration_case",
                runner.V7CorpusSplit.CALIBRATION,
                "1" * 64,
                "standard_3x3_numeric_labels_v1",
            )
        },
    )

    with pytest.raises(ValueError, match="source, case, split, or checksum drifted"):
        runner.evaluate_annotation_payload(
            manifest_path=runner.Path("manifest.json"),
            inventory_path=runner.Path("inventory.json"),
            annotations_path=runner.Path("annotations.json"),
            selected_splits={runner.V7CorpusSplit.CALIBRATION},
        )


def test_evaluation_contract_blocks_frozen_inventory_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runner, "load_v7_corpus_manifest", lambda _path: _Manifest())
    monkeypatch.setattr(runner, "_frozen_inventory", lambda _path: ("c" * 64, ()))

    with pytest.raises(ValueError, match="inventory drifted"):
        runner.evaluate_annotation_payload(
            manifest_path=runner.Path("manifest.json"),
            inventory_path=runner.Path("inventory.json"),
            annotations_path=runner.Path("annotations.json"),
            selected_splits={runner.V7CorpusSplit.CALIBRATION},
        )
