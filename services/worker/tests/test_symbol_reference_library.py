from __future__ import annotations

import numpy as np
import pytest
from game_predictor_worker.symbols.reference_library import (
    NEIGHBOUR_COUNT,
    ReferenceLibraryError,
    Vote,
    combined_descriptor,
    decide,
    descriptor_matrix,
    gray_world,
    hue_descriptor,
    normalize_rows,
    shape_descriptor,
    vote,
    vote_batch,
)


def _crop(kind: str, colour: tuple[int, int, int] = (200, 40, 40)) -> np.ndarray:
    crop = np.full((64, 64, 3), 20, dtype=np.uint8)
    if kind == "disc":
        rows, columns = np.ogrid[:64, :64]
        crop[(rows - 32) ** 2 + (columns - 32) ** 2 < 22**2] = colour
    elif kind == "bar":
        crop[28:36, 6:58] = colour
    else:
        crop[6:58, 28:36] = colour
    return crop


def _library() -> tuple[np.ndarray, np.ndarray]:
    references = normalize_rows(
        np.array([[1.0, 0.0]] * NEIGHBOUR_COUNT + [[0.0, 1.0]] * NEIGHBOUR_COUNT, dtype=np.float32)
    )
    labels = np.array([0] * NEIGHBOUR_COUNT + [1] * NEIGHBOUR_COUNT, dtype=np.int64)
    return references, labels


def test_unanimous_votes_in_both_descriptors_give_a_proposal() -> None:
    references, labels = _library()
    result = vote(np.array([1.0, 0.0], dtype=np.float32), references, labels, class_count=2)

    proposal = decide(result, result)

    assert result.unanimous
    assert proposal.class_index == 0
    assert proposal.reason == "unanimous"


def test_six_of_seven_votes_require_manual_review() -> None:
    references = normalize_rows(np.array([[1.0, 0.0]] * NEIGHBOUR_COUNT, dtype=np.float32))
    labels = np.array([0, 0, 0, 0, 0, 0, 1], dtype=np.int64)

    result = vote(np.array([1.0, 0.0], dtype=np.float32), references, labels, class_count=2)
    proposal = decide(result, result)

    assert result.agreeing_count == 6
    assert proposal.class_index is None
    assert proposal.reason == "not_unanimous"


def test_disagreeing_descriptors_require_manual_review() -> None:
    first = Vote(0, NEIGHBOUR_COUNT, NEIGHBOUR_COUNT, 0.9)
    second = Vote(1, NEIGHBOUR_COUNT, NEIGHBOUR_COUNT, 0.9)

    proposal = decide(first, second)

    assert proposal.class_index is None
    assert proposal.reason == "descriptors_disagree"


def test_too_few_references_after_exclusion_require_manual_review() -> None:
    references, labels = _library()
    excluded = np.ones(labels.shape, dtype=np.bool_)
    excluded[:3] = False

    result = vote(
        np.array([1.0, 0.0], dtype=np.float32),
        references,
        labels,
        class_count=2,
        excluded=excluded,
    )

    assert result.class_index is None
    assert result.neighbour_count == 3
    assert decide(result, result).reason == "insufficient_references"


def test_excluded_references_never_vote() -> None:
    references, labels = _library()
    excluded = labels == 0

    result = vote(
        np.array([1.0, 0.0], dtype=np.float32),
        references,
        labels,
        class_count=2,
        excluded=excluded,
    )

    assert result.class_index == 1


def test_vote_is_deterministic_for_equal_similarities() -> None:
    references = normalize_rows(np.array([[1.0, 0.0]] * 9, dtype=np.float32))
    labels = np.array([1, 1, 1, 1, 1, 1, 1, 0, 0], dtype=np.int64)
    query = np.array([1.0, 0.0], dtype=np.float32)

    first = vote(query, references, labels, class_count=2)
    second = vote(query, references, labels, class_count=2)

    assert first == second
    assert first.class_index == 1
    assert first.agreeing_count == NEIGHBOUR_COUNT


def test_shape_descriptor_ignores_hue_at_equal_luma() -> None:
    # Pure red and the gray value OpenCV maps it to share luma, not hue.
    red = _crop("disc", (200, 0, 0))
    luma = int(round(0.299 * 200))
    gray = _crop("disc", (luma, luma, luma))

    assert np.allclose(shape_descriptor(red), shape_descriptor(gray), atol=0.02)
    assert not np.allclose(hue_descriptor(red), hue_descriptor(gray), atol=0.02)


def test_shape_descriptor_separates_shapes() -> None:
    disc = shape_descriptor(_crop("disc"))
    horizontal = shape_descriptor(_crop("bar"))
    vertical = shape_descriptor(_crop("column"))

    assert float(horizontal @ vertical) < float(horizontal @ horizontal) - 0.2
    assert float(disc @ horizontal) < float(disc @ disc) - 0.2


def test_gray_world_equalizes_channel_means() -> None:
    tinted = np.clip(
        _crop("disc", (220, 220, 220)).astype(np.float32) * np.array([1.0, 0.8, 0.5]), 0, 255
    ).astype(np.uint8)

    balanced = gray_world(tinted)
    means = balanced.reshape(-1, 3).mean(axis=0)

    assert float(means.max() - means.min()) < 2.0


def test_descriptor_matrix_and_combined_descriptor_shapes() -> None:
    crops = [_crop("disc"), _crop("bar")]
    shape, hue = descriptor_matrix(crops)
    feature_map = np.ones((2, 16), dtype=np.float32)

    combined = combined_descriptor(shape, feature_map, hue)

    assert shape.shape == (2, 272)
    assert hue.shape == (2, 12)
    assert combined.shape == (2, 272 + 16 + 12)


@pytest.mark.parametrize(
    "crop",
    [
        np.zeros((32, 32, 3), dtype=np.uint8),
        np.zeros((64, 64), dtype=np.uint8),
        np.zeros((64, 64, 3), dtype=np.float32),
    ],
)
def test_invalid_crop_is_an_error(crop: np.ndarray) -> None:
    with pytest.raises(ReferenceLibraryError) as error:
        shape_descriptor(crop)

    assert error.value.code == "SYMBOL_REFERENCE_CROP_INVALID"


def test_invalid_vote_inputs_are_errors() -> None:
    references, labels = _library()
    query = np.array([1.0, 0.0], dtype=np.float32)

    with pytest.raises(ReferenceLibraryError):
        vote(query, references, labels[:-1], class_count=2)
    with pytest.raises(ReferenceLibraryError):
        vote(query, references, labels, class_count=1)
    with pytest.raises(ReferenceLibraryError):
        normalize_rows(np.array([[np.nan, 1.0]], dtype=np.float32))
    with pytest.raises(ReferenceLibraryError):
        descriptor_matrix([])


def test_vote_batch_matches_single_votes() -> None:
    rng = np.random.default_rng(3)
    references = normalize_rows(rng.random((60, 12), dtype=np.float32))
    labels = rng.integers(0, 4, 60).astype(np.int64)
    queries = normalize_rows(rng.random((25, 12), dtype=np.float32))

    batch = vote_batch(queries, references, labels, class_count=4)
    single = [vote(query, references, labels, class_count=4) for query in queries]

    # Matrix and vector products may differ in the last float32 digit only.
    assert [(v.class_index, v.agreeing_count) for v in batch] == [
        (v.class_index, v.agreeing_count) for v in single
    ]
    assert np.allclose([v.best_similarity for v in batch], [v.best_similarity for v in single])


def test_vote_batch_keeps_boundary_ties_in_row_order() -> None:
    references = normalize_rows(np.array([[1.0, 0.0]] * 9, dtype=np.float32))
    labels = np.array([1, 1, 1, 1, 1, 1, 1, 0, 0], dtype=np.int64)
    query = np.array([[1.0, 0.0]], dtype=np.float32)

    assert vote_batch(query, references, labels, class_count=2) == [
        vote(query[0], references, labels, class_count=2)
    ]
