"""Pure, bounded exact correction split; no inferred recording identities.

The versioned search space is one to three nonempty consecutive role blocks per
ordered import, each role at most once, with ten unique source photos between
blocks. An unordered import is indivisible. All candidates in this space are
examined or an explicit work-limit error is raised; no partial optimum escapes.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from fractions import Fraction
from itertools import permutations
from pathlib import PurePosixPath
from typing import Literal

from game_predictor_api.domain.image_geometry_v2 import (
    ImageGeometryContractError,
    is_sequence_range_filename_candidate,
    parse_attested_sequence_range_filename,
    sequence_attestation_checksum_sha256,
)

ROLES = ("TRAIN", "VALIDATION", "REGRESSION")
SPLIT_SCHEMA_VERSION = "grid-correction-split-v1"
SPLIT_SOLVER_VERSION = "bounded-exact-three-blocks-v1"
BUFFER_PHOTOS = 10
_SHA = re.compile(r"[0-9a-f]{64}")
_MANAGED_NAME = re.compile(r"[0-9a-f]{64}\.(?:jpg|jpeg)", re.IGNORECASE)
_MIN_PHOTOS = (10, 5, 5)
_MIN_BOARDS = (30, 15, 15)


def role_boards(count: int, role: int, *, full_training: bool = False) -> int:
    """New screen policy excludes partial TRAIN/A, retaining labelled REG targets."""
    return 0 if full_training and role < 2 and count != 9 else count


def correction_data_availability(
    photos: int, boards: int, split_status: Literal["minima", "infeasible", "ready"]
) -> dict[str, int | str]:
    """Observed annotated population before role/buffer allocation; deficits are lower bounds."""
    minimum_photos, minimum_boards = sum(_MIN_PHOTOS), sum(_MIN_BOARDS)
    return {
        "photos": photos,
        "boards": boards,
        "minimumPhotos": minimum_photos,
        "minimumBoards": minimum_boards,
        "photoDeficit": max(0, minimum_photos - photos),
        "boardDeficit": max(0, minimum_boards - boards),
        "splitStatus": split_status,
    }


class CorrectionSplitError(ValueError):
    """Fail closed with a stable code and machine-readable observed counts."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        photos: int = 0,
        boards: int = 0,
        role_counts: tuple[CorrectionRoleCount, ...] = (),
    ):
        super().__init__(message)
        self.code = code
        self.photos = photos
        self.boards = boards
        # Protected per-role counts reached before failing, when the solver knows them.
        self.role_counts = role_counts


@dataclass(frozen=True, slots=True)
class CorrectionSplitSource:
    source_id: str
    import_id: str
    byte_sha256: str
    pixel_sha256: str | None
    logical_filename: str
    eligible_boards: int
    attested_start: int | None = None
    attested_end: int | None = None
    attested_slots: tuple[int, ...] = ()
    attestation_checksum_sha256: str | None = None
    board_bindings: tuple[tuple[int, int], ...] = ()
    component_ids: tuple[str, ...] = ()
    allowed_roles: frozenset[str] = frozenset(ROLES)
    frozen_role: str | None = None
    frozen_buffer: bool = False
    pending_correction: bool = False
    # Retain the original order/closure, but never assign new use to this source.
    new_use_excluded: bool = False


@dataclass(frozen=True, slots=True)
class CorrectionImportOrder:
    import_id: str
    method: str
    # One canonical photo key per exact byte/pixel alias component.
    photo_keys: tuple[str, ...]
    ranges: tuple[tuple[int, int] | None, ...]


@dataclass(frozen=True, slots=True)
class CorrectionRoleCount:
    role: str
    photos: int
    boards: int


@dataclass(frozen=True, slots=True)
class CorrectionSplitResult:
    assignments: tuple[tuple[str, str | None], ...]
    buffers: tuple[str, ...]
    import_orders: tuple[CorrectionImportOrder, ...]
    role_counts: tuple[CorrectionRoleCount, ...]
    limitations: tuple[str, ...]
    objective_numerator: int
    objective_denominator: int
    representative_sources: tuple[str, ...]
    schema_version: str = SPLIT_SCHEMA_VERSION
    solver_version: str = SPLIT_SOLVER_VERSION


class _DisjointSet:
    def __init__(self, keys: Iterable[str]):
        self.parents = dict.fromkeys(keys, "")
        for key in self.parents:
            self.parents[key] = key

    def find(self, key: str) -> str:
        root = key
        while self.parents[root] != root:
            root = self.parents[root]
        while self.parents[key] != key:
            previous = self.parents[key]
            self.parents[key] = root
            key = previous
        return root

    def union(self, left: str, right: str) -> None:
        first, second = sorted((self.find(left), self.find(right)))
        self.parents[second] = first


@dataclass(slots=True)
class _Work:
    limit: int
    used: int = 0

    def take(self, amount: int = 1) -> None:
        self.used += amount
        if self.used > self.limit:
            raise CorrectionSplitError(
                "GRID_CORRECTION_SPLIT_WORK_LIMIT",
                "The exact split search exceeded its work budget; no optimum was returned.",
            )


@dataclass(frozen=True, slots=True)
class _Candidate:
    # Half-open photo intervals; role index 3 denotes a buffer.
    segments: tuple[tuple[int, int, int], ...]
    counts: tuple[int, ...]
    shared: tuple[tuple[str, int], ...]
    tie: tuple[int, ...]


def _attestation(source: CorrectionSplitSource) -> tuple[int, int] | None:
    start, end = source.attested_start, source.attested_end
    if start is None or end is None:
        return None
    try:
        if is_sequence_range_filename_candidate(source.logical_filename):
            parsed = parse_attested_sequence_range_filename(source.logical_filename)
            if (parsed.start, parsed.end) != (start, end):
                raise CorrectionSplitError(
                    "GRID_CORRECTION_SEQUENCE_CONFLICT",
                    "A logical seq_ filename contradicts the current geometry attestation.",
                )
        checksum = sequence_attestation_checksum_sha256(
            sequence_range_start=start,
            sequence_range_end=end,
            active_board_slots=source.attested_slots,
        )
        bindings = tuple((position, start + position) for position in source.attested_slots)
        if (
            checksum != source.attestation_checksum_sha256
            or tuple(sorted(source.board_bindings)) != bindings
            or any(type(position) is not int for position in source.attested_slots)
            or any(type(value) is not int for binding in source.board_bindings for value in binding)
        ):
            return None
        if not is_sequence_range_filename_candidate(
            source.logical_filename
        ) and not _MANAGED_NAME.fullmatch(
            PurePosixPath(source.logical_filename.replace("\\", "/")).name
        ):
            return None
        if source.eligible_boards > len(source.attested_slots):
            raise CorrectionSplitError(
                "GRID_CORRECTION_SPLIT_INVALID", "Eligible boards exceed attested source slots."
            )
    except ImageGeometryContractError as error:
        if is_sequence_range_filename_candidate(source.logical_filename):
            # A malformed filename is also an explicit, contradictory sequence claim.
            try:
                parse_attested_sequence_range_filename(source.logical_filename)
            except ImageGeometryContractError:
                raise CorrectionSplitError(
                    "GRID_CORRECTION_SEQUENCE_CONFLICT", "Invalid logical seq_ filename."
                ) from error
        return None
    return start, end


def _validate(sources: tuple[CorrectionSplitSource, ...]) -> None:
    seen: set[str] = set()
    for source in sources:
        if (
            not source.source_id
            or not source.import_id
            or source.source_id in seen
            or not _SHA.fullmatch(source.byte_sha256)
            or (source.pixel_sha256 is not None and not _SHA.fullmatch(source.pixel_sha256))
            or isinstance(source.eligible_boards, bool)
            or not isinstance(source.eligible_boards, int)
            or not 0 <= source.eligible_boards <= 9
            or not source.allowed_roles.issubset(ROLES)
            or source.frozen_role not in (*ROLES, None)
            or any(not component for component in source.component_ids)
        ):
            raise CorrectionSplitError("GRID_CORRECTION_SPLIT_INVALID", "Invalid source evidence.")
        seen.add(source.source_id)
        if source.frozen_buffer and source.frozen_role is not None:
            raise CorrectionSplitError(
                "GRID_CORRECTION_PROTECTION_CONFLICT", "A frozen buffer cannot carry a role."
            )


def _prepare_groups(
    sources: tuple[CorrectionSplitSource, ...],
) -> tuple[
    _DisjointSet,
    _DisjointSet,
    tuple[CorrectionImportOrder, ...],
    dict[str, int],
    dict[str, int],
]:
    copies = _DisjointSet(source.source_id for source in sources)
    identities: dict[tuple[str, str], str] = {}
    for source in sources:
        for kind, checksum in (("bytes", source.byte_sha256), ("pixels", source.pixel_sha256)):
            if checksum is not None:
                previous = identities.setdefault((kind, checksum), source.source_id)
                copies.union(previous, source.source_id)
    components = _DisjointSet(source.source_id for source in sources)
    known: dict[str, str] = {}
    imports: dict[str, list[CorrectionSplitSource]] = defaultdict(list)
    boards: dict[str, int] = {}
    owner: dict[str, str] = {}
    for source in sources:
        photo = copies.find(source.source_id)
        components.union(source.source_id, photo)
        boards[photo] = max(boards.get(photo, 0), source.eligible_boards)
        owner[photo] = min(owner.get(photo, source.import_id), source.import_id)
        imports[source.import_id].append(source)
        for component in source.component_ids:
            components.union(source.source_id, known.setdefault(component, source.source_id))
    orders: list[CorrectionImportOrder] = []
    for import_id, members in sorted(imports.items()):
        ranges: dict[str, tuple[int, int] | None] = {}
        reliable = True
        named = True
        for source in members:
            photo, attested = copies.find(source.source_id), _attestation(source)
            if attested is None or (photo in ranges and ranges[photo] != attested):
                reliable = False
            ranges[photo] = attested
            named &= is_sequence_range_filename_candidate(source.logical_filename)
        ordered = sorted(ranges, key=lambda key: (ranges[key] or (0, 0), key))
        if reliable:
            previous_end = 0
            for key in ordered:
                value = ranges[key]
                assert value is not None
                if value[0] <= previous_end:
                    reliable = False
                previous_end = value[1]
        if not reliable:
            ordered = sorted(ranges)
            for source in members:
                components.union(members[0].source_id, source.source_id)
        method = (
            ("attested-sequence-order-v1" if named else "verified-attestation-order-v1")
            if reliable
            else "indivisible-import-v1"
        )
        orders.append(
            CorrectionImportOrder(
                import_id, method, tuple(ordered), tuple(ranges[key] for key in ordered)
            )
        )
    owner_indices = {photo: list(sorted(imports)).index(value) for photo, value in owner.items()}
    return copies, components, tuple(orders), boards, owner_indices


def _prepare(
    sources: tuple[CorrectionSplitSource, ...],
) -> tuple[
    _DisjointSet,
    _DisjointSet,
    tuple[CorrectionImportOrder, ...],
    dict[str, frozenset[int]],
    dict[str, int],
    dict[str, int],
]:
    copies, components, orders, boards, owner_indices = _prepare_groups(sources)
    allowed: dict[str, frozenset[int]] = {}
    fixed: dict[str, int] = {}
    excluded = {components.find(s.source_id) for s in sources if s.new_use_excluded}
    for source in sources:
        component = components.find(source.source_id)
        if component in excluded:
            allowed[component] = frozenset(range(4))
            boards[copies.find(source.source_id)] = 0
            continue
        permitted = frozenset(ROLES.index(role) for role in source.allowed_roles) | {3}
        allowed[component] = allowed.get(component, frozenset(range(4))) & permitted
        frozen = (
            3
            if source.frozen_buffer
            else (ROLES.index(source.frozen_role) if source.frozen_role is not None else None)
        )
        if frozen is not None:
            if component in fixed and fixed[component] != frozen:
                raise CorrectionSplitError(
                    "GRID_CORRECTION_PROTECTION_CONFLICT",
                    "Aliases or sessions have conflicting pins.",
                )
            fixed[component] = frozen
    for component, frozen in fixed.items():
        if frozen < 3 and frozen not in allowed[component]:
            raise CorrectionSplitError(
                "GRID_CORRECTION_PROTECTION_CONFLICT", "A prior role contradicts protected use."
            )
        allowed[component] = frozenset((frozen,))
    # Count a duplicate photo once globally, in a stable owning import.
    return copies, components, orders, allowed, boards, owner_indices


def _candidates(
    order: CorrectionImportOrder,
    import_index: int,
    components: _DisjointSet,
    allowed: dict[str, frozenset[int]],
    boards: dict[str, int],
    owners: dict[str, int],
    shared_components: frozenset[str],
    work: _Work,
    *,
    full_training: bool = False,
    excluded_components: frozenset[str] = frozenset(),
) -> tuple[_Candidate, ...]:
    size = len(order.photo_keys)
    photo_prefix, board_prefix = [[0] for _ in range(3)], [[0] for _ in range(3)]
    forbidden = [[0] for _ in range(4)]
    positions: dict[str, list[int]] = defaultdict(list)
    for index, photo in enumerate(order.photo_keys):
        component = components.find(photo)
        positions[component].append(index)
        count = boards[photo] if owners[photo] == import_index else 0
        for role in range(3):
            eligible = role_boards(count, role, full_training=full_training)
            photo_prefix[role].append(photo_prefix[role][-1] + int(eligible > 0))
            board_prefix[role].append(board_prefix[role][-1] + eligible)
        permitted = allowed[component]
        for role in range(4):
            # Buffers may never consume a source with a previously frozen role.
            blocked = role not in permitted
            forbidden[role].append(forbidden[role][-1] + int(blocked))
    multiple = {
        key: value
        for key, value in positions.items()
        if len(value) > 1 and key not in excluded_components
    }
    cross = {key: value[0] for key, value in positions.items() if key in shared_components}
    candidate_work = 1 + sum(map(len, multiple.values())) + len(cross)
    found: dict[tuple[tuple[int, ...], tuple[tuple[str, int], ...]], _Candidate] = {}

    def add(segments: tuple[tuple[int, int, int], ...]) -> None:
        work.take(candidate_work)
        if any(forbidden[role][end] != forbidden[role][start] for start, end, role in segments):
            return

        def role_at(position: int) -> int:
            return next(role for start, end, role in segments if start <= position < end)

        if any(len({role_at(position) for position in values}) > 1 for values in multiple.values()):
            return
        counts = [0] * 6
        for start, end, role in segments:
            if role < 3:
                counts[role] += photo_prefix[role][end] - photo_prefix[role][start]
                counts[role + 3] = min(
                    _MIN_BOARDS[role],
                    counts[role + 3] + board_prefix[role][end] - board_prefix[role][start],
                )
        shared = tuple(sorted((key, role_at(position)) for key, position in cross.items()))
        # Stable group (import) order, role order, then boundary order defines ties.
        tie = tuple(value for start, end, role in segments for value in (role, start, end))
        candidate = _Candidate(segments, tuple(counts), shared, tie)
        key = candidate.counts, shared
        if key not in found or tie < found[key].tie:
            found[key] = candidate
            if len(found) > 100_000:
                raise CorrectionSplitError(
                    "GRID_CORRECTION_SPLIT_WORK_LIMIT", "Exact candidate memory limit exceeded."
                )

    for role in range(3):
        add(((0, size, role),))
    if all(allowed[components.find(photo)] == frozenset((3,)) for photo in order.photo_keys):
        add(((0, size, 3),))
    if order.method != "indivisible-import-v1" and len(positions) > 1:
        for roles in permutations(range(3), 2):
            for first in range(1, size - BUFFER_PHOTOS):
                add(((0, first, roles[0]), (first, first + 10, 3), (first + 10, size, roles[1])))
        for three_roles in permutations(range(3)):
            for first in range(1, size - 21):
                for second in range(first + 11, size - 10):
                    add(
                        (
                            (0, first, three_roles[0]),
                            (first, first + 10, 3),
                            (first + 10, second, three_roles[1]),
                            (second, second + 10, 3),
                            (second + 10, size, three_roles[2]),
                        )
                    )
    return tuple(sorted(found.values(), key=lambda candidate: candidate.tie))


def solve_correction_split(
    sources: Iterable[CorrectionSplitSource],
    *,
    max_work: int = 3_000_000,
    full_training: bool = False,
) -> CorrectionSplitResult:
    """Return a provisional immutable exact split; caller owns freeze and trust.

    ``eligible_boards`` must already count only current exact human-approved
    geometries. ``component_ids`` come from proven registry closure, never an
    inferred recording. External prior-use protections enter as allowed roles
    and frozen pins. Attestation bindings cover every active source slot.
    """
    ordered_sources = tuple(sorted(sources, key=lambda source: source.source_id))
    if not isinstance(max_work, int) or isinstance(max_work, bool) or max_work < 1:
        raise CorrectionSplitError("GRID_CORRECTION_SPLIT_INVALID", "Invalid work budget.")
    if len(ordered_sources) > 5000:
        raise CorrectionSplitError("GRID_CORRECTION_SPLIT_WORK_LIMIT", "Source limit exceeded.")
    _validate(ordered_sources)
    copies, components, orders, allowed, boards, owners = _prepare(ordered_sources)
    available_photos = sum(value > 0 for value in boards.values())
    available_boards = sum(boards.values())
    if available_photos < sum(_MIN_PHOTOS) or available_boards < sum(_MIN_BOARDS):
        raise CorrectionSplitError(
            "GRID_CORRECTION_SPLIT_MINIMA",
            "Insufficient labeled photos or boards for three roles.",
            photos=available_photos,
            boards=available_boards,
        )
    component_imports: dict[str, set[str]] = defaultdict(set)
    for source in ordered_sources:
        component_imports[components.find(source.source_id)].add(source.import_id)
    excluded = frozenset(
        components.find(s.source_id) for s in ordered_sources if s.new_use_excluded
    )
    shared = frozenset(
        key
        for key, imports in component_imports.items()
        if len(imports) > 1 and key not in excluded
    )
    work = _Work(max_work)
    # Exact dynamic programming retains counts, capped minima and cross-import
    # equality obligations. Identical states retain the smallest full tie key.
    StateKey = tuple[tuple[int, ...], tuple[tuple[str, int], ...]]
    states: dict[StateKey, tuple[_Candidate, ...]] = {((0,) * 6, ()): ()}
    for index, order in enumerate(orders):
        candidates = _candidates(
            order,
            index,
            components,
            allowed,
            boards,
            owners,
            shared,
            work,
            full_training=full_training,
            excluded_components=excluded,
        )
        next_states: dict[StateKey, tuple[_Candidate, ...]] = {}
        for (counts, pins), path in states.items():
            pin_map = dict(pins)
            for candidate in candidates:
                work.take(1 + len(pins) + len(candidate.shared))
                if any(key in pin_map and pin_map[key] != role for key, role in candidate.shared):
                    continue
                new_counts = tuple(
                    counts[i] + candidate.counts[i]
                    if i < 3
                    else min(_MIN_BOARDS[i - 3], counts[i] + candidate.counts[i])
                    for i in range(6)
                )
                new_pins = tuple(sorted((pin_map | dict(candidate.shared)).items()))
                key = new_counts, new_pins
                new_path = (*path, candidate)
                prior = next_states.get(key)
                if prior is None or tuple(item.tie for item in new_path) < tuple(
                    item.tie for item in prior
                ):
                    next_states[key] = new_path
                    if len(next_states) > 100_000:
                        raise CorrectionSplitError(
                            "GRID_CORRECTION_SPLIT_WORK_LIMIT", "Exact state memory limit exceeded."
                        )
        states = next_states
    best: tuple[Fraction, tuple[tuple[int, ...], ...], tuple[_Candidate, ...]] | None = None
    for (counts, _pins), path in states.items():
        if any(counts[i] < _MIN_PHOTOS[i] or counts[i + 3] < _MIN_BOARDS[i] for i in range(3)):
            continue
        total = sum(counts[:3])
        score = Fraction(
            sum(abs(100 * counts[i] - (70, 15, 15)[i] * total) for i in range(3)), 100 * total
        )
        tie = tuple(candidate.tie for candidate in path)
        if best is None or (score, tie) < best[:2]:
            best = score, tie, path
    if best is None:
        raise CorrectionSplitError(
            "GRID_CORRECTION_SPLIT_INFEASIBLE",
            "No protected split meets all role minima.",
            photos=available_photos,
            boards=available_boards,
        )
    photo_roles: dict[str, int] = {}
    for order, candidate in zip(orders, best[2], strict=True):
        for start, end, role in candidate.segments:
            for photo in order.photo_keys[start:end]:
                photo_roles[photo] = role
    assignments = tuple(
        (source.source_id, ROLES[role] if role < 3 and not source.new_use_excluded else None)
        for source in ordered_sources
        for role in (photo_roles[copies.find(source.source_id)],)
    )
    role_counts = tuple(
        CorrectionRoleCount(
            role_name,
            sum(
                role_boards(count, role, full_training=full_training) > 0
                and photo_roles[photo] == role
                for photo, count in boards.items()
            ),
            sum(
                role_boards(count, role, full_training=full_training)
                for photo, count in boards.items()
                if photo_roles[photo] == role
            ),
        )
        for role, role_name in enumerate(ROLES)
    )
    limitations = ("PHOTO_ONLY_NO_PROVEN_SESSION_INDEPENDENCE", "UNKNOWN_ANCESTOR_USE_NOT_PROVEN")
    representatives: dict[str, CorrectionSplitSource] = {}
    for source in ordered_sources:
        photo = copies.find(source.source_id)
        prior_source = representatives.get(photo)
        if prior_source is None or (-source.eligible_boards, source.source_id) < (
            -prior_source.eligible_boards,
            prior_source.source_id,
        ):
            representatives[photo] = source
    return CorrectionSplitResult(
        assignments,
        tuple(
            source.source_id
            for source in ordered_sources
            if not source.new_use_excluded and photo_roles[copies.find(source.source_id)] == 3
        ),
        orders,
        role_counts,
        limitations,
        best[0].numerator,
        best[0].denominator,
        tuple(
            sorted(
                source.source_id
                for source in representatives.values()
                if not source.new_use_excluded
            )
        ),
    )
