from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _load(name: str, relative: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPOSITORY_ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


code_map = _load("generate_code_map_test_module", "scripts/generate_code_map.py")
collect = _load("token_pilot_collect_test_module", "scripts/token_pilot_collect.py")


def test_code_map_check_detects_staleness_and_is_stable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(code_map, "MAP_PATH", tmp_path / "CODE_MAP.md")
    monkeypatch.setattr(code_map, "SYMBOLS_PATH", tmp_path / "CODE_MAP_SYMBOLS.md")
    assert code_map.main_with_args(["--check"]) == 1
    assert code_map.main_with_args([]) == 0
    first = (tmp_path / "CODE_MAP.md").read_bytes(), (tmp_path / "CODE_MAP_SYMBOLS.md").read_bytes()
    assert code_map.main_with_args(["--check"]) == 0
    assert code_map.main_with_args([]) == 0
    second = (
        (tmp_path / "CODE_MAP.md").read_bytes(),
        (tmp_path / "CODE_MAP_SYMBOLS.md").read_bytes(),
    )
    assert first == second
    (tmp_path / "CODE_MAP.md").write_text("stale", encoding="utf-8")
    assert code_map.main_with_args(["--check"]) == 1


def test_code_map_extracts_public_symbols(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(code_map, "ROOT", tmp_path)
    source = tmp_path / "module.py"
    source.write_text(
        '"""Doc line."""\n\nclass Public: ...\nclass _Private: ...\n'
        "def run() -> None: ...\nasync def go() -> None: ...\ndef _hidden() -> None: ...\n",
        encoding="utf-8",
    )
    module = code_map.python_module(source)
    assert module.symbols == ["class Public", "run", "go"]
    assert module.doc == "Doc line."
    ts = tmp_path / "view.tsx"
    ts.write_text(
        "export function View() {}\nexport const LIMIT = 3;\nexport type Props = {};\n"
        "const hidden = 1;\n",
        encoding="utf-8",
    )
    assert code_map.ts_module(ts).symbols == ["View", "LIMIT", "Props"]


def _assistant(message_id: str, **usage: int) -> str:
    return json.dumps(
        {
            "type": "assistant",
            "message": {"id": message_id, "model": "m", "usage": usage},
        }
    )


def test_collect_dedupes_streamed_lines_and_adds_subagents(tmp_path: Path) -> None:
    session = tmp_path / "abc.jsonl"
    session.write_text(
        "\n".join(
            [
                _assistant("m1", input_tokens=2, output_tokens=5, cache_read_input_tokens=100),
                _assistant("m1", input_tokens=2, output_tokens=40, cache_read_input_tokens=100),
                _assistant("m2", input_tokens=1, output_tokens=10, cache_creation_input_tokens=50),
                json.dumps({"type": "user", "message": {"usage": {"input_tokens": 999}}}),
                "not json",
            ]
        ),
        encoding="utf-8",
    )
    subagents = tmp_path / "abc" / "subagents"
    subagents.mkdir(parents=True)
    (subagents / "agent-1.jsonl").write_text(
        _assistant("s1", input_tokens=3, output_tokens=7), encoding="utf-8"
    )
    usage = collect.session_usage(session)
    assert (usage.input_tokens, usage.output_tokens) == (6, 57)
    assert (usage.cache_creation_tokens, usage.cache_read_tokens) == (50, 100)
    assert usage.calls == 3


def test_collect_renders_delta_and_disqualification(tmp_path: Path) -> None:
    rows = [
        {
            "variant": "baseline",
            "task": "T1",
            "run": "1",
            "input_tokens": "1000",
            "quality": "PASS",
        },
        {
            "variant": "baseline",
            "task": "T1",
            "run": "2",
            "input_tokens": "1000",
            "quality": "PASS",
        },
        {"variant": "serena", "task": "T1", "run": "1", "input_tokens": "500", "quality": "PASS"},
        {"variant": "graphify", "task": "T1", "run": "1", "input_tokens": "400", "quality": "FAIL"},
        {"variant": "serena", "task": "indexing", "run": "1", "input_tokens": "200"},
    ]
    table = collect.render_table(rows)
    assert "-50.0%" in table
    assert "DYSKWALIFIKACJA" in table
    assert "Koszt jednorazowy indeksowania" in table


def test_symbol_index_lists_every_symbol_and_check_detects_a_late_rename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    module = package / "wide.py"
    names = [f"function_{index:02d}" for index in range(12)]

    def write(late_name: str) -> None:
        body = [f"def {name}() -> None: ..." for name in names[:-1]] + [
            f"def {late_name}() -> None: ..."
        ]
        module.write_text("\n".join(body) + "\n", encoding="utf-8")

    write("late_symbol_name")
    monkeypatch.setattr(code_map, "ROOT", tmp_path)
    monkeypatch.setattr(code_map, "SYMBOL_ROOTS", ("pkg",))
    monkeypatch.setattr(code_map, "MAP_PATH", tmp_path / "CODE_MAP.md")
    monkeypatch.setattr(code_map, "SYMBOLS_PATH", tmp_path / "CODE_MAP_SYMBOLS.md")
    monkeypatch.setattr(code_map, "render_overview", lambda: "overview\n")

    index = code_map.render_symbols()
    assert "late_symbol_name" in index  # the 12th symbol is searchable
    assert "(+" not in index  # the index is never truncated
    assert "(+" in code_map.format_symbols(names)  # the overview keeps its cap

    assert code_map.main_with_args([]) == 0
    assert code_map.main_with_args(["--check"]) == 0
    write("renamed_late_symbol")
    assert code_map.main_with_args(["--check"]) == 1
