"""File-only T3 replay and lossless production rasters for the comparison CLI."""

from __future__ import annotations

import hashlib
import json
import re
from functools import partial
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np
from game_predictor_api.domain.canonical_source import rgb_pixel_checksum_sha256
from game_predictor_api.domain.grid_training_cohorts import digest
from PIL import Image

from ..filesystem import long_path_aware
from .comparison_production_crop_report import _content
from .grid_cohort_dataset import GridBoardDataset, GridCohortSnapshot, has_full_geometry
from .production_cell_evaluation import reference_context, render_cells
from .production_cell_run import ProductionContentRun
from .virtual_cell_extraction import VirtualCellRender

INDEX_VERSION = "grid-comparison-production-cells-index-v1"
_METADATA_LIMIT = 1024 * 1024
_DETAIL_LIMIT = 96 * 1024 * 1024


def _inside(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative:
        raise ValueError("CONTENT_COMPARISON_PATH_INVALID")
    value = PurePosixPath(relative)
    if value.is_absolute() or ".." in value.parts or str(value) != relative:
        raise ValueError("CONTENT_COMPARISON_PATH_INVALID")
    path = root.joinpath(*value.parts)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("CONTENT_COMPARISON_PATH_OUTSIDE_REPORT")
    for candidate in (path, *path.parents):
        if candidate == root.parent:
            break
        if candidate.is_symlink() or candidate.is_junction():
            raise ValueError("CONTENT_COMPARISON_LINKED_PATH")
    return long_path_aware(path)


def _read(root: Path, relative: str, limit: int, sha: str | None = None) -> Any:
    with _inside(root, relative).open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("CONTENT_COMPARISON_SIZE_LIMIT")
    if sha is not None and (
        re.fullmatch(r"[0-9a-f]{64}", sha) is None or hashlib.sha256(raw).hexdigest() != sha
    ):
        raise ValueError("CONTENT_COMPARISON_CHECKSUM_MISMATCH")
    return json.loads(raw)


def _write_output(root: Path, relative: str, raw: bytes) -> Path:
    """Create a file once; reuse only identical bytes without touching an existing file."""
    path = _inside(root, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(raw)
    except FileExistsError:
        with path.open("rb") as stream:
            previous = stream.read(len(raw) + 1)
        if previous != raw:
            raise ValueError("CONTENT_COMPARISON_OUTPUT_CONFLICT") from None
    return path


def _png(root: Path, relative: str, rgb: Any, expected: str) -> dict[str, Any]:
    # The normalized-pixel checksum deliberately differs from the PNG-file hash.
    if rgb_pixel_checksum_sha256(rgb) != expected:
        raise ValueError("CONTENT_COMPARISON_PIXEL_MISMATCH")
    encoded = BytesIO()
    Image.fromarray(rgb).save(encoded, format="PNG")
    raw = encoded.getvalue()
    path = _write_output(root, relative, raw)
    with Image.open(path) as image:
        if image.mode != "RGB" or not np.array_equal(np.asarray(image), rgb):
            raise ValueError("CONTENT_COMPARISON_PNG_REPLAY_MISMATCH")
    return {
        "image": relative,
        "width": rgb.shape[1],
        "height": rgb.shape[0],
        "renderedPixelSha256": expected,
        "pngFileSha256": hashlib.sha256(raw).hexdigest(),
    }


def _unavailable(reason: str) -> dict[str, Any]:
    return {"state": "unavailable", "reason": reason}


def _neural_input(
    root: Path,
    frame: Any,
    source: Any,
    target: Any,
    proof: Any,
    game: str,
    name: str,
) -> dict[str, Any]:
    from uuid import UUID

    from ..geometry_core.preprocessing import crop_board
    from ..geometry_core.rescue import BoardCropGeometryV1, BoardCropGeometryV2
    from ..geometry_core.settings import BoardPreset
    from .production_cell_input import verify_input

    if proof is None:
        return _unavailable("Brak przypiętego dowodu rastra wejścia T3.")
    if proof.get("version") != "frozen-a-neural-input-content-v1":
        return _unavailable("Nieobsługiwana wersja dowodu wejścia T3.")
    verify_input(frame, source, target, proof, UUID(game))
    board = BoardPreset.model_validate(proof["boardPreset"])
    geometry = proof["geometry"]
    if geometry is not None:
        geometry = (
            BoardCropGeometryV2.model_validate(geometry)
            if "canvas" in geometry
            else BoardCropGeometryV1.model_validate(geometry)
        )
    pixels = crop_board(
        frame.rgb, np.asarray(proof["matrix"], np.float64), board, geometry=geometry
    )
    image = _png(
        root,
        f"production-cell-images/{source['sourceId']}/{target['positionIndex']}/{name}-input.png",
        pixels,
        proof["inputRasterSha256"],
    )
    return {
        "state": "available",
        **image,
        "rgbSha256": proof["inputRasterSha256"],
        "tensorShape": None,
        "tensorSha256": None,
        "margin": board.margin if geometry is None else geometry.margin,
        "sourceToInput": proof["matrix"],
        "schemaVersion": proof["version"],
        "proofSha256": proof["sha256"],
        "stageLabel": "wejście planszy — odtworzony raster T3",
        "rawUnavailable": "T3 utrwala raster RGB i jego sumę, bez zapisanego tensora/raw logits.",
        "humanReference": "pinned independent content15",
        "realSupport": proof["realSupport"],
        "inputContentStates": proof["inputContentStates"],
        "inputCropped": proof["inputCropped"],
        "routing": proof["routing"],
        "path": proof["path"],
        "geometry": proof["geometry"],
    }


def _save_cell(
    root: Path,
    prefix: str,
    expected: list[dict[str, Any]],
    assessments: list[Any],
    model: str,
    cells: dict[int, dict[str, Any]],
    rendered: VirtualCellRender,
) -> None:
    index = rendered.cell_index
    if index in cells or index not in range(15):
        raise ValueError("CONTENT_COMPARISON_CELL_INDEX")
    witness = expected[index]
    if (
        rendered.rendered_pixel_checksum_sha256 != witness["renderedPixelSha256"]
        or rendered.render_spec_checksum_sha256 != witness["renderSpecSha256"]
    ):
        raise ValueError("CONTENT_COMPARISON_RENDER_MISMATCH")
    image = _png(root, f"{prefix}/{index}.png", rendered.rgb, witness["renderedPixelSha256"])
    cells[index] = {
        "state": "available",
        "cellIndex": index,
        **image,
        **witness,
        "renderSpec": rendered.render_spec,
        "assessment": assessments[index].get(model),
        "contentState": assessments[index]["contentState"],
    }


class ComparisonProductionCells:
    """Retain at most one source's metadata; never load a model or write domain data."""

    def __init__(self, root: Path, evaluation: dict[str, Any]) -> None:
        self.root, self.evaluation = root.resolve(), evaluation
        self._key: tuple[str, str] | None = None
        self._photo: dict[str, Any] = {}

    def for_board(
        self,
        source: dict[str, Any],
        board: dict[str, Any],
        inference: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            key = digest(source), digest(inference)
            if self._key != key:
                self._photo = self._replay(source, inference)
                self._key = key
            photo = self._photo
            matches = [b for b in photo["boards"] if b["positionIndex"] == board["position_index"]]
            if len(matches) != 1 or type(board["position_index"]) is not int:
                raise ValueError("CONTENT_COMPARISON_SLOT_UNAVAILABLE")
            result = matches[0]
            if (
                type(board["sequence_number"]) is not int
                or result["sequenceNumber"] != board["sequence_number"]
                or (board["grid_rows"], board["grid_columns"]) != (3, 5)
                or photo["provenance"]["gameId"]
                != board.get("game_id", self.evaluation["trainingGameId"])
            ):
                raise ValueError("CONTENT_COMPARISON_TARGET_MISMATCH")
            return {"state": "available", **photo["provenance"], **result}
        except (OSError, ValueError, KeyError, TypeError, IndexError, StopIteration) as error:
            # Bad optional file evidence does not invalidate historical geometry views.
            return _unavailable(str(error))

    def _replay(self, source: dict[str, Any], inference: dict[str, Any]) -> dict[str, Any]:
        index = _read(self.root, "production-cells/index.json", _METADATA_LIMIT)
        if (
            not isinstance(index, dict)
            or set(index) != {"schemaVersion", "entries"}
            or index["schemaVersion"] != INDEX_VERSION
            or not isinstance(index["entries"], list)
            or len(index["entries"]) > 4096
            or any(not isinstance(e, dict) for e in index["entries"])
        ):
            raise ValueError("CONTENT_COMPARISON_INDEX_INVALID")
        matches = [e for e in index["entries"] if e.get("sourceId") == source["id"]]
        if len(matches) != 1:
            raise ValueError("CONTENT_COMPARISON_SOURCE_NOT_UNIQUE")
        entry = matches[0]
        if set(entry) != {"sourceId", "gameId", "role", "manifest", "detail"}:
            raise ValueError("CONTENT_COMPARISON_ENTRY_INVALID")
        role, game = entry["role"], entry["gameId"]
        if role not in ("VALIDATION", "REGRESSION"):
            raise ValueError("CONTENT_COMPARISON_ROLE_INVALID")
        report = self.evaluation["report"]
        if (
            report.get("schemaVersion") != "grid-model-evaluation-read-v6"
            or report["versionId"] != self.evaluation["versionId"]
            or report["baseVersionId"] != self.evaluation["baseVersionId"]
        ):
            raise ValueError("CONTENT_COMPARISON_T3_REPORT_REQUIRED")
        # Both immutable pins come from the saved evaluation, never the index alone.
        cohort = next(c for c in report["cohorts"] if c["gameId"] == game)
        game_report = next(g for g in report["games"] if g["gameId"] == game)
        raw = report["rawQuality"]
        raw_game = next(g for g in raw["games"] if g["gameId"] == game)
        if (
            entry["detail"] != game_report["roles"][role]["detail"]
            or entry["detail"] != raw_game["roles"][role]["detail"]
            or cohort != next(c for c in raw["cohorts"] if c["gameId"] == game)
            or raw["versionId"] != report["versionId"]
            or raw["baseVersionId"] != report["baseVersionId"]
            or entry["manifest"]["sha256"] != cohort["manifestSha256"]
            or set(entry["manifest"]) != {"path", "sha256"}
            or set(entry["detail"]) != {"path", "sha256"}
        ):
            raise ValueError("CONTENT_COMPARISON_EVALUATION_PIN_MISMATCH")
        _inside(self.root, entry["manifest"]["path"])
        snapshot = GridCohortSnapshot(
            self.root, entry["manifest"]["path"], entry["manifest"]["sha256"]
        )
        if (
            snapshot.manifest["gameId"] != game
            or snapshot.manifest["cohortId"] != cohort["cohortId"]
            or snapshot.manifest["base"]["versionId"] != self.evaluation["baseVersionId"]
        ):
            raise ValueError("CONTENT_COMPARISON_SNAPSHOT_MISMATCH")
        document = _read(
            self.root, entry["detail"]["path"], _DETAIL_LIMIT, entry["detail"]["sha256"]
        )
        if (
            document["schemaVersion"] != "grid-model-evaluation-detail-v1"
            or document["jobId"] != self.evaluation["evaluationId"]
            or document["gameId"] != game
            or document["cohortId"] != cohort["cohortId"]
            or document["role"] != role
        ):
            raise ValueError("CONTENT_COMPARISON_DETAIL_IDENTITY")
        records = [p for p in document["photos"] if p["sourceId"] == source["id"]]
        if len(records) != 1:
            raise ValueError("CONTENT_COMPARISON_DETAIL_SOURCE_NOT_UNIQUE")
        recorded = records[0]["contentEvaluation"]
        if (
            recorded["version"] != "production-cell-photo-v1"
            or recorded["sourceId"] != source["id"]
        ):
            raise ValueError("CONTENT_COMPARISON_PHOTO_VERSION")
        dataset = GridBoardDataset(snapshot, role) if role == "VALIDATION" else None
        if dataset is None:
            from .grid_cohort_dataset import GridAssessmentDataset

            dataset = GridAssessmentDataset(snapshot, role)
        selected = [(s, labels) for s, labels in dataset.indexed() if s["sourceId"] == source["id"]]
        if len(selected) != 1:
            raise ValueError("CONTENT_COMPARISON_SNAPSHOT_SOURCE_NOT_UNIQUE")
        frozen, labels = selected[0]
        identity = frozen["sourceIdentity"]
        if identity["checksum_sha256"] != source["checksum_sha256"] or (
            identity["oriented_width"],
            identity["oriented_height"],
        ) != (source["oriented_width"], source["oriented_height"]):
            raise ValueError("CONTENT_COMPARISON_SOURCE_IDENTITY")
        frame = snapshot.frame(frozen, role)
        self._verify(snapshot, frozen, labels, frame, recorded, records[0], role, inference)
        targets = sorted(frozen["targets"], key=lambda t: t["positionIndex"])
        boards = []
        for target, row in zip(targets, recorded["boards"], strict=True):
            models = {}
            context = reference_context(target)
            for name in ("base", "candidate"):
                match = row[name]
                prediction = match["matchedPrediction"]
                if match["matchAmbiguous"] or type(prediction) is not int or context is None:
                    models[name] = {
                        **_unavailable("Brak jednoznacznego przypisania T3 do tego slotu."),
                        "matchedPrediction": prediction,
                        "matchAmbiguous": match["matchAmbiguous"],
                    }
                    continue
                usable = [
                    d for d in recorded["models"][name]["detections"] if d["nodes"] is not None
                ]
                nodes = usable[prediction]["nodes"]
                expected = recorded["models"][name]["crops"][
                    prediction * 15 : (prediction + 1) * 15
                ]
                if len(expected) != 15:
                    raise ValueError("CONTENT_COMPARISON_CROP_COUNT")
                cells: dict[int, dict[str, Any]] = {}

                sink = partial(
                    _save_cell,
                    self.root,
                    f"production-cell-images/{source['id']}/{target['positionIndex']}/{name}",
                    expected,
                    row["cells"],
                    name,
                    cells,
                )
                try:
                    actual = render_cells(frame, nodes, target, context, raster_sink=sink)
                except ValueError:
                    # The strict full-photo T3 replay above has already verified
                    # this precise per-model failure witness. Keep its scope here.
                    invalid = [{"support": None, "reason": "CONTENT_PREDICTION_INVALID"}] * 15
                    if expected != invalid or cells:
                        raise
                    models[name] = {
                        **_unavailable("CONTENT_PREDICTION_INVALID"),
                        "matchedPrediction": prediction,
                        "matchAmbiguous": False,
                    }
                    continue
                if actual != expected:
                    raise ValueError("CONTENT_COMPARISON_RENDER_CHANGED")
                models[name] = {
                    "state": "available",
                    "nodes": nodes,
                    "matchedPrediction": prediction,
                    "matchAmbiguous": False,
                    "neuralInput": _neural_input(
                        self.root,
                        frame,
                        frozen,
                        target,
                        match["inputEvidence"],
                        game,
                        name,
                    ),
                    "cells": [
                        cells.get(i, {"cellIndex": i, **_unavailable(expected[i]["reason"])})
                        for i in range(15)
                    ],
                }
            boards.append(
                {
                    "positionIndex": target["positionIndex"],
                    "sequenceNumber": target["sequenceNumber"],
                    "referenceNodes": target["nodes"],
                    "humanReference": _content(target, identity, game),
                    "contentReferenceSha256": target.get("contentReferenceSha256"),
                    "contentReferenceRevision": target.get("contentReferenceRevision"),
                    "renderContext": context,
                    "models": models,
                }
            )
        return {
            "boards": boards,
            "provenance": {
                "schemaVersion": recorded["version"],
                "sourceId": recorded["sourceId"],
                "gameId": game,
                "role": role,
                "manifest": entry["manifest"],
                "detail": entry["detail"],
                "referenceSha256": recorded["referenceSha256"],
                "reasonCodes": recorded["reasonCodes"],
                "original": _png(
                    self.root,
                    f"production-cell-images/{source['id']}/source.png",
                    frame.rgb,
                    frame.pixel_checksum_sha256,
                ),
            },
        }

    @staticmethod
    def _verify(
        snapshot: Any,
        source: Any,
        labels: Any,
        frame: Any,
        recorded: Any,
        row: Any,
        role: str,
        inference: Any,
    ) -> None:
        from types import SimpleNamespace

        from ..training_core.grid_correction_metrics import CorrectionControlPhoto, evaluate_photo
        from ..training_core.grid_evaluation import predictions
        from .production_cell_evaluation import ProductionContentObserver
        from .production_cell_input import verify_input

        boards = {b["positionIndex"]: b for b in recorded["boards"]}

        def read_input(
            frame: Any, source: Any, target: Any, detection: Any, engine: Any, game: Any
        ) -> Any:
            proof = boards[target["positionIndex"]][engine]["inputEvidence"]
            if proof is not None and proof["screenQuad"] != detection.screen_quad.tolist():
                raise ValueError("CONTENT_COMPARISON_INPUT_DETECTION_CHANGED")
            return verify_input(frame, source, target, proof, game)

        observer = ProductionContentObserver(
            snapshot, role, u=ProductionContentRun(snapshot).u, input_reader=read_input
        )
        photo = CorrectionControlPhoto(
            source["sourceId"],
            row["groupId"],
            source["original"]["sha256"],
            tuple(n for n, _ in labels),
            lambda: frame.rgb,
            full_geometry=has_full_geometry(source),
        )
        observed = {}
        for name in ("base", "candidate"):
            saved = recorded["models"][name]["detections"]
            if [d["nodes"] for d in saved] != [d["nodes"] for d in inference[name]["detections"]]:
                raise ValueError("CONTENT_COMPARISON_INFERENCE_CHANGED")
            found = [
                SimpleNamespace(
                    nodes=None if d["nodes"] is None else np.asarray(d["nodes"], np.float64),
                    screen_quad=np.asarray(d["screenQuad"], np.float64),
                )
                for d in saved
            ]
            result = evaluate_photo(
                photo.source_id,
                photo.group_id,
                list(photo.labels),
                predictions(found),
                full_geometry=photo.full_geometry,
            )
            if result.as_dict() != row[name]:
                raise ValueError("CONTENT_COMPARISON_METRICS_CHANGED")
            observed[name] = found, result, name
        if observer(photo, frame.rgb, observed) != recorded:
            raise ValueError("CONTENT_COMPARISON_T3_REPLAY_CHANGED")
