"""Build baseline-versus-local-mesh cards for the rejected v7 sequences."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, cast

import cv2
import numpy as np
from numpy.typing import NDArray

ROOT = Path(__file__).resolve().parents[1]
WORKER_SOURCE = ROOT / "services" / "worker" / "src"
sys.path.insert(0, str(WORKER_SOURCE))

from game_predictor_worker.images.cell_crop_quality import (  # noqa: E402
    QUALITY_GATE_VERSION,
    CellCropQuality,
    assess_cell_crop,
)
from game_predictor_worker.images.symbol_mesh import (  # noqa: E402
    HISTORICAL_CENTERED_MESH_VERSION,
    MESH_VERSION,
    build_historical_centered_symbol_mesh_v4,
    build_symbol_mesh,
)

DEFAULT_MANIFEST = ROOT / "ai_docs" / "quality" / "m5-corpus-manifest.json"
DEFAULT_FEEDBACK = ROOT / "ai_docs" / "quality" / "m5-v7-owner-visual-feedback.json"
DEFAULT_FRAME_REPORT = (
    ROOT / "ai_docs" / "quality" / "m5-board-cell-crops-v10-wide-frame-preflight-report.json"
)
DEFAULT_V7_REPORT = (
    ROOT / "ai_docs" / "quality" / "m5-board-cell-crops-v7-reviewed-symbol-aware-report.json"
)
DEFAULT_CROP_ROOT = ROOT / "artifacts" / "m5-board-crops"
DEFAULT_OUTPUT_ROOT = ROOT / "artifacts" / "m5-symbol-extrapolated-mesh-v8-review"


class MeshGalleryError(ValueError):
    pass


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise MeshGalleryError(f"{label} must be an object.")
    return cast(Mapping[str, object], value)


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise MeshGalleryError(f"{label} must be an array.")
    return cast(Sequence[object], value)


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise MeshGalleryError(f"{label} must be an integer.")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise MeshGalleryError(f"{label} must be text.")
    return value


def _load_json(path: Path) -> Mapping[str, object]:
    try:
        value: Any = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise MeshGalleryError(f"Cannot read {path}.") from error
    return _mapping(value, path.name)


def _safe_path(root: Path, value: object, namespace: str) -> Path:
    relative = PurePosixPath(_text(value, "relativePath"))
    if relative.is_absolute() or not relative.parts or relative.parts[0] != namespace:
        raise MeshGalleryError("Artifact path is outside the expected namespace.")
    path = (root / Path(*relative.parts)).resolve(strict=True)
    if not path.is_relative_to(root):
        raise MeshGalleryError("Artifact path escapes its root.")
    return path


def _decode(path: Path) -> NDArray[np.uint8]:
    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if bgr is None:
        raise MeshGalleryError(f"Cannot decode {path}.")
    return cast(NDArray[np.uint8], cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))


def _encode(rgb: NDArray[np.uint8]) -> bytes:
    encoded, buffer = cv2.imencode(
        ".png",
        cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR),
        [cv2.IMWRITE_PNG_COMPRESSION, 6],
    )
    if not encoded:
        raise MeshGalleryError("Cannot encode gallery card.")
    return bytes(buffer)


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


def _cell_sheet(
    cells: Sequence[NDArray[np.uint8]],
    qualities: Sequence[CellCropQuality] | None = None,
) -> NDArray[np.uint8]:
    rendered: list[NDArray[np.uint8]] = []
    colours = {
        "eligible": (40, 220, 100),
        "clipped": (245, 70, 60),
        "occluded": (190, 90, 245),
        "interface_contaminated": (255, 155, 45),
        "uncertain": (245, 215, 55),
    }
    abbreviations = {
        "eligible": "OK",
        "clipped": "CLIP",
        "occluded": "OCC",
        "interface_contaminated": "UI",
        "uncertain": "?",
    }
    for index, cell in enumerate(cells):
        image = cell.copy()
        if qualities is not None:
            quality = qualities[index]
            colour = colours[quality.status]
            cv2.rectangle(image, (1, 1), (88, 88), colour, 3, cv2.LINE_AA)
            cv2.putText(
                image,
                abbreviations[quality.status],
                (5, 17),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                colour,
                1,
                cv2.LINE_AA,
            )
        rendered.append(image)
    rows = [np.concatenate(rendered[row * 5 : (row + 1) * 5], axis=1) for row in range(3)]
    sheet = cast(NDArray[np.uint8], np.concatenate(rows, axis=0))
    return cast(
        NDArray[np.uint8],
        cv2.resize(sheet, (500, 300), interpolation=cv2.INTER_NEAREST),
    )


def _card(
    baseline: NDArray[np.uint8],
    frame: NDArray[np.uint8],
    mesh_overlay: NDArray[np.uint8],
    mesh_cells: NDArray[np.uint8],
    *,
    baseline_label: str,
    sequence_number: int,
) -> bytes:
    panels = [baseline, frame, mesh_overlay, mesh_cells]
    header = np.full((42, 2000, 3), (7, 14, 22), dtype=np.uint8)
    labels = [
        f"seq {sequence_number} | {baseline_label}",
        "expanded complete frame",
        "local symbol mesh",
        "90x90 mesh crops",
    ]
    for index, label in enumerate(labels):
        cv2.putText(
            header,
            label,
            (index * 500 + 12, 27),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            (235, 247, 255),
            1,
            cv2.LINE_AA,
        )
    return _encode(
        cast(
            NDArray[np.uint8],
            np.concatenate((header, np.concatenate(panels, axis=1)), axis=0),
        )
    )


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--feedback", type=Path, default=DEFAULT_FEEDBACK)
    parser.add_argument("--frame-report", type=Path, default=DEFAULT_FRAME_REPORT)
    parser.add_argument("--v7-report", type=Path, default=DEFAULT_V7_REPORT)
    parser.add_argument("--crop-root", type=Path, default=DEFAULT_CROP_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--report-output",
        type=Path,
        help="Optional second location for the deterministic JSON report.",
    )
    parser.add_argument(
        "--all-sequences",
        action="store_true",
        help="Build review cards for the complete manifest instead of owner-rejected v7 cases.",
    )
    parser.add_argument(
        "--assess-quality",
        action="store_true",
        help="Run the deterministic per-cell training eligibility gate.",
    )
    parser.add_argument(
        "--mesh-mode",
        choices=("current", "historical-v4"),
        default="current",
        help="Select the current candidate or reproduce the owner-reviewed v4 crops.",
    )
    return parser.parse_args()


def main() -> int:
    args = _args()
    try:
        manifest = _load_json(args.manifest)
        feedback = _load_json(args.feedback)
        frame_report = _load_json(args.frame_report)
        v7 = _load_json(args.v7_report)
        crop_root = args.crop_root.resolve(strict=True)
        output_root = args.output_root.resolve()
        manifest_images = list(_sequence(manifest.get("images"), "manifest.images"))
        sequence_numbers: list[object] = (
            [
                sequence_number
                for raw in manifest_images
                for image in [_mapping(raw, "manifest.image")]
                for sequence_number in range(
                    _integer(
                        image.get("expectedSequenceStart"),
                        "expectedSequenceStart",
                    ),
                    _integer(
                        image.get("expectedSequenceEnd"),
                        "expectedSequenceEnd",
                    )
                    + 1,
                )
            ]
            if args.all_sequences
            else list(
                _sequence(
                    feedback.get("listedSequenceNumbers"),
                    "feedback.listedSequenceNumbers",
                )
            )
        )
        frame_namespace = _text(frame_report.get("cropperVersion"), "cropperVersion")
        build_mesh = (
            build_historical_centered_symbol_mesh_v4
            if args.mesh_mode == "historical-v4"
            else build_symbol_mesh
        )
        mesh_version = (
            HISTORICAL_CENTERED_MESH_VERSION if args.mesh_mode == "historical-v4" else MESH_VERSION
        )
        frame_by_source = {
            _text(image.get("sourceChecksumSha256"), "sourceChecksumSha256"): image
            for raw in _sequence(frame_report.get("images"), "frameReport.images")
            for image in [_mapping(raw, "frameReport.image")]
        }
        v7_by_source = {
            _text(image.get("sourceChecksumSha256"), "sourceChecksumSha256"): image
            for raw in _sequence(v7.get("images"), "v7.images")
            for image in [_mapping(raw, "v7.image")]
        }
        entries: list[dict[str, object]] = []
        for raw_sequence in sequence_numbers:
            sequence_number = _integer(raw_sequence, "sequenceNumber")
            image = next(
                _mapping(raw, "manifest.image")
                for raw in manifest_images
                if _integer(
                    _mapping(raw, "manifest.image").get("expectedSequenceStart"),
                    "expectedSequenceStart",
                )
                <= sequence_number
                <= _integer(
                    _mapping(raw, "manifest.image").get("expectedSequenceEnd"),
                    "expectedSequenceEnd",
                )
            )
            source = _text(image.get("sha256"), "manifest.sha256")
            position = sequence_number - _integer(
                image.get("expectedSequenceStart"),
                "expectedSequenceStart",
            )
            frame_image = _mapping(frame_by_source[source], "frameReport.image")
            v7_image = _mapping(v7_by_source[source], "v7.image")
            frame_board = next(
                _mapping(raw, "frameReport.board")
                for raw in _sequence(frame_image.get("boards"), "frameReport.boards")
                if _integer(
                    _mapping(raw, "frameReport.board").get("positionIndex"),
                    "positionIndex",
                )
                == position
            )
            v7_board = next(
                _mapping(raw, "v7.board")
                for raw in _sequence(v7_image.get("boards"), "v7.boards")
                if _integer(
                    _mapping(raw, "v7.board").get("positionIndex"),
                    "positionIndex",
                )
                == position
            )
            frame = _decode(
                _safe_path(
                    crop_root,
                    frame_board.get("boardRelativePath"),
                    frame_namespace,
                )
            )
            mesh = build_mesh(frame)
            if mesh.status != "meshed":
                entries.append(
                    {
                        "fallbackReason": mesh.fallback_reason,
                        "sequenceNumber": sequence_number,
                        "status": "fallback",
                    }
                )
                continue
            qualities = (
                [
                    assess_cell_crop(
                        cell.rgb,
                        expected_center_x=(
                            (cell.center_x - cell.left)
                            / (cell.right - cell.left)
                            * cell.rgb.shape[1]
                        ),
                        expected_center_y=(
                            (cell.center_y - cell.top)
                            / (cell.bottom - cell.top)
                            * cell.rgb.shape[0]
                        ),
                        center_confidence=mesh.raw_centers[index].confidence,
                        edge_column=cell.column_index in (0, 4),
                    )
                    for index, cell in enumerate(mesh.cells)
                ]
                if args.assess_quality
                else None
            )
            content = _card(
                _decode(
                    _safe_path(
                        crop_root,
                        v7_board.get("overlayRelativePath"),
                        "board-cell-crops-v7-reviewed-symbol-aware-affine-v1",
                    )
                ),
                frame,
                mesh.overlay_rgb,
                _cell_sheet(
                    [cell.rgb for cell in mesh.cells],
                    qualities,
                ),
                baseline_label=("v7 baseline" if args.all_sequences else "rejected v7"),
                sequence_number=sequence_number,
            )
            relative = f"cards/seq-{sequence_number:03d}.png"
            _write_atomic(output_root / Path(*PurePosixPath(relative).parts), content)
            entry: dict[str, object] = {
                "cardChecksumSha256": hashlib.sha256(content).hexdigest(),
                "cardRelativePath": relative,
                "columnCenterSource": mesh.column_center_source,
                "reliableCenterCount": mesh.reliable_center_count,
                "sequenceNumber": sequence_number,
                "status": "meshed",
            }
            if qualities is not None:
                entry["cellQualities"] = [
                    {
                        "columnIndex": mesh.cells[index].column_index,
                        **quality.to_dict(),
                        "rowIndex": mesh.cells[index].row_index,
                    }
                    for index, quality in enumerate(qualities)
                ]
            entries.append(entry)
        cards = [entry for entry in entries if entry.get("status") == "meshed"]
        body = "".join(
            f"<article><h2>Seq {entry['sequenceNumber']}</h2>"
            f'<img src="{html.escape(cast(str, entry["cardRelativePath"]))}" '
            f'alt="Porównanie sekwencji {entry["sequenceNumber"]}"></article>'
            for entry in cards
        )
        heading = (
            f"Pełny korpus: v7 vs {mesh_version}"
            if args.all_sequences
            else f"Odrzucone wycinki vs {mesh_version}"
        )
        page = (
            "<!doctype html><html lang='pl'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>M5 {mesh_version}</title><style>"
            "body{margin:24px;background:#07111b;color:#edf7ff;font-family:system-ui}"
            "article{margin:24px 0;background:#0c1b27;border:1px solid #1e4055;"
            "border-radius:12px;overflow:hidden}h2{padding:0 16px}img{width:100%;display:block}"
            f"</style></head><body><h1>{heading}</h1>"
            f"<p>Wersja: {mesh_version}. Karty: {len(cards)}/{len(entries)}.</p>"
            f"{body}</body></html>"
        ).encode()
        _write_atomic(output_root / "index.html", page)
        report = {
            "entries": entries,
            "fallbackCount": len(entries) - len(cards),
            "meshVersion": mesh_version,
            "meshedCount": len(cards),
            "schemaVersion": 1,
            "scope": "full_corpus" if args.all_sequences else "rejected_v7_sequences",
            "status": "waiting_for_owner_review",
        }
        if args.assess_quality:
            quality_counts = {
                status: sum(
                    1
                    for entry in entries
                    for cell in cast(
                        Sequence[Mapping[str, object]],
                        entry.get("cellQualities", ()),
                    )
                    if cell.get("status") == status
                )
                for status in (
                    "eligible",
                    "clipped",
                    "occluded",
                    "interface_contaminated",
                    "uncertain",
                )
            }
            report["qualityCounts"] = quality_counts
            report["qualityGateVersion"] = QUALITY_GATE_VERSION
            report["quarantinedCellCount"] = (
                sum(quality_counts.values()) - quality_counts["eligible"]
            )
            report["trainingEligibleCellCount"] = quality_counts["eligible"]
        report_bytes = (
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode()
        _write_atomic(output_root / "gallery.json", report_bytes)
        if args.report_output is not None:
            _write_atomic(args.report_output.resolve(), report_bytes)
        print(
            json.dumps(
                {
                    "fallbackCount": report["fallbackCount"],
                    "meshedCount": report["meshedCount"],
                    "output": str((output_root / "index.html").resolve()),
                    "reportOutput": (
                        str(args.report_output.resolve())
                        if args.report_output is not None
                        else None
                    ),
                    "sha256": hashlib.sha256(report_bytes).hexdigest(),
                },
                sort_keys=True,
            )
        )
        return 0
    except (MeshGalleryError, OSError, json.JSONDecodeError, StopIteration) as error:
        print(
            json.dumps(
                {"message": str(error), "status": "failed"},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
