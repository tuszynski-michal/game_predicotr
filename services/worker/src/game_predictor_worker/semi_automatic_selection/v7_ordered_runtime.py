"""Bounded preparation with deterministic, single-consumer V7 ordering.

V7 can overlap reading/decoding a future source with OCR of the current source,
but the stateful proof, quality and checkpoint path must observe source indexes
in manifest order.  This module intentionally knows nothing about Paddle or
images: callers own their immutable input/output contracts and keep one mutable
recognizer in the serial ``consume`` callback.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from time import perf_counter


class V7OrderedRuntimeError(RuntimeError):
    """One bounded stage failed before its source could be consumed."""

    def __init__(self, *, source_index: int, stage: str, cause: BaseException) -> None:
        super().__init__(f"V7 ordered runtime {stage} failed at source {source_index}: {cause}")
        self.source_index = source_index
        self.stage = stage
        self.__cause__ = cause


@dataclass(frozen=True, slots=True)
class V7OrderedRuntimePolicy:
    """A measured concurrency profile; OCR remains outside this worker pool."""

    prepare_workers: int = 4
    max_in_flight: int = 8

    def __post_init__(self) -> None:
        if not 1 <= self.prepare_workers <= 4:
            raise ValueError("V7 preparation workers must be between one and four.")
        if not self.prepare_workers <= self.max_in_flight <= 8:
            raise ValueError("V7 max in-flight must be between workers and eight.")

    @classmethod
    def for_workers(cls, prepare_workers: int) -> V7OrderedRuntimePolicy:
        """Use the bounded default selected by the T11 benchmark protocol."""

        return cls(
            prepare_workers=prepare_workers,
            max_in_flight=min(8, prepare_workers * 2),
        )

    def as_dict(self) -> dict[str, int]:
        return {
            "maxInFlight": self.max_in_flight,
            "prepareWorkers": self.prepare_workers,
        }


@dataclass(frozen=True, slots=True)
class V7OrderedRuntimeInput[InputValue]:
    source_index: int
    value: InputValue


@dataclass(frozen=True, slots=True)
class V7OrderedRuntimeMetrics:
    input_count: int
    maximum_in_flight: int
    maximum_queued_ready: int
    prepare_seconds: float
    consume_seconds: float
    total_seconds: float

    def as_dict(self) -> dict[str, float | int]:
        return {
            "consumeMilliseconds": round(self.consume_seconds * 1000, 4),
            "inputCount": self.input_count,
            "maxInFlightObserved": self.maximum_in_flight,
            "maxQueuedReadyObserved": self.maximum_queued_ready,
            "prepareMilliseconds": round(self.prepare_seconds * 1000, 4),
            "totalMilliseconds": round(self.total_seconds * 1000, 4),
        }


@dataclass(frozen=True, slots=True)
class V7OrderedRuntimeResult:
    """Scheduler-owned result; consumer outputs belong to its checkpoint sink."""

    metrics: V7OrderedRuntimeMetrics


def run_v7_ordered_runtime[InputValue, PreparedValue](
    inputs: Iterable[V7OrderedRuntimeInput[InputValue]],
    *,
    prepare: Callable[[InputValue], PreparedValue],
    consume: Callable[[int, PreparedValue], None],
    policy: V7OrderedRuntimePolicy | None = None,
) -> V7OrderedRuntimeResult:
    """Prepare future inputs concurrently and consume only the next source.

    The only retained image-like payloads are futures in the bounded window.
    The serial ``consume`` callback writes each small result to its own bounded
    sink or checkpoint and returns nothing, so this scheduler cannot collect a
    full folder of OCR results in memory.
    When preparation fails, prior consumed sources remain a valid resumable
    prefix; no later source is passed to ``consume``.  The caller owns the
    checkpoint boundary for that prefix.
    """

    active_policy = policy or V7OrderedRuntimePolicy()
    ordered_inputs = tuple(inputs)
    _validate_ordered_inputs(ordered_inputs)
    if not ordered_inputs:
        return V7OrderedRuntimeResult(
            metrics=V7OrderedRuntimeMetrics(
                input_count=0,
                maximum_in_flight=0,
                maximum_queued_ready=0,
                prepare_seconds=0.0,
                consume_seconds=0.0,
                total_seconds=0.0,
            ),
        )

    started_at = perf_counter()
    prepare_seconds = 0.0
    consume_seconds = 0.0
    maximum_in_flight = 0
    maximum_queued_ready = 0
    futures: dict[int, Future[tuple[PreparedValue, float]]] = {}
    next_submit_position = 0
    next_consume_position = 0

    def submit_next(executor: ThreadPoolExecutor) -> bool:
        nonlocal next_submit_position, maximum_in_flight
        if next_submit_position >= len(ordered_inputs):
            return False
        item = ordered_inputs[next_submit_position]
        futures[item.source_index] = executor.submit(_time_prepare, prepare, item.value)
        next_submit_position += 1
        maximum_in_flight = max(maximum_in_flight, len(futures))
        return True

    executor = ThreadPoolExecutor(
        max_workers=active_policy.prepare_workers,
        thread_name_prefix="v7-prepare",
    )
    try:
        while len(futures) < active_policy.max_in_flight and submit_next(executor):
            pass
        while next_consume_position < len(ordered_inputs):
            item = ordered_inputs[next_consume_position]
            future = futures.pop(item.source_index)
            ready_count = sum(candidate.done() for candidate in futures.values())
            maximum_queued_ready = max(maximum_queued_ready, ready_count)
            try:
                prepared, elapsed_prepare_seconds = future.result()
            except BaseException as error:
                raise V7OrderedRuntimeError(
                    source_index=item.source_index,
                    stage="prepare",
                    cause=error,
                ) from error
            prepare_seconds += elapsed_prepare_seconds
            consumed_started_at = perf_counter()
            try:
                consume(item.source_index, prepared)
            except BaseException as error:
                raise V7OrderedRuntimeError(
                    source_index=item.source_index,
                    stage="consume",
                    cause=error,
                ) from error
            consume_seconds += perf_counter() - consumed_started_at
            next_consume_position += 1
            # Do not retain the just-consumed image while replenishing the
            # preparation window.  ``future`` was popped above; clearing both
            # scheduler references keeps live prepared payloads bounded by the
            # configured future window, excluding an intentional caller-owned
            # value returned by ``consume``.
            del prepared
            del future
            submit_next(executor)
    except BaseException:
        for future in futures.values():
            future.cancel()
        executor.shutdown(wait=True, cancel_futures=True)
        raise
    else:
        executor.shutdown(wait=True)

    return V7OrderedRuntimeResult(
        metrics=V7OrderedRuntimeMetrics(
            input_count=len(ordered_inputs),
            maximum_in_flight=maximum_in_flight,
            maximum_queued_ready=maximum_queued_ready,
            prepare_seconds=prepare_seconds,
            consume_seconds=consume_seconds,
            total_seconds=perf_counter() - started_at,
        ),
    )


def _validate_ordered_inputs[InputValue](
    inputs: tuple[V7OrderedRuntimeInput[InputValue], ...],
) -> None:
    if not inputs:
        return
    expected = inputs[0].source_index
    for item in inputs:
        if item.source_index != expected or item.source_index < 0:
            raise ValueError(
                "V7 runtime inputs require unique consecutive non-negative source indexes."
            )
        expected += 1


def _time_prepare[InputValue, PreparedValue](
    prepare: Callable[[InputValue], PreparedValue],
    value: InputValue,
) -> tuple[PreparedValue, float]:
    started_at = perf_counter()
    return prepare(value), perf_counter() - started_at


__all__ = [
    "V7OrderedRuntimeError",
    "V7OrderedRuntimeInput",
    "V7OrderedRuntimeMetrics",
    "V7OrderedRuntimePolicy",
    "V7OrderedRuntimeResult",
    "run_v7_ordered_runtime",
]
