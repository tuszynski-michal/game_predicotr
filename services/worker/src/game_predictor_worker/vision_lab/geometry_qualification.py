"""D-453 geometry-only qualification; never a source role or symbol approval."""

from pathlib import PurePosixPath

from .annotation_contracts import (
    AnnotationState,
    GeometryAnnotation,
    GeometryQualificationBinding,
    GeometryQualificationRequest,
    StoredGeometryQualification,
)
from .contracts import Source
from .photo_review import board_revisions, photo_accepted

TARGETS_ONLY_777_POLICY = "lab-geometry-cohort-777-targets-v2"


def historical_folder_777(source: Source) -> bool:
    """Exact immutable provenance supported by D-453 and D-455."""
    parts = PurePosixPath(source.filename).parts
    return (
        source.source_kind == "folder"
        and source.game_name == "777"
        and len(parts) >= 2
        and parts[0] == "777"
        and source.role == "comparison_only"
    )


def geometry_role_eligible(
    state: AnnotationState, source: Source, policy: str | None, cohort: set[str] | None
) -> bool:
    """D-455 exempts only unselected historical context, never a target."""
    return (
        source.role == "data"
        or (
            policy == TARGETS_ONLY_777_POLICY
            and cohort is not None
            and source.id not in cohort
            and historical_folder_777(source)
        )
        or qualification_effective(state, source)
    )


def full_human_targets(state: AnnotationState, source: Source) -> dict[str, GeometryAnnotation]:
    return {
        key: item
        for key, item in state.annotations.items()
        if item.source_id == source.id
        and item.source_sha256 == source.sha256
        and item.location_approved
        and item.full_approved
        and item.presence == "present"
        and len(item.nodes) == (item.topology.columns + 1) * (item.topology.rows + 1)
        and all(point.provenance == "human" for point in item.nodes)
    }


def validate_binding(
    state: AnnotationState, source: Source, game_id: str, binding: GeometryQualificationBinding
) -> None:
    # Folder importer stores the exact top-level game directory in both fields.
    # A comparison role alone, a substring, or a DB game name is not this evidence.
    if (
        source.id != binding.source_id
        or source.game_id != game_id
        or not historical_folder_777(source)
    ):
        raise ValueError("GEOMETRY_QUALIFICATION_HISTORICAL_777_REQUIRED")
    if binding.source_sha256 != source.sha256:
        raise ValueError("GEOMETRY_QUALIFICATION_SOURCE_CHANGED")
    if binding.expected_board_revisions != board_revisions(state, source.id):
        raise ValueError("GEOMETRY_QUALIFICATION_GEOMETRY_CHANGED")
    if not photo_accepted(state, source):
        raise ValueError("GEOMETRY_QUALIFICATION_PHOTO_ACCEPTANCE_REQUIRED")
    if not full_human_targets(state, source):
        raise ValueError("GEOMETRY_QUALIFICATION_FULL_HUMAN_TARGET_REQUIRED")


def qualification_effective(state: AnnotationState, source: Source) -> bool:
    qualification = state.geometry_qualifications.get(source.id)
    if qualification is None:
        return False
    try:
        validate_binding(state, source, qualification.game_id, qualification)
    except ValueError:
        return False
    return True


def validate_qualification_request(
    state: AnnotationState, sources: dict[str, Source], request: GeometryQualificationRequest
) -> None:
    ids = [binding.source_id for binding in request.bindings]
    if len(set(ids)) != len(ids):
        raise ValueError("GEOMETRY_QUALIFICATION_DUPLICATE_SOURCE")
    for binding in request.bindings:
        source = sources.get(binding.source_id)
        if source is None:
            raise ValueError("SOURCE_NOT_FOUND")
        validate_binding(state, source, request.game_id, binding)


def apply_qualification(
    state: AnnotationState,
    sources: dict[str, Source],
    request: GeometryQualificationRequest,
    now: str,
) -> None:
    validate_qualification_request(state, sources, request)
    for binding in request.bindings:
        state.geometry_qualifications[binding.source_id] = StoredGeometryQualification(
            **binding.model_dump(),
            policy_version=request.policy_version,
            decision_reference=request.decision_reference,
            purpose=request.purpose,
            game_id=request.game_id,
            actor=request.actor,
            decided_at=now,
            revision=state.revision + 1,
        )
    state.split_stale = state.split is not None
