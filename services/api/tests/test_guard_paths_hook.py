from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
HOOK = REPOSITORY_ROOT / "scripts" / "hooks" / "guard_paths.py"


def _run(payload: object | str) -> tuple[int, str, str]:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    result = subprocess.run(
        [sys.executable, "-I", str(HOOK)],
        input=text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )
    return result.returncode, result.stdout, result.stderr


def _call(tool: str, path: str, **extra: object) -> dict[str, object]:
    key = "notebook_path" if tool == "NotebookEdit" else "file_path"
    return {"tool_name": tool, "tool_input": {key: path}, **extra}


@pytest.mark.parametrize(
    ("tool", "path"),
    [
        ("Edit", r"D:\game_predicotr\.env"),
        ("Write", "D:/game_predicotr/apps/admin/.env.local"),
        ("Edit", r"D:\game_predicotr\.ENV.production"),
        ("Write", r"D:\game_predicotr\.tooling\keys\release.jks"),
        ("Edit", "D:/game_predicotr/worktrees/x/.tooling/jdk/release/NOTICE"),
        ("Write", r"C:\Users\tuszy\Documents\game_predicotr\x.md"),
        ("Edit", "c:/users/TUSZY/documents/Game_Predicotr/services/api/main.py"),
        ("Edit", r"C:\Users\tuszy\Documents\game_predicotr\subdir\..\x.md"),
        ("Edit", r"D:\game_predicotr\package-lock.json"),
        ("Write", r"D:\game_predicotr\apps\admin\Package-Lock.json"),
        ("NotebookEdit", r"D:\game_predicotr\.env"),
    ],
)
def test_protected_paths_are_blocked(tool: str, path: str) -> None:
    code, stdout, stderr = _run(_call(tool, path))
    assert code == 2
    assert stdout == ""
    assert "Edycja zablokowana" in stderr
    assert path in stderr


def test_relative_path_is_resolved_against_cwd() -> None:
    code, _, stderr = _run(_call("Edit", "../.env", cwd=r"D:\game_predicotr\apps"))
    assert code == 2
    assert "Edycja zablokowana" in stderr
    old_copy = _call("Write", "docs/x.md", cwd=r"C:\Users\tuszy\Documents\game_predicotr")
    assert _run(old_copy)[0] == 2
    assert _run(_call("Edit", "../../.env", cwd=r"D:\game_predicotr\apps\admin"))[0] == 2


@pytest.mark.parametrize(
    ("tool", "path"),
    [
        ("Edit", r"D:\game_predicotr\.env.example"),
        ("Write", "D:/game_predicotr/apps/admin/.env.example"),
        ("Edit", r"D:\game_predicotr\services\api\environment.py"),
        ("Edit", r"D:\game_predicotr\docs\dotenv.md"),
        ("Write", r"D:\game_predicotr\ai_docs\guides\tooling.md"),
        ("Edit", r"D:\game_predicotr\scripts\tooling_notes.py"),
        ("Edit", r"D:\game_predicotr\package.json"),
        ("Edit", r"C:\Users\tuszy\Documents\game_predicotr_other\x.md"),
        ("Write", r"D:\game_predicotr\worktrees\game_predicotr\x.md"),
        ("Edit", r"C:\Users\tuszy\Documents\other\x.md"),
    ],
)
def test_ordinary_paths_are_allowed(tool: str, path: str) -> None:
    assert _run(_call(tool, path)) == (0, "", "")


def test_other_tools_and_garbage_fail_open() -> None:
    assert _run({"tool_name": "Read", "tool_input": {"file_path": ".env"}}) == (0, "", "")
    assert _run({"tool_name": "Bash", "tool_input": {"command": "echo > .env"}}) == (0, "", "")
    assert _run("not json") == (0, "", "")
    assert _run("[]") == (0, "", "")
    assert _run("") == (0, "", "")
    assert _run({"tool_name": "Edit", "tool_input": "x"}) == (0, "", "")
    assert _run({"tool_name": "Edit", "tool_input": {}}) == (0, "", "")
    assert _run({"tool_name": "Edit", "tool_input": {"file_path": 7}}) == (0, "", "")
    assert _run({"tool_name": "Edit", "tool_input": {"file_path": "  "}}) == (0, "", "")
    assert _run({"tool_name": "Edit"}) == (0, "", "")


def test_utf8_bom_and_polish_letters_in_stdin_are_handled() -> None:
    payload = "\ufeff" + json.dumps(
        _call("Edit", r"D:\game_predicotr\zażółć\.env"), ensure_ascii=False
    )
    code, _, stderr = _run(payload)
    assert code == 2
    assert "zażółć" in stderr
