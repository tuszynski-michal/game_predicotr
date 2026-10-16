from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location(
    "check_current_state_window_test_module",
    REPOSITORY_ROOT / "scripts" / "check_current_state_window.py",
)
assert _SPEC is not None and _SPEC.loader is not None
window = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = window
_SPEC.loader.exec_module(window)

DONE_LINE = "- **TASK-{n:04}** — Tytuł {n} — v1.0.{n} / abc{n:04} — tasks/completed/{n:04}-x.md\n"

STATE = """# Current State

## Obowiązujące ograniczenia

- Punkt pierwszy.{extra}

## Aktywne taski

### TASK-0001 — aktywny (todo)

- `ai_docs/tasks/0001-active.md`.

## Ostatnie 10 ukończonych tasków

{done}"""


def _write(root: Path, done_lines: list[str], extra: str = "") -> None:
    process = root / "ai_docs" / "process"
    process.mkdir(parents=True, exist_ok=True)
    tasks = root / "ai_docs" / "tasks"
    tasks.mkdir(parents=True, exist_ok=True)
    (tasks / "0001-active.md").write_text("# t\n", encoding="utf-8", newline="\n")
    (process / "CURRENT_STATE.md").write_text(
        STATE.format(done="".join(done_lines), extra=extra), encoding="utf-8", newline="\n"
    )


@pytest.fixture
def run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> Callable[[], tuple[int, str]]:
    monkeypatch.setattr(window, "STATE", tmp_path / "ai_docs" / "process" / "CURRENT_STATE.md")
    monkeypatch.setattr(window, "TASKS", tmp_path / "ai_docs" / "tasks")

    def call() -> tuple[int, str]:
        code = window.main()
        return code, capsys.readouterr().out

    return call


def test_repository_window_is_consistent() -> None:
    assert window.main() == 0


def test_new_format_passes(tmp_path: Path, run: Callable[[], tuple[int, str]]) -> None:
    _write(tmp_path, [DONE_LINE.format(n=n) for n in range(1, 11)])
    code, out = run()
    assert code == 0
    assert "10 done entries" in out


def test_eleven_done_entries_fail(tmp_path: Path, run: Callable[[], tuple[int, str]]) -> None:
    _write(tmp_path, [DONE_LINE.format(n=n) for n in range(1, 12)])
    code, out = run()
    assert code == 1
    assert "11 done entries" in out


def test_malformed_done_entry_fails(tmp_path: Path, run: Callable[[], tuple[int, str]]) -> None:
    _write(tmp_path, ["- **TASK-0001** — bez wersji i ścieżki\n"])
    code, out = run()
    assert code == 1
    assert "malformed done entry" in out


def test_old_done_section_format_is_rejected(
    tmp_path: Path, run: Callable[[], tuple[int, str]]
) -> None:
    _write(tmp_path, ["### TASK-0001 — stary (done)\n", "\n", "- opis\n"])
    code, out = run()
    assert code == 1
    assert "malformed done entry" in out


def test_active_task_without_section_fails(
    tmp_path: Path, run: Callable[[], tuple[int, str]]
) -> None:
    _write(tmp_path, [DONE_LINE.format(n=1)])
    (tmp_path / "ai_docs" / "tasks" / "0002-missing.md").write_text("# t\n", encoding="utf-8")
    code, out = run()
    assert code == 1
    assert "TASK-0002" in out


def test_file_size_is_not_checked_here(tmp_path: Path, run: Callable[[], tuple[int, str]]) -> None:
    _write(tmp_path, [DONE_LINE.format(n=1)], extra="x" * 150_000 + "\n")
    code, _ = run()
    assert code == 0
