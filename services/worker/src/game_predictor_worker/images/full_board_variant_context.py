"""Resolve final results and independently replay their physical input witnesses."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from uuid import UUID

import numpy as np
from game_predictor_api.domain.full_board_variant_context import (
    make_variant_context,
    require_variant_context,
    require_variant_witness,
)
from game_predictor_api.domain.grid_model_registry import descriptor_sha256 as digest
from game_predictor_api.storage.grid_content_bundle import read_content_bundle_bytes

from ..geometry_core.rescue import GridRescueVariantV2
from .full_board_completeness import calibration_routing_sha
from .grid_rescue_strategy import slots
from .production_cell_input import verify_input


def _contexts(
    candidate_sha: str,
    screen: Mapping[str, Any],
    board: Mapping[str, Any],
    routing: Any,
    path: str | None,
    variant: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    if path not in (None, "combined") or (path is None and routing is not None):
        raise ValueError("VARIANT_ROUTE_UNSUPPORTED")
    route_sha = calibration_routing_sha(candidate_sha, board, routing, path)
    common = {
        "candidateManifestSha256": candidate_sha,
        "routingSha256": route_sha,
        "selectedPath": path,
        "screenPreset": dict(screen),
        "boardPreset": dict(board),
    }
    values = [
        make_variant_context(
            **common,
            stage="baseline",
            screenGeometry=None,
            boardGeometry=None,
        )
    ]
    if path == "combined":
        actual = GridRescueVariantV2.model_validate(variant)
        values.append(
            make_variant_context(
                **common,
                stage="wide",
                screenGeometry=actual.screen.model_dump(mode="json"),
                boardGeometry=actual.board.model_dump(mode="json"),
            )
        )
    return sorted(values, key=lambda value: value["sha256"])


def engine_variant_contexts(engine: Any, candidate_sha: str) -> list[dict[str, Any]]:
    core = getattr(engine, "engine", engine)
    variant = getattr(engine, "variant", None)
    return _contexts(
        candidate_sha,
        core.settings.screen.model_dump(mode="json"),
        core.settings.board.model_dump(mode="json"),
        getattr(engine, "routing", None),
        getattr(engine, "path", None),
        None if variant is None else variant.model_dump(mode="json"),
    )


def bundle_variant_contexts(bundle: Mapping[str, Any], candidate_sha: str) -> list[dict[str, Any]]:
    from game_predictor_api.domain.grid_content_experiment_evidence import (
        require_content_experiment_evidence,
    )

    require_content_experiment_evidence(bundle)
    rescue = bundle["contentRescue"]
    return _contexts(
        candidate_sha,
        bundle["preset"]["screen"],
        bundle["preset"]["board"],
        rescue["routing"],
        rescue["selectedPath"],
        rescue["variant"],
    )


def manifest_variant_contexts(root: Path, manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    from game_predictor_api.application.grid_model_evaluation import bundle_sha256

    path = (root / manifest["managedDirectory"] / "bundle.json").resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("VARIANT_BUNDLE_PATH_INVALID")
    payload = read_content_bundle_bytes(path)
    if hashlib.sha256(payload).hexdigest() != bundle_sha256(manifest):
        raise ValueError("VARIANT_BUNDLE_CHANGED")
    return bundle_variant_contexts(json.loads(payload), digest(manifest))


def resolve_final_stage(
    detection: Any,
    position: int,
    baseline: Sequence[Any],
    replacements: Sequence[int],
    *,
    combined: bool,
) -> str | None:
    if detection is None:
        return None
    if not combined:
        return "baseline"
    binding = slots(list(baseline))
    if not binding or position not in binding:
        return None
    original = baseline[binding[position]]
    if detection is original:
        return "baseline"
    # A final spatial rebind can move another BASE object's apparent position.
    # That object is never evidence of a successful WIDE replacement here.
    if any(detection is item for item in baseline):
        return None
    return "wide" if position in replacements else None


def observe_variant_witness(
    *,
    source: Mapping[str, Any],
    position: int,
    detection: Any,
    engine: Any,
    contexts: Sequence[Mapping[str, Any]],
    input_proof: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if detection is None or detection.nodes is None or input_proof is None:
        return None
    result = getattr(engine, "last_result", None)
    stage = resolve_final_stage(
        detection,
        position,
        getattr(engine, "last_baseline", []),
        () if result is None else result.replacement_positions,
        combined=getattr(engine, "path", None) == "combined",
    )
    context = next((c for c in contexts if c["stage"] == stage), None)
    if context is None:
        return None
    nodes = np.asarray(detection.nodes, dtype=np.float64).tolist()
    body = {
        "version": "full-board-final-variant-witness-v1",
        "sourceId": source["sourceId"],
        "sourceRepresentativeSha256": source["sourceIdentity"]["normalized_pixel_checksum_sha256"],
        "positionIndex": position,
        "variantKey": context["sha256"],
        "finalDetection": {
            "nodes": nodes,
            "screenQuad": np.asarray(detection.screen_quad, dtype=np.float64).tolist(),
        },
        "detectionNodesSha256": digest(nodes),
        "origin": "baseline" if stage == "baseline" else "replacement",
        "inputContentEvidence": dict(input_proof),
    }
    return require_variant_witness({**body, "sha256": digest(body)}, context)


def verify_variant_witness(
    snapshot: Any,
    source: Mapping[str, Any],
    target: Mapping[str, Any],
    witness: Mapping[str, Any],
    context: Mapping[str, Any],
    *,
    role: str,
    validation_purpose: str | None = None,
) -> dict[str, Any]:
    checked = require_variant_witness(witness, require_variant_context(context))
    if (
        checked["sourceId"] != source["sourceId"]
        or checked["positionIndex"] != target["positionIndex"]
    ):
        raise ValueError("VARIANT_WITNESS_TARGET_CHANGED")
    frame = snapshot.frame(source, role, validation_purpose=validation_purpose)
    if (
        verify_input(
            frame,
            source,
            target,
            checked["inputContentEvidence"],
            UUID(snapshot.manifest["gameId"]),
        )
        is None
    ):
        raise ValueError("VARIANT_INPUT_REFERENCE_REQUIRED")
    return checked
