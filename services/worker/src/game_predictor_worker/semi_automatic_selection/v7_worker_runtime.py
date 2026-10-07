"""Worker orchestration for the durable V7 scan, before output publication.

The V7 domain modules intentionally do not know about jobs or image files.  This
adapter owns the narrow worker boundary: it restores one pinned scan, verifies
the whole local folder before and after scanning, and persists only its durable
checkpoint.  A calibrated image observer is deliberately injected.  The
production default has no approved calibration and fails before any JPEG is
opened; a later release task must provide that measured observer explicitly.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from stat import S_ISDIR, S_ISREG
from time import monotonic
from typing import NoReturn, Protocol, cast

from .contracts import SemiAutomaticSelectionDirection, SemiAutomaticSelectionRange
from .local_source_manifest import (
    LocalSourceManifest,
    LocalSourceManifestError,
    build_local_source_manifest,
    resolve_local_source_asset,
)
from .v7_configuration import V7BorderStyle
from .v7_observation_codec import advance_observation_digest
from .v7_run_state import (
    V7PinnedSource,
    V7PinnedSourceManifest,
    V7RunFinalization,
    V7RunStateError,
    V7RunStatePhase,
    V7ScanObservation,
    V7ScanRunState,
)

V7_WORKER_RUNTIME_VERSION = "v7-worker-runtime-v2"
V7_WORKER_RUNTIME_CHECKPOINT_SCHEMA_VERSION = 2
_V7_LEGACY_WORKER_RUNTIME_VERSION = "v7-worker-runtime-v1"
_V7_LEGACY_WORKER_RUNTIME_CHECKPOINT_SCHEMA_VERSION = 1


class V7WorkerRuntimeError(ValueError):
    """A stable worker-facing failure which must not fall back to legacy V1–V6."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class V7WorkerConfiguration:
    """The server-owned subset needed by the V7 worker boundary."""

    first_sequence_number: int
    last_sequence_number: int
    direction: SemiAutomaticSelectionDirection
    border_style: V7BorderStyle
    localizer_fingerprint: str
    calibration_fingerprint: str
    pilot: dict[str, object] | None = None

    def __post_init__(self) -> None:
        if (
            self.first_sequence_number < 1
            or self.last_sequence_number < self.first_sequence_number
            or (self.last_sequence_number - self.first_sequence_number + 1) % 9
        ):
            _fail("V7_CONFIGURATION_INVALID", "V7 worker bounds must contain complete pages.")
        for fingerprint in (self.localizer_fingerprint, self.calibration_fingerprint):
            if len(fingerprint) != 64 or any(
                item not in "0123456789abcdef" for item in fingerprint
            ):
                _fail("V7_CONFIGURATION_INVALID", "V7 worker fingerprints must be SHA-256 values.")

    @property
    def expected_ranges(self) -> tuple[SemiAutomaticSelectionRange, ...]:
        ranges = tuple(
            SemiAutomaticSelectionRange(start=start, end=start + 8)
            for start in range(self.first_sequence_number, self.last_sequence_number + 1, 9)
        )
        if self.direction is SemiAutomaticSelectionDirection.ASCENDING:
            return ranges
        return tuple(reversed(ranges))


@dataclass(frozen=True, slots=True)
class V7SourceObservationRequest:
    """One checksum-verified asset available to a calibrated V7 observer."""

    source: V7PinnedSource
    source_content: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.source_content, bytes) or not self.source_content:
            _fail("V7_SCAN_OBSERVATION_INVALID", "The V7 source bytes are invalid.")


class V7SourceObserver(Protocol):
    """Maps one verified image to one complete, source-local V7 observation."""

    def observe(self, request: V7SourceObservationRequest) -> V7ScanObservation: ...


class V7SourceObserverFactory(Protocol):
    """Builds an observer only for an approved server-owned calibration."""

    def create(
        self,
        configuration: V7WorkerConfiguration,
        manifest: LocalSourceManifest,
    ) -> V7SourceObserver: ...


class UnavailableV7SourceObserverFactory:
    """Production-safe default until an approved calibration adapter exists."""

    def create(
        self,
        configuration: V7WorkerConfiguration,
        manifest: LocalSourceManifest,
    ) -> V7SourceObserver:
        del configuration, manifest
        _fail(
            "V7_CALIBRATION_UNAVAILABLE",
            "V7 has no approved server-owned calibration runtime.",
        )


@dataclass(frozen=True, slots=True)
class V7CheckpointPolicy:
    """Bound recomputation after process loss without changing observations."""

    max_sources: int = 16
    max_seconds: float = 2.0

    def __post_init__(self) -> None:
        if (
            type(self.max_sources) is not int
            or not 1 <= self.max_sources <= 16
            or not math.isfinite(self.max_seconds)
            or not 0 < self.max_seconds <= 2.0
        ):
            raise ValueError("V7 checkpoint bounds must be at most 16 sources or 2 seconds.")


@dataclass(frozen=True, slots=True)
class V7WorkerRuntimeProgress:
    checkpoint: dict[str, object]
    processed_sources: int
    total_sources: int
    phase: V7RunStatePhase
    blocked_source_drift: bool = False
    source_indexes: tuple[int, ...] | None = None
    pinned_manifest: V7PinnedSourceManifest | None = None
    observations: tuple[V7ScanObservation, ...] | None = None
    diagnostic_scan_state: dict[str, object] | None = None
    source_error_count: int | None = None


@dataclass(frozen=True, slots=True)
class V7WorkerRuntimeResult:
    checkpoint: dict[str, object]
    finalization: V7RunFinalization


V7CheckpointPersister = Callable[[V7WorkerRuntimeProgress], None]


class V7WorkerRuntime:
    """Runs a V7 source prefix in order and persists no output operation."""

    def __init__(
        self,
        observer_factory: V7SourceObserverFactory | None = None,
        *,
        checkpoint_policy: V7CheckpointPolicy | None = None,
        clock: Callable[[], float] = monotonic,
        independent_progress: bool = False,
    ) -> None:
        if independent_progress and checkpoint_policy is None:
            raise ValueError("Independent V7 progress requires a bounded checkpoint policy.")
        self._observer_factory = observer_factory or UnavailableV7SourceObserverFactory()
        self._checkpoint_policy = checkpoint_policy
        self._clock = clock
        self._independent_progress = independent_progress

    @property
    def independent_progress(self) -> bool:
        return self._independent_progress

    def run(
        self,
        *,
        manifest: LocalSourceManifest,
        configuration: V7WorkerConfiguration,
        checkpoint: Mapping[str, object],
        persist: V7CheckpointPersister,
        resume_reference: dict[str, object] | None = None,
    ) -> V7WorkerRuntimeResult:
        """Resume or finish a scan.  The factory runs before any source validation.

        This ordering keeps a direct V7 job with no approved calibration from
        hashing, decoding or otherwise opening a source JPEG.
        """

        if self._independent_progress and resume_reference is None:
            _fail("V7_RUN_STATE_CHECKPOINT_INVALID", "Independent V7 progress needs a resume base.")
        observer = self._observer_factory.create(configuration, manifest)
        state = V7ScanRunState(
            manifest,
            expected_ranges=configuration.expected_ranges,
            border_style=configuration.border_style,
            checkpoint=_scan_state_checkpoint(
                checkpoint,
                configuration,
                require_config_bound_checkpoint=(
                    getattr(observer, "requires_config_bound_checkpoint", False) is True
                ),
            ),
        )
        persisted_index = state.cursors.next_source_index
        persisted_time = self._clock()
        pending_observations: list[V7ScanObservation] = []
        current_resume_reference = resume_reference

        def flush(*, blocked_source_drift: bool = False) -> V7WorkerRuntimeProgress:
            nonlocal persisted_index, persisted_time, current_resume_reference
            progress = _progress(
                state,
                configuration,
                blocked_source_drift=blocked_source_drift,
                source_indexes=(
                    None
                    if self._checkpoint_policy is None
                    else tuple(range(persisted_index, state.cursors.next_source_index))
                ),
                resume_reference=current_resume_reference if self._independent_progress else None,
                observations=(tuple(pending_observations) if self._independent_progress else None),
            )
            persist(progress)
            if progress.checkpoint.get("runtimeVersion") == "v7-worker-runtime-v3":
                current_resume_reference = cast(
                    dict[str, object], progress.checkpoint["resumeBase"]
                )
            pending_observations.clear()
            persisted_index = state.cursors.next_source_index
            persisted_time = self._clock()
            return progress

        def persist_drift(error: V7WorkerRuntimeError) -> None:
            if error.code == "V7_SOURCE_MANIFEST_DRIFT":
                flush(blocked_source_drift=True)

        try:
            _require_manifest_unchanged(manifest)
        except V7WorkerRuntimeError as error:
            persist_drift(error)
            raise
        if state.phase is V7RunStatePhase.SCANNING:
            for source_index in range(state.cursors.next_source_index, len(manifest.sources)):
                pinned_source = state.source_manifest.sources[source_index]
                try:
                    source_path, source = resolve_local_source_asset(
                        manifest,
                        source_index=source_index,
                        expected_checksum_sha256=pinned_source.checksum_sha256,
                    )
                    source_content = _read_verified_source_bytes(
                        source_path,
                        expected_checksum_sha256=pinned_source.checksum_sha256,
                    )
                except LocalSourceManifestError as error:
                    try:
                        _raise_manifest_error(error, manifest=manifest, source_index=source_index)
                    except V7WorkerRuntimeError as runtime_error:
                        persist_drift(runtime_error)
                        raise
                except V7WorkerRuntimeError as error:
                    persist_drift(error)
                    raise
                if source != manifest.sources[source_index]:
                    _fail("V7_SOURCE_MANIFEST_DRIFT", "The V7 local source identity changed.")
                observation = observer.observe(
                    V7SourceObservationRequest(
                        source=pinned_source,
                        source_content=source_content,
                    )
                )
                if observation.source_index != source_index:
                    _fail(
                        "V7_SCAN_OBSERVATION_INVALID",
                        "The V7 observer returned another source index.",
                    )
                try:
                    state.consume(observation)
                except V7RunStateError as error:
                    raise V7WorkerRuntimeError(error.code, str(error)) from error
                if self._independent_progress:
                    pending_observations.append(observation)
                policy = self._checkpoint_policy
                if (
                    policy is None
                    or state.cursors.next_source_index - persisted_index >= policy.max_sources
                    or self._clock() - persisted_time >= policy.max_seconds
                ):
                    flush()
            try:
                state.complete_scan()
            except V7RunStateError as error:
                raise V7WorkerRuntimeError(error.code, str(error)) from error
            flush()
        if state.phase is V7RunStatePhase.FINALIZATION_PENDING:
            try:
                current_manifest = _require_manifest_unchanged(manifest)
            except V7WorkerRuntimeError as error:
                persist_drift(error)
                raise
            try:
                finalization = state.finalize(current_manifest)
            except V7RunStateError as error:
                persist_drift(V7WorkerRuntimeError(error.code, str(error)))
                raise V7WorkerRuntimeError(error.code, str(error)) from error
            progress = flush()
            return V7WorkerRuntimeResult(
                checkpoint=progress.checkpoint,
                finalization=finalization,
            )
        if state.phase is V7RunStatePhase.FINALIZED:
            try:
                current_manifest = _require_manifest_unchanged(manifest)
            except V7WorkerRuntimeError as error:
                persist_drift(error)
                raise
            try:
                finalization = state.finalize(current_manifest)
            except V7RunStateError as error:
                persist_drift(V7WorkerRuntimeError(error.code, str(error)))
                raise V7WorkerRuntimeError(error.code, str(error)) from error
            return V7WorkerRuntimeResult(
                checkpoint=_runtime_checkpoint(state, configuration),
                finalization=finalization,
            )
        _fail("V7_RUN_STATE_PHASE_INVALID", "The V7 worker cannot run this scan state.")


def _scan_state_checkpoint(
    checkpoint: Mapping[str, object],
    configuration: V7WorkerConfiguration,
    *,
    require_config_bound_checkpoint: bool,
) -> dict[str, object] | None:
    if not checkpoint:
        return None
    if checkpoint.get("blockedReason") == "V7_SOURCE_MANIFEST_DRIFT":
        _fail("V7_SOURCE_MANIFEST_DRIFT", "The V7 run is durably blocked by source drift.")
    version = checkpoint.get("runtimeVersion")
    schema_version = checkpoint.get("schemaVersion")
    contract = (version, schema_version)
    if contract not in {
        (V7_WORKER_RUNTIME_VERSION, V7_WORKER_RUNTIME_CHECKPOINT_SCHEMA_VERSION),
        (
            _V7_LEGACY_WORKER_RUNTIME_VERSION,
            _V7_LEGACY_WORKER_RUNTIME_CHECKPOINT_SCHEMA_VERSION,
        ),
    } or not isinstance(checkpoint.get("scanState"), dict):
        _fail("V7_RUN_STATE_CHECKPOINT_INVALID", "The V7 worker checkpoint is invalid.")
    if contract == (V7_WORKER_RUNTIME_VERSION, V7_WORKER_RUNTIME_CHECKPOINT_SCHEMA_VERSION):
        if (
            checkpoint.get("calibrationFingerprint") != configuration.calibration_fingerprint
            or checkpoint.get("localizerFingerprint") != configuration.localizer_fingerprint
            or (
                configuration.pilot is not None
                and checkpoint.get("pilotSnapshot") != configuration.pilot
            )
        ):
            _fail(
                "V7_CALIBRATION_FINGERPRINT_MISMATCH",
                "The V7 worker checkpoint belongs to another calibration profile.",
            )
    elif require_config_bound_checkpoint:
        _fail(
            "V7_CALIBRATION_FINGERPRINT_MISMATCH",
            "A profile-bound V7 observer cannot resume an unbound legacy checkpoint.",
        )
    return dict(cast(dict[str, object], checkpoint["scanState"]))


def _runtime_checkpoint(
    state: V7ScanRunState,
    configuration: V7WorkerConfiguration,
    *,
    blocked_source_drift: bool = False,
) -> dict[str, object]:
    checkpoint: dict[str, object] = {
        "calibrationFingerprint": configuration.calibration_fingerprint,
        "localizerFingerprint": configuration.localizer_fingerprint,
        "runtimeVersion": V7_WORKER_RUNTIME_VERSION,
        "scanState": state.checkpoint(),
        "schemaVersion": V7_WORKER_RUNTIME_CHECKPOINT_SCHEMA_VERSION,
    }
    if configuration.pilot is not None:
        checkpoint["pilotSnapshot"] = dict(configuration.pilot)
    if blocked_source_drift:
        checkpoint["blockedReason"] = "V7_SOURCE_MANIFEST_DRIFT"
    return checkpoint


def _progress(
    state: V7ScanRunState,
    configuration: V7WorkerConfiguration,
    *,
    blocked_source_drift: bool = False,
    source_indexes: tuple[int, ...] | None = None,
    resume_reference: dict[str, object] | None = None,
    observations: tuple[V7ScanObservation, ...] | None = None,
) -> V7WorkerRuntimeProgress:
    if resume_reference is not None and state.phase is not V7RunStatePhase.FINALIZED:
        reference = dict(resume_reference)
        digest = reference.get("observationsDigest")
        if not isinstance(digest, str):
            _fail("V7_RUN_STATE_CHECKPOINT_INVALID", "The resume base has no observation digest.")
        for observation in observations or ():
            digest = advance_observation_digest(digest, observation)
        reference["observationsDigest"] = digest
        checkpoint: dict[str, object] = {
            "runtimeVersion": "v7-worker-runtime-v3",
            "schemaVersion": 3,
            "resumeBase": reference,
            "calibrationFingerprint": configuration.calibration_fingerprint,
            "localizerFingerprint": configuration.localizer_fingerprint,
            "processedSources": state.cursors.next_source_index,
            "scanState": {
                "phase": state.phase.value,
                "sourceManifest": state.source_manifest.as_header_dict(),
                "tracker": {"cursors": state.cursors.as_dict()},
            },
        }
        if configuration.pilot is not None:
            checkpoint["pilotSnapshot"] = dict(configuration.pilot)
        if blocked_source_drift:
            checkpoint["blockedReason"] = "V7_SOURCE_MANIFEST_DRIFT"
    else:
        checkpoint = _runtime_checkpoint(
            state, configuration, blocked_source_drift=blocked_source_drift
        )
    return V7WorkerRuntimeProgress(
        checkpoint=checkpoint,
        processed_sources=state.cursors.next_source_index,
        total_sources=len(state.source_manifest.sources),
        phase=state.phase,
        blocked_source_drift=blocked_source_drift,
        source_indexes=source_indexes,
        pinned_manifest=None if source_indexes is None else state.source_manifest,
        observations=observations,
        source_error_count=state.source_error_count,
        diagnostic_scan_state=(
            None if resume_reference is None else state.diagnostic_checkpoint(source_indexes or ())
        ),
    )


def _read_verified_source_bytes(path: Path, *, expected_checksum_sha256: str) -> bytes:
    try:
        content = path.read_bytes()
    except OSError as error:
        raise V7WorkerRuntimeError(
            "SEMI_AUTOMATIC_SELECTION_SOURCE_UNAVAILABLE",
            "The local source JPEG is unavailable.",
        ) from error
    if hashlib.sha256(content).hexdigest() != expected_checksum_sha256:
        _fail("V7_SOURCE_MANIFEST_DRIFT", "The pinned V7 source JPEG changed.")
    return content


def _require_manifest_unchanged(manifest: LocalSourceManifest) -> LocalSourceManifest:
    """Rebuild identity so added, removed and unselected changed JPEGs all block V7."""

    try:
        current = build_local_source_manifest(
            manifest.source_root,
            selection_id=manifest.selection_id,
            display_name=manifest.display_name,
        )
    except LocalSourceManifestError as error:
        _raise_manifest_error(error, manifest=manifest)
    if current.content != manifest.content:
        _fail("V7_SOURCE_MANIFEST_DRIFT", "The pinned V7 source folder changed.")
    return current


def _raise_manifest_error(
    error: LocalSourceManifestError,
    *,
    manifest: LocalSourceManifest,
    source_index: int | None = None,
) -> NoReturn:
    if error.code in {
        "SEMI_AUTOMATIC_SELECTION_SOURCE_CHANGED",
        "SEMI_AUTOMATIC_SELECTION_SOURCE_EMPTY",
    } or (
        error.code == "SEMI_AUTOMATIC_SELECTION_SOURCE_UNAVAILABLE"
        and _has_missing_or_empty_pinned_source(manifest, source_index=source_index)
    ):
        _fail("V7_SOURCE_MANIFEST_DRIFT", "The pinned V7 source folder changed.")
    raise V7WorkerRuntimeError(error.code, str(error)) from error


def _has_missing_or_empty_pinned_source(
    manifest: LocalSourceManifest,
    *,
    source_index: int | None,
) -> bool:
    """Treat only observable deletion/empty content as permanent input drift.

    A disconnected root or an unreadable non-empty JPEG remains an unavailable
    source rather than a claimed change of identity.  The next retry can then
    retry it safely, while a restored deleted file cannot revive a blocked run.
    """

    try:
        root_metadata = manifest.source_root.stat()
    except OSError:
        return False
    if not S_ISDIR(root_metadata.st_mode):
        return False
    sources = manifest.sources if source_index is None else (manifest.sources[source_index],)
    for source in sources:
        try:
            path = manifest.source_root.joinpath(*source.relative_path.split("/"))
            metadata = path.stat()
        except FileNotFoundError:
            return True
        except OSError:
            return False
        if not S_ISREG(metadata.st_mode) or metadata.st_size < 1:
            return True
    return False


def _fail(code: str, message: str) -> NoReturn:
    raise V7WorkerRuntimeError(code, message)


__all__ = [
    "V7CheckpointPolicy",
    "UnavailableV7SourceObserverFactory",
    "V7SourceObservationRequest",
    "V7SourceObserver",
    "V7SourceObserverFactory",
    "V7WorkerConfiguration",
    "V7WorkerRuntime",
    "V7WorkerRuntimeError",
    "V7WorkerRuntimeProgress",
    "V7WorkerRuntimeResult",
    "V7_WORKER_RUNTIME_CHECKPOINT_SCHEMA_VERSION",
    "V7_WORKER_RUNTIME_VERSION",
]
