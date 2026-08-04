"""Deterministic streaming state machine for representative image selection."""

from __future__ import annotations

import hashlib
import statistics
from collections import Counter, deque
from collections.abc import Iterable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
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
    SelectorOpenGroupState,
    SelectorResumeState,
    SequenceRange,
)
from .manifest import (
    APPEARANCE_ONLY_SELECTOR_VERSIONS,
    BEST_AVAILABLE_SELECTOR_VERSIONS,
    BEST_EFFORT_SELECTOR_VERSIONS,
    DEFAULT_SELECTOR_MANIFEST,
    EXACT_MULTI_GAP_SELECTOR_VERSIONS,
    FIRST_USABLE_POLICY,
    FIRST_USABLE_SELECTOR_VERSIONS,
    LEGACY_SELECTOR_VERSION,
    ORDERED_SELECTOR_VERSIONS,
    AppearanceDescriptorConfig,
    RangeFreeRepresentativePolicy,
    SelectorManifest,
)

BEST_AVAILABLE_REASON = "QUALITY_BEST_AVAILABLE"
INFERRED_RANGE_REASON = "RANGE_INFERRED_FROM_BOUNDED_GAP"
MAX_INFERRED_RANGE_SIZE = 9
DEFAULT_PARALLEL_SCAN_WORKERS = 4
DEFAULT_PARALLEL_SCAN_PREFETCH = 8
MAX_PARALLEL_SCAN_WORKERS = 8
MAX_PARALLEL_SCAN_PREFETCH = 32


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


def appearance_distance(
    first: tuple[float, ...],
    second: tuple[float, ...],
    config: AppearanceDescriptorConfig,
) -> float:
    """Return a weighted distance for the fixed-size v9 appearance vector."""

    phash_count = config.phash_size * config.phash_size
    hue_end = phash_count + config.hue_bins
    saturation_end = hue_end + config.saturation_bins
    value_end = saturation_end + config.value_bins
    edge_grid_end = value_end + config.edge_grid_rows * config.edge_grid_columns
    expected_count = edge_grid_end + config.edge_orientation_bins
    if len(first) != expected_count or len(second) != expected_count:
        return 1.0

    def mean_absolute(start: int, end: int) -> float:
        return statistics.fmean(abs(first[index] - second[index]) for index in range(start, end))

    def total_variation(start: int, end: int) -> float:
        return 0.5 * sum(abs(first[index] - second[index]) for index in range(start, end))

    phash = mean_absolute(0, phash_count)
    hsv = statistics.fmean(
        (
            total_variation(phash_count, hue_end),
            total_variation(hue_end, saturation_end),
            total_variation(saturation_end, value_end),
        )
    )
    edge = statistics.fmean(
        (
            mean_absolute(value_end, edge_grid_end),
            total_variation(edge_grid_end, expected_count),
        )
    )
    return min(
        1.0,
        phash * config.phash_weight + hsv * config.hsv_weight + edge * config.edge_weight,
    )


def _has_comparable_geometry(
    first: CheapImageObservation,
    second: CheapImageObservation,
    minimum_confidence: float,
) -> bool:
    return (
        first.geometry_confidence >= minimum_confidence
        and second.geometry_confidence >= minimum_confidence
        and bool(first.geometry_signature)
        and len(first.geometry_signature) == len(second.geometry_signature)
    )


def _unique_observation_anchors(
    observations: tuple[CheapImageObservation | None, ...],
) -> tuple[CheapImageObservation, ...]:
    anchors: list[CheapImageObservation] = []
    indexes: set[int] = set()
    for observation in observations:
        if observation is None or observation.source.order_index in indexes:
            continue
        indexes.add(observation.source.order_index)
        anchors.append(observation)
    return tuple(anchors)


@dataclass(slots=True)
class _OpenGroup:
    group_order: int
    top_k: int
    prefer_first_usable: bool = False
    appearance_only: bool = False
    representative_policy: RangeFreeRepresentativePolicy | None = None
    source_count: int = 0
    top_observations: list[CheapImageObservation] = field(default_factory=list)
    board_counts: Counter[int] = field(default_factory=Counter)
    reference: CheapImageObservation | None = None
    last_observation: CheapImageObservation | None = None
    appearance_centroid: list[float] = field(default_factory=list)
    appearance_observation_count: int = 0

    def add(self, observation: CheapImageObservation) -> None:
        self.source_count += 1
        if not self.appearance_only or observation.appearance_signature:
            self.last_observation = observation
        if observation.appearance_signature:
            if not self.appearance_centroid:
                self.appearance_centroid = list(observation.appearance_signature)
            elif len(self.appearance_centroid) != len(observation.appearance_signature):
                raise SelectionContractError(
                    "IMAGE_SELECTION_APPEARANCE_SIGNATURE_INVALID",
                    "Appearance signatures within one run must use one fixed dimension.",
                )
            else:
                next_count = self.appearance_observation_count + 1
                self.appearance_centroid = [
                    current + (value - current) / next_count
                    for current, value in zip(
                        self.appearance_centroid,
                        observation.appearance_signature,
                        strict=True,
                    )
                ]
            self.appearance_observation_count += 1
        if observation.board_count is not None:
            self.board_counts[observation.board_count] += 1
        candidates = (*self.top_observations, observation)
        ranked = sorted(
            candidates,
            key=_fallback_observation_rank if self.appearance_only else _observation_rank,
        )
        if self.prefer_first_usable:
            first_usable = min(
                (
                    item
                    for item in candidates
                    if _is_reasonably_readable_observation(
                        item,
                        policy=self.representative_policy,
                    )
                ),
                key=lambda item: (item.source.order_index, item.source.checksum_sha256),
                default=None,
            )
            selected = (
                ranked[:1]
                if first_usable is None and self.appearance_only
                else ([] if first_usable is None else [first_usable])
            )
            selected_indexes = {item.source.order_index for item in selected}
            remaining = [item for item in ranked if item.source.order_index not in selected_indexes]
            if not (self.appearance_only and first_usable is None):
                selected.extend(remaining[:1] if self.appearance_only else remaining)
            self.top_observations = sorted(
                selected[: self.top_k],
                key=_fallback_observation_rank if self.appearance_only else _observation_rank,
            )
        else:
            self.top_observations = ranked[: self.top_k]
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

    def to_state(self) -> SelectorOpenGroupState:
        return SelectorOpenGroupState(
            group_order=self.group_order,
            source_count=self.source_count,
            top_observations=tuple(self.top_observations),
            board_counts=tuple(sorted(self.board_counts.items())),
            last_observation=self.last_observation,
            appearance_centroid=tuple(self.appearance_centroid),
            appearance_observation_count=self.appearance_observation_count,
        )

    @classmethod
    def from_state(
        cls,
        state: SelectorOpenGroupState,
        *,
        top_k: int,
        prefer_first_usable: bool = False,
        appearance_only: bool = False,
        representative_policy: RangeFreeRepresentativePolicy | None = None,
    ) -> _OpenGroup:
        if len(state.top_observations) > top_k:
            raise SelectionContractError(
                "IMAGE_SELECTION_CHECKPOINT_INVALID",
                "The selector checkpoint exceeds the configured top-k bound.",
            )
        group = cls(
            group_order=state.group_order,
            top_k=top_k,
            prefer_first_usable=prefer_first_usable,
            appearance_only=appearance_only,
            representative_policy=representative_policy,
            source_count=state.source_count,
            top_observations=list(state.top_observations),
            board_counts=Counter(dict(state.board_counts)),
            appearance_centroid=list(state.appearance_centroid),
            appearance_observation_count=state.appearance_observation_count,
        )
        group.top_observations.sort(key=_observation_rank)
        group.reference = group.top_observations[0]
        group.last_observation = state.last_observation or max(
            group.top_observations,
            key=lambda observation: observation.source.order_index,
        )
        return group


def _observation_rank(observation: CheapImageObservation) -> tuple[float, int, str]:
    return (
        -observation.quality.overall_score,
        observation.source.order_index,
        observation.source.checksum_sha256,
    )


def _has_hard_scan_failure(observation: CheapImageObservation) -> bool:
    return not observation.appearance_signature or any(
        reason.startswith("IMAGE_SELECTION_SCAN_") for reason in observation.reason_codes
    )


def _is_reasonably_readable_observation(
    observation: CheapImageObservation,
    *,
    policy: RangeFreeRepresentativePolicy | None = None,
) -> bool:
    if _has_hard_scan_failure(observation):
        return False
    quality = observation.quality
    if policy is None:
        return (
            quality.overall_score >= FIRST_USABLE_POLICY.minimum_quality_score
            and quality.sharpness >= FIRST_USABLE_POLICY.minimum_sharpness
        )
    return (
        quality.overall_score >= policy.minimum_quality_score
        and quality.sharpness >= policy.minimum_sharpness
        and quality.exposure >= policy.minimum_exposure
        and quality.highlight_retention >= policy.minimum_highlight_retention
        and quality.board_visibility >= policy.minimum_board_visibility
    )


def _fallback_observation_rank(
    observation: CheapImageObservation,
) -> tuple[float, float, float, float, float, float, int, str]:
    quality = observation.quality
    return (
        -quality.overall_score,
        -quality.sharpness,
        -quality.exposure,
        -quality.highlight_retention,
        -quality.glare_resistance,
        -quality.board_visibility,
        observation.source.order_index,
        observation.source.checksum_sha256,
    )


def _range_free_candidate_rank(
    candidate: CandidateResult,
) -> tuple[float, float, float, float, float, float, int, str]:
    quality = candidate.quality
    return (
        -quality.overall_score,
        -quality.sharpness,
        -quality.exposure,
        -quality.highlight_retention,
        -quality.glare_resistance,
        -quality.board_visibility,
        candidate.source.order_index,
        candidate.source.checksum_sha256,
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


def _best_available_candidate_rank(
    candidate: CandidateResult,
) -> tuple[float, float, float, float, float, int, str]:
    confidence = (
        0.0 if candidate.recognized_range is None else candidate.recognized_range.confidence
    )
    return (
        -candidate.quality.overall_score,
        -candidate.quality.sharpness,
        -candidate.quality.perspective,
        -candidate.quality.board_visibility,
        -confidence,
        candidate.source.order_index,
        candidate.source.checksum_sha256,
    )


class FastImageSelector:
    """Group a natural-order stream and verify only the best candidates."""

    def __init__(
        self,
        manifest: SelectorManifest = DEFAULT_SELECTOR_MANIFEST,
        *,
        scan_workers: int = 1,
        scan_prefetch: int | None = None,
    ) -> None:
        if not 1 <= scan_workers <= MAX_PARALLEL_SCAN_WORKERS:
            raise ValueError(f"scan_workers must be between 1 and {MAX_PARALLEL_SCAN_WORKERS}.")
        effective_prefetch = scan_workers if scan_prefetch is None else scan_prefetch
        if not scan_workers <= effective_prefetch <= MAX_PARALLEL_SCAN_PREFETCH:
            raise ValueError(
                "scan_prefetch must be at least scan_workers and no greater than "
                f"{MAX_PARALLEL_SCAN_PREFETCH}."
            )
        self.manifest = manifest
        self._appearance_only = manifest.algorithm_version in APPEARANCE_ONLY_SELECTOR_VERSIONS
        self._prefer_first_usable = (
            manifest.algorithm_version in FIRST_USABLE_SELECTOR_VERSIONS or self._appearance_only
        )
        self._representative_policy = (
            manifest.representative_policy if self._appearance_only else None
        )
        self._scan_workers = scan_workers
        self._scan_prefetch = effective_prefetch

    def select(
        self,
        sources: Iterable[ImageSelectionSource],
        *,
        analyzer: CheapImageAnalyzer,
        verifier: CandidateVerifier,
        audit_sink: SelectionAuditSink | None = None,
        resume_state: SelectorResumeState | None = None,
        existing_groups: Iterable[SelectionGroupResult] = (),
    ) -> ImageSelectionResult:
        ordered_sources = tuple(sources)
        self._validate_source_order(ordered_sources)
        sink = audit_sink or NullSelectionAuditSink()
        groups = list(existing_groups)
        self._validate_resume(
            ordered_sources,
            groups=groups,
            resume_state=resume_state,
        )
        completed_ranges: dict[tuple[int, int], int] = {}
        unresolved_ranges: dict[tuple[int, int], int] = {}
        unresolved_fingerprints: dict[int, str] = {}
        for group in groups:
            if (
                group.status
                in {
                    SelectionGroupStatus.AUTO_SELECTED,
                    SelectionGroupStatus.MANUALLY_SELECTED,
                }
                and group.range is not None
            ):
                completed_ranges[(group.range.start, group.range.end)] = group.group_order
            elif group.status is SelectionGroupStatus.MANUAL_REQUIRED:
                if group.range is not None:
                    unresolved_ranges[(group.range.start, group.range.end)] = group.group_order
                if group.reference_fingerprint_hex is not None:
                    unresolved_fingerprints[group.group_order] = group.reference_fingerprint_hex
        current = (
            None
            if resume_state is None or resume_state.current_group is None
            else _OpenGroup.from_state(
                resume_state.current_group,
                top_k=self.manifest.top_k,
                prefer_first_usable=self._prefer_first_usable,
                appearance_only=self._appearance_only,
                representative_policy=self._representative_policy,
            )
        )
        pending = [] if resume_state is None else list(resume_state.pending_observations)
        processed_count = 0 if resume_state is None else resume_state.checkpoint.processed_count
        scan_failure_count = 0 if resume_state is None else resume_state.scan_failure_count
        verification_count = 0 if resume_state is None else resume_state.verification_count

        def ingest(group: _OpenGroup, observation: CheapImageObservation) -> None:
            nonlocal scan_failure_count
            group.add(observation)
            if any(code.startswith("IMAGE_SELECTION_SCAN_") for code in observation.reason_codes):
                scan_failure_count += 1
            sink.candidate_scanned(observation, group_order=group.group_order)

        def finalize(group: _OpenGroup) -> None:
            nonlocal verification_count
            previous_groups = tuple(groups)
            result, count = self._finalize_group(
                group,
                verifier=verifier,
                existing_groups=groups,
                completed_ranges=completed_ranges,
                unresolved_ranges=unresolved_ranges,
                unresolved_fingerprints=unresolved_fingerprints,
            )
            verification_count += count
            for before, after in zip(previous_groups, groups, strict=True):
                if before != after:
                    sink.group_finalized(after)
            if result.status is SelectionGroupStatus.AUTO_SELECTED and result.range is not None:
                completed_ranges[(result.range.start, result.range.end)] = result.group_order
            elif result.status is SelectionGroupStatus.MANUAL_REQUIRED:
                if result.range is not None:
                    unresolved_ranges[(result.range.start, result.range.end)] = result.group_order
                if group.reference is not None:
                    unresolved_fingerprints[result.group_order] = group.reference.fingerprint_hex
            groups.append(result)
            sink.group_finalized(result)
            if (
                self.manifest.algorithm_version in EXACT_MULTI_GAP_SELECTOR_VERSIONS
                and result.status is SelectionGroupStatus.AUTO_SELECTED
                and result.range is not None
            ):
                for recovered_index, recovered in self._recover_trailing_exact_gap(groups):
                    groups[recovered_index] = recovered
                    assert recovered.range is not None
                    completed_ranges[(recovered.range.start, recovered.range.end)] = (
                        recovered.group_order
                    )
                    unresolved_fingerprints.pop(recovered.group_order, None)
                    sink.group_finalized(recovered)

        first_source_index = 0 if resume_state is None else resume_state.checkpoint.next_order_index
        for observation in self._analyze_in_source_order(
            ordered_sources[first_source_index:],
            analyzer=analyzer,
        ):
            processed_count += 1
            if current is None:
                current = _OpenGroup(
                    group_order=0,
                    top_k=self.manifest.top_k,
                    prefer_first_usable=self._prefer_first_usable,
                    appearance_only=self._appearance_only,
                    representative_policy=self._representative_policy,
                )
                ingest(current, observation)
            elif pending:
                pending_anchor = (
                    pending[0]
                    if self.manifest.algorithm_version == LEGACY_SELECTOR_VERSION
                    else pending[-1]
                )
                if self._pending_matches(pending_anchor, observation):
                    pending.append(observation)
                    if len(pending) >= self.manifest.boundary_confirmation_count:
                        finalize(current)
                        current = _OpenGroup(
                            group_order=len(groups),
                            top_k=self.manifest.top_k,
                            prefer_first_usable=self._prefer_first_usable,
                            appearance_only=self._appearance_only,
                            representative_policy=self._representative_policy,
                        )
                        for item in pending:
                            ingest(current, item)
                        pending.clear()
                else:
                    # One visually different frame is not a confirmed page
                    # boundary. It is commonly a transition animation, glare,
                    # or an unstable cheap board detection. Keep it with the
                    # current range and begin confirmation again from the new
                    # observation instead of creating a singleton group.
                    appearance_restart = self._appearance_only and (
                        self._is_changed_from_group_majority(current, observation)
                        or self._is_boundary_candidate(current, observation)
                    )
                    for item in pending:
                        ingest(current, item)
                    pending.clear()
                    if self._appearance_only:
                        restart_confirmation = appearance_restart
                    else:
                        restart_confirmation = (
                            self.manifest.algorithm_version in ORDERED_SELECTOR_VERSIONS
                            and self._is_changed_from_group_majority(current, observation)
                        ) or self._is_boundary_candidate(current, observation)
                    if restart_confirmation:
                        pending.append(observation)
                    else:
                        ingest(current, observation)
            elif self._is_boundary_candidate(current, observation):
                pending.append(observation)
            else:
                ingest(current, observation)

            if processed_count % self.manifest.scan_batch_size == 0:
                self._save_state(
                    sink,
                    processed_count=processed_count,
                    groups=groups,
                    current=current,
                    pending=pending,
                    scan_failure_count=scan_failure_count,
                    verification_count=verification_count,
                )

        if current is not None:
            if pending:
                finalize(current)
                current = _OpenGroup(
                    group_order=len(groups),
                    top_k=self.manifest.top_k,
                    prefer_first_usable=self._prefer_first_usable,
                    appearance_only=self._appearance_only,
                    representative_policy=self._representative_policy,
                )
                for observation in pending:
                    ingest(current, observation)
            finalize(current)
        if self.manifest.algorithm_version in BEST_AVAILABLE_SELECTOR_VERSIONS:
            recovered_groups = self._recover_bounded_best_available_groups(groups)
            for index, recovered in enumerate(recovered_groups):
                if recovered != groups[index]:
                    groups[index] = recovered
                    sink.group_finalized(recovered)
        state = self._save_state(
            sink,
            processed_count=processed_count,
            groups=groups,
            current=None,
            pending=[],
            scan_failure_count=scan_failure_count,
            verification_count=verification_count,
        )
        return ImageSelectionResult(
            selector_version=self.manifest.algorithm_version,
            selector_fingerprint=self.manifest.fingerprint,
            input_count=len(ordered_sources),
            groups=tuple(groups),
            checkpoint=state.checkpoint,
            scan_failure_count=scan_failure_count,
            verification_count=verification_count,
        )

    def _analyze_in_source_order(
        self,
        sources: tuple[ImageSelectionSource, ...],
        *,
        analyzer: CheapImageAnalyzer,
    ) -> Iterator[CheapImageObservation]:
        if self._scan_workers == 1:
            for source in sources:
                yield analyzer.analyze(source)
            return

        source_iterator = iter(sources)
        pending: deque[Future[CheapImageObservation]] = deque()
        with ThreadPoolExecutor(
            max_workers=self._scan_workers,
            thread_name_prefix="image-selection-scan",
        ) as executor:

            def fill_prefetch() -> None:
                while len(pending) < self._scan_prefetch:
                    try:
                        source = next(source_iterator)
                    except StopIteration:
                        return
                    pending.append(executor.submit(analyzer.analyze, source))

            fill_prefetch()
            while pending:
                future = pending.popleft()
                try:
                    yield future.result()
                except BaseException:
                    for queued in pending:
                        queued.cancel()
                    raise
                fill_prefetch()

    def _is_boundary_candidate(
        self,
        current: _OpenGroup,
        observation: CheapImageObservation,
    ) -> bool:
        reference = current.reference
        if reference is None:
            return False
        if self._appearance_only:
            return self._is_appearance_boundary(current, observation)
        if self.manifest.algorithm_version in ORDERED_SELECTOR_VERSIONS:
            return self._is_ordered_boundary(current, observation)
        if self.manifest.algorithm_version != LEGACY_SELECTOR_VERSION:
            return self._is_temporally_stable_boundary(current, observation)
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

    def _is_ordered_boundary(
        self,
        current: _OpenGroup,
        observation: CheapImageObservation,
    ) -> bool:
        """Detect a page change from adjacent frames, not historical top-k.

        Ordered camera captures drift gradually within one page.  The existing
        pending guard confirms that a visually different observation is the
        start of a stable next page.  Historical quality representatives must
        not veto that boundary after an earlier page happened to look similar.
        """

        adjacent = current.last_observation or current.reference
        if adjacent is None:
            return False
        threshold = self.manifest.thresholds
        visual_distance = fingerprint_distance(
            adjacent.fingerprint_hex,
            observation.fingerprint_hex,
        )
        if visual_distance < threshold.fingerprint_change_distance:
            return False
        geometry_changed = (
            _has_comparable_geometry(
                adjacent,
                observation,
                threshold.minimum_geometry_confidence,
            )
            and geometry_distance(
                adjacent.geometry_signature,
                observation.geometry_signature,
            )
            >= threshold.geometry_change_distance
        )
        return (
            visual_distance >= threshold.strong_fingerprint_change_distance
            or geometry_changed
            or self.manifest.boundary_confirmation_count > 1
        )

    def _is_appearance_boundary(
        self,
        current: _OpenGroup,
        observation: CheapImageObservation,
    ) -> bool:
        adjacent = current.last_observation
        centroid = tuple(current.appearance_centroid)
        signature = observation.appearance_signature
        if adjacent is None or not adjacent.appearance_signature or not centroid or not signature:
            return False
        config = self.manifest.appearance_descriptor
        threshold = self.manifest.appearance_thresholds
        adjacent_distance = appearance_distance(
            adjacent.appearance_signature,
            signature,
            config,
        )
        centroid_distance = appearance_distance(centroid, signature, config)
        return (
            adjacent_distance >= threshold.adjacent_boundary_distance
            and centroid_distance >= threshold.centroid_boundary_distance
        ) or (
            adjacent_distance >= threshold.strong_boundary_distance
            and centroid_distance >= threshold.centroid_boundary_distance * 0.75
        )

    def _is_changed_from_group_majority(
        self,
        current: _OpenGroup,
        observation: CheapImageObservation,
    ) -> bool:
        """Keep tracking a multi-frame transition away from the old page."""

        if self._appearance_only:
            if not current.appearance_centroid or not observation.appearance_signature:
                return False
            return (
                appearance_distance(
                    tuple(current.appearance_centroid),
                    observation.appearance_signature,
                    self.manifest.appearance_descriptor,
                )
                >= self.manifest.appearance_thresholds.centroid_boundary_distance
            )
        anchors = _unique_observation_anchors((*current.top_observations, current.reference))
        if not anchors:
            return False
        threshold = self.manifest.thresholds.fingerprint_change_distance
        changed = sum(
            fingerprint_distance(anchor.fingerprint_hex, observation.fingerprint_hex) >= threshold
            for anchor in anchors
        )
        return changed * 2 > len(anchors)

    def _is_temporally_stable_boundary(
        self,
        current: _OpenGroup,
        observation: CheapImageObservation,
    ) -> bool:
        """Require a change from both stable and temporally adjacent anchors.

        A camera sweep can move far away from the best-quality frame while each
        adjacent frame still depicts the same page. Comparing only with the
        best frame turns that gradual drift into many short groups. The v3
        selector keeps the adjacent anchor bounded in the durable checkpoint
        and treats geometry without a lattice as unknown, never as maximum
        change.
        """

        threshold = self.manifest.thresholds
        anchors = _unique_observation_anchors((*current.top_observations, current.last_observation))
        if not anchors:
            return False
        visual_distances = tuple(
            fingerprint_distance(anchor.fingerprint_hex, observation.fingerprint_hex)
            for anchor in anchors
        )
        if min(visual_distances) < threshold.fingerprint_change_distance:
            return False

        strong_visual_change = min(visual_distances) >= threshold.strong_fingerprint_change_distance
        geometry_changed = any(
            _has_comparable_geometry(anchor, observation, threshold.minimum_geometry_confidence)
            and geometry_distance(
                anchor.geometry_signature,
                observation.geometry_signature,
            )
            >= threshold.geometry_change_distance
            for anchor in anchors
        )
        return strong_visual_change or geometry_changed

    def _pending_matches(
        self,
        first: CheapImageObservation,
        next_observation: CheapImageObservation,
    ) -> bool:
        if self._appearance_only:
            if not first.appearance_signature or not next_observation.appearance_signature:
                return False
            return (
                appearance_distance(
                    first.appearance_signature,
                    next_observation.appearance_signature,
                    self.manifest.appearance_descriptor,
                )
                <= self.manifest.appearance_thresholds.pending_same_group_distance
            )
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
        if self._appearance_only:
            return self._finalize_appearance_group(group), 0
        consensus = group.board_count_consensus
        observations_to_verify = (
            sorted(
                group.top_observations,
                key=lambda observation: observation.source.order_index,
            )
            if self._prefer_first_usable
            else group.top_observations
        )
        verified: list[tuple[CheapImageObservation, CandidateVerification]] = []
        for observation in observations_to_verify:
            verification = verifier.verify(observation, expected_board_count=consensus)
            verified.append((observation, verification))
            if self._prefer_first_usable and self._is_first_usable_verification(
                observation,
                verification,
                board_count_consensus=consensus,
            ):
                break
        range_keys = {
            (verification.recognized_range.start, verification.recognized_range.end)
            for _, verification in verified
            if verification.recognized_range is not None
            and verification.recognized_range.confidence
            >= self.manifest.thresholds.minimum_range_confidence
        }
        range_conflict = len(range_keys) > 1
        rank = (
            _best_available_candidate_rank
            if self.manifest.algorithm_version in BEST_AVAILABLE_SELECTOR_VERSIONS
            else _candidate_rank
        )
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
                key=rank,
            )
        )
        eligible = [
            candidate
            for candidate in candidates
            if candidate.decision is CandidateDecision.ELIGIBLE
        ]
        recognized_range = self._group_range(candidates)
        selected = None if not eligible else self._select_automatic(eligible[0])
        if (
            selected is None
            and recognized_range is not None
            and self.manifest.algorithm_version in BEST_AVAILABLE_SELECTOR_VERSIONS
        ):
            best_available = next(
                (
                    candidate
                    for candidate in candidates
                    if self._can_use_inferred_best_available(candidate)
                ),
                None,
            )
            if best_available is not None:
                selected = replace(
                    best_available,
                    decision=CandidateDecision.SELECTED_AUTOMATIC,
                    recognized_range=recognized_range,
                    reason_codes=tuple(
                        dict.fromkeys((*best_available.reason_codes, BEST_AVAILABLE_REASON))
                    ),
                )
        if selected is not None:
            selected_identity = (
                selected.source.order_index,
                selected.source.checksum_sha256,
            )
            candidates = tuple(
                selected
                if (candidate.source.order_index, candidate.source.checksum_sha256)
                == selected_identity
                else candidate
                for candidate in candidates
            )
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
                        reference_fingerprint_hex=group.reference.fingerprint_hex,
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
                    sorted((*previous.top_candidates, *candidates), key=rank)[: self.manifest.top_k]
                )
                existing_groups[unresolved_order] = replace(
                    previous,
                    source_count=previous.source_count + group.source_count,
                    range=selected_range,
                    board_count_consensus=consensus or previous.board_count_consensus,
                    status=SelectionGroupStatus.AUTO_SELECTED,
                    selected_candidate=selected,
                    top_candidates=combined,
                    reference_fingerprint_hex=previous.reference_fingerprint_hex,
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
                        reference_fingerprint_hex=group.reference.fingerprint_hex,
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
                    reference_fingerprint_hex=group.reference.fingerprint_hex,
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
                reference_fingerprint_hex=group.reference.fingerprint_hex,
            ),
            len(verified),
        )

    def _finalize_appearance_group(self, group: _OpenGroup) -> SelectionGroupResult:
        assert group.reference is not None
        observations = tuple(group.top_observations)
        usable = min(
            (
                observation
                for observation in observations
                if _is_reasonably_readable_observation(
                    observation,
                    policy=self.manifest.representative_policy,
                )
            ),
            key=lambda observation: (
                observation.source.order_index,
                observation.source.checksum_sha256,
            ),
            default=None,
        )
        decodable = tuple(
            observation for observation in observations if not _has_hard_scan_failure(observation)
        )
        selected_observation = (
            usable
            if usable is not None
            else (None if not decodable else min(decodable, key=_fallback_observation_rank))
        )
        selected_identity = (
            None
            if selected_observation is None
            else (
                selected_observation.source.order_index,
                selected_observation.source.checksum_sha256,
            )
        )
        used_best_available = selected_observation is not None and usable is None
        candidates = []
        for observation in observations:
            identity = (
                observation.source.order_index,
                observation.source.checksum_sha256,
            )
            hard_failure = _has_hard_scan_failure(observation)
            reasons = observation.reason_codes
            if identity == selected_identity and used_best_available:
                reasons = tuple(dict.fromkeys((*reasons, BEST_AVAILABLE_REASON)))
            candidates.append(
                CandidateResult(
                    source=observation.source,
                    decision=(
                        CandidateDecision.SELECTED_AUTOMATIC
                        if identity == selected_identity
                        else (
                            CandidateDecision.REJECTED
                            if hard_failure
                            else CandidateDecision.ELIGIBLE
                        )
                    ),
                    quality=observation.quality,
                    recognized_range=None,
                    reason_codes=reasons,
                    width=observation.width,
                    height=observation.height,
                )
            )
        ranked_candidates = tuple(sorted(candidates, key=_range_free_candidate_rank))
        selected_candidate = next(
            (
                candidate
                for candidate in ranked_candidates
                if candidate.decision is CandidateDecision.SELECTED_AUTOMATIC
            ),
            None,
        )
        fingerprint_sha256 = hashlib.sha256(
            bytes.fromhex(group.reference.fingerprint_hex)
        ).hexdigest()
        return SelectionGroupResult(
            group_order=group.group_order,
            source_count=group.source_count,
            range=None,
            fingerprint_sha256=fingerprint_sha256,
            board_count_consensus=None,
            status=(
                SelectionGroupStatus.AUTO_SELECTED
                if selected_candidate is not None
                else SelectionGroupStatus.MANUAL_REQUIRED
            ),
            selected_candidate=selected_candidate,
            top_candidates=ranked_candidates,
            reference_fingerprint_hex=group.reference.fingerprint_hex,
        )

    def _candidate_result(
        self,
        observation: CheapImageObservation,
        verification: CandidateVerification,
        *,
        board_count_consensus: int | None,
        range_conflict: bool,
    ) -> CandidateResult:
        recognized_range = verification.recognized_range
        trusted_full_verification = (
            recognized_range is not None
            and verification.geometry_complete
            and verification.full_frame_visible
            and verification.board_count == recognized_range.board_count
        )
        reasons = [
            reason
            for reason in observation.reason_codes
            if not trusted_full_verification or not reason.startswith(("BOARD_", "GEOMETRY_"))
        ]
        reasons.extend(verification.reason_codes)
        threshold = self.manifest.thresholds
        quality = observation.quality
        if (
            not trusted_full_verification
            and quality.overall_score < threshold.minimum_quality_score
        ):
            reasons.append("QUALITY_SCORE_LOW")
        if quality.sharpness < threshold.minimum_sharpness:
            reasons.append("QUALITY_BLUR")
        if not trusted_full_verification and quality.exposure < threshold.minimum_exposure:
            reasons.append("QUALITY_EXPOSURE")
        if quality.highlight_retention < threshold.minimum_highlight_retention:
            reasons.append("QUALITY_HIGHLIGHT_CLIPPING")
        if quality.glare_resistance < threshold.minimum_glare_resistance:
            reasons.append("QUALITY_GLARE")
        if (
            not trusted_full_verification
            and quality.border_margin < threshold.minimum_border_margin
        ):
            reasons.append("QUALITY_FRAME_CROPPED")
        if (
            not trusted_full_verification
            and observation.geometry_confidence < threshold.minimum_geometry_confidence
        ):
            reasons.append("GEOMETRY_CONFIDENCE_LOW")
        if not verification.geometry_complete:
            reasons.append("GEOMETRY_INCOMPLETE")
        if not verification.full_frame_visible:
            reasons.append("FRAME_NOT_FULLY_VISIBLE")
        if not trusted_full_verification and (
            board_count_consensus is None or verification.board_count != board_count_consensus
        ):
            reasons.append("BOARD_COUNT_CONSENSUS_MISMATCH")
        if recognized_range is None:
            reasons.append("RANGE_UNKNOWN")
        elif recognized_range.confidence < threshold.minimum_range_confidence:
            reasons.append("RANGE_CONFIDENCE_LOW")
        elif recognized_range.board_count != verification.board_count:
            reasons.append("RANGE_BOARD_COUNT_MISMATCH")
        if range_conflict:
            reasons.append("RANGE_CONFLICT")
        unique_reasons = tuple(dict.fromkeys(reasons))
        blocking_reasons = (
            tuple(
                reason
                for reason in unique_reasons
                if not reason.startswith("QUALITY_") or reason == "QUALITY_BLUR"
            )
            if self.manifest.algorithm_version in BEST_AVAILABLE_SELECTOR_VERSIONS
            else unique_reasons
        )
        return CandidateResult(
            source=observation.source,
            decision=(
                CandidateDecision.ELIGIBLE if not blocking_reasons else CandidateDecision.REJECTED
            ),
            quality=quality,
            recognized_range=recognized_range,
            reason_codes=unique_reasons,
            width=observation.width,
            height=observation.height,
        )

    def _is_first_usable_verification(
        self,
        observation: CheapImageObservation,
        verification: CandidateVerification,
        *,
        board_count_consensus: int | None,
    ) -> bool:
        recognized_range = verification.recognized_range
        if (
            recognized_range is None
            or recognized_range.confidence < self.manifest.thresholds.minimum_range_confidence
            or verification.board_count != recognized_range.board_count
        ):
            return False
        candidate = self._candidate_result(
            observation,
            verification,
            board_count_consensus=board_count_consensus,
            range_conflict=False,
        )
        return self._can_use_inferred_best_available(candidate)

    def _select_automatic(self, candidate: CandidateResult) -> CandidateResult:
        reasons = candidate.reason_codes
        if self.manifest.algorithm_version in BEST_AVAILABLE_SELECTOR_VERSIONS and any(
            reason.startswith("QUALITY_") for reason in reasons
        ):
            reasons = tuple(dict.fromkeys((*reasons, BEST_AVAILABLE_REASON)))
        return replace(
            candidate,
            decision=CandidateDecision.SELECTED_AUTOMATIC,
            reason_codes=reasons,
        )

    def _recover_bounded_best_available_groups(
        self,
        groups: list[SelectionGroupResult],
    ) -> tuple[SelectionGroupResult, ...]:
        recovered = list(groups)
        resolved_indexes = [
            index
            for index, group in enumerate(recovered)
            if group.status
            in {
                SelectionGroupStatus.AUTO_SELECTED,
                SelectionGroupStatus.MANUALLY_SELECTED,
            }
            and group.range is not None
        ]
        for previous_index, next_index in zip(
            resolved_indexes,
            resolved_indexes[1:],
            strict=False,
        ):
            for group_index, replacement in self._recover_exact_gap_block(
                recovered,
                previous_index=previous_index,
                next_index=next_index,
            ):
                recovered[group_index] = replacement
        return tuple(recovered)

    def _recover_trailing_exact_gap(
        self,
        groups: list[SelectionGroupResult],
    ) -> tuple[tuple[int, SelectionGroupResult], ...]:
        next_index = len(groups) - 1
        previous_index = next_index - 1
        while previous_index >= 0:
            group = groups[previous_index]
            if group.status is SelectionGroupStatus.MANUAL_REQUIRED and group.range is None:
                previous_index -= 1
                continue
            break
        if previous_index < 0 or previous_index == next_index - 1:
            return ()
        return self._recover_exact_gap_block(
            groups,
            previous_index=previous_index,
            next_index=next_index,
        )

    def _recover_exact_gap_block(
        self,
        groups: list[SelectionGroupResult],
        *,
        previous_index: int,
        next_index: int,
    ) -> tuple[tuple[int, SelectionGroupResult], ...]:
        group_indexes = tuple(range(previous_index + 1, next_index))
        if not group_indexes or any(
            groups[index].status is not SelectionGroupStatus.MANUAL_REQUIRED
            or groups[index].range is not None
            for index in group_indexes
        ):
            return ()
        if (
            self.manifest.algorithm_version not in EXACT_MULTI_GAP_SELECTOR_VERSIONS
            and len(group_indexes) != 1
        ):
            return ()

        previous_range = groups[previous_index].range
        next_range = groups[next_index].range
        if previous_range is None or next_range is None:
            return ()
        gap_start = previous_range.end + 1
        gap_end = next_range.start - 1
        gap_size = gap_end - gap_start + 1
        if gap_size < 1:
            return ()
        range_sizes: tuple[int, ...]
        if len(group_indexes) == 1 and gap_size <= MAX_INFERRED_RANGE_SIZE:
            range_sizes = (gap_size,)
        elif (
            self.manifest.algorithm_version in EXACT_MULTI_GAP_SELECTOR_VERSIONS
            and gap_size == len(group_indexes) * MAX_INFERRED_RANGE_SIZE
        ):
            range_sizes = (MAX_INFERRED_RANGE_SIZE,) * len(group_indexes)
        else:
            return ()

        existing_ranges = {
            (group.range.start, group.range.end)
            for group in groups
            if group.range is not None
            and group.status
            in {
                SelectionGroupStatus.AUTO_SELECTED,
                SelectionGroupStatus.MANUALLY_SELECTED,
            }
        }
        replacements: list[tuple[int, SelectionGroupResult]] = []
        range_start = gap_start
        for group_index, range_size in zip(group_indexes, range_sizes, strict=True):
            group = groups[group_index]
            inferred = SequenceRange(
                start=range_start,
                end=range_start + range_size - 1,
                confidence=self.manifest.thresholds.minimum_range_confidence,
            )
            if (inferred.start, inferred.end) in existing_ranges:
                return ()
            candidates = tuple(
                candidate
                for candidate in group.top_candidates
                if self._can_use_inferred_best_available(candidate)
            )
            if not candidates:
                return ()
            selected_source = sorted(candidates, key=_best_available_candidate_rank)[0]
            selected = replace(
                selected_source,
                decision=CandidateDecision.SELECTED_AUTOMATIC,
                recognized_range=inferred,
                reason_codes=tuple(
                    dict.fromkeys(
                        (
                            *selected_source.reason_codes,
                            BEST_AVAILABLE_REASON,
                            INFERRED_RANGE_REASON,
                        )
                    )
                ),
            )
            selected_identity = (
                selected.source.order_index,
                selected.source.checksum_sha256,
            )
            top_candidates = tuple(
                selected
                if (candidate.source.order_index, candidate.source.checksum_sha256)
                == selected_identity
                else candidate
                for candidate in group.top_candidates
            )
            replacements.append(
                (
                    group_index,
                    replace(
                        group,
                        range=inferred,
                        status=SelectionGroupStatus.AUTO_SELECTED,
                        selected_candidate=selected,
                        top_candidates=top_candidates,
                    ),
                )
            )
            range_start = inferred.end + 1
        return tuple(replacements)

    def _can_use_inferred_best_available(self, candidate: CandidateResult) -> bool:
        hard_failure = any(
            reason.startswith("IMAGE_SELECTION_SCAN_")
            or reason in {"IMAGE_SELECTION_VERIFY_GEOMETRY_FAILED", "RANGE_CONFLICT"}
            for reason in candidate.reason_codes
        )
        if self.manifest.algorithm_version in BEST_EFFORT_SELECTOR_VERSIONS:
            return not hard_failure
        return (
            candidate.quality.sharpness >= self.manifest.thresholds.minimum_sharpness
            and not hard_failure
            and not any(
                reason == "IMAGE_OCCLUDED" or reason.startswith("IMAGE_SELECTION_SCAN_")
                for reason in candidate.reason_codes
            )
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

    def _save_state(
        self,
        sink: SelectionAuditSink,
        *,
        processed_count: int,
        groups: list[SelectionGroupResult],
        current: _OpenGroup | None,
        pending: list[CheapImageObservation],
        scan_failure_count: int,
        verification_count: int,
    ) -> SelectorResumeState:
        checkpoint = self._checkpoint(
            processed_count=processed_count,
            finalized_group_count=len(groups),
        )
        state = SelectorResumeState(
            checkpoint=checkpoint,
            current_group=None if current is None else current.to_state(),
            pending_observations=tuple(pending),
            scan_failure_count=scan_failure_count,
            verification_count=verification_count,
        )
        sink.checkpoint_saved(checkpoint)
        state_callback = getattr(sink, "selector_state_saved", None)
        if callable(state_callback):
            state_callback(state)
        return state

    def _validate_resume(
        self,
        sources: tuple[ImageSelectionSource, ...],
        *,
        groups: list[SelectionGroupResult],
        resume_state: SelectorResumeState | None,
    ) -> None:
        for expected_order, group in enumerate(groups):
            if group.group_order != expected_order:
                raise SelectionContractError(
                    "IMAGE_SELECTION_CHECKPOINT_INVALID",
                    "Persisted groups are not contiguous in selector order.",
                )
        if resume_state is None:
            if groups:
                raise SelectionContractError(
                    "IMAGE_SELECTION_CHECKPOINT_INVALID",
                    "Persisted groups require a matching selector checkpoint.",
                )
            return
        checkpoint = resume_state.checkpoint
        if (
            checkpoint.schema_version != 1
            or checkpoint.selector_fingerprint != self.manifest.fingerprint
            or checkpoint.next_order_index != checkpoint.processed_count
            or not 0 <= checkpoint.next_order_index <= len(sources)
            or checkpoint.finalized_group_count != len(groups)
            or resume_state.scan_failure_count < 0
            or resume_state.verification_count < 0
            or len(resume_state.pending_observations) >= self.manifest.boundary_confirmation_count
        ):
            raise SelectionContractError(
                "IMAGE_SELECTION_CHECKPOINT_INVALID",
                "The selector checkpoint is inconsistent with its input and manifest.",
            )
        current = resume_state.current_group
        if current is None:
            if resume_state.pending_observations or checkpoint.next_order_index < len(sources):
                raise SelectionContractError(
                    "IMAGE_SELECTION_CHECKPOINT_INVALID",
                    "An unfinished selector checkpoint is missing its open group.",
                )
        elif current.group_order != len(groups):
            raise SelectionContractError(
                "IMAGE_SELECTION_CHECKPOINT_INVALID",
                "The selector checkpoint open group has an invalid order.",
            )
        observed_indexes = [
            observation.source.order_index
            for observation in (
                (() if current is None else current.top_observations)
                + (
                    ()
                    if current is None or current.last_observation is None
                    else (current.last_observation,)
                )
                + resume_state.pending_observations
            )
        ]
        if any(index >= checkpoint.next_order_index for index in observed_indexes):
            raise SelectionContractError(
                "IMAGE_SELECTION_CHECKPOINT_INVALID",
                "The selector checkpoint references an unprocessed source.",
            )

    @staticmethod
    def _validate_source_order(sources: tuple[ImageSelectionSource, ...]) -> None:
        for expected_index, source in enumerate(sources):
            if source.order_index != expected_index:
                raise SelectionContractError(
                    "IMAGE_SELECTION_ORDER_INVALID",
                    "Selection sources must use contiguous natural-order indexes.",
                )


__all__ = [
    "FastImageSelector",
    "appearance_distance",
    "fingerprint_distance",
    "geometry_distance",
]
