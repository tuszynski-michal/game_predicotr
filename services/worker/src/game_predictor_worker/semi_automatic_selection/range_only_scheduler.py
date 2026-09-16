"""Deterministic visual scheduling for expensive range-only OCR probes.

Appearance is used only to decide when OCR should run.  It never becomes range
evidence and therefore cannot assign, interpolate, or validate a sequence.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

import numpy as np
from numpy.typing import NDArray

from game_predictor_worker.images.selection.adapters import (
    OpenCvAppearanceFingerprintAnalyzer,
)
from game_predictor_worker.images.selection.engine import appearance_distance
from game_predictor_worker.images.selection.manifest import AppearanceDescriptorConfig
from game_predictor_worker.images.selection.ports import ThumbnailFrame

from .contracts import SemiAutomaticSelectionError
from .range_only_ocr import RangeOnlyOcrSchedulingPolicy

RANGE_ONLY_OCR_SCHEDULER_CHECKPOINT_SCHEMA_VERSION = 1
RANGE_ONLY_OCR_SKIPPED_REASON = "RANGE_OCR_SKIPPED_VISUAL_REDUNDANCY"


@dataclass(frozen=True, slots=True)
class RangeOnlyOcrProbeDecision:
    source_index: int
    should_probe: bool
    reason: str
    adjacent_distance: float | None
    last_probe_distance: float | None


class AdaptiveRangeOcrProbeScheduler:
    """Probe boundaries and a fixed interval while consuming every source once."""

    def __init__(
        self,
        policy: RangeOnlyOcrSchedulingPolicy,
        *,
        checkpoint: Mapping[str, object] | None = None,
    ) -> None:
        self._policy = policy
        self._descriptor_config = AppearanceDescriptorConfig()
        self._analyzer = OpenCvAppearanceFingerprintAnalyzer(self._descriptor_config)
        if self._analyzer.version != policy.appearance_descriptor_version:
            raise ValueError("The appearance descriptor differs from the scheduling policy.")
        self._signature_length = _appearance_signature_length(self._descriptor_config)
        self._policy_fingerprint = _canonical_sha256(policy.as_dict())
        self._next_source_index = 0
        self._previous_signature: tuple[float, ...] | None = None
        self._last_probe_signature: tuple[float, ...] | None = None
        self._last_probe_source_index: int | None = None
        self._force_next_probe = False
        if checkpoint is not None:
            self._restore(checkpoint)

    @property
    def next_source_index(self) -> int:
        return self._next_source_index

    @property
    def policy_fingerprint(self) -> str:
        return self._policy_fingerprint

    def decide(
        self,
        *,
        source_index: int,
        thumbnail_rgb: NDArray[np.uint8],
    ) -> RangeOnlyOcrProbeDecision:
        if thumbnail_rgb.ndim != 3 or thumbnail_rgb.shape[2] != 3:
            raise ValueError("Range-only OCR scheduling requires an RGB thumbnail.")
        height, width = thumbnail_rgb.shape[:2]
        if min(height, width) < 1:
            raise ValueError("Range-only OCR scheduling requires a non-empty thumbnail.")
        fingerprint = self._analyzer.analyze(
            ThumbnailFrame(
                rgb=thumbnail_rgb,
                source_width=width,
                source_height=height,
            )
        )
        return self.decide_signature(
            source_index=source_index,
            signature=fingerprint.appearance_signature,
        )

    def decide_signature(
        self,
        *,
        source_index: int,
        signature: Sequence[float],
    ) -> RangeOnlyOcrProbeDecision:
        self._require_next(source_index)
        current = tuple(float(value) for value in signature)
        if len(current) != self._signature_length or not all(
            np.isfinite(value) for value in current
        ):
            raise ValueError("The appearance signature is invalid.")

        adjacent = self._distance(self._previous_signature, current)
        from_probe = self._distance(self._last_probe_signature, current)
        if self._last_probe_source_index is None:
            should_probe, reason = True, "first_source"
        elif self._force_next_probe:
            should_probe, reason = True, "after_unavailable_source"
        elif (
            (adjacent is not None and adjacent >= self._policy.strong_boundary_distance)
            or (
                from_probe is not None
                and from_probe >= self._policy.strong_boundary_distance
            )
        ):
            should_probe, reason = True, "visual_boundary"
        elif (
            source_index - self._last_probe_source_index
            >= self._policy.maximum_probe_interval
        ):
            should_probe, reason = True, "bounded_interval"
        else:
            should_probe, reason = False, "visual_redundancy"

        self._previous_signature = current
        self._next_source_index += 1
        self._force_next_probe = False
        if should_probe:
            self._last_probe_signature = current
            self._last_probe_source_index = source_index
        return RangeOnlyOcrProbeDecision(
            source_index=source_index,
            should_probe=should_probe,
            reason=reason,
            adjacent_distance=adjacent,
            last_probe_distance=from_probe,
        )

    def record_unavailable(self, *, source_index: int) -> None:
        """Advance deterministic state after a JPEG cannot be decoded."""

        self._require_next(source_index)
        self._next_source_index += 1
        self._previous_signature = None
        self._force_next_probe = True

    def force_probe_after_failure(self) -> None:
        """Make the next source a probe when a scheduled full decode failed."""

        if self._next_source_index < 1:
            _checkpoint_error("OCR scheduling cannot recover before consuming a source.")
        self._previous_signature = None
        self._force_next_probe = True

    def checkpoint(self) -> dict[str, object]:
        return {
            "forceNextProbe": self._force_next_probe,
            "lastProbeSignature": _signature_payload(self._last_probe_signature),
            "lastProbeSourceIndex": self._last_probe_source_index,
            "nextSourceIndex": self._next_source_index,
            "policyFingerprint": self._policy_fingerprint,
            "previousSignature": _signature_payload(self._previous_signature),
            "schemaVersion": RANGE_ONLY_OCR_SCHEDULER_CHECKPOINT_SCHEMA_VERSION,
        }

    def _distance(
        self,
        previous: tuple[float, ...] | None,
        current: tuple[float, ...],
    ) -> float | None:
        if previous is None:
            return None
        return appearance_distance(previous, current, self._descriptor_config)

    def _require_next(self, source_index: int) -> None:
        if source_index != self._next_source_index:
            _checkpoint_error("OCR probe sources must be consumed once in source order.")

    def _restore(self, value: Mapping[str, object]) -> None:
        try:
            if (
                value.get("schemaVersion")
                != RANGE_ONLY_OCR_SCHEDULER_CHECKPOINT_SCHEMA_VERSION
                or value.get("policyFingerprint") != self._policy_fingerprint
            ):
                raise ValueError("contract mismatch")
            next_source_index = _strict_int(value["nextSourceIndex"])
            last_probe_source_index = _optional_int(value.get("lastProbeSourceIndex"))
            previous_signature = _restore_signature(
                value.get("previousSignature"),
                expected_length=self._signature_length,
            )
            last_probe_signature = _restore_signature(
                value.get("lastProbeSignature"),
                expected_length=self._signature_length,
            )
            force_next_probe = value["forceNextProbe"]
            if not isinstance(force_next_probe, bool):
                raise ValueError("invalid force flag")
            if (
                next_source_index < 0
                or (last_probe_source_index is None) != (last_probe_signature is None)
                or (
                    last_probe_source_index is not None
                    and not 0 <= last_probe_source_index < next_source_index
                )
                or (next_source_index == 0 and previous_signature is not None)
            ):
                raise ValueError("invalid scheduler state")
        except (KeyError, TypeError, ValueError) as error:
            raise SemiAutomaticSelectionError(
                "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
                "The durable OCR scheduling checkpoint is invalid.",
            ) from error
        self._next_source_index = next_source_index
        self._last_probe_source_index = last_probe_source_index
        self._previous_signature = previous_signature
        self._last_probe_signature = last_probe_signature
        self._force_next_probe = force_next_probe


def _signature_payload(value: tuple[float, ...] | None) -> list[float] | None:
    return None if value is None else list(value)


def _restore_signature(
    value: object,
    *,
    expected_length: int,
) -> tuple[float, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list) or len(value) != expected_length:
        raise ValueError("invalid signature")
    raw = cast(list[object], value)
    if any(not isinstance(item, int | float) or isinstance(item, bool) for item in raw):
        raise ValueError("invalid signature values")
    signature = tuple(float(cast(int | float, item)) for item in raw)
    if not all(np.isfinite(item) for item in signature):
        raise ValueError("invalid signature values")
    return signature


def _appearance_signature_length(config: AppearanceDescriptorConfig) -> int:
    return (
        config.phash_size * config.phash_size
        + config.hue_bins
        + config.saturation_bins
        + config.value_bins
        + config.edge_grid_rows * config.edge_grid_columns
        + config.edge_orientation_bins
    )


def _optional_int(value: object) -> int | None:
    return None if value is None else _strict_int(value)


def _strict_int(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("integer required")
    return value


def _canonical_sha256(value: Mapping[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


def _checkpoint_error(message: str) -> None:
    raise SemiAutomaticSelectionError(
        "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
        message,
    )


__all__ = [
    "RANGE_ONLY_OCR_SCHEDULER_CHECKPOINT_SCHEMA_VERSION",
    "RANGE_ONLY_OCR_SKIPPED_REASON",
    "AdaptiveRangeOcrProbeScheduler",
    "RangeOnlyOcrProbeDecision",
]
