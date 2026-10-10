"""Symbol-agreement filter and the ``production-geometry-split-v1``/``-v2`` policies.

TASK-0801 introduced v1; TASK-0813 adds v2, which is v1 plus one step (see below).

Pure logic over the candidate manifest of TASK-0800 (one row per production
board). Nothing here reads a database, an image or the network, and nothing here
imports production storage (D-447). File integrity is injected as a callable so
the same plan runs in preview (stat only) and build (SHA-256 and decode) mode.

The unit is the photo (D-484): a photo enters training or development whole and
only when every candidate board passes the filter, and boards of one photo never
end up in different roles.

Roles, in order of precedence:

1. ``gold`` -- every photo with at least one G board, plus every photo sharing a
   SHA-256 with one. Only G boards are evaluation targets.
2. ``development`` -- whole family groups chosen in seeded order until their
   filtered pool holds enough S and B photos; a stratified sample is drawn from it.
3. ``training`` -- a stratified sample from the remaining family groups, per label
   level, stratified by family and difficulty bin, with a per-family share cap.

``production-geometry-split-v2`` inserts a step before the development choice:
family groups holding G boards are held out of training as a whole, so part of the
gold set lies in families never seen in training. Groups with G boards are sorted by
G boards per 1 000 filter-passing photos of the group (descending; tie: group id;
a group without filter-passing photos sorts first) and taken one by one while the
held-out groups hold less than 30% of all G boards and the next group would not
raise the training-pool loss (filter-passing photos of held-out groups / all
filter-passing photos) above 20%. The first group is always taken. Held-out groups
open the development family list; their filter-passing photos feed development, and
whole groups in v1 seeded order are added only when they cannot fill it.

Every random choice is a sort by ``sha256(seed | purpose | key)``, so the result
does not depend on the Python version, hash randomisation or input order.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Final

POLICY_VERSION: Final = "production-geometry-split-v1"
POLICY_VERSION_V2: Final = "production-geometry-split-v2"
POLICY_VERSIONS: Final = (POLICY_VERSION, POLICY_VERSION_V2)
FILTER_VERSION: Final = "production-geometry-symbol-filter-v1"
# Predictions at or below this quality without a human decision fail the filter
# (``cellsBelowFilter`` of the TASK-0800 manifest counts exactly those cells).
FILTER_MAX_LOW_QUALITY: Final = 0.80

ROLE_GOLD: Final = "gold"
ROLE_DEVELOPMENT: Final = "development"
ROLE_TRAINING: Final = "training"
ROLES: Final = (ROLE_GOLD, ROLE_DEVELOPMENT, ROLE_TRAINING)
TRAINING_LEVELS: Final = ("S", "B")

REJECT_UNCLASSIFIED: Final = "UNCLASSIFIED_BOARD"
REJECT_INCOMPLETE: Final = "INCOMPLETE_BOARD_SET"
REJECT_SYMBOL_FILTER: Final = "SYMBOL_FILTER_BELOW_THRESHOLD"
REJECT_MIXED_LEVELS: Final = "MIXED_LABEL_LEVELS"
REJECT_INVALID_GEOMETRY: Final = "INVALID_GEOMETRY_ROW"

GOLD_BASIS_BOARD: Final = "has_gold_board"
GOLD_BASIS_SHA_TWIN: Final = "sha_twin_of_gold"

_EXPECTED_NODES: Final = 24


@dataclass(frozen=True, slots=True)
class BoardFacts:
    board_id: str
    position_index: int
    level: str
    cells_below_filter: int
    max_angle_deviation_deg: float
    area_fraction: float
    geometry_valid: bool = True


@dataclass(frozen=True, slots=True)
class ImageFacts:
    image_id: str
    sha256: str
    family_id: str
    expected_boards: int
    candidate_boards: int
    boards: tuple[BoardFacts, ...]

    @property
    def levels(self) -> frozenset[str]:
        return frozenset(board.level for board in self.boards)


def board_facts_from_row(row: Mapping[str, Any]) -> BoardFacts:
    """The filter- and split-relevant facts of one ``production-geometry-candidate-v1`` row."""

    geometry = row.get("geometry") or {}
    topology = geometry.get("topology") or {}
    nodes = geometry.get("nodes") or []
    valid = (
        row.get("coordinateSpace") == "exif-normalized-rgb-pixels-v1"
        and topology.get("columns") == 5
        and topology.get("rows") == 3
        and len(nodes) == _EXPECTED_NODES
        and all(isinstance(node, Sequence) and len(node) == 2 for node in nodes)
    )
    difficulty = row["difficulty"]
    return BoardFacts(
        board_id=str(row["recognizedBoardId"]),
        position_index=int(row["positionIndex"]),
        level=str(row["label"]["level"]),
        cells_below_filter=int(row["symbolSignals"]["cellsBelowFilter"]),
        max_angle_deviation_deg=float(difficulty["maxAngleDeviationDeg"]),
        area_fraction=float(difficulty["areaFraction"]),
        geometry_valid=valid,
    )


class ImageFactsCollector:
    """Folds candidate rows (any order) into one :class:`ImageFacts` per photo."""

    def __init__(self) -> None:
        self._headers: dict[str, tuple[str, str, int, int]] = {}
        self._boards: dict[str, list[BoardFacts]] = defaultdict(list)

    def add(self, row: Mapping[str, Any]) -> None:
        image_id = str(row["sourceImageId"])
        header = (
            str(row["sourceChecksumSha256"]),
            str(row["family"]["familyId"]),
            int(row["expectedBoardsOnImage"]),
            int(row["candidateBoardsOnImage"]),
        )
        known = self._headers.setdefault(image_id, header)
        if known != header:
            raise ValueError(f"CANDIDATE_IMAGE_HEADER_CONFLICT: {image_id}")
        self._boards[image_id].append(board_facts_from_row(row))

    def images(self) -> dict[str, ImageFacts]:
        result: dict[str, ImageFacts] = {}
        for image_id in sorted(self._headers):
            sha256, family, expected, candidate = self._headers[image_id]
            boards = tuple(sorted(self._boards[image_id], key=lambda b: b.position_index))
            if len({board.board_id for board in boards}) != len(boards):
                raise ValueError(f"CANDIDATE_BOARD_DUPLICATE: {image_id}")
            result[image_id] = ImageFacts(image_id, sha256, family, expected, candidate, boards)
        return result


def filter_reasons(image: ImageFacts) -> tuple[str, ...]:
    """Why a non-gold photo cannot be a training/development unit (empty = it passes)."""

    reasons: list[str] = []
    if any(not board.geometry_valid for board in image.boards):
        reasons.append(REJECT_INVALID_GEOMETRY)
    if "U" in image.levels:
        reasons.append(REJECT_UNCLASSIFIED)
    if (
        image.candidate_boards != image.expected_boards
        or len(image.boards) != image.expected_boards
    ):
        reasons.append(REJECT_INCOMPLETE)
    if any(board.cells_below_filter > 0 for board in image.boards):
        reasons.append(REJECT_SYMBOL_FILTER)
    if len(image.levels - {"U"}) > 1:
        reasons.append(REJECT_MIXED_LEVELS)
    return tuple(reasons)


def image_level(image: ImageFacts) -> str | None:
    """The single S/B level of a filter-passing photo."""

    levels = image.levels
    if len(levels) == 1:
        level = next(iter(levels))
        if level in TRAINING_LEVELS:
            return level
    return None


def order_key(seed: int, purpose: str, key: str) -> str:
    return hashlib.sha256(f"{seed}|{purpose}|{key}".encode()).hexdigest()


def image_difficulty(image: ImageFacts) -> tuple[float, float]:
    """(skew, scale) of a photo: the largest board corner deviation from 90 degrees and
    the lower median of the boards' quad area as a fraction of the photo."""

    skew = max(board.max_angle_deviation_deg for board in image.boards)
    areas = sorted(board.area_fraction for board in image.boards)
    return skew, areas[(len(areas) - 1) // 2]


def quantile_edges(values: Iterable[float], bins: int) -> tuple[float, ...]:
    """``bins - 1`` inner edges at the empirical ``k / bins`` quantiles (lower order statistic)."""

    ordered = sorted(values)
    if not ordered:
        return ()
    return tuple(ordered[(len(ordered) * k) // bins] for k in range(1, bins))


def bin_index(value: float, edges: Sequence[float]) -> int:
    return sum(1 for edge in edges if value >= edge)


def capped_allocation(
    weights: Mapping[str, int], total: int, caps: Mapping[str, int]
) -> dict[str, int]:
    """Split ``total`` proportionally to ``weights`` without exceeding ``caps``.

    Water-filling: keys whose proportional share reaches their cap are fixed at the
    cap and the rest is shared again; the final integer split uses the largest
    remainder with the key as tie-break. Exact rational arithmetic keeps it stable.
    """

    keys = sorted(weights)
    budget = min(total, sum(max(0, caps[key]) for key in keys))
    fixed: dict[str, int] = {}
    active = [key for key in keys if caps[key] > 0 and weights[key] > 0]
    while active:
        remaining = budget - sum(fixed.values())
        weight_sum = sum(weights[key] for key in active)
        if remaining <= 0:
            break
        over = [
            key for key in active if Fraction(remaining * weights[key], weight_sum) >= caps[key]
        ]
        if not over:
            break
        for key in over:
            fixed[key] = caps[key]
        active = [key for key in active if key not in fixed]
    result = dict.fromkeys(keys, 0)
    result.update(fixed)
    remaining = budget - sum(fixed.values())
    if active and remaining > 0:
        weight_sum = sum(weights[key] for key in active)
        ideal = {key: Fraction(remaining * weights[key], weight_sum) for key in active}
        base = {key: int(ideal[key]) for key in active}
        leftover = remaining - sum(base.values())
        for key in sorted(active, key=lambda k: (-(ideal[k] - base[k]), k))[:leftover]:
            base[key] += 1
        result.update(base)
    return result


@dataclass(frozen=True, slots=True)
class SplitConfig:
    seed: int
    training_per_level: int = 3000
    development_per_level: int = 300
    family_cap_fraction: Fraction = Fraction(1, 4)
    difficulty_bins: int = 3
    filter_max_low_quality: float = FILTER_MAX_LOW_QUALITY
    policy_version: str = POLICY_VERSION
    # v2 only: stop holding out gold families once they hold this share of G boards...
    heldout_gold_share: Fraction = Fraction(3, 10)
    # ...or when the next family would push the training-pool loss above this share.
    heldout_max_pool_loss: Fraction = Fraction(1, 5)

    def __post_init__(self) -> None:
        if self.policy_version not in POLICY_VERSIONS:
            raise ValueError(f"SPLIT_POLICY_UNSUPPORTED: {self.policy_version}")

    @property
    def holds_out_gold_families(self) -> bool:
        return self.policy_version == POLICY_VERSION_V2

    def describe(self) -> dict[str, Any]:
        # v1 keeps its exact description: it is part of the published v1 snapshot ID.
        described = self._describe_v1()
        if self.holds_out_gold_families:
            described["policyVersion"] = self.policy_version
            described["heldoutGoldFamilies"] = {
                "goldShareBelow": str(self.heldout_gold_share),
                "maxTrainingPoolLoss": str(self.heldout_max_pool_loss),
                "rule": (
                    "family groups with G boards sorted by G boards per 1000 filter-passing "
                    "photos descending (tie: group id; groups without filter-passing photos "
                    "first); taken in order while the held-out groups hold less than "
                    "goldShareBelow of all G boards and the next group keeps the loss of "
                    "filter-passing photos at or below maxTrainingPoolLoss; the first group "
                    "is always taken; held-out groups never enter training and feed "
                    "development, topped up by whole groups in v1 seeded order"
                ),
            }
        return described

    def _describe_v1(self) -> dict[str, Any]:
        return {
            "policyVersion": POLICY_VERSION,
            "seed": self.seed,
            "trainingPerLevel": self.training_per_level,
            "developmentPerLevel": self.development_per_level,
            "trainingLevels": list(TRAINING_LEVELS),
            "familyCapFraction": str(self.family_cap_fraction),
            "familyCapPerLevel": self.family_cap(),
            "difficultyBins": self.difficulty_bins,
            "filter": {
                "version": FILTER_VERSION,
                "rule": (
                    "board passes when no cell without a human decision has a prediction "
                    "quality <= threshold (cellsBelowFilter == 0); photo passes when every "
                    "candidate board passes, the candidate set equals the expected boards, "
                    "and no board is unclassified (U)"
                ),
                "maxLowQualityConfidence": self.filter_max_low_quality,
            },
        }

    def family_cap(self) -> int:
        return int(self.training_per_level * self.family_cap_fraction)


# (image id) -> None when the source file is usable, else the exclusion reason.
IntegrityCheck = Callable[[str], str | None]


@dataclass(slots=True)
class SplitPlan:
    config: SplitConfig
    roles: dict[str, str] = field(default_factory=dict)
    gold_basis: dict[str, str] = field(default_factory=dict)
    family_group_of: dict[str, str] = field(default_factory=dict)
    family_groups: dict[str, list[str]] = field(default_factory=dict)
    development_groups: list[str] = field(default_factory=list)
    training_groups: list[str] = field(default_factory=list)
    filter_rejections: dict[str, tuple[str, ...]] = field(default_factory=dict)
    integrity_exclusions: dict[str, str] = field(default_factory=dict)
    image_levels: dict[str, str] = field(default_factory=dict)
    difficulty: dict[str, dict[str, Any]] = field(default_factory=dict)
    difficulty_edges: dict[str, list[float]] = field(default_factory=dict)
    allocations: list[dict[str, Any]] = field(default_factory=list)
    shortfalls: list[dict[str, Any]] = field(default_factory=list)
    family_seen_in_training: dict[str, bool] = field(default_factory=dict)
    development_family_order: list[dict[str, Any]] = field(default_factory=list)
    heldout_groups: list[str] = field(default_factory=list)
    heldout_selection: dict[str, Any] = field(default_factory=dict)


def _sha_components(images: Mapping[str, ImageFacts]) -> dict[str, list[str]]:
    by_sha: dict[str, list[str]] = defaultdict(list)
    for image_id in sorted(images):
        by_sha[images[image_id].sha256].append(image_id)
    return dict(by_sha)


def _family_groups(
    images: Mapping[str, ImageFacts], gold: set[str]
) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Families joined by any shared SHA-256 outside the gold set (union-find)."""

    parents: dict[str, str] = {}

    def find(value: str) -> str:
        parents.setdefault(value, value)
        while parents[value] != value:
            parents[value] = parents[parents[value]]
            value = parents[value]
        return value

    for image in images.values():
        find(image.family_id)
    for ids in _sha_components(images).values():
        families = sorted({images[i].family_id for i in ids if i not in gold})
        for other in families[1:]:
            a, b = sorted((find(families[0]), find(other)))
            parents[b] = a
    group_of = {family: find(family) for family in sorted(parents)}
    groups: dict[str, list[str]] = defaultdict(list)
    for family, group in group_of.items():
        groups[group].append(family)
    return group_of, dict(groups)


def _draw(
    plan: SplitPlan,
    *,
    role: str,
    level: str,
    pool: Mapping[str, list[str]],
    quota: int,
    caps: Mapping[str, int],
    stratum_of: Mapping[str, str],
    check: IntegrityCheck,
) -> None:
    """Stratified draw: family quotas (capped), then difficulty-bin quotas, then seeded order."""

    seed = plan.config.seed
    weights = {group: len(ids) for group, ids in pool.items()}
    family_quota = capped_allocation(weights, quota, caps)
    available_total = sum(weights.values())
    if available_total < quota:
        plan.shortfalls.append(
            {
                "role": role,
                "level": level,
                "stratum": "*",
                "requested": quota,
                "available": available_total,
                "reason": "POOL_SMALLER_THAN_TARGET",
            }
        )
    for group in sorted(pool):
        if family_quota[group] == 0:
            continue
        by_bin: dict[str, list[str]] = defaultdict(list)
        for image_id in pool[group]:
            by_bin[stratum_of[image_id]].append(image_id)
        bin_weights = {key: len(ids) for key, ids in by_bin.items()}
        bin_quota = capped_allocation(bin_weights, family_quota[group], bin_weights)
        for stratum in sorted(by_bin):
            wanted = bin_quota[stratum]
            if wanted == 0:
                continue
            ordered = sorted(
                by_bin[stratum],
                key=lambda i: order_key(seed, f"{role}|{level}|{group}|{stratum}", i),
            )
            taken = 0
            for image_id in ordered:
                if taken == wanted:
                    break
                reason = check(image_id)
                if reason is not None:
                    plan.integrity_exclusions[image_id] = reason
                    continue
                plan.roles[image_id] = role
                taken += 1
            plan.allocations.append(
                {
                    "role": role,
                    "level": level,
                    "familyGroup": group,
                    "difficultyBin": stratum,
                    "available": len(ordered),
                    "requested": wanted,
                    "selected": taken,
                }
            )
            if taken < wanted:
                plan.shortfalls.append(
                    {
                        "role": role,
                        "level": level,
                        "familyGroup": group,
                        "stratum": stratum,
                        "requested": wanted,
                        "available": taken,
                        "reason": "STRATUM_EXHAUSTED_AFTER_INTEGRITY_EXCLUSIONS",
                    }
                )


def plan_split(
    images: Mapping[str, ImageFacts], config: SplitConfig, check: IntegrityCheck
) -> SplitPlan:
    """Assign gold, development and training photos (policy from ``config.policy_version``)."""

    plan = SplitPlan(config=config)
    components = _sha_components(images)
    gold: set[str] = set()
    for image_id, image in images.items():
        if "G" in image.levels:
            for twin in components[image.sha256]:
                gold.add(twin)
                plan.gold_basis.setdefault(twin, GOLD_BASIS_SHA_TWIN)
            plan.gold_basis[image_id] = GOLD_BASIS_BOARD
    plan.family_group_of, plan.family_groups = _family_groups(images, gold)
    for image_id in sorted(gold):
        reason = check(image_id)
        if reason is None:
            plan.roles[image_id] = ROLE_GOLD
        else:
            plan.integrity_exclusions[image_id] = reason

    eligible: dict[str, str] = {}
    for image_id, image in images.items():
        if image_id in gold:
            continue
        reasons = filter_reasons(image)
        level = image_level(image)
        if reasons or level is None:
            plan.filter_rejections[image_id] = reasons or (REJECT_MIXED_LEVELS,)
            continue
        eligible[image_id] = level
    plan.image_levels = dict(eligible)

    skew_values = []
    area_values = []
    raw: dict[str, tuple[float, float]] = {}
    for image_id in eligible:
        skew, area = image_difficulty(images[image_id])
        raw[image_id] = (skew, area)
        skew_values.append(skew)
        area_values.append(area)
    bins = config.difficulty_bins
    skew_edges = quantile_edges(skew_values, bins)
    area_edges = quantile_edges(area_values, bins)
    plan.difficulty_edges = {
        "maxAngleDeviationDeg": list(skew_edges),
        "medianAreaFraction": list(area_edges),
    }
    stratum_of: dict[str, str] = {}
    for image_id, (skew, area) in raw.items():
        skew_bin = bin_index(skew, skew_edges)
        area_bin = bin_index(area, area_edges)
        stratum_of[image_id] = f"skew{skew_bin}-area{area_bin}"
        plan.difficulty[image_id] = {
            "maxAngleDeviationDeg": skew,
            "medianAreaFraction": area,
            "skewBin": skew_bin,
            "areaBin": area_bin,
            "bin": stratum_of[image_id],
        }

    pools: dict[str, dict[str, list[str]]] = {level: defaultdict(list) for level in TRAINING_LEVELS}
    for image_id in sorted(eligible):
        group = plan.family_group_of[images[image_id].family_id]
        pools[eligible[image_id]][group].append(image_id)

    # Development: whole family groups in seeded order until both levels can fill it.
    # v2 opens the list with the held-out gold groups.
    dev_need = config.development_per_level
    have = dict.fromkeys(TRAINING_LEVELS, 0)
    if config.holds_out_gold_families:
        plan.heldout_groups = select_heldout_gold_groups(plan, images, pools, gold, config)
        for group in plan.heldout_groups:
            counts = {level: len(pools[level].get(group, [])) for level in TRAINING_LEVELS}
            plan.development_groups.append(group)
            for level in TRAINING_LEVELS:
                have[level] += counts[level]
            plan.development_family_order.append(
                {"familyGroup": group, **counts, "basis": "heldout_gold"}
            )
    for group in sorted(
        plan.family_groups, key=lambda g: order_key(config.seed, "development-family", g)
    ):
        if all(have[level] >= dev_need for level in TRAINING_LEVELS):
            break
        if group in plan.heldout_groups:
            continue
        counts = {level: len(pools[level].get(group, [])) for level in TRAINING_LEVELS}
        if not any(counts.values()):
            continue
        plan.development_groups.append(group)
        for level in TRAINING_LEVELS:
            have[level] += counts[level]
        entry: dict[str, Any] = {"familyGroup": group, **counts}
        if config.holds_out_gold_families:
            entry["basis"] = "seeded_order"
        plan.development_family_order.append(entry)
    if not all(have[level] >= dev_need for level in TRAINING_LEVELS):
        raise ValueError(f"DEVELOPMENT_POOL_INSUFFICIENT: {have}")
    plan.training_groups = sorted(
        group for group in plan.family_groups if group not in set(plan.development_groups)
    )
    if not plan.training_groups:
        raise ValueError("NO_TRAINING_FAMILY_GROUPS_LEFT")

    for level in TRAINING_LEVELS:
        dev_pool = {g: pools[level][g] for g in plan.development_groups if pools[level].get(g)}
        _draw(
            plan,
            role=ROLE_DEVELOPMENT,
            level=level,
            pool=dev_pool,
            quota=dev_need,
            caps={g: len(ids) for g, ids in dev_pool.items()},
            stratum_of=stratum_of,
            check=check,
        )
        train_pool = {g: pools[level][g] for g in plan.training_groups if pools[level].get(g)}
        cap = config.family_cap()
        _draw(
            plan,
            role=ROLE_TRAINING,
            level=level,
            pool=train_pool,
            quota=config.training_per_level,
            caps={g: min(cap, len(ids)) for g, ids in train_pool.items()},
            stratum_of=stratum_of,
            check=check,
        )

    trained_groups = {
        plan.family_group_of[images[i].family_id]
        for i, role in plan.roles.items()
        if role == ROLE_TRAINING
    }
    for image_id, role in plan.roles.items():
        if role == ROLE_GOLD:
            group = plan.family_group_of[images[image_id].family_id]
            plan.family_seen_in_training[image_id] = group in trained_groups
    assert_disjoint(plan, images)
    return plan


def select_heldout_gold_groups(
    plan: SplitPlan,
    images: Mapping[str, ImageFacts],
    pools: Mapping[str, Mapping[str, list[str]]],
    gold: set[str],
    config: SplitConfig,
) -> list[str]:
    """The v2 held-out gold family groups, in selection order (see the module docstring).

    Raises ``HELDOUT_GOLD_THRESHOLDS_IRRECONCILABLE`` when the loss cap stops the
    selection before the held-out groups reach the gold share, or when the first group
    alone exceeds the loss cap: the operator then chooses, not the code. The
    candidate table is kept in ``plan.heldout_selection`` either way.
    """

    gold_boards: dict[str, int] = defaultdict(int)
    for image_id in gold:
        image = images[image_id]
        count = sum(1 for board in image.boards if board.level == "G")
        if count:
            gold_boards[plan.family_group_of[image.family_id]] += count
    passing = {
        group: sum(len(pools[level].get(group, [])) for level in TRAINING_LEVELS)
        for group in plan.family_groups
    }
    total_gold = sum(gold_boards.values())
    total_pool = sum(passing.values())
    if total_gold == 0:
        raise ValueError("HELDOUT_GOLD_NO_GOLD_BOARDS")
    if total_pool == 0:
        raise ValueError("HELDOUT_GOLD_NO_FILTER_PASSING_PHOTOS")

    def rank(group: str) -> tuple[int, Fraction, str]:
        if passing[group] == 0:
            return (0, Fraction(0), group)
        return (1, -Fraction(gold_boards[group] * 1000, passing[group]), group)

    candidates = sorted(gold_boards, key=rank)
    table = [
        {
            "familyGroup": group,
            "goldBoards": gold_boards[group],
            "filterPassingPhotos": passing[group],
            "filterPassingByLevel": {
                level: len(pools[level].get(group, [])) for level in TRAINING_LEVELS
            },
            "goldBoardsPer1000Photos": None
            if passing[group] == 0
            else round(gold_boards[group] * 1000 / passing[group], 4),
        }
        for group in candidates
    ]
    selected: list[str] = []
    held_gold = 0
    held_pool = 0
    stop = "ALL_GOLD_GROUPS_TAKEN"
    for group in candidates:
        if selected:
            if Fraction(held_gold, total_gold) >= config.heldout_gold_share:
                stop = "GOLD_SHARE_REACHED"
                break
            if Fraction(held_pool + passing[group], total_pool) > config.heldout_max_pool_loss:
                stop = "POOL_LOSS_CAP"
                break
        selected.append(group)
        held_gold += gold_boards[group]
        held_pool += passing[group]
    gold_share = Fraction(held_gold, total_gold)
    pool_loss = Fraction(held_pool, total_pool)
    plan.heldout_selection = {
        "candidates": table,
        "selected": list(selected),
        "stopReason": stop,
        "goldBoardsTotal": total_gold,
        "goldBoardsHeldOut": held_gold,
        "goldShareHeldOut": float(gold_share),
        "filterPassingPhotosTotal": total_pool,
        "filterPassingPhotosHeldOut": held_pool,
        "trainingPoolLoss": float(pool_loss),
    }
    if pool_loss > config.heldout_max_pool_loss or gold_share < config.heldout_gold_share:
        raise ValueError(
            "HELDOUT_GOLD_THRESHOLDS_IRRECONCILABLE: "
            f"goldShare={float(gold_share):.4f} poolLoss={float(pool_loss):.4f} "
            f"selected={selected}"
        )
    return selected


def assert_disjoint(plan: SplitPlan, images: Mapping[str, ImageFacts]) -> None:
    """Refuse a split with any leak between roles (photo, SHA-256, family group, unit rule)."""

    problems: list[str] = []
    by_role: dict[str, set[str]] = {role: set() for role in ROLES}
    for image_id, role in plan.roles.items():
        by_role[role].add(image_id)

    def shas(role: str) -> set[str]:
        return {images[i].sha256 for i in by_role[role]}

    def groups(role: str) -> set[str]:
        return {plan.family_group_of[images[i].family_id] for i in by_role[role]}

    if shas(ROLE_GOLD) & (shas(ROLE_TRAINING) | shas(ROLE_DEVELOPMENT)):
        problems.append("GOLD_SHA_IN_TRAINING_OR_DEVELOPMENT")
    if shas(ROLE_DEVELOPMENT) & shas(ROLE_TRAINING):
        problems.append("DEVELOPMENT_SHA_IN_TRAINING")
    if groups(ROLE_DEVELOPMENT) & groups(ROLE_TRAINING):
        problems.append("DEVELOPMENT_FAMILY_IN_TRAINING")
    if groups(ROLE_DEVELOPMENT) - set(plan.development_groups):
        problems.append("DEVELOPMENT_PHOTO_OUTSIDE_DEVELOPMENT_FAMILIES")
    if set(plan.development_groups) & set(plan.training_groups):
        problems.append("FAMILY_GROUP_IN_TWO_ROLES")
    if set(plan.heldout_groups) - set(plan.development_groups):
        problems.append("HELDOUT_FAMILY_OUTSIDE_DEVELOPMENT")
    if set(plan.heldout_groups) & groups(ROLE_TRAINING):
        problems.append("HELDOUT_FAMILY_IN_TRAINING")
    gold_shas = {images[i].sha256 for i in plan.gold_basis}
    for image_id in by_role[ROLE_TRAINING] | by_role[ROLE_DEVELOPMENT]:
        image = images[image_id]
        if image.sha256 in gold_shas or "G" in image.levels:
            problems.append(f"GOLD_RELATED_PHOTO_OUTSIDE_GOLD:{image_id}")
        if filter_reasons(image) or image_level(image) is None:
            problems.append(f"UNFILTERED_PHOTO_IN_{plan.roles[image_id].upper()}:{image_id}")
    if problems:
        raise ValueError("SPLIT_LEAKAGE: " + ", ".join(sorted(set(problems))[:20]))


def photo_level_label(plan: SplitPlan, image: ImageFacts) -> str:
    """S/B for training units, G for photos with a gold board, else the joined board levels."""

    if image.image_id in plan.image_levels:
        return plan.image_levels[image.image_id]
    if "G" in image.levels:
        return "G"
    return "+".join(sorted(image.levels))


def split_summary(plan: SplitPlan, images: Mapping[str, ImageFacts]) -> dict[str, Any]:
    """Counts per role, level, family group and difficulty bin, plus rejections."""

    per_role: dict[str, dict[str, Any]] = {}
    for role in ROLES:
        ids = sorted(i for i, r in plan.roles.items() if r == role)
        levels: dict[str, int] = defaultdict(int)
        boards: dict[str, int] = defaultdict(int)
        families: dict[str, int] = defaultdict(int)
        bins: dict[str, int] = defaultdict(int)
        for image_id in ids:
            image = images[image_id]
            levels[photo_level_label(plan, image)] += 1
            for board in image.boards:
                boards[board.level] += 1
            families[plan.family_group_of[image.family_id]] += 1
            if image_id in plan.difficulty:
                bins[plan.difficulty[image_id]["bin"]] += 1
        per_role[role] = {
            "images": len(ids),
            "imagesByLevel": dict(sorted(levels.items())),
            "boardsByLevel": dict(sorted(boards.items())),
            "imagesByFamilyGroup": dict(sorted(families.items())),
            "imagesByDifficultyBin": dict(sorted(bins.items())),
        }
    training_total = per_role[ROLE_TRAINING]["images"]
    shares = (
        {
            group: count / training_total
            for group, count in per_role[ROLE_TRAINING]["imagesByFamilyGroup"].items()
        }
        if training_total
        else {}
    )
    reasons: dict[str, int] = defaultdict(int)
    primary: dict[str, int] = defaultdict(int)
    for image_reasons in plan.filter_rejections.values():
        primary[image_reasons[0]] += 1
        for reason in image_reasons:
            reasons[reason] += 1
    rejected_by_level: dict[str, int] = defaultdict(int)
    for image_id in plan.filter_rejections:
        rejected_by_level["+".join(sorted(images[image_id].levels))] += 1
    integrity: dict[str, int] = defaultdict(int)
    for reason in plan.integrity_exclusions.values():
        integrity[reason] += 1
    gold_ids = [i for i, r in plan.roles.items() if r == ROLE_GOLD]
    gold_boards = sum(1 for i in gold_ids for board in images[i].boards if board.level == "G")
    seen = [i for i in gold_ids if plan.family_seen_in_training.get(i)]
    summary: dict[str, Any] = {
        "roles": per_role,
        "trainingFamilyShare": dict(sorted(shares.items())),
        "maxTrainingFamilyShare": max(shares.values()) if shares else 0.0,
        "developmentFamilyGroups": list(plan.development_groups),
        "developmentFamilyOrder": list(plan.development_family_order),
        "trainingFamilyGroups": list(plan.training_groups),
        "familyGroups": {g: list(f) for g, f in sorted(plan.family_groups.items())},
        "filterPassingImagesByLevel": {
            level: sum(1 for v in plan.image_levels.values() if v == level)
            for level in TRAINING_LEVELS
        },
        "filterRejectedImages": len(plan.filter_rejections),
        "filterRejectionsByReason": dict(sorted(reasons.items())),
        "filterRejectionsByPrimaryReason": dict(sorted(primary.items())),
        "filterRejectionsByBoardLevels": dict(sorted(rejected_by_level.items())),
        "integrityExclusions": len(plan.integrity_exclusions),
        "integrityExclusionsByReason": dict(sorted(integrity.items())),
        "difficultyEdges": plan.difficulty_edges,
        "shortfalls": list(plan.shortfalls),
        "gold": {
            "images": len(gold_ids),
            "imagesWithGoldBoards": sum(
                1 for i in gold_ids if plan.gold_basis.get(i) == GOLD_BASIS_BOARD
            ),
            "shaTwinImages": sum(
                1 for i in gold_ids if plan.gold_basis.get(i) == GOLD_BASIS_SHA_TWIN
            ),
            "goldBoards": gold_boards,
            "imagesInFamiliesSeenInTraining": len(seen),
            "goldBoardsInFamiliesSeenInTraining": sum(
                1 for i in seen for board in images[i].boards if board.level == "G"
            ),
        },
    }
    if plan.config.holds_out_gold_families:
        unseen = [i for i in gold_ids if not plan.family_seen_in_training.get(i)]
        summary["policyVersion"] = plan.config.policy_version
        summary["gold"]["imagesInFamiliesUnseenInTraining"] = len(unseen)
        summary["gold"]["goldBoardsInFamiliesUnseenInTraining"] = sum(
            1 for i in unseen for board in images[i].boards if board.level == "G"
        )
        development = set(plan.development_groups)
        outside_training = sum(
            1 for i in plan.image_levels if plan.family_group_of[images[i].family_id] in development
        )
        summary["heldoutGoldFamilies"] = {
            **plan.heldout_selection,
            "additionalDevelopmentFamilyGroups": [
                g for g in plan.development_groups if g not in plan.heldout_groups
            ],
            "trainingPoolLossWithAllDevelopmentFamilies": outside_training
            / max(1, len(plan.image_levels)),
        }
    return summary
