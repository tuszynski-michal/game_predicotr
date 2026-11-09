"""Inherit one render choice from the current A labels, never abandoned sessions."""

from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from game_predictor_api.domain.grid_cell_content import ContentError, ContentRevision
from game_predictor_api.domain.grid_training_cohorts import digest

from .grid_cell_content_models import GridCellContentRevisionModel as Revision
from .grid_cell_content_models import GridCellContentSessionModel as Measurement
from .grid_content_oracle_context import require_current_evaluation_contract


def select_a_render_contract(
    session: Session,
    root: Path,
    game: UUID,
    split: dict[str, Any],
    target_nodes: dict[str, dict[int, Any]],
) -> dict[str, Any] | None:
    selected: list[tuple[ContentRevision | None, Any]] = []
    for source in split["sources"]:
        if (
            source.get("validationPurpose") != "A"
            or not source.get("representative")
            or source.get("detectorExcluded")
            or source.get("contentExcluded")
            or not source.get("eligibleBoards")
        ):
            continue
        for index in target_nodes.get(source["sourceId"], {}):
            row = session.scalar(
                select(Revision)
                .where(
                    Revision.game_id == game,
                    Revision.pixel_sha256 == source["pixelSha256"],
                    Revision.position_index == index,
                )
                .order_by(Revision.revision.desc())
                .limit(1)
            )
            annotation = ContentRevision.model_validate(row.document) if row is not None else None
            if (
                row is not None
                and annotation is not None
                and annotation.sha256 != row.document_sha256
            ):
                raise ContentError("CONTENT_REFERENCE_CHECKSUM", "The current A label changed.")
            measured = (
                None
                if annotation is None or annotation.sessionId is None
                else session.get(Measurement, (game, annotation.sessionId))
            )
            selected.append((annotation, measured))
    contracts = [
        m.document["evaluationContract"]
        for _, m in selected
        if m is not None and m.document.get("evaluationContract") is not None
    ]
    if not contracts:
        return None
    contract = contracts[0]
    session_ids = set()
    for annotation, measured in selected:
        if (
            annotation is None
            or annotation.origin != "manual_blind"
            or annotation.passNumber != 2
            or not annotation.reference.humanApproved
            or measured is None
            or measured.phase != "frozen"
            or measured.report is None
            or measured.document.get("evaluationContract") != contract
            or measured.report.get("evaluationContract") != contract
            or measured.report.get("state") != "ready"
            or measured.report.get("qualificationState") != "ready"
            or measured.report.get("sha256")
            != digest({k: v for k, v in measured.report.items() if k != "sha256"})
            or measured.progress["pass2"].get(
                f"{annotation.source.sourceRepresentativeSha256}:{annotation.reference.positionIndex}"
            )
            != annotation.reference.revision
        ):
            raise ContentError(
                "CONTENT_A_RENDER_SELECTION_REQUIRED",
                "A needs one frozen measurement for this crop.",
            )
        session_ids.add(str(measured.id))
    if len(session_ids) != 1:
        raise ContentError(
            "CONTENT_A_RENDER_SELECTION_REQUIRED", "A references mixed measurements."
        )
    require_current_evaluation_contract(session, root, game, contract)
    return dict(contract)
