from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "build_m5_projective_fixed_padding_regression.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "build_m5_projective_fixed_padding_regression_test",
        SCRIPT,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = _load_script()
RegressionGateError = cast(type[ValueError], MODULE.RegressionGateError)


def test_full_preflight_paths_use_separate_immutable_namespace() -> None:
    phase_paths = cast(
        Callable[
            [str, str, Path | None, Path | None],
            tuple[Path, Path],
        ],
        MODULE._phase_paths,
    )

    output, report = phase_paths("full", "v14-bbox", None, None)

    assert output.name == "m5-global-bbox-fallback-v14-full-preflight"
    assert report.name == "m5-global-bbox-fallback-v14-full-preflight-report.json"


def test_full_artifacts_are_reused_but_never_overwritten(tmp_path: Path) -> None:
    write = cast(
        Callable[[Path, bytes], None],
        lambda path, content: MODULE._write_immutable_or_check(
            path,
            content,
            check=False,
        ),
    )
    target = tmp_path / "artifact.png"

    write(target, b"first")
    write(target, b"first")

    assert target.read_bytes() == b"first"
    with pytest.raises(RegressionGateError, match="Immutable artifact collision"):
        write(target, b"second")


def test_full_gallery_groups_cards_by_source_image() -> None:
    html_page = cast(
        Callable[[Sequence[Mapping[str, object]]], bytes],
        lambda entries: MODULE._html_page(entries, phase="full"),
    )
    entries = (
        {
            "cardRelativePath": "cards/seq-001.png",
            "primaryFallbackReason": None,
            "sequenceNumber": 1,
            "sourceImageId": "m5-img-001",
            "status": "cropped",
        },
        {
            "cardRelativePath": "cards/seq-002.png",
            "primaryFallbackReason": "GLOBAL_SYMBOL_LATTICE_AXIS_ASSIGNMENT_FAILED",
            "sequenceNumber": 2,
            "sourceImageId": "m5-img-001",
            "status": "cropped",
        },
        {
            "cardRelativePath": "cards/seq-010.png",
            "primaryFallbackReason": None,
            "sequenceNumber": 10,
            "sourceImageId": "m5-img-002",
            "status": "fallback",
        },
    )

    content = html_page(entries).decode()

    assert content.count("<section>") == 2
    assert "m5-img-001" in content
    assert "m5-img-002" in content
    assert "cards/seq-010.png" in content
