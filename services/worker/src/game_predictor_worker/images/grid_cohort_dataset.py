"""Application snapshot adapter outside the isolated neutral training core.

Role selection precedes every image read. A valid artifact is historical evidence;
it does not grant permission for a new run or replace live eligibility checks.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn
from uuid import UUID

import numpy as np
from game_predictor_api.domain.canonical_source import (
    CANONICAL_SOURCE_LOADER_VERSION,
    RGB_PIXEL_CHECKSUM_VERSION,
    CanonicalSourceFrame,
    CanonicalSourceLoadError,
    decode_canonical_source_bytes,
)
from game_predictor_api.domain.grid_model_registry import (
    GridModelRegistryError,
    descriptor_sha256,
    validate_manifest,
)
from PIL import __version__ as PILLOW_VERSION

from game_predictor_worker.filesystem import long_path_aware

_ROLES = {"TRAIN", "VALIDATION", "REGRESSION"}
_SHA = re.compile(r"^[0-9a-f]{64}$")
_METADATA_LIMIT = 16 * 1024 * 1024
_SOURCE_LIMIT = 64 * 1024 * 1024


class GridCohortDatasetError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _fail(code: str, message: str) -> NoReturn:
    raise GridCohortDatasetError(code, message)


def _integer(value: object, minimum: int = 0) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def _sha(value: object) -> bool:
    return isinstance(value, str) and _SHA.fullmatch(value) is not None


def _uuid(value: object) -> bool:
    try:
        return isinstance(value, str) and str(UUID(value)) == value
    except ValueError:
        return False


def _json(content: bytes) -> Any:
    def invalid_constant(value: str) -> None:
        _fail("METADATA_INVALID", f"Non-finite JSON value: {value}.")

    try:
        return json.loads(content, parse_constant=invalid_constant)
    except (ValueError, UnicodeError) as error:
        raise GridCohortDatasetError("METADATA_INVALID", "Snapshot JSON is invalid.") from error


class GridCohortSnapshot:
    """Keep at most one metadata page and one canonical image frame in memory."""

    def __init__(
        self, artifact_root: Path, manifest_relative_path: str, expected_manifest_sha256: str
    ) -> None:
        original_root = Path(artifact_root).absolute()
        if any(
            path.is_symlink() or path.is_junction()
            for path in (original_root, *original_root.parents)
        ):
            _fail("PATH_UNSAFE", "Linked artifact roots are forbidden.")
        self.root = original_root.resolve()
        self._page_key: tuple[str, str] | None = None
        self._page_cache: dict[str, Any] | None = None
        self._frame_key: tuple[str, str, str] | None = None
        self._frame_cache: CanonicalSourceFrame | None = None
        self._manifest = self._read_json(
            {"path": manifest_relative_path, "sha256": expected_manifest_sha256}
        )
        self._validate_manifest()
        self._directory = (
            f"data/grid-training-cohorts/{self._manifest['gameId']}/{self._manifest['cohortId']}/"
        )
        self._assert_cohort_path(manifest_relative_path)
        self._verify_index()

    @property
    def manifest(self) -> dict[str, Any]:
        return copy.deepcopy(self._manifest)

    def _safe(self, relative: object) -> Path:
        if not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative:
            _fail("PATH_UNSAFE", "Snapshot paths must be relative managed paths.")
        value = PurePosixPath(relative)
        if value.is_absolute() or ".." in value.parts or str(value) != relative:
            _fail("PATH_UNSAFE", "Snapshot path leaves managed storage.")
        path = self.root.joinpath(*value.parts)
        for candidate in (path, *path.parents):
            if candidate == self.root.parent:
                break
            if candidate.is_symlink() or candidate.is_junction():
                _fail("PATH_UNSAFE", "Linked snapshot files are forbidden.")
        if not path.resolve().is_relative_to(self.root):
            _fail("PATH_UNSAFE", "Snapshot path leaves managed storage.")
        return long_path_aware(path)

    def _assert_cohort_path(self, relative: str) -> None:
        if not isinstance(relative, str) or not relative.startswith(self._directory):
            _fail("COHORT_PATH_MISMATCH", "Snapshot reference belongs to another cohort.")

    def _read(self, pin: dict[str, Any], maximum: int) -> bytes:
        if not isinstance(pin, dict) or not _sha(pin.get("sha256")):
            _fail("PIN_INVALID", "An exact SHA-256 file pin is required.")
        if "bytes" in pin and not _integer(pin["bytes"]):
            _fail("PIN_INVALID", "An exact non-negative file size is required.")
        path = self._safe(pin.get("path"))
        try:
            with path.open("rb") as stream:
                content = stream.read(maximum + 1)
        except OSError as error:
            raise GridCohortDatasetError(
                "DATASET_ASSET_UNAVAILABLE", "Snapshot artifact is unavailable."
            ) from error
        if len(content) > maximum:
            _fail("ASSET_SIZE_LIMIT", "Snapshot artifact exceeds its bounded size.")
        if "bytes" in pin and len(content) != pin["bytes"]:
            _fail("ASSET_SIZE_MISMATCH", "Snapshot artifact size changed.")
        if hashlib.sha256(content).hexdigest() != pin["sha256"]:
            _fail("CHECKSUM_MISMATCH", "Snapshot artifact bytes changed.")
        return content

    def _read_json(self, pin: dict[str, Any]) -> dict[str, Any]:
        value = _json(self._read(pin, _METADATA_LIMIT))
        if not isinstance(value, dict):
            _fail("METADATA_INVALID", "A snapshot metadata object is required.")
        return value

    def _validate_manifest(self) -> None:
        value = self._manifest
        if (
            value.get("schemaVersion") != "application-grid-snapshot-v1"
            or value.get("policyVersion") != "application-grid-cohort-v1"
            or value.get("weightPolicy") != "correction-weight-4-to-1-v1"
            or value.get("mode") not in ("grid-only", "screen+grid")
            or any(not _uuid(value.get(key)) for key in ("gameId", "cohortId", "familyId"))
        ):
            _fail("POLICY_UNSUPPORTED", "Snapshot policy or identity is unsupported.")
        base = value.get("base")
        if not isinstance(base, dict) or not isinstance(base.get("manifest"), dict):
            _fail("BASE_MANIFEST_INVALID", "An immutable catalogue base is required.")
        descriptor = base["manifest"]
        try:
            validate_manifest(descriptor)
        except (GridModelRegistryError, KeyError, TypeError, ValueError) as error:
            raise GridCohortDatasetError(
                "BASE_MANIFEST_INVALID", "Catalogue descriptor is invalid."
            ) from error
        if (
            not _sha(base.get("manifestSha256"))
            or descriptor_sha256(descriptor) != base["manifestSha256"]
            or not _uuid(base.get("versionId"))
            or not _uuid(base.get("familyId"))
            or base["versionId"] != descriptor["versionId"]
            or base["familyId"] != descriptor["familyId"]
        ):
            _fail("BASE_MANIFEST_MISMATCH", "Catalogue base identity or checksum differs.")
        preprocessing = {
            key: descriptor[key]
            for key in ("preprocessingVersion", "decodingPolicyVersion", "inferenceManifest")
        }
        if value.get("preprocessing") != preprocessing:
            _fail("PREPROCESSING_MISMATCH", "Snapshot preprocessing differs from its base.")
        decoder = value.get("decoder")
        if (
            not isinstance(decoder, dict)
            or decoder.get("adapterVersion") != CANONICAL_SOURCE_LOADER_VERSION
            or decoder.get("pixelAlgorithm") != RGB_PIXEL_CHECKSUM_VERSION
            or decoder.get("pillowVersion") != PILLOW_VERSION
        ):
            _fail("DECODER_UNSUPPORTED", "Snapshot requires a different canonical decoder.")
        if not _integer(value.get("pageCount")):
            _fail("INDEX_INVALID", "Snapshot page count is invalid.")
        counts = value.get("counts")
        if (
            not isinstance(counts, dict)
            or set(counts) != _ROLES
            or any(
                not isinstance(counts[role], dict)
                or any(
                    not _integer(counts[role].get(key))
                    for key in ("boards", "photos", "fullPhotos")
                )
                for role in _ROLES
            )
        ):
            _fail("COUNTS_INVALID", "Explicit per-role source and target counts are required.")

    def _verify_index(self) -> Path:
        pin = self._manifest.get("pageIndex")
        if (
            not isinstance(pin, dict)
            or not _sha(pin.get("sha256"))
            or not _integer(pin.get("bytes"))
        ):
            _fail("INDEX_INVALID", "A checksummed page index is required.")
        path = self._safe(pin.get("path"))
        self._assert_cohort_path(pin["path"])
        digest, size, count = hashlib.sha256(), 0, 0
        try:
            with path.open("rb") as stream:
                while line := stream.readline(65537):
                    if len(line) > 65536:
                        _fail("INDEX_INVALID", "Page index line exceeds its bound.")
                    digest.update(line)
                    size += len(line)
                    count += 1
                    row = _json(line)
                    if (
                        not isinstance(row, dict)
                        or not all(
                            _integer(row.get(key)) for key in ("bytes", "boardCount", "screenCount")
                        )
                        or not isinstance(row.get("path"), str)
                        or not _sha(row.get("sha256"))
                    ):
                        _fail("INDEX_INVALID", "Page index row is invalid.")
            if (
                digest.hexdigest() != pin["sha256"]
                or size != pin["bytes"]
                or count != self._manifest["pageCount"]
            ):
                _fail("INDEX_MISMATCH", "Snapshot page index changed.")
        except OSError as error:
            raise GridCohortDatasetError(
                "DATASET_ASSET_UNAVAILABLE", "Page index is unavailable."
            ) from error
        return path

    def sources(self) -> Iterator[dict[str, Any]]:
        """Stream metadata only; retain excluded and control rows without reading images."""
        path = self._verify_index()
        previous = -1
        with path.open("rb") as stream:
            for line in stream:
                pin = _json(line)
                self._assert_cohort_path(pin["path"])
                content = self._read(pin, _METADATA_LIMIT)
                key = pin["path"], pin["sha256"]
                if key != self._page_key:
                    self._page_cache = _json(content)
                    self._page_key = key
                page = self._page_cache
                if (
                    not isinstance(page, dict)
                    or not _integer(page.get("firstOrdinal"))
                    or not _integer(page.get("lastOrdinal"))
                    or page["firstOrdinal"] <= previous
                    or page["lastOrdinal"] < page["firstOrdinal"]
                    or not isinstance(page.get("sources"), list)
                    or not 1 <= len(page["sources"]) <= 5
                ):
                    _fail("PAGE_INVALID", "Snapshot page order or size is invalid.")
                previous = page["lastOrdinal"]
                board_count = screen_count = 0
                for source in page["sources"]:
                    if (
                        not isinstance(source, dict)
                        or not _uuid(source.get("sourceId"))
                        or source.get("role") not in (*_ROLES, None)
                        or type(source.get("used")) is not bool
                    ):
                        _fail(
                            "SOURCE_INVALID",
                            "Snapshot source identity, role or used flag is invalid.",
                        )
                    if source["used"]:
                        if source["role"] not in _ROLES or not isinstance(
                            source.get("targets"), list
                        ):
                            _fail(
                                "ROLE_REQUIRED",
                                "Used sources require a proven role and target list.",
                            )
                        board_count += len(source["targets"])
                        screen_count += int(source.get("screenEligible") is True)
                if board_count != pin["boardCount"] or screen_count != pin["screenCount"]:
                    _fail("PAGE_COUNTS_MISMATCH", "Page target counts differ from their index.")
                yield from page["sources"]

    def frame(self, source: dict[str, Any], role: str) -> CanonicalSourceFrame:
        # Keep this guard before path resolution, existence, byte reads and decode.
        if role not in _ROLES or source.get("role") != role or source.get("used") is not True:
            _fail(
                "ROLE_MISMATCH",
                "A dataset cannot read pixels outside its explicitly selected role.",
            )
        pin, identity = source.get("original"), source.get("sourceIdentity")
        if not isinstance(pin, dict) or not isinstance(identity, dict):
            _fail(
                "SOURCE_INVALID", "Used source requires an immutable image and canonical identity."
            )
        orientation = identity.get("exif_orientation")
        if (
            not _integer(pin.get("bytes"))
            or not _sha(identity.get("checksum_sha256"))
            or not _sha(identity.get("normalized_pixel_checksum_sha256"))
            or not _integer(identity.get("oriented_width"), 1)
            or not _integer(identity.get("oriented_height"), 1)
            or identity.get("normalization_adapter_version") != CANONICAL_SOURCE_LOADER_VERSION
            or (orientation is not None and (not _integer(orientation, 1) or orientation > 8))
        ):
            _fail(
                "SOURCE_IDENTITY_MISMATCH", "Canonical source pins are incomplete or unsupported."
            )
        self._assert_cohort_path(pin.get("path", ""))
        if pin.get("sha256") != identity.get("checksum_sha256"):
            _fail("SOURCE_IDENTITY_MISMATCH", "Original byte identity differs from its source pin.")
        content = self._read(pin, _SOURCE_LIMIT)
        key = pin["path"], pin["sha256"], descriptor_sha256(identity)
        if self._frame_key != key:
            self._frame_cache = None
            self._frame_key = None
            try:
                frame = decode_canonical_source_bytes(
                    content, expected_source_checksum_sha256=pin["sha256"]
                )
            except CanonicalSourceLoadError as error:
                raise GridCohortDatasetError(error.code, str(error)) from error
            normalized = frame.source
            if (
                normalized.normalized_pixel_checksum_sha256
                != identity.get("normalized_pixel_checksum_sha256")
                or normalized.normalization_adapter_version
                != identity.get("normalization_adapter_version")
                or (normalized.width, normalized.height)
                != (identity.get("oriented_width"), identity.get("oriented_height"))
                or normalized.exif_orientation != identity.get("exif_orientation")
            ):
                _fail(
                    "SOURCE_IDENTITY_MISMATCH",
                    "Canonical pixel identity, dimensions or EXIF differs.",
                )
            self._frame_cache, self._frame_key = frame, key
        assert self._frame_cache is not None
        return self._frame_cache


def _nodes(target: dict[str, Any]) -> np.ndarray:
    raw = target.get("nodes")
    if (
        not isinstance(raw, list)
        or len(raw) != 24
        or any(
            not isinstance(point, dict)
            or set(point) != {"x", "y"}
            or any(
                not isinstance(point[axis], int | float)
                or isinstance(point[axis], bool)
                or not math.isfinite(point[axis])
                for axis in ("x", "y")
            )
            for point in raw
        )
    ):
        _fail("EXACT_NODES_REQUIRED", "Every target requires all 24 finite stored nodes.")
    return np.asarray([[point["x"], point["y"]] for point in raw], dtype=np.float64)


def _target(target: dict[str, Any]) -> tuple[np.ndarray, int, dict[str, Any]]:
    nodes = _nodes(target)
    approval = target.get("approval", {})
    if not isinstance(approval, dict):
        _fail("TARGET_PROOF_INVALID", "Human-label proof is invalid.")
    origin = approval.get("origin")
    if not isinstance(origin, str):
        _fail("TARGET_PROOF_INVALID", "An exact human-label origin is required.")
    weight = {"human_corrected": 4, "human_checked_unchanged": 1}.get(origin)
    if (
        weight is None
        or approval.get("weight") != weight
        or not _integer(target.get("sequenceNumber"))
    ):
        _fail("TARGET_PROOF_INVALID", "Target sequence or human-label weight differs.")
    render = target.get("render")
    if not isinstance(render, dict) or not isinstance(render.get("configuration"), dict):
        _fail("RENDER_UNRESOLVED", "Exact render configuration is required.")
    return nodes, weight, render["configuration"]


class GridBoardDataset:
    def __init__(self, snapshot: GridCohortSnapshot, role: str = "TRAIN") -> None:
        if role not in _ROLES:
            _fail("ROLE_INVALID", "Choose TRAIN, VALIDATION or REGRESSION explicitly.")
        self.snapshot, self.role = snapshot, role

    def _sources(self) -> Iterator[dict[str, Any]]:
        for source in self.snapshot.sources():
            if source["used"] and source["role"] == self.role:
                targets = source["targets"]
                if any(not isinstance(target, dict) for target in targets):
                    _fail("TARGETS_INVALID", "Each target must be a metadata object.")
                positions = [target.get("positionIndex") for target in targets]
                if (
                    not 1 <= len(targets) <= 9
                    or any(not _integer(p) or p > 8 for p in positions)
                    or len(set(positions)) != len(positions)
                ):
                    _fail("TARGETS_INVALID", "Targets require distinct physical positions.")
                full = source.get("screenEligible") is True and set(positions) == set(range(9))
                if (
                    self.role != "TRAIN" or self.snapshot._manifest["mode"] == "screen+grid"
                ) and not full:
                    _fail(
                        "FULL_PHOTO_REQUIRED",
                        "Control and screen cohorts require nine full targets.",
                    )
                yield source

    def indexed(self) -> list[tuple[dict[str, Any], list[tuple[np.ndarray, int]]]]:
        """Metadata-only index of the role: each source with its (nodes, weight) targets in
        physical position order, after the root count check of ``__len__``."""
        len(self)
        result = []
        for source in self._sources():
            ordered = sorted(source["targets"], key=lambda target: target["positionIndex"])
            result.append((source, [_target(target)[:2] for target in ordered]))
        return result

    def __len__(self) -> int:
        boards = photos = full = 0
        for source in self._sources():
            boards += len(source["targets"])
            photos += 1
            full += int(source.get("screenEligible") is True)
        if self.snapshot._manifest["counts"][self.role] != {
            "boards": boards,
            "photos": photos,
            "fullPhotos": full,
        }:
            _fail("COUNTS_MISMATCH", "Per-role metadata counts differ from the root manifest.")
        return boards

    def __getitem__(self, index: int) -> dict[str, Any]:
        if not _integer(index):
            raise IndexError(index)
        for source in self._sources():
            if index >= len(source["targets"]):
                index -= len(source["targets"])
                continue
            target = source["targets"][index]
            nodes, weight, configuration = _target(target)
            frame = self.snapshot.frame(source, self.role)
            return {
                "sourceRgb": frame.rgb,
                "nodes": nodes,
                "sourceId": source["sourceId"],
                "positionIndex": target["positionIndex"],
                "sequenceNumber": target["sequenceNumber"],
                "role": self.role,
                "sampleWeight": weight,
                "renderConfiguration": copy.deepcopy(configuration),
            }
        raise IndexError(index)


class GridScreenDataset(GridBoardDataset):
    def __len__(self) -> int:
        super().__len__()
        result = 0
        for source in self._sources():
            if source.get("screenEligible") is True:
                if len(source["targets"]) != 9:
                    _fail(
                        "FULL_PHOTO_REQUIRED",
                        "A screen target requires all nine physical positions.",
                    )
                result += 1
        return result

    def __getitem__(self, index: int) -> dict[str, Any]:
        if not _integer(index):
            raise IndexError(index)
        for source in self._sources():
            if source.get("screenEligible") is not True:
                continue
            if len(source["targets"]) != 9:
                _fail(
                    "FULL_PHOTO_REQUIRED", "A screen target requires all nine physical positions."
                )
            if index:
                index -= 1
                continue
            targets = sorted(source["targets"], key=lambda target: target["positionIndex"])
            nodes = np.stack([_target(target)[0] for target in targets])
            frame = self.snapshot.frame(source, self.role)
            return {
                "sourceRgb": frame.rgb,
                "nodes": nodes,
                "sourceId": source["sourceId"],
                "role": self.role,
                "targets": copy.deepcopy(targets),
            }
        raise IndexError(index)
