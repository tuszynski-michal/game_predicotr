from __future__ import annotations

import pytest
from game_predictor_worker.semi_automatic_selection.contracts import (
    SEMI_AUTOMATIC_SELECTION_FULL_RANGE_SIZE,
    RangeEvidenceGate,
    RangeEvidenceObservation,
    RangeEvidenceStatus,
    SemiAutomaticSelectionDirection,
    SemiAutomaticSelectionError,
    SemiAutomaticSelectionRange,
    SemiAutomaticSelectionRunStatus,
    SemiAutomaticSelectionSource,
    SemiAutomaticSequenceBounds,
    expected_ranges_fingerprint,
    fingerprint_sources,
    is_valid_run_status_transition,
)

_CHECKSUM = "a" * 64


def _source(
    *,
    source_index: int = 0,
    relative_path: str = "source-001.jpg",
) -> SemiAutomaticSelectionSource:
    return SemiAutomaticSelectionSource(
        source_index=source_index,
        relative_path=relative_path,
        size_bytes=123,
        checksum_sha256=_CHECKSUM,
    )


def _observation(
    *,
    observed_range: SemiAutomaticSelectionRange | None,
    has_strong_local_proof: bool = True,
    confidence: float | None = 0.01,
    **overrides: object,
) -> RangeEvidenceObservation:
    values: dict[str, object] = {
        "source": _source(),
        "observed_range": observed_range,
        "confidence": confidence,
        "has_strong_local_proof": has_strong_local_proof,
    }
    values.update(overrides)
    return RangeEvidenceObservation(**values)  # type: ignore[arg-type]


def test_expected_ranges_are_inclusive_and_keep_partial_final_page() -> None:
    bounds = SemiAutomaticSequenceBounds(first_sequence_number=1, last_sequence_number=19_809)

    ranges = bounds.expected_ranges()

    assert bounds.full_range_size == SEMI_AUTOMATIC_SELECTION_FULL_RANGE_SIZE == 9
    assert len(ranges) == 2_201
    assert ranges[:2] == (
        SemiAutomaticSelectionRange(start=1, end=9),
        SemiAutomaticSelectionRange(start=10, end=18),
    )
    assert ranges[-1] == SemiAutomaticSelectionRange(start=19_801, end=19_809)
    assert SemiAutomaticSelectionRange(start=19_800, end=19_809).board_count == 10
    assert bounds.expected_index_for_range(SemiAutomaticSelectionRange(19_800, 19_809)) is None


def test_descending_bounds_keep_range_names_ascending_but_reverse_source_order() -> None:
    bounds = SemiAutomaticSequenceBounds(
        first_sequence_number=27,
        last_sequence_number=1,
        direction=SemiAutomaticSelectionDirection.DESCENDING,
    )

    assert bounds.expected_ranges() == (
        SemiAutomaticSelectionRange(19, 27),
        SemiAutomaticSelectionRange(10, 18),
        SemiAutomaticSelectionRange(1, 9),
    )
    assert bounds.expected_index_for_range(SemiAutomaticSelectionRange(10, 18)) == 1


@pytest.mark.parametrize(
    ("first", "last", "direction"),
    [
        (0, 9, SemiAutomaticSelectionDirection.ASCENDING),
        (9, 1, SemiAutomaticSelectionDirection.ASCENDING),
        (1, 9, SemiAutomaticSelectionDirection.DESCENDING),
    ],
)
def test_sequence_bounds_reject_invalid_directional_intervals(
    first: int,
    last: int,
    direction: SemiAutomaticSelectionDirection,
) -> None:
    with pytest.raises(SemiAutomaticSelectionError) as error:
        SemiAutomaticSequenceBounds(
            first_sequence_number=first,
            last_sequence_number=last,
            direction=direction,
        )

    assert error.value.code == "SEMI_AUTOMATIC_SELECTION_BOUNDS_INVALID"


def test_source_fingerprint_is_deterministic_and_requires_stable_natural_indexes() -> None:
    sources = (
        _source(source_index=0, relative_path="capture-2.jpg"),
        SemiAutomaticSelectionSource(
            source_index=1,
            relative_path="capture-10.jpg",
            size_bytes=456,
            checksum_sha256="b" * 64,
        ),
    )

    assert fingerprint_sources(sources) == fingerprint_sources(tuple(sources))
    assert expected_ranges_fingerprint(
        SemiAutomaticSequenceBounds(first_sequence_number=1, last_sequence_number=18)
    ) == expected_ranges_fingerprint(
        SemiAutomaticSequenceBounds(first_sequence_number=1, last_sequence_number=18)
    )

    with pytest.raises(SemiAutomaticSelectionError) as error:
        fingerprint_sources((sources[1],))

    assert error.value.code == "SEMI_AUTOMATIC_SELECTION_SOURCE_ORDER_INVALID"


@pytest.mark.parametrize("path", ("../source.jpg", "/source.jpg", "folder\\source.jpg", "a//b.jpg"))
def test_source_identity_rejects_unsafe_or_noncanonical_relative_paths(path: str) -> None:
    with pytest.raises(SemiAutomaticSelectionError) as error:
        _source(relative_path=path)

    assert error.value.code == "SEMI_AUTOMATIC_SELECTION_SOURCE_PATH_UNSAFE"


def test_range_evidence_accepts_exact_local_proof_without_board_quality_gate() -> None:
    gate = RangeEvidenceGate(
        SemiAutomaticSequenceBounds(first_sequence_number=1, last_sequence_number=18)
    )

    result = gate.evaluate(
        _observation(
            observed_range=SemiAutomaticSelectionRange(1, 9),
            confidence=0.01,
            diagnostic_reason_codes=("IMAGE_BLURRY", "IMAGE_OCCLUDED"),
        )
    )

    assert result.status is RangeEvidenceStatus.EXACT_RANGE
    assert result.expected_index == 0
    assert result.confidence == 0.01
    assert result.reason_codes == (
        "IMAGE_BLURRY",
        "IMAGE_OCCLUDED",
        "EXACT_LOCAL_RANGE_PROOF",
    )


def test_range_evidence_requires_local_proof_but_does_not_apply_its_own_threshold() -> None:
    gate = RangeEvidenceGate(
        SemiAutomaticSequenceBounds(first_sequence_number=1, last_sequence_number=9)
    )

    insufficient = gate.evaluate(
        _observation(
            observed_range=SemiAutomaticSelectionRange(1, 9),
            has_strong_local_proof=False,
            confidence=0.99,
        )
    )
    exact = gate.evaluate(
        _observation(
            observed_range=SemiAutomaticSelectionRange(1, 9),
            has_strong_local_proof=True,
            confidence=0.0,
        )
    )

    assert insufficient.status is RangeEvidenceStatus.RANGE_AMBIGUOUS
    assert "RANGE_PROOF_INSUFFICIENT" in insufficient.reason_codes
    assert exact.status is RangeEvidenceStatus.EXACT_RANGE


def test_range_evidence_distinguishes_unreadable_outside_and_noncanonical_ranges() -> None:
    gate = RangeEvidenceGate(
        SemiAutomaticSequenceBounds(first_sequence_number=1, last_sequence_number=18)
    )

    unreadable = gate.evaluate(
        _observation(
            observed_range=None,
            has_strong_local_proof=False,
            confidence=None,
        )
    )
    outside = gate.evaluate(_observation(observed_range=SemiAutomaticSelectionRange(19, 27)))
    noncanonical = gate.evaluate(_observation(observed_range=SemiAutomaticSelectionRange(1, 8)))

    assert unreadable.status is RangeEvidenceStatus.RANGE_UNREADABLE
    assert outside.status is RangeEvidenceStatus.OUTSIDE_REQUESTED_RANGE
    assert noncanonical.status is RangeEvidenceStatus.NOT_EXPECTED_RANGE


def test_range_evidence_rejects_ambiguous_and_undecodable_sources() -> None:
    gate = RangeEvidenceGate(
        SemiAutomaticSequenceBounds(first_sequence_number=1, last_sequence_number=9)
    )

    ambiguous = gate.evaluate(
        _observation(
            observed_range=None,
            has_strong_local_proof=False,
            confidence=None,
            is_ambiguous=True,
        )
    )
    source_error = gate.evaluate(
        _observation(
            observed_range=None,
            has_strong_local_proof=False,
            confidence=None,
            source_decodable=False,
        )
    )

    assert ambiguous.status is RangeEvidenceStatus.RANGE_AMBIGUOUS
    assert source_error.status is RangeEvidenceStatus.SOURCE_ERROR


def test_run_status_transitions_are_explicit_and_terminal_states_do_not_restart() -> None:
    assert is_valid_run_status_transition(
        current=SemiAutomaticSelectionRunStatus.CONFIGURATION,
        target=SemiAutomaticSelectionRunStatus.UPLOADING,
    )
    assert is_valid_run_status_transition(
        current=SemiAutomaticSelectionRunStatus.RUNNING,
        target=SemiAutomaticSelectionRunStatus.PAUSED,
    )
    assert is_valid_run_status_transition(
        current=SemiAutomaticSelectionRunStatus.REVIEW_MODE,
        target=SemiAutomaticSelectionRunStatus.EDIT_SOURCE_MODE,
    )
    assert not is_valid_run_status_transition(
        current=SemiAutomaticSelectionRunStatus.COMPLETED,
        target=SemiAutomaticSelectionRunStatus.RUNNING,
    )
