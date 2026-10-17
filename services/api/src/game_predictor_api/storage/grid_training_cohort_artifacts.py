"""Bounded, content-addressed files published before their database receipts."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID, uuid4

from game_predictor_api.domain.canonical_source import (
    CANONICAL_SOURCE_LOADER_VERSION,
    CanonicalSourceFrame,
    CanonicalSourceLoadError,
    decode_canonical_source_bytes,
)
from game_predictor_api.domain.grid_training_cohorts import (
    SOURCE_BYTE_LIMIT,
    GridCohortError,
    canonical,
)

CHUNK = 1024 * 1024
HARD_RESERVE = 5 * 1024**3


def _native_io(path: Path) -> Path:
    if os.name != "nt":
        return path
    value = str(path)
    if value.startswith("\\\\?\\"):
        return path
    return Path("\\\\?\\UNC\\" + value[2:] if value.startswith("\\\\") else "\\\\?\\" + value)


class GridCohortArtifactStore:
    def __init__(self, artifact_root: Path) -> None:
        original = artifact_root.absolute()
        if any(
            _native_io(path).is_symlink() or _native_io(path).is_junction()
            for path in (original, *original.parents)
        ):
            raise GridCohortError("GRID_COHORT_PATH_UNSAFE", "Linked artifact roots are forbidden.")
        self.root = original.resolve()

    def safe(self, relative: str) -> Path:
        value = PurePosixPath(relative)
        if value.is_absolute() or ".." in value.parts or "\\" in relative or ":" in relative:
            raise GridCohortError("GRID_COHORT_PATH_UNSAFE", "Invalid managed artifact path.")
        candidate = self.root.joinpath(*value.parts)
        for item in (candidate, *candidate.parents):
            if item == self.root.parent:
                break
            native = _native_io(item)
            if native.is_symlink() or native.is_junction():
                raise GridCohortError("GRID_COHORT_PATH_UNSAFE", "Linked artifacts are forbidden.")
        if not candidate.resolve().is_relative_to(self.root):
            raise GridCohortError("GRID_COHORT_PATH_UNSAFE", "Artifact leaves managed storage.")
        return _native_io(candidate)

    def _directory(self, game: UUID, cohort: UUID) -> str:
        return f"data/grid-training-cohorts/{game}/{cohort}"

    def verify(self, relative: str, expected: str, *, size: int | None = None) -> Path:
        path = self.safe(relative)
        if not path.is_file() or (size is not None and path.stat().st_size != size):
            raise GridCohortError(
                "DATASET_ASSET_UNAVAILABLE", "The immutable artifact is unavailable."
            )
        actual = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(CHUNK):
                actual.update(chunk)
        if actual.hexdigest() != expected:
            raise GridCohortError("CHECKSUM_MISMATCH", "The immutable artifact changed.")
        return path

    def read_json(self, relative: str, expected: str) -> dict[str, Any]:
        path = self.verify(relative, expected)
        if path.stat().st_size > 16 * 1024 * 1024:
            raise GridCohortError(
                "GRID_COHORT_METADATA_TOO_LARGE", "Metadata page exceeds its bound."
            )
        value = json.loads(path.read_bytes())
        if not isinstance(value, dict):
            raise GridCohortError("GRID_COHORT_MANIFEST_INVALID", "Expected an object manifest.")
        return value

    def _publish(self, directory: str, suffix: str, chunks: Iterable[bytes]) -> dict[str, Any]:
        destination = self.safe(directory)
        destination.mkdir(parents=True, exist_ok=True)
        temporary = destination / f".tmp-{uuid4().hex}.part"
        checksum, size = hashlib.sha256(), 0
        try:
            with temporary.open("xb") as output:
                for chunk in chunks:
                    if shutil.disk_usage(destination).free - len(chunk) < HARD_RESERVE:
                        raise GridCohortError(
                            "GRID_COHORT_STORAGE_LOW", "Managed storage reserve is required."
                        )
                    output.write(chunk)
                    checksum.update(chunk)
                    size += len(chunk)
                output.flush()
                os.fsync(output.fileno())
            sha = checksum.hexdigest()
            relative = f"{directory}/{sha}.{suffix}"
            target = self.safe(relative)
            if target.exists():
                self.verify(relative, sha, size=size)
            else:
                # The name includes the complete content hash. Concurrent identical
                # publishers can only publish the same verified immutable bytes.
                # Windows rename still requires the extended-length spelling
                # when a content hash makes the final path exceed MAX_PATH.
                os.replace(temporary, target)
            if os.name != "nt":
                descriptor = os.open(destination, os.O_RDONLY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            self.verify(relative, sha, size=size)
            return {"path": relative, "sha256": sha, "bytes": size}
        finally:
            temporary.unlink(missing_ok=True)

    def publish_json(self, game: UUID, cohort: UUID, value: object) -> dict[str, Any]:
        return self._publish(self._directory(game, cohort) + "/pages", "json", [canonical(value)])

    def publish_index(
        self, game: UUID, cohort: UUID, pages: Iterable[dict[str, Any]]
    ) -> dict[str, Any]:
        return self._publish(
            self._directory(game, cohort) + "/indexes",
            "jsonl",
            (canonical(page) + b"\n" for page in pages),
        )

    def decode_source(self, source: dict[str, Any]) -> tuple[CanonicalSourceFrame, bytes]:
        relative = source["relative_path"]
        path = self.safe("data/" + relative)
        if not path.is_file():
            from game_predictor_worker.images.normalization import managed_original_is_cropped

            # D-562: geometry training needs the whole frame, never a crop canvas.
            if managed_original_is_cropped(path, source["checksum_sha256"]):
                raise GridCohortError(
                    "SOURCE_ORIGINAL_CROPPED",
                    "The selected original was replaced by its crop; cohorts need the full frame.",
                )
            raise GridCohortError(
                "SOURCE_BYTES_UNAVAILABLE", "The selected original is unavailable."
            )
        if path.stat().st_size > SOURCE_BYTE_LIMIT:
            raise GridCohortError("SOURCE_BYTE_LIMIT", "The selected source exceeds 64 MiB.")
        # A bounded read handles a file growing after stat; the hash and JPEG
        # decoder consume precisely these bytes, never a second version.
        with path.open("rb") as stream:
            content = stream.read(SOURCE_BYTE_LIMIT + 1)
        if len(content) > SOURCE_BYTE_LIMIT:
            raise GridCohortError("SOURCE_BYTE_LIMIT", "The selected source exceeds 64 MiB.")
        try:
            frame = decode_canonical_source_bytes(
                content, expected_source_checksum_sha256=source["checksum_sha256"]
            )
        except CanonicalSourceLoadError as error:
            raise GridCohortError(error.code, str(error)) from error
        return frame, content

    def copy_source(self, game: UUID, cohort: UUID, source: dict[str, Any]) -> dict[str, Any]:
        # Both large locals die before the next source is decoded. Returning only
        # immutable metadata prevents the five-source page from retaining frames.
        frame, content = self.decode_source(source)
        normalized = frame.source
        if (
            normalized.normalized_pixel_checksum_sha256
            != source["normalized_pixel_checksum_sha256"]
            or normalized.normalization_adapter_version != source["normalization_adapter_version"]
            or normalized.normalization_adapter_version != CANONICAL_SOURCE_LOADER_VERSION
            or (normalized.width, normalized.height)
            != (source["oriented_width"], source["oriented_height"])
            or normalized.exif_orientation != source["exif_orientation"]
        ):
            raise GridCohortError("SOURCE_PIXEL_MISMATCH", "Canonical source metadata differs.")
        return self._publish(self._directory(game, cohort) + "/originals", "jpg", [content])
