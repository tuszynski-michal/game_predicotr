"""File-only TRAIN projection of a sealed margin diagnostic; never run models or SQL."""

from __future__ import annotations

import hashlib
import json
import math
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import UUID

import numpy as np
from game_predictor_api.domain.grid_cell_content import ContentRevision
from game_predictor_api.domain.grid_training_cohorts import digest
from PIL import Image

from ..geometry_core.input_diagnostics import InputStage, array_sha256
from .normalization import CanonicalSourceLoader, rgb_pixel_checksum_sha256
from .production_crop_artifacts import checked, read_json, safe_path, write_bytes, write_json

MAX_IMAGE_BYTES = 64 * 1024 * 1024
MAX_IMAGE_PIXELS = 32 * 1024 * 1024


def _missing(reason: str) -> dict[str, Any]:
    return {"state": "unavailable", "reason": reason}


def _points(raw: Any, count: int = 24) -> list[list[float]]:
    if not isinstance(raw, list) or len(raw) != count:
        raise ValueError("CROP_HTML_POINTS_UNAVAILABLE")
    points = [[p["x"], p["y"]] if isinstance(p, dict) else list(p) for p in raw]
    if any(
        len(p) != 2
        or any(
            type(v) not in (int, float) or (type(v) is float and not math.isfinite(v)) for v in p
        )
        for p in points
    ):
        raise ValueError("CROP_HTML_POINTS_INVALID")
    return points


def _asset_bytes(root: Path, pin: dict[str, Any]) -> bytes:
    path = safe_path(root, pin["path"])
    if type(pin["bytes"]) is not int or not 0 < pin["bytes"] <= MAX_IMAGE_BYTES:
        raise ValueError("CROP_HTML_IMAGE_LIMIT")
    if path.stat().st_size != pin["bytes"]:
        raise ValueError("CROP_HTML_IMAGE_SIZE_CHANGED")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != pin["sha256"]:
        raise ValueError("CROP_HTML_IMAGE_CHANGED")
    return raw


def _publish(output: Path, relative: str, raw: bytes, rgb: Any) -> dict[str, Any]:
    try:
        pin = write_bytes(output, relative, raw)
    except ValueError as error:
        # A conflicting output is not a missing input image; abort publication.
        raise RuntimeError("CROP_HTML_OUTPUT_CONFLICT") from error
    return {
        "state": "available",
        "image": pin["path"],
        "fileSha256": pin["sha256"],
        "pixelSha256": rgb_pixel_checksum_sha256(rgb),
        "width": rgb.shape[1],
        "height": rgb.shape[0],
    }


def _original(artifacts: Path, output: Path, source: dict[str, Any], name: str) -> dict[str, Any]:
    try:
        pin, identity = source["original"], source["sourceIdentity"]
        if pin["sha256"] != identity["checksum_sha256"]:
            raise ValueError("CROP_HTML_SOURCE_PIN_CHANGED")
        _asset_bytes(artifacts, pin)
        frame = CanonicalSourceLoader(max_source_pixels=MAX_IMAGE_PIXELS).load(
            safe_path(artifacts, pin["path"]), expected_source_checksum_sha256=pin["sha256"]
        )
        if frame.pixel_checksum_sha256 != identity["normalized_pixel_checksum_sha256"] or (
            frame.source.width,
            frame.source.height,
        ) != (identity["oriented_width"], identity["oriented_height"]):
            raise ValueError("CROP_HTML_SOURCE_PIXELS_CHANGED")
        stream = BytesIO()
        Image.fromarray(frame.rgb).save(stream, format="PNG")
    except (OSError, ValueError, KeyError, TypeError) as error:
        return _missing(
            "CROP_HTML_SOURCE_UNAVAILABLE" if isinstance(error, OSError) else str(error)
        )
    return _publish(output, name, stream.getvalue(), frame.rgb)


def _png(
    root: Path,
    output: Path,
    pin: dict[str, Any],
    name: str,
    *,
    witness: dict[str, Any] | None = None,
    expected_size: tuple[int, int] | None = None,
) -> dict[str, Any]:
    try:
        raw = _asset_bytes(root, pin)
        with Image.open(BytesIO(raw)) as image:
            if (
                image.format != "PNG"
                or image.mode != "RGB"
                or image.width * image.height > MAX_IMAGE_PIXELS
            ):
                raise ValueError("CROP_HTML_RGB_PNG_REQUIRED")
            rgb = np.asarray(image).copy()
        if rgb_pixel_checksum_sha256(rgb) != pin["pixelSha256"]:
            raise ValueError("CROP_HTML_RASTER_PIXELS_CHANGED")
        if expected_size is not None and (rgb.shape[1], rgb.shape[0]) != expected_size:
            raise ValueError("CROP_HTML_RENDER_SIZE_CHANGED")
        if witness is not None:
            stage = InputStage.model_validate(witness["input"])
            sample = rgb.transpose(2, 0, 1).astype("<f4")
            if (
                (stage.width, stage.height) != (rgb.shape[1], rgb.shape[0])
                or stage.rgb_sha256 != array_sha256(rgb)
                or stage.tensor_sha256 != array_sha256(sample)
                or witness["observedSampleTensorSha256"] != array_sha256(sample)
                or tuple(stage.tensor_shape)
                != ((1, *sample.shape) if stage.tensor_layout == "NCHW" else sample.shape)
            ):
                raise ValueError("CROP_HTML_INPUT_WITNESS_CHANGED")
    except (OSError, ValueError, KeyError, TypeError) as error:
        return _missing(str(error))
    return _publish(output, name, raw, rgb)


def _content(target: dict[str, Any], identity: dict[str, Any], game: str) -> dict[str, Any]:
    if target.get("contentAnnotation") is None:
        return _missing("CONTENT_APPROVED_REFERENCE_MISSING")
    try:
        annotation = ContentRevision.model_validate(target["contentAnnotation"])
        if (
            annotation.sha256 != target["contentReferenceSha256"]
            or not annotation.reference.humanApproved
            or str(annotation.reference.gameId) != game
            or annotation.reference.positionIndex != target["positionIndex"]
            or annotation.sequenceNumber != target["sequenceNumber"]
            or annotation.source.sourceRepresentativeSha256
            != identity["normalized_pixel_checksum_sha256"]
            or (annotation.source.width, annotation.source.height)
            != (identity["oriented_width"], identity["oriented_height"])
        ):
            raise ValueError("CONTENT_REFERENCE_IDENTITY_CONFLICT")
    except (ValueError, KeyError, TypeError) as error:
        return _missing(str(error))
    return {
        "state": "available",
        "revision": annotation.reference.revision,
        "sha256": annotation.sha256,
        "origin": annotation.origin,
        "approvedBy": annotation.approvedBy,
        "cells": [c.model_dump(mode="json") for c in annotation.reference.cells],
    }


def _neural_inputs(
    root: Path, output: Path, photo: dict[str, Any], identity: dict[str, Any], name: str
) -> dict[str, Any]:
    proof = photo.get("neuralInput", {})
    if proof.get("state") not in ("available", "partial"):
        return _missing(proof.get("reason", "CROP_ACTUAL_INPUT_UNAVAILABLE"))
    try:
        checked(proof, "production-crop-input-witness-v1")
        if (
            proof["sourceId"] != photo["sourceId"]
            or proof["sourcePixelSha256"] != identity["normalized_pixel_checksum_sha256"]
            or digest(proof["context"]) != proof["contextSha256"]
            or len(proof["entries"]) > 4096
        ):
            raise ValueError("CROP_HTML_INPUT_SOURCE_CHANGED")
        indices = [(e["stage"], e["predictionIndex"]) for e in proof["entries"]]
        if len(indices) != len(set(indices)) or any(
            stage not in ("screen", "board") or type(i) is not int or i < 0 for stage, i in indices
        ):
            raise ValueError("CROP_HTML_INPUT_INDEX_INVALID")
    except (KeyError, ValueError, TypeError) as error:
        return _missing(str(error))
    entries = []
    for entry in proof["entries"]:
        asset = _png(
            root,
            output,
            entry,
            f"inputs/{name}-{entry['stage']}-{entry['predictionIndex']}.png",
            witness=entry,
        )
        entries.append(
            {
                **asset,
                "stage": entry["stage"],
                "originalPredictionIndex": entry["predictionIndex"],
                "input": entry["input"],
                "observedSampleTensorSha256": entry["observedSampleTensorSha256"],
            }
        )
    return {
        "state": proof["state"],
        "reason": proof.get("reason"),
        "entries": entries,
        "context": proof["context"],
        "unavailablePredictionIndices": proof["unavailablePredictionIndices"],
        "unavailableScreenStages": proof["unavailableScreenStages"],
    }


def _geometry(
    root: Path,
    output: Path,
    photo: dict[str, Any],
    target: dict[str, Any],
    identity: dict[str, Any],
    kind: str,
    name: str,
    label_index: int,
) -> dict[str, Any]:
    pair = photo.get("geometry", {}).get(kind, {})
    cells: list[dict[str, Any]] = [
        {
            "cellIndex": i,
            "base": _missing("CROP_PAIR_UNAVAILABLE"),
            "candidate": _missing("CROP_PAIR_UNAVAILABLE"),
            "contentState": "unknown",
            "classification": None,
        }
        for i in range(15)
    ]
    result: dict[str, Any] = {
        "state": pair.get("state", "unavailable"),
        "cells": cells,
        "gate": pair.get("gate"),
        "nodes": None,
        "labReference": pair.get("labRgb", {}).get("reference"),
        "geometryMetrics": {
            key: pair.get("geometryMetrics", {}).get(key)
            for key in (
                "full_geometry",
                "expected",
                "predicted",
                "matched",
                "correct",
                "false_boards",
                "duplicates",
                "complete_correct",
                "complete_correct_strict",
                "normalized_error",
            )
        },
        "boardMatches": {},
    }
    if pair.get("state") != "available":
        result["reasonCodes"] = pair.get("reasonCodes", ["CROP_PAIR_UNAVAILABLE"])
        return result
    observed = pair["observation"]
    boards = [b for b in observed["boards"] if b["positionIndex"] == target["positionIndex"]]
    if observed["sourceId"] != photo["sourceId"] or len(boards) != 1:
        return {**result, "state": "unavailable", "reasonCodes": ["CROP_HTML_BOARD_NOT_UNIQUE"]}
    board = boards[0]
    for variant in ("base", "candidate"):
        observed_match = board.get(variant, {})
        matches = [
            match
            for match in pair.get("geometryMetrics", {}).get("matches", [])
            if match.get("label") == label_index
            and match.get("prediction") == observed_match.get("matchedPrediction")
        ]
        result["boardMatches"][variant] = (
            {key: matches[0].get(key) for key in ("valid", "correct", "iou", "nme", "max_error")}
            if len(matches) == 1 and observed_match.get("matchAmbiguous") is False
            else None
        )
    classes = [
        c
        for c in pair.get("classification", [])
        if c["positionIndex"] == target["positionIndex"]
        and c["sequenceNumber"] == target["sequenceNumber"]
    ]
    for index, cell in enumerate(cells):
        assessments = [c for c in board["cells"] if c["cellIndex"] == index]
        assessment = assessments[0] if len(assessments) == 1 else {}
        cell["contentState"] = assessment.get("contentState", "unknown")
        truths = [c for c in classes if c["cellIndex"] == index]
        if len(truths) == 1:
            truth = truths[0]
            captured_classes = target.get("classes", [])
            captured = captured_classes[index] if len(captured_classes) == 15 else {}
            reference = truth.get("classReference", {})
            class_pin_matches = captured.get("state") == reference.get("state") and all(
                captured.get(k) == reference.get(k)
                for k in ("code", "renderedPixelSha256", "event")
            )
            cell["classification"] = (
                {
                    key: truth.get(key)
                    for key in (
                        "state",
                        "reason",
                        "acceptanceState",
                        "classReference",
                        "base",
                        "candidate",
                        "baseCorrect",
                        "candidateCorrect",
                        "baseFalseAccept",
                        "candidateFalseAccept",
                    )
                }
                if class_pin_matches
                else _missing("CROP_HTML_CLASS_REFERENCE_UNAVAILABLE")
            )
        for variant in ("base", "candidate"):
            try:
                match = board[variant]
                p = match["matchedPrediction"]
                if match["matchAmbiguous"] or type(p) is not int or p < 0:
                    raise ValueError("CROP_HTML_MATCH_UNAVAILABLE")
                # Both keys below use the usable-detection index. They are never
                # interpreted as neural-input original-found indices.
                detections = pair["observation"]["models"][variant]["detections"]
                usable = [d for d in detections if d["nodes"] is not None]
                nodes = _points(usable[p]["nodes"])
                if variant == "base":
                    result["nodes"] = nodes
                candidates = [
                    r
                    for r in pair["rasters"]
                    if r["variant"] == variant
                    and r["predictionIndex"] == p
                    and r["cellIndex"] == index
                ]
                if len(candidates) != 1:
                    raise ValueError("CROP_HTML_RASTER_NOT_UNIQUE")
                pin = candidates[0]
                spec = pin["renderSpec"]
                row, col = divmod(index, 5)
                expected_quad = [
                    nodes[row * 6 + col],
                    nodes[row * 6 + col + 1],
                    nodes[(row + 1) * 6 + col + 1],
                    nodes[(row + 1) * 6 + col],
                ]
                if (
                    digest(spec) != pin["renderSpecSha256"]
                    or spec["cellIndex"] != index
                    or spec["boardSlot"] != target["positionIndex"]
                    or spec["sourceChecksumSha256"] != identity["checksum_sha256"]
                    or spec["normalizedPixelChecksumSha256"]
                    != identity["normalized_pixel_checksum_sha256"]
                    or spec["configuration"] != pair["configurations"][variant]
                    or spec["configuration"]["paddingFraction"]
                    != (0.08 if variant == "base" else 0.0)
                    or _points(spec["sourceQuad"], 4) != expected_quad
                ):
                    raise ValueError("CROP_HTML_RENDER_PIN_CHANGED")
                footprint = spec["paddedSourceQuad"]
                _points(footprint, 4)
                asset = _png(
                    root,
                    output,
                    pin,
                    f"cells/{name}-{kind}-{target['positionIndex']}-{variant}-{index}.png",
                    expected_size=(
                        spec["configuration"]["outputWidth"],
                        spec["configuration"]["outputHeight"],
                    ),
                )
                cell[variant] = {
                    **asset,
                    "assessment": assessment.get(variant),
                    "usablePredictionIndex": p,
                    "renderSpecSha256": pin["renderSpecSha256"],
                    "configuration": spec["configuration"],
                    "quad": footprint,
                }
            except (ValueError, KeyError, TypeError, IndexError) as error:
                cell[variant] = _missing(str(error))
    return result


def render_crop_report(report_path: Path, *, output: Path, artifact_root: Path) -> Path:
    """Produce an immutable standalone visual projection; all pixels are opt-in TRAIN."""
    root = report_path.absolute().parent
    report = read_json(root, report_path.name)
    capture = read_json(root, "capture.json")
    checked(report, "production-crop-comparison-v1")
    checked(capture, "production-crop-capture-v1")
    if (
        report["captureSha256"] != capture["sha256"]
        or report.get("diagnosticOnly") is not True
        or report.get("qualificationAllowed") is not False
        or capture.get("diagnosticOnly") is not True
        or capture.get("qualificationAllowed") is not False
        or report.get("variantNames") != {"base": "legacy08", "candidate": "legacy00"}
        or report.get("accessScope") != "internal-diagnostic-metadata"
        or report.get("visualExportRule") != "TRAIN-and-visualExportAllowed-only"
    ):
        raise ValueError("CROP_HTML_DIAGNOSTIC_REPORT_REQUIRED")
    if len(report["photos"]) > 50 or len(capture["photos"]) > 50:
        raise ValueError("CROP_HTML_SOURCE_LIMIT")
    if output.resolve().is_relative_to(root.resolve()) or root.resolve().is_relative_to(
        output.resolve()
    ):
        raise ValueError("CROP_HTML_SEPARATE_OUTPUT_REQUIRED")
    if (
        output.exists()
        and any(output.iterdir())
        and not (output / "crop-comparison-data.json").is_file()
    ):
        raise ValueError("CROP_HTML_NEW_OUTPUT_REQUIRED")
    output.mkdir(parents=True, exist_ok=True)
    photos = []
    omitted_train = 0
    seen: set[str] = set()
    for photo in report["photos"]:
        # Never let A metadata enter public JSON, even when an A pin contains paths.
        if photo.get("role") != "TRAIN" or photo.get("visualExportAllowed") is not True:
            omitted_train += photo.get("role") == "TRAIN"
            continue
        if photo.get("state") != "available":
            omitted_train += 1
            continue
        name = str(UUID(photo["sourceId"]))
        if name in seen:
            raise ValueError("CROP_HTML_SOURCE_NOT_UNIQUE")
        seen.add(name)
        members = [p for p in capture["photos"] if p["sourceId"] == photo["sourceId"]]
        if (
            len(members) != 1
            or members[0]["role"] != "TRAIN"
            or members[0]["state"] != "available"
            or photo["state"] != "available"
        ):
            raise ValueError("CROP_HTML_TRAIN_MEMBERSHIP_REQUIRED")
        member = members[0]
        source = member["frozenSource"]
        if source["sourceId"] != photo["sourceId"] or source["role"] != "TRAIN":
            raise ValueError("CROP_HTML_SOURCE_PIN_CHANGED")
        identity = source["sourceIdentity"]
        if (
            str(identity["id"]) != photo["sourceId"]
            or str(identity["game_id"]) != capture["gameId"]
        ):
            raise ValueError("CROP_HTML_SOURCE_PIN_CHANGED")
        positions = [t["positionIndex"] for t in member["targets"]]
        if (
            not 1 <= len(positions) <= 9
            or len(set(positions)) != len(positions)
            or any(type(p) is not int or not 0 <= p < 9 for p in positions)
        ):
            raise ValueError("CROP_HTML_TARGETS_INVALID")
        if any(
            type(t.get("sequenceNumber")) is not int or t["sequenceNumber"] < 1
            for t in member["targets"]
        ):
            raise ValueError("CROP_HTML_SEQUENCE_UNRESOLVED")
        original = _original(artifact_root, output, source, f"originals/{name}.png")
        boards = []
        for target in sorted(member["targets"], key=lambda t: t["positionIndex"]):
            # The producer's match.label is the original target ordinal, not positionIndex.
            label_index = next(i for i, item in enumerate(member["targets"]) if item is target)
            try:
                nodes = _points(target["nodes"])
            except (ValueError, KeyError, TypeError):
                nodes = None
            boards.append(
                {
                    "positionIndex": target["positionIndex"],
                    "sequenceNumber": target["sequenceNumber"],
                    "nodes": nodes,
                    "content": _content(target, identity, capture["gameId"]),
                    "geometry": {
                        kind: _geometry(
                            root, output, photo, target, identity, kind, name, label_index
                        )
                        for kind in ("human", "model")
                    },
                }
            )
        photos.append(
            {
                "sourceId": name,
                "role": "TRAIN",
                "visualExportAllowed": True,
                "width": identity["oriented_width"],
                "height": identity["oriented_height"],
                "original": original,
                "boards": boards,
                "neuralInput": _neural_inputs(root, output, photo, identity, name),
                "measurementQualificationState": photo.get("measurementQualificationState"),
                "measurementUse": photo.get("measurementUse"),
            }
        )
    public = {
        "schemaVersion": "production-crop-html-v1",
        "reportSha256": report["sha256"],
        "captureSha256": capture["sha256"],
        "diagnosticOnly": True,
        "qualificationAllowed": False,
        "omittedTrainSources": omitted_train,
        "photos": photos,
    }
    write_json(output, "crop-comparison-data.json", public)
    template = (
        Path(__file__).resolve().parents[5] / "scripts/templates/production-crop-comparison.html"
    ).read_text(encoding="utf-8")
    encoded = (
        json.dumps(public, ensure_ascii=False, allow_nan=False)
        .replace("<", "\\u003c")
        .replace("&", "\\u0026")
    )
    raw = template.replace("__CROP_DATA__", encoded).encode("utf-8")
    write_bytes(output, "index.html", raw)
    return output / "index.html"
