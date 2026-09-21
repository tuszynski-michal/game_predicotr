from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from game_predictor_worker.semi_automatic_selection import v7_configuration
from game_predictor_worker.semi_automatic_selection.contracts import SemiAutomaticSelectionDirection
from game_predictor_worker.semi_automatic_selection.v7_configuration import (
    V7BorderStyle,
    V7CorpusCase,
    V7CorpusManifest,
    V7CorpusSplit,
    V7SelectionConfigurationError,
    build_v7_selection_configuration,
    load_v7_corpus_manifest,
    parse_v7_full_range,
)


def test_single_number_normalizes_to_a_full_page_and_default_configuration() -> None:
    configuration = build_v7_selection_configuration(
        source_root=Path(r"C:\photos\1 - 19810"),
        first_range_input="1",
        last_range_input="19-27",
    )

    assert configuration.first_range.as_dict() == {"start": 1, "end": 9}
    assert [value.as_dict() for value in configuration.expected_ranges] == [
        {"start": 1, "end": 9},
        {"start": 10, "end": 18},
        {"start": 19, "end": 27},
    ]
    assert configuration.expected_group_count == 3
    assert configuration.output_root == Path(r"C:\photos\1 - 19810 cut")
    assert configuration.direction is SemiAutomaticSelectionDirection.ASCENDING
    assert configuration.border_style is V7BorderStyle.TOP_AND_SIDES


def test_descending_page_traversal_keeps_each_filename_range_ascending() -> None:
    configuration = build_v7_selection_configuration(
        source_root=Path(r"C:\photos\run"),
        first_range_input="19–27",
        last_range_input="1-9",
        direction=SemiAutomaticSelectionDirection.DESCENDING,
        border_style=V7BorderStyle.FULL_FRAME,
    )

    assert [value.as_dict() for value in configuration.expected_ranges] == [
        {"start": 19, "end": 27},
        {"start": 10, "end": 18},
        {"start": 1, "end": 9},
    ]
    assert configuration.expected_group_count == 3


@pytest.mark.parametrize("value", ["", "1-8", "1-10", "one", "0", "1-0", "18-10"])
def test_automatic_configuration_rejects_non_full_or_invalid_page(value: str) -> None:
    with pytest.raises(V7SelectionConfigurationError) as error:
        parse_v7_full_range(value)

    assert error.value.code in {"V7_RANGE_INPUT_INVALID", "V7_FULL_PAGE_REQUIRED"}


def test_configuration_rejects_ranges_that_conflict_with_direction() -> None:
    with pytest.raises(V7SelectionConfigurationError) as error:
        build_v7_selection_configuration(
            source_root=Path(r"C:\photos\run"),
            first_range_input="19-27",
            last_range_input="1-9",
        )

    assert error.value.code == "V7_RANGE_DIRECTION_INVALID"


def _make_case_directory(root: Path, name: str, content: bytes) -> None:
    directory = root / name
    directory.mkdir()
    (directory / "frame10.JPG").write_bytes(content)
    (directory / "frame2.jpeg").write_bytes(content + b"2")


def _complete_manifest(root: Path) -> V7CorpusManifest:
    return V7CorpusManifest(
        corpus_root=root,
        cases=(
            V7CorpusCase(
                "dev", "development", V7CorpusSplit.DEVELOPMENT, None, ("small_group",), None
            ),
            V7CorpusCase(
                "cal",
                "calibration",
                V7CorpusSplit.CALIBRATION,
                V7BorderStyle.TOP_AND_SIDES,
                ("left_crop",),
                None,
            ),
            V7CorpusCase(
                "val",
                "validation",
                V7CorpusSplit.VALIDATION,
                V7BorderStyle.FULL_FRAME,
                ("top_crop",),
                SemiAutomaticSelectionDirection.ASCENDING,
            ),
            V7CorpusCase(
                "hold",
                "holdout",
                V7CorpusSplit.HOLDOUT,
                V7BorderStyle.IRREGULAR_OR_NONE,
                ("treasure_border",),
                SemiAutomaticSelectionDirection.DESCENDING,
            ),
            V7CorpusCase(
                "reference",
                "reference",
                V7CorpusSplit.REFERENCE_ONLY,
                None,
                ("quality_reference",),
                None,
            ),
        ),
    )


def test_freeze_inventory_requires_exact_direct_directory_coverage_and_detects_content_change(
    tmp_path: Path,
) -> None:
    for name in ("development", "calibration", "validation", "holdout", "reference"):
        _make_case_directory(tmp_path, name, name.encode("ascii"))
    manifest = _complete_manifest(tmp_path)

    first = manifest.freeze_inventory()
    (tmp_path / "development" / "frame2.jpeg").write_bytes(b"changed")
    second = manifest.freeze_inventory()

    assert [item.jpeg_count for item in first] == [2, 2, 2, 2, 2]
    assert first[0].fingerprint != second[0].fingerprint
    (tmp_path / "unlisted").mkdir()
    with pytest.raises(V7SelectionConfigurationError, match="directories differ") as error:
        manifest.freeze_inventory()
    assert error.value.code == "V7_CORPUS_DIRECTORY_DRIFT"


@pytest.mark.parametrize("directory_name", [".", "..", "nested\\case", "C:\\outside"])
def test_corpus_case_rejects_paths_other_than_one_direct_child(directory_name: str) -> None:
    with pytest.raises(V7SelectionConfigurationError) as error:
        V7CorpusCase(
            "cal",
            directory_name,
            V7CorpusSplit.CALIBRATION,
            V7BorderStyle.TOP_AND_SIDES,
            ("left_crop",),
            None,
        )

    assert error.value.code == "V7_CORPUS_CASE_INVALID"


def test_resolve_case_sources_returns_only_validated_direct_jpegs(tmp_path: Path) -> None:
    for name in ("development", "calibration", "validation", "holdout", "reference"):
        _make_case_directory(tmp_path, name, name.encode("ascii"))
    manifest = _complete_manifest(tmp_path)

    sources = manifest.resolve_case_sources(("cal",))

    assert [source.case_id for source in sources] == ["cal", "cal"]
    assert all(source.path.parent == tmp_path / "calibration" for source in sources)
    assert all(len(source.source_checksum_sha256) == 64 for source in sources)


def test_freeze_inventory_rejects_an_empty_case_in_any_split(tmp_path: Path) -> None:
    for name in ("development", "calibration", "validation", "holdout", "reference"):
        (tmp_path / name).mkdir()
    for name in ("development", "calibration", "validation", "reference"):
        (tmp_path / name / "frame.jpg").write_bytes(b"jpeg")

    with pytest.raises(V7SelectionConfigurationError) as error:
        _complete_manifest(tmp_path).freeze_inventory()

    assert error.value.code == "V7_CORPUS_SPLIT_EMPTY"


def test_selected_mummies_cannot_be_reclassified_as_a_scored_group() -> None:
    with pytest.raises(V7SelectionConfigurationError) as error:
        V7CorpusCase(
            "mummies",
            "wybrane mumie",
            V7CorpusSplit.HOLDOUT,
            None,
            ("small_group",),
            None,
        )

    assert error.value.code == "V7_CORPUS_MUMMIES_ROLE_INVALID"


def test_windows_reparse_point_attribute_is_treated_like_a_link() -> None:
    reparse_stat = SimpleNamespace(st_file_attributes=0x0400)
    ordinary_stat = SimpleNamespace(st_file_attributes=0)

    assert v7_configuration._has_windows_reparse_attribute(reparse_stat)
    assert not v7_configuration._has_windows_reparse_attribute(ordinary_stat)


def test_corpus_root_rejects_a_junction_in_an_ancestor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unsafe_parent = tmp_path.absolute().parent
    original_check = v7_configuration._is_link_or_reparse
    monkeypatch.setattr(
        v7_configuration,
        "_is_link_or_reparse",
        lambda path: path == unsafe_parent or original_check(path),
    )

    with pytest.raises(V7SelectionConfigurationError) as error:
        v7_configuration._resolve_directory(tmp_path, "V7_CORPUS_ROOT_UNAVAILABLE")

    assert error.value.code == "V7_CORPUS_PATH_UNSAFE"


def test_direct_jpegs_use_a_stable_name_tiebreak_after_the_natural_number() -> None:
    files = (Path("frame2.jpg"), Path("frame02.jpg"), Path("frame10.jpg"))

    sorted_files = sorted(
        files,
        key=lambda item: (v7_configuration._natural_key(item.name), item.name),
    )
    assert sorted_files == [
        Path("frame02.jpg"),
        Path("frame2.jpg"),
        Path("frame10.jpg"),
    ]


def test_manifest_requires_disjoint_scored_splits_and_reference_semantics(tmp_path: Path) -> None:
    with pytest.raises(V7SelectionConfigurationError) as error:
        V7CorpusManifest(
            corpus_root=tmp_path,
            cases=(
                V7CorpusCase(
                    "dev",
                    "development",
                    V7CorpusSplit.DEVELOPMENT,
                    None,
                    ("small_group",),
                    None,
                ),
            ),
        )
    assert error.value.code == "V7_CORPUS_SPLITS_INCOMPLETE"

    with pytest.raises(V7SelectionConfigurationError) as reference_error:
        V7CorpusCase(
            "reference",
            "reference",
            V7CorpusSplit.REFERENCE_ONLY,
            None,
            ("small_group",),
            None,
        )
    assert reference_error.value.code == "V7_CORPUS_REFERENCE_INVALID"


def test_load_manifest_keeps_operator_root_out_of_production_configuration(tmp_path: Path) -> None:
    payload = {
        "schemaVersion": 1,
        "corpusRoot": str(tmp_path),
        "cases": [
            {
                "caseId": "dev",
                "directoryName": "development",
                "split": "development",
                "borderStyle": None,
                "expectedDirection": None,
                "scenarios": ["small_group"],
            },
            {
                "caseId": "cal",
                "directoryName": "calibration",
                "split": "calibration",
                "borderStyle": "top_and_sides",
                "expectedDirection": None,
                "scenarios": ["partial_occlusion"],
            },
            {
                "caseId": "val",
                "directoryName": "validation",
                "split": "validation",
                "borderStyle": "full_frame",
                "expectedDirection": "ascending",
                "scenarios": ["right_crop"],
            },
            {
                "caseId": "hold",
                "directoryName": "holdout",
                "split": "holdout",
                "borderStyle": "irregular_or_none",
                "expectedDirection": "descending",
                "scenarios": ["treasure_border"],
            },
            {
                "caseId": "reference",
                "directoryName": "reference",
                "split": "reference_only",
                "borderStyle": None,
                "expectedDirection": None,
                "scenarios": ["quality_reference"],
            },
        ],
    }
    manifest_path = tmp_path / "corpus.json"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    manifest = load_v7_corpus_manifest(manifest_path)

    assert manifest.cases[-1].split is V7CorpusSplit.REFERENCE_ONLY
    assert manifest.cases[-1].border_style is None
    assert manifest.schema_version == 1
    assert "geometryFamilyId" not in manifest.cases[0].as_dict(schema_version=1)

    payload["cases"][0]["geometryFamilyId"] = "standard_3x3_numeric_labels_v1"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(V7SelectionConfigurationError) as error:
        load_v7_corpus_manifest(manifest_path)
    assert error.value.code == "V7_CORPUS_MANIFEST_INVALID"


def test_manifest_v1_fingerprint_is_stable_and_rejects_v2_optional_geometry_fields(
    tmp_path: Path,
) -> None:
    cases = _complete_manifest(tmp_path).cases
    legacy = V7CorpusManifest(corpus_root=tmp_path, cases=cases, schema_version=1)
    with_v2_fields = V7CorpusManifest(
        corpus_root=tmp_path,
        cases=(
            *cases[:-1],
            V7CorpusCase(
                "reference",
                "reference",
                V7CorpusSplit.REFERENCE_ONLY,
                None,
                ("quality_reference",),
                None,
                geometry_family_id="standard_3x3_numeric_labels_v1",
                source_game_ref="reference-game",
            ),
        ),
        schema_version=2,
    )

    assert (
        legacy.fingerprint()
        == V7CorpusManifest(
            corpus_root=tmp_path,
            cases=cases,
            schema_version=1,
        ).fingerprint()
    )
    with pytest.raises(V7SelectionConfigurationError) as error:
        V7CorpusManifest(
            corpus_root=tmp_path,
            cases=with_v2_fields.cases,
            schema_version=1,
        )
    assert error.value.code == "V7_CORPUS_MANIFEST_INVALID"
    assert legacy.fingerprint() != with_v2_fields.fingerprint()
