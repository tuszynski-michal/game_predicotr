"""Game-scoped immutable comparisons, with job lease and source revision fencing."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from game_predictor_api.domain.catalog import GameShapeGeometryConfiguration
from game_predictor_api.domain.geometry_correction_reverts import (
    REVERTED_SOURCE_GEOMETRY_STATUS,
)
from game_predictor_api.domain.grid_shadow import (
    GRID_SHADOW_VALIDATION_KIND,
    GridShadowError,
    GridShadowResult,
    GridShadowStatus,
    shadow_digest,
    validate_shadow_output,
)
from game_predictor_api.domain.image_grid_reviews import (
    ImageGridReviewListFilter,
    ImageGridReviewListItem,
    ImageGridReviewView,
)
from game_predictor_api.domain.jobs import Job, JobStatus, JobType
from game_predictor_api.storage.image_grid_review_repository import (
    SqlAlchemyImageGridReviewRepository,
)
from game_predictor_api.storage.image_review_repository import acquire_image_sequence_locks
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository, job_from_record
from game_predictor_api.storage.models import (
    GameModel,
    ImageGeometryShadowResultModel,
    ImageSourceGeometryRevisionModel,
    JobModel,
    RulesVersionModel,
    SourceImageModel,
)


class SqlAlchemyGridShadowRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def require_game_for_update(self, game_id: UUID) -> GameShapeGeometryConfiguration | None:
        game = self._session.scalar(
            select(GameModel).where(GameModel.id == game_id).with_for_update()
        )
        if game is None:
            raise GridShadowError("GAME_NOT_FOUND", "Game does not exist.", status_code=404)
        try:
            return (
                None
                if game.shape_geometry_configuration is None
                else GameShapeGeometryConfiguration(game.shape_geometry_configuration)
            )
        except ValueError:
            return None

    def find_request(self, game_id: UUID, request_id: UUID) -> Job | None:
        row = self._session.scalar(
            select(JobModel).where(
                JobModel.game_id == game_id,
                JobModel.job_type == JobType.VALIDATE,
                JobModel.input_payload["validation_kind"].as_string()
                == GRID_SHADOW_VALIDATION_KIND,
                JobModel.input_payload["request_id"].as_string() == str(request_id),
            )
        )
        return None if row is None else job_from_record(row)

    def add_job(self, job: Job) -> Job:
        return SqlAlchemyJobRepository(self._session).add_job(job)

    def pin_source(self, game_id: UUID, source_image_id: UUID) -> dict[str, object]:
        row = self._session.execute(
            select(SourceImageModel, ImageSourceGeometryRevisionModel)
            .join(
                ImageSourceGeometryRevisionModel,
                ImageSourceGeometryRevisionModel.source_image_id == SourceImageModel.id,
            )
            .where(
                ImageSourceGeometryRevisionModel.game_id == game_id,
                SourceImageModel.id == source_image_id,
                # TASK-0966: a reverted revision is never the current one.
                ImageSourceGeometryRevisionModel.status != REVERTED_SOURCE_GEOMETRY_STATUS,
            )
            .order_by(ImageSourceGeometryRevisionModel.revision.desc())
            .limit(1)
            .execution_options(populate_existing=True)
        ).first()
        if row is None:
            raise GridShadowError(
                "GRID_SHADOW_SOURCE_NOT_MATERIALIZED",
                "Source image has no materialized geometry for this game.",
            )
        source, geometry = row
        game = self._session.get(GameModel, game_id)
        rules = self._session.get(RulesVersionModel, geometry.topology_rules_version_id)
        if game is None or rules is None or rules.game_id != game_id:
            raise GridShadowError(
                "GRID_SHADOW_SOURCE_BINDING_INVALID",
                "Source topology does not belong to the selected game.",
            )
        if (rules.rows, rules.columns) != (3, 5):
            raise GridShadowError(
                "GRID_SHADOW_TOPOLOGY_UNSUPPORTED", "Shadow supports only 5 × 3 boards."
            )
        if game.board_topology_rules_version_id is not None:
            game_rules = self._session.get(RulesVersionModel, game.board_topology_rules_version_id)
            if game_rules is None or (game_rules.rows, game_rules.columns) != (3, 5):
                raise GridShadowError(
                    "GRID_SHADOW_TOPOLOGY_UNSUPPORTED", "The current game topology must be 5 × 3."
                )
        count = geometry.sequence_range_end - geometry.sequence_range_start + 1
        if (
            not 1 <= count <= 9
            or geometry.sequence_range_start < 1
            or geometry.sequence_range_end > game.expected_layout_count
            or tuple(geometry.active_board_slots) != tuple(range(count))
        ):
            raise GridShadowError(
                "GRID_SHADOW_SEQUENCE_INVALID",
                "Source range does not match the attested active slots or game boundary.",
            )
        if source.checksum_sha256 != geometry.source_checksum_sha256:
            raise GridShadowError(
                "GRID_SHADOW_SOURCE_CHECKSUM_MISMATCH", "Source and geometry SHA differ."
            )
        if (source.oriented_width or source.width, source.oriented_height or source.height) != (
            geometry.oriented_width,
            geometry.oriented_height,
        ):
            raise GridShadowError(
                "GRID_SHADOW_SOURCE_DIMENSIONS_MISMATCH", "Source and geometry dimensions differ."
            )
        if source.normalized_pixel_checksum_sha256 != geometry.normalized_pixel_checksum_sha256:
            raise GridShadowError(
                "GRID_SHADOW_SOURCE_PIXELS_MISMATCH", "Normalized pixel identity differs."
            )
        items = self.review_items(game_id, source_image_id)
        if any(
            item.position_index not in geometry.active_board_slots
            or item.sequence_number != geometry.sequence_range_start + item.position_index
            for item in items
        ):
            raise GridShadowError(
                "GRID_SHADOW_SLOT_BINDING_INVALID",
                "Review targets do not match the attested source range.",
            )
        indexed = {item.position_index: item for item in items}
        if len(indexed) != len(items):
            raise GridShadowError(
                "GRID_SHADOW_SLOT_AMBIGUOUS", "Multiple current review targets occupy one slot."
            )
        baseline = []
        for position in geometry.active_board_slots:
            item = indexed.get(position)
            raw = (
                geometry.board_geometries[position]
                if position < len(geometry.board_geometries)
                else {}
            )
            baseline.append(
                {
                    "position_index": position,
                    "sequence_number": geometry.sequence_range_start + position,
                    "slot_id": None if item is None else str(item.slot_id),
                    "slot_kind": None if item is None else item.slot_kind.value,
                    "geometry_revision": None if item is None else item.geometry_revision,
                    "resolution_revision": None if item is None else item.resolution_revision,
                    "recognized_board_id": None
                    if item is None or item.recognized_board_id is None
                    else str(item.recognized_board_id),
                    "geometry": dict(raw) if item is None else dict(item.geometry),
                    "geometry_engine_name": geometry.engine_kind
                    if item is None
                    else item.geometry_engine_name,
                    "geometry_engine_version": geometry.engine_version
                    if item is None
                    else item.geometry_engine_version,
                    "grid_rows": 3,
                    "grid_columns": 5,
                }
            )
        binding: dict[str, object] = {
            "source_image_id": str(source.id),
            "import_job_id": str(source.import_job_id),
            "relative_path": source.relative_path,
            "checksum_sha256": source.checksum_sha256,
            "normalized_pixel_checksum_sha256": geometry.normalized_pixel_checksum_sha256,
            "width": geometry.oriented_width,
            "height": geometry.oriented_height,
            "source_geometry_revision_id": str(geometry.id),
            "source_geometry_revision": geometry.revision,
            "geometry_checksum_sha256": geometry.geometry_checksum_sha256,
            "rules_version_id": str(geometry.topology_rules_version_id),
            "baseline_engine_name": geometry.engine_kind,
            "baseline_engine_version": geometry.engine_version,
            "baseline_geometry_source": geometry.geometry_source,
            "sequence_range_start": geometry.sequence_range_start,
            "sequence_range_end": geometry.sequence_range_end,
            "active_board_slots": list(geometry.active_board_slots),
            "baseline_slots": baseline,
        }
        binding["bindings_sha256"] = shadow_digest(binding)
        return binding

    def review_items(
        self, game_id: UUID, source_image_id: UUID
    ) -> tuple[ImageGridReviewListItem, ...]:
        return (
            SqlAlchemyImageGridReviewRepository(self._session)
            .list_grid_reviews(
                review_filter=ImageGridReviewListFilter(
                    game_id, ImageGridReviewView.ALL, None, source_image_id
                ),
                after_key=None,
                before_key=None,
                limit=20,
            )
            .items
        )

    def get_result(self, game_id: UUID, result_id: UUID) -> GridShadowResult | None:
        row = self._session.scalar(
            select(ImageGeometryShadowResultModel).where(
                ImageGeometryShadowResultModel.game_id == game_id,
                ImageGeometryShadowResultModel.id == result_id,
            )
        )
        return None if row is None else _result(row)

    def get_result_for_source(
        self, game_id: UUID, job_id: UUID, source_image_id: UUID
    ) -> GridShadowResult | None:
        row = self._session.scalar(
            select(ImageGeometryShadowResultModel).where(
                ImageGeometryShadowResultModel.game_id == game_id,
                ImageGeometryShadowResultModel.job_id == job_id,
                ImageGeometryShadowResultModel.source_image_id == source_image_id,
            )
        )
        return None if row is None else _result(row)

    def list_results(
        self, game_id: UUID, *, source_image_id: UUID | None, after_id: UUID | None, limit: int
    ) -> tuple[GridShadowResult, ...]:
        table = ImageGeometryShadowResultModel
        statement = select(table).where(table.game_id == game_id)
        if source_image_id is not None:
            statement = statement.where(table.source_image_id == source_image_id)
        if after_id is not None:
            anchor = self.get_result(game_id, after_id)
            if anchor is None or (
                source_image_id is not None and anchor.source_image_id != source_image_id
            ):
                raise GridShadowError(
                    "GRID_SHADOW_CURSOR_INVALID", "Cursor result no longer exists.", status_code=422
                )
            statement = statement.where(
                tuple_(table.created_at, table.id) < (anchor.created_at, anchor.id)
            )
        return tuple(
            _result(row)
            for row in self._session.scalars(
                statement.order_by(table.created_at.desc(), table.id.desc()).limit(limit)
            )
        )

    def publish_result(
        self,
        *,
        game_id: UUID,
        job_id: UUID,
        lease_owner: str,
        lease_token: UUID,
        pinned_source: Mapping[str, object],
        model: Mapping[str, object],
        output: Mapping[str, object],
    ) -> GridShadowResult:
        source_id = UUID(str(pinned_source["source_image_id"]))
        start = int(str(pinned_source["sequence_range_start"]))
        end = int(str(pinned_source["sequence_range_end"]))
        if not 1 <= end - start + 1 <= 9:
            raise GridShadowError("GRID_SHADOW_JOB_BINDING_INVALID", "Invalid pinned range.")
        # Order the owner FK lock before source locks. Cleanup takes Game FOR UPDATE
        # before deleting artifacts; KEY SHARE also remains compatible with correction FKs.
        game = self._session.scalar(
            select(GameModel.id)
            .where(GameModel.id == game_id)
            .with_for_update(read=True, key_share=True)
        )
        if game is None:
            raise GridShadowError("GAME_NOT_FOUND", "Game does not exist.", status_code=404)
        acquire_image_sequence_locks(
            self._session, game_id=game_id, sequence_numbers=list(range(start, end + 1))
        )
        self._session.execute(
            select(SourceImageModel.id).where(SourceImageModel.id == source_id).with_for_update()
        )
        job = self._session.scalar(
            select(JobModel)
            .where(JobModel.id == job_id, JobModel.game_id == game_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        now = datetime.now(UTC)
        if (
            job is None
            or job.status != JobStatus.PROCESSING
            or job.lease_owner != lease_owner
            or job.lease_token != lease_token
            or job.lease_expires_at is None
            or job.lease_expires_at <= now
            or job.cancel_requested_at is not None
            or job.input_payload.get("validation_kind") != GRID_SHADOW_VALIDATION_KIND
        ):
            raise GridShadowError(
                "GRID_SHADOW_LEASE_LOST", "Shadow job lease is no longer current."
            )
        expected_sources = job.input_payload.get("sources")
        if (
            job.input_payload.get("model") != dict(model)
            or not isinstance(expected_sources, list)
            or dict(pinned_source) not in expected_sources
        ):
            raise GridShadowError(
                "GRID_SHADOW_JOB_BINDING_INVALID", "Published inputs do not match the pinned job."
            )
        validate_shadow_output(output, pinned_source)
        current = self.pin_source(game_id, source_id)
        if current.get("bindings_sha256") != pinned_source.get("bindings_sha256"):
            raise GridShadowError(
                "GRID_SHADOW_SOURCE_STALE", "Source geometry changed during the comparison."
            )
        existing = self.get_result_for_source(game_id, job_id, source_id)
        checksum = shadow_digest(dict(output))
        if existing is not None:
            if existing.output_checksum_sha256 != checksum:
                raise GridShadowError(
                    "GRID_SHADOW_RESULT_CONFLICT", "A different immutable result already exists."
                )
            return existing
        raw_reasons = output.get("reasons", [])
        reasons = cast(list[str], raw_reasons) if isinstance(raw_reasons, list) else []
        row = ImageGeometryShadowResultModel(
            game_id=game_id,
            id=uuid4(),
            job_id=job_id,
            source_image_id=source_id,
            source_checksum_sha256=str(pinned_source["checksum_sha256"]),
            source_geometry_revision_id=UUID(str(pinned_source["source_geometry_revision_id"])),
            source_geometry_revision=int(str(pinned_source["source_geometry_revision"])),
            source_geometry_checksum_sha256=str(pinned_source["geometry_checksum_sha256"]),
            source_width=int(str(pinned_source["width"])),
            source_height=int(str(pinned_source["height"])),
            model_profile=str(model["profile"]),
            model_version=str(model["version"]),
            model_manifest_checksum_sha256=str(model["manifest_checksum_sha256"]),
            source_binding=dict(pinned_source),
            model_binding=dict(model),
            binding_checksum_sha256=shadow_digest(
                {"source": dict(pinned_source), "model": dict(model)}
            ),
            status=str(output.get("status", "needs_review")),
            reasons=reasons,
            output=dict(output),
            output_checksum_sha256=checksum,
            created_at=now,
        )
        self._session.add(row)
        self._session.flush()
        return _result(row)


def _result(row: ImageGeometryShadowResultModel) -> GridShadowResult:
    if (
        shadow_digest({"source": row.source_binding, "model": row.model_binding})
        != row.binding_checksum_sha256
    ):
        raise GridShadowError(
            "GRID_SHADOW_RESULT_BINDING_MISMATCH", "Stored input binding checksum differs."
        )
    if shadow_digest(row.output) != row.output_checksum_sha256:
        raise GridShadowError(
            "GRID_SHADOW_RESULT_CHECKSUM_MISMATCH", "Stored comparison checksum differs."
        )
    if row.output.get("status") != row.status:
        raise GridShadowError(
            "GRID_SHADOW_RESULT_BINDING_MISMATCH", "Stored status differs from output."
        )
    bound = dict(row.source_binding)
    digest = bound.pop("bindings_sha256", None)
    if digest != shadow_digest(bound):
        raise GridShadowError(
            "GRID_SHADOW_RESULT_BINDING_MISMATCH", "Stored source binding checksum differs."
        )
    if (
        row.model_binding.get("profile") != row.model_profile
        or row.model_binding.get("version") != row.model_version
        or row.model_binding.get("manifest_checksum_sha256") != row.model_manifest_checksum_sha256
        or row.source_binding.get("source_image_id") != str(row.source_image_id)
        or row.source_binding.get("checksum_sha256") != row.source_checksum_sha256
        or row.source_binding.get("source_geometry_revision_id")
        != str(row.source_geometry_revision_id)
        or row.source_binding.get("source_geometry_revision") != row.source_geometry_revision
        or row.source_binding.get("geometry_checksum_sha256") != row.source_geometry_checksum_sha256
        or row.source_binding.get("width") != row.source_width
        or row.source_binding.get("height") != row.source_height
        or row.output.get("reasons", []) != row.reasons
    ):
        raise GridShadowError(
            "GRID_SHADOW_RESULT_BINDING_MISMATCH", "Stored identities differ from the binding."
        )
    validate_shadow_output(row.output, row.source_binding)
    return GridShadowResult(
        row.id,
        row.game_id,
        row.job_id,
        row.source_image_id,
        row.source_checksum_sha256,
        row.source_geometry_revision_id,
        row.source_geometry_revision,
        row.source_geometry_checksum_sha256,
        row.source_width,
        row.source_height,
        row.model_profile,
        row.model_version,
        row.model_manifest_checksum_sha256,
        row.source_binding,
        row.model_binding,
        cast(GridShadowStatus, row.status),
        tuple(row.reasons),
        row.output,
        row.output_checksum_sha256,
        row.created_at,
    )
