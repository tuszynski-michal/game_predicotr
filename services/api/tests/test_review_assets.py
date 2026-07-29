from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.application.review_assets import (
    resolve_review_board_asset,
    resolve_review_cell_asset,
    resolve_review_source_asset,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.reviews import (
    ReviewItem,
    ReviewItemStatus,
    ReviewNotFoundError,
)
from game_predictor_api.main import create_app


def _item(
    *,
    source_checksum: str,
    board_relative_path: str = "boards/seq-001/board.png",
) -> ReviewItem:
    cells = [
        {
            "cellIndex": index,
            "cropRelativePath": f"cells/seq-001/r{index // 5:02d}-c{index % 5:02d}.png",
        }
        for index in range(15)
    ]
    return ReviewItem(
        id=uuid4(),
        review_batch_id=uuid4(),
        board_id="1" * 64,
        selection_rank=1,
        sequence_number=1,
        source_image_id="source-1",
        source_image_checksum_sha256=source_checksum,
        source_group="source-group",
        board_relative_path=board_relative_path,
        status=ReviewItemStatus.PENDING,
        prediction_snapshot={"cells": cells},
        created_at=datetime.now(UTC),
    )


def _write_assets(crop_root: Path, source_root: Path) -> tuple[ReviewItem, bytes]:
    image_bytes = b"checksum-bound-source-image"
    source_root.mkdir(parents=True)
    (source_root / "source.jpg").write_bytes(image_bytes)
    (crop_root / "boards" / "seq-001").mkdir(parents=True)
    (crop_root / "boards" / "seq-001" / "board.png").write_bytes(b"board")
    (crop_root / "cells" / "seq-001").mkdir(parents=True)
    for index in range(15):
        path = crop_root / "cells" / "seq-001" / f"r{index // 5:02d}-c{index % 5:02d}.png"
        path.write_bytes(f"cell-{index}".encode())
    return _item(source_checksum=hashlib.sha256(image_bytes).hexdigest()), image_bytes


def test_resolves_only_item_scoped_images_and_verifies_source_checksum(
    tmp_path: Path,
) -> None:
    crop_root = tmp_path / "crops"
    source_root = tmp_path / "sources"
    item, source_bytes = _write_assets(crop_root, source_root)

    source = resolve_review_source_asset(item, source_root)
    board = resolve_review_board_asset(item, crop_root)
    cell = resolve_review_cell_asset(item, 14, crop_root)

    assert source.path.read_bytes() == source_bytes
    assert source.media_type == "image/jpeg"
    assert board.path.name == "board.png"
    assert board.media_type == "image/png"
    assert cell.path.name == "r02-c04.png"


def test_asset_resolution_fails_closed_for_unsafe_or_ambiguous_files(
    tmp_path: Path,
) -> None:
    crop_root = tmp_path / "crops"
    source_root = tmp_path / "sources"
    item, source_bytes = _write_assets(crop_root, source_root)

    with pytest.raises(ReviewNotFoundError) as invalid_cell:
        resolve_review_cell_asset(item, 15, crop_root)
    assert invalid_cell.value.code == "REVIEW_CELL_NOT_FOUND"

    unsafe = replace(item, board_relative_path="../source.jpg")
    with pytest.raises(ReviewNotFoundError) as unsafe_path:
        resolve_review_board_asset(unsafe, crop_root)
    assert unsafe_path.value.code == "REVIEW_ASSET_PATH_UNSAFE"

    (source_root / "duplicate.jpeg").write_bytes(source_bytes)
    with pytest.raises(ReviewNotFoundError) as ambiguous:
        resolve_review_source_asset(item, source_root)
    assert ambiguous.value.code == "REVIEW_SOURCE_ASSET_AMBIGUOUS"


class _AssetReviewService:
    def __init__(self, item: ReviewItem) -> None:
        self.item = item

    def get_review_item(self, review_item_id: UUID) -> ReviewItem:
        assert review_item_id == self.item.id
        return self.item


def test_item_scoped_asset_endpoints_stream_images_without_path_input(
    tmp_path: Path,
) -> None:
    crop_root = tmp_path / "crops"
    source_root = tmp_path / "sources"
    item, source_bytes = _write_assets(crop_root, source_root)
    settings = replace(
        ApiSettings.from_environment({}),
        review_crop_root=crop_root,
        review_source_root=source_root,
    )
    service = _AssetReviewService(item)

    with TestClient(
        create_app(
            settings,
            review_service_dependency=lambda: service,
        )
    ) as client:
        source = client.get(f"/api/v1/admin/review-items/{item.id}/assets/source")
        board = client.get(f"/api/v1/admin/review-items/{item.id}/assets/board")
        cell = client.get(f"/api/v1/admin/review-items/{item.id}/assets/cells/4")
        missing = client.get(f"/api/v1/admin/review-items/{item.id}/assets/cells/15")

    assert source.status_code == 200
    assert source.content == source_bytes
    assert source.headers["content-type"].startswith("image/jpeg")
    assert source.headers["cache-control"] == "private, immutable, max-age=31536000"
    assert board.content == b"board"
    assert cell.content == b"cell-4"
    assert missing.status_code == 404
    assert missing.json()["code"] == "REVIEW_CELL_NOT_FOUND"
