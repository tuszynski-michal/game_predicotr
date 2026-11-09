"""Project frozen source bindings into review drafts without canonical geometry."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import cast

from game_predictor_api.domain.image_geometry_v2 import canonical_json_bytes
from game_predictor_api.domain.neural_crop_policy import (
    LEGACY_NEURAL_AUTO_CROP_POLICY,
    NEURAL_AUTO_CROP_POLICY,
    SYMBOL_REVIEW_CROP_POLICY,
    neural_auto_crop_blockers,
    neural_auto_crop_evidence,
)
from game_predictor_api.domain.neural_grid_operation_pin import (
    operation_pin_blockers,
    symbol_review_qualification_blockers,
)
from game_predictor_api.domain.neural_grid_proposal import (
    NEURAL_GRID_PREFLIGHT_POLICY_VERSION,
    NEURAL_GRID_REVIEW_REASON,
    validate_neural_source_binding,
    validate_neural_source_proposal,
)
from game_predictor_api.domain.v3_engine_acceptance import (
    V3_ENGINE_ACCEPTANCE_POLICIES,
    is_game_scoped_neural_acceptance,
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
    manual: Mapping[str, object],
    entry: Mapping[str, object],
    *,
    automatic_crops: bool = False,
    execution_policy: str = LEGACY_NEURAL_AUTO_CROP_POLICY,
    engine_acceptance_policy: str | None = None,
    rows: int = 3,
    columns: int = 5,
    operation_pin: object = None,
    qualification_blockers: tuple[str, ...] | None = None,
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
        blockers = neural_auto_crop_blockers(
            policy=execution_policy,
            detection=detection,
            binding=binding,
            position=position,
            width=cast(int, proposal["sourceWidth"]),
            height=cast(int, proposal["sourceHeight"]),
            rows=rows,
            columns=columns,
        )
        if is_game_scoped_neural_acceptance(engine_acceptance_policy):
            blockers += operation_pin_blockers(
                operation_pin,
                model_snapshot=proposal["engineSnapshot"],
                game_id=str(proposal["gameId"]),
                for_symbol_review=engine_acceptance_policy == "v3-symbol-review-v1",
            )
            blockers += (
                symbol_review_qualification_blockers(qualification_blockers)
                if engine_acceptance_policy == "v3-symbol-review-v1"
                else qualification_blockers
                if qualification_blockers is not None
                else ("NEURAL_GRID_GAME_EVALUATION_UNCHECKED",)
            )
        if engine_acceptance_policy == "v3-engine-acceptance-v4":
            from game_predictor_api.domain.calibrated_neural_evidence import (
                calibrated_result_blockers,
            )

            evidence = cast(Mapping[str, object], entry.get("calibrationEvidence") or {}).get(
                "" if detection is None else str(detection["detectionId"])
            )
            blockers += calibrated_result_blockers(
                evidence, pin=operation_pin, proposal=proposal, detection=detection
            )
            shared["neuralCalibrationEvidence"] = evidence
        automatic = automatic_crops and not blockers
        if automatic_crops and execution_policy in (
            NEURAL_AUTO_CROP_POLICY,
            SYMBOL_REVIEW_CROP_POLICY,
        ):
            reasons.extend(blockers)
            if detection is not None:
                shared["neuralAcceptanceEvidence"] = neural_auto_crop_evidence(detection)
        if automatic:
            shared["neuralExecutionPolicy"] = execution_policy
        board = {
            **raw_board,
            **shared,
            "positionIndex": position,
            "sequenceNumber": start + position,
            "initialQuad": quad,
            "reviewDraftQuad": quad,
            "finalQuad": quad if automatic else None,
            **(
                {"disposition": "automatic" if automatic else "needs_manual_review"}
                if automatic_crops
                else {}
            ),
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
                    "structuredDisposition": "automatic" if automatic else "needs_manual_review",
                },
                "reasonCodes": list(dict.fromkeys(reasons)),
            }
        )
    structured = {
        **manual,
        "boards": boards,
        "geometrySource": "auto",
        "engineKind": "neural_grid_v1",
        "engineId": "neural_grid_v1" if automatic_crops else manual["engineId"],
        "engineVersion": execution_policy
        if automatic_crops
        else NEURAL_GRID_PREFLIGHT_POLICY_VERSION,
        "status": "needs_review",
        "reasonCodes": [NEURAL_GRID_REVIEW_REASON],
        "neuralProposalBinding": dict(binding),
    }
    structured.pop("resultChecksumSha256", None)
    if engine_acceptance_policy in V3_ENGINE_ACCEPTANCE_POLICIES:
        # Only new policy-pinned executions mint this immutable evidence.
        # Legacy checkpoints are replayed without reconstructing their payload.
        structured["globalInitialization"] = {
            **cast(Mapping[str, object], manual["globalInitialization"]),
            "v3EngineAcceptance": {
                "policyVersion": engine_acceptance_policy,
                "proposal": dict(proposal),
                "binding": dict(binding),
                **(
                    {"operationPin": operation_pin}
                    if is_game_scoped_neural_acceptance(engine_acceptance_policy)
                    else {}
                ),
            },
        }
    structured["resultChecksumSha256"] = hashlib.sha256(
        canonical_json_bytes(structured)
    ).hexdigest()
    return {
        "manualGeometryRequired": not automatic_crops,
        "structuredGeometry": structured,
        "boards": projected,
    }
