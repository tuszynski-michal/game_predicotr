"""Durable crop runs of managed originals: plan, then confirmed execution (D-562).

The plan phase classifies every original in the run's scope, writes an
immutable manifest under ``data/source-crop-runs/<runId>/`` and records a
preview token. The execute phase starts only after the operator confirmed that
exact manifest. Per original it re-checks eligibility, crops losslessly with
``jpegtran``, verifies the decoded pixels (R7), writes the crop and then its
attestation atomically, and records the registry row in the same transaction as
a final eligibility check. Originals are only read. Progress is checkpointed
every 25 originals; a restart resumes after the last checkpoint and an original
that already has a registry row is never cropped twice.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import secrets
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Final, Protocol, cast
from uuid import UUID, uuid4

import numpy as np
from game_predictor_api.application.source_crop_runs import SourceCropRun, SourceCropScope
from game_predictor_api.domain.canonical_source import (
    ORIENTATION_TAG,
    CanonicalSourceLoadError,
    decode_canonical_source_bytes,
    decode_cropped_source_bytes,
    rgb_pixel_checksum_sha256,
)
from game_predictor_api.domain.jobs import Job, JobConflictError
from game_predictor_api.domain.source_crop import (
    DEFAULT_MARGIN_PX,
    SOURCE_CROP_POLICY_VERSION,
    PixelBox,
    SourceCropAttestation,
    SourceCropError,
    attestation_sha256,
    compose_canvas,
    cropped_original_relative_paths,
    encode_attestation,
    imcu_from_sampling_factors,
    is_crop_beneficial,
    plan_source_crop,
    raw_dimensions,
    verify_crop_pixels,
)
from game_predictor_api.domain.source_crop_eligibility import CropBlobEligibility
from game_predictor_api.storage.source_crop_run_repository import assert_job_lease
from game_predictor_api.storage.source_image_crop_models import SourceImageCropModel
from game_predictor_api.storage.source_image_crop_repository import (
    MAX_ELIGIBILITY_PAGE,
    SourceImageCropRepository,
)
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import Engine, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from game_predictor_worker.images.jpegtran import (
    JpegtranCropper,
    LosslessCropper,
    SourceCropToolError,
)
from game_predictor_worker.jobs.runtime import JobExecutionContext, JobHandlerError

MANIFEST_SCHEMA_VERSION: Final = 1
MANIFEST_DIRECTORY: Final = PurePosixPath("data", "source-crop-runs")
CHECKPOINT_EVERY_DEFAULT: Final = 25
CHECKPOINT_EVERY = CHECKPOINT_EVERY_DEFAULT
PLAN_PAGE_SIZE: Final = MAX_ELIGIBILITY_PAGE
MAX_RUN_FAILURES: Final = 100
_LOCK_NOT_AVAILABLE: Final = "55P03"
# Plan-only reasons next to the eligibility exclusions (CropExclusion).
ALREADY_CROPPED: Final = "ALREADY_CROPPED"
ORIGINAL_MISSING: Final = "ORIGINAL_MISSING"
ORIGINAL_HEADER_MISMATCH: Final = "ORIGINAL_HEADER_MISMATCH"
CROP_PLAN_INVALID: Final = "CROP_PLAN_INVALID"
# Execute outcomes; ``cropped`` counts as success, ``failed`` as failure and
# everything else as skipped.
CROPPED: Final = "cropped"
OUTCOME_ALREADY_CROPPED: Final = "alreadyCropped"
NOT_ELIGIBLE: Final = "notEligible"
NOT_BENEFICIAL: Final = "notBeneficial"
FAILED: Final = "failed"
_SKIPPED_OUTCOMES: Final = frozenset({OUTCOME_ALREADY_CROPPED, NOT_ELIGIBLE, NOT_BENEFICIAL})


@dataclass(frozen=True, slots=True)
class RegisteredCrop:
    job_id: UUID | None
    original_size_bytes: int
    crop_size_bytes: int
    attestation_sha256: str = ""
    state: str = "verified"
    deletion_job_id: UUID | None = None


class SourceCropCatalog(Protocol):
    """Eligibility and the crop registry, read from one snapshot per call."""

    def eligibility_page(
        self, *, after: str | None, scope: SourceCropScope, page_size: int
    ) -> list[CropBlobEligibility]: ...

    def registered(self, checksums: Sequence[str]) -> dict[str, RegisteredCrop]: ...

    def current(
        self, checksum: str
    ) -> tuple[CropBlobEligibility | None, RegisteredCrop | None]: ...

    def record_if_still_eligible(
        self,
        attestation: SourceCropAttestation,
        *,
        attestation_sha256: str,
        protected_points: tuple[tuple[float, float], ...],
        job_id: UUID,
        lease_token: UUID,
        verified_at: datetime,
    ) -> bool: ...

    def blob_lock(self, checksum: str) -> AbstractContextManager[None]:
        """Serialize every executor that touches the files of one original."""
        ...

    def assert_lease(self, job_id: UUID, lease_token: UUID) -> None: ...


class SourceCropRunStore(Protocol):
    def get_run(self, run_id: UUID) -> SourceCropRun: ...

    def mark_previewed(
        self,
        run_id: UUID,
        *,
        plan_job_id: UUID,
        lease_token: UUID,
        manifest_relative_path: str,
        manifest_checksum_sha256: str,
        preview_token: str,
        eligible_count: int,
        excluded_count: int,
        exclusion_counts: Mapping[str, int],
        candidate_bytes: int,
        estimated_saved_bytes: int,
    ) -> SourceCropRun: ...

    def manifest_of(self, run_id: UUID, *, job_id: UUID) -> SourceCropRun: ...

    def mark_processing(
        self, run_id: UUID, *, job_id: UUID, lease_token: UUID
    ) -> SourceCropRun: ...

    def checkpoint(
        self,
        run_id: UUID,
        *,
        job_id: UUID,
        lease_token: UUID,
        checkpoint_index: int,
        outcomes: Mapping[str, int],
        succeeded: int,
        skipped: int,
        failed: int,
        saved_bytes: int,
        failures: Sequence[Mapping[str, object]],
    ) -> None: ...

    def complete(self, run_id: UUID, *, job_id: UUID, lease_token: UUID) -> None: ...


class SqlSourceCropCatalog:
    """Cross-game eligibility on schema-owner sessions, one REPEATABLE READ snapshot each."""

    def __init__(self, owner_session_factory: sessionmaker[Session]) -> None:
        self._session_factory = owner_session_factory

    @contextmanager
    def _snapshot(self) -> Iterator[Session]:
        with self._session_factory.begin() as session:
            # Eligibility reads facts and geometry in separate statements.
            session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
            yield session

    def eligibility_page(
        self, *, after: str | None, scope: SourceCropScope, page_size: int
    ) -> list[CropBlobEligibility]:
        with self._snapshot() as session:
            return SourceImageCropRepository(session).eligibility(
                page_size=page_size,
                after_checksum=after,
                scope_game=scope.game_id,
                only_checksums=scope.only_checksums,
            )

    def registered(self, checksums: Sequence[str]) -> dict[str, RegisteredCrop]:
        if not checksums:
            return {}
        with self._snapshot() as session:
            repository = SourceImageCropRepository(session)
            found: dict[str, RegisteredCrop] = {}
            for checksum in checksums:
                row = repository.get(checksum)
                if row is not None:
                    found[checksum] = _registered(row)
            return found

    def current(self, checksum: str) -> tuple[CropBlobEligibility | None, RegisteredCrop | None]:
        with self._snapshot() as session:
            repository = SourceImageCropRepository(session)
            row = repository.get(checksum)
            page = repository.eligibility(page_size=1, only_checksums=(checksum,))
            return (page[0] if page else None), (None if row is None else _registered(row))

    def record_if_still_eligible(
        self,
        attestation: SourceCropAttestation,
        *,
        attestation_sha256: str,
        protected_points: tuple[tuple[float, float], ...],
        job_id: UUID,
        lease_token: UUID,
        verified_at: datetime,
    ) -> bool:
        checksum = attestation.original_checksum_sha256
        with self._snapshot() as session:
            assert_job_lease(session, job_id, lease_token)
            repository = SourceImageCropRepository(session)
            page = repository.eligibility(page_size=1, only_checksums=(checksum,))
            if (
                not page
                or not page[0].eligible
                or page[0].protected_points != protected_points
                or repository.get(checksum) is not None
            ):
                return False
            repository.record_verified(
                attestation,
                attestation_sha256=attestation_sha256,
                job_id=job_id,
                verified_at=verified_at,
            )
            return True

    @contextmanager
    def blob_lock(self, checksum: str) -> Iterator[None]:
        # A session-level advisory lock on a dedicated connection: it spans the
        # snapshot reads, the file work and the registry write of one original.
        engine = cast(Engine, self._session_factory.kw["bind"])
        key = _blob_lock_key(checksum)
        with engine.connect() as connection:
            connection.execute(text("SET lock_timeout = '300s'"))
            connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": key})
            connection.commit()
            try:
                yield
            finally:
                connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
                connection.commit()

    def assert_lease(self, job_id: UUID, lease_token: UUID) -> None:
        with self._session_factory.begin() as session:
            assert_job_lease(session, job_id, lease_token)

    def delete_original_if_still_eligible(
        self,
        checksum: str,
        *,
        attestation_sha256: str,
        game_ids: Sequence[UUID],
        still_covered: Callable[[tuple[tuple[float, float], ...]], bool],
        job_id: UUID,
        lease_token: UUID,
        deleted_at: datetime,
        unlink: Callable[[], None],
    ) -> str:
        """TASK-1048 (R8): unlink and ``original_deleted`` in one transaction.

        Every game-data write holds the shared storage write fence of its game
        until COMMIT (``GameStorageRouter``). The exclusive fence of each game
        of the blob is taken first, on a separate connection, so no write in
        those games is in flight while the snapshot is read and none starts
        until this COMMIT. Then the lease, the current eligibility (the same
        games), the coverage of today's protected quads by the attested crop
        and the locked ``verified`` row with the planned attestation are
        checked; the file is removed inside the transaction and the row is
        marked before COMMIT. A COMMIT that fails after the unlink leaves
        ``verified`` with no original, which the next attempt reconciles after
        verifying the crop again. Returns ``deleted``, ``not_eligible``,
        ``crop_outdated`` or ``game_busy`` (a fence wait timed out).
        """

        try:
            with self._game_fences(game_ids), self._snapshot() as session:
                assert_job_lease(session, job_id, lease_token)
                repository = SourceImageCropRepository(session)
                page = repository.eligibility(page_size=1, only_checksums=(checksum,))
                row = session.scalar(
                    select(SourceImageCropModel)
                    .where(SourceImageCropModel.original_checksum_sha256 == checksum)
                    .with_for_update()
                )
                if (
                    not page
                    or not page[0].eligible
                    or not set(page[0].game_ids) <= set(game_ids)
                    or row is None
                    or row.state != "verified"
                    or row.attestation_sha256 != attestation_sha256
                ):
                    return "not_eligible"
                if not still_covered(page[0].protected_points):
                    return "crop_outdated"
                unlink()
                repository.mark_original_deleted(
                    checksum, deleted_at=deleted_at, deletion_job_id=job_id
                )
                return "deleted"
        except OperationalError as error:
            if getattr(error.orig, "sqlstate", None) == _LOCK_NOT_AVAILABLE:
                return "game_busy"
            raise

    @contextmanager
    def _game_fences(self, game_ids: Sequence[UUID]) -> Iterator[None]:
        engine = cast(Engine, self._session_factory.kw["bind"])
        keys = sorted({str(game_id) for game_id in game_ids})
        with engine.connect() as connection:
            connection.execute(text("SET lock_timeout = '120s'"))
            held: list[str] = []
            try:
                for key in keys:  # one global order: no deadlock between two runs
                    connection.execute(
                        text("SELECT pg_advisory_lock(hashtextextended(:key, 519))"),
                        {"key": key},
                    )
                    held.append(key)
                connection.commit()
                yield
            finally:
                connection.rollback()
                for key in held:
                    connection.execute(
                        text("SELECT pg_advisory_unlock(hashtextextended(:key, 519))"),
                        {"key": key},
                    )
                connection.commit()


@dataclass(slots=True)
class _Progress:
    index: int
    outcomes: dict[str, int]
    succeeded: int
    skipped: int
    failed: int
    saved_bytes: int
    failures: list[dict[str, object]]
    success_outcome: str = CROPPED
    skipped_outcomes: frozenset[str] = _SKIPPED_OUTCOMES

    def add(self, outcome: str, saved: int, failure: Mapping[str, object] | None) -> None:
        self.index += 1
        self.outcomes[outcome] = self.outcomes.get(outcome, 0) + 1
        if outcome == self.success_outcome:
            self.succeeded += 1
            self.saved_bytes += saved
        elif outcome in self.skipped_outcomes:
            self.skipped += 1
        else:
            self.failed += 1
        if failure is not None and len(self.failures) < MAX_RUN_FAILURES:
            self.failures.append(dict(failure))


@dataclass(frozen=True, slots=True)
class _PlanEntry:
    checksum_sha256: str
    size_bytes: int
    crop_box: PixelBox
    estimated_saved_bytes: int

    def to_json(self) -> dict[str, object]:
        return {
            "checksumSha256": self.checksum_sha256,
            "sizeBytes": self.size_bytes,
            "cropBox": self.crop_box.as_list(),
            "estimatedSavedBytes": self.estimated_saved_bytes,
        }


@dataclass(frozen=True, slots=True)
class _BlobResult:
    outcome: str
    saved_bytes: int = 0
    failure: Mapping[str, object] | None = None


class _BlobFailure(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class SourceCropHandler:
    """Plans and executes ``source_crop`` runs (lane ``general``)."""

    def __init__(
        self,
        runs: SourceCropRunStore,
        catalog: SourceCropCatalog,
        artifact_root: Path,
        *,
        cropper_factory: Callable[[], LosslessCropper] = JpegtranCropper.resolve,
    ) -> None:
        self._runs = runs
        self._catalog = catalog
        self._artifact_root = artifact_root.resolve()
        self._data_root = self._artifact_root / "data"
        self._cropper_factory = cropper_factory

    def __call__(self, context: JobExecutionContext, job: Job) -> None:
        # The run follows the job: a failure or cancellation of this job reaches
        # the run atomically through ``synchronize_source_crop_job``.
        run_id, phase = _payload(job)
        try:
            if phase == "plan":
                self._plan(context, job, run_id)
            else:
                self._execute(context, job, run_id)
        except SourceCropToolError as error:
            raise JobHandlerError(error.code, error.message) from error

    # ----- plan --------------------------------------------------------------

    def _plan(self, context: JobExecutionContext, job: Job, run_id: UUID) -> None:
        run = self._runs.get_run(run_id)
        if run.plan_job_id != job.id or run.kind != "crop":
            raise JobHandlerError(
                "SOURCE_CROP_RUN_JOB_MISMATCH", "The plan job does not own this crop run."
            )
        if run.status in ("failed", "cancelled"):
            raise _finished(run)
        if run.status != "planning":
            return  # the preview was recorded before a restart
        entries: list[dict[str, object]] = []
        exclusions: dict[str, int] = {}
        candidate_bytes = 0
        estimated_saved = 0
        examined = 0
        after: str | None = None
        limit = run.scope.limit
        while limit is None or len(entries) < limit:
            page = self._catalog.eligibility_page(
                after=after, scope=run.scope, page_size=PLAN_PAGE_SIZE
            )
            if not page:
                break
            after = page[-1].original_checksum_sha256
            registered = self._catalog.registered(
                [item.original_checksum_sha256 for item in page if item.eligible]
            )
            for item in page:
                if limit is not None and len(entries) >= limit:
                    break
                examined += 1
                reasons = [reason.value for reason in item.exclusions]
                if not reasons and item.original_checksum_sha256 in registered:
                    reasons = [ALREADY_CROPPED]
                entry = None if reasons else self._plan_entry(item)
                if isinstance(entry, str):
                    reasons = [entry]
                if not isinstance(entry, _PlanEntry):
                    for reason in reasons:
                        exclusions[reason] = exclusions.get(reason, 0) + 1
                    continue
                entries.append(entry.to_json())
                candidate_bytes += entry.size_bytes
                estimated_saved += entry.estimated_saved_bytes
            context.checkpoint(
                checkpoint_payload={"schema_version": 1, "sourceCropRunId": str(run_id)},
                stage="source_crop_plan",
                current=examined,
                total=None,
                success_count=len(entries),
                failure_count=0,
                review_count=examined - len(entries),
            )
        manifest = {
            "schemaVersion": MANIFEST_SCHEMA_VERSION,
            "kind": "crop",
            "runId": str(run_id),
            "planJobId": str(job.id),
            "policyVersion": SOURCE_CROP_POLICY_VERSION,
            "marginPx": DEFAULT_MARGIN_PX,
            "scope": run.scope.to_payload(),
            "createdAt": context.now().isoformat(),
            "examinedCount": examined,
            "eligibleCount": len(entries),
            "excludedCount": examined - len(entries),
            "exclusionCounts": dict(sorted(exclusions.items())),
            "candidateBytes": candidate_bytes,
            "estimatedSavedBytes": estimated_saved,
            "entries": entries,
        }
        content = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
        relative = MANIFEST_DIRECTORY / str(run_id) / "manifest.json"
        _write_atomic(self._artifact_root.joinpath(*relative.parts), content)
        self._runs.mark_previewed(
            run_id,
            plan_job_id=job.id,
            lease_token=context.lease_token,
            manifest_relative_path=relative.as_posix(),
            manifest_checksum_sha256=hashlib.sha256(content).hexdigest(),
            preview_token=secrets.token_hex(32),
            eligible_count=len(entries),
            excluded_count=examined - len(entries),
            exclusion_counts=exclusions,
            candidate_bytes=candidate_bytes,
            estimated_saved_bytes=estimated_saved,
        )

    def _plan_entry(self, item: CropBlobEligibility) -> _PlanEntry | str:
        """A manifest entry from the JPEG header, or the plan exclusion reason."""

        path = self._original_path(item)
        try:
            size = path.stat().st_size
            with Image.open(path) as image:
                raw_size = image.size
                factors = [(int(h), int(v)) for _, h, v, _ in getattr(image, "layer", ())]
        except FileNotFoundError:
            return ORIGINAL_MISSING
        except (OSError, UnidentifiedImageError, ValueError):
            return ORIGINAL_HEADER_MISMATCH
        if item.oriented_width is None or item.oriented_height is None:
            return ORIGINAL_HEADER_MISMATCH
        try:
            if (
                raw_dimensions(item.oriented_width, item.oriented_height, item.exif_orientation)
                != raw_size
            ):
                return ORIGINAL_HEADER_MISMATCH
            plan = plan_source_crop(
                item.protected_points,
                oriented_width=item.oriented_width,
                oriented_height=item.oriented_height,
                orientation=item.exif_orientation,
                imcu=imcu_from_sampling_factors(factors),
            )
        except SourceCropError:
            return CROP_PLAN_INVALID
        area = item.oriented_width * item.oriented_height
        box = plan.oriented_box
        estimated_crop = -(-size * box.width * box.height // area)
        return _PlanEntry(
            checksum_sha256=item.original_checksum_sha256,
            size_bytes=size,
            crop_box=box,
            estimated_saved_bytes=max(0, size - estimated_crop),
        )

    # ----- execute -----------------------------------------------------------

    def _execute(self, context: JobExecutionContext, job: Job, run_id: UUID) -> None:
        run = self._runs.manifest_of(run_id, job_id=job.id)
        if run.kind != "crop":
            raise JobHandlerError(
                "SOURCE_CROP_RUN_JOB_MISMATCH", "The execute job does not own this crop run."
            )
        if run.status in ("failed", "cancelled"):
            raise _finished(run)
        if run.status == "completed":
            return
        entries = self._load_manifest(job, run)
        cropper = self._cropper_factory()  # SOURCE_CROP_TOOL_UNAVAILABLE before any write
        lease = context.lease_token
        run = self._runs.mark_processing(run_id, job_id=job.id, lease_token=lease)
        progress = _Progress(
            index=run.checkpoint_index,
            outcomes=dict(run.outcome_counts),
            succeeded=run.succeeded_count,
            skipped=run.skipped_count,
            failed=run.failed_count,
            saved_bytes=run.saved_bytes,
            failures=[dict(item) for item in run.failures],
        )
        while progress.index < len(entries):
            stop = min(len(entries), progress.index + CHECKPOINT_EVERY)
            while progress.index < stop:
                checksum = entries[progress.index]
                with self._catalog.blob_lock(checksum):
                    result = self._crop_one(checksum, cropper, job.id, lease, context.now())
                progress.add(result.outcome, result.saved_bytes, result.failure)
            self._runs.checkpoint(
                run_id,
                job_id=job.id,
                lease_token=lease,
                checkpoint_index=progress.index,
                outcomes=progress.outcomes,
                succeeded=progress.succeeded,
                skipped=progress.skipped,
                failed=progress.failed,
                saved_bytes=progress.saved_bytes,
                failures=progress.failures,
            )
            context.checkpoint(
                checkpoint_payload={
                    "schema_version": 1,
                    "sourceCropRunId": str(run_id),
                    "checkpointIndex": progress.index,
                },
                stage="source_crop_execute",
                current=progress.index,
                total=len(entries),
                success_count=progress.succeeded,
                failure_count=progress.failed,
                review_count=progress.skipped,
            )
        self._runs.complete(run_id, job_id=job.id, lease_token=lease)

    def _load_manifest(self, job: Job, run: SourceCropRun) -> list[str]:
        expected = run.manifest_checksum_sha256
        relative = MANIFEST_DIRECTORY / str(run.id) / "manifest.json"
        path = self._artifact_root.joinpath(*relative.parts)
        try:
            content = path.read_bytes()
        except OSError as error:
            raise JobHandlerError(
                "SOURCE_CROP_MANIFEST_CHANGED", "The crop run manifest is unavailable."
            ) from error
        if (
            expected is None
            or hashlib.sha256(content).hexdigest() != expected
            or job.input_payload.get("manifest_checksum_sha256") != expected
        ):
            raise JobHandlerError(
                "SOURCE_CROP_MANIFEST_CHANGED", "The crop run manifest checksum changed."
            )
        try:
            manifest = json.loads(content)
            raw_entries = manifest["entries"]
            if manifest["schemaVersion"] != MANIFEST_SCHEMA_VERSION or not isinstance(
                raw_entries, list
            ):
                raise ValueError
            checksums = [str(entry["checksumSha256"]) for entry in raw_entries]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise JobHandlerError(
                "SOURCE_CROP_MANIFEST_CHANGED", "The crop run manifest is invalid."
            ) from error
        return checksums

    def _crop_one(
        self,
        checksum: str,
        cropper: LosslessCropper,
        job_id: UUID,
        lease_token: UUID,
        now: datetime,
    ) -> _BlobResult:
        eligibility, registered = self._catalog.current(checksum)
        crop_path, attestation_path = self._crop_paths(checksum)
        if registered is not None:
            if not (crop_path.is_file() and attestation_path.is_file()):
                # A registry row never hides missing crop files.
                return _BlobResult(
                    FAILED,
                    failure={
                        "checksumSha256": checksum,
                        "code": "SOURCE_CROP_FILES_MISSING",
                        "message": "The registered crop or its attestation is missing.",
                    },
                )
            if registered.job_id == job_id:
                # Recorded by this job before a restart, after the last checkpoint.
                saved = registered.original_size_bytes - registered.crop_size_bytes
                return _BlobResult(CROPPED, max(0, saved))
            return _BlobResult(OUTCOME_ALREADY_CROPPED)
        if eligibility is None or not eligibility.eligible:
            return _BlobResult(NOT_ELIGIBLE)
        try:
            return self._create_crop(
                eligibility, cropper, job_id, lease_token, now, crop_path, attestation_path
            )
        except _BlobFailure as failure:
            return _BlobResult(
                FAILED,
                failure={
                    "checksumSha256": checksum,
                    "code": failure.code,
                    "message": failure.message,
                },
            )
        finally:
            _remove_parts(crop_path.parent, checksum)

    def _create_crop(
        self,
        eligibility: CropBlobEligibility,
        cropper: LosslessCropper,
        job_id: UUID,
        lease_token: UUID,
        now: datetime,
        crop_path: Path,
        attestation_path: Path,
    ) -> _BlobResult:
        checksum = eligibility.original_checksum_sha256
        original_path = self._original_path(eligibility)
        try:
            content = original_path.read_bytes()
        except FileNotFoundError as error:
            raise _BlobFailure("ORIGINAL_MISSING", "The managed original is missing.") from error
        except OSError as error:
            raise _BlobFailure(
                "ORIGINAL_UNREADABLE", "The managed original cannot be read."
            ) from error
        if hashlib.sha256(content).hexdigest() != checksum:
            raise _BlobFailure(
                "ORIGINAL_CHECKSUM_MISMATCH", "The managed original differs from its checksum."
            )
        # The original is intact and has no registry row, so leftover crop files
        # are an unregistered output of an interrupted run: start over. The
        # blob lock and a current lease keep a superseded executor away.
        self._catalog.assert_lease(job_id, lease_token)
        _unlink(crop_path)
        _unlink(attestation_path)
        try:
            frame = decode_canonical_source_bytes(content, expected_source_checksum_sha256=checksum)
            with Image.open(io.BytesIO(content)) as image:
                factors = [(int(h), int(v)) for _, h, v, _ in getattr(image, "layer", ())]
                orientation_tag = image.getexif().get(ORIENTATION_TAG)
        except CanonicalSourceLoadError as error:
            raise _BlobFailure(error.code, str(error)) from error
        except (OSError, UnidentifiedImageError, ValueError) as error:
            raise _BlobFailure(
                "ORIGINAL_UNREADABLE", "The original header cannot be read."
            ) from error
        source = frame.source
        if (
            source.width != eligibility.oriented_width
            or source.height != eligibility.oriented_height
            or source.normalized_pixel_checksum_sha256
            != eligibility.normalized_pixel_checksum_sha256
        ):
            raise _BlobFailure(
                "ORIGINAL_IDENTITY_MISMATCH",
                "The decoded original differs from its recorded dimensions or pixels.",
            )
        try:
            plan = plan_source_crop(
                eligibility.protected_points,
                oriented_width=source.width,
                oriented_height=source.height,
                orientation=source.exif_orientation,
                imcu=imcu_from_sampling_factors(factors),
            )
        except SourceCropError as error:
            raise _BlobFailure(error.code, str(error)) from error
        box = plan.oriented_box
        if box == PixelBox(0, 0, source.width, source.height):
            return _BlobResult(NOT_BENEFICIAL)
        crop_part = _part_path(crop_path, checksum)
        crop_part.parent.mkdir(parents=True, exist_ok=True)
        try:
            cropper.crop(original_path, crop_part, plan.raw_box)
            crop_content = crop_part.read_bytes()
        except SourceCropToolError as error:
            raise _BlobFailure(error.code, error.message) from error
        except OSError as error:
            raise _BlobFailure(
                "SOURCE_CROP_TOOL_FAILED", "The crop output cannot be read."
            ) from error
        if not is_crop_beneficial(
            original_size_bytes=len(content), crop_size_bytes=len(crop_content)
        ):
            return _BlobResult(NOT_BENEFICIAL)
        try:
            with Image.open(io.BytesIO(crop_content)) as cropped:
                if cropped.format != "JPEG" or cropped.getexif().get(ORIENTATION_TAG) != (
                    orientation_tag
                ):
                    raise _BlobFailure(
                        "SOURCE_CROP_VERIFICATION_FAILED",
                        "The crop is not a JPEG with the original EXIF orientation.",
                    )
                crop_rgb = np.array(
                    ImageOps.exif_transpose(cropped).convert("RGB"), dtype=np.uint8, copy=True
                )
            verdict = verify_crop_pixels(
                frame.rgb[box.top : box.bottom, box.left : box.right],
                crop_rgb,
                crop_box=box,
                image_width=source.width,
                image_height=source.height,
                protected=plan.protected_box,
            )
            canvas = compose_canvas(
                crop_rgb, crop_box=box, width=source.width, height=source.height
            )
            attestation = SourceCropAttestation(
                original_checksum_sha256=checksum,
                original_size_bytes=len(content),
                original_normalized_pixel_checksum_sha256=source.normalized_pixel_checksum_sha256,
                original_width=source.width,
                original_height=source.height,
                original_exif_orientation=source.exif_orientation,
                crop_checksum_sha256=hashlib.sha256(crop_content).hexdigest(),
                crop_size_bytes=len(crop_content),
                crop_normalized_pixel_checksum_sha256=rgb_pixel_checksum_sha256(crop_rgb),
                canvas_pixel_checksum_sha256=rgb_pixel_checksum_sha256(canvas),
                crop_box=box,
                raw_crop_box=plan.raw_box,
                protected_box=plan.protected_box,
                margin_px=plan.margin_px,
                imcu_width=plan.imcu_width,
                imcu_height=plan.imcu_height,
                edge_mismatch_pixels=verdict.edge_mismatch_pixels,
                tool_version=cropper.version,
            )
            document = encode_attestation(attestation)
            # The loader's own path must accept what is about to be published.
            rebuilt = decode_cropped_source_bytes(
                crop_content, document, expected_source_checksum_sha256=checksum
            )
        except SourceCropError as error:
            raise _BlobFailure(error.code, str(error)) from error
        except CanonicalSourceLoadError as error:
            raise _BlobFailure(error.code, str(error)) from error
        except (OSError, UnidentifiedImageError) as error:
            raise _BlobFailure(
                "SOURCE_CROP_VERIFICATION_FAILED", "The crop output cannot be decoded."
            ) from error
        if rgb_pixel_checksum_sha256(rebuilt.rgb) != attestation.canvas_pixel_checksum_sha256:
            raise _BlobFailure(
                "SOURCE_CROP_VERIFICATION_FAILED",
                "The rebuilt canvas differs from the attestation.",
            )
        # Crop first, attestation last: the loader never sees a crop alone.
        os.replace(crop_part, crop_path)
        document_sha256 = attestation_sha256(document)
        try:
            _write_atomic(attestation_path, document, part=_part_path(attestation_path, checksum))
            recorded = self._catalog.record_if_still_eligible(
                attestation,
                attestation_sha256=document_sha256,
                protected_points=eligibility.protected_points,
                job_id=job_id,
                lease_token=lease_token,
                verified_at=now,
            )
        except JobConflictError as error:
            if error.code == "JOB_LEASE_LOST":
                # Refused before the insert: nothing refers to these files.
                _unlink(attestation_path)
                _unlink(crop_path)
            raise
        except Exception:
            # The COMMIT may have succeeded although its answer was lost.
            state = self._recorded_by(checksum, document_sha256)
            if state is None:
                raise  # unknown or unreadable: keep the files for reconciliation
            if state is False:
                _unlink(attestation_path)
                _unlink(crop_path)
                raise
            recorded = True
        if not recorded:
            _unlink(attestation_path)
            _unlink(crop_path)
            return _BlobResult(NOT_ELIGIBLE)
        return _BlobResult(CROPPED, len(content) - len(crop_content))

    def _recorded_by(self, checksum: str, document_sha256: str) -> bool | None:
        """Whether the registry holds this exact attestation; ``None`` when unknown."""

        try:
            _, registered = self._catalog.current(checksum)
        except Exception:
            return None
        if registered is None:
            return False
        return registered.attestation_sha256 == document_sha256 or None

    def _original_path(self, item: CropBlobEligibility) -> Path:
        relative = PurePosixPath(item.original_relative_path)
        return self._data_root.joinpath(*relative.parts)

    def _crop_paths(self, checksum: str) -> tuple[Path, Path]:
        crop, attestation = cropped_original_relative_paths(checksum)
        return self._data_root.joinpath(*crop.parts), self._data_root.joinpath(*attestation.parts)


def _payload(job: Job) -> tuple[UUID, str]:
    payload = job.input_payload
    try:
        run_id = UUID(str(payload["source_crop_run_id"]))
        phase = str(payload["phase"])
    except (KeyError, ValueError) as error:
        raise JobHandlerError(
            "SOURCE_CROP_PAYLOAD_INVALID", "The crop job payload is invalid."
        ) from error
    if phase not in ("plan", "execute") or payload.get("kind") != "crop":
        raise JobHandlerError("SOURCE_CROP_PAYLOAD_INVALID", "The crop job payload is invalid.")
    return run_id, phase


def _registered(row: Any) -> RegisteredCrop:
    return RegisteredCrop(
        job_id=row.job_id,
        original_size_bytes=int(row.original_size_bytes),
        crop_size_bytes=int(row.crop_size_bytes),
        attestation_sha256=str(row.attestation_sha256),
        state=str(row.state),
        deletion_job_id=row.deletion_job_id,
    )


def _finished(run: SourceCropRun) -> JobHandlerError:
    return JobHandlerError(
        "SOURCE_CROP_RUN_FINISHED",
        f"The crop run is {run.status}; retry its job or create a new preview.",
    )


def _blob_lock_key(checksum: str) -> int:
    digest = hashlib.sha256(f"source-crop-blob-v1:{checksum}".encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


def _part_path(target: Path, checksum: str) -> Path:
    return target.with_name(f".{checksum}.{uuid4().hex}.part")


def _remove_parts(directory: Path, checksum: str) -> None:
    """Drop this original's temporary files; other originals' are untouched."""

    if not directory.is_dir():
        return
    for part in directory.glob(f".{checksum}.*.part"):
        _unlink(part)


def _write_atomic(target: Path, content: bytes, *, part: Path | None = None) -> None:
    temporary = part or target.with_name(f".{target.name}.{uuid4().hex}.part")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with temporary.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        _unlink(temporary)


def _unlink(path: Path) -> None:
    path.unlink(missing_ok=True)


__all__ = [
    "CHECKPOINT_EVERY",
    "MANIFEST_DIRECTORY",
    "RegisteredCrop",
    "SourceCropCatalog",
    "SourceCropHandler",
    "SourceCropRunStore",
    "SqlSourceCropCatalog",
]
