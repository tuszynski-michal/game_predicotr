"""Verify DECISION_LOG anchors and the decision index (TASK-0938).

Checks:
1. every ``DECISION_LOG*.md#d-...`` link found in ``ai_docs/**/*.md``,
   ``AGENTS.md`` and ``CLAUDE.md`` resolves to an existing heading anchor
   (GitHub-style slug, duplicate suffix ``-1``, ``-2`` ...) in the target file;
2. every ``| [D-NNN](file#anchor) |`` row of ``DECISION_LOG.md`` and
   ``decisions/DECISION_INDEX_*.md`` points at an existing heading, and the set
   of (number, anchor) pairs in the indexes equals the set of ``## D-NNN`` /
   ``### D-NNN`` headings (outside code fences) in ``decisions/DECISION_LOG_*.md``;
3. the newest full entries kept in ``DECISION_LOG.md`` are indexed too;
4. the whole ``DECISION_LOG.md`` stays below 100 000 bytes (when it approaches
   the limit, the oldest index rows move to ``decisions/DECISION_INDEX_ARCHIVE.md``).

Markdown links must resolve by their exact relative path; textual ``D-NNN``
references without a path are not checked.

Exit code 0 when everything resolves, 1 otherwise.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROCESS = ROOT / "ai_docs" / "process"
INDEX_FILES = [
    PROCESS / "DECISION_LOG.md",
    *sorted((PROCESS / "decisions").glob("DECISION_INDEX_*.md")),
]
ENTRY_FILES = sorted((PROCESS / "decisions").glob("DECISION_LOG_*.md"))

LINK_RE = re.compile(
    r"\]\((?P<path>[\w./\\-]*DECISION_LOG[\w-]*\.md)#(?P<anchor>d-\d[^\s)\]`'\">]*)"
)
ROW_RE = re.compile(r"^\| \[(?P<num>D-\d+)\]\((?P<path>[^)#]+)#(?P<anchor>[^)]+)\)")
HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.*?)[ \t]*$")
MAX_LOG_BYTES = 100_000
ENTRY_RE = re.compile(r"^#{2,3} (D-\d+)\b")


def github_slug(text: str) -> str:
    slug = text.strip().lower()
    slug = re.sub(r"[^\w\- ]", "", slug)
    return slug.replace(" ", "-")


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def headings(path: Path) -> list[tuple[str, str]]:
    """Return (heading line, anchor) for non-fenced headings, with duplicate suffixes."""
    seen: dict[str, int] = {}
    result: list[tuple[str, str]] = []
    fenced = False
    for line in read_lines(path):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        match = HEADING_RE.match(line)
        if not match:
            continue
        base = github_slug(match.group(2))
        count = seen.get(base, 0)
        seen[base] = count + 1
        result.append((line, base if count == 0 else f"{base}-{count}"))
    return result


_anchor_cache: dict[Path, set[str]] = {}


def anchors(path: Path) -> set[str]:
    if path not in _anchor_cache:
        _anchor_cache[path] = {anchor for _, anchor in headings(path)}
    return _anchor_cache[path]


def scan_files() -> list[Path]:
    files = sorted((ROOT / "ai_docs").rglob("*.md"))
    files += [ROOT / "AGENTS.md", ROOT / "CLAUDE.md"]
    return [path for path in files if path.is_file()]


def check_links(problems: list[str]) -> int:
    checked = 0
    for path in scan_files():
        fenced = False
        for number, line in enumerate(read_lines(path), start=1):
            if line.lstrip().startswith("```"):
                fenced = not fenced
                continue
            if fenced:
                continue
            for match in LINK_RE.finditer(line):
                checked += 1
                raw = match.group("path").replace("\\", "/")
                anchor = match.group("anchor").rstrip(".,;:")
                target = (path.parent / raw).resolve()
                if not target.is_file():
                    # Markdown links must name an existing relative path; there is
                    # deliberately no fallback to a same-named file elsewhere.
                    problems.append(
                        f"{path.relative_to(ROOT)}:{number}: link path {raw} does not exist "
                        "(resolved relative to the linking file)"
                    )
                    continue
                if anchor in anchors(target):
                    continue
                if target.name == "DECISION_LOG.md":
                    hits = [f.name for f in ENTRY_FILES if anchor in anchors(f)]
                    hint = f" (anchor now lives in decisions/{hits[0]})" if hits else ""
                else:
                    hint = ""
                problems.append(
                    f"{path.relative_to(ROOT)}:{number}: anchor #{anchor} not found in "
                    f"{target.relative_to(ROOT)}{hint}"
                )
    return checked


def check_index(problems: list[str]) -> tuple[int, int]:
    entry_pairs: dict[tuple[str, str], int] = {}
    for path in ENTRY_FILES:
        fenced = False
        anchor_by_line = {line: anchor for line, anchor in headings(path)}
        for line in read_lines(path):
            if line.lstrip().startswith("```"):
                fenced = not fenced
                continue
            if fenced:
                continue
            match = ENTRY_RE.match(line)
            if match:
                key = (match.group(1), anchor_by_line[line])
                entry_pairs[key] = entry_pairs.get(key, 0) + 1
    index_pairs: dict[tuple[str, str], int] = {}
    for path in INDEX_FILES:
        if not path.is_file():
            problems.append(f"missing index file {path.relative_to(ROOT)}")
            continue
        for number, line in enumerate(read_lines(path), start=1):
            match = ROW_RE.match(line)
            if not match:
                continue
            raw = match.group("path")
            target = (path.parent / raw).resolve()
            anchor = match.group("anchor")
            if not target.is_file() or anchor not in anchors(target):
                where = f"{path.relative_to(ROOT)}:{number}"
                problems.append(f"{where}: {match.group('num')} -> {raw}#{anchor} does not resolve")
            key = (match.group("num"), anchor)
            index_pairs[key] = index_pairs.get(key, 0) + 1
    for key in sorted(set(entry_pairs) - set(index_pairs)):
        problems.append(f"entry {key[0]} (#{key[1]}) has no index row")
    for key in sorted(set(index_pairs) - set(entry_pairs)):
        problems.append(f"index row {key[0]} (#{key[1]}) has no entry heading")
    for key, count in sorted(index_pairs.items()):
        if count > 1:
            problems.append(f"index row {key[0]} (#{key[1]}) listed {count} times")
    return len(entry_pairs), len(index_pairs)


def check_size(problems: list[str]) -> int:
    """Fail when the whole DECISION_LOG.md reaches the size limit.

    When the file approaches MAX_LOG_BYTES, move the oldest index rows to
    decisions/DECISION_INDEX_ARCHIVE.md.
    """
    size = (PROCESS / "DECISION_LOG.md").stat().st_size
    if size >= MAX_LOG_BYTES:
        problems.append(
            f"DECISION_LOG.md has {size} bytes, limit is {MAX_LOG_BYTES}; "
            "move the oldest index rows to decisions/DECISION_INDEX_ARCHIVE.md"
        )
    return size


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    problems: list[str] = []
    checked = check_links(problems)
    entries, rows = check_index(problems)
    size = check_size(problems)
    if problems:
        print(f"check_decision_links: FAIL ({len(problems)} problems)")
        for problem in problems[:100]:
            print(f"  {problem}")
        return 1
    print(
        f"check_decision_links: OK ({checked} anchor links, {entries} entries, "
        f"{rows} index rows, DECISION_LOG.md {size} bytes)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
