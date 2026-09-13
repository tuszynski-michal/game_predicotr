"""SQLAlchemy persistence for append-only full-page geometry corrections."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from game_predictor_api.domain.geometry_qualification import parse_slot_qualifications
from game_predictor_api.domain.jobs import JobConflictError
from game_predictor_api.domain.page_geometry_overrides import (
    ImagePageGeometryOverride,
    ImagePageSourceExclusion,
    PageGeometryQuads,
)
from game_predictor_api.storage.game_storage_routing import (
    GameStorageIntent,
    GameStorageRouter,
)
from game_predictor_api.storage.models import (
    ImagePageGeometryOverrideModel,
    ImagePageSourceExclusionModel,
)


class SqlAlchemyPageGeometryOverrideRepository:
    def __init__(
        self,
        session: Session,
        storage_router: GameStorageRouter | None = None,
    ) -> None:
        self._session = session
        self._storage_router = storage_router or GameStorageRouter()

    def _bind(self, game_id: UUID, *, intent: GameStorageIntent) -> None:
        """Route every correction read to the same store as its writes."""

        self._storage_router.bind(self._session, game_id, intent=intent)

    def get_current(
        self,
        *,
        game_id: UUID,
        source_checksum_sha256: str,
    ) -> ImagePageGeometryOverride | None:
        self._bind(game_id, intent=GameStorageIntent.READ)
        row = self._session.scalar(
            select(ImagePageGeometryOverrideModel)
            .where(
                ImagePageGeometryOverrideModel.game_id == game_id,
                ImagePageGeometryOverrideModel.source_checksum_sha256 == source_checksum_sha256,
            )
            .order_by(ImagePageGeometryOverrideModel.revision.desc())
            .limit(1)
        )
        return None if row is None else _to_domain(row)

    def list_current(self, *, game_id: UUID) -> tuple[ImagePageGeometryOverride, ...]:
        self._bind(game_id, intent=GameStorageIntent.READ)
        rows = self._session.scalars(
            select(ImagePageGeometryOverrideModel)
            .where(ImagePageGeometryOverrideModel.game_id == game_id)
            .order_by(
                ImagePageGeometryOverrideModel.source_checksum_sha256.asc(),
                ImagePageGeometryOverrideModel.revision.desc(),
            )
        )
        current: dict[str, ImagePageGeometryOverride] = {}
        for row in rows:
            current.setdefault(row.source_checksum_sha256, _to_domain(row))
        return tuple(current[key] for key in sorted(current))

    def append(self, value: ImagePageGeometryOverride) -> ImagePageGeometryOverride:
        self._bind(value.game_id, intent=GameStorageIntent.WRITE)
        row = ImagePageGeometryOverrideModel(
            id=value.id,
            game_id=value.game_id,
            source_checksum_sha256=value.source_checksum_sha256,
            image_width=value.image_width,
            image_height=value.image_height,
            final_quads=[list(quad) for quad in value.final_quads],
            slot_qualifications=(
                None
                if value.slot_qualifications is None
                else [item.to_dict() for item in value.slot_qualifications]
            ),
            revision=value.revision,
            actor=value.actor,
            decision_checksum_sha256=value.decision_checksum_sha256,
            created_at=value.created_at,
        )
        try:
            with self._session.begin_nested():
                self._session.add(row)
                self._session.flush()
        except IntegrityError as error:
            if getattr(getattr(error.orig, "diag", None), "constraint_name", None) != (
                "uq_image_page_geometry_overrides_revision"
            ):
                raise
            raise JobConflictError(
                "IMAGE_PAGE_GEOMETRY_REVISION_CONFLICT",
                "A concurrent editor saved this source revision. Reload before changing it.",
            ) from error
        return _to_domain(row)

    def get_exclusion(
        self,
        *,
        game_id: UUID,
        browser_selection_id: UUID,
        source_checksum_sha256: str,
    ) -> ImagePageSourceExclusion | None:
        self._bind(game_id, intent=GameStorageIntent.READ)
        row = self._session.scalar(
            select(ImagePageSourceExclusionModel).where(
                ImagePageSourceExclusionModel.browser_selection_id == browser_selection_id,
                ImagePageSourceExclusionModel.source_checksum_sha256 == source_checksum_sha256,
            )
        )
        return None if row is None else _exclusion_to_domain(row)

    def list_exclusions(
        self,
        *,
        game_id: UUID,
        browser_selection_id: UUID,
    ) -> tuple[ImagePageSourceExclusion, ...]:
        self._bind(game_id, intent=GameStorageIntent.READ)
        rows = self._session.scalars(
            select(ImagePageSourceExclusionModel)
            .where(ImagePageSourceExclusionModel.browser_selection_id == browser_selection_id)
            .order_by(ImagePageSourceExclusionModel.source_relative_path.asc())
        )
        return tuple(_exclusion_to_domain(row) for row in rows)

    def append_exclusion(self, value: ImagePageSourceExclusion) -> ImagePageSourceExclusion:
        self._bind(value.game_id, intent=GameStorageIntent.WRITE)
        row = ImagePageSourceExclusionModel(
            id=value.id,
            game_id=value.game_id,
            browser_selection_id=value.browser_selection_id,
            geometry_preflight_job_id=value.geometry_preflight_job_id,
            source_manifest_checksum_sha256=value.source_manifest_checksum_sha256,
            geometry_manifest_checksum_sha256=value.geometry_manifest_checksum_sha256,
            source_checksum_sha256=value.source_checksum_sha256,
            source_relative_path=value.source_relative_path,
            actor=value.actor,
            decision_checksum_sha256=value.decision_checksum_sha256,
            created_at=value.created_at,
        )
        self._session.add(row)
        self._session.flush()
        return _exclusion_to_domain(row)


def _to_domain(row: ImagePageGeometryOverrideModel) -> ImagePageGeometryOverride:
    return ImagePageGeometryOverride(
        id=row.id,
        game_id=row.game_id,
        source_checksum_sha256=row.source_checksum_sha256,
        image_width=row.image_width,
        image_height=row.image_height,
        final_quads=cast(PageGeometryQuads, tuple(tuple(quad) for quad in row.final_quads)),
        revision=row.revision,
        actor=row.actor,
        decision_checksum_sha256=row.decision_checksum_sha256,
        created_at=row.created_at,
        slot_qualifications=parse_slot_qualifications(
            row.slot_qualifications, expected_board_count=len(row.final_quads)
        ),
    )


def _exclusion_to_domain(
    row: ImagePageSourceExclusionModel,
) -> ImagePageSourceExclusion:
    return ImagePageSourceExclusion(
        id=row.id,
        game_id=row.game_id,
        browser_selection_id=row.browser_selection_id,
        geometry_preflight_job_id=row.geometry_preflight_job_id,
        source_manifest_checksum_sha256=row.source_manifest_checksum_sha256,
        geometry_manifest_checksum_sha256=row.geometry_manifest_checksum_sha256,
        source_checksum_sha256=row.source_checksum_sha256,
        source_relative_path=row.source_relative_path,
        actor=row.actor,
        decision_checksum_sha256=row.decision_checksum_sha256,
        created_at=row.created_at,
    )


__all__ = ["SqlAlchemyPageGeometryOverrideRepository"]
