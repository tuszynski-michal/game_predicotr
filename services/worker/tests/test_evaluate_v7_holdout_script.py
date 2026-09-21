from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path

import pytest

FINGERPRINT = "a" * 64
SOURCE_CHECKSUM = "b" * 64
ALGORITHM_FINGERPRINT = "c" * 64
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location(
    "evaluate_v7_holdout_test_module",
    REPOSITORY_ROOT / "scripts" / "evaluate_v7_holdout.py",
)
assert _SPEC is not None and _SPEC.loader is not None
runner = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(runner)


@dataclass(frozen=True, slots=True)
class _Case:
    case_id: str = "reels_test"
    split: object = runner.V7CorpusSplit.HOLDOUT


@dataclass(frozen=True, slots=True)
class _InventoryItem:
    case_id: str = "reels_test"

    def as_dict(self) -> dict[str, object]:
        return {"caseId": self.case_id, "fingerprint": FINGERPRINT, "jpegCount": 2}


@dataclass(frozen=True, slots=True)
class _Manifest:
    cases: tuple[object, ...] = (_Case(),)

    def fingerprint(self) -> str:
        return FINGERPRINT

    def freeze_inventory(self) -> tuple[_InventoryItem, ...]:
        return (_InventoryItem(),)


class _ChangingManifest:
    def __init__(self) -> None:
        self.freeze_calls = 0
        self.cases = (_Case(),)

    def fingerprint(self) -> str:
        return FINGERPRINT

    def freeze_inventory(self) -> tuple[_InventoryItem, ...]:
        self.freeze_calls += 1
        if self.freeze_calls == 1:
            return (_InventoryItem(),)
        return (_InventoryItem(case_id="changed"),)


def _geometry() -> dict[str, object]:
    return {
        "inputFingerprint": "d" * 64,
        "manifestFingerprint": FINGERPRINT,
        "status": "passed",
        "version": "v7-calibration-v1",
    }


def _truth() -> dict[str, object]:
    return {
        "automaticallyRecoverable": True,
        "acceptableRepresentativeSources": [
            {
                "sourceChecksumSha256": SOURCE_CHECKSUM,
                "sourceId": "reels_test/source-1.jpg",
            }
        ],
        "caseId": "range-1-9",
        "corpusCaseId": "reels_test",
        "eligibleAcceptableRepresentative": True,
        "evidenceSources": [
            {
                "sourceChecksumSha256": SOURCE_CHECKSUM,
                "sourceId": "reels_test/source-1.jpg",
            }
        ],
        "expectedRangeEnd": 9,
        "expectedRangeStart": 1,
        "split": "holdout",
    }


def _source_observation(
    source_id: str = "reels_test/source-1.jpg",
    checksum: str = SOURCE_CHECKSUM,
    *,
    range_start: int = 1,
    range_end: int = 9,
    top: bool = True,
    bottom: bool = True,
) -> dict[str, object]:
    return {
        "bottomCropped": bottom,
        "representedRangeEnd": range_end,
        "representedRangeStart": range_start,
        "sourceChecksumSha256": checksum,
        "sourceId": source_id,
        "topCropped": top,
    }


def _prediction() -> dict[str, object]:
    return {
        "bottomWarning": True,
        "caseId": "range-1-9",
        "manualReview": False,
        "predictedRangeEnd": 9,
        "predictedRangeStart": 1,
        "selectedSource": {
            "sourceChecksumSha256": SOURCE_CHECKSUM,
            "sourceId": "reels_test/source-1.jpg",
        },
        "topWarning": True,
    }


def _payloads() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    inventory = [_InventoryItem().as_dict()]
    inventory_fingerprint = runner._fingerprint(inventory)
    calibration = {
        "corpusManifestFingerprint": FINGERPRINT,
        "geometry": _geometry(),
        "schemaVersion": 1,
    }
    truth = {
        "cases": [_truth()],
        "holdoutInventoryFingerprint": inventory_fingerprint,
        "manifestFingerprint": FINGERPRINT,
        "schemaVersion": 1,
        "sourceObservations": [_source_observation()],
    }
    prediction = {
        "algorithmFingerprint": ALGORITHM_FINGERPRINT,
        "calibrationFingerprint": runner._fingerprint(_geometry()),
        "cases": [_prediction()],
        "holdoutInventoryFingerprint": inventory_fingerprint,
        "manifestFingerprint": FINGERPRINT,
        "schemaVersion": 1,
    }
    return calibration, truth, prediction


def _configure_runner(
    monkeypatch: pytest.MonkeyPatch,
    *,
    calibration: dict[str, object],
    truth: dict[str, object],
    prediction: dict[str, object],
) -> None:
    inventory = [_InventoryItem().as_dict()]
    payloads = {
        "calibration.json": calibration,
        "truth.json": truth,
        "prediction.json": prediction,
    }
    monkeypatch.setattr(runner, "load_v7_corpus_manifest", lambda _path: _Manifest())
    monkeypatch.setattr(runner, "_frozen_inventory", lambda _path: (FINGERPRINT, tuple(inventory)))
    monkeypatch.setattr(runner, "_read_object", lambda path, _name: payloads[path.name])
    monkeypatch.setattr(
        runner,
        "_holdout_source_identities",
        lambda _manifest, *, holdout_case_id: {
            "reels_test/source-1.jpg": (
                holdout_case_id,
                runner.V7CorpusSplit.HOLDOUT,
                SOURCE_CHECKSUM,
            )
        },
    )


def _evaluate() -> dict[str, object]:
    return runner.evaluate_holdout(
        manifest_path=Path("manifest.json"),
        inventory_path=Path("inventory.json"),
        calibration_path=Path("calibration.json"),
        truth_path=Path("truth.json"),
        predictions_path=Path("prediction.json"),
    )


def test_evaluator_accepts_only_frozen_holdout_evidence_and_never_activates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calibration, truth, prediction = _payloads()
    _configure_runner(monkeypatch, calibration=calibration, truth=truth, prediction=prediction)

    report = _evaluate()

    assert report["acceptance"]["status"] == "passed"
    assert report["algorithmFingerprint"] == ALGORITHM_FINGERPRINT
    assert report["holdoutCaseId"] == "reels_test"
    assert report["productionActivation"] == {
        "reason": (
            "T13b handler integration, T12 review, and an explicit activation decision "
            "are required."
        ),
        "status": "blocked",
    }


def test_evaluator_reports_empty_holdout_as_not_evaluable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calibration, truth, prediction = _payloads()
    truth["cases"] = []
    prediction["cases"] = []
    _configure_runner(monkeypatch, calibration=calibration, truth=truth, prediction=prediction)

    report = _evaluate()

    assert report["acceptance"]["status"] == "not_evaluable"


def test_evaluator_derives_incorrect_outcomes_from_raw_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calibration, truth, prediction = _payloads()
    prediction["cases"][0]["predictedRangeStart"] = 10
    prediction["cases"][0]["predictedRangeEnd"] = 18
    _configure_runner(monkeypatch, calibration=calibration, truth=truth, prediction=prediction)

    report = _evaluate()

    assert report["acceptance"]["status"] == "failed"
    assert report["acceptance"]["incorrectAutomaticRangeCount"] == 1


def test_evaluator_derives_wrong_representative_from_truth_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calibration, truth, prediction = _payloads()
    truth["cases"][0]["acceptableRepresentativeSources"] = [
        {
            "sourceChecksumSha256": "d" * 64,
            "sourceId": "reels_test/source-2.jpg",
        }
    ]
    truth["sourceObservations"].append(
        _source_observation("reels_test/source-2.jpg", "d" * 64)
    )
    _configure_runner(monkeypatch, calibration=calibration, truth=truth, prediction=prediction)
    monkeypatch.setattr(
        runner,
        "_holdout_source_identities",
        lambda _manifest, *, holdout_case_id: {
            "reels_test/source-1.jpg": (
                holdout_case_id,
                runner.V7CorpusSplit.HOLDOUT,
                SOURCE_CHECKSUM,
            ),
            "reels_test/source-2.jpg": (
                holdout_case_id,
                runner.V7CorpusSplit.HOLDOUT,
                "d" * 64,
            ),
        },
    )

    report = _evaluate()

    assert report["acceptance"]["status"] == "failed"
    assert report["acceptance"]["representativeSelection"]["numerator"] == 0


def test_evaluator_rejects_declared_range_when_selected_source_is_another_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calibration, truth, prediction = _payloads()
    prediction["cases"][0]["selectedSource"] = {
        "sourceChecksumSha256": "d" * 64,
        "sourceId": "reels_test/source-2.jpg",
    }
    truth["sourceObservations"].append(
        _source_observation(
            "reels_test/source-2.jpg",
            "d" * 64,
            range_start=10,
            range_end=18,
            top=False,
            bottom=False,
        )
    )
    _configure_runner(monkeypatch, calibration=calibration, truth=truth, prediction=prediction)
    monkeypatch.setattr(
        runner,
        "_holdout_source_identities",
        lambda _manifest, *, holdout_case_id: {
            "reels_test/source-1.jpg": (
                holdout_case_id,
                runner.V7CorpusSplit.HOLDOUT,
                SOURCE_CHECKSUM,
            ),
            "reels_test/source-2.jpg": (
                holdout_case_id,
                runner.V7CorpusSplit.HOLDOUT,
                "d" * 64,
            ),
        },
    )

    report = _evaluate()

    assert report["acceptance"]["incorrectAutomaticRangeCount"] == 1
    assert report["acceptance"]["rangeRecovery"]["numerator"] == 0


def test_evaluator_uses_selected_source_crop_truth_not_case_truth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calibration, truth, prediction = _payloads()
    truth["cases"][0]["acceptableRepresentativeSources"].append(
        {
            "sourceChecksumSha256": "d" * 64,
            "sourceId": "reels_test/source-2.jpg",
        }
    )
    truth["sourceObservations"] = [
        _source_observation(top=False, bottom=False),
        _source_observation("reels_test/source-2.jpg", "d" * 64, top=True, bottom=False),
    ]
    _configure_runner(monkeypatch, calibration=calibration, truth=truth, prediction=prediction)
    monkeypatch.setattr(
        runner,
        "_holdout_source_identities",
        lambda _manifest, *, holdout_case_id: {
            "reels_test/source-1.jpg": (
                holdout_case_id,
                runner.V7CorpusSplit.HOLDOUT,
                SOURCE_CHECKSUM,
            ),
            "reels_test/source-2.jpg": (
                holdout_case_id,
                runner.V7CorpusSplit.HOLDOUT,
                "d" * 64,
            ),
        },
    )

    full_report = _evaluate()
    prediction["cases"][0]["selectedSource"] = {
        "sourceChecksumSha256": "d" * 64,
        "sourceId": "reels_test/source-2.jpg",
    }
    prediction["cases"][0]["topWarning"] = False
    cropped_report = _evaluate()

    assert full_report["acceptance"]["topCropRecall"]["denominator"] == 0
    assert cropped_report["acceptance"]["topCropRecall"] == {
        "denominator": 1,
        "minimumPercent": 100,
        "numerator": 0,
        "percentage": 0.0,
        "status": "failed",
    }


def test_evaluator_rejects_manual_outcome_labels_in_raw_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calibration, truth, prediction = _payloads()
    prediction["cases"][0]["rangeOutcome"] = "correct"
    _configure_runner(monkeypatch, calibration=calibration, truth=truth, prediction=prediction)

    with pytest.raises(ValueError, match="raw observations"):
        _evaluate()


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda calibration, _truth, _prediction: calibration["geometry"].update(
                {"status": "failed"}
            ),
            "not a passed calibration",
        ),
        (
            lambda _calibration, truth, _prediction: truth.update(
                {"manifestFingerprint": "e" * 64}
            ),
            "manifest fingerprint differs",
        ),
        (
            lambda _calibration, truth, _prediction: truth["cases"][0].update(
                {"split": "validation"}
            ),
            "truth case is invalid",
        ),
        (
            lambda _calibration, _truth, prediction: prediction["cases"][0][
                "selectedSource"
            ].update(
                {"sourceChecksumSha256": "f" * 64}
            ),
            "prediction source identity or checksum drifted",
        ),
        (
            lambda _calibration, truth, _prediction: truth["cases"][0][
                "acceptableRepresentativeSources"
            ][0].update({"sourceChecksumSha256": "f" * 64}),
            "truth source identity or checksum drifted",
        ),
    ],
)
def test_evaluator_rejects_calibration_fingerprint_split_and_source_drift(
    monkeypatch: pytest.MonkeyPatch,
    mutation: object,
    message: str,
) -> None:
    calibration, truth, prediction = _payloads()
    mutation(calibration, truth, prediction)  # type: ignore[operator]
    _configure_runner(monkeypatch, calibration=calibration, truth=truth, prediction=prediction)

    with pytest.raises(ValueError, match=message):
        _evaluate()


def test_evaluator_rejects_frozen_inventory_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    calibration, truth, prediction = _payloads()
    _configure_runner(monkeypatch, calibration=calibration, truth=truth, prediction=prediction)
    monkeypatch.setattr(runner, "_frozen_inventory", lambda _path: ("f" * 64, ()))

    with pytest.raises(ValueError, match="manifest or inventory drifted"):
        _evaluate()


def test_evaluator_rechecks_inventory_after_source_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    calibration, truth, prediction = _payloads()
    _configure_runner(monkeypatch, calibration=calibration, truth=truth, prediction=prediction)
    manifest = _ChangingManifest()
    monkeypatch.setattr(runner, "load_v7_corpus_manifest", lambda _path: manifest)

    with pytest.raises(ValueError, match="changed while source identities"):
        _evaluate()


class _MemoryReportPath:
    def __init__(self) -> None:
        self.content: bytes | None = None

    @property
    def parent(self) -> _MemoryReportPath:
        return self

    def exists(self) -> bool:
        return self.content is not None

    def read_bytes(self) -> bytes:
        assert self.content is not None
        return self.content

    def mkdir(self, *, parents: bool, exist_ok: bool) -> None:
        assert parents and exist_ok

    def open(self, mode: str) -> _MemoryReportWriter:
        assert mode == "xb"
        if self.content is not None:
            raise FileExistsError
        return _MemoryReportWriter(self)


class _MemoryReportWriter:
    def __init__(self, target: _MemoryReportPath) -> None:
        self.target = target

    def __enter__(self) -> _MemoryReportWriter:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def write(self, content: bytes) -> int:
        self.target.content = content
        return len(content)


def test_report_write_is_idempotent_and_never_overwrites_different_result() -> None:
    target = _MemoryReportPath()
    runner._write_once(target, {"schemaVersion": 1})
    runner._write_once(target, {"schemaVersion": 1})

    with pytest.raises(ValueError, match="already exists"):
        runner._write_once(target, {"schemaVersion": 2})
