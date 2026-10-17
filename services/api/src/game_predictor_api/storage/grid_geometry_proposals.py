"""Same-transaction proposal decisions composed with the existing manual writer."""

import copy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4, uuid5

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from game_predictor_api.application.grid_geometry_proposals import ProposalCommandOutcome
from game_predictor_api.application.grid_reinference import digest
from game_predictor_api.application.virtual_grid_geometry import VirtualGridGeometryService
from game_predictor_api.domain.geometry_qualification import GeometryQualification
from game_predictor_api.domain.image_geometry_v2 import SourceLatticeNodes, SourcePoint
from game_predictor_api.domain.image_grid_reviews import ImageGridReviewError
from game_predictor_api.domain.image_reviews import (
    ImageReviewGeometryPoint,
    ImageReviewNotFoundError,
)
from game_predictor_api.schemas.image_reviews import OperationalImageReviewGeometryPreviewCommand
from game_predictor_api.schemas.source_lattice_geometry import to_source_lattice_nodes
from game_predictor_api.storage.grid_geometry_proposal_models import (
    GridGeometryProposalEventModel as Event,
)
from game_predictor_api.storage.grid_geometry_proposal_models import (
    GridGeometryProposalModel as Proposal,
)
from game_predictor_api.storage.grid_reinference import (
    SqlAlchemyGridReinferenceRepository,
    source_fence,
    target_fence,
)
from game_predictor_api.storage.grid_reinference_models import (
    GridReinferenceOperationModel as Operation,
)
from game_predictor_api.storage.grid_reinference_models import (
    GridReinferenceSourceModel as Source,
)
from game_predictor_api.storage.grid_reinference_models import (
    GridReinferenceTargetModel as Target,
)
from game_predictor_api.storage.image_review_repository import acquire_image_review_sequence_locks
from game_predictor_api.storage.sequence_ownership_lock import acquire_sequence_ownership_lock
from game_predictor_api.storage.virtual_grid_geometry_repository import (
    SqlAlchemyVirtualGridGeometryRepository,
)


def proposal_target_fence(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Extend the frozen 0999 domain fence with render/topology provenance."""
    board = snapshot["board"] or {}
    return {
        "base": target_fence(snapshot),
        "board": {
            key: board.get(key)
            for key in (
                "asset_mode",
                "grid_rows",
                "grid_columns",
                "geometry_qualification",
                "unavailable_cell_indices",
                "pipeline_fingerprint",
            )
        },
        "cells": [
            {
                key: cell.get(key)
                for key in (
                    "id",
                    "asset_mode",
                    "cell_index",
                    "render_identity_v2_sha256",
                    "approved_render_identity_v2_sha256",
                    "render_spec_checksum_sha256",
                )
            }
            for cell in snapshot["cells"]
        ],
    }


def error(code: str, message: str) -> dict[str, Any]:
    return {"code": "GRID_PROPOSAL_" + code, "message": message, "details": {}}


class SqlAlchemyGridGeometryProposalRepository:
    def __init__(self, session: Session, artifact_root: Path) -> None:
        self.session = session
        self.reinference = SqlAlchemyGridReinferenceRepository(session, artifact_root)
        self.geometry_repository = SqlAlchemyVirtualGridGeometryRepository(
            session, source_snapshot_policy="current_live_slots"
        )
        self.geometry = VirtualGridGeometryService(self.geometry_repository, artifact_root)

    def _target(self, game_id: UUID, target_id: UUID) -> Target:
        row = self.session.scalar(
            select(Target).where(Target.game_id == game_id, Target.target_result_id == target_id)
        )
        if row is None:
            raise ImageReviewNotFoundError("GRID_PROPOSAL_NOT_FOUND", "Target result not found.")
        return row

    def _proposal(self, game: UUID, job: UUID, review: UUID, proposal: UUID) -> Proposal:
        row = self.session.scalar(
            select(Proposal)
            .where(
                Proposal.game_id == game,
                Proposal.id == proposal,
                Proposal.import_job_id == job,
                Proposal.review_item_id == review,
            )
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise ImageReviewNotFoundError(
                "GRID_PROPOSAL_NOT_FOUND", "Proposal not found in this scope."
            )
        return row

    def _current(self, game: UUID, target: Target) -> tuple[dict[str, Any] | None, list[str]]:
        retained = self.session.get(Source, (game, target.operation_id, target.source_ordinal))
        source = self.session.execute(
            text("SELECT to_jsonb(s) FROM source_images s WHERE s.game_id=:game AND s.id=:source"),
            {"game": game, "source": target.source_image_id},
        ).scalar_one_or_none()
        if (
            retained is None
            or retained.live_source_image_id != target.source_image_id
            or source is None
        ):
            return None, ["SOURCE_MISSING"]
        if source_fence(source) != source_fence(retained.document["source"]):
            return None, ["SOURCE_CHANGED"]
        current = next(
            (
                value
                for value in self.reinference.source_targets(
                    game, target.source_image_id, {"categories": ["grid_issue", "all_automatic"]}
                )
                if value["positionIndex"] == target.position_index
            ),
            None,
        )
        if current is None:
            return None, ["TARGET_MISSING"]
        if current["kind"] != "grid_issue":
            return current, ["ISSUE_CHANGED"]
        if proposal_target_fence(current) != proposal_target_fence(target.snapshot):
            return current, ["TARGET_CHANGED"]
        return current, []

    def _view(self, proposal: Proposal) -> dict[str, Any]:
        target = self._target(proposal.game_id, proposal.target_result_id)
        _, reasons = self._current(proposal.game_id, target)
        if proposal.state != "pending":
            reasons = ["PROPOSAL_" + proposal.state.upper(), *reasons]
        return {
            "id": str(proposal.id),
            "revision": proposal.revision,
            "state": proposal.state,
            "candidate": proposal.document,
            "accepted": proposal.accepted,
            "applicable": not reasons,
            "reasons": reasons,
        }

    def get_proposal(
        self, game_id: UUID, import_job_id: UUID, review_item_id: UUID, proposal_id: UUID
    ) -> dict[str, Any]:
        self.reinference.bind(game_id, write=False)
        return self._view(self._proposal(game_id, import_job_id, review_item_id, proposal_id))

    def list_proposals(
        self, game_id: UUID, import_job_id: UUID, review_item_id: UUID
    ) -> dict[str, Any]:
        self.reinference.bind(game_id, write=False)
        proposals = list(
            self.session.scalars(
                select(Proposal)
                .where(
                    Proposal.game_id == game_id,
                    Proposal.import_job_id == import_job_id,
                    Proposal.review_item_id == review_item_id,
                )
                .order_by(Proposal.id)
                .limit(100)
            )
        )
        known = {row.target_result_id for row in proposals}
        # Direct per-review JSON identity lookup, bounded independently of operation pages.
        targets = self.session.scalars(
            select(Target)
            .where(
                Target.game_id == game_id,
                Target.outcome == "proposal_ready",
                text(
                    "(snapshot #>> '{review,id}')=:review "
                    "AND (snapshot #>> '{source,import_job_id}')=:job"
                ),
            )
            .params(review=str(review_item_id), job=str(import_job_id))
            .order_by(Target.ordinal, Target.target_result_id)
            .limit(100)
        )
        candidates = []
        for target in targets:
            if target.target_result_id not in known:
                try:
                    candidate = self._candidate(target)
                except ImageReviewNotFoundError as invalid:
                    if invalid.code != "GRID_PROPOSAL_RESULT_INVALID":
                        raise
                    continue
                _, reasons = self._current(game_id, target)
                operation = self.session.get(Operation, (game_id, target.operation_id))
                assert operation is not None
                candidates.append(
                    {
                        "targetResultId": str(target.target_result_id),
                        "originalGeometry": candidate,
                        "modelSnapshot": operation.document["modelSnapshot"],
                        "applicable": not reasons,
                        "reasons": reasons,
                    }
                )
        return {"proposals": [self._view(row) for row in proposals], "candidates": candidates}

    def command(
        self,
        game_id: UUID,
        import_job_id: UUID,
        review_item_id: UUID,
        proposal_id: UUID | None,
        kind: str,
        payload: dict[str, Any],
        actor: str,
    ) -> ProposalCommandOutcome:
        self.reinference.bind(game_id)
        key = UUID(payload["idempotencyKey"])
        command = {
            "gameId": str(game_id),
            "importJobId": str(import_job_id),
            "reviewItemId": str(review_item_id),
            "proposalId": str(proposal_id),
            "kind": kind,
            "payload": payload,
            "actor": actor,
        }
        sha = digest(command)
        self.reinference.key_lock(
            f"grid-proposal:{game_id}:{proposal_id if kind != 'create' else 'create'}:{kind}:{key}"
        )
        prior = self.session.scalar(
            select(Event).where(
                Event.game_id == game_id,
                Event.command_kind == kind,
                Event.idempotency_key == key,
                *(() if kind == "create" else (Event.proposal_id == proposal_id,)),
            )
        )
        if prior is not None:
            if prior.command_sha256 != sha:
                return ProposalCommandOutcome(
                    409, error("IDEMPOTENCY_CONFLICT", "Key represents another command."), None
                )
            current = (
                None
                if prior.proposal_id is None
                else self.get_proposal(game_id, import_job_id, review_item_id, prior.proposal_id)
            )
            return ProposalCommandOutcome(
                prior.document["status"], prior.document["receipt"], current
            )
        # All proposal mutators share ownership before source/item/proposal rows.
        acquire_sequence_ownership_lock(self.session, game_id=game_id)
        self.geometry_repository._ensure_projection_state(game_id)
        acquire_image_review_sequence_locks(
            self.session,
            game_id=game_id,
            review_item_id=review_item_id,
            requested_sequence_number=None,
        )
        proposal = None
        event_kind, status = "command_rejected", 409
        receipt: dict[str, Any]
        if kind == "create":
            target = self._target(game_id, UUID(payload["targetResultId"]))
            self._validate_result_scope(target, game_id, import_job_id, review_item_id)
            current, reasons = self._locked_current(game_id, target)
            if not self._live_scope(game_id, import_job_id, review_item_id, target):
                receipt = error(
                    "SOURCE_MISSING", "Candidate source or review no longer exists in scope."
                )
            else:
                proposal = self.session.scalar(
                    select(Proposal)
                    .where(
                        Proposal.game_id == game_id,
                        Proposal.target_result_id == target.target_result_id,
                    )
                    .with_for_update()
                )
                if proposal is None and reasons:
                    receipt = error(reasons[0], "Candidate source or review changed.")
                elif proposal is None:
                    operation = self.session.get(Operation, (game_id, target.operation_id))
                    assert operation is not None
                    candidate = self._candidate(target)
                    proposal = Proposal(
                        game_id=game_id,
                        id=uuid4(),
                        target_result_id=target.target_result_id,
                        operation_id=target.operation_id,
                        target_ordinal=target.ordinal,
                        import_job_id=import_job_id,
                        review_item_id=review_item_id,
                        state="pending",
                        revision=1,
                        document={
                            "schemaVersion": "grid-geometry-proposal-v1",
                            "result": copy.deepcopy(target.result),
                            "resultSha256": digest(target.result),
                            "originalGeometry": candidate,
                            "originalCandidateSha256": digest(candidate),
                            "modelSnapshot": copy.deepcopy(operation.document["modelSnapshot"]),
                            "targetFence": proposal_target_fence(target.snapshot),
                            "sourceFence": source_fence(target.snapshot["source"]),
                            "sourceImageId": str(target.source_image_id),
                            "positionIndex": target.position_index,
                            "sequenceNumber": target.snapshot["sequenceNumber"],
                            "expectedGeometryRevision": current["board"]["geometry_revision"],
                            "expectedResolutionRevision": current["review"]["resolution_revision"],
                        },
                    )
                    self.session.add(proposal)
                    self.session.flush()
                    event_kind = "created"
                else:
                    event_kind = "command_completed"
                if proposal is not None:
                    status = 200
                    receipt = {
                        "proposalId": str(proposal.id),
                        "state": proposal.state,
                        "revision": proposal.revision,
                    }
        else:
            assert proposal_id is not None
            proposal = self._proposal(game_id, import_job_id, review_item_id, proposal_id)
            target = self._target(game_id, proposal.target_result_id)
            current, reasons = self._locked_current(game_id, target)
            self.session.refresh(proposal, with_for_update=True)
            if payload["expectedProposalRevision"] != proposal.revision:
                receipt = error("REVISION_CONFLICT", "Proposal revision changed.")
            elif proposal.state != "pending":
                receipt = error("STATE_CONFLICT", "Proposal is terminal.")
            elif kind == "reject":
                proposal.state, proposal.revision = "rejected", proposal.revision + 1
                event_kind, status = "rejected", 200
                receipt = {
                    "proposalId": str(proposal.id),
                    "state": "rejected",
                    "revision": proposal.revision,
                }
            elif reasons:
                proposal.state, proposal.revision = "stale", proposal.revision + 1
                event_kind = "stale"
                receipt = error(reasons[0], "Proposal is no longer applicable.")
            elif payload["originalCandidateSha256"] != proposal.document["originalCandidateSha256"]:
                receipt = error("CANDIDATE_CONFLICT", "Original candidate checksum changed.")
            elif (
                payload["expectedGeometryRevision"] != current["board"]["geometry_revision"]
                or payload["expectedResolutionRevision"] != current["review"]["resolution_revision"]
            ):
                receipt = error("REVISION_CONFLICT", "Review revision changed.")
            else:
                actual = (
                    proposal.document["originalGeometry"]
                    if payload["mode"] == "model"
                    else payload["geometry"]
                )
                geometry = OperationalImageReviewGeometryPreviewCommand.model_validate(actual)
                if (
                    geometry.expected_geometry_revision != payload["expectedGeometryRevision"]
                    or geometry.expected_resolution_revision
                    != payload["expectedResolutionRevision"]
                ):
                    receipt = error(
                        "REVISION_CONFLICT", "Edited geometry revision differs from command."
                    )
                else:
                    try:
                        with self.session.begin_nested():
                            result = self.geometry.save_review_item(
                                game_id=game_id,
                                import_job_id=import_job_id,
                                review_item_id=review_item_id,
                                idempotency_key=uuid5(proposal.id, f"accept:{key}"),
                                expected_geometry_revision=geometry.expected_geometry_revision,
                                expected_resolution_revision=geometry.expected_resolution_revision,
                                corners=tuple(
                                    ImageReviewGeometryPoint(point.x, point.y)
                                    for point in geometry.corners
                                ),
                                lattice_nodes=to_source_lattice_nodes(geometry.lattice_nodes),
                                geometry_qualification=None
                                if geometry.geometry_qualification is None
                                else geometry.geometry_qualification.to_domain(),
                                expected_proposal_checksum_sha256=geometry.expected_proposal_checksum_sha256,
                                actor=actor,
                                created_at=datetime.now(UTC),
                            )
                    except (ImageGridReviewError, ImageReviewNotFoundError) as failure:
                        if failure.code not in {
                            "IMAGE_GRID_REVIEW_REVISION_CONFLICT",
                            "IMAGE_GRID_REVIEW_SOURCE_DRIFT",
                            "IMAGE_GRID_REVIEW_TOPOLOGY_CONFLICT",
                            "IMAGE_GRID_REVIEW_PROPOSAL_STALE",
                            "IMAGE_GRID_REVIEW_SOURCE_SLOT_CONFLICT",
                            "IMAGE_CANONICAL_SOURCE_CHECKSUM_MISMATCH",
                            "IMAGE_CANONICAL_SOURCE_PIXEL_CHECKSUM_MISMATCH",
                            "IMAGE_REVIEW_ASSET_CHECKSUM_DRIFT",
                            "IMAGE_REVIEW_ASSET_NOT_FOUND",
                        }:
                            raise
                        proposal.state, proposal.revision = "stale", proposal.revision + 1
                        event_kind = "stale"
                        receipt = error("CURRENT_GEOMETRY_CONFLICT", str(failure))
                    else:
                        actual = {
                            **actual,
                            "geometryQualification": None
                            if result.revision.geometry_qualification is None
                            else result.revision.geometry_qualification.to_dict(),
                        }
                        proposal.accepted = {
                            "mode": payload["mode"],
                            "geometry": actual,
                            "geometrySha256": digest(actual),
                            "actor": actor,
                            "manualRevisionId": str(result.revision.id),
                            "originalCandidateSha256": proposal.document["originalCandidateSha256"],
                        }
                        proposal.state, proposal.revision = "accepted", proposal.revision + 1
                        event_kind, status = "accepted", 200
                        receipt = {
                            "proposalId": str(proposal.id),
                            "state": "accepted",
                            "revision": proposal.revision,
                            "accepted": proposal.accepted,
                        }
        self.session.add(
            Event(
                game_id=game_id,
                id=uuid4(),
                proposal_id=None if proposal is None else proposal.id,
                ordinal=1
                if proposal is None
                else 1
                + (
                    self.session.scalar(
                        select(func.max(Event.ordinal)).where(
                            Event.game_id == game_id, Event.proposal_id == proposal.id
                        )
                    )
                    or 0
                ),
                kind=event_kind,
                command_kind=kind,
                idempotency_key=key,
                command_sha256=sha,
                document={
                    "actor": actor,
                    "at": datetime.now(UTC).isoformat(),
                    "command": command,
                    "status": status,
                    "receipt": receipt,
                    "revision": None if proposal is None else proposal.revision,
                },
            )
        )
        self.session.flush()
        return ProposalCommandOutcome(
            status, receipt, None if proposal is None else self._view(proposal)
        )

    def _locked_current(self, game: UUID, target: Target) -> tuple[dict[str, Any], list[str]]:
        self.session.execute(
            text("SELECT id FROM source_images WHERE game_id=:game AND id=:id FOR UPDATE"),
            {"game": game, "id": target.source_image_id},
        )
        # Ownership serializes full-board writers; explicit cell locks fence per-cell writers.
        review = target.snapshot["review"]["id"]
        self.session.execute(
            text("SELECT id FROM image_review_items WHERE game_id=:game AND id=:id FOR UPDATE"),
            {"game": game, "id": review},
        )
        self.session.execute(
            text("SELECT game_id FROM image_symbol_review_states WHERE game_id=:game FOR UPDATE"),
            {"game": game},
        )
        self.session.execute(
            text(
                "SELECT id FROM image_symbol_review_cells WHERE game_id=:game "
                "AND review_item_id=:id ORDER BY cell_index FOR UPDATE"
            ),
            {"game": game, "id": review},
        )
        current, reasons = self._current(game, target)
        return current or {}, reasons

    def _live_scope(self, game: UUID, job: UUID, review: UUID, target: Target) -> bool:
        retained = self.session.get(Source, (game, target.operation_id, target.source_ordinal))
        if retained is None or retained.live_source_image_id != target.source_image_id:
            return False
        return (
            self.session.execute(
                text(
                    "SELECT r.id FROM image_review_items r JOIN recognized_boards b "
                    "ON b.id=r.recognized_board_id JOIN source_images s ON s.id=b.source_image_id "
                    "WHERE r.game_id=:game AND b.game_id=:game AND s.game_id=:game "
                    "AND s.import_job_id=:job AND s.id=:source AND r.id=:review"
                ),
                {"game": game, "job": job, "source": target.source_image_id, "review": review},
            ).scalar_one_or_none()
            is not None
        )

    @staticmethod
    def _validate_result_scope(target: Target, game: UUID, job: UUID, review: UUID) -> None:
        result = target.result or {}
        snapshot = target.snapshot
        if snapshot.get("review", {}).get("id") != str(review) or snapshot.get("source", {}).get(
            "import_job_id"
        ) != str(job):
            raise ImageReviewNotFoundError(
                "GRID_PROPOSAL_NOT_FOUND", "Target outside review scope."
            )
        if (
            target.outcome != "proposal_ready"
            or result.get("outcome") != "proposal_ready"
            or result.get("schemaVersion") != "grid-reinference-target-result-v1"
            or snapshot.get("kind") != "grid_issue"
            or result.get("targetResultId") != str(target.target_result_id)
            or result.get("operationId") != str(target.operation_id)
            or result.get("sourceImageId") != str(target.source_image_id)
            or result.get("positionIndex") != target.position_index
            or result.get("frozenFenceSha256") != target.fingerprint_sha256
            or digest(target_fence(snapshot)) != target.fingerprint_sha256
        ):
            raise ImageReviewNotFoundError(
                "GRID_PROPOSAL_RESULT_INVALID", "Target is not a valid proposal result."
            )

    @staticmethod
    def _candidate(target: Target) -> dict[str, Any]:
        assert target.result is not None
        detection = target.result["geometry"]
        nodes = detection["latticeNodes"]
        # 0999 only emits full-visibility bound structurally valid detections here.
        if (
            not detection.get("structurallyValid")
            or len(nodes) != 24
            or detection.get("cellVisibility") != ["full"] * 15
        ):
            raise ImageReviewNotFoundError(
                "GRID_PROPOSAL_RESULT_INVALID", "Incomplete candidate geometry."
            )
        SourceLatticeNodes(tuple(SourcePoint(point["x"], point["y"]) for point in nodes))
        board = target.snapshot["board"]
        candidate = {
            # Only the legacy redundant StrictInt outline is rounded; all 24
            # source-space nodes and the immutable result retain exact floats.
            "corners": [
                {"x": int(nodes[index]["x"] + 0.5), "y": int(nodes[index]["y"] + 0.5)}
                for index in (0, 5, 23, 18)
            ],
            "latticeNodes": nodes,
            "expectedGeometryRevision": board["geometry_revision"],
            "expectedResolutionRevision": target.snapshot["review"]["resolution_revision"],
            "geometryQualification": GeometryQualification().to_dict(),
            "expectedProposalChecksumSha256": board["board_geometry"].get(
                "neuralProposalChecksumSha256"
            ),
        }
        return OperationalImageReviewGeometryPreviewCommand.model_validate(candidate).model_dump(
            mode="json", by_alias=True
        )
