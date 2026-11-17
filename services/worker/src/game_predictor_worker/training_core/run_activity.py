"""Attempt-bound evidence of completed work; heartbeats never count as progress."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

PROGRESS_LIMIT_POLICY = "operator-progress-supervised-v1"
PROGRESS_STALL_SECONDS = 300.0
ACTIVITY_FORMAT = "grid-run-activity-v1"
ACTIVITY_FILE = "activity.json"


def progress_supervised(spec: Mapping[str, Any]) -> bool:
    budget = spec.get("budget")
    if not isinstance(budget, Mapping):
        return False
    if budget.get("timePolicy") != PROGRESS_LIMIT_POLICY:
        return False
    if budget.get("remainingSeconds") is not None or budget.get("stallSeconds") != 300:
        raise ValueError("GRID_RUN_SUPERVISION_INVALID")
    return True


class ActivityPublisher:
    def __init__(
        self,
        directory: Path,
        job_id: str,
        attempt: int,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.path = directory / ACTIVITY_FILE
        self.job_id, self.attempt, self.clock = job_id, attempt, clock
        self.sequence = 0
        self.completed: dict[str, int] = {}
        self.last_write = float("-inf")
        self.last_phase = ""

    def advance(self, phase: str, current: int) -> None:
        if not phase or len(phase) > 96 or type(current) is not int or current < 0:
            raise ValueError("GRID_RUN_ACTIVITY_INVALID")
        if current <= self.completed.get(phase, -1):
            return
        self.completed[phase] = current
        self.sequence += 1
        now = self.clock()
        if phase == self.last_phase and now - self.last_write < 1:
            return
        body = {
            "format": ACTIVITY_FORMAT,
            "jobId": self.job_id,
            "attempt": self.attempt,
            "sequence": self.sequence,
            "phase": phase,
            "current": current,
        }
        temporary = self.path.with_suffix(".tmp")
        delays = (0.01, 0.02, 0.04, 0.08, 0.16, 0.16)
        for attempt in range(len(delays) + 1):
            try:
                temporary.write_text(json.dumps(body), encoding="utf-8")
                temporary.replace(self.path)
                break
            except PermissionError as error:
                if getattr(error, "winerror", None) not in (None, 5, 32, 33):
                    raise
                if attempt == len(delays):
                    # Auxiliary evidence is ephemeral. A later completed unit retries;
                    # sustained publication failure is handled by the stall watchdog.
                    return
                time.sleep(delays[attempt])
        self.last_write, self.last_phase = now, phase


class ActivityObserver:
    def __init__(
        self,
        directory: Path,
        job_id: str,
        attempt: int,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.path = directory / ACTIVITY_FILE
        self.job_id, self.attempt, self.clock = job_id, attempt, clock
        self.last_progress = clock()
        self.sequence = 0
        self.completed: dict[str, int] = {}

    def stalled(self) -> bool:
        now = self.clock()
        try:
            with self.path.open("rb") as stream:
                content = stream.read(16_385)
            value = json.loads(content) if len(content) <= 16_384 else None
        except (OSError, ValueError):
            value = None
        if (
            isinstance(value, dict)
            and value.get("format") == ACTIVITY_FORMAT
            and value.get("jobId") == self.job_id
            and type(value.get("attempt")) is int
            and value["attempt"] == self.attempt
            and type(value.get("sequence")) is int
            and value["sequence"] > self.sequence
            and isinstance(value.get("phase"), str)
            and 0 < len(value["phase"]) <= 96
            and type(value.get("current")) is int
            and value["current"] > self.completed.get(value["phase"], -1)
        ):
            self.sequence = value["sequence"]
            self.completed[value["phase"]] = value["current"]
            self.last_progress = now
        return now - self.last_progress >= PROGRESS_STALL_SECONDS
