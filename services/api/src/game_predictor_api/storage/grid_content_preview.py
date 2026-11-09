"""Read-only ordinary overlays from current geometry and persisted production footprints."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import select

from game_predictor_api.domain.board_render_manifests import sha256_canonical_json
from game_predictor_api.domain.grid_cell_content import ContentError, ContentSource
from game_predictor_api.domain.grid_visibility_contract import CellContentReference
from game_predictor_api.domain.image_geometry_v2 import SOURCE_SUPPORT_EPSILON
from game_predictor_api.schemas.grid_cell_content import (
    ContentOrdinaryPreview,
    ContentProductionFootprint,
)

from .grid_cell_content_models import GridCellContentSessionModel
from .grid_cell_content_targets import _live_source, _members, _snapshot

if TYPE_CHECKING:
    from .grid_cell_content import SqlAlchemyGridCellContentRepository


def protected_source(
    repo: SqlAlchemyGridCellContentRepository, game: UUID, source: ContentSource
) -> bool:
    """All slots/copies and all persisted passes stay out of auxiliary galleries."""
    query = (
        select(GridCellContentSessionModel.id)
        .where(
            GridCellContentSessionModel.game_id == game,
            GridCellContentSessionModel.document.contains(
                {
                    "targets": [
                        {
                            "source": {
                                "sourceRepresentativeSha256": source.sourceRepresentativeSha256
                            }
                        }
                    ]
                }
            ),
        )
        .limit(1)
    )
    return repo.session.scalar(query) is not None


def _points(raw: Any, count: int) -> list[list[float]]:
    if not isinstance(raw, list) or len(raw) != count:
        raise ValueError("Missing exact points")
    try:
        points = [[p["x"], p["y"]] if isinstance(p, dict) else list(p) for p in raw]
    except (KeyError, TypeError) as error:
        raise ValueError("Malformed saved points") from error
    if any(
        len(p) != 2
        or any(
            type(v) not in (int, float) or (type(v) is float and not math.isfinite(v)) for v in p
        )
        for p in points
    ):
        raise ValueError("Saved coordinates must be finite real numbers")
    return points


def preview_document(
    source: ContentSource, target: dict[str, Any], cohort: UUID, manifest: str
) -> dict[str, Any]:
    """Never regularize saved nodes or manufacture crop footprints from cell bounds."""
    board = target["board"]
    result: dict[str, Any] = {
        "version": "grid-content-ordinary-preview-v1",
        "cohortId": str(cohort),
        "manifestSha256": manifest,
        "state": "available",
        "reasonCodes": [],
        "nodes": None,
        "geometryRevision": board.get("geometry_revision"),
        "sourceGeometryRevisionId": board.get("source_geometry_revision_id"),
        "geometrySha256": board.get("geometry_checksum_sha256"),
        "geometryEngine": board.get("geometry_engine_name"),
        "geometryEngineVersion": board.get("geometry_engine_version"),
        "productionCells": [],
    }
    try:
        nodes = _points((board.get("board_geometry") or {}).get("latticeNodes"), 24)
        # Validate the actual saved coordinates; do not silently coerce malformed geometry.
        ContentOrdinaryPreview.model_validate({**result, "nodes": nodes})
        if any(
            not -source.width <= x <= 2 * source.width
            or not -source.height <= y <= 2 * source.height
            for x, y in nodes
        ):
            raise ValueError("Saved nodes exceed supported manual bounds")
    except ValueError:
        result.update(state="unavailable", reasonCodes=["CONTENT_SAVED_NODES_UNAVAILABLE"])
        return result
    result["nodes"] = nodes
    renders = [
        r
        for r in target.get("renders", [])
        if isinstance(r, dict) and r.get("geometry_revision") == board.get("geometry_revision")
    ]
    if len(renders) != 1:
        result["state"] = "unavailable"
        result["reasonCodes"] = ["CONTENT_PRODUCTION_MANIFEST_UNAVAILABLE"]
        return result
    render = renders[0]
    document = render.get("cells")
    try:
        valid_manifest = (
            isinstance(document, dict)
            and isinstance(document.get("cells"), list)
            and sha256_canonical_json(document) == render.get("manifest_checksum_sha256")
        )
    except (TypeError, ValueError):
        valid_manifest = False
    if not valid_manifest or not isinstance(document, dict):
        result.update(state="unavailable", reasonCodes=["CONTENT_PRODUCTION_MANIFEST_CONFLICT"])
        return result
    seen: set[int] = set()
    # Repeated identities have no unique production footprint; omit every copy.
    entries = document["cells"]
    indices = [entry.get("cellIndex") for entry in entries if isinstance(entry, dict)]
    for entry in entries:
        try:
            footprint = _verified_footprint(entry, board, source, nodes)
            index = footprint["cellIndex"]
            if indices.count(index) != 1:
                raise ValueError("Duplicate production cell")
        except (KeyError, TypeError, ValueError):
            # These are pure document/contract failures, not repository or DB errors.
            result["state"] = "unavailable"
            if "CONTENT_PRODUCTION_CELL_UNAVAILABLE" not in result["reasonCodes"]:
                result["reasonCodes"].append("CONTENT_PRODUCTION_CELL_UNAVAILABLE")
            continue
        seen.add(index)
        quad = footprint["quad"]
        # Partial cells legitimately warp outside the photo. Preserve their
        # actual footprint; never clamp it or claim those are real pixels.
        if "CONTENT_PRODUCTION_FOOTPRINT_OUTSIDE_SOURCE" not in result["reasonCodes"] and any(
            x < -SOURCE_SUPPORT_EPSILON
            or x > source.width - 1 + SOURCE_SUPPORT_EPSILON
            or y < -SOURCE_SUPPORT_EPSILON
            or y > source.height - 1 + SOURCE_SUPPORT_EPSILON
            for x, y in quad
        ):
            result["reasonCodes"].append("CONTENT_PRODUCTION_FOOTPRINT_OUTSIDE_SOURCE")
        result["productionCells"].append(footprint)
    result["productionCells"].sort(key=lambda c: c["cellIndex"])
    if len(seen) != 15:
        result["reasonCodes"].append("CONTENT_PRODUCTION_CELLS_PARTIAL")
    return ContentOrdinaryPreview.model_validate(result).model_dump(mode="json")


def _verified_footprint(
    entry: Any, board: dict[str, Any], source: ContentSource, nodes: list[list[float]]
) -> dict[str, Any]:
    if not isinstance(entry, dict):
        raise ValueError("Missing production cell")
    spec, index = entry["renderSpec"], entry["cellIndex"]
    if (
        type(index) is not int
        or not 0 <= index < 15
        or not isinstance(spec, dict)
        or sha256_canonical_json(spec) != entry["renderSpecChecksumSha256"]
        or spec["sourceChecksumSha256"] != source.sourceSha256
        or spec["normalizedPixelChecksumSha256"] != source.sourceRepresentativeSha256
        or spec["geometryRevision"] != board["geometry_revision"]
        or spec["boardSlot"] != board["position_index"]
        or spec["cellIndex"] != index
    ):
        raise ValueError("Production cell pin differs")
    row, col = divmod(index, 5)
    expected = [
        nodes[row * 6 + col],
        nodes[row * 6 + col + 1],
        nodes[(row + 1) * 6 + col + 1],
        nodes[(row + 1) * 6 + col],
    ]
    if _points(spec["sourceQuad"], 4) != expected:
        raise ValueError("Production cell belongs to different saved nodes")
    quad = _points(spec["paddedSourceQuad"], 4)
    CellContentReference.model_validate({"state": "visible", "quad": quad})
    return ContentProductionFootprint.model_validate(
        {
            "cellIndex": index,
            "quad": quad,
            "renderSpecSha256": entry["renderSpecChecksumSha256"],
            "configuration": spec["configuration"],
        }
    ).model_dump(mode="json")


def ordinary_preview(
    repo: SqlAlchemyGridCellContentRepository,
    game: UUID,
    source_id: UUID,
    position: int,
    cohort: UUID,
    manifest: str,
) -> dict[str, Any]:
    from .grid_cell_content import source_identity

    snapshot = _snapshot(repo, game, cohort, manifest)
    for frozen, role, target in _members(snapshot):
        if frozen["sourceId"] != str(source_id) or target["positionIndex"] != position:
            continue
        source = source_identity(frozen["sourceIdentity"])
        empty = {
            "version": "grid-content-ordinary-preview-v1",
            "cohortId": cohort,
            "manifestSha256": manifest,
            "nodes": None,
            "productionCells": [],
        }
        if role in {"B", "REGRESSION"}:
            return ContentOrdinaryPreview.model_validate(
                {**empty, "state": "protected", "reasonCodes": ["CONTENT_CONTROL_ROLE_PROTECTED"]}
            ).model_dump(mode="json", exclude_unset=True)
        if protected_source(repo, game, source):
            return ContentOrdinaryPreview.model_validate(
                {**empty, "state": "protected", "reasonCodes": ["CONTENT_BLIND_SOURCE_PROTECTED"]}
            ).model_dump(mode="json", exclude_unset=True)
        reason, boards = _live_source(repo, game, source)
        if reason is not None:
            return ContentOrdinaryPreview.model_validate(
                {**empty, "state": "unavailable", "reasonCodes": [reason]}
            ).model_dump(mode="json", exclude_unset=True)
        repo.require_current_board(boards.get(position), target["sequenceNumber"])
        return preview_document(source, boards[position], cohort, manifest)
    raise ContentError("CONTENT_TARGET_UNAVAILABLE", "The target is outside this cohort.", 404)
