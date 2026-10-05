"""Exact immutable RGB crops; all callers hold the geometry lock."""

import hashlib
import io
import math

import cv2
import numpy as np
import PIL
from PIL import Image

from .annotation_contracts import AnnotationState, GeometryAnnotation
from .annotations import annotation_key, digest
from .catalog import Catalog
from .contracts import Board, Point
from .geometry import cell_quads, crop_cell
from .photo_review import photo_accepted
from .symbol_contracts import CropBinding, LabBoardRequest, LabCropRequest
from .symbol_dataset_version import LabelPreviewGrant
from .symbol_labels import guard_pixels


def render_spec() -> dict[str, str]:
    return {
        "opencv": cv2.__version__,
        "pillow": PIL.__version__,
        "exif": "transpose-rgb-v1",
        "warp": "INTER_LINEAR-BORDER_CONSTANT-96",
        "encoding": "PNG-compress6",
    }


def geometry_for(
    state: AnnotationState, catalog: Catalog, request: LabCropRequest | LabBoardRequest
) -> GeometryAnnotation:
    source = catalog.sources[request.source_id]
    annotation = state.annotations.get(annotation_key(source.id, request.board_index))
    if (
        annotation is None
        or not annotation.full_approved
        or annotation.presence != "present"
        or annotation.revision != request.expected_geometry_revision
        or annotation.source_sha256 != source.sha256
        or not photo_accepted(state, source)
        or not annotation.nodes
        or any(node.provenance != "human" for node in annotation.nodes)
    ):
        raise ValueError("SYMBOL_GEOMETRY_STALE")
    if (
        isinstance(request, LabCropRequest)
        and request.cell_index >= annotation.topology.columns * annotation.topology.rows
    ):
        raise ValueError("SYMBOL_CELL_INVALID")
    return annotation


def render_crop(
    state: AnnotationState,
    catalog: Catalog,
    snapshot_id: str,
    catalog_digest: str,
    request: LabCropRequest,
    *,
    preview_grant: LabelPreviewGrant | None = None,
) -> tuple[CropBinding, bytes]:
    guard_pixels(state, catalog, request.source_id, preview_grant)
    annotation = geometry_for(state, catalog, request)
    board = Board(position_index=annotation.board_index, status="complete", nodes=annotation.nodes)
    quad = cell_quads(board, annotation.topology)[request.cell_index]
    rgb = np.asarray(catalog.image(catalog.sources[request.source_id]), dtype=np.uint8)
    return render_cell(rgb, quad, annotation, catalog, snapshot_id, catalog_digest, request)


def render_cell(
    rgb: np.ndarray,
    quad: np.ndarray,
    annotation: GeometryAnnotation,
    catalog: Catalog,
    snapshot_id: str,
    catalog_digest: str,
    request: LabCropRequest,
) -> tuple[CropBinding, bytes]:
    """Shared exact renderer: board and single-cell paths produce identical bytes."""
    crop = crop_cell(rgb, quad)
    if crop is None:
        raise ValueError("SYMBOL_CROP_OUTSIDE_SOURCE")
    output = io.BytesIO()
    Image.fromarray(crop).save(output, format="PNG", compress_level=6)
    data = output.getvalue()
    if len(data) > 256 * 1024:
        raise ValueError("SYMBOL_CROP_TOO_LARGE")
    spec = render_spec()
    binding = CropBinding(
        snapshot_manifest_id=snapshot_id,
        catalog_digest=catalog_digest,
        game_id=catalog.sources[request.source_id].game_id,
        source_id=request.source_id,
        source_sha256=catalog.sources[request.source_id].sha256,
        board_index=request.board_index,
        geometry_revision=annotation.revision,
        geometry_digest=digest(annotation.model_dump()),
        topology=annotation.topology,
        cell_index=request.cell_index,
        quad=[Point(x=float(x), y=float(y), provenance="human") for x, y in quad],
        renderer_version="lab-symbol-crop-rgb96-v1",
        render_spec=spec,
        render_spec_digest=digest(spec),
        pixel_sha256=hashlib.sha256(crop.tobytes()).hexdigest(),
        byte_sha256=hashlib.sha256(data).hexdigest(),
        crop_id="0" * 64,
    )
    binding.crop_id = digest(binding.model_dump(exclude={"crop_id"}))
    return binding, data


def render_board(
    state: AnnotationState,
    catalog: Catalog,
    snapshot_id: str,
    catalog_digest: str,
    request: LabBoardRequest,
    *,
    preview_grant: LabelPreviewGrant | None = None,
) -> tuple[GeometryAnnotation, np.ndarray, list[tuple[CropBinding, bytes]]]:
    guard_pixels(state, catalog, request.source_id, preview_grant)
    annotation = geometry_for(state, catalog, request)
    rgb = np.asarray(catalog.image(catalog.sources[request.source_id]), dtype=np.uint8)
    board = Board(position_index=annotation.board_index, status="complete", nodes=annotation.nodes)
    cells = [
        render_cell(
            rgb,
            quad,
            annotation,
            catalog,
            snapshot_id,
            catalog_digest,
            LabCropRequest(
                kind="lab_cell",
                source_id=request.source_id,
                board_index=request.board_index,
                cell_index=index,
                expected_geometry_revision=request.expected_geometry_revision,
            ),
        )
        for index, quad in enumerate(cell_quads(board, annotation.topology))
    ]
    return annotation, rgb, cells


def render_selected_bindings(
    state: AnnotationState,
    catalog: Catalog,
    snapshot_id: str,
    catalog_digest: str,
    selections: list[tuple[str, int, int, int]],
    *,
    preview_grant: LabelPreviewGrant | None = None,
) -> list[tuple[CropBinding, bytes]]:
    """Render only selected cells, decoding each source at most once."""
    current_source: str | None = None
    image: np.ndarray | None = None
    boards: dict[tuple[str, int], tuple[GeometryAnnotation, list[np.ndarray]]] = {}
    result: list[tuple[CropBinding, bytes]] = []
    for sid, board_index, cell_index, revision in selections:
        if sid != current_source:
            if current_source is not None and sid < current_source:
                raise ValueError("SYMBOL_QUEUE_BINDINGS_INVALID")
            guard_pixels(state, catalog, sid, preview_grant)
            image = np.asarray(catalog.image(catalog.sources[sid]), dtype=np.uint8)
            current_source = sid
            boards.clear()
        key = (sid, board_index)
        if key not in boards:
            annotation = geometry_for(
                state,
                catalog,
                LabBoardRequest(
                    kind="lab_board",
                    source_id=sid,
                    board_index=board_index,
                    expected_geometry_revision=revision,
                ),
            )
            board = Board(
                position_index=annotation.board_index, status="complete", nodes=annotation.nodes
            )
            boards[key] = (annotation, cell_quads(board, annotation.topology))
        annotation, quads = boards[key]
        if cell_index >= len(quads):
            raise ValueError("SYMBOL_CELL_INVALID")
        assert image is not None
        result.append(
            render_cell(
                image,
                quads[cell_index],
                annotation,
                catalog,
                snapshot_id,
                catalog_digest,
                LabCropRequest(
                    kind="lab_cell",
                    source_id=sid,
                    board_index=board_index,
                    cell_index=cell_index,
                    expected_geometry_revision=revision,
                ),
            )
        )
    return result


def board_context(rgb: np.ndarray, nodes: list[Point]) -> tuple[bytes, int, int, list[Point]]:
    """Bounded source-perspective context, retaining every actual grid node."""
    height, width = rgb.shape[:2]
    margin = 8
    left = max(0, math.floor(min(n.x for n in nodes)) - margin)
    top = max(0, math.floor(min(n.y for n in nodes)) - margin)
    right = min(width, math.ceil(max(n.x for n in nodes)) + margin + 1)
    bottom = min(height, math.ceil(max(n.y for n in nodes)) + margin + 1)
    image = Image.fromarray(rgb[top:bottom, left:right])
    image.thumbnail((960, 960), Image.Resampling.LANCZOS)
    preview_width, preview_height = image.size
    scaled = [
        Point(
            x=(n.x - left) * preview_width / (right - left),
            y=(n.y - top) * preview_height / (bottom - top),
            provenance=n.provenance,
        )
        for n in nodes
    ]
    output = io.BytesIO()
    image.save(output, format="PNG", compress_level=6)
    data = output.getvalue()
    if len(data) > 4 * 1024 * 1024:
        raise ValueError("SYMBOL_BOARD_PREVIEW_TOO_LARGE")
    return data, preview_width, preview_height, scaled
