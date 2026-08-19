"""SQLAlchemy persistence for append-only full-page geometry corrections."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from game_predictor_api.domain.page_geometry_overrides import (
    ImagePageGeometryOverride,
    PageGeometryQuads,
)
from game_predictor_api.storage.models import ImagePageGeometryOverrideModel


class SqlAlchemyPageGeometryOverrideRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_current(
        self,
        *,
        game_id: UUID,
        source_checksum_sha256: str,
    ) -> ImagePageGeometryOverride | None:
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
        row = ImagePageGeometryOverrideModel(
            id=value.id,
            game_id=value.game_id,
            source_checksum_sha256=value.source_checksum_sha256,
            image_width=value.image_width,
            image_height=value.image_height,
            final_quads=[list(quad) for quad in value.final_quads],
            revision=value.revision,
            actor=value.actor,
            decision_checksum_sha256=value.decision_checksum_sha256,
            created_at=value.created_at,
        )
        self._session.add(row)
        self._session.flush()
        return _to_domain(row)


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
    )


__all__ = ["SqlAlchemyPageGeometryOverrideRepository"]
