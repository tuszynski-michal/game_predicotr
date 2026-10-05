"""Pure validity and holdout checks; no symbol training policy is implied."""

from .annotation_contracts import AnnotationState
from .annotations import digest
from .catalog import Catalog
from .splits import build_components
from .symbol_contracts import LabelValidity
from .symbol_dataset_version import LabelPreviewGrant


def holdout_reason(
    state: AnnotationState,
    catalog: Catalog,
    source_id: str,
    *,
    component_members: list[str] | None = None,
    pilot_current: bool | None = None,
    policy_validated: bool = False,
) -> str | None:
    split = state.split
    if split is None:
        return None
    if policy_validated:
        return _component_holdout(state, catalog, source_id, component_members)
    if state.split_stale:
        return "HOLDOUT_POLICY_UNRESOLVED"
    games = {s.game_id for s in catalog.sources.values()}
    if split.unseen_game_id not in games or any(
        s not in catalog.sources for s in split.assignments
    ):
        return "HOLDOUT_POLICY_UNRESOLVED"
    if any(
        p not in {"development", "validation", "final_test", "unseen_game", "measurement"}
        for p in split.assignments.values()
    ):
        return "HOLDOUT_POLICY_UNRESOLVED"
    if any(
        s not in split.assignments
        or split.assignments[s] != "measurement"
        or group not in {"baseline", "hybrid"}
        for s, group in split.measurement.items()
    ):
        return "HOLDOUT_POLICY_UNRESOLVED"
    if split.policy_version == "lab-geometry-whole-game-pilot-v1":
        from .whole_game_split import pilot_is_current

        if set(split.game_partitions or {}) != games or not (
            pilot_is_current(catalog, state) if pilot_current is None else pilot_current
        ):
            return "HOLDOUT_POLICY_UNRESOLVED"
    else:
        keys = {
            "revision",
            "unseen_game_id",
            "seed",
            "assignments",
            "measurement",
            "annotation_fingerprints",
            "exclusions",
        }
        if split.policy_version != "legacy":
            if split.purpose != "geometry":
                return "HOLDOUT_POLICY_UNRESOLVED"
            keys |= {
                "purpose",
                "policy_version",
                "geometry_qualification_fingerprints",
                "geometry_target_fingerprints",
            }
            if split.policy_version in {
                "lab-geometry-cohort-split-v1",
                "lab-geometry-cohort-777-targets-v2",
            }:
                keys |= {
                    "geometry_source_ids",
                    "leakage_components",
                    "leakage_component_fingerprints",
                }
        elif split.purpose != "legacy":
            return "HOLDOUT_POLICY_UNRESOLVED"
        if (
            split.game_partitions is not None
            or digest([state.snapshot_id, split.model_dump(include=keys)]) != split.fingerprint
        ):
            return "HOLDOUT_POLICY_UNRESOLVED"
        if any(
            key not in state.annotations or digest(state.annotations[key].model_dump()) != value
            for key, value in split.annotation_fingerprints.items()
        ):
            return "HOLDOUT_POLICY_UNRESOLVED"
    return _component_holdout(state, catalog, source_id, component_members)


def _component_holdout(
    state: AnnotationState,
    catalog: Catalog,
    source_id: str,
    component_members: list[str] | None,
) -> str | None:
    split = state.split
    assert split is not None
    members = (
        component_members
        if component_members is not None
        else next(ids for ids in build_components(catalog, state).values() if source_id in ids)
    )
    for member in members:
        source = catalog.sources[member]
        partition = (split.game_partitions or {}).get(source.game_id)
        if partition in {"final_test", "unseen_game"} or source.game_id == split.unseen_game_id:
            return "HOLDOUT_NOT_RELEASED"
        if split.assignments.get(member) in {"final_test", "unseen_game"}:
            return "HOLDOUT_NOT_RELEASED"
    return None


def guard_pixels(
    state: AnnotationState,
    catalog: Catalog,
    source_id: str,
    preview_grant: LabelPreviewGrant | None = None,
) -> None:
    if source_id not in catalog.sources:
        raise KeyError("SYMBOL_SOURCE_NOT_FOUND")
    if catalog.sources[source_id].role == "comparison_only":
        raise ValueError("SYMBOL_ROLE_EXCLUDED")
    reason = (
        preview_grant.reason(state, catalog, source_id)
        if preview_grant is not None
        else holdout_reason(state, catalog, source_id)
    )
    if reason:
        raise ValueError(reason)


def qualify_symbol_sample(
    reasons: list[str], state: AnnotationState, catalog: Catalog, source_id: str
) -> LabelValidity:
    blockers = ["SYMBOL_SPLIT_NOT_FROZEN"]
    if reasons:
        blockers.append("SYMBOL_LABEL_INVALID")
    members = next(ids for ids in build_components(catalog, state).values() if source_id in ids)
    if any(catalog.sources[s].role == "comparison_only" for s in members):
        blockers.append("SYMBOL_ROLE_EXCLUDED")
    if any(
        s not in state.families or state.families[s].provenance == "unresolved" for s in members
    ):
        blockers.append("SYMBOL_PROVENANCE_UNRESOLVED")
    if any(
        catalog.sources[s].role == "777_v2_declared"
        and (s not in state.families or state.families[s].provenance != "777_v2_verified")
        for s in members
    ):
        blockers.append("SYMBOL_PROVENANCE_CONFLICT")
    if reason := holdout_reason(state, catalog, source_id):
        blockers.append(reason)
    return LabelValidity(label_valid=not reasons, reasons=reasons, training_blockers=blockers)
