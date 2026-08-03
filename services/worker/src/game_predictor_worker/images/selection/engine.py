"""Deterministic streaming state machine for representative image selection."""

from __future__ import annotations

import hashlib
import statistics
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field, replace

from .contracts import (
    CandidateDecision,
    CandidateResult,
    CandidateVerification,
    CandidateVerifier,
    CheapImageAnalyzer,
    CheapImageObservation,
    ImageSelectionResult,
    ImageSelectionSource,
    NullSelectionAuditSink,
    SelectionAuditSink,
    SelectionContractError,
    SelectionGroupResult,
    SelectionGroupStatus,
    SelectorCheckpoint,
    SequenceRange,
)
from .manifest import DEFAULT_SELECTOR_MANIFEST, SelectorManifest


def fingerprint_distance(first: str, second: str) -> float:
    """Return normalized Hamming distance for same-sized hexadecimal hashes."""

    if len(first) != len(second):
        return 1.0
    different_bits = (int(first, 16) ^ int(second, 16)).bit_count()
    return different_bits / (len(first) * 4)


def geometry_distance(first: tuple[float, ...], second: tuple[float, ...]) -> float:
    if not first or not second or len(first) != len(second):
        return 1.0
    return min(
        1.0,
        statistics.fmean(abs(left - right) for left, right in zip(first, second, strict=True)),
    )


@dataclass(slots=True)
class _OpenGroup:
    group_order: int
    top_k: int
    source_count: int = 0
    top_observations: list[CheapImageObservation] = field(default_factory=list)
    board_counts: Counter[int] = field(default_factory=Counter)
    reference: CheapImageObservation | None = None

    def add(self, observation: CheapImageObservation) -> None:
        self.source_count += 1
        if observation.board_count is not None:
            self.board_counts[observation.board_count] += 1
        self.top_observations.append(observation)
        self.top_observations.sort(key=_observation_rank)
        del self.top_observations[self.top_k :]
        if self.reference is None or _observation_rank(observation) < _observation_rank(
            self.reference
        ):
            self.reference = observation

    @property
    def board_count_consensus(self) -> int | None:
        if not self.board_counts:
            return None
        return min(
            self.board_counts,
            key=lambda value: (-self.board_counts[value], -value),
        )


def _observation_rank(observation: CheapImageObservation) -> tuple[float, int, str]:
    return (
        -observation.quality.overall_score,
        observation.source.order_index,
        observation.source.checksum_sha256,
    )


def _candidate_rank(candidate: CandidateResult) -> tuple[float, float, int, str]:
    confidence = (
        0.0 if candidate.recognized_range is None else candidate.recognized_range.confidence
    )
    return (
        -candidate.quality.overall_score,
        -confidence,
        candidate.source.order_index,
        candidate.source.checksum_sha256,
    )


class FastImageSelector:
    """Group a natural-order stream and verify only the best candidates."""

    def __init__(self, manifest: SelectorManifest = DEFAULT_SELECTOR_MANIFEST) -> None:
        self.manifest = manifest

    def select(
        self,
        sources: Iterable[ImageSelectionSource],
        *,
        analyzer: CheapImageAnalyzer,
        verifier: CandidateVerifier,
        audit_sink: SelectionAuditSink | None = None,
    ) -> ImageSelectionResult:
        ordered_sources = tuple(sources)
        self._validate_source_order(ordered_sources)
        sink = audit_sink or NullSelectionAuditSink()
        groups: list[SelectionGroupResult] = []
        completed_ranges: dict[tuple[int, int], int] = {}
        unresolved_ranges: dict[tuple[int, int], int] = {}
        unresolved_fingerprints: dict[int, str] = {}
        current: _OpenGroup | None = None
        pending: list[CheapImageObservation] = []
        processed_count = 0
        scan_failure_count = 0
        verification_count = 0

        def ingest(group: _OpenGroup, observation: CheapImageObservation) -> None:
            nonlocal scan_failure_count
            group.add(observation)
            if any(code.startswith("IMAGE_SELECTION_SCAN_") for code in observation.reason_codes):
                scan_failure_count += 1
            sink.candidate_scanned(observation, group_order=group.group_order)

        def finalize(group: _OpenGroup) -> None:
            nonlocal verification_count
            result, count = self._finalize_group(
                group,
                verifier=verifier,
                existing_groups=groups,
                completed_ranges=completed_ranges,
                unresolved_ranges=unresolved_ranges,
                unresolved_fingerprints=unresolved_fingerprints,
            )
            verification_count += count
            if result.status is SelectionGroupStatus.AUTO_SELECTED and result.range is not None:
                completed_ranges[(result.range.start, result.range.end)] = result.group_order
            elif result.status is SelectionGroupStatus.MANUAL_REQUIRED:
                if result.range is not None:
                    unresolved_ranges[(result.range.start, result.range.end)] = result.group_order
                if group.reference is not None:
                    unresolved_fingerprints[result.group_order] = group.reference.fingerprint_hex
            groups.append(result)
            sink.group_finalized(result)

        for source in ordered_sources:
            observation = analyzer.analyze(source)
            processed_count += 1
            if current is None:
                current = _OpenGroup(group_order=0, top_k=self.manifest.top_k)
                ingest(current, observation)
            elif pending:
                if self._pending_matches(pending[0], observation):
                    pending.append(observation)
                    if len(pending) >= self.manifest.boundary_confirmation_count:
                        finalize(current)
                        current = _OpenGroup(
                            group_order=len(groups),
                            top_k=self.manifest.top_k,
                        )
                        for item in pending:
                            ingest(current, item)
                        pending.clear()
                else:
                    finalize(current)
                    current = _OpenGroup(
                        group_order=len(groups),
                        top_k=self.manifest.top_k,
                    )
                    for item in pending:
                        ingest(current, item)
                    pending.clear()
                    finalize(current)
                    current = _OpenGroup(
                        group_order=len(groups),
                        top_k=self.manifest.top_k,
                    )
                    ingest(current, observation)
            elif self._is_boundary_candidate(current, observation):
                pending.append(observation)
            else:
                ingest(current, observation)

            if processed_count % self.manifest.scan_batch_size == 0:
                sink.checkpoint_saved(
                    self._checkpoint(
                        processed_count=processed_count,
                        finalized_group_count=len(groups),
                    )
                )

        if current is not None:
            if pending:
                finalize(current)
                current = _OpenGroup(
                    group_order=len(groups),
                    top_k=self.manifest.top_k,
                )
                for observation in pending:
                    ingest(current, observation)
            finalize(current)
        checkpoint = self._checkpoint(
            processed_count=processed_count,
            finalized_group_count=len(groups),
        )
        sink.checkpoint_saved(checkpoint)
        return ImageSelectionResult(
            selector_version=self.manifest.algorithm_version,
            selector_fingerprint=self.manifest.fingerprint,
            input_count=len(ordered_sources),
            groups=tuple(groups),
            checkpoint=checkpoint,
            scan_failure_count=scan_failure_count,
            verification_count=verification_count,
        )

    def _is_boundary_candidate(
        self,
        current: _OpenGroup,
        observation: CheapImageObservation,
    ) -> bool:
        reference = current.reference
        if reference is None:
            return False
        threshold = self.manifest.thresholds
        if (
            reference.geometry_confidence < threshold.minimum_geometry_confidence
            or observation.geometry_confidence < threshold.minimum_geometry_confidence
        ):
            return False
        visual_distance = fingerprint_distance(
            reference.fingerprint_hex,
            observation.fingerprint_hex,
        )
        if visual_distance < threshold.fingerprint_change_distance:
            return False
        lattice_distance = geometry_distance(
            reference.geometry_signature,
            observation.geometry_signature,
        )
        return (
            visual_distance >= threshold.strong_fingerprint_change_distance
            or lattice_distance >= threshold.geometry_change_distance
            or self.manifest.boundary_confirmation_count > 1
        )

    def _pending_matches(
        self,
        first: CheapImageObservation,
        next_observation: CheapImageObservation,
    ) -> bool:
        return (
            fingerprint_distance(first.fingerprint_hex, next_observation.fingerprint_hex)
            <= self.manifest.thresholds.same_group_fingerprint_distance
        )

    def _finalize_group(
        self,
        group: _OpenGroup,
        *,
        verifier: CandidateVerifier,
        existing_groups: list[SelectionGroupResult],
        completed_ranges: dict[tuple[int, int], int],
        unresolved_ranges: dict[tuple[int, int], int],
        unresolved_fingerprints: dict[int, str],
    ) -> tuple[SelectionGroupResult, int]:
        if group.reference is None:
            raise SelectionContractError(
                "IMAGE_SELECTION_GROUP_EMPTY",
                "An image-selection group cannot be finalized without a source.",
            )
        consensus = group.board_count_consensus
        verified = [
            (observation, verifier.verify(observation, expected_board_count=consensus))
            for observation in group.top_observations
        ]
        range_keys = {
            (verification.recognized_range.start, verification.recognized_range.end)
            for _, verification in verified
            if verification.recognized_range is not None
            and verification.recognized_range.confidence
            >= self.manifest.thresholds.minimum_range_confidence
        }
        range_conflict = len(range_keys) > 1
        candidates = tuple(
            sorted(
                (
                    self._candidate_result(
                        observation,
                        verification,
                        board_count_consensus=consensus,
                        range_conflict=range_conflict,
                    )
                    for observation, verification in verified
                ),
                key=_candidate_rank,
            )
        )
        eligible = [
            candidate
            for candidate in candidates
            if candidate.decision is CandidateDecision.ELIGIBLE
        ]
        selected = (
            None
            if not eligible
            else replace(eligible[0], decision=CandidateDecision.SELECTED_AUTOMATIC)
        )
        recognized_range = self._group_range(candidates)
        fingerprint_sha256 = hashlib.sha256(
            bytes.fromhex(group.reference.fingerprint_hex)
        ).hexdigest()

        if selected is not None and selected.recognized_range is not None:
            selected_range = selected.recognized_range
            range_key = (selected_range.start, selected_range.end)
            if range_key in completed_ranges:
                return (
                    SelectionGroupResult(
                        group_order=group.group_order,
                        source_count=group.source_count,
                        range=selected_range,
                        fingerprint_sha256=fingerprint_sha256,
                        board_count_consensus=consensus,
                        status=SelectionGroupStatus.SKIPPED_EXISTING_RANGE,
                        selected_candidate=None,
                        top_candidates=candidates,
                        duplicate_of_group_order=completed_ranges[range_key],
                    ),
                    len(verified),
                )
            unresolved_order = unresolved_ranges.get(range_key)
            if unresolved_order is None:
                unresolved_order = self._matching_unresolved_fingerprint(
                    group.reference.fingerprint_hex,
                    unresolved_fingerprints,
                )
            if unresolved_order is not None:
                previous = existing_groups[unresolved_order]
                combined = tuple(
                    sorted((*previous.top_candidates, *candidates), key=_candidate_rank)[
                        : self.manifest.top_k
                    ]
                )
                existing_groups[unresolved_order] = replace(
                    previous,
                    source_count=previous.source_count + group.source_count,
                    range=selected_range,
                    board_count_consensus=consensus or previous.board_count_consensus,
                    status=SelectionGroupStatus.AUTO_SELECTED,
                    selected_candidate=selected,
                    top_candidates=combined,
                )
                completed_ranges[range_key] = unresolved_order
                unresolved_ranges.pop(range_key, None)
                unresolved_fingerprints.pop(unresolved_order, None)
                return (
                    SelectionGroupResult(
                        group_order=group.group_order,
                        source_count=group.source_count,
                        range=selected_range,
                        fingerprint_sha256=fingerprint_sha256,
                        board_count_consensus=consensus,
                        status=SelectionGroupStatus.SKIPPED_EXISTING_RANGE,
                        selected_candidate=None,
                        top_candidates=candidates,
                        duplicate_of_group_order=unresolved_order,
                    ),
                    len(verified),
                )
            return (
                SelectionGroupResult(
                    group_order=group.group_order,
                    source_count=group.source_count,
                    range=selected_range,
                    fingerprint_sha256=fingerprint_sha256,
                    board_count_consensus=consensus,
                    status=SelectionGroupStatus.AUTO_SELECTED,
                    selected_candidate=selected,
                    top_candidates=candidates,
                ),
                len(verified),
            )

        return (
            SelectionGroupResult(
                group_order=group.group_order,
                source_count=group.source_count,
                range=recognized_range,
                fingerprint_sha256=fingerprint_sha256,
                board_count_consensus=consensus,
                status=SelectionGroupStatus.MANUAL_REQUIRED,
                selected_candidate=None,
                top_candidates=candidates,
            ),
            len(verified),
        )

    def _candidate_result(
        self,
        observation: CheapImageObservation,
        verification: CandidateVerification,
        *,
        board_count_consensus: int | None,
        range_conflict: bool,
    ) -> CandidateResult:
        reasons = list(observation.reason_codes)
        reasons.extend(verification.reason_codes)
        threshold = self.manifest.thresholds
        quality = observation.quality
        if quality.overall_score < threshold.minimum_quality_score:
            reasons.append("QUALITY_SCORE_LOW")
        if quality.sharpness < threshold.minimum_sharpness:
            reasons.append("QUALITY_BLUR")
        if quality.exposure < threshold.minimum_exposure:
            reasons.append("QUALITY_EXPOSURE")
        if quality.highlight_retention < threshold.minimum_highlight_retention:
            reasons.append("QUALITY_HIGHLIGHT_CLIPPING")
        if quality.glare_resistance < threshold.minimum_glare_resistance:
            reasons.append("QUALITY_GLARE")
        if quality.border_margin < threshold.minimum_border_margin:
            reasons.append("QUALITY_FRAME_CROPPED")
        if observation.geometry_confidence < threshold.minimum_geometry_confidence:
            reasons.append("GEOMETRY_CONFIDENCE_LOW")
        if not verification.geometry_complete:
            reasons.append("GEOMETRY_INCOMPLETE")
        if not verification.full_frame_visible:
            reasons.append("FRAME_NOT_FULLY_VISIBLE")
        if board_count_consensus is None or verification.board_count != board_count_consensus:
            reasons.append("BOARD_COUNT_CONSENSUS_MISMATCH")
        recognized_range = verification.recognized_range
        if recognized_range is None:
            reasons.append("RANGE_UNKNOWN")
        elif recognized_range.confidence < threshold.minimum_range_confidence:
            reasons.append("RANGE_CONFIDENCE_LOW")
        elif recognized_range.board_count != verification.board_count:
            reasons.append("RANGE_BOARD_COUNT_MISMATCH")
        if range_conflict:
            reasons.append("RANGE_CONFLICT")
        unique_reasons = tuple(dict.fromkeys(reasons))
        return CandidateResult(
            source=observation.source,
            decision=(
                CandidateDecision.ELIGIBLE if not unique_reasons else CandidateDecision.REJECTED
            ),
            quality=quality,
            recognized_range=recognized_range,
            reason_codes=unique_reasons,
        )

    def _group_range(self, candidates: tuple[CandidateResult, ...]) -> SequenceRange | None:
        ranges = {
            (candidate.recognized_range.start, candidate.recognized_range.end)
            for candidate in candidates
            if candidate.recognized_range is not None
            and candidate.recognized_range.confidence
            >= self.manifest.thresholds.minimum_range_confidence
        }
        if len(ranges) != 1:
            return None
        start, end = next(iter(ranges))
        confidence = max(
            candidate.recognized_range.confidence
            for candidate in candidates
            if candidate.recognized_range is not None
            and (candidate.recognized_range.start, candidate.recognized_range.end) == (start, end)
        )
        return SequenceRange(start=start, end=end, confidence=confidence)

    def _matching_unresolved_fingerprint(
        self,
        fingerprint_hex: str,
        unresolved_fingerprints: dict[int, str],
    ) -> int | None:
        matches = [
            group_order
            for group_order, candidate in unresolved_fingerprints.items()
            if fingerprint_distance(fingerprint_hex, candidate)
            <= self.manifest.thresholds.duplicate_fingerprint_distance
        ]
        return min(matches) if matches else None

    def _checkpoint(
        self,
        *,
        processed_count: int,
        finalized_group_count: int,
    ) -> SelectorCheckpoint:
        return SelectorCheckpoint(
            schema_version=1,
            selector_fingerprint=self.manifest.fingerprint,
            next_order_index=processed_count,
            processed_count=processed_count,
            finalized_group_count=finalized_group_count,
        )

    @staticmethod
    def _validate_source_order(sources: tuple[ImageSelectionSource, ...]) -> None:
        for expected_index, source in enumerate(sources):
            if source.order_index != expected_index:
                raise SelectionContractError(
                    "IMAGE_SELECTION_ORDER_INVALID",
                    "Selection sources must use contiguous natural-order indexes.",
                )


__all__ = ["FastImageSelector", "fingerprint_distance", "geometry_distance"]
