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
)
from .engine import FastImageSelector
from .manifest import SelectorManifest

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


def evaluate_recovery(
    source_groups: tuple[RecoverySourceGroup, ...],
    *,
    manifest: SelectorManifest,
    analyzer: CheapImageAnalyzer,
    verifier: CandidateVerifier,
    sequence_direction: str,
    first_sequence_number: int,
    scan_workers: int = 1,
    scan_prefetch: int | None = None,
    progress_callback: RecoveryProgressCallback | None = None,
) -> RecoveryEvaluation:
    """Rebuild unresolved blocks without persisting either source or projection."""

    blocks = plan_recovery_blocks(source_groups)
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
                groups=require_representative_range_evidence(local.groups),
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
    return RecoveryEvaluation(
        projection=assemble_recovery_projection(source_groups, tuple(recovered)),
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
    if sum(group.source_count for group in groups) != len(ordered_observations):
        raise SelectionContractError(
            "IMAGE_SELECTION_RECOVERY_PARTITION_MISMATCH",
            "Recovered group sizes do not cover the candidate block exactly once.",
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
        forbidden_reason = selected is not None and any(
            reason in _FORBIDDEN_RECOVERY_RANGE_REASONS for reason in selected.reason_codes
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


def assemble_recovery_projection(
    source_groups: tuple[RecoverySourceGroup, ...],
    recovered_blocks: tuple[RecoveredBlock, ...],
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
    "prepare_recovery_block",
    "require_representative_range_evidence",
    "restore_recovered_block",
]
