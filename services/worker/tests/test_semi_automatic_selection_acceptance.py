from __future__ import annotations

import importlib.util
import sys
from io import BytesIO
from pathlib import Path

import numpy as np
from game_predictor_worker.semi_automatic_selection.range_only_ocr import (
    RangeOnlyLabelEvidence,
    RangeOnlyRecognition,
)
from PIL import Image

_SCRIPT = Path(__file__).parents[3] / "scripts" / "run_semi_automatic_selection_acceptance.py"
_SPEC = importlib.util.spec_from_file_location("semi_automatic_acceptance", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


class _Recognizer:
    version = "acceptance-test-v1"
    fingerprint = "a" * 64

    def __init__(self) -> None:
        self.calls = 0

    def recognize(
        self, _rgb_image: np.ndarray[tuple[int, ...], np.dtype[np.uint8]]
    ) -> RangeOnlyRecognition:
        start = self.calls * 9 + 1
        self.calls += 1
        return RangeOnlyRecognition(
            observed_range=_MODULE.SemiAutomaticSelectionRange(start, start + 8),
            confidence=0.99,
            has_strong_local_proof=True,
            reason_codes=("RANGE_OCR_LABEL_LATTICE_THREE_ADJACENT",),
            label_evidence=tuple(
                RangeOnlyLabelEvidence(position, start + position, 0.99, "test")
                for position in (0, 1, 4)
            ),
        )


def _jpeg() -> bytes:
    output = BytesIO()
    Image.new("RGB", (12, 12), (20, 30, 40)).save(output, format="JPEG")
    return output.getvalue()


def test_acceptance_uses_seq_names_as_read_only_oracle_and_range_only_counts(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    content = _jpeg()
    for index in range(10):
        start = index * 9 + 1
        (source / f"seq_{start}-{start + 8}.jpg").write_bytes(content)

    recognizer = _Recognizer()
    report = _MODULE.run_acceptance(source_root=source, sample_size=10, recognizer=recognizer)

    assert recognizer.calls == 10
    assert report["contract"] == "semi-automatic-selection-acceptance-v2"
    assert report["falseAssignments"] == 0
    assert report["exactMatches"] == 10
    assert report["gatePassed"] is True
    assert report["ocrCalls"] == 10
    assert report["overlappingAssignments"] == 0
    assert report["rejectedRawHypotheses"] == 0
    assert len(str(report["sourceManifestSha256"])) == 64
    assert report["geometryCalls"] == 0
    assert report["cropperCalls"] == 0
    assert report["symbolInferenceCalls"] == 0
    assert all(path.read_bytes() == content for path in source.iterdir())


def test_api_package_does_not_construct_the_asgi_app_for_domain_imports() -> None:
    sys.modules.pop("game_predictor_api.main", None)
    import game_predictor_api

    assert "game_predictor_api.main" not in sys.modules
    assert callable(game_predictor_api.create_app)
