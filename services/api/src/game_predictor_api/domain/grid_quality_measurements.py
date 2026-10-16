"""Descriptive sampling and explicit human verdicts, independent of model training."""

import hashlib
import heapq
import json
from collections.abc import Iterable
from typing import Any

POLICY = "grid-quality-measurement-v1"
POPULATION_POLICY = "current-source-occurrences-exclude-fully-superseded-v1"


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class PopulationSampler:
    """Consume UUID-keyset metadata once; retain at most the requested sample size."""

    def __init__(self, seed: str, size: int) -> None:
        if not 1 <= size <= 100:
            raise ValueError("Sample size must be between 1 and 100.")
        self.seed, self.size = seed, size
        self.count = 0
        self._digest = hashlib.sha256()
        self._selected: list[tuple[int, str]] = []
        self._last: str | None = None

    def add(self, occurrence: dict[str, Any]) -> None:
        key = occurrence["sourceId"]
        if self._last is not None and key <= self._last:
            raise ValueError("Population must use unique ascending source UUIDs.")
        self._last = key
        self.count += 1
        self._digest.update((canonical(occurrence) + "\n").encode())
        rank = int(digest([POLICY, self.seed, key]), 16)
        item = (-rank, key)
        if len(self._selected) < self.size:
            heapq.heappush(self._selected, item)
        elif item > self._selected[0]:
            heapq.heapreplace(self._selected, item)

    @property
    def population_sha256(self) -> str:
        return self._digest.hexdigest()

    @property
    def selected(self) -> list[str]:
        return sorted(key for _, key in self._selected)


def empty_judgments() -> list[dict[str, Any]]:
    return [
        {
            "positionIndex": index,
            "geometry": "unreviewed",
            "detection": "unreviewed",
            "sequence": "unreviewed",
        }
        for index in range(9)
    ]


def measurement_report(members: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Every rate retains its own denominator; hard samples never enter random totals."""
    result: dict[str, Any] = {}
    for sample in ("random", "hard"):
        rows = [row for row in members if row["sampleKind"] == sample]
        expected = len(rows) * 9
        totals = {
            axis: {
                verdict: 0
                for verdict in ("correct", "incorrect", "unknown", "not_assessable", "unreviewed")
            }
            for axis in ("geometry", "detection", "sequence")
        }
        reviewed = assessable = complete_correct = complete_incorrect = 0
        manual_symbols = symbol_total = unexpected = 0
        producers: dict[str, dict[str, Any]] = {}
        producer_gaps = 0
        for row in rows:
            judgments = row.get("judgments") or empty_judgments()
            for verdict in judgments:
                for axis in totals:
                    totals[axis][verdict[axis]] += 1
            fully_reviewed = len(judgments) == 9 and all(
                item["geometry"] != "unreviewed" for item in judgments
            )
            fully_assessable = fully_reviewed and all(
                item["geometry"] in ("correct", "incorrect") for item in judgments
            )
            reviewed += int(fully_reviewed)
            assessable += int(fully_assessable)
            axes_complete = fully_assessable and all(
                item[axis] in ("correct", "incorrect")
                for item in judgments
                for axis in ("detection", "sequence")
            )
            extras = row.get("unexpectedJudgments", [])
            extras_complete = len(extras) == len(row.get("unexpectedDetections", [])) and all(
                item["verdict"] in ("correct", "incorrect") for item in extras
            )
            if axes_complete and extras_complete:
                correct = all(
                    item[axis] == "correct" for item in judgments for axis in totals
                ) and not row.get("unexpectedDetections")
                complete_correct += int(correct)
                complete_incorrect += int(not correct)
            unexpected += len(row.get("unexpectedDetections", []))
            for position in row["positions"]:
                producer = position["original"].get("producer")
                if producer is None:
                    producer_gaps += 1
                else:
                    snapshot = producer["engineSnapshot"]
                    key = digest(snapshot)
                    group = producers.setdefault(
                        key,
                        {
                            "snapshotSha256": key,
                            "engineSnapshot": snapshot,
                            "positionCount": 0,
                            "geometryAssessedCount": 0,
                            "geometryCorrectCount": 0,
                        },
                    )
                    group["positionCount"] += 1
                    verdict = judgments[position["positionIndex"]]["geometry"]
                    group["geometryAssessedCount"] += int(verdict in ("correct", "incorrect"))
                    group["geometryCorrectCount"] += int(verdict == "correct")
                manual_symbols += position["currentManualSymbolCount"]
                symbol_total += position["currentSymbolCellCount"]
        rates = {}
        for axis, counts in totals.items():
            denominator = counts["correct"] + counts["incorrect"]
            rates[axis] = {
                **counts,
                "assessedCount": denominator,
                "reviewedCount": expected - counts["unreviewed"],
                "expectedCount": expected,
                "correctRate": counts["correct"] / denominator if denominator else None,
                "coverage": denominator / expected if expected else None,
            }
        result[sample] = {
            "sampleCount": len(rows),
            "expectedPositionCount": expected,
            "fullyReviewedCount": reviewed,
            "fullyAssessableCount": assessable,
            "completeCorrectCount": complete_correct,
            "completeIncorrectCount": complete_incorrect,
            "completeUnknownCount": len(rows) - complete_correct - complete_incorrect,
            "unexpectedDetectionCount": unexpected,
            "axes": rates,
            "symbols": {
                "currentManualConfirmationCount": manual_symbols,
                "currentCellCount": symbol_total,
                "classifierAccuracy": None,
            },
            "producerCoverage": {
                "expectedPositionCount": expected,
                "provenPositionCount": expected - producer_gaps,
                "coverageGapCount": producer_gaps,
                "producers": sorted(producers.values(), key=lambda value: value["snapshotSha256"]),
                "activeModelAccuracy": None,
            },
        }
    return result
