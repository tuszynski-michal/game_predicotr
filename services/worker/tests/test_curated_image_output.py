from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path
from uuid import UUID

import pytest
from game_predictor_worker.images.selection.contracts import (
    CandidateDecision,
    CandidateResult,
    ImageQualityMetrics,
    ImageSelectionResult,
    ImageSelectionSource,
    SelectionContractError,
    SelectionGroupResult,
    SelectionGroupStatus,
    SelectorCheckpoint,
    SequenceRange,
)
from game_predictor_worker.images.selection.output import (
    LEGACY_OUTPUT_MANIFEST_CONTRACT,
    LEGACY_OUTPUT_MANIFEST_SCHEMA_VERSION,
    CuratedImageOutputPublisher,
    verify_curated_image_manifest,
)
from PIL import Image

RUN_ID = UUID("00000000-0000-0000-0000-000000000154")


def _jpeg(path: Path, color: tuple[int, int, int]) -> bytes:
    Image.new("RGB", (48, 32), color).save(path, format="JPEG", quality=90)
    return path.read_bytes()


def _quality(score: float = 0.9) -> ImageQualityMetrics:
    return ImageQualityMetrics(score, score, score, score, score, score, score, score)


def _result(
    source: ImageSelectionSource,
    *,
    unresolved: bool = False,
    range_free: bool = False,
) -> ImageSelectionResult:
    candidate = CandidateResult(
        source=source,
        decision=CandidateDecision.SELECTED_AUTOMATIC,
        quality=_quality(),
        recognized_range=None if range_free else SequenceRange(1, 9, 0.98),
        reason_codes=("RANGE_UNKNOWN",) if range_free else (),
    )
    group = SelectionGroupResult(
        group_order=0,
        source_count=1,
        range=None if unresolved or range_free else SequenceRange(1, 9, 0.98),
        fingerprint_sha256="f" * 64,
        board_count_consensus=9,
        status=(
            SelectionGroupStatus.MANUAL_REQUIRED
            if unresolved
            else SelectionGroupStatus.AUTO_SELECTED
        ),
        selected_candidate=None if unresolved else candidate,
        top_candidates=(candidate,),
    )
    return ImageSelectionResult(
        selector_version="fast-image-selector-v1",
        selector_fingerprint="a" * 64,
        input_count=1,
        groups=(group,),
        checkpoint=SelectorCheckpoint(1, "a" * 64, 1, 1, 1),
        scan_failure_count=0,
        verification_count=1,
    )


def test_publisher_copies_one_verified_jpeg_without_mutating_source(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    source_path = source_root / "00000001.jpg"
    original = _jpeg(source_path, (240, 160, 20))
    checksum = hashlib.sha256(original).hexdigest()
    source = ImageSelectionSource(0, "photos/one.jpg", source_path.name, checksum, len(original))
    source_snapshot = {path.name: path.read_bytes() for path in source_root.iterdir()}

    published = CuratedImageOutputPublisher(tmp_path / "artifacts").publish(
        run_id=RUN_ID,
        source_root=source_root,
        input_manifest_sha256="b" * 64,
        result=_result(source),
    )

    assert {path.name: path.read_bytes() for path in source_root.iterdir()} == source_snapshot
    assert len(published.manifest.entries) == 1
    entry = published.manifest.entries[0]
    assert entry.output_relative_path == "images/seq_1-9.jpg"
    assert entry.group_order == 0
    assert entry.output_checksum_sha256 == checksum
    assert published.manifest_relative_path == (
        f"data/exports/image-selections/{published.manifest_sha256}/manifest.json"
    )
    assert (
        verify_curated_image_manifest(
            published.output_directory,
            expected_manifest_sha256=published.manifest_sha256,
            expected_run_id=RUN_ID,
        )
        == published.manifest
    )


def test_publisher_emits_range_free_v2_entry_with_stable_group_name(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    source_path = source_root / "photo.jpg"
    content = _jpeg(source_path, (40, 120, 220))
    checksum = hashlib.sha256(content).hexdigest()
    source = ImageSelectionSource(0, "photos/original.jpg", "photo.jpg", checksum, len(content))

    published = CuratedImageOutputPublisher(tmp_path / "artifacts").publish(
        run_id=RUN_ID,
        source_root=source_root,
        input_manifest_sha256="b" * 64,
        result=_result(source, range_free=True),
    )

    entry = published.manifest.entries[0]
    assert entry.group_order == 0
    assert entry.range_start is None
    assert entry.range_end is None
    assert entry.source_relative_path == "photos/original.jpg"
    assert entry.output_relative_path == "images/selection_0.jpg"
    assert entry.output_checksum_sha256 == checksum
    assert entry.reason_codes == ("RANGE_UNKNOWN",)
    assert entry.selection_method == "automatic"


def test_verifier_keeps_historical_v1_manifest_readable(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    source_path = source_root / "photo.jpg"
    content = _jpeg(source_path, (120, 220, 40))
    source = ImageSelectionSource(
        0,
        "photo.jpg",
        "photo.jpg",
        hashlib.sha256(content).hexdigest(),
        len(content),
    )
    published = CuratedImageOutputPublisher(tmp_path / "artifacts").publish(
        run_id=RUN_ID,
        source_root=source_root,
        input_manifest_sha256="b" * 64,
        result=_result(source),
    )
    legacy = replace(
        published.manifest,
        schema_version=LEGACY_OUTPUT_MANIFEST_SCHEMA_VERSION,
        contract=LEGACY_OUTPUT_MANIFEST_CONTRACT,
    )
    manifest_path = published.output_directory / "manifest.json"
    manifest_path.write_bytes(legacy.canonical_bytes)

    verified = verify_curated_image_manifest(
        published.output_directory,
        expected_manifest_sha256=legacy.checksum_sha256,
        expected_run_id=RUN_ID,
    )

    assert verified.schema_version == 1
    assert verified.entries[0].output_relative_path == "images/seq_1-9.jpg"


def test_publisher_is_idempotent_for_same_run_and_content(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    source_path = source_root / "photo.jpg"
    content = _jpeg(source_path, (20, 160, 240))
    checksum = hashlib.sha256(content).hexdigest()
    source = ImageSelectionSource(0, "photo.jpg", "photo.jpg", checksum, len(content))
    publisher = CuratedImageOutputPublisher(tmp_path / "artifacts")

    first = publisher.publish(
        run_id=RUN_ID,
        source_root=source_root,
        input_manifest_sha256="b" * 64,
        result=_result(source),
    )
    repeated = publisher.publish(
        run_id=RUN_ID,
        source_root=source_root,
        input_manifest_sha256="b" * 64,
        result=_result(source),
    )

    assert repeated.manifest_sha256 == first.manifest_sha256
    assert repeated.output_directory == first.output_directory


def test_failure_before_commit_does_not_publish_partial_output(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    source_path = source_root / "photo.jpg"
    content = _jpeg(source_path, (80, 80, 80))
    checksum = hashlib.sha256(content).hexdigest()
    source = ImageSelectionSource(0, "photo.jpg", "photo.jpg", checksum, len(content))

    def fail(_pending: Path) -> None:
        raise RuntimeError("injected before commit")

    with pytest.raises(RuntimeError, match="injected"):
        CuratedImageOutputPublisher(tmp_path / "artifacts", before_commit=fail).publish(
            run_id=RUN_ID,
            source_root=source_root,
            input_manifest_sha256="b" * 64,
            result=_result(source),
        )

    export_root = tmp_path / "artifacts" / "data" / "exports" / "image-selections"
    assert not any(path.name == "manifest.json" for path in export_root.rglob("manifest.json"))


def test_publisher_blocks_unresolved_group_and_checksum_drift(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    source_path = source_root / "photo.jpg"
    content = _jpeg(source_path, (160, 20, 80))
    source = ImageSelectionSource(
        0,
        "photo.jpg",
        "photo.jpg",
        hashlib.sha256(content).hexdigest(),
        len(content),
    )
    publisher = CuratedImageOutputPublisher(tmp_path / "artifacts")

    with pytest.raises(SelectionContractError) as unresolved:
        publisher.publish(
            run_id=RUN_ID,
            source_root=source_root,
            input_manifest_sha256="b" * 64,
            result=_result(source, unresolved=True),
        )
    source_path.write_bytes(content + b"changed")
    with pytest.raises(SelectionContractError) as changed:
        publisher.publish(
            run_id=RUN_ID,
            source_root=source_root,
            input_manifest_sha256="b" * 64,
            result=_result(source),
        )

    assert unresolved.value.code == "IMAGE_SELECTION_NOT_READY"
    assert changed.value.code == "IMAGE_SELECTION_MANIFEST_MISMATCH"


def test_publisher_allows_a_resolved_range_without_a_jpeg(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    result = ImageSelectionResult(
        selector_version="fast-image-selector-v1",
        selector_fingerprint="a" * 64,
        input_count=1,
        groups=(
            SelectionGroupResult(
                group_order=0,
                source_count=1,
                range=SequenceRange(1, 9, 1.0),
                fingerprint_sha256="f" * 64,
                board_count_consensus=9,
                status=SelectionGroupStatus.MISSING_IMAGE,
                selected_candidate=None,
                top_candidates=(),
            ),
        ),
        checkpoint=SelectorCheckpoint(1, "a" * 64, 1, 1, 1),
        scan_failure_count=0,
        verification_count=1,
    )

    published = CuratedImageOutputPublisher(tmp_path / "artifacts").publish(
        run_id=RUN_ID,
        source_root=source_root,
        input_manifest_sha256="b" * 64,
        result=result,
    )

    assert published.manifest.entries == ()
    assert (
        verify_curated_image_manifest(
            published.output_directory,
            expected_manifest_sha256=published.manifest_sha256,
            expected_run_id=RUN_ID,
        )
        == published.manifest
    )
