"""Existing detail/source routes support sparse image crops for symbol context."""

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


@pytest.mark.parametrize("indices", [(), (3, 8, 13), tuple(range(15))])
def test_existing_detail_and_checksum_bound_source_accept_sparse_crops(
    tmp_path: Path, indices: tuple[int, ...]
) -> None:
    game_id, job_id = uuid4(), uuid4()
    item = _item(game_id, job_id, source_order_index=0, suggested_sequence_number=62440)
    source = tmp_path / "data" / "sources" / "context.png"
    source.parent.mkdir(parents=True)
    content = b"checksum-bound-source-context"
    source.write_bytes(content)
    geometry = {
        "imageWidth": 100,
        "imageHeight": 80,
        "latticeBoundsQuad": [
            {"x": -10, "y": 10},
            {"x": 90, "y": 10},
            {"x": 90, "y": 70},
            {"x": -10, "y": 70},
        ],
    }
    item = replace(
        item,
        cells=tuple(item.cells[index] for index in indices),
        source_relative_path="sources/context.png",
        source_checksum_sha256=hashlib.sha256(content).hexdigest(),
        geometry_revision=7,
        geometry=geometry,
    )
    repository = MemoryOperationalImageReviewRepository(
        game_id=game_id, import_job_id=job_id, items=[item]
    )
    app = create_app(
        replace(ApiSettings.from_environment({}), artifact_root=tmp_path),
        image_review_service_dependency=lambda: OperationalImageReviewService(repository),
    )
    with TestClient(app) as client:
        route = f"/api/v1/admin/image-review-items/{item.id}"
        params = {"gameId": str(game_id), "importJobId": str(job_id)}
        detail = client.get(route, params=params)
        assert detail.status_code == 200, detail.text
        payload = detail.json()
        assert [cell["cellIndex"] for cell in payload["cells"]] == list(indices)
        assert payload["geometryRevision"] == 7
        assert payload["geometry"] == geometry
        assert payload["sourceChecksumSha256"] == item.source_checksum_sha256
        image = client.get(route + "/assets/source", params=params)
        assert image.status_code == 200 and image.content == content
        source.write_bytes(b"changed-source")
        stale = client.get(route + "/assets/source", params=params)
        assert stale.status_code == 404
        assert stale.json()["code"] == "IMAGE_REVIEW_ASSET_CHECKSUM_DRIFT"
