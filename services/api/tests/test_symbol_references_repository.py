from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from io import BytesIO
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
from game_predictor_api.domain.image_geometry_v2 import canonical_json_bytes
from game_predictor_api.domain.image_symbol_reviews import SymbolCellReviewAsset
from game_predictor_api.domain.symbol_references import (
    ApprovedSymbolReferenceCandidate,
    SymbolReferenceImage,
)
from game_predictor_api.storage.symbol_references_repository import (
    SqlAlchemyApprovedSymbolReferenceRepository,
)
from game_predictor_worker.images.normalization import (
    RGB_PIXEL_CHECKSUM_VERSION,
    CanonicalSourceLoader,
    rgb_pixel_checksum_sha256,
)
from game_predictor_worker.images.virtual_cell_extraction import (
    VIRTUAL_CELL_RENDER_SPEC_VERSION,
    source_direct_warp_rgb,
)
from PIL import Image
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
            image_checksum_sha256=kwargs["image_checksum_sha256"],
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


def test_candidate_query_requires_current_individual_human_approval_not_parent_resolution():
    repository = SqlAlchemyApprovedSymbolReferenceRepository(Mock())
    statement = repository._candidate_query(game_id=uuid4(), symbol_id=uuid4())
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)

    assert "image_symbol_review_cells" in sql
    assert "image_board_search_fast_documents" in sql
    assert "approved_crop_sample_id" in sql
    assert "review_state" in sql
    assert "image_sequence_canonical" not in sql
    assert "resolved_value" not in sql.split("WHERE", maxsplit=1)[-1]
    assert "approved" in compiled.params.values()
    assert "active" in compiled.params.values()


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
        page = client.get(f"/admin/games/{game_id}/symbols/{symbol_id}/approved-image-candidates")
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


def test_virtual_selection_materializes_a_durable_full_resolution_png(tmp_path):
    game_id, symbol_id = uuid4(), uuid4()
    candidate = _virtual_candidate(tmp_path)
    repository = MemoryApprovedReferences(game_id, candidate)
    service = ApprovedSymbolReferenceService(
        repository,
        ManagedSymbolReferenceArtifactStore(tmp_path),
    )
    app = FastAPI()
    app.include_router(create_symbol_references_router(lambda: service, tmp_path))

    with TestClient(app) as client:
        preview = client.get(
            f"/admin/games/{game_id}/symbols/{symbol_id}/approved-image-candidates/"
            f"{candidate.observation_id}/asset"
        )
        selected = client.post(
            f"/admin/games/{game_id}/symbols/{symbol_id}/approved-image-candidates/"
            f"{candidate.observation_id}/selection",
            json={"expectedChecksumSha256": candidate.crop_checksum_sha256, "selectedBy": "admin"},
        )

    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/png"
    with Image.open(BytesIO(preview.content)) as preview_image:
        assert preview_image.size == (64, 64)
    assert selected.status_code == 200
    reference_directory = tmp_path / "data" / "symbol-references" / str(game_id) / str(symbol_id)
    files = tuple(reference_directory.glob("*.png"))
    assert len(files) == 1
    stored = files[0].read_bytes()
    stored_checksum = hashlib.sha256(stored).hexdigest()
    assert repository.selection is not None
    assert repository.selection["image_checksum_sha256"] == stored_checksum
    assert stored_checksum != candidate.crop_checksum_sha256

    assert candidate.virtual_asset is not None
    source_checksum = candidate.virtual_asset.source_checksum_sha256
    assert source_checksum is not None
    source = tmp_path / "data" / "originals" / source_checksum[:2] / f"{source_checksum}.jpg"
    source.unlink()
    with TestClient(app) as client:
        reference = client.get(f"/admin/games/{game_id}/symbols/{symbol_id}/image/asset")
    assert reference.status_code == 200
    assert reference.content == stored


def _virtual_candidate(artifact_root):
    source = Image.new("RGB", (160, 120), color=(50, 90, 140))
    buffer = BytesIO()
    source.save(buffer, format="JPEG", quality=95)
    source_bytes = buffer.getvalue()
    source_checksum = hashlib.sha256(source_bytes).hexdigest()
    source_path = (
        artifact_root / "data" / "originals" / source_checksum[:2] / f"{source_checksum}.jpg"
    )
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(source_bytes)
    loader = CanonicalSourceLoader()
    frame = loader.load(source_path, expected_source_checksum_sha256=source_checksum)
    quad = [
        {"x": 20.0, "y": 20.0},
        {"x": 139.0, "y": 20.0},
        {"x": 139.0, "y": 99.0},
        {"x": 20.0, "y": 99.0},
    ]
    rgb = source_direct_warp_rgb(
        frame.rgb,
        source_quad=tuple((point["x"], point["y"]) for point in quad),
        output_width=64,
        output_height=64,
    )
    checksum = rgb_pixel_checksum_sha256(rgb)
    render_spec = {
        "configuration": {
            "extractorVersion": "direct-perspective-cell-v1",
            "outputHeight": 64,
            "outputWidth": 64,
        },
        "logicalCellKeySha256": "b" * 64,
        "normalizedPixelChecksumSha256": frame.source.normalized_pixel_checksum_sha256,
        "paddedSourceQuad": quad,
        "pixelChecksumVersion": RGB_PIXEL_CHECKSUM_VERSION,
        "schemaVersion": VIRTUAL_CELL_RENDER_SPEC_VERSION,
        "sourceChecksumSha256": source_checksum,
    }
    source_geometry_id = uuid4()
    asset = SymbolCellReviewAsset(
        cell_review_id=uuid4(),
        crop_relative_path=None,
        crop_checksum_sha256=checksum,
        geometry_revision=0,
        current_geometry_revision=0,
        revision=2,
        asset_mode="virtual_source",
        source_checksum_sha256=source_checksum,
        normalized_pixel_checksum_sha256=frame.source.normalized_pixel_checksum_sha256,
        source_geometry_revision_id=source_geometry_id,
        current_source_geometry_revision_id=source_geometry_id,
        geometry_checksum_sha256="c" * 64,
        logical_cell_key="b" * 64,
        render_spec=render_spec,
        render_spec_checksum_sha256=hashlib.sha256(canonical_json_bytes(render_spec)).hexdigest(),
        rendered_pixel_checksum_sha256=checksum,
        extractor_version="direct-perspective-cell-v1",
    )
    loader.clear()
    return replace(
        _candidate("data/crops/unused.png", checksum),
        resolution_revision=0,
        geometry_revision=0,
        crop_relative_path=None,
        crop_checksum_sha256=checksum,
        status="approved",
        asset_mode="virtual_source",
        virtual_asset=asset,
    )
