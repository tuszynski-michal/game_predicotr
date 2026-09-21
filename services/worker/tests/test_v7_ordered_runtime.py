from __future__ import annotations

import gc
import weakref
from threading import Event
from time import sleep

import pytest
from game_predictor_worker.semi_automatic_selection.v7_ordered_runtime import (
    V7OrderedRuntimeError,
    V7OrderedRuntimeInput,
    V7OrderedRuntimePolicy,
    run_v7_ordered_runtime,
)


def _inputs(count: int) -> tuple[V7OrderedRuntimeInput[int], ...]:
    return tuple(V7OrderedRuntimeInput(index, index) for index in range(count))


def test_consumes_out_of_order_preparation_in_source_order() -> None:
    consumed: list[int] = []
    values: list[int] = []

    def consume(source_index: int, value: int) -> None:
        consumed.append(source_index)
        values.append(value * 10)

    result = run_v7_ordered_runtime(
        _inputs(6),
        prepare=lambda value: _slow_first(value),
        consume=consume,
        policy=V7OrderedRuntimePolicy(prepare_workers=4, max_in_flight=4),
    )

    assert consumed == [0, 1, 2, 3, 4, 5]
    assert values == [0, 10, 20, 30, 40, 50]
    assert result.metrics.maximum_in_flight <= 4
    assert result.metrics.maximum_queued_ready >= 1


def test_never_schedules_more_than_bounded_window_while_first_input_is_slow() -> None:
    release_first = Event()
    started: list[int] = []
    consumed: list[int] = []

    def prepare(value: int) -> int:
        started.append(value)
        if value == 0:
            assert release_first.wait(timeout=1)
        return value

    def consume(source_index: int, value: int) -> None:
        consumed.append(source_index)

    # The event is released by the third scheduled preparation, before source 0
    # can be consumed and before a fourth item could be added to the window.
    def release_after_two(value: int) -> int:
        prepared = prepare(value)
        if value == 2:
            release_first.set()
        return prepared

    result = run_v7_ordered_runtime(
        _inputs(7),
        prepare=release_after_two,
        consume=consume,
        policy=V7OrderedRuntimePolicy(prepare_workers=3, max_in_flight=3),
    )

    assert result.metrics.maximum_in_flight == 3
    assert consumed == list(range(7))
    assert started[:3] == [0, 1, 2] or started[:3] == [0, 2, 1]


def test_prepare_failure_keeps_only_a_resumable_consumed_prefix() -> None:
    consumed: list[int] = []

    def prepare(value: int) -> int:
        if value == 2:
            raise OSError("bad jpeg")
        return value

    with pytest.raises(V7OrderedRuntimeError) as error:
        run_v7_ordered_runtime(
            _inputs(5),
            prepare=prepare,
            consume=lambda source_index, value: consumed.append(source_index),
            policy=V7OrderedRuntimePolicy(prepare_workers=3, max_in_flight=3),
        )

    assert error.value.stage == "prepare"
    assert error.value.source_index == 2
    assert consumed == [0, 1]


def test_consume_failure_does_not_consume_later_sources() -> None:
    consumed: list[int] = []

    def consume(source_index: int, value: int) -> None:
        consumed.append(source_index)
        if source_index == 1:
            raise ValueError("checkpoint unavailable")

    with pytest.raises(V7OrderedRuntimeError) as error:
        run_v7_ordered_runtime(
            _inputs(4),
            prepare=lambda value: value,
            consume=consume,
            policy=V7OrderedRuntimePolicy(prepare_workers=2, max_in_flight=4),
        )

    assert error.value.stage == "consume"
    assert error.value.source_index == 1
    assert consumed == [0, 1]


def test_rejects_nonconsecutive_or_negative_indexes_before_workers_start() -> None:
    started = False

    def prepare(value: int) -> int:
        nonlocal started
        started = True
        return value

    with pytest.raises(ValueError, match="unique consecutive"):
        run_v7_ordered_runtime(
            (V7OrderedRuntimeInput(0, 0), V7OrderedRuntimeInput(2, 2)),
            prepare=prepare,
            consume=lambda _index, _value: None,
        )
    with pytest.raises(ValueError, match="unique consecutive"):
        run_v7_ordered_runtime(
            (V7OrderedRuntimeInput(-1, -1),),
            prepare=prepare,
            consume=lambda _index, _value: None,
        )
    assert not started


def test_worker_count_does_not_change_ordered_result_or_digest_input() -> None:
    values_by_workers: dict[int, tuple[int, ...]] = {}
    metrics_by_workers: dict[int, int] = {}
    for workers in (1, 2, 4):
        values: list[int] = []

        def consume(source_index: int, value: int, *, observed_values: list[int] = values) -> None:
            observed_values.append((source_index * 100) + value)

        result = run_v7_ordered_runtime(
            _inputs(12),
            prepare=lambda value: _slow_first(value),
            consume=consume,
            policy=V7OrderedRuntimePolicy.for_workers(workers),
        )
        values_by_workers[workers] = tuple(values)
        metrics_by_workers[workers] = result.metrics.maximum_in_flight

    assert values_by_workers[1] == values_by_workers[2] == values_by_workers[4]
    assert metrics_by_workers == {1: 2, 2: 4, 4: 8}
    assert V7OrderedRuntimePolicy() == V7OrderedRuntimePolicy.for_workers(4)


def test_releases_consumed_payload_before_refilling_preparation_window() -> None:
    payload_zero: weakref.ReferenceType[Payload] | None = None
    payload_was_released_before_next_prepare = False

    def prepare(value: int) -> Payload:
        nonlocal payload_was_released_before_next_prepare
        if value == 2:
            gc.collect()
            assert payload_zero is not None
            payload_was_released_before_next_prepare = payload_zero() is None
        return Payload(value)

    def consume(source_index: int, payload: Payload) -> None:
        nonlocal payload_zero
        if source_index == 0:
            payload_zero = weakref.ref(payload)

    result = run_v7_ordered_runtime(
        _inputs(3),
        prepare=prepare,
        consume=consume,
        policy=V7OrderedRuntimePolicy(prepare_workers=1, max_in_flight=2),
    )

    assert result.metrics.input_count == 3
    assert payload_was_released_before_next_prepare


def _slow_first(value: int) -> int:
    sleep(0.02 if value == 0 else 0.001)
    return value


class Payload:
    def __init__(self, value: int) -> None:
        self.value = value
