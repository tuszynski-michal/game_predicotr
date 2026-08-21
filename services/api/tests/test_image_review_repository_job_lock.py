from unittest.mock import Mock
from uuid import uuid4

from game_predictor_api.domain.jobs import JobType
from game_predictor_api.storage.image_review_repository import (
    SqlAlchemyOperationalImageReviewRepository,
)


def test_training_lock_ignores_unrelated_active_jobs() -> None:
    session = Mock()
    session.scalar.return_value = False
    repository = SqlAlchemyOperationalImageReviewRepository(session)

    assert repository.has_active_heavy_job(game_id=uuid4()) is False

    statement = session.scalar.call_args.args[0]
    assert JobType.SYMBOL_TRAINING in statement.compile().params.values()
