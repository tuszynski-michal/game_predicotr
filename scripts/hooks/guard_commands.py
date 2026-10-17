"""Claude Code PreToolUse hook: ask before destructive shell commands (TASK-1040).

Reads the hook payload from stdin. For ``Bash``/``PowerShell`` it prints a
``permissionDecision: "ask"`` JSON (exit code 0) with a Polish reason when the
command text matches one of the destructive patterns below; otherwise it prints
nothing and exits 0. The hook never denies and fails open: malformed input or an
unexpected exception never blocks a call.

Patterns (the command is split into segments on ``; && || | newline`` outside
quotes, nested ``cmd /c``, ``powershell -Command`` and ``bash -c`` strings are
analysed recursively):

* ``db:reset`` anywhere in the command;
* ``git push`` with ``--force``/``-f``/``--force-with-lease``/``+refspec``;
  ``git reset --hard``; ``git clean`` with ``-f``; ``git worktree remove`` with
  ``--force``/``-f``; ``git branch -D``;
* SQL ``DROP DATABASE|TABLE|SCHEMA`` and ``TRUNCATE`` (case-insensitive, also
  inside quotes, so a commit message mentioning them asks too);
* recursive delete (``rm -r``, ``Remove-Item -Recurse``, ``rmdir /s``) whose target
  is the repository root, ``D:\\game_predicotr`` itself, or a path with a ``.venv``
  or ``node_modules`` component (junctions in worktrees included: a recursive
  delete through a junction removes the target's contents). ``cmd /c rmdir <path>``
  without ``/s`` (junction-safe unlink) and deletes of other paths stay allowed;
* write-type git commands and file-writing cmdlets/redirections that target the
  old copy ``C:\\Users\\tuszy\\Documents\\game_predicotr`` (path in the segment, or a
  ``cd`` into it earlier in the command). Read-only git commands stay allowed.

Run as ``python -I scripts/hooks/guard_commands.py`` (stdlib only).
"""

from __future__ import annotations

import json
import os
import posixpath
import re
import sys
from pathlib import Path
from typing import Any

GUARDED_TOOLS = frozenset({"Bash", "PowerShell"})
D_ROOT = "d:/game_predicotr"
OLD_COPY_ROOT = "c:/users/tuszy/documents/game_predicotr"
OLD_COPY_TEXT = re.compile(
    r"(?:\b[a-z]:|(?<![\w.])/[a-z])[\\/]+users[\\/]+tuszy[\\/]+documents[\\/]+game_predicotr",
    re.IGNORECASE,
)
SQL_DESTRUCTIVE = re.compile(
    r"\bDROP\s+(?:DATABASE|TABLE|SCHEMA)\b"
    r"|\bTRUNCATE\s+TABLE\b"
    r"|\bTRUNCATE\s+(?:ONLY\s+)?[\w.\"]+\s*(?:;|[\"'`]|\b(?:RESTART|CONTINUE|CASCADE)\b)",
    re.IGNORECASE,
)
DB_RESET = re.compile(r"\bdb:reset", re.IGNORECASE)
CD_TO_OLD_COPY = re.compile(
    r"\b(?:cd|chdir|pushd|set-location|sl)\s+(?:-(?:path|literalpath)\s+)?[\"']?"
    + OLD_COPY_TEXT.pattern,
    re.IGNORECASE,
)
REDIRECT_TO_OLD_COPY = re.compile(r">>?\s*[\"']?" + OLD_COPY_TEXT.pattern, re.IGNORECASE)

WRAPPER_PREFIXES = frozenset({"&", "call", "command", "time", "sudo", "nohup", "exec", "env"})
SHELL_WRAPPERS = frozenset({"cmd", "powershell", "pwsh", "bash", "sh", "wsl"})
INLINE_FLAGS = frozenset({"/c", "/k", "-c", "-command"})
GIT_OPTIONS_WITH_VALUE = frozenset({"-c", "--git-dir", "--work-tree", "--namespace", "-C"})
GIT_WRITE_COMMANDS = frozenset(
    {
        "commit",
        "push",
        "merge",
        "reset",
        "checkout",
        "switch",
        "rebase",
        "stash",
        "mv",
        "rm",
        "add",
        "restore",
        "clean",
        "pull",
        "cherry-pick",
        "revert",
    }
)
DELETE_COMMANDS = frozenset({"rm", "remove-item", "ri", "rmdir", "rd", "del", "erase"})
WRITE_CMDLETS = frozenset(
    {
        "set-content",
        "out-file",
        "add-content",
        "remove-item",
        "move-item",
        "copy-item",
        "ri",
        "mi",
        "move",
        "cp",
        "copy",
        "cpi",
        "mv",
        "rm",
        "del",
        "erase",
        "rmdir",
        "rd",
        "sc",
        "ac",
    }
)
COPY_COMMANDS = frozenset({"copy-item", "cp", "copy", "cpi"})
CMD_STYLE_DELETE = frozenset({"rmdir", "rd", "del", "erase"})
POWERSHELL_RECURSE = frozenset({"-r", "-re", "-rec", "-recu", "-recur", "-recurs", "-recurse"})
SHORT_FLAG_CLUSTER = re.compile(r"^-[a-zA-Z]{1,4}$")
FORCE_CLUSTER = re.compile(r"^-[a-zA-Z]*f[a-zA-Z]*$")
DELETE_BRANCH_CLUSTER = re.compile(r"^-[a-zA-Z]*D[a-zA-Z]*$")
_DRIVE = re.compile(r"^[a-z]:/")
_GIT_BASH_DRIVE = re.compile(r"^/([a-z])/")
_ENV_ASSIGNMENT = re.compile(r"^\w+=")
_TOKEN = re.compile(r"\"[^\"]*\"|'[^']*'|\S+")


def split_segments(command: str) -> list[str]:
    """Split on ``; && || | newline`` outside single/double quotes."""
    segments: list[str] = []
    current: list[str] = []
    quote = ""
    index = 0
    while index < len(command):
        char = command[index]
        if quote:
            if char == quote:
                quote = ""
            current.append(char)
        elif char in "\"'":
            quote = char
            current.append(char)
        elif char in ";|\n&" and (char != "&" or command[index : index + 2] == "&&"):
            segments.append("".join(current))
            current = []
            if command[index : index + 2] in ("&&", "||"):
                index += 1
        else:
            current.append(char)
        index += 1
    segments.append("".join(current))
    return [segment.strip() for segment in segments if segment.strip()]


def tokenize(segment: str) -> list[str]:
    return [token.strip("\"'") for token in _TOKEN.findall(segment)]


def normalize(path: str, cwd: str = "") -> str:
    """Lower-cased, forward-slash, dot-segment-free path; ``""`` when unresolvable."""
    text = path.strip().strip("\"'").replace("\\", "/").lower()
    if not text or "$" in text or "%" in text:
        return ""
    text = _GIT_BASH_DRIVE.sub(r"\1:/", text)
    if not (_DRIVE.match(text) or text.startswith("/")) and cwd:
        base = _GIT_BASH_DRIVE.sub(r"\1:/", cwd.strip().replace("\\", "/").lower())
        text = f"{base}/{text}"
    text = posixpath.normpath(text)
    return text.rstrip("/") if len(text) > 1 else text


def project_root(environ: dict[str, str]) -> str:
    raw = environ.get("CLAUDE_PROJECT_DIR") or str(Path(__file__).resolve().parents[2])
    return normalize(raw)


def _command_start(tokens: list[str]) -> int:
    index = 0
    while index < len(tokens) and (
        tokens[index].lower() in WRAPPER_PREFIXES or _ENV_ASSIGNMENT.match(tokens[index])
    ):
        index += 1
    return index


def _basename(token: str) -> str:
    return token.replace("\\", "/").rsplit("/", 1)[-1].lower()


def _git_parts(tokens: list[str]) -> tuple[str, list[str]] | None:
    """Return ``(subcommand, arguments after it)`` for a ``git`` invocation."""
    start = _command_start(tokens)
    if start >= len(tokens) or _basename(tokens[start]) not in {"git", "git.exe"}:
        return None
    index = start + 1
    while index < len(tokens) and tokens[index].startswith("-"):
        index += 2 if tokens[index] in GIT_OPTIONS_WITH_VALUE else 1
    if index >= len(tokens):
        return None
    return tokens[index].lower(), tokens[index + 1 :]


def _has_force_flag(args: list[str]) -> bool:
    for arg in args:
        if arg in {"--force", "--force-if-includes"} or arg.startswith("--force-with-lease"):
            return True
        if FORCE_CLUSTER.match(arg):
            return True
    return False


def _git_destructive(subcommand: str, args: list[str]) -> str | None:
    if subcommand == "push" and (
        _has_force_flag(args) or any(arg.startswith("+") and len(arg) > 1 for arg in args)
    ):
        return "git push z wymuszeniem (--force / -f / --force-with-lease / +refspec)"
    if subcommand == "reset" and "--hard" in args:
        return "git reset --hard (traci niezacommitowane zmiany)"
    if subcommand == "clean" and (
        "--force" in args or any(FORCE_CLUSTER.match(arg) for arg in args)
    ):
        return "git clean -f (usuwa nieśledzone pliki)"
    if subcommand == "worktree" and args[:1] == ["remove"] and _has_force_flag(args[1:]):
        return "git worktree remove --force"
    if subcommand == "branch" and any(DELETE_BRANCH_CLUSTER.match(arg) for arg in args):
        return "git branch -D (usuwa gałąź bez sprawdzenia scalenia)"
    return None


def _is_recursive(command_name: str, args: list[str]) -> bool:
    for arg in args:
        lowered = arg.lower().split(":", 1)[0]
        if command_name in CMD_STYLE_DELETE and lowered == "/s":
            return True
        if arg == "--recursive" or lowered in POWERSHELL_RECURSE:
            return True
        if SHORT_FLAG_CLUSTER.match(arg) and "r" in arg.lower():
            return True
    return False


def _delete_targets(command_name: str, args: list[str]) -> list[str]:
    targets: list[str] = []
    for arg in args:
        if arg.startswith("-"):
            continue
        if command_name in CMD_STYLE_DELETE and arg.startswith("/") and len(arg) <= 3:
            continue
        targets.extend(part for part in arg.split(",") if part)
    return targets


def _risky_delete_target(target: str, cwd: str, roots: set[str]) -> bool:
    text = target.replace("\\", "/")
    # Strip a trailing wildcard/dot so `repo/*` and `repo/.` count as the root.
    while text.endswith(("/*", "/.")):
        text = text[:-2]
    path = normalize(text, cwd)
    if not path:
        return False
    if text in {"*", "."}:
        path = normalize(cwd) if cwd else ""
    if path in roots:
        return True
    parts = [part for part in path.split("/") if part]
    return ".venv" in parts or "node_modules" in parts


def _delete_reason(tokens: list[str], cwd: str, roots: set[str]) -> str | None:
    start = _command_start(tokens)
    if start >= len(tokens):
        return None
    name = _basename(tokens[start]).removesuffix(".exe")
    if name not in DELETE_COMMANDS:
        return None
    args = tokens[start + 1 :]
    if not _is_recursive(name, args):
        return None
    if any(_risky_delete_target(target, cwd, roots) for target in _delete_targets(name, args)):
        return (
            "rekurencyjne usuwanie katalogu głównego repozytorium, D:\\game_predicotr, .venv "
            "albo node_modules (przez junction usuwa zawartość celu); bezpieczne odlinkowanie: "
            "cmd /c rmdir <ścieżka> bez /s"
        )
    return None


def _old_copy_write_reason(
    segment: str, tokens: list[str], after_cd_to_old_copy: bool
) -> str | None:
    mentions = bool(OLD_COPY_TEXT.search(segment))
    if not (mentions or after_cd_to_old_copy):
        return None
    reason = (
        "polecenie zapisujące w starej kopii C:\\Users\\tuszy\\Documents\\game_predicotr "
        "(której nie wolno zmieniać)"
    )
    if REDIRECT_TO_OLD_COPY.search(segment):
        return reason
    start = _command_start(tokens)
    if start >= len(tokens):
        return None
    name = _basename(tokens[start]).removesuffix(".exe")
    git = _git_parts(tokens)
    if git is not None:
        return reason if git[0] in GIT_WRITE_COMMANDS else None
    if name not in WRITE_CMDLETS:
        return None
    if name in COPY_COMMANDS:
        # Copying FROM the old copy only reads it: ask when it is the destination.
        args = [arg for arg in tokens[start + 1 :] if not arg.startswith("-")]
        destination = args[-1] if len(args) >= 2 else ""
        explicit = [
            tokens[i + 1]
            for i, token in enumerate(tokens[:-1])
            if token.lower() in {"-destination", "-dest"}
        ]
        candidates = explicit or ([destination] if destination else [])
        if candidates:
            return reason if any(OLD_COPY_TEXT.search(c) for c in candidates) else None
        return reason if after_cd_to_old_copy else None
    return reason


def analyze(command: str, cwd: str, roots: set[str], depth: int = 0) -> list[str]:
    reasons: list[str] = []
    if DB_RESET.search(command):
        reasons.append("db:reset (reset bazy)")
    if SQL_DESTRUCTIVE.search(command):
        reasons.append("SQL DROP DATABASE/TABLE/SCHEMA lub TRUNCATE")
    after_cd = bool(CD_TO_OLD_COPY.search(command))
    for segment in split_segments(command):
        tokens = tokenize(segment)
        if not tokens:
            continue
        start = _command_start(tokens)
        if (
            depth < 2
            and start < len(tokens)
            and _basename(tokens[start]).removesuffix(".exe") in SHELL_WRAPPERS
        ):
            for index, token in enumerate(tokens[start + 1 :], start + 1):
                if token.lower() in INLINE_FLAGS:
                    inner = segment.split(tokens[index], 1)[-1].strip()
                    if len(inner) >= 2 and inner[0] == inner[-1] and inner[0] in "\"'":
                        inner = inner[1:-1]
                    reasons.extend(analyze(inner, cwd, roots, depth + 1))
                    break
        git = _git_parts(tokens)
        if git is not None:
            found = _git_destructive(*git)
            if found:
                reasons.append(found)
        delete = _delete_reason(tokens, cwd, roots)
        if delete:
            reasons.append(delete)
        old_copy = _old_copy_write_reason(segment, tokens, after_cd)
        if old_copy:
            reasons.append(old_copy)
    return list(dict.fromkeys(reasons))


def decide(payload: Any, environ: dict[str, str]) -> str | None:
    """Return the ask reason, or ``None`` when the command is allowed."""
    if not isinstance(payload, dict) or payload.get("tool_name") not in GUARDED_TOOLS:
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    command = tool_input.get("command")
    if not isinstance(command, str) or not command.strip():
        return None
    cwd = payload.get("cwd")
    roots = {D_ROOT, project_root(environ)}
    reasons = analyze(command, cwd if isinstance(cwd, str) else "", roots)
    if not reasons:
        return None
    return "Polecenie wymaga potwierdzenia operatora: " + "; ".join(reasons) + "."


def read_payload() -> Any:
    """Parse the stdin JSON as UTF-8 (a BOM from a PowerShell pipe is tolerated)."""
    return json.loads(sys.stdin.buffer.read().decode("utf-8-sig"))


def main() -> int:
    try:
        payload = read_payload()
        reason = decide(payload, dict(os.environ))
    except Exception:  # noqa: BLE001 - fail open on any malformed input
        return 0
    if reason is None:
        return 0
    decision = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": reason,
        }
    }
    # ASCII-only JSON (\\u escapes) is safe on any Windows pipe code page.
    sys.stdout.write(json.dumps(decision) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
