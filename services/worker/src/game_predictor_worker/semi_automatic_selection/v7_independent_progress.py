"""Recover independent SQL observations from one immutable v2 resume base.

The base is adopted once, not rewritten as the scan grows. New observations
already have their own SQL identities. Only the small reference is updated in
the run; neither source JPEGs nor reviewed output operations belong here.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from game_predictor_api.domain.v7_selection_delivery import payload_fingerprint
from game_predictor_api.storage.models import V7SourceObservationModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from game_predictor_worker.filesystem import long_path_aware
from game_predictor_worker.jobs.runtime import JobHandlerError

from .local_source_manifest import LocalSourceManifest
from .v7_observation_codec import advance_observation_digest, deserialize_scan_observation
from .v7_run_state import V7ScanRunState
from .v7_worker_runtime import (
    V7WorkerConfiguration,
    _runtime_checkpoint,
    _scan_state_checkpoint,
)

INDEPENDENT_PROGRESS_VERSION = "v7-worker-runtime-v3"
_BASE_VERSION = "v7-independent-resume-base-v1"


@dataclass(frozen=True, slots=True)
class V7PreparedIndependentProgress:
    checkpoint: dict[str, object]
    resume_reference: dict[str, object]


def prepare_independent_progress(
    session: Session,
    *,
    artifact_root: Path,
    run_id: UUID,
    checkpoint: dict[str, object],
    configuration: V7WorkerConfiguration,
    manifest: LocalSourceManifest,
) -> V7PreparedIndependentProgress:
    """Adopt v2 once or recover v3 once; never called from a progress flush."""

    if checkpoint.get("runtimeVersion") == INDEPENDENT_PROGRESS_VERSION:
        return _recover(session, artifact_root, run_id, checkpoint, configuration, manifest)
    scan = _scan_state_checkpoint(
        checkpoint, configuration, require_config_bound_checkpoint=bool(configuration.pilot)
    )
    state = V7ScanRunState(
        manifest,
        expected_ranges=configuration.expected_ranges,
        border_style=configuration.border_style,
        checkpoint=scan,
    )
    base = {
        "version": _BASE_VERSION,
        "runId": str(run_id),
        "manifestChecksumSha256": manifest.checksum_sha256,
        "sourceFingerprint": manifest.source_fingerprint,
        "checkpoint": checkpoint,
    }
    content = json.dumps(base, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    checksum = hashlib.sha256(content).hexdigest()
    path = _base_path(artifact_root, run_id, checksum)
    _publish_base(path, content)
    reference: dict[str, object] = {
        "version": _BASE_VERSION,
        "relativePath": path.relative_to(artifact_root.resolve()).as_posix(),
        "checksumSha256": checksum,
        "processedSources": state.cursors.next_source_index,
        "observationsDigest": checksum,
    }
    return V7PreparedIndependentProgress(checkpoint, reference)


def _recover(
    session: Session,
    artifact_root: Path,
    run_id: UUID,
    checkpoint: dict[str, object],
    configuration: V7WorkerConfiguration,
    manifest: LocalSourceManifest,
) -> V7PreparedIndependentProgress:
    if checkpoint.get("blockedReason") == "V7_SOURCE_MANIFEST_DRIFT":
        _fail("V7_SOURCE_MANIFEST_DRIFT", "The scan is durably blocked by source drift.")
    try:
        reference = checkpoint["resumeBase"]
        if not isinstance(reference, dict) or reference.get("version") != _BASE_VERSION:
            raise ValueError("Invalid resume base reference.")
        checksum = reference["checksumSha256"]
        if not isinstance(checksum, str):
            raise ValueError("Invalid resume base checksum.")
        path = _base_path(artifact_root, run_id, checksum)
        if reference["relativePath"] != path.relative_to(artifact_root.resolve()).as_posix():
            raise ValueError("Resume base escaped its run scope.")
        base_index = _index(reference["processedSources"])
        scan = checkpoint["scanState"]
        if not isinstance(scan, dict):
            raise ValueError("Invalid independent scan control.")
        control = scan["tracker"]
        if not isinstance(control, dict) or not isinstance(control.get("cursors"), dict):
            raise ValueError("Invalid independent scan cursor.")
        target_index = _index(control["cursors"]["nextSourceIndex"])
        if not base_index <= target_index <= len(manifest.sources):
            raise ValueError("Invalid independent prefix bounds.")
        if (
            checkpoint.get("schemaVersion") != 3
            or checkpoint.get("processedSources") != target_index
            or checkpoint.get("calibrationFingerprint") != configuration.calibration_fingerprint
            or checkpoint.get("localizerFingerprint") != configuration.localizer_fingerprint
            or checkpoint.get("pilotSnapshot") != configuration.pilot
            or scan.get("phase") not in {"scanning", "finalization_pending"}
        ):
            raise ValueError("Independent progress configuration changed.")
        content = long_path_aware(path).read_bytes()
        if hashlib.sha256(content).hexdigest() != checksum:
            raise ValueError("The immutable resume base changed.")
        base = json.loads(content)
        if (
            not isinstance(base, dict)
            or base.get("version") != _BASE_VERSION
            or base.get("runId") != str(run_id)
            or base.get("manifestChecksumSha256") != manifest.checksum_sha256
            or base.get("sourceFingerprint") != manifest.source_fingerprint
            or not isinstance(base.get("checkpoint"), dict)
        ):
            raise ValueError("The resume base belongs to a different scan.")
        base_scan = _scan_state_checkpoint(
            base["checkpoint"],
            configuration,
            require_config_bound_checkpoint=bool(configuration.pilot),
        )
        state = V7ScanRunState(
            manifest,
            expected_ranges=configuration.expected_ranges,
            border_style=configuration.border_style,
            checkpoint=base_scan,
        )
        if state.cursors.next_source_index != base_index:
            raise ValueError("Resume base cursor changed.")
        header = scan.get("sourceManifest")
        pinned = state.source_manifest
        expected_header = {
            "selectionId": str(pinned.selection_id),
            "sourceRoot": str(pinned.source_root),
            "manifestChecksumSha256": pinned.manifest_checksum_sha256,
            "sourceFingerprint": pinned.source_fingerprint,
        }
        if header != expected_header:
            raise ValueError("Independent manifest reference changed.")
        rows = session.scalars(
            select(V7SourceObservationModel)
            .where(
                V7SourceObservationModel.run_id == run_id,
                V7SourceObservationModel.source_index >= base_index,
            )
            .order_by(V7SourceObservationModel.source_index)
            .execution_options(yield_per=64)
        )
        observations_digest = checksum
        for row in rows:
            if (
                row.source_index != state.cursors.next_source_index
                or row.source_index >= target_index
            ):
                _fail("V7_SOURCE_OBSERVATION_CHANGED", "The independent prefix changed.")
            source = pinned.sources[row.source_index]
            if (
                row.source_checksum_sha256 != source.checksum_sha256
                or row.payload.get("sourceChecksumSha256") != source.checksum_sha256
                or row.payload.get("sourceId") != source.source_id
                or row.payload.get("sourceIndex") != row.source_index
                or row.payload_fingerprint != payload_fingerprint(row.payload)
            ):
                _fail("V7_SOURCE_OBSERVATION_CHANGED", "An independent source record changed.")
            observation = deserialize_scan_observation(row.payload.get("resumeObservation"))
            if observation.source_index != row.source_index:
                _fail("V7_SOURCE_OBSERVATION_CHANGED", "A recovery observation changed identity.")
            state.consume(observation)
            observations_digest = advance_observation_digest(observations_digest, observation)
        if state.cursors.next_source_index != target_index:
            _fail("V7_SOURCE_OBSERVATION_CHANGED", "The independent prefix is incomplete.")
        if reference.get("observationsDigest") != observations_digest:
            _fail("V7_SOURCE_OBSERVATION_CHANGED", "The independent observation digest changed.")
        if scan["phase"] == "finalization_pending":
            state.complete_scan()
        if state.cursors.as_dict() != control["cursors"]:
            raise ValueError("Independent sequence/view cursor changed.")
        return V7PreparedIndependentProgress(
            _runtime_checkpoint(state, configuration), dict(reference)
        )
    except JobHandlerError:
        raise
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise JobHandlerError(
            "V7_RUN_STATE_CHECKPOINT_INVALID", "Independent V7 recovery failed validation."
        ) from error


def _base_path(artifact_root: Path, run_id: UUID, checksum: str) -> Path:
    if len(checksum) != 64 or any(value not in "0123456789abcdef" for value in checksum):
        _fail("V7_RUN_STATE_CHECKPOINT_INVALID", "Invalid independent base checksum.")
    root = artifact_root.resolve()
    parts = (
        "exports",
        "semi-automatic-selection",
        str(run_id),
        "v7-resume-base",
        f"{checksum}.json",
    )
    path = root
    for part in parts:
        path = path / part
        if path.is_symlink():
            _fail("V7_RUN_STATE_CHECKPOINT_INVALID", "A resume base path is a symbolic link.")
    if root not in path.resolve().parents:
        _fail("V7_RUN_STATE_CHECKPOINT_INVALID", "A resume base escaped the artifact root.")
    return path


def _publish_base(path: Path, content: bytes) -> None:
    filesystem_path = long_path_aware(path)
    temporary_path: Path | None = None
    try:
        filesystem_path.parent.mkdir(parents=True, exist_ok=True)
        if filesystem_path.exists():
            if filesystem_path.read_bytes() != content:
                _fail("V7_RUN_STATE_CHECKPOINT_INVALID", "An immutable resume base changed.")
            return
        with tempfile.NamedTemporaryFile(
            dir=filesystem_path.parent, prefix=".v7-base-", delete=False
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary_path, filesystem_path)
        except FileExistsError:
            if filesystem_path.read_bytes() != content:
                _fail("V7_RUN_STATE_CHECKPOINT_INVALID", "An immutable resume base changed.")
    except OSError as error:
        raise JobHandlerError(
            "V7_RESUME_BASE_WRITE_FAILED", "The resume base could not be saved."
        ) from error
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _index(value: object) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("Invalid independent cursor.")
    return value


def _fail(code: str, message: str) -> None:
    raise JobHandlerError(code, message)
