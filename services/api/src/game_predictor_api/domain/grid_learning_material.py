"""New-use exclusions and counted human material, without changing historical roles."""

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from .grid_correction_split import BUFFER_PHOTOS, ROLES, CorrectionSplitSource, _prepare_groups
from .grid_training_cohorts import digest

MATERIAL_VERSION = "effective-grid-learning-material-v1"
ERROR_CATEGORIES = (
    "missing-row",
    "shifted-board",
    "clipped-edge",
    "neighbor-takeover",
    "perspective",
    "incomplete-image",
)


def conflicting_groups(
    sources: Sequence[CorrectionSplitSource], contexts: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Close copies, sessions and indivisible imports BEFORE inspecting their roles.

    A conflicting source can never disappear while a cross-import alias survives.
    Exclusion is a new manifest fact; it neither changes nor releases an old pin.
    """
    copies, components, orders, boards, _ = _prepare_groups(tuple(sources))
    groups: dict[str, list[CorrectionSplitSource]] = defaultdict(list)
    for source in sources:
        groups[components.find(source.source_id)].append(source)
    methods = {order.import_id: order.method for order in orders}
    result = []
    for members in groups.values():
        roles = {role for s in members for role in contexts[s.source_id]["priorRoles"]}
        purposes = {
            purpose
            for s in members
            for purpose in contexts[s.source_id].get("validationPurposes", [])
        }
        reasons = set()
        if len(roles) > 1:
            reasons.add("GRID_CORRECTION_PROTECTION_CONFLICT")
        if len(purposes) > 1:
            reasons.add("GRID_VALIDATION_PURPOSE_CONFLICT")
        allowed = set.intersection(*(set(s.allowed_roles) for s in members))
        if (roles - {"BUFFER"}) - allowed or (not allowed and roles != {"BUFFER"}):
            reasons.add("GRID_CORRECTION_PROTECTION_CONFLICT")
        if not reasons:
            continue
        ids = sorted(s.source_id for s in members)
        photos = {copies.find(s.source_id) for s in members}
        imports = sorted({s.import_id for s in members})
        result.append(
            {
                "componentKey": digest(ids),
                "sourceIds": ids,
                "importIds": imports,
                "photos": len(photos),
                "labelledPhotos": sum(boards[p] > 0 for p in photos),
                "boards": sum(boards[p] for p in photos),
                "priorRoles": sorted(roles),
                "priorPurposes": sorted(purposes),
                "reasonCodes": sorted(reasons),
                "orderingMethods": {key: methods[key] for key in imports},
            }
        )
    return sorted(result, key=lambda item: item["componentKey"])


def protect_excluded_neighborhoods(
    sources: Sequence[CorrectionSplitSource],
    contexts: Mapping[str, Mapping[str, Any]],
    exclusions: list[dict[str, Any]],
) -> tuple[list[CorrectionSplitSource], list[dict[str, Any]]]:
    """Preserve every order position and close protection over aliases/sessions.

    Conflict groups and their ten-photo neighborhoods are unavailable to NEW use.
    Historical anchors also constrain neighboring roles even when the anchor itself
    is excluded. These are solver masks, never replacements for ledger history.
    """
    if not exclusions:
        return list(sources), exclusions
    copies, components, orders, boards, _ = _prepare_groups(tuple(sources))
    groups: dict[str, list[CorrectionSplitSource]] = defaultdict(list)
    for source in sources:
        groups[components.find(source.source_id)].append(source)
    seed = {components.find(key) for group in exclusions for key in group["sourceIds"]}
    blocked = set(seed)
    permitted = {
        key: set.intersection(*(set(s.allowed_roles) for s in members))
        for key, members in groups.items()
    }
    historical = {
        key: {
            role for s in members for role in contexts[s.source_id]["priorRoles"] if role in ROLES
        }
        for key, members in groups.items()
    }
    for order in orders:
        for index, photo in enumerate(order.photo_keys):
            key = components.find(photo)
            neighbors = {
                components.find(p)
                for p in order.photo_keys[max(0, index - BUFFER_PHOTOS) : index + BUFFER_PHOTOS + 1]
            }
            if key in seed:
                blocked.update(neighbors)
            # Keep the original historical constraints, including anchors which
            # cannot appear as a new role in the resulting split.
            if historical[key]:
                same_role = historical[key] if len(historical[key]) == 1 else set()
                for neighbor in neighbors:
                    permitted[neighbor].intersection_update(same_role)
    neighborhood = set(blocked)
    # A roleless photo between two different historical anchors is an ordinary
    # forced buffer (empty allowed roles), not an exclusion. Only a component whose
    # own historical role contradicts a neighboring anchor is unusable.
    contradicted = {
        key
        for key, members in groups.items()
        if not permitted[key]
        and (historical[key] or any(s.frozen_role is not None for s in members))
        and not all(s.frozen_buffer for s in members)
    }
    blocked.update(contradicted)
    methods = {order.import_id: order.method for order in orders}
    result = list(exclusions)
    for key in sorted(blocked - seed):
        members = groups[key]
        ids = sorted(s.source_id for s in members)
        photos = {copies.find(s.source_id) for s in members}
        imports = sorted({s.import_id for s in members})
        result.append(
            {
                "componentKey": digest(ids),
                "sourceIds": ids,
                "importIds": imports,
                "photos": len(photos),
                "labelledPhotos": sum(boards[p] > 0 for p in photos),
                "boards": sum(boards[p] for p in photos),
                "priorRoles": sorted(
                    {role for s in members for role in contexts[s.source_id]["priorRoles"]}
                ),
                "priorPurposes": sorted(
                    {
                        p
                        for s in members
                        for p in contexts[s.source_id].get("validationPurposes", [])
                    }
                ),
                "reasonCodes": [
                    "GRID_CORRECTION_PROTECTION_CONFLICT"
                    if key in contradicted and key not in neighborhood
                    else "GRID_CORRECTION_EXCLUDED_NEIGHBORHOOD"
                ],
                "orderingMethods": {key: methods[key] for key in imports},
            }
        )
    masked = [
        replace(s, eligible_boards=0, pending_correction=False, new_use_excluded=True)
        if components.find(s.source_id) in blocked
        else replace(s, allowed_roles=frozenset(permitted[components.find(s.source_id)]))
        for s in sources
    ]
    return masked, sorted(result, key=lambda item: item["componentKey"])


def role_shortfalls(counts: Sequence[Any]) -> dict[str, Any]:
    """Exact deficits of the protected assignment reached before infeasibility."""
    roles = {}
    for count in counts:
        photos, boards = (10, 30) if count.role == "TRAIN" else (5, 15)
        roles[count.role] = {
            "photos": count.photos,
            "boards": count.boards,
            "minimumPhotos": photos,
            "minimumBoards": boards,
            "photoDeficit": max(0, photos - count.photos),
            "boardDeficit": max(0, boards - count.boards),
        }
    return {"basis": "protected-roles-before-infeasibility", "roles": roles}


def material_report(
    sources: Sequence[CorrectionSplitSource],
    labels: Mapping[str, Sequence[Mapping[str, Any]]],
    exclusions: list[dict[str, Any]],
    pins: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Deduplicate by canonical photo and position, preserving the actual approval.

    Category photo counts overlap; board counts partition each role. A human
    correction proves its weight, never a particular detector failure category.
    """
    copies, _, _, _, _ = _prepare_groups(tuple(sources))
    excluded = {key for group in exclusions for key in group["sourceIds"]}
    selected = {str(pin["sourceId"]): pin for pin in pins if pin.get("representative")}
    representatives: dict[str, CorrectionSplitSource] = {}
    for source in sources:
        photo = copies.find(source.source_id)
        old = representatives.get(photo)
        if old is None or (-source.eligible_boards, source.source_id) < (
            -old.eligible_boards,
            old.source_id,
        ):
            representatives[photo] = source
    totals: dict[str, Counter[str]] = defaultdict(Counter)
    photo_sets: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for photo, source in representatives.items():
        pin = selected.get(source.source_id)
        buffer = bool(pin and pin.get("buffer"))
        if (
            pin
            and not buffer
            and (
                not pin.get("eligibleBoards")
                or pin.get("contentExcluded")
                or pin.get("detectorExcluded")
            )
        ):
            pin = None
        role = (
            "EXCLUDED"
            if source.source_id in excluded
            else "BUFFER"
            if buffer
            else (
                f"VALIDATION-{pin.get('validationPurpose') or 'A'}"
                if pin and pin.get("role") == "VALIDATION"
                else str(pin["role"])
                if pin and pin.get("role")
                else "UNASSIGNED"
            )
        )
        for label in labels.get(source.source_id, ()):
            proof = label.get("approval") or {}
            kind = (
                "corrected"
                if proof.get("origin") == "human_corrected" and proof.get("weight") == 4
                else "good"
                if proof.get("origin") == "human_checked_unchanged" and proof.get("weight") == 1
                else "unknown"
            )
            totals[role][kind + "Boards"] += 1
            photo_sets[role][kind].add(photo)
            photo_sets[role]["all"].add(photo)
    roles = {}
    for role in sorted(totals):
        roles[role] = {
            **{
                kind + "Boards": totals[role][kind + "Boards"]
                for kind in ("corrected", "good", "unknown")
            },
            **{
                kind + "Photos": len(photo_sets[role][kind])
                for kind in ("corrected", "good", "unknown")
            },
            "photos": len(photo_sets[role]["all"]),
            "boards": sum(totals[role].values()),
            "photoCategoriesMayOverlap": True,
        }
    # Available counts are lower bounds; allocation constraints may need more data.
    available = [s for s in representatives.values() if s.source_id not in excluded]
    nphotos = sum(s.eligible_boards > 0 for s in available)
    nboards = sum(s.eligible_boards for s in available)
    return {
        "version": MATERIAL_VERSION,
        "weights": {"corrected": 4, "good": 1},
        "roles": roles,
        "exclusions": exclusions,
        "excludedPhotos": sum(group["photos"] for group in exclusions),
        "excludedBoards": sum(group["boards"] for group in exclusions),
        "availablePhotos": nphotos,
        "availableBoards": nboards,
        "minimumPhotos": 20,
        "minimumBoards": 60,
        "minimumBasis": "geometry-three-role-lower-bounds",
        "photoDeficit": max(0, 20 - nphotos),
        "boardDeficit": max(0, 60 - nboards),
        "deficitsAreLowerBounds": True,
        "historyModified": False,
    }
