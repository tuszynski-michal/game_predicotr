"""Typed ports for the release workflow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID

from game_predictor_api.domain.mobile_releases import MobileRelease

from game_predictor_worker.snapshots.validator import SnapshotArtifact


@dataclass(frozen=True, slots=True)
class AndroidReleaseBuildSpec:
    release_version: str
    version_code: int
    snapshot: SnapshotArtifact


@dataclass(frozen=True, slots=True)
class AndroidReleaseArtifact:
    apk_path: Path
    apk_sha256: str
    snapshot_sha256: str


class AndroidReleaseBuilder(Protocol):
    def build(
        self,
        spec: AndroidReleaseBuildSpec,
    ) -> AndroidReleaseArtifact: ...


class ReleaseWorkflowStore(Protocol):
    def load_release(self, mobile_release_id: UUID) -> MobileRelease | None: ...

    def require_current_sources(self, release: MobileRelease) -> None: ...

    def mark_building(
        self,
        mobile_release_id: UUID,
        *,
        build_job_id: UUID,
    ) -> MobileRelease: ...

    def record_snapshot(
        self,
        mobile_release_id: UUID,
        *,
        build_job_id: UUID,
        relative_path: str,
        checksum: str,
    ) -> MobileRelease: ...

    def mark_ready(
        self,
        mobile_release_id: UUID,
        *,
        build_job_id: UUID,
        apk_relative_path: str,
        apk_checksum: str,
    ) -> MobileRelease: ...

    def mark_failed(
        self,
        mobile_release_id: UUID,
        *,
        build_job_id: UUID,
    ) -> MobileRelease: ...
