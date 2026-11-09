"""D-597: repeatability may diagnose clipping, but never qualify that render."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from game_predictor_api.domain.grid_cell_content import (
    ContentRevision,
    ContentTarget,
    oracle_qualification,
)
from game_predictor_api.domain.grid_content_repeatability import repeatability_report
from game_predictor_api.domain.grid_training_cohorts import digest

from .grid_cell_content_models import GridCellContentRevisionModel as Revision
from .grid_cell_content_models import GridCellContentSessionModel as Measurement


def diagnostic_render_oracle(
    row: Revision, annotation: ContentRevision, measured: Measurement
) -> bool:
    """Only witnessed rendering of visible human labels may explain a blocked crop."""
    oracle = row.oracle
    key = f"{row.pixel_sha256}:{row.position_index}"
    context = measured.document.get("oracleContexts", {}).get(key)
    if not isinstance(oracle, dict) or not isinstance(context, dict):
        return False
    cells = oracle.get("cells", [])
    if not isinstance(cells, list) or any(not isinstance(cell, dict) for cell in cells):
        return False
    if (
        context.get("state") != "available"
        or annotation.origin != "manual_blind"
        or annotation.passNumber != 2
        or annotation.sessionId != measured.id
        or not annotation.reference.humanApproved
        or annotation.sha256 != row.document_sha256
        or oracle.get("version") != "production-cell-content-oracle-v1"
        or oracle.get("sha256") != digest({k: v for k, v in oracle.items() if k != "sha256"})
        or oracle.get("contentReferenceSha256") != annotation.sha256
        or oracle.get("contentReferenceRevision") != row.revision
        or oracle.get("humanGeometrySha256") != digest(annotation.measuredNodes)
        or oracle.get("renderConfiguration") != context.get("renderConfiguration")
        or oracle.get("classifierSnapshotSha256")
        != digest({k: context[k] for k in ("classifier", "renderConfiguration") if k in context})
        or len(cells) != 15
        or {c.get("cellIndex") for c in cells} != set(range(15))
    ):
        return False
    for cell in cells:
        content = annotation.reference.cells[cell["cellIndex"]]
        if (
            content.state != "visible"
            or cell.get("contentState") != "visible"
            or cell.get("state") not in {"preserved", "clipped"}
            or any(
                not isinstance(cell.get(key), str)
                or len(cell[key]) != 64
                or any(c not in "0123456789abcdef" for c in cell[key])
                for key in ("renderSpecSha256", "renderedPixelSha256")
            )
        ):
            return False
    expected = (
        "render_contract_blocked" if any(c["state"] == "clipped" for c in cells) else "checked"
    )
    return bool(oracle.get("state") == expected)


def diagnostic_measurement_ready(session: Session, game: UUID, measured: Measurement) -> bool:
    """Rebuild the stored repeatability and oracle summary; no pixels or mutations."""
    report = measured.report
    if (
        measured.phase != "frozen"
        or report is None
        or report.get("qualificationState") != "render_contract_blocked"
    ):
        return False
    try:
        targets = [ContentTarget.model_validate(t) for t in measured.document["targets"]]
        first, second, oracles = [], [], []
        for target in targets:
            key = f"{target.source.sourceRepresentativeSha256}:{target.positionIndex}"
            pair = []
            for number in (1, 2):
                revision = measured.progress[f"pass{number}"][key]
                row = session.get(
                    Revision,
                    (
                        game,
                        target.source.sourceRepresentativeSha256,
                        target.positionIndex,
                        revision,
                    ),
                )
                if row is None:
                    return False
                annotation = ContentRevision.model_validate(row.document)
                if annotation.sha256 != row.document_sha256 or annotation.sessionId != measured.id:
                    return False
                pair.append(annotation)
                if number == 2:
                    latest = session.scalar(
                        select(Revision.revision)
                        .where(
                            Revision.game_id == game,
                            Revision.pixel_sha256 == row.pixel_sha256,
                            Revision.position_index == row.position_index,
                        )
                        .order_by(Revision.revision.desc())
                        .limit(1)
                    )
                    if latest != revision or not diagnostic_render_oracle(
                        row, annotation, measured
                    ):
                        return False
                    assert row.oracle is not None
                    oracles.append(
                        {
                            "contentReferenceSha256": annotation.sha256,
                            "oracleSha256": row.oracle["sha256"],
                            "state": row.oracle["state"],
                        }
                    )
            first.append(pair[0])
            second.append(pair[1])
        repeated = repeatability_report(targets, first, second, [game])
        if repeated["state"] != "ready":
            return False
        qualification = oracle_qualification([o["state"] for o in oracles])
        summary = {k: v for k, v in qualification.items() if k != "qualificationState"}
        summary["referencesSha256"] = digest(oracles)
        body = {
            **{k: v for k, v in repeated.items() if k != "sha256"},
            "oracle": summary,
            "qualificationState": qualification["qualificationState"],
            **(
                {"evaluationContract": measured.document["evaluationContract"]}
                if "evaluationContract" in measured.document
                else {}
            ),
        }
        return bool(report == {**body, "sha256": digest(body)})
    except (KeyError, TypeError, ValueError):
        return False
