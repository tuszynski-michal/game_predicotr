"""Durable, checkpointed deletion of immutable storage-GC manifests."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from uuid import UUID

from game_predictor_api.application.storage_gc import (
    StorageGcArtifactStore,
    _execution_key_from_path,
    _file_observation_checksum,
    _tree_observation,
)
from game_predictor_api.domain.jobs import Job
from game_predictor_api.domain.storage_retention import (
    StorageArtifactClass,
    StorageArtifactObservation,
    StorageRetentionPolicy,
    StorageRootKind,
    evaluate_storage_retention,
)
from game_predictor_api.storage.models import StorageGcRunModel
from game_predictor_api.storage.storage_gc_repository import SqlAlchemyStorageGcRepository
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from game_predictor_worker.jobs.runtime import JobExecutionContext, JobHandlerError

MAX_BATCH_PATHS = 250
MAX_BATCH_BYTES = 512 * 1024**2


class StorageGcHandler:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        artifact_root: Path,
        import_root: Path,
    ) -> None:
        self._session_factory = session_factory
        self._artifact_root = artifact_root.resolve()
        self._import_root = import_root.resolve()
        self._repository = SqlAlchemyStorageGcRepository(session_factory)
        self._scanner = StorageGcArtifactStore(self._artifact_root, self._import_root)

    def __call__(self, context: JobExecutionContext, job: Job) -> None:
        run_id = _run_id(job)
        manifest, entries = self._load_manifest(job, run_id)
        policy = _policy(manifest)
        counters = self._start_or_resume(run_id, context.now())
        index = counters["checkpointIndex"]
        _purge_deleted_markers(
            self._artifact_root,
            self._import_root,
            run_id,
            range(0, index),
        )
        if index >= len(entries):
            self._complete(run_id, context.now())
            return
        try:
            while index < len(entries):
                batch_start = index
                batch_end = _batch_end(entries, index)
                current = self._current_observations(
                    entries[index:batch_end], context.now()
                )
                for entry_index in range(index, batch_end):
                    entry = entries[entry_index]
                    outcome, size = self._process_entry(
                        run_id,
                        entry_index,
                        entry,
                        current=current,
                        policy=policy,
                        now=context.now(),
                    )
                    counters[outcome] = counters.get(outcome, 0) + 1
                    if outcome == "deletedCount":
                        counters["deletedBytes"] += size
                index = batch_end
                counters["checkpointIndex"] = index
                self._checkpoint(run_id, counters, context.now())
                context.checkpoint(
                    checkpoint_payload={
                        "schema_version": 1,
                        "storageGcRunId": str(run_id),
                        **counters,
                    },
                    stage="storage_gc_delete",
                    current=index,
                    total=len(entries),
                    success_count=counters["deletedCount"],
                    failure_count=counters["failedCount"],
                    review_count=counters["conflictCount"] + counters["protectedCount"],
                )
                _purge_deleted_markers(
                    self._artifact_root,
                    self._import_root,
                    run_id,
                    range(batch_start, batch_end),
                )
            self._complete(run_id, context.now())
        except BaseException as error:
            self._fail(run_id, error, context.now())
            raise

    def _load_manifest(
        self, job: Job, run_id: UUID
    ) -> tuple[Mapping[str, object], tuple[Mapping[str, object], ...]]:
        with self._session_factory() as session:
            row = session.get(StorageGcRunModel, run_id)
            if row is None or row.job_id != job.id:
                raise JobHandlerError(
                    "STORAGE_GC_RUN_NOT_FOUND", "The storage GC run does not match this job."
                )
            relative_path = row.manifest_relative_path
            expected_checksum = row.manifest_checksum_sha256
        path = _safe_root_path(self._artifact_root, relative_path)
        try:
            content = path.read_bytes()
        except OSError as error:
            raise JobHandlerError(
                "STORAGE_GC_SOURCE_CHANGED", "The immutable GC manifest is unavailable."
            ) from error
        if hashlib.sha256(content).hexdigest() != expected_checksum or (
            job.input_payload.get("manifest_checksum_sha256") != expected_checksum
        ):
            raise JobHandlerError(
                "STORAGE_GC_SOURCE_CHANGED", "The immutable GC manifest checksum changed."
            )
        try:
            payload = json.loads(content)
            raw_entries = payload["candidates"]
            if payload["schemaVersion"] != 1 or not isinstance(raw_entries, list):
                raise ValueError
            entries = tuple(item for item in raw_entries if isinstance(item, Mapping))
            if len(entries) != len(raw_entries):
                raise ValueError
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise JobHandlerError(
                "STORAGE_GC_SOURCE_CHANGED", "The immutable GC manifest is invalid."
            ) from error
        return payload, entries

    def _current_observations(
        self,
        entries: Sequence[Mapping[str, object]],
        now: datetime,
    ) -> dict[tuple[str, str], StorageArtifactObservation]:
        normalization_keys = tuple(
            _execution_key_from_path(Path(*PurePosixPath(str(entry["relativePath"])).parts))
            for entry in entries
            if entry.get("artifactClass") == "normalization_working_bitmap"
        )
        statuses = self._repository.normalization_dependency_statuses(
            tuple(key for key in normalization_keys if key is not None)
        )
        needs_staging = any(
            entry.get("artifactClass") == "browser_staging" for entry in entries
        )
        staging = (
            {str(item.upload_id): item for item in self._repository.browser_staging_sources()}
            if needs_staging
            else {}
        )
        observations: dict[tuple[str, str], StorageArtifactObservation] = {}
        for entry in entries:
            root_kind = StorageRootKind(str(entry["rootKind"]))
            relative_path = str(entry["relativePath"])
            root = (
                self._artifact_root
                if root_kind is StorageRootKind.ARTIFACT
                else self._import_root
            )
            path = _safe_root_path(root, relative_path)
            if not path.exists():
                continue
            artifact_class = StorageArtifactClass(str(entry["artifactClass"]))
            if artifact_class is StorageArtifactClass.BROWSER_STAGING:
                source = staging.get(PurePosixPath(relative_path).name)
                if source is None:
                    continue
                size, modified, fingerprint, symlink = _tree_observation(path)
                observation = StorageArtifactObservation(
                    relative_path=relative_path,
                    size_bytes=size,
                    modified_at=max(modified, source.finalized_at),
                    artifact_class=artifact_class,
                    dependency_job_statuses=source.dependency_job_statuses,
                    linked_import_exists=source.linked_import_exists,
                    managed_originals_verified=(
                        source.managed_originals_verified
                        and self._scanner.verify_managed_manifest(source)
                    ),
                    last_dependency_at=source.last_dependency_at,
                    is_symlink=symlink,
                    root_kind=root_kind,
                    observation_checksum_sha256=fingerprint,
                )
            else:
                stat = path.stat(follow_symlinks=False)
                key = _execution_key_from_path(path)
                observation = StorageArtifactObservation(
                    relative_path=relative_path,
                    size_bytes=stat.st_size,
                    modified_at=datetime.fromtimestamp(stat.st_mtime, UTC),
                    artifact_class=artifact_class,
                    dependency_job_statuses=(
                        ("processing",) if key is None else statuses.get(key, ())
                    ),
                    is_symlink=path.is_symlink(),
                    root_kind=root_kind,
                    observation_checksum_sha256=_file_observation_checksum(path, stat),
                )
            observations[(root_kind.value, relative_path)] = observation
        return observations

    def _process_entry(
        self,
        run_id: UUID,
        entry_index: int,
        entry: Mapping[str, object],
        *,
        current: Mapping[tuple[str, str], StorageArtifactObservation],
        policy: StorageRetentionPolicy,
        now: datetime,
    ) -> tuple[str, int]:
        root_kind = str(entry.get("rootKind"))
        relative_path = str(entry.get("relativePath"))
        if root_kind not in {"artifact", "import"}:
            raise JobHandlerError("STORAGE_GC_PATH_UNSAFE", "The GC root kind is invalid.")
        _validate_managed_candidate_path(
            root_kind=root_kind,
            artifact_class=str(entry.get("artifactClass")),
            relative_path=relative_path,
        )
        root = self._artifact_root if root_kind == "artifact" else self._import_root
        path = _safe_root_path(root, relative_path)
        trash = _trash_path(root, run_id, entry_index, relative_path)
        marker = _deleted_marker(trash)
        size = int(entry.get("sizeBytes", 0))
        if not path.exists() and (trash.exists() or marker.exists()):
            try:
                if trash.exists():
                    _write_deleted_marker(marker, size)
                    _delete_trash(trash)
            except OSError as error:
                raise JobHandlerError(
                    "STORAGE_GC_DELETE_FAILED",
                    "A quarantined GC candidate could not be finalized.",
                ) from error
            return "deletedCount", size
        if not path.exists():
            return "missingCount", 0
        observation = current.get((root_kind, relative_path))
        if observation is None:
            return "conflictCount", 0
        decision = evaluate_storage_retention(observation, policy=policy, now=now)
        expected_observation = entry.get("observationChecksumSha256")
        if (
            not decision.eligible
            or observation.size_bytes != size
            or observation.observation_checksum_sha256 != expected_observation
        ):
            return (
                "protectedCount" if not decision.eligible else "conflictCount",
                0,
            )
        try:
            trash.parent.mkdir(parents=True, exist_ok=True)
            os.replace(path, trash)
            _write_deleted_marker(marker, size)
            _delete_trash(trash)
            _remove_empty_parents(path.parent, stop=root)
        except OSError as error:
            raise JobHandlerError(
                "STORAGE_GC_DELETE_FAILED",
                "A GC candidate could not be moved and deleted safely.",
            ) from error
        return "deletedCount", size

    def _start_or_resume(self, run_id: UUID, now: datetime) -> dict[str, int]:
        with self._session_factory.begin() as session:
            row = session.execute(
                select(StorageGcRunModel)
                .where(StorageGcRunModel.id == run_id)
                .with_for_update()
            ).scalar_one()
            if row.status == "completed":
                return {
                    "checkpointIndex": row.candidate_count,
                    "deletedCount": row.deleted_count,
                    "deletedBytes": row.deleted_bytes,
                    "conflictCount": row.conflict_count,
                    "failedCount": row.failed_count,
                    "protectedCount": 0,
                    "missingCount": 0,
                }
            row.status = "processing"
            row.started_at = row.started_at or now
            row.updated_at = now
            return {
                "checkpointIndex": row.checkpoint_index,
                "deletedCount": row.deleted_count,
                "deletedBytes": row.deleted_bytes,
                "conflictCount": row.conflict_count,
                "failedCount": row.failed_count,
                "protectedCount": 0,
                "missingCount": 0,
            }

    def _checkpoint(self, run_id: UUID, counters: Mapping[str, int], now: datetime) -> None:
        with self._session_factory.begin() as session:
            row = session.get(StorageGcRunModel, run_id, with_for_update=True)
            if row is None:
                raise JobHandlerError("STORAGE_GC_RUN_NOT_FOUND", "The GC run disappeared.")
            row.checkpoint_index = counters["checkpointIndex"]
            row.deleted_count = counters["deletedCount"]
            row.deleted_bytes = counters["deletedBytes"]
            row.conflict_count = counters["conflictCount"] + counters["protectedCount"]
            row.failed_count = counters["failedCount"]
            row.updated_at = now

    def _complete(self, run_id: UUID, now: datetime) -> None:
        with self._session_factory.begin() as session:
            row = session.get(StorageGcRunModel, run_id, with_for_update=True)
            if row is None:
                return
            row.status = "completed"
            row.finished_at = now
            row.updated_at = now
            row.inventory_after = {"completedAt": now.isoformat()}

    def _fail(self, run_id: UUID, error: BaseException, now: datetime) -> None:
        with self._session_factory.begin() as session:
            row = session.get(StorageGcRunModel, run_id, with_for_update=True)
            if row is None:
                return
            row.status = "failed"
            row.failed_count += 1
            row.error_code = (
                error.code if isinstance(error, JobHandlerError) else "STORAGE_GC_FAILED"
            )
            row.error_message = str(error)[:4000]
            row.finished_at = now
            row.updated_at = now


def _run_id(job: Job) -> UUID:
    try:
        return UUID(str(job.input_payload["storage_gc_run_id"]))
    except (KeyError, ValueError) as error:
        raise JobHandlerError(
            "STORAGE_GC_PAYLOAD_INVALID", "The GC job payload is invalid."
        ) from error


def _policy(manifest: Mapping[str, object]) -> StorageRetentionPolicy:
    raw = manifest.get("policy")
    if not isinstance(raw, Mapping):
        raise JobHandlerError("STORAGE_GC_SOURCE_CHANGED", "The GC policy is invalid.")
    try:
        from datetime import timedelta

        return StorageRetentionPolicy(
            version=str(raw["version"]),
            retention=timedelta(seconds=int(raw["retentionSeconds"])),
            warning_free_bytes=int(raw["warningFreeBytes"]),
            automatic_gc_free_bytes=int(raw["automaticGcFreeBytes"]),
            target_free_bytes=int(raw["targetFreeBytes"]),
            hard_reserve_bytes=int(raw["hardReserveBytes"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise JobHandlerError("STORAGE_GC_SOURCE_CHANGED", "The GC policy is invalid.") from error


def _batch_end(entries: Sequence[Mapping[str, object]], start: int) -> int:
    total_bytes = 0
    end = start
    while end < len(entries) and end - start < MAX_BATCH_PATHS:
        size = max(0, int(entries[end].get("sizeBytes", 0)))
        if end > start and total_bytes + size > MAX_BATCH_BYTES:
            break
        total_bytes += size
        end += 1
    return end


def _safe_root_path(root: Path, relative_path: str) -> Path:
    relative = PurePosixPath(relative_path)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
        or "\\" in relative_path
    ):
        raise JobHandlerError("STORAGE_GC_PATH_UNSAFE", "The GC path is unsafe.")
    path = root.joinpath(*relative.parts)
    current = root
    for part in relative.parts:
        current /= part
        if current.exists() and current.is_symlink():
            raise JobHandlerError("STORAGE_GC_PATH_UNSAFE", "The GC path contains a symlink.")
    if not path.resolve().is_relative_to(root):
        raise JobHandlerError("STORAGE_GC_PATH_UNSAFE", "The GC path escapes its root.")
    return path


def _validate_managed_candidate_path(
    *, root_kind: str, artifact_class: str, relative_path: str
) -> None:
    path = PurePosixPath(relative_path)
    valid = False
    if artifact_class == "normalization_working_bitmap" and root_kind == "artifact":
        valid = (
            len(path.parts) == 6
            and path.parts[:3] == ("data", "working", "image-normalization-v1")
            and path.name == "normalized.png"
        )
    elif artifact_class == "temporary_file" and root_kind == "artifact":
        valid = (
            path.parts[:2] == ("data", "working")
            and (path.name.startswith(".tmp") or path.suffix.casefold() == ".part")
        )
    elif artifact_class == "browser_staging" and root_kind == "import":
        try:
            valid = len(path.parts) == 2 and path.parts[0] == "browser-selections"
            UUID(path.parts[1])
        except (ValueError, IndexError):
            valid = False
    if not valid:
        raise JobHandlerError(
            "STORAGE_GC_PATH_UNSAFE",
            "The GC candidate is outside an approved disposable namespace.",
        )


def _trash_path(root: Path, run_id: UUID, index: int, relative_path: str) -> Path:
    suffix = hashlib.sha256(relative_path.encode()).hexdigest()[:16]
    return root / ".storage-gc-trash" / str(run_id) / f"{index:012d}-{suffix}"


def _delete_trash(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def _deleted_marker(trash: Path) -> Path:
    return trash.with_name(f"{trash.name}.deleted")


def _write_deleted_marker(marker: Path, size_bytes: int) -> None:
    with marker.open("w", encoding="ascii") as target:
        target.write(str(size_bytes))
        target.flush()
        os.fsync(target.fileno())


def _purge_deleted_markers(
    artifact_root: Path,
    import_root: Path,
    run_id: UUID,
    indexes: range,
) -> None:
    prefixes = tuple(f"{index:012d}-" for index in indexes)
    for root in (artifact_root, import_root):
        trash_root = root / ".storage-gc-trash" / str(run_id)
        if not trash_root.is_dir() or trash_root.is_symlink():
            continue
        for marker in trash_root.glob("*.deleted"):
            if marker.name.startswith(prefixes):
                marker.unlink(missing_ok=True)
        _remove_empty_parents(trash_root, stop=root)


def _remove_empty_parents(path: Path, *, stop: Path) -> None:
    current = path
    while current != stop and current.is_relative_to(stop):
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


__all__ = ["MAX_BATCH_BYTES", "MAX_BATCH_PATHS", "StorageGcHandler"]
