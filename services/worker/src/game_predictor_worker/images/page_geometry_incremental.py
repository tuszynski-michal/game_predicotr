"""Incremental reuse and durable shards for page-geometry preflight."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import cast

from game_predictor_worker.jobs.runtime import JobHandlerError

from .source_ingestion import ManagedOriginal

PAGE_GEOMETRY_REUSE_CONTRACT_VERSION = "page-geometry-entry-reuse-v1"
PAGE_GEOMETRY_CHECKPOINT_SCHEMA_VERSION = 1
EXACT_POLICY_COMPATIBILITY = "exact_policy"
REPLACEMENT_LINEAGE_COMPATIBILITY = "replacement_lineage_exact_policy"
LATERAL_V2_TO_V3_COMPATIBILITY = "lateral_v2_to_v3"
LATERAL_V3_TO_V2_COMPATIBILITY = "lateral_v3_to_v2"
BASELINE_TO_SELECTIVE_COMPATIBILITY = "baseline_to_selective_v1_1"
_COMPATIBILITY_MODES = frozenset(
    {
        EXACT_POLICY_COMPATIBILITY,
        REPLACEMENT_LINEAGE_COMPATIBILITY,
        LATERAL_V2_TO_V3_COMPATIBILITY,
        LATERAL_V3_TO_V2_COMPATIBILITY,
        BASELINE_TO_SELECTIVE_COMPATIBILITY,
    }
)
_LATERAL_V2_SCHEMA = "lateral-partial-geometry-snapshot-v2"
_LATERAL_V3_SCHEMA = "lateral-partial-geometry-snapshot-v3"
_LATERAL_V1_SCHEMA = "lateral-partial-geometry-snapshot-v1"
_SELECTIVE_SCHEMA = "selective-frame-geometry-snapshot-v1"
_CHECKPOINT_ERROR = "IMAGE_PAGE_GEOMETRY_CHECKPOINT_INVALID"
_BASE_MANIFEST_ERROR = "IMAGE_PAGE_GEOMETRY_BASE_MANIFEST_INVALID"


@dataclass(frozen=True, slots=True)
class BasePageGeometryManifestDescriptor:
    job_id: str
    manifest_checksum_sha256: str
    source_manifest_checksum_sha256: str
    compatibility_mode: str
    base_source_selection_id: str | None = None
    base_override_fingerprints: dict[str, str] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        return {
            "contractVersion": PAGE_GEOMETRY_REUSE_CONTRACT_VERSION,
            "jobId": self.job_id,
            "manifestChecksumSha256": self.manifest_checksum_sha256,
            "sourceManifestChecksumSha256": self.source_manifest_checksum_sha256,
            "compatibilityMode": self.compatibility_mode,
            **(
                {"baseSourceSelectionId": self.base_source_selection_id}
                if self.base_source_selection_id is not None
                else {}
            ),
            **(
                {"baseOverrideFingerprints": self.base_override_fingerprints}
                if self.base_override_fingerprints
                else {}
            ),
        }


@dataclass(frozen=True, slots=True)
class PageGeometryReusePlan:
    entries: dict[str, object]
    recompute_originals: tuple[ManagedOriginal, ...]

    @property
    def reused_source_count(self) -> int:
        return len(self.entries)

    @property
    def recomputed_source_count(self) -> int:
        return len(self.recompute_originals)


@dataclass(frozen=True, slots=True)
class LoadedPageGeometryCheckpoint:
    entries: dict[str, object]
    metadata: dict[str, object]
    state_checksum_sha256: str
    state_relative_path: str


def parse_base_manifest_descriptor(value: object) -> BasePageGeometryManifestDescriptor:
    required = {
        "contractVersion",
        "jobId",
        "manifestChecksumSha256",
        "sourceManifestChecksumSha256",
        "compatibilityMode",
    }
    if (
        not isinstance(value, Mapping)
        or not required.issubset(value)
        or not set(value).issubset(required | {"baseOverrideFingerprints", "baseSourceSelectionId"})
    ):
        raise JobHandlerError(
            _BASE_MANIFEST_ERROR,
            "The pinned base page-geometry manifest descriptor is invalid.",
        )
    job_id = value.get("jobId")
    manifest_checksum = value.get("manifestChecksumSha256")
    source_checksum = value.get("sourceManifestChecksumSha256")
    compatibility_mode = value.get("compatibilityMode")
    base_source_selection_id = value.get("baseSourceSelectionId")
    raw_fingerprints = value.get("baseOverrideFingerprints", {})
    if (
        value.get("contractVersion") != PAGE_GEOMETRY_REUSE_CONTRACT_VERSION
        or not isinstance(job_id, str)
        or not _is_uuid(job_id)
        or not _is_sha256(manifest_checksum)
        or not _is_sha256(source_checksum)
        or compatibility_mode not in _COMPATIBILITY_MODES
        or (
            compatibility_mode == REPLACEMENT_LINEAGE_COMPATIBILITY
            and (
                not isinstance(base_source_selection_id, str)
                or not _is_uuid(base_source_selection_id)
            )
        )
        or (
            compatibility_mode != REPLACEMENT_LINEAGE_COMPATIBILITY
            and base_source_selection_id is not None
        )
        or not isinstance(raw_fingerprints, Mapping)
        or any(
            not _is_sha256(checksum) or not _is_sha256(fingerprint)
            for checksum, fingerprint in raw_fingerprints.items()
        )
    ):
        raise JobHandlerError(
            _BASE_MANIFEST_ERROR,
            "The pinned base page-geometry manifest descriptor is invalid.",
        )
    return BasePageGeometryManifestDescriptor(
        job_id=job_id,
        manifest_checksum_sha256=cast(str, manifest_checksum),
        source_manifest_checksum_sha256=cast(str, source_checksum),
        compatibility_mode=cast(str, compatibility_mode),
        base_source_selection_id=cast(str | None, base_source_selection_id),
        base_override_fingerprints=dict(sorted(raw_fingerprints.items())),
    )


def load_base_manifest(
    artifact_root: Path,
    descriptor: BasePageGeometryManifestDescriptor,
    *,
    game_id: str,
    source_selection_id: str,
    source_manifest_checksum_sha256: str,
    preflight_policy_version: str,
    page_registration_profile: Mapping[str, object],
    lateral_partial_geometry: object,
) -> Mapping[str, object]:
    path = (
        artifact_root
        / "data"
        / "page-geometry-manifests"
        / f"{descriptor.manifest_checksum_sha256}.json"
    )
    try:
        content = path.read_bytes()
    except OSError as error:
        raise JobHandlerError(
            _BASE_MANIFEST_ERROR,
            "The pinned base page-geometry manifest is unavailable.",
        ) from error
    if hashlib.sha256(content).hexdigest() != descriptor.manifest_checksum_sha256:
        raise JobHandlerError(
            _BASE_MANIFEST_ERROR,
            "The pinned base page-geometry manifest checksum changed.",
        )
    try:
        manifest = json.loads(content)
    except json.JSONDecodeError as error:
        raise JobHandlerError(
            _BASE_MANIFEST_ERROR,
            "The pinned base page-geometry manifest is not valid JSON.",
        ) from error
    if (
        not isinstance(manifest, Mapping)
        or manifest.get("gameId") != game_id
        or manifest.get("sourceSelectionId")
        != (
            descriptor.base_source_selection_id
            if descriptor.compatibility_mode == REPLACEMENT_LINEAGE_COMPATIBILITY
            else source_selection_id
        )
        or manifest.get("sourceManifestChecksumSha256")
        != descriptor.source_manifest_checksum_sha256
        or (
            descriptor.compatibility_mode != REPLACEMENT_LINEAGE_COMPATIBILITY
            and descriptor.source_manifest_checksum_sha256 != source_manifest_checksum_sha256
        )
        or manifest.get("version") != preflight_policy_version
        or manifest.get("pageRegistrationProfile") != page_registration_profile
        or not isinstance(manifest.get("entries"), Mapping)
    ):
        raise JobHandlerError(
            _BASE_MANIFEST_ERROR,
            "The pinned base page-geometry manifest does not match this preflight.",
        )
    base_lateral = manifest.get("lateralPartialGeometry")
    if descriptor.compatibility_mode in {
        EXACT_POLICY_COMPATIBILITY,
        REPLACEMENT_LINEAGE_COMPATIBILITY,
    }:
        compatible = base_lateral == lateral_partial_geometry
    elif descriptor.compatibility_mode == LATERAL_V2_TO_V3_COMPATIBILITY:
        compatible = _lateral_v2_to_v3_compatible(base_lateral, lateral_partial_geometry)
    elif descriptor.compatibility_mode == LATERAL_V3_TO_V2_COMPATIBILITY:
        compatible = _lateral_v2_to_v3_compatible(lateral_partial_geometry, base_lateral)
    else:
        compatible = _baseline_to_selective_compatible(base_lateral, lateral_partial_geometry)
    if not compatible:
        raise JobHandlerError(
            _BASE_MANIFEST_ERROR,
            "The pinned base page-geometry policy is not compatible with this preflight.",
        )
    return manifest


def plan_manifest_reuse(
    originals: Sequence[ManagedOriginal],
    *,
    payload: Mapping[str, object],
    base_manifest: Mapping[str, object] | None,
    compatibility_mode: str | None,
    base_override_fingerprints: Mapping[str, str] | None = None,
) -> PageGeometryReusePlan:
    if base_manifest is None:
        return PageGeometryReusePlan({}, tuple(originals))
    raw_entries = base_manifest.get("entries")
    if not isinstance(raw_entries, Mapping):
        raise JobHandlerError(
            _BASE_MANIFEST_ERROR,
            "The pinned base page-geometry manifest has no entry map.",
        )
    raw_overrides = payload.get("pageGeometryOverrides")
    overrides = raw_overrides if isinstance(raw_overrides, Mapping) else {}
    base_fingerprints = base_override_fingerprints or {}
    changed_override_checksums: set[str] = set()
    for checksum, value in raw_entries.items():
        if not isinstance(checksum, str) or not isinstance(value, Mapping):
            continue
        if _is_manual_entry(value) and not _manual_entry_matches_override(
            value, overrides.get(checksum)
        ):
            changed_override_checksums.add(checksum)
    for checksum in set(base_fingerprints) | set(overrides):
        if base_fingerprints.get(checksum) != _override_fingerprint(overrides.get(checksum)):
            changed_override_checksums.add(checksum)
    invalidated_anchors = set(changed_override_checksums)
    if compatibility_mode == REPLACEMENT_LINEAGE_COMPATIBILITY:
        current_checksums = {original.checksum_sha256 for original in originals}
        invalidated_anchors.update(set(raw_entries) - current_checksums)

    stable_external_anchors = {
        checksum
        for checksum, fingerprint in base_fingerprints.items()
        if fingerprint == _override_fingerprint(overrides.get(checksum))
    }
    profile = payload.get("pageRegistrationProfile")
    profile_anchors = profile.get("anchors") if isinstance(profile, Mapping) else None
    fixed_anchors = (
        {
            anchor.get("sourceChecksumSha256")
            for anchor in profile_anchors
            if isinstance(anchor, Mapping) and _is_sha256(anchor.get("sourceChecksumSha256"))
        }
        if isinstance(profile_anchors, list)
        else set()
    )

    reused: dict[str, object] = {}
    recompute: list[ManagedOriginal] = []
    threshold, maximum_review_slots = _frame_review_thresholds(payload)
    for original in originals:
        checksum = original.checksum_sha256
        raw_entry = raw_entries.get(checksum)
        if not isinstance(raw_entry, Mapping):
            recompute.append(original)
            continue
        entry = dict(raw_entry)
        if entry.get("sourceRelativePath") != original.source_relative_path:
            recompute.append(original)
            continue
        status = entry.get("status")
        if status == "skipped_human_resolved":
            if _fully_canonical(original, payload):
                reused[checksum] = entry
            else:
                recompute.append(original)
            continue
        current_override = overrides.get(checksum)
        if _is_manual_entry(entry):
            if _manual_entry_matches_override(entry, current_override):
                reused[checksum] = entry
            else:
                recompute.append(original)
            continue
        if isinstance(current_override, Mapping) or status != "registered":
            recompute.append(original)
            continue
        anchor_checksum = entry.get("anchorSourceChecksumSha256")
        if not _is_sha256(anchor_checksum):
            recompute.append(original)
            continue
        if checksum in invalidated_anchors or anchor_checksum in invalidated_anchors:
            recompute.append(original)
            continue
        if (
            anchor_checksum not in raw_entries
            and anchor_checksum not in stable_external_anchors
            and anchor_checksum not in fixed_anchors
        ):
            recompute.append(original)
            continue
        if compatibility_mode == LATERAL_V2_TO_V3_COMPATIBILITY:
            coverages = entry.get("boardRedEdgeCoverages")
            if (
                not isinstance(coverages, Sequence)
                or isinstance(coverages, str | bytes)
                or not coverages
                or any(
                    not isinstance(value, int | float) or isinstance(value, bool)
                    for value in coverages
                )
            ):
                recompute.append(original)
                continue
            weak_count = sum(float(value) < threshold for value in coverages)
            if 1 <= weak_count <= maximum_review_slots:
                recompute.append(original)
                continue
        reused[checksum] = entry
    # An entry selected for recomputation cannot remain an anchor of a reused
    # result, even when its own cause was missing provenance, review or a
    # policy transition rather than a changed manual override.
    invalidated_anchors.update(original.checksum_sha256 for original in recompute)
    while True:
        descendants = {
            checksum
            for checksum, entry in raw_entries.items()
            if isinstance(checksum, str)
            and isinstance(entry, Mapping)
            and entry.get("anchorSourceChecksumSha256") in invalidated_anchors
        }
        added = descendants - invalidated_anchors
        if not added:
            break
        invalidated_anchors.update(added)
    if any(checksum in invalidated_anchors for checksum in reused):
        reused = {
            checksum: entry
            for checksum, entry in reused.items()
            if checksum not in invalidated_anchors
        }
        recompute = [original for original in originals if original.checksum_sha256 not in reused]
    return PageGeometryReusePlan(reused, tuple(recompute))


def _override_fingerprint(value: object) -> str | None:
    if not isinstance(value, Mapping):
        return None
    identity = {
        "decisionChecksumSha256": value.get("decisionChecksumSha256"),
        "overrideId": value.get("overrideId"),
        "revision": value.get("revision"),
    }
    if (
        not _is_sha256(identity["decisionChecksumSha256"])
        or not isinstance(identity["overrideId"], str)
        or not isinstance(identity["revision"], int)
    ):
        return None
    return hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("ascii")
    ).hexdigest()


class PageGeometryCheckpointStore:
    """Checksummed append-only result shards with one atomically replaced index."""

    def __init__(
        self,
        artifact_root: Path,
        *,
        job_id: str,
        input_fingerprint_sha256: str,
        source_inventory_checksum_sha256: str,
        shard_size: int = 25,
    ) -> None:
        self._artifact_root = artifact_root.resolve()
        self._directory = (
            self._artifact_root / "data" / "page-geometry-preflight-checkpoints" / job_id
        )
        self._results_directory = self._directory / "results"
        self._state_path = self._directory / "state.json"
        self._input_fingerprint = input_fingerprint_sha256
        self._inventory_checksum = source_inventory_checksum_sha256
        self._shard_size = shard_size
        self._shards: list[dict[str, object]] = []

    def load(self, *, required: bool) -> LoadedPageGeometryCheckpoint | None:
        if not self._state_path.is_file():
            if required:
                raise JobHandlerError(
                    _CHECKPOINT_ERROR,
                    "The durable page-geometry checkpoint is missing.",
                )
            return None
        try:
            content = self._state_path.read_bytes()
            value = json.loads(content)
        except (OSError, json.JSONDecodeError) as error:
            raise JobHandlerError(
                _CHECKPOINT_ERROR,
                "The durable page-geometry checkpoint index is invalid.",
            ) from error
        if (
            not isinstance(value, Mapping)
            or value.get("schemaVersion") != PAGE_GEOMETRY_CHECKPOINT_SCHEMA_VERSION
            or value.get("inputFingerprintSha256") != self._input_fingerprint
            or value.get("sourceInventoryChecksumSha256") != self._inventory_checksum
            or not isinstance(value.get("metadata"), Mapping)
            or not isinstance(value.get("shards"), list)
        ):
            raise JobHandlerError(
                _CHECKPOINT_ERROR,
                "The durable page-geometry checkpoint does not match this job.",
            )
        entries: dict[str, object] = {}
        shards: list[dict[str, object]] = []
        for raw in cast(list[object], value["shards"]):
            if (
                not isinstance(raw, Mapping)
                or not isinstance(raw.get("relativePath"), str)
                or not _is_sha256(raw.get("checksumSha256"))
            ):
                raise JobHandlerError(
                    _CHECKPOINT_ERROR,
                    "The durable page-geometry checkpoint shard reference is invalid.",
                )
            path = self._safe_data_path(cast(str, raw["relativePath"]))
            try:
                shard_content = path.read_bytes()
            except OSError as error:
                raise JobHandlerError(
                    _CHECKPOINT_ERROR,
                    "A durable page-geometry checkpoint shard is missing.",
                ) from error
            if hashlib.sha256(shard_content).hexdigest() != raw["checksumSha256"]:
                raise JobHandlerError(
                    _CHECKPOINT_ERROR,
                    "A durable page-geometry checkpoint shard changed.",
                )
            try:
                shard = json.loads(shard_content)
            except json.JSONDecodeError as error:
                raise JobHandlerError(
                    _CHECKPOINT_ERROR,
                    "A durable page-geometry checkpoint shard is invalid.",
                ) from error
            raw_entries = shard.get("entries") if isinstance(shard, Mapping) else None
            if not isinstance(raw_entries, list):
                raise JobHandlerError(
                    _CHECKPOINT_ERROR,
                    "A durable page-geometry checkpoint shard has no entries.",
                )
            for item in raw_entries:
                if (
                    not isinstance(item, list)
                    or len(item) != 2
                    or not isinstance(item[0], str)
                    or not isinstance(item[1], Mapping)
                ):
                    raise JobHandlerError(
                        _CHECKPOINT_ERROR,
                        "A durable page-geometry checkpoint entry is invalid.",
                    )
                entries[item[0]] = dict(item[1])
            shards.append(dict(raw))
        self._shards = shards
        return LoadedPageGeometryCheckpoint(
            entries=entries,
            metadata=dict(cast(Mapping[str, object], value["metadata"])),
            state_checksum_sha256=hashlib.sha256(content).hexdigest(),
            state_relative_path=self._relative_to_data(self._state_path),
        )

    def initialize(
        self,
        entries: Mapping[str, object],
        *,
        metadata: Mapping[str, object],
    ) -> LoadedPageGeometryCheckpoint:
        if self._state_path.exists():
            raise JobHandlerError(
                _CHECKPOINT_ERROR,
                "The durable page-geometry checkpoint already exists.",
            )
        items = list(entries.items())
        for start in range(0, len(items), self._shard_size):
            self._append_shard(dict(items[start : start + self._shard_size]))
        return self._write_state(dict(metadata), dict(entries))

    def append(
        self,
        entries: Mapping[str, object],
        *,
        metadata: Mapping[str, object],
        all_entries: Mapping[str, object],
    ) -> LoadedPageGeometryCheckpoint:
        if entries:
            self._append_shard(entries)
        return self._write_state(dict(metadata), dict(all_entries))

    def _append_shard(self, entries: Mapping[str, object]) -> None:
        sequence = len(self._shards)
        content = _json_bytes(
            {
                "schemaVersion": PAGE_GEOMETRY_CHECKPOINT_SCHEMA_VERSION,
                "sequence": sequence,
                "entries": [[key, value] for key, value in entries.items()],
            }
        )
        checksum = hashlib.sha256(content).hexdigest()
        # The checksum is attested by the state index. Keep the filename short
        # enough for default Windows MAX_PATH installations.
        path = self._results_directory / f"{sequence:08d}.json"
        _write_immutable(path, content, collision_code=_CHECKPOINT_ERROR)
        self._shards.append(
            {
                "relativePath": self._relative_to_data(path),
                "checksumSha256": checksum,
            }
        )

    def _write_state(
        self,
        metadata: dict[str, object],
        entries: dict[str, object],
    ) -> LoadedPageGeometryCheckpoint:
        content = _json_bytes(
            {
                "schemaVersion": PAGE_GEOMETRY_CHECKPOINT_SCHEMA_VERSION,
                "inputFingerprintSha256": self._input_fingerprint,
                "sourceInventoryChecksumSha256": self._inventory_checksum,
                "shards": self._shards,
                "metadata": metadata,
            }
        )
        _write_atomic(self._state_path, content)
        return LoadedPageGeometryCheckpoint(
            entries=entries,
            metadata=metadata,
            state_checksum_sha256=hashlib.sha256(content).hexdigest(),
            state_relative_path=self._relative_to_data(self._state_path),
        )

    def _relative_to_data(self, path: Path) -> str:
        return (PurePosixPath("data") / path.relative_to(self._artifact_root / "data")).as_posix()

    def _safe_data_path(self, relative_path: str) -> Path:
        if not relative_path.startswith("data/"):
            raise JobHandlerError(_CHECKPOINT_ERROR, "Checkpoint path is outside managed data.")
        path = (self._artifact_root / Path(*PurePosixPath(relative_path).parts)).resolve()
        if not path.is_relative_to((self._artifact_root / "data").resolve()):
            raise JobHandlerError(_CHECKPOINT_ERROR, "Checkpoint path is outside managed data.")
        return path


def source_inventory_checksum(originals: Sequence[ManagedOriginal]) -> str:
    return hashlib.sha256(
        _json_bytes([original.checksum_sha256 for original in originals])
    ).hexdigest()


def recompute_inventory_checksum(originals: Sequence[ManagedOriginal]) -> str:
    return hashlib.sha256(
        _json_bytes([original.checksum_sha256 for original in originals])
    ).hexdigest()


def _manual_entry_matches_override(entry: Mapping[str, object], value: object) -> bool:
    return (
        isinstance(value, Mapping)
        and entry.get("manualOverrideDecisionChecksumSha256") == value.get("decisionChecksumSha256")
        and entry.get("manualOverrideId") == value.get("overrideId")
        and entry.get("manualOverrideRevision") == value.get("revision")
    )


def _is_manual_entry(entry: Mapping[str, object]) -> bool:
    return entry.get("registrationVersion") == "manual-page-geometry-override-v1"


def _frame_review_thresholds(payload: Mapping[str, object]) -> tuple[float, int]:
    lateral = payload.get("lateralPartialGeometry")
    if not isinstance(lateral, Mapping):
        return 0.65, 3
    threshold = lateral.get("minimumAutomaticBoardRedEdgeCoverage", 0.65)
    maximum = lateral.get("maximumFrameReviewSlots", 3)
    if (
        not isinstance(threshold, int | float)
        or isinstance(threshold, bool)
        or not isinstance(maximum, int)
        or isinstance(maximum, bool)
    ):
        raise JobHandlerError(
            _BASE_MANIFEST_ERROR,
            "The target lateral geometry thresholds are invalid.",
        )
    return float(threshold), maximum


def _fully_canonical(original: ManagedOriginal, payload: Mapping[str, object]) -> bool:
    canonical = payload.get("canonicalSequenceNumbers")
    return (
        isinstance(original.sequence_range_start, int)
        and isinstance(original.sequence_range_end, int)
        and isinstance(canonical, set)
        and all(
            number in canonical
            for number in range(
                original.sequence_range_start,
                original.sequence_range_end + 1,
            )
        )
    )


def _lateral_v2_to_v3_compatible(base: object, target: object) -> bool:
    return (
        isinstance(base, Mapping)
        and isinstance(target, Mapping)
        and base.get("schemaVersion") == _LATERAL_V2_SCHEMA
        and target.get("schemaVersion") == _LATERAL_V3_SCHEMA
        and base.get("variant") == target.get("variant")
        and base.get("partialGridTrainingProfile") == target.get("partialGridTrainingProfile")
    )


def _baseline_to_selective_compatible(base: object, target: object) -> bool:
    return (
        isinstance(base, Mapping)
        and isinstance(target, Mapping)
        and base.get("schemaVersion") in {_LATERAL_V1_SCHEMA, _LATERAL_V2_SCHEMA}
        and target.get("schemaVersion") == _SELECTIVE_SCHEMA
        and base.get("partialGridTrainingProfile") == target.get("partialGridTrainingProfile")
    )


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")


def _write_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError as error:
        temporary.unlink(missing_ok=True)
        raise JobHandlerError(
            _CHECKPOINT_ERROR,
            "The durable page-geometry checkpoint could not be written.",
        ) from error


def _write_immutable(path: Path, content: bytes, *, collision_code: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise JobHandlerError(collision_code, "A checkpoint shard checksum collision occurred.")
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
                    collision_code,
                    "A checkpoint shard checksum collision occurred.",
                ) from None
        finally:
            temporary.unlink(missing_ok=True)
    except OSError as error:
        temporary.unlink(missing_ok=True)
        raise JobHandlerError(
            _CHECKPOINT_ERROR,
            "A durable page-geometry checkpoint shard could not be written.",
        ) from error


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_uuid(value: str) -> bool:
    from uuid import UUID

    try:
        UUID(value)
    except ValueError:
        return False
    return True
