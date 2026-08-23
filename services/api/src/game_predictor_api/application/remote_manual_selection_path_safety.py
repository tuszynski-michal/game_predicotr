"""Fail-closed Windows path policy for host-bound remote selection output."""

from __future__ import annotations

import ctypes
import os
import stat
import unicodedata
from contextlib import AbstractContextManager
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Final

from game_predictor_api.domain.remote_manual_selections import (
    RemoteManualSelectionConflictError,
    RemoteManualSelectionError,
)

if os.name == "nt":
    import msvcrt

_INVALID_COMPONENT_CHARACTERS: Final[frozenset[str]] = frozenset('<>:"/\\|?*')
_RESERVED_NAMES: Final[frozenset[str]] = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{value}" for value in range(1, 10)),
        *(f"LPT{value}" for value in range(1, 10)),
        *(f"COM{value}" for value in ("¹", "²", "³")),
        *(f"LPT{value}" for value in ("¹", "²", "³")),
    }
)

_FILE_READ_ATTRIBUTES = 0x0080
_GENERIC_READ = 0x80000000
_FILE_SHARE_READ = 0x00000001
_FILE_SHARE_WRITE = 0x00000002
_OPEN_EXISTING = 3
_FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
_FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
_FILE_ATTRIBUTE_TAG_INFO_CLASS = 9
_FILE_NAME_NORMALIZED = 0
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


@dataclass(frozen=True, slots=True)
class WindowsPathLimits:
    max_component_utf16_units: int
    max_path_utf16_units: int


@dataclass(frozen=True, slots=True)
class ValidatedWindowsComponent:
    display_name: str
    normalized_name: str


@dataclass(frozen=True, slots=True)
class WindowsBoundBase:
    final_path: Path
    display_name: str
    limits: WindowsPathLimits


class _FileAttributeTagInfo(ctypes.Structure):
    _fields_ = [
        ("file_attributes", wintypes.DWORD),
        ("reparse_tag", wintypes.DWORD),
    ]


def validate_windows_component(
    value: str,
    *,
    limits: WindowsPathLimits,
) -> ValidatedWindowsComponent:
    """Validate one collection/batch component and derive its Windows key."""

    normalized = unicodedata.normalize("NFC", value)
    if not normalized or normalized in {".", ".."}:
        raise _invalid_name("The directory name must contain one non-empty component.")
    if normalized != value:
        # The canonical value is returned, but the caller must persist/display it.
        value = normalized
    if os.path.isabs(value) or value.startswith(("\\\\", "//")):
        raise _invalid_name("Absolute and UNC directory names are not allowed.")
    if any(character in _INVALID_COMPONENT_CHARACTERS for character in value):
        raise _invalid_name("The directory name contains a forbidden Windows character.")
    if any(ord(character) < 32 for character in value):
        raise _invalid_name("The directory name contains a control character.")
    if value.endswith((".", " ")):
        raise _invalid_name("The directory name cannot end with a dot or space.")
    reserved_stem = value.split(".", 1)[0].upper()
    if reserved_stem in _RESERVED_NAMES:
        raise _invalid_name("The directory name is reserved by Windows.")
    if _utf16_units(value) > limits.max_component_utf16_units:
        raise RemoteManualSelectionError(
            "REMOTE_SELECTION_PATH_COMPONENT_TOO_LONG",
            "The directory name exceeds the filesystem component limit.",
        )
    return ValidatedWindowsComponent(
        display_name=value,
        normalized_name=value.casefold(),
    )


class LockedWindowsBase(AbstractContextManager["LockedWindowsBase"]):
    """Hold non-delete-sharing directory handles across child creation."""

    def __init__(
        self,
        *,
        handles: list[int],
        bound_base: WindowsBoundBase,
    ) -> None:
        self._handles = handles
        self.bound_base = bound_base

    def __enter__(self) -> LockedWindowsBase:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback
        while self._handles:
            _close_handle(self._handles.pop())

    def open_or_create_child(
        self,
        parent: Path,
        component: ValidatedWindowsComponent,
    ) -> tuple[Path, bool]:
        _assert_contained(self.bound_base.final_path, parent)
        _assert_path_length(parent / component.display_name, self.bound_base.limits)
        match = _find_casefold_match(parent, component)
        created = False
        if match is None:
            candidate = parent / component.display_name
            try:
                os.mkdir(candidate)
                created = True
            except FileExistsError:
                match = _find_casefold_match(parent, component)
                if match is None:
                    raise _path_conflict("The target directory appeared concurrently.") from None
            target = candidate if match is None else match
        else:
            target = match
        handle, final_path = _open_verified_directory(target)
        try:
            _assert_contained(self.bound_base.final_path, final_path)
            expected = _normalized_path(target)
            if _normalized_path(final_path) != expected:
                raise _unsafe_path("The target directory final path changed.")
        except BaseException:
            _close_handle(handle)
            raise
        self._handles.append(handle)
        return final_path, created

    def open_existing_child(
        self,
        parent: Path,
        component: ValidatedWindowsComponent,
    ) -> Path | None:
        _assert_contained(self.bound_base.final_path, parent)
        match = _find_casefold_match(parent, component)
        if match is None:
            return None
        handle, final_path = _open_verified_directory(match)
        try:
            _assert_contained(self.bound_base.final_path, final_path)
            if _normalized_path(final_path) != _normalized_path(match):
                raise _unsafe_path("The target directory final path changed.")
        except BaseException:
            _close_handle(handle)
            raise
        self._handles.append(handle)
        return final_path

    def assert_regular_file(self, path: Path) -> None:
        _assert_contained(self.bound_base.final_path, path)
        try:
            metadata = path.lstat()
        except OSError as error:
            raise _path_conflict("The ownership marker is unavailable.") from error
        if not stat.S_ISREG(metadata.st_mode) or _is_reparse_stat(metadata):
            raise _unsafe_path("The ownership marker is not a regular local file.")

    def read_regular_file(self, path: Path, *, max_bytes: int) -> bytes:
        _assert_contained(self.bound_base.final_path, path)
        handle = _open_verified_regular_file(path)
        descriptor = -1
        try:
            descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY)
            handle = 0  # Ownership moved to the Python descriptor.
            with os.fdopen(descriptor, "rb", closefd=True) as stream:
                descriptor = -1
                payload = stream.read(max_bytes + 1)
        except OSError as error:
            raise _path_conflict("The ownership marker is unavailable.") from error
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if handle:
                _close_handle(handle)
        if len(payload) > max_bytes:
            raise _path_conflict("The ownership marker exceeds its size limit.")
        return payload


class WindowsPathGuard:
    """Open and lock a local-drive directory chain using Win32 final handles."""

    def inspect_base(self, path: Path) -> WindowsBoundBase:
        with self.lock_base(path) as locked:
            return locked.bound_base

    def lock_base(self, path: Path) -> LockedWindowsBase:
        if os.name != "nt":
            raise RemoteManualSelectionError(
                "REMOTE_SELECTION_HOST_WINDOWS_REQUIRED",
                "Host folder mapping is available only on Windows.",
            )
        absolute = Path(os.path.abspath(path))
        if not absolute.is_absolute() or not absolute.drive or str(absolute).startswith("\\\\"):
            raise _unsafe_path("The selected base must be a local absolute directory.")
        if not absolute.is_dir():
            raise RemoteManualSelectionError(
                "REMOTE_SELECTION_BASE_UNAVAILABLE",
                "The selected host base directory is unavailable.",
            )

        handles: list[int] = []
        try:
            chain = _directory_chain(absolute)
            for component_path in chain[:-1]:
                _assert_existing_directory_not_reparse(component_path)
            handle, final_path = _open_verified_directory(absolute)
            handles.append(handle)
            if _normalized_path(final_path) != _normalized_path(absolute):
                raise _unsafe_path("The selected base final path changed.")
            limits = _read_path_limits(final_path)
            _assert_path_length(final_path, limits)
            return LockedWindowsBase(
                handles=handles,
                bound_base=WindowsBoundBase(
                    final_path=final_path,
                    display_name=absolute.name or absolute.drive,
                    limits=limits,
                ),
            )
        except BaseException:
            while handles:
                _close_handle(handles.pop())
            raise


def _assert_existing_directory_not_reparse(path: Path) -> None:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise _unsafe_path("A host directory component cannot be inspected safely.") from error
    if not stat.S_ISDIR(metadata.st_mode) or _is_reparse_stat(metadata):
        raise _unsafe_path("A reparse point exists in the host directory chain.")


def _directory_chain(path: Path) -> tuple[Path, ...]:
    current = Path(path.anchor)
    chain = [current]
    for part in path.parts[1:]:
        current /= part
        chain.append(current)
    return tuple(chain)


def _open_verified_directory(path: Path) -> tuple[int, Path]:
    kernel32 = _kernel32()
    raw_handle = kernel32.CreateFileW(
        str(path),
        _FILE_READ_ATTRIBUTES,
        _FILE_SHARE_READ | _FILE_SHARE_WRITE,
        None,
        _OPEN_EXISTING,
        _FILE_FLAG_BACKUP_SEMANTICS | _FILE_FLAG_OPEN_REPARSE_POINT,
        None,
    )
    handle = int(raw_handle) if raw_handle is not None else 0
    if handle == 0 or handle == _INVALID_HANDLE_VALUE:
        raise _unsafe_path("A host directory could not be opened safely.")
    try:
        attributes = _FileAttributeTagInfo()
        if not kernel32.GetFileInformationByHandleEx(
            wintypes.HANDLE(handle),
            _FILE_ATTRIBUTE_TAG_INFO_CLASS,
            ctypes.byref(attributes),
            ctypes.sizeof(attributes),
        ):
            raise _unsafe_path("A host directory could not be inspected safely.")
        if attributes.file_attributes & _FILE_ATTRIBUTE_REPARSE_POINT:
            raise _unsafe_path("A reparse point exists in the host directory chain.")
        final_path = _final_path_for_handle(handle)
        if not final_path.is_dir():
            raise _unsafe_path("The host path is not a directory.")
        return handle, final_path
    except BaseException:
        _close_handle(handle)
        raise


def _open_verified_regular_file(path: Path) -> int:
    kernel32 = _kernel32()
    raw_handle = kernel32.CreateFileW(
        str(path),
        _GENERIC_READ | _FILE_READ_ATTRIBUTES,
        _FILE_SHARE_READ | _FILE_SHARE_WRITE,
        None,
        _OPEN_EXISTING,
        _FILE_FLAG_OPEN_REPARSE_POINT,
        None,
    )
    handle = int(raw_handle) if raw_handle is not None else 0
    if handle == 0 or handle == _INVALID_HANDLE_VALUE:
        raise _path_conflict("The ownership marker is unavailable.")
    try:
        attributes = _FileAttributeTagInfo()
        if not kernel32.GetFileInformationByHandleEx(
            wintypes.HANDLE(handle),
            _FILE_ATTRIBUTE_TAG_INFO_CLASS,
            ctypes.byref(attributes),
            ctypes.sizeof(attributes),
        ):
            raise _unsafe_path("The ownership marker could not be inspected safely.")
        if attributes.file_attributes & _FILE_ATTRIBUTE_REPARSE_POINT:
            raise _unsafe_path("The ownership marker is a reparse point.")
        return handle
    except BaseException:
        _close_handle(handle)
        raise


def _final_path_for_handle(handle: int) -> Path:
    kernel32 = _kernel32()
    size = 512
    while size <= 32768:
        buffer = ctypes.create_unicode_buffer(size)
        length = kernel32.GetFinalPathNameByHandleW(
            wintypes.HANDLE(handle),
            buffer,
            size,
            _FILE_NAME_NORMALIZED,
        )
        if length == 0:
            raise _unsafe_path("The host directory final path is unavailable.")
        if length < size:
            return Path(_strip_extended_prefix(buffer.value))
        size = int(length) + 1
    raise _unsafe_path("The host directory final path exceeds the Windows limit.")


def _kernel32() -> ctypes.WinDLL:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.GetFileInformationByHandleEx.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    kernel32.GetFileInformationByHandleEx.restype = wintypes.BOOL
    kernel32.GetFinalPathNameByHandleW.argtypes = [
        wintypes.HANDLE,
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    kernel32.GetFinalPathNameByHandleW.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    return kernel32


def _close_handle(handle: int) -> None:
    if os.name == "nt" and handle not in {0, _INVALID_HANDLE_VALUE}:
        _kernel32().CloseHandle(wintypes.HANDLE(handle))


def _read_path_limits(path: Path) -> WindowsPathLimits:
    kernel32 = _kernel32()
    maximum_component = wintypes.DWORD()
    root = f"{path.drive}\\"
    ok = kernel32.GetVolumeInformationW(
        root,
        None,
        0,
        None,
        ctypes.byref(maximum_component),
        None,
        None,
        0,
    )
    component_limit = int(maximum_component.value) if ok else 255
    return WindowsPathLimits(
        max_component_utf16_units=component_limit,
        max_path_utf16_units=32766 if _long_paths_enabled() else 259,
    )


def _long_paths_enabled() -> bool:
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\FileSystem",
        ) as key:
            value, _kind = winreg.QueryValueEx(key, "LongPathsEnabled")
            return int(value) == 1
    except (OSError, ValueError):
        return False


def _find_casefold_match(
    parent: Path,
    component: ValidatedWindowsComponent,
) -> Path | None:
    try:
        matches = [
            entry
            for entry in os.scandir(parent)
            if unicodedata.normalize("NFC", entry.name).casefold() == component.normalized_name
        ]
    except OSError as error:
        raise _unsafe_path("The host directory cannot be enumerated safely.") from error
    if len(matches) > 1:
        raise _path_conflict("Multiple case-insensitive directory matches exist.")
    if not matches:
        return None
    match = matches[0]
    if unicodedata.normalize("NFC", match.name) != component.display_name:
        raise RemoteManualSelectionConflictError(
            "REMOTE_SELECTION_PATH_CASE_COLLISION",
            "A case-insensitive or Unicode-equivalent directory already exists.",
        )
    if not match.is_dir(follow_symlinks=False):
        raise _path_conflict("The target name is already used by a non-directory entry.")
    try:
        metadata = match.stat(follow_symlinks=False)
    except OSError as error:
        raise _unsafe_path("The target directory cannot be inspected safely.") from error
    if _is_reparse_stat(metadata):
        raise _unsafe_path("A reparse point exists at the target directory.")
    return Path(match.path)


def _assert_contained(base: Path, candidate: Path) -> None:
    try:
        common = os.path.commonpath((_normalized_path(base), _normalized_path(candidate)))
    except ValueError as error:
        raise _unsafe_path("The target directory is outside the approved host base.") from error
    if common != _normalized_path(base):
        raise _unsafe_path("The target directory is outside the approved host base.")


def _assert_path_length(path: Path, limits: WindowsPathLimits) -> None:
    if _utf16_units(str(path)) > limits.max_path_utf16_units:
        raise RemoteManualSelectionError(
            "REMOTE_SELECTION_PATH_TOO_LONG",
            "The target path exceeds the active Windows path limit.",
        )


def _normalized_path(path: Path) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def _strip_extended_prefix(value: str) -> str:
    if value.startswith("\\\\?\\UNC\\"):
        return "\\\\" + value[8:]
    return value[4:] if value.startswith("\\\\?\\") else value


def _is_reparse_stat(metadata: os.stat_result) -> bool:
    return bool(getattr(metadata, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT)


def _utf16_units(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


def _invalid_name(message: str) -> RemoteManualSelectionError:
    return RemoteManualSelectionError("REMOTE_SELECTION_PATH_NAME_INVALID", message)


def _unsafe_path(message: str) -> RemoteManualSelectionError:
    return RemoteManualSelectionError("REMOTE_SELECTION_PATH_UNSAFE", message)


def _path_conflict(message: str) -> RemoteManualSelectionConflictError:
    return RemoteManualSelectionConflictError("REMOTE_SELECTION_PATH_COLLISION", message)


__all__ = [
    "LockedWindowsBase",
    "ValidatedWindowsComponent",
    "WindowsBoundBase",
    "WindowsPathGuard",
    "WindowsPathLimits",
    "validate_windows_component",
]
