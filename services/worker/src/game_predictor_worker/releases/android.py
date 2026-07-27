"""Controlled Windows Android build with immutable artifact publication."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from collections.abc import Callable, Sequence
from pathlib import Path

from game_predictor_worker.releases.contracts import (
    AndroidReleaseArtifact,
    AndroidReleaseBuildSpec,
)
from game_predictor_worker.snapshots import validate_snapshot_artifact

_SEMANTIC_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")


class AndroidReleaseError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class PowerShellAndroidReleaseBuilder:
    def __init__(
        self,
        repository_root: Path,
        artifact_root: Path,
        *,
        command_runner: Callable[[Sequence[str], Path], None] | None = None,
    ) -> None:
        self._repository_root = repository_root.resolve()
        self._artifact_root = artifact_root.resolve()
        self._command_runner = command_runner

    def build(
        self,
        spec: AndroidReleaseBuildSpec,
        *,
        heartbeat: Callable[[], None] | None = None,
    ) -> AndroidReleaseArtifact:
        snapshot = validate_snapshot_artifact(spec.snapshot.directory)
        if snapshot != spec.snapshot:
            raise AndroidReleaseError(
                "ANDROID_SNAPSHOT_CHANGED",
                "The snapshot changed before the Android build.",
            )
        if snapshot.manifest.release_version != spec.release_version:
            raise AndroidReleaseError(
                "ANDROID_RELEASE_VERSION_MISMATCH",
                "The Android release version does not match the snapshot.",
            )
        if not 1 <= spec.version_code <= 2_100_000_000:
            raise AndroidReleaseError(
                "ANDROID_VERSION_CODE_INVALID",
                "Android versionCode is outside the supported range.",
            )

        mobile_snapshot = self._repository_root / "apps" / "mobile" / "assets" / "snapshot"
        database_target = mobile_snapshot / "m1-snapshot.db"
        manifest_target = mobile_snapshot / "manifest.json"
        if not database_target.is_file() or not manifest_target.is_file():
            raise AndroidReleaseError(
                "ANDROID_ASSET_BASELINE_MISSING",
                "The mobile snapshot baseline files are missing.",
            )

        staging_root = self._artifact_root / ".android-build"
        staging_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="release-",
            dir=staging_root,
        ) as temporary_name:
            backup = Path(temporary_name)
            database_backup = backup / database_target.name
            manifest_backup = backup / manifest_target.name
            shutil.copy2(database_target, database_backup)
            shutil.copy2(manifest_target, manifest_backup)
            try:
                shutil.copy2(snapshot.database_path, database_target)
                shutil.copy2(snapshot.manifest_path, manifest_target)
                source_apk = self._build_and_verify(
                    spec,
                    snapshot_sha256=snapshot.manifest.snapshot_file_sha256,
                    heartbeat=heartbeat,
                )
                apk_sha256 = _file_sha256(source_apk)
                final_apk = (
                    self._artifact_root
                    / "android-releases"
                    / spec.release_version
                    / f"app-release-{apk_sha256}.apk"
                )
                _publish_immutable(source_apk, final_apk, apk_sha256)
                _require_snapshot_in_apk(
                    final_apk,
                    release_version=spec.release_version,
                    snapshot_sha256=snapshot.manifest.snapshot_file_sha256,
                )
                return AndroidReleaseArtifact(
                    apk_path=final_apk,
                    apk_sha256=apk_sha256,
                    snapshot_sha256=snapshot.manifest.snapshot_file_sha256,
                )
            finally:
                # Restore the bytes in place. Replacing the destination file would
                # also replace its Windows owner and ACL with those of the temporary
                # backup, making the next non-elevated build unable to read it.
                shutil.copyfile(database_backup, database_target)
                shutil.copyfile(manifest_backup, manifest_target)

    def _build_and_verify(
        self,
        spec: AndroidReleaseBuildSpec,
        *,
        snapshot_sha256: str,
        heartbeat: Callable[[], None] | None,
    ) -> Path:
        version_name = _android_version_name(spec.release_version)
        build_script = self._repository_root / "scripts" / "build_android_debug.ps1"
        verify_script = self._repository_root / "scripts" / "verify_android_apk.ps1"
        source_apk = (
            self._repository_root
            / "apps"
            / "mobile"
            / "android"
            / "app"
            / "build"
            / "outputs"
            / "apk"
            / "release"
            / "app-release.apk"
        )
        try:
            self._run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(build_script),
                    "-Variant",
                    "Release",
                    "-Architectures",
                    "arm64-v8a",
                    "-VersionName",
                    version_name,
                    "-VersionCode",
                    str(spec.version_code),
                ],
                self._repository_root,
                heartbeat=heartbeat,
            )
            if not source_apk.is_file():
                raise AndroidReleaseError(
                    "ANDROID_APK_MISSING",
                    "Gradle completed without producing the expected release APK.",
                )
            _require_snapshot_in_apk(
                source_apk,
                release_version=spec.release_version,
                snapshot_sha256=snapshot_sha256,
            )
            self._run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(verify_script),
                    "-ApkPath",
                    str(source_apk.relative_to(self._repository_root)),
                ],
                self._repository_root,
                heartbeat=heartbeat,
            )
        except AndroidReleaseError:
            raise
        except (OSError, subprocess.CalledProcessError) as error:
            raise AndroidReleaseError(
                "ANDROID_BUILD_FAILED",
                "The controlled Android release build or verification failed.",
            ) from error
        return source_apk

    def _run(
        self,
        command: Sequence[str],
        cwd: Path,
        *,
        heartbeat: Callable[[], None] | None,
    ) -> None:
        if self._command_runner is not None:
            self._command_runner(command, cwd)
            return
        _run_command(command, cwd, heartbeat=heartbeat)


def _run_command(
    command: Sequence[str],
    cwd: Path,
    *,
    heartbeat: Callable[[], None] | None = None,
    heartbeat_interval_seconds: float = 15.0,
) -> None:
    if heartbeat_interval_seconds <= 0:
        raise ValueError("heartbeat_interval_seconds must be positive.")
    process = subprocess.Popen(
        list(command),
        cwd=cwd,
        stdin=subprocess.DEVNULL,
    )
    try:
        while True:
            try:
                return_code = process.wait(timeout=heartbeat_interval_seconds)
                break
            except subprocess.TimeoutExpired:
                if heartbeat is not None:
                    heartbeat()
    except BaseException:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        raise
    if return_code != 0:
        raise subprocess.CalledProcessError(return_code, list(command))


def _android_version_name(release_version: str) -> str:
    if _SEMANTIC_VERSION.fullmatch(release_version):
        return release_version
    suffix = release_version.replace("_", "-")
    return f"0.0.0-release.{suffix}"


def _publish_immutable(
    source: Path,
    destination: Path,
    expected_sha256: str,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if not destination.is_file() or _file_sha256(destination) != expected_sha256:
            raise AndroidReleaseError(
                "ANDROID_ARTIFACT_COLLISION",
                "An existing Android artifact has different content.",
            )
        return
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    try:
        shutil.copy2(source, temporary)
        if _file_sha256(temporary) != expected_sha256:
            raise AndroidReleaseError(
                "ANDROID_ARTIFACT_COPY_FAILED",
                "The copied Android artifact checksum changed.",
            )
        try:
            os.link(temporary, destination)
        except FileExistsError as error:
            if _file_sha256(destination) != expected_sha256:
                raise AndroidReleaseError(
                    "ANDROID_ARTIFACT_COLLISION",
                    "An existing Android artifact has different content.",
                ) from error
    finally:
        temporary.unlink(missing_ok=True)


def _require_snapshot_in_apk(
    apk_path: Path,
    *,
    release_version: str,
    snapshot_sha256: str,
) -> None:
    try:
        with zipfile.ZipFile(apk_path) as archive:
            bundle = archive.read("assets/index.android.bundle")
            if release_version.encode("utf-8") not in bundle:
                raise AndroidReleaseError(
                    "ANDROID_RELEASE_VERSION_MISSING",
                    "The APK bundle does not contain the release version.",
                )
            if snapshot_sha256.encode("ascii") not in bundle:
                raise AndroidReleaseError(
                    "ANDROID_SNAPSHOT_CHECKSUM_MISSING",
                    "The APK bundle does not contain the snapshot checksum.",
                )
            matching = False
            for name in archive.namelist():
                if not name.endswith(".db"):
                    continue
                with archive.open(name) as database:
                    digest = hashlib.sha256()
                    for chunk in iter(
                        lambda: database.read(1024 * 1024),
                        b"",
                    ):
                        digest.update(chunk)
                    checksum = digest.hexdigest()
                if checksum == snapshot_sha256:
                    matching = True
                    break
            if not matching:
                raise AndroidReleaseError(
                    "ANDROID_SNAPSHOT_MISMATCH",
                    "The APK does not contain the exact release snapshot.",
                )
    except AndroidReleaseError:
        raise
    except (KeyError, OSError, zipfile.BadZipFile) as error:
        raise AndroidReleaseError(
            "ANDROID_APK_INVALID",
            "The release APK is not a readable standalone archive.",
        ) from error


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
