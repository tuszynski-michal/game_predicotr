from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
HOOK = REPOSITORY_ROOT / "scripts" / "hooks" / "format_edited_file.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("format_edited_file_hook", HOOK)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hook = _load()


def _run(payload: object | str, project_dir: Path | None = None) -> tuple[int, str, str]:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    env = {key: value for key, value in os.environ.items() if key != "CLAUDE_PROJECT_DIR"}
    if project_dir is not None:
        env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    result = subprocess.run(
        [sys.executable, "-I", str(HOOK)],
        input=text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=40,
        env=env,
        check=False,
    )
    return result.returncode, result.stdout, result.stderr


@pytest.mark.parametrize(
    ("relative", "expected"),
    [
        ("services/api/src/game_predictor_api/main.py", "ruff"),
        ("services/worker/tests/test_x.py", "ruff"),
        ("services/test_support/helpers.py", "ruff"),
        ("scripts/hooks/guard_paths.py", "ruff"),
        ("scripts/x.PY", "ruff"),
        ("Services/API/src/x.py", "ruff"),
        ("package.json", "prettier"),
        ("README.md", "prettier"),
        ("eslint.config.mjs", "prettier"),
        ("apps/admin/src/app/page.tsx", "prettier"),
        ("apps/reviewer/package.json", "prettier"),
        ("infra/compose.yaml", "prettier"),
        ("packages/shared-ts/src/index.ts", "prettier"),
        ("packages/shared-ts/styles/site.css", "prettier"),
        ("ai_docs/guides/CLAUDE_CODE_AUTOMATIONS.md", None),
        ("ai_docs/process/CURRENT_STATE.md", None),
        ("AGENTS.md", "prettier"),
        ("services/api/alembic.ini", None),
        ("services/api/openapi.json", None),
        ("services/other/x.py", None),
        ("services/x.py", None),
        ("apps/admin/notes.txt", None),
        ("apps/admin/script.py", None),
        ("docs/readme.md", None),
        ("src/x.ts", None),
        ("scripts/run.ps1", None),
        ("scripts/data.json", None),
        ("tests/test_x.py", None),
        (".claude/settings.json", None),
    ],
)
def test_classification(relative: str, expected: str | None) -> None:
    assert hook.classify(REPOSITORY_ROOT / relative, REPOSITORY_ROOT) == expected


def test_files_outside_the_repository_are_not_formatted(tmp_path: Path) -> None:
    assert hook.classify(tmp_path / "scripts" / "x.py", REPOSITORY_ROOT) is None
    assert hook.classify(REPOSITORY_ROOT.parent / "scripts" / "x.py", REPOSITORY_ROOT) is None
    assert hook.classify(REPOSITORY_ROOT, REPOSITORY_ROOT) is None


def test_formatter_command_is_none_without_formatter(tmp_path: Path) -> None:
    source = tmp_path / "scripts" / "x.py"
    assert hook.formatter_command("ruff", source, tmp_path) is None
    assert hook.formatter_command("prettier", tmp_path / "package.json", tmp_path) is None


def test_missing_formatter_fails_open_and_leaves_the_file(tmp_path: Path) -> None:
    source = tmp_path / "scripts" / "x.py"
    source.parent.mkdir()
    messy = "x   =  1\n"
    source.write_text(messy, encoding="utf-8")
    payload = {"tool_name": "Edit", "tool_input": {"file_path": str(source)}}
    assert _run(payload, tmp_path) == (0, "", "")
    assert source.read_text(encoding="utf-8") == messy
    manifest = tmp_path / "package.json"
    manifest.write_text('{"a":1}', encoding="utf-8")
    payload = {"tool_name": "Write", "tool_input": {"file_path": str(manifest)}}
    assert _run(payload, tmp_path) == (0, "", "")
    assert manifest.read_text(encoding="utf-8") == '{"a":1}'


def test_broken_formatter_fails_open(tmp_path: Path) -> None:
    python = tmp_path / ".venv" / ("Scripts" if os.name == "nt" else "bin")
    python.mkdir(parents=True)
    fake = python / ("python.exe" if os.name == "nt" else "python")
    fake.write_bytes(b"not an executable")
    source = tmp_path / "scripts" / "x.py"
    source.parent.mkdir()
    source.write_text("x   =  1\n", encoding="utf-8")
    payload = {"tool_name": "Edit", "tool_input": {"file_path": str(source)}}
    assert _run(payload, tmp_path) == (0, "", "")
    assert source.read_text(encoding="utf-8") == "x   =  1\n"


def test_other_tools_missing_files_and_garbage_fail_open(tmp_path: Path) -> None:
    source = tmp_path / "scripts" / "x.py"
    source.parent.mkdir()
    source.write_text("x   =  1\n", encoding="utf-8")
    assert _run({"tool_name": "Bash", "tool_input": {"file_path": str(source)}}, tmp_path) == (
        0,
        "",
        "",
    )
    assert _run({"tool_name": "Edit", "tool_input": {"file_path": str(tmp_path / "no.py")}}) == (
        0,
        "",
        "",
    )
    assert _run("not json") == (0, "", "")
    assert _run("[]") == (0, "", "")
    assert _run({"tool_name": "Edit", "tool_input": "x"}) == (0, "", "")
    assert _run({"tool_name": "Edit", "tool_input": {"file_path": 3}}) == (0, "", "")
    assert _run({"tool_name": "Edit"}) == (0, "", "")
    assert source.read_text(encoding="utf-8") == "x   =  1\n"
