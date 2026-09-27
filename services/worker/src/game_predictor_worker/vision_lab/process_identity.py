"""PID reuse-safe identity without a database or a process-control dependency."""

import os
import sys
from pathlib import Path


def process_created(pid: int) -> str | None:
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [
            ctypes.POINTER(wintypes.FILETIME)
        ] * 4
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            if ctypes.get_last_error() in (87, 1168):
                return None
            raise ValueError("RUN_PROCESS_IDENTITY_UNAVAILABLE")
        try:
            code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
                raise ValueError("RUN_PROCESS_IDENTITY_UNAVAILABLE")
            if code.value != 259:
                return None
            values = [wintypes.FILETIME() for _ in range(4)]
            if not kernel.GetProcessTimes(handle, *(ctypes.byref(value) for value in values)):
                raise ValueError("RUN_PROCESS_IDENTITY_UNAVAILABLE")
            return str((values[0].dwHighDateTime << 32) | values[0].dwLowDateTime)
        finally:
            kernel.CloseHandle(handle)
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        if fields[0] == "Z":
            return None
        return fields[19]
    except FileNotFoundError:
        return None
    except OSError as error:
        raise ValueError("RUN_PROCESS_IDENTITY_UNAVAILABLE") from error


def own_identity() -> tuple[int, str]:
    pid = os.getpid()
    created = process_created(pid)
    if created is None:
        raise ValueError("RUN_PROCESS_IDENTITY_UNAVAILABLE")
    return pid, created
