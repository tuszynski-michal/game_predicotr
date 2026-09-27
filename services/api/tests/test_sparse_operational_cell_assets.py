"""Asset URLs retain logical cell indices when the actual crop list is sparse."""

import hashlib
from dataclasses import replace
from uuid import uuid4

import pytest
from game_predictor_api.application.image_review_assets import resolve_operational_cell_asset
from game_predictor_api.domain.image_reviews import ImageReviewNotFoundError
from test_operational_image_reviews import _item


def test_sparse_cell_asset_uses_logical_index_and_rejects_outside(tmp_path):
    item = _item(uuid4(), uuid4(), source_order_index=0, suggested_sequence_number=62440)
    cells = []
    for index in (1, 14):
        data = f"real-crop-{index}".encode()
        path = tmp_path / "data" / f"cell-{index}.png"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(data)
        cells.append(
            replace(
                item.cells[index],
                crop_relative_path=path.name,
                crop_checksum_sha256=hashlib.sha256(data).hexdigest(),
            )
        )
    item = replace(item, cells=tuple(cells))
    for index in (1, 14):
        asset = resolve_operational_cell_asset(item, index, tmp_path)
        assert asset.path.read_bytes() == f"real-crop-{index}".encode()
    with pytest.raises(ImageReviewNotFoundError) as error:
        resolve_operational_cell_asset(item, 0, tmp_path)
    assert error.value.code == "IMAGE_REVIEW_CELL_NOT_FOUND"
