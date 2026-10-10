"""Claude Code PreToolUse hook: block whole-file reads of large files (TASK-0939).

Reads the hook payload from stdin. For the ``Read`` tool it blocks (exit code 2,
reason on stderr) when the file is larger than 200 KB and the call has no
``offset``/``limit`` (and no ``pages``). Every other case exits 0 (allow). The
hook fails open: malformed input or an unreadable path never blocks a call.

Environment overrides (set in the shell that starts Claude Code):

* ``GAME_PREDICTOR_ALLOW_LARGE_READ=1`` - disable the check entirely;
* ``GAME_PREDICTOR_MAX_READ_BYTES=<n>`` - change the threshold (default 204800).

Run as ``python -I scripts/hooks/block_large_read.py`` (stdlib only).
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

DEFAULT_MAX_BYTES = 200 * 1024
# Binary formats are read through the Read tool's own image/PDF handling.
EXEMPT_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".pdf"})
BLOCK_EXIT_CODE = 2


def threshold(environ: Mapping[str, str]) -> int:
    raw = environ.get("GAME_PREDICTOR_MAX_READ_BYTES", "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    return DEFAULT_MAX_BYTES


def decide(payload: Any, environ: Mapping[str, str], cwd: Path | None = None) -> str | None:
    """Return the block message, or ``None`` when the call is allowed."""
    if environ.get("GAME_PREDICTOR_ALLOW_LARGE_READ", "").strip() == "1":
        return None
    if not isinstance(payload, dict) or payload.get("tool_name") != "Read":
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    if any(tool_input.get(key) is not None for key in ("offset", "limit", "pages")):
        return None
    file_path = tool_input.get("file_path")
    if not isinstance(file_path, str) or not file_path:
        return None
    path = Path(file_path)
    if not path.is_absolute():
        base = Path(str(payload.get("cwd") or cwd or Path.cwd()))
        path = base / path
    if path.suffix.lower() in EXEMPT_SUFFIXES:
        return None
    try:
        size = path.stat().st_size
    except OSError:
        return None
    limit = threshold(environ)
    if size <= limit:
        return None
    return (
        f"Odczyt zablokowany: {file_path} ma {size // 1024} KB (limit {limit // 1024} KB) "
        "i wywołanie nie ma offset/limit. Zacznij od ai_docs/architecture/CODE_MAP.md "
        "(mapa obszarów) i ai_docs/architecture/CODE_MAP_SYMBOLS.md, wyszukaj miejsce "
        "przez rg (np. rg -n '<symbol>' <katalog>), a potem powtórz Read z offset i limit "
        "obejmującymi tylko potrzebny fragment. Wyłączenie hooka: ai_docs/guides/TOKEN_TOOLING.md."
    )


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (OSError, ValueError):
        return 0
    message = decide(payload, os.environ)
    if message is None:
        return 0
    # UTF-8 explicitly: the Windows pipe code page is not UTF-8 by default.
    sys.stderr.buffer.write((message + "\n").encode("utf-8"))
    sys.stderr.buffer.flush()
    return BLOCK_EXIT_CODE


if __name__ == "__main__":
    raise SystemExit(main())
