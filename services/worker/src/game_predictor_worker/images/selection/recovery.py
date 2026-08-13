"""Pure planning helpers for immutable unresolved-range recovery runs."""

from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import UUID

from .contracts import (
    CandidateResult,
    CheapImageObservation,
    ImageSelectionSource,
    SelectionContractError,
    SelectionGroupResult,
    SelectionGroupStatus,
)

_PROTECTED_USER_STATUSES = {
    SelectionGroupStatus.MANUALLY_SELECTED,
    SelectionGroupStatus.MISSING_IMAGE,
    SelectionGroupStatus.RANGE_CONFIRMED,
    SelectionGroupStatus.REJECTED_BY_USER,
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
        sources=tuple(
            replace(source, order_index=index) for index, source in enumerate(originals)
        ),
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

    original_by_local = {
        index: source for index, source in enumerate(block_input.original_sources)
    }
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
                        (
                            None
                            if duplicate is None
                            else ("block", block_number, duplicate)
                        ),
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
    return RecoveryProjection(
        groups=tuple(groups),
        group_sources=galleries,
        origin_group_ids=origins,
    )


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
    "RecoveryBlockInput",
    "RecoveryProjection",
    "RecoverySourceGroup",
    "assemble_recovery_projection",
    "plan_recovery_blocks",
    "prepare_recovery_block",
    "restore_recovered_block",
]
