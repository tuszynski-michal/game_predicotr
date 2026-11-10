from unittest.mock import Mock
from uuid import uuid4

import pytest
from game_predictor_api.domain.jobs import JobStatus, JobType
from game_predictor_api.storage.image_review_repository import (
    SqlAlchemyOperationalImageReviewRepository,
)


@pytest.mark.parametrize("blocked", [True, False])
def test_training_lock_is_scoped_to_mutating_job_types_and_active_statuses(blocked) -> None:
    session = Mock()
    session.scalar.return_value = blocked
    repository = SqlAlchemyOperationalImageReviewRepository(session)

    game = uuid4()
    assert repository.has_active_heavy_job(game_id=game) is blocked

    statement = session.scalar.call_args.args[0]
    parameters = statement.compile().params
    assert parameters["game_id_1"] == game
    assert set(parameters["job_type_1"]) == {
        JobType.SYMBOL_TRAINING,
        JobType.IMAGE_SYMBOL_REVIEW_BULK,
        JobType.IMPORT,
        JobType.IMAGE_GRID_REINFERENCE,
    }
    assert set(parameters["status_1"]) == {JobStatus.CREATED, JobStatus.PROCESSING}
    assert not set(parameters["status_1"]) & {
        JobStatus.WAITING_FOR_REVIEW,
        JobStatus.COMPLETED,
        JobStatus.FAILED,
        JobStatus.CANCELLED,
    }
