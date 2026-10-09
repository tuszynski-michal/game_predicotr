from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location(
    "check_decision_links_test_module",
    REPOSITORY_ROOT / "scripts" / "check_decision_links.py",
)
assert _SPEC is not None and _SPEC.loader is not None
checker = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(checker)

ENTRY_HEADING = "## D-001 — Pierwsza decyzja"
ANCHOR = "d-001--pierwsza-decyzja"


@pytest.fixture
def tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    process = tmp_path / "ai_docs" / "process"
    (process / "decisions").mkdir(parents=True)
    (process / "decisions" / "DECISION_LOG_2026.md").write_text(
        f"# Log\n\n{ENTRY_HEADING}\n\n- Status: accepted\n", encoding="utf-8"
    )
    (process / "decisions" / "DECISION_INDEX_ARCHIVE.md").write_text(
        "# Archive\n", encoding="utf-8"
    )
    (process / "DECISION_LOG.md").write_text(
        "| Nr | T |\n|---|---|\n"
        f"| [D-001](decisions/DECISION_LOG_2026.md#{ANCHOR}) | Pierwsza | accepted | x | y |\n",
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text("agents\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("claude\n", encoding="utf-8")
    monkeypatch.setattr(checker, "ROOT", tmp_path)
    monkeypatch.setattr(checker, "PROCESS", process)
    monkeypatch.setattr(
        checker,
        "INDEX_FILES",
        [process / "DECISION_LOG.md", process / "decisions" / "DECISION_INDEX_ARCHIVE.md"],
    )
    monkeypatch.setattr(checker, "ENTRY_FILES", [process / "decisions" / "DECISION_LOG_2026.md"])
    monkeypatch.setattr(checker, "_anchor_cache", {})
    return tmp_path


def _run(problems: list[str]) -> None:
    checker.check_links(problems)
    checker.check_index(problems)
    checker.check_size(problems)


def test_valid_tree_has_no_problems(tree: Path) -> None:
    (tree / "ai_docs" / "note.md").write_text(
        f"[ok](process/decisions/DECISION_LOG_2026.md#{ANCHOR})\n", encoding="utf-8"
    )
    problems: list[str] = []
    _run(problems)
    assert problems == []


def test_existing_anchor_with_nonexistent_path_fails(tree: Path) -> None:
    (tree / "ai_docs" / "note.md").write_text(
        f"[bad](process/DECISION_LOG_2026.md#{ANCHOR})\n", encoding="utf-8"
    )
    problems: list[str] = []
    _run(problems)
    assert any("does not exist" in problem for problem in problems)


def test_missing_anchor_fails(tree: Path) -> None:
    (tree / "ai_docs" / "note.md").write_text(
        "[bad](process/decisions/DECISION_LOG_2026.md#d-999-brak)\n", encoding="utf-8"
    )
    problems: list[str] = []
    _run(problems)
    assert any("not found" in problem for problem in problems)


def test_oversized_decision_log_fails(tree: Path) -> None:
    log = tree / "ai_docs" / "process" / "DECISION_LOG.md"
    log.write_text(log.read_text(encoding="utf-8") + "x" * checker.MAX_LOG_BYTES, encoding="utf-8")
    problems: list[str] = []
    _run(problems)
    assert any("limit is" in problem for problem in problems)
