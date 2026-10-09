from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
HOOK = REPOSITORY_ROOT / "scripts" / "hooks" / "block_large_read.py"
LARGE_BYTES = 300 * 1024


def _run(payload: object | str, extra_env: dict[str, str] | None = None) -> tuple[int, str]:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    env = {key: value for key, value in os.environ.items() if not key.startswith("GAME_PREDICTOR_")}
    env.update(extra_env or {})
    result = subprocess.run(
        [sys.executable, "-I", str(HOOK)],
        input=text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        env=env,
        check=False,
    )
    return result.returncode, result.stderr


def _read(path: Path, **extra: object) -> dict[str, object]:
    return {"tool_name": "Read", "tool_input": {"file_path": str(path), **extra}}


@pytest.fixture()
def large_file(tmp_path: Path) -> Path:
    path = tmp_path / "large.txt"
    path.write_bytes(b"x" * LARGE_BYTES)
    return path


@pytest.fixture()
def small_file(tmp_path: Path) -> Path:
    path = tmp_path / "small.txt"
    path.write_bytes(b"x" * 1024)
    return path


def test_large_file_without_range_is_blocked(large_file: Path) -> None:
    code, message = _run(_read(large_file))
    assert code == 2
    assert "CODE_MAP.md" in message
    assert "Odczyt zablokowany" in message
    assert "rg" in message


@pytest.mark.parametrize("extra", [{"limit": 50}, {"offset": 10}, {"offset": 0, "limit": 80}])
def test_large_file_with_range_is_allowed(large_file: Path, extra: dict[str, int]) -> None:
    assert _run(_read(large_file, **extra)) == (0, "")


def test_small_file_is_allowed(small_file: Path) -> None:
    assert _run(_read(small_file)) == (0, "")


def test_large_image_and_pdf_are_exempt(tmp_path: Path) -> None:
    for name in ("shot.png", "doc.pdf"):
        path = tmp_path / name
        path.write_bytes(b"x" * LARGE_BYTES)
        assert _run(_read(path)) == (0, "")


def test_other_tools_missing_files_and_garbage_fail_open(tmp_path: Path) -> None:
    assert _run({"tool_name": "Bash", "tool_input": {"command": "ls"}}) == (0, "")
    assert _run(_read(tmp_path / "missing.txt")) == (0, "")
    assert _run("not json") == (0, "")
    assert _run("[]") == (0, "")
    assert _run({"tool_name": "Read", "tool_input": "x"}) == (0, "")


def test_environment_switches(large_file: Path) -> None:
    assert _run(_read(large_file), {"GAME_PREDICTOR_ALLOW_LARGE_READ": "1"}) == (0, "")
    assert _run(_read(large_file), {"GAME_PREDICTOR_MAX_READ_BYTES": str(LARGE_BYTES)}) == (0, "")
    code, _ = _run(_read(large_file), {"GAME_PREDICTOR_MAX_READ_BYTES": "1000"})
    assert code == 2
