"""Deterministic v7 source occurrences, gaps, cursors and EOF finalization."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import NoReturn, cast

from .contracts import SemiAutomaticSelectionRange
from .v7_range_proof import (
    V7LabelEvidence,
    V7RangeProofKind,
    V7RangeProofResolver,
    V7RangeProofResult,
    V7WeakFrameEvidence,
)

V7_OCCURRENCE_ALGORITHM_VERSION = "v7-occurrence-tracker-v2"
V7_OCCURRENCE_CHECKPOINT_SCHEMA_VERSION = 2
_V7_LEGACY_OCCURRENCE_ALGORITHM_VERSION = "v7-occurrence-tracker-v1"
_V7_LEGACY_OCCURRENCE_CHECKPOINT_SCHEMA_VERSION = 1
V7_WEAK_EVIDENCE_VISUAL_HAMMING_DISTANCE = 4
_OCCURRENCE_ID_PREFIX = "v7-occurrence-"


class V7OccurrenceError(ValueError):
    """A malformed or out-of-order v7 occurrence operation."""


class V7AnalysisPhase(StrEnum):
    RUNNING = "running"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    COMPLETE = "complete"


@dataclass(frozen=True, slots=True)
class V7RunCursors:
    """Worker, sequence and operator-view cursors are deliberately independent."""

    next_source_index: int
    sequence_cursor_index: int
    viewed_source_index: int | None

    def __post_init__(self) -> None:
        if self.next_source_index < 0 or self.sequence_cursor_index < -1:
            _fail("V7_OCCURRENCE_CURSOR_INVALID", "V7 cursors cannot be negative.")
        if self.viewed_source_index is not None and not (
            0 <= self.viewed_source_index < self.next_source_index
        ):
            _fail("V7_OCCURRENCE_CURSOR_INVALID", "The operator view cursor is invalid.")

    def as_dict(self) -> dict[str, object]:
        return {
            "nextSourceIndex": self.next_source_index,
            "sequenceCursorIndex": self.sequence_cursor_index,
            "viewedSourceIndex": self.viewed_source_index,
        }


@dataclass(frozen=True, slots=True)
class V7ProvenSource:
    """One source-local proof retained for later ranking and audit."""

    source_index: int
    source_id: str
    proof_kind: V7RangeProofKind
    supporting_source_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            self.source_index < 0
            or not self.source_id
            or self.proof_kind is V7RangeProofKind.NONE
            or not self.supporting_source_ids
            or self.source_id not in self.supporting_source_ids
        ):
            _fail("V7_OCCURRENCE_PROOF_INVALID", "A proven v7 source is invalid.")
        if self.proof_kind is V7RangeProofKind.STRONG_FIVE_LABEL:
            if self.supporting_source_ids != (self.source_id,):
                _fail("V7_OCCURRENCE_PROOF_INVALID", "A strong v7 proof is invalid.")
            return
        if (
            self.proof_kind is not V7RangeProofKind.MULTI_FRAME_THREE_PLUS_THREE
            or len(self.supporting_source_ids) != 2
            or len(set(self.supporting_source_ids)) != 2
        ):
            _fail("V7_OCCURRENCE_PROOF_INVALID", "A 3+3 v7 proof is invalid.")

    def as_dict(self) -> dict[str, object]:
        return {
            "proofKind": self.proof_kind.value,
            "sourceId": self.source_id,
            "sourceIndex": self.source_index,
            "supportingSourceIds": list(self.supporting_source_ids),
        }

    @classmethod
    def from_dict(cls, value: object) -> V7ProvenSource:
        raw = _mapping(value, "A proven v7 source checkpoint must be an object.")
        try:
            return cls(
                source_index=_int(raw["sourceIndex"]),
                source_id=_string(raw["sourceId"]),
                proof_kind=V7RangeProofKind(_string(raw["proofKind"])),
                supporting_source_ids=_strings(raw["supportingSourceIds"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise V7OccurrenceError("A proven v7 source checkpoint is invalid.") from error


@dataclass(frozen=True, slots=True)
class V7Occurrence:
    """One contiguous occurrence of one expected range in source order."""

    occurrence_id: str
    expected_index: int
    sequence_range: SemiAutomaticSelectionRange
    first_source_index: int
    last_source_index: int
    proven_sources: tuple[V7ProvenSource, ...]

    def __post_init__(self) -> None:
        if (
            _occurrence_number(self.occurrence_id) < 0
            or self.expected_index < 0
            or self.first_source_index < 0
            or self.last_source_index < self.first_source_index
            or not self.proven_sources
        ):
            _fail("V7_OCCURRENCE_INVALID", "A v7 occurrence is invalid.")
        if any(
            not self.first_source_index <= item.source_index <= self.last_source_index
            for item in self.proven_sources
        ):
            _fail("V7_OCCURRENCE_INVALID", "Occurrence proof is outside its source interval.")
        source_indexes = tuple(item.source_index for item in self.proven_sources)
        if source_indexes != tuple(sorted(set(source_indexes))):
            _fail("V7_OCCURRENCE_INVALID", "Occurrence proofs are not in source order.")

    def as_dict(self) -> dict[str, object]:
        return {
            "expectedIndex": self.expected_index,
            "firstSourceIndex": self.first_source_index,
            "lastSourceIndex": self.last_source_index,
            "occurrenceId": self.occurrence_id,
            "provenSources": [item.as_dict() for item in self.proven_sources],
            "rangeEnd": self.sequence_range.end,
            "rangeStart": self.sequence_range.start,
        }

    @classmethod
    def from_dict(cls, value: object) -> V7Occurrence:
        raw = _mapping(value, "A v7 occurrence checkpoint must be an object.")
        try:
            proofs = tuple(V7ProvenSource.from_dict(item) for item in _items(raw["provenSources"]))
            return cls(
                occurrence_id=_string(raw["occurrenceId"]),
                expected_index=_int(raw["expectedIndex"]),
                sequence_range=SemiAutomaticSelectionRange(
                    _int(raw["rangeStart"]), _int(raw["rangeEnd"])
                ),
                first_source_index=_int(raw["firstSourceIndex"]),
                last_source_index=_int(raw["lastSourceIndex"]),
                proven_sources=proofs,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise V7OccurrenceError("A v7 occurrence checkpoint is invalid.") from error


@dataclass(slots=True)
class _OpenOccurrence:
    occurrence_id: str
    expected_index: int
    sequence_range: SemiAutomaticSelectionRange
    first_source_index: int
    last_source_index: int
    proven_sources: list[V7ProvenSource] = field(default_factory=list)

    @classmethod
    def open(
        cls,
        occurrence_id: str,
        expected_index: int,
        sequence_range: SemiAutomaticSelectionRange,
        source: V7ProvenSource,
        *,
        first_source_index: int | None = None,
    ) -> _OpenOccurrence:
        return cls(
            occurrence_id=occurrence_id,
            expected_index=expected_index,
            sequence_range=sequence_range,
            first_source_index=(
                source.source_index if first_source_index is None else first_source_index
            ),
            last_source_index=source.source_index,
            proven_sources=[source],
        )

    @classmethod
    def from_occurrence(cls, occurrence: V7Occurrence) -> _OpenOccurrence:
        return cls(
            occurrence_id=occurrence.occurrence_id,
            expected_index=occurrence.expected_index,
            sequence_range=occurrence.sequence_range,
            first_source_index=occurrence.first_source_index,
            last_source_index=occurrence.last_source_index,
            proven_sources=list(occurrence.proven_sources),
        )

    def append_unproven(self, source_index: int) -> None:
        self.last_source_index = source_index

    def append_proven(self, source: V7ProvenSource) -> None:
        self.last_source_index = source.source_index
        self.proven_sources.append(source)

    def close(self, last_source_index: int | None = None) -> V7Occurrence:
        return V7Occurrence(
            occurrence_id=self.occurrence_id,
            expected_index=self.expected_index,
            sequence_range=self.sequence_range,
            first_source_index=self.first_source_index,
            last_source_index=(
                self.last_source_index if last_source_index is None else last_source_index
            ),
            proven_sources=tuple(self.proven_sources),
        )


@dataclass(frozen=True, slots=True)
class V7OccurrenceObservation:
    """One source in manifest order and its source-local proof result."""

    source_index: int
    source_id: str
    proof: V7RangeProofResult
    weak_evidence: V7WeakFrameEvidence | None = None

    def __post_init__(self) -> None:
        if self.source_index < 0 or not self.source_id:
            _fail("V7_OCCURRENCE_OBSERVATION_INVALID", "A source observation is invalid.")
        if self.weak_evidence is not None and (
            self.weak_evidence.source_id != self.source_id
            or self.proof.kind is not V7RangeProofKind.NONE
        ):
            _fail("V7_OCCURRENCE_OBSERVATION_INVALID", "V7 weak evidence is invalid.")


@dataclass(frozen=True, slots=True)
class _PendingWeakEvidence:
    """One bounded source-local weak hypothesis owned by the tracker."""

    sequence_range: SemiAutomaticSelectionRange
    evidence: V7WeakFrameEvidence

    def as_dict(self) -> dict[str, object]:
        return {
            "labels": [
                {
                    "positionConfidence": item.position_confidence,
                    "positionIndex": item.position_index,
                    "recognitionConfidence": item.recognition_confidence,
                    "sequenceNumber": item.sequence_number,
                }
                for item in self.evidence.labels
            ],
            "rangeEnd": self.sequence_range.end,
            "rangeStart": self.sequence_range.start,
            "sourceId": self.evidence.source_id,
            "visualHash": f"{self.evidence.visual_hash:016x}",
            "visualSignature": self.evidence.visual_signature.hex(),
        }


class V7OccurrenceTracker:
    """Pure state machine: only EOF exposes globally rankable occurrences."""

    def __init__(
        self,
        expected_ranges: tuple[SemiAutomaticSelectionRange, ...],
        *,
        checkpoint: dict[str, object] | None = None,
    ) -> None:
        if not expected_ranges or len(set(expected_ranges)) != len(expected_ranges):
            _fail("V7_OCCURRENCE_CONFIGURATION_INVALID", "Expected v7 ranges must be unique.")
        if any(item.board_count != 9 for item in expected_ranges):
            _fail("V7_OCCURRENCE_CONFIGURATION_INVALID", "V7 occurrences require full 3x3 ranges.")
        self._expected_ranges = expected_ranges
        self._range_indexes = {value: index for index, value in enumerate(expected_ranges)}
        self._proof_resolver = V7RangeProofResolver(expected_ranges)
        self._phase = V7AnalysisPhase.RUNNING
        self._next_source_index = 0
        self._sequence_cursor_index = -1
        self._viewed_source_index: int | None = None
        self._confirmed_indexes: set[int] = set()
        self._unresolved_gap_indexes: set[int] = set()
        self._next_occurrence_number = 0
        self._seen_source_indexes: dict[str, int] = {}
        self._pending_weak: _PendingWeakEvidence | None = None
        self._active: _OpenOccurrence | None = None
        self._finalized: list[V7Occurrence] = []
        if checkpoint is not None:
            self._restore(checkpoint)

    @property
    def phase(self) -> V7AnalysisPhase:
        return self._phase

    @property
    def cursors(self) -> V7RunCursors:
        return V7RunCursors(
            next_source_index=self._next_source_index,
            sequence_cursor_index=self._sequence_cursor_index,
            viewed_source_index=self._viewed_source_index,
        )

    @property
    def unresolved_gap_indexes(self) -> tuple[int, ...]:
        return tuple(sorted(self._unresolved_gap_indexes))

    @property
    def finalized_occurrences(self) -> tuple[V7Occurrence, ...]:
        return tuple(self._finalized)

    def source_index_for(self, source_id: str) -> int | None:
        """Return the pinned manifest position for one already scanned source."""

        return self._seen_source_indexes.get(source_id)

    def set_viewed_source_index(self, source_index: int | None) -> None:
        if source_index is not None and not 0 <= source_index < self._next_source_index:
            _fail("V7_OCCURRENCE_CURSOR_INVALID", "The selected source has not been scanned.")
        self._viewed_source_index = source_index

    def pause(self) -> None:
        self._require_phase(V7AnalysisPhase.RUNNING)
        self._phase = V7AnalysisPhase.PAUSED

    def resume(self) -> None:
        self._require_phase(V7AnalysisPhase.PAUSED)
        self._phase = V7AnalysisPhase.RUNNING

    def cancel(self) -> None:
        if self._phase not in {V7AnalysisPhase.RUNNING, V7AnalysisPhase.PAUSED}:
            _fail("V7_OCCURRENCE_PHASE_INVALID", "Only a nonterminal v7 scan can be cancelled.")
        self._phase = V7AnalysisPhase.CANCELLED

    def consume(self, observation: V7OccurrenceObservation) -> None:
        self._require_phase(V7AnalysisPhase.RUNNING)
        if observation.source_index != self._next_source_index:
            _fail(
                "V7_OCCURRENCE_ORDER_INVALID", "V7 sources must be consumed once in manifest order."
            )
        if observation.source_id in self._seen_source_indexes:
            _fail("V7_OCCURRENCE_ORDER_INVALID", "A v7 source ID cannot occur twice.")
        effective_proof = self._effective_proof(observation)
        effective_observation = V7OccurrenceObservation(
            source_index=observation.source_index,
            source_id=observation.source_id,
            proof=effective_proof,
        )
        if effective_proof.kind is V7RangeProofKind.NONE:
            if effective_proof.sequence_range is not None or effective_proof.supporting_source_ids:
                _fail("V7_OCCURRENCE_PROOF_INVALID", "A no-proof observation has proof payload.")
            self._next_source_index += 1
            self._seen_source_indexes[observation.source_id] = observation.source_index
            if self._active is not None:
                self._active.append_unproven(observation.source_index)
            return
        sequence_range = effective_proof.sequence_range
        if (
            sequence_range is None
            or sequence_range not in self._range_indexes
            or not effective_proof.supporting_source_ids
            or observation.source_id not in effective_proof.supporting_source_ids
        ):
            _fail("V7_OCCURRENCE_PROOF_INVALID", "A v7 proof is not valid for this run.")
        expected_index = self._range_indexes[sequence_range]
        source = V7ProvenSource(
            source_index=observation.source_index,
            source_id=observation.source_id,
            proof_kind=effective_proof.kind,
            supporting_source_ids=effective_proof.supporting_source_ids,
        )
        first_source_index = self._validate_proof_support(
            effective_observation, expected_index, source.proof_kind
        )
        self._pending_weak = None
        self._next_source_index += 1
        self._seen_source_indexes[observation.source_id] = observation.source_index
        self._confirm(expected_index)
        if self._active is not None and self._active.expected_index == expected_index:
            self._active.append_proven(source)
            return
        if self._active is not None:
            self._finalized.append(self._active.close(first_source_index - 1))
        self._active = _OpenOccurrence.open(
            self._allocate_occurrence_id(),
            expected_index,
            sequence_range,
            source,
            first_source_index=first_source_index,
        )

    def _effective_proof(self, observation: V7OccurrenceObservation) -> V7RangeProofResult:
        """Resolve only a valid 3+3 pair; all other weak input remains unproven."""

        if observation.proof.kind is not V7RangeProofKind.NONE:
            return observation.proof
        evidence = observation.weak_evidence
        if evidence is None:
            return observation.proof
        current_hypotheses = self._proof_resolver.weak_hypotheses(
            evidence.as_frame(
                occurrence_id="v7-occurrence-pending",
                visual_cluster_id=f"v7-visual-{evidence.visual_hash:016x}",
            )
        )
        if len(current_hypotheses) != 1:
            return observation.proof
        sequence_range = current_hypotheses[0].sequence_range
        previous = self._pending_weak
        if previous is None or previous.sequence_range != sequence_range:
            self._pending_weak = _PendingWeakEvidence(sequence_range, evidence)
            return observation.proof
        first = previous.evidence.as_frame(
            occurrence_id="v7-occurrence-pending",
            visual_cluster_id=_visual_cluster_id(previous.evidence, evidence),
        )
        second = evidence.as_frame(
            occurrence_id="v7-occurrence-pending",
            visual_cluster_id=_visual_cluster_id(evidence, previous.evidence),
        )
        proof = self._proof_resolver.resolve_pair(first, second)
        if proof.kind is V7RangeProofKind.MULTI_FRAME_THREE_PLUS_THREE:
            self._pending_weak = None
        return proof

    def finish(self) -> tuple[V7Occurrence, ...]:
        """Finalize at EOF once; repeated calls return the same immutable result."""

        if self._phase is V7AnalysisPhase.COMPLETE:
            return self.finalized_occurrences
        self._require_phase(V7AnalysisPhase.RUNNING)
        if self._active is not None:
            self._finalized.append(self._active.close())
            self._active = None
        self._pending_weak = None
        self._phase = V7AnalysisPhase.COMPLETE
        return self.finalized_occurrences

    def global_occurrences(self) -> tuple[V7Occurrence, ...]:
        if self._phase is not V7AnalysisPhase.COMPLETE:
            _fail(
                "V7_OCCURRENCE_FINALIZATION_REQUIRED",
                "V7 global ranking requires EOF finalization.",
            )
        return self.finalized_occurrences

    def checkpoint(self) -> dict[str, object]:
        return {
            "activeOccurrence": None if self._active is None else self._active.close().as_dict(),
            "algorithmVersion": V7_OCCURRENCE_ALGORITHM_VERSION,
            "confirmedExpectedIndexes": sorted(self._confirmed_indexes),
            "cursors": self.cursors.as_dict(),
            "expectedRanges": [[item.start, item.end] for item in self._expected_ranges],
            "finalizedOccurrences": [item.as_dict() for item in self._finalized],
            "nextOccurrenceNumber": self._next_occurrence_number,
            "pendingWeakEvidence": (
                None if self._pending_weak is None else self._pending_weak.as_dict()
            ),
            "phase": self._phase.value,
            "schemaVersion": V7_OCCURRENCE_CHECKPOINT_SCHEMA_VERSION,
            "seenSources": [
                {"sourceId": source_id, "sourceIndex": source_index}
                for source_id, source_index in sorted(
                    self._seen_source_indexes.items(), key=lambda item: item[1]
                )
            ],
            "unresolvedGapIndexes": list(self.unresolved_gap_indexes),
        }

    def _confirm(self, expected_index: int) -> None:
        self._confirmed_indexes.add(expected_index)
        self._sequence_cursor_index = max(self._sequence_cursor_index, expected_index)
        self._unresolved_gap_indexes = {
            index
            for index in range(self._sequence_cursor_index + 1)
            if index not in self._confirmed_indexes
        }

    def _allocate_occurrence_id(self) -> str:
        occurrence_id = f"{_OCCURRENCE_ID_PREFIX}{self._next_occurrence_number:08d}"
        self._next_occurrence_number += 1
        return occurrence_id

    def _validate_proof_support(
        self,
        observation: V7OccurrenceObservation,
        expected_index: int,
        proof_kind: V7RangeProofKind,
    ) -> int:
        supporting_source_ids = observation.proof.supporting_source_ids
        if proof_kind is V7RangeProofKind.STRONG_FIVE_LABEL:
            if supporting_source_ids != (observation.source_id,):
                _fail("V7_OCCURRENCE_PROOF_INVALID", "A strong proof must support itself only.")
            return observation.source_index
        if proof_kind is not V7RangeProofKind.MULTI_FRAME_THREE_PLUS_THREE:
            _fail("V7_OCCURRENCE_PROOF_INVALID", "V7 proof kind is unsupported.")
        if len(supporting_source_ids) != 2 or len(set(supporting_source_ids)) != 2:
            _fail("V7_OCCURRENCE_PROOF_INVALID", "A 3+3 proof requires two unique sources.")
        support_indexes: list[int] = []
        for source_id in supporting_source_ids:
            if source_id == observation.source_id:
                support_indexes.append(observation.source_index)
                continue
            source_index = self._seen_source_indexes.get(source_id)
            if source_index is None:
                _fail("V7_OCCURRENCE_PROOF_INVALID", "A 3+3 support source was not scanned.")
            support_indexes.append(source_index)
        if max(support_indexes) != observation.source_index:
            _fail(
                "V7_OCCURRENCE_PROOF_INVALID", "A 3+3 proof is not attached to its latest source."
            )
        if self._active is not None:
            if self._active.expected_index == expected_index:
                crosses_boundary = min(support_indexes) < self._active.first_source_index
            else:
                last_proven_source_index = self._active.proven_sources[-1].source_index
                crosses_boundary = min(support_indexes) <= last_proven_source_index
            if crosses_boundary:
                _fail(
                    "V7_OCCURRENCE_PROOF_INVALID",
                    "A 3+3 proof crosses a confirmed v7 occurrence boundary.",
                )
        return min(support_indexes)

    def _require_phase(self, expected: V7AnalysisPhase) -> None:
        if self._phase is not expected:
            _fail(
                "V7_OCCURRENCE_PHASE_INVALID",
                f"V7 operation requires {expected.value}, received {self._phase.value}.",
            )

    def _restore(self, checkpoint: dict[str, object]) -> None:
        try:
            contract = (checkpoint.get("algorithmVersion"), checkpoint.get("schemaVersion"))
            if (
                contract
                not in {
                    (V7_OCCURRENCE_ALGORITHM_VERSION, V7_OCCURRENCE_CHECKPOINT_SCHEMA_VERSION),
                    (
                        _V7_LEGACY_OCCURRENCE_ALGORITHM_VERSION,
                        _V7_LEGACY_OCCURRENCE_CHECKPOINT_SCHEMA_VERSION,
                    ),
                }
                or _ranges(checkpoint.get("expectedRanges")) != self._expected_ranges
            ):
                raise ValueError("checkpoint contract mismatch")
            raw_cursors = _mapping(
                checkpoint["cursors"], "V7 checkpoint cursors must be an object."
            )
            cursors = V7RunCursors(
                next_source_index=_int(raw_cursors["nextSourceIndex"]),
                sequence_cursor_index=_int(raw_cursors["sequenceCursorIndex"]),
                viewed_source_index=_optional_int(raw_cursors.get("viewedSourceIndex")),
            )
            phase = V7AnalysisPhase(_string(checkpoint["phase"]))
            confirmed = set(
                _indexes(checkpoint["confirmedExpectedIndexes"], len(self._expected_ranges))
            )
            unresolved = set(
                _indexes(checkpoint["unresolvedGapIndexes"], len(self._expected_ranges))
            )
            finalized = [
                V7Occurrence.from_dict(item) for item in _items(checkpoint["finalizedOccurrences"])
            ]
            active_raw = checkpoint.get("activeOccurrence")
            active = (
                None
                if active_raw is None
                else _OpenOccurrence.from_occurrence(V7Occurrence.from_dict(active_raw))
            )
            next_occurrence_number = _int(checkpoint["nextOccurrenceNumber"])
            seen_source_indexes = _seen_source_indexes(
                checkpoint["seenSources"], cursors.next_source_index
            )
            if contract == (
                _V7_LEGACY_OCCURRENCE_ALGORITHM_VERSION,
                _V7_LEGACY_OCCURRENCE_CHECKPOINT_SCHEMA_VERSION,
            ):
                pending_weak = None
            else:
                pending_weak = _pending_weak_from_dict(checkpoint["pendingWeakEvidence"])
        except (KeyError, TypeError, ValueError) as error:
            raise V7OccurrenceError("The v7 occurrence checkpoint is invalid.") from error
        if next_occurrence_number < 0:
            _fail("V7_OCCURRENCE_CHECKPOINT_INVALID", "V7 occurrence counter is invalid.")
        occurrences = [*finalized, *(() if active is None else (active.close(),))]
        occurrence_numbers = tuple(_occurrence_number(item.occurrence_id) for item in occurrences)
        if (
            occurrence_numbers != tuple(sorted(occurrence_numbers))
            or len(set(occurrence_numbers)) != len(occurrence_numbers)
            or next_occurrence_number != (max(occurrence_numbers, default=-1) + 1)
        ):
            _fail("V7_OCCURRENCE_CHECKPOINT_INVALID", "V7 occurrence identity can be repeated.")
        if any(
            occurrence.expected_index >= len(self._expected_ranges)
            or occurrence.sequence_range != self._expected_ranges[occurrence.expected_index]
            or occurrence.last_source_index >= cursors.next_source_index
            for occurrence in finalized
        ):
            _fail("V7_OCCURRENCE_CHECKPOINT_INVALID", "Finalized v7 occurrence is invalid.")
        if active is not None and (
            active.expected_index >= len(self._expected_ranges)
            or active.sequence_range != self._expected_ranges[active.expected_index]
            or active.last_source_index >= cursors.next_source_index
            or active.last_source_index != cursors.next_source_index - 1
        ):
            _fail("V7_OCCURRENCE_CHECKPOINT_INVALID", "Active v7 occurrence is invalid.")
        previous_last_source_index = -1
        for occurrence in occurrences:
            if occurrence.first_source_index <= previous_last_source_index:
                _fail("V7_OCCURRENCE_CHECKPOINT_INVALID", "V7 occurrences overlap.")
            previous_last_source_index = occurrence.last_source_index
            for source in occurrence.proven_sources:
                if seen_source_indexes.get(source.source_id) != source.source_index:
                    _fail(
                        "V7_OCCURRENCE_CHECKPOINT_INVALID",
                        "V7 proof source does not match its source cursor.",
                    )
                if any(
                    support_id not in seen_source_indexes
                    or not occurrence.first_source_index
                    <= seen_source_indexes[support_id]
                    <= occurrence.last_source_index
                    for support_id in source.supporting_source_ids
                ):
                    _fail(
                        "V7_OCCURRENCE_CHECKPOINT_INVALID",
                        "V7 proof support crosses an occurrence boundary.",
                    )
        if confirmed != {occurrence.expected_index for occurrence in occurrences}:
            _fail(
                "V7_OCCURRENCE_CHECKPOINT_INVALID",
                "V7 confirmed ranges do not match occurrence proof.",
            )
        expected_sequence_cursor = max(confirmed, default=-1)
        if cursors.sequence_cursor_index != expected_sequence_cursor:
            _fail("V7_OCCURRENCE_CHECKPOINT_INVALID", "V7 sequence cursor does not match proof.")
        expected_gaps = {
            index for index in range(cursors.sequence_cursor_index + 1) if index not in confirmed
        }
        if unresolved != expected_gaps:
            _fail("V7_OCCURRENCE_CHECKPOINT_INVALID", "V7 gap state does not match its cursor.")
        if phase is V7AnalysisPhase.COMPLETE and active is not None:
            _fail("V7_OCCURRENCE_CHECKPOINT_INVALID", "Completed v7 scan has an active occurrence.")
        if pending_weak is not None and (
            phase is V7AnalysisPhase.COMPLETE
            or pending_weak.sequence_range not in self._range_indexes
            or pending_weak.evidence.source_id not in seen_source_indexes
        ):
            _fail("V7_OCCURRENCE_CHECKPOINT_INVALID", "V7 pending weak evidence is invalid.")
        if pending_weak is not None:
            hypotheses = self._proof_resolver.weak_hypotheses(
                pending_weak.evidence.as_frame(
                    occurrence_id="v7-occurrence-pending",
                    visual_cluster_id=f"v7-visual-{pending_weak.evidence.visual_hash:016x}",
                )
            )
            if len(hypotheses) != 1 or hypotheses[0].sequence_range != pending_weak.sequence_range:
                _fail("V7_OCCURRENCE_CHECKPOINT_INVALID", "V7 pending weak evidence is invalid.")
        if (
            phase in {V7AnalysisPhase.RUNNING, V7AnalysisPhase.PAUSED, V7AnalysisPhase.CANCELLED}
            and confirmed
            and active is None
        ):
            _fail(
                "V7_OCCURRENCE_CHECKPOINT_INVALID",
                "An unfinished v7 scan lost its active occurrence.",
            )
        self._phase = phase
        self._next_source_index = cursors.next_source_index
        self._sequence_cursor_index = cursors.sequence_cursor_index
        self._viewed_source_index = cursors.viewed_source_index
        self._confirmed_indexes = confirmed
        self._unresolved_gap_indexes = unresolved
        self._next_occurrence_number = next_occurrence_number
        self._seen_source_indexes = seen_source_indexes
        self._pending_weak = pending_weak
        self._active = active
        self._finalized = finalized


def _pending_weak_from_dict(value: object) -> _PendingWeakEvidence | None:
    if value is None:
        return None
    try:
        raw = _mapping(value, "V7 pending weak evidence must be an object.")
        visual_hash = raw["visualHash"]
        visual_signature = raw["visualSignature"]
        if (
            not isinstance(visual_hash, str)
            or len(visual_hash) != 16
            or any(character not in "0123456789abcdef" for character in visual_hash)
            or not isinstance(visual_signature, str)
            or len(visual_signature) != 128
            or any(character not in "0123456789abcdef" for character in visual_signature)
        ):
            raise ValueError("visual hash")
        labels = tuple(
            V7LabelEvidence(
                position_index=_int(_mapping(item, "V7 weak label is invalid.")["positionIndex"]),
                sequence_number=_int(_mapping(item, "V7 weak label is invalid.")["sequenceNumber"]),
                recognition_confidence=_number(
                    _mapping(item, "V7 weak label is invalid.")["recognitionConfidence"]
                ),
                position_confidence=_number(
                    _mapping(item, "V7 weak label is invalid.")["positionConfidence"]
                ),
            )
            for item in _items(raw["labels"])
        )
        return _PendingWeakEvidence(
            sequence_range=SemiAutomaticSelectionRange(
                _int(raw["rangeStart"]), _int(raw["rangeEnd"])
            ),
            evidence=V7WeakFrameEvidence(
                source_id=_string(raw["sourceId"]),
                labels=labels,
                visual_hash=int(visual_hash, 16),
                visual_signature=bytes.fromhex(visual_signature),
            ),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise V7OccurrenceError("V7 pending weak evidence is invalid.") from error


def _visual_cluster_id(first: V7WeakFrameEvidence, second: V7WeakFrameEvidence) -> str:
    """Give visually dependent sources the same cluster without storing images."""

    if first.visual_signature == second.visual_signature or (
        (first.visual_hash ^ second.visual_hash).bit_count()
        <= V7_WEAK_EVIDENCE_VISUAL_HAMMING_DISTANCE
    ):
        return "v7-visual-dependent"
    return f"v7-visual-{first.visual_hash:016x}"


def _mapping(value: object, message: str) -> dict[str, object]:
    if not isinstance(value, dict):
        _fail("V7_OCCURRENCE_CHECKPOINT_INVALID", message)
    return cast(dict[str, object], value)


def _items(value: object) -> list[object]:
    if not isinstance(value, list):
        _fail("V7_OCCURRENCE_CHECKPOINT_INVALID", "V7 checkpoint list is invalid.")
    return value


def _strings(value: object) -> tuple[str, ...]:
    values = tuple(_string(item) for item in _items(value))
    if not values:
        _fail("V7_OCCURRENCE_CHECKPOINT_INVALID", "V7 support IDs are missing.")
    return values


def _indexes(value: object, expected_count: int) -> tuple[int, ...]:
    values = tuple(_int(item) for item in _items(value))
    if len(set(values)) != len(values) or any(not 0 <= item < expected_count for item in values):
        _fail("V7_OCCURRENCE_CHECKPOINT_INVALID", "V7 range index is invalid.")
    return values


def _seen_source_indexes(value: object, next_source_index: int) -> dict[str, int]:
    result: dict[str, int] = {}
    indexes: set[int] = set()
    for item in _items(value):
        raw = _mapping(item, "V7 seen-source checkpoint must be an object.")
        source_id = _string(raw.get("sourceId"))
        source_index = _int(raw.get("sourceIndex"))
        if source_id in result or source_index in indexes:
            _fail("V7_OCCURRENCE_CHECKPOINT_INVALID", "V7 seen source is duplicated.")
        result[source_id] = source_index
        indexes.add(source_index)
    if indexes != set(range(next_source_index)):
        _fail("V7_OCCURRENCE_CHECKPOINT_INVALID", "V7 seen sources do not match scan cursor.")
    return result


def _ranges(value: object) -> tuple[SemiAutomaticSelectionRange, ...]:
    result: list[SemiAutomaticSelectionRange] = []
    for item in _items(value):
        if not isinstance(item, list) or len(item) != 2:
            _fail("V7_OCCURRENCE_CHECKPOINT_INVALID", "V7 expected range is invalid.")
        result.append(SemiAutomaticSelectionRange(_int(item[0]), _int(item[1])))
    return tuple(result)


def _string(value: object) -> str:
    if not isinstance(value, str) or not value:
        _fail("V7_OCCURRENCE_CHECKPOINT_INVALID", "V7 checkpoint string is invalid.")
    return value


def _int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail("V7_OCCURRENCE_CHECKPOINT_INVALID", "V7 checkpoint integer is invalid.")
    return value


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        _fail("V7_OCCURRENCE_CHECKPOINT_INVALID", "V7 checkpoint number is invalid.")
    return float(value)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return _int(value)


def _occurrence_number(occurrence_id: str) -> int:
    if not occurrence_id.startswith(_OCCURRENCE_ID_PREFIX):
        return -1
    suffix = occurrence_id.removeprefix(_OCCURRENCE_ID_PREFIX)
    if len(suffix) != 8 or not suffix.isdecimal():
        return -1
    return int(suffix)


def _fail(code: str, message: str) -> NoReturn:
    del code
    raise V7OccurrenceError(message)
