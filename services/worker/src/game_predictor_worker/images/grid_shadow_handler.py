"""Bounded, opt-in V3 comparison on materialized sources; never updates primary grids."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from pathlib import Path, PurePosixPath
from typing import Any, Protocol
from uuid import UUID

import cv2
import numpy as np
from game_predictor_api.domain.catalog import GameShapeGeometryConfiguration
from game_predictor_api.domain.grid_engine_profiles import (
    GridEngineModelError,
    GridEngineModelVersion,
    grid_engine_manifest,
    grid_engine_profile_for,
)
from game_predictor_api.domain.grid_shadow import (
    GRID_SHADOW_MAX_SOURCES,
    GRID_SHADOW_VALIDATION_KIND,
    GridShadowError,
    shadow_digest,
    validate_shadow_output,
)
from game_predictor_api.domain.jobs import Job, JobType
from game_predictor_api.storage.grid_engine_model_store import ManagedGridEngineModelStore
from game_predictor_api.storage.grid_shadow import SqlAlchemyGridShadowRepository
from sqlalchemy.orm import Session, sessionmaker

from game_predictor_worker.geometry_core.bounded_runtime import (
    CPUShadowRunner,
    GeometryRuntimeError,
)
from game_predictor_worker.geometry_core.gate import (
    GateThresholds,
    NetworkBoard,
    ReferenceBoard,
    compare,
    decide,
)
from game_predictor_worker.geometry_core.inference import BoardDetection
from game_predictor_worker.geometry_core.lattice import lattice_cell_quads, structurally_valid
from game_predictor_worker.geometry_core.preprocessing import ByteImage, FloatArray, grid_from_quad
from game_predictor_worker.jobs.runtime import JobExecutionContext, JobHandlerError

from .normalization import CanonicalSourceLoader, CanonicalSourceLoadError

_RUN1_THRESHOLDS = GateThresholds(0.90, 0.04, 0.005)
_RUN1_WEIGHTS_SHA256 = "19b8d1382d5fe13b7e054b2d4eb846c25f7a91f680fa113b7d1d30571cdc80f9"
_MANUAL = "GRID_SHADOW_MANUAL_REVIEW_REQUIRED"
_UNCALIBRATED = "NEURAL_GRID_GATE_UNCALIBRATED"
_DEFAULT_SOURCE_SECONDS = 30.0


class BoundedRunner(Protocol):
    def run(
        self,
        bundle: Path,
        bundle_sha256: str,
        rgb: ByteImage,
        *,
        heartbeat: Callable[[], None],
        max_seconds: float,
    ) -> list[BoardDetection]: ...


def _nodes_json(nodes: FloatArray | None) -> list[dict[str, float]] | None:
    if nodes is None or not np.isfinite(nodes).all():
        return None
    return [{"x": float(x), "y": float(y)} for x, y in nodes]


def baseline_nodes(geometry: Mapping[str, object]) -> FloatArray | None:
    """Reconstruct the current source-direct quad; a review draft is not a baseline."""
    value = geometry.get("symbolGridQuad")
    if not isinstance(value, list | tuple) or len(value) != 4:
        return None
    try:
        quad = np.asarray(
            [[float(point["x"]), float(point["y"])] for point in value], dtype=np.float32
        )
    except (KeyError, TypeError, ValueError):
        return None
    nodes = grid_from_quad(quad)
    return nodes if structurally_valid(nodes) else None


def cell_visibility(nodes: FloatArray | None, width: int, height: int) -> list[str]:
    if nodes is None:
        return ["unknown"] * 15
    try:
        cells = lattice_cell_quads(nodes)
    except ValueError:
        return ["unknown"] * 15
    viewport = np.array([[0, 0], [width, 0], [width, height], [0, height]], dtype=np.float32)
    result = []
    for quad in cells:
        if bool(
            (quad[:, 0] >= 0).all()
            and (quad[:, 0] <= width).all()
            and (quad[:, 1] >= 0).all()
            and (quad[:, 1] <= height).all()
        ):
            result.append("full")
        else:
            area, _intersection = cv2.intersectConvexConvex(quad, viewport)
            result.append("partial" if area > 0 else "outside")
    return result


def build_shadow_output(
    source: Mapping[str, Any], detections: list[BoardDetection], *, calibrated: bool
) -> dict[str, object]:
    """Match by quad IoU, retain attested slot IDs, and isolate extra detections."""
    slots = source["baseline_slots"]
    references = [
        ReferenceBoard(slot["position_index"], baseline_nodes(slot["geometry"])) for slot in slots
    ]
    network = [
        NetworkBoard(
            nodes=detection.nodes,
            fit_residual=detection.fit_residual,
            fit_inliers=detection.fit_inliers,
            fit_failed="NEURAL_GRID_FIT_FAILED" in detection.reasons,
            score=detection.score,
            reasons=tuple(detection.reasons),
        )
        for index, detection in enumerate(detections)
    ]
    comparison = compare(references, network)
    # Comparison/pairing is independent of thresholds. Mumie never uses calibrated confidence.
    decisions = decide(comparison, _RUN1_THRESHOLDS).boards if calibrated else ()
    paired = {pair.reference_index: pair.network_index for pair in comparison.pairs}
    assigned = set(paired.values())
    reasons = [_MANUAL]
    if not calibrated:
        reasons.append(_UNCALIBRATED)
    outputs = []
    for index, (slot, reference) in enumerate(zip(slots, references, strict=True)):
        network_index = paired.get(index)
        detection = detections[network_index] if network_index is not None else None
        nodes = None if detection is None else detection.nodes
        slot_reasons = [_MANUAL]
        if not calibrated:
            slot_reasons.append(_UNCALIBRATED)
        if calibrated:
            decision = next((item for item in decisions if item.reference_index == index), None)
            if decision is not None:
                slot_reasons.extend(decision.reasons)
        if detection is None:
            slot_reasons.append("HYBRID_V3_REFERENCE_ONLY")
            if reference.nodes is None:
                slot_reasons.append("GRID_SHADOW_REFERENCE_UNAVAILABLE")
        else:
            slot_reasons.extend(detection.reasons)
        valid = nodes is not None and structurally_valid(nodes)
        state = "missing" if detection is None else "needs_review" if valid else "invalid"
        outputs.append(
            {
                "positionIndex": slot["position_index"],
                "sequenceNumber": slot["sequence_number"],
                "baselineNodes24": _nodes_json(reference.nodes),
                "neuralNodes24": _nodes_json(nodes),
                "state": state,
                "reasonCodes": list(dict.fromkeys(slot_reasons)),
                "cellVisibility": cell_visibility(
                    nodes if valid else reference.nodes, source["width"], source["height"]
                ),
            }
        )
    extras = [
        {
            "detectionIndex": index,
            "nodes24": _nodes_json(detection.nodes),
            "reasonCodes": ["GRID_SHADOW_UNASSIGNED_DETECTION", *detection.reasons],
        }
        for index, detection in enumerate(detections)
        if index not in assigned
    ]
    if extras:
        reasons.append("GRID_SHADOW_UNASSIGNED_DETECTIONS")
    if any(item["state"] == "missing" for item in outputs):
        reasons.append("GRID_SHADOW_GEOMETRY_INCOMPLETE")
    output: dict[str, object] = {
        "schemaVersion": 1,
        "status": "needs_review",
        "reasons": reasons,
        "slots": outputs,
        "unassignedDetections": extras,
    }
    validate_shadow_output(output, source)
    return output


class GridShadowHandler:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        artifact_root: Path,
        *,
        enabled: bool = False,
        threads: int = 1,
        runner: BoundedRunner | None = None,
        repository_factory: Callable[[Session], Any] = SqlAlchemyGridShadowRepository,
        model_store: Any = None,
        source_loader: CanonicalSourceLoader | None = None,
        clock: Callable[[], float] = time.monotonic,
        max_source_seconds: float = _DEFAULT_SOURCE_SECONDS,
    ) -> None:
        if not 1 <= threads <= 64 or not 0 < max_source_seconds <= 120:
            raise ValueError("Invalid bounded shadow runtime configuration.")
        self._sessions = session_factory
        self._root = artifact_root.resolve()
        self._enabled = enabled
        self._threads = threads
        self._runner = runner or CPUShadowRunner(threads)
        self._repositories = repository_factory
        self._models = model_store or ManagedGridEngineModelStore(self._root)
        self._loader = source_loader or CanonicalSourceLoader()
        self._clock = clock
        self._max_source_seconds = max_source_seconds

    def __call__(self, context: JobExecutionContext, job: Job) -> None:
        if not self._enabled:
            raise JobHandlerError("GRID_SHADOW_DISABLED", "Geometry comparison is disabled.")
        try:
            self._run(context, job)
        except (
            GridShadowError,
            GridEngineModelError,
            CanonicalSourceLoadError,
            GeometryRuntimeError,
        ) as error:
            raise JobHandlerError(error.code, str(error)) from error
        finally:
            self._loader.clear()

    def _run(self, context: JobExecutionContext, job: Job) -> None:
        payload = job.input_payload
        sources = payload.get("sources")
        model = payload.get("model")
        digest_input = {
            key: value for key, value in payload.items() if key != "input_digest_sha256"
        }
        if (
            job.game_id is None
            or job.job_type is not JobType.VALIDATE
            or payload.get("schema_version") != 1
            or payload.get("validation_kind") != GRID_SHADOW_VALIDATION_KIND
            or not isinstance(sources, list)
            or not 1 <= len(sources) <= GRID_SHADOW_MAX_SOURCES
            or not isinstance(model, dict)
            or payload.get("input_digest_sha256") != shadow_digest(digest_input)
        ):
            raise JobHandlerError(
                "GRID_SHADOW_INPUT_INVALID", "Pinned comparison input is invalid."
            )
        for source in sources:
            _validate_source(source)
        if len({source["source_image_id"] for source in sources}) != len(sources):
            raise JobHandlerError("GRID_SHADOW_INPUT_INVALID", "Duplicate pinned source IDs.")
        version = _registered_version(model)
        directory = self._models.require(version)
        for index, source in enumerate(sources):

            def heartbeat(completed: int = index) -> None:
                context.heartbeat()
                if context.job.cancel_requested_at is not None:
                    # The normal checkpoint transition finalizes cancellation and raises
                    # the runtime's stop signal. The bounded runner then reaps its child.
                    context.checkpoint(
                        checkpoint_payload={
                            "workflow": GRID_SHADOW_VALIDATION_KIND,
                            "next_source": completed,
                        },
                        stage="grid_geometry_shadow",
                        current=completed,
                        total=len(sources),
                        success_count=completed,
                        failure_count=0,
                        review_count=completed,
                    )

            heartbeat()
            started = self._clock()
            source_id = UUID(source["source_image_id"])
            with self._sessions.begin() as session:
                repository = self._repositories(session)
                current = repository.pin_source(job.game_id, source_id)
                if current != source:
                    raise GridShadowError("GRID_SHADOW_SOURCE_STALE", "Pinned source changed.")
                existing = repository.get_result_for_source(job.game_id, job.id, source_id)
            frame = self._loader.load(
                _source_path(self._root / "data", source["relative_path"]),
                expected_source_checksum_sha256=source["checksum_sha256"],
            )
            if (
                frame.source.width != source["width"]
                or frame.source.height != source["height"]
                or frame.source.normalized_pixel_checksum_sha256
                != source["normalized_pixel_checksum_sha256"]
            ):
                raise GridShadowError("GRID_SHADOW_SOURCE_PIXELS_MISMATCH", "Pinned pixels differ.")
            if existing is not None:
                if dict(existing.source_binding) != source or dict(existing.model_binding) != model:
                    raise GridShadowError(
                        "GRID_SHADOW_RESULT_CONFLICT", "Stored result bindings differ."
                    )
                output = dict(existing.output)
            else:
                detections = self._runner.run(
                    directory,
                    str(model["bundle_checksum_sha256"]),
                    frame.rgb,
                    heartbeat=heartbeat,
                    max_seconds=max(0.001, self._max_source_seconds - (self._clock() - started)),
                )
                output = build_shadow_output(
                    source,
                    detections,
                    calibrated=version.profile is GameShapeGeometryConfiguration.GRID_PROFILE_777_V2
                    and version.weights_sha256 == _RUN1_WEIGHTS_SHA256,
                )
            self._loader.clear()
            if self._clock() - started > self._max_source_seconds:
                raise JobHandlerError(
                    "GRID_SHADOW_SOURCE_TIME_LIMIT", "Source comparison exceeded its time limit."
                )
            heartbeat()
            if job.lease_owner is None:
                raise JobHandlerError("GRID_SHADOW_LEASE_LOST", "The worker has no active lease.")
            with self._sessions.begin() as session:
                self._repositories(session).publish_result(
                    game_id=job.game_id,
                    job_id=job.id,
                    lease_owner=job.lease_owner,
                    lease_token=context.lease_token,
                    pinned_source=source,
                    model=model,
                    output=output,
                )
            context.checkpoint(
                checkpoint_payload={
                    "workflow": GRID_SHADOW_VALIDATION_KIND,
                    "next_source": index + 1,
                },
                stage="grid_geometry_shadow",
                current=index + 1,
                total=len(sources),
                success_count=index + 1,
                failure_count=0,
                review_count=index + 1,
            )


def _registered_version(model: Mapping[str, object]) -> GridEngineModelVersion:
    try:
        configuration = GameShapeGeometryConfiguration(str(model["profile"]))
    except (KeyError, ValueError) as error:
        raise JobHandlerError(
            "GRID_SHADOW_MODEL_BINDING_INVALID", "Unknown pinned profile."
        ) from error
    profile = grid_engine_profile_for(configuration)
    version = (
        next((item for item in profile.versions if item.version == model.get("version")), None)
        if profile
        else None
    )
    if version is None:
        raise JobHandlerError("GRID_SHADOW_MODEL_BINDING_INVALID", "Unknown pinned model version.")
    expected = {
        "profile": version.profile.value,
        "version": version.version,
        "manifest_checksum_sha256": shadow_digest(grid_engine_manifest(version)),
        "bundle_checksum_sha256": next(
            file.sha256 for file in version.files if file.name == "bundle.json"
        ),
        "weights_sha256": version.weights_sha256,
        "files": [
            {"name": file.name, "sha256": file.sha256, "size_bytes": file.size_bytes}
            for file in version.files
        ],
    }
    if dict(model) != expected:
        raise JobHandlerError("GRID_SHADOW_MODEL_BINDING_INVALID", "Pinned registry model differs.")
    return version


def _validate_source(source: Any) -> None:
    if not isinstance(source, dict):
        raise JobHandlerError("GRID_SHADOW_INPUT_INVALID", "Pinned source must be an object.")
    binding = {key: value for key, value in source.items() if key != "bindings_sha256"}
    if source.get("bindings_sha256") != shadow_digest(binding):
        raise JobHandlerError(
            "GRID_SHADOW_SOURCE_BINDING_INVALID", "Source binding checksum differs."
        )
    start, end = source.get("sequence_range_start"), source.get("sequence_range_end")
    active, slots = source.get("active_board_slots"), source.get("baseline_slots")
    if (
        type(start) is not int
        or type(end) is not int
        or start < 1
        or not 1 <= end - start + 1 <= 9
        or active != list(range(end - start + 1))
        or not isinstance(slots, list)
        or len(slots) != len(active)
    ):
        raise JobHandlerError("GRID_SHADOW_SEQUENCE_INVALID", "Pinned source slots are ambiguous.")
    for position, slot in zip(active, slots, strict=True):
        if (slot.get("grid_rows"), slot.get("grid_columns")) != (3, 5):
            raise JobHandlerError("GRID_SHADOW_TOPOLOGY_UNSUPPORTED", "Only 5 × 3 is supported.")
        if (
            slot.get("position_index") != position
            or slot.get("sequence_number") != start + position
        ):
            raise JobHandlerError("GRID_SHADOW_SEQUENCE_INVALID", "Pinned slot identity differs.")
    checksum = source.get("checksum_sha256")
    if (
        not isinstance(checksum, str)
        or source.get("relative_path") != f"originals/{checksum[:2]}/{checksum}.jpg"
    ):
        raise JobHandlerError(
            "GRID_SHADOW_SOURCE_PATH_INVALID", "Source must be a managed original."
        )


def _source_path(root: Path, relative: str) -> Path:
    parts = PurePosixPath(relative)
    if parts.is_absolute() or ".." in parts.parts or "\\" in relative or ":" in relative:
        raise JobHandlerError("GRID_SHADOW_SOURCE_PATH_INVALID", "Source path must be managed.")
    path = root.joinpath(*parts.parts).resolve()
    if not path.is_relative_to(root):
        raise JobHandlerError(
            "GRID_SHADOW_SOURCE_PATH_INVALID", "Source path escapes managed storage."
        )
    return path


__all__ = ["GridShadowHandler", "baseline_nodes", "build_shadow_output", "cell_visibility"]
