from __future__ import annotations

from game_predictor_worker.semi_automatic_selection.contracts import SemiAutomaticSelectionRange
from game_predictor_worker.semi_automatic_selection.v7_range_proof import (
    V7FrameEvidence,
    V7LabelEvidence,
    V7RangeProofKind,
    V7RangeProofResolver,
)


def _frame(
    source: str,
    labels: tuple[tuple[int, int], ...],
    *,
    occurrence: str = "occurrence-a",
    cluster: str = "cluster-a",
) -> V7FrameEvidence:
    return V7FrameEvidence(
        source_id=source,
        occurrence_id=occurrence,
        visual_cluster_id=cluster,
        labels=tuple(V7LabelEvidence(position, value, 0.98, 0.97) for position, value in labels),
    )


def _resolver() -> V7RangeProofResolver:
    return V7RangeProofResolver(
        (SemiAutomaticSelectionRange(1, 9), SemiAutomaticSelectionRange(10, 18))
    )


def test_five_reliable_labels_prove_full_page_despite_missing_left_column() -> None:
    result = _resolver().resolve_frame(
        _frame("left-crop", ((1, 2), (2, 3), (4, 5), (5, 6), (8, 9)))
    )

    assert result.kind is V7RangeProofKind.STRONG_FIVE_LABEL
    assert result.sequence_range == SemiAutomaticSelectionRange(1, 9)


def test_five_reliable_labels_prove_full_page_despite_missing_right_column() -> None:
    result = _resolver().resolve_frame(
        _frame("right-crop", ((0, 1), (3, 4), (4, 5), (6, 7), (7, 8)))
    )

    assert result.kind is V7RangeProofKind.STRONG_FIVE_LABEL
    assert result.sequence_range == SemiAutomaticSelectionRange(1, 9)


def test_sixth_reliable_conflicting_label_vetoes_five_matching_labels() -> None:
    result = _resolver().resolve_frame(
        _frame("mixed", ((0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 99)))
    )

    assert result.kind is V7RangeProofKind.NONE
    assert result.reason_codes == ("CONFLICTING_RELIABLE_LABEL",)


def test_unreliable_mismatch_is_absence_of_evidence_not_a_conflict() -> None:
    frame = V7FrameEvidence(
        source_id="blurred-sixth",
        occurrence_id="occurrence-a",
        visual_cluster_id="cluster-a",
        labels=(
            *(
                V7LabelEvidence(position, value, 0.98, 0.97)
                for position, value in ((0, 1), (1, 2), (2, 3), (4, 5), (8, 9))
            ),
            V7LabelEvidence(5, 99, 0.51, 0.97),
        ),
    )

    result = _resolver().resolve_frame(frame)

    assert result.kind is V7RangeProofKind.STRONG_FIVE_LABEL
    assert result.sequence_range == SemiAutomaticSelectionRange(1, 9)


def test_three_plus_three_requires_two_own_hypotheses_from_independent_clusters() -> None:
    first = _frame("first", ((0, 1), (4, 5), (8, 9)), cluster="cluster-a")
    second = _frame("second", ((1, 2), (3, 4), (7, 8)), cluster="cluster-b")

    result = _resolver().resolve_pair(first, second)

    assert result.kind is V7RangeProofKind.MULTI_FRAME_THREE_PLUS_THREE
    assert result.supporting_source_ids == ("first", "second")


def test_three_plus_three_rejects_duplicate_cluster_other_occurrence_and_two_labels() -> None:
    first = _frame("first", ((0, 1), (4, 5), (8, 9)), cluster="cluster-a")
    same_cluster = _frame("second", ((1, 2), (3, 4), (7, 8)), cluster="cluster-a")
    other_occurrence = _frame(
        "third", ((1, 2), (3, 4), (7, 8)), occurrence="occurrence-b", cluster="cluster-b"
    )
    two_labels = _frame("fourth", ((1, 2), (3, 4)), cluster="cluster-b")

    assert _resolver().resolve_pair(first, same_cluster).reason_codes == (
        "VISUALLY_DEPENDENT_CONFIRMATION",
    )
    assert _resolver().resolve_pair(first, other_occurrence).reason_codes == (
        "CROSS_OCCURRENCE_CONFIRMATION_FORBIDDEN",
    )
    assert _resolver().resolve_pair(first, two_labels).reason_codes == (
        "INSUFFICIENT_INDEPENDENT_3_PLUS_3_EVIDENCE",
    )
