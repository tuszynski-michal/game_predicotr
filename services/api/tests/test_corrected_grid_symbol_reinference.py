from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.application.image_reviews import OperationalImageReviewService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.jobs import JobError
from game_predictor_api.main import create_app
from game_predictor_api.schemas.jobs import JobResponse
from game_predictor_api.storage.corrected_grid_symbol_targets import (
    corrected_grid_symbol_targets_query,
)
from sqlalchemy.dialects import postgresql
from test_jobs_api import _client


def test_corrected_target_query_binds_current_revision_and_import():
    game, import_id = uuid4(), uuid4()
    query = str(
        corrected_grid_symbol_targets_query(game, import_job_id=import_id).compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    for expected in (
        str(game),
        str(import_id),
        "manual_override",
        "image_board_geometry_revisions.revision",
        "recognized_boards.geometry_revision",
        "source_available IS true",
        "review_state = 'pending'",
        "image_board_geometry_revisions.corrected_by NOT LIKE",
        "waiting_for_review",
        "completed",
    ):
        assert expected in query
    # Historical corrections cannot admit a current geometry without its exact revision.
    assert "image_board_geometry_revisions.revision = recognized_boards.geometry_revision" in query
    assert "EXISTS" in query


def test_corrected_targets_are_persisted_and_serialized(tmp_path: Path):
    _, game, jobs, _ = _client(tmp_path)
    item = uuid4()
    job = jobs.create_pending_symbol_reinference_job(
        game_id=game, corrected_grid_targets=((item, 3),)
    )
    assert job.input_payload["corrected_grid_targets"] == [
        {"review_item_id": str(item), "geometry_revision": 3}
    ]
    response = JobResponse.from_domain(job).model_dump(mode="json", by_alias=True)
    assert response["inputPayload"]["correctedGridTargets"] == [
        {"reviewItemId": str(item), "geometryRevision": 3}
    ]
    assert job.input_payload["symbol_model"]


def _http_context(tmp_path):
    _, game, jobs, _ = _client(tmp_path)
    repo = MagicMock()
    repo.game_counts.return_value = MagicMock(accepted=0, corrected=0, rejected=0)
    repo.pending_symbol_reinference_count.return_value = 99
    repo.corrected_grid_symbol_targets.return_value = ((uuid4(), 2),)
    app = create_app(
        ApiSettings.from_environment({}),
        image_review_service_dependency=lambda: OperationalImageReviewService(repo),
        job_service_dependency=lambda: jobs,
    )
    return TestClient(app), repo, game


def test_preview_and_start_share_the_frozen_corrected_scope(tmp_path):
    client, repo, game = _http_context(tmp_path)
    import_id = uuid4()
    root = "/api/v1/admin/image-review-items/pending-symbol-reinference"
    params = {"corrected_geometry": "true", "import_job_id": str(import_id)}
    preview = client.get(f"{root}/preview/{game}", params=params)
    assert preview.status_code == 200, preview.text
    assert preview.json()["pendingCount"] == 1
    response = client.post(f"{root}/{game}", params=params)
    assert response.status_code == 200, response.text
    targets = response.json()["inputPayload"]["correctedGridTargets"]
    assert targets == [
        {
            "reviewItemId": str(repo.corrected_grid_symbol_targets.return_value[0][0]),
            "geometryRevision": 2,
        }
    ]
    repo.corrected_grid_symbol_targets.assert_called_with(game, import_job_id=import_id)
    repo.pending_symbol_reinference_count.assert_not_called()


def test_empty_scope_does_not_fall_back_to_global_pending(tmp_path):
    client, repo, game = _http_context(tmp_path)
    repo.corrected_grid_symbol_targets.return_value = ()
    response = client.post(
        f"/api/v1/admin/image-review-items/pending-symbol-reinference/{game}",
        params={"corrected_geometry": "true"},
    )
    assert response.status_code in {409, 422}
    assert response.json()["code"] == "IMAGE_SYMBOL_REINFERENCE_EMPTY"
    repo.pending_symbol_reinference_count.assert_not_called()


def test_existing_global_scope_remains_unchanged(tmp_path):
    client, repo, game = _http_context(tmp_path)
    root = "/api/v1/admin/image-review-items/pending-symbol-reinference"
    assert client.get(f"{root}/preview/{game}").json()["pendingCount"] == 99
    started = client.post(f"{root}/{game}")
    assert started.status_code == 200
    assert started.json()["inputPayload"]["correctedGridTargets"] is None
    repo.corrected_grid_symbol_targets.assert_not_called()


def test_oversized_scope_is_rejected_without_truncation():
    repo = MagicMock()
    repo.corrected_grid_symbol_targets.return_value = ((uuid4(), 1),) * 20_001
    with pytest.raises(JobError) as error:
        OperationalImageReviewService(repo).corrected_grid_symbol_targets(uuid4())
    assert error.value.code == "IMAGE_SYMBOL_REINFERENCE_SCOPE_TOO_LARGE"


def test_endpoint_scope_and_response_without_network(tmp_path):
    from game_predictor_api.api.image_reviews import create_image_reviews_router

    _, game, jobs, _ = _client(tmp_path)
    repo = MagicMock()
    repo.corrected_grid_symbol_targets.return_value = ((uuid4(), 3),)
    repo.game_counts.return_value = MagicMock(accepted=0, corrected=0, rejected=0)
    service = OperationalImageReviewService(repo)
    router = create_image_reviews_router(lambda: service, tmp_path, lambda: None, lambda: jobs)
    endpoints = {route.operation_id: route.endpoint for route in router.routes}
    import_id = uuid4()
    preview = endpoints["previewPendingSymbolReinference"](
        game, service, corrected_geometry=True, import_job_id=import_id
    )
    assert preview.pending_count == 1
    result = endpoints["startPendingSymbolReinference"](
        game, service, jobs, corrected_geometry=True, import_job_id=import_id
    )
    payload = result.model_dump(mode="json", by_alias=True)["inputPayload"]
    assert payload["correctedGridTargets"] == [
        {
            "reviewItemId": str(repo.corrected_grid_symbol_targets.return_value[0][0]),
            "geometryRevision": 3,
        }
    ]
    repo.corrected_grid_symbol_targets.assert_called_with(game, import_job_id=import_id)
    repo.pending_symbol_reinference_count.assert_not_called()

    # Repeating a start for the same frozen input cannot create a duplicate job.
    with pytest.raises(JobError) as duplicate:
        endpoints["startPendingSymbolReinference"](
            game, service, jobs, corrected_geometry=True, import_job_id=import_id
        )
    assert duplicate.value.code == "JOB_INPUT_ALREADY_EXISTS"
    assert duplicate.value.details["existingJobId"] == str(result.id)

    repo.corrected_grid_symbol_targets.return_value = ()
    with pytest.raises(JobError) as empty:
        endpoints["startPendingSymbolReinference"](
            game, service, jobs, corrected_geometry=True, import_job_id=import_id
        )
    assert empty.value.code == "IMAGE_SYMBOL_REINFERENCE_EMPTY"


def test_import_scope_never_silently_expands_to_entire_game(tmp_path):
    from game_predictor_api.api.image_reviews import create_image_reviews_router

    service, jobs = MagicMock(), MagicMock()
    router = create_image_reviews_router(lambda: service, tmp_path, lambda: None, lambda: jobs)
    endpoints = {route.operation_id: route.endpoint for route in router.routes}
    for operation in ("previewPendingSymbolReinference", "startPendingSymbolReinference"):
        kwargs = {"job_service": jobs} if operation.startswith("start") else {}
        with pytest.raises(JobError) as error:
            endpoints[operation](uuid4(), service, import_job_id=uuid4(), **kwargs)
        assert error.value.code == "IMAGE_SYMBOL_REINFERENCE_SCOPE_INVALID"
    service.pending_symbol_reinference_count.assert_not_called()


def test_global_endpoint_keeps_existing_job_contract_without_network(tmp_path):
    from game_predictor_api.api.image_reviews import create_image_reviews_router

    _, game, jobs, _ = _client(tmp_path)
    service = MagicMock()
    service.pending_symbol_reinference_count.return_value = 99
    router = create_image_reviews_router(lambda: service, tmp_path, lambda: None, lambda: jobs)
    start = next(
        route.endpoint
        for route in router.routes
        if route.operation_id == "startPendingSymbolReinference"
    )
    result = start(game, service, jobs)
    assert result.input_payload.corrected_grid_targets is None
    service.corrected_grid_symbol_targets.assert_not_called()
