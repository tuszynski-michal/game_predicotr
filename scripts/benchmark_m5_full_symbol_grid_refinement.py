"""Measure symbol-aware guards on every board without materializing crops."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, cast

import cv2
import numpy as np
from numpy.typing import NDArray

ROOT = Path(__file__).resolve().parents[1]
WORKER_SOURCE = ROOT / "services" / "worker" / "src"
sys.path.insert(0, str(WORKER_SOURCE))

from game_predictor_worker.images.local_grid_calibration import (  # noqa: E402
    LocalImageGridCalibrationProfiles,
)
from game_predictor_worker.images.rectification import (  # noqa: E402
    page_geometry_from_report,
)
from game_predictor_worker.images.symbol_grid_refinement import (  # noqa: E402
    REFINER_VERSION,
    refine_symbol_grid,
)

REPORT_VERSION = "m5-full-symbol-grid-refinement-benchmark-v1"
DEFAULT_NORMALIZATION_REPORT = ROOT / "ai_docs" / "quality" / "m5-normalization-report.json"
DEFAULT_DETECTION_REPORT = ROOT / "ai_docs" / "quality" / "m5-page-board-detection-report.json"
DEFAULT_MANIFEST = ROOT / "ai_docs" / "quality" / "m5-corpus-manifest.json"
DEFAULT_PROFILES = ROOT / "ai_docs" / "quality" / "m5-complete-local-grid-profiles.json"
DEFAULT_NORMALIZATION_ROOT = ROOT / "artifacts" / "m5-normalization"
DEFAULT_OUTPUT = ROOT / "ai_docs" / "quality" / "m5-full-symbol-grid-refinement-report.json"


class FullBenchmarkError(ValueError):
    """Stable full-corpus benchmark error."""


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise FullBenchmarkError(f"{label} must be an object.")
    return cast(Mapping[str, object], value)


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise FullBenchmarkError(f"{label} must be an array.")
    return cast(Sequence[object], value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise FullBenchmarkError(f"{label} must be non-empty text.")
    return value


def _load_json(path: Path, label: str) -> tuple[bytes, Mapping[str, object]]:
    try:
        content = path.read_bytes()
        value: Any = json.loads(content)
    except (OSError, json.JSONDecodeError) as error:
        raise FullBenchmarkError(f"{label} cannot be read.") from error
    return content, _mapping(value, label)


def _safe_normalized_path(root: Path, value: object) -> Path:
    relative = PurePosixPath(_text(value, "normalizedRelativePath"))
    if (
        relative.is_absolute()
        or not relative.parts
        or relative.parts[0] != "image-normalization-v1"
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise FullBenchmarkError("Normalized path leaves its namespace.")
    root = root.resolve(strict=True)
    path = (root / Path(*relative.parts)).resolve(strict=True)
    if not path.is_relative_to(root):
        raise FullBenchmarkError("Normalized path leaves its root.")
    return path


def _decode_rgb(path: Path) -> NDArray[np.uint8]:
    content = path.read_bytes()
    bgr = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_COLOR)
    if bgr is None:
        raise FullBenchmarkError("Normalized image cannot be decoded.")
    return cast(NDArray[np.uint8], cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))


def _numbers(
    entries: Sequence[Mapping[str, object]],
    field: str,
) -> list[float]:
    return [
        float(value)
        for entry in entries
        if isinstance(value := entry.get(field), int | float) and not isinstance(value, bool)
    ]


def _metric(values: Sequence[float], percentile: float) -> float | None:
    return None if not values else round(float(np.percentile(values, percentile)), 4)


def build_report(
    *,
    normalization_report_path: Path,
    detection_report_path: Path,
    manifest_path: Path,
    profiles_path: Path,
    normalization_root: Path,
    geometry_source: str,
) -> dict[str, object]:
    normalization_bytes, normalization = _load_json(
        normalization_report_path,
        "normalizationReport",
    )
    detection_bytes, detection = _load_json(detection_report_path, "detectionReport")
    profiles_bytes = profiles_path.read_bytes()
    profiles = LocalImageGridCalibrationProfiles.from_files(
        profiles_path,
        manifest_path,
    )
    normalized_by_source = {
        _text(item.get("sourceChecksumSha256"), "sourceChecksumSha256"): item
        for raw in _sequence(normalization.get("images"), "normalization.images")
        for item in [_mapping(raw, "normalization.image")]
    }
    entries: list[dict[str, object]] = []
    for detection_index, raw in enumerate(
        _sequence(detection.get("detections"), "detection.detections")
    ):
        item = _mapping(raw, f"detection.detections[{detection_index}]")
        source = _text(item.get("sourceChecksumSha256"), "sourceChecksumSha256")
        normalized = normalized_by_source.get(source)
        if normalized is None:
            raise FullBenchmarkError("Detection source is missing normalization.")
        path = _safe_normalized_path(
            normalization_root,
            normalized.get("normalizedRelativePath"),
        )
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != normalized.get("normalizedChecksumSha256"):
            raise FullBenchmarkError("Normalized image checksum drift.")
        rgb = _decode_rgb(path)
        geometry = page_geometry_from_report(
            _mapping(item.get("result"), "detection.result"),
            f"detection.detections[{detection_index}].result",
        )
        selected_geometry = (
            profiles.calibrate(source, geometry) if geometry_source == "calibrated" else geometry
        )
        if selected_geometry.status != "detected":
            raise FullBenchmarkError("Complete profiles did not calibrate a source.")
        for board in selected_geometry.boards:
            result = refine_symbol_grid(rgb, board.quad)
            value = result.to_dict()
            value.update(
                {
                    "boardPosition": board.position_index,
                    "calibrationProfileId": board.calibration_profile_id,
                    "sourceImageChecksumSha256": source,
                }
            )
            entries.append(value)
    fallbacks = [entry for entry in entries if entry["status"] == "fallback"]
    reasons = Counter(_text(entry.get("fallbackReason"), "fallbackReason") for entry in fallbacks)
    refined = [entry for entry in entries if entry["status"] == "refined"]
    return {
        "detectionReportSha256": hashlib.sha256(detection_bytes).hexdigest(),
        "entries": entries,
        "normalizationReportSha256": hashlib.sha256(normalization_bytes).hexdigest(),
        "profileSetSha256": hashlib.sha256(profiles_bytes).hexdigest(),
        "geometrySource": geometry_source,
        "refinerVersion": REFINER_VERSION,
        "reportVersion": REPORT_VERSION,
        "status": "ready" if not fallbacks else "needs_tuning",
        "summary": {
            "baselineMedianResidualPx": _metric(
                _numbers(entries, "baselineMedianResidualPx"),
                50.0,
            ),
            "boardCount": len(entries),
            "fallbackCount": len(fallbacks),
            "fallbackReasons": dict(sorted(reasons.items())),
            "maxCornerShiftP95Px": _metric(
                _numbers(entries, "maxCornerShiftPx"),
                95.0,
            ),
            "refinedCount": len(refined),
            "refinedMedianResidualPx": _metric(
                _numbers(refined, "refinedMedianResidualPx"),
                50.0,
            ),
            "refinedP95ResidualP95Px": _metric(
                _numbers(refined, "refinedP95ResidualPx"),
                95.0,
            ),
        },
        "trainingAllowed": False,
    }


def _json_bytes(value: Mapping[str, object]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _write_atomic(path: Path, content: bytes) -> None:
    if path.exists() and path.read_bytes() == content:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--normalization-report",
        type=Path,
        default=DEFAULT_NORMALIZATION_REPORT,
    )
    parser.add_argument(
        "--detection-report",
        type=Path,
        default=DEFAULT_DETECTION_REPORT,
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--profiles", type=Path, default=DEFAULT_PROFILES)
    parser.add_argument(
        "--normalization-root",
        type=Path,
        default=DEFAULT_NORMALIZATION_ROOT,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--geometry-source",
        choices=("calibrated", "detector"),
        default="calibrated",
    )
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _args()
    try:
        report = build_report(
            normalization_report_path=args.normalization_report,
            detection_report_path=args.detection_report,
            manifest_path=args.manifest,
            profiles_path=args.profiles,
            normalization_root=args.normalization_root,
            geometry_source=args.geometry_source,
        )
        content = _json_bytes(report)
        if args.check:
            if not args.output.exists() or args.output.read_bytes() != content:
                raise FullBenchmarkError("Full benchmark report is missing or stale.")
        else:
            _write_atomic(args.output, content)
        print(
            json.dumps(
                {
                    "output": str(args.output.resolve()),
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "status": report["status"],
                    "summary": report["summary"],
                },
                sort_keys=True,
            )
        )
        return 0
    except (FullBenchmarkError, OSError, json.JSONDecodeError) as error:
        print(
            json.dumps({"code": "FULL_SYMBOL_GRID_BENCHMARK_FAILED", "message": str(error)}),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
