"""Controlled local-folder selection for image import jobs."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path, PurePosixPath
from secrets import token_urlsafe
from threading import Lock
from uuid import UUID, uuid4

from game_predictor_worker.images.image_file import ImageFileError, read_jpeg_dimensions
from game_predictor_worker.images.pipeline_contract import (
    current_pipeline_manifest,
    pipeline_fingerprint,
)

from game_predictor_api.application.image_selections import ImageSelectionService
from game_predictor_api.application.jobs import JobService
from game_predictor_api.domain.image_selections import ImageSelectionRun
from game_predictor_api.domain.jobs import Job, JobConflictError, JobError

SUPPORTED_IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg"})
SELECTION_TTL = timedelta(minutes=15)
BROWSER_UPLOAD_TTL = timedelta(hours=24)
MAX_PREFLIGHT_FILES = 1_000_000
MAX_PHOTO_SELECTION_FILES = 30_000
MIN_FREE_SPACE_RESERVE_BYTES = 512 * 1024 * 1024
IMAGE_RELATIVE_PATH_HEADER = "X-Image-Relative-Path"
UPLOAD_STATE_FILE_NAME = "_upload_state.json"
UPLOAD_MANIFEST_FILE_NAME = "_browser_manifest.json"
UPLOAD_METRICS_FILE_NAME = "_upload_metrics.json"


class ImageSelectionPurpose(StrEnum):
    LAYOUT_IMPORT = "layout_import"
    PHOTO_SELECTION = "photo_selection"


@dataclass(frozen=True, slots=True)
class SelectedImageFolder:
    selection_token: str
    selection_id: UUID
    path: Path
    supported_file_count: int
    expires_at: datetime
    display_name: str
    purpose: ImageSelectionPurpose = ImageSelectionPurpose.LAYOUT_IMPORT
    game_id: UUID | None = None
    input_manifest_sha256: str | None = None
    image_selection_run_id: UUID | None = None
    managed: bool = False


@dataclass(slots=True)
class BrowserImageUpload:
    upload_id: UUID
    path: Path
    display_name: str
    purpose: ImageSelectionPurpose
    game_id: UUID | None
    expected_file_count: int
    expected_total_bytes: int
    created_at: datetime
    uploaded_indexes: set[int]
    uploaded_files: dict[int, BrowserUploadedFile]
    uploaded_bytes: int = 0


@dataclass(frozen=True, slots=True)
class BrowserUploadedFile:
    file_index: int
    relative_path: str
    stored_file_name: str
    size_bytes: int
    checksum_sha256: str


class WindowsFolderPicker:
    """Invoke one fixed PowerShell helper; no caller-controlled command exists."""

    def __init__(self, script_path: Path, *, timeout_seconds: int = 120) -> None:
        self._script_path = script_path.resolve()
        self._timeout_seconds = timeout_seconds

    def choose(self) -> Path | None:
        if os.name != "nt":
            raise JobError(
                "IMAGE_FOLDER_PICKER_UNAVAILABLE",
                "The native folder picker is available only on local Windows.",
            )
        if not self._script_path.is_file():
            raise JobError(
                "IMAGE_FOLDER_PICKER_UNAVAILABLE",
                "The controlled folder picker helper is missing.",
            )
        startup_info = subprocess.STARTUPINFO()
        startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup_info.wShowWindow = 1  # SW_SHOWNORMAL; override a hidden API parent.
        try:
            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-STA",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(self._script_path),
                ],
                check=False,
                capture_output=True,
                encoding="utf-8-sig",
                errors="strict",
                shell=False,
                startupinfo=startup_info,
                timeout=self._timeout_seconds,
            )
        except subprocess.TimeoutExpired as error:
            raise JobError(
                "IMAGE_FOLDER_PICKER_TIMEOUT",
                "Folder selection exceeded the controlled time limit.",
            ) from error
        except OSError as error:
            raise JobError(
                "IMAGE_FOLDER_PICKER_UNAVAILABLE",
                "The native folder picker could not be started.",
            ) from error
        if result.returncode != 0:
            raise JobError(
                "IMAGE_FOLDER_PICKER_FAILED",
                "The native folder picker failed.",
            )
        try:
            payload = json.loads(result.stdout.strip())
        except json.JSONDecodeError as error:
            raise JobError(
                "IMAGE_FOLDER_PICKER_FAILED",
                "The native folder picker returned an invalid result.",
            ) from error
        if payload == {"status": "cancelled"}:
            return None
        if not isinstance(payload, dict) or not isinstance(payload.get("path"), str):
            raise JobError(
                "IMAGE_FOLDER_PICKER_FAILED",
                "The native folder picker returned an invalid result.",
            )
        return Path(payload["path"])


class ImageFolderSelectionService:
    """Keep short-lived approved paths outside browser-controlled payloads."""

    def __init__(
        self,
        picker: WindowsFolderPicker | Callable[[], Path | None],
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._picker = picker.choose if isinstance(picker, WindowsFolderPicker) else picker
        self._clock = clock or (lambda: datetime.now(UTC))
        self._selections: dict[str, SelectedImageFolder] = {}
        self._lock = Lock()
        self._picker_lock = Lock()

    def select(self) -> SelectedImageFolder | None:
        if not self._picker_lock.acquire(blocking=False):
            raise JobConflictError(
                "IMAGE_FOLDER_PICKER_ALREADY_OPEN",
                "A folder selection window is already open.",
            )
        try:
            path = self._picker()
        finally:
            self._picker_lock.release()
        return None if path is None else self.approve(path)

    def approve(
        self,
        path: Path,
        *,
        display_name: str | None = None,
        purpose: ImageSelectionPurpose = ImageSelectionPurpose.LAYOUT_IMPORT,
        game_id: UUID | None = None,
        input_manifest_sha256: str | None = None,
        image_selection_run_id: UUID | None = None,
        selection_id: UUID | None = None,
        managed: bool = False,
    ) -> SelectedImageFolder:
        resolved, count = inspect_image_folder(path)
        if purpose is ImageSelectionPurpose.PHOTO_SELECTION and (
            game_id is None or input_manifest_sha256 is None
        ):
            raise JobError(
                "IMAGE_SELECTION_SOURCE_PURPOSE_INVALID",
                "Photo-selection staging requires a game and an input manifest.",
            )
        now = self._clock()
        stable_selection_id = selection_id or uuid4()
        selected = SelectedImageFolder(
            selection_token=token_urlsafe(32),
            selection_id=stable_selection_id,
            path=resolved,
            supported_file_count=count,
            expires_at=now + SELECTION_TTL,
            display_name=display_name or resolved.name,
            purpose=purpose,
            game_id=game_id,
            input_manifest_sha256=input_manifest_sha256,
            image_selection_run_id=image_selection_run_id,
            managed=managed,
        )
        with self._lock:
            self._remove_expired(now)
            existing = next(
                (
                    value
                    for value in self._selections.values()
                    if value.selection_id == stable_selection_id
                ),
                None,
            )
            if existing is not None:
                if (
                    existing.path != resolved
                    or existing.purpose is not purpose
                    or existing.game_id != game_id
                    or existing.image_selection_run_id != image_selection_run_id
                ):
                    raise JobConflictError(
                        "IMAGE_FOLDER_SELECTION_CONFLICT",
                        "The stable folder selection already references another source.",
                    )
                return existing
            self._selections[selected.selection_token] = selected
        return selected

    def create_import_job(
        self,
        job_service: JobService,
        *,
        game_id: UUID,
        selection_token: str,
    ) -> Job:
        now = self._clock()
        with self._lock:
            self._remove_expired(now)
            selected = self._selections.get(selection_token)
        if selected is None:
            raise JobError(
                "IMAGE_FOLDER_SELECTION_INVALID",
                "The folder selection is missing, expired, or already used.",
            )
        if selected.purpose is not ImageSelectionPurpose.LAYOUT_IMPORT:
            raise JobError(
                "IMAGE_FOLDER_SELECTION_PURPOSE_INVALID",
                "Photo-selection staging cannot be used as a layout import.",
            )
        if selected.game_id is not None and selected.game_id != game_id:
            raise JobError(
                "IMAGE_FOLDER_SELECTION_GAME_MISMATCH",
                "The curated image selection belongs to a different game.",
            )
        resolved, _count = inspect_image_folder(selected.path)
        if resolved != selected.path:
            raise JobError(
                "IMAGE_FOLDER_SELECTION_CHANGED",
                "The selected image folder no longer resolves to the approved path.",
            )
        job = job_service.create_image_import_job(
            game_id=game_id,
            selection_id=selected.selection_id,
            source_directory=selected.path,
            source_display_name=selected.display_name,
            pipeline_fingerprint=pipeline_fingerprint(current_pipeline_manifest()),
            image_selection_run_id=selected.image_selection_run_id,
        )
        with self._lock:
            self._selections.pop(selection_token, None)
        return job

    def create_image_selection_run(
        self,
        image_selection_service: ImageSelectionService,
        *,
        game_id: UUID,
        selection_token: str,
        selector_fingerprint: str,
    ) -> tuple[ImageSelectionRun, bool]:
        now = self._clock()
        with self._lock:
            self._remove_expired(now)
            selected = self._selections.get(selection_token)
        if selected is None:
            raise JobError(
                "IMAGE_FOLDER_SELECTION_INVALID",
                "The folder selection is missing, expired, or already used.",
            )
        if (
            selected.purpose is not ImageSelectionPurpose.PHOTO_SELECTION
            or selected.game_id != game_id
            or selected.input_manifest_sha256 is None
        ):
            raise JobError(
                "IMAGE_SELECTION_SOURCE_PURPOSE_INVALID",
                "The staged folder is not approved for this game's photo selection.",
            )
        resolved, _count = inspect_image_folder(selected.path)
        if resolved != selected.path:
            raise JobError(
                "IMAGE_FOLDER_SELECTION_CHANGED",
                "The selected image folder no longer resolves to the approved path.",
            )
        run, created = image_selection_service.create_run(
            game_id=game_id,
            source_selection_id=selected.selection_id,
            input_manifest_sha256=selected.input_manifest_sha256,
            selector_fingerprint=selector_fingerprint,
        )
        with self._lock:
            self._selections.pop(selection_token, None)
        if not created and selected.managed:
            shutil.rmtree(selected.path, ignore_errors=True)
        return run, created

    def _remove_expired(self, now: datetime) -> None:
        expired = [
            (token, selection)
            for token, selection in self._selections.items()
            if selection.expires_at <= now
        ]
        for token, selection in expired:
            self._selections.pop(token, None)
            if selection.managed:
                shutil.rmtree(selection.path, ignore_errors=True)


class BrowserImageSelectionService:
    """Stage files chosen by the browser and mint the existing import token."""

    def __init__(
        self,
        selection_service: ImageFolderSelectionService,
        upload_root: Path,
        *,
        max_bytes: int,
        photo_selection_max_bytes: int | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._selection_service = selection_service
        self._upload_root = upload_root.resolve() / "browser-selections"
        self._upload_root.mkdir(parents=True, exist_ok=True)
        self._max_bytes = max_bytes
        self._photo_selection_max_bytes = photo_selection_max_bytes or max_bytes
        self._clock = clock or (lambda: datetime.now(UTC))
        self._uploads: dict[UUID, BrowserImageUpload] = {}
        self._lock = Lock()

    def begin(
        self,
        *,
        display_name: str,
        expected_file_count: int,
        expected_total_bytes: int,
        purpose: ImageSelectionPurpose = ImageSelectionPurpose.LAYOUT_IMPORT,
        game_id: UUID | None = None,
    ) -> BrowserImageUpload:
        normalized_name = display_name.strip()
        if (
            not normalized_name
            or len(normalized_name) > 200
            or "/" in normalized_name
            or "\\" in normalized_name
        ):
            raise JobError(
                "IMAGE_BROWSER_SELECTION_NAME_INVALID",
                "The selected folder name is invalid.",
            )
        max_files = (
            MAX_PHOTO_SELECTION_FILES
            if purpose is ImageSelectionPurpose.PHOTO_SELECTION
            else MAX_PREFLIGHT_FILES
        )
        if not 1 <= expected_file_count <= max_files:
            raise JobError(
                "IMAGE_BROWSER_SELECTION_COUNT_INVALID",
                f"The browser selection must contain between 1 and {max_files} files.",
            )
        max_bytes = (
            self._photo_selection_max_bytes
            if purpose is ImageSelectionPurpose.PHOTO_SELECTION
            else self._max_bytes
        )
        if not 1 <= expected_total_bytes <= max_bytes:
            raise JobError(
                "IMAGE_BROWSER_SELECTION_SIZE_INVALID",
                "The browser selection exceeds the configured import size limit.",
            )
        if purpose is ImageSelectionPurpose.PHOTO_SELECTION and game_id is None:
            raise JobError(
                "IMAGE_SELECTION_SOURCE_PURPOSE_INVALID",
                "Photo-selection staging must be scoped to one game.",
            )
        now = self._clock()
        with self._lock:
            self._remove_expired(now)
        upload_id = uuid4()
        upload_path = self._upload_root / str(upload_id)
        free_bytes = shutil.disk_usage(self._upload_root.parent).free
        if expected_total_bytes + MIN_FREE_SPACE_RESERVE_BYTES > free_bytes:
            raise JobError(
                "IMAGE_BROWSER_SELECTION_DISK_SPACE_INSUFFICIENT",
                "There is not enough free space for the staged folder.",
                details={
                    "requiredBytes": expected_total_bytes,
                    "availableBytes": max(0, free_bytes - MIN_FREE_SPACE_RESERVE_BYTES),
                },
            )
        upload_path.mkdir(parents=True, exist_ok=False)
        upload = BrowserImageUpload(
            upload_id=upload_id,
            path=upload_path,
            display_name=normalized_name,
            purpose=purpose,
            game_id=game_id,
            expected_file_count=expected_file_count,
            expected_total_bytes=expected_total_bytes,
            created_at=now,
            uploaded_indexes=set(),
            uploaded_files={},
        )
        self._write_upload_state(upload)
        with self._lock:
            self._uploads[upload_id] = upload
        return upload

    def upload_file(
        self,
        upload_id: UUID,
        file_index: int,
        *,
        relative_path: str,
        content: bytes,
    ) -> BrowserImageUpload:
        normalized_path = PurePosixPath(relative_path.replace("\\", "/"))
        if (
            normalized_path.is_absolute()
            or not normalized_path.name
            or any(part in {"", ".", ".."} for part in normalized_path.parts)
            or normalized_path.suffix.casefold() not in SUPPORTED_IMAGE_SUFFIXES
        ):
            raise JobError(
                "IMAGE_BROWSER_FILE_PATH_INVALID",
                "The browser supplied an invalid image path.",
            )
        if not content:
            raise JobError(
                "IMAGE_BROWSER_FILE_EMPTY",
                "The uploaded image file is empty.",
            )
        checksum_sha256 = hashlib.sha256(content).hexdigest()
        with self._lock:
            upload = self._get_upload(upload_id)
            if not 0 <= file_index < upload.expected_file_count:
                raise JobError(
                    "IMAGE_BROWSER_FILE_INDEX_INVALID",
                    "The uploaded image index is outside the declared selection.",
                )
            if file_index in upload.uploaded_indexes:
                existing = upload.uploaded_files[file_index]
                if (
                    existing.relative_path == normalized_path.as_posix()
                    and existing.size_bytes == len(content)
                    and existing.checksum_sha256 == checksum_sha256
                ):
                    return upload
                raise JobConflictError(
                    "IMAGE_BROWSER_FILE_ALREADY_UPLOADED",
                    "This upload index already contains a different image file.",
                )
            if upload.uploaded_bytes + len(content) > upload.expected_total_bytes:
                raise JobError(
                    "IMAGE_BROWSER_SELECTION_SIZE_MISMATCH",
                    "Uploaded bytes exceed the declared browser selection size.",
                )
            suffix = normalized_path.suffix.casefold()
            target = upload.path / f"{file_index + 1:08d}{suffix}"
            temporary = upload.path / f".{file_index + 1:08d}.part"
            try:
                temporary.write_bytes(content)
                read_jpeg_dimensions(temporary)
                temporary.replace(target)
            except (OSError, ImageFileError) as error:
                temporary.unlink(missing_ok=True)
                raise JobError(
                    "IMAGE_BROWSER_FILE_INVALID",
                    "The uploaded file is not a readable JPEG image.",
                ) from error
            upload.uploaded_indexes.add(file_index)
            upload.uploaded_bytes += len(content)
            upload.uploaded_files[file_index] = BrowserUploadedFile(
                file_index=file_index,
                relative_path=normalized_path.as_posix(),
                stored_file_name=target.name,
                size_bytes=len(content),
                checksum_sha256=checksum_sha256,
            )
            self._write_upload_state(upload)
            return upload

    def finalize(self, upload_id: UUID) -> SelectedImageFolder:
        with self._lock:
            upload = self._get_upload(upload_id)
            if (
                len(upload.uploaded_indexes) != upload.expected_file_count
                or upload.uploaded_bytes != upload.expected_total_bytes
            ):
                raise JobConflictError(
                    "IMAGE_BROWSER_SELECTION_INCOMPLETE",
                    "The browser selection has not uploaded every declared image.",
                )
            manifest_payload = {
                "schemaVersion": 1,
                "purpose": upload.purpose.value,
                "gameId": None if upload.game_id is None else str(upload.game_id),
                "orderingPolicy": "natural_relative_path_v1",
                "files": [
                    {
                        "orderIndex": value.file_index,
                        "relativePath": value.relative_path,
                        "storedFileName": value.stored_file_name,
                        "sizeBytes": value.size_bytes,
                        "checksumSha256": value.checksum_sha256,
                    }
                    for value in sorted(
                        upload.uploaded_files.values(),
                        key=lambda item: item.file_index,
                    )
                ],
            }
            manifest_bytes = json.dumps(
                manifest_payload,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
            manifest_path = upload.path / UPLOAD_MANIFEST_FILE_NAME
            temporary_manifest = upload.path / f".{UPLOAD_MANIFEST_FILE_NAME}.part"
            temporary_manifest.write_bytes(manifest_bytes)
            temporary_manifest.replace(manifest_path)
            completed_at = self._clock()
            upload_metrics = {
                "completedAt": completed_at.isoformat(),
                "durationSeconds": max(
                    0.0,
                    (completed_at - upload.created_at).total_seconds(),
                ),
                "schemaVersion": 1,
                "startedAt": upload.created_at.isoformat(),
            }
            metrics_path = upload.path / UPLOAD_METRICS_FILE_NAME
            temporary_metrics = upload.path / f".{UPLOAD_METRICS_FILE_NAME}.part"
            temporary_metrics.write_text(
                json.dumps(
                    upload_metrics,
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            temporary_metrics.replace(metrics_path)
            selected = self._selection_service.approve(
                upload.path,
                display_name=upload.display_name,
                purpose=upload.purpose,
                game_id=upload.game_id,
                input_manifest_sha256=manifest_sha256,
                selection_id=upload.upload_id,
                managed=True,
            )
            self._uploads.pop(upload_id, None)
            return selected

    def get(self, upload_id: UUID) -> BrowserImageUpload:
        with self._lock:
            return self._get_upload(upload_id)

    def cancel(self, upload_id: UUID) -> None:
        with self._lock:
            upload = self._uploads.pop(upload_id, None)
            if upload is None:
                upload = self._load_upload(upload_id)
                self._uploads.pop(upload_id, None)
        if upload is not None:
            shutil.rmtree(upload.path, ignore_errors=True)

    def _get_upload(self, upload_id: UUID) -> BrowserImageUpload:
        upload = self._uploads.get(upload_id)
        if upload is None:
            upload = self._load_upload(upload_id)
            if upload is not None:
                self._uploads[upload_id] = upload
        if upload is None:
            raise JobError(
                "IMAGE_BROWSER_SELECTION_NOT_FOUND",
                "The browser image selection does not exist or has expired.",
            )
        return upload

    def _write_upload_state(self, upload: BrowserImageUpload) -> None:
        payload = {
            "schemaVersion": 1,
            "uploadId": str(upload.upload_id),
            "displayName": upload.display_name,
            "purpose": upload.purpose.value,
            "gameId": None if upload.game_id is None else str(upload.game_id),
            "expectedFileCount": upload.expected_file_count,
            "expectedTotalBytes": upload.expected_total_bytes,
            "createdAt": upload.created_at.isoformat(),
            "files": [
                {
                    "fileIndex": value.file_index,
                    "relativePath": value.relative_path,
                    "storedFileName": value.stored_file_name,
                    "sizeBytes": value.size_bytes,
                    "checksumSha256": value.checksum_sha256,
                }
                for value in sorted(
                    upload.uploaded_files.values(),
                    key=lambda item: item.file_index,
                )
            ],
        }
        destination = upload.path / UPLOAD_STATE_FILE_NAME
        temporary = upload.path / f".{UPLOAD_STATE_FILE_NAME}.part"
        temporary.write_text(
            json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(destination)

    def _load_upload(self, upload_id: UUID) -> BrowserImageUpload | None:
        upload_path = (self._upload_root / str(upload_id)).resolve()
        if not upload_path.is_relative_to(self._upload_root) or not upload_path.is_dir():
            return None
        state_path = upload_path / UPLOAD_STATE_FILE_NAME
        try:
            if state_path.is_file():
                payload = json.loads(state_path.read_text(encoding="utf-8"))
            else:
                payload = self._rebuild_upload_state_from_finalized_manifest(
                    upload_id,
                    upload_path,
                )
            if payload.get("schemaVersion") != 1 or payload.get("uploadId") != str(upload_id):
                return None
            files = {
                int(value["fileIndex"]): BrowserUploadedFile(
                    file_index=int(value["fileIndex"]),
                    relative_path=str(value["relativePath"]),
                    stored_file_name=str(value["storedFileName"]),
                    size_bytes=int(value["sizeBytes"]),
                    checksum_sha256=str(value["checksumSha256"]),
                )
                for value in payload["files"]
            }
            created_at = datetime.fromisoformat(str(payload["createdAt"]))
            upload = BrowserImageUpload(
                upload_id=upload_id,
                path=upload_path,
                display_name=str(payload["displayName"]),
                purpose=ImageSelectionPurpose(str(payload["purpose"])),
                game_id=(None if payload.get("gameId") is None else UUID(str(payload["gameId"]))),
                expected_file_count=int(payload["expectedFileCount"]),
                expected_total_bytes=int(payload["expectedTotalBytes"]),
                created_at=created_at,
                uploaded_indexes=set(files),
                uploaded_files=files,
                uploaded_bytes=sum(value.size_bytes for value in files.values()),
            )
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return None
        if upload.created_at + BROWSER_UPLOAD_TTL <= self._clock():
            shutil.rmtree(upload.path, ignore_errors=True)
            return None
        return upload

    @staticmethod
    def _rebuild_upload_state_from_finalized_manifest(
        upload_id: UUID,
        upload_path: Path,
    ) -> dict[str, object]:
        manifest = json.loads((upload_path / UPLOAD_MANIFEST_FILE_NAME).read_text(encoding="utf-8"))
        metrics = json.loads((upload_path / UPLOAD_METRICS_FILE_NAME).read_text(encoding="utf-8"))
        manifest_files = manifest["files"]
        first_relative_path = str(manifest_files[0]["relativePath"])
        display_name = PurePosixPath(first_relative_path).parts[0]
        files = [
            {
                "checksumSha256": value["checksumSha256"],
                "fileIndex": value["orderIndex"],
                "relativePath": value["relativePath"],
                "sizeBytes": value["sizeBytes"],
                "storedFileName": value["storedFileName"],
            }
            for value in manifest_files
        ]
        return {
            "schemaVersion": 1,
            "uploadId": str(upload_id),
            "displayName": display_name,
            "purpose": manifest["purpose"],
            "gameId": manifest["gameId"],
            "expectedFileCount": len(files),
            "expectedTotalBytes": sum(int(value["sizeBytes"]) for value in files),
            "createdAt": metrics["startedAt"],
            "files": files,
        }

    def _remove_expired(self, now: datetime) -> None:
        expired_ids = [
            upload_id
            for upload_id, upload in self._uploads.items()
            if upload.created_at + BROWSER_UPLOAD_TTL <= now
        ]
        for upload_id in expired_ids:
            upload = self._uploads.pop(upload_id)
            shutil.rmtree(upload.path, ignore_errors=True)


def inspect_image_folder(path: Path) -> tuple[Path, int]:
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise JobError(
            "IMAGE_FOLDER_NOT_FOUND",
            "The selected image folder does not exist or is unavailable.",
        ) from error
    if not resolved.is_dir():
        raise JobError(
            "IMAGE_FOLDER_NOT_DIRECTORY",
            "The selected image source must be a directory.",
        )
    count = 0
    first_supported: Path | None = None
    try:
        for current_root, directory_names, file_names in os.walk(
            resolved,
            followlinks=False,
        ):
            directory_names.sort(key=lambda value: (value.casefold(), value))
            file_names.sort(key=lambda value: (value.casefold(), value))
            for file_name in file_names:
                candidate = Path(current_root) / file_name
                if candidate.suffix.casefold() not in SUPPORTED_IMAGE_SUFFIXES:
                    continue
                count += 1
                if first_supported is None:
                    first_supported = candidate
                if count > MAX_PREFLIGHT_FILES:
                    raise JobError(
                        "IMAGE_FOLDER_TOO_LARGE",
                        "The selected folder exceeds the controlled preflight limit.",
                    )
    except OSError as error:
        raise JobError(
            "IMAGE_FOLDER_UNREADABLE",
            "The selected image folder cannot be scanned.",
        ) from error
    if first_supported is None:
        raise JobError(
            "IMAGE_FOLDER_EMPTY",
            "The selected folder contains no supported JPEG images.",
        )
    try:
        read_jpeg_dimensions(first_supported)
    except ImageFileError as error:
        raise JobError(error.code, str(error)) from error
    return resolved, count


__all__ = [
    "BrowserImageSelectionService",
    "BrowserImageUpload",
    "BrowserUploadedFile",
    "BROWSER_UPLOAD_TTL",
    "IMAGE_RELATIVE_PATH_HEADER",
    "ImageFolderSelectionService",
    "ImageSelectionPurpose",
    "SelectedImageFolder",
    "WindowsFolderPicker",
    "inspect_image_folder",
]
