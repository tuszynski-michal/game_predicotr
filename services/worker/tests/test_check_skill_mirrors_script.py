from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location(
    "check_skill_mirrors_test_module", REPOSITORY_ROOT / "scripts" / "check_skill_mirrors.py"
)
assert _SPEC is not None and _SPEC.loader is not None
mirrors: ModuleType = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = mirrors
_SPEC.loader.exec_module(mirrors)

PAIR = ((".claude/skills/x/SKILL.md", ".agents/skills/x/SKILL.md"),)


def make(root: Path, left: bytes, right: bytes | None) -> None:
    (root / ".claude/skills/x").mkdir(parents=True)
    (root / ".claude/skills/x/SKILL.md").write_bytes(left)
    if right is not None:
        (root / ".agents/skills/x").mkdir(parents=True)
        (root / ".agents/skills/x/SKILL.md").write_bytes(right)


def test_identical_pair_passes(tmp_path: Path) -> None:
    make(tmp_path, "Treść\n".encode(), "Treść\n".encode())
    assert mirrors.check(tmp_path, PAIR) == []


def test_differing_copy_fails_with_clear_message(tmp_path: Path) -> None:
    make(tmp_path, b"a\n", b"a \n")
    problems = mirrors.check(tmp_path, PAIR)
    assert len(problems) == 1
    assert ".agents/skills/x/SKILL.md differs from .claude/skills/x/SKILL.md" in problems[0]


def test_line_ending_difference_is_a_difference(tmp_path: Path) -> None:
    make(tmp_path, b"a\nb\n", b"a\r\nb\r\n")
    assert len(mirrors.check(tmp_path, PAIR)) == 1


def test_missing_copy_fails(tmp_path: Path) -> None:
    make(tmp_path, b"a\n", None)
    problems = mirrors.check(tmp_path, PAIR)
    assert problems == ["missing skill file(s): .agents/skills/x/SKILL.md"]


def test_main_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make(tmp_path, b"a\n", b"b\n")
    assert mirrors.main(tmp_path, PAIR) == 1
    assert "check_skill_mirrors: FAIL" in capsys.readouterr().out
    (tmp_path / ".agents/skills/x/SKILL.md").write_bytes(b"a\n")
    assert mirrors.main(tmp_path, PAIR) == 0
    assert "check_skill_mirrors: OK" in capsys.readouterr().out


def test_repository_mirrors_are_identical() -> None:
    assert mirrors.check(REPOSITORY_ROOT) == []
