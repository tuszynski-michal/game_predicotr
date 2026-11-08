"""Actual neural input witness and independent frozen-A replay, separate from final crops."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any
from uuid import UUID

import cv2
import numpy as np
from game_predictor_api.domain.canonical_source import rgb_pixel_checksum_sha256
from game_predictor_api.domain.grid_training_cohorts import digest
from game_predictor_api.domain.production_cell_geometry import assess_content, intersect_support

from ..geometry_core.preprocessing import board_rectifier, crop_board
from ..geometry_core.rescue import BoardCropGeometryV1
from ..geometry_core.settings import BoardPreset
from .full_board_completeness import calibration_routing_sha
from .grid_cell_content_reference import frozen_content_reference
from .grid_rescue_strategy import slots
from .production_cell_evaluation import real_source_support


def engine_input_context(engine: Any) -> dict[str, Any]:
    core = getattr(engine, "engine", engine)
    variant = getattr(engine, "variant", None)
    return {
        "boardPreset": BoardPreset.model_validate(
            core.settings.board, from_attributes=True
        ).model_dump(mode="json"),
        "routing": getattr(engine, "routing", None),
        "path": getattr(engine, "path", None),
        "variant": None if variant is None else variant.model_dump(mode="json"),
    }


def manifest_input_context(root: Any, manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Read preprocessing from the already registry-pinned bundle; no ORT/inference."""
    import hashlib
    import json

    from game_predictor_api.application.grid_model_evaluation import bundle_sha256
    from game_predictor_api.domain.grid_rescue_policy import require_rescue_evidence

    path = (root / manifest["managedDirectory"] / "bundle.json").resolve()
    if not path.is_relative_to(root.resolve()) or path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("INPUT_CONTENT_BUNDLE_PATH_OR_SIZE")
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != bundle_sha256(manifest):
        raise ValueError("INPUT_CONTENT_BUNDLE_CHANGED")
    bundle = json.loads(content)
    context = {
        "boardPreset": BoardPreset.model_validate(bundle["preset"]["board"]).model_dump(
            mode="json"
        ),
        "routing": None,
        "path": None,
        "variant": None,
    }
    if "rescue" in bundle:
        proof = require_rescue_evidence(bundle)
        selected = proof["selection"]["selectedPath"]
        if selected is not None:
            context.update(
                path=selected,
                routing=proof["selection"]["pathProofs"][selected].get("routing"),
                variant=proof["recipe"]["variant"],
            )
    return context


def require_input_context(proof: Mapping[str, Any], expected: Mapping[str, Any] | None) -> None:
    if expected is None or any(
        proof[key] != expected[key] for key in ("boardPreset", "routing", "path")
    ):
        raise ValueError("INPUT_CONTENT_MODEL_CONTEXT_CHANGED")
    geometry = proof["geometry"]
    if geometry is not None and (
        expected["path"] not in ("board_only", "combined")
        or expected["variant"] is None
        or geometry != expected["variant"].get("board")
    ):
        raise ValueError("INPUT_CONTENT_VARIANT_CHANGED")


def _input(
    frame: Any, reference: Any, quad: Any, board: BoardPreset, geometry: Any
) -> dict[str, Any]:
    matrix = board_rectifier(np.asarray(quad, dtype=np.float64), board, geometry=geometry)
    width, height = board.canvas
    support = cv2.perspectiveTransform(
        np.asarray([[[0, 0], [width, 0], [width, height], [0, height]]], dtype=np.float64),
        np.linalg.inv(matrix),
    )[0].tolist()
    actual = intersect_support(support, real_source_support(frame))
    raster = crop_board(frame.rgb, matrix, board)
    states = [
        None if cell.state != "visible" else assess_content(cell.quad, actual, 0.0)["state"]
        for cell in reference.cells
    ]
    # A hidden/unknown glyph is never reconstructed from geometry. Such a board
    # cannot supply a positive or negative threshold-training label.
    cropped = (
        None if any(state is None for state in states) else any(s != "preserved" for s in states)
    )
    return {
        "matrix": matrix.tolist(),
        "inputSupport": support,
        "realSupport": actual,
        "inputRasterSha256": rgb_pixel_checksum_sha256(raster),
        "inputContentStates": states,
        "inputCropped": cropped,
        "sourceCanvasSha256": frame.pixel_checksum_sha256,
    }


def observe_input(
    frame: Any,
    source: Mapping[str, Any],
    target: Mapping[str, Any],
    detection: Any,
    engine: Any,
    game: UUID,
) -> dict[str, Any] | None:
    reference = frozen_content_reference(game, source, target)
    core = getattr(engine, "engine", engine)
    settings = getattr(core, "settings", None)
    if reference is None or settings is None or detection is None:
        return None
    position = target["positionIndex"]
    primary = getattr(engine, "last_baseline", None)
    binding = None if primary is None else slots(primary)
    original = (
        None
        if primary is None or not binding or position not in binding
        else primary[binding[position]]
    )
    result = getattr(engine, "last_result", None)
    rescued = result is not None and position in result.crop_calls and original is not detection
    geometry = (
        engine.variant.board if rescued and engine.path in ("board_only", "combined") else None
    )
    values = _input(frame, reference, detection.screen_quad, settings.board, geometry)
    body = {
        "version": "frozen-a-neural-input-content-v1",
        "sourceId": source["sourceId"],
        "positionIndex": position,
        "sourceRepresentativeSha256": reference.sourceRepresentativeSha256,
        "contentReferenceSha256": target["contentReferenceSha256"],
        "contentReferenceRevision": target["contentReferenceRevision"],
        "screenQuad": np.asarray(detection.screen_quad, dtype=np.float64).tolist(),
        "boardPreset": settings.board.model_dump(mode="json"),
        "geometry": None if geometry is None else geometry.model_dump(mode="json"),
        "routing": getattr(engine, "routing", None),
        "path": getattr(engine, "path", None),
        **values,
    }
    return {**body, "sha256": digest(body)}


def bind_input_references(
    frozen: Any,
    snapshot: Any,
    prepared: Mapping[str, Any],
    expected_context: Mapping[str, Any] | None = None,
) -> Any:
    """Re-decode trusted A pixels and recompute each label before T1 accepts its tuple.

    Observed screen quads are model outputs, just like the existing calibration
    feature vectors. Their preprocessing/routing, raster, frame and human content
    are independently rebound here; self-declared inputCropped is never accepted.
    """
    from .grid_cohort_dataset import GridBoardDataset

    proofs = prepared.get("inputContentEvidence", [])
    if not proofs:
        return frozen
    plan = prepared["plan"]
    sources = {
        source["sourceId"]: source
        for source, _ in GridBoardDataset(snapshot, "VALIDATION").indexed()
    }
    verified = {}
    seen = set()
    for proof in proofs:
        require_input_context(proof, expected_context)
        body = {key: value for key, value in proof.items() if key != "sha256"}
        if proof.get("version") != "frozen-a-neural-input-content-v1" or proof.get(
            "sha256"
        ) != digest(body):
            raise ValueError("INPUT_CONTENT_EVIDENCE_INVALID")
        source = sources[proof["sourceId"]]
        target = next(t for t in source["targets"] if t["positionIndex"] == proof["positionIndex"])
        reference = frozen_content_reference(frozen.game_id, source, target)
        if reference is None:
            raise ValueError("INPUT_CONTENT_REFERENCE_REQUIRED")
        board = BoardPreset.model_validate(proof["boardPreset"])
        geometry = (
            None
            if proof["geometry"] is None
            else BoardCropGeometryV1.model_validate(proof["geometry"])
        )
        if (
            calibration_routing_sha(
                plan["candidateManifestSha256"], board, proof["routing"], proof["path"]
            )
            != plan["routingSha256"]
        ):
            raise ValueError("INPUT_CONTENT_ROUTING_CHANGED")
        frame = snapshot.frame(source, "VALIDATION")
        values = _input(frame, reference, proof["screenQuad"], board, geometry)
        if (
            any(proof[key] != value for key, value in values.items())
            or proof["contentReferenceSha256"] != target["contentReferenceSha256"]
            or proof["contentReferenceRevision"] != target["contentReferenceRevision"]
            or proof["sourceRepresentativeSha256"] != reference.sourceRepresentativeSha256
        ):
            raise ValueError("INPUT_CONTENT_EVIDENCE_CHANGED")
        key = reference.sourceRepresentativeSha256, reference.positionIndex
        if key in seen:
            raise ValueError("INPUT_CONTENT_EVIDENCE_DUPLICATE")
        seen.add(key)
        if type(values["inputCropped"]) is bool:
            verified[key] = (
                target["contentReferenceSha256"],
                target["contentReferenceRevision"],
                values["inputCropped"],
            )
    return replace(frozen, content_references=verified)


def verify_input(
    frame: Any,
    source: Mapping[str, Any],
    target: Mapping[str, Any],
    proof: Mapping[str, Any] | None,
    game: UUID,
) -> dict[str, Any] | None:
    if proof is None:
        return None
    reference = frozen_content_reference(game, source, target)
    if reference is None or proof.get("sha256") != digest(
        {k: v for k, v in proof.items() if k != "sha256"}
    ):
        raise ValueError("INPUT_CONTENT_EVIDENCE_INVALID")
    if (
        proof["sourceId"] != source["sourceId"]
        or proof["positionIndex"] != target["positionIndex"]
        or proof["sourceRepresentativeSha256"] != reference.sourceRepresentativeSha256
        or proof["contentReferenceSha256"] != target["contentReferenceSha256"]
        or proof["contentReferenceRevision"] != target["contentReferenceRevision"]
    ):
        raise ValueError("INPUT_CONTENT_REFERENCE_CHANGED")
    board = BoardPreset.model_validate(proof["boardPreset"])
    geometry = (
        None if proof["geometry"] is None else BoardCropGeometryV1.model_validate(proof["geometry"])
    )
    actual = _input(frame, reference, proof["screenQuad"], board, geometry)
    if any(proof[key] != value for key, value in actual.items()):
        raise ValueError("INPUT_CONTENT_EVIDENCE_CHANGED")
    return dict(proof)
