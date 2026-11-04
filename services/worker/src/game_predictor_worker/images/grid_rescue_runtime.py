"""Immutable attempt receipts: loss of a result never replenishes rescue budget."""

from __future__ import annotations

import json
import os
import tempfile
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, cast

import cv2
from game_predictor_api.domain.grid_rescue_policy import require_rescue_evidence, require_rescue_pin

from ..geometry_core.bounded_runtime import GeometryRuntimeError
from ..geometry_core.inference import BoardDetection
from ..geometry_core.rescue import GridRescueVariantV1
from ..geometry_core.rescue_serialization import detection_document, detection_from_document
from ..training_core.grid_training_admission import canonical, digest
from .grid_rescue_strategy import execute_path


class RescueAttemptStore:
    def __init__(self, directory: Path, identity: Mapping[str, Any]) -> None:
        self.directory, self.identity = directory, dict(identity)
        self.position_alias = False
        directory.mkdir(parents=True, exist_ok=True)

    def _read(self, path: Path, *, allow_position_alias: bool = False) -> dict[str, Any]:
        if path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("GRID_RESCUE_CHECKPOINT_LIMIT")
        value = json.loads(path.read_text(encoding="utf-8"))
        if (
            set(value) != {"identity", "payload", "sha256"}
            or not isinstance(value["identity"], dict)
            or value["sha256"]
            != digest({"identity": value["identity"], "payload": value["payload"]})
        ):
            raise ValueError("GRID_RESCUE_CHECKPOINT_INVALID")
        if not isinstance(value["payload"], dict):
            raise ValueError("GRID_RESCUE_CHECKPOINT_INVALID")
        if value["identity"] != self.identity:
            stored = value["identity"]
            same_except_positions = (
                allow_position_alias
                and isinstance(stored.get("positions"), list)
                and isinstance(self.identity.get("positions"), list)
                and {k: v for k, v in stored.items() if k != "positions"}
                == {k: v for k, v in self.identity.items() if k != "positions"}
            )
            if not same_except_positions:
                raise ValueError("GRID_RESCUE_CHECKPOINT_INVALID")
            # Same bytes in the same operation reuse the first immutable scope.
            # This caller may read baseline/receipts, but cannot spend any tokens.
            self.identity = stored
            self.position_alias = True
        return cast(dict[str, Any], value["payload"])

    def _create(self, path: Path, payload: dict[str, Any]) -> bool:
        value = {"identity": self.identity, "payload": payload}
        content = canonical({**value, "sha256": digest(value)})
        descriptor, temporary = tempfile.mkstemp(prefix=".rescue-pending-", dir=path.parent)
        pending = Path(temporary)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                # Same-directory hard-link publication is atomic and never replaces
                # an existing target. Interrupted temporary files are never receipts.
                os.link(pending, path)
            except FileExistsError:
                # Every caller validates the winning complete receipt below.
                return False
        finally:
            pending.unlink(missing_ok=True)
        if self._read(path) != payload:
            raise ValueError("GRID_RESCUE_CHECKPOINT_INVALID")
        return True

    def baseline(self, calculate: Callable[[], list[BoardDetection]]) -> list[BoardDetection]:
        path = self.directory / "baseline.json"
        if not path.exists():
            self._create(path, {"detections": [detection_document(item) for item in calculate()]})
        value = self._read(path, allow_position_alias=True)
        return [detection_from_document(item) for item in value["detections"]]

    def attempt(
        self, key: str, request: dict[str, Any], calculate: Callable[[], list[BoardDetection]]
    ) -> list[BoardDetection] | None:
        if self.position_alias:
            raise ValueError("GRID_RESCUE_SLOT_BINDING_REQUIRED")
        if key != "redetect" and not (
            key.startswith("crop-") and key[5:] in {str(i) for i in range(9)}
        ):
            raise ValueError("GRID_RESCUE_ATTEMPT_KEY_INVALID")
        reserved, result = (
            self.directory / f"{key}.reserved.json",
            self.directory / f"{key}.result.json",
        )
        reservation = {"state": "reserved", "request": request}
        fresh = self._create(reserved, reservation)
        if self._read(reserved) != reservation:
            raise ValueError("GRID_RESCUE_ATTEMPT_PIN_CHANGED")
        if not fresh:
            if not result.exists():
                return None
        else:
            self._create(
                result,
                {
                    "reservationSha256": digest(reservation),
                    "detections": [detection_document(item) for item in calculate()],
                },
            )
        value = self._read(result)
        if value["reservationSha256"] != digest(reservation):
            raise ValueError("GRID_RESCUE_CHECKPOINT_INVALID")
        return [detection_from_document(item) for item in value["detections"]]

    def summary(self, reasons: tuple[str, ...]) -> dict[str, Any]:
        attempts = []
        for key in ("redetect", *(f"crop-{position}" for position in range(9))):
            reserved = self.directory / f"{key}.reserved.json"
            if not reserved.exists():
                continue
            reservation = self._read(reserved)
            result = self.directory / f"{key}.result.json"
            completed = self._read(result) if result.exists() else None
            attempts.append(
                {
                    "attempt": key,
                    "request": reservation["request"],
                    "reservationSha256": digest(reservation),
                    "resultSha256": None if completed is None else digest(completed),
                    "state": "consumed_without_result" if completed is None else "completed",
                }
            )
        value = {
            "contractVersion": "grid-rescue-execution-v1",
            "preprocessingContract": "neural-grid-rescue-preprocessing-v1",
            "identity": self.identity,
            "attempts": attempts,
            "reasonCodes": list(reasons),
        }
        return {**value, "sha256": digest(value)}


def run_with_rescue(
    *,
    runner: Any,
    bundle: Path,
    bundle_sha: str,
    rgb: Any,
    heartbeat: Callable[[], None],
    max_seconds: float,
    directory: Path,
    source_sha: str,
    pin: Mapping[str, Any] | None,
    expected_positions: set[int],
    summary_sink: dict[str, Any] | None = None,
) -> list[BoardDetection]:
    if pin is None:
        return cast(
            list[BoardDetection],
            runner.run(bundle, bundle_sha, rgb, heartbeat=heartbeat, max_seconds=max_seconds),
        )
    deadline = time.monotonic() + max_seconds

    def remaining() -> float:
        value = deadline - time.monotonic()
        if value <= 0:
            raise GeometryRuntimeError(
                "NEURAL_GRID_SOURCE_TIME_LIMIT", "Bounded rescue exceeded the source deadline."
            )
        return value

    checked = require_rescue_pin(dict(pin), bundle_sha=bundle_sha)
    bundle_file = bundle / "bundle.json"
    if bundle_file.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("GRID_RESCUE_BUNDLE_CHANGED")
    content = bundle_file.read_bytes()
    import hashlib

    if len(content) > 16 * 1024 * 1024 or hashlib.sha256(content).hexdigest() != bundle_sha:
        raise ValueError("GRID_RESCUE_BUNDLE_CHANGED")
    proof = require_rescue_evidence(json.loads(content))
    if (
        proof["sha256"] != checked["proofSha256"]
        or proof["selection"]["selectedPath"] != checked["selectedPath"]
        or proof["recipe"]["variantId"] != checked["variantId"]
    ):
        raise ValueError("GRID_RESCUE_PIN_CHANGED")
    store = RescueAttemptStore(
        directory / source_sha,
        {
            "sourceSha256": source_sha,
            "pin": checked,
            "baselinePresetSha256": proof["recipe"]["baselinePresetSha256"],
            "opencvVersion": cv2.__version__,
            "preprocessingContract": "neural-grid-rescue-preprocessing-v1",
            "positions": sorted(expected_positions),
            "width": int(rgb.shape[1]),
            "height": int(rgb.shape[0]),
        },
    )
    found = store.baseline(
        lambda: runner.run(bundle, bundle_sha, rgb, heartbeat=heartbeat, max_seconds=remaining())
    )
    if store.position_alias:
        for detection in found:
            detection.reasons = list(
                dict.fromkeys([*detection.reasons, "NEURAL_GRID_SLOT_BINDING_REQUIRED"])
            )
        if summary_sink is not None:
            summary_sink.update(store.summary(("GRID_RESCUE_SLOT_BINDING_REQUIRED",)))
        return found
    variant = GridRescueVariantV1.model_validate(checked["variant"])

    def detect(geometry: Any) -> list[BoardDetection] | None:
        request = {
            "kind": "screen",
            "geometry": geometry.model_dump(mode="json"),
            "opencvVersion": cv2.__version__,
            "preprocessingContract": "neural-grid-rescue-preprocessing-v1",
        }
        return store.attempt(
            "redetect",
            request,
            lambda: runner.run_stage(
                bundle,
                bundle_sha,
                rgb,
                request=request,
                heartbeat=heartbeat,
                max_seconds=remaining(),
            ),
        )

    def recrop(position: int, detection: BoardDetection, geometry: Any) -> BoardDetection | None:
        request = {
            "kind": "board",
            "geometry": None if geometry is None else geometry.model_dump(mode="json"),
            "opencvVersion": cv2.__version__,
            "preprocessingContract": "neural-grid-rescue-preprocessing-v1",
            "detection": detection_document(detection),
        }
        result = store.attempt(
            f"crop-{position}",
            request,
            lambda: runner.run_stage(
                bundle,
                bundle_sha,
                rgb,
                request=request,
                heartbeat=heartbeat,
                max_seconds=remaining(),
            ),
        )
        if result is not None and len(result) != 1:
            raise ValueError("GRID_RESCUE_CROP_RESULT_INVALID")
        return None if result is None else result[0]

    reasons: tuple[str, ...] = ("GRID_RESCUE_EXECUTION_INTERRUPTED",)
    try:
        result = execute_path(
            found,
            width=rgb.shape[1],
            height=rgb.shape[0],
            variant=variant,
            path=checked["selectedPath"],
            detect=detect,
            recrop=recrop,
            expected_positions=expected_positions,
        )
        reasons = result.reasons
    finally:
        if summary_sink is not None:
            summary_sink.update(store.summary(reasons))
    return result.detections
