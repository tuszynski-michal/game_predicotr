"""SQL persistence for the canonical sequence projection."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from game_predictor_api.domain.image_sequence_canonical import (
    ImageSequenceCanonicalRepository,
)
from game_predictor_api.storage.models import ImageSequenceCanonicalModel


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


__all__ = ["SqlAlchemyImageSequenceCanonicalRepository"]
