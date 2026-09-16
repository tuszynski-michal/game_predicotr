"""Checksum-bound metadata manifest for local semi-automatic source folders."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from uuid import UUID

from .contracts import SemiAutomaticSelectionSource, fingerprint_sources

LOCAL_SOURCE_MANIFEST_SCHEMA_VERSION = 1
LOCAL_SOURCE_MANIFEST_DIRECTORY = "semi-automatic-selection-sources"
LOCAL_SOURCE_MANIFEST_FILE = "source-manifest.json"
_NATURAL_PART = re.compile(r"(\d+)")
_SUPPORTED_SUFFIXES = frozenset({".jpg", ".jpeg"})


class LocalSourceManifestError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class LocalSourceManifest:
    selection_id: UUID
    display_name: str
    source_root: Path
    sources: tuple[SemiAutomaticSelectionSource, ...]
    source_fingerprint: str
    total_bytes: int
    content: bytes
    checksum_sha256: str


def build_local_source_manifest(
    source_root: Path,
    *,
    selection_id: UUID,
    display_name: str,
    maximum_files: int = 100_000,
) -> LocalSourceManifest:
    root = _resolve_source_root(source_root)
    candidates: list[tuple[str, Path]] = []
    try:
        for current_root, directory_names, file_names in os.walk(root, followlinks=False):
            directory_names.sort(key=_natural_key)
            file_names.sort(key=_natural_key)
            for file_name in file_names:
                candidate = Path(current_root) / file_name
                if candidate.suffix.casefold() not in _SUPPORTED_SUFFIXES:
                    continue
                resolved = candidate.resolve(strict=True)
                if candidate.is_symlink() or (root != resolved and root not in resolved.parents):
                    _fail("SEMI_AUTOMATIC_SELECTION_SOURCE_PATH_UNSAFE", "Source escaped its root.")
                relative_path = resolved.relative_to(root).as_posix()
                candidates.append((relative_path, resolved))
                if len(candidates) > maximum_files:
                    _fail(
                        "SEMI_AUTOMATIC_SELECTION_SOURCE_TOO_LARGE",
                        "The local source exceeds the supported file limit.",
                    )
    except OSError as error:
        raise LocalSourceManifestError(
            "SEMI_AUTOMATIC_SELECTION_SOURCE_UNAVAILABLE",
            "The local source folder cannot be scanned.",
        ) from error
    if not candidates:
        _fail(
            "SEMI_AUTOMATIC_SELECTION_SOURCE_EMPTY",
            "The local source folder contains no JPEG files.",
        )
    candidates.sort(key=lambda item: _natural_key(item[0]))
    sources: list[SemiAutomaticSelectionSource] = []
    for source_index, (relative_path, path) in enumerate(candidates):
        try:
            size_bytes = path.stat().st_size
            checksum_sha256 = _sha256_file(path)
        except OSError as error:
            raise LocalSourceManifestError(
                "SEMI_AUTOMATIC_SELECTION_SOURCE_UNAVAILABLE",
                "A local source JPEG cannot be read.",
            ) from error
        if size_bytes < 1:
            _fail(
                "SEMI_AUTOMATIC_SELECTION_SOURCE_UNAVAILABLE",
                "A local source JPEG is empty.",
            )
        sources.append(
            SemiAutomaticSelectionSource(
                source_index=source_index,
                relative_path=relative_path,
                size_bytes=size_bytes,
                checksum_sha256=checksum_sha256,
            )
        )
    source_values = tuple(sources)
    source_fingerprint = fingerprint_sources(source_values)
    payload = {
        "displayName": display_name,
        "files": [
            {
                "checksumSha256": source.checksum_sha256,
                "orderIndex": source.source_index,
                "relativePath": source.relative_path,
                "sizeBytes": source.size_bytes,
            }
            for source in source_values
        ],
        "orderingPolicy": "natural_relative_path_v1",
        "schemaVersion": LOCAL_SOURCE_MANIFEST_SCHEMA_VERSION,
        "selectionId": str(selection_id),
        "sourceFingerprint": source_fingerprint,
        "sourceKind": "local_folder",
        "sourceRoot": str(root),
    }
    content = _canonical_bytes(payload)
    return LocalSourceManifest(
        selection_id=selection_id,
        display_name=display_name,
        source_root=root,
        sources=source_values,
        source_fingerprint=source_fingerprint,
        total_bytes=sum(source.size_bytes for source in source_values),
        content=content,
        checksum_sha256=hashlib.sha256(content).hexdigest(),
    )


def write_local_source_manifest(artifact_root: Path, manifest: LocalSourceManifest) -> str:
    root = artifact_root.resolve()
    relative = PurePosixPath(
        "exports",
        LOCAL_SOURCE_MANIFEST_DIRECTORY,
        str(manifest.selection_id),
        LOCAL_SOURCE_MANIFEST_FILE,
    )
    target = root.joinpath(*relative.parts).resolve()
    if root != target and root not in target.parents:
        _fail("SEMI_AUTOMATIC_SELECTION_SOURCE_PATH_UNSAFE", "Manifest path escaped its root.")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        try:
            existing = target.read_bytes()
        except OSError as error:
            raise LocalSourceManifestError(
                "SEMI_AUTOMATIC_SELECTION_SOURCE_MANIFEST_UNAVAILABLE",
                "The local source manifest cannot be read.",
            ) from error
        if existing != manifest.content:
            _fail(
                "SEMI_AUTOMATIC_SELECTION_SOURCE_CHANGED",
                "The source selection already has a different manifest.",
            )
        return relative.as_posix()
    temporary = target.with_name(f".{target.name}.part")
    try:
        temporary.write_bytes(manifest.content)
        temporary.replace(target)
    except OSError as error:
        temporary.unlink(missing_ok=True)
        raise LocalSourceManifestError(
            "SEMI_AUTOMATIC_SELECTION_SOURCE_MANIFEST_UNAVAILABLE",
            "The local source manifest cannot be written.",
        ) from error
    return relative.as_posix()


def load_local_source_manifest(
    artifact_root: Path,
    *,
    relative_path: str,
    expected_checksum_sha256: str,
    expected_selection_id: UUID,
) -> LocalSourceManifest:
    root = artifact_root.resolve()
    relative = PurePosixPath(relative_path.replace("\\", "/"))
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        _fail("SEMI_AUTOMATIC_SELECTION_SOURCE_PATH_UNSAFE", "Manifest path is unsafe.")
    target = root.joinpath(*relative.parts).resolve()
    if root != target and root not in target.parents:
        _fail("SEMI_AUTOMATIC_SELECTION_SOURCE_PATH_UNSAFE", "Manifest path escaped its root.")
    try:
        content = target.read_bytes()
    except OSError as error:
        raise LocalSourceManifestError(
            "SEMI_AUTOMATIC_SELECTION_SOURCE_MANIFEST_UNAVAILABLE",
            "The local source manifest cannot be read.",
        ) from error
    if hashlib.sha256(content).hexdigest() != expected_checksum_sha256:
        _fail(
            "SEMI_AUTOMATIC_SELECTION_SOURCE_CHANGED",
            "The local source manifest checksum changed.",
        )
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as error:
        raise LocalSourceManifestError(
            "SEMI_AUTOMATIC_SELECTION_SOURCE_CHANGED",
            "The local source manifest is invalid.",
        ) from error
    if (
        not isinstance(payload, dict)
        or payload.get("schemaVersion") != LOCAL_SOURCE_MANIFEST_SCHEMA_VERSION
        or payload.get("sourceKind") != "local_folder"
        or payload.get("selectionId") != str(expected_selection_id)
        or payload.get("orderingPolicy") != "natural_relative_path_v1"
        or not isinstance(payload.get("displayName"), str)
        or not isinstance(payload.get("sourceRoot"), str)
        or not isinstance(payload.get("files"), list)
    ):
        _fail("SEMI_AUTOMATIC_SELECTION_SOURCE_CHANGED", "Manifest scope is invalid.")
    source_root = _resolve_source_root(Path(payload["sourceRoot"]))
    raw_files = payload["files"]
    sources: list[SemiAutomaticSelectionSource] = []
    for expected_index, raw in enumerate(raw_files):
        if not isinstance(raw, dict) or raw.get("orderIndex") != expected_index:
            _fail("SEMI_AUTOMATIC_SELECTION_SOURCE_CHANGED", "Manifest ordering is invalid.")
        try:
            source = SemiAutomaticSelectionSource(
                source_index=expected_index,
                relative_path=str(raw["relativePath"]),
                size_bytes=int(raw["sizeBytes"]),
                checksum_sha256=str(raw["checksumSha256"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise LocalSourceManifestError(
                "SEMI_AUTOMATIC_SELECTION_SOURCE_CHANGED",
                "A local source manifest entry is invalid.",
            ) from error
        sources.append(source)
    source_values = tuple(sources)
    source_fingerprint = fingerprint_sources(source_values)
    if payload.get("sourceFingerprint") != source_fingerprint:
        _fail("SEMI_AUTOMATIC_SELECTION_SOURCE_CHANGED", "Source fingerprint changed.")
    return LocalSourceManifest(
        selection_id=expected_selection_id,
        display_name=payload["displayName"],
        source_root=source_root,
        sources=source_values,
        source_fingerprint=source_fingerprint,
        total_bytes=sum(source.size_bytes for source in source_values),
        content=content,
        checksum_sha256=expected_checksum_sha256,
    )


def resolve_local_source_asset(
    manifest: LocalSourceManifest,
    *,
    source_index: int,
    expected_checksum_sha256: str,
) -> tuple[Path, SemiAutomaticSelectionSource]:
    if source_index < 0 or source_index >= len(manifest.sources):
        _fail("SEMI_AUTOMATIC_SELECTION_SOURCE_NOT_FOUND", "The source does not exist.")
    source = manifest.sources[source_index]
    if source.checksum_sha256 != expected_checksum_sha256:
        _fail("SEMI_AUTOMATIC_SELECTION_SOURCE_CHANGED", "Source identity does not match.")
    relative = PurePosixPath(source.relative_path)
    target = manifest.source_root.joinpath(*relative.parts).resolve()
    if manifest.source_root != target and manifest.source_root not in target.parents:
        _fail("SEMI_AUTOMATIC_SELECTION_SOURCE_PATH_UNSAFE", "Source path escaped its root.")
    try:
        if (
            target.stat().st_size != source.size_bytes
            or _sha256_file(target) != source.checksum_sha256
        ):
            _fail("SEMI_AUTOMATIC_SELECTION_SOURCE_CHANGED", "The source JPEG changed.")
    except OSError as error:
        raise LocalSourceManifestError(
            "SEMI_AUTOMATIC_SELECTION_SOURCE_UNAVAILABLE",
            "The source JPEG is unavailable.",
        ) from error
    return target, source


def _resolve_source_root(path: Path) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise LocalSourceManifestError(
            "SEMI_AUTOMATIC_SELECTION_SOURCE_UNAVAILABLE",
            "The local source folder is unavailable.",
        ) from error
    if not resolved.is_dir():
        _fail("SEMI_AUTOMATIC_SELECTION_SOURCE_UNAVAILABLE", "The source is not a directory.")
    return resolved


def _natural_key(value: str) -> tuple[tuple[int, int | str], ...]:
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part.casefold())
        for part in _NATURAL_PART.split(value)
        if part
    )


def _canonical_bytes(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _fail(code: str, message: str) -> None:
    raise LocalSourceManifestError(code, message)


__all__ = [
    "LocalSourceManifest",
    "LocalSourceManifestError",
    "build_local_source_manifest",
    "load_local_source_manifest",
    "resolve_local_source_asset",
    "write_local_source_manifest",
]
