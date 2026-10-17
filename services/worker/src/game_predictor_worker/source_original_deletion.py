"""Durable deletion of managed originals replaced by verified crops (D-562, TASK-1048).

The only destructive step of the crop plan, and irreversible: there is no copy
of the photos. A run is planned like a crop run (eligibility of every game,
an immutable manifest, a preview token) and executed only after its own
confirmation with ``acknowledgeIrreversible``. Per original the job holds the
blob lock and then requires, in this order: a current lease, a registry row
``verified`` with the attestation of the plan, current eligibility, a crop and
attestation that the loader accepts with the attested canvas, and an original
whose SHA-256 and size equal the row. The unlink and the state
``original_deleted`` are one unit: the file is removed inside the transaction
that re-checks eligibility and the lease and marks the row. A restart that finds
the original already gone with the row still ``verified`` re-verifies the crop
and only then marks the row (R8).
"""

from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Protocol
from uuid import UUID

from game_predictor_api.application.source_crop_runs import SourceCropRun
from game_predictor_api.domain.canonical_source import (
    CanonicalSourceLoadError,
    decode_cropped_source_bytes,
    rgb_pixel_checksum_sha256,
)
from game_predictor_api.domain.jobs import Job
from game_predictor_api.domain.source_crop import (
    SourceCropAttestation,
    crop_covers_points,
    cropped_original_relative_paths,
)

from game_predictor_worker.jobs.runtime import JobExecutionContext, JobHandlerError
from game_predictor_worker.source_crop import (
    CHECKPOINT_EVERY_DEFAULT,
    MANIFEST_DIRECTORY,
    MANIFEST_SCHEMA_VERSION,
    PLAN_PAGE_SIZE,
    RegisteredCrop,
    SourceCropCatalog,
    SourceCropRunStore,
    _finished,
    _Progress,
    _write_atomic,
)

KIND = "original_deletion"
CHECKPOINT_EVERY = CHECKPOINT_EVERY_DEFAULT
# Plan-only reasons next to the eligibility exclusions.
NOT_CROPPED = "NOT_CROPPED"
ALREADY_DELETED = "ALREADY_DELETED"
# Execute outcomes; ``deleted`` is success, ``failed`` failure, the rest skipped.
DELETED = "deleted"
OUTCOME_NOT_CROPPED = "notCropped"
OUTCOME_ALREADY_DELETED = "alreadyDeleted"
CROP_CHANGED = "cropChanged"
CROP_OUTDATED = "cropOutdated"
GAME_BUSY = "gameBusy"
NOT_ELIGIBLE = "notEligible"
FAILED = "failed"
_SKIPPED = frozenset(
    {
        OUTCOME_NOT_CROPPED,
        OUTCOME_ALREADY_DELETED,
        CROP_CHANGED,
        CROP_OUTDATED,
        GAME_BUSY,
        NOT_ELIGIBLE,
    }
)
_UNIT_OUTCOMES = {
    "deleted": DELETED,
    "not_eligible": NOT_ELIGIBLE,
    "crop_outdated": CROP_OUTDATED,
    "game_busy": GAME_BUSY,
}


class SourceDeletionCatalog(SourceCropCatalog, Protocol):
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
        """Run ``unlink`` and mark the row in one fenced, re-checked transaction.

        Returns ``deleted``, ``not_eligible``, ``crop_outdated`` or ``game_busy``.
        """
        ...


@dataclass(frozen=True, slots=True)
class _Result:
    outcome: str
    freed_bytes: int = 0
    failure: Mapping[str, object] | None = None


class _Refused(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class SourceOriginalDeletionHandler:
    """Plans and executes ``source_original_deletion`` runs (lane ``general``)."""

    def __init__(
        self, runs: SourceCropRunStore, catalog: SourceDeletionCatalog, artifact_root: Path
    ) -> None:
        self._runs = runs
        self._catalog = catalog
        self._artifact_root = artifact_root.resolve()
        self._data_root = self._artifact_root / "data"

    def __call__(self, context: JobExecutionContext, job: Job) -> None:
        run_id, phase = _payload(job)
        if phase == "plan":
            self._plan(context, job, run_id)
        else:
            self._execute(context, job, run_id)

    # ----- plan --------------------------------------------------------------

    def _plan(self, context: JobExecutionContext, job: Job, run_id: UUID) -> None:
        run = self._runs.get_run(run_id)
        if run.plan_job_id != job.id or run.kind != KIND:
            raise JobHandlerError(
                "SOURCE_CROP_RUN_JOB_MISMATCH", "The plan job does not own this deletion run."
            )
        if run.status in ("failed", "cancelled"):
            raise _finished(run)
        if run.status != "planning":
            return
        entries: list[dict[str, object]] = []
        exclusions: dict[str, int] = {}
        candidate_bytes = 0
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
            rows = self._catalog.registered([item.original_checksum_sha256 for item in page])
            for item in page:
                if limit is not None and len(entries) >= limit:
                    break
                examined += 1
                reasons = [reason.value for reason in item.exclusions]
                row = rows.get(item.original_checksum_sha256)
                if not reasons:
                    if row is None:
                        reasons = [NOT_CROPPED]
                    elif row.state != "verified":
                        reasons = [ALREADY_DELETED]
                if reasons or row is None:
                    for reason in reasons:
                        exclusions[reason] = exclusions.get(reason, 0) + 1
                    continue
                entries.append(
                    {
                        "checksumSha256": item.original_checksum_sha256,
                        "sizeBytes": row.original_size_bytes,
                        "attestationSha256": row.attestation_sha256,
                    }
                )
                candidate_bytes += row.original_size_bytes
            context.checkpoint(
                checkpoint_payload={"schema_version": 1, "sourceCropRunId": str(run_id)},
                stage="source_original_deletion_plan",
                current=examined,
                total=None,
                success_count=len(entries),
                failure_count=0,
                review_count=examined - len(entries),
            )
        manifest = {
            "schemaVersion": MANIFEST_SCHEMA_VERSION,
            "kind": KIND,
            "runId": str(run_id),
            "planJobId": str(job.id),
            # The operator decided to delete without any copy of the photos.
            "irreversible": True,
            "scope": run.scope.to_payload(),
            "createdAt": context.now().isoformat(),
            "examinedCount": examined,
            "eligibleCount": len(entries),
            "excludedCount": examined - len(entries),
            "exclusionCounts": dict(sorted(exclusions.items())),
            "candidateBytes": candidate_bytes,
            "estimatedSavedBytes": candidate_bytes,
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
            estimated_saved_bytes=candidate_bytes,
        )

    # ----- execute -----------------------------------------------------------

    def _execute(self, context: JobExecutionContext, job: Job, run_id: UUID) -> None:
        run = self._runs.manifest_of(run_id, job_id=job.id)
        if run.kind != KIND:
            raise JobHandlerError(
                "SOURCE_CROP_RUN_JOB_MISMATCH", "The execute job does not own this deletion run."
            )
        if run.status in ("failed", "cancelled"):
            raise _finished(run)
        if run.status == "completed":
            return
        entries = self._load_manifest(job, run)
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
            success_outcome=DELETED,
            skipped_outcomes=_SKIPPED,
        )
        while progress.index < len(entries):
            stop = min(len(entries), progress.index + CHECKPOINT_EVERY)
            while progress.index < stop:
                checksum, attestation = entries[progress.index]
                with self._catalog.blob_lock(checksum):
                    result = self._delete_one(checksum, attestation, job.id, lease, context.now())
                progress.add(result.outcome, result.freed_bytes, result.failure)
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
                stage="source_original_deletion_execute",
                current=progress.index,
                total=len(entries),
                success_count=progress.succeeded,
                failure_count=progress.failed,
                review_count=progress.skipped,
            )
        self._runs.complete(run_id, job_id=job.id, lease_token=lease)

    def _load_manifest(self, job: Job, run: SourceCropRun) -> list[tuple[str, str]]:
        expected = run.manifest_checksum_sha256
        relative = MANIFEST_DIRECTORY / str(run.id) / "manifest.json"
        try:
            content = self._artifact_root.joinpath(*relative.parts).read_bytes()
        except OSError as error:
            raise JobHandlerError(
                "SOURCE_CROP_MANIFEST_CHANGED", "The deletion run manifest is unavailable."
            ) from error
        if (
            expected is None
            or hashlib.sha256(content).hexdigest() != expected
            or job.input_payload.get("manifest_checksum_sha256") != expected
        ):
            raise JobHandlerError(
                "SOURCE_CROP_MANIFEST_CHANGED", "The deletion run manifest checksum changed."
            )
        try:
            manifest = json.loads(content)
            if (
                manifest["schemaVersion"] != MANIFEST_SCHEMA_VERSION
                or manifest["kind"] != KIND
                or not isinstance(manifest["entries"], list)
            ):
                raise ValueError
            return [
                (str(entry["checksumSha256"]), str(entry["attestationSha256"]))
                for entry in manifest["entries"]
            ]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise JobHandlerError(
                "SOURCE_CROP_MANIFEST_CHANGED", "The deletion run manifest is invalid."
            ) from error

    def _delete_one(
        self,
        checksum: str,
        planned_attestation: str,
        job_id: UUID,
        lease_token: UUID,
        now: datetime,
    ) -> _Result:
        self._catalog.assert_lease(job_id, lease_token)
        eligibility, row = self._catalog.current(checksum)
        if row is None:
            return _Result(OUTCOME_NOT_CROPPED)
        if row.state != "verified":
            if row.deletion_job_id == job_id:
                # Deleted by this job after its last checkpoint: count it once.
                return _Result(DELETED, row.original_size_bytes)
            return _Result(OUTCOME_ALREADY_DELETED)
        if row.attestation_sha256 != planned_attestation:
            return _Result(CROP_CHANGED)
        if eligibility is None or not eligibility.eligible:
            return _Result(NOT_ELIGIBLE)
        original = self._data_root.joinpath(
            *PurePosixPath(eligibility.original_relative_path).parts
        )
        try:
            attestation = self._verify_crop(checksum, row)
            self._verify_original(original, checksum, row)
        except _Refused as refused:
            return _Result(
                FAILED,
                failure={
                    "checksumSha256": checksum,
                    "code": refused.code,
                    "message": refused.message,
                },
            )

        def unlink() -> None:
            # Without quarantine (operator decision); a missing file is the
            # reconciliation of an earlier unlink whose state write was lost.
            original.unlink(missing_ok=True)

        outcome = _UNIT_OUTCOMES[
            self._catalog.delete_original_if_still_eligible(
                checksum,
                attestation_sha256=row.attestation_sha256,
                game_ids=eligibility.game_ids,
                # Geometry approved after the crop may lie outside it.
                still_covered=lambda points: crop_covers_points(attestation, points),
                job_id=job_id,
                lease_token=lease_token,
                deleted_at=now,
                unlink=unlink,
            )
        ]
        # A reconciled original was freed by an unlink whose state write was lost.
        return _Result(outcome, row.original_size_bytes if outcome == DELETED else 0)

    def _verify_crop(self, checksum: str, row: RegisteredCrop) -> SourceCropAttestation:
        crop_relative, attestation_relative = cropped_original_relative_paths(checksum)
        try:
            crop = self._data_root.joinpath(*crop_relative.parts).read_bytes()
            document = self._data_root.joinpath(*attestation_relative.parts).read_bytes()
        except OSError as error:
            raise _Refused(
                "SOURCE_CROP_FILES_MISSING", "The crop or its attestation cannot be read."
            ) from error
        if hashlib.sha256(document).hexdigest() != row.attestation_sha256:
            raise _Refused(
                "SOURCE_CROP_ATTESTATION_CHANGED", "The attestation differs from the registry."
            )
        try:
            frame = decode_cropped_source_bytes(
                crop, document, expected_source_checksum_sha256=checksum
            )
        except CanonicalSourceLoadError as error:
            raise _Refused(error.code, str(error)) from error
        assert frame.crop is not None
        if (
            rgb_pixel_checksum_sha256(frame.rgb)
            != frame.crop.attestation.canvas_pixel_checksum_sha256
        ):
            raise _Refused(
                "SOURCE_CROP_CANVAS_MISMATCH", "The rebuilt canvas differs from the attestation."
            )
        return frame.crop.attestation

    @staticmethod
    def _verify_original(path: Path, checksum: str, row: RegisteredCrop) -> None:
        """Refuse a changed original; an absent one is reconciled by the caller."""

        try:
            content = path.read_bytes()
        except FileNotFoundError:
            return
        except OSError as error:
            raise _Refused("ORIGINAL_UNREADABLE", "The managed original cannot be read.") from error
        if hashlib.sha256(content).hexdigest() != checksum or len(content) != (
            row.original_size_bytes
        ):
            raise _Refused(
                "ORIGINAL_CHANGED", "The managed original differs from its registry row."
            )


def _payload(job: Job) -> tuple[UUID, str]:
    payload = job.input_payload
    try:
        run_id = UUID(str(payload["source_crop_run_id"]))
        phase = str(payload["phase"])
    except (KeyError, ValueError) as error:
        raise JobHandlerError(
            "SOURCE_CROP_PAYLOAD_INVALID", "The deletion job payload is invalid."
        ) from error
    if phase not in ("plan", "execute") or payload.get("kind") != KIND:
        raise JobHandlerError("SOURCE_CROP_PAYLOAD_INVALID", "The deletion job payload is invalid.")
    return run_id, phase


__all__ = ["SourceDeletionCatalog", "SourceOriginalDeletionHandler"]
