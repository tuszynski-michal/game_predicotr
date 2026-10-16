"""Bounded metadata reads for nine physical positions; no inference or image sweep."""

import copy
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from game_predictor_api.domain.grid_quality_measurements import digest
from game_predictor_api.storage.grid_reinference import (
    SqlAlchemyGridReinferenceRepository,
    source_fence,
)


def observation(
    geometry: dict[str, Any] | None, producer: dict[str, Any] | None, reason: str | None = None
) -> dict[str, Any]:
    raw = (geometry or {}).get("latticeNodes")
    nodes = (
        [raw[index : index + 6] for index in range(0, 24, 6)]
        if (isinstance(raw, list) and len(raw) == 24)
        else None
    )
    return {
        "available": nodes is not None and reason != "PRODUCER_COVERAGE_GAP",
        "reason": reason or (None if nodes is not None else "ORIGINAL_GEOMETRY_UNAVAILABLE"),
        "nodes": nodes,
        "geometry": geometry,
        "producer": producer,
    }


def geometry_approval_fence(target: dict[str, Any]) -> dict[str, Any]:
    board, review = target.get("board") or {}, target.get("review") or {}
    return {
        "board": {
            key: board.get(key)
            for key in (
                "id",
                "source_image_id",
                "position_index",
                "sequence_number",
                "geometry_revision",
                "source_geometry_revision_id",
                "geometry_checksum_sha256",
                "board_geometry",
                "grid_rows",
                "grid_columns",
                "completeness_status",
                "unavailable_cell_indices",
                "geometry_engine_name",
                "geometry_engine_version",
                "asset_mode",
                "board_relative_path",
                "board_checksum_sha256",
                "geometry_qualification",
                "status",
            )
        },
        "review": {key: review.get(key) for key in ("id", "status", "resolution_revision")},
        "owner": {
            key: (target.get("owner") or {}).get(key)
            for key in (
                "review_item_id",
                "recognized_board_id",
                "source_image_id",
                "sequence_number",
            )
        },
        "foreignOwner": target.get("foreignOwner"),
        "issues": [
            {
                "id": cell["id"],
                "revision": cell.get("revision"),
                "qualityIssue": cell.get("quality_issue"),
            }
            for cell in target.get("cells", [])
            if cell.get("quality_issue") == "grid_issue" and cell.get("review_state") == "pending"
        ],
        "pending": target.get("pending"),
        "cells": target.get("cells", []),
        "renders": target.get("renders", []),
    }


def own_target(target: dict[str, Any]) -> bool:
    board, review, owner = target.get("board"), target.get("review"), target.get("owner")
    if not board or not review or target.get("foreignOwner") is not None:
        return False
    if owner is None:
        # The existing unique live pending review is the first-save owner
        # before symbol decisions materialize a canonical sequence.
        return (
            review.get("status") in ("pending", "accepted", "corrected")
            and board.get("status") != "rejected"
        )
    return bool(
        board
        and review
        and owner
        and target.get("foreignOwner") is None
        and owner.get("recognized_board_id") == board["id"]
        and owner.get("review_item_id") == review["id"]
        and owner.get("source_image_id") == board["source_image_id"]
    )


def current_targets(session: Session, game: UUID, source: UUID) -> dict[int, dict[str, Any]]:
    from pathlib import Path

    # The caller already bound the connection's READ/RLS route. Plain Session
    # prevents the generic text-SQL event from upgrading a safe GET to WRITE.
    with Session(bind=session.connection()) as reader:
        targets = {
            row["positionIndex"]: row
            for row in SqlAlchemyGridReinferenceRepository(reader, Path(".")).source_targets(
                game, source, {"categories": ["all_automatic", "deferred"]}
            )
        }
        for row in reader.execute(
            text(
                "SELECT to_jsonb(m) FROM board_render_manifests m "
                "JOIN recognized_boards b ON b.game_id=m.game_id AND b.id=m.recognized_board_id "
                "AND b.geometry_revision=m.geometry_revision "
                "WHERE b.game_id=:game AND b.source_image_id=:source "
                "ORDER BY b.position_index,m.geometry_revision"
            ),
            {"game": game, "source": source},
        ).scalars():
            for target in targets.values():
                if (target.get("board") or {}).get("id") == row["recognized_board_id"]:
                    target.setdefault("renders", []).append(row)
        return targets


def read_source(session: Session, game: UUID, source: UUID) -> dict[str, Any] | None:
    return (
        session.connection()
        .execute(
            text("SELECT to_jsonb(s) FROM source_images s WHERE s.game_id=:game AND s.id=:source"),
            {"game": game, "source": source},
        )
        .scalar_one_or_none()
    )


def approval_blocker(session: Session, game: UUID, target: dict[str, Any]) -> str | None:
    """Use the existing writer's read-only eligibility and provenance guard."""
    from game_predictor_api.domain.image_grid_reviews import ImageGridReviewError
    from game_predictor_api.storage.virtual_grid_geometry_repository import (
        SqlAlchemyVirtualGridGeometryRepository,
    )

    review = target.get("review") or {}
    if not review.get("id") or not review.get("import_job_id"):
        return "CURRENT_REVIEW_UNAVAILABLE"
    try:
        with Session(bind=session.connection()) as reader:
            SqlAlchemyVirtualGridGeometryRepository(reader).virtual_geometry_context(
                game_id=game,
                import_job_id=UUID(review["import_job_id"]),
                review_item_id=UUID(review["id"]),
                pending_geometry_id=None,
            )
    except ImageGridReviewError as error:
        return error.code
    return None


def original_target(
    session: Session, game: UUID, metadata: dict[str, Any], target: dict[str, Any]
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[dict[str, Any]]]:
    """Follow explicit per-cell previous-source edges, never chronology or node similarity."""
    from game_predictor_api.domain.neural_grid_proposal import validate_neural_source_binding

    board, review = target.get("board") or {}, target.get("review") or {}
    pointer, number = board.get("source_geometry_revision_id"), board.get("geometry_revision")
    geometry = board.get("board_geometry")
    if (
        not pointer
        or not review
        or board.get("sequence_number") is None
        or not isinstance(number, int)
    ):
        return None, None, []
    seen = set()
    lineage: list[dict[str, Any]] = []
    for _ in range(100):
        if pointer in seen:
            return None, None, []
        seen.add(pointer)
        revision = session.execute(
            text(
                "SELECT to_jsonb(g) FROM image_source_geometry_revisions g "
                "WHERE game_id=:game AND source_image_id=:source AND id=:id"
            ),
            {"game": game, "source": metadata["id"], "id": pointer},
        ).scalar_one_or_none()
        if revision is None or any(
            revision.get(key) != metadata.get(source_key)
            for key, source_key in (
                ("source_checksum_sha256", "checksum_sha256"),
                ("normalized_pixel_checksum_sha256", "normalized_pixel_checksum_sha256"),
            )
        ):
            return None, None, []
        slot = next(
            (
                value
                for value in revision["board_geometries"]
                if value.get("positionIndex") == board["position_index"]
            ),
            None,
        )
        if slot is None or slot.get("sequenceNumber") != board["sequence_number"]:
            return None, None, []
        if revision["geometry_source"] == "auto":
            initialization = revision.get("global_initialization") or {}
            proof = (
                initialization.get("gridReinference")
                or initialization.get("v3EngineAcceptance")
                or {}
            )
            proposal, binding = proof.get("proposal"), proof.get("binding")
            if not proposal or not binding:
                return geometry, None, []
            validate_neural_source_binding(binding, proposal)
            assignment = next(
                (
                    value
                    for value in binding["assignments"]
                    if value["positionIndex"] == board["position_index"]
                ),
                None,
            )
            detection = next(
                (
                    value
                    for value in proposal["detections"]
                    if assignment and value["detectionId"] == assignment["detectionId"]
                ),
                None,
            )
            if (
                proposal["gameId"] != str(game)
                or proposal["sourceChecksumSha256"] != metadata["checksum_sha256"]
                or binding["confirmedRange"]["sequenceRangeStart"] + board["position_index"]
                != board["sequence_number"]
                or detection is None
                or not geometry
                or geometry.get("latticeNodes") != detection.get("latticeNodes")
                or geometry.get("detectionId") != detection["detectionId"]
                or geometry.get("neuralProposalChecksumSha256")
                != proposal["proposalChecksumSha256"]
            ):
                return None, None, []
            snapshot = proposal["engineSnapshot"]
            if proof.get("modelSnapshot", snapshot) != snapshot:
                return None, None, []
            assigned = {value["detectionId"] for value in binding["assignments"]}
            extras = [
                copy.deepcopy(value)
                for value in proposal["detections"]
                if value["detectionId"] not in assigned
            ]
            return (
                geometry,
                {
                    "sourceRevisionId": revision["id"],
                    "sourceRevision": revision["revision"],
                    "engineSnapshot": snapshot,
                    "operationId": proof.get("operationId"),
                    "producingImportJobId": metadata["import_job_id"],
                    "proposalChecksumSha256": proposal["proposalChecksumSha256"],
                    "binding": binding,
                    "boardId": board["id"],
                    "reviewItemId": review["id"],
                    "positionIndex": board["position_index"],
                    "sequenceNumber": board["sequence_number"],
                    "geometryRevision": number,
                    "lineage": lineage,
                },
                extras,
            )
        # Manual changes retain explicit before/after source references in the
        # existing cell audit. Missing or divergent edges are coverage gaps.
        edges = list(
            session.execute(
                text("""SELECT DISTINCT cell_review_id,
            previous_source_geometry_revision_id FROM image_symbol_review_events
            WHERE game_id=:game AND review_item_id=:review AND action='geometry_invalidated'
            AND source_geometry_revision_id=:pointer AND geometry_revision=:number LIMIT 16"""),
                {"game": game, "review": review["id"], "pointer": pointer, "number": number},
            ).all()
        )
        parents = {
            str(row.previous_source_geometry_revision_id)
            for row in edges
            if row.previous_source_geometry_revision_id is not None
        }
        if (
            len(edges) != 15
            or len(parents) != 1
            or len({row.cell_review_id for row in edges}) != 15
        ):
            return None, None, []
        parent = next(iter(parents))
        lineage.append(
            {
                "sourceRevisionId": pointer,
                "previousSourceRevisionId": parent,
                "boardGeometryRevision": number,
                "proof": "15-cell-geometry-invalidated",
            }
        )
        number -= 1
        if number < 0:
            return None, None, []
        if number == 0:
            original = review.get("snapshot") or {}
            original_geometry = original.get("geometry")
            prior = session.execute(
                text(
                    "SELECT geometry_checksum_sha256 FROM image_source_geometry_revisions "
                    "WHERE game_id=:game AND source_image_id=:source AND id=:id"
                ),
                {"game": game, "source": metadata["id"], "id": parent},
            ).scalar_one_or_none()
            if (
                original.get("sourceChecksumSha256") != metadata["checksum_sha256"]
                or original.get("geometryChecksumSha256") != prior
            ):
                return None, None, []
            geometry = original_geometry
        else:
            record = session.execute(
                text(
                    "SELECT to_jsonb(g) FROM image_board_geometry_revisions g "
                    "WHERE game_id=:game AND recognized_board_id=:board AND review_item_id=:review "
                    "AND revision=:number AND source_geometry_revision_id=:parent"
                ),
                {
                    "game": game,
                    "board": board["id"],
                    "review": review["id"],
                    "number": number,
                    "parent": parent,
                },
            ).scalar_one_or_none()
            if record is None:
                return None, None, []
            geometry = record["geometry"]
        pointer = parent
    return None, None, []


def freeze_member(session: Session, game: UUID, source: UUID) -> dict[str, Any]:
    metadata = read_source(session, game, source)
    assert metadata is not None
    targets = current_targets(session, game, source)
    unexpected: list[dict[str, Any]] = []
    extra_seen: set[str] = set()
    positions = []
    for index in range(9):
        target = targets.get(index) or {
            "board": None,
            "review": None,
            "pending": None,
            "cells": [],
            "owner": None,
            "foreignOwner": None,
            "positionIndex": index,
            "sequenceNumber": None,
        }
        board, review = target["board"] or {}, target["review"] or {}
        geometry, producer, extras = original_target(session, game, metadata, target)
        for extra in extras:
            assert producer is not None
            key = digest([producer["proposalChecksumSha256"], extra])
            if key not in extra_seen:
                unexpected.append(extra)
                extra_seen.add(key)
        original = observation(
            geometry, producer, "PRODUCER_COVERAGE_GAP" if producer is None else None
        )
        current = observation(
            board.get("board_geometry"), None, None if board else "CURRENT_GEOMETRY_UNAVAILABLE"
        )
        fence = geometry_approval_fence(target)
        blocker = approval_blocker(session, game, target)
        eligible = bool(
            blocker is None
            and current["available"]
            and own_target(target)
            and not fence["issues"]
            and board.get("sequence_number") is not None
            and board.get("status") != "rejected"
            and review.get("status") != "superseded"
            and board.get("completeness_status") == "complete"
            and not board.get("unavailable_cell_indices")
            and board.get("grid_rows") == 3
            and board.get("grid_columns") == 5
            and board.get("geometry_checksum_sha256") is not None
        )
        positions.append(
            {
                "positionIndex": index,
                "sequenceNumber": target.get("sequenceNumber"),
                "original": original,
                "current": current,
                "reviewItemId": review.get("id"),
                "targetSha256": digest(fence),
                "targetFence": fence,
                "ownership": "own"
                if own_target(target)
                else (
                    "foreign" if target.get("owner") or target.get("foreignOwner") else "unknown"
                ),
                "currentManualSymbolCount": 0,
                "currentSymbolCellCount": len(target["cells"]),
                "approvalEligible": eligible,
                "approvalBlocker": blocker
                if blocker
                else (None if eligible else "TARGET_INELIGIBLE"),
            }
        )
    return {
        "sourceId": str(source),
        "importJobId": metadata["import_job_id"],
        "source": metadata,
        "sourceFence": source_fence(metadata),
        "positions": positions,
        "unexpectedDetections": unexpected,
    }


def symbol_confirmation_count(target: dict[str, Any], own_symbol_ids: set[str]) -> int:
    board = target.get("board") or {}
    return sum(
        bool(
            cell.get("review_state") == "approved"
            and cell.get("assignment_source") in ("human", "board_decision")
            and cell.get("assigned_symbol_id") in own_symbol_ids
            and cell.get("source_available") is True
            and not cell.get("quality_issue")
            and cell.get("geometry_revision") == board.get("geometry_revision")
            and cell.get("source_geometry_revision_id") == board.get("source_geometry_revision_id")
            and cell.get("approved_geometry_revision") == cell.get("geometry_revision")
            and cell.get("approved_source_geometry_revision_id")
            == cell.get("source_geometry_revision_id")
            and (
                (
                    cell.get("rendered_pixel_checksum_sha256") is not None
                    and cell.get("approved_rendered_pixel_checksum_sha256")
                    == cell.get("rendered_pixel_checksum_sha256")
                )
                or (
                    cell.get("crop_checksum_sha256") is not None
                    and cell.get("approved_crop_checksum_sha256")
                    == cell.get("crop_checksum_sha256")
                )
            )
        )
        for cell in target.get("cells", [])
    )
