"""Counters advance only for committed pending-to-terminal transitions."""

from types import SimpleNamespace

import pytest
from game_predictor_api.storage.image_symbol_review_bulk_operation_repository import (
    _advance_operation_counts,
)


@pytest.mark.parametrize(
    ("status", "attribute"),
    [("applied", "applied_count"), ("conflict", "conflict_count"), ("failed", "failed_count")],
)
def test_committed_transition_advances_only_its_counter(status, attribute):
    operation = SimpleNamespace(target_count=15, applied_count=4, conflict_count=2, failed_count=1)
    before = vars(operation).copy()
    _advance_operation_counts(operation, status=status, count=3)
    assert vars(operation) == {**before, attribute: before[attribute] + 3}
    # A replay whose targets are already terminal has no new transitions.
    after = vars(operation).copy()
    _advance_operation_counts(operation, status=status, count=0)
    assert vars(operation) == after


def test_transition_cannot_exceed_frozen_membership():
    operation = SimpleNamespace(target_count=2, applied_count=2, conflict_count=0, failed_count=0)
    with pytest.raises(ValueError, match="frozen operation"):
        _advance_operation_counts(operation, status="applied", count=1)


def test_negative_transition_is_rejected_before_counter_change():
    operation = SimpleNamespace(target_count=2, applied_count=0, conflict_count=0, failed_count=0)
    with pytest.raises(ValueError, match="negative"):
        _advance_operation_counts(operation, status="applied", count=-1)
    assert operation.applied_count == 0
