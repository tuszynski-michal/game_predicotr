from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location(
    "close_task_test_module", REPOSITORY_ROOT / "scripts" / "close_task.py"
)
assert _SPEC is not None and _SPEC.loader is not None
close_task: ModuleType = importlib.util.module_from_spec(_SPEC)
# dataclasses resolve annotations through sys.modules, so register before executing.
sys.modules[_SPEC.name] = close_task
_SPEC.loader.exec_module(close_task)

STATE_PATH = "ai_docs/process/CURRENT_STATE.md"
ARCHIVE_PATH = "ai_docs/archive/CURRENT_STATE_2026Q4.md"
OLD_ARCHIVE_PATH = "ai_docs/archive/CURRENT_STATE_2026Q3.md"
COMPACT_ARCHIVE_PATH = "ai_docs/archive/CURRENT_STATE_ADMIN_COMPACT_2026-10-09.md"
TASK_PATH = "ai_docs/tasks/0001-first-task.md"
COMPLETED_PATH = "ai_docs/tasks/completed/0001-first-task.md"

TASK_FILE = """---
title: Pierwszy task
status: todo
last_updated: 2026-10-01
---

# TASK-0001 — Pierwszy task

## Status

`todo`

## Goal

Cel.

## Outcome

Commit: v1.0.20 (hash dopisuje kolejny commit).

Reszta wyniku.
"""

DONE_TEXT = """### TASK-0001 — Pierwszy task (done)

- Plik: `ai_docs/tasks/completed/0001-first-task.md`. Commit **v1.0.20**.
- Wynik: zrobione.
"""


def done_items(count: int) -> str:
    return "".join(
        f"- **TASK-{100 + n:04}** — stary {n} — v1.0.{n} / `abc{n:05}` — "
        f"tasks/completed/{100 + n:04}-old.md\n"
        for n in range(count, 0, -1)
    )


def state_text(done_count: int = 10, extra_pointer: bool = False) -> str:
    extra = (
        "### TASK-0002 — drugi (todo)\n\n- `ai_docs/tasks/0002-second.md`.\n\n"
        if extra_pointer
        else ""
    )
    return (
        "---\ntitle: Current project state\nstatus: active\nlast_updated: 2026-10-16\n---\n\n"
        "# Current State\n\nNagłówek z regułą.\n\n"
        "## Obowiązujące ograniczenia\n\n- Punkt pierwszy.\n\n"
        "## Aktywne taski\n\nWstęp.\n\n"
        "### TASK-0001 — Pierwszy task (todo)\n\n- `ai_docs/tasks/0001-first-task.md`.\n\n"
        f"{extra}"
        "## Ostatnie 10 ukończonych tasków\n\n"
        f"{done_items(done_count)}"
    )


ARCHIVE_Q4 = (
    "---\ntitle: Archive Q4\nstatus: archive\n---\n\n"
    "# Current State — archiwum 2026Q4\n\n"
    "### TASK-0050 — Starszy (done)\n\n- Commit **v1.0.5**.\n"
)
ARCHIVE_Q3 = (
    "# Current State — archiwum 2026Q3\n\n"
    "### TASK-0001 — Stary numer (done)\n\n- Commit **v1.0.20**.\n"
)


def run_git(root: Path, *args: str) -> str:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.autocrlf=false",
            *args,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=True,
    )
    return result.stdout


def write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    write(tmp_path, STATE_PATH, state_text())
    write(tmp_path, ARCHIVE_PATH, ARCHIVE_Q4)
    write(tmp_path, OLD_ARCHIVE_PATH, ARCHIVE_Q3)
    write(tmp_path, COMPACT_ARCHIVE_PATH, "# Compact\n")
    write(tmp_path, TASK_PATH, TASK_FILE)
    write(tmp_path, "ai_docs/tasks/completed/0100-old.md", "# old\n")
    run_git(tmp_path, "init", "-q")
    run_git(tmp_path, "add", "-A")
    run_git(tmp_path, "commit", "-q", "-m", "fixture")
    return tmp_path


@pytest.fixture
def done_file(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("done") / "done.md"
    path.write_bytes(DONE_TEXT.encode("utf-8"))
    return path


def snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


def close_args(done: Path, *extra: str) -> list[str]:
    return [
        "close",
        "TASK-0001",
        "--title",
        "Pierwszy task",
        "--version",
        "v1.0.20",
        "--done-file",
        str(done),
        "--date",
        "2026-10-17",
        *extra,
    ]


def run(root: Path, *args: str) -> int:
    return int(close_task.main(["--root", str(root), *args]))


def read(root: Path, relative: str) -> str:
    return (root / relative).read_bytes().decode("utf-8")


def test_close_moves_task_and_updates_window_archive_and_status(
    repo: Path, done_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(repo, *close_args(done_file)) == 0
    out = capsys.readouterr().out
    assert "checks: window and budgets pass" in out

    assert not (repo / TASK_PATH).exists()
    task = read(repo, COMPLETED_PATH)
    assert "status: done\nlast_updated: 2026-10-17\n" in task
    assert "## Status\n\n`done`\n\n## Goal" in task
    assert "title: Pierwszy task\n" in task
    assert "Commit: v1.0.20 (hash dopisuje kolejny commit)." in task
    # git performed a rename (tracked file).
    assert "R" in run_git(repo, "status", "--short", "--", "ai_docs/tasks").split()[0]

    state = read(repo, STATE_PATH)
    assert "TASK-0001 — Pierwszy task (todo)" not in state
    assert "Wstęp.\n\n## Ostatnie 10 ukończonych tasków\n\n" in state
    items = [
        line for line in state.split("## Ostatnie 10 ukończonych tasków\n")[1].splitlines() if line
    ]
    assert items[0] == (
        "- **TASK-0001** — Pierwszy task — v1.0.20 — tasks/completed/0001-first-task.md"
    )
    # 10 old items + the new one = 11; the oldest (stary 1, last line) is dropped.
    assert len(items) == 10
    assert "stary 1 " not in state
    assert "stary 2 " in state

    # newest archive (Q4) gets the section right under the title; Q3 and the compact copy stay.
    archive = read(repo, ARCHIVE_PATH)
    assert archive.startswith(ARCHIVE_Q4.split("# Current State")[0])
    assert (
        f"# Current State — archiwum 2026Q4\n\n{DONE_TEXT}\n### TASK-0050 — Starszy (done)"
    ) in archive
    assert read(repo, OLD_ARCHIVE_PATH) == ARCHIVE_Q3
    assert read(repo, COMPACT_ARCHIVE_PATH) == "# Compact\n"

    for relative in (STATE_PATH, ARCHIVE_PATH, COMPLETED_PATH):
        raw = (repo / relative).read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf")
        assert b"\r" not in raw
        assert raw.endswith(b"\n") and not raw.endswith(b"\n\n")


def test_close_with_fewer_than_ten_items_keeps_all(repo: Path, done_file: Path) -> None:
    write(repo, STATE_PATH, state_text(done_count=3))
    assert run(repo, *close_args(done_file)) == 0
    state = read(repo, STATE_PATH)
    assert state.count("- **TASK-") == 4


def test_close_into_empty_done_list(repo: Path, done_file: Path) -> None:
    write(repo, STATE_PATH, state_text(done_count=0))
    assert run(repo, *close_args(done_file)) == 0
    state = read(repo, STATE_PATH)
    assert state.endswith(
        "## Ostatnie 10 ukończonych tasków\n\n"
        "- **TASK-0001** — Pierwszy task — v1.0.20 — tasks/completed/0001-first-task.md\n"
    )


def test_status_section_without_blank_line_keeps_following_heading(
    repo: Path, done_file: Path
) -> None:
    write(
        repo,
        TASK_PATH,
        TASK_FILE.replace("## Status\n\n`todo`\n\n## Goal", "## Status\n`todo`\n## Goal"),
    )
    assert run(repo, *close_args(done_file)) == 0
    assert "## Status\n`done`\n## Goal\n" in read(repo, COMPLETED_PATH)


def test_close_preserves_crlf_files(repo: Path, done_file: Path) -> None:
    for relative in (STATE_PATH, ARCHIVE_PATH):
        write(repo, relative, read(repo, relative).replace("\n", "\r\n"))
    assert run(repo, *close_args(done_file)) == 0
    for relative in (STATE_PATH, ARCHIVE_PATH):
        raw = (repo / relative).read_bytes()
        assert raw.count(b"\n") == raw.count(b"\r\n")
    assert "**TASK-0001** — Pierwszy task — v1.0.20 — tasks/completed" in read(repo, STATE_PATH)


def test_close_untracked_task_file_is_moved_without_git(repo: Path, done_file: Path) -> None:
    run_git(repo, "rm", "-q", "--cached", TASK_PATH)
    assert run(repo, *close_args(done_file)) == 0
    assert (repo / COMPLETED_PATH).is_file()
    assert not (repo / TASK_PATH).exists()


def test_record_hash_updates_window_archive_and_outcome(
    repo: Path, done_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(repo, *close_args(done_file)) == 0
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-q", "-m", "v1.0.20 - TASK-0001")
    commit = run_git(repo, "rev-parse", "HEAD").strip()
    capsys.readouterr()

    assert run(repo, "record-hash", "TASK-0001", "--commit", commit) == 0

    short = commit[:8]
    assert (
        f"- **TASK-0001** — Pierwszy task — v1.0.20 / `{short}` — "
        "tasks/completed/0001-first-task.md"
    ) in read(repo, STATE_PATH)
    assert "Commit **v1.0.20 / `" + commit + "`**." in read(repo, ARCHIVE_PATH)
    assert f"Commit: v1.0.20 / `{commit}`.\n" in read(repo, COMPLETED_PATH)
    assert "Commit: v1.0.20 (hash" not in read(repo, COMPLETED_PATH)
    # the old Q3 section with the same task number and version is not touched
    assert read(repo, OLD_ARCHIVE_PATH) == ARCHIVE_Q3

    # a second run has nothing left to match and fails without writing
    before = snapshot(repo)
    assert run(repo, "record-hash", "TASK-0001", "--commit", commit) == 1
    assert snapshot(repo) == before


def test_record_hash_rejects_unknown_commit_and_malformed_hash(
    repo: Path, done_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(repo, *close_args(done_file)) == 0
    before = snapshot(repo)
    assert run(repo, "record-hash", "TASK-0001", "--commit", "a" * 40) == 1
    assert "does not exist" in capsys.readouterr().err
    assert run(repo, "record-hash", "TASK-0001", "--commit", "abc123") == 1
    assert "40-character" in capsys.readouterr().err
    assert snapshot(repo) == before


def test_record_hash_ambiguous_window_items_need_version(repo: Path, done_file: Path) -> None:
    write(repo, STATE_PATH, state_text(done_count=3))
    assert run(repo, *close_args(done_file)) == 0
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-q", "-m", "v1.0.20 - TASK-0001")
    commit = run_git(repo, "rev-parse", "HEAD").strip()
    state = read(repo, STATE_PATH)
    duplicate = "- **TASK-0001** — Pierwszy task — v1.0.20 — tasks/completed/0001-first-task.md\n"
    other = "- **TASK-0001** — Inny — v1.0.30 — tasks/completed/0001-first-task.md\n"
    write(repo, STATE_PATH, state.replace(duplicate, duplicate + other, 1))
    before = snapshot(repo)
    assert run(repo, "record-hash", "TASK-0001", "--commit", commit) == 1
    assert snapshot(repo) == before
    assert run(repo, "record-hash", "TASK-0001", "--commit", commit, "--version", "v1.0.20") == 0
    assert f"v1.0.20 / `{commit[:8]}`" in read(repo, STATE_PATH)
    assert "v1.0.30 — tasks" in read(repo, STATE_PATH)


def test_collision_of_two_task_files_is_an_error(
    repo: Path, done_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(repo, "ai_docs/tasks/0001-other-task.md", TASK_FILE)
    before = snapshot(repo)
    assert run(repo, *close_args(done_file)) == 1
    err = capsys.readouterr().err
    assert "several active task files" in err
    assert "0001-first-task.md" in err and "0001-other-task.md" in err
    assert snapshot(repo) == before


def test_missing_task_file_is_an_error(
    repo: Path, done_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (repo / TASK_PATH).unlink()
    before = snapshot(repo)
    assert run(repo, *close_args(done_file)) == 1
    assert "no active task file" in capsys.readouterr().err
    assert snapshot(repo) == before


def test_completed_directory_files_are_not_candidates(repo: Path, done_file: Path) -> None:
    write(repo, "ai_docs/tasks/completed/0001-already.md", "# old\n")
    assert run(repo, *close_args(done_file)) == 0


def test_missing_pointer_is_an_error(
    repo: Path, done_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(
        repo,
        STATE_PATH,
        state_text().replace("TASK-0001 — Pierwszy task (todo)", "Inny wskaźnik (todo)"),
    )
    before = snapshot(repo)
    assert run(repo, *close_args(done_file)) == 1
    assert "pointer" in capsys.readouterr().err
    assert snapshot(repo) == before


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("### TASK-0002 — Zły numer (done)\n\nv1.0.20\n", "must start with a heading"),
        ("### TASK-0001 — Brak statusu\n\nv1.0.20\n", "must start with a heading"),
        ("### TASK-0001 — Bez wersji (done)\n\n- Commit.\n", "never mentions v1.0.20"),
        ("### TASK-0001 — Inna wersja (done)\n\n- Commit v1.0.200.\n", "never mentions v1.0.20"),
    ],
)
def test_invalid_done_file_is_an_error(
    repo: Path,
    tmp_path_factory: pytest.TempPathFactory,
    capsys: pytest.CaptureFixture[str],
    text: str,
    message: str,
) -> None:
    bad = tmp_path_factory.mktemp("bad") / "bad.md"
    bad.write_bytes(text.encode("utf-8"))
    before = snapshot(repo)
    assert run(repo, *close_args(bad)) == 1
    assert message in capsys.readouterr().err
    assert snapshot(repo) == before


def test_dry_run_prints_plan_and_writes_nothing(
    repo: Path, done_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = snapshot(repo)
    status_before = run_git(repo, "status", "--short")
    assert run(repo, "--dry-run", *close_args(done_file)) == 0
    out = capsys.readouterr().out
    assert "DRY RUN: no file written" in out
    assert "window:    add - **TASK-0001** — Pierwszy task — v1.0.20" in out
    assert "window:    drop - **TASK-0101**" in out
    assert "checks: window and budgets would pass" in out
    assert snapshot(repo) == before
    assert run_git(repo, "status", "--short") == status_before


def test_dry_run_reports_a_failing_check_without_writing(
    repo: Path, done_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = snapshot(repo)
    args = ["--dry-run", *close_args(done_file)]
    args[args.index("Pierwszy task")] = "T" * 450
    assert run(repo, *args) == 1
    err = capsys.readouterr().err
    assert "checks would fail" in err and "done entry" in err
    assert snapshot(repo) == before


def test_red_budget_check_rolls_back_every_write_and_the_move(
    repo: Path, done_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = snapshot(repo)
    status_before = run_git(repo, "status", "--short")
    args = close_args(done_file)
    args[args.index("Pierwszy task")] = "T" * 450  # window item exceeds the 400 B budget
    assert run(repo, *args) == 1
    err = capsys.readouterr().err
    assert "checks failed after the change" in err and "done entry" in err
    assert snapshot(repo) == before
    assert (repo / TASK_PATH).is_file() and not (repo / COMPLETED_PATH).exists()
    assert run_git(repo, "status", "--short") == status_before
    # the repository is intact: the very same close works with a sane title
    assert run(repo, *close_args(done_file)) == 0


def test_red_window_check_rolls_back(
    repo: Path, done_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # An unrelated active task without a pointer makes the window check fail after closing.
    write(repo, "ai_docs/tasks/0002-second.md", TASK_FILE.replace("0001", "0002"))
    before = snapshot(repo)
    assert run(repo, *close_args(done_file)) == 1
    err = capsys.readouterr().err
    assert "TASK-0002 has no section" in err
    assert snapshot(repo) == before
    assert (repo / TASK_PATH).is_file()


def test_malformed_arguments_are_errors(
    repo: Path, done_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        run(
            repo,
            "close",
            "TASK-1",
            "--title",
            "x",
            "--version",
            "v1.0.20",
            "--done-file",
            str(done_file),
        )
        == 1
    )
    assert (
        run(
            repo,
            "close",
            "TASK-0001",
            "--title",
            "x",
            "--version",
            "1.0.20",
            "--done-file",
            str(done_file),
        )
        == 1
    )
    assert (
        run(
            repo,
            "close",
            "TASK-0001",
            "--title",
            "x",
            "--version",
            "v1.0.20",
            "--done-file",
            str(done_file) + ".missing",
        )
        == 1
    )
    assert capsys.readouterr().err.count("close_task: ERROR") == 3
