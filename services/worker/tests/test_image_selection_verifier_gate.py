from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _load_gate_module():
    script = (
        Path(__file__).resolve().parents[3] / "scripts" / "run_image_selection_verifier_gate.py"
    )
    spec = spec_from_file_location("run_image_selection_verifier_gate", script)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _report(*, seconds: float, checksum: str = "a" * 64) -> dict[str, object]:
    return {
        "source": {
            "manifestSha256": "b" * 64,
            "analyzedImageCount": 200,
            "firstOrderIndex": 0,
            "lastOrderIndex": 199,
        },
        "selector": {"version": "fast-image-selector-v10.2", "fingerprint": "c" * 64},
        "summary": {"totalSeconds": seconds},
        "groups": [
            {
                "group": 1,
                "sourceCount": 20,
                "firstSourceIndex": 0,
                "lastSourceIndex": 19,
                "status": "auto_selected",
                "recognizedRange": "1-9",
                "selectedChecksumSha256": checksum,
                "selectedSourceRelativePath": "images/001.jpg",
                "topCandidates": [{"checksumSha256": checksum}],
            }
        ],
    }


def test_gate_activates_two_verifiers_only_for_identical_faster_result() -> None:
    gate = _load_gate_module()

    evaluation = gate.evaluate_reports(
        _report(seconds=100),
        _report(seconds=80),
        minimum_improvement_percent=10,
    )

    assert evaluation["canonicalDecisionMatch"] is True
    assert evaluation["dualImprovementPercent"] == 20
    assert evaluation["decision"] == "activate_two_verifiers"


def test_gate_keeps_one_verifier_when_representative_changes() -> None:
    gate = _load_gate_module()

    evaluation = gate.evaluate_reports(
        _report(seconds=100),
        _report(seconds=70, checksum="d" * 64),
        minimum_improvement_percent=10,
    )

    assert evaluation["canonicalDecisionMatch"] is False
    assert evaluation["decision"] == "keep_one_verifier"


def test_gate_keeps_one_verifier_when_gain_is_too_small() -> None:
    gate = _load_gate_module()

    evaluation = gate.evaluate_reports(
        _report(seconds=100),
        _report(seconds=95),
        minimum_improvement_percent=10,
    )

    assert evaluation["canonicalDecisionMatch"] is True
    assert evaluation["decision"] == "keep_one_verifier"
