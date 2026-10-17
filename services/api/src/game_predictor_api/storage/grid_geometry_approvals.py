"""Approval projection/event/receipt in one transaction, without recrop or symbol writes."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from game_predictor_api.domain.grid_quality_measurements import digest
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
)
from game_predictor_api.storage.grid_quality_measurement_models import (
    GridGeometryApprovalCommandModel as Command,
)
from game_predictor_api.storage.grid_quality_measurements import (
    SqlAlchemyGridQualityMeasurementRepository,
    conflict,
)
from game_predictor_api.storage.grid_quality_observations import (
    approval_blocker,
    current_targets,
    own_target,
    read_source,
)
from game_predictor_api.storage.grid_quality_repoint import unchanged_frozen_target
from game_predictor_api.storage.grid_reinference import source_fence
from game_predictor_api.storage.image_geometry_completeness_state_repository import (
    recompute_source_image_geometry_completeness,
)
from game_predictor_api.storage.image_review_repository import acquire_image_review_sequence_locks
from game_predictor_api.storage.models import (
    ImageBoardGeometryReviewEventModel,
    RecognizedBoardModel,
)
from game_predictor_api.storage.sequence_ownership_lock import acquire_sequence_ownership_lock
from game_predictor_api.storage.virtual_grid_geometry_repository import (
    SqlAlchemyVirtualGridGeometryRepository,
)


class SqlAlchemyGridGeometryApprovalRepository:
    def __init__(self, session: Session, artifact_root: Path) -> None:
        self.session = session
        self.measurements = SqlAlchemyGridQualityMeasurementRepository(session, artifact_root)

    def approve(
        self, game: UUID, job: UUID, review: UUID, command: dict[str, Any], actor: str
    ) -> dict[str, Any]:
        self.measurements.bind(game, write=True)
        self.measurements.key_lock(game, "approval:" + command["idempotencyKey"])
        sha = digest(
            {"game": str(game), "job": str(job), "review": str(review), "command": command}
        )
        old = self.session.get(Command, (game, UUID(command["idempotencyKey"])))
        if old:
            if (
                old.command_sha256 != sha
                or old.import_job_id != job
                or old.review_item_id != review
            ):
                conflict("IDEMPOTENCY_CONFLICT", "The approval key has different content.")
            return {"receipt": old.document["receipt"]}
        measurement = self.measurements.header(game, UUID(command["measurementId"]))
        self.measurements.store.verify(measurement.manifest_path, measurement.manifest_sha256)
        member = self.measurements.member(
            game, measurement.id, UUID(command["sourceId"]), command["sampleKind"]
        )
        position = member.frozen["positions"][command["positionIndex"]]
        if (
            measurement.manifest_sha256 != command["manifestSha256"]
            or position["targetSha256"] != command["targetSha256"]
            or position["reviewItemId"] != str(review)
            or member.frozen["importJobId"] != str(job)
        ):
            conflict("TARGET_CONFLICT", "The shown observation belongs to another target.")
        if not position["approvalEligible"] or not position["current"]["available"]:
            conflict("APPROVAL_UNAVAILABLE", "The frozen current geometry is not eligible.")
        acquire_sequence_ownership_lock(self.session, game_id=game)
        SqlAlchemyVirtualGridGeometryRepository(self.session)._ensure_projection_state(game)
        acquire_image_review_sequence_locks(
            self.session, game_id=game, review_item_id=review, requested_sequence_number=None
        )
        self.session.execute(
            text("SELECT id FROM source_images WHERE game_id=:game AND id=:source FOR UPDATE"),
            {"game": game, "source": member.source_id},
        )
        source = read_source(self.session, game, member.source_id)
        self.session.refresh(member)
        if member.live_source_image_id is None or source is None:
            conflict("SOURCE_UNAVAILABLE", "The measured source was removed.")
        if source_fence(source) != member.frozen["sourceFence"]:
            conflict("SOURCE_CHANGED", "The source identity has changed.")
        from game_predictor_api.application.image_review_assets import _resolve

        _resolve(
            self.measurements.store.root,
            source["relative_path"],
            source["checksum_sha256"],
            asset_kind="grid-quality-source",
        )
        board_id = position["targetFence"]["board"]["id"]
        board = self.session.scalar(
            select(RecognizedBoardModel)
            .where(RecognizedBoardModel.id == UUID(board_id))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        self.session.execute(
            text("SELECT id FROM image_review_items WHERE game_id=:game AND id=:review FOR UPDATE"),
            {"game": game, "review": review},
        )
        self.session.execute(
            text(
                "SELECT id FROM image_symbol_review_cells WHERE game_id=:game "
                "AND review_item_id=:review ORDER BY cell_index FOR UPDATE"
            ),
            {"game": game, "review": review},
        )
        target = current_targets(self.session, game, member.source_id).get(command["positionIndex"])
        if target is not None and approval_blocker(self.session, game, target):
            conflict(
                "CANONICAL_TARGET_UNAVAILABLE", "The current target is not eligible for review."
            )
        if (
            board is None
            or target is None
            or not own_target(target)
            or not unchanged_frozen_target(
                self.session, game, member.source_id, position["targetFence"], target
            )
        ):
            conflict(
                "TARGET_CHANGED", "The current geometry, issue, revision or owner has changed."
            )
        if board.board_geometry != position["current"]["geometry"]:
            conflict("GEOMETRY_CHANGED", "Show and assess the newer geometry before approving it.")
        checksum = board.geometry_checksum_sha256
        if not isinstance(checksum, str) or len(checksum) != 64:
            conflict("IDENTITY_UNAVAILABLE", "The exact geometry identity is unavailable.")
        at, event_id = datetime.now(UTC), uuid4()
        previous = board.approved_geometry_revision
        board.approved_geometry_revision = board.geometry_revision
        board.geometry_approved_at, board.geometry_approved_by = at, actor
        self.session.add(
            ImageBoardGeometryReviewEventModel(
                id=event_id,
                review_item_id=review,
                recognized_board_id=board.id,
                geometry_revision=board.geometry_revision,
                grid_rows=board.grid_rows,
                grid_columns=board.grid_columns,
                board_checksum_sha256=checksum,
                action="approved",
                previous_approved_geometry_revision=previous,
                approved_geometry_revision=board.geometry_revision,
                actor=actor,
                created_at=at,
            )
        )
        self.session.flush()
        recompute_source_image_geometry_completeness(
            self.session, game, member.source_id, actor=actor, materialize=False
        )
        SqlAlchemyBoardSearchProjectionRepository(self.session).sync_review_item(review)
        receipt = {
            "eventId": str(event_id),
            "reviewItemId": str(review),
            "boardId": str(board.id),
            "geometryRevision": board.geometry_revision,
            "geometryChecksumSha256": checksum,
            "kind": "approved_unchanged",
            "actor": actor,
            "at": at.isoformat(),
            "commandSha256": sha,
            "historicalReceipt": True,
        }
        self.session.add(
            Command(
                game_id=game,
                idempotency_key=UUID(command["idempotencyKey"]),
                review_item_id=review,
                import_job_id=job,
                command_sha256=sha,
                document={"command": command, "receipt": receipt},
            )
        )
        self.session.flush()
        return {"receipt": receipt}
