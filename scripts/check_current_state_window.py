"""Verify the rolling window of ai_docs/process/CURRENT_STATE.md (TASK-0938).

Checks:
1. every active task file ``ai_docs/tasks/NNNN-*.md`` has a heading containing
   ``TASK-NNNN`` (level 2-4) in CURRENT_STATE.md;
2. the section "Ostatnie 10 ukończonych tasków" has at most 10 done entries, each
   a one-line bullet ``- **TASK-NNNN** — title — vX.Y.N / hash — tasks/completed/<file>.md``;
3. the section "Obowiązujące ograniczenia" exists and is not empty.

Byte budgets (file, sections, active pointers, done entries) are owned by
``scripts/check_startup_read_budget.py``.

Exit code 0 when the window is consistent, 1 otherwise.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "ai_docs" / "process" / "CURRENT_STATE.md"
TASKS = ROOT / "ai_docs" / "tasks"
MAX_DONE = 10
CONSTRAINTS_HEADING = "## Obowiązujące ograniczenia"
DONE_HEADING = "## Ostatnie 10 ukończonych tasków"
# The commit hash is optional: a closing commit cannot contain its own hash,
# which the lead adds in the next commit.
DONE_ENTRY_RE = re.compile(
    r"^- \*\*TASK-\d{4}\*\* — .+ — v\d+\.\d+\.\d+( / .+)? — tasks/completed/\S+\.md$"
)


def section_lines(lines: list[str], heading: str) -> list[str] | None:
    """Lines of a ``##`` section (without the heading), or None when missing."""
    if heading not in lines:
        return None
    body: list[str] = []
    for line in lines[lines.index(heading) + 1 :]:
        if line.startswith("## "):
            break
        body.append(line)
    return body


def main(root: Path | None = None) -> int:
    """Check the window of ``root`` (default: this repository, via ``STATE``/``TASKS``)."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    state = STATE if root is None else root / "ai_docs" / "process" / "CURRENT_STATE.md"
    tasks = TASKS if root is None else root / "ai_docs" / "tasks"
    problems: list[str] = []
    raw = state.read_bytes()
    if raw.replace(b"\r\n", b"").count(b"\r"):
        # a bare CR (e.g. a tool that dropped the LF) still splits into lines below,
        # so the window would look valid while the file is one line for git
        problems.append("CURRENT_STATE.md contains bare CR line endings; use LF or CRLF")
    lines = raw.decode("utf-8").splitlines()

    headings = [line for line in lines if re.match(r"#{2,4} ", line)]
    active = sorted(
        path.name[:4] for path in tasks.glob("[0-9][0-9][0-9][0-9]-*.md") if path.is_file()
    )
    for task_id in active:
        pattern = re.compile(rf"\bTASK-{task_id}\b")
        if not any(pattern.search(heading) for heading in headings):
            problems.append(f"active task TASK-{task_id} has no section in CURRENT_STATE.md")

    done_body = section_lines(lines, DONE_HEADING)
    done: list[str] = []
    if done_body is None:
        problems.append(f'missing section "{DONE_HEADING[3:]}"')
    else:
        done = [line for line in done_body if line.strip()]
        for line in done:
            if not DONE_ENTRY_RE.match(line):
                problems.append(f"malformed done entry: {line[:80]}")
        if len(done) > MAX_DONE:
            problems.append(
                f"{len(done)} done entries, limit is {MAX_DONE}; delete the oldest "
                "(its full section is already in the archive)"
            )

    body = section_lines(lines, CONSTRAINTS_HEADING)
    if body is None:
        problems.append(f'missing section "{CONSTRAINTS_HEADING[3:]}"')
    else:
        if not any(line.startswith("- ") for line in body):
            problems.append('section "Obowiązujące ograniczenia" has no bullet points')

    if problems:
        print(f"check_current_state_window: FAIL ({len(problems)} problems)")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print(
        f"check_current_state_window: OK ({len(active)} active tasks, "
        f"{len(done)} done entries, {len(raw)} bytes)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
