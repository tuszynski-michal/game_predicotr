"""Project frozen source bindings into review drafts without canonical geometry."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import cast

from game_predictor_api.domain.image_geometry_v2 import canonical_json_bytes
from game_predictor_api.domain.neural_grid_proposal import (
    NEURAL_GRID_PREFLIGHT_POLICY_VERSION,
    NEURAL_GRID_REVIEW_REASON,
    validate_neural_source_binding,
    validate_neural_source_proposal,
)

from .source_ingestion import ManagedOriginal


def bound_neural_originals(
    originals: Sequence[ManagedOriginal], entries: Mapping[str, object]
) -> tuple[ManagedOriginal, ...]:
    """Expose effective attested ranges only when the immutable source is bound."""
    result = []
    for original in originals:
        entry = entries.get(original.checksum_sha256)
        if (
            not isinstance(entry, Mapping)
            or entry.get("status") != "review_required"
            or entry.get("neuralProposalBinding") is None
        ):
            continue
        proposal = validate_neural_source_proposal(entry.get("neuralProposal"))
        binding = validate_neural_source_binding(entry["neuralProposalBinding"], proposal)
        if proposal["sourceChecksumSha256"] != original.checksum_sha256 or proposal[
            "originalRange"
        ] != {
            "sequenceRangeStart": original.sequence_range_start,
            "sequenceRangeEnd": original.sequence_range_end,
        }:
            raise ValueError("A neural source binding differs from its immutable original.")
        active = cast(Mapping[str, int], binding["confirmedRange"])
        result.append(
            replace(
                original,
                sequence_range_start=active["sequenceRangeStart"],
                sequence_range_end=active["sequenceRangeEnd"],
                sequence_range_source="neural_source_binding_v1",
            )
        )
    return tuple(result)


def neural_pending_payload(
    manual: Mapping[str, object], entry: Mapping[str, object]
) -> dict[str, object]:
    """Keep all active positions, including missing middle cells, in deferred review."""
    proposal = validate_neural_source_proposal(entry.get("neuralProposal"))
    binding = validate_neural_source_binding(entry.get("neuralProposalBinding"), proposal)
    active = cast(Mapping[str, int], binding["confirmedRange"])
    start, end = active["sequenceRangeStart"], active["sequenceRangeEnd"]
    if (
        manual["sourceChecksumSha256"] != proposal["sourceChecksumSha256"]
        or manual["canonicalWidth"] != proposal["sourceWidth"]
        or manual["canonicalHeight"] != proposal["sourceHeight"]
    ):
        raise ValueError("Neural pending geometry requires the exact normalized source.")
    detections = {
        cast(str, item["detectionId"]): item
        for item in cast(list[Mapping[str, object]], proposal["detections"])
    }
    assigned = {
        cast(int, item["positionIndex"]): detections[cast(str, item["detectionId"])]
        for item in cast(list[Mapping[str, object]], binding["assignments"])
    }
    raw_boards = cast(Sequence[Mapping[str, object]], manual["boards"])
    if len(raw_boards) != end - start + 1:
        raise ValueError("The pending board slots differ from the confirmed source range.")
    boards = []
    projected = []
    for position, raw_board in enumerate(raw_boards):
        detection = assigned.get(position)
        nodes = None if detection is None else detection["latticeNodes"]
        quad = (
            None
            if nodes is None
            else [cast(list[object], nodes)[index] for index in (0, 5, 23, 18)]
        )
        reasons = [NEURAL_GRID_REVIEW_REASON]
        if detection is None:
            reasons.append("NEURAL_GRID_SLOT_DETECTION_MISSING")
        else:
            reasons.extend(cast(list[str], detection["reasonCodes"]))
        shared = {
            "latticeNodes": nodes,
            "neuralProposalChecksumSha256": proposal["proposalChecksumSha256"],
            "detectionId": None if detection is None else detection["detectionId"],
            "neuralProposalBinding": dict(binding),
        }
        board = {
            **raw_board,
            **shared,
            "positionIndex": position,
            "sequenceNumber": start + position,
            "initialQuad": quad,
            "reviewDraftQuad": quad,
            "finalQuad": None,
            "reviewDraftOrigin": "neural_grid_v1",
            "reasonCodes": list(dict.fromkeys(reasons)),
            "geometryConfidence": 0.0 if detection is None else detection["score"],
        }
        boards.append(board)
        projected.append(
            {
                "positionIndex": position,
                "sequenceNumber": start + position,
                "confidence": 0.0 if detection is None else detection["score"],
                "geometry": {
                    "quad": quad,
                    **shared,
                    "structuredDisposition": "needs_manual_review",
                },
                "reasonCodes": list(dict.fromkeys(reasons)),
            }
        )
    structured = {
        **manual,
        "boards": boards,
        "geometrySource": "auto",
        "engineKind": "neural_grid_v1",
        "engineVersion": NEURAL_GRID_PREFLIGHT_POLICY_VERSION,
        "status": "needs_review",
        "reasonCodes": [NEURAL_GRID_REVIEW_REASON],
        "neuralProposalBinding": dict(binding),
    }
    structured.pop("resultChecksumSha256", None)
    structured["resultChecksumSha256"] = hashlib.sha256(
        canonical_json_bytes(structured)
    ).hexdigest()
    return {"manualGeometryRequired": True, "structuredGeometry": structured, "boards": projected}
