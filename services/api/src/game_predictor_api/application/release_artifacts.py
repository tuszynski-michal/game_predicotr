"""Controlled read access to immutable mobile release artifacts."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from game_predictor_api.domain.mobile_releases import (
    MobileRelease,
    MobileReleaseConflictError,
    MobileReleaseStatus,
)


@dataclass(frozen=True, slots=True)
class MobileReleaseApkArtifact:
    path: Path
    download_name: str


def resolve_mobile_release_apk(
    release: MobileRelease,
    artifact_root: Path,
) -> MobileReleaseApkArtifact:
    if (
        release.status is not MobileReleaseStatus.READY
        or release.apk_path is None
        or release.apk_checksum is None
    ):
        raise MobileReleaseConflictError(
            "MOBILE_RELEASE_APK_NOT_READY",
            "The verified APK is not available for this mobile release.",
            details={"mobileReleaseId": str(release.id)},
        )

    root = artifact_root.resolve()
    relative_path = PurePosixPath(release.apk_path)
    unresolved_candidate = root.joinpath(*relative_path.parts)
    cursor = root
    contains_symlink = False
    for part in relative_path.parts:
        cursor = cursor / part
        contains_symlink = contains_symlink or cursor.is_symlink()
    candidate = unresolved_candidate.resolve()
    if (
        not candidate.is_relative_to(root)
        or candidate.suffix.lower() != ".apk"
        or not candidate.is_file()
        or contains_symlink
    ):
        raise MobileReleaseConflictError(
            "MOBILE_RELEASE_APK_UNAVAILABLE",
            "The persisted APK artifact is unavailable.",
            details={"mobileReleaseId": str(release.id)},
        )

    checksum = _sha256(candidate)
    if checksum != release.apk_checksum:
        raise MobileReleaseConflictError(
            "MOBILE_RELEASE_APK_CHECKSUM_MISMATCH",
            "The persisted APK artifact no longer matches the release checksum.",
            details={"mobileReleaseId": str(release.id)},
        )

    return MobileReleaseApkArtifact(
        path=candidate,
        download_name=f"game-predictor-{release.version}.apk",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
