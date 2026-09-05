"""Durable preflight that builds a content-addressed page-geometry manifest."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath
from typing import cast

import numpy as np
from game_predictor_api.domain.jobs import Job, JobType
from PIL import Image, ImageOps, UnidentifiedImageError

from game_predictor_worker.jobs.runtime import JobExecutionContext, JobHandlerError

from .page_geometry_registration import (
    PAGE_REGISTRATION_BOARD_AREA_MASK_VERSION,
    PAGE_REGISTRATION_VERSION,
    VerifiedPageRegistrar,
)
from .source_ingestion import (
    BROWSER_SELECTION_MANIFEST,
    ManagedOriginal,
    ManagedOriginalStore,
    _safe_source_path,
)

PAGE_GEOMETRY_MANIFEST_SCHEMA_VERSION = 2
LEGACY_PAGE_GEOMETRY_PREFLIGHT_VERSION = "page-geometry-preflight-v1"
PAGE_GEOMETRY_PREFLIGHT_VERSION = "page-geometry-preflight-v2-auto-anchor"
PAGE_GEOMETRY_PREFLIGHT_BOARD_AREA_VERSION = (
    "page-geometry-preflight-v3-board-area-mask"
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
            source_count = _manifest_count(manifest, "sourceCount")
            registered_count = _manifest_count(manifest, "registeredSourceCount")
            review_count = _manifest_count(manifest, "reviewRequiredSourceCount")
            _checkpoint(
                context,
                payload,
                manifest_checksum=hashlib.sha256(output.read_bytes()).hexdigest(),
                manifest_relative_path=_relative_to_data(self._artifact_root, output),
                processed=source_count,
                total=source_count,
                registered=registered_count,
                review_required=review_count,
                complete=True,
                phase=_PROGRESS_PHASE_COMPLETE,
                phase_current=1,
                phase_total=1,
            )
            return

        source_directory = Path(cast(str, payload["sourceDirectory"]))
        _verify_browser_source_manifest(
            source_directory,
            expected_checksum=cast(str, payload["sourceManifestChecksumSha256"]),
        )
        try:
            managed = self._originals.load_or_create_manifest(
                job,
                source_directory=source_directory,
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
        registration_profile = _profile_with_manual_override_anchors(
            cast(Mapping[str, object], payload["pageRegistrationProfile"]),
            cast(Mapping[str, object], payload["pageGeometryOverrides"]),
        )
        registrar = VerifiedPageRegistrar(
            registration_profile,
            load_anchor_rgb=lambda checksum: self._load_preflight_anchor_rgb(
                checksum,
                by_checksum=originals_by_checksum,
                source_directory=managed.source_directory,
            ),
        )
        entries: dict[str, object] = {}
        registered = review_required = skipped = 0
        total = len(managed.originals)
        # Keep the submitted work bounded.  Passing all 2,201 sources to one
        # executor.map() delayed the first result/checkpoint after a resumed
        # worker process, making a healthy preflight look stalled and delaying
        # cancellation.  A bounded page batch has the same deterministic order
        # and bounded parallel registration, while publishing durable progress
        # between batches.
        for batch_start in range(0, total, _CHECKPOINT_BATCH_SIZE):
            batch = managed.originals[batch_start : batch_start + _CHECKPOINT_BATCH_SIZE]
            with ThreadPoolExecutor(max_workers=self._registration_workers) as executor:
                results = executor.map(
                    lambda original: self._evaluate_source(
                        original,
                        source_directory=managed.source_directory,
                        payload=payload,
                        registrar=registrar,
                    ),
                    batch,
                )
                for checksum, entry, outcome in results:
                    entries[checksum] = entry
                    if outcome == "registered":
                        registered += 1
                    elif outcome == "review_required":
                        review_required += 1
                    else:
                        skipped += 1
            processed = batch_start + len(batch)
            _checkpoint(
                context,
                payload,
                manifest_checksum=None,
                manifest_relative_path=None,
                processed=processed,
                total=total,
                registered=registered,
                review_required=review_required,
                complete=False,
                phase=_PROGRESS_PHASE_SOURCE_REGISTRATION,
                phase_current=processed,
                phase_total=total,
            )
        auto_anchor_passes: list[dict[str, object]] = []
        if _uses_auto_anchors(cast(str, payload["preflightPolicyVersion"])):
            entries, auto_anchor_passes = self._retry_with_verified_auto_anchors(
                entries,
                managed.originals,
                context=context,
                source_directory=managed.source_directory,
                payload=payload,
                base_profile=registration_profile,
            )
            registered = _entry_status_count(entries, "registered")
            review_required = _entry_status_count(entries, "review_required")
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
        )
        checksum = hashlib.sha256(content).hexdigest()
        output = self._output_path(checksum)
        self._write_immutable(output, content)
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
        )

    def _evaluate_source(
        self,
        original: ManagedOriginal,
        *,
        source_directory: Path,
        payload: Mapping[str, object],
        registrar: VerifiedPageRegistrar,
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
        override = self._override(
            payload,
            original.checksum_sha256,
            width=int(rgb.shape[1]),
            height=int(rgb.shape[0]),
            expected_board_count=_expected_board_count(original),
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
        if not registrar.available:
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
        evaluation = registrar.evaluate(rgb)
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
    ) -> tuple[dict[str, object], list[dict[str, object]]]:
        """Retry unresolved views with a bounded, stricter anchor cohort."""

        by_checksum = {original.checksum_sha256: original for original in originals}
        raw_anchors = base_profile.get("anchors")
        anchors = (
            [dict(value) for value in raw_anchors if isinstance(value, Mapping)]
            if isinstance(raw_anchors, Sequence) and not isinstance(raw_anchors, str | bytes)
            else []
        )
        used = {
            value.get("sourceChecksumSha256")
            for value in anchors
            if isinstance(value.get("sourceChecksumSha256"), str)
        }
        reports: list[dict[str, object]] = []
        for pass_number in range(1, _AUTO_ANCHOR_MAX_PASSES + 1):
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
            for checksum in selected:
                entry = cast(Mapping[str, object], entries[checksum])
                anchors.append(
                    {
                        "sourceChecksumSha256": checksum,
                        "imageWidth": entry["imageWidth"],
                        "imageHeight": entry["imageHeight"],
                        "quads": entry["quads"],
                        "provenance": "strict-auto-anchor-v1",
                    }
                )
                used.add(checksum)
            registrar = VerifiedPageRegistrar(
                {**base_profile, "anchors": anchors},
                load_anchor_rgb=lambda checksum: self._load_preflight_anchor_rgb(
                    checksum,
                    by_checksum=by_checksum,
                    source_directory=source_directory,
                ),
            )
            resolved = 0
            unresolved = [
                original
                for original in originals
                if isinstance(entries.get(original.checksum_sha256), Mapping)
                and cast(Mapping[str, object], entries[original.checksum_sha256]).get("status")
                == "review_required"
            ]
            _checkpoint(
                context,
                payload,
                manifest_checksum=None,
                manifest_relative_path=None,
                processed=len(originals),
                total=len(originals),
                registered=_entry_status_count(entries, "registered"),
                review_required=len(unresolved),
                complete=False,
                phase=_PROGRESS_PHASE_AUTO_ANCHOR_RETRY,
                phase_current=0,
                phase_total=len(unresolved),
                auto_anchor_pass=pass_number,
                auto_anchor_pass_count=_AUTO_ANCHOR_MAX_PASSES,
            )
            for retry_index, original in enumerate(unresolved, start=1):
                checksum, entry, outcome = self._evaluate_source(
                    original,
                    source_directory=source_directory,
                    payload=payload,
                    registrar=registrar,
                )
                if outcome == "registered":
                    entry["automaticAnchorPass"] = pass_number
                    entries[checksum] = entry
                    resolved += 1
                if retry_index % _CHECKPOINT_BATCH_SIZE == 0 or retry_index == len(unresolved):
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
                        phase_current=retry_index,
                        phase_total=len(unresolved),
                        auto_anchor_pass=pass_number,
                        auto_anchor_pass_count=_AUTO_ANCHOR_MAX_PASSES,
                    )
            reports.append(
                {
                    "pass": pass_number,
                    "promotedAnchorChecksums": selected,
                    "resolvedSourceCount": resolved,
                }
            )
            if resolved == 0:
                break
        return entries, reports

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
        path = (
            self._artifact_root
            / "data"
            / "originals"
            / checksum_sha256[:2]
            / f"{checksum_sha256}.jpg"
        )
        try:
            with Image.open(path) as image:
                image.load()
                return np.asarray(ImageOps.exif_transpose(image).convert("RGB"), dtype=np.uint8)
        except (OSError, UnidentifiedImageError) as error:
            raise JobHandlerError(
                "IMAGE_PAGE_GEOMETRY_ANCHOR_UNAVAILABLE",
                "A reviewed geometry anchor image is unavailable.",
            ) from error

    @staticmethod
    def _override(
        payload: Mapping[str, object],
        source_checksum_sha256: str,
        *,
        width: int,
        height: int,
        expected_board_count: int,
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


def _uses_auto_anchors(preflight_policy_version: str) -> bool:
    return preflight_policy_version in {
        PAGE_GEOMETRY_PREFLIGHT_VERSION,
        PAGE_GEOMETRY_PREFLIGHT_BOARD_AREA_VERSION,
    }


def _registration_policy_matches_preflight(
    preflight_policy_version: object,
    registration_policy_version: object,
) -> bool:
    expected = {
        LEGACY_PAGE_GEOMETRY_PREFLIGHT_VERSION: PAGE_REGISTRATION_VERSION,
        PAGE_GEOMETRY_PREFLIGHT_VERSION: PAGE_REGISTRATION_VERSION,
        PAGE_GEOMETRY_PREFLIGHT_BOARD_AREA_VERSION: (
            PAGE_REGISTRATION_BOARD_AREA_MASK_VERSION
        ),
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
    optional = {"preflight_policy_version", "source_display_name"}
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
    if (
        not isinstance(selection, str)
        or not isinstance(directory, str)
        or not isinstance(checksum, str)
        or len(checksum) != 64
        or not isinstance(profile, Mapping)
        or not isinstance(overrides, Mapping)
        or not isinstance(canonical, list)
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
    return {
        "sourceSelectionId": selection,
        "sourceDirectory": directory,
        "sourceManifestChecksumSha256": checksum,
        "pageRegistrationProfile": dict(profile),
        "pageGeometryOverrides": dict(overrides),
        "canonicalSequenceNumbers": set(canonical),
        "preflightPolicyVersion": policy,
    }


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
            PAGE_GEOMETRY_MANIFEST_SCHEMA_VERSION
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
        if complete
        or not _uses_auto_anchors(cast(str, payload["preflightPolicyVersion"]))
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
) -> dict[str, object]:
    """Use reviewed page overrides as immutable cold-start registration anchors."""

    raw_anchors = profile.get("anchors")
    anchors = (
        [dict(value) for value in raw_anchors if isinstance(value, Mapping)]
        if isinstance(raw_anchors, Sequence) and not isinstance(raw_anchors, str | bytes)
        else []
    )
    known_checksums = {
        value.get("sourceChecksumSha256")
        for value in anchors
        if isinstance(value.get("sourceChecksumSha256"), str)
    }
    for checksum, raw in sorted(overrides.items()):
        if checksum in known_checksums or not isinstance(raw, Mapping):
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


def _strong_auto_anchor(entry: Mapping[str, object]) -> bool:
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
    "PAGE_GEOMETRY_PREFLIGHT_VERSION",
    "PAGE_GEOMETRY_PREFLIGHT_BOARD_AREA_VERSION",
    "PageGeometryPreflightHandler",
]
