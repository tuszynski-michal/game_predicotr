"""Read-only evaluation of symbol proposals from operator-verified cells.

The command opens a READ ONLY database transaction, recreates checksum-bound
virtual crops from managed originals and writes reports only below the chosen
output directory. It never mutates domain data and never approves a cell.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import math
import sys
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import cv2
import numpy as np
import torch
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.prediction_revisions import PREDICTIONS_DIGEST_VERSION
from game_predictor_api.storage.cell_render_specs import (
    CellRenderSpecError,
    CellRenderSpecKey,
    load_cell_render_specs,
)
from game_predictor_api.storage.database import (
    create_maintenance_database_engine,
    create_session_factory,
)
from game_predictor_api.storage.game_storage_routing import game_storage_scope
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
    hint_candidates,
    normalize_rows,
    vote,
    vote_batch,
)
from game_predictor_worker.symbols.reference_library_writer import (
    MODEL_VERSION as WRITER_MODEL_VERSION,
)
from game_predictor_worker.symbols.reference_library_writer import (
    TARGET_QUALITY_CHANGED,
    BoardPlan,
    ReferenceLibraryWriteError,
    TargetCell,
    apply_board,
    predictions_digest,
    revert_board,
    revert_checksum,
)
from numpy.typing import NDArray
from PIL import Image, ImageDraw
from sqlalchemy import Connection, text
from sqlalchemy.exc import DBAPIError

REPORT_VERSION = "symbol-reference-library-evaluation-v1"
REFERENCES_PER_GROUP = 40
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
    c.recognized_board_id AS recognized_board_id,
    c.geometry_revision AS geometry_revision,
    c.render_spec_checksum_sha256 AS render_spec_checksum_sha256
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
    AND c.render_spec_checksum_sha256 IS NOT NULL
    AND c.approved_render_spec_checksum_sha256 = c.render_spec_checksum_sha256
    AND c.approved_rendered_pixel_checksum_sha256 = c.rendered_pixel_checksum_sha256
    AND s.status = 'active'
    -- D-465: a bulk approval of the model prediction is not operator evidence.
    AND NOT (
      :exclude_bulk_approve
      AND coalesce((
        SELECT e.action = 'approve' AND e.operation_id IS NOT NULL
        FROM game_data_v2.image_symbol_review_events e
        WHERE e.game_id = c.game_id
          AND e.cell_review_id = c.id
          AND e.action IN ('approve', 'reassign')
        ORDER BY e.created_at DESC, e.id DESC
        LIMIT 1
      ), false)
    )
)
SELECT * FROM eligible WHERE group_rank <= :per_group ORDER BY id
"""

# A stable split of one confidence range by cell id, for ranges too large for one cache
# (e.g. hundreds of thousands of cells at exactly 100%). One shard selects everything.
_SHARD_CLAUSE = (
    "(:shard_count = 1 OR mod(('x' || left(md5(c.id::text), 7))::bit(28)::int, :shard_count)"
    " = :shard_index)"
)

_PREVIEW_SQL = f"""
SELECT {_CELL_COLUMNS}, NULL::text AS label
FROM game_data_v2.image_symbol_review_cells c
WHERE c.game_id = :game_id
  AND c.review_state = 'pending'
  AND c.asset_mode = 'virtual_source'
  AND c.source_available = true
  AND c.quality_issue IS NULL
  AND (c.source_visibility IS NULL OR c.source_visibility = 'full')
  AND c.render_spec_checksum_sha256 IS NOT NULL
  AND c.prediction_symbol_code = ANY(:symbols)
  AND c.prediction_confidence >= :min_confidence
  AND c.prediction_confidence < :max_confidence
  AND {_SHARD_CLAUSE}
ORDER BY c.id
"""

_PREVIEW_SCOPE_SQL = f"""
SELECT reason, count(*) AS cells
FROM (
  SELECT CASE
           WHEN c.quality_issue IS NOT NULL THEN 'quality_issue:' || c.quality_issue
           WHEN c.asset_mode <> 'virtual_source' THEN 'asset_mode:' || c.asset_mode
           WHEN NOT c.source_available THEN 'source_unavailable'
           WHEN c.source_visibility IS NOT NULL AND c.source_visibility <> 'full'
             THEN 'visibility:' || c.source_visibility
           WHEN c.render_spec_checksum_sha256 IS NULL THEN 'render_spec_missing'
         END AS reason
  FROM game_data_v2.image_symbol_review_cells c
  WHERE c.game_id = :game_id
    AND c.review_state = 'pending'
    AND c.prediction_symbol_code = ANY(:symbols)
    AND c.prediction_confidence >= :min_confidence
    AND c.prediction_confidence < :max_confidence
    AND {_SHARD_CLAUSE}
) outside
WHERE reason IS NOT NULL
GROUP BY reason
"""

REFERENCE_POLICIES = {"all-human-v1": False, "no-bulk-approve-v2": True}
DEFAULT_REFERENCE_POLICY = "no-bulk-approve-v2"

_PENDING_SQL = f"""
WITH eligible AS (
  SELECT {_CELL_COLUMNS},
         NULL::text AS label,
         row_number() OVER (
           PARTITION BY c.prediction_symbol_code, c.import_job_id
           ORDER BY md5(c.id::text || :order_salt), c.id
         ) AS import_rank
  FROM game_data_v2.image_symbol_review_cells c
  WHERE c.game_id = :game_id
    AND c.review_state = 'pending'
    AND c.asset_mode = 'virtual_source'
    AND c.source_available = true
    AND c.quality_issue IS NULL
    AND (c.source_visibility IS NULL OR c.source_visibility = 'full')
    AND c.render_spec_checksum_sha256 IS NOT NULL
    AND c.prediction_symbol_code IS NOT NULL
    AND c.prediction_confidence >= :min_confidence
    AND c.prediction_confidence < :max_confidence
), ranked AS (
  SELECT *, row_number() OVER (
           PARTITION BY prediction_symbol_code
           ORDER BY import_rank, md5(id || :order_salt), id
         ) AS symbol_rank
  FROM eligible
)
SELECT * FROM ranked WHERE symbol_rank <= :per_symbol
ORDER BY prediction_symbol_code, symbol_rank
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


def _shard(value: str) -> tuple[int, int]:
    """Parse ``INDEX/COUNT`` with ``0 <= INDEX < COUNT``."""

    index_text, separator, count_text = value.partition("/")
    try:
        index, count = int(index_text), int(count_text)
    except ValueError:
        index, count = -1, 0
    if separator != "/" or not 0 <= index < count:
        raise argparse.ArgumentTypeError(f"invalid shard {value!r}; expected INDEX/COUNT")
    return index, count


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

    blind = commands.add_parser(
        "blind-sample", help="Freeze proposals and write an offline blind-review page."
    )
    blind.add_argument("--game-code", required=True)
    blind.add_argument("--output-dir", required=True, type=Path)
    blind.add_argument("--artifact-root", type=Path)
    blind.add_argument("--library-cache", required=True, type=Path)
    blind.add_argument("--exclude-cells", type=Path, action="append", default=[])
    blind.add_argument("--min-confidence", type=float, default=0.6)
    blind.add_argument("--max-confidence", type=float, default=0.8)
    blind.add_argument("--per-symbol", type=int, default=25, choices=range(1, 101))
    blind.add_argument("--seed", type=int, default=20260929)
    blind.add_argument("--time-budget-seconds", type=float, default=90.0)

    compare = commands.add_parser("compare", help="Compare blind ratings with frozen proposals.")
    compare.add_argument("--frozen", required=True, type=Path)
    compare.add_argument("--ratings", required=True, type=Path)
    compare.add_argument("--output", required=True, type=Path)
    compare.add_argument("--with-database", action="store_true")

    rescore = commands.add_parser(
        "blind-rescore", help="Re-propose a frozen blind sample with another reference policy."
    )
    rescore.add_argument("--game-code", required=True)
    rescore.add_argument("--frozen", required=True, type=Path)
    rescore.add_argument("--blind-cache", required=True, type=Path)
    rescore.add_argument("--ratings", required=True, type=Path, action="append")
    rescore.add_argument("--output", required=True, type=Path)
    rescore.add_argument("--artifact-root", type=Path)
    rescore.add_argument("--library-cache", required=True, type=Path)
    rescore.add_argument("--time-budget-seconds", type=float, default=90.0)

    preview = commands.add_parser(
        "preview", help="Propose symbols for all matching pending cells and write a local view."
    )
    preview.add_argument("--game-code", required=True)
    preview.add_argument("--output-dir", required=True, type=Path)
    preview.add_argument("--artifact-root", type=Path)
    preview.add_argument("--library-cache", required=True, type=Path)
    preview.add_argument("--symbol", required=True)
    preview.add_argument("--min-confidence", type=float, default=0.0)
    preview.add_argument("--max-confidence", type=float, default=0.8)
    preview.add_argument("--band-edge", type=float, action="append", default=[])
    preview.add_argument("--thumbnails-per-group", type=int, default=40, choices=range(1, 201))
    preview.add_argument("--time-budget-seconds", type=float, default=70.0)
    preview.add_argument(
        "--shard",
        type=_shard,
        default=(0, 1),
        help="INDEX/COUNT: only cells whose id hash falls in this shard, e.g. 2/6.",
    )

    apply_preview = commands.add_parser(
        "apply-preview", help="Run the preview and write a manifest of cells to update."
    )
    for action in preview._actions:
        if action.dest != "help":
            apply_preview._add_action(action)

    apply = commands.add_parser("apply", help="Write library predictions from a manifest.")
    apply.add_argument("--game-code", required=True)
    apply.add_argument("--manifest", required=True, type=Path)
    apply.add_argument("--expected-sha256", required=True)
    apply.add_argument("--limit-boards", type=int)
    apply.add_argument(
        "--board", action="append", default=[], help="Only these review item ids (canary)."
    )
    apply.add_argument("--time-budget-seconds", type=float, default=90.0)

    revert = commands.add_parser(
        "apply-revert", help="Restore the model predictions a manifest run replaced."
    )
    for action in apply._actions:
        if action.dest != "help":
            revert._add_action(action)
    revert.add_argument(
        "--all", action="store_true", help="Revert every board of the manifest (no --board)."
    )

    verify = commands.add_parser("apply-verify", help="Read back cells written from a manifest.")
    verify.add_argument("--manifest", required=True, type=Path)
    verify.add_argument("--expected-sha256", required=True)

    for command in (evaluate, blind, rescore, preview, apply_preview):
        command.add_argument(
            "--reference-policy",
            choices=tuple(REFERENCE_POLICIES),
            default=DEFAULT_REFERENCE_POLICY,
        )
        command.add_argument(
            "--references-per-group",
            type=int,
            default=REFERENCES_PER_GROUP,
            choices=range(1, 201),
        )
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


def _with_render_specs(
    connection: Connection, game_id: str, rows: Sequence[Mapping[Any, Any]]
) -> list[dict[str, Any]]:
    """Attach each cell's render spec from its board render manifest (D-467 S7).

    One batched, checksum-verified read; the cell column is no longer read.
    """

    keys = [
        CellRenderSpecKey(
            recognized_board_id=UUID(str(row["recognized_board_id"])),
            geometry_revision=int(row["geometry_revision"]),
            cell_index=int(row["cell_index"]),
            render_spec_checksum_sha256=str(row["render_spec_checksum_sha256"]),
        )
        for row in rows
    ]
    try:
        specs = load_cell_render_specs(
            connection, game_id=UUID(game_id), keys=keys, schema="game_data_v2"
        )
    except CellRenderSpecError as error:
        raise EvaluationError(error.code, error.message) from error
    return [{**row, "render_spec": specs[key]} for row, key in zip(rows, keys, strict=True)]


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


def _save_cache(
    path: Path, cache: Mapping[str, Mapping[str, Any]], context_size: int = CONTEXT_SIZE
) -> None:
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
        else np.zeros((0, context_size, context_size, 3), np.uint8),
        context_quads=np.stack([cache[key]["context_quad"] for key in keys])
        if keys
        else np.zeros((0, 4, 2), np.float32),
    )
    temporary.replace(path)


def _cache_key(cell: Cell) -> str:
    return f"{cell.id}:{cell.rendered_pixel_checksum_sha256}"


def _context(
    rgb: NDArray[np.uint8], cell: Cell, size: int = CONTEXT_SIZE
) -> tuple[NDArray[np.uint8], NDArray[np.float32]]:
    quad = np.asarray(cell.source_quad, dtype=np.float32)
    centre = quad.mean(axis=0)
    half = max(float(np.ptp(quad[:, 0])), float(np.ptp(quad[:, 1]))) * 1.5
    left, top = int(max(0, centre[0] - half)), int(max(0, centre[1] - half))
    right = int(min(rgb.shape[1], centre[0] + half))
    bottom = int(min(rgb.shape[0], centre[1] + half))
    canvas = np.zeros((size, size, 3), dtype=np.uint8)
    if size == 0 or right <= left or bottom <= top:
        return canvas, np.zeros((4, 2), dtype=np.float32)
    window = rgb[top:bottom, left:right]
    scale = size / max(window.shape[:2])
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
    context_size: int = CONTEXT_SIZE,
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
        empty_context = np.zeros((context_size, context_size, 3), dtype=np.uint8)
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
                entry["context"], entry["context_quad"] = _context(frame.rgb, cell, context_size)
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
        _save_cache(cache_path, cache, context_size)
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


def digest_json(value: object) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _write_json(path: Path, value: object) -> str:
    content = _json_bytes(value)
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


@dataclass(frozen=True, slots=True)
class Snapshot:
    game_id: str
    game_name: str
    fingerprint: dict[str, int]
    model: ActiveModel
    symbol_names: dict[str, str]
    references: list[Cell]
    pending: list[Cell]
    not_in_scope: dict[str, int]


@dataclass(frozen=True, slots=True)
class Library:
    cells: list[Cell]
    labels: NDArray[np.int64]
    imports: NDArray[np.str_]
    shape: FloatArray
    combined: FloatArray
    excluded: dict[str, int]


def _read_snapshot(
    settings: ApiSettings,
    game_code: str,
    artifact_root: Path,
    pending_parameters: Mapping[str, object],
    *,
    reference_policy: str,
    references_per_group: int = REFERENCES_PER_GROUP,
    pending_sql: str = _PENDING_SQL,
    scope_sql: str | None = None,
) -> Snapshot:
    """Read everything from one REPEATABLE READ, READ ONLY transaction."""

    if reference_policy not in REFERENCE_POLICIES:
        raise EvaluationError(
            "SYMBOL_REFERENCE_POLICY_UNKNOWN", f"Unknown reference policy {reference_policy}."
        )

    engine = create_maintenance_database_engine(settings)
    try:
        with engine.connect().execution_options(
            isolation_level="REPEATABLE READ", postgresql_readonly=True
        ) as connection:
            game_id, game_name = _game(connection, game_code)
            # One snapshot; the fingerprint lets separate runs be compared.
            fingerprint = _cell_state_fingerprint(connection, game_id)
            model = _active_model(connection, game_id, artifact_root)
            symbol_names = {
                str(row["code"]): str(row["name"])
                for row in connection.execute(
                    text("SELECT code, name FROM public.symbols WHERE game_id = :game_id"),
                    {"game_id": game_id},
                ).mappings()
            }
            references = [
                _cell(row)
                for row in _with_render_specs(
                    connection,
                    game_id,
                    connection.execute(
                        text(_REFERENCE_SQL),
                        {
                            "game_id": game_id,
                            "per_group": references_per_group,
                            "exclude_bulk_approve": REFERENCE_POLICIES[reference_policy],
                        },
                    )
                    .mappings()
                    .all(),
                )
            ]
            pending = [
                _cell(row)
                for row in _with_render_specs(
                    connection,
                    game_id,
                    connection.execute(
                        text(pending_sql), {"game_id": game_id, **pending_parameters}
                    )
                    .mappings()
                    .all(),
                )
            ]
            not_in_scope = (
                {
                    str(row["reason"]): int(row["cells"])
                    for row in connection.execute(
                        text(scope_sql), {"game_id": game_id, **pending_parameters}
                    ).mappings()
                }
                if scope_sql is not None
                else {}
            )
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
    return Snapshot(
        game_id,
        game_name,
        fingerprint,
        model,
        symbol_names,
        references,
        pending,
        dict(sorted(not_in_scope.items())),
    )


def _build_library(
    references: Sequence[Cell], cache: Mapping[str, Mapping[str, Any]], model: ActiveModel
) -> Library:
    usable, excluded = _usable(references, cache)
    if len(usable) < NEIGHBOUR_COUNT:
        raise EvaluationError(
            "SYMBOL_REFERENCE_LIBRARY_EMPTY", "Too few verified cells form a library."
        )
    codes = model.class_codes
    labels = np.array([codes.index(cast(str, cell.label)) for cell in usable], dtype=np.int64)
    imports = np.array([cell.import_job_id for cell in usable])
    shape, combined = _descriptors(usable, cache, model)
    return Library(usable, labels, imports, shape, combined, excluded)


def _evaluate(arguments: argparse.Namespace) -> int:
    if not 0.0 <= arguments.min_confidence < arguments.max_confidence <= 1.0001:
        raise EvaluationError("SYMBOL_REFERENCE_BAND_INVALID", "The confidence band is invalid.")
    deadline = time.monotonic() + float(arguments.time_budget_seconds)
    settings = ApiSettings.from_environment()
    artifact_root = (arguments.artifact_root or settings.artifact_root).resolve()
    output = cast(Path, arguments.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "sheets").mkdir(exist_ok=True)

    snapshot = _read_snapshot(
        settings,
        arguments.game_code,
        artifact_root,
        {
            "min_confidence": arguments.min_confidence,
            "max_confidence": arguments.max_confidence,
            "per_symbol": arguments.pending_per_symbol,
            "order_salt": "",
        },
        reference_policy=arguments.reference_policy,
        references_per_group=arguments.references_per_group,
    )
    game_id, game_name, fingerprint = snapshot.game_id, snapshot.game_name, snapshot.fingerprint
    model, references, pending = snapshot.model, snapshot.references, snapshot.pending
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
    pending, excluded_pending = _usable(pending, cache)
    library = _build_library(references, cache, model)
    references, labels, imports = library.cells, library.labels, library.imports
    reference_shape, reference_combined = library.shape, library.combined
    excluded_references = library.excluded

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
            "referencesPerGroup": arguments.references_per_group,
            "minConfidence": arguments.min_confidence,
            "maxConfidence": arguments.max_confidence,
            "pendingPerSymbol": arguments.pending_per_symbol,
            "evaluationExclusion": "same-import-job",
            "referencePolicy": arguments.reference_policy,
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


BLIND_FORMAT = "symbol-reference-blind-sample-v1"
RATINGS_FORMAT = "symbol-reference-blind-ratings-v1"
COMPARE_VERSION = "symbol-reference-blind-comparison-v1"
REVIEW = "DO_PRZEGLADU"
NON_SYMBOL_RATINGS = {
    "NIECZYTELNY": "Nieczytelny",
    "ZASLONIETY": "Zasłonięty",
    "ZLA_SIATKA": "Zła siatka",
}
_STATE_KEYS = {"NIECZYTELNY": "N", "ZASLONIETY": "Z", "ZLA_SIATKA": "S"}
BLIND_CONTEXT_SIZE = 224
GATE_OVERALL = 0.98
GATE_PER_SYMBOL = 0.95
GATE_MIN_SUPPORT = 10


def _excluded_ids(paths: Sequence[Path]) -> set[str]:
    """Cell ids already shown with a proposal; they cannot be rated blindly."""

    excluded: set[str] = set()
    for path in paths:
        value: Any = json.loads(path.read_text(encoding="utf-8"))
        rows = value.get("cells", []) if isinstance(value, Mapping) else value
        if not isinstance(rows, list):
            raise EvaluationError(
                "SYMBOL_REFERENCE_EXCLUSION_INVALID", f"{path.name} is not a list of cells."
            )
        for row in rows:
            identifier = (
                row.get("cellReviewId", row.get("id")) if isinstance(row, Mapping) else None
            )
            if not isinstance(identifier, str):
                raise EvaluationError(
                    "SYMBOL_REFERENCE_EXCLUSION_INVALID", f"{path.name} has a row without an id."
                )
            excluded.add(identifier)
    return excluded


def _data_uri(image: Image.Image, image_format: str, media_type: str) -> str:
    stream = io.BytesIO()
    if image_format == "PNG":
        image.save(stream, format="PNG", optimize=True)
    else:
        image.save(stream, format="JPEG", quality=90)
    return f"data:{media_type};base64," + base64.b64encode(stream.getvalue()).decode("ascii")


def _crop_uri(rgb: NDArray[np.uint8], size: int) -> str:
    enlarged = cv2.resize(rgb, (size, size), interpolation=cv2.INTER_NEAREST)
    return _data_uri(Image.fromarray(enlarged), "PNG", "image/png")


def _context_uri(rgb: NDArray[np.uint8], quad: NDArray[np.float32]) -> str:
    canvas = np.ascontiguousarray(rgb.copy())
    cv2.polylines(canvas, [quad.astype(np.int32)], True, (0, 255, 0), 1)
    return _data_uri(Image.fromarray(canvas), "JPEG", "image/jpeg")


def _blind_html(
    items: Sequence[Mapping[str, str]],
    symbols: Sequence[tuple[str, str]],
    frozen_sha256: str,
) -> str:
    """Offline page; it receives only ids and pixels, never proposals or predictions."""

    options = [
        {"code": code, "name": name, "key": str(index + 1) if index < 9 else ""}
        for index, (code, name) in enumerate(symbols)
    ] + [
        {"code": code, "name": name, "key": _STATE_KEYS[code]}
        for code, name in NON_SYMBOL_RATINGS.items()
    ]
    payload = json.dumps(
        {
            "frozenSha256": frozen_sha256,
            "format": RATINGS_FORMAT,
            "items": list(items),
            "options": options,
            "states": list(NON_SYMBOL_RATINGS),
        },
        ensure_ascii=False,
    ).replace("</", "<\\/")
    return _BLIND_PAGE_TEMPLATE.replace("__PAYLOAD__", payload).replace(
        "__FROZEN__", frozen_sha256[:12]
    )


_BLIND_PAGE_TEMPLATE = (Path(__file__).with_name("symbol_reference_blind_review.html")).read_text(
    encoding="utf-8"
)


def _blind_sample(arguments: argparse.Namespace) -> int:
    if not 0.0 <= arguments.min_confidence < arguments.max_confidence <= 1.0001:
        raise EvaluationError("SYMBOL_REFERENCE_BAND_INVALID", "The confidence band is invalid.")
    deadline = time.monotonic() + float(arguments.time_budget_seconds)
    settings = ApiSettings.from_environment()
    artifact_root = (arguments.artifact_root or settings.artifact_root).resolve()
    output = cast(Path, arguments.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    excluded_ids = _excluded_ids(arguments.exclude_cells)
    per_symbol = int(arguments.per_symbol)
    snapshot = _read_snapshot(
        settings,
        arguments.game_code,
        artifact_root,
        {
            "min_confidence": arguments.min_confidence,
            "max_confidence": arguments.max_confidence,
            # Over-fetch so previously shown cells can be removed without shrinking the sample.
            "per_symbol": per_symbol + len(excluded_ids),
            "order_salt": BLIND_FORMAT,
        },
        reference_policy=arguments.reference_policy,
        references_per_group=arguments.references_per_group,
    )
    chosen: list[Cell] = []
    taken: Counter[str] = Counter()
    for cell in snapshot.pending:
        predicted = cast(str, cell.prediction_symbol_code)
        if cell.id not in excluded_ids and taken[predicted] < per_symbol:
            chosen.append(cell)
            taken[predicted] += 1

    library_cache, remaining = _render(
        snapshot.references,
        artifact_root=artifact_root,
        cache_path=cast(Path, arguments.library_cache).resolve(),
        deadline=deadline,
    )
    blind_cache, blind_remaining = _render(
        chosen,
        artifact_root=artifact_root,
        cache_path=output / "blind-cache.npz",
        deadline=deadline,
        context_size=BLIND_CONTEXT_SIZE,
    )
    if remaining or blind_remaining:
        print(
            f"INCOMPLETE: {remaining + blind_remaining} crops still to render; "
            "run the same command again."
        )
        return EXIT_INCOMPLETE

    model = snapshot.model
    codes = model.class_codes
    library = _build_library(snapshot.references, library_cache, model)
    chosen, excluded_chosen = _usable(chosen, blind_cache)
    if not chosen:
        raise EvaluationError("SYMBOL_REFERENCE_BLIND_EMPTY", "No pending cell can be sampled.")
    sampled = dict(
        sorted(Counter(cast(str, cell.prediction_symbol_code) for cell in chosen).items())
    )
    shape, combined = _descriptors(chosen, blind_cache, model)
    proposals = _proposals(
        shape,
        combined,
        library.shape,
        library.combined,
        library.labels,
        class_count=len(codes),
        exclusions=[None] * len(chosen),
    )
    rows = [
        {
            "cellReviewId": cell.id,
            "importJobId": cell.import_job_id,
            "sequenceNumber": cell.sequence_number,
            "cellIndex": cell.cell_index,
            "renderedPixelChecksumSha256": cell.rendered_pixel_checksum_sha256,
            "activeModelSymbol": cell.prediction_symbol_code,
            "activeModelConfidence": cell.prediction_confidence,
            "proposal": REVIEW if proposal.class_index is None else codes[proposal.class_index],
            "reason": proposal.reason,
            "shapeVotes": proposal.shape_vote.agreeing_count,
            "combinedVotes": proposal.combined_vote.agreeing_count,
        }
        for cell, proposal in zip(chosen, proposals, strict=True)
    ]
    rows.sort(key=lambda row: cast(str, row["cellReviewId"]))
    frozen = {
        "format": BLIND_FORMAT,
        "libraryVersion": REFERENCE_LIBRARY_VERSION,
        "game": {"id": snapshot.game_id, "code": arguments.game_code, "name": snapshot.game_name},
        "activeModel": {
            "iterationId": model.iteration_id,
            "checkpointSha256": model.checkpoint_sha256,
        },
        "cellStateFingerprint": snapshot.fingerprint,
        "parameters": {
            "minConfidence": arguments.min_confidence,
            "maxConfidence": arguments.max_confidence,
            "perSymbol": per_symbol,
            "seed": arguments.seed,
            "excludedPreviouslyShown": len(excluded_ids),
            "referencePolicy": arguments.reference_policy,
            "referencesPerGroup": arguments.references_per_group,
        },
        "library": {"cells": len(library.cells), "excluded": library.excluded},
        "symbolCodes": list(codes),
        "perSymbol": sampled,
        "excluded": excluded_chosen,
        "cells": rows,
    }
    frozen_path = output / "blind-frozen.json"
    content = _json_bytes(frozen)
    if frozen_path.exists() and frozen_path.read_bytes() != content:
        # Ratings are bound to one freeze; a different sample must use a new directory.
        raise EvaluationError(
            "SYMBOL_REFERENCE_BLIND_FROZEN_EXISTS",
            f"{frozen_path} holds a different sample; choose another --output-dir.",
        )
    frozen_path.write_bytes(content)
    frozen_sha = hashlib.sha256(content).hexdigest()

    order = np.random.default_rng(int(arguments.seed)).permutation(len(chosen))
    items = []
    for position in order.tolist():
        cell = chosen[position]
        entry = blind_cache[_cache_key(cell)]
        items.append(
            {
                "id": cell.id,
                "crop": _crop_uri(entry["crop"], 192),
                "context": _context_uri(entry["context"], entry["context_quad"]),
            }
        )
    symbols = [(code, snapshot.symbol_names.get(code, code)) for code in codes]
    page = _blind_html(items, symbols, frozen_sha)
    (output / "blind-review.html").write_text(page, encoding="utf-8")
    print(f"cells={len(chosen)} perSymbol={sampled} excluded={excluded_chosen}")
    if any(count < per_symbol for count in sampled.values()) or len(sampled) < len(taken):
        print(f"WARNING: fewer than {per_symbol} cells for some predicted symbols.")
    print(f"blind-frozen.json sha256={frozen_sha}")
    print(f"blind-review.html -> {output / 'blind-review.html'}")
    return 0


def _compare_ratings(
    frozen: Mapping[str, Any],
    frozen_sha256: str,
    ratings: Mapping[str, Any],
    decisions: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Pure comparison of frozen proposals with blind operator ratings."""

    if ratings.get("format") != RATINGS_FORMAT or ratings.get("frozenSha256") != frozen_sha256:
        raise EvaluationError(
            "SYMBOL_REFERENCE_RATINGS_MISMATCH",
            "The ratings file belongs to a different frozen sample.",
        )
    values = ratings.get("ratings")
    if not isinstance(values, Mapping):
        raise EvaluationError("SYMBOL_REFERENCE_RATINGS_INVALID", "Ratings must be an object.")
    cells = {str(row["cellReviewId"]): row for row in frozen["cells"]}
    unknown = sorted(set(values) - set(cells))
    if unknown:
        raise EvaluationError(
            "SYMBOL_REFERENCE_RATINGS_INVALID", f"Ratings reference unknown cells: {unknown[:3]}."
        )
    symbol_codes = sorted(
        {str(code) for code in frozen.get("symbolCodes", [])}
        | {str(row["activeModelSymbol"]) for row in cells.values()}
        | {str(row["proposal"]) for row in cells.values() if row["proposal"] != REVIEW}
    )
    allowed = set(symbol_codes) | set(NON_SYMBOL_RATINGS)
    invalid = sorted({str(value) for value in values.values()} - allowed)
    if invalid:
        raise EvaluationError(
            "SYMBOL_REFERENCE_RATINGS_INVALID", f"Ratings use unknown values: {invalid}."
        )

    rated = {str(key): str(value) for key, value in values.items()}
    symbol_rated = {key: value for key, value in rated.items() if value not in NON_SYMBOL_RATINGS}
    confident = {
        key: str(cells[key]["proposal"]) for key in symbol_rated if cells[key]["proposal"] != REVIEW
    }
    correct = sum(confident[key] == symbol_rated[key] for key in confident)
    model_correct = sum(
        str(cells[key]["activeModelSymbol"]) == value for key, value in symbol_rated.items()
    )
    per_proposal: dict[str, dict[str, object]] = {}
    for code in symbol_codes:
        keys = [key for key, value in confident.items() if value == code]
        hits = sum(symbol_rated[key] == code for key in keys)
        per_proposal[code] = {
            "confidentProposals": len(keys),
            "correct": hits,
            "accuracy": _ratio(hits, len(keys)),
            "gateEligible": len(keys) >= GATE_MIN_SUPPORT,
        }
    confident_on_states = Counter(
        value
        for key, value in rated.items()
        if value in NON_SYMBOL_RATINGS and cells[key]["proposal"] != REVIEW
    )
    complete = len(rated) == len(cells)
    overall = _ratio(correct, len(confident))
    eligible = [row for row in per_proposal.values() if row["gateEligible"]]
    gate_passed = (
        complete
        and overall is not None
        and overall >= GATE_OVERALL
        and all(cast(float, row["accuracy"]) >= GATE_PER_SYMBOL for row in eligible)
    )
    confusion: Counter[tuple[str, str]] = Counter(
        (symbol_rated[key], value) for key, value in confident.items()
    )
    report: dict[str, object] = {
        "version": COMPARE_VERSION,
        "frozenSha256": frozen_sha256,
        "cells": len(cells),
        "rated": len(rated),
        "complete": complete,
        "ratingCounts": dict(sorted(Counter(rated.values()).items())),
        "symbolRated": len(symbol_rated),
        "confidentProposals": len(confident),
        "confidentCoverage": _ratio(len(confident), len(symbol_rated)),
        "confidentAccuracy": overall,
        "activeModelAccuracy": _ratio(model_correct, len(symbol_rated)),
        "perProposedSymbol": per_proposal,
        "unconfirmedSymbols": [
            code for code, row in per_proposal.items() if not row["gateEligible"]
        ],
        "confidentProposalsOnNonSymbolRatings": dict(sorted(confident_on_states.items())),
        "confidentConfusion": [
            {"operator": truth, "proposal": proposed, "cells": count}
            for (truth, proposed), count in sorted(confusion.items())
        ],
        "confidentErrors": [
            {"cellReviewId": key, "operator": symbol_rated[key], "proposal": value}
            for key, value in sorted(confident.items())
            if value != symbol_rated[key]
        ],
        "gate": {
            "overallThreshold": GATE_OVERALL,
            "perSymbolThreshold": GATE_PER_SYMBOL,
            "minimumSupport": GATE_MIN_SUPPORT,
            "passed": gate_passed,
        },
    }
    if decisions is not None:
        report["laterAdminDecisions"] = {
            "cells": len(decisions),
            "agreeWithBlindRating": sum(
                rated.get(key) == value for key, value in decisions.items()
            ),
            "agreeWithConfidentProposal": sum(
                confident.get(key) == value for key, value in decisions.items()
            ),
        }
    return report


def _admin_decisions(game_id: str, cell_ids: Sequence[str]) -> dict[str, str]:
    """Read-only lookup of symbols the operator approved in Admin after the freeze."""

    engine = create_maintenance_database_engine(ApiSettings.from_environment())
    try:
        with engine.connect().execution_options(postgresql_readonly=True) as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT c.id::text AS id, s.code
                    FROM game_data_v2.image_symbol_review_cells c
                    JOIN public.symbols s ON s.id = c.assigned_symbol_id
                    WHERE c.game_id = :game_id AND c.review_state = 'approved'
                      AND c.assignment_source = 'human'
                      AND c.id = ANY(CAST(:ids AS uuid[]))
                    """
                ),
                {"game_id": game_id, "ids": list(cell_ids)},
            ).mappings()
            return {str(row["id"]): str(row["code"]) for row in rows}
    finally:
        engine.dispose()


def _compare(arguments: argparse.Namespace) -> int:
    frozen_bytes = cast(Path, arguments.frozen).read_bytes()
    frozen_sha = hashlib.sha256(frozen_bytes).hexdigest()
    frozen: Any = json.loads(frozen_bytes)
    if not isinstance(frozen, Mapping) or frozen.get("format") != BLIND_FORMAT:
        raise EvaluationError("SYMBOL_REFERENCE_FROZEN_INVALID", "Unknown frozen sample format.")
    ratings: Any = json.loads(cast(Path, arguments.ratings).read_text(encoding="utf-8"))
    if not isinstance(ratings, Mapping):
        raise EvaluationError("SYMBOL_REFERENCE_RATINGS_INVALID", "Ratings must be an object.")
    decisions = (
        _admin_decisions(
            str(frozen["game"]["id"]), [str(row["cellReviewId"]) for row in frozen["cells"]]
        )
        if arguments.with_database
        else None
    )
    report = _compare_ratings(frozen, frozen_sha, ratings, decisions)
    output = cast(Path, arguments.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    report_sha = _write_json(output, report)
    summary = {
        key: report[key]
        for key in ("rated", "complete", "confidentCoverage", "confidentAccuracy", "gate")
    }
    print(json.dumps(summary, sort_keys=True))
    print(f"{output.name} sha256={report_sha}")
    return 0


RESCORE_VERSION = "symbol-reference-blind-rescore-v1"
PREVIEW_VERSION = "symbol-reference-preview-v2"
PREVIEW_CONTEXT_SIZE = 144


def _frozen_cells(path: Path) -> tuple[dict[str, Any], str]:
    content = path.read_bytes()
    frozen: Any = json.loads(content)
    if not isinstance(frozen, Mapping) or frozen.get("format") != BLIND_FORMAT:
        raise EvaluationError("SYMBOL_REFERENCE_FROZEN_INVALID", "Unknown frozen sample format.")
    return dict(frozen), hashlib.sha256(content).hexdigest()


def _cached_crops(
    cache: Mapping[str, Mapping[str, Any]], rows: Sequence[Mapping[str, Any]]
) -> list[NDArray[np.uint8]]:
    """Return the frozen cells' crops, refusing any cell whose pixels were not frozen."""

    crops: list[NDArray[np.uint8]] = []
    for row in rows:
        key = f"{row['cellReviewId']}:{row['renderedPixelChecksumSha256']}"
        entry = cache.get(key)
        if entry is None or entry["status"] != "ok":
            raise EvaluationError(
                "SYMBOL_REFERENCE_FROZEN_PIXELS_MISSING",
                f"Cell {row['cellReviewId']} has no frozen crop with the recorded checksum.",
            )
        crop = cast(NDArray[np.uint8], entry["crop"])
        if rgb_pixel_checksum_sha256(crop) != row["renderedPixelChecksumSha256"]:
            raise EvaluationError(
                "SYMBOL_REFERENCE_FROZEN_PIXELS_MISSING",
                f"Cell {row['cellReviewId']} crop differs from the frozen checksum.",
            )
        crops.append(crop)
    return crops


def _blind_rescore(arguments: argparse.Namespace) -> int:
    deadline = time.monotonic() + float(arguments.time_budget_seconds)
    settings = ApiSettings.from_environment()
    artifact_root = (arguments.artifact_root or settings.artifact_root).resolve()
    frozen, frozen_sha = _frozen_cells(cast(Path, arguments.frozen))
    snapshot = _read_snapshot(
        settings,
        arguments.game_code,
        artifact_root,
        {"min_confidence": 0.0, "max_confidence": 0.0, "per_symbol": 0, "order_salt": ""},
        reference_policy=arguments.reference_policy,
        references_per_group=arguments.references_per_group,
    )
    library_cache, remaining = _render(
        snapshot.references,
        artifact_root=artifact_root,
        cache_path=cast(Path, arguments.library_cache).resolve(),
        deadline=deadline,
    )
    if remaining:
        print(f"INCOMPLETE: {remaining} crops still to render; run the same command again.")
        return EXIT_INCOMPLETE
    model = snapshot.model
    codes = model.class_codes
    if (
        frozen.get("game", {}).get("code") != arguments.game_code
        or frozen.get("activeModel", {}).get("checkpointSha256") != model.checkpoint_sha256
    ):
        raise EvaluationError(
            "SYMBOL_REFERENCE_FROZEN_CONTEXT_MISMATCH",
            "The frozen sample belongs to another game or active model checkpoint.",
        )
    rows = list(frozen["cells"])
    sample_ids = {str(row["cellReviewId"]) for row in rows}
    # A sample cell verified later in Admin must not vote for itself.
    references = [cell for cell in snapshot.references if cell.id not in sample_ids]
    library = _build_library(references, library_cache, model)
    crops = np.stack(_cached_crops(_load_cache(cast(Path, arguments.blind_cache)), rows))
    shape, hue = descriptor_matrix(list(crops))
    combined = normalize_rows(combined_descriptor(shape, _feature_maps(model, crops), hue))
    proposals = _proposals(
        shape,
        combined,
        library.shape,
        library.combined,
        library.labels,
        class_count=len(codes),
        exclusions=[None] * len(rows),
    )
    rescored = dict(frozen)
    rescored["cells"] = [
        {
            **row,
            "proposal": REVIEW if proposal.class_index is None else codes[proposal.class_index],
            "reason": proposal.reason,
            "shapeVotes": proposal.shape_vote.agreeing_count,
            "combinedVotes": proposal.combined_vote.agreeing_count,
        }
        for row, proposal in zip(rows, proposals, strict=True)
    ]
    changed = sum(
        before["proposal"] != after["proposal"]
        for before, after in zip(rows, rescored["cells"], strict=True)
    )
    comparisons: dict[str, object] = {}
    for ratings_path in cast(list[Path], arguments.ratings):
        ratings: Any = json.loads(ratings_path.read_text(encoding="utf-8"))
        if not isinstance(ratings, Mapping):
            raise EvaluationError("SYMBOL_REFERENCE_RATINGS_INVALID", "Ratings must be an object.")
        # Ratings stay bound to the original freeze; only the proposals are recomputed.
        comparisons[ratings_path.name] = {
            "original": _compare_ratings(frozen, frozen_sha, ratings),
            "rescored": _compare_ratings(rescored, frozen_sha, ratings),
            "reviewHints": _review_hint_accuracy(
                rows, proposals, codes, cast(Mapping[str, Any], ratings.get("ratings", {}))
            ),
        }
    report = {
        "version": RESCORE_VERSION,
        "frozenSha256": frozen_sha,
        "originalReferencePolicy": frozen.get("parameters", {}).get(
            "referencePolicy", "all-human-v1"
        ),
        "referencePolicy": arguments.reference_policy,
        "referencesPerGroup": arguments.references_per_group,
        "cellStateFingerprint": snapshot.fingerprint,
        "library": {
            "cells": len(library.cells),
            "excluded": library.excluded,
            "sampleCellsRemoved": len(snapshot.references) - len(references),
        },
        "changedProposals": changed,
        "rescoredCells": rescored["cells"],
        "comparisons": comparisons,
    }
    output = cast(Path, arguments.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    report_sha = _write_json(output, report)
    for name, value in comparisons.items():
        for variant in ("original", "rescored"):
            result = cast(Mapping[str, Any], cast(Mapping[str, Any], value)[variant])
            print(
                f"{name} {variant}: coverage={result['confidentCoverage']} "
                f"accuracy={result['confidentAccuracy']} gate={result['gate']['passed']}"
            )
    print(f"library={len(library.cells)} changedProposals={changed}")
    print(f"{output.name} sha256={report_sha}")
    return 0


def _review_hint_accuracy(
    rows: Sequence[Mapping[str, Any]],
    proposals: Sequence[Proposal],
    codes: Sequence[str],
    ratings: Mapping[str, Any],
) -> dict[str, object]:
    """How often each hint names the operator's symbol on cells left for review."""

    hits: Counter[str] = Counter()
    cells = 0
    for row, proposal in zip(rows, proposals, strict=True):
        truth = ratings.get(str(row["cellReviewId"]))
        if proposal.class_index is not None or truth not in codes:
            continue
        cells += 1
        fused = [codes[index] for index in hint_candidates(proposal, 2)]
        shape = proposal.shape_vote.class_index
        model = str(row["activeModelSymbol"])
        hits["shape"] += shape is not None and codes[shape] == truth
        hits["fused1"] += fused[:1] == [truth]
        hits["fused2"] += truth in fused
        hits["model"] += model == truth
        hits["fused1OrModel"] += truth in {*fused[:1], model}
    keys = ("fused1", "fused1OrModel", "fused2", "model", "shape")
    return {"cells": cells, **{key: hits[key] for key in keys}}


def _band_bounds(edges: Sequence[float], low: float, high: float) -> list[tuple[float, float]]:
    bounds = [low, *sorted(edges), high]
    return list(zip(bounds, bounds[1:], strict=False))


def _band_label(lower: float, upper: float) -> str:
    return f"{round(lower * 100)}–{round(upper * 100)}%"


def _band(confidence: float, edges: Sequence[float], low: float, high: float) -> str:
    for lower, upper in _band_bounds(edges, low, high):
        if lower <= confidence < upper:
            return _band_label(lower, upper)
    raise EvaluationError("SYMBOL_REFERENCE_BAND_INVALID", f"Confidence {confidence} is outside.")


def _preview_groups(
    rows: Sequence[Mapping[str, Any]], per_group: int
) -> dict[tuple[str, str], list[str]]:
    """Deterministic thumbnail choice per (band, proposal) group."""

    groups: dict[tuple[str, str], list[str]] = {}
    ordered = sorted(
        rows,
        key=lambda row: hashlib.sha256(str(row["cellReviewId"]).encode()).hexdigest(),
    )
    for row in ordered:
        key = (str(row["band"]), str(row["proposal"]))
        members = groups.setdefault(key, [])
        if len(members) < per_group:
            members.append(str(row["cellReviewId"]))
    return dict(sorted(groups.items()))


def _preview_html(payload: Mapping[str, Any]) -> str:
    content = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    template = Path(__file__).with_name("symbol_reference_preview.html").read_text(encoding="utf-8")
    return template.replace("__PAYLOAD__", content)


def _display_confidence(value: float) -> str:
    """Truncate, never round up, so a value below a band edge never shows the edge."""

    return f"{math.floor(value * 100) / 100:.2f}"


PREVIEW_ROWS_CHUNK = 2000


def _preview_rows(
    cells: Sequence[Cell],
    cache: Mapping[str, Mapping[str, Any]],
    library: Library,
    model: ActiveModel,
    *,
    edges: Sequence[float],
    low: float,
    high: float,
) -> list[dict[str, Any]]:
    codes = model.class_codes
    rows: list[dict[str, Any]] = []
    # Resumed runs split cells at the same boundaries, so float32 voting stays bit-identical.
    for start in range(0, len(cells), PREVIEW_ROWS_CHUNK):
        chunk = cells[start : start + PREVIEW_ROWS_CHUNK]
        shape, combined = _descriptors(chunk, cache, model)
        # Batched voting; without exclusions it selects the same neighbours as ``vote``.
        proposals = [
            decide(shape_vote, combined_vote)
            for shape_vote, combined_vote in zip(
                vote_batch(shape, library.shape, library.labels, class_count=len(codes)),
                vote_batch(combined, library.combined, library.labels, class_count=len(codes)),
                strict=True,
            )
        ]
        for cell, proposal in zip(chunk, proposals, strict=True):
            confidence = float(cell.prediction_confidence or 0.0)
            shape_vote = proposal.shape_vote
            rows.append(
                {
                    "cellReviewId": cell.id,
                    "importJobId": cell.import_job_id,
                    "sequenceNumber": cell.sequence_number,
                    "cellIndex": cell.cell_index,
                    "renderedPixelChecksumSha256": cell.rendered_pixel_checksum_sha256,
                    "activeModelSymbol": cell.prediction_symbol_code,
                    "activeModelConfidence": confidence,
                    "band": _band(confidence, edges, low, high),
                    "proposal": REVIEW
                    if proposal.class_index is None
                    else codes[proposal.class_index],
                    "reason": proposal.reason,
                    "shapeHint": None
                    if shape_vote.class_index is None
                    else codes[shape_vote.class_index],
                    "hints": [codes[index] for index in hint_candidates(proposal)],
                    "shapeVotes": shape_vote.agreeing_count,
                    "combinedVotes": proposal.combined_vote.agreeing_count,
                }
            )
    rows.sort(key=lambda row: str(row["cellReviewId"]))
    return rows


def _read_rows_cache(path: Path, key: str) -> Mapping[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # A damaged cache is only a lost shortcut; the rows are recomputed.
        return None
    if not isinstance(value, Mapping) or value.get("key") != key:
        return None
    return cast(Mapping[str, Any], value)


def _cached_preview_rows(path: Path, key: str) -> list[dict[str, Any]] | None:
    """Rows computed by an earlier, interrupted run over exactly the same inputs."""

    value = _read_rows_cache(path, key)
    # Caches written before chunked rows have no ``complete`` flag and are complete.
    if value is None or value.get("complete", True) is not True:
        return None
    return cast(list[dict[str, Any]], value["rows"])


def _partial_preview_rows(path: Path, key: str) -> list[dict[str, Any]]:
    """Rows of the chunks an interrupted run finished; each row depends only on its cell."""

    value = _read_rows_cache(path, key)
    if value is None or value.get("complete", True) is not False:
        return []
    return list(cast(list[dict[str, Any]], value["rows"]))


def _write_rows_cache(path: Path, key: str, rows: list[dict[str, Any]], *, complete: bool) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(_json_bytes({"key": key, "complete": complete, "rows": rows}))
    temporary.replace(path)


def _preview(arguments: argparse.Namespace) -> int:
    low, high = float(arguments.min_confidence), float(arguments.max_confidence)
    # The default 60% edge applies only when it lies inside the requested range.
    edges = sorted(float(edge) for edge in arguments.band_edge) or (
        [0.6] if low < 0.6 < high else []
    )
    if not 0.0 <= low < high <= 1.0001 or any(not low < edge < high for edge in edges):
        raise EvaluationError("SYMBOL_REFERENCE_BAND_INVALID", "The confidence bands are invalid.")
    deadline = time.monotonic() + float(arguments.time_budget_seconds)
    settings = ApiSettings.from_environment()
    artifact_root = (arguments.artifact_root or settings.artifact_root).resolve()
    output = cast(Path, arguments.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    symbol = str(arguments.symbol)
    shard_index, shard_count = arguments.shard
    parameters = {
        "symbols": [symbol],
        "min_confidence": low,
        "max_confidence": high,
        "shard_index": shard_index,
        "shard_count": shard_count,
    }
    snapshot = _read_snapshot(
        settings,
        arguments.game_code,
        artifact_root,
        parameters,
        reference_policy=arguments.reference_policy,
        references_per_group=arguments.references_per_group,
        pending_sql=_PREVIEW_SQL,
        scope_sql=_PREVIEW_SCOPE_SQL,
    )
    if symbol not in snapshot.model.class_codes:
        raise EvaluationError(
            "SYMBOL_REFERENCE_CLASS_UNKNOWN", f"Unknown predicted symbol: {symbol}."
        )
    if not snapshot.pending:
        raise EvaluationError(
            "SYMBOL_REFERENCE_PREVIEW_EMPTY", "No pending cell matches the preview."
        )
    library_cache, remaining = _render(
        snapshot.references,
        artifact_root=artifact_root,
        cache_path=cast(Path, arguments.library_cache).resolve(),
        deadline=deadline,
    )
    cells_cache, cells_remaining = _render(
        snapshot.pending,
        artifact_root=artifact_root,
        cache_path=output / "preview-crops.npz",
        deadline=deadline,
        context_size=0,
    )
    if remaining or cells_remaining:
        print(
            f"INCOMPLETE: {remaining + cells_remaining} of {len(snapshot.pending)} crops "
            "still to render; run the same command again."
        )
        return EXIT_INCOMPLETE

    model = snapshot.model
    codes = model.class_codes
    library = _build_library(snapshot.references, library_cache, model)
    cells, excluded = _usable(snapshot.pending, cells_cache)
    rows_key = digest_json(
        {
            "version": PREVIEW_VERSION,
            "libraryVersion": REFERENCE_LIBRARY_VERSION,
            "fingerprint": snapshot.fingerprint,
            "policy": arguments.reference_policy,
            "checkpoint": model.checkpoint_sha256,
            "bands": [low, *edges, high],
            "library": [_cache_key(cell) for cell in library.cells],
            "cells": [_cache_key(cell) for cell in cells],
        }
    )
    rows_path = output / "preview-rows-cache.json"
    rows = _cached_preview_rows(rows_path, rows_key)
    if rows is None:
        # Descriptors of a large scope do not fit one run; chunks are persisted as they finish
        # so the next run continues, and every run finishes at least one chunk.
        # Partial rows live in their own file, so no reader can take them for the final cache.
        partial_path = output / "preview-rows-partial.json"
        partial = _partial_preview_rows(partial_path, rows_key)
        done = {str(row["cellReviewId"]) for row in partial}
        todo = [cell for cell in cells if str(cell.id) not in done]
        for start in range(0, len(todo), PREVIEW_ROWS_CHUNK):
            if start and time.monotonic() >= deadline:
                break
            partial.extend(
                _preview_rows(
                    todo[start : start + PREVIEW_ROWS_CHUNK],
                    cells_cache,
                    library,
                    model,
                    edges=edges,
                    low=low,
                    high=high,
                )
            )
            _write_rows_cache(partial_path, rows_key, partial, complete=False)
        if len(partial) < len(cells):
            print(
                f"INCOMPLETE: {len(cells) - len(partial)} of {len(cells)} proposals "
                "still to compute; run the same command again."
            )
            return EXIT_INCOMPLETE
        rows = sorted(partial, key=lambda row: str(row["cellReviewId"]))
        # Persist before thumbnails so a resumed run spends its budget on rendering only.
        _write_rows_cache(rows_path, rows_key, rows, complete=True)
        partial_path.unlink(missing_ok=True)
    groups = _preview_groups(rows, int(arguments.thumbnails_per_group))
    thumbnail_ids = {identifier for members in groups.values() for identifier in members}
    by_id = {cell.id: cell for cell in cells}
    context_cache, context_remaining = _render(
        [by_id[identifier] for identifier in sorted(thumbnail_ids)],
        artifact_root=artifact_root,
        cache_path=output / "preview-context.npz",
        deadline=deadline,
        context_size=PREVIEW_CONTEXT_SIZE,
    )
    if context_remaining:
        print(
            f"INCOMPLETE: {context_remaining} thumbnails still to render; "
            "run the same command again."
        )
        return EXIT_INCOMPLETE

    band_order = [_band_label(lower, upper) for lower, upper in _band_bounds(edges, low, high)]
    summary: dict[str, dict[str, int]] = {}
    for row in rows:
        band = summary.setdefault(str(row["band"]), {})
        band[str(row["proposal"])] = band.get(str(row["proposal"]), 0) + 1
    ordered_summary = {
        band: dict(sorted(summary[band].items())) for band in band_order if band in summary
    }
    report = {
        "version": PREVIEW_VERSION,
        "libraryVersion": REFERENCE_LIBRARY_VERSION,
        "referencePolicy": arguments.reference_policy,
        "game": {"id": snapshot.game_id, "code": arguments.game_code, "name": snapshot.game_name},
        "activeModel": {
            "iterationId": model.iteration_id,
            "checkpointSha256": model.checkpoint_sha256,
        },
        "cellStateFingerprint": snapshot.fingerprint,
        "parameters": {
            "symbol": symbol,
            "minConfidence": low,
            "maxConfidence": high,
            "bandEdges": edges,
            "thumbnailsPerGroup": int(arguments.thumbnails_per_group),
            "referencesPerGroup": arguments.references_per_group,
            # Only sharded runs carry the key, so unsharded revision checksums stay as before.
            **({"shard": f"{shard_index}/{shard_count}"} if shard_count > 1 else {}),
        },
        "library": {"cells": len(library.cells), "excluded": library.excluded},
        "libraryIdentitySha256": _library_identity(arguments, model, library),
        "cells": len(rows),
        "excluded": excluded,
        "notInScope": snapshot.not_in_scope,
        "summary": ordered_summary,
        "rows": rows,
    }
    report_sha = _write_json(output / "preview.json", report)

    names = {code: snapshot.symbol_names.get(code, code) for code in codes}
    names[REVIEW] = "Do przeglądu"
    thumbnails: dict[str, dict[str, str]] = {}
    row_by_id = {str(row["cellReviewId"]): row for row in rows}
    for identifier in sorted(thumbnail_ids):
        entry = context_cache[_cache_key(by_id[identifier])]
        row = row_by_id[identifier]
        thumbnails[identifier] = {
            "crop": _crop_uri(entry["crop"], 96),
            "context": _context_uri(entry["context"], entry["context_quad"]),
            "confidence": _display_confidence(float(row["activeModelConfidence"])),
            "votes": f"{row['shapeVotes']}/{row['combinedVotes']}",
            "hint": " / ".join(names.get(code, code) for code in row["hints"]) or "–",
        }
    page = _preview_html(
        {
            "title": f"{snapshot.game_name}: {names[symbol]}",
            "names": names,
            "predicted": symbol,
            "summary": ordered_summary,
            "groups": [
                {"band": band, "proposal": proposal, "ids": members}
                for (band, proposal), members in groups.items()
            ],
            "thumbnails": thumbnails,
            "library": len(library.cells),
            "policy": arguments.reference_policy,
            "excluded": excluded,
            "notInScope": snapshot.not_in_scope,
            "reportSha256": report_sha,
        }
    )
    (output / "preview.html").write_text(page, encoding="utf-8")
    print(f"cells={len(rows)} excluded={excluded} notInScope={snapshot.not_in_scope}")
    print(f"library={len(library.cells)}")
    for band_label, counts in ordered_summary.items():
        print(band_label, counts)
    print(f"preview.json sha256={report_sha}")
    print(f"preview.html -> {output / 'preview.html'}")
    return 0


APPLY_MANIFEST_FORMAT = "symbol-reference-apply-manifest-v1"
APPLY_BATCH = 1000


def _library_identity(arguments: argparse.Namespace, model: ActiveModel, library: Library) -> str:
    return digest_json(
        {
            "version": REFERENCE_LIBRARY_VERSION,
            "writerModelVersion": WRITER_MODEL_VERSION,
            "policy": arguments.reference_policy,
            "referencesPerGroup": arguments.references_per_group,
            "checkpoint": model.checkpoint_sha256,
            "library": [_cache_key(cell) for cell in library.cells],
        }
    )


def _chunks(values: Sequence[str], size: int) -> list[list[str]]:
    return [list(values[start : start + size]) for start in range(0, len(values), size)]


def _apply_preview(arguments: argparse.Namespace) -> int:
    result = _preview(arguments)
    if result != 0:
        return result
    output = cast(Path, arguments.output_dir).resolve()
    preview: Any = json.loads((output / "preview.json").read_text(encoding="utf-8"))
    targets = {
        str(row["cellReviewId"]): row for row in preview["rows"] if row["proposal"] != REVIEW
    }
    settings = ApiSettings.from_environment()
    engine = create_maintenance_database_engine(settings)
    cells: dict[str, Mapping[str, Any]] = {}
    latest: dict[str, Mapping[str, Any]] = {}
    try:
        with engine.connect().execution_options(
            isolation_level="REPEATABLE READ", postgresql_readonly=True
        ) as connection:
            game_id = str(preview["game"]["id"])
            fingerprint = _cell_state_fingerprint(connection, game_id)
            for chunk in _chunks(sorted(targets), APPLY_BATCH):
                for row in connection.execute(
                    text(
                        """
                        SELECT c.id::text AS id, c.review_item_id::text AS review_item_id,
                               c.recognized_board_id::text AS recognized_board_id,
                               c.prediction_revision_id::text AS prediction_revision_id,
                               c.cell_index, c.review_state, c.assignment_source,
                               c.quality_issue, c.prediction_symbol_code,
                               c.rendered_pixel_checksum_sha256
                        FROM game_data_v2.image_symbol_review_cells c
                        WHERE c.game_id = :game_id AND c.id = ANY(CAST(:ids AS uuid[]))
                        """
                    ),
                    {"game_id": game_id, "ids": chunk},
                ).mappings():
                    cells[str(row["id"])] = dict(row)
            items = sorted({str(cell["review_item_id"]) for cell in cells.values()})
            for chunk in _chunks(items, APPLY_BATCH):
                for row in connection.execute(
                    text(
                        """
                        SELECT DISTINCT ON (p.review_item_id)
                               p.review_item_id::text AS review_item_id, p.id::text AS id,
                               p.model_version, p.predictions
                        FROM game_data_v2.image_symbol_prediction_revisions p
                        WHERE p.game_id = :game_id AND p.review_item_id = ANY(CAST(:ids AS uuid[]))
                        ORDER BY p.review_item_id, p.created_at DESC, p.id DESC
                        """
                    ),
                    {"game_id": game_id, "ids": chunk},
                ).mappings():
                    latest[str(row["review_item_id"])] = dict(row)
    finally:
        engine.dispose()
    if fingerprint != preview["cellStateFingerprint"]:
        raise EvaluationError(
            "SYMBOL_REFERENCE_APPLY_STATE_DRIFT",
            "Cell state changed between the preview and the manifest; run apply-preview again.",
        )

    excluded: Counter[str] = Counter()
    boards: dict[str, dict[str, Any]] = {}
    moves: Counter[str] = Counter()
    for cell_id, row in sorted(targets.items()):
        cell = cells.get(cell_id)
        revision = None if cell is None else latest.get(str(cell["review_item_id"]))
        if cell is None:
            excluded["cell_missing"] += 1
        elif cell["review_state"] != "pending":
            excluded["not_pending"] += 1
        elif cell["assignment_source"] != "model":
            excluded["assignment_not_model"] += 1
        elif cell["quality_issue"] is not None:
            excluded["quality_issue"] += 1
        elif revision is None or revision["id"] != cell["prediction_revision_id"]:
            excluded["revision_not_current"] += 1
        elif cell["rendered_pixel_checksum_sha256"] != row["renderedPixelChecksumSha256"]:
            excluded["pixels_changed"] += 1
        elif cell["prediction_symbol_code"] != row["activeModelSymbol"]:
            excluded["prediction_changed"] += 1
        elif _entry_for_cell(revision["predictions"], int(cell["cell_index"])).get(
            "referenceLibrary"
        ):
            excluded["already_library_prediction"] += 1
        else:
            item_id = str(cell["review_item_id"])
            board = boards.setdefault(
                item_id,
                {
                    "reviewItemId": item_id,
                    "recognizedBoardId": str(cell["recognized_board_id"]),
                    "predictionRevisionId": str(revision["id"]),
                    "predictionsSha256": predictions_digest(revision["predictions"]),
                    "targets": [],
                },
            )
            board["targets"].append(
                {
                    "cellReviewId": cell_id,
                    "cellIndex": int(cell["cell_index"]),
                    "renderedPixelChecksumSha256": row["renderedPixelChecksumSha256"],
                    "oldSymbol": row["activeModelSymbol"],
                    "newSymbol": row["proposal"],
                    "shapeVotes": row["shapeVotes"],
                    "combinedVotes": row["combinedVotes"],
                }
            )
            moves[f"{row['activeModelSymbol']}->{row['proposal']}"] += 1
    # The revision checksum identifies this run: library and scope. A later run with another
    # scope writes its own revision on top of this one instead of looking already applied.
    revision_checksum = digest_json(
        {
            "libraryIdentitySha256": preview["libraryIdentitySha256"],
            "parameters": preview["parameters"],
            "referencePolicy": preview["referencePolicy"],
        }
    )
    manifest = {
        "format": APPLY_MANIFEST_FORMAT,
        # TASK-0794: ``predictionsSha256`` is the v2 digest (slim projection);
        # manifests without this field carry v1 digests, which ``apply`` and
        # ``apply-revert`` still accept through ``legacy_predictions_sha256``.
        "predictionsDigestVersion": PREDICTIONS_DIGEST_VERSION,
        "writerModelVersion": WRITER_MODEL_VERSION,
        "revisionChecksumSha256": revision_checksum,
        "game": preview["game"],
        "previewSha256": hashlib.sha256((output / "preview.json").read_bytes()).hexdigest(),
        "libraryIdentitySha256": preview["libraryIdentitySha256"],
        "referencePolicy": preview["referencePolicy"],
        "parameters": preview["parameters"],
        "cellStateFingerprint": fingerprint,
        "targets": sum(len(board["targets"]) for board in boards.values()),
        "moves": dict(sorted(moves.items())),
        "excluded": dict(sorted(excluded.items())),
        "boards": [boards[key] for key in sorted(boards)],
    }
    manifest_sha = _write_json(output / "apply-manifest.json", manifest)
    print(f"boards={len(boards)} targets={manifest['targets']} excluded={manifest['excluded']}")
    print(f"moves={manifest['moves']}")
    print(f"apply-manifest.json sha256={manifest_sha}")
    return 0


def _entry_for_cell(predictions: Sequence[Mapping[str, Any]], cell_index: int) -> Mapping[str, Any]:
    for entry in predictions:
        if int(entry.get("rowIndex", -1)) * 5 + int(entry.get("columnIndex", -1)) == cell_index:
            return entry
    return {}


def _read_manifest(path: Path, expected_sha256: str) -> dict[str, Any]:
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != expected_sha256:
        raise EvaluationError(
            "SYMBOL_REFERENCE_APPLY_MANIFEST_MISMATCH",
            "The manifest differs from the approved checksum.",
        )
    manifest: Any = json.loads(content)
    if (
        not isinstance(manifest, Mapping)
        or manifest.get("format") != APPLY_MANIFEST_FORMAT
        or not isinstance(manifest.get("revisionChecksumSha256"), str)
    ):
        raise EvaluationError("SYMBOL_REFERENCE_APPLY_MANIFEST_INVALID", "Unknown manifest.")
    return dict(manifest)


def _board_plan(board: Mapping[str, Any]) -> BoardPlan:
    return BoardPlan(
        review_item_id=UUID(str(board["reviewItemId"])),
        recognized_board_id=UUID(str(board["recognizedBoardId"])),
        prediction_revision_id=UUID(str(board["predictionRevisionId"])),
        predictions_sha256=str(board["predictionsSha256"]),
        targets=tuple(
            TargetCell(
                cell_review_id=UUID(str(target["cellReviewId"])),
                cell_index=int(target["cellIndex"]),
                rendered_pixel_checksum_sha256=str(target["renderedPixelChecksumSha256"]),
                old_symbol=str(target["oldSymbol"]),
                new_symbol=str(target["newSymbol"]),
                shape_votes=int(target["shapeVotes"]),
                combined_votes=int(target["combinedVotes"]),
            )
            for target in board["targets"]
        ),
    )


def _done(receipts: Mapping[str, str]) -> set[str]:
    """Boards whose last receipt is final; a failed board is retried by the next run."""

    return {board for board, status in receipts.items() if not status.startswith("failed")}


def _receipts(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            result[str(value["reviewItemId"])] = str(value["status"])
    return result


def _apply(arguments: argparse.Namespace, *, revert: bool = False) -> int:
    deadline = time.monotonic() + float(arguments.time_budget_seconds)
    manifest_path = cast(Path, arguments.manifest).resolve()
    manifest = _read_manifest(manifest_path, str(arguments.expected_sha256))
    if manifest["game"]["code"] != arguments.game_code:
        raise EvaluationError("SYMBOL_REFERENCE_APPLY_GAME_MISMATCH", "Wrong game code.")
    prefix = "revert-receipts" if revert else "apply-receipts"
    receipts_path = manifest_path.with_name(f"{prefix}-{str(arguments.expected_sha256)[:12]}.jsonl")
    write_board = revert_board if revert else apply_board
    if revert and not arguments.board and not arguments.all:
        raise EvaluationError(
            "SYMBOL_REFERENCE_REVERT_SCOPE_REQUIRED",
            "Name the boards to revert with --board, or pass --all to revert the whole run.",
        )
    done = _done(_receipts(receipts_path))
    pending = [board for board in manifest["boards"] if board["reviewItemId"] not in done]
    if arguments.board:
        selected = set(arguments.board)
        unknown = selected - {str(board["reviewItemId"]) for board in manifest["boards"]}
        if unknown:
            raise EvaluationError(
                "SYMBOL_REFERENCE_APPLY_BOARD_UNKNOWN",
                f"Boards not in the manifest: {', '.join(sorted(unknown))}.",
            )
        pending = [board for board in pending if board["reviewItemId"] in selected]
    if arguments.limit_boards is not None:
        pending = pending[: int(arguments.limit_boards)]
    game_id = UUID(str(manifest["game"]["id"]))
    engine = create_maintenance_database_engine(ApiSettings.from_environment())
    session_factory = create_session_factory(engine)
    counts: Counter[str] = Counter()
    processed = 0
    try:
        with receipts_path.open("a", encoding="utf-8") as receipts:
            for board in pending:
                if time.monotonic() >= deadline:
                    break
                plan = _board_plan(board)
                try:
                    with (
                        game_storage_scope(game_id),
                        session_factory() as session,
                        session.begin(),
                    ):
                        status = write_board(
                            session,
                            game_id=game_id,
                            plan=plan,
                            library_checksum_sha256=str(manifest["revisionChecksumSha256"]),
                        )
                except (ReferenceLibraryWriteError, DBAPIError) as error:
                    code = getattr(error, "code", None) or type(error).__name__
                    skippable = (
                        isinstance(error, ReferenceLibraryWriteError)
                        and error.code == TARGET_QUALITY_CHANGED
                        # A revert that cannot finish must stop: the library prediction stays.
                        and not revert
                    )
                    if not skippable:
                        # A failed board stays retryable; the transaction has rolled back.
                        receipts.write(
                            json.dumps(
                                {"reviewItemId": board["reviewItemId"], "status": f"failed:{code}"}
                            )
                            + "\n"
                        )
                        receipts.flush()
                        print(f"FAILED {board['reviewItemId']}: {error}", file=sys.stderr)
                        return 2
                    # Rolled back; the target is no longer eligible, so the board is stale.
                    print(f"SKIPPED {board['reviewItemId']}: {error}", file=sys.stderr)
                    status = f"stale:{code}"
                receipts.write(
                    json.dumps({"reviewItemId": board["reviewItemId"], "status": status}) + "\n"
                )
                receipts.flush()
                counts[status] += 1
                processed += 1
    finally:
        engine.dispose()
    receipts_now = _receipts(receipts_path)
    done = _done(receipts_now)
    remaining = sum(1 for board in manifest["boards"] if board["reviewItemId"] not in done)
    totals = Counter(receipts_now.values())
    print(f"this run={dict(counts)} total={dict(sorted(totals.items()))} remaining={remaining}")
    if remaining and arguments.limit_boards is None and not arguments.board:
        print("INCOMPLETE: run the same command again.")
        return EXIT_INCOMPLETE
    return 0


def _apply_verify(arguments: argparse.Namespace) -> int:
    manifest_path = cast(Path, arguments.manifest).resolve()
    manifest = _read_manifest(manifest_path, str(arguments.expected_sha256))
    game_id = str(manifest["game"]["id"])
    targets = {
        str(target["cellReviewId"]): target
        for board in manifest["boards"]
        for target in board["targets"]
    }
    states: Counter[str] = Counter()
    reverted_checksum = revert_checksum(str(manifest["revisionChecksumSha256"]))
    engine = create_maintenance_database_engine(ApiSettings.from_environment())
    try:
        with engine.connect().execution_options(postgresql_readonly=True) as connection:
            for chunk in _chunks(sorted(targets), APPLY_BATCH):
                for row in connection.execute(
                    text(
                        """
                        SELECT c.id::text AS id, c.review_state, c.assignment_source,
                               c.prediction_symbol_code, p.model_version,
                               p.model_checksum_sha256
                        FROM game_data_v2.image_symbol_review_cells c
                        LEFT JOIN game_data_v2.image_symbol_prediction_revisions p
                          ON p.id = c.prediction_revision_id
                        WHERE c.game_id = :game_id AND c.id = ANY(CAST(:ids AS uuid[]))
                        """
                    ),
                    {"game_id": game_id, "ids": chunk},
                ).mappings():
                    target = targets[str(row["id"])]
                    if row["review_state"] != "pending":
                        states["decided_by_operator"] += 1
                    elif row["model_version"] == WRITER_MODEL_VERSION and str(
                        row["model_checksum_sha256"]
                    ) != str(manifest["revisionChecksumSha256"]):
                        states["other_library_run"] += 1
                    elif (
                        row["model_version"] == WRITER_MODEL_VERSION
                        and row["prediction_symbol_code"] == target["newSymbol"]
                    ):
                        states["library_prediction"] += 1
                    elif row["model_checksum_sha256"] == reverted_checksum:
                        states["reverted"] += 1
                    elif row["prediction_symbol_code"] == target["oldSymbol"]:
                        states["unchanged"] += 1
                    else:
                        states["other"] += 1
    finally:
        engine.dispose()
    receipts = _receipts(
        manifest_path.with_name(f"apply-receipts-{str(arguments.expected_sha256)[:12]}.jsonl")
    )
    reverts = _receipts(
        manifest_path.with_name(f"revert-receipts-{str(arguments.expected_sha256)[:12]}.jsonl")
    )
    report = {
        "manifestSha256": arguments.expected_sha256,
        "targets": len(targets),
        "cellStates": dict(sorted(states.items())),
        "boardReceipts": dict(sorted(Counter(receipts.values()).items())),
        "revertReceipts": dict(sorted(Counter(reverts.values()).items())),
    }
    report_sha = _write_json(manifest_path.with_name("apply-verify.json"), report)
    print(json.dumps(report, sort_keys=True))
    print(f"apply-verify.json sha256={report_sha}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parse_args(argv)
    try:
        if arguments.command == "evaluate":
            return _evaluate(arguments)
        if arguments.command == "blind-sample":
            return _blind_sample(arguments)
        if arguments.command == "compare":
            return _compare(arguments)
        if arguments.command == "blind-rescore":
            return _blind_rescore(arguments)
        if arguments.command == "preview":
            return _preview(arguments)
        if arguments.command == "apply-preview":
            return _apply_preview(arguments)
        if arguments.command == "apply":
            return _apply(arguments)
        if arguments.command == "apply-revert":
            return _apply(arguments, revert=True)
        if arguments.command == "apply-verify":
            return _apply_verify(arguments)
    except EvaluationError as error:
        print(str(error), file=sys.stderr)
        return 2
    raise AssertionError(arguments.command)


if __name__ == "__main__":
    raise SystemExit(main())
