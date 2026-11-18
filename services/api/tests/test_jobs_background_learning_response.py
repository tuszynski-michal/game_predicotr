"""A queued preparation must not make the whole generic job monitor return 500."""

from uuid import uuid4

import pytest
from game_predictor_api.domain.jobs import JobType, create_job
from game_predictor_api.schemas.jobs import GridCorrectionLearningJobPayload
from pydantic import ValidationError
from test_jobs_api import _client


def test_background_preparation_is_visible_in_job_listing_and_detail(tmp_path):
    client, game, _, repository = _client(tmp_path)
    job = repository.add_job(
        create_job(
            JobType.GRID_CORRECTION_LEARNING,
            game_id=game,
            input_payload={
                "schema_version": 1,
                "learning_kind": "grid-correction-learning-v1",
                "idempotency_key": str(uuid4()),
                "actor": "local-owner",
                "backgroundPreparation": True,
                "command": {"trainingMode": "screen+grid", "prepareInBackground": True},
                "preview": {"baseVersionId": str(uuid4()), "defaultRevision": 5},
            },
        )
    )
    with client:
        listing = client.get("/api/v1/admin/jobs")
        detail = client.get(f"/api/v1/admin/jobs/{job.id}")
    assert listing.status_code == detail.status_code == 200
    assert next(item for item in listing.json() if item["id"] == str(job.id)) == detail.json()
    assert detail.json()["inputPayload"]["backgroundPreparation"] is True
    assert "pins" not in detail.json()["inputPayload"]


def test_unprepared_legacy_payload_is_still_rejected():
    payload = {
        "schema_version": 1,
        "learning_kind": "grid-correction-learning-v1",
        "idempotency_key": str(uuid4()),
        "actor": "local-owner",
        "command": {},
        "preview": {},
    }
    with pytest.raises(ValidationError, match="requires prepared pins"):
        GridCorrectionLearningJobPayload.model_validate(payload)
    assert GridCorrectionLearningJobPayload.model_validate({**payload, "pins": {}}).pins == {}
