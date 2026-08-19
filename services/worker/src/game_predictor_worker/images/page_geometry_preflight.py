"""Durable preflight that builds a content-addressed page-geometry manifest."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath
from typing import cast

import numpy as np
from game_predictor_api.domain.jobs import Job, JobType
from PIL import Image, ImageOps, UnidentifiedImageError

from game_predictor_worker.jobs.runtime import JobExecutionContext, JobHandlerError

from .page_geometry_registration import PAGE_REGISTRATION_VERSION, VerifiedPageRegistrar
from .source_ingestion import (
    BROWSER_SELECTION_MANIFEST,
    ManagedOriginal,
    ManagedOriginalStore,
    _safe_source_path,
)

PAGE_GEOMETRY_MANIFEST_SCHEMA_VERSION = 1
PAGE_GEOMETRY_PREFLIGHT_VERSION = "page-geometry-preflight-v1"
_CHECKPOINT_BATCH_SIZE = 10
# Registration is CPU-bound but OpenCV runs most feature work outside the GIL.
# Four concurrent pages keeps the current workstation busy without competing
# with the worker process itself or materialising more than four JPEGs at once.
_REGISTRATION_WORKERS = 4


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
    ) -> None:
        self._artifact_root = artifact_root.resolve()
        self._originals = ManagedOriginalStore(self._artifact_root)

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
            )
            return

        source_directory = Path(cast(str, payload["sourceDirectory"]))
        _verify_browser_source_manifest(
            source_directory,
            expected_checksum=cast(str, payload["sourceManifestChecksumSha256"]),
        )
        managed = self._originals.load_or_create_manifest(
            job,
            source_directory=source_directory,
        )
        registrar = VerifiedPageRegistrar(
            cast(Mapping[str, object], payload["pageRegistrationProfile"]),
            load_anchor_rgb=self._load_anchor_rgb,
        )
        if not registrar.available:
            raise JobHandlerError(
                "IMAGE_PAGE_GEOMETRY_PROFILE_EMPTY",
                "No complete reviewed page is available as a geometry registration anchor.",
            )
        entries: dict[str, object] = {}
        registered = review_required = skipped = 0
        total = len(managed.originals)
        with ThreadPoolExecutor(max_workers=_REGISTRATION_WORKERS) as executor:
            results = executor.map(
                lambda original: self._evaluate_source(
                    original,
                    source_directory=managed.source_directory,
                    payload=payload,
                    registrar=registrar,
                ),
                managed.originals,
            )
            for index, (checksum, entry, outcome) in enumerate(results, start=1):
                entries[checksum] = entry
                if outcome == "registered":
                    registered += 1
                elif outcome == "review_required":
                    review_required += 1
                else:
                    skipped += 1
                if index % _CHECKPOINT_BATCH_SIZE == 0 or index == total:
                    _checkpoint(
                        context,
                        payload,
                        manifest_checksum=None,
                        manifest_relative_path=None,
                        processed=index,
                        total=total,
                        registered=registered,
                        review_required=review_required,
                        complete=False,
                    )
        content = _manifest_bytes(
            job, payload, entries, total, registered, review_required, skipped
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
        )
        if override is not None:
            return (
                original.checksum_sha256,
                {
                    "status": "registered",
                    "sourceRelativePath": original.source_relative_path,
                    **override,
                },
                "registered",
            )
        result = registrar.register(rgb)
        if result is None:
            return (
                original.checksum_sha256,
                {
                    "status": "review_required",
                    "sourceRelativePath": original.source_relative_path,
                },
                "review_required",
            )
        return (
            original.checksum_sha256,
            {
                "status": "registered",
                "sourceRelativePath": original.source_relative_path,
                **result.to_payload(),
            },
            "registered",
        )

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
    ) -> dict[str, object] | None:
        overrides = payload.get("pageGeometryOverrides")
        raw = overrides.get(source_checksum_sha256) if isinstance(overrides, Mapping) else None
        if not isinstance(raw, Mapping):
            return None
        if raw.get("imageWidth") != width or raw.get("imageHeight") != height:
            return None
        quads = raw.get("quads")
        if not isinstance(quads, list) or len(quads) != 9:
            return None
        return {
            "anchorSourceChecksumSha256": None,
            "boardRedEdgeCoverages": [1.0] * 9,
            "inlierCount": 0,
            "inlierRatio": 0.0,
            "manualOverrideDecisionChecksumSha256": raw.get("decisionChecksumSha256"),
            "manualOverrideId": raw.get("overrideId"),
            "manualOverrideRevision": raw.get("revision"),
            "meanRedEdgeCoverage": 1.0,
            "p95ReprojectionError": 0.0,
            "quads": quads,
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
    if (
        job.job_type is not JobType.VALIDATE
        or job.game_id is None
        or set(payload) != required
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
    if (
        not isinstance(selection, str)
        or not isinstance(directory, str)
        or not isinstance(checksum, str)
        or len(checksum) != 64
        or not isinstance(profile, Mapping)
        or profile.get("policy") != PAGE_REGISTRATION_VERSION
        or not isinstance(overrides, Mapping)
        or not isinstance(canonical, list)
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
) -> bytes:
    value = {
        "entries": dict(sorted(entries.items())),
        "gameId": str(job.game_id),
        "pageRegistrationProfile": payload["pageRegistrationProfile"],
        "reviewRequiredSourceCount": review_required,
        "skippedHumanResolvedSourceCount": skipped_human_resolved,
        "registeredSourceCount": registered,
        "schemaVersion": PAGE_GEOMETRY_MANIFEST_SCHEMA_VERSION,
        "sourceCount": source_count,
        "sourceManifestChecksumSha256": payload["sourceManifestChecksumSha256"],
        "sourceSelectionId": payload["sourceSelectionId"],
        "version": PAGE_GEOMETRY_PREFLIGHT_VERSION,
    }
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
        or value.get("schemaVersion") != PAGE_GEOMETRY_MANIFEST_SCHEMA_VERSION
        or value.get("version") != PAGE_GEOMETRY_PREFLIGHT_VERSION
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
) -> None:
    value: dict[str, object] = {
        "schema_version": 1,
        "workflow": PAGE_GEOMETRY_PREFLIGHT_VERSION,
        "source_selection_id": payload["sourceSelectionId"],
        "source_manifest_sha256": payload["sourceManifestChecksumSha256"],
        "processed_source_count": processed,
        "registered_source_count": registered,
        "review_required_source_count": review_required,
        "complete": complete,
    }
    if manifest_checksum is not None and manifest_relative_path is not None:
        value["geometry_manifest_checksum_sha256"] = manifest_checksum
        value["geometry_manifest_relative_path"] = manifest_relative_path
    context.checkpoint(
        checkpoint_payload=value,
        stage=("page_geometry_manifest_ready" if complete else "page_geometry_registering"),
        current=processed,
        total=total,
        success_count=registered,
        failure_count=0,
        review_count=review_required,
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


__all__ = [
    "PAGE_GEOMETRY_MANIFEST_SCHEMA_VERSION",
    "PAGE_GEOMETRY_PREFLIGHT_VERSION",
    "PageGeometryPreflightHandler",
]
