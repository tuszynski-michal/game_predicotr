"""Read-only evaluation of symbol proposals from operator-verified cells.

The command opens a READ ONLY database transaction, recreates checksum-bound
virtual crops from managed originals and writes reports only below the chosen
output directory. It never mutates domain data and never approves a cell.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import cv2
import numpy as np
import torch
from game_predictor_api.config import ApiSettings
from game_predictor_api.storage.database import create_database_engine
from game_predictor_worker.images.normalization import (
    CanonicalSourceLoader,
    CanonicalSourceLoadError,
    rgb_pixel_checksum_sha256,
)
from game_predictor_worker.images.symbol_model_benchmark import SpatialSymbolCnn
from game_predictor_worker.images.virtual_cell_extraction import (
    VirtualCellExtractionError,
    source_direct_warp_rgb,
)
from game_predictor_worker.symbols.reference_library import (
    CROP_SIZE,
    NEIGHBOUR_COUNT,
    REFERENCE_LIBRARY_VERSION,
    FloatArray,
    Proposal,
    combined_descriptor,
    decide,
    descriptor_matrix,
    gray_world,
    normalize_rows,
    vote,
)
from numpy.typing import NDArray
from PIL import Image, ImageDraw
from sqlalchemy import Connection, text

REPORT_VERSION = "symbol-reference-library-evaluation-v1"
REFERENCES_PER_GROUP = 15
CONTEXT_SIZE = 96
EXIT_INCOMPLETE = 3
_TRANSIENT_SOURCE_ERRORS = frozenset(
    {
        "IMAGE_CANONICAL_SOURCE_NOT_FOUND",
        "IMAGE_CANONICAL_SOURCE_PATH_INVALID",
        "IMAGE_SOURCE_UNREADABLE",
    }
)

_CELL_COLUMNS = """
    c.id::text AS id,
    c.import_job_id::text AS import_job_id,
    c.sequence_number AS sequence_number,
    c.cell_index AS cell_index,
    c.prediction_symbol_code AS prediction_symbol_code,
    c.prediction_confidence AS prediction_confidence,
    c.rendered_pixel_checksum_sha256 AS rendered_pixel_checksum_sha256,
    c.render_spec AS render_spec
"""

_REFERENCE_SQL = f"""
WITH eligible AS (
  SELECT {_CELL_COLUMNS},
         s.code AS label,
         row_number() OVER (
           PARTITION BY s.code, c.import_job_id, (c.prediction_symbol_code = s.code)
           ORDER BY md5(c.id::text), c.id
         ) AS group_rank
  FROM game_data_v2.image_symbol_review_cells c
  JOIN public.symbols s ON s.id = c.assigned_symbol_id
  WHERE c.game_id = :game_id
    AND c.review_state = 'approved'
    AND c.assignment_source = 'human'
    AND c.asset_mode = 'virtual_source'
    AND c.approved_asset_mode = 'virtual_source'
    AND c.source_available = true
    AND c.quality_issue IS NULL
    AND (c.source_visibility IS NULL OR c.source_visibility = 'full')
    AND c.render_spec IS NOT NULL
    AND c.approved_render_spec_checksum_sha256 = c.render_spec_checksum_sha256
    AND c.approved_rendered_pixel_checksum_sha256 = c.rendered_pixel_checksum_sha256
    AND s.status = 'active'
)
SELECT * FROM eligible WHERE group_rank <= :per_group ORDER BY id
"""

_PENDING_SQL = f"""
WITH eligible AS (
  SELECT {_CELL_COLUMNS},
         NULL::text AS label,
         row_number() OVER (
           PARTITION BY c.prediction_symbol_code, c.import_job_id
           ORDER BY md5(c.id::text), c.id
         ) AS import_rank
  FROM game_data_v2.image_symbol_review_cells c
  WHERE c.game_id = :game_id
    AND c.review_state = 'pending'
    AND c.asset_mode = 'virtual_source'
    AND c.source_available = true
    AND c.quality_issue IS NULL
    AND (c.source_visibility IS NULL OR c.source_visibility = 'full')
    AND c.render_spec IS NOT NULL
    AND c.prediction_symbol_code IS NOT NULL
    AND c.prediction_confidence >= :min_confidence
    AND c.prediction_confidence < :max_confidence
), ranked AS (
  SELECT *, row_number() OVER (
           PARTITION BY prediction_symbol_code
           ORDER BY import_rank, md5(id), id
         ) AS symbol_rank
  FROM eligible
)
SELECT * FROM ranked WHERE symbol_rank <= :per_symbol ORDER BY id
"""


class EvaluationError(RuntimeError):
    """Stable, operator-readable failure of the read-only evaluation."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True, slots=True)
class Cell:
    id: str
    import_job_id: str
    sequence_number: int
    cell_index: int
    prediction_symbol_code: str | None
    prediction_confidence: float | None
    rendered_pixel_checksum_sha256: str
    source_checksum_sha256: str
    padded_quad: tuple[tuple[float, float], ...]
    source_quad: tuple[tuple[float, float], ...]
    label: str | None


@dataclass(frozen=True, slots=True)
class ActiveModel:
    iteration_id: str
    checkpoint_path: Path
    checkpoint_sha256: str
    class_codes: tuple[str, ...]


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    evaluate = commands.add_parser("evaluate", help="Measure proposals and sample pending cells.")
    evaluate.add_argument("--game-code", required=True)
    evaluate.add_argument("--output-dir", required=True, type=Path)
    evaluate.add_argument("--artifact-root", type=Path)
    evaluate.add_argument("--min-confidence", type=float, default=0.6)
    evaluate.add_argument("--max-confidence", type=float, default=0.8)
    evaluate.add_argument("--pending-per-symbol", type=int, default=50, choices=range(1, 201))
    evaluate.add_argument("--time-budget-seconds", type=float, default=90.0)
    return parser.parse_args(argv)


def _quad(value: object, label: str) -> tuple[tuple[float, float], ...]:
    if not isinstance(value, list) or len(value) != 4:
        raise EvaluationError("SYMBOL_REFERENCE_RENDER_SPEC_INVALID", f"{label} is not a quad.")
    points: list[tuple[float, float]] = []
    for point in value:
        if not isinstance(point, Mapping):
            raise EvaluationError(
                "SYMBOL_REFERENCE_RENDER_SPEC_INVALID", f"{label} has an invalid point."
            )
        points.append((float(point["x"]), float(point["y"])))
    return tuple(points)


def _cell(row: Mapping[str, Any]) -> Cell:
    spec = row["render_spec"]
    if not isinstance(spec, Mapping):
        raise EvaluationError(
            "SYMBOL_REFERENCE_RENDER_SPEC_INVALID", f"Cell {row['id']} has no render spec."
        )
    configuration = spec.get("configuration")
    if (
        not isinstance(configuration, Mapping)
        or configuration.get("outputWidth") != CROP_SIZE
        or configuration.get("outputHeight") != CROP_SIZE
    ):
        raise EvaluationError(
            "SYMBOL_REFERENCE_RENDER_SPEC_INVALID",
            f"Cell {row['id']} does not describe a {CROP_SIZE} px crop.",
        )
    confidence = row["prediction_confidence"]
    try:
        return Cell(
            id=str(row["id"]),
            import_job_id=str(row["import_job_id"]),
            sequence_number=int(row["sequence_number"]),
            cell_index=int(row["cell_index"]),
            prediction_symbol_code=row["prediction_symbol_code"],
            prediction_confidence=None if confidence is None else float(confidence),
            rendered_pixel_checksum_sha256=str(row["rendered_pixel_checksum_sha256"]),
            source_checksum_sha256=str(spec["sourceChecksumSha256"]),
            padded_quad=_quad(spec.get("paddedSourceQuad"), "paddedSourceQuad"),
            source_quad=_quad(spec.get("sourceQuad"), "sourceQuad"),
            label=row["label"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise EvaluationError(
            "SYMBOL_REFERENCE_RENDER_SPEC_INVALID",
            f"Cell {row['id']} has an incomplete render spec.",
        ) from error


def _game(connection: Connection, game_code: str) -> tuple[str, str]:
    row = (
        connection.execute(
            text("SELECT id::text AS id, name FROM public.games WHERE code = :code"),
            {"code": game_code},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise EvaluationError("SYMBOL_REFERENCE_GAME_NOT_FOUND", f"Unknown game code {game_code}.")
    return str(row["id"]), str(row["name"])


def _active_model(connection: Connection, game_id: str, artifact_root: Path) -> ActiveModel:
    row = (
        connection.execute(
            text(
                """
                SELECT a.action, i.id::text AS iteration_id, i.checkpoint_relative_path,
                       i.checkpoint_checksum_sha256
                FROM game_data_v2.game_symbol_model_activations a
                LEFT JOIN game_data_v2.symbol_model_iterations i ON i.id = a.model_iteration_id
                WHERE a.game_id = :game_id
                ORDER BY a.activation_number DESC
                LIMIT 1
                """
            ),
            {"game_id": game_id},
        )
        .mappings()
        .one_or_none()
    )
    if row is None or row["action"] != "activate" or row["checkpoint_relative_path"] is None:
        raise EvaluationError(
            "SYMBOL_REFERENCE_ACTIVE_MODEL_MISSING",
            "The game has no active symbol model checkpoint.",
        )
    data_root = (artifact_root / "data").resolve()
    path = (data_root / str(row["checkpoint_relative_path"])).resolve()
    if not path.is_relative_to(data_root) or not path.is_file():
        raise EvaluationError(
            "SYMBOL_REFERENCE_CHECKPOINT_MISSING", "The active model checkpoint is not readable."
        )
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    if checksum != row["checkpoint_checksum_sha256"]:
        raise EvaluationError(
            "SYMBOL_REFERENCE_CHECKPOINT_DRIFT",
            "The active model checkpoint differs from its recorded checksum.",
        )
    payload: Any = torch.load(path, map_location="cpu", weights_only=True)
    codes = tuple(str(code) for code in payload["classCodes"])
    return ActiveModel(str(row["iteration_id"]), path, checksum, codes)


def _feature_maps(model: ActiveModel, crops: NDArray[np.uint8]) -> FloatArray:
    payload: Any = torch.load(model.checkpoint_path, map_location="cpu", weights_only=True)
    network = SpatialSymbolCnn(len(model.class_codes))
    network.load_state_dict(payload["bestState"])
    network.eval()
    torch.set_num_threads(1)
    balanced = np.stack([gray_world(crop) for crop in crops])
    batch = balanced.transpose(0, 3, 1, 2).astype(np.float32) / 127.5 - 1.0
    outputs: list[NDArray[np.float32]] = []
    with torch.inference_mode():
        for start in range(0, len(batch), 256):
            features = network.features(torch.from_numpy(batch[start : start + 256]))
            outputs.append(features.flatten(1).numpy().astype(np.float32))
    return cast(FloatArray, np.concatenate(outputs))


def _cell_state_fingerprint(connection: Connection, game_id: str) -> dict[str, int]:
    row = (
        connection.execute(
            text(
                """
                SELECT count(*) AS cells, coalesce(sum(revision), 0) AS revision_sum,
                       count(*) FILTER (WHERE review_state = 'approved') AS approved
                FROM game_data_v2.image_symbol_review_cells WHERE game_id = :game_id
                """
            ),
            {"game_id": game_id},
        )
        .mappings()
        .one()
    )
    return {key: int(row[key]) for key in ("cells", "revision_sum", "approved")}


def _load_cache(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    with np.load(path, allow_pickle=False) as archive:
        keys = archive["keys"].tolist()
        return {
            key: {
                "status": str(status),
                "crop": crop,
                "context": context,
                "context_quad": quad,
            }
            for key, status, crop, context, quad in zip(
                keys,
                archive["status"].tolist(),
                archive["crops"],
                archive["contexts"],
                archive["context_quads"],
                strict=True,
            )
        }


def _save_cache(path: Path, cache: Mapping[str, Mapping[str, Any]]) -> None:
    keys = sorted(cache)
    temporary = path.with_name(path.name + ".tmp.npz")
    np.savez(
        temporary,
        keys=np.array(keys),
        status=np.array([cache[key]["status"] for key in keys]),
        crops=np.stack([cache[key]["crop"] for key in keys])
        if keys
        else np.zeros((0, CROP_SIZE, CROP_SIZE, 3), np.uint8),
        contexts=np.stack([cache[key]["context"] for key in keys])
        if keys
        else np.zeros((0, CONTEXT_SIZE, CONTEXT_SIZE, 3), np.uint8),
        context_quads=np.stack([cache[key]["context_quad"] for key in keys])
        if keys
        else np.zeros((0, 4, 2), np.float32),
    )
    temporary.replace(path)


def _cache_key(cell: Cell) -> str:
    return f"{cell.id}:{cell.rendered_pixel_checksum_sha256}"


def _context(rgb: NDArray[np.uint8], cell: Cell) -> tuple[NDArray[np.uint8], NDArray[np.float32]]:
    quad = np.asarray(cell.source_quad, dtype=np.float32)
    centre = quad.mean(axis=0)
    half = max(float(np.ptp(quad[:, 0])), float(np.ptp(quad[:, 1]))) * 1.5
    left, top = int(max(0, centre[0] - half)), int(max(0, centre[1] - half))
    right = int(min(rgb.shape[1], centre[0] + half))
    bottom = int(min(rgb.shape[0], centre[1] + half))
    canvas = np.zeros((CONTEXT_SIZE, CONTEXT_SIZE, 3), dtype=np.uint8)
    if right <= left or bottom <= top:
        return canvas, np.zeros((4, 2), dtype=np.float32)
    window = rgb[top:bottom, left:right]
    scale = CONTEXT_SIZE / max(window.shape[:2])
    width = max(1, int(window.shape[1] * scale))
    height = max(1, int(window.shape[0] * scale))
    canvas[:height, :width] = cv2.resize(window, (width, height), interpolation=cv2.INTER_AREA)
    return canvas, ((quad - np.array([left, top], dtype=np.float32)) * scale).astype(np.float32)


def _render(
    cells: Sequence[Cell],
    *,
    artifact_root: Path,
    cache_path: Path,
    deadline: float,
) -> tuple[dict[str, dict[str, Any]], int]:
    """Render missing crops until the deadline; returns the cache and the remainder."""

    cache = _load_cache(cache_path)
    missing = sorted(
        (cell for cell in cells if _cache_key(cell) not in cache),
        key=lambda cell: (cell.source_checksum_sha256, cell.id),
    )
    loader = CanonicalSourceLoader()
    originals = (artifact_root / "data" / "originals").resolve()
    rendered = 0
    unavailable = 0
    for cell in missing:
        if time.monotonic() >= deadline:
            break
        checksum = cell.source_checksum_sha256
        empty_crop = np.zeros((CROP_SIZE, CROP_SIZE, 3), dtype=np.uint8)
        empty_context = np.zeros((CONTEXT_SIZE, CONTEXT_SIZE, 3), dtype=np.uint8)
        entry: dict[str, Any] = {
            "status": "ok",
            "crop": empty_crop,
            "context": empty_context,
            "context_quad": np.zeros((4, 2), dtype=np.float32),
        }
        try:
            frame = loader.load(
                originals / checksum[:2] / f"{checksum}.jpg",
                expected_source_checksum_sha256=checksum,
            )
            crop = source_direct_warp_rgb(
                frame.rgb,
                source_quad=cell.padded_quad,
                output_width=CROP_SIZE,
                output_height=CROP_SIZE,
            )
            if rgb_pixel_checksum_sha256(crop) != cell.rendered_pixel_checksum_sha256:
                entry["status"] = "IMAGE_VIRTUAL_CELL_PIXEL_CHECKSUM_MISMATCH"
            else:
                entry["crop"] = crop
                entry["context"], entry["context_quad"] = _context(frame.rgb, cell)
        except (CanonicalSourceLoadError, VirtualCellExtractionError) as error:
            if error.code in _TRANSIENT_SOURCE_ERRORS:
                # A missing or unreadable file may be restored; retry on the next run.
                unavailable += 1
                continue
            entry["status"] = error.code
        except cv2.error:
            entry["status"] = "IMAGE_VIRTUAL_CELL_RENDER_FAILED"
        cache[_cache_key(cell)] = entry
        rendered += 1
    if rendered:
        _save_cache(cache_path, cache)
    if unavailable:
        raise EvaluationError(
            "SYMBOL_REFERENCE_SOURCE_UNAVAILABLE",
            f"{unavailable} managed originals are unavailable; check --artifact-root.",
        )
    return cache, len(missing) - rendered


def _proposals(
    shape: FloatArray,
    combined: FloatArray,
    reference_shape: FloatArray,
    reference_combined: FloatArray,
    labels: NDArray[np.int64],
    *,
    class_count: int,
    exclusions: Sequence[NDArray[np.bool_] | None],
) -> list[Proposal]:
    return [
        decide(
            vote(shape[index], reference_shape, labels, class_count=class_count, excluded=mask),
            vote(
                combined[index],
                reference_combined,
                labels,
                class_count=class_count,
                excluded=mask,
            ),
        )
        for index, mask in enumerate(exclusions)
    ]


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else round(numerator / denominator, 6)


def _evaluation(
    cells: Sequence[Cell],
    proposals: Sequence[Proposal],
    labels: NDArray[np.int64],
    codes: Sequence[str],
    *,
    min_confidence: float,
    max_confidence: float,
) -> dict[str, object]:
    shape_winner = np.array(
        [-1 if p.shape_vote.class_index is None else p.shape_vote.class_index for p in proposals]
    )
    combined_winner = np.array(
        [
            -1 if p.combined_vote.class_index is None else p.combined_vote.class_index
            for p in proposals
        ]
    )
    confident = np.array([-1 if p.class_index is None else p.class_index for p in proposals])
    model = np.array(
        [
            codes.index(cell.prediction_symbol_code) if cell.prediction_symbol_code in codes else -1
            for cell in cells
        ]
    )
    confidence = np.array(
        [
            -1.0 if cell.prediction_confidence is None else cell.prediction_confidence
            for cell in cells
        ]
    )

    def summary(mask: NDArray[np.bool_]) -> dict[str, object]:
        total = int(mask.sum())
        sure = mask & (confident >= 0)
        return {
            "cells": total,
            "activeModelAccuracy": _ratio(int((model[mask] == labels[mask]).sum()), total),
            "shapeVoteAccuracy": _ratio(int((shape_winner[mask] == labels[mask]).sum()), total),
            "combinedVoteAccuracy": _ratio(
                int((combined_winner[mask] == labels[mask]).sum()), total
            ),
            "confidentCoverage": _ratio(int(sure.sum()), total),
            "confidentAccuracy": _ratio(
                int((confident[sure] == labels[sure]).sum()), int(sure.sum())
            ),
            "confidentErrors": int((confident[sure] != labels[sure]).sum()),
        }

    everything = np.ones(len(cells), dtype=np.bool_)
    band = (confidence >= min_confidence) & (confidence < max_confidence)
    confusion = [[0 for _ in codes] for _ in codes]
    for truth, proposed in zip(labels.tolist(), confident.tolist(), strict=True):
        if proposed >= 0:
            confusion[truth][proposed] += 1
    return {
        "all": summary(everything),
        "byOperatorSymbol": {code: summary(labels == index) for index, code in enumerate(codes)},
        "byPredictedSymbolInBand": {
            code: summary(band & (model == index)) for index, code in enumerate(codes)
        },
        "band": summary(band),
        "reviewReasons": dict(sorted(Counter(p.reason for p in proposals).items())),
        "confidentConfusionMatrix": {
            "rowsOperator_columnsProposal": list(codes),
            "matrix": confusion,
        },
        "confidentErrorCells": [
            {
                "cellReviewId": cell.id,
                "importJobId": cell.import_job_id,
                "operator": codes[int(truth)],
                "proposal": codes[int(proposed)],
            }
            for cell, truth, proposed in zip(cells, labels, confident, strict=True)
            if proposed >= 0 and proposed != truth
        ],
    }


def _sheet(
    path: Path,
    rows: Sequence[tuple[Cell, Proposal, Mapping[str, Any]]],
    codes: Sequence[str],
) -> None:
    tile_width, tile_height, columns = 236, 140, 5
    sheet = Image.new(
        "RGB", (tile_width * columns, tile_height * ((len(rows) + columns - 1) // columns))
    )
    for index, (cell, proposal, entry) in enumerate(rows):
        tile = Image.new("RGB", (tile_width, tile_height), (25, 25, 25))
        crop = cv2.resize(entry["crop"], (108, 108), interpolation=cv2.INTER_NEAREST)
        context = np.ascontiguousarray(
            cv2.resize(entry["context"], (108, 108), interpolation=cv2.INTER_LINEAR)
        )
        quad = (entry["context_quad"] * (108 / CONTEXT_SIZE)).astype(np.int32)
        cv2.polylines(context, [quad], True, (0, 255, 0), 1)
        tile.paste(Image.fromarray(crop), (4, 30))
        tile.paste(Image.fromarray(context), (120, 30))
        draw = ImageDraw.Draw(tile)
        confidence = cell.prediction_confidence or 0.0
        draw.text(
            (4, 2),
            f"#{index + 1} {cell.id[:8]} {cell.prediction_symbol_code} {confidence:.2f}",
            fill=(255, 255, 255),
        )
        if proposal.class_index is None:
            shape = proposal.shape_vote
            hint = "-" if shape.class_index is None else codes[shape.class_index]
            label, colour = (
                f"DO PRZEGLADU ({hint} {shape.agreeing_count}/{shape.neighbour_count})",
                (255, 170, 80),
            )
        else:
            label, colour = f"-> {codes[proposal.class_index]} 7/7", (120, 255, 120)
        draw.text((4, 15), label, fill=colour)
        sheet.paste(tile, ((index % columns) * tile_width, (index // columns) * tile_height))
    sheet.save(path)


def _write_json(path: Path, value: object) -> str:
    content = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def _usable(
    cells: Sequence[Cell], cache: Mapping[str, Mapping[str, Any]]
) -> tuple[list[Cell], dict[str, int]]:
    usable: list[Cell] = []
    excluded: Counter[str] = Counter()
    for cell in cells:
        status = str(cache[_cache_key(cell)]["status"])
        if status == "ok":
            usable.append(cell)
        else:
            excluded[status] += 1
    return usable, dict(sorted(excluded.items()))


def _descriptors(
    cells: Sequence[Cell], cache: Mapping[str, Mapping[str, Any]], model: ActiveModel
) -> tuple[FloatArray, FloatArray]:
    crops = np.stack([cache[_cache_key(cell)]["crop"] for cell in cells])
    shape, hue = descriptor_matrix(list(crops))
    combined = normalize_rows(combined_descriptor(shape, _feature_maps(model, crops), hue))
    return shape, combined


def _evaluate(arguments: argparse.Namespace) -> int:
    if not 0.0 <= arguments.min_confidence < arguments.max_confidence <= 1.0001:
        raise EvaluationError("SYMBOL_REFERENCE_BAND_INVALID", "The confidence band is invalid.")
    deadline = time.monotonic() + float(arguments.time_budget_seconds)
    settings = ApiSettings.from_environment()
    artifact_root = (arguments.artifact_root or settings.artifact_root).resolve()
    output = cast(Path, arguments.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "sheets").mkdir(exist_ok=True)

    engine = create_database_engine(settings)
    try:
        with engine.connect().execution_options(
            isolation_level="REPEATABLE READ", postgresql_readonly=True
        ) as connection:
            game_id, game_name = _game(connection, arguments.game_code)
            # One REPEATABLE READ snapshot; the fingerprint lets separate runs be compared.
            fingerprint = _cell_state_fingerprint(connection, game_id)
            model = _active_model(connection, game_id, artifact_root)
            references = [
                _cell(cast(Mapping[str, Any], row))
                for row in connection.execute(
                    text(_REFERENCE_SQL),
                    {"game_id": game_id, "per_group": REFERENCES_PER_GROUP},
                ).mappings()
            ]
            pending = [
                _cell(cast(Mapping[str, Any], row))
                for row in connection.execute(
                    text(_PENDING_SQL),
                    {
                        "game_id": game_id,
                        "min_confidence": arguments.min_confidence,
                        "max_confidence": arguments.max_confidence,
                        "per_symbol": arguments.pending_per_symbol,
                    },
                ).mappings()
            ]
    finally:
        engine.dispose()
    unknown = sorted(
        {str(cell.label) for cell in references if cell.label not in model.class_codes}
    )
    if unknown:
        raise EvaluationError(
            "SYMBOL_REFERENCE_CLASS_UNKNOWN",
            f"Operator symbols are unknown to the active model: {unknown}.",
        )

    cache, remaining = _render(
        [*references, *pending],
        artifact_root=artifact_root,
        cache_path=output / "crop-cache.npz",
        deadline=deadline,
    )
    if remaining:
        print(f"INCOMPLETE: {remaining} crops still to render; run the same command again.")
        return EXIT_INCOMPLETE

    codes = model.class_codes
    references, excluded_references = _usable(references, cache)
    pending, excluded_pending = _usable(pending, cache)
    if len(references) < NEIGHBOUR_COUNT:
        raise EvaluationError(
            "SYMBOL_REFERENCE_LIBRARY_EMPTY", "Too few verified cells form a library."
        )
    labels = np.array([codes.index(cast(str, cell.label)) for cell in references], dtype=np.int64)
    imports = np.array([cell.import_job_id for cell in references])
    reference_shape, reference_combined = _descriptors(references, cache, model)

    evaluation = _evaluation(
        references,
        _proposals(
            reference_shape,
            reference_combined,
            reference_shape,
            reference_combined,
            labels,
            class_count=len(codes),
            exclusions=[imports == cell.import_job_id for cell in references],
        ),
        labels,
        codes,
        min_confidence=arguments.min_confidence,
        max_confidence=arguments.max_confidence,
    )

    pending_rows: list[dict[str, object]] = []
    pending_summary: dict[str, dict[str, int]] = {}
    if pending:
        pending_shape, pending_combined = _descriptors(pending, cache, model)
        proposals = _proposals(
            pending_shape,
            pending_combined,
            reference_shape,
            reference_combined,
            labels,
            class_count=len(codes),
            exclusions=[None] * len(pending),
        )
        by_symbol: dict[str, list[tuple[Cell, Proposal, Mapping[str, Any]]]] = {}
        for cell, proposal in zip(pending, proposals, strict=True):
            predicted = cast(str, cell.prediction_symbol_code)
            proposed = (
                "DO_PRZEGLADU" if proposal.class_index is None else codes[proposal.class_index]
            )
            pending_summary.setdefault(predicted, {})
            pending_summary[predicted][proposed] = pending_summary[predicted].get(proposed, 0) + 1
            by_symbol.setdefault(predicted, []).append((cell, proposal, cache[_cache_key(cell)]))
            pending_rows.append(
                {
                    "cellReviewId": cell.id,
                    "importJobId": cell.import_job_id,
                    "sequenceNumber": cell.sequence_number,
                    "cellIndex": cell.cell_index,
                    "renderedPixelChecksumSha256": cell.rendered_pixel_checksum_sha256,
                    "activeModelSymbol": predicted,
                    "activeModelConfidence": cell.prediction_confidence,
                    "proposal": proposed,
                    "reason": proposal.reason,
                    "shapeVotes": proposal.shape_vote.agreeing_count,
                    "combinedVotes": proposal.combined_vote.agreeing_count,
                }
            )
        for predicted, rows in sorted(by_symbol.items()):
            rows.sort(key=lambda row: hashlib.md5(row[0].id.encode()).hexdigest())  # noqa: S324
            _sheet(output / "sheets" / f"pending-{predicted}.png", rows, codes)

    report = {
        "reportVersion": REPORT_VERSION,
        "libraryVersion": REFERENCE_LIBRARY_VERSION,
        "game": {"id": game_id, "code": arguments.game_code, "name": game_name},
        "activeModel": {
            "iterationId": model.iteration_id,
            "checkpointSha256": model.checkpoint_sha256,
            "classCodes": list(codes),
        },
        "parameters": {
            "neighbourCount": NEIGHBOUR_COUNT,
            "referencesPerGroup": REFERENCES_PER_GROUP,
            "minConfidence": arguments.min_confidence,
            "maxConfidence": arguments.max_confidence,
            "pendingPerSymbol": arguments.pending_per_symbol,
            "evaluationExclusion": "same-import-job",
        },
        "cellStateFingerprint": fingerprint,
        "library": {
            "cells": len(references),
            "imports": len(set(imports.tolist())),
            "bySymbol": dict(sorted(Counter(cast(str, c.label) for c in references).items())),
            "excluded": excluded_references,
            "activeModelAgreed": sum(
                cell.prediction_symbol_code == cell.label for cell in references
            ),
        },
        "evaluation": evaluation,
        "pending": {
            "cells": len(pending),
            "excluded": excluded_pending,
            "byActiveModelSymbol": {
                key: dict(sorted(value.items())) for key, value in sorted(pending_summary.items())
            },
        },
    }
    report_sha = _write_json(output / "report.json", report)
    proposals_sha = _write_json(
        output / "pending-proposals.json",
        sorted(pending_rows, key=lambda row: cast(str, row["cellReviewId"])),
    )
    print(json.dumps(evaluation["all"], sort_keys=True))
    print(f"report.json sha256={report_sha}")
    print(f"pending-proposals.json sha256={proposals_sha}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parse_args(argv)
    try:
        if arguments.command == "evaluate":
            return _evaluate(arguments)
    except EvaluationError as error:
        print(str(error), file=sys.stderr)
        return 2
    raise AssertionError(arguments.command)


if __name__ == "__main__":
    raise SystemExit(main())
