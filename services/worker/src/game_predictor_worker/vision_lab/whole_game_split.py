"""D-456 pilot: freeze whole games without inventing verified families or timings."""

from collections import Counter

from .annotation_contracts import AnnotationState, FrozenSplit, SplitRequest
from .annotations import digest
from .catalog import Catalog
from .geometry_qualification import (
    WHOLE_GAME_PILOT_POLICY,
    full_human_targets,
    geometry_role_eligible,
)
from .photo_review import photo_accepted
from .splits import build_components, component_fingerprints


def freeze_whole_game_split(
    catalog: Catalog, state: AnnotationState, request: SplitRequest
) -> FrozenSplit:
    """Called after the common purpose/cohort validation in freeze_splits."""
    partitions = request.game_partitions
    if partitions is None:
        raise ValueError("PILOT_GAME_PARTITIONS_REQUIRED")
    if request.measurement_source_ids or request.difficulties:
        raise ValueError("PILOT_MEASUREMENT_NOT_SUPPORTED")
    counts: Counter[str] = Counter(partitions.values())
    if (
        set(partitions) != {source.game_id for source in catalog.sources.values()}
        or counts["development"] < 1
        or any(counts[partition] != 1 for partition in ("validation", "final_test", "unseen_game"))
        or partitions.get(request.unseen_game_id) != "unseen_game"
    ):
        raise ValueError("PILOT_GAME_PARTITIONS_INVALID")
    cohort = set(request.geometry_source_ids or [])
    components = build_components(catalog, state)
    for ids in components.values():
        if len({partitions[catalog.sources[source_id].game_id] for source_id in ids}) != 1:
            raise ValueError("PILOT_CROSS_PARTITION_COMPONENT")
        if cohort.intersection(ids) and any(
            not geometry_role_eligible(
                state, catalog.sources[source_id], WHOLE_GAME_PILOT_POLICY, cohort
            )
            for source_id in ids
        ):
            raise ValueError("COMPARISON_OR_777_PROVENANCE_UNRESOLVED")
    targets = {}
    assignments = {}
    for source_id in sorted(cohort):
        source = catalog.sources[source_id]
        if not photo_accepted(state, source):
            raise ValueError("PHOTO_REVIEW_ACCEPTANCE_REQUIRED")
        source_targets = full_human_targets(state, source)
        if not source_targets:
            raise ValueError("PILOT_FULL_GEOMETRY_REQUIRED")
        if any(
            item.topology.columns != 5 or item.topology.rows != 3
            for item in source_targets.values()
        ):
            raise ValueError("PILOT_TOPOLOGY_NOT_SUPPORTED")
        targets.update(source_targets)
        assignments[source_id] = partitions[source.game_id]
    if set(assignments.values()) != {"development", "validation", "final_test", "unseen_game"}:
        raise ValueError("PILOT_GAME_PARTITIONS_INVALID")
    data = dict(
        purpose="geometry",
        policy_version=WHOLE_GAME_PILOT_POLICY,
        revision=state.revision + 1,
        unseen_game_id=request.unseen_game_id,
        seed=request.seed,
        game_partitions=dict(sorted(partitions.items())),
        geometry_source_ids=sorted(cohort),
        assignments=assignments,
        measurement={},
        exclusions={
            source_id: "NOT_IN_GEOMETRY_COHORT"
            for source_id in catalog.sources
            if source_id not in cohort
        },
        annotation_fingerprints={
            key: digest(item.model_dump())
            for key, item in state.annotations.items()
            if item.source_id in cohort
        },
        geometry_target_fingerprints={
            key: digest(item.model_dump()) for key, item in targets.items()
        },
        geometry_qualification_fingerprints={
            source_id: digest(state.geometry_qualifications[source_id].model_dump())
            for source_id in sorted(cohort)
            if catalog.sources[source_id].role != "data"
        },
        leakage_components=components,
        leakage_component_fingerprints=component_fingerprints(catalog, state, components),
    )
    return FrozenSplit.model_validate({"fingerprint": digest([state.snapshot_id, data]), **data})


def pilot_is_current(catalog: Catalog, state: AnnotationState) -> bool:
    """Validate only this new protocol, preserving the frozen record verbatim."""
    from .splits import freeze_splits

    split = state.split
    if split is None:
        return False
    try:
        request = SplitRequest(
            request_id="pilot-read-validation",
            expected_revision=state.revision,
            actor="read-validation",
            purpose=split.purpose,
            geometry_policy=WHOLE_GAME_PILOT_POLICY,
            geometry_source_ids=split.geometry_source_ids,
            game_partitions=split.game_partitions,
            unseen_game_id=split.unseen_game_id,
            seed=split.seed,
        )
        expected = freeze_splits(
            catalog, state.model_copy(update={"revision": split.revision - 1}), request
        )
    except ValueError:
        return False
    return expected == split
