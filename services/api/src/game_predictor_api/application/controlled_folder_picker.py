"""One fixed Windows folder picker shared by local-only workflows."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from threading import Lock

from game_predictor_api.domain.jobs import JobConflictError, JobError


class WindowsFolderPicker:
    """Invoke one fixed PowerShell helper with process-wide exclusive display.

    The caller can neither provide a command nor a starting path.  The lock is
    owned by the picker instance so all services sharing it also share the
    one-window invariant.
    """

    def __init__(self, script_path: Path, *, timeout_seconds: int = 120) -> None:
        self._script_path = script_path.resolve()
        self._timeout_seconds = timeout_seconds
        self._picker_lock = Lock()

    def choose(self) -> Path | None:
        if not self._picker_lock.acquire(blocking=False):
            raise JobConflictError(
                "IMAGE_FOLDER_PICKER_ALREADY_OPEN",
                "A folder selection window is already open.",
            )
        try:
            return self._choose_exclusive()
        finally:
            self._picker_lock.release()

    def _choose_exclusive(self) -> Path | None:
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


__all__ = ["WindowsFolderPicker"]
