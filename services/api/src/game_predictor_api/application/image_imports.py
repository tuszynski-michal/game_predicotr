"""Controlled local-folder selection for image import jobs."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from secrets import token_urlsafe
from threading import Lock
from uuid import UUID, uuid4

from game_predictor_worker.images.image_file import ImageFileError, read_jpeg_dimensions
from game_predictor_worker.images.pipeline_contract import (
    current_pipeline_manifest,
    pipeline_fingerprint,
)

from game_predictor_api.application.jobs import JobService
from game_predictor_api.domain.jobs import Job, JobConflictError, JobError

SUPPORTED_IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg"})
SELECTION_TTL = timedelta(minutes=15)
MAX_PREFLIGHT_FILES = 1_000_000
IMAGE_RELATIVE_PATH_HEADER = "X-Image-Relative-Path"


@dataclass(frozen=True, slots=True)
class SelectedImageFolder:
    selection_token: str
    selection_id: UUID
    path: Path
    supported_file_count: int
    expires_at: datetime
    display_name: str
    managed: bool = False


@dataclass(slots=True)
class BrowserImageUpload:
    upload_id: UUID
    path: Path
    display_name: str
    expected_file_count: int
    expected_total_bytes: int
    created_at: datetime
    uploaded_indexes: set[int]
    uploaded_bytes: int = 0


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
        managed: bool = False,
    ) -> SelectedImageFolder:
        resolved, count = inspect_image_folder(path)
        now = self._clock()
        selected = SelectedImageFolder(
            selection_token=token_urlsafe(32),
            selection_id=uuid4(),
            path=resolved,
            supported_file_count=count,
            expires_at=now + SELECTION_TTL,
            display_name=display_name or resolved.name,
            managed=managed,
        )
        with self._lock:
            self._remove_expired(now)
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
        )
        with self._lock:
            self._selections.pop(selection_token, None)
        return job

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
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._selection_service = selection_service
        self._upload_root = upload_root.resolve() / "browser-selections"
        self._max_bytes = max_bytes
        self._clock = clock or (lambda: datetime.now(UTC))
        self._uploads: dict[UUID, BrowserImageUpload] = {}
        self._lock = Lock()

    def begin(
        self,
        *,
        display_name: str,
        expected_file_count: int,
        expected_total_bytes: int,
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
        if not 1 <= expected_file_count <= MAX_PREFLIGHT_FILES:
            raise JobError(
                "IMAGE_BROWSER_SELECTION_COUNT_INVALID",
                "The browser selection must contain at least one supported file.",
            )
        if not 1 <= expected_total_bytes <= self._max_bytes:
            raise JobError(
                "IMAGE_BROWSER_SELECTION_SIZE_INVALID",
                "The browser selection exceeds the configured import size limit.",
            )
        now = self._clock()
        with self._lock:
            self._remove_expired(now)
        upload_id = uuid4()
        upload_path = self._upload_root / str(upload_id)
        upload_path.mkdir(parents=True, exist_ok=False)
        upload = BrowserImageUpload(
            upload_id=upload_id,
            path=upload_path,
            display_name=normalized_name,
            expected_file_count=expected_file_count,
            expected_total_bytes=expected_total_bytes,
            created_at=now,
            uploaded_indexes=set(),
        )
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
        with self._lock:
            upload = self._get_upload(upload_id)
            if not 0 <= file_index < upload.expected_file_count:
                raise JobError(
                    "IMAGE_BROWSER_FILE_INDEX_INVALID",
                    "The uploaded image index is outside the declared selection.",
                )
            if file_index in upload.uploaded_indexes:
                raise JobConflictError(
                    "IMAGE_BROWSER_FILE_ALREADY_UPLOADED",
                    "This browser image file has already been uploaded.",
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
            selected = self._selection_service.approve(
                upload.path,
                display_name=upload.display_name,
                managed=True,
            )
            self._uploads.pop(upload_id, None)
            return selected

    def cancel(self, upload_id: UUID) -> None:
        with self._lock:
            upload = self._uploads.pop(upload_id, None)
        if upload is not None:
            shutil.rmtree(upload.path, ignore_errors=True)

    def _get_upload(self, upload_id: UUID) -> BrowserImageUpload:
        upload = self._uploads.get(upload_id)
        if upload is None:
            raise JobError(
                "IMAGE_BROWSER_SELECTION_NOT_FOUND",
                "The browser image selection does not exist or has expired.",
            )
        return upload

    def _remove_expired(self, now: datetime) -> None:
        expired_ids = [
            upload_id
            for upload_id, upload in self._uploads.items()
            if upload.created_at + SELECTION_TTL <= now
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
    "IMAGE_RELATIVE_PATH_HEADER",
    "ImageFolderSelectionService",
    "SelectedImageFolder",
    "WindowsFolderPicker",
    "inspect_image_folder",
]
