"""Claude Code PostToolUse hook: format only the file that was just edited (TASK-1040).

Reads the hook payload from stdin. For ``Edit``/``Write`` it formats the edited file
when it is inside the repository root (``CLAUDE_PROJECT_DIR``, fallback: this
script's repository):

* ``.py`` under ``services/api``, ``services/worker``, ``services/test_support`` or
  ``scripts`` -> ``<repo>/.venv/Scripts/python.exe -m ruff format <file>``;
* files in the ``format:check`` prettier scope of ``package.json`` (root-level
  ``*.{css,js,json,md,mjs,ts,tsx,yaml,yml}`` and the same extensions under ``apps/``,
  ``infra/`` and ``packages/``) -> ``<repo>/node_modules/.bin/prettier(.cmd) --write``.

Anything else (for example ``ai_docs/**/*.md``) is left untouched. The hook is
fail-open: a missing formatter, a timeout (20 s) or any error exits 0 silently, and
nothing is ever printed.

Run as ``python -I scripts/hooks/format_edited_file.py`` (stdlib only).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

FORMAT_TIMEOUT_SECONDS = 20
GUARDED_TOOLS = frozenset({"Edit", "Write"})
RUFF_ROOTS = (
    ("services", "api"),
    ("services", "worker"),
    ("services", "test_support"),
    ("scripts",),
)
PRETTIER_SUFFIXES = frozenset(
    {".css", ".js", ".json", ".md", ".mjs", ".ts", ".tsx", ".yaml", ".yml"}
)
PRETTIER_DIRECTORIES = frozenset({"apps", "infra", "packages"})


def repository_root(environ: dict[str, str]) -> Path:
    raw = environ.get("CLAUDE_PROJECT_DIR")
    return Path(raw) if raw else Path(__file__).resolve().parents[2]


def relative_parts(file_path: Path, root: Path) -> tuple[str, ...] | None:
    """Path parts of ``file_path`` relative to ``root``, or ``None`` when outside it."""
    try:
        relative = os.path.relpath(os.path.abspath(file_path), os.path.abspath(root))
    except ValueError:  # different drive on Windows
        return None
    parts = PurePosixPath(relative.replace("\\", "/")).parts
    if not parts or parts[0] == "..":
        return None
    return parts


def classify(file_path: Path, root: Path) -> str | None:
    """Return ``"ruff"``, ``"prettier"`` or ``None`` (leave the file untouched)."""
    parts = relative_parts(file_path, root)
    if parts is None:
        return None
    parts = tuple(part.lower() for part in parts)
    suffix = file_path.suffix.lower()
    if suffix == ".py" and any(parts[: len(prefix)] == prefix for prefix in RUFF_ROOTS):
        return "ruff"
    if suffix in PRETTIER_SUFFIXES and (len(parts) == 1 or parts[0] in PRETTIER_DIRECTORIES):
        return "prettier"
    return None


def formatter_command(kind: str, file_path: Path, root: Path) -> list[str] | None:
    windows = os.name == "nt"
    if kind == "ruff":
        python = root / ".venv" / ("Scripts/python.exe" if windows else "bin/python")
        command = [str(python), "-m", "ruff", "format", "--force-exclude", str(file_path)]
        return command if python.exists() else None
    prettier = root / "node_modules" / ".bin" / ("prettier.cmd" if windows else "prettier")
    return [str(prettier), "--write", str(file_path)] if prettier.exists() else None


def target_file(payload: Any) -> Path | None:
    if not isinstance(payload, dict) or payload.get("tool_name") not in GUARDED_TOOLS:
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    raw = tool_input.get("file_path")
    if not isinstance(raw, str) or not raw.strip():
        return None
    path = Path(raw)
    if not path.is_absolute():
        cwd = payload.get("cwd")
        path = Path(cwd if isinstance(cwd, str) and cwd else os.getcwd()) / path
    return path if path.is_file() else None


def read_payload() -> Any:
    """Parse the stdin JSON as UTF-8 (a BOM from a PowerShell pipe is tolerated)."""
    return json.loads(sys.stdin.buffer.read().decode("utf-8-sig"))


def main() -> int:
    try:
        payload = read_payload()
        file_path = target_file(payload)
        if file_path is None:
            return 0
        root = repository_root(dict(os.environ))
        kind = classify(file_path, root)
        if kind is None:
            return 0
        command = formatter_command(kind, file_path, root)
        if command is None:
            return 0
        subprocess.run(
            command,
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=FORMAT_TIMEOUT_SECONDS,
            check=False,
        )
    except Exception:  # noqa: BLE001 - formatting must never block or fail a tool call
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
