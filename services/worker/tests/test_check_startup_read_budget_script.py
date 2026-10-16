from __future__ import annotations

import dataclasses
import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location(
    "check_startup_read_budget_test_module",
    REPOSITORY_ROOT / "scripts" / "check_startup_read_budget.py",
)
assert _SPEC is not None and _SPEC.loader is not None
budget = importlib.util.module_from_spec(_SPEC)
# dataclasses resolve annotations through sys.modules, so register before executing.
sys.modules[_SPEC.name] = budget
_SPEC.loader.exec_module(budget)

STATE = """# Current State

## Obowiązujące ograniczenia

- Punkt pierwszy.
  Ciąg dalszy punktu.

## Aktywne taski

### TASK-0001 — krótki (todo)

- Plik taska.

```markdown
## To nie jest sekcja
```

### TASK-0002 — długi (todo)

{long}

## Ostatnie 10 ukończonych tasków

- **TASK-0003** — zamknięty — v1.0.1 / abc — tasks/completed/0003-x.md
- **TASK-0004** — zamknięty — v1.0.2 / def — tasks/completed/0004-x.md
"""


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    process = tmp_path / "ai_docs" / "process"
    process.mkdir(parents=True)
    (process / "CURRENT_STATE.md").write_text(
        STATE.format(long="x" * 1500), encoding="utf-8", newline="\n"
    )
    rows = "".join(f"| [D-{n:03}](d.md#d-{n:03}) | t | accepted |\n" for n in range(1, 32))
    (process / "DECISION_LOG.md").write_text(f"# Decision Log\n\n{rows}", encoding="utf-8")
    (tmp_path / "ai_docs" / "README.md").write_text("readme\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("agents\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("claude\n", encoding="utf-8")
    return tmp_path


def _enforce(name: str) -> tuple[Any, ...]:
    return tuple(dataclasses.replace(item, enforced=item.name == name) for item in budget.BUDGETS)


def test_repository_passes_with_current_flags() -> None:
    assert budget.check(REPOSITORY_ROOT) == []


def test_unenforced_budgets_only_report(tree: Path) -> None:
    unenforced = tuple(dataclasses.replace(item, enforced=False) for item in budget.BUDGETS)
    assert budget.check(tree, unenforced) == []
    text = "\n".join(budget.report(tree, unenforced))
    assert "startup total" in text
    assert "DECISION_LOG.md index rows: 31" in text
    assert "### TASK-0002" in text


def test_enforced_section_budget_fails_with_hint(tree: Path) -> None:
    problems = budget.check(tree, _enforce("active task section"))
    assert len(problems) == 1
    assert "TASK-0002" in problems[0]
    assert "budget 1200 B" in problems[0]
    assert "task Outcome" in problems[0]


def test_enforced_index_rows_budget_fails(tree: Path) -> None:
    problems = budget.check(tree, _enforce("DECISION_LOG.md index rows"))
    assert problems and "31 rows, budget 30 rows" in problems[0]


def test_heading_inside_code_fence_is_not_a_section(tree: Path) -> None:
    lines = budget.read_lines(tree, budget.CURRENT_STATE)
    titles = [section.title for section in budget.sections(lines)]
    assert "To nie jest sekcja" not in titles
    assert "TASK-0001 — krótki (todo)" in titles


def test_bullet_items_include_continuation_lines(tree: Path) -> None:
    lines = budget.read_lines(tree, budget.CURRENT_STATE)
    constraints = budget.top_section(lines, budget.CONSTRAINTS)
    assert constraints is not None
    items = budget.section_items(constraints)
    assert len(items) == 1
    assert items[0][1] == len("- Punkt pierwszy.\n  Ciąg dalszy punktu.\n".encode())
    done = budget.top_section(lines, budget.DONE)
    assert done is not None
    assert len(budget.section_items(done)) == 2


def test_current_state_budgets_are_enforced_by_default() -> None:
    enforced = {item.name for item in budget.BUDGETS if item.enforced}
    assert {
        "CURRENT_STATE.md",
        f"section {budget.CONSTRAINTS}",
        f"section {budget.PLANS}",
        "active task section",
        "done entry",
    } <= enforced


def test_default_flags_fail_on_active_section_over_1200_bytes(tree: Path) -> None:
    problems = budget.check(tree)
    assert any("active task section [TASK-0002" in problem for problem in problems)


def test_default_flags_fail_on_file_over_30000_bytes(tree: Path) -> None:
    state = tree / budget.CURRENT_STATE
    state.write_text(STATE.format(long="x" * 30_000), encoding="utf-8", newline="\n")
    problems = budget.check(tree)
    assert any(
        problem.startswith("CURRENT_STATE.md [") and "budget 30000 B" in problem
        for problem in problems
    )


def test_default_flags_fail_on_done_entry_over_400_bytes(tree: Path) -> None:
    state = tree / budget.CURRENT_STATE
    text = state.read_text(encoding="utf-8")
    state.write_text(
        text + "- **TASK-0005** — " + "y" * 450 + " — v1.0.3 / ghi — tasks/completed/0005-x.md\n",
        encoding="utf-8",
        newline="\n",
    )
    problems = budget.check(tree)
    assert any(problem.startswith("done entry [") for problem in problems)
