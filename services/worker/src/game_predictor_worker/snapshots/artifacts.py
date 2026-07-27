"""Immutable publication of validated production snapshot artifacts."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from game_predictor_worker.snapshots.contracts import ProductionSnapshotSpec
from game_predictor_worker.snapshots.generator import ProductionSnapshotGenerator
from game_predictor_worker.snapshots.manifest import (
    SNAPSHOT_DATABASE_FILE,
    SNAPSHOT_MANIFEST_FILE,
    SnapshotArtifactError,
    SnapshotArtifactManifest,
    build_snapshot_manifest,
)
from game_predictor_worker.snapshots.validator import (
    SnapshotArtifact,
    validate_snapshot_artifact,
)


class ProductionSnapshotArtifactPublisher:
    def __init__(
        self,
        generator: ProductionSnapshotGenerator,
        artifact_root: Path,
    ) -> None:
        self._generator = generator
        self._artifact_root = artifact_root

    def publish(self, spec: ProductionSnapshotSpec) -> SnapshotArtifact:
        self._artifact_root.mkdir(parents=True, exist_ok=True)
        artifact_root = self._artifact_root.resolve()
        staging_root = artifact_root / ".staging"
        staging_root.mkdir(parents=True, exist_ok=True)
        staging_directory = Path(
            tempfile.mkdtemp(
                prefix="snapshot-",
                dir=staging_root,
            )
        )
        try:
            result = self._generator.generate(
                staging_directory / SNAPSHOT_DATABASE_FILE,
                spec,
            )
            manifest = build_snapshot_manifest(result)
            manifest_path = staging_directory / SNAPSHOT_MANIFEST_FILE
            try:
                with manifest_path.open("xb") as file:
                    file.write(manifest.to_bytes())
            except OSError as error:
                raise SnapshotArtifactError(
                    "SNAPSHOT_MANIFEST_WRITE_FAILED",
                    "The snapshot manifest could not be written.",
                ) from error

            validate_snapshot_artifact(
                staging_directory,
                enforce_final_layout=False,
            )
            final_directory = (
                artifact_root
                / "snapshots"
                / manifest.release_version
                / manifest.logical_content_sha256
            )
            _require_within_root(final_directory, artifact_root)
            final_directory.parent.mkdir(parents=True, exist_ok=True)
            if final_directory.exists():
                return _reuse_existing(final_directory, manifest)
            try:
                os.rename(staging_directory, final_directory)
            except FileExistsError:
                return _reuse_existing(final_directory, manifest)
            except OSError as error:
                if final_directory.exists():
                    return _reuse_existing(final_directory, manifest)
                raise SnapshotArtifactError(
                    "SNAPSHOT_ARTIFACT_PUBLISH_FAILED",
                    "The validated snapshot artifact could not be published.",
                ) from error
            return validate_snapshot_artifact(final_directory)
        finally:
            if staging_directory.exists():
                _remove_staging_directory(staging_directory, staging_root)


def _reuse_existing(
    final_directory: Path,
    expected_manifest: SnapshotArtifactManifest,
) -> SnapshotArtifact:
    try:
        artifact = validate_snapshot_artifact(final_directory)
    except SnapshotArtifactError as error:
        raise SnapshotArtifactError(
            "SNAPSHOT_ARTIFACT_COLLISION",
            "An existing artifact at the immutable path is not valid.",
        ) from error
    if artifact.manifest != expected_manifest:
        raise SnapshotArtifactError(
            "SNAPSHOT_ARTIFACT_COLLISION",
            "An existing artifact at the immutable path has different metadata.",
        )
    return artifact


def _require_within_root(path: Path, root: Path) -> None:
    resolved_parent = path.parent.resolve()
    if root != resolved_parent and root not in resolved_parent.parents:
        raise SnapshotArtifactError(
            "SNAPSHOT_ARTIFACT_PATH_INVALID",
            "The snapshot artifact path escapes the configured root.",
        )


def _remove_staging_directory(path: Path, staging_root: Path) -> None:
    resolved_path = path.resolve()
    resolved_root = staging_root.resolve()
    if resolved_root not in resolved_path.parents:
        raise SnapshotArtifactError(
            "SNAPSHOT_STAGING_PATH_INVALID",
            "Refusing to clean a staging path outside the artifact root.",
        )
    shutil.rmtree(resolved_path)
