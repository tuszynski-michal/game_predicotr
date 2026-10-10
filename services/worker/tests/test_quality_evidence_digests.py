"""TASK-0940: checksum-bound quality evidence must match the files it pins.

The reports in ``ai_docs/quality`` pin each other by raw SHA-256. A re-pin that
stops short of a fixed point (or an edit of one report without updating its
referrers) leaves intermediate digests behind; this test runs the repository
checker so the gate catches that drift.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[3]


def _checker() -> ModuleType:
    path = ROOT / "scripts" / "check_quality_evidence_digests.py"
    spec = importlib.util.spec_from_file_location("check_quality_evidence_digests", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_pinned_quality_digest_matches_its_file() -> None:
    assert _checker().find_mismatches() == []


def test_checker_flags_a_stale_digest_and_a_missing_file() -> None:
    checker = _checker()
    problems: list[str] = []
    checker._check_target(
        "owner.json",
        "/ref",
        "ai_docs/quality/m5-corpus-manifest.json",
        "0" * 64,
        problems,
    )
    checker._check_target(
        "owner.json", "/ref", "ai_docs/quality/not-there.json", "0" * 64, problems
    )
    # Paths outside the tracked directories (corpus-relative names) are not references.
    checker._check_target("owner.json", "/ref", "5983122166590934317.jpg", "0" * 64, problems)

    assert len(problems) == 2
    assert "pinned 000000000000" in problems[0]
    assert "does not exist" in problems[1]
