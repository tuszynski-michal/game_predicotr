"""Durable preflight that builds a content-addressed page-geometry manifest."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path, PurePosixPath
from typing import cast

import cv2
import numpy as np
from game_predictor_api.domain.geometry_qualification import page_anchor_exclusion_reason
from game_predictor_api.domain.image_geometry_v2 import SourceQuad
from game_predictor_api.domain.jobs import Job, JobType
from PIL import Image, ImageOps, UnidentifiedImageError

from game_predictor_worker.jobs.runtime import JobExecutionContext, JobHandlerError

from .contrast_frame_grid_v12 import (
    CONTRAST_FRAME_GRID_V12_REGISTRATION_VERSION,
    ContrastFrameGridV12Error,
    ContrastFrameGridV12Profile,
    ContrastFrameGridV12Registrar,
)
from .geometry import Point, Quad
from .lateral_partial_contract import LateralPartialContractError, LateralPartialGeometrySnapshot
from .page_geometry_incremental import (
    BasePageGeometryManifestDescriptor,
    LoadedPageGeometryCheckpoint,
    PageGeometryCheckpointStore,
    load_base_manifest,
    parse_base_manifest_descriptor,
    plan_manifest_reuse,
    recompute_inventory_checksum,
    source_inventory_checksum,
)
from .page_geometry_registration import (
    PAGE_REGISTRATION_BOARD_AREA_MASK_VERSION,
    PAGE_REGISTRATION_VERSION,
    LateralPageRegistrationCandidate,
    PageRegistrationInitialization,
    VerifiedPageRegistrar,
    _red_edge_coverage,
    _red_mask,
)
from .shape_geometry_v2.preflight import (
    SHAPE_GEOMETRY_V2_PREFLIGHT_POLICY_VERSION,
    ShapeGeometryV2PreflightError,
    ShapeGeometryV2PreflightProfile,
    parse_shape_geometry_v2_preflight_profile,
    verify_shape_geometry_v2_profile,
)
from .source_ingestion import (
    BROWSER_SELECTION_MANIFEST,
    ManagedOriginal,
    ManagedOriginalStore,
    _safe_source_path,
)
from .structured_geometry.global_initialization import (
    DEFAULT_STRUCTURED_GEOMETRY_INITIALIZATION_THRESHOLDS,
    _generic_frame_line_initialization,
)

PAGE_GEOMETRY_MANIFEST_SCHEMA_VERSION = 2
PAGE_GEOMETRY_MANIFEST_SHAPE_V2_SCHEMA_VERSION = 3
PAGE_GEOMETRY_MANIFEST_CONTRAST_FRAME_V12_SCHEMA_VERSION = 4
LEGACY_PAGE_GEOMETRY_PREFLIGHT_VERSION = "page-geometry-preflight-v1"
PAGE_GEOMETRY_PREFLIGHT_VERSION = "page-geometry-preflight-v2-auto-anchor"
PAGE_GEOMETRY_PREFLIGHT_BOARD_AREA_VERSION = "page-geometry-preflight-v3-board-area-mask"
PAGE_GEOMETRY_PREFLIGHT_CONTRAST_FRAME_V12_VERSION = (
    "page-geometry-preflight-v12-contrast-frame-grid"
)
_CHECKPOINT_BATCH_SIZE = 25
_AUTO_ANCHOR_MAX_PASSES = 2
_AUTO_ANCHOR_LIMIT_PER_PASS = 21
_PROGRESS_PHASE_SOURCE_REGISTRATION = "source_registration"
_PROGRESS_PHASE_AUTO_ANCHOR_RETRY = "auto_anchor_retry"
_PROGRESS_PHASE_MANIFEST_WRITE = "manifest_write"
_PROGRESS_PHASE_COMPLETE = "complete"
# Registration is CPU-bound but OpenCV runs most feature work outside the GIL.
# Four pages remain the compatibility default for direct construction.  The
# supervised general worker passes its bounded cooperative process budget.
_DEFAULT_REGISTRATION_WORKERS = 4


def _expected_board_count(original: ManagedOriginal) -> int:
    start = original.sequence_range_start
    end = original.sequence_range_end
    if isinstance(start, int) and isinstance(end, int) and 1 <= start <= end <= start + 8:
        return end - start + 1
    return 9


def _source_quad_to_quad(quad: SourceQuad) -> Quad:
    return tuple(
        Point(int(round(point.x)), int(round(point.y))) for point in quad.corners
    )


def _standalone_frame_line_candidate(
    rgb: np.ndarray,
    *,
    source_checksum_sha256: str,
    expected_board_count: int,
) -> LateralPageRegistrationCandidate | None:
    """Fallback candidate from line-based frame detection without an anchor."""

    if expected_board_count != 9:
        return None
    active_slots = tuple(range(expected_board_count))
    generic, _metrics = _generic_frame_line_initialization(
        rgb,
        active_board_slots=active_slots,
        thresholds=DEFAULT_STRUCTURED_GEOMETRY_INITIALIZATION_THRESHOLDS,
    )
    if generic is None:
        return None
    red_mask = _red_mask(rgb)
    red_neighbourhood = cv2.dilate(red_mask, np.ones((3, 3), dtype=np.uint8))
    quads = tuple(_source_quad_to_quad(quad) for quad in generic.quads)
    coverage = tuple(_red_edge_coverage(red_neighbourhood, quad) for quad in quads)
    return LateralPageRegistrationCandidate(
        initialization=PageRegistrationInitialization(
            anchor_source_checksum_sha256=source_checksum_sha256,
            active_board_slots=active_slots,
            initialization_quads=quads,
            native_homography=generic.homography,
            inlier_count=0,
            inlier_ratio=0.0,
            p95_reprojection_error=0.0,
            feature_count=0,
            registration_version=PAGE_REGISTRATION_VERSION,
        ),
        policy_checksum_sha256="0" * 64,
        board_red_edge_coverages=coverage,
        recovery_kind="standalone_frame_lines",
        review_required_slots=active_slots,
        version="lateral-page-registration-candidate-v2",
    )


class PageGeometryPreflightHandler:
    """Build a reusable all-or-nothing manifest before an image import.

    A source with no verified registration is counted as review-required, not
    a failed board detection.  The final immutable manifest is written only
    once every source has been assessed and can be reused after API/worker
    restarts without repeating ORB work.
    """

    def __init__(
        self,
        *,
        artifact_root: Path,
        registration_workers: int = _DEFAULT_REGISTRATION_WORKERS,
    ) -> None:
        if not 1 <= registration_workers <= 64:
            raise ValueError("registration_workers must be between 1 and 64.")
        self._artifact_root = artifact_root.resolve()
        self._originals = ManagedOriginalStore(self._artifact_root)
        self._registration_workers = registration_workers

    def __call__(self, context: JobExecutionContext, job: Job) -> None:
        payload = _input(job)
        output = self._existing_output(job)
        if output is not None:
            manifest = _load_manifest(output)
            if "lateralPartialGeometry" in payload:
                from .lateral_partial_artifact import require_lateral_manifest

                checkpoint = cast(Mapping[str, object], job.checkpoint_payload)
                if hashlib.sha256(output.read_bytes()).hexdigest() != checkpoint.get(
                    "geometry_manifest_checksum_sha256"
                ):
                    raise JobHandlerError(
                        "IMAGE_PAGE_GEOMETRY_MANIFEST_DRIFT",
                        "The completed page-geometry manifest changed.",
                    )
                require_lateral_manifest(
                    manifest,
                    game_id=str(job.game_id),
                    source_selection_id=cast(str, payload["sourceSelectionId"]),
                    source_manifest_sha256=cast(str, payload["sourceManifestChecksumSha256"]),
                    policy=LateralPartialGeometrySnapshot.from_payload(
                        payload["lateralPartialGeometry"]
                    ),
                )
            reuse = manifest.get("reuseProvenance")
            reused_source_count = (
                reuse.get("reusedSourceCount") if isinstance(reuse, Mapping) else None
            )
            recomputed_source_count = (
                reuse.get("recomputedSourceCount") if isinstance(reuse, Mapping) else None
            )
            source_count = _manifest_count(manifest, "sourceCount")
            _checkpoint(
                context,
                payload,
                manifest_checksum=hashlib.sha256(output.read_bytes()).hexdigest(),
                manifest_relative_path=_relative_to_data(self._artifact_root, output),
                processed=source_count,
                total=source_count,
                registered=_manifest_count(manifest, "registeredSourceCount"),
                review_required=_manifest_count(manifest, "reviewRequiredSourceCount"),
                complete=True,
                phase=_PROGRESS_PHASE_COMPLETE,
                phase_current=1,
                phase_total=1,
                reused_source_count=(
                    reused_source_count if isinstance(reused_source_count, int) else None
                ),
                recomputed_source_count=(
                    recomputed_source_count if isinstance(recomputed_source_count, int) else None
                ),
                previous_checkpoint=job.checkpoint_payload,
            )
            return

        source_directory = Path(cast(str, payload["sourceDirectory"]))
        raw_partial_policy = payload.get("lateralPartialGeometry")
        lateral_partial_policy = (
            LateralPartialGeometrySnapshot.from_payload(raw_partial_policy)
            if isinstance(raw_partial_policy, Mapping)
            else None
        )
        managed_reprepare = "managed_source_job_id" in job.input_payload
        if managed_reprepare:
            from uuid import UUID

            managed_id = UUID(str(job.input_payload["managed_source_job_id"]))
            source_manifest = (
                self._artifact_root / "data" / "originals" / "manifests" / f"{managed_id}.json"
            )
            if (
                not source_manifest.is_file()
                or hashlib.sha256(source_manifest.read_bytes()).hexdigest()
                != job.input_payload["managed_source_manifest_checksum_sha256"]
            ):
                raise JobHandlerError(
                    "IMAGE_REPROCESS_PAGE_GEOMETRY_MANIFEST_INCOMPATIBLE",
                    "The pinned managed original inventory changed before preflight.",
                )
        if not managed_reprepare:
            _verify_browser_source_manifest(
                source_directory,
                expected_checksum=cast(str, payload["sourceManifestChecksumSha256"]),
            )
        try:
            managed = self._originals.load_or_create_manifest(
                replace(job, input_payload={**job.input_payload, "schema_version": 6})
                if managed_reprepare
                else job,
                source_directory=source_directory,
            )
            if managed_reprepare:
                for original in managed.originals:
                    path = self._artifact_root / original.managed_relative_path
                    if not path.is_file():
                        raise JobHandlerError(
                            "IMAGE_PAGE_GEOMETRY_SOURCE_UNAVAILABLE",
                            "A managed JPEG needed for preflight is unavailable.",
                        )
                    self._originals.ensure_original(managed, original)
                managed = replace(
                    managed,
                    source_directory=self._artifact_root,
                    originals=tuple(
                        replace(item, source_storage_relative_path=item.managed_relative_path)
                        for item in managed.originals
                    ),
                )
        except JobHandlerError as error:
            if error.code != "IMAGE_SOURCE_UNAVAILABLE":
                raise
            raise JobHandlerError(
                "IMAGE_PAGE_GEOMETRY_SOURCE_UNAVAILABLE",
                "A staged image cannot be decoded for geometry preflight.",
            ) from error

        originals_by_checksum = {
            original.checksum_sha256: original for original in managed.originals
        }
        available_override_anchor_checksums = set(originals_by_checksum)
        raw_overrides = cast(Mapping[str, object], payload["pageGeometryOverrides"])
        for checksum in raw_overrides:
            if _is_sha256(checksum) and self._managed_anchor_path(checksum).is_file():
                available_override_anchor_checksums.add(checksum)
        shape_profile = payload.get("shapeGeometryV2Profile")
        contrast_profile = payload.get("contrastFrameGridV12Profile")
        registration_profile: dict[str, object] | None = None
        registrar: object | None = None
        if isinstance(contrast_profile, ContrastFrameGridV12Profile):
            registrar = ContrastFrameGridV12Registrar(
                contrast_profile,
                load_anchor_rgb=lambda checksum: self._load_preflight_anchor_rgb(
                    checksum,
                    by_checksum=originals_by_checksum,
                    source_directory=managed.source_directory,
                ),
            )
            _prepare_registrar(registrar)
        elif not isinstance(shape_profile, ShapeGeometryV2PreflightProfile):
            registration_profile = _profile_with_manual_override_anchors(
                cast(Mapping[str, object], payload["pageRegistrationProfile"]),
                raw_overrides,
                available_checksums=available_override_anchor_checksums,
            )
            registrar = VerifiedPageRegistrar(
                registration_profile,
                load_anchor_rgb=lambda checksum: self._load_preflight_anchor_rgb(
                    checksum,
                    by_checksum=originals_by_checksum,
                    source_directory=managed.source_directory,
                ),
            )
            _prepare_registrar(registrar)

        total = len(managed.originals)
        descriptor = (
            None
            if isinstance(contrast_profile, ContrastFrameGridV12Profile)
            else _base_manifest_descriptor(payload)
        )
        base_manifest = (
            None
            if descriptor is None
            else load_base_manifest(
                self._artifact_root,
                descriptor,
                game_id=str(job.game_id),
                source_selection_id=cast(str, payload["sourceSelectionId"]),
                source_manifest_checksum_sha256=cast(str, payload["sourceManifestChecksumSha256"]),
                preflight_policy_version=cast(str, payload["preflightPolicyVersion"]),
                page_registration_profile=cast(
                    Mapping[str, object], payload["pageRegistrationProfile"]
                ),
                lateral_partial_geometry=payload.get("lateralPartialGeometry"),
            )
        )
        reuse_plan = plan_manifest_reuse(
            managed.originals,
            payload=payload,
            base_manifest=base_manifest,
            compatibility_mode=(None if descriptor is None else descriptor.compatibility_mode),
            base_override_fingerprints=(
                None if descriptor is None else descriptor.base_override_fingerprints
            ),
        )
        reused_source_count = reuse_plan.reused_source_count
        recomputed_source_count = reuse_plan.recomputed_source_count
        recompute_checksum = recompute_inventory_checksum(reuse_plan.recompute_originals)
        checkpoint_store = PageGeometryCheckpointStore(
            self._artifact_root,
            job_id=str(job.id),
            input_fingerprint_sha256=job.input_key,
            source_inventory_checksum_sha256=source_inventory_checksum(managed.originals),
            shard_size=_CHECKPOINT_BATCH_SIZE,
        )
        durable_required = isinstance(job.checkpoint_payload, Mapping) and isinstance(
            job.checkpoint_payload.get("durable_checkpoint_relative_path"), str
        )
        checkpoint_state = checkpoint_store.load(required=durable_required)
        if checkpoint_state is None:
            checkpoint_state = checkpoint_store.initialize(
                reuse_plan.entries,
                metadata={
                    "phase": _PROGRESS_PHASE_SOURCE_REGISTRATION,
                    "sourceNextIndex": 0,
                    "recomputeInventoryChecksumSha256": recompute_checksum,
                    "reusedSourceCount": reused_source_count,
                    "recomputedSourceCount": recomputed_source_count,
                    "autoAnchorPasses": [],
                    "activeAutoAnchorPass": None,
                },
            )
        _validate_resumed_checkpoint(
            checkpoint_state,
            recompute_checksum=recompute_checksum,
            reused_source_count=reused_source_count,
            recomputed_source_count=recomputed_source_count,
            source_checksums={original.checksum_sha256 for original in managed.originals},
        )
        entries = dict(checkpoint_state.entries)
        metadata = dict(checkpoint_state.metadata)
        if metadata.get("phase") == _PROGRESS_PHASE_COMPLETE:
            checksum_value = metadata.get("geometryManifestChecksumSha256")
            relative = metadata.get("geometryManifestRelativePath")
            if (
                not isinstance(checksum_value, str)
                or not _is_sha256(checksum_value)
                or not isinstance(relative, str)
            ):
                raise JobHandlerError(
                    "IMAGE_PAGE_GEOMETRY_CHECKPOINT_INVALID",
                    "The completed durable page-geometry checkpoint is incomplete.",
                )
            output = (self._artifact_root / Path(*PurePosixPath(relative).parts)).resolve()
            if (
                not output.is_relative_to((self._artifact_root / "data").resolve())
                or not output.is_file()
                or hashlib.sha256(output.read_bytes()).hexdigest() != checksum_value
            ):
                raise JobHandlerError(
                    "IMAGE_PAGE_GEOMETRY_CHECKPOINT_INVALID",
                    "The completed durable page-geometry manifest is unavailable.",
                )
            manifest = _load_manifest(output)
            _checkpoint(
                context,
                payload,
                manifest_checksum=checksum_value,
                manifest_relative_path=relative,
                processed=total,
                total=total,
                registered=_manifest_count(manifest, "registeredSourceCount"),
                review_required=_manifest_count(manifest, "reviewRequiredSourceCount"),
                complete=True,
                phase=_PROGRESS_PHASE_COMPLETE,
                phase_current=1,
                phase_total=1,
                reused_source_count=reused_source_count,
                recomputed_source_count=recomputed_source_count,
                durable_checkpoint=checkpoint_state,
            )
            return

        source_next_index = _checkpoint_integer(metadata, "sourceNextIndex")
        if source_next_index > recomputed_source_count:
            raise JobHandlerError(
                "IMAGE_PAGE_GEOMETRY_CHECKPOINT_INVALID",
                "The durable page-geometry source cursor is invalid.",
            )
        if metadata.get("phase") == _PROGRESS_PHASE_SOURCE_REGISTRATION:
            with ThreadPoolExecutor(max_workers=self._registration_workers) as executor:
                for batch_start in range(
                    source_next_index,
                    recomputed_source_count,
                    _CHECKPOINT_BATCH_SIZE,
                ):
                    batch = reuse_plan.recompute_originals[
                        batch_start : batch_start + _CHECKPOINT_BATCH_SIZE
                    ]
                    results = executor.map(
                        lambda original, registrar=registrar: self._evaluate_source(
                            original,
                            source_directory=managed.source_directory,
                            payload=payload,
                            registrar=registrar,
                            lateral_partial_policy=lateral_partial_policy,
                            enable_standalone_fallback=True,
                        ),
                        batch,
                    )
                    delta: dict[str, object] = {}
                    for checksum, entry, _outcome in results:
                        entries[checksum] = entry
                        delta[checksum] = entry
                    source_next_index = batch_start + len(batch)
                    metadata["sourceNextIndex"] = source_next_index
                    checkpoint_state = checkpoint_store.append(
                        delta,
                        metadata=metadata,
                        all_entries=entries,
                    )
                    _checkpoint(
                        context,
                        payload,
                        manifest_checksum=None,
                        manifest_relative_path=None,
                        processed=reused_source_count + source_next_index,
                        total=total,
                        registered=_entry_status_count(entries, "registered"),
                        review_required=_entry_status_count(entries, "review_required"),
                        complete=False,
                        phase=_PROGRESS_PHASE_SOURCE_REGISTRATION,
                        phase_current=source_next_index,
                        phase_total=recomputed_source_count,
                        reused_source_count=reused_source_count,
                        recomputed_source_count=recomputed_source_count,
                        durable_checkpoint=checkpoint_state,
                    )
            metadata["phase"] = _PROGRESS_PHASE_AUTO_ANCHOR_RETRY
            checkpoint_state = checkpoint_store.append({}, metadata=metadata, all_entries=entries)

        auto_anchor_passes = _checkpoint_reports(checkpoint_state.metadata.get("autoAnchorPasses"))
        if _uses_auto_anchors(cast(str, payload["preflightPolicyVersion"])):
            if registration_profile is None:
                raise JobHandlerError(
                    "INVALID_PAGE_GEOMETRY_PREFLIGHT_PAYLOAD",
                    "Automatic anchors require a verified page-registration profile.",
                )
            entries, auto_anchor_passes, checkpoint_state = self._retry_with_verified_auto_anchors(
                entries,
                managed.originals,
                context=context,
                source_directory=managed.source_directory,
                payload=payload,
                base_profile=registration_profile,
                checkpoint_store=checkpoint_store,
                checkpoint_state=checkpoint_state,
                reused_source_count=reused_source_count,
                recomputed_source_count=recomputed_source_count,
                lateral_partial_policy=lateral_partial_policy,
            )
        registered = _entry_status_count(entries, "registered")
        review_required = _entry_status_count(entries, "review_required")
        skipped = _entry_status_count(entries, "skipped_human_resolved")
        metadata = dict(checkpoint_state.metadata)
        metadata["phase"] = _PROGRESS_PHASE_MANIFEST_WRITE
        metadata["autoAnchorPasses"] = auto_anchor_passes
        metadata["activeAutoAnchorPass"] = None
        checkpoint_state = checkpoint_store.append({}, metadata=metadata, all_entries=entries)
        _checkpoint(
            context,
            payload,
            manifest_checksum=None,
            manifest_relative_path=None,
            processed=total,
            total=total,
            registered=registered,
            review_required=review_required,
            complete=False,
            phase=_PROGRESS_PHASE_MANIFEST_WRITE,
            phase_current=0,
            phase_total=1,
            reused_source_count=reused_source_count,
            recomputed_source_count=recomputed_source_count,
            durable_checkpoint=checkpoint_state,
        )
        content = _manifest_bytes(
            job,
            payload,
            entries,
            total,
            registered,
            review_required,
            skipped,
            auto_anchor_passes=auto_anchor_passes,
            base_manifest=descriptor,
            reused_source_count=reused_source_count,
            recomputed_source_count=recomputed_source_count,
        )
        checksum = hashlib.sha256(content).hexdigest()
        output = self._output_path(checksum)
        self._write_immutable(output, content)
        metadata["phase"] = _PROGRESS_PHASE_COMPLETE
        metadata["geometryManifestChecksumSha256"] = checksum
        metadata["geometryManifestRelativePath"] = _relative_to_data(self._artifact_root, output)
        checkpoint_state = checkpoint_store.append({}, metadata=metadata, all_entries=entries)
        _checkpoint(
            context,
            payload,
            manifest_checksum=checksum,
            manifest_relative_path=_relative_to_data(self._artifact_root, output),
            processed=total,
            total=total,
            registered=registered,
            review_required=review_required,
            complete=True,
            phase=_PROGRESS_PHASE_COMPLETE,
            phase_current=1,
            phase_total=1,
            reused_source_count=reused_source_count,
            recomputed_source_count=recomputed_source_count,
            durable_checkpoint=checkpoint_state,
        )

    def _evaluate_source(
        self,
        original: ManagedOriginal,
        *,
        source_directory: Path,
        payload: Mapping[str, object],
        registrar: object | None,
        lateral_partial_policy: LateralPartialGeometrySnapshot | None = None,
        enable_standalone_fallback: bool = False,
    ) -> tuple[str, dict[str, object], str]:
        if _fully_canonical(original.sequence_range_start, original.sequence_range_end, payload):
            return (
                original.checksum_sha256,
                {
                    "status": "skipped_human_resolved",
                    "sourceRelativePath": original.source_relative_path,
                },
                "skipped_human_resolved",
            )
        rgb = _load_source_rgb(
            source_directory,
            original.source_storage_relative_path or original.source_relative_path,
        )
        contrast_profile = payload.get("contrastFrameGridV12Profile")
        is_v12 = isinstance(contrast_profile, ContrastFrameGridV12Profile)
        override = self._override(
            payload,
            original.checksum_sha256,
            width=int(rgb.shape[1]),
            height=int(rgb.shape[0]),
            expected_board_count=_expected_board_count(original),
            require_v12_pair=is_v12,
        )
        if override is not None:
            return (
                original.checksum_sha256,
                {
                    "status": "registered",
                    "sourceRelativePath": original.source_relative_path,
                    "imageHeight": int(rgb.shape[0]),
                    "imageWidth": int(rgb.shape[1]),
                    **override,
                },
                "registered",
            )
        shape_profile = payload.get("shapeGeometryV2Profile")
        if isinstance(shape_profile, ShapeGeometryV2PreflightProfile):
            verification = verify_shape_geometry_v2_profile(rgb, shape_profile)
            if _expected_board_count(original) != 9:
                verification = replace(
                    verification,
                    verdict="needs_manual_review",
                    reason_code="SHAPE_GEOMETRY_V2_SOURCE_TOPOLOGY_UNSUPPORTED",
                )
            return (
                original.checksum_sha256,
                {
                    "status": "review_required",
                    "sourceRelativePath": original.source_relative_path,
                    "imageHeight": int(rgb.shape[0]),
                    "imageWidth": int(rgb.shape[1]),
                    "reasonCode": verification.reason_code,
                    "shapeGeometryV2Verification": verification.to_payload(),
                },
                "review_required",
            )
        if isinstance(registrar, ContrastFrameGridV12Registrar):
            evaluation = registrar.evaluate(
                rgb, active_board_slots=tuple(range(_expected_board_count(original)))
            )
            if evaluation.result is None:
                return (
                    original.checksum_sha256,
                    {
                        "status": "review_required",
                        "sourceRelativePath": original.source_relative_path,
                        "imageHeight": int(rgb.shape[0]),
                        "imageWidth": int(rgb.shape[1]),
                        **evaluation.failure_payload(),
                    },
                    "review_required",
                )
            return (
                original.checksum_sha256,
                {
                    "status": "registered",
                    "sourceRelativePath": original.source_relative_path,
                    "imageHeight": int(rgb.shape[0]),
                    "imageWidth": int(rgb.shape[1]),
                    **evaluation.result.to_payload(),
                },
                "registered",
            )
        expected_board_count = _expected_board_count(original)
        if not isinstance(registrar, VerifiedPageRegistrar) or not registrar.available:
            if (
                enable_standalone_fallback
                and lateral_partial_policy is not None
                and expected_board_count == 9
            ):
                standalone_candidate = _standalone_frame_line_candidate(
                    rgb,
                    source_checksum_sha256=original.checksum_sha256,
                    expected_board_count=expected_board_count,
                )
                if standalone_candidate is not None:
                    standalone_candidate = replace(
                        standalone_candidate,
                        policy_checksum_sha256=lateral_partial_policy.checksum_sha256,
                        version=(
                            "lateral-page-registration-candidate-v3"
                            if lateral_partial_policy.selective_frame_review
                            else "lateral-page-registration-candidate-v2"
                        ),
                    )
                    return (
                        original.checksum_sha256,
                        {
                            "status": "review_required",
                            "sourceRelativePath": original.source_relative_path,
                            "imageHeight": int(rgb.shape[0]),
                            "imageWidth": int(rgb.shape[1]),
                            "reasonCode": "PAGE_GEOMETRY_STANDALONE_FRAME_LINE_CANDIDATE",
                            "lateralRegistrationCandidate": standalone_candidate.to_payload(),
                        },
                        "review_required",
                    )
            return (
                original.checksum_sha256,
                {
                    "status": "review_required",
                    "sourceRelativePath": original.source_relative_path,
                    "imageHeight": int(rgb.shape[0]),
                    "imageWidth": int(rgb.shape[1]),
                    "reasonCode": "PAGE_GEOMETRY_BOOTSTRAP_ANCHOR_REQUIRED",
                },
                "review_required",
            )
        evaluation = (
            registrar.evaluate(rgb)
            if lateral_partial_policy is None
            else registrar.evaluate(
                rgb,
                lateral_partial_policy=lateral_partial_policy,
                active_board_slots=tuple(range(expected_board_count)),
            )
        )
        if evaluation.result is None:
            if (
                enable_standalone_fallback
                and lateral_partial_policy is not None
                and expected_board_count == 9
            ):
                standalone_candidate = _standalone_frame_line_candidate(
                    rgb,
                    source_checksum_sha256=original.checksum_sha256,
                    expected_board_count=expected_board_count,
                )
                if standalone_candidate is not None:
                    standalone_candidate = replace(
                        standalone_candidate,
                        policy_checksum_sha256=lateral_partial_policy.checksum_sha256,
                        version=(
                            "lateral-page-registration-candidate-v3"
                            if lateral_partial_policy.selective_frame_review
                            else "lateral-page-registration-candidate-v2"
                        ),
                    )
                    return (
                        original.checksum_sha256,
                        {
                            "status": "review_required",
                            "sourceRelativePath": original.source_relative_path,
                            "imageHeight": int(rgb.shape[0]),
                            "imageWidth": int(rgb.shape[1]),
                            "reasonCode": "PAGE_GEOMETRY_STANDALONE_FRAME_LINE_CANDIDATE",
                            "lateralRegistrationCandidate": standalone_candidate.to_payload(),
                        },
                        "review_required",
                    )
            return (
                original.checksum_sha256,
                {
                    "status": "review_required",
                    "sourceRelativePath": original.source_relative_path,
                    "imageHeight": int(rgb.shape[0]),
                    "imageWidth": int(rgb.shape[1]),
                    **evaluation.failure_payload(),
                },
                "review_required",
            )
        result = evaluation.result
        return (
            original.checksum_sha256,
            {
                "status": "registered",
                "sourceRelativePath": original.source_relative_path,
                "imageHeight": int(rgb.shape[0]),
                "imageWidth": int(rgb.shape[1]),
                **result.to_payload(),
            },
            "registered",
        )

    def _retry_with_verified_auto_anchors(
        self,
        entries: dict[str, object],
        originals: Sequence[ManagedOriginal],
        *,
        context: JobExecutionContext,
        source_directory: Path,
        payload: Mapping[str, object],
        base_profile: Mapping[str, object],
        checkpoint_store: PageGeometryCheckpointStore,
        checkpoint_state: LoadedPageGeometryCheckpoint,
        reused_source_count: int,
        recomputed_source_count: int,
        lateral_partial_policy: LateralPartialGeometrySnapshot | None = None,
    ) -> tuple[dict[str, object], list[dict[str, object]], LoadedPageGeometryCheckpoint]:
        """Retry unresolved views in bounded parallel batches with durable cursors."""

        metadata = dict(checkpoint_state.metadata)
        reports = _checkpoint_reports(metadata.get("autoAnchorPasses"))
        if metadata.get("phase") in {
            _PROGRESS_PHASE_MANIFEST_WRITE,
            _PROGRESS_PHASE_COMPLETE,
        }:
            return entries, reports, checkpoint_state

        by_checksum = {original.checksum_sha256: original for original in originals}
        raw_anchors = base_profile.get("anchors")
        base_anchors = (
            [dict(value) for value in raw_anchors if isinstance(value, Mapping)]
            if isinstance(raw_anchors, Sequence) and not isinstance(raw_anchors, str | bytes)
            else []
        )
        while len(reports) < _AUTO_ANCHOR_MAX_PASSES:
            if reports and reports[-1].get("resolvedSourceCount") == 0:
                break
            pass_number = len(reports) + 1
            active = metadata.get("activeAutoAnchorPass")
            if active is None:
                used = {
                    value.get("sourceChecksumSha256")
                    for value in base_anchors
                    if isinstance(value.get("sourceChecksumSha256"), str)
                }
                for report in reports:
                    promoted = report.get("promotedAnchorChecksums")
                    if isinstance(promoted, list):
                        used.update(value for value in promoted if isinstance(value, str))
                candidates = [
                    checksum
                    for checksum, entry in entries.items()
                    if checksum not in used
                    and isinstance(entry, Mapping)
                    and _strong_auto_anchor(entry)
                ]
                selected = _spread_candidates(candidates, _AUTO_ANCHOR_LIMIT_PER_PASS)
                if not selected:
                    break
                retry_checksums = [
                    original.checksum_sha256
                    for original in originals
                    if isinstance(entries.get(original.checksum_sha256), Mapping)
                    and cast(Mapping[str, object], entries[original.checksum_sha256]).get("status")
                    == "review_required"
                ]
                active = {
                    "pass": pass_number,
                    "promotedAnchorChecksums": selected,
                    "retrySourceChecksums": retry_checksums,
                    "nextIndex": 0,
                    "resolvedSourceCount": 0,
                }
                metadata["activeAutoAnchorPass"] = active
                checkpoint_state = checkpoint_store.append(
                    {}, metadata=metadata, all_entries=entries
                )
            if not isinstance(active, Mapping) or active.get("pass") != pass_number:
                raise JobHandlerError(
                    "IMAGE_PAGE_GEOMETRY_CHECKPOINT_INVALID",
                    "The durable auto-anchor pass is invalid.",
                )
            selected = _checkpoint_checksum_list(
                active.get("promotedAnchorChecksums"), field="promoted anchors"
            )
            retry_checksums = _checkpoint_checksum_list(
                active.get("retrySourceChecksums"), field="retry sources"
            )
            next_index = _checkpoint_integer(active, "nextIndex")
            resolved = _checkpoint_integer(active, "resolvedSourceCount")
            if next_index > len(retry_checksums):
                raise JobHandlerError(
                    "IMAGE_PAGE_GEOMETRY_CHECKPOINT_INVALID",
                    "The durable auto-anchor cursor is invalid.",
                )

            anchors = list(base_anchors)
            for report in reports:
                promoted = _checkpoint_checksum_list(
                    report.get("promotedAnchorChecksums"), field="promoted anchors"
                )
                anchors.extend(_anchor_payload(checksum, entries) for checksum in promoted)
            anchors.extend(_anchor_payload(checksum, entries) for checksum in selected)
            registrar = VerifiedPageRegistrar(
                {**base_profile, "anchors": anchors},
                load_anchor_rgb=lambda checksum: self._load_preflight_anchor_rgb(
                    checksum,
                    by_checksum=by_checksum,
                    source_directory=source_directory,
                ),
            )
            _prepare_registrar(registrar)
            _checkpoint(
                context,
                payload,
                manifest_checksum=None,
                manifest_relative_path=None,
                processed=len(originals),
                total=len(originals),
                registered=_entry_status_count(entries, "registered"),
                review_required=_entry_status_count(entries, "review_required"),
                complete=False,
                phase=_PROGRESS_PHASE_AUTO_ANCHOR_RETRY,
                phase_current=next_index,
                phase_total=len(retry_checksums),
                auto_anchor_pass=pass_number,
                auto_anchor_pass_count=_AUTO_ANCHOR_MAX_PASSES,
                reused_source_count=reused_source_count,
                recomputed_source_count=recomputed_source_count,
                durable_checkpoint=checkpoint_state,
            )
            with ThreadPoolExecutor(max_workers=self._registration_workers) as executor:
                for batch_start in range(
                    next_index,
                    len(retry_checksums),
                    _CHECKPOINT_BATCH_SIZE,
                ):
                    batch_checksums = retry_checksums[
                        batch_start : batch_start + _CHECKPOINT_BATCH_SIZE
                    ]
                    try:
                        batch = [by_checksum[checksum] for checksum in batch_checksums]
                    except KeyError as error:
                        raise JobHandlerError(
                            "IMAGE_PAGE_GEOMETRY_CHECKPOINT_INVALID",
                            "The durable auto-anchor source inventory changed.",
                        ) from error
                    results = executor.map(
                        lambda original, registrar=registrar: self._evaluate_source(
                            original,
                            source_directory=source_directory,
                            payload=payload,
                            registrar=registrar,
                            lateral_partial_policy=lateral_partial_policy,
                            enable_standalone_fallback=False,
                        ),
                        batch,
                    )
                    delta: dict[str, object] = {}
                    for checksum, entry, outcome in results:
                        if outcome == "registered":
                            entry["automaticAnchorPass"] = pass_number
                            entries[checksum] = entry
                            delta[checksum] = entry
                            resolved += 1
                    next_index = batch_start + len(batch)
                    active = {
                        "pass": pass_number,
                        "promotedAnchorChecksums": selected,
                        "retrySourceChecksums": retry_checksums,
                        "nextIndex": next_index,
                        "resolvedSourceCount": resolved,
                    }
                    metadata["activeAutoAnchorPass"] = active
                    checkpoint_state = checkpoint_store.append(
                        delta,
                        metadata=metadata,
                        all_entries=entries,
                    )
                    _checkpoint(
                        context,
                        payload,
                        manifest_checksum=None,
                        manifest_relative_path=None,
                        processed=len(originals),
                        total=len(originals),
                        registered=_entry_status_count(entries, "registered"),
                        review_required=_entry_status_count(entries, "review_required"),
                        complete=False,
                        phase=_PROGRESS_PHASE_AUTO_ANCHOR_RETRY,
                        phase_current=next_index,
                        phase_total=len(retry_checksums),
                        auto_anchor_pass=pass_number,
                        auto_anchor_pass_count=_AUTO_ANCHOR_MAX_PASSES,
                        reused_source_count=reused_source_count,
                        recomputed_source_count=recomputed_source_count,
                        durable_checkpoint=checkpoint_state,
                    )
            report = {
                "pass": pass_number,
                "promotedAnchorChecksums": selected,
                "resolvedSourceCount": resolved,
            }
            reports.append(report)
            metadata["autoAnchorPasses"] = reports
            metadata["activeAutoAnchorPass"] = None
            checkpoint_state = checkpoint_store.append({}, metadata=metadata, all_entries=entries)
            if resolved == 0:
                break
        return entries, reports, checkpoint_state

    def _load_preflight_anchor_rgb(
        self,
        checksum_sha256: str,
        *,
        by_checksum: Mapping[str, ManagedOriginal],
        source_directory: Path,
    ) -> np.ndarray:
        original = by_checksum.get(checksum_sha256)
        if original is not None:
            return _load_source_rgb(
                source_directory,
                original.source_storage_relative_path or original.source_relative_path,
            )
        return self._load_anchor_rgb(checksum_sha256)

    def _load_anchor_rgb(self, checksum_sha256: str) -> np.ndarray:
        path = self._managed_anchor_path(checksum_sha256)
        try:
            with Image.open(path) as image:
                image.load()
                return np.asarray(ImageOps.exif_transpose(image).convert("RGB"), dtype=np.uint8)
        except (OSError, UnidentifiedImageError) as error:
            raise JobHandlerError(
                "IMAGE_PAGE_GEOMETRY_ANCHOR_UNAVAILABLE",
                "A reviewed geometry anchor image is unavailable.",
            ) from error

    def _managed_anchor_path(self, checksum_sha256: str) -> Path:
        return (
            self._artifact_root
            / "data"
            / "originals"
            / checksum_sha256[:2]
            / f"{checksum_sha256}.jpg"
        )

    @staticmethod
    def _override(
        payload: Mapping[str, object],
        source_checksum_sha256: str,
        *,
        width: int,
        height: int,
        expected_board_count: int,
        require_v12_pair: bool = False,
    ) -> dict[str, object] | None:
        overrides = payload.get("pageGeometryOverrides")
        raw = overrides.get(source_checksum_sha256) if isinstance(overrides, Mapping) else None
        if not isinstance(raw, Mapping):
            return None
        if raw.get("imageWidth") != width or raw.get("imageHeight") != height:
            return None
        quads = raw.get("quads")
        if (
            not isinstance(quads, Sequence)
            or isinstance(quads, str | bytes)
            or len(quads) != expected_board_count
        ):
            return None
        board_frames = raw.get("boardFrameQuads")
        symbol_grids = raw.get("symbolGridQuads")
        has_v12_pair = (
            isinstance(board_frames, Sequence)
            and not isinstance(board_frames, str | bytes)
            and len(board_frames) == expected_board_count
            and isinstance(symbol_grids, Sequence)
            and not isinstance(symbol_grids, str | bytes)
            and len(symbol_grids) == expected_board_count
        )
        if require_v12_pair and not has_v12_pair:
            return None
        if require_v12_pair:
            return {
                "anchorSourceChecksumSha256": None,
                "boardFrameQuads": list(board_frames),
                "featureCount": 0,
                "inlierCount": 0,
                "inlierRatio": 0.0,
                "manualOverrideDecisionChecksumSha256": raw.get("decisionChecksumSha256"),
                "manualOverrideId": raw.get("overrideId"),
                "manualOverrideRevision": raw.get("revision"),
                "p95ReprojectionError": 0.0,
                "quads": list(board_frames),
                "registrationVersion": CONTRAST_FRAME_GRID_V12_REGISTRATION_VERSION,
                "symbolGridQuads": list(symbol_grids),
                "thresholdsVersion": "manual-v12-page-frame-grid-override-v1",
                **(
                    {"slotQualifications": raw["slotQualifications"]}
                    if "slotQualifications" in raw
                    else {}
                ),
            }
        return {
            "anchorSourceChecksumSha256": None,
            "boardRedEdgeCoverages": [1.0] * expected_board_count,
            "inlierCount": 0,
            "inlierRatio": 0.0,
            "manualOverrideDecisionChecksumSha256": raw.get("decisionChecksumSha256"),
            "manualOverrideId": raw.get("overrideId"),
            "manualOverrideRevision": raw.get("revision"),
            "meanRedEdgeCoverage": 1.0,
            "p95ReprojectionError": 0.0,
            "quads": list(quads),
            "registrationVersion": "manual-page-geometry-override-v1",
            "thresholdsVersion": "manual-page-geometry-override-v1",
            **(
                {"slotQualifications": raw["slotQualifications"]}
                if "slotQualifications" in raw
                else {}
            ),
        }

    def _existing_output(self, job: Job) -> Path | None:
        checkpoint = job.checkpoint_payload
        if not isinstance(checkpoint, Mapping) or checkpoint.get("complete") is not True:
            return None
        relative = checkpoint.get("geometry_manifest_relative_path")
        if not isinstance(relative, str) or not relative.startswith("data/"):
            return None
        path = (self._artifact_root / Path(*PurePosixPath(relative).parts)).resolve()
        if path.is_relative_to((self._artifact_root / "data").resolve()) and path.is_file():
            return path
        return None

    def _output_path(self, checksum_sha256: str) -> Path:
        return self._artifact_root / "data" / "page-geometry-manifests" / f"{checksum_sha256}.json"

    @staticmethod
    def _write_immutable(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_bytes() != content:
                raise JobHandlerError(
                    "IMAGE_PAGE_GEOMETRY_MANIFEST_COLLISION",
                    "A page geometry manifest already exists with different content.",
                )
            return
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.stem}.",
            suffix=".tmp",
            dir=path.parent,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                if path.read_bytes() != content:
                    raise JobHandlerError(
                        "IMAGE_PAGE_GEOMETRY_MANIFEST_COLLISION",
                        "A page geometry manifest already exists with different content.",
                    ) from None
            finally:
                temporary.unlink(missing_ok=True)
        except OSError as error:
            temporary.unlink(missing_ok=True)
            raise JobHandlerError(
                "IMAGE_PAGE_GEOMETRY_MANIFEST_WRITE_FAILED",
                "The verified page geometry manifest could not be written safely.",
            ) from error


def _base_manifest_descriptor(
    payload: Mapping[str, object],
) -> BasePageGeometryManifestDescriptor | None:
    value = payload.get("basePageGeometryManifest")
    return None if value is None else parse_base_manifest_descriptor(value)


def _prepare_registrar(registrar: object) -> None:
    prepare = getattr(registrar, "prepare", None)
    if callable(prepare):
        prepare()


def _validate_resumed_checkpoint(
    checkpoint: LoadedPageGeometryCheckpoint,
    *,
    recompute_checksum: str,
    reused_source_count: int,
    recomputed_source_count: int,
    source_checksums: set[str],
) -> None:
    metadata = checkpoint.metadata
    if (
        metadata.get("phase")
        not in {
            _PROGRESS_PHASE_SOURCE_REGISTRATION,
            _PROGRESS_PHASE_AUTO_ANCHOR_RETRY,
            _PROGRESS_PHASE_MANIFEST_WRITE,
            _PROGRESS_PHASE_COMPLETE,
        }
        or metadata.get("recomputeInventoryChecksumSha256") != recompute_checksum
        or metadata.get("reusedSourceCount") != reused_source_count
        or metadata.get("recomputedSourceCount") != recomputed_source_count
        or not set(checkpoint.entries).issubset(source_checksums)
    ):
        raise JobHandlerError(
            "IMAGE_PAGE_GEOMETRY_CHECKPOINT_INVALID",
            "The durable page-geometry checkpoint does not match the current plan.",
        )
    _checkpoint_integer(metadata, "sourceNextIndex")
    _checkpoint_reports(metadata.get("autoAnchorPasses"))


def _checkpoint_integer(value: Mapping[str, object], field: str) -> int:
    result = value.get(field)
    if not isinstance(result, int) or isinstance(result, bool) or result < 0:
        raise JobHandlerError(
            "IMAGE_PAGE_GEOMETRY_CHECKPOINT_INVALID",
            f"The durable page-geometry checkpoint has an invalid {field}.",
        )
    return result


def _checkpoint_reports(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        raise JobHandlerError(
            "IMAGE_PAGE_GEOMETRY_CHECKPOINT_INVALID",
            "The durable page-geometry auto-anchor reports are invalid.",
        )
    reports: list[dict[str, object]] = []
    for expected_pass, raw in enumerate(value, start=1):
        if (
            not isinstance(raw, Mapping)
            or raw.get("pass") != expected_pass
            or not isinstance(raw.get("resolvedSourceCount"), int)
            or isinstance(raw.get("resolvedSourceCount"), bool)
            or cast(int, raw["resolvedSourceCount"]) < 0
        ):
            raise JobHandlerError(
                "IMAGE_PAGE_GEOMETRY_CHECKPOINT_INVALID",
                "A durable page-geometry auto-anchor report is invalid.",
            )
        _checkpoint_checksum_list(raw.get("promotedAnchorChecksums"), field="promoted anchors")
        reports.append(dict(raw))
    return reports


def _checkpoint_checksum_list(value: object, *, field: str) -> list[str]:
    if (
        not isinstance(value, list)
        or any(not _is_sha256(item) for item in value)
        or len(set(cast(list[str], value))) != len(value)
    ):
        raise JobHandlerError(
            "IMAGE_PAGE_GEOMETRY_CHECKPOINT_INVALID",
            f"The durable page-geometry {field} are invalid.",
        )
    return list(cast(list[str], value))


def _anchor_payload(checksum: str, entries: Mapping[str, object]) -> dict[str, object]:
    entry = entries.get(checksum)
    if (
        not isinstance(entry, Mapping)
        or not isinstance(entry.get("imageWidth"), int)
        or not isinstance(entry.get("imageHeight"), int)
        or not isinstance(entry.get("quads"), list)
    ):
        raise JobHandlerError(
            "IMAGE_PAGE_GEOMETRY_CHECKPOINT_INVALID",
            "A promoted page-geometry anchor is unavailable after resume.",
        )
    return {
        "sourceChecksumSha256": checksum,
        "imageWidth": entry["imageWidth"],
        "imageHeight": entry["imageHeight"],
        "quads": entry["quads"],
        "provenance": "strict-auto-anchor-v1",
    }


def _uses_auto_anchors(preflight_policy_version: str) -> bool:
    return preflight_policy_version in {
        PAGE_GEOMETRY_PREFLIGHT_VERSION,
        PAGE_GEOMETRY_PREFLIGHT_BOARD_AREA_VERSION,
    }


def _registration_policy_matches_preflight(
    preflight_policy_version: object,
    registration_policy_version: object,
) -> bool:
    if not isinstance(preflight_policy_version, str):
        return False
    expected = {
        LEGACY_PAGE_GEOMETRY_PREFLIGHT_VERSION: PAGE_REGISTRATION_VERSION,
        PAGE_GEOMETRY_PREFLIGHT_VERSION: PAGE_REGISTRATION_VERSION,
        PAGE_GEOMETRY_PREFLIGHT_BOARD_AREA_VERSION: (PAGE_REGISTRATION_BOARD_AREA_MASK_VERSION),
        SHAPE_GEOMETRY_V2_PREFLIGHT_POLICY_VERSION: PAGE_REGISTRATION_VERSION,
        PAGE_GEOMETRY_PREFLIGHT_CONTRAST_FRAME_V12_VERSION: PAGE_REGISTRATION_VERSION,
    }
    return expected.get(preflight_policy_version) == registration_policy_version


def _input(job: Job) -> dict[str, object]:
    payload = job.input_payload
    required = {
        "schema_version",
        "validation_kind",
        "source_selection_id",
        "source_directory",
        "source_manifest_sha256",
        "page_registration_profile",
        "page_geometry_overrides",
        "canonical_sequence_numbers",
    }
    optional = {
        "preflight_policy_version",
        "source_display_name",
        "source_exclusions",
        "lateral_partial_geometry",
        "lateralPartialGeometry",
        "managed_source_job_id",
        "managed_source_manifest_checksum_sha256",
        "base_page_geometry_manifest",
        "replacement_parent_upload_id",
        "replacement_parent_manifest_sha256",
        "shape_geometry_v2_profile",
        "contrast_frame_grid_v12_profile",
    }
    policy = payload.get("preflight_policy_version", LEGACY_PAGE_GEOMETRY_PREFLIGHT_VERSION)
    payload_keys = frozenset(payload)
    if (
        job.job_type is not JobType.VALIDATE
        or job.game_id is None
        or not required.issubset(payload_keys)
        or not payload_keys.issubset(required | optional)
        or payload.get("schema_version") != 2
        or payload.get("validation_kind") != "page_geometry_preflight"
    ):
        raise JobHandlerError(
            "INVALID_PAGE_GEOMETRY_PREFLIGHT_PAYLOAD",
            "The page geometry preflight payload is invalid.",
        )
    selection = payload.get("source_selection_id")
    directory = payload.get("source_directory")
    checksum = payload.get("source_manifest_sha256")
    profile = payload.get("page_registration_profile")
    overrides = payload.get("page_geometry_overrides")
    canonical = payload.get("canonical_sequence_numbers")
    source_display_name = payload.get("source_display_name")
    source_exclusions = payload.get("source_exclusions", {})
    if (
        not isinstance(selection, str)
        or not isinstance(directory, str)
        or not isinstance(checksum, str)
        or len(checksum) != 64
        or not isinstance(profile, Mapping)
        or not isinstance(overrides, Mapping)
        or not isinstance(canonical, list)
        or not isinstance(source_exclusions, Mapping)
        or (
            source_display_name is not None
            and (
                not isinstance(source_display_name, str)
                or not source_display_name.strip()
                or len(source_display_name) > 255
            )
        )
        or policy
        not in {
            LEGACY_PAGE_GEOMETRY_PREFLIGHT_VERSION,
            PAGE_GEOMETRY_PREFLIGHT_VERSION,
            PAGE_GEOMETRY_PREFLIGHT_BOARD_AREA_VERSION,
            SHAPE_GEOMETRY_V2_PREFLIGHT_POLICY_VERSION,
            PAGE_GEOMETRY_PREFLIGHT_CONTRAST_FRAME_V12_VERSION,
        }
        or not _registration_policy_matches_preflight(policy, profile.get("policy"))
        or any(
            not isinstance(value, int) or isinstance(value, bool) or value < 1
            for value in canonical
        )
    ):
        raise JobHandlerError(
            "INVALID_PAGE_GEOMETRY_PREFLIGHT_PAYLOAD",
            "The page geometry preflight source or profile is invalid.",
        )
    result: dict[str, object] = {
        "sourceSelectionId": selection,
        "sourceDirectory": directory,
        "sourceManifestChecksumSha256": checksum,
        "pageRegistrationProfile": dict(profile),
        "pageGeometryOverrides": dict(overrides),
        "canonicalSequenceNumbers": set(canonical),
        "preflightPolicyVersion": policy,
        "sourceExclusions": dict(source_exclusions),
    }
    if policy == SHAPE_GEOMETRY_V2_PREFLIGHT_POLICY_VERSION:
        if "shape_geometry_v2_profile" not in payload:
            raise JobHandlerError(
                "INVALID_PAGE_GEOMETRY_PREFLIGHT_PAYLOAD",
                "The shared shape-geometry preflight requires a pinned profile.",
            )
        try:
            result["shapeGeometryV2Profile"] = parse_shape_geometry_v2_preflight_profile(
                payload["shape_geometry_v2_profile"]
            )
        except ShapeGeometryV2PreflightError as error:
            raise JobHandlerError(error.code, str(error)) from error
    elif "shape_geometry_v2_profile" in payload:
        raise JobHandlerError(
            "INVALID_PAGE_GEOMETRY_PREFLIGHT_PAYLOAD",
            "Only the shared shape-geometry preflight can pin a shared profile.",
        )
    if policy == PAGE_GEOMETRY_PREFLIGHT_CONTRAST_FRAME_V12_VERSION:
        if "contrast_frame_grid_v12_profile" not in payload:
            raise JobHandlerError(
                "INVALID_PAGE_GEOMETRY_PREFLIGHT_PAYLOAD",
                "V1.2 contrast-frame preflight requires a pinned game profile.",
            )
        try:
            result["contrastFrameGridV12Profile"] = ContrastFrameGridV12Profile.from_payload(
                payload["contrast_frame_grid_v12_profile"]
            )
        except ContrastFrameGridV12Error as error:
            raise JobHandlerError(error.code, str(error)) from error
    elif "contrast_frame_grid_v12_profile" in payload:
        raise JobHandlerError(
            "INVALID_PAGE_GEOMETRY_PREFLIGHT_PAYLOAD",
            "Only V1.2 contrast-frame preflight can pin a V1.2 profile.",
        )
    lateral_partial_key: str | None = None
    if "lateral_partial_geometry" in payload or "lateralPartialGeometry" in payload:
        if "lateral_partial_geometry" in payload and "lateralPartialGeometry" in payload:
            raise JobHandlerError(
                "INVALID_PAGE_GEOMETRY_PREFLIGHT_PAYLOAD",
                "Only one lateral-partial geometry policy may be provided.",
            )
        lateral_partial_key = (
            "lateralPartialGeometry"
            if "lateralPartialGeometry" in payload
            else "lateral_partial_geometry"
        )
    if lateral_partial_key is not None:
        if policy == PAGE_GEOMETRY_PREFLIGHT_CONTRAST_FRAME_V12_VERSION:
            raise JobHandlerError(
                "INVALID_PAGE_GEOMETRY_PREFLIGHT_PAYLOAD",
                "V1.2 contrast-frame preflight cannot pin a legacy red-frame policy.",
            )
        try:
            result["lateralPartialGeometry"] = LateralPartialGeometrySnapshot.from_payload(
                payload[lateral_partial_key]
            ).to_payload()
        except LateralPartialContractError as error:
            raise JobHandlerError(error.code, str(error)) from error
    if "base_page_geometry_manifest" in payload:
        result["basePageGeometryManifest"] = parse_base_manifest_descriptor(
            payload["base_page_geometry_manifest"]
        ).to_payload()
    if any(
        key in payload
        for key in ("managed_source_job_id", "managed_source_manifest_checksum_sha256")
    ):
        from uuid import UUID

        try:
            UUID(str(payload.get("managed_source_job_id")))
            if "lateralPartialGeometry" not in result or not _is_sha256(
                payload.get("managed_source_manifest_checksum_sha256")
            ):
                raise ValueError("Managed preflight requires a pinned policy and checksum.")
        except ValueError as error:
            raise JobHandlerError("INVALID_PAGE_GEOMETRY_PREFLIGHT_PAYLOAD", str(error)) from error
    return result


def _load_source_rgb(root: Path, relative_path: str) -> np.ndarray:
    try:
        path = _safe_source_path(root, relative_path)
        with Image.open(path) as image:
            image.load()
            return np.asarray(ImageOps.exif_transpose(image).convert("RGB"), dtype=np.uint8)
    except (OSError, UnidentifiedImageError) as error:
        raise JobHandlerError(
            "IMAGE_PAGE_GEOMETRY_SOURCE_UNAVAILABLE",
            "A staged image cannot be decoded for geometry preflight.",
        ) from error


def _verify_browser_source_manifest(source_directory: Path, *, expected_checksum: str) -> None:
    """Verify the attested browser manifest, not the derived managed manifest.

    `source_manifest_sha256` belongs to `_browser_manifest.json`.  The managed
    originals manifest is deliberately job-specific (it includes the job ID),
    so its checksum must never be compared with the browser checksum.
    """

    manifest_path = source_directory / BROWSER_SELECTION_MANIFEST
    try:
        actual_checksum = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    except OSError as error:
        raise JobHandlerError(
            "IMAGE_PAGE_GEOMETRY_SOURCE_MANIFEST_CHANGED",
            "The browser source manifest is unavailable after geometry preflight was requested.",
        ) from error
    if actual_checksum != expected_checksum:
        raise JobHandlerError(
            "IMAGE_PAGE_GEOMETRY_SOURCE_MANIFEST_CHANGED",
            "The browser source manifest changed after geometry preflight was requested.",
        )


def _manifest_bytes(
    job: Job,
    payload: Mapping[str, object],
    entries: Mapping[str, object],
    source_count: int,
    registered: int,
    review_required: int,
    skipped_human_resolved: int,
    *,
    auto_anchor_passes: Sequence[Mapping[str, object]],
    base_manifest: BasePageGeometryManifestDescriptor | None = None,
    reused_source_count: int = 0,
    recomputed_source_count: int | None = None,
) -> bytes:
    version = cast(str, payload["preflightPolicyVersion"])
    value: dict[str, object] = {
        "entries": dict(sorted(entries.items())),
        "gameId": str(job.game_id),
        "pageRegistrationProfile": payload["pageRegistrationProfile"],
        "reviewRequiredSourceCount": review_required,
        "skippedHumanResolvedSourceCount": skipped_human_resolved,
        "registeredSourceCount": registered,
        "schemaVersion": (
            PAGE_GEOMETRY_MANIFEST_CONTRAST_FRAME_V12_SCHEMA_VERSION
            if version == PAGE_GEOMETRY_PREFLIGHT_CONTRAST_FRAME_V12_VERSION
            else PAGE_GEOMETRY_MANIFEST_SHAPE_V2_SCHEMA_VERSION
            if version == SHAPE_GEOMETRY_V2_PREFLIGHT_POLICY_VERSION
            else PAGE_GEOMETRY_MANIFEST_SCHEMA_VERSION
            if _uses_auto_anchors(version)
            else 1
        ),
        "sourceCount": source_count,
        "sourceManifestChecksumSha256": payload["sourceManifestChecksumSha256"],
        "sourceSelectionId": payload["sourceSelectionId"],
        "version": version,
    }
    if _uses_auto_anchors(version):
        value["automaticAnchorPasses"] = list(auto_anchor_passes)
    value["reuseProvenance"] = {
        "contractVersion": "page-geometry-entry-reuse-v1",
        "baseManifest": None if base_manifest is None else base_manifest.to_payload(),
        "reusedSourceCount": reused_source_count,
        "recomputedSourceCount": (
            source_count if recomputed_source_count is None else recomputed_source_count
        ),
    }
    if "lateralPartialGeometry" in payload:
        value["lateralPartialGeometry"] = payload["lateralPartialGeometry"]
    if "shapeGeometryV2Profile" in payload:
        profile = payload["shapeGeometryV2Profile"]
        if not isinstance(profile, ShapeGeometryV2PreflightProfile):
            raise JobHandlerError(
                "INVALID_PAGE_GEOMETRY_PREFLIGHT_PAYLOAD",
                "The shared shape-geometry profile was not validated before manifest writing.",
            )
        value["shapeGeometryV2Profile"] = profile.to_payload()
    if "contrastFrameGridV12Profile" in payload:
        profile = payload["contrastFrameGridV12Profile"]
        if not isinstance(profile, ContrastFrameGridV12Profile):
            raise JobHandlerError(
                "INVALID_PAGE_GEOMETRY_PREFLIGHT_PAYLOAD",
                "The V1.2 contrast-frame profile was not validated before manifest writing.",
            )
        value["contrastFrameGridV12Profile"] = profile.to_payload()
    return (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _load_manifest(path: Path) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise JobHandlerError(
            "IMAGE_PAGE_GEOMETRY_MANIFEST_INVALID",
            "The page geometry preflight manifest is invalid.",
        ) from error
    if (
        not isinstance(value, Mapping)
        or (value.get("schemaVersion"), value.get("version"))
        not in {
            (1, LEGACY_PAGE_GEOMETRY_PREFLIGHT_VERSION),
            (PAGE_GEOMETRY_MANIFEST_SCHEMA_VERSION, PAGE_GEOMETRY_PREFLIGHT_VERSION),
            (
                PAGE_GEOMETRY_MANIFEST_SCHEMA_VERSION,
                PAGE_GEOMETRY_PREFLIGHT_BOARD_AREA_VERSION,
            ),
            (
                PAGE_GEOMETRY_MANIFEST_SHAPE_V2_SCHEMA_VERSION,
                SHAPE_GEOMETRY_V2_PREFLIGHT_POLICY_VERSION,
            ),
            (
                PAGE_GEOMETRY_MANIFEST_CONTRAST_FRAME_V12_SCHEMA_VERSION,
                PAGE_GEOMETRY_PREFLIGHT_CONTRAST_FRAME_V12_VERSION,
            ),
        }
        or not isinstance(value.get("sourceCount"), int)
        or not isinstance(value.get("registeredSourceCount"), int)
        or not isinstance(value.get("reviewRequiredSourceCount"), int)
        or not isinstance(value.get("skippedHumanResolvedSourceCount"), int)
    ):
        raise JobHandlerError(
            "IMAGE_PAGE_GEOMETRY_MANIFEST_INVALID",
            "The page geometry preflight manifest has an unsupported structure.",
        )
    return value


def _manifest_count(manifest: Mapping[str, object], field: str) -> int:
    value = manifest.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise JobHandlerError(
            "IMAGE_PAGE_GEOMETRY_MANIFEST_INVALID",
            f"The page geometry manifest has an invalid {field}.",
        )
    return value


def _checkpoint(
    context: JobExecutionContext,
    payload: Mapping[str, object],
    *,
    manifest_checksum: str | None,
    manifest_relative_path: str | None,
    processed: int,
    total: int,
    registered: int,
    review_required: int,
    complete: bool,
    phase: str,
    phase_current: int,
    phase_total: int,
    auto_anchor_pass: int | None = None,
    auto_anchor_pass_count: int | None = None,
    reused_source_count: int | None = None,
    recomputed_source_count: int | None = None,
    durable_checkpoint: LoadedPageGeometryCheckpoint | None = None,
    previous_checkpoint: Mapping[str, object] | None = None,
) -> None:
    value: dict[str, object] = {
        "schema_version": 1,
        "workflow": payload["preflightPolicyVersion"],
        "source_selection_id": payload["sourceSelectionId"],
        "source_manifest_sha256": payload["sourceManifestChecksumSha256"],
        "processed_source_count": processed,
        "registered_source_count": registered,
        "review_required_source_count": review_required,
        "complete": complete,
        "progress_phase": phase,
        "phase_current": phase_current,
        "phase_total": phase_total,
    }
    if auto_anchor_pass is not None and auto_anchor_pass_count is not None:
        value["auto_anchor_pass"] = auto_anchor_pass
        value["auto_anchor_pass_count"] = auto_anchor_pass_count
    if reused_source_count is not None and recomputed_source_count is not None:
        value["reused_source_count"] = reused_source_count
        value["recomputed_source_count"] = recomputed_source_count
    if durable_checkpoint is not None:
        value["durable_checkpoint_schema_version"] = 1
        value["durable_checkpoint_relative_path"] = durable_checkpoint.state_relative_path
        value["durable_checkpoint_checksum_sha256"] = durable_checkpoint.state_checksum_sha256
    elif previous_checkpoint is not None and (
        previous_checkpoint.get("durable_checkpoint_schema_version") == 1
        and isinstance(previous_checkpoint.get("durable_checkpoint_relative_path"), str)
        and _is_sha256(previous_checkpoint.get("durable_checkpoint_checksum_sha256"))
    ):
        for key in (
            "durable_checkpoint_schema_version",
            "durable_checkpoint_relative_path",
            "durable_checkpoint_checksum_sha256",
        ):
            value[key] = previous_checkpoint[key]
    if manifest_checksum is not None and manifest_relative_path is not None:
        value["geometry_manifest_checksum_sha256"] = manifest_checksum
        value["geometry_manifest_relative_path"] = manifest_relative_path
    # In v2 ``review_required`` is provisional until the bounded auto-anchor
    # passes have finished.  Publishing it as the shared job review counter
    # during the first pass makes that counter decrease whenever a later pass
    # resolves a page, which violates the monotonic job-progress contract.
    # Keep the provisional value in the checkpoint payload, but publish the
    # review outcome only with the immutable final manifest.
    published_review_count = (
        review_required
        if complete or not _uses_auto_anchors(cast(str, payload["preflightPolicyVersion"]))
        else 0
    )
    context.checkpoint(
        checkpoint_payload=value,
        stage=(
            "page_geometry_manifest_ready"
            if complete
            else (
                f"page_geometry_auto_anchor_pass_{auto_anchor_pass}"
                if phase == _PROGRESS_PHASE_AUTO_ANCHOR_RETRY
                else (
                    "page_geometry_manifest_writing"
                    if phase == _PROGRESS_PHASE_MANIFEST_WRITE
                    else "page_geometry_registering"
                )
            )
        ),
        current=processed,
        total=total,
        success_count=registered,
        failure_count=0,
        review_count=published_review_count,
    )


def _relative_to_data(artifact_root: Path, path: Path) -> str:
    return (PurePosixPath("data") / path.relative_to(artifact_root / "data")).as_posix()


def _fully_canonical(
    start: int | None,
    end: int | None,
    payload: Mapping[str, object],
) -> bool:
    canonical = payload.get("canonicalSequenceNumbers")
    return (
        isinstance(start, int)
        and isinstance(end, int)
        and isinstance(canonical, set)
        and all(number in canonical for number in range(start, end + 1))
    )


def _entry_status_count(entries: Mapping[str, object], status: str) -> int:
    return sum(
        1
        for entry in entries.values()
        if isinstance(entry, Mapping) and entry.get("status") == status
    )


def _profile_with_manual_override_anchors(
    profile: Mapping[str, object],
    overrides: Mapping[str, object],
    *,
    available_checksums: set[str],
) -> dict[str, object]:
    """Use only resolvable reviewed overrides as optional cold-start anchors.

    Explicit anchors already present in the base profile remain mandatory and
    are deliberately not filtered here.  Game-wide manual overrides are an
    optional source of extra anchors: cleanup of their old staging must not
    prevent an unrelated new staging from reaching manual review.
    """

    raw_anchors = profile.get("anchors")
    anchors = (
        [dict(value) for value in raw_anchors if isinstance(value, Mapping)]
        if isinstance(raw_anchors, Sequence) and not isinstance(raw_anchors, str | bytes)
        else []
    )
    # Only a new snapshot containing explicit qualifications can remove an
    # excluded override from the frozen profile's anchor candidates. Old
    # jobs without those fields keep their exact historical anchor list.
    anchors = [
        anchor
        for anchor in anchors
        if not (
            isinstance(
                (override := overrides.get(str(anchor.get("sourceChecksumSha256")))), Mapping
            )
            and _anchor_qualification_reason(override) is not None
        )
    ]
    known_checksums = {
        value.get("sourceChecksumSha256")
        for value in anchors
        if isinstance(value.get("sourceChecksumSha256"), str)
    }
    for checksum, raw in sorted(overrides.items()):
        if (
            checksum in known_checksums
            or checksum not in available_checksums
            or not isinstance(raw, Mapping)
        ):
            continue
        if _anchor_qualification_reason(raw) is not None:
            continue
        width = raw.get("imageWidth")
        height = raw.get("imageHeight")
        quads = raw.get("quads")
        if (
            not isinstance(checksum, str)
            or len(checksum) != 64
            or not isinstance(width, int)
            or isinstance(width, bool)
            or width < 1
            or not isinstance(height, int)
            or isinstance(height, bool)
            or height < 1
            or not isinstance(quads, Sequence)
            or isinstance(quads, str | bytes)
            or len(quads) != 9
        ):
            continue
        anchors.append(
            {
                "sourceChecksumSha256": checksum,
                "imageWidth": width,
                "imageHeight": height,
                "quads": list(quads),
                "provenance": "manual-page-geometry-override-v1",
            }
        )
        known_checksums.add(checksum)
    return {**profile, "anchors": anchors}


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _anchor_qualification_reason(entry: Mapping[str, object]) -> str | None:
    raw = entry.get("slotQualifications")
    if raw is None:
        return None
    quads = entry.get("quads")
    count = len(quads) if isinstance(quads, Sequence) and not isinstance(quads, str | bytes) else 0
    reason = page_anchor_exclusion_reason(raw, expected_board_count=count)
    return "incomplete_anchor" if count != 9 else reason


def _strong_auto_anchor(entry: Mapping[str, object]) -> bool:
    if _anchor_qualification_reason(entry) is not None:
        return False
    coverages = entry.get("boardRedEdgeCoverages")
    quads = entry.get("quads")
    return (
        entry.get("status") == "registered"
        and isinstance(entry.get("imageWidth"), int)
        and isinstance(entry.get("imageHeight"), int)
        and isinstance(quads, list)
        and len(quads) == 9
        and isinstance(coverages, list)
        and len(coverages) == 9
        and all(isinstance(value, int | float) and float(value) >= 0.65 for value in coverages)
        and isinstance(entry.get("inlierCount"), int)
        and cast(int, entry["inlierCount"]) >= 60
        and isinstance(entry.get("inlierRatio"), int | float)
        and float(cast(int | float, entry["inlierRatio"])) >= 0.35
        and isinstance(entry.get("p95ReprojectionError"), int | float)
        and float(cast(int | float, entry["p95ReprojectionError"])) <= 1.75
        and isinstance(entry.get("meanRedEdgeCoverage"), int | float)
        and float(cast(int | float, entry["meanRedEdgeCoverage"])) >= 0.82
    )


def _spread_candidates(candidates: Sequence[str], limit: int) -> list[str]:
    ordered = list(candidates)
    if len(ordered) <= limit:
        return ordered
    return [ordered[round(index * (len(ordered) - 1) / (limit - 1))] for index in range(limit)]


__all__ = [
    "LEGACY_PAGE_GEOMETRY_PREFLIGHT_VERSION",
    "PAGE_GEOMETRY_MANIFEST_SCHEMA_VERSION",
    "PAGE_GEOMETRY_MANIFEST_SHAPE_V2_SCHEMA_VERSION",
    "PAGE_GEOMETRY_PREFLIGHT_VERSION",
    "PAGE_GEOMETRY_PREFLIGHT_BOARD_AREA_VERSION",
    "PageGeometryPreflightHandler",
]
