"""Projection into a newly frozen cohort; historical snapshots remain byte-identical."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from game_predictor_api.domain.grid_cell_content import (
    ContentError,
    ContentRevision,
    content_source_identity,
    same_content_frame,
)
from game_predictor_api.domain.grid_training_cohorts import GridCohortError, digest, exact_lattice

from .grid_cell_content_models import GridCellContentRevisionModel as Revision
from .grid_cell_content_models import GridCellContentSessionModel as Measurement


def content_pin(
    session: Session,
    game: UUID,
    source: dict[str, Any],
    target: dict[str, Any],
    *,
    purpose: str,
) -> dict[str, Any]:
    """Missing labels are explicit absence, never estimated from the geometry."""
    row = session.scalar(
        select(Revision)
        .where(
            Revision.game_id == game,
            Revision.pixel_sha256 == source["normalized_pixel_checksum_sha256"],
            Revision.position_index == target["positionIndex"],
        )
        .order_by(Revision.revision.desc())
        .limit(1)
    )
    if row is None:
        return {}
    annotation = ContentRevision.model_validate(row.document)
    if annotation.sha256 != row.document_sha256:
        raise ContentError("CONTENT_REFERENCE_CHECKSUM", "The retained label checksum differs.")
    if not annotation.reference.humanApproved:
        return {}
    target_source = content_source_identity(source)
    if (
        annotation.reference.gameId != game
        or not same_content_frame(annotation.source, target_source)
        or annotation.sequenceNumber != target["sequenceNumber"]
    ):
        raise ContentError(
            "CONTENT_REFERENCE_IDENTITY_CONFLICT",
            "The content label and target normalized frame or sequence differ.",
        )
    if purpose == "A":
        measured = (
            None
            if annotation.sessionId is None
            else session.get(Measurement, (game, annotation.sessionId))
        )
        key = f"{row.pixel_sha256}:{row.position_index}"
        if (
            annotation.origin != "manual_blind"
            or annotation.passNumber != 2
            or measured is None
            or measured.phase != "frozen"
            or measured.report is None
            or measured.report.get("state") != "ready"
            or measured.report.get("qualificationState") != "ready"
            or measured.progress["pass2"].get(key) != row.revision
        ):
            return {}
    return {
        "contentReferenceSha256": row.document_sha256,
        "contentReferenceRevision": row.revision,
        "contentAnnotation": row.document,
        "contentTargetSource": target_source.model_dump(mode="json"),
        **({"contentOracle": row.oracle} if row.oracle is not None else {}),
    }


def apply_blind_a_geometry(label: dict[str, Any]) -> dict[str, Any]:
    """New content policy evaluates A against the repeated manual measurement."""
    if "contentAnnotation" not in label:
        raise GridCohortError("CONTENT_BLIND_A_REQUIRED", "A requires a frozen blind reference.")
    annotation = ContentRevision.model_validate(label["contentAnnotation"])
    if (
        annotation.origin != "manual_blind"
        or annotation.passNumber != 2
        or annotation.measuredNodes is None
    ):
        raise GridCohortError("CONTENT_BLIND_A_REQUIRED", "A requires the second blind geometry.")
    nodes, cells = exact_lattice(
        {"latticeNodes": [{"x": x, "y": y} for x, y in annotation.measuredNodes]},
        annotation.source.width,
        annotation.source.height,
    )
    assert annotation.approvedAt is not None
    pin = {
        "version": "blind-content-geometry-reference-v1",
        "sessionId": str(annotation.sessionId),
        "contentRevision": annotation.reference.revision,
        "contentReferenceSha256": annotation.sha256,
        "nodesSha256": digest(nodes),
        "passNumber": 2,
    }
    return {
        **label,
        "nodes": nodes,
        "blindGeometry": pin,
        "canonicalApproval": label["approval"],
        "canonicalRender": label["render"],
        "approval": {
            "origin": "human_corrected",
            "weight": 4,
            "basis": "blind-content-pass2",
            "actor": annotation.actor,
            "at": annotation.approvedAt.isoformat(),
            "sessionId": str(annotation.sessionId),
            "contentRevision": annotation.reference.revision,
        },
        "render": {
            **label["render"],
            "cellQuads": cells,
            "basis": "blind-content-pass2",
            "existingManifest": False,
        },
    }


def require_current_content_pin(session: Session, game: UUID, target: dict[str, Any]) -> None:
    if "contentAnnotation" not in target:
        return
    annotation = ContentRevision.model_validate(target["contentAnnotation"])
    row = session.scalar(
        select(Revision)
        .where(
            Revision.game_id == game,
            Revision.pixel_sha256 == annotation.reference.sourceRepresentativeSha256,
            Revision.position_index == annotation.reference.positionIndex,
        )
        .order_by(Revision.revision.desc())
        .limit(1)
    )
    if (
        row is None
        or row.document_sha256 != target.get("contentReferenceSha256")
        or row.revision != target.get("contentReferenceRevision")
        or digest(row.document) != row.document_sha256
        or row.live_source_image_id is None
    ):
        raise ContentError(
            "CONTENT_REFERENCE_STALE",
            "The frozen independent content reference is no longer current.",
        )
