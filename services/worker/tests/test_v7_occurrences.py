from __future__ import annotations

from copy import deepcopy

import pytest
from game_predictor_worker.semi_automatic_selection.contracts import SemiAutomaticSelectionRange
from game_predictor_worker.semi_automatic_selection.v7_occurrences import (
    V7AnalysisPhase,
    V7OccurrenceError,
    V7OccurrenceObservation,
    V7OccurrenceTracker,
)
from game_predictor_worker.semi_automatic_selection.v7_range_proof import (
    V7LabelEvidence,
    V7RangeProofKind,
    V7RangeProofResult,
    V7WeakFrameEvidence,
)

RANGES = (
    SemiAutomaticSelectionRange(1, 9),
    SemiAutomaticSelectionRange(10, 18),
    SemiAutomaticSelectionRange(19, 27),
)


def _proof(source_id: str, sequence_range: SemiAutomaticSelectionRange) -> V7RangeProofResult:
    return V7RangeProofResult(
        kind=V7RangeProofKind.STRONG_FIVE_LABEL,
        sequence_range=sequence_range,
        supporting_source_ids=(source_id,),
        reason_codes=(),
    )


def _none() -> V7RangeProofResult:
    return V7RangeProofResult(V7RangeProofKind.NONE, None, (), ("NO_LOCAL_PROOF",))


def _weak(
    source_id: str,
    labels: dict[int, int],
    *,
    visual_hash: int,
) -> V7WeakFrameEvidence:
    return V7WeakFrameEvidence(
        source_id=source_id,
        visual_hash=visual_hash,
        visual_signature=bytes([visual_hash % 8]) * 64,
        labels=tuple(
            V7LabelEvidence(
                position_index=position_index,
                sequence_number=sequence_number,
                recognition_confidence=0.99,
                position_confidence=0.99,
            )
            for position_index, sequence_number in sorted(labels.items())
        ),
    )


def _multi_proof(
    sequence_range: SemiAutomaticSelectionRange,
    supporting_source_ids: tuple[str, str],
) -> V7RangeProofResult:
    return V7RangeProofResult(
        kind=V7RangeProofKind.MULTI_FRAME_THREE_PLUS_THREE,
        sequence_range=sequence_range,
        supporting_source_ids=supporting_source_ids,
        reason_codes=(),
    )


def _consume(
    tracker: V7OccurrenceTracker,
    source_index: int,
    sequence_range: SemiAutomaticSelectionRange | None,
) -> None:
    source_id = f"source-{source_index}"
    tracker.consume(
        V7OccurrenceObservation(
            source_index=source_index,
            source_id=source_id,
            proof=_none() if sequence_range is None else _proof(source_id, sequence_range),
        )
    )


def test_later_a_remains_global_candidate_without_rewinding_sequence_cursor() -> None:
    tracker = V7OccurrenceTracker(RANGES)

    _consume(tracker, 0, RANGES[0])
    _consume(tracker, 1, RANGES[1])
    _consume(tracker, 2, RANGES[0])
    occurrences = tracker.finish()

    assert [item.sequence_range for item in occurrences] == [RANGES[0], RANGES[1], RANGES[0]]
    assert [item.occurrence_id for item in occurrences] == [
        "v7-occurrence-00000000",
        "v7-occurrence-00000001",
        "v7-occurrence-00000002",
    ]
    assert tracker.cursors.sequence_cursor_index == 1
    assert tracker.unresolved_gap_indexes == ()
    assert [
        item.occurrence_id
        for item in tracker.global_occurrences()
        if item.sequence_range == RANGES[0]
    ] == [
        "v7-occurrence-00000000",
        "v7-occurrence-00000002",
    ]


def test_later_b_fills_gap_without_rewinding_cursor() -> None:
    tracker = V7OccurrenceTracker(RANGES)

    _consume(tracker, 0, RANGES[0])
    _consume(tracker, 1, RANGES[2])
    assert tracker.cursors.sequence_cursor_index == 2
    assert tracker.unresolved_gap_indexes == (1,)

    _consume(tracker, 2, RANGES[1])

    assert tracker.cursors.sequence_cursor_index == 2
    assert tracker.unresolved_gap_indexes == ()
    assert [item.sequence_range for item in tracker.finish()] == [RANGES[0], RANGES[2], RANGES[1]]


def test_unproven_sources_and_pause_do_not_split_active_occurrence() -> None:
    tracker = V7OccurrenceTracker(RANGES)
    _consume(tracker, 0, RANGES[0])
    _consume(tracker, 1, None)
    worker_and_sequence_before_view = (
        tracker.cursors.next_source_index,
        tracker.cursors.sequence_cursor_index,
    )
    tracker.set_viewed_source_index(1)
    assert (
        tracker.cursors.next_source_index,
        tracker.cursors.sequence_cursor_index,
    ) == worker_and_sequence_before_view
    before_pause = tracker.checkpoint()

    tracker.pause()
    restored = V7OccurrenceTracker(RANGES, checkpoint=tracker.checkpoint())

    assert restored.phase is V7AnalysisPhase.PAUSED
    assert restored.cursors == tracker.cursors
    assert restored.checkpoint()["activeOccurrence"] == before_pause["activeOccurrence"]
    restored.resume()
    _consume(restored, 2, RANGES[0])

    (occurrence,) = restored.finish()
    assert occurrence.first_source_index == 0
    assert occurrence.last_source_index == 2
    assert [item.source_index for item in occurrence.proven_sources] == [0, 2]
    assert restored.cursors.viewed_source_index == 1


def test_eof_finalization_is_idempotent_and_requires_eof_for_global_candidates() -> None:
    tracker = V7OccurrenceTracker(RANGES)
    _consume(tracker, 0, RANGES[0])

    with pytest.raises(V7OccurrenceError, match="EOF"):
        tracker.global_occurrences()

    first = tracker.finish()
    second = tracker.finish()

    assert first == second == tracker.global_occurrences()
    assert tracker.phase is V7AnalysisPhase.COMPLETE
    with pytest.raises(V7OccurrenceError, match="requires running"):
        _consume(tracker, 1, RANGES[1])


def test_checkpoint_restores_gaps_active_occurrence_and_all_cursors() -> None:
    original = V7OccurrenceTracker(RANGES)
    _consume(original, 0, RANGES[0])
    _consume(original, 1, RANGES[2])
    original.set_viewed_source_index(0)

    restored = V7OccurrenceTracker(RANGES, checkpoint=original.checkpoint())

    assert restored.cursors == original.cursors
    assert restored.source_index_for("source-0") == 0
    assert restored.source_index_for("missing-source") is None
    assert restored.unresolved_gap_indexes == (1,)
    _consume(restored, 2, RANGES[1])
    assert restored.cursors.sequence_cursor_index == 2
    assert restored.unresolved_gap_indexes == ()


def test_cancelled_tracker_cannot_finalize_or_mutate_worker_progress() -> None:
    tracker = V7OccurrenceTracker(RANGES)
    _consume(tracker, 0, RANGES[0])
    tracker.set_viewed_source_index(0)
    tracker.cancel()

    assert tracker.phase is V7AnalysisPhase.CANCELLED
    assert tracker.cursors.viewed_source_index == 0
    with pytest.raises(V7OccurrenceError, match="requires running"):
        tracker.finish()
    with pytest.raises(V7OccurrenceError, match="requires running"):
        _consume(tracker, 1, RANGES[1])
    with pytest.raises(V7OccurrenceError, match="cancelled"):
        tracker.cancel()

    restored = V7OccurrenceTracker(RANGES, checkpoint=tracker.checkpoint())
    assert restored.phase is V7AnalysisPhase.CANCELLED
    assert restored.cursors == tracker.cursors


def test_rejects_out_of_order_foreign_and_malformed_proofs() -> None:
    tracker = V7OccurrenceTracker(RANGES)
    with pytest.raises(V7OccurrenceError, match="manifest order"):
        tracker.consume(V7OccurrenceObservation(1, "source-1", _proof("source-1", RANGES[0])))

    foreign = SemiAutomaticSelectionRange(28, 36)
    with pytest.raises(V7OccurrenceError, match="not valid"):
        tracker.consume(V7OccurrenceObservation(0, "source-0", _proof("source-0", foreign)))
    assert tracker.cursors.next_source_index == 0

    malformed_none = V7RangeProofResult(V7RangeProofKind.NONE, RANGES[0], (), ())
    with pytest.raises(V7OccurrenceError, match="no-proof"):
        tracker.consume(V7OccurrenceObservation(0, "source-0", malformed_none))
    assert tracker.cursors.next_source_index == 0


def test_invalid_checkpoint_fails_closed() -> None:
    tracker = V7OccurrenceTracker(RANGES)
    _consume(tracker, 0, RANGES[0])
    checkpoint = deepcopy(tracker.checkpoint())
    checkpoint["unresolvedGapIndexes"] = [2]

    with pytest.raises(V7OccurrenceError, match="gap state"):
        V7OccurrenceTracker(RANGES, checkpoint=checkpoint)


def test_checkpoint_cannot_reuse_an_occurrence_identity_after_restart() -> None:
    tracker = V7OccurrenceTracker(RANGES)
    _consume(tracker, 0, RANGES[0])
    checkpoint = deepcopy(tracker.checkpoint())
    checkpoint["nextOccurrenceNumber"] = 0

    with pytest.raises(V7OccurrenceError, match="identity can be repeated"):
        V7OccurrenceTracker(RANGES, checkpoint=checkpoint)


def test_three_plus_three_can_open_one_occurrence_after_unproven_source() -> None:
    tracker = V7OccurrenceTracker(RANGES)
    _consume(tracker, 0, None)
    tracker.consume(
        V7OccurrenceObservation(
            1,
            "source-1",
            _multi_proof(RANGES[0], ("source-0", "source-1")),
        )
    )

    (occurrence,) = tracker.finish()
    assert (occurrence.first_source_index, occurrence.last_source_index) == (0, 1)
    assert occurrence.proven_sources[0].supporting_source_ids == ("source-0", "source-1")


def test_tracker_resolves_independent_three_plus_three_and_restores_pending_evidence() -> None:
    tracker = V7OccurrenceTracker(RANGES)
    tracker.consume(
        V7OccurrenceObservation(
            0,
            "source-0",
            _none(),
            _weak("source-0", {0: 1, 4: 5, 8: 9}, visual_hash=0),
        )
    )
    checkpoint = tracker.checkpoint()
    assert checkpoint["pendingWeakEvidence"] is not None

    restored = V7OccurrenceTracker(RANGES, checkpoint=checkpoint)
    restored.consume(
        V7OccurrenceObservation(
            1,
            "source-1",
            _none(),
            _weak(
                "source-1",
                {1: 2, 3: 4, 7: 8},
                visual_hash=(1 << 64) - 1,
            ),
        )
    )

    (occurrence,) = restored.finish()
    assert occurrence.sequence_range == RANGES[0]
    assert occurrence.proven_sources[0].proof_kind is V7RangeProofKind.MULTI_FRAME_THREE_PLUS_THREE
    assert occurrence.proven_sources[0].supporting_source_ids == ("source-0", "source-1")


def test_tracker_rejects_duplicate_or_two_label_weak_evidence() -> None:
    tracker = V7OccurrenceTracker(RANGES)
    tracker.consume(
        V7OccurrenceObservation(
            0,
            "source-0",
            _none(),
            _weak("source-0", {0: 1, 4: 5, 8: 9}, visual_hash=0),
        )
    )
    tracker.consume(
        V7OccurrenceObservation(
            1,
            "source-1",
            _none(),
            _weak("source-1", {1: 2, 3: 4, 7: 8}, visual_hash=0),
        )
    )
    assert tracker.finish() == ()

    two_labels = V7OccurrenceTracker(RANGES)
    two_labels.consume(
        V7OccurrenceObservation(
            0,
            "source-0",
            _none(),
            _weak("source-0", {0: 1, 4: 5}, visual_hash=0),
        )
    )
    two_labels.consume(
        V7OccurrenceObservation(
            1,
            "source-1",
            _none(),
            _weak("source-1", {1: 2, 3: 4, 7: 8}, visual_hash=(1 << 64) - 1),
        )
    )
    assert two_labels.finish() == ()


def test_checkpoint_rejects_missing_or_incoherent_pending_weak_evidence() -> None:
    tracker = V7OccurrenceTracker(RANGES)
    tracker.consume(
        V7OccurrenceObservation(
            0,
            "source-0",
            _none(),
            _weak("source-0", {0: 1, 4: 5, 8: 9}, visual_hash=0),
        )
    )
    corrupt = deepcopy(tracker.checkpoint())
    pending = corrupt["pendingWeakEvidence"]
    assert isinstance(pending, dict)
    labels = pending["labels"]
    assert isinstance(labels, list)
    labels.append(
        {
            "positionConfidence": 0.99,
            "positionIndex": 1,
            "recognitionConfidence": 0.99,
            "sequenceNumber": 2,
        }
    )

    with pytest.raises(V7OccurrenceError, match="pending weak"):
        V7OccurrenceTracker(RANGES, checkpoint=corrupt)

    missing = deepcopy(tracker.checkpoint())
    missing.pop("pendingWeakEvidence")
    with pytest.raises(V7OccurrenceError, match="checkpoint"):
        V7OccurrenceTracker(RANGES, checkpoint=missing)

    legacy = deepcopy(tracker.checkpoint())
    legacy["schemaVersion"] = 1
    legacy["algorithmVersion"] = "v7-occurrence-tracker-v1"
    legacy.pop("pendingWeakEvidence")
    restored = V7OccurrenceTracker(RANGES, checkpoint=legacy)
    assert restored.cursors == tracker.cursors


def test_three_plus_three_can_open_the_next_range_after_restart() -> None:
    tracker = V7OccurrenceTracker(RANGES)
    _consume(tracker, 0, RANGES[0])
    _consume(tracker, 1, None)

    restored = V7OccurrenceTracker(RANGES, checkpoint=tracker.checkpoint())
    restored.consume(
        V7OccurrenceObservation(
            2,
            "source-2",
            _multi_proof(RANGES[1], ("source-1", "source-2")),
        )
    )

    first, second = restored.finish()
    assert (first.sequence_range, first.first_source_index, first.last_source_index) == (
        RANGES[0],
        0,
        0,
    )
    assert (second.sequence_range, second.first_source_index, second.last_source_index) == (
        RANGES[1],
        1,
        2,
    )


def test_three_plus_three_rejects_reused_source_or_cross_occurrence_support() -> None:
    tracker = V7OccurrenceTracker(RANGES)
    _consume(tracker, 0, RANGES[0])
    _consume(tracker, 1, RANGES[1])

    with pytest.raises(V7OccurrenceError, match="crosses"):
        tracker.consume(
            V7OccurrenceObservation(
                2,
                "source-2",
                _multi_proof(RANGES[0], ("source-0", "source-2")),
            )
        )
    assert tracker.cursors.next_source_index == 2

    with pytest.raises(V7OccurrenceError, match="3\\+3"):
        tracker.consume(
            V7OccurrenceObservation(
                2,
                "source-2",
                _multi_proof(RANGES[1], ("source-2", "source-2")),
            )
        )
    assert tracker.cursors.next_source_index == 2


def test_checkpoint_rejects_proofless_confirmation_and_active_overlap() -> None:
    tracker = V7OccurrenceTracker(RANGES)
    _consume(tracker, 0, RANGES[0])
    proofless_confirmation = deepcopy(tracker.checkpoint())
    proofless_confirmation["confirmedExpectedIndexes"] = [0, 1, 2]
    proofless_confirmation["cursors"] = {
        **proofless_confirmation["cursors"],
        "sequenceCursorIndex": 2,
    }
    proofless_confirmation["unresolvedGapIndexes"] = []

    with pytest.raises(V7OccurrenceError, match="do not match occurrence proof"):
        V7OccurrenceTracker(RANGES, checkpoint=proofless_confirmation)

    _consume(tracker, 1, RANGES[1])
    overlap = deepcopy(tracker.checkpoint())
    active = overlap["activeOccurrence"]
    assert isinstance(active, dict)
    active["firstSourceIndex"] = 0

    with pytest.raises(V7OccurrenceError, match="occurrences overlap"):
        V7OccurrenceTracker(RANGES, checkpoint=overlap)

    valid_checkpoint = tracker.checkpoint()
    missing_active = deepcopy(valid_checkpoint)
    missing_active["activeOccurrence"] = None
    finalized = missing_active["finalizedOccurrences"]
    assert isinstance(finalized, list)
    finalized.append(valid_checkpoint["activeOccurrence"])
    with pytest.raises(V7OccurrenceError, match="lost its active occurrence"):
        V7OccurrenceTracker(RANGES, checkpoint=missing_active)


def test_checkpoint_rejects_three_plus_three_support_crossing_a_finalized_occurrence() -> None:
    tracker = V7OccurrenceTracker(RANGES)
    _consume(tracker, 0, RANGES[0])
    _consume(tracker, 1, RANGES[1])
    checkpoint = deepcopy(tracker.checkpoint())
    active = checkpoint["activeOccurrence"]
    assert isinstance(active, dict)
    proofs = active["provenSources"]
    assert isinstance(proofs, list)
    proof = proofs[0]
    assert isinstance(proof, dict)
    proof["proofKind"] = V7RangeProofKind.MULTI_FRAME_THREE_PLUS_THREE.value
    proof["supportingSourceIds"] = ["source-0", "source-1"]

    with pytest.raises(V7OccurrenceError, match="crosses an occurrence boundary"):
        V7OccurrenceTracker(RANGES, checkpoint=checkpoint)


def test_checkpoint_rejects_malformed_strong_proof_and_incomplete_source_registry() -> None:
    tracker = V7OccurrenceTracker(RANGES)
    _consume(tracker, 0, RANGES[0])

    malformed_proof = deepcopy(tracker.checkpoint())
    active = malformed_proof["activeOccurrence"]
    assert isinstance(active, dict)
    proofs = active["provenSources"]
    assert isinstance(proofs, list)
    proof = proofs[0]
    assert isinstance(proof, dict)
    proof["supportingSourceIds"] = ["source-0", "forged-source"]
    with pytest.raises(V7OccurrenceError, match="occurrence checkpoint is invalid"):
        V7OccurrenceTracker(RANGES, checkpoint=malformed_proof)

    incomplete_registry = deepcopy(tracker.checkpoint())
    seen_sources = incomplete_registry["seenSources"]
    assert isinstance(seen_sources, list)
    seen_sources.clear()
    with pytest.raises(V7OccurrenceError, match="occurrence checkpoint is invalid"):
        V7OccurrenceTracker(RANGES, checkpoint=incomplete_registry)
