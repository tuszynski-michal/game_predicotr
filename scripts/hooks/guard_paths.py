"""Claude Code PreToolUse hook: block edits of protected paths (TASK-1040).

Reads the hook payload from stdin. For ``Edit``/``Write``/``NotebookEdit`` it blocks
(exit code 2, Polish reason on stderr) when the target path is:

* a ``.env`` file or ``.env.*`` other than ``.env.example`` (secrets);
* anything under ``.tooling/`` (isolated JDK/SDK and release signing keys);
* anything under the old copy ``C:\\Users\\tuszy\\Documents\\game_predicotr``;
* ``package-lock.json`` (changed by npm, never by hand).

Every other case exits 0 (allow). The hook fails open: malformed input never blocks.
Comparison is case-insensitive with normalised separators; relative paths are
resolved against the payload ``cwd``.

Run as ``python -I scripts/hooks/guard_paths.py`` (stdlib only).
"""

from __future__ import annotations

import json
import posixpath
import re
import sys
from typing import Any

BLOCK_EXIT_CODE = 2
GUARDED_TOOLS = frozenset({"Edit", "Write", "NotebookEdit"})
OLD_COPY_ROOT = "c:/users/tuszy/documents/game_predicotr"
_DRIVE = re.compile(r"^[a-z]:/")
_GIT_BASH_DRIVE = re.compile(r"^/([a-z])/")


def normalize(path: str, cwd: str = "") -> str:
    """Lower-cased, forward-slash, dot-segment-free form of ``path``."""
    text = path.strip().strip("\"'").replace("\\", "/").lower()
    text = _GIT_BASH_DRIVE.sub(r"\1:/", text)
    if not (_DRIVE.match(text) or text.startswith("/")) and cwd:
        base = _GIT_BASH_DRIVE.sub(r"\1:/", cwd.strip().replace("\\", "/").lower())
        text = f"{base}/{text}"
    text = posixpath.normpath(text)
    return text.rstrip("/") if len(text) > 1 else text


def decide(payload: Any) -> str | None:
    """Return the block message, or ``None`` when the call is allowed."""
    if not isinstance(payload, dict) or payload.get("tool_name") not in GUARDED_TOOLS:
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    raw = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not isinstance(raw, str) or not raw.strip():
        return None
    cwd = payload.get("cwd")
    path = normalize(raw, cwd if isinstance(cwd, str) else "")
    parts = [part for part in path.split("/") if part]
    name = parts[-1] if parts else ""

    if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
        return (
            f"Edycja zablokowana: {raw} to plik z sekretami (.env). Agent nie zapisuje plików "
            ".env; zmień go ręcznie albo edytuj .env.example (jedyny wyjątek)."
        )
    if ".tooling" in parts:
        return (
            f"Edycja zablokowana: {raw} jest w .tooling/ (izolowany JDK/SDK i klucze podpisu "
            "wydań). Nie edytuj ani nie drukuj tych plików; zmiana narzędzi to decyzja operatora."
        )
    if path == OLD_COPY_ROOT or path.startswith(OLD_COPY_ROOT + "/"):
        return (
            f"Edycja zablokowana: {raw} jest w starej kopii C:\\Users\\tuszy\\Documents\\"
            "game_predicotr, której nie wolno zmieniać. Pracuj w D:\\game_predicotr "
            "(dedykowany worktree)."
        )
    if name == "package-lock.json":
        return (
            f"Edycja zablokowana: {raw} zmienia się tylko przez npm (npm install / npm "
            "uninstall), nigdy ręcznie."
        )
    return None


def read_payload() -> Any:
    """Parse the stdin JSON as UTF-8 (a BOM from a PowerShell pipe is tolerated)."""
    return json.loads(sys.stdin.buffer.read().decode("utf-8-sig"))


def main() -> int:
    try:
        payload = read_payload()
    except (OSError, ValueError):
        return 0
    try:
        message = decide(payload)
    except Exception:  # noqa: BLE001 - fail open on any unexpected input shape
        return 0
    if message is None:
        return 0
    # UTF-8 explicitly: the Windows pipe code page is not UTF-8 by default.
    sys.stderr.buffer.write((message + "\n").encode("utf-8"))
    sys.stderr.buffer.flush()
    return BLOCK_EXIT_CODE


if __name__ == "__main__":
    raise SystemExit(main())
