"""Read-only, cohort-scoped counts; no images, hints, model execution or label writes."""

from collections import Counter
from typing import Any
from uuid import UUID

from game_predictor_api.domain.grid_cell_content import ContentRevision, same_content_frame
from game_predictor_api.domain.grid_training_cohorts import digest

from .grid_cell_content import SqlAlchemyGridCellContentRepository
from .grid_quality_observations import current_targets
from .production_crop_capture import _classes


def training_inventory(
    repo: SqlAlchemyGridCellContentRepository, game: UUID, cohort: UUID, manifest: str
) -> dict[str, Any]:
    from game_predictor_api.domain.grid_cell_content import content_source_identity

    repo.bind(game)
    snapshot = repo.snapshot(game, cohort, manifest)
    rows = list(snapshot.sources())
    if len(rows) > 2000:
        raise ValueError("CONTENT_INVENTORY_SCOPE_LIMIT")
    counts: dict[str, Counter[str]] = {}
    reasons: dict[str, Counter[str]] = {}
    for source in rows:
        role = source.get("validationPurpose") or source.get("role") or "UNASSIGNED"
        counter = counts.setdefault(role, Counter())
        failures = reasons.setdefault(role, Counter())
        counter["sources"] += 1
        if not source.get("used"):
            continue
        counter["usedSources"] += 1
        live = current_targets(repo.session, game, UUID(source["sourceId"]))
        identity = content_source_identity({**source["sourceIdentity"], "id": source["sourceId"]})
        for target in source["targets"]:
            counter["frozenGeometryBoards"] += 1
            counter["frozenRenderReferenceBoards"] += int("productionContentReference" in target)
            counter["frozenContentBoards"] += int("contentAnnotation" in target)
            frozen = target.get("contentAnnotation")
            if frozen:
                counter["frozenOutlineCells"] += sum(
                    c.get("quad") is not None for c in frozen["reference"]["cells"]
                )
            annotation_row = repo.latest(
                game, identity.sourceRepresentativeSha256, target["positionIndex"]
            )
            if annotation_row is not None:
                annotation = ContentRevision.model_validate(annotation_row.document)
                if (
                    annotation.sha256 != annotation_row.document_sha256
                    or not same_content_frame(annotation.source, identity)
                    or annotation.sequenceNumber != target["sequenceNumber"]
                ):
                    failures["CONTENT_LIVE_IDENTITY_CONFLICT"] += 1
                else:
                    counter["liveContentBoards"] += 1
                    counter["liveApprovedContentBoards"] += int(annotation.reference.humanApproved)
                    counter["liveOutlineCells"] += sum(
                        c.quad is not None for c in annotation.reference.cells
                    )
            current = live.get(target["positionIndex"])
            if current is None:
                failures["CURRENT_TARGET_MISSING"] += 15
                continue
            board = current["board"]
            if board.get("sequence_number") != target["sequenceNumber"]:
                failures["CURRENT_SEQUENCE_CHANGED"] += 15
                continue
            counter["liveGeometryBoards"] += int(
                len((board.get("board_geometry") or {}).get("latticeNodes", [])) == 24
            )
            for cell in _classes(repo.session, game, current):
                if cell["state"] == "available":
                    counter["liveHumanClassCells"] += 1
                else:
                    failures[cell["reason"]] += 1
    keys = (
        "sources",
        "usedSources",
        "frozenGeometryBoards",
        "frozenRenderReferenceBoards",
        "frozenContentBoards",
        "frozenOutlineCells",
        "liveContentBoards",
        "liveApprovedContentBoards",
        "liveOutlineCells",
        "liveGeometryBoards",
        "liveHumanClassCells",
    )
    body = {
        "version": "content-training-inventory-v1",
        "gameId": str(game),
        "cohortId": str(cohort),
        "manifestSha256": manifest,
        "scope": "selected-cohort-used-targets",
        "roleSourcesScope": "all-frozen-cohort-members",
        "globalGameCounts": False,
        "roles": {
            role: {
                **{key: counts[role][key] for key in keys},
                "reasonCounts": dict(sorted(reasons[role].items())),
            }
            for role in sorted(counts)
        },
        "contentReadiness": repo.readiness(game, cohort, manifest),
        "measuredModelQuality": "not_measured",
        "domainWrites": False,
        "pixelsRead": False,
    }
    return {**body, "sha256": digest(body)}
