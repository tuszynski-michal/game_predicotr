"""Retired source detail and checksum-bound preview remain available for audit."""

import hashlib
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.application.image_reviews import OperationalImageReviewService
from game_predictor_api.config import ApiSettings
from game_predictor_api.main import create_app
from test_operational_image_reviews import MemoryOperationalImageReviewRepository, _item


@pytest.mark.parametrize("state", ["retired", "replaced"])
def test_historical_source_metadata_and_checksum_bound_preview(tmp_path: Path, state: str) -> None:
    game, job = uuid4(), uuid4()
    content = b"retained-source-preview"
    source = tmp_path / "data" / "sources" / "retained.png"
    source.parent.mkdir(parents=True)
    source.write_bytes(content)
    item = replace(
        _item(game, job, source_order_index=0, suggested_sequence_number=7),
        status="accepted",
        source_state=state,
        selectable=False,
        source_relative_path="sources/retained.png",
        source_checksum_sha256=hashlib.sha256(content).hexdigest(),
    )
    repository = MemoryOperationalImageReviewRepository(
        game_id=game, import_job_id=job, items=[item]
    )
    app = create_app(
        replace(ApiSettings.from_environment({}), artifact_root=tmp_path),
        image_review_service_dependency=lambda: OperationalImageReviewService(repository),
    )
    with TestClient(app) as client:
        route = f"/api/v1/admin/image-review-items/{item.id}"
        context = {"gameId": str(game), "importJobId": str(job)}
        detail = client.get(route, params=context)
        assert detail.status_code == 200
        assert detail.json()["sourceState"] == state
        assert detail.json()["selectable"] is False
        preview = client.get(route + "/assets/source", params=context)
        assert preview.status_code == 200 and preview.content == content
