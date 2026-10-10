from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location(
    "verify_artifact_references_test_module",
    REPOSITORY_ROOT / "scripts" / "verify_artifact_references.py",
)
assert _SPEC is not None and _SPEC.loader is not None
script: Any = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = script
_SPEC.loader.exec_module(script)

LEGACY = r"C:\Users\tuszy\Documents\game_predicotr"


def _mapping(table: str, column: str, **kwargs: Any) -> Any:
    return next(
        mapping for mapping in script.COLUMN_MAPPINGS if mapping.key == (*table.split("."), column)
    )


def test_data_prefixed_paths_resolve_under_the_artifact_root(tmp_path: Path) -> None:
    resolved = script.resolve_reference("data/symbol-references/a.png", script.ROOT_DATA, tmp_path)

    assert resolved == tmp_path / "data" / "symbol-references" / "a.png"


def test_managed_paths_resolve_under_the_data_root(tmp_path: Path) -> None:
    resolved = script.resolve_reference("originals/ab/abc.jpg", script.ROOT_DATA, tmp_path)

    assert resolved == tmp_path / "data" / "originals" / "ab" / "abc.jpg"


def test_artifact_root_columns_do_not_add_the_data_directory(tmp_path: Path) -> None:
    resolved = script.resolve_reference(
        "models/lab-symbol-candidates/x/origin.json", script.ROOT_ARTIFACT, tmp_path
    )

    assert resolved == tmp_path / "models" / "lab-symbol-candidates" / "x" / "origin.json"


def test_lab_candidate_paths_resolve_under_the_artifact_root_in_every_column(
    tmp_path: Path,
) -> None:
    resolved = script.resolve_reference(
        "models/lab-symbol-candidates/x/manifest.json", script.ROOT_DATA, tmp_path
    )
    managed = script.resolve_reference("models/7/run/checkpoints/a.pt", script.ROOT_DATA, tmp_path)

    assert resolved == tmp_path / "models" / "lab-symbol-candidates" / "x" / "manifest.json"
    assert managed == tmp_path / "data" / "models" / "7" / "run" / "checkpoints" / "a.pt"


@pytest.mark.parametrize(
    "value",
    ["", "   ", "/abs/file.jpg", r"C:\abs\file.jpg", "C:/abs/file.jpg", "originals/../../x.jpg"],
)
def test_absolute_empty_and_escaping_paths_are_invalid(tmp_path: Path, value: str) -> None:
    assert script.resolve_reference(value, script.ROOT_DATA, tmp_path) is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (LEGACY, True),
        (LEGACY + r"\imports\a", True),
        ("c:/users/TUSZY/documents/game_predicotr/imports/a", True),
        (LEGACY + "_old\\imports", False),
        (r"D:\game_predicotr\imports\a", False),
    ],
)
def test_prefix_match_is_case_and_separator_insensitive(value: str, expected: bool) -> None:
    assert script.is_under_prefix(value, LEGACY) is expected


def test_manifest_scan_finds_prefixed_strings_in_keys_values_and_lists() -> None:
    document = {
        "files": [{"path": LEGACY + r"\imports\a.jpg"}, {"path": "originals/a.jpg"}],
        LEGACY + r"\key": 1,
        "nested": {"other": r"D:\game_predicotr\x"},
    }

    hits = script.find_prefixed_strings(document, LEGACY)

    assert sorted(hits) == sorted([LEGACY + r"\imports\a.jpg", LEGACY + r"\key"])


def test_check_column_counts_existing_missing_invalid_and_manifest_entries(tmp_path: Path) -> None:
    manifest = tmp_path / "data" / "board-cell-processing-manifests" / "m.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"source": LEGACY + r"\imports\x.jpg"}), encoding="utf-8")
    mapping = _mapping(
        "game_data_v2.image_board_geometry_pending", "processing_manifest_relative_path"
    )

    report = script.check_column(
        mapping,
        ["data/board-cell-processing-manifests/m.json", "data/missing.json", r"C:\x.json"],
        tmp_path,
        LEGACY,
    )

    assert (report.distinct_paths, report.existing, report.missing, report.invalid) == (3, 1, 1, 1)
    assert report.missing_samples == ["data/missing.json"]
    assert (report.manifests_read, report.manifest_legacy_entries) == (1, 1)


def test_check_column_reports_files_resolved_under_the_legacy_prefix(tmp_path: Path) -> None:
    (tmp_path / "data" / "originals").mkdir(parents=True)
    (tmp_path / "data" / "originals" / "a.jpg").write_bytes(b"x")
    mapping = _mapping("game_data_v2.source_images", "relative_path")

    report = script.check_column(mapping, ["originals/a.jpg"], tmp_path, str(tmp_path))

    assert (report.existing, report.legacy_resolved) == (1, 1)


def test_directories_count_legacy_prefix_and_repository_equivalent(tmp_path: Path) -> None:
    (tmp_path / "imports" / "job-a").mkdir(parents=True)
    rows = [
        ("1", "waiting_for_review", LEGACY + r"\imports\job-a"),
        ("2", "completed", LEGACY + r"\imports\job-b"),
        ("3", "completed", str(tmp_path / "imports" / "job-a")),
    ]

    report = script.check_directories("jobs", rows, LEGACY, tmp_path)

    assert report.rows == 3
    assert report.legacy_prefixed == 2
    assert report.legacy_equivalent_existing == 1
    assert report.by_status["completed"] == {"rows": 2, "legacy_prefixed": 1}


def test_unknown_columns_are_unmapped_and_known_exclusions_are_listed() -> None:
    discovery = script.classify_columns(
        [
            ("game_data_v2", "source_images", "relative_path"),
            ("public", "paylines", "row_path"),
            ("public", "new_table", "export_relative_path"),
        ]
    )

    assert [mapping.name for mapping in discovery.mapped] == [
        "game_data_v2.source_images.relative_path"
    ]
    assert discovery.excluded == [("public", "paylines", "row_path")]
    assert discovery.unmapped == [("public", "new_table", "export_relative_path")]
    assert len(discovery.absent) == len(script.COLUMN_MAPPINGS) - 1


def _report(**legacy: int) -> dict[str, Any]:
    values = {
        "resolved_files": 0,
        "manifest_entries": 0,
        "job_source_directories": 0,
        "remote_sessions": 0,
    }
    values.update(legacy)
    return {
        "columns": [{"missing": 0, "invalid": 0, "manifests_unreadable": 0}],
        "unmapped_columns": [{"column": "public.t.empty_path", "rows_non_null": 0}],
        "legacy": values,
    }


def test_gate_passes_without_forbid_prefix_even_with_legacy_dependencies() -> None:
    assert script.evaluate(_report(job_source_directories=181, manifest_entries=3), None) == []


def test_forbid_prefix_turns_every_legacy_count_into_an_error() -> None:
    errors = script.evaluate(_report(job_source_directories=181, manifest_entries=3), LEGACY)

    assert errors == [
        "FORBIDDEN_PREFIX_MANIFEST_ENTRIES 3",
        "FORBIDDEN_PREFIX_JOB_SOURCE_DIRECTORIES 181",
    ]


def test_missing_files_and_unmapped_columns_with_data_always_fail() -> None:
    report = _report()
    report["columns"][0]["missing"] = 1
    report["unmapped_columns"][0]["rows_non_null"] = 5

    assert script.evaluate(report, None) == [
        "MISSING_FILES 1",
        "UNMAPPED_COLUMNS_WITH_DATA public.t.empty_path",
    ]
