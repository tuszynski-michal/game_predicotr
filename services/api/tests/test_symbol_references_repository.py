from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from game_predictor_api.api.symbol_references import create_symbol_references_router
from game_predictor_api.application.symbol_references import (
    ApprovedSymbolReferenceService,
    ManagedSymbolReferenceArtifactStore,
)
from game_predictor_api.domain.catalog import Symbol, SymbolStatus
from game_predictor_api.domain.symbol_references import (
    ApprovedSymbolReferenceCandidate,
    SymbolReferenceImage,
)
from game_predictor_api.storage.symbol_references_repository import (
    SqlAlchemyApprovedSymbolReferenceRepository,
)
from sqlalchemy.dialects import postgresql


class MemoryApprovedReferences:
    def __init__(self, game_id, candidate):
        self.game_id = game_id
        self.candidate = candidate
        self.reference = None
        self.selection = None

    def game_exists(self, game_id):
        return game_id == self.game_id

    def list_candidates(self, *, after_key, limit, **kwargs):
        return (self.candidate,) if after_key is None else ()

    def get_candidate(self, *, observation_id, **kwargs):
        return self.candidate if observation_id == self.candidate.observation_id else None

    def get_reference(self, **kwargs):
        return self.reference

    def select_reference(self, **kwargs):
        self.selection = kwargs
        self.reference = SymbolReferenceImage(
            symbol_id=kwargs["symbol_id"],
            source_review_item_id=self.candidate.review_item_id,
            source_recognized_board_id=self.candidate.recognized_board_id,
            source_observation_id=self.candidate.observation_id,
            sequence_number=self.candidate.sequence_number,
            cell_index=self.candidate.cell_index,
            resolution_revision=self.candidate.resolution_revision,
            geometry_revision=self.candidate.geometry_revision,
            image_relative_path=kwargs["image_relative_path"],
            image_checksum_sha256=kwargs["expected_checksum_sha256"],
            selected_by=kwargs["selected_by"],
            selected_at=datetime.now(UTC),
        )
        return Symbol(
            id=kwargs["symbol_id"],
            game_id=kwargs["game_id"],
            mobile_code=1,
            code="lemon",
            name="Lemon",
            image_path=kwargs["image_relative_path"],
            is_wildcard=False,
            display_order=0,
            status=SymbolStatus.ACTIVE,
        )


def _candidate(path: str, checksum: str) -> ApprovedSymbolReferenceCandidate:
    return ApprovedSymbolReferenceCandidate(
        observation_id=uuid4(),
        review_item_id=uuid4(),
        recognized_board_id=uuid4(),
        sequence_number=81,
        cell_index=7,
        resolution_revision=3,
        geometry_revision=2,
        crop_relative_path=path,
        crop_checksum_sha256=checksum,
        status="corrected",
    )


def test_candidate_query_requires_canonical_human_resolution_not_model_prediction():
    repository = SqlAlchemyApprovedSymbolReferenceRepository(Mock())
    statement = repository._candidate_query(game_id=uuid4(), symbol_code="lemon")
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)

    assert "image_sequence_canonical" in sql
    assert "resolved_value" in sql
    assert "symbolCodes" in compiled.params.values()
    assert "prediction" not in sql.split("WHERE", maxsplit=1)[-1]
    assert ["accepted", "corrected"] in compiled.params.values()


def test_read_only_api_serves_checksum_bound_approved_crop(tmp_path):
    content = b"approved-crop"
    crop = tmp_path / "data" / "crops" / "approved.png"
    crop.parent.mkdir(parents=True)
    crop.write_bytes(content)
    game_id, symbol_id = uuid4(), uuid4()
    candidate = _candidate("data/crops/approved.png", hashlib.sha256(content).hexdigest())
    service = ApprovedSymbolReferenceService(MemoryApprovedReferences(game_id, candidate))
    app = FastAPI()
    app.include_router(create_symbol_references_router(lambda: service, tmp_path))

    with TestClient(app) as client:
        page = client.get(
            f"/admin/games/{game_id}/symbols/{symbol_id}/approved-image-candidates"
        )
        asset = client.get(
            f"/admin/games/{game_id}/symbols/{symbol_id}/approved-image-candidates/"
            f"{candidate.observation_id}/asset"
        )

    assert page.status_code == 200
    assert page.json()["items"] == [
        {
            "observationId": str(candidate.observation_id),
            "cropChecksumSha256": candidate.crop_checksum_sha256,
            "sequenceNumber": 81,
            "cellIndex": 7,
            "geometryRevision": 2,
            "status": "corrected",
        }
    ]
    assert asset.status_code == 200
    assert asset.content == content


def test_selection_api_copies_bytes_and_serves_only_durable_reference(tmp_path):
    content = b"approved-crop"
    crop = tmp_path / "data" / "crops" / "approved.png"
    crop.parent.mkdir(parents=True)
    crop.write_bytes(content)
    game_id, symbol_id = uuid4(), uuid4()
    candidate = _candidate("data/crops/approved.png", hashlib.sha256(content).hexdigest())
    repository = MemoryApprovedReferences(game_id, candidate)
    service = ApprovedSymbolReferenceService(
        repository,
        ManagedSymbolReferenceArtifactStore(tmp_path),
    )
    app = FastAPI()
    app.include_router(create_symbol_references_router(lambda: service, tmp_path))

    with TestClient(app) as client:
        response = client.post(
            f"/admin/games/{game_id}/symbols/{symbol_id}/approved-image-candidates/"
            f"{candidate.observation_id}/selection",
            json={"expectedChecksumSha256": candidate.crop_checksum_sha256, "selectedBy": "admin"},
        )
        reference = client.get(f"/admin/games/{game_id}/symbols/{symbol_id}/image/asset")

    assert response.status_code == 200
    assert repository.selection is not None
    assert response.json()["imagePath"] == repository.selection["image_relative_path"]
    assert reference.status_code == 200
    assert reference.content == content
