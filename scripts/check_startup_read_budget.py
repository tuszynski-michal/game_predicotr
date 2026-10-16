"""Measure the mandatory startup read and enforce its byte budgets (TASK-1019).

The mandatory startup read is the set of documents every agent session reads
before a task (``AGENTS.md`` "Obowiązkowa kolejność czytania"). Claude Code also
loads ``CLAUDE.md`` automatically, so it is measured separately.

Budgets come from ``ai_docs/delivery/STARTUP_READ_DIET_EXECUTION_PLAN_20261016.md``
(decision D3). Every budget has an ``enforced`` flag: a budget that is not
enforced is only reported; an enforced budget makes the script exit 1 when it is
exceeded. This script is the single owner of size limits for these documents.

Usage: ``python scripts/check_startup_read_budget.py [--report]``.
Exit code 0 when every enforced budget holds, 1 otherwise.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

AGENTS = "AGENTS.md"
README = "ai_docs/README.md"
CURRENT_STATE = "ai_docs/process/CURRENT_STATE.md"
DECISION_LOG = "ai_docs/process/DECISION_LOG.md"
CLAUDE = "CLAUDE.md"
STARTUP_FILES = (AGENTS, README, CURRENT_STATE, DECISION_LOG)

CONSTRAINTS = "Obowiązujące ograniczenia"
PLANS = "Plany z niezakończonymi taskami"
ACTIVE = "Aktywne taski"
DONE = "Ostatnie 10 ukończonych tasków"

HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.*?)[ \t]*$")
INDEX_ROW_RE = re.compile(r"^\| \[D-\d+\]")


@dataclass(frozen=True)
class Section:
    level: int
    title: str
    lines: list[str]

    @property
    def size(self) -> int:
        return sum(len(line.encode("utf-8")) for line in self.lines)


def read_lines(root: Path, relative: str) -> list[str]:
    """Lines with LF endings; empty when the file is missing.

    Sizes are measured with LF line endings so that a Windows checkout with
    ``core.autocrlf=true`` (CRLF on disk) and an LF checkout give the same result.
    """
    path = root / relative
    if not path.is_file():
        return []
    return path.read_bytes().replace(b"\r\n", b"\n").decode("utf-8").splitlines(keepends=True)


def file_size(root: Path, relative: str) -> int:
    """Byte size with LF line endings (see ``read_lines``)."""
    path = root / relative
    return len(path.read_bytes().replace(b"\r\n", b"\n")) if path.is_file() else 0


def sections(lines: list[str]) -> list[Section]:
    """Split Markdown into ``##``/``###`` sections; headings in code fences do not count.

    A section runs from its heading to the next heading of the same or a higher
    level (``##`` sections contain their ``###`` subsections).
    """
    starts: list[tuple[int, int, str]] = []
    fenced = False
    for number, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        match = HEADING_RE.match(line.rstrip("\r\n"))
        if match and len(match.group(1)) in (2, 3):
            starts.append((number, len(match.group(1)), match.group(2)))
    result: list[Section] = []
    for position, (start, level, title) in enumerate(starts):
        end = len(lines)
        for later_start, later_level, _ in starts[position + 1 :]:
            if later_level <= level:
                end = later_start
                break
        result.append(Section(level, title, lines[start:end]))
    return result


def top_section(lines: list[str], title: str) -> Section | None:
    for section in sections(lines):
        if section.level == 2 and section.title == title:
            return section
    return None


def section_items(section: Section) -> list[tuple[str, int]]:
    """Items of a section: its ``###`` subsections, else its top-level bullets."""
    subsections = [item for item in sections(section.lines) if item.level == 3]
    if subsections:
        return [(item.title, item.size) for item in subsections]
    items: list[tuple[str, int]] = []
    for line in section.lines[1:]:
        if line.startswith("- "):
            items.append((line[2:62].strip(), len(line.encode("utf-8"))))
        elif items and line.startswith("  ") and line.strip():
            label, size = items[-1]
            items[-1] = (label, size + len(line.encode("utf-8")))
    return items


Measure = Callable[[Path], list[tuple[str, int]]]


def _file(relative: str) -> Measure:
    return lambda root: [(relative, file_size(root, relative))]


def _section(title: str) -> Measure:
    def measure(root: Path) -> list[tuple[str, int]]:
        section = top_section(read_lines(root, CURRENT_STATE), title)
        return [(title, section.size if section else 0)]

    return measure


def _items(title: str) -> Measure:
    def measure(root: Path) -> list[tuple[str, int]]:
        section = top_section(read_lines(root, CURRENT_STATE), title)
        return section_items(section) if section else []

    return measure


def _index_rows(root: Path) -> list[tuple[str, int]]:
    rows = sum(1 for line in read_lines(root, DECISION_LOG) if INDEX_ROW_RE.match(line))
    return [("DECISION_LOG.md index rows", rows)]


def _startup_total(root: Path) -> list[tuple[str, int]]:
    return [("startup total", sum(file_size(root, name) for name in STARTUP_FILES))]


@dataclass(frozen=True)
class Budget:
    name: str
    limit: int
    enforced: bool
    measure: Measure
    unit: str = "B"
    hint: str = ""


BUDGETS: tuple[Budget, ...] = (
    Budget(
        "DECISION_LOG.md",
        12_000,
        True,
        _file(DECISION_LOG),
        hint="move the oldest index rows to decisions/DECISION_INDEX_ARCHIVE.md",
    ),
    Budget(
        "DECISION_LOG.md index rows",
        30,
        True,
        _index_rows,
        unit="rows",
        hint="move the oldest index rows to decisions/DECISION_INDEX_ARCHIVE.md",
    ),
    Budget(
        "CURRENT_STATE.md",
        30_000,
        True,
        _file(CURRENT_STATE),
        hint="shorten sections or move blocks unchanged to ai_docs/archive/",
    ),
    Budget(f"section {CONSTRAINTS}", 8_000, True, _section(CONSTRAINTS)),
    Budget(f"section {PLANS}", 5_000, True, _section(PLANS)),
    Budget(
        "active task section",
        1_200,
        True,
        _items(ACTIVE),
        hint="keep status, task file, blocker or next step; details belong in the task Outcome",
    ),
    Budget(
        "done entry",
        400,
        True,
        _items(DONE),
        hint="one line per done task; the full section goes to the archive",
    ),
    Budget(
        "CLAUDE.md",
        6_000,
        True,
        _file(CLAUDE),
        hint="keep only Claude-specific guidance; process rules belong in AGENTS.md",
    ),
    Budget(
        "startup total",
        90_000,
        True,
        _startup_total,
        hint="shrink the largest file of the mandatory startup read",
    ),
)


def check(root: Path, budgets: tuple[Budget, ...] = BUDGETS) -> list[str]:
    """Return one problem per measured item that exceeds an enforced budget."""
    problems: list[str] = []
    for budget in budgets:
        if not budget.enforced:
            continue
        for label, value in budget.measure(root):
            if value > budget.limit:
                hint = f"; {budget.hint}" if budget.hint else ""
                problems.append(
                    f"{budget.name} [{label}]: {value} {budget.unit}, "
                    f"budget {budget.limit} {budget.unit}{hint}"
                )
    return problems


def report(root: Path, budgets: tuple[Budget, ...] = BUDGETS) -> list[str]:
    """Human-readable measurement of files, sections and budgets."""
    out = ["Files (bytes):"]
    for name in (*STARTUP_FILES, CLAUDE):
        suffix = "" if name in STARTUP_FILES else "  (loaded by Claude Code, not in total)"
        out.append(f"  {file_size(root, name):>8}  {name}{suffix}")
    out.append(f"  {_startup_total(root)[0][1]:>8}  startup total")
    out.append("CURRENT_STATE.md sections (bytes):")
    for section in sections(read_lines(root, CURRENT_STATE)):
        indent = "  " if section.level == 2 else "      "
        out.append(f"  {section.size:>8}{indent}{'#' * section.level} {section.title[:80]}")
    out.append(f"DECISION_LOG.md index rows: {_index_rows(root)[0][1]}")
    out.append("Budgets:")
    for budget in budgets:
        values = budget.measure(root)
        worst = max((value for _, value in values), default=0)
        over = sum(1 for _, value in values if value > budget.limit)
        state = "enforced" if budget.enforced else "report-only"
        out.append(
            f"  {budget.name}: max {worst} / {budget.limit} {budget.unit}, "
            f"{over} over ({len(values)} measured, {state})"
        )
    return out


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--report", action="store_true", help="print the full measurement")
    args = parser.parse_args(argv)
    if args.report:
        print("\n".join(report(ROOT)))
    problems = check(ROOT)
    if problems:
        print(f"check_startup_read_budget: FAIL ({len(problems)} problems)")
        for problem in problems:
            print(f"  {problem}")
        return 1
    total = _startup_total(ROOT)[0][1]
    enforced = sum(1 for budget in BUDGETS if budget.enforced)
    print(
        f"check_startup_read_budget: OK (startup read {total} bytes, "
        f"{enforced}/{len(BUDGETS)} budgets enforced)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
