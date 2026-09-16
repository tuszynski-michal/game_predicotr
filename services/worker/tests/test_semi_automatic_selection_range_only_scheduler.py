from __future__ import annotations

from dataclasses import replace

import pytest
from game_predictor_worker.semi_automatic_selection.contracts import (
    SemiAutomaticSelectionError,
)
from game_predictor_worker.semi_automatic_selection.range_only_ocr import (
    RANGE_ONLY_OCR_SCHEDULING_POLICY_V3,
)
from game_predictor_worker.semi_automatic_selection.range_only_scheduler import (
    AdaptiveRangeOcrProbeScheduler,
)


def _signature(value: float) -> tuple[float, ...]:
    return (value,) * 177


def test_scheduler_probes_first_source_and_bounded_interval() -> None:
    scheduler = AdaptiveRangeOcrProbeScheduler(RANGE_ONLY_OCR_SCHEDULING_POLICY_V3)

    decisions = [
        scheduler.decide_signature(source_index=index, signature=_signature(0.5))
        for index in range(6)
    ]

    assert [item.should_probe for item in decisions] == [True, False, False, False, False, True]
    assert decisions[0].reason == "first_source"
    assert decisions[-1].reason == "bounded_interval"


def test_scheduler_probes_a_strong_visual_boundary() -> None:
    scheduler = AdaptiveRangeOcrProbeScheduler(RANGE_ONLY_OCR_SCHEDULING_POLICY_V3)
    scheduler.decide_signature(source_index=0, signature=_signature(0.0))

    decision = scheduler.decide_signature(source_index=1, signature=_signature(1.0))

    assert decision.should_probe is True
    assert decision.reason == "visual_boundary"
    assert decision.adjacent_distance is not None
    assert (
        decision.adjacent_distance
        >= RANGE_ONLY_OCR_SCHEDULING_POLICY_V3.strong_boundary_distance
    )


def test_scheduler_checkpoint_restores_exact_next_decision() -> None:
    original = AdaptiveRangeOcrProbeScheduler(RANGE_ONLY_OCR_SCHEDULING_POLICY_V3)
    for index in range(3):
        original.decide_signature(source_index=index, signature=_signature(0.5))
    restored = AdaptiveRangeOcrProbeScheduler(
        RANGE_ONLY_OCR_SCHEDULING_POLICY_V3,
        checkpoint=original.checkpoint(),
    )

    expected = original.decide_signature(source_index=3, signature=_signature(0.5))
    actual = restored.decide_signature(source_index=3, signature=_signature(0.5))

    assert actual == expected
    assert restored.checkpoint() == original.checkpoint()


def test_unavailable_source_forces_the_next_probe() -> None:
    scheduler = AdaptiveRangeOcrProbeScheduler(RANGE_ONLY_OCR_SCHEDULING_POLICY_V3)
    scheduler.record_unavailable(source_index=0)

    decision = scheduler.decide_signature(source_index=1, signature=_signature(0.5))

    assert decision.should_probe is True
    assert decision.reason == "first_source"


def test_scheduler_rejects_another_policy_or_non_contiguous_source() -> None:
    scheduler = AdaptiveRangeOcrProbeScheduler(RANGE_ONLY_OCR_SCHEDULING_POLICY_V3)
    scheduler.decide_signature(source_index=0, signature=_signature(0.5))
    changed_policy = replace(RANGE_ONLY_OCR_SCHEDULING_POLICY_V3, maximum_probe_interval=6)

    with pytest.raises(SemiAutomaticSelectionError):
        AdaptiveRangeOcrProbeScheduler(changed_policy, checkpoint=scheduler.checkpoint())
    with pytest.raises(SemiAutomaticSelectionError):
        scheduler.decide_signature(source_index=2, signature=_signature(0.5))


def test_scheduler_rejects_a_signature_with_another_descriptor_shape() -> None:
    scheduler = AdaptiveRangeOcrProbeScheduler(RANGE_ONLY_OCR_SCHEDULING_POLICY_V3)

    with pytest.raises(ValueError, match="appearance signature"):
        scheduler.decide_signature(source_index=0, signature=(0.5,) * 176)

    scheduler.decide_signature(source_index=0, signature=_signature(0.5))
    checkpoint = scheduler.checkpoint()
    checkpoint["previousSignature"] = [0.5] * 176

    with pytest.raises(SemiAutomaticSelectionError):
        AdaptiveRangeOcrProbeScheduler(
            RANGE_ONLY_OCR_SCHEDULING_POLICY_V3,
            checkpoint=checkpoint,
        )
