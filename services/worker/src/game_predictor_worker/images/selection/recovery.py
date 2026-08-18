"""Pure planning helpers for immutable unresolved-range recovery runs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from uuid import UUID

from .contracts import (
    CandidateDecision,
    CandidateResult,
    CandidateVerifier,
    CheapImageAnalyzer,
    CheapImageObservation,
    ImageSelectionSource,
    SelectionContractError,
    SelectionGroupResult,
    SelectionGroupStatus,
    SelectorCheckpoint,
    SequenceRange,
)
from .engine import FastImageSelector
from .manifest import (
    ADAPTIVE_CARDINALITY_SELECTOR_VERSION,
    CARDINALITY_GUARDED_SELECTOR_VERSION,
    CARDINALITY_PARTITIONED_SELECTOR_VERSION,
    PROOF_FIRST_SELECTOR_VERSIONS,
    QUANTILE_SAMPLED_SELECTOR_VERSION,
    SEQUENCE_VALIDATED_SELECTOR_VERSION,
    SINGLE_FRAME_EARLY_EXIT_SELECTOR_VERSION,
    STAGED_OCR_SELECTOR_VERSION,
    SelectorManifest,
)
from .range_proof import has_strong_local_range_proof
from .sequence_bounds import SequenceBounds

_PROTECTED_USER_STATUSES = {
    SelectionGroupStatus.MANUALLY_SELECTED,
    SelectionGroupStatus.MISSING_IMAGE,
    SelectionGroupStatus.RANGE_CONFIRMED,
    SelectionGroupStatus.REJECTED_BY_USER,
}
_OUTPUT_STATUSES = {
    SelectionGroupStatus.AUTO_SELECTED,
    SelectionGroupStatus.MANUALLY_SELECTED,
    SelectionGroupStatus.RANGE_CONFIRMED,
}


@dataclass(frozen=True, slots=True)
class RecoverySourceGroup:
    """One immutable source projection and every preserved gallery source."""

    origin_group_id: UUID
    result: SelectionGroupResult
    sources: tuple[ImageSelectionSource, ...]


@dataclass(frozen=True, slots=True)
class RecoveryBlock:
    """A maximal problem block expanded by bounded resolved guards."""

    first_group_index: int
    last_group_index: int
    source_groups: tuple[RecoverySourceGroup, ...]


@dataclass(frozen=True, slots=True)
class RecoveryBlockInput:
    """A locally indexed selector input with reversible source identities."""

    sources: tuple[ImageSelectionSource, ...]
    original_sources: tuple[ImageSelectionSource, ...]
    origin_group_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class RecoveredBlock:
    block: RecoveryBlock
    groups: tuple[SelectionGroupResult, ...]
    group_sources: tuple[tuple[CheapImageObservation, ...], ...]
    origin_group_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class RecoveryProjection:
    groups: tuple[SelectionGroupResult, ...]
    group_sources: dict[int, tuple[CheapImageObservation, ...]]
    origin_group_ids: dict[int, UUID]


@dataclass(frozen=True, slots=True)
class RecoveryEvaluationProgress:
    """One completed recovery block for bounded durable progress reporting."""

    completed_blocks: int
    block_count: int
    completed_candidates: int
    candidate_count: int
    scan_failure_count: int
    verification_count: int


@dataclass(frozen=True, slots=True)
class RecoveryEvaluation:
    """Read-only result shared by the durable worker and operational dry-run."""

    projection: RecoveryProjection
    block_count: int
    candidate_count: int
    scan_failure_count: int
    verification_count: int


RecoveryProgressCallback = Callable[[RecoveryEvaluationProgress], None]

_FORBIDDEN_RECOVERY_RANGE_REASONS = frozenset(
    {
        "RANGE_EXACT_GAP_INFERRED",
        "RANGE_INFERRED_FROM_BOUNDED_GAP",
        "RANGE_OWNER_ANCHOR",
    }
)
_CARDINALITY_RANGE_REASON = "RANGE_CARDINALITY_INFERRED"
_CARDINALITY_BLOCKING_REASONS = frozenset(
    {
        "IMAGE_OCCLUDED",
        "IMAGE_SELECTION_VERIFY_GEOMETRY_FAILED",
        "QUALITY_BLUR",
        "RANGE_CONFLICT",
    }
)
_INFINITE_ASSIGNMENT_COST = 10**15


def evaluate_recovery(
    source_groups: tuple[RecoverySourceGroup, ...],
    *,
    manifest: SelectorManifest,
    analyzer: CheapImageAnalyzer,
    verifier: CandidateVerifier,
    sequence_direction: str,
    first_sequence_number: int,
    last_sequence_number: int | None = None,
    scan_workers: int = 1,
    scan_prefetch: int | None = None,
    progress_callback: RecoveryProgressCallback | None = None,
) -> RecoveryEvaluation:
    """Rebuild unresolved blocks without persisting either source or projection."""

    bounds = (
        None
        if last_sequence_number is None
        else SequenceBounds(
            first_sequence_number,
            last_sequence_number,
            sequence_direction,
        )
    )
    planned_source_groups = (
        source_groups
        if bounds is None
        else prepare_source_groups_for_bounds(source_groups, bounds=bounds)
    )
    blocks = plan_recovery_blocks(planned_source_groups)
    if not blocks:
        raise SelectionContractError(
            "IMAGE_SELECTION_RECOVERY_NOT_REQUIRED",
            "The source run has no unresolved range-review groups.",
        )
    prepared = tuple((block, prepare_recovery_block(block)) for block in blocks)
    candidate_count = sum(len(block_input.sources) for _, block_input in prepared)
    completed_candidates = 0
    scan_failure_count = 0
    verification_count = 0
    recovered: list[RecoveredBlock] = []
    for block_number, (block, block_input) in enumerate(prepared, start=1):
        sink = RecoveryBlockAuditSink()
        local = FastImageSelector(
            manifest,
            scan_workers=scan_workers,
            scan_prefetch=scan_prefetch,
        ).select(
            block_input.sources,
            analyzer=analyzer,
            verifier=verifier,
            audit_sink=sink,
            sequence_direction=sequence_direction,
            first_sequence_number=first_sequence_number,
            # ``first_sequence_number`` remains the global modulo-alignment
            # origin. A local block must never pretend its first group is the
            # first group of the complete source run.
            anchor_first_group=False,
        )
        recovered.append(
            restore_recovered_block(
                block=block,
                block_input=block_input,
                groups=_partitioned_recovery_groups(
                    require_representative_range_evidence(
                        local.groups,
                        allow_exact_gap=(
                            (
                                manifest.algorithm_version
                                in {
                                    CARDINALITY_GUARDED_SELECTOR_VERSION,
                                    CARDINALITY_PARTITIONED_SELECTOR_VERSION,
                                    ADAPTIVE_CARDINALITY_SELECTOR_VERSION,
                                    STAGED_OCR_SELECTOR_VERSION,
                                    QUANTILE_SAMPLED_SELECTOR_VERSION,
                                    SINGLE_FRAME_EARLY_EXIT_SELECTOR_VERSION,
                                }
                                or manifest.algorithm_version in PROOF_FIRST_SELECTOR_VERSIONS
                            )
                            and bounds is not None
                        ),
                    )
                ),
                observations=sink.observations,
            )
        )
        completed_candidates += len(block_input.sources)
        scan_failure_count += local.scan_failure_count
        verification_count += local.verification_count
        if progress_callback is not None:
            progress_callback(
                RecoveryEvaluationProgress(
                    completed_blocks=block_number,
                    block_count=len(prepared),
                    completed_candidates=completed_candidates,
                    candidate_count=candidate_count,
                    scan_failure_count=scan_failure_count,
                    verification_count=verification_count,
                )
            )
    projection = assemble_recovery_projection(
        planned_source_groups,
        tuple(recovered),
        reconcile_duplicates=bounds is None,
    )
    return RecoveryEvaluation(
        projection=(
            projection
            if bounds is None
            else reconcile_projection_to_sequence_bounds(
                projection,
                bounds=bounds,
                require_local_range_proof=(
                    manifest.algorithm_version in PROOF_FIRST_SELECTOR_VERSIONS
                ),
                allow_expected_sequence_confirmation=(
                    manifest.algorithm_version == SEQUENCE_VALIDATED_SELECTOR_VERSION
                ),
            )
        ),
        block_count=len(prepared),
        candidate_count=candidate_count,
        scan_failure_count=scan_failure_count,
        verification_count=verification_count,
    )


class RecoveryBlockAuditSink:
    """Capture one bounded block without mutating either durable run."""

    def __init__(self) -> None:
        self._observations: dict[int, CheapImageObservation] = {}

    @property
    def observations(self) -> tuple[CheapImageObservation, ...]:
        return tuple(self._observations[index] for index in sorted(self._observations))

    def candidate_scanned(
        self,
        observation: CheapImageObservation,
        *,
        group_order: int,
    ) -> None:
        del group_order
        existing = self._observations.setdefault(observation.source.order_index, observation)
        if existing != observation:
            raise SelectionContractError(
                "IMAGE_SELECTION_RECOVERY_OBSERVATION_MISMATCH",
                "One recovery source produced inconsistent scan observations.",
            )

    def checkpoint_saved(self, checkpoint: SelectorCheckpoint) -> None:
        del checkpoint

    def group_finalized(self, group: SelectionGroupResult) -> None:
        del group


def plan_recovery_blocks(
    groups: tuple[RecoverySourceGroup, ...],
    *,
    guard_count: int = 2,
) -> tuple[RecoveryBlock, ...]:
    """Return disjoint blocks around every consecutive RANGE_REQUIRED span."""

    if guard_count < 0:
        raise ValueError("guard_count must not be negative.")
    problem_indexes = [
        index
        for index, group in enumerate(groups)
        if group.result.status is SelectionGroupStatus.RANGE_REQUIRED
    ]
    if not problem_indexes:
        return ()

    raw: list[tuple[int, int]] = []
    cursor = 0
    while cursor < len(problem_indexes):
        first = problem_indexes[cursor]
        last = first
        cursor += 1
        while cursor < len(problem_indexes) and problem_indexes[cursor] == last + 1:
            last = problem_indexes[cursor]
            cursor += 1
        first = _expand_left(groups, first, guard_count)
        last = _expand_right(groups, last, guard_count)
        if raw and first <= raw[-1][1] + 1:
            raw[-1] = (raw[-1][0], max(raw[-1][1], last))
        else:
            raw.append((first, last))

    return tuple(
        RecoveryBlock(
            first_group_index=first,
            last_group_index=last,
            source_groups=groups[first : last + 1],
        )
        for first, last in raw
    )


def prepare_source_groups_for_bounds(
    groups: tuple[RecoverySourceGroup, ...],
    *,
    bounds: SequenceBounds,
) -> tuple[RecoverySourceGroup, ...]:
    """Turn every cardinality or grid disagreement into an explicit rebuild input."""

    assignment = _sequence_assignment(
        tuple(group.result for group in groups),
        bounds=bounds,
    )
    prepared: list[RecoverySourceGroup] = []
    for source_group, slot in zip(groups, assignment, strict=True):
        result = source_group.result
        if slot is None:
            prepared.append(
                replace(
                    source_group,
                    result=replace(
                        result,
                        status=SelectionGroupStatus.SKIPPED_EXISTING_RANGE,
                        selected_candidate=None,
                        top_candidates=(),
                        duplicate_of_group_order=None,
                    ),
                )
            )
            continue
        expected = bounds.range_for_group(slot)
        if result.status in _PROTECTED_USER_STATUSES:
            _require_expected_protected_range(result, expected)
            prepared.append(source_group)
            continue
        if (
            result.status is SelectionGroupStatus.AUTO_SELECTED
            and _same_range(result.range, expected)
            and result.selected_candidate is not None
        ):
            prepared.append(source_group)
            continue
        prepared.append(
            replace(
                source_group,
                result=replace(
                    result,
                    range=None,
                    status=SelectionGroupStatus.RANGE_REQUIRED,
                    selected_candidate=_demote_candidate(result.selected_candidate),
                    top_candidates=tuple(
                        replace(
                            candidate,
                            decision=CandidateDecision.ELIGIBLE,
                            recognized_range=None,
                        )
                        for candidate in result.top_candidates
                    ),
                    duplicate_of_group_order=None,
                ),
            )
        )
    return tuple(prepared)


def reconcile_projection_to_sequence_bounds(
    projection: RecoveryProjection,
    *,
    bounds: SequenceBounds,
    require_local_range_proof: bool = False,
    allow_expected_sequence_confirmation: bool = False,
) -> RecoveryProjection:
    """Enforce one logical owner for every group in the declared inclusive range."""

    if require_local_range_proof:
        return _reconcile_proof_first_projection(
            projection,
            bounds=bounds,
            allow_expected_sequence_confirmation=allow_expected_sequence_confirmation,
        )

    assignment = _sequence_assignment(projection.groups, bounds=bounds)
    owner_order_by_slot = {
        slot: group.group_order
        for group, slot in zip(projection.groups, assignment, strict=True)
        if slot is not None
    }
    normalized: list[SelectionGroupResult] = []
    kept_before = 0
    for group, slot in zip(projection.groups, assignment, strict=True):
        if slot is not None:
            normalized.append(
                _assign_cardinality_range(
                    group,
                    expected=bounds.range_for_group(slot),
                )
            )
            kept_before += 1
            continue
        recognized_slot = None if group.range is None else bounds.group_index_for_range(group.range)
        owner_slot = (
            recognized_slot
            if recognized_slot in owner_order_by_slot
            else min(max(kept_before - 1, 0), bounds.expected_group_count - 1)
        )
        owner_range = bounds.range_for_group(owner_slot)
        normalized.append(
            replace(
                group,
                range=owner_range,
                status=SelectionGroupStatus.SKIPPED_EXISTING_RANGE,
                selected_candidate=None,
                top_candidates=(),
                duplicate_of_group_order=owner_order_by_slot[owner_slot],
            )
        )

    owners = tuple(
        group
        for group in normalized
        if group.status is not SelectionGroupStatus.SKIPPED_EXISTING_RANGE
    )
    if len(owners) != bounds.expected_group_count:
        raise SelectionContractError(
            "IMAGE_SELECTION_GROUP_CARDINALITY_MISMATCH",
            "The recovered projection does not contain the expected number of groups.",
        )
    for index, group in enumerate(owners):
        if not _same_range(group.range, bounds.range_for_group(index)):
            raise SelectionContractError(
                "IMAGE_SELECTION_SEQUENCE_COVERAGE_MISMATCH",
                "The recovered projection does not cover the complete sequence grid.",
            )
    return replace(projection, groups=tuple(normalized))


def _reconcile_proof_first_projection(
    projection: RecoveryProjection,
    *,
    bounds: SequenceBounds,
    allow_expected_sequence_confirmation: bool,
) -> RecoveryProjection:
    """Validate proven ranges without manufacturing missing sequence ownership."""

    normalized: list[SelectionGroupResult] = []
    owner_order_by_range: dict[tuple[int, int], int] = {}
    for group in projection.groups:
        if group.status in _PROTECTED_USER_STATUSES:
            if group.range is not None and bounds.group_index_for_range(group.range) is None:
                raise SelectionContractError(
                    "IMAGE_SELECTION_PROTECTED_RANGE_CONFLICT",
                    "A protected user decision falls outside the declared sequence bounds.",
                )
            if group.range is not None:
                key = (group.range.start, group.range.end)
                if key in owner_order_by_range:
                    raise SelectionContractError(
                        "IMAGE_SELECTION_PROTECTED_RANGE_CONFLICT",
                        "Two protected user decisions claim the same sequence range.",
                    )
                owner_order_by_range[key] = group.group_order
            normalized.append(replace(group, duplicate_of_group_order=None))
            continue

        if (
            group.status is SelectionGroupStatus.SKIPPED_EXISTING_RANGE
            and group.range is not None
            and bounds.group_index_for_range(group.range) is not None
            and any(
                _same_range(candidate.recognized_range, group.range)
                and has_strong_local_range_proof(
                    candidate.recognized_range,
                    candidate.reason_codes,
                    minimum_confidence=0.90,
                    label_observations=candidate.range_label_observations,
                    require_position_evidence=True,
                )
                for candidate in group.top_candidates
            )
        ):
            key = (group.range.start, group.range.end)
            owner_order = owner_order_by_range.get(key)
            if owner_order is not None:
                normalized.append(
                    replace(
                        group,
                        selected_candidate=None,
                        top_candidates=(),
                        duplicate_of_group_order=owner_order,
                    )
                )
                continue

        selected = group.selected_candidate
        proven = (
            group.status is SelectionGroupStatus.AUTO_SELECTED
            and group.range is not None
            and selected is not None
            and _same_range(selected.recognized_range, group.range)
            and has_strong_local_range_proof(
                selected.recognized_range,
                selected.reason_codes,
                minimum_confidence=0.90,
                label_observations=selected.range_label_observations,
                require_position_evidence=True,
            )
            and bounds.group_index_for_range(group.range) is not None
        )
        if proven:
            assert group.range is not None
            key = (group.range.start, group.range.end)
            owner_order = owner_order_by_range.get(key)
            if owner_order is None:
                owner_order_by_range[key] = group.group_order
                normalized.append(replace(group, duplicate_of_group_order=None))
            else:
                normalized.append(
                    replace(
                        group,
                        status=SelectionGroupStatus.SKIPPED_EXISTING_RANGE,
                        selected_candidate=None,
                        top_candidates=(),
                        duplicate_of_group_order=owner_order,
                    )
                )
            continue

        candidates = _proof_first_review_candidates(group)
        if group.status is SelectionGroupStatus.SKIPPED_UNREADABLE:
            normalized.append(
                replace(
                    group,
                    range=None,
                    selected_candidate=None,
                    top_candidates=candidates,
                    duplicate_of_group_order=None,
                )
            )
            continue
        normalized.append(
            replace(
                group,
                range=None,
                status=SelectionGroupStatus.RANGE_REQUIRED,
                selected_candidate=(candidates[0] if candidates else None),
                top_candidates=candidates,
                duplicate_of_group_order=None,
            )
        )

    return replace(
        projection,
        groups=(
            _promote_expected_sequence_matches(
                tuple(normalized),
                bounds=bounds,
            )
            if allow_expected_sequence_confirmation
            else tuple(normalized)
        ),
    )


def _proof_first_review_candidates(
    group: SelectionGroupResult,
) -> tuple[CandidateResult, ...]:
    candidates = (
        () if group.selected_candidate is None else (group.selected_candidate,)
    ) + group.top_candidates
    result: list[CandidateResult] = []
    seen: set[tuple[int, str]] = set()
    for candidate in candidates:
        identity = (candidate.source.order_index, candidate.source.checksum_sha256)
        if identity in seen:
            continue
        seen.add(identity)
        result.append(replace(candidate, decision=CandidateDecision.ELIGIBLE))
    return tuple(result)


def _promote_expected_sequence_matches(
    groups: tuple[SelectionGroupResult, ...],
    *,
    bounds: SequenceBounds,
) -> tuple[SelectionGroupResult, ...]:
    """Use ordered slots as hypotheses, never as unverified canonical truth."""

    if len(groups) < bounds.expected_group_count:
        return groups
    locked_slots: dict[int, int] = {}
    for physical_index, group in enumerate(groups):
        selected = group.selected_candidate
        if (
            group.status is SelectionGroupStatus.AUTO_SELECTED
            and group.range is not None
            and selected is not None
            and _same_range(selected.recognized_range, group.range)
            and has_strong_local_range_proof(
                selected.recognized_range,
                selected.reason_codes,
                minimum_confidence=0.90,
                label_observations=selected.range_label_observations,
                require_position_evidence=True,
            )
        ):
            slot = bounds.group_index_for_range(group.range)
            if slot is not None:
                locked_slots[physical_index] = slot

    try:
        assignment = _sequence_assignment(
            groups,
            bounds=bounds,
            locked_slots=locked_slots,
            allow_skipped_owners=False,
        )
    except SelectionContractError:
        # Conflicting OCR anchors make the ordered hypothesis ambiguous. Keep the
        # existing proof-first result for manual range review instead of failing
        # the complete run or manufacturing sequence ownership.
        return groups
    owner_physical_by_slot = {
        slot: physical_index
        for physical_index, slot in enumerate(assignment)
        if slot is not None
    }
    owner_order_by_slot = {
        slot: groups[physical_index].group_order
        for slot, physical_index in owner_physical_by_slot.items()
    }
    promoted: list[SelectionGroupResult] = []
    for physical_index, (group, slot) in enumerate(zip(groups, assignment, strict=True)):
        if slot is None:
            recognized_slot = (
                None if group.range is None else bounds.group_index_for_range(group.range)
            )
            owner_slot = (
                recognized_slot
                if recognized_slot in owner_order_by_slot
                else min(
                    owner_physical_by_slot,
                    key=lambda candidate_slot: (
                        abs(owner_physical_by_slot[candidate_slot] - physical_index),
                        owner_physical_by_slot[candidate_slot] > physical_index,
                        candidate_slot,
                    ),
                )
            )
            promoted.append(
                replace(
                    group,
                    range=bounds.range_for_group(owner_slot),
                    status=SelectionGroupStatus.SKIPPED_EXISTING_RANGE,
                    selected_candidate=None,
                    top_candidates=(),
                    duplicate_of_group_order=owner_order_by_slot[owner_slot],
                )
            )
            continue
        if group.status is not SelectionGroupStatus.RANGE_REQUIRED:
            promoted.append(group)
            continue
        expected = bounds.range_for_group(slot)
        candidate = _expected_sequence_candidate(group, expected=expected)
        if candidate is None:
            promoted.append(group)
            continue
        selected = replace(
            candidate,
            decision=CandidateDecision.SELECTED_AUTOMATIC,
            recognized_range=SequenceRange(
                expected.start,
                expected.end,
                max(0.90, candidate.recognized_range.confidence)
                if candidate.recognized_range is not None
                else 0.90,
            ),
            reason_codes=tuple(
                dict.fromkeys((*candidate.reason_codes, "RANGE_EXPECTED_SEQUENCE_CONFIRMED"))
            ),
        )
        identity = (selected.source.order_index, selected.source.checksum_sha256)
        candidates = tuple(
            selected if (item.source.order_index, item.source.checksum_sha256) == identity else item
            for item in _proof_first_review_candidates(group)
        )
        promoted.append(
            replace(
                group,
                range=selected.recognized_range,
                status=SelectionGroupStatus.AUTO_SELECTED,
                selected_candidate=selected,
                top_candidates=candidates,
                duplicate_of_group_order=None,
            )
        )
    return tuple(promoted)


def _expected_sequence_candidate(
    group: SelectionGroupResult,
    *,
    expected: SequenceRange,
) -> CandidateResult | None:
    usable: list[CandidateResult] = []
    blocking_reasons = {
        "IMAGE_OCCLUDED",
        "IMAGE_SELECTION_VERIFY_GEOMETRY_FAILED",
        "QUALITY_BLUR",
        "QUALITY_LAYOUT_BLUR",
        "RANGE_CARDINALITY_INFERRED",
        "RANGE_CONFLICT",
        "RANGE_EXACT_GAP_INFERRED",
        "RANGE_INFERRED_FROM_BOUNDED_GAP",
        "RANGE_OCR_FUSED_EVIDENCE_CONFLICT",
        "RANGE_OWNER_ANCHOR",
    }
    for candidate in _proof_first_review_candidates(group):
        geometry_support = (
            group.board_count_consensus is not None
            and group.board_count_consensus >= 5
        ) or "RANGE_OCR_LAYOUT_ANCHORED_TWO_LABEL" in candidate.reason_codes
        if not geometry_support:
            continue
        if candidate.recognized_range is not None and not _same_range(
            candidate.recognized_range,
            expected,
        ):
            continue
        if any(
            reason in blocking_reasons or reason.startswith("IMAGE_SELECTION_SCAN_")
            for reason in candidate.reason_codes
        ):
            continue
        strong_observations = tuple(
            observation
            for observation in candidate.range_label_observations
            if observation.confidence >= 0.82
        )
        if any(
            observation.position_index >= expected.board_count
            or observation.sequence_number != expected.start + observation.position_index
            for observation in strong_observations
        ):
            continue
        if len({observation.position_index for observation in strong_observations}) < 2:
            continue
        usable.append(candidate)
    if not usable:
        return None
    return min(
        usable,
        key=lambda candidate: (
            -len(
                {
                    observation.position_index
                    for observation in candidate.range_label_observations
                    if observation.confidence >= 0.82
                }
            ),
            -candidate.quality.overall_score,
            candidate.source.order_index,
            candidate.source.checksum_sha256,
        ),
    )


def _sequence_assignment(
    groups: tuple[SelectionGroupResult, ...],
    *,
    bounds: SequenceBounds,
    locked_slots: dict[int, int] | None = None,
    allow_skipped_owners: bool = True,
) -> tuple[int | None, ...]:
    """Choose exactly N ordered owners while preserving hard user decisions."""

    expected = bounds.expected_group_count
    extra = len(groups) - expected
    if extra < 0:
        raise SelectionContractError(
            "IMAGE_SELECTION_GROUP_CARDINALITY_UNDERFLOW",
            "There are fewer detected image groups than the declared sequence requires.",
        )
    total_sources = sum(max(1, group.source_count) for group in groups)
    max_skippable_sources = max(
        2,
        (2 * total_sources + expected - 1) // expected,
    )
    previous: list[float] = [float(_INFINITE_ASSIGNMENT_COST)] * (extra + 1)
    previous[0] = 0.0
    history: list[list[tuple[int, bool] | None]] = []
    for physical_index, group in enumerate(groups):
        current: list[float] = [float(_INFINITE_ASSIGNMENT_COST)] * (extra + 1)
        back: list[tuple[int, bool] | None] = [None] * (extra + 1)
        for skipped in range(min(physical_index, extra) + 1):
            prior = previous[skipped]
            if prior >= _INFINITE_ASSIGNMENT_COST:
                continue
            slot = physical_index - skipped
            if slot < expected:
                locked_slot = None if locked_slots is None else locked_slots.get(physical_index)
                keep_cost = (
                    _INFINITE_ASSIGNMENT_COST
                    if (locked_slot is not None and locked_slot != slot)
                    or (
                        not allow_skipped_owners
                        and group.status is SelectionGroupStatus.SKIPPED_EXISTING_RANGE
                    )
                    else _keep_assignment_cost(
                        group,
                        expected=bounds.range_for_group(slot),
                        slot=slot,
                        bounds=bounds,
                    )
                )
                if prior + keep_cost < current[skipped]:
                    current[skipped] = prior + keep_cost
                    back[skipped] = (skipped, True)
            if (
                skipped < extra
                and group.status not in _PROTECTED_USER_STATUSES
                and (
                    group.source_count <= max_skippable_sources
                    or group.status is SelectionGroupStatus.SKIPPED_EXISTING_RANGE
                )
            ):
                skip_cost = _skip_assignment_cost(group, max_skippable_sources)
                if prior + skip_cost < current[skipped + 1]:
                    current[skipped + 1] = prior + skip_cost
                    back[skipped + 1] = (skipped, False)
        previous = current
        history.append(back)
    if previous[extra] >= _INFINITE_ASSIGNMENT_COST:
        raise SelectionContractError(
            "IMAGE_SELECTION_GROUP_CARDINALITY_CONFLICT",
            "The expected group count conflicts with protected decisions or merged groups.",
        )

    assignment: list[int | None] = [None] * len(groups)
    skipped = extra
    for physical_index in range(len(groups) - 1, -1, -1):
        step = history[physical_index][skipped]
        if step is None:
            raise SelectionContractError(
                "IMAGE_SELECTION_GROUP_CARDINALITY_CONFLICT",
                "The sequence assignment could not be reconstructed.",
            )
        prior_skipped, kept = step
        if kept:
            assignment[physical_index] = physical_index - skipped
        skipped = prior_skipped
    return tuple(assignment)


def _keep_assignment_cost(
    group: SelectionGroupResult,
    *,
    expected: SequenceRange,
    slot: int,
    bounds: SequenceBounds,
) -> float:
    if group.status in _PROTECTED_USER_STATUSES:
        return 0.0 if _same_range(group.range, expected) else _INFINITE_ASSIGNMENT_COST
    if group.range is None:
        return 3.0
    if _same_range(group.range, expected):
        return 0.0
    anchor = group.range.start if bounds.direction == "ascending" else group.range.end
    delta = (
        (anchor - bounds.first) / bounds.group_size
        if bounds.direction == "ascending"
        else (bounds.first - anchor) / bounds.group_size
    )
    return 2.0 + abs(delta - slot) * 3.0


def _skip_assignment_cost(group: SelectionGroupResult, limit: int) -> float:
    base = {
        SelectionGroupStatus.SKIPPED_EXISTING_RANGE: 0.0,
        SelectionGroupStatus.RANGE_REQUIRED: 12.0,
        SelectionGroupStatus.AUTO_SELECTED: 30.0,
    }.get(group.status, 40.0)
    return base + max(1, group.source_count) / limit


def _assign_cardinality_range(
    group: SelectionGroupResult,
    *,
    expected: SequenceRange,
) -> SelectionGroupResult:
    if group.status in _PROTECTED_USER_STATUSES:
        _require_expected_protected_range(group, expected)
        return replace(group, duplicate_of_group_order=None)
    if group.status in {
        SelectionGroupStatus.SKIPPED_UNREADABLE,
        SelectionGroupStatus.REJECTED_BY_USER,
    }:
        return replace(group, range=expected, duplicate_of_group_order=None)

    candidate = _cardinality_candidate(group, expected=expected)
    if candidate is None:
        return replace(
            group,
            range=expected,
            status=SelectionGroupStatus.MANUAL_REQUIRED,
            selected_candidate=None,
            duplicate_of_group_order=None,
        )
    selected = replace(
        candidate,
        decision=CandidateDecision.SELECTED_AUTOMATIC,
        recognized_range=expected,
        reason_codes=tuple(
            dict.fromkeys(
                (
                    *(
                        reason
                        for reason in candidate.reason_codes
                        if reason not in _FORBIDDEN_RECOVERY_RANGE_REASONS
                    ),
                    _CARDINALITY_RANGE_REASON,
                )
            )
        ),
    )
    identity = (selected.source.order_index, selected.source.checksum_sha256)
    top_candidates = tuple(
        selected
        if (candidate.source.order_index, candidate.source.checksum_sha256) == identity
        else candidate
        for candidate in group.top_candidates
    )
    if not any(
        (candidate.source.order_index, candidate.source.checksum_sha256) == identity
        for candidate in top_candidates
    ):
        top_candidates = (selected, *top_candidates)
    return replace(
        group,
        range=expected,
        status=SelectionGroupStatus.AUTO_SELECTED,
        selected_candidate=selected,
        top_candidates=top_candidates,
        duplicate_of_group_order=None,
    )


def _cardinality_candidate(
    group: SelectionGroupResult,
    *,
    expected: SequenceRange,
) -> CandidateResult | None:
    candidates = (
        () if group.selected_candidate is None else (group.selected_candidate,)
    ) + group.top_candidates
    seen: set[tuple[int, str]] = set()
    usable: list[CandidateResult] = []
    for candidate in candidates:
        identity = (candidate.source.order_index, candidate.source.checksum_sha256)
        if identity in seen:
            continue
        seen.add(identity)
        if candidate.decision is CandidateDecision.REJECTED:
            continue
        if candidate.recognized_range is not None and not _same_range(
            candidate.recognized_range,
            expected,
        ):
            continue
        if any(
            reason in _CARDINALITY_BLOCKING_REASONS or reason.startswith("IMAGE_SELECTION_SCAN_")
            for reason in candidate.reason_codes
        ):
            continue
        usable.append(candidate)
    if not usable:
        return None
    return min(
        usable,
        key=lambda candidate: (
            candidate.recognized_range is None,
            -candidate.quality.overall_score,
            candidate.source.order_index,
            candidate.source.checksum_sha256,
        ),
    )


def _demote_candidate(candidate: CandidateResult | None) -> CandidateResult | None:
    if candidate is None:
        return None
    return replace(candidate, decision=CandidateDecision.ELIGIBLE, recognized_range=None)


def _require_expected_protected_range(
    group: SelectionGroupResult,
    expected: SequenceRange,
) -> None:
    if not _same_range(group.range, expected):
        raise SelectionContractError(
            "IMAGE_SELECTION_PROTECTED_RANGE_CONFLICT",
            "A protected user decision conflicts with the declared sequence bounds.",
        )


def _same_range(first: SequenceRange | None, second: SequenceRange) -> bool:
    return first is not None and (first.start, first.end) == (second.start, second.end)


def prepare_recovery_block(block: RecoveryBlock) -> RecoveryBlockInput:
    """Flatten and checksum-deduplicate one block into engine-local ordering."""

    values: list[tuple[ImageSelectionSource, UUID]] = []
    seen_checksums: set[str] = set()
    for group in block.source_groups:
        for source in group.sources:
            if source.checksum_sha256 in seen_checksums:
                continue
            seen_checksums.add(source.checksum_sha256)
            values.append((source, group.origin_group_id))
    values.sort(key=lambda value: (value[0].order_index, value[0].checksum_sha256))
    if not values:
        raise SelectionContractError(
            "IMAGE_SELECTION_RECOVERY_SOURCE_EMPTY",
            "An unresolved recovery block has no preserved candidates.",
        )
    originals = tuple(source for source, _ in values)
    return RecoveryBlockInput(
        sources=tuple(replace(source, order_index=index) for index, source in enumerate(originals)),
        original_sources=originals,
        origin_group_ids=tuple(origin for _, origin in values),
    )


def restore_recovered_block(
    *,
    block: RecoveryBlock,
    block_input: RecoveryBlockInput,
    groups: tuple[SelectionGroupResult, ...],
    observations: tuple[CheapImageObservation, ...],
) -> RecoveredBlock:
    """Restore global source identities and deterministically partition galleries."""

    original_by_local = {index: source for index, source in enumerate(block_input.original_sources)}
    observation_by_local = {
        observation.source.order_index: observation for observation in observations
    }
    if set(observation_by_local) != set(original_by_local):
        raise SelectionContractError(
            "IMAGE_SELECTION_RECOVERY_OBSERVATION_MISMATCH",
            "Recovery did not analyze every preserved source exactly once.",
        )
    ordered_observations = tuple(
        replace(
            observation_by_local[index],
            source=original_by_local[index],
        )
        for index in range(len(original_by_local))
    )
    covered_source_count = sum(group.source_count for group in groups)
    if covered_source_count != len(ordered_observations):
        raise SelectionContractError(
            "IMAGE_SELECTION_RECOVERY_PARTITION_MISMATCH",
            "Recovered group sizes cover "
            f"{covered_source_count} candidates as "
            f"{[group.source_count for group in groups]}; "
            f"expected {len(ordered_observations)}.",
        )

    restored_groups: list[SelectionGroupResult] = []
    restored_sources: list[tuple[CheapImageObservation, ...]] = []
    origins: list[UUID] = []
    offset = 0
    for group in groups:
        group_observations = ordered_observations[offset : offset + group.source_count]
        offset += group.source_count
        restored = replace(
            group,
            selected_candidate=(
                None
                if group.selected_candidate is None
                else _restore_candidate(group.selected_candidate, original_by_local)
            ),
            top_candidates=tuple(
                _restore_candidate(candidate, original_by_local)
                for candidate in group.top_candidates
            ),
        )
        restored_groups.append(restored)
        restored_sources.append(group_observations)
        origin_indexes = {
            block_input.original_sources.index(observation.source)
            for observation in group_observations
        }
        origins.append(
            _representative_origin(
                restored,
                group_observations,
                block_input,
                origin_indexes,
            )
        )
    return RecoveredBlock(
        block=block,
        groups=tuple(restored_groups),
        group_sources=tuple(restored_sources),
        origin_group_ids=tuple(origins),
    )


def require_representative_range_evidence(
    groups: tuple[SelectionGroupResult, ...],
    *,
    allow_exact_gap: bool = False,
) -> tuple[SelectionGroupResult, ...]:
    """Fail closed when an automatic range was borrowed or inferred."""

    normalized: list[SelectionGroupResult] = []
    for group in groups:
        if group.status is not SelectionGroupStatus.AUTO_SELECTED:
            normalized.append(group)
            continue
        selected = group.selected_candidate
        selected_range = None if selected is None else selected.recognized_range
        group_key = None if group.range is None else (group.range.start, group.range.end)
        selected_key = (
            None if selected_range is None else (selected_range.start, selected_range.end)
        )
        forbidden_reasons = (
            _FORBIDDEN_RECOVERY_RANGE_REASONS - {"RANGE_EXACT_GAP_INFERRED"}
            if allow_exact_gap
            else _FORBIDDEN_RECOVERY_RANGE_REASONS
        )
        forbidden_reason = selected is not None and any(
            reason in forbidden_reasons for reason in selected.reason_codes
        )
        if (
            selected is not None
            and group_key is not None
            and selected_key == group_key
            and not forbidden_reason
        ):
            normalized.append(group)
            continue

        demoted = (
            None
            if selected is None
            else replace(
                selected,
                decision=CandidateDecision.ELIGIBLE,
                recognized_range=None,
                reason_codes=tuple(
                    dict.fromkeys(
                        (
                            *selected.reason_codes,
                            "RECOVERY_REPRESENTATIVE_RANGE_EVIDENCE_REQUIRED",
                        )
                    )
                ),
            )
        )
        selected_identity = (
            None
            if selected is None
            else (selected.source.order_index, selected.source.checksum_sha256)
        )
        normalized.append(
            replace(
                group,
                range=None,
                status=SelectionGroupStatus.RANGE_REQUIRED,
                selected_candidate=demoted,
                top_candidates=tuple(
                    demoted
                    if demoted is not None
                    and selected_identity
                    == (candidate.source.order_index, candidate.source.checksum_sha256)
                    else candidate
                    for candidate in group.top_candidates
                ),
            )
        )
    return tuple(normalized)


def _partitioned_recovery_groups(
    groups: tuple[SelectionGroupResult, ...],
) -> tuple[SelectionGroupResult, ...]:
    """Drop empty duplicate markers already counted by their recovered owner."""

    return tuple(
        group
        for group in groups
        if not (
            group.status is SelectionGroupStatus.SKIPPED_EXISTING_RANGE
            and group.duplicate_of_group_order is not None
            and group.selected_candidate is None
            and not group.top_candidates
        )
    )


def assemble_recovery_projection(
    source_groups: tuple[RecoverySourceGroup, ...],
    recovered_blocks: tuple[RecoveredBlock, ...],
    *,
    reconcile_duplicates: bool = True,
) -> RecoveryProjection:
    """Replace rebuilt intervals, preserve all other groups, and renumber once."""

    by_first = {item.block.first_group_index: item for item in recovered_blocks}
    values: list[
        tuple[
            SelectionGroupResult,
            tuple[CheapImageObservation, ...],
            UUID,
            tuple[str, int, int],
            tuple[str, int, int] | None,
        ]
    ] = []
    index = 0
    while index < len(source_groups):
        recovered = by_first.get(index)
        if recovered is not None:
            block_number = recovered.block.first_group_index
            for group, gallery, origin in zip(
                recovered.groups,
                recovered.group_sources,
                recovered.origin_group_ids,
                strict=True,
            ):
                duplicate = group.duplicate_of_group_order
                values.append(
                    (
                        group,
                        gallery,
                        origin,
                        ("block", block_number, group.group_order),
                        (None if duplicate is None else ("block", block_number, duplicate)),
                    )
                )
            index = recovered.block.last_group_index + 1
            continue
        source = source_groups[index]
        duplicate = source.result.duplicate_of_group_order
        values.append(
            (
                source.result,
                (),
                source.origin_group_id,
                ("source", 0, source.result.group_order),
                None if duplicate is None else ("source", 0, duplicate),
            )
        )
        index += 1

    order_map = {key: order for order, (_, _, _, key, _) in enumerate(values)}
    groups: list[SelectionGroupResult] = []
    galleries: dict[int, tuple[CheapImageObservation, ...]] = {}
    origins: dict[int, UUID] = {}
    for order, (group, gallery, origin, _, duplicate_key) in enumerate(values):
        normalized = replace(
            group,
            group_order=order,
            duplicate_of_group_order=(
                None if duplicate_key is None else order_map.get(duplicate_key)
            ),
        )
        groups.append(normalized)
        if gallery:
            galleries[order] = gallery
        origins[order] = origin
    if reconcile_duplicates:
        groups = list(_reconcile_duplicate_output_ranges(tuple(groups)))
    return RecoveryProjection(
        groups=tuple(groups),
        group_sources=galleries,
        origin_group_ids=origins,
    )


def _reconcile_duplicate_output_ranges(
    groups: tuple[SelectionGroupResult, ...],
) -> tuple[SelectionGroupResult, ...]:
    """Keep one deterministic output owner when independent blocks overlap."""

    by_range: dict[tuple[int, int], list[int]] = {}
    for index, group in enumerate(groups):
        if group.status not in _OUTPUT_STATUSES or group.range is None:
            continue
        by_range.setdefault((group.range.start, group.range.end), []).append(index)

    normalized = list(groups)
    for indexes in by_range.values():
        if len(indexes) < 2:
            continue
        protected = [index for index in indexes if groups[index].status in _PROTECTED_USER_STATUSES]
        if len(protected) > 1:
            # Two owner decisions cannot be discarded automatically. The dry-run
            # structural gate will keep this conflict fail-closed.
            continue
        owner_index = protected[0] if protected else indexes[0]
        owner_order = groups[owner_index].group_order
        for index in indexes:
            if index == owner_index:
                continue
            duplicate = groups[index]
            normalized[index] = replace(
                duplicate,
                status=SelectionGroupStatus.SKIPPED_EXISTING_RANGE,
                selected_candidate=None,
                top_candidates=(),
                duplicate_of_group_order=owner_order,
            )
    return tuple(normalized)


def _expand_left(
    groups: tuple[RecoverySourceGroup, ...],
    first: int,
    guard_count: int,
) -> int:
    remaining = guard_count
    cursor = first
    while cursor > 0 and remaining:
        candidate = groups[cursor - 1]
        if candidate.result.status in _PROTECTED_USER_STATUSES:
            break
        if candidate.result.status is not SelectionGroupStatus.AUTO_SELECTED:
            break
        cursor -= 1
        remaining -= 1
    return cursor


def _expand_right(
    groups: tuple[RecoverySourceGroup, ...],
    last: int,
    guard_count: int,
) -> int:
    remaining = guard_count
    cursor = last
    while cursor + 1 < len(groups) and remaining:
        candidate = groups[cursor + 1]
        if candidate.result.status in _PROTECTED_USER_STATUSES:
            break
        if candidate.result.status is not SelectionGroupStatus.AUTO_SELECTED:
            break
        cursor += 1
        remaining -= 1
    return cursor


def _restore_candidate(
    candidate: CandidateResult,
    original_by_local: dict[int, ImageSelectionSource],
) -> CandidateResult:
    try:
        source = original_by_local[candidate.source.order_index]
    except KeyError as error:
        raise SelectionContractError(
            "IMAGE_SELECTION_RECOVERY_CANDIDATE_MISMATCH",
            "A recovered representative is outside its preserved source block.",
        ) from error
    return replace(candidate, source=source)


def _representative_origin(
    group: SelectionGroupResult,
    observations: tuple[CheapImageObservation, ...],
    block_input: RecoveryBlockInput,
    origin_indexes: set[int],
) -> UUID:
    if group.selected_candidate is not None:
        selected_order = group.selected_candidate.source.order_index
        for index in origin_indexes:
            if block_input.original_sources[index].order_index == selected_order:
                return block_input.origin_group_ids[index]
    if observations:
        first_order = observations[0].source.order_index
        for index in origin_indexes:
            if block_input.original_sources[index].order_index == first_order:
                return block_input.origin_group_ids[index]
    raise SelectionContractError(
        "IMAGE_SELECTION_RECOVERY_PROVENANCE_MISSING",
        "A recovered group has no source-group provenance.",
    )


__all__ = [
    "RecoveredBlock",
    "RecoveryBlock",
    "RecoveryBlockAuditSink",
    "RecoveryBlockInput",
    "RecoveryEvaluation",
    "RecoveryEvaluationProgress",
    "RecoveryProjection",
    "RecoveryProgressCallback",
    "RecoverySourceGroup",
    "assemble_recovery_projection",
    "evaluate_recovery",
    "plan_recovery_blocks",
    "prepare_source_groups_for_bounds",
    "prepare_recovery_block",
    "reconcile_projection_to_sequence_bounds",
    "require_representative_range_evidence",
    "restore_recovered_block",
]
