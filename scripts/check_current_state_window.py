"""Verify the rolling window of ai_docs/process/CURRENT_STATE.md (TASK-0938).

Checks:
1. every active task file ``ai_docs/tasks/NNNN-*.md`` has a heading containing
   ``TASK-NNNN`` (level 2-4) in CURRENT_STATE.md;
2. at most 10 ``### TASK-... (done...)`` sections;
3. the section "Obowiązujące ograniczenia" exists and is not empty;
4. the file is smaller than 100 KB (100 000 bytes).

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
MAX_BYTES = 100_000
CONSTRAINTS_HEADING = "## Obowiązujące ograniczenia"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    problems: list[str] = []
    raw = STATE.read_bytes()
    lines = raw.decode("utf-8").splitlines()
    if len(raw) >= MAX_BYTES:
        problems.append(f"CURRENT_STATE.md has {len(raw)} bytes, limit is {MAX_BYTES}")

    headings = [line for line in lines if re.match(r"#{2,4} ", line)]
    active = sorted(
        path.name[:4] for path in TASKS.glob("[0-9][0-9][0-9][0-9]-*.md") if path.is_file()
    )
    for task_id in active:
        pattern = re.compile(rf"\bTASK-{task_id}\b")
        if not any(pattern.search(heading) for heading in headings):
            problems.append(f"active task TASK-{task_id} has no section in CURRENT_STATE.md")

    done = [line for line in lines if re.match(r"### TASK-\d+.*\(done", line)]
    if len(done) > MAX_DONE:
        problems.append(
            f"{len(done)} done sections, limit is {MAX_DONE}; move the oldest to the archive"
        )

    if CONSTRAINTS_HEADING not in lines:
        problems.append(f'missing section "{CONSTRAINTS_HEADING[3:]}"')
    else:
        start = lines.index(CONSTRAINTS_HEADING)
        body = []
        for line in lines[start + 1 :]:
            if line.startswith("## "):
                break
            body.append(line)
        if not any(line.startswith("- ") for line in body):
            problems.append('section "Obowiązujące ograniczenia" has no bullet points')

    if problems:
        print(f"check_current_state_window: FAIL ({len(problems)} problems)")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print(
        f"check_current_state_window: OK ({len(active)} active tasks, "
        f"{len(done)} done sections, {len(raw)} bytes)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
