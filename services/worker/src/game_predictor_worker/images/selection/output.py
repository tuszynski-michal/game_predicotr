"""Atomic, content-addressed output for representative image selections."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn, cast
from uuid import UUID, uuid4

from game_predictor_worker.images.image_file import ImageFileError, read_jpeg_dimensions

from .contracts import (
    CandidateResult,
    ImageSelectionResult,
    SelectionContractError,
    SelectionGroupStatus,
    SequenceRange,
)

OUTPUT_MANIFEST_FILE = "manifest.json"
OUTPUT_MANIFEST_SCHEMA_VERSION = 1
OUTPUT_MANIFEST_CONTRACT = "curated-image-selection-output-v1"


@dataclass(frozen=True, slots=True)
class CuratedImageEntry:
    range_start: int
    range_end: int
    source_order_index: int
    source_relative_path: str
    source_checksum_sha256: str
    output_relative_path: str
    output_checksum_sha256: str
    size_bytes: int
    width: int
    height: int
    quality_metrics: Mapping[str, float]

    def to_dict(self) -> dict[str, object]:
        return {
            "height": self.height,
            "outputChecksumSha256": self.output_checksum_sha256,
            "outputRelativePath": self.output_relative_path,
            "qualityMetrics": dict(self.quality_metrics),
            "rangeEnd": self.range_end,
            "rangeStart": self.range_start,
            "sizeBytes": self.size_bytes,
            "sourceChecksumSha256": self.source_checksum_sha256,
            "sourceOrderIndex": self.source_order_index,
            "sourceRelativePath": self.source_relative_path,
            "width": self.width,
        }


@dataclass(frozen=True, slots=True)
class CuratedImageManifest:
    run_id: UUID
    input_manifest_sha256: str
    selector_version: str
    selector_fingerprint: str
    entries: tuple[CuratedImageEntry, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": OUTPUT_MANIFEST_CONTRACT,
            "entries": [entry.to_dict() for entry in self.entries],
            "inputManifestSha256": self.input_manifest_sha256,
            "runId": str(self.run_id),
            "schemaVersion": OUTPUT_MANIFEST_SCHEMA_VERSION,
            "selectorFingerprint": self.selector_fingerprint,
            "selectorVersion": self.selector_version,
        }

    @property
    def canonical_bytes(self) -> bytes:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")

    @property
    def checksum_sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()


@dataclass(frozen=True, slots=True)
class PublishedImageSelection:
    manifest: CuratedImageManifest
    manifest_sha256: str
    manifest_relative_path: str
    output_directory: Path


class CuratedImageOutputPublisher:
    """Copy verified JPEGs and expose the run with one atomic directory rename."""

    def __init__(
        self,
        artifact_root: Path,
        *,
        before_commit: Callable[[Path], None] | None = None,
    ) -> None:
        self._artifact_root = artifact_root.resolve()
        self._exports_root = (
            self._artifact_root / "data" / "exports" / "image-selections"
        )
        self._before_commit = before_commit

    def publish(
        self,
        *,
        run_id: UUID,
        source_root: Path,
        input_manifest_sha256: str,
        result: ImageSelectionResult,
    ) -> PublishedImageSelection:
        source = source_root.resolve(strict=True)
        if not source.is_dir():
            _fail("IMAGE_SELECTION_SOURCE_INVALID", "Source root must be a directory.")
        _validate_sha256(input_manifest_sha256)
        selected_groups: list[tuple[CandidateResult, SequenceRange]] = []
        seen_ranges: set[tuple[int, int]] = set()
        for group in sorted(result.groups, key=lambda value: value.group_order):
            if group.status is SelectionGroupStatus.SKIPPED_EXISTING_RANGE:
                continue
            candidate = group.selected_candidate
            recognized = group.range
            if (
                group.status is not SelectionGroupStatus.AUTO_SELECTED
                or recognized is None
                or candidate is None
            ):
                _fail(
                    "IMAGE_SELECTION_NOT_READY",
                    "Every non-duplicate group must have one approved candidate.",
                )
            key = (recognized.start, recognized.end)
            if key in seen_ranges:
                _fail(
                    "IMAGE_SELECTION_RANGE_CONFLICT",
                    "A selected sequence range occurs more than once.",
                )
            seen_ranges.add(key)
            selected_groups.append((candidate, recognized))
        if not selected_groups:
            _fail("IMAGE_SELECTION_NOT_READY", "The run has no selected sequence range.")

        pending_root = self._exports_root / ".pending" / uuid4().hex[:12]
        images_root = pending_root / "images"
        images_root.mkdir(parents=True, exist_ok=False)
        entries: list[CuratedImageEntry] = []
        try:
            for candidate, recognized in selected_groups:
                source_path = _safe_child(source, candidate.source.stored_relative_path)
                source_checksum = _sha256_file(source_path)
                if source_checksum != candidate.source.checksum_sha256:
                    _fail(
                        "IMAGE_SELECTION_MANIFEST_MISMATCH",
                        "A selected source checksum changed before publication.",
                    )
                file_name = (
                    f"seq_{recognized.start:06d}-{recognized.end:06d}"
                    f"__{source_checksum[:12]}.jpg"
                )
                output_path = images_root / file_name
                _copy_and_fsync(source_path, output_path)
                copied_checksum = _sha256_file(output_path)
                if copied_checksum != source_checksum:
                    _fail(
                        "IMAGE_SELECTION_MANIFEST_MISMATCH",
                        "A curated image differs from its selected source.",
                    )
                try:
                    width, height = read_jpeg_dimensions(output_path)
                except ImageFileError as error:
                    raise SelectionContractError(
                        "IMAGE_SELECTION_OUTPUT_INVALID",
                        "A curated output is not a readable JPEG.",
                    ) from error
                entries.append(
                    CuratedImageEntry(
                        range_start=recognized.start,
                        range_end=recognized.end,
                        source_order_index=candidate.source.order_index,
                        source_relative_path=candidate.source.relative_path,
                        source_checksum_sha256=source_checksum,
                        output_relative_path=f"images/{file_name}",
                        output_checksum_sha256=copied_checksum,
                        size_bytes=output_path.stat().st_size,
                        width=width,
                        height=height,
                        quality_metrics=candidate.quality.to_dict(),
                    )
                )
            manifest = CuratedImageManifest(
                run_id=run_id,
                input_manifest_sha256=input_manifest_sha256,
                selector_version=result.selector_version,
                selector_fingerprint=result.selector_fingerprint,
                entries=tuple(entries),
            )
            manifest_sha256 = manifest.checksum_sha256
            manifest_path = pending_root / OUTPUT_MANIFEST_FILE
            _write_and_fsync(manifest_path, manifest.canonical_bytes)
            verify_curated_image_manifest(
                pending_root,
                expected_manifest_sha256=manifest_sha256,
                expected_run_id=run_id,
            )
            if self._before_commit is not None:
                self._before_commit(pending_root)
            final_root = self._exports_root / manifest_sha256
            final_root.parent.mkdir(parents=True, exist_ok=True)
            if final_root.exists():
                verify_curated_image_manifest(
                    final_root,
                    expected_manifest_sha256=manifest_sha256,
                    expected_run_id=run_id,
                )
                shutil.rmtree(pending_root, ignore_errors=True)
            else:
                try:
                    pending_root.replace(final_root)
                except OSError:
                    if not final_root.exists():
                        raise
                    verify_curated_image_manifest(
                        final_root,
                        expected_manifest_sha256=manifest_sha256,
                        expected_run_id=run_id,
                    )
                    shutil.rmtree(pending_root, ignore_errors=True)
            manifest_relative_path = _relative_to_artifact(
                final_root / OUTPUT_MANIFEST_FILE,
                self._artifact_root,
            )
            return PublishedImageSelection(
                manifest=manifest,
                manifest_sha256=manifest_sha256,
                manifest_relative_path=manifest_relative_path,
                output_directory=final_root,
            )
        except BaseException:
            shutil.rmtree(pending_root, ignore_errors=True)
            raise


def verify_curated_image_manifest(
    output_directory: Path,
    *,
    expected_manifest_sha256: str,
    expected_run_id: UUID | None = None,
) -> CuratedImageManifest:
    _validate_sha256(expected_manifest_sha256)
    root = output_directory.resolve(strict=True)
    manifest_path = root / OUTPUT_MANIFEST_FILE
    try:
        content = manifest_path.read_bytes()
        value = cast(dict[str, Any], json.loads(content))
    except (OSError, json.JSONDecodeError, TypeError) as error:
        raise SelectionContractError(
            "IMAGE_SELECTION_MANIFEST_MISMATCH",
            "The curated output manifest cannot be read.",
        ) from error
    if hashlib.sha256(content).hexdigest() != expected_manifest_sha256:
        _fail("IMAGE_SELECTION_MANIFEST_MISMATCH", "Output manifest checksum changed.")
    try:
        if (
            value["contract"] != OUTPUT_MANIFEST_CONTRACT
            or int(value["schemaVersion"]) != OUTPUT_MANIFEST_SCHEMA_VERSION
        ):
            raise ValueError
        run_id = UUID(str(value["runId"]))
        entries = tuple(_entry_from_dict(cast(dict[str, Any], item)) for item in value["entries"])
        manifest = CuratedImageManifest(
            run_id=run_id,
            input_manifest_sha256=str(value["inputManifestSha256"]),
            selector_version=str(value["selectorVersion"]),
            selector_fingerprint=str(value["selectorFingerprint"]),
            entries=entries,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise SelectionContractError(
            "IMAGE_SELECTION_MANIFEST_MISMATCH",
            "The curated output manifest has an invalid contract.",
        ) from error
    if expected_run_id is not None and manifest.run_id != expected_run_id:
        _fail("IMAGE_SELECTION_MANIFEST_MISMATCH", "Output manifest belongs to another run.")
    if manifest.canonical_bytes != content:
        _fail("IMAGE_SELECTION_MANIFEST_MISMATCH", "Output manifest is not canonical JSON.")
    seen_ranges: set[tuple[int, int]] = set()
    expected_files = {OUTPUT_MANIFEST_FILE}
    for entry in manifest.entries:
        key = (entry.range_start, entry.range_end)
        if key in seen_ranges:
            _fail("IMAGE_SELECTION_RANGE_CONFLICT", "Output manifest repeats a sequence range.")
        seen_ranges.add(key)
        image_path = _safe_child(root, entry.output_relative_path)
        if _sha256_file(image_path) != entry.output_checksum_sha256:
            _fail("IMAGE_SELECTION_MANIFEST_MISMATCH", "A curated image checksum changed.")
        if image_path.stat().st_size != entry.size_bytes:
            _fail("IMAGE_SELECTION_MANIFEST_MISMATCH", "A curated image size changed.")
        try:
            dimensions = read_jpeg_dimensions(image_path)
        except ImageFileError as error:
            raise SelectionContractError(
                "IMAGE_SELECTION_MANIFEST_MISMATCH",
                "A curated image is no longer a readable JPEG.",
            ) from error
        if dimensions != (entry.width, entry.height):
            _fail("IMAGE_SELECTION_MANIFEST_MISMATCH", "Curated image dimensions changed.")
        expected_files.add(entry.output_relative_path)
    actual_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }
    if actual_files != expected_files:
        _fail("IMAGE_SELECTION_MANIFEST_MISMATCH", "Output directory differs from manifest.")
    return manifest


def _entry_from_dict(value: dict[str, Any]) -> CuratedImageEntry:
    entry = CuratedImageEntry(
        range_start=int(value["rangeStart"]),
        range_end=int(value["rangeEnd"]),
        source_order_index=int(value["sourceOrderIndex"]),
        source_relative_path=_safe_relative_path(str(value["sourceRelativePath"])),
        source_checksum_sha256=str(value["sourceChecksumSha256"]),
        output_relative_path=_safe_relative_path(str(value["outputRelativePath"])),
        output_checksum_sha256=str(value["outputChecksumSha256"]),
        size_bytes=int(value["sizeBytes"]),
        width=int(value["width"]),
        height=int(value["height"]),
        quality_metrics={
            str(key): float(metric)
            for key, metric in cast(dict[str, Any], value["qualityMetrics"]).items()
        },
    )
    if (
        entry.range_start < 1
        or entry.range_end < entry.range_start
        or entry.source_order_index < 0
        or entry.size_bytes < 1
        or entry.width < 1
        or entry.height < 1
    ):
        raise ValueError
    _validate_sha256(entry.source_checksum_sha256)
    _validate_sha256(entry.output_checksum_sha256)
    return entry


def _safe_relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in value
        or (path.parts and ":" in path.parts[0])
    ):
        raise ValueError
    return path.as_posix()


def _safe_child(root: Path, relative_path: str) -> Path:
    try:
        normalized = _safe_relative_path(relative_path)
        child = (root / Path(*PurePosixPath(normalized).parts)).resolve(strict=True)
    except (OSError, ValueError) as error:
        raise SelectionContractError(
            "IMAGE_SELECTION_MANIFEST_MISMATCH",
            "A curated image path is missing or unsafe.",
        ) from error
    if not child.is_relative_to(root) or not child.is_file():
        _fail("IMAGE_SELECTION_MANIFEST_MISMATCH", "A curated image path is unsafe.")
    return child


def _copy_and_fsync(source: Path, destination: Path) -> None:
    with source.open("rb") as input_file, destination.open("xb") as output_file:
        shutil.copyfileobj(input_file, output_file, length=1024 * 1024)
        output_file.flush()
        os.fsync(output_file.fileno())


def _write_and_fsync(destination: Path, content: bytes) -> None:
    with destination.open("xb") as output:
        output.write(content)
        output.flush()
        os.fsync(output.fileno())


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise SelectionContractError(
            "IMAGE_SELECTION_MANIFEST_MISMATCH",
            "A curated image cannot be read.",
        ) from error
    return digest.hexdigest()


def _relative_to_artifact(path: Path, artifact_root: Path) -> str:
    try:
        return path.resolve(strict=True).relative_to(artifact_root).as_posix()
    except (OSError, ValueError) as error:
        raise SelectionContractError(
            "IMAGE_SELECTION_OUTPUT_INVALID",
            "Curated output escaped the managed artifact root.",
        ) from error


def _validate_sha256(value: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        _fail("IMAGE_SELECTION_MANIFEST_MISMATCH", "Expected a lowercase SHA-256 value.")


def _fail(code: str, message: str) -> NoReturn:
    raise SelectionContractError(code, message)


__all__ = [
    "CuratedImageEntry",
    "CuratedImageManifest",
    "CuratedImageOutputPublisher",
    "PublishedImageSelection",
    "verify_curated_image_manifest",
]
