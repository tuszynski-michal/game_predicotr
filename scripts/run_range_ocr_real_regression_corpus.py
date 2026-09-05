"""Audit historical range OCR runtimes on real, redacted user fixtures.

This is a read-only diagnostic tool. It loads each JPEG through the production
EXIF canonicalizer, production localizer and real Paddle recognition model. It
does not create jobs, staging records, outputs, geometry, board crops or symbol
inference. Human labels are an oracle for the report only; the source filename
is neutral and is never parsed for a range.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from uuid import NAMESPACE_URL, uuid5

from PIL import Image

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "services" / "worker" / "src"))

from game_predictor_worker.semi_automatic_selection.contracts import (  # type: ignore[import-untyped]  # noqa: E402
    RangeEvidenceResult,
    SemiAutomaticSelectionSource,
    SemiAutomaticSequenceBounds,
)
from game_predictor_worker.semi_automatic_selection.middle_row_locator import (  # type: ignore[import-untyped]  # noqa: E402
    MiddleRowTripleLocator,
)
from game_predictor_worker.semi_automatic_selection.middle_row_range import (  # type: ignore[import-untyped]  # noqa: E402
    ExpectedRangeTable,
)
from game_predictor_worker.semi_automatic_selection.middle_row_runtime import (  # type: ignore[import-untyped]  # noqa: E402
    MiddleRowBatchRuntime,
    MiddleRowRunOrientation,
    MiddleRowSourcePayload,
    build_middle_row_paddle_adapter,
)
from game_predictor_worker.semi_automatic_selection.range_only_ocr import (  # type: ignore[import-untyped]  # noqa: E402
    RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V2,
    RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V3,
    RangeOnlyOcrAdapter,
    build_paddle_range_only_recognizer_for_contract,
)
from game_predictor_worker.semi_automatic_selection.range_proof_v5 import (  # type: ignore[import-untyped]  # noqa: E402
    RowExpectedRangeTable,
)
from game_predictor_worker.semi_automatic_selection.row_first_locator_v5 import (  # type: ignore[import-untyped]  # noqa: E402
    RowFirstTripleLocator,
)
from game_predictor_worker.semi_automatic_selection.row_first_runtime_v5 import (  # type: ignore[import-untyped]  # noqa: E402
    RowFirstBatchRuntime,
    RowFirstSourcePayload,
)

_CORPUS_ROOT = REPOSITORY_ROOT / "services" / "worker" / "tests" / "fixtures" / "range_ocr_real_v6"
_MANIFEST = _CORPUS_ROOT / "manifest.json"


@dataclass(frozen=True, slots=True)
class CorpusCase:
    relative_path: str
    checksum_sha256: str
    human_label: Mapping[str, object]

    @property
    def expected_bounds(self) -> SemiAutomaticSequenceBounds:
        if self.human_label["kind"] == "readable_exact":
            value = self.human_label["expectedRange"]
            assert isinstance(value, list) and len(value) == 2
            return SemiAutomaticSequenceBounds(int(value[0]), int(value[1]))
        visible = self.human_label["visibleRanges"]
        assert isinstance(visible, list) and len(visible) == 2
        first = visible[0]
        last = visible[1]
        assert isinstance(first, list) and isinstance(last, list)
        return SemiAutomaticSequenceBounds(int(first[0]), int(last[1]))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_cases() -> tuple[CorpusCase, ...]:
    raw = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("contract") != "range-ocr-real-regression-corpus-v1":
        raise ValueError("The real range OCR corpus manifest is unsupported.")
    values = raw.get("cases")
    if not isinstance(values, list) or len(values) != 4:
        raise ValueError("The real range OCR corpus must contain exactly four cases.")
    result: list[CorpusCase] = []
    for item in values:
        if not isinstance(item, dict):
            raise ValueError("The real range OCR corpus item is invalid.")
        relative = item.get("relativePath")
        checksum = item.get("sha256")
        label = item.get("humanLabel")
        if (
            not isinstance(relative, str)
            or not isinstance(checksum, str)
            or not isinstance(label, dict)
            or "seq_" in relative.casefold()
        ):
            raise ValueError("The real range OCR corpus item is invalid.")
        path = _CORPUS_ROOT / relative
        if _sha256(path) != checksum:
            raise ValueError(f"The real range OCR fixture checksum differs: {relative}")
        result.append(CorpusCase(relative, checksum, label))
    return tuple(result)


def _source(case: CorpusCase, index: int) -> SemiAutomaticSelectionSource:
    path = _CORPUS_ROOT / case.relative_path
    return SemiAutomaticSelectionSource(
        source_index=index,
        relative_path=case.relative_path,
        size_bytes=path.stat().st_size,
        checksum_sha256=case.checksum_sha256,
    )


def _result_payload(result: RangeEvidenceResult) -> dict[str, object]:
    return {
        "confidence": result.confidence,
        "observedRange": (
            None
            if result.observed_range is None
            else [result.observed_range.start, result.observed_range.end]
        ),
        "reasonCodes": list(result.reason_codes),
        "status": result.status.value,
    }


def _legacy_result(
    *,
    fingerprint: str,
    source: SemiAutomaticSelectionSource,
    content: bytes,
    bounds: SemiAutomaticSequenceBounds,
    model_root: Path,
) -> RangeEvidenceResult:
    recognizer = build_paddle_range_only_recognizer_for_contract(model_root, fingerprint)
    return RangeOnlyOcrAdapter(bounds=bounds, recognizer=recognizer).recognize(
        source=source,
        rgb_image=_canonical_rgb(content),
    )


def _canonical_rgb(content: bytes) -> Image.Image:
    from game_predictor_worker.semi_automatic_selection.middle_row_locator import (
        canonicalize_source_image,
    )

    return cast(Image.Image, canonicalize_source_image(content).rgb)


def _middle_row_result(
    *,
    source: SemiAutomaticSelectionSource,
    content: bytes,
    bounds: SemiAutomaticSequenceBounds,
    model_root: Path,
) -> RangeEvidenceResult:
    runtime = MiddleRowBatchRuntime(
        run_id=uuid5(NAMESPACE_URL, f"range-ocr-real-v4:{source.checksum_sha256}"),
        expected_ranges=ExpectedRangeTable.from_bounds(bounds),
        rotation=MiddleRowRunOrientation.DEG_0,
        locator=MiddleRowTripleLocator(),
        recognizer=build_middle_row_paddle_adapter(model_root),
    )
    return runtime.process_batch((MiddleRowSourcePayload(source=source, content=content),))[0]


def _row_first_result(
    *,
    source: SemiAutomaticSelectionSource,
    content: bytes,
    bounds: SemiAutomaticSequenceBounds,
    model_root: Path,
) -> RangeEvidenceResult:
    runtime = RowFirstBatchRuntime(
        run_id=uuid5(NAMESPACE_URL, f"range-ocr-real-v5:{source.checksum_sha256}"),
        expected_ranges=RowExpectedRangeTable.from_bounds(bounds),
        locator=RowFirstTripleLocator(),
        recognizer=build_middle_row_paddle_adapter(model_root),
    )
    return runtime.process_batch((RowFirstSourcePayload(source=source, content=content),))[0]


def run_audit(*, model_root: Path, cases: Sequence[CorpusCase]) -> dict[str, object]:
    result: list[dict[str, object]] = []
    for index, case in enumerate(cases):
        source = _source(case, index)
        content = (_CORPUS_ROOT / case.relative_path).read_bytes()
        bounds = case.expected_bounds
        result.append(
            {
                "fixture": case.relative_path,
                "humanLabel": dict(case.human_label),
                "variants": {
                    "v2": _result_payload(
                        _legacy_result(
                            fingerprint=RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V2,
                            source=source,
                            content=content,
                            bounds=bounds,
                            model_root=model_root,
                        )
                    ),
                    "v3": _result_payload(
                        _legacy_result(
                            fingerprint=RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V3,
                            source=source,
                            content=content,
                            bounds=bounds,
                            model_root=model_root,
                        )
                    ),
                    "v4_1": _result_payload(
                        _middle_row_result(
                            source=source,
                            content=content,
                            bounds=bounds,
                            model_root=model_root,
                        )
                    ),
                    "v5": _result_payload(
                        _row_first_result(
                            source=source,
                            content=content,
                            bounds=bounds,
                            model_root=model_root,
                        )
                    ),
                },
            }
        )
    return {
        "contract": "range-ocr-real-regression-audit-v1",
        "corpusManifestSha256": _sha256(_MANIFEST),
        "note": "Read-only real OCR audit. Human labels are report oracles, never OCR input.",
        "results": result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ocr-model-root",
        type=Path,
        default=REPOSITORY_ROOT / "artifacts" / "m5-models" / "sequence-number-ocr-v1",
    )
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = args.report.resolve()
    if report.is_relative_to(_CORPUS_ROOT):
        raise ValueError("The read-only audit report cannot be written into the fixture corpus.")
    payload = run_audit(model_root=args.ocr_model_root.resolve(strict=True), cases=_load_cases())
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
