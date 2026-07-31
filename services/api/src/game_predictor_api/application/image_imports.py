"""Controlled local-folder selection for image import jobs."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from secrets import token_urlsafe
from threading import Lock
from uuid import UUID, uuid4

from game_predictor_worker.images.image_file import ImageFileError, read_jpeg_dimensions
from game_predictor_worker.images.pipeline_contract import (
    current_pipeline_manifest,
    pipeline_fingerprint,
)

from game_predictor_api.application.jobs import JobService
from game_predictor_api.domain.jobs import Job, JobError

SUPPORTED_IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg"})
SELECTION_TTL = timedelta(minutes=15)
MAX_PREFLIGHT_FILES = 1_000_000


@dataclass(frozen=True, slots=True)
class SelectedImageFolder:
    selection_token: str
    selection_id: UUID
    path: Path
    supported_file_count: int
    expires_at: datetime


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

    def select(self) -> SelectedImageFolder | None:
        path = self._picker()
        if path is None:
            return None
        resolved, count = inspect_image_folder(path)
        now = self._clock()
        selected = SelectedImageFolder(
            selection_token=token_urlsafe(32),
            selection_id=uuid4(),
            path=resolved,
            supported_file_count=count,
            expires_at=now + SELECTION_TTL,
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
            source_display_name=selected.path.name,
            pipeline_fingerprint=pipeline_fingerprint(current_pipeline_manifest()),
        )
        with self._lock:
            self._selections.pop(selection_token, None)
        return job

    def _remove_expired(self, now: datetime) -> None:
        expired = [
            token for token, selection in self._selections.items() if selection.expires_at <= now
        ]
        for token in expired:
            self._selections.pop(token, None)


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
    "ImageFolderSelectionService",
    "SelectedImageFolder",
    "WindowsFolderPicker",
    "inspect_image_folder",
]
