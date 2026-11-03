"""Deterministic protected islands for the incremental correction policy.

The bootstrap uses the legacy bounded exact solver. Once controls suffice,
existing protections are anchors and additional labelled components may train.
This policy does not claim the legacy 70/15/15 optimum.
"""

from collections import defaultdict
from collections.abc import Iterable

from .grid_correction_split import (
    BUFFER_PHOTOS,
    ROLES,
    CorrectionRoleCount,
    CorrectionSplitError,
    CorrectionSplitResult,
    CorrectionSplitSource,
    _prepare,
    _validate,
    _Work,
    solve_correction_split,
)


def solve_incremental_split(
    sources: Iterable[CorrectionSplitSource], *, max_work: int = 3_000_000
) -> CorrectionSplitResult:
    values = tuple(sorted(sources, key=lambda item: item.source_id))
    if not isinstance(max_work, int) or isinstance(max_work, bool) or max_work < 1:
        raise CorrectionSplitError("GRID_CORRECTION_SPLIT_INVALID", "Invalid work budget.")
    if len(values) > 5000:
        raise CorrectionSplitError("GRID_CORRECTION_SPLIT_WORK_LIMIT", "Source limit exceeded.")
    _validate(values)
    copies, components, orders, allowed, boards, _ = _prepare(values)
    work = _Work(max_work)
    members: dict[str, set[str]] = defaultdict(set)
    pending_photos = {copies.find(s.source_id) for s in values if s.pending_correction}
    for photo in boards:
        members[components.find(photo)].add(photo)
    roles: dict[str, int] = {
        group: next(iter(permitted)) for group, permitted in allowed.items() if len(permitted) == 1
    }

    def counts() -> tuple[CorrectionRoleCount, ...]:
        return tuple(
            CorrectionRoleCount(
                name,
                sum(n > 0 and roles.get(components.find(p)) == i for p, n in boards.items()),
                sum(n for p, n in boards.items() if roles.get(components.find(p)) == i),
            )
            for i, name in enumerate(ROLES)
        )

    if any(c.photos < 5 or c.boards < 15 for c in counts()[1:]):
        initial = solve_correction_split(values, max_work=max_work)
        # Keep complete labelled components, not unlabelled tails of a role.
        for source_id, initial_role in initial.assignments:
            group = components.find(source_id)
            if initial_role is not None and any(boards[p] for p in members[group]):
                roles[group] = ROLES.index(initial_role)
        for source_id in initial.buffers:
            roles[components.find(source_id)] = 3

    positions: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for order_index, order in enumerate(orders):
        for index, photo in enumerate(order.photo_keys):
            positions[components.find(photo)].append((order_index, index))

    def safe(group: str, role: int) -> bool:
        if role not in allowed[group]:
            return False
        for order_index, index in positions[group]:
            order = orders[order_index]
            # Components already collapse every unordered import.
            for neighbor in order.photo_keys[max(0, index - 10) : index + 11]:
                work.take()
                other = roles.get(components.find(neighbor))
                if other is not None and other < 3 and other != role:
                    return False
        return True

    for group in sorted(members):
        if group not in roles and any(boards[p] for p in members[group]) and safe(group, 0):
            roles[group] = 0

    missing_reserves: list[str] = []
    for role in (1, 2):
        existing = sum(
            len(photos)
            for group, photos in members.items()
            if roles.get(group) == role and not any(boards[p] for p in photos)
        )
        distances: list[list[int]] = []
        for order in orders:
            order_distances = [5001] * len(order.photo_keys)
            nearest = -5001
            for index, photo in enumerate(order.photo_keys):
                work.take()
                if roles.get(components.find(photo)) == role:
                    nearest = index
                order_distances[index] = min(5001, index - nearest)
            nearest = len(order.photo_keys) + 5001
            for index in range(len(order.photo_keys) - 1, -1, -1):
                work.take()
                if roles.get(components.find(order.photo_keys[index])) == role:
                    nearest = index
                order_distances[index] = min(order_distances[index], nearest - index)
            distances.append(order_distances)
        candidates: list[tuple[int, str]] = []
        for group, photos in members.items():
            if group in roles or any(boards[p] for p in photos) or not photos <= pending_photos:
                continue
            distance = min(
                (distances[order_index][index] for order_index, index in positions[group]),
                default=5001,
            )
            work.take(len(positions[group]))
            # Reuse already protected neighborhoods, never create remote holdouts.
            if distance <= BUFFER_PHOTOS:
                candidates.append((distance, group))
        for _, group in sorted(candidates):
            if existing + len(members[group]) <= 5 and safe(group, role):
                roles[group] = role
                existing += len(members[group])
        if existing < 5:
            missing_reserves.append(f"{ROLES[role]}_RESERVE_SHORTFALL")

    # Persist ten entire photos at every change of assigned role. Unassigned
    # photos elsewhere remain free; they are neither controls nor test results.
    for order in orders:
        previous: tuple[int, int] | None = None
        for index, photo in enumerate(order.photo_keys):
            current_role = roles.get(components.find(photo))
            if current_role is None or current_role == 3:
                continue
            if previous is not None and previous[1] != current_role:
                left = previous[0] + 1
                if index - left < BUFFER_PHOTOS:
                    raise CorrectionSplitError(
                        "GRID_CORRECTION_PROTECTION_CONFLICT", "Protected roles lack ten photos."
                    )
                start = left if current_role == 0 else index - BUFFER_PHOTOS
                for key in order.photo_keys[start : start + BUFFER_PHOTOS]:
                    group = components.find(key)
                    if roles.get(group, 3) != 3 or 3 not in allowed[group]:
                        raise CorrectionSplitError(
                            "GRID_CORRECTION_PROTECTION_CONFLICT", "A buffer splits a component."
                        )
                    roles[group] = 3
            previous = index, current_role

    measured = counts()
    if any(
        c.photos < (10 if c.role == "TRAIN" else 5) or c.boards < (30 if c.role == "TRAIN" else 15)
        for c in measured
    ):
        raise CorrectionSplitError(
            "GRID_CORRECTION_SPLIT_INFEASIBLE",
            "Protected islands do not meet role minima.",
            photos=sum(n > 0 for n in boards.values()),
            boards=sum(boards.values()),
        )
    representatives: dict[str, CorrectionSplitSource] = {}
    for value in values:
        photo = copies.find(value.source_id)
        prior = representatives.get(photo)
        if prior is None or (-value.eligible_boards, value.source_id) < (
            -prior.eligible_boards,
            prior.source_id,
        ):
            representatives[photo] = value
    return CorrectionSplitResult(
        assignments=tuple(
            (s.source_id, ROLES[r] if r is not None and r < 3 else None)
            for s in values
            for r in (roles.get(components.find(s.source_id)),)
        ),
        buffers=tuple(s.source_id for s in values if roles.get(components.find(s.source_id)) == 3),
        import_orders=orders,
        role_counts=measured,
        limitations=(
            "PHOTO_ONLY_NO_PROVEN_SESSION_INDEPENDENCE",
            "UNKNOWN_ANCESTOR_USE_NOT_PROVEN",
            *missing_reserves,
        ),
        objective_numerator=0,
        objective_denominator=1,
        representative_sources=tuple(sorted(s.source_id for s in representatives.values())),
        schema_version="grid-correction-split-v2",
        solver_version="protected-islands-v2",
    )
