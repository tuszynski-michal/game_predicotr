"""Verify that mirrored skill copies are byte-identical (TASK-1030).

The canonical text of a skill lives in ``.claude/skills/<name>/SKILL.md``. Codex
reads its copy from ``.agents/skills/<name>/SKILL.md`` (verified with the installed
Codex CLI, see TASK-1030 Outcome). Skills that differ on purpose by audit
direction (``audit-task`` and ``claude-audit``) are not listed here.

Exit code 0 when every listed pair exists and is identical, 1 otherwise.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (canonical Claude Code copy, Codex copy), relative to the repository root.
MIRRORED_PAIRS: tuple[tuple[str, str], ...] = (
    (".claude/skills/task-close/SKILL.md", ".agents/skills/task-close/SKILL.md"),
)


def check(root: Path, pairs: tuple[tuple[str, str], ...] = MIRRORED_PAIRS) -> list[str]:
    """One problem per missing or differing mirrored pair."""
    problems: list[str] = []
    for canonical, mirror in pairs:
        left = root / canonical
        right = root / mirror
        missing = [
            name for name, path in ((canonical, left), (mirror, right)) if not path.is_file()
        ]
        if missing:
            problems.append(f"missing skill file(s): {', '.join(missing)}")
        elif left.read_bytes() != right.read_bytes():
            problems.append(
                f"{mirror} differs from {canonical}; copy the canonical file over the mirror"
            )
    return problems


def main(root: Path = ROOT, pairs: tuple[tuple[str, str], ...] = MIRRORED_PAIRS) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    problems = check(root, pairs)
    if problems:
        print(f"check_skill_mirrors: FAIL ({len(problems)} problems)")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print(f"check_skill_mirrors: OK ({len(pairs)} mirrored pairs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
