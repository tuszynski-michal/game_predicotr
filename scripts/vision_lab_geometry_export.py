"""Read-only export of the production geometry of one game to a candidate manifest (TASK-0800).

For every live board of every source image whose persisted gate state is
``geometry_complete`` the export writes one JSON Lines row: identifiers, the image
checksum and path, oriented size, the label level (G/S/B/U), the 24 grid nodes in
exif-normalized pixels, the partial-board mask, the source family, symbol-filter
signals and difficulty metrics. Boards and images that are not candidates are
counted and listed with a reason; one bad board never stops the export.

The command never writes to the database. It reads in short
``REPEATABLE READ READ ONLY`` transactions, one batch of images per transaction,
bound to the game, with the owner role of ``vision_lab_export.py``. It copies no
image and writes only into its own directory under ``--output-root``. An
interrupted export resumes from its progress file without duplicating rows.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from collections import Counter, deque
from collections.abc import Iterator, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from game_predictor_api.domain.image_geometry_completeness import (
    DEFAULT_LOW_QUALITY_MAX_CONFIDENCE,
)
from game_predictor_worker.vision_lab import production_geometry as geometry
from sqlalchemy import Connection, Engine, create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vision_lab_export as _base  # noqa: E402  (sibling script, same read-only transaction setup)

EXPORTER_VERSION = "vision-lab-geometry-export-v1"
CANDIDATE_SCHEMA = "production-geometry-candidate-v1"
REPORT_SCHEMA = "production-geometry-report-v1"
DEFAULT_BATCH_IMAGES = 100
DEFAULT_WORKERS = 4
_STATEMENT_TIMEOUT_MS = 60_000
_TRANSACTION_TIMEOUT_MS = 120_000
_SOURCE_REVISION_MISSING = "SOURCE_GEOMETRY_REVISION_MISSING"
_CANDIDATES = "candidates.jsonl"
_EXCLUSIONS = "exclusions.jsonl"
_IMAGE_IDS = "image_ids.txt"
_PROGRESS = "progress.json"
_REPORT = "report.json"
_MANIFEST = "export_manifest.json"

_IMAGE_LIST_SQL = text(
    """
SELECT s.id FROM source_images s
WHERE s.game_id = :game_id AND s.geometry_completeness_status = 'geometry_complete'
ORDER BY s.id
LIMIT :limit
"""
)

_IMAGES_SQL = text(
    """
SELECT s.id, s.import_job_id, s.relative_path, s.checksum_sha256, s.status,
  COALESCE(s.oriented_width, s.width) AS width,
  COALESCE(s.oriented_height, s.height) AS height,
  (SELECT r.active_board_slots
     FROM image_source_geometry_revisions r
     WHERE r.game_id = :game_id AND r.source_image_id = s.id
     ORDER BY r.revision DESC LIMIT 1) AS active_board_slots
FROM source_images s
WHERE s.game_id = :game_id AND s.id = ANY (:ids)
  AND s.geometry_completeness_status = 'geometry_complete'
ORDER BY s.id
"""
)

# One row per live board of the batch images. Only the pieces the export needs are
# extracted server-side: the quads of the source-revision entry, the revision
# authors and the (index, quad) pairs of the render manifest.
_BOARDS_SQL = text(
    """
WITH bx AS (
  SELECT b.id, b.source_image_id, b.position_index, b.sequence_number, b.status,
    b.completeness_status, b.unavailable_cell_indices, b.geometry_qualification,
    b.geometry_revision, b.approved_geometry_revision, b.geometry_approved_by,
    b.geometry_approved_at, b.grid_rows, b.grid_columns, b.geometry_engine_name,
    b.geometry_engine_version, b.geometry_checksum_sha256, b.source_geometry_revision_id,
    b.board_geometry -> 'symbolGridQuad' AS board_symbol_grid_quad,
    p.id AS source_revision_id, p.revision AS source_revision, p.status AS source_status,
    p.geometry_source AS source_geometry_source, p.created_by AS source_created_by,
    p.engine_kind AS source_engine_kind, p.engine_version AS source_engine_version,
    jsonb_path_query_first(
      p.board_geometries, '$[*] ? (@.positionIndex == $position)',
      jsonb_build_object('position', b.position_index)) AS source_entry
  FROM recognized_boards b
  LEFT JOIN image_source_geometry_revisions p
    ON p.game_id = b.game_id AND p.id = b.source_geometry_revision_id
  WHERE b.game_id = :game_id AND b.source_image_id = ANY (:image_ids) AND b.status <> 'rejected'
)
SELECT bx.id, bx.source_image_id, bx.position_index, bx.sequence_number, bx.status,
  bx.completeness_status, bx.unavailable_cell_indices, bx.geometry_qualification,
  bx.geometry_revision, bx.approved_geometry_revision, bx.geometry_approved_by,
  bx.geometry_approved_at, bx.grid_rows, bx.grid_columns, bx.geometry_engine_name,
  bx.geometry_engine_version, bx.geometry_checksum_sha256, bx.board_symbol_grid_quad,
  bx.source_revision_id, bx.source_revision, bx.source_status, bx.source_geometry_source,
  bx.source_created_by, bx.source_engine_kind, bx.source_engine_version,
  bx.source_entry -> 'symbolGridQuad' AS source_symbol_grid_quad,
  bx.source_entry -> 'finalQuad' AS source_final_quad,
  rv.corners AS revision_corners,
  (SELECT jsonb_agg(jsonb_build_array(rr.revision, rr.corrected_by) ORDER BY rr.revision)
     FROM image_board_geometry_revisions rr
     WHERE rr.game_id = :game_id AND rr.recognized_board_id = bx.id
       AND rr.revision <= bx.geometry_revision) AS revision_authors,
  m.recognized_board_id IS NOT NULL AS manifest_present,
  m.extractor_version AS manifest_extractor_version,
  m.cells -> 'cells' -> 0 -> 'renderSpec' -> 'topology' AS manifest_topology,
  m.cells -> 'cells' -> 0 -> 'renderSpec' ->> 'coordinateSpace' AS manifest_coordinate_space,
  jsonb_path_query_array(m.cells, '$.cells[*].cellIndex') AS manifest_cell_indices,
  jsonb_path_query_array(m.cells, '$.cells[*].renderSpec.sourceQuad') AS manifest_cell_quads
FROM bx
LEFT JOIN image_board_geometry_revisions rv
  ON rv.game_id = :game_id AND rv.recognized_board_id = bx.id AND rv.revision = bx.geometry_revision
LEFT JOIN board_render_manifests m
  ON m.game_id = :game_id AND m.recognized_board_id = bx.id
  AND m.geometry_revision = bx.geometry_revision
ORDER BY bx.source_image_id, bx.position_index
"""
)

# Same low-quality definition as the completeness report (TASK-0806): a pending
# cell whose source is available (or outside) with a prediction at or below the
# threshold.
_CELLS_SQL = text(
    """
SELECT c.recognized_board_id,
  count(*) AS cells,
  count(*) FILTER (WHERE c.review_state = 'approved') AS human_decided_cells,
  count(*) FILTER (
    WHERE c.review_state = 'pending' AND (c.source_available OR c.source_visibility = 'outside')
      AND c.prediction_confidence <= :max_confidence) AS low_quality_cells,
  min(c.prediction_confidence) FILTER (
    WHERE c.review_state = 'pending' AND (c.source_available OR c.source_visibility = 'outside')
      AND c.prediction_confidence <= :max_confidence) AS min_low_quality_confidence,
  min(c.prediction_confidence) AS min_prediction_confidence,
  count(*) FILTER (WHERE c.prediction_confidence IS NULL) AS cells_without_prediction,
  count(*) FILTER (
    WHERE c.review_state <> 'approved'
      AND (c.prediction_confidence IS NULL OR c.prediction_confidence <= :max_confidence)
  ) AS cells_below_filter,
  count(*) FILTER (WHERE NOT c.source_available) AS source_unavailable_cells,
  count(*) FILTER (WHERE c.geometry_revision <> b.geometry_revision) AS other_revision_cells
FROM image_symbol_review_cells c
JOIN recognized_boards b ON b.game_id = :game_id AND b.id = c.recognized_board_id
WHERE c.game_id = :game_id AND c.recognized_board_id = ANY (:board_ids)
GROUP BY c.recognized_board_id
"""
)

_JOBS_SQL = text(
    """
SELECT j.id, j.input_payload ->> 'source_display_name' AS display_name,
  j.input_payload ->> 'source_directory' AS source_directory,
  j.input_payload ->> 'previous_job_id' AS previous_job_id
FROM jobs j
WHERE j.game_id = :game_id AND j.id = ANY (:job_ids)
"""
)

_UNIVERSE_SQL = {
    "imagesByGateStatus": text(
        """
SELECT s.geometry_completeness_status AS status,
  s.geometry_completeness_evaluated_at IS NOT NULL AS evaluated, count(*) AS n
FROM source_images s WHERE s.game_id = :game_id GROUP BY 1, 2 ORDER BY 1, 2
"""
    ),
    "boardsByStatus": text(
        """
SELECT b.status, count(*) AS n FROM recognized_boards b
WHERE b.game_id = :game_id GROUP BY 1 ORDER BY 1
"""
    ),
    "liveBoardsByImageGateStatus": text(
        """
SELECT s.geometry_completeness_status AS status, count(*) AS n
FROM recognized_boards b
JOIN source_images s ON s.game_id = b.game_id AND s.id = b.source_image_id
WHERE b.game_id = :game_id AND b.status <> 'rejected' GROUP BY 1 ORDER BY 1
"""
    ),
    "rejectedBoardsOnCompleteImages": text(
        """
SELECT count(*) AS n FROM recognized_boards b
JOIN source_images s ON s.game_id = b.game_id AND s.id = b.source_image_id
WHERE b.game_id = :game_id AND b.status = 'rejected'
  AND s.geometry_completeness_status = 'geometry_complete'
"""
    ),
}


# --- original production output (TASK-0804) -----------------------------------------------

ORIGINALS_SCHEMA = "production-original-v1"
ORIGINALS_REPORT_SCHEMA = "production-originals-report-v1"
_ORIGINALS = "production-originals.jsonl"
_ORIGINALS_INPUT = "input_image_ids.txt"

_ORIGINAL_IMAGES_SQL = text(
    """
SELECT s.id, s.checksum_sha256,
  COALESCE(s.oriented_width, s.width) AS width,
  COALESCE(s.oriented_height, s.height) AS height
FROM source_images s
WHERE s.game_id = :game_id AND s.id = ANY (:ids)
"""
)

_ORIGINAL_REVISIONS_SQL = text(
    """
SELECT r.id, r.source_image_id, r.revision, r.geometry_source, r.engine_kind, r.engine_version,
  r.status, r.created_by, r.created_at, r.coordinate_space, r.source_checksum_sha256,
  r.oriented_width, r.oriented_height, r.active_board_slots, r.warnings, r.processing_time_ms
FROM image_source_geometry_revisions r
WHERE r.game_id = :game_id AND r.source_image_id = ANY (:ids)
ORDER BY r.source_image_id, r.revision
"""
)

_ORIGINAL_ENTRIES_SQL = text(
    """
SELECT r.id AS revision_id, e -> 'positionIndex' AS position_index,
  e -> 'sequenceNumber' AS sequence_number, e -> 'symbolGridQuad' AS symbol_grid_quad,
  e ->> 'disposition' AS disposition, e ->> 'localLatticeStatus' AS lattice_status,
  e -> 'reasonCodes' AS reason_codes, e -> 'geometryConfidence' AS geometry_confidence
FROM image_source_geometry_revisions r, jsonb_array_elements(r.board_geometries) e
WHERE r.game_id = :game_id AND r.id = ANY (:revision_ids)
"""
)

# Render manifests that were cut from the original revision at board geometry revision 0
# (the engine grid itself, when the board was ever materialized from it): an independent
# check that the stored grid quad is the grid the engine produced.
_ORIGINAL_MANIFESTS_SQL = text(
    """
SELECT m.source_geometry_revision_id AS revision_id, b.position_index,
  jsonb_path_query_array(m.cells, '$.cells[*].cellIndex') AS cell_indices,
  jsonb_path_query_array(m.cells, '$.cells[*].renderSpec.sourceQuad') AS cell_quads
FROM board_render_manifests m
JOIN recognized_boards b ON b.game_id = m.game_id AND b.id = m.recognized_board_id
WHERE m.game_id = :game_id AND m.source_geometry_revision_id = ANY (:revision_ids)
  AND m.geometry_revision = 0
"""
)


class GeometryExportError(RuntimeError):
    """The export cannot continue without losing or duplicating evidence."""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@contextmanager
def _batch_transaction(
    engine: Engine, game_id: UUID, expected_generation: int | None
) -> Iterator[Connection]:
    """A short read-only transaction bound to the game (see ``vision_lab_export``)."""

    with _base._read_transaction(engine, game_id, expected_generation) as connection:
        connection.execute(
            text("SELECT set_config('statement_timeout', :timeout, true)"),
            {"timeout": str(_STATEMENT_TIMEOUT_MS)},
        )
        connection.execute(
            text("SELECT set_config('idle_in_transaction_session_timeout', :timeout, true)"),
            {"timeout": str(_TRANSACTION_TIMEOUT_MS)},
        )
        if connection.exec_driver_sql("SHOW transaction_read_only").scalar_one() != "on":
            raise GeometryExportError("The export transaction is not read-only")
        yield connection


def _round_point(point: geometry.Point) -> list[float]:
    return [round(point[0], 4), round(point[1], 4)]


def _source_directory_id(source_directory: str | None) -> str | None:
    """Last path component of the import's source directory (a browser selection id)."""

    if not source_directory:
        return None
    parts = [part for part in source_directory.replace("\\", "/").split("/") if part]
    return parts[-1] if parts else None


def _family(job_id: UUID, job: Mapping[str, Any] | None) -> dict[str, Any]:
    """Source family of an import: the browser-selection directory, else the job.

    Source images are content-addressed (``originals/xx/<sha>.jpg``), so the
    original recording file or folder is not stored per image. The import job
    records the selection directory and a display name naming the cut of the
    recording; two jobs that imported the same directory are one family.
    """

    directory = _source_directory_id(job["source_directory"]) if job else None
    return {
        "familyId": f"selection:{directory}" if directory else f"job:{job_id}",
        "familyBasis": "import_source_directory" if directory else "import_job",
        "importJobId": str(job_id),
        "sourceDisplayName": job["display_name"] if job else None,
        "sourceDirectoryId": directory,
        "previousJobId": job["previous_job_id"] if job else None,
    }


def _manifest_cells(indices: object, quads: object) -> dict[int, geometry.Quad]:
    """Cell index -> stored source quad; the two arrays come from one document walk."""

    if not isinstance(indices, list) or not indices or not isinstance(quads, list):
        raise geometry.ProductionGeometryError(
            geometry.EXCLUSION_MANIFEST_MALFORMED, "the manifest has no cell list"
        )
    if len(indices) != len(quads):
        raise geometry.ProductionGeometryError(
            geometry.EXCLUSION_MANIFEST_MALFORMED, "a manifest cell has no source quad"
        )
    cells: dict[int, geometry.Quad] = {}
    for index, raw in zip(indices, quads, strict=True):
        quad = geometry.parse_quad(raw)
        if isinstance(index, bool) or not isinstance(index, int) or quad is None or index in cells:
            raise geometry.ProductionGeometryError(
                geometry.EXCLUSION_MANIFEST_MALFORMED, "a manifest cell is invalid or repeated"
            )
        cells[index] = quad
    return cells


def _candidate_quads(board: Mapping[str, Any]) -> list[geometry.QuadCandidate]:
    """Stored quads that may be the grid quad, most specific first.

    ``revision_corners`` are the corners the manual save of the current board
    revision rendered; the source-entry ``symbolGridQuad`` is the grid of an
    engine/imported revision; ``finalQuad`` is the entry's frame quad. The manifest
    decides which of them is the rendered grid (``derive_consistent_nodes``).
    """

    candidates: list[geometry.QuadCandidate] = []
    for source, raw in (
        ("board_revision_corners", board["revision_corners"]),
        ("source_revision_symbol_grid_quad", board["source_symbol_grid_quad"]),
        ("board_symbol_grid_quad", board["board_symbol_grid_quad"]),
        ("source_revision_final_quad", board["source_final_quad"]),
    ):
        quad = geometry.parse_quad(raw)
        if quad is not None:
            candidates.append(geometry.QuadCandidate(source, quad))
    return candidates


def _qualification(board: Mapping[str, Any]) -> dict[str, Any] | None:
    raw = board["geometry_qualification"]
    if not isinstance(raw, Mapping):
        return None
    return {
        "version": raw.get("version"),
        "excludeFromGeometryTraining": raw.get("excludeFromGeometryTraining"),
        "includeInPartialGridTraining": raw.get("includeInPartialGridTraining"),
        "exclusionReason": raw.get("exclusionReason"),
        "fullyUnavailableCellIndices": raw.get("fullyUnavailableCellIndices"),
    }


def _build_row(
    game_id: UUID,
    image: Mapping[str, Any],
    board: Mapping[str, Any],
    cells: Mapping[str, Any] | None,
    family: Mapping[str, Any],
) -> dict[str, Any]:
    """The candidate row of one board, or ``ProductionGeometryError`` (exclusion)."""

    if board["source_revision_id"] is None:
        raise geometry.ProductionGeometryError(_SOURCE_REVISION_MISSING, "no source revision")
    slots = image["active_board_slots"] or []
    if board["position_index"] not in slots:
        raise geometry.ProductionGeometryError(
            geometry.EXCLUSION_POSITION_OUTSIDE_SLOTS,
            f"position {board['position_index']} is not an active slot of the image",
        )
    if not board["manifest_present"]:
        raise geometry.ProductionGeometryError(
            geometry.EXCLUSION_MANIFEST_MISSING, "no render manifest for the current revision"
        )
    topology = board["manifest_topology"]
    rows = topology.get("rows") if isinstance(topology, Mapping) else None
    columns = topology.get("columns") if isinstance(topology, Mapping) else None
    # The manifest topology is what the cells were cut with. A board whose own grid
    # fields are unset (boards converted from the legacy store) is judged by it;
    # set board fields must agree.
    board_grid = (board["grid_rows"], board["grid_columns"])
    if (
        rows != geometry.GRID_ROWS
        or columns != geometry.GRID_COLUMNS
        or board_grid not in {(None, None), (geometry.GRID_ROWS, geometry.GRID_COLUMNS)}
    ):
        raise geometry.ProductionGeometryError(
            geometry.EXCLUSION_TOPOLOGY_NOT_5X3,
            f"manifest {rows}x{columns}, board {board_grid[0]}x{board_grid[1]}",
        )
    if board["manifest_coordinate_space"] != geometry.COORDINATE_SPACE:
        raise geometry.ProductionGeometryError(
            geometry.EXCLUSION_MANIFEST_MALFORMED,
            f"coordinate space {board['manifest_coordinate_space']}",
        )
    manifest_cells = _manifest_cells(board["manifest_cell_indices"], board["manifest_cell_quads"])
    unavailable = [int(index) for index in board["unavailable_cell_indices"] or []]
    derived = geometry.derive_consistent_nodes(
        _candidate_quads(board), manifest_cells, unavailable_cell_indices=unavailable
    )
    authors = [
        (int(revision), str(author)) for revision, author in (board["revision_authors"] or [])
    ]
    level = geometry.classify_label_level(
        geometry.LabelFacts(
            geometry_revision=board["geometry_revision"],
            approved_geometry_revision=board["approved_geometry_revision"],
            approved_by=board["geometry_approved_by"],
            revision_authors=authors,
            source_geometry_source=board["source_geometry_source"],
            source_status=board["source_status"],
            source_created_by=board["source_created_by"],
        )
    )
    width, height = int(image["width"]), int(image["height"])
    difficulty = geometry.quad_difficulty(derived.quad)
    difficulty.update(
        {
            "areaFraction": difficulty["areaPx"] / (width * height),
            "nodesOutsideImage": geometry.nodes_outside_image(derived.nodes, width, height),
            **geometry.page_position(int(board["position_index"])),
            "partialBoard": board["completeness_status"] == "pending_partial",
            "expectedBoardsOnImage": len(slots),
        }
    )
    signals = {
        "cells": 0,
        "humanDecidedCells": 0,
        "lowQualityCells": 0,
        "minLowQualityConfidence": None,
        "minPredictionConfidence": None,
        "cellsWithoutPrediction": 0,
        "cellsBelowFilter": 0,
        "sourceUnavailableCells": 0,
        "otherRevisionCells": 0,
    }
    if cells is not None:
        signals = {
            "cells": int(cells["cells"]),
            "humanDecidedCells": int(cells["human_decided_cells"]),
            "lowQualityCells": int(cells["low_quality_cells"]),
            "minLowQualityConfidence": cells["min_low_quality_confidence"],
            "minPredictionConfidence": cells["min_prediction_confidence"],
            "cellsWithoutPrediction": int(cells["cells_without_prediction"]),
            "cellsBelowFilter": int(cells["cells_below_filter"]),
            "sourceUnavailableCells": int(cells["source_unavailable_cells"]),
            "otherRevisionCells": int(cells["other_revision_cells"]),
        }
    approved_at = board["geometry_approved_at"]
    return {
        "schemaVersion": CANDIDATE_SCHEMA,
        "gameId": str(game_id),
        "sourceImageId": str(image["id"]),
        "recognizedBoardId": str(board["id"]),
        "importJobId": str(image["import_job_id"]),
        "sourceChecksumSha256": image["checksum_sha256"],
        "sourceRelativePath": image["relative_path"],
        "orientedWidth": width,
        "orientedHeight": height,
        "coordinateSpace": geometry.COORDINATE_SPACE,
        "positionIndex": int(board["position_index"]),
        "sequenceNumber": board["sequence_number"],
        "expectedBoardsOnImage": len(slots),
        "candidateBoardsOnImage": None,
        "label": {
            "level": level.level,
            "basis": level.basis,
            "approvalActor": level.approval_actor,
            "geometryApprovedBy": board["geometry_approved_by"],
            "geometryApprovedAt": approved_at.isoformat() if approved_at is not None else None,
            "geometryRevision": int(board["geometry_revision"]),
            "approvedGeometryRevision": board["approved_geometry_revision"],
            "revisionAuthors": [[revision, author] for revision, author in authors],
        },
        "engine": {
            "sourceEngineKind": board["source_engine_kind"],
            "sourceEngineVersion": board["source_engine_version"],
            "boardEngineName": board["geometry_engine_name"],
            "boardEngineVersion": board["geometry_engine_version"],
            "boardGridRows": board["grid_rows"],
            "boardGridColumns": board["grid_columns"],
            "geometryChecksumSha256": board["geometry_checksum_sha256"],
            "sourceGeometryRevision": board["source_revision"],
            "sourceGeometrySource": board["source_geometry_source"],
            "sourceRevisionStatus": board["source_status"],
            "sourceRevisionCreatedBy": board["source_created_by"],
            "manifestExtractorVersion": board["manifest_extractor_version"],
        },
        "geometry": {
            "topology": {"rows": geometry.GRID_ROWS, "columns": geometry.GRID_COLUMNS},
            "nodeOrder": "row-major",
            "quadSource": derived.quad_source,
            "quad": [_round_point(point) for point in derived.quad],
            "nodes": [_round_point(point) for point in derived.nodes],
            "maxManifestDeviationPx": round(derived.max_deviation_px, 6),
        },
        "partial": {
            "isPartial": board["completeness_status"] == "pending_partial",
            "unavailableCellIndices": unavailable,
            "manifestMissingCellIndices": list(derived.missing_cell_indices),
            "qualification": _qualification(board),
        },
        "family": dict(family),
        "symbolSignals": {"lowQualityMaxConfidence": DEFAULT_LOW_QUALITY_MAX_CONFIDENCE, **signals},
        "difficulty": difficulty,
    }


def _json_line(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
        + b"\n"
    )


def _fetch(connection: Connection, statement: Any, parameters: Mapping[str, Any]) -> list[Any]:
    return [dict(row) for row in connection.execute(statement, parameters).mappings()]


def _process_batch(
    connection: Connection,
    game_id: UUID,
    images: Sequence[Mapping[str, Any]],
    job_cache: dict[UUID, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Candidate rows and exclusions of one batch of images (one transaction)."""

    unknown_jobs = sorted({image["import_job_id"] for image in images} - set(job_cache), key=str)
    if unknown_jobs:
        for row in _fetch(connection, _JOBS_SQL, {"game_id": game_id, "job_ids": unknown_jobs}):
            job_cache[row["id"]] = row
    boards = _fetch(
        connection,
        _BOARDS_SQL,
        {"game_id": game_id, "image_ids": [image["id"] for image in images]},
    )
    cells = {
        row["recognized_board_id"]: row
        for row in _fetch(
            connection,
            _CELLS_SQL,
            {
                "game_id": game_id,
                "board_ids": [board["id"] for board in boards],
                "max_confidence": DEFAULT_LOW_QUALITY_MAX_CONFIDENCE,
            },
        )
    }
    by_image = {image["id"]: image for image in images}
    rows_by_image: dict[UUID, list[dict[str, Any]]] = {image["id"]: [] for image in images}
    exclusions: list[dict[str, Any]] = []
    for board in boards:
        image = by_image[board["source_image_id"]]
        family = _family(image["import_job_id"], job_cache.get(image["import_job_id"]))
        try:
            rows_by_image[image["id"]].append(
                _build_row(game_id, image, board, cells.get(board["id"]), family)
            )
        except geometry.ProductionGeometryError as error:
            exclusions.append(_exclusion(image, board, error.code, str(error)))
        except Exception as error:  # one malformed board must not stop the export
            exclusions.append(
                _exclusion(
                    image, board, geometry.EXCLUSION_INTEGRITY, f"{type(error).__name__}: {error}"
                )
            )
    rows: list[dict[str, Any]] = []
    for image in images:
        image_rows = rows_by_image[image["id"]]
        for row in image_rows:
            row["candidateBoardsOnImage"] = len(image_rows)
        rows.extend(image_rows)
    return rows, exclusions


def _exclusion(
    image: Mapping[str, Any], board: Mapping[str, Any], reason: str, detail: str
) -> dict[str, Any]:
    return {
        "recognizedBoardId": str(board["id"]),
        "sourceImageId": str(image["id"]),
        "positionIndex": board["position_index"],
        "boardStatus": board["status"],
        "reason": reason,
        "detail": detail[:500],
    }


def _write_json_atomic(path: Path, value: object) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as output:
        output.write(
            json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n"
        )
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)


def _truncate(path: Path, size: int) -> None:
    mode = "r+b" if path.exists() else "wb"
    with path.open(mode) as handle:
        if handle.seek(0, os.SEEK_END) < size:
            raise GeometryExportError(f"{path.name} is shorter than its recorded progress")
        handle.truncate(size)


def _append(path: Path, lines: Sequence[bytes]) -> int:
    with path.open("ab") as output:
        for line in lines:
            output.write(line)
        output.flush()
        os.fsync(output.fileno())
        return output.tell()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _resolve_game(engine: Engine, game_id: str | None, game_name: str) -> UUID:
    if game_id is not None:
        return UUID(game_id)
    with engine.connect() as connection:
        connection.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        rows = connection.execute(
            text("SELECT id FROM games WHERE name = :name"), {"name": game_name}
        ).all()
        connection.rollback()
    if len(rows) != 1:
        raise GeometryExportError(f"Game name {game_name!r} matches {len(rows)} games")
    return cast(UUID, rows[0][0])


def _batch_work(
    engine: Engine,
    game_id: UUID,
    generation: int | None,
    ids: Sequence[UUID],
    job_cache: dict[UUID, Mapping[str, Any]],
) -> tuple[int, list[dict[str, Any]], list[dict[str, Any]]]:
    """One batch in its own short read-only transaction (runs in a worker thread)."""

    with _batch_transaction(engine, game_id, generation) as connection:
        images = _fetch(connection, _IMAGES_SQL, {"game_id": game_id, "ids": list(ids)})
        rows, exclusions = _process_batch(connection, game_id, images, job_cache)
    return len(images), rows, exclusions


def run_export(
    engine: Engine,
    game_id: UUID,
    output_root: Path,
    *,
    export_id: str,
    batch_images: int = DEFAULT_BATCH_IMAGES,
    max_images: int | None = None,
    resume: bool = False,
    stop_after_batches: int | None = None,
    workers: int = DEFAULT_WORKERS,
) -> Path | None:
    """Export the candidates; returns the published directory, or ``None`` when stopped early.

    The complete images are listed once and cut into fixed batches; ``workers``
    threads read batches concurrently, each in its own short read-only
    transaction, while results are written strictly in batch order. The ordered
    image list is stored next to the output so a resume uses the same batches.
    ``stop_after_batches`` stops after that many batches without publishing (tests
    use it to interrupt an export; production runs leave it unset).
    """

    output_root.mkdir(parents=True, exist_ok=True)
    final = output_root / export_id
    partial = output_root / f".partial-{export_id}"
    if final.exists():
        raise GeometryExportError(f"{final} already exists; choose another --export-id")
    candidates_path, exclusions_path, progress_path, ids_path = (
        partial / _CANDIDATES,
        partial / _EXCLUSIONS,
        partial / _PROGRESS,
        partial / _IMAGE_IDS,
    )
    started = time.monotonic()
    if partial.exists():
        if not resume:
            raise GeometryExportError(f"{partial} exists; pass --resume to continue it")
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
        if progress["gameId"] != str(game_id) or progress["exporterVersion"] != EXPORTER_VERSION:
            raise GeometryExportError("The partial export belongs to another game or version")
        if _sha256_file(ids_path) != progress["imageIdsSha256"]:
            raise GeometryExportError("The stored image list changed; the partial export is void")
        _truncate(candidates_path, progress["candidatesBytes"])
        _truncate(exclusions_path, progress["exclusionsBytes"])
        progress["resumes"] += 1
    else:
        if resume:
            raise GeometryExportError(f"{partial} does not exist; nothing to resume")
        partial.mkdir()
        candidates_path.touch()
        exclusions_path.touch()
        with _batch_transaction(engine, game_id, None) as connection:
            generation = int(connection.info["vision_export_generation"])
            listed = [
                str(row[0])
                for row in connection.execute(
                    _IMAGE_LIST_SQL, {"game_id": game_id, "limit": max_images}
                )
            ]
        ids_path.write_text("\n".join(listed) + "\n", encoding="ascii")
        progress = {
            "gameId": str(game_id),
            "exporterVersion": EXPORTER_VERSION,
            "startedAt": _now(),
            "batchImages": batch_images,
            "imageCount": len(listed),
            "imageIdsSha256": _sha256_file(ids_path),
            "batchesDone": 0,
            "images": 0,
            "imagesNoLongerComplete": 0,
            "candidateRows": 0,
            "exclusionRows": 0,
            "candidatesBytes": 0,
            "exclusionsBytes": 0,
            "storageGeneration": generation,
            "transactionReadOnlyVerified": True,
            "resumes": 0,
        }
        _write_json_atomic(progress_path, progress)
    ids = [UUID(line) for line in ids_path.read_text(encoding="ascii").split()]
    size = int(progress["batchImages"])
    batches = [ids[offset : offset + size] for offset in range(0, len(ids), size)]
    job_cache: dict[UUID, Mapping[str, Any]] = {}
    generation_pin = progress["storageGeneration"]
    consumed = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        window: deque[Future[tuple[int, list[dict[str, Any]], list[dict[str, Any]]]]] = deque()
        next_batch = progress["batchesDone"]
        while progress["batchesDone"] < len(batches):
            while len(window) < workers * 2 and next_batch < len(batches):
                window.append(
                    pool.submit(
                        _batch_work, engine, game_id, generation_pin, batches[next_batch], job_cache
                    )
                )
                next_batch += 1
            count, rows, exclusions = window.popleft().result()
            progress["candidatesBytes"] = _append(
                candidates_path, [_json_line(row) for row in rows]
            )
            progress["exclusionsBytes"] = _append(
                exclusions_path, [_json_line(item) for item in exclusions]
            )
            expected = len(batches[progress["batchesDone"]])
            progress["images"] += count
            progress["imagesNoLongerComplete"] += expected - count
            progress["batchesDone"] += 1
            progress["candidateRows"] += len(rows)
            progress["exclusionRows"] += len(exclusions)
            progress["updatedAt"] = _now()
            _write_json_atomic(progress_path, progress)
            consumed += 1
            if stop_after_batches is not None and consumed >= stop_after_batches:
                for future in window:
                    future.cancel()
                return None
    universe = _universe(engine, game_id, generation_pin)
    report = build_report(partial, universe, progress)
    report["run"] = {
        "startedAt": progress["startedAt"],
        "finishedAt": _now(),
        "batchImages": size,
        "workers": workers,
        "wallSecondsThisRun": round(time.monotonic() - started, 1),
        "resumes": progress["resumes"],
        "imagesListed": progress["imageCount"],
        "imagesNoLongerComplete": progress["imagesNoLongerComplete"],
    }
    _write_json_atomic(partial / _REPORT, report)
    progress["completed"] = True
    progress["updatedAt"] = _now()
    _write_json_atomic(progress_path, progress)
    files = {
        name: {"sha256": _sha256_file(partial / name), "bytes": (partial / name).stat().st_size}
        for name in (_CANDIDATES, _EXCLUSIONS, _REPORT, _IMAGE_IDS)
    }
    _write_json_atomic(
        partial / _MANIFEST,
        {
            "schemaVersion": 1,
            "exporterVersion": EXPORTER_VERSION,
            "candidateSchema": CANDIDATE_SCHEMA,
            "reportSchema": REPORT_SCHEMA,
            "gameId": str(game_id),
            "exportId": export_id,
            "candidateRows": progress["candidateRows"],
            "exclusionRows": progress["exclusionRows"],
            "images": progress["images"],
            "files": files,
        },
    )
    partial.rename(final)
    return final


def _original_row(
    game_id: UUID,
    image_id: UUID,
    image: Mapping[str, Any] | None,
    revisions: Sequence[Mapping[str, Any]],
    entries: Mapping[UUID, list[Mapping[str, Any]]],
    manifests: Mapping[tuple[UUID, int], Mapping[str, Any]],
) -> dict[str, Any]:
    """The original production output of one image, or its explicit absence."""

    row: dict[str, Any] = {
        "schemaVersion": ORIGINALS_SCHEMA,
        "gameId": str(game_id),
        "sourceImageId": str(image_id),
        "coordinateSpace": geometry.COORDINATE_SPACE,
        "sourceChecksumSha256": None if image is None else image["checksum_sha256"],
        "orientedWidth": None if image is None else int(image["width"]),
        "orientedHeight": None if image is None else int(image["height"]),
        "lineage": [
            {
                "revision": int(r["revision"]),
                "geometrySource": r["geometry_source"],
                "engineKind": r["engine_kind"],
                "engineVersion": r["engine_version"],
                "status": r["status"],
                "createdBy": r["created_by"],
                "createdAt": r["created_at"].isoformat(),
            }
            for r in revisions
        ],
        "status": "missing",
        "missingReason": None,
        "detail": None,
        "firstManualRevision": None,
        "original": None,
        "boards": [],
    }
    if image is None:
        row["missingReason"] = geometry.ORIGINAL_MISSING_IMAGE_NOT_FOUND
        return row
    selection = geometry.select_production_original(
        geometry.RevisionFacts(int(r["revision"]), str(r["geometry_source"]), str(r["engine_kind"]))
        for r in revisions
    )
    row["firstManualRevision"] = selection.first_manual_revision
    if selection.original_revision is None:
        row["missingReason"] = selection.missing_reason
        row["detail"] = "lineage has no automatic structured_opencv_v1 revision before manual"
        return row
    original = next(r for r in revisions if int(r["revision"]) == selection.original_revision)
    mismatch = [
        name
        for name, ok in (
            ("coordinateSpace", original["coordinate_space"] == geometry.COORDINATE_SPACE),
            ("checksum", original["source_checksum_sha256"] == image["checksum_sha256"]),
            ("width", int(original["oriented_width"]) == int(image["width"])),
            ("height", int(original["oriented_height"]) == int(image["height"])),
        )
        if not ok
    ]
    if mismatch:
        row["missingReason"] = geometry.ORIGINAL_MISSING_SOURCE_MISMATCH
        row["detail"] = ",".join(mismatch)
        return row
    revision_id = original["id"]
    boards = []
    for entry in sorted(entries.get(revision_id, []), key=lambda item: int(item["position_index"])):
        position = int(entry["position_index"])
        nodes, reason = geometry.original_board_nodes({"symbolGridQuad": entry["symbol_grid_quad"]})
        check: dict[str, Any] = {"present": False, "maxDeviationPx": None}
        manifest = manifests.get((revision_id, position))
        if manifest is not None and nodes is not None:
            try:
                cells = _manifest_cells(manifest["cell_indices"], manifest["cell_quads"])
                check = {
                    "present": True,
                    "maxDeviationPx": round(geometry.max_manifest_deviation(nodes, cells), 6),
                }
            except geometry.ProductionGeometryError as error:
                check = {"present": True, "maxDeviationPx": None, "error": error.code}
        boards.append(
            {
                "positionIndex": position,
                "sequenceNumber": entry["sequence_number"],
                "disposition": entry["disposition"],
                "localLatticeStatus": entry["lattice_status"],
                "reasonCodes": entry["reason_codes"],
                "geometryConfidence": entry["geometry_confidence"],
                "nodes": None if nodes is None else [_round_point(p) for p in nodes],
                "missingReason": reason,
                "manifestCheck": check,
            }
        )
    row.update(
        status="present",
        original={
            "revisionId": str(revision_id),
            "revision": int(original["revision"]),
            "engineKind": original["engine_kind"],
            "engineVersion": original["engine_version"],
            "status": original["status"],
            "createdBy": original["created_by"],
            "createdAt": original["created_at"].isoformat(),
            "activeBoardSlots": list(original["active_board_slots"] or []),
            "warnings": original["warnings"],
            "processingTimeMs": original["processing_time_ms"],
            "isCurrentRevision": int(original["revision"]) == int(revisions[-1]["revision"]),
        },
        boards=boards,
    )
    return row


def _originals_batch(
    engine: Engine, game_id: UUID, generation: int | None, ids: Sequence[UUID]
) -> list[dict[str, Any]]:
    """One batch of images in its own short read-only transaction."""

    with _batch_transaction(engine, game_id, generation) as connection:
        parameters = {"game_id": game_id, "ids": list(ids)}
        images = {row["id"]: row for row in _fetch(connection, _ORIGINAL_IMAGES_SQL, parameters)}
        revisions: dict[UUID, list[dict[str, Any]]] = {image_id: [] for image_id in ids}
        for row in _fetch(connection, _ORIGINAL_REVISIONS_SQL, parameters):
            revisions[row["source_image_id"]].append(row)
        candidate_ids: list[UUID] = []
        for image_rows in revisions.values():
            selection = geometry.select_production_original(
                geometry.RevisionFacts(
                    int(r["revision"]), str(r["geometry_source"]), str(r["engine_kind"])
                )
                for r in image_rows
            )
            candidate_ids.extend(
                r["id"] for r in image_rows if int(r["revision"]) == selection.original_revision
            )
        entries: dict[UUID, list[Mapping[str, Any]]] = {}
        manifests: dict[tuple[UUID, int], Mapping[str, Any]] = {}
        if candidate_ids:
            scope = {"game_id": game_id, "revision_ids": candidate_ids}
            for row in _fetch(connection, _ORIGINAL_ENTRIES_SQL, scope):
                entries.setdefault(row["revision_id"], []).append(row)
            for row in _fetch(connection, _ORIGINAL_MANIFESTS_SQL, scope):
                manifests[(row["revision_id"], int(row["position_index"]))] = row
    return [
        _original_row(
            game_id, image_id, images.get(image_id), revisions[image_id], entries, manifests
        )
        for image_id in ids
    ]


def _originals_report(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    missing: Counter[str] = Counter()
    statuses: Counter[str] = Counter()
    board_missing: Counter[str] = Counter()
    dispositions: Counter[str] = Counter()
    deviations: list[float] = []
    boards = boards_with_grid = 0
    for row in rows:
        if row["status"] != "present":
            missing[str(row["missingReason"])] += 1
            continue
        statuses[str(row["original"]["status"])] += 1
        for board in row["boards"]:
            boards += 1
            dispositions[str(board["disposition"])] += 1
            if board["nodes"] is None:
                board_missing[str(board["missingReason"])] += 1
            else:
                boards_with_grid += 1
            deviation = board["manifestCheck"].get("maxDeviationPx")
            if deviation is not None:
                deviations.append(float(deviation))
    return {
        "schemaVersion": ORIGINALS_REPORT_SCHEMA,
        "images": len(rows),
        "imagesWithOriginal": sum(statuses.values()),
        "imagesWithoutOriginal": _counter(missing),
        "originalRevisionStatus": _counter(statuses),
        "boards": boards,
        "boardsWithGrid": boards_with_grid,
        "boardsWithoutGrid": _counter(board_missing),
        "boardDispositions": _counter(dispositions),
        "manifestChecks": len(deviations),
        "manifestMaxDeviationPx": _quantiles(deviations),
    }


def run_originals_export(
    engine: Engine,
    game_id: UUID,
    output_root: Path,
    *,
    export_id: str,
    image_ids: Sequence[UUID],
    batch_images: int = DEFAULT_BATCH_IMAGES,
) -> Path:
    """``production-originals.jsonl`` for the given images (TASK-0804); read only.

    For every image: the last automatic ``structured_opencv_v1`` source-geometry revision
    before the first manual revision, with the 24 nodes of every board in
    ``exif-normalized-rgb-pixels-v1``; a board without a grid and an image without such a
    revision are explicit (``missingReason``), never dropped. Publication is a single
    rename of a complete directory; an existing export id is refused.
    """

    output_root.mkdir(parents=True, exist_ok=True)
    final = output_root / export_id
    partial = output_root / f".partial-{export_id}"
    if final.exists() or partial.exists():
        raise GeometryExportError(f"{final} (or its partial directory) already exists")
    partial.mkdir()
    ordered = sorted(set(image_ids), key=str)
    (partial / _ORIGINALS_INPUT).write_text(
        "\n".join(str(i) for i in ordered) + "\n", encoding="ascii"
    )
    started = time.monotonic()
    with _batch_transaction(engine, game_id, None) as connection:
        generation = int(connection.info["vision_export_generation"])
        alembic_revision = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
    rows: list[dict[str, Any]] = []
    for offset in range(0, len(ordered), batch_images):
        rows.extend(
            _originals_batch(engine, game_id, generation, ordered[offset : offset + batch_images])
        )
    _append(partial / _ORIGINALS, [_json_line(row) for row in rows])
    report = _originals_report(rows)
    report.update(
        gameId=str(game_id),
        exporterVersion=EXPORTER_VERSION,
        alembicRevision=alembic_revision,
        storageGeneration=generation,
        transactionReadOnlyVerified=True,
        selectionRule=(
            "last automatic structured_opencv_v1 source-geometry revision before the first "
            "manual revision; boards without symbolGridQuad and images without such a "
            "revision are explicit"
        ),
        wallSeconds=round(time.monotonic() - started, 1),
        finishedAt=_now(),
    )
    _write_json_atomic(partial / _REPORT, report)
    files = {
        name: {"sha256": _sha256_file(partial / name), "bytes": (partial / name).stat().st_size}
        for name in (_ORIGINALS, _ORIGINALS_INPUT, _REPORT)
    }
    _write_json_atomic(
        partial / _MANIFEST,
        {
            "schemaVersion": 1,
            "exporterVersion": EXPORTER_VERSION,
            "originalsSchema": ORIGINALS_SCHEMA,
            "reportSchema": ORIGINALS_REPORT_SCHEMA,
            "gameId": str(game_id),
            "exportId": export_id,
            "images": len(rows),
            "files": files,
        },
    )
    partial.rename(final)
    return final


def snapshot_image_ids(snapshot: Path, roles: Sequence[str]) -> list[UUID]:
    """Image ids of the given roles from a production snapshot's ``split.json`` (ids only)."""

    document = json.loads((snapshot / "split.json").read_text(encoding="utf-8"))
    if document.get("selectionColumns", [None, None])[:2] != ["imageId", "role"]:
        raise GeometryExportError("The snapshot split format is not supported")
    wanted = set(roles)
    return [UUID(str(row[0])) for row in document["selection"] if row[1] in wanted]


def _universe(engine: Engine, game_id: UUID, generation: int | None) -> dict[str, Any]:
    """Whole-game counts used to reconcile the export (one short transaction)."""

    with _batch_transaction(engine, game_id, generation) as connection:
        result: dict[str, Any] = {}
        for name, statement in _UNIVERSE_SQL.items():
            rows = _fetch(connection, statement, {"game_id": game_id})
            if name == "rejectedBoardsOnCompleteImages":
                result[name] = int(rows[0]["n"])
            elif name == "imagesByGateStatus":
                result[name] = [
                    {"status": row["status"], "evaluated": row["evaluated"], "images": row["n"]}
                    for row in rows
                ]
            else:
                result[name] = {str(row["status"]): int(row["n"]) for row in rows}
        result["alembicRevision"] = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
    return result


def _quantiles(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {key: None for key in ("min", "p05", "p25", "p50", "p75", "p95", "p99", "max")}
    ordered = sorted(values)

    def at(fraction: float) -> float:
        return ordered[min(len(ordered) - 1, int(math.floor(fraction * (len(ordered) - 1) + 0.5)))]

    return {
        "min": ordered[0],
        "p05": at(0.05),
        "p25": at(0.25),
        "p50": at(0.5),
        "p75": at(0.75),
        "p95": at(0.95),
        "p99": at(0.99),
        "max": ordered[-1],
    }


def _counter(counter: Counter[Any]) -> dict[str, int]:
    return {str(key): counter[key] for key in sorted(counter, key=str)}


def build_report(
    directory: Path, universe: Mapping[str, Any], progress: Mapping[str, Any]
) -> dict[str, Any]:
    """The count report, computed from the written files (so a resumed run agrees)."""

    levels: Counter[str] = Counter()
    level_basis: Counter[str] = Counter()
    actors: Counter[str] = Counter()
    quad_sources: Counter[str] = Counter()
    unclassified_by_creator: Counter[str] = Counter()
    engines: Counter[str] = Counter()
    families: Counter[str] = Counter()
    level_by_family: Counter[str] = Counter()
    page_cells: Counter[str] = Counter()
    boards_per_image: Counter[int] = Counter()
    expected_per_image: Counter[int] = Counter()
    partial_boards = 0
    images_with_candidates: set[str] = set()
    per_image: dict[str, int] = {}
    expected_images: dict[str, int] = {}
    images_by_level: dict[str, set[str]] = {}
    excluded_reasons: Counter[str] = Counter()
    deviations: list[float] = []
    areas: list[float] = []
    area_fractions: list[float] = []
    ratios_h: list[float] = []
    ratios_v: list[float] = []
    angle_dev: list[float] = []
    signals: dict[str, Counter[str]] = {}
    min_conf: dict[str, list[float]] = {}
    outside_nodes = 0
    with (directory / _CANDIDATES).open("rb") as source:
        for line in source:
            row = json.loads(line)
            level = row["label"]["level"]
            levels[level] += 1
            level_basis[f"{level}/{row['label']['basis']}"] += 1
            actors[
                f"{level}/{row['label']['approvalActor'] or row['label']['geometryApprovedBy']}"
            ] += 1
            quad_sources[row["geometry"]["quadSource"]] += 1
            if level == "U":
                unclassified_by_creator[
                    f"{row['label']['basis']}|{row['engine']['sourceRevisionCreatedBy']}"
                ] += 1
            engines[
                f"{row['engine']['sourceEngineKind']}|{row['engine']['sourceEngineVersion']}"
                f"|{row['engine']['sourceGeometrySource']}"
            ] += 1
            families[row["family"]["familyId"]] += 1
            level_by_family[f"{row['family']['familyId']}|{level}"] += 1
            image_id = row["sourceImageId"]
            images_with_candidates.add(image_id)
            per_image[image_id] = row["candidateBoardsOnImage"]
            expected_images[image_id] = row["expectedBoardsOnImage"]
            images_by_level.setdefault(level, set()).add(image_id)
            page_cells[
                f"row{row['difficulty']['pageRow']}-col{row['difficulty']['pageColumn']}"
            ] += 1
            if row["partial"]["isPartial"]:
                partial_boards += 1
            deviations.append(row["geometry"]["maxManifestDeviationPx"])
            difficulty = row["difficulty"]
            areas.append(difficulty["areaPx"])
            area_fractions.append(difficulty["areaFraction"])
            ratios_h.append(difficulty["edgeRatioHorizontal"])
            ratios_v.append(difficulty["edgeRatioVertical"])
            angle_dev.append(difficulty["maxAngleDeviationDeg"])
            outside_nodes += 1 if difficulty["nodesOutsideImage"] else 0
            sig = row["symbolSignals"]
            counters = signals.setdefault(level, Counter())
            counters["boards"] += 1
            counters["boardsWithCells"] += 1 if sig["cells"] else 0
            counters["allCellsHumanDecided"] += (
                1 if sig["cells"] and sig["humanDecidedCells"] == sig["cells"] else 0
            )
            counters["noLowQualityCell"] += 1 if sig["cells"] and not sig["lowQualityCells"] else 0
            counters["filterReady"] += 1 if sig["cells"] and not sig["cellsBelowFilter"] else 0
            counters["anyHumanDecidedCell"] += 1 if sig["humanDecidedCells"] else 0
            if sig["minPredictionConfidence"] is not None:
                min_conf.setdefault(level, []).append(sig["minPredictionConfidence"])
    for count in per_image.values():
        boards_per_image[count] += 1
    for value in expected_images.values():
        expected_per_image[value] += 1
    exclusion_images: set[str] = set()
    with (directory / _EXCLUSIONS).open("rb") as source:
        for line in source:
            item = json.loads(line)
            excluded_reasons[item["reason"]] += 1
            exclusion_images.add(item["sourceImageId"])
    live_by_gate = universe["liveBoardsByImageGateStatus"]
    live_on_complete = int(live_by_gate.get("geometry_complete", 0))
    candidate_rows = sum(levels.values())
    excluded_rows = sum(excluded_reasons.values())
    gate = {
        str(item["status"]): item for item in universe["imagesByGateStatus"] if item["evaluated"]
    }
    return {
        "schemaVersion": REPORT_SCHEMA,
        "exporterVersion": EXPORTER_VERSION,
        "gameId": progress["gameId"],
        "alembicRevision": universe["alembicRevision"],
        "storageGeneration": progress["storageGeneration"],
        "transactionReadOnlyVerified": progress["transactionReadOnlyVerified"],
        "lowQualityMaxConfidence": DEFAULT_LOW_QUALITY_MAX_CONFIDENCE,
        "nodeToleranceMaxPx": geometry.NODE_TOLERANCE_PX,
        "universe": universe,
        "reconciliation": {
            "liveBoardsOnCompleteImages": live_on_complete,
            "candidateRows": candidate_rows,
            "excludedRows": excluded_rows,
            "candidatesPlusExcluded": candidate_rows + excluded_rows,
            "matches": candidate_rows + excluded_rows == live_on_complete,
            "imagesProcessed": progress["images"],
            "completeImagesInGate": int(
                sum(
                    i["images"]
                    for i in universe["imagesByGateStatus"]
                    if i["status"] == "geometry_complete"
                )
            ),
            "gateEvaluatedStatuses": sorted(gate),
        },
        "candidates": {
            "rows": candidate_rows,
            "images": len(images_with_candidates),
            "byLevel": _counter(levels),
            "imagesByLevel": {level: len(ids) for level, ids in sorted(images_by_level.items())},
            "byLevelAndBasis": _counter(level_basis),
            "byLevelAndApprovalActor": _counter(actors),
            "byQuadSource": _counter(quad_sources),
            "unclassifiedByBasisAndSourceCreator": _counter(unclassified_by_creator),
            "byEngineAndGeometrySource": _counter(engines),
            "partialBoards": partial_boards,
            "boardsWithNodesOutsideImage": outside_nodes,
            "boardsPerImage": {str(k): v for k, v in sorted(boards_per_image.items())},
            "expectedBoardsPerImage": {str(k): v for k, v in sorted(expected_per_image.items())},
            "byPageSlot": _counter(page_cells),
        },
        "exclusions": {
            "rows": excluded_rows,
            "images": len(exclusion_images),
            "byReason": _counter(excluded_reasons),
            "rejectedBoardsNeverCandidates": universe["boardsByStatus"].get("rejected", 0),
            "rejectedBoardsOnCompleteImages": universe["rejectedBoardsOnCompleteImages"],
            "liveBoardsOnImagesOutsideComplete": {
                key: value for key, value in live_by_gate.items() if key != "geometry_complete"
            },
        },
        "families": {
            "count": len(families),
            "boardsPerFamily": _counter(families),
            "boardsPerFamilyAndLevel": _counter(level_by_family),
        },
        "symbolSignals": {
            level: {
                **_counter(counters),
                "minPredictionConfidence": _quantiles(min_conf.get(level, [])),
            }
            for level, counters in sorted(signals.items())
        },
        "difficulty": {
            "areaPx": _quantiles(areas),
            "areaFraction": _quantiles(area_fractions),
            "edgeRatioHorizontal": _quantiles(ratios_h),
            "edgeRatioVertical": _quantiles(ratios_v),
            "maxAngleDeviationDeg": _quantiles(angle_dev),
            "maxManifestDeviationPx": _quantiles(deviations),
        },
    }


def main() -> None:
    from game_predictor_api.config import ApiSettings

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--game-id", default=None, help="game UUID (default: the game named 777)")
    parser.add_argument("--game-name", default="777")
    parser.add_argument("--export-id", default=None)
    parser.add_argument("--batch-images", type=int, default=DEFAULT_BATCH_IMAGES)
    parser.add_argument("--max-images", type=int, default=None, help="limit for dry runs")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--production-originals-for",
        type=Path,
        default=None,
        help="TASK-0804: write production-originals.jsonl for the images of a production "
        "snapshot (split.json image ids of --originals-roles) instead of the candidates",
    )
    parser.add_argument("--originals-roles", default="development,gold")
    arguments = parser.parse_args()
    if not 1 <= arguments.batch_images <= 500:
        parser.error("--batch-images must be between 1 and 500")
    if not 1 <= arguments.workers <= 8:
        parser.error("--workers must be between 1 and 8")
    settings = ApiSettings.from_environment()
    engine = create_engine(settings.owner_database_url, connect_args={"connect_timeout": 5})
    try:
        game_id = _resolve_game(engine, arguments.game_id, arguments.game_name)
        if arguments.production_originals_for is not None:
            roles = [r.strip() for r in arguments.originals_roles.split(",") if r.strip()]
            stamp = f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
            print(
                run_originals_export(
                    engine,
                    game_id,
                    arguments.output_root,
                    export_id=arguments.export_id
                    or f"production-originals-{str(game_id)[:8]}-{stamp}",
                    image_ids=snapshot_image_ids(arguments.production_originals_for, roles),
                    batch_images=arguments.batch_images,
                )
            )
            return
        export_id = arguments.export_id or (
            f"production-geometry-{str(game_id)[:8]}-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
        )
        result = run_export(
            engine,
            game_id,
            arguments.output_root,
            export_id=export_id,
            batch_images=arguments.batch_images,
            max_images=arguments.max_images,
            resume=arguments.resume,
            workers=arguments.workers,
        )
    finally:
        engine.dispose()
    print(result)


if __name__ == "__main__":
    main()
