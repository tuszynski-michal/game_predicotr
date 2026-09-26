"""Freeze only verified connected families, duplicates and declared derivatives."""

import random
from collections import defaultdict

from .annotation_contracts import AnnotationState, FrozenSplit, SplitRequest
from .annotations import digest
from .catalog import Catalog
from .photo_review import photo_accepted


def freeze_splits(catalog: Catalog, state: AnnotationState, request: SplitRequest) -> FrozenSplit:
    parents = {source_id: source_id for source_id in catalog.sources}

    def find(value: str) -> str:
        while parents[value] != value:
            parents[value] = parents[parents[value]]
            value = parents[value]
        return value

    def union(left: str, right: str) -> None:
        a, b = sorted((find(left), find(right)))
        parents[b] = a

    checksums: dict[str, str] = {}
    families: dict[str, str] = {}
    for source_id, source in catalog.sources.items():
        union(source_id, checksums.setdefault(source.sha256, source_id))
        decision = state.families.get(source_id)
        if decision:
            union(source_id, families.setdefault(decision.family_id, source_id))
            for other in decision.source_ids + decision.related_source_ids:
                union(source_id, other)
    groups: dict[str, list[str]] = defaultdict(list)
    for source_id in sorted(parents):
        groups[find(source_id)].append(source_id)
    approved = {
        a.source_id
        for a in state.annotations.values()
        if a.location_approved and a.presence == "present"
    }
    exclusions = {}
    eligible = {}
    for key, ids in groups.items():
        reason = None
        if any(catalog.sources[s].role != "data" for s in ids):
            reason = "COMPARISON_OR_777_PROVENANCE_UNRESOLVED"
        elif any(
            s not in state.families or state.families[s].provenance != "verified" for s in ids
        ):
            reason = "FAMILY_PROVENANCE_UNRESOLVED"
        elif any(s not in approved for s in ids):
            reason = "HUMAN_LOCATION_APPROVAL_REQUIRED"
        elif any(not photo_accepted(state, catalog.sources[s]) for s in ids):
            reason = "PHOTO_REVIEW_ACCEPTANCE_REQUIRED"
        if reason:
            exclusions.update(dict.fromkeys(ids, reason))
        else:
            eligible[key] = ids
    if request.unseen_game_id not in {s.game_id for s in catalog.sources.values()}:
        raise ValueError("UNSEEN_GAME_NOT_FOUND")
    measure = set(request.measurement_source_ids)
    if not measure or any(s not in parents or s in exclusions for s in measure):
        raise ValueError("VERIFIED_MEASUREMENT_SOURCES_REQUIRED")
    assignments: dict[str, str] = {}
    measurement: dict[str, str] = {}
    strata: dict[tuple[str, str], list[list[str]]] = defaultdict(list)
    development = []
    unseen = []
    for ids in eligible.values():
        games = {catalog.sources[s].game_id for s in ids}
        if games == {request.unseen_game_id}:
            if measure.intersection(ids):
                raise ValueError("MEASUREMENT_UNSEEN_OVERLAP")
            unseen.extend(ids)
            assignments.update(dict.fromkeys(ids, "unseen_game"))
        elif request.unseen_game_id in games:
            raise ValueError("UNSEEN_GAME_RELATED_TO_DEVELOPMENT")
        elif measure.intersection(ids):
            if len(games) != 1 or any(s not in request.difficulties for s in ids):
                raise ValueError("MEASUREMENT_STRATUM_REQUIRED")
            difficulties = {request.difficulties[s] for s in ids}
            if len(difficulties) != 1:
                raise ValueError("RELATED_MEASUREMENT_DIFFICULTY_CONFLICT")
            strata[(next(iter(games)), next(iter(difficulties)))].append(ids)
            assignments.update(dict.fromkeys(ids, "measurement"))
        else:
            development.append(ids)
    if not unseen or len(development) < 3:
        raise ValueError("INSUFFICIENT_VERIFIED_SPLIT_GROUPS")
    rng = random.Random(request.seed)
    for stratum in sorted(strata):
        group_list = strata[stratum]
        if len(group_list) < 2:
            raise ValueError("MEASUREMENT_REQUIRES_TWO_INDEPENDENT_GROUPS_PER_STRATUM")
        rng.shuffle(group_list)
        for index, ids in enumerate(group_list):
            measurement.update(dict.fromkeys(ids, "baseline" if index % 2 == 0 else "hybrid"))
    rng.shuffle(development)
    for index, ids in enumerate(development):
        partition = "validation" if index == 0 else "final_test" if index == 1 else "development"
        assignments.update(dict.fromkeys(ids, partition))
    training_topologies = {
        a.topology.columns
        for a in state.annotations.values()
        if a.location_approved
        and a.presence == "present"
        and assignments.get(a.source_id) == "development"
    }
    unseen_topologies = {
        a.topology.columns
        for a in state.annotations.values()
        if a.location_approved and a.presence == "present" and a.source_id in unseen
    }
    if not unseen_topologies.issubset(training_topologies):
        raise ValueError("UNSEEN_GAME_REMOVES_TRAINING_TOPOLOGY")
    fingerprints = {
        key: digest(item.model_dump())
        for key, item in state.annotations.items()
        if item.source_id in assignments
    }
    data = dict(
        revision=state.revision + 1,
        unseen_game_id=request.unseen_game_id,
        seed=request.seed,
        assignments=assignments,
        measurement=measurement,
        annotation_fingerprints=fingerprints,
        exclusions=exclusions,
    )
    return FrozenSplit.model_validate({"fingerprint": digest([state.snapshot_id, data]), **data})
