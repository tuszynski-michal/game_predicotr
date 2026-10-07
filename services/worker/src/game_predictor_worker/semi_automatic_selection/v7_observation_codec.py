"""Lossless, versioned observations for replay without image recognition."""

from __future__ import annotations

import hashlib
import json
from typing import cast

from .contracts import SemiAutomaticSelectionRange
from .v7_quality import V7FrameQuality
from .v7_range_proof import (
    V7LabelEvidence,
    V7RangeProofKind,
    V7RangeProofResult,
    V7WeakFrameEvidence,
)
from .v7_run_state import (
    V7RunStateError,
    V7ScanObservation,
    _board_quality,
    _frame_quality_as_dict,
    _observation_diagnostics,
)


def advance_observation_digest(previous_digest: str, observation: V7ScanObservation) -> str:
    """Bind the committed ordered prefix using one constant-size digest."""
    if len(previous_digest) != 64 or any(c not in "0123456789abcdef" for c in previous_digest):
        raise V7RunStateError("V7_RUN_STATE_CHECKPOINT_INVALID", "Invalid observation digest.")
    content = json.dumps(
        serialize_scan_observation(observation),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(bytes.fromhex(previous_digest) + content).hexdigest()


def serialize_scan_observation(observation: V7ScanObservation) -> dict[str, object]:
    weak = observation.weak_evidence
    return {
        "version": "v7-resume-observation-v1",
        **_observation_diagnostics(observation),
        "quality": None
        if observation.quality is None
        else _frame_quality_as_dict(observation.quality),
        "weakEvidence": None
        if weak is None
        else {
            "sourceId": weak.source_id,
            "labels": [_label_payload(label) for label in weak.labels],
            "visualHash": str(weak.visual_hash),
            "visualSignature": weak.visual_signature.hex(),
        },
    }


def deserialize_scan_observation(raw: object) -> V7ScanObservation:
    """Reject malformed/noncanonical state rather than repairing missing evidence."""
    try:
        value = _mapping(raw)
        if value["version"] != "v7-resume-observation-v1":
            raise ValueError("Unknown observation version.")
        proof = _mapping(value["proof"])
        start, end = proof["rangeStart"], proof["rangeEnd"]
        sequence_range = (
            None
            if start is None and end is None
            else SemiAutomaticSelectionRange(_integer(start), _integer(end))
        )
        quality_raw = value["quality"]
        quality = None
        if quality_raw is not None:
            q = _mapping(quality_raw)
            quality = V7FrameQuality(
                source_id=_text(q["sourceId"]),
                source_index=_integer(q["sourceIndex"]),
                boards=tuple(_board_quality(board) for board in _items(q["boards"])),
            )
        weak_raw = value["weakEvidence"]
        weak = None
        if weak_raw is not None:
            w = _mapping(weak_raw)
            weak = V7WeakFrameEvidence(
                source_id=_text(w["sourceId"]),
                labels=tuple(_label(label) for label in _items(w["labels"])),
                visual_hash=int(_text(w["visualHash"])),
                visual_signature=bytes.fromhex(_text(w["visualSignature"])),
            )
        error = value["sourceErrorCode"]
        observation = V7ScanObservation(
            source_index=_integer(value["sourceIndex"]),
            proof=V7RangeProofResult(
                kind=V7RangeProofKind(_text(proof["kind"])),
                sequence_range=sequence_range,
                supporting_source_ids=tuple(
                    _text(item) for item in _items(proof["supportingSourceIds"])
                ),
                reason_codes=tuple(_text(item) for item in _items(proof["reasonCodes"])),
            ),
            quality=quality,
            source_error_code=None if error is None else _text(error),
            weak_evidence=weak,
            labels=tuple(_label(label) for label in _items(value["labels"])),
            observed_position_indices=tuple(
                _integer(item) for item in _items(value["observedPositionIndices"])
            ),
        )
        if serialize_scan_observation(observation) != value:
            raise ValueError("Observation is not canonical.")
        return observation
    except (KeyError, TypeError, ValueError) as error:
        raise V7RunStateError(
            "V7_RUN_STATE_CHECKPOINT_INVALID", "The resume observation is invalid."
        ) from error


def _label_payload(label: V7LabelEvidence) -> dict[str, object]:
    return {
        "positionIndex": label.position_index,
        "sequenceNumber": label.sequence_number,
        "recognitionConfidence": label.recognition_confidence,
        "positionConfidence": label.position_confidence,
    }


def _label(raw: object) -> V7LabelEvidence:
    value = _mapping(raw)
    return V7LabelEvidence(
        position_index=_integer(value["positionIndex"]),
        sequence_number=_integer(value["sequenceNumber"]),
        recognition_confidence=_number(value["recognitionConfidence"]),
        position_confidence=_number(value["positionConfidence"]),
    )


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("Expected an object.")
    return cast(dict[str, object], value)


def _items(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("Expected a list.")
    return value


def _integer(value: object) -> int:
    if type(value) is not int:
        raise ValueError("Expected an integer.")
    return value


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("Expected a number.")
    return float(value)


def _text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("Expected nonempty text.")
    return value
