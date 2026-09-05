"""SQL persistence for the canonical sequence projection."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from game_predictor_api.domain.image_sequence_canonical import (
    ImageSequenceCanonicalRepository,
)
from game_predictor_api.storage.models import GameModel, ImageSequenceCanonicalModel


class SqlAlchemyImageSequenceCanonicalRepository(ImageSequenceCanonicalRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def canonical_numbers(self, game_id: UUID) -> set[int]:
        try:
            values = self._session.scalars(
                select(ImageSequenceCanonicalModel.sequence_number).where(
                    ImageSequenceCanonicalModel.game_id == game_id
                )
            ).all()
        except ProgrammingError as error:
            # Keep older local databases usable until the migration is applied;
            # a missing projection means that no sequence can be safely reused.
            if "image_sequence_canonical" not in str(error).lower():
                raise
            self._session.rollback()
            return set()
        return {int(value) for value in values}

    def canonical_source_checksums(self, game_id: UUID) -> Mapping[int, str]:
        try:
            rows = self._session.execute(
                select(
                    ImageSequenceCanonicalModel.sequence_number,
                    ImageSequenceCanonicalModel.source_checksum_sha256,
                ).where(ImageSequenceCanonicalModel.game_id == game_id)
            ).all()
        except ProgrammingError as error:
            if "image_sequence_canonical" not in str(error).lower():
                raise
            self._session.rollback()
            return {}
        return {int(number): str(checksum) for number, checksum in rows}

    def expected_layout_count(self, game_id: UUID) -> int | None:
        value = self._session.scalar(
            select(GameModel.expected_layout_count).where(GameModel.id == game_id)
        )
        return int(value) if value is not None else None


__all__ = ["SqlAlchemyImageSequenceCanonicalRepository"]
