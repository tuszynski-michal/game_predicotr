"""Persistence boundary for v0.10 source geometry and per-game rollout state.

Nothing in this module activates the v0.10 image pipeline.  New games are
backfilled into explicit legacy modes, while source geometry is append-only
and can only be stored after the source coordinate metadata is complete.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.orm import Session

from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.image_geometry_v2 import (
    SEQUENCE_ATTESTATION_SCHEMA_VERSION,
    SOURCE_COORDINATE_SPACE,
    board_topology_fingerprint_sha256,
    sequence_attestation_checksum_sha256,
)
from game_predictor_api.storage.models import (
    GameModel,
    ImageGeometryRolloutStateModel,
    ImageSourceGeometryRevisionModel,
    JobModel,
    RulesVersionModel,
    SourceImageModel,
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_BACKFILL_ACTOR = "system:virtual-geometry-foundation"
_DEFAULT_BACKFILL_LIMIT = 200
_MAX_BACKFILL_LIMIT = 500


class ImageGeometryPersistenceError(RuntimeError):
    """Fail-closed persistence error with a stable operator-facing code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class SourceGeometryRevisionInput:
    game_id: UUID
    source_image_id: UUID
    topology_rules_version_id: UUID
    sequence_range_start: int
    sequence_range_end: int
    active_board_slots: tuple[int, ...]
    source_checksum_sha256: str
    normalized_pixel_checksum_sha256: str
    oriented_width: int
    oriented_height: int
    normalization_adapter_version: str
    global_initialization: dict[str, object] | None
    board_geometries: tuple[dict[str, object], ...]
    engine_kind: str
    engine_version: str
    geometry_source: str
    status: str
    geometry_checksum_sha256: str
    processing_time_ms: int | None
    warnings: tuple[dict[str, object], ...]
    created_by: str


@dataclass(frozen=True, slots=True)
class StoredSourceGeometryRevision:
    id: UUID
    revision: int
    geometry_checksum_sha256: str
    created: bool


@dataclass(frozen=True, slots=True)
class GeometryRolloutState:
    game_id: UUID
    geometry_mode: str
    cell_asset_mode: str
    revision: int
    backfill_status: str


@dataclass(frozen=True, slots=True)
class GeometryRolloutBackfillStep:
    processed_game_count: int
    inserted_state_count: int
    last_game_id: UUID | None
    has_more: bool


class SqlAlchemyImageSourceGeometryRepository:
    """Append and read immutable, source-coordinate geometry revisions."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def append(self, value: SourceGeometryRevisionInput) -> StoredSourceGeometryRevision:
        self._validate_input(value)
        source = self._session.execute(
            select(SourceImageModel)
            .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
            .where(
                SourceImageModel.id == value.source_image_id,
                JobModel.game_id == value.game_id,
            )
            .with_for_update(of=SourceImageModel)
        ).scalar_one_or_none()
        if source is None:
            raise ImageGeometryPersistenceError(
                "IMAGE_GEOMETRY_SOURCE_NOT_FOUND",
                "The source image does not belong to the requested game.",
            )
        self._validate_source_metadata(source=source, value=value)
        topology_rules = self._session.scalar(
            select(RulesVersionModel).where(
                RulesVersionModel.id == value.topology_rules_version_id,
                RulesVersionModel.game_id == value.game_id,
            )
        )
        if topology_rules is None:
            raise ImageGeometryPersistenceError(
                "IMAGE_GEOMETRY_TOPOLOGY_INVALID",
                "The pinned topology rules version does not belong to the requested game.",
            )
        topology_fingerprint = board_topology_fingerprint_sha256(
            topology_rules_version_id=topology_rules.id,
            topology=BoardTopology(rows=topology_rules.rows, columns=topology_rules.columns),
        )
        attestation_checksum = sequence_attestation_checksum_sha256(
            sequence_range_start=value.sequence_range_start,
            sequence_range_end=value.sequence_range_end,
            active_board_slots=value.active_board_slots,
        )

        existing = self._session.execute(
            select(ImageSourceGeometryRevisionModel).where(
                ImageSourceGeometryRevisionModel.source_image_id == value.source_image_id,
                ImageSourceGeometryRevisionModel.geometry_checksum_sha256
                == value.geometry_checksum_sha256,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return StoredSourceGeometryRevision(
                id=existing.id,
                revision=existing.revision,
                geometry_checksum_sha256=existing.geometry_checksum_sha256,
                created=False,
            )

        latest_revision = self._session.execute(
            select(ImageSourceGeometryRevisionModel.revision)
            .where(ImageSourceGeometryRevisionModel.source_image_id == value.source_image_id)
            .order_by(ImageSourceGeometryRevisionModel.revision.desc())
            .limit(1)
        ).scalar_one_or_none()
        revision = 0 if latest_revision is None else latest_revision + 1
        model = ImageSourceGeometryRevisionModel(
            id=uuid4(),
            game_id=value.game_id,
            source_image_id=value.source_image_id,
            topology_rules_version_id=value.topology_rules_version_id,
            revision=revision,
            sequence_range_start=value.sequence_range_start,
            sequence_range_end=value.sequence_range_end,
            active_board_slots=list(value.active_board_slots),
            coordinate_space=SOURCE_COORDINATE_SPACE,
            source_checksum_sha256=value.source_checksum_sha256,
            normalized_pixel_checksum_sha256=value.normalized_pixel_checksum_sha256,
            oriented_width=value.oriented_width,
            oriented_height=value.oriented_height,
            normalization_adapter_version=value.normalization_adapter_version,
            global_initialization=value.global_initialization,
            board_geometries=list(value.board_geometries),
            engine_kind=value.engine_kind,
            engine_version=value.engine_version,
            geometry_source=value.geometry_source,
            status=value.status,
            geometry_checksum_sha256=value.geometry_checksum_sha256,
            topology_fingerprint_sha256=topology_fingerprint,
            sequence_attestation_schema_version=SEQUENCE_ATTESTATION_SCHEMA_VERSION,
            sequence_attestation_checksum_sha256=attestation_checksum,
            processing_time_ms=value.processing_time_ms,
            warnings=list(value.warnings),
            created_by=value.created_by,
        )
        self._session.add(model)
        self._session.flush()
        return StoredSourceGeometryRevision(
            id=model.id,
            revision=model.revision,
            geometry_checksum_sha256=model.geometry_checksum_sha256,
            created=True,
        )

    def get(self, revision_id: UUID) -> ImageSourceGeometryRevisionModel | None:
        model: ImageSourceGeometryRevisionModel | None = self._session.get(
            ImageSourceGeometryRevisionModel, revision_id
        )
        return model

    @staticmethod
    def _validate_input(value: SourceGeometryRevisionInput) -> None:
        board_count = value.sequence_range_end - value.sequence_range_start + 1
        if (
            value.sequence_range_start < 1
            or board_count not in range(1, 10)
            or value.active_board_slots != tuple(range(board_count))
            or len(value.board_geometries) != board_count
        ):
            raise ImageGeometryPersistenceError(
                "IMAGE_GEOMETRY_SEQUENCE_ATTESTATION_INVALID",
                "Source geometry must cover the contiguous attested row-major slots.",
            )
        if not all(
            _SHA256.fullmatch(checksum)
            for checksum in (
                value.source_checksum_sha256,
                value.normalized_pixel_checksum_sha256,
                value.geometry_checksum_sha256,
            )
        ):
            raise ImageGeometryPersistenceError(
                "IMAGE_GEOMETRY_CHECKSUM_INVALID",
                "Source geometry requires lowercase SHA-256 provenance.",
            )
        if not value.created_by.strip() or not value.engine_version.strip():
            raise ImageGeometryPersistenceError(
                "IMAGE_GEOMETRY_PROVENANCE_INVALID",
                "Source geometry requires a versioned engine and actor.",
            )

    @staticmethod
    def _validate_source_metadata(
        *,
        source: SourceImageModel,
        value: SourceGeometryRevisionInput,
    ) -> None:
        if (
            source.checksum_sha256 != value.source_checksum_sha256
            or source.coordinate_space != SOURCE_COORDINATE_SPACE
            or source.normalized_pixel_checksum_sha256 != value.normalized_pixel_checksum_sha256
            or source.oriented_width != value.oriented_width
            or source.oriented_height != value.oriented_height
            or source.normalization_adapter_version != value.normalization_adapter_version
        ):
            raise ImageGeometryPersistenceError(
                "IMAGE_GEOMETRY_SOURCE_PROVENANCE_MISMATCH",
                "The source coordinate metadata changed or is incomplete.",
            )


class SqlAlchemyImageGeometryRolloutRepository:
    """Read rollout state and fill missing games in bounded legacy batches."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, game_id: UUID) -> GeometryRolloutState | None:
        model = self._session.get(ImageGeometryRolloutStateModel, game_id)
        if model is None:
            return None
        return GeometryRolloutState(
            game_id=model.game_id,
            geometry_mode=model.geometry_mode,
            cell_asset_mode=model.cell_asset_mode,
            revision=model.revision,
            backfill_status=model.backfill_status,
        )

    def backfill_legacy_states(
        self,
        *,
        after_game_id: UUID | None = None,
        limit: int = _DEFAULT_BACKFILL_LIMIT,
    ) -> GeometryRolloutBackfillStep:
        if limit < 1 or limit > _MAX_BACKFILL_LIMIT:
            raise ValueError(f"limit must be between 1 and {_MAX_BACKFILL_LIMIT}")
        query = select(GameModel.id).order_by(GameModel.id).limit(limit + 1)
        if after_game_id is not None:
            query = query.where(GameModel.id > after_game_id)
        game_ids = list(self._session.execute(query).scalars())
        batch = game_ids[:limit]
        if not batch:
            return GeometryRolloutBackfillStep(0, 0, after_game_id, False)

        inserted_game_ids = tuple(
            self._session.execute(
                postgresql_insert(ImageGeometryRolloutStateModel)
                .values(
                    [
                        {
                            "game_id": game_id,
                            "geometry_mode": "legacy",
                            "cell_asset_mode": "legacy_files",
                            "revision": 0,
                            "backfill_status": "not_started",
                            "updated_by": _BACKFILL_ACTOR,
                        }
                        for game_id in batch
                    ]
                )
                .on_conflict_do_nothing(index_elements=["game_id"])
                .returning(ImageGeometryRolloutStateModel.game_id)
            ).scalars()
        )
        return GeometryRolloutBackfillStep(
            processed_game_count=len(batch),
            inserted_state_count=len(inserted_game_ids),
            last_game_id=batch[-1],
            has_more=len(game_ids) > limit,
        )


__all__ = [
    "GeometryRolloutBackfillStep",
    "GeometryRolloutState",
    "ImageGeometryPersistenceError",
    "SourceGeometryRevisionInput",
    "SqlAlchemyImageGeometryRolloutRepository",
    "SqlAlchemyImageSourceGeometryRepository",
    "StoredSourceGeometryRevision",
]
