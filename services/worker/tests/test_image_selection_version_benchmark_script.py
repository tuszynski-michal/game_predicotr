import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

from game_predictor_worker.images.selection.sequence_bounds import SequenceBounds


def _benchmark_module() -> ModuleType:
    script = Path(__file__).parents[3] / "scripts" / "benchmark_image_selection_versions.py"
    spec = spec_from_file_location("benchmark_image_selection_versions", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load the image-selection version benchmark.")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_raw_jpeg_loader_supports_natural_and_reverse_read_only_order(
    tmp_path: Path,
) -> None:
    benchmark = _benchmark_module()
    (tmp_path / "photo10.jpg").write_bytes(b"ten")
    (tmp_path / "photo2.jpg").write_bytes(b"two")

    natural, natural_sha256, source_kind = benchmark._load_sources(
        tmp_path,
        source_order="natural",
    )
    reverse, reverse_sha256, reverse_kind = benchmark._load_sources(
        tmp_path,
        source_order="reverse",
    )

    assert [source.relative_path for source in natural] == ["photo2.jpg", "photo10.jpg"]
    assert [source.relative_path for source in reverse] == ["photo10.jpg", "photo2.jpg"]
    assert [source.order_index for source in reverse] == [0, 1]
    assert source_kind == reverse_kind == "raw_jpeg_directory"
    assert natural_sha256 != reverse_sha256


def test_raw_jpeg_loader_applies_profile_limit_before_hashing_sources(
    tmp_path: Path,
) -> None:
    benchmark = _benchmark_module()
    (tmp_path / "photo1.jpg").write_bytes(b"one")
    (tmp_path / "photo2.jpg").write_bytes(b"two")

    sources, _, source_kind = benchmark._load_sources(
        tmp_path,
        source_order="natural",
        limit=1,
    )

    assert [source.relative_path for source in sources] == ["photo1.jpg"]
    assert source_kind == "raw_jpeg_directory"


def test_v1020_low_quality_annotations_cover_every_descending_range() -> None:
    path = (
        Path(__file__).parents[3]
        / "ai_docs"
        / "quality"
        / "image-selection-v1020-low-quality-descending-annotations.json"
    )
    contract = json.loads(path.read_text(encoding="utf-8"))
    cases = contract["cases"]
    sequence = contract["expectedSequence"]
    bounds = SequenceBounds(
        sequence["first"],
        sequence["last"],
        sequence["direction"],
        sequence["groupSize"],
    )

    assert contract["contract"] == "image-selection-real-corpus-annotations-v2"
    assert contract["corpus"]["imageCount"] == 283
    assert sequence["groupCount"] == bounds.expected_group_count == 17
    assert len(cases) == 20
    assert len({case["relativePath"] for case in cases}) == len(cases)
    assert all(len(case["checksumSha256"]) == 64 for case in cases)
    assert all(case["readability"] in {"clear", "borderline", "unreadable"} for case in cases)
    clear_ranges = {
        (case["expectedRange"]["start"], case["expectedRange"]["end"])
        for case in cases
        if case["automaticCandidateEligible"]
    }
    expected_ranges = {
        (value.start, value.end)
        for value in (bounds.range_for_group(index) for index in range(bounds.expected_group_count))
    }
    assert clear_ranges == expected_ranges
    assert all(
        case["readability"] == "unreadable"
        and not case["rangeLegible"]
        and not case["layoutLegible"]
        for case in cases
        if not case["automaticCandidateEligible"]
    )
