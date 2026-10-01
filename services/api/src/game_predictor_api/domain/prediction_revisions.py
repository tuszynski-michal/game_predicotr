"""Shape and digest of symbol prediction revisions (D-467 S8, TASK-0794; D-466).

``image_symbol_prediction_revisions.predictions`` is a list with one entry per
predicted cell.  A virtual cell entry carries ``virtualCell`` with the render
identity of the cell it was predicted from: checksums and logical keys.  Up
to TASK-0794 it also carried the full ``renderSpec`` (a copy of the board
render manifest entry, ~2.5 KB per cell); the slim shape
(``PREDICTION_VIRTUAL_CELL_SCHEMA``) drops it and new revisions must not
carry it.

Digests used by the reference-library runs (D-466):

- v1 (``predictions_digest_v1``): sha256 of the canonical JSON of the stored
  list, i.e. of whatever shape the row had;
- v2 (``predictions_digest``): sha256 of the canonical JSON of the slim
  projection, so a full revision and the same revision after slimming have
  the same v2 digest.

Manifests written before TASK-0794 carry v1 digests of full revisions; the
slimming script keeps that value in ``legacy_predictions_sha256``.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any, Final

PREDICTION_VIRTUAL_CELL_SCHEMA: Final = "slim-v2"
PREDICTIONS_DIGEST_VERSION: Final = 2
VIRTUAL_CELL_KEY: Final = "virtualCell"
RENDER_SPEC_KEY: Final = "renderSpec"


class PredictionRevisionShapeError(ValueError):
    """A prediction revision payload does not have the slim shape."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def canonical_json(value: object) -> bytes:
    """The canonical JSON of the reference-library digests (unchanged since D-466)."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def has_virtual_render_spec(predictions: Sequence[object]) -> bool:
    """Whether any entry still carries ``virtualCell.renderSpec``."""

    return any(
        isinstance(entry, Mapping)
        and isinstance(entry.get(VIRTUAL_CELL_KEY), Mapping)
        and RENDER_SPEC_KEY in entry[VIRTUAL_CELL_KEY]
        for entry in predictions
    )


def slim_predictions(predictions: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Deep copy of the entries without ``virtualCell.renderSpec``; nothing else changes."""

    slim: list[dict[str, Any]] = []
    for entry in predictions:
        copied = copy.deepcopy(dict(entry))
        virtual = copied.get(VIRTUAL_CELL_KEY)
        if isinstance(virtual, dict):
            virtual.pop(RENDER_SPEC_KEY, None)
        slim.append(copied)
    return slim


def require_slim_predictions(predictions: object) -> None:
    """Reject a payload that is not a list or still carries ``virtualCell.renderSpec``."""

    if not isinstance(predictions, list):
        raise PredictionRevisionShapeError(
            "PREDICTION_REVISION_PREDICTIONS_INVALID",
            "Prediction revision predictions must be a list.",
        )
    if has_virtual_render_spec(predictions):
        raise PredictionRevisionShapeError(
            "PREDICTION_REVISION_RENDER_SPEC_PRESENT",
            "A prediction revision must not carry virtualCell.renderSpec "
            f"({PREDICTION_VIRTUAL_CELL_SCHEMA}); the render specification "
            "lives in the board render manifest.",
        )


def predictions_digest_v1(predictions: Sequence[Mapping[str, Any]]) -> str:
    """Digest of the stored list as it is (the pre-TASK-0794 ``predictions_digest``)."""

    return hashlib.sha256(canonical_json(list(predictions))).hexdigest()


def predictions_digest(predictions: Sequence[Mapping[str, Any]]) -> str:
    """Digest v2: the same value for a full revision and its slim form."""

    return predictions_digest_v1(slim_predictions(predictions))


def predictions_match(
    predictions: Sequence[Mapping[str, Any]],
    *,
    legacy_predictions_sha256: str | None,
    expected_sha256: str,
) -> bool:
    """Whether a planned digest (v1 or v2) still describes this revision.

    A v2 plan matches the slim projection.  A v1 plan of a revision that was
    not slimmed yet matches its stored list; once slimmed, it matches the v1
    digest the slimming kept in ``legacy_predictions_sha256``.
    """

    return expected_sha256 in {
        predictions_digest(predictions),
        predictions_digest_v1(predictions),
        legacy_predictions_sha256,
    }


__all__ = [
    "PREDICTIONS_DIGEST_VERSION",
    "PREDICTION_VIRTUAL_CELL_SCHEMA",
    "PredictionRevisionShapeError",
    "canonical_json",
    "has_virtual_render_spec",
    "predictions_digest",
    "predictions_digest_v1",
    "predictions_match",
    "require_slim_predictions",
    "slim_predictions",
]
