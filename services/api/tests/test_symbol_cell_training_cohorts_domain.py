from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from game_predictor_api.domain.image_reviews import ImageReviewConflictError
from game_predictor_api.domain.symbol_cell_training_cohorts import (
    ApprovedSymbolCellCandidate,
    SymbolCellSelectionConfig,
    build_symbol_cell_training_manifest,
    select_symbol_cell_training_samples,
)


def _candidate(
    index: int,
    *,
    symbol_code: str = "cherry",
    source_image_id: UUID | None = None,
    checksum: str | None = None,
    predicted: str | None = "cherry",
    perceptual_hash: int | None = None,
    mean_rgb: tuple[int, int, int] = (100, 110, 120),
) -> ApprovedSymbolCellCandidate:
    return ApprovedSymbolCellCandidate(
        cell_review_id=UUID(int=index + 1),
        review_item_id=uuid4(),
        recognized_board_id=uuid4(),
        source_image_id=source_image_id or UUID(int=10_000 + index),
        import_job_id=uuid4(),
        assigned_symbol_id=uuid4(),
        symbol_code=symbol_code,
        sequence_number=index // 15 + 1,
        cell_index=index % 15,
        cell_revision=1,
        geometry_revision=0,
        crop_sample_id=f"crop-{index}",
        crop_relative_path=f"crops/{index}.jpg",
        crop_checksum_sha256=checksum or f"{index + 1:064x}",
        source_checksum_sha256=f"{index + 10_000:064x}",
        source_relative_path=f"originals/{index}.jpg",
        cropper_version="cropper-v1",
        prediction_symbol_code=predicted,
        perceptual_hash_64=index if perceptual_hash is None else perceptual_hash,
        mean_rgb=mean_rgb,
    )


def test_selection_prioritizes_corrections_and_is_bounded() -> None:
    candidates = [
        *(_candidate(index, predicted="plum") for index in range(7)),
        *(_candidate(index + 100) for index in range(20)),
    ]

    selection = select_symbol_cell_training_samples(
        candidates=candidates,
        active_symbol_codes=("cherry",),
        config=SymbolCellSelectionConfig(
            target_samples_per_symbol=10,
            max_samples_per_symbol=12,
            near_duplicate_hamming_distance=0,
            near_duplicate_color_distance=0,
        ),
    )

    assert len(selection.samples) == 10
    assert [sample.selection_reason for sample in selection.samples[:7]] == ["human_correction"] * 7
    assert selection.coverage[0].selected_correction_count == 7


def test_corrections_may_extend_target_but_never_exceed_hard_maximum() -> None:
    selection = select_symbol_cell_training_samples(
        candidates=[_candidate(index, predicted="plum") for index in range(30)],
        active_symbol_codes=("cherry",),
        config=SymbolCellSelectionConfig(
            target_samples_per_symbol=10,
            max_samples_per_symbol=12,
            near_duplicate_hamming_distance=0,
            near_duplicate_color_distance=0,
        ),
    )

    assert len(selection.samples) == 12
    assert selection.coverage[0].selected_correction_count == 12


def test_exact_and_near_duplicates_are_excluded() -> None:
    candidates = [
        _candidate(0, checksum="a" * 64, perceptual_hash=0),
        _candidate(1, checksum="a" * 64, perceptual_hash=2**32),
        _candidate(2, checksum="b" * 64, perceptual_hash=1, mean_rgb=(101, 110, 120)),
        _candidate(3, checksum="c" * 64, perceptual_hash=0xFFFF0000FFFF0000),
    ]

    selection = select_symbol_cell_training_samples(
        candidates=candidates,
        active_symbol_codes=("cherry",),
        config=SymbolCellSelectionConfig(
            target_samples_per_symbol=10,
            max_samples_per_symbol=10,
        ),
    )

    assert len(selection.samples) == 2
    assert selection.coverage[0].exact_duplicate_count == 1
    assert selection.coverage[0].near_duplicate_count == 1


def test_round_robin_selection_represents_sources_before_reusing_them() -> None:
    source_a = uuid4()
    source_b = uuid4()
    candidates = [
        _candidate(index, source_image_id=source_a, perceptual_hash=index << 16)
        for index in range(5)
    ] + [_candidate(100, source_image_id=source_b, perceptual_hash=0xFFFF0000FFFF0000)]

    selection = select_symbol_cell_training_samples(
        candidates=candidates,
        active_symbol_codes=("cherry",),
        config=SymbolCellSelectionConfig(
            target_samples_per_symbol=2,
            max_samples_per_symbol=2,
            near_duplicate_hamming_distance=0,
            near_duplicate_color_distance=0,
        ),
    )

    assert {sample.candidate.source_image_id for sample in selection.samples} == {
        source_a,
        source_b,
    }


def test_selection_rejects_inactive_symbol_and_invalid_checksum() -> None:
    with pytest.raises(ImageReviewConflictError) as inactive:
        select_symbol_cell_training_samples(
            candidates=[_candidate(0, symbol_code="plum")],
            active_symbol_codes=("cherry",),
        )
    assert inactive.value.code == "SYMBOL_CELL_TRAINING_SYMBOL_INACTIVE"

    with pytest.raises(ImageReviewConflictError) as checksum:
        select_symbol_cell_training_samples(
            candidates=[_candidate(0, checksum="broken")],
            active_symbol_codes=("cherry",),
        )
    assert checksum.value.code == "SYMBOL_CELL_TRAINING_CHECKSUM_INVALID"


def test_candidate_traversal_performs_a_bounded_number_of_similarity_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from game_predictor_api.domain import symbol_cell_training_cohorts as module

    comparisons = 0
    original = module._is_near_duplicate

    def counted(*args: object, **kwargs: object) -> bool:
        nonlocal comparisons
        comparisons += 1
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(module, "_is_near_duplicate", counted)
    candidate_count = 2_000
    select_symbol_cell_training_samples(
        candidates=[
            _candidate(
                index,
                perceptual_hash=(index * 0x9E3779B97F4A7C15) & ((1 << 64) - 1),
                mean_rgb=(index % 256, (index * 3) % 256, (index * 7) % 256),
            )
            for index in range(candidate_count)
        ],
        active_symbol_codes=("cherry",),
        config=SymbolCellSelectionConfig(
            target_samples_per_symbol=candidate_count,
            max_samples_per_symbol=candidate_count,
            max_similarity_comparisons_per_band=8,
        ),
    )

    assert comparisons <= candidate_count * 4 * 8


def test_manifest_contains_individual_cells_without_requiring_a_complete_board() -> None:
    game_id = uuid4()
    selection = select_symbol_cell_training_samples(
        candidates=[_candidate(0), _candidate(1, symbol_code="plum", predicted="cherry")],
        active_symbol_codes=("cherry", "plum"),
    )

    manifest, content, checksum = build_symbol_cell_training_manifest(
        game_id=game_id, selection=selection
    )

    assert manifest["schemaVersion"] == 2
    assert manifest["datasetKind"] == "verified-symbol-cell-training-cohort-v2"
    assert len(manifest["cells"]) == 2
    assert "boards" not in manifest
    assert len(content) > 0
    assert len(checksum) == 64
