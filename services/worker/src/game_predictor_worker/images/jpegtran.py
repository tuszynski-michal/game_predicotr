"""Lossless JPEG crops with ``jpegtran`` from libjpeg-turbo (D-562, TASK-1047).

The tool is resolved from ``GAME_PREDICTOR_JPEGTRAN_PATH`` or the isolated
``.tooling`` install relative to the worker's working directory (the repository
root for every npm script). Resolution checks the version before any file is
written, so a missing tool fails the job with ``SOURCE_CROP_TOOL_UNAVAILABLE``.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

from game_predictor_api.domain.source_crop import PixelBox

JPEGTRAN_PATH_ENV: Final = "GAME_PREDICTOR_JPEGTRAN_PATH"
DEFAULT_JPEGTRAN_PATH: Final = Path(".tooling", "libjpeg-turbo-3.2.0", "bin", "jpegtran.exe")
JPEGTRAN_VERSION_ENV: Final = "GAME_PREDICTOR_JPEGTRAN_VERSION"
# R7/R9: the approved libjpeg-turbo release; another one needs an explicit setting.
DEFAULT_JPEGTRAN_VERSION: Final = "3.2.0"
VERSION_TIMEOUT_SECONDS: Final = 10
CROP_TIMEOUT_SECONDS: Final = 30  # R8: per original


class SourceCropToolError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class LosslessCropper(Protocol):
    """Writes the region ``raw_box`` of a stored JPEG without re-encoding it."""

    @property
    def version(self) -> str: ...

    def crop(self, source: Path, target: Path, raw_box: PixelBox) -> None: ...


@dataclass(frozen=True, slots=True)
class JpegtranCropper:
    executable: Path
    version: str

    @classmethod
    def resolve(cls, environment: Mapping[str, str] | None = None) -> JpegtranCropper:
        values = os.environ if environment is None else environment
        configured = values.get(JPEGTRAN_PATH_ENV, "").strip()
        executable = Path(configured) if configured else DEFAULT_JPEGTRAN_PATH
        executable = executable.resolve()
        if not executable.is_file():
            raise SourceCropToolError(
                "SOURCE_CROP_TOOL_UNAVAILABLE",
                f"jpegtran was not found; install libjpeg-turbo or set {JPEGTRAN_PATH_ENV}.",
            )
        try:
            completed = subprocess.run(
                [str(executable), "-version"],
                capture_output=True,
                text=True,
                timeout=VERSION_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise SourceCropToolError(
                "SOURCE_CROP_TOOL_UNAVAILABLE", "jpegtran cannot be started."
            ) from error
        if completed.returncode != 0:
            raise SourceCropToolError(
                "SOURCE_CROP_TOOL_UNAVAILABLE", "jpegtran -version did not succeed."
            )
        expected = values.get(JPEGTRAN_VERSION_ENV, "").strip() or DEFAULT_JPEGTRAN_VERSION
        # libjpeg-turbo prints the version to stderr.
        version = require_jpegtran_version(completed.stderr or completed.stdout, expected)
        return cls(executable=executable, version=version)

    def crop(self, source: Path, target: Path, raw_box: PixelBox) -> None:
        geometry = f"{raw_box.width}x{raw_box.height}+{raw_box.left}+{raw_box.top}"
        try:
            completed = subprocess.run(
                [
                    str(self.executable),
                    "-copy",
                    "all",
                    "-optimize",
                    "-crop",
                    geometry,
                    "-outfile",
                    str(target),
                    str(source),
                ],
                capture_output=True,
                text=True,
                timeout=CROP_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise SourceCropToolError(
                "SOURCE_CROP_TOOL_FAILED", "jpegtran did not finish."
            ) from error
        if completed.returncode != 0:
            raise SourceCropToolError(
                "SOURCE_CROP_TOOL_FAILED",
                f"jpegtran exited with {completed.returncode}: {completed.stderr.strip()[:300]}",
            )


def require_jpegtran_version(output: str, expected: str) -> str:
    """The version line when it names exactly the ``expected`` libjpeg-turbo release."""

    lines = output.strip().splitlines()
    line = lines[0].strip() if lines else ""
    prefix = f"libjpeg-turbo version {expected}"
    if line != prefix and not line.startswith(prefix + " "):
        raise SourceCropToolError(
            "SOURCE_CROP_TOOL_UNAVAILABLE",
            f"jpegtran must be libjpeg-turbo {expected}; found {line[:120]!r}.",
        )
    return line[:200]


__all__ = [
    "CROP_TIMEOUT_SECONDS",
    "DEFAULT_JPEGTRAN_PATH",
    "DEFAULT_JPEGTRAN_VERSION",
    "JPEGTRAN_VERSION_ENV",
    "JPEGTRAN_PATH_ENV",
    "JpegtranCropper",
    "LosslessCropper",
    "SourceCropToolError",
    "require_jpegtran_version",
]
