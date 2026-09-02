"""Recoverable JSONL diagnostics for the range-only selection engine."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import NoReturn, cast
from uuid import UUID

from .contracts import (
    RangeEvidenceResult,
    RangeEvidenceStatus,
    SemiAutomaticSelectionError,
    SemiAutomaticSelectionRange,
    SemiAutomaticSelectionSource,
)
from .engine import RangeGroup, RangeGroupSelection, select_middle_exact_observation
from .middle_row_grouping import (
    MIDDLE_ROW_EVIDENCE_SELECTOR_VERSION,
    ROW_FIRST_EVIDENCE_SELECTOR_VERSION,
    select_exact_evidence_span_observation,
    select_middle_row_exact_observation,
)

SEMI_AUTOMATIC_SELECTION_DIAGNOSTIC_CONTRACT = "semi-automatic-range-selection-diagnostics-v1"


class SemiAutomaticSelectionAudit:
    """Append observations/groups and atomically replace bounded checkpoints."""

    def __init__(self, artifact_root: Path, run_id: UUID) -> None:
        root = artifact_root.resolve()
        self.root = root / "exports" / "semi-automatic-selection" / str(run_id)
        self.root.mkdir(parents=True, exist_ok=True)
        if root not in self.root.resolve().parents:
            _fail(
                "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
                "The diagnostics directory escapes the managed artifact root.",
            )
        self.observations_path = self.root / "observations.jsonl"
        self.groups_path = self.root / "groups.jsonl"
        self.checkpoint_path = self.root / "checkpoint.json"
        self.report_path = self.root / "selection-report.json"

    def reconcile(self, *, observation_count: int, group_count: int) -> None:
        """Discard only uncommitted JSONL suffixes after a crash."""

        _truncate_to_committed_lines(
            self.observations_path,
            observation_count,
            identity_field="sourceIndex",
        )
        _truncate_to_committed_lines(
            self.groups_path,
            group_count,
            identity_field="groupOrder",
        )

    def append_observation(self, evidence: RangeEvidenceResult) -> None:
        _append_json(self.observations_path, observation_to_dict(evidence))

    def append_groups(self, groups: Iterable[RangeGroup]) -> None:
        for group in groups:
            _append_json(self.groups_path, group.to_dict())

    def write_checkpoint(self, checkpoint: Mapping[str, object]) -> None:
        _write_atomic_json(self.checkpoint_path, checkpoint)

    def iter_groups(self, *, start_group_order: int = 0) -> Iterator[RangeGroup]:
        for payload in _iter_json_lines(self.groups_path):
            group = RangeGroup.from_dict(payload)
            if group.group_order >= start_group_order:
                yield group

    def iter_observation_payloads(self) -> Iterator[dict[str, object]]:
        """Yield persisted observations without selecting a representative."""

        yield from _iter_json_lines(self.observations_path)

    def iter_group_selections(
        self,
        *,
        start_group_order: int = 0,
        selection_method: str | None = None,
    ) -> Iterator[RangeGroupSelection]:
        """Merge both ordered JSONL streams in O(N) time and bounded memory."""

        observations = iter(_iter_observations(self.observations_path))
        current = next(observations, None)
        for group in self.iter_groups(start_group_order=start_group_order):
            group_first_source_index = group.first_source_index
            group_last_source_index = group.last_source_index
            while current is not None and current.source.source_index < group_first_source_index:
                current = next(observations, None)

            def group_evidence(
                group_end: int = group_last_source_index,
            ) -> Iterator[RangeEvidenceResult]:
                nonlocal current
                while current is not None and current.source.source_index <= group_end:
                    value = current
                    current = next(observations, None)
                    yield value

            evidence = group_evidence()
            if selection_method == MIDDLE_ROW_EVIDENCE_SELECTOR_VERSION:
                yield select_middle_row_exact_observation(group, evidence)
            elif selection_method == ROW_FIRST_EVIDENCE_SELECTOR_VERSION:
                yield select_exact_evidence_span_observation(
                    group,
                    evidence,
                    selector_version=ROW_FIRST_EVIDENCE_SELECTOR_VERSION,
                )
            else:
                yield select_middle_exact_observation(group, evidence)

    def write_report(self, payload: Mapping[str, object]) -> tuple[str, str]:
        document = {
            "contract": SEMI_AUTOMATIC_SELECTION_DIAGNOSTIC_CONTRACT,
            **dict(payload),
        }
        _write_atomic_json(self.report_path, document)
        content = self.report_path.read_bytes()
        return (
            self.report_path.relative_to(self.root.parents[2]).as_posix(),
            hashlib.sha256(content).hexdigest(),
        )


def observation_to_dict(evidence: RangeEvidenceResult) -> dict[str, object]:
    payload: dict[str, object] = {
        "confidence": evidence.confidence,
        "expectedIndex": evidence.expected_index,
        "observedRange": (
            None
            if evidence.observed_range is None
            else {
                "end": evidence.observed_range.end,
                "start": evidence.observed_range.start,
            }
        ),
        "reasonCodes": list(evidence.reason_codes),
        "sourceChecksumSha256": evidence.source.checksum_sha256,
        "sourceIndex": evidence.source.source_index,
        "sourceRelativePath": evidence.source.relative_path,
        "sourceSizeBytes": evidence.source.size_bytes,
        "status": evidence.status.value,
    }
    if evidence.local_readability_score is not None:
        payload["localReadabilityScore"] = evidence.local_readability_score
    if evidence.minimum_ocr_confidence is not None:
        payload["minimumOcrConfidence"] = evidence.minimum_ocr_confidence
    if evidence.observation_key is not None:
        payload["observationKey"] = evidence.observation_key
    if evidence.runtime_diagnostics is not None:
        payload["runtimeDiagnostics"] = dict(evidence.runtime_diagnostics)
    return payload


def observation_from_dict(value: dict[str, object]) -> RangeEvidenceResult:
    raw_range = value.get("observedRange")
    try:
        observed_range = (
            None
            if raw_range is None
            else SemiAutomaticSelectionRange(
                start=_as_int(cast(dict[str, object], raw_range)["start"]),
                end=_as_int(cast(dict[str, object], raw_range)["end"]),
            )
        )
        expected_index_raw = value.get("expectedIndex")
        confidence_raw = value.get("confidence")
        readability_raw = value.get("localReadabilityScore")
        minimum_confidence_raw = value.get("minimumOcrConfidence")
        diagnostics_raw = value.get("runtimeDiagnostics")
        if diagnostics_raw is not None and not isinstance(diagnostics_raw, dict):
            raise TypeError("runtime diagnostics")
        return RangeEvidenceResult(
            source=SemiAutomaticSelectionSource(
                source_index=_as_int(value["sourceIndex"]),
                relative_path=str(value["sourceRelativePath"]),
                size_bytes=_as_int(value["sourceSizeBytes"]),
                checksum_sha256=str(value["sourceChecksumSha256"]),
            ),
            status=RangeEvidenceStatus(str(value["status"])),
            observed_range=observed_range,
            expected_index=(None if expected_index_raw is None else _as_int(expected_index_raw)),
            confidence=None if confidence_raw is None else _as_float(confidence_raw),
            reason_codes=tuple(
                str(item) for item in cast(list[object], value.get("reasonCodes", []))
            ),
            local_readability_score=(
                None if readability_raw is None else _as_float(readability_raw)
            ),
            minimum_ocr_confidence=(
                None if minimum_confidence_raw is None else _as_float(minimum_confidence_raw)
            ),
            observation_key=(
                None if value.get("observationKey") is None else str(value["observationKey"])
            ),
            runtime_diagnostics=(
                None if diagnostics_raw is None else cast(dict[str, object], diagnostics_raw)
            ),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise SemiAutomaticSelectionError(
            "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
            "A persisted range observation is invalid.",
        ) from error


def _iter_observations(path: Path) -> Iterator[RangeEvidenceResult]:
    for payload in _iter_json_lines(path):
        yield observation_from_dict(payload)


def _iter_json_lines(path: Path) -> Iterator[dict[str, object]]:
    try:
        with path.open("r", encoding="utf-8") as source:
            for line in source:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise TypeError("JSONL value is not an object")
                yield cast(dict[str, object], value)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError) as error:
        raise SemiAutomaticSelectionError(
            "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
            "The range-selection JSONL diagnostics are invalid.",
        ) from error


def _truncate_to_committed_lines(path: Path, count: int, *, identity_field: str) -> None:
    if count < 0:
        _fail(
            "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
            "A diagnostics checkpoint cannot contain negative counters.",
        )
    if not path.exists():
        if count:
            _fail(
                "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
                "Committed diagnostics disappeared after checkpointing.",
            )
        path.write_bytes(b"")
        return
    committed_offset = 0
    line_count = 0
    try:
        with path.open("r+b") as stream:
            while line_count < count:
                line = stream.readline()
                if not line:
                    raise ValueError("committed JSONL suffix is missing")
                value = json.loads(line)
                if not isinstance(value, dict) or value.get(identity_field) != line_count:
                    raise ValueError("JSONL identities are not contiguous")
                line_count += 1
                committed_offset = stream.tell()
            if stream.read(1):
                stream.truncate(committed_offset)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise SemiAutomaticSelectionError(
            "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
            "Committed JSONL diagnostics do not match the durable checkpoint.",
        ) from error


def _append_json(path: Path, payload: Mapping[str, object]) -> None:
    line = json.dumps(
        dict(payload),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    with path.open("a", encoding="utf-8", newline="\n") as output:
        output.write(f"{line}\n")


def _write_atomic_json(path: Path, payload: Mapping[str, object]) -> None:
    content = json.dumps(dict(payload), ensure_ascii=True, indent=2, sort_keys=True)
    temporary = path.with_name(f".{path.name}.part")
    temporary.write_text(f"{content}\n", encoding="utf-8", newline="\n")
    temporary.replace(path)


def _as_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise TypeError("value is not an integer")
    return int(value)


def _as_float(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise TypeError("value is not numeric")
    return float(value)


def _fail(code: str, message: str) -> NoReturn:
    raise SemiAutomaticSelectionError(code, message)


__all__ = [
    "SEMI_AUTOMATIC_SELECTION_DIAGNOSTIC_CONTRACT",
    "SemiAutomaticSelectionAudit",
    "observation_from_dict",
    "observation_to_dict",
]
