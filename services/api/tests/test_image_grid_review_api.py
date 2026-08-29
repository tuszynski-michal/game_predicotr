from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from game_predictor_api.api.image_grid_reviews import create_image_grid_reviews_router
from game_predictor_api.application.image_grid_reviews import (
    ImageGridReviewListSlice,
    ImageGridReviewRepository,
    ImageGridReviewService,
)
from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.image_grid_reviews import (
    ImageGridApprovalResult,
    ImageGridReviewCounts,
    ImageGridReviewError,
    ImageGridReviewListFilter,
    ImageGridReviewListItem,
    ImageGridReviewSourceAsset,
    ImageGridReviewState,
)
from game_predictor_api.domain.image_reviews import (
    ImageReviewGeometryCellArtifact,
    ImageReviewGeometryPoint,
    ImageReviewGeometryRevision,
)
from game_predictor_api.schemas.image_grid_reviews import (
    to_image_grid_review_geometry_response,
)

SOURCE_BYTES = b"source"
SHA = hashlib.sha256(SOURCE_BYTES).hexdigest()


class MemoryGridReviewRepository(ImageGridReviewRepository):
    def __init__(self, items: tuple[ImageGridReviewListItem, ...], source_path: str) -> None:
        self.items = items
        self.source_path = source_path
        self.approved: list[UUID] = []

    def require_game(self, game_id: UUID) -> None:
        if not self.items or self.items[0].game_id != game_id:
            raise ImageGridReviewError("GAME_NOT_FOUND", "missing")

    def list_grid_reviews(
        self,
        *,
        review_filter: ImageGridReviewListFilter,
        after_key: tuple[int, str] | None,
        before_key: tuple[int, str] | None,
        limit: int,
    ) -> ImageGridReviewListSlice:
        matching = [
            item
            for item in self.items
            if (
                review_filter.import_job_id is None
                or item.import_job_id == review_filter.import_job_id
            )
            and (
                review_filter.source_image_id is None
                or item.source_image_id == review_filter.source_image_id
            )
            and (review_filter.view.value == "all" or item.state.value == review_filter.view.value)
        ]
        if after_key is not None:
            matching = [item for item in matching if item.cursor_key > after_key]
        if before_key is not None:
            matching = [item for item in matching if item.cursor_key < before_key]
            visible = matching[-limit:]
        else:
            visible = matching[:limit]
        return ImageGridReviewListSlice(
            items=tuple(visible),
            has_previous=bool(visible and self.items[0].cursor_key < visible[0].cursor_key),
            has_next=bool(visible and self.items[-1].cursor_key > visible[-1].cursor_key),
        )

    def grid_review_counts(
        self,
        *,
        review_filter: ImageGridReviewListFilter,
    ) -> ImageGridReviewCounts:
        items = tuple(
            item
            for item in self.items
            if review_filter.import_job_id is None
            or item.import_job_id == review_filter.import_job_id
            if review_filter.source_image_id is None
            or item.source_image_id == review_filter.source_image_id
        )
        return ImageGridReviewCounts(
            needs_validation=sum(
                item.state is ImageGridReviewState.NEEDS_VALIDATION for item in items
            ),
            needs_correction=sum(
                item.state is ImageGridReviewState.NEEDS_CORRECTION for item in items
            ),
            approved=sum(item.state is ImageGridReviewState.APPROVED for item in items),
        )

    def get_grid_review_source_asset(
        self,
        *,
        game_id: UUID,
        review_item_id: UUID,
    ) -> ImageGridReviewSourceAsset | None:
        item = next((item for item in self.items if item.review_item_id == review_item_id), None)
        if item is None or item.game_id != game_id:
            return None
        return ImageGridReviewSourceAsset(
            review_item_id=item.review_item_id,
            source_relative_path=self.source_path,
            source_checksum_sha256=item.source_checksum_sha256,
            source_width=item.source_width,
            source_height=item.source_height,
            geometry_revision=item.geometry_revision,
            resolution_revision=item.resolution_revision,
            topology=item.topology,
        )

    def approve_grid_geometry(
        self,
        *,
        game_id: UUID,
        review_item_id: UUID,
        expected_resolution_revision: int,
        expected_geometry_revision: int,
        expected_source_checksum_sha256: str,
        expected_source_width: int,
        expected_source_height: int,
        expected_grid_rows: int,
        expected_grid_columns: int,
        actor: str,
    ) -> ImageGridApprovalResult:
        item = next(item for item in self.items if item.review_item_id == review_item_id)
        assert item.game_id == game_id
        assert expected_resolution_revision == item.resolution_revision
        assert expected_geometry_revision == item.geometry_revision
        assert expected_source_checksum_sha256 == item.source_checksum_sha256
        assert (expected_source_width, expected_source_height) == (
            item.source_width,
            item.source_height,
        )
        assert (expected_grid_rows, expected_grid_columns) == (
            item.topology.rows,
            item.topology.columns,
        )
        assert actor == "local-admin"
        self.approved.append(review_item_id)
        return ImageGridApprovalResult(
            item=replace(
                item,
                approved_geometry_revision=item.geometry_revision,
                state=ImageGridReviewState.APPROVED,
            ),
            changed=True,
        )


class UnusedOperationalService:
    pass


def _item(
    game_id: UUID,
    import_job_id: UUID,
    sequence_number: int,
    state: ImageGridReviewState,
    *,
    source_image_id: UUID | None = None,
    position_index: int = 0,
) -> ImageGridReviewListItem:
    return ImageGridReviewListItem(
        review_item_id=uuid4(),
        game_id=game_id,
        import_job_id=import_job_id,
        recognized_board_id=uuid4(),
        source_image_id=source_image_id or uuid4(),
        position_index=position_index,
        sequence_number=sequence_number,
        source_checksum_sha256=SHA,
        source_width=1920,
        source_height=1080,
        geometry_revision=1,
        approved_geometry_revision=(1 if state is ImageGridReviewState.APPROVED else None),
        resolution_revision=0,
        topology=BoardTopology(rows=3, columns=5),
        geometry={"source": "test"},
        asset_mode="virtual_source",
        geometry_engine_name="board-cell-processing-v20",
        geometry_engine_version="v20",
        board_confidence=0.91,
        reason_codes=("verified_registration",),
        state=state,
    )


def _client(
    tmp_path: Path,
) -> tuple[
    TestClient,
    MemoryGridReviewRepository,
    tuple[ImageGridReviewListItem, ...],
]:
    game_id = uuid4()
    import_job_id = uuid4()
    items = (
        _item(game_id, import_job_id, 1, ImageGridReviewState.NEEDS_VALIDATION),
        _item(game_id, import_job_id, 2, ImageGridReviewState.NEEDS_VALIDATION),
        _item(game_id, import_job_id, 3, ImageGridReviewState.NEEDS_CORRECTION),
    )
    source = tmp_path / "data" / "sources" / "source.jpg"
    source.parent.mkdir(parents=True)
    source.write_bytes(SOURCE_BYTES)
    repository = MemoryGridReviewRepository(items, "sources/source.jpg")
    app = FastAPI()
    app.include_router(
        create_image_grid_reviews_router(
            lambda: ImageGridReviewService(repository),
            lambda: UnusedOperationalService(),
            tmp_path,
        ),
        prefix="/api/v1",
    )

    @app.exception_handler(ImageGridReviewError)
    async def handle_error(_request: Request, error: ImageGridReviewError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"code": error.code, "message": error.message})

    return TestClient(app), repository, items


def test_grid_review_api_lists_keyset_page_and_approves_exact_revision(tmp_path: Path) -> None:
    client, repository, items = _client(tmp_path)
    first = client.get(
        f"/api/v1/admin/games/{items[0].game_id}/grid-reviews",
        params={"view": "needs_validation", "limit": 1},
    )
    assert first.status_code == 200
    assert [item["sequenceNumber"] for item in first.json()["items"]] == [1]
    assert first.json()["counts"] == {
        "needsValidation": 2,
        "needsCorrection": 1,
        "approved": 0,
        "total": 3,
    }
    second = client.get(
        f"/api/v1/admin/games/{items[0].game_id}/grid-reviews",
        params={
            "view": "needs_validation",
            "limit": 1,
            "afterCursor": first.json()["nextCursor"],
        },
    )
    assert second.status_code == 200
    assert [item["sequenceNumber"] for item in second.json()["items"]] == [2]
    assert second.json()["previousCursor"] is not None
    previous = client.get(
        f"/api/v1/admin/games/{items[0].game_id}/grid-reviews",
        params={
            "view": "needs_validation",
            "limit": 1,
            "beforeCursor": second.json()["previousCursor"],
        },
    )
    assert previous.status_code == 200
    assert [item["sequenceNumber"] for item in previous.json()["items"]] == [1]

    target = items[0]
    approved = client.post(
        f"/api/v1/admin/image-reviews/{target.review_item_id}/geometry-approval",
        params={"gameId": str(target.game_id)},
        json={
            "expectedResolutionRevision": target.resolution_revision,
            "expectedGeometryRevision": target.geometry_revision,
            "expectedSourceChecksumSha256": target.source_checksum_sha256,
            "expectedSourceWidth": target.source_width,
            "expectedSourceHeight": target.source_height,
            "expectedGridRows": target.topology.rows,
            "expectedGridColumns": target.topology.columns,
        },
    )
    assert approved.status_code == 200
    assert approved.json()["changed"] is True
    assert approved.json()["item"]["state"] == "approved"
    assert repository.approved == [target.review_item_id]

    asset = client.get(
        f"/api/v1/admin/image-reviews/{target.review_item_id}/source-asset",
        params={
            "gameId": str(target.game_id),
            "expectedSourceChecksumSha256": target.source_checksum_sha256,
        },
    )
    assert asset.status_code == 200
    assert asset.content == SOURCE_BYTES


def test_grid_review_cursor_cannot_be_replayed_in_another_filter(tmp_path: Path) -> None:
    client, _repository, items = _client(tmp_path)
    response = client.get(
        f"/api/v1/admin/games/{items[0].game_id}/grid-reviews",
        params={"view": "needs_validation", "limit": 1},
    )
    cursor = response.json()["nextCursor"]
    conflict = client.get(
        f"/api/v1/admin/games/{items[0].game_id}/grid-reviews",
        params={"view": "all", "afterCursor": cursor},
    )

    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IMAGE_GRID_REVIEW_CURSOR_SCOPE_INVALID"


def test_grid_review_api_lists_only_one_source_and_binds_cursor_scope(tmp_path: Path) -> None:
    client, _repository, items = _client(tmp_path)
    source_image_id = uuid4()
    other_source_image_id = uuid4()
    game_id = items[0].game_id
    import_job_id = items[0].import_job_id
    source_items = (
        _item(
            game_id,
            import_job_id,
            10,
            ImageGridReviewState.NEEDS_VALIDATION,
            source_image_id=source_image_id,
            position_index=0,
        ),
        _item(
            game_id,
            import_job_id,
            11,
            ImageGridReviewState.NEEDS_VALIDATION,
            source_image_id=source_image_id,
            position_index=1,
        ),
        _item(
            game_id,
            import_job_id,
            12,
            ImageGridReviewState.NEEDS_VALIDATION,
            source_image_id=other_source_image_id,
            position_index=0,
        ),
    )
    _repository.items = source_items

    response = client.get(
        f"/api/v1/admin/games/{game_id}/grid-reviews",
        params={
            "view": "all",
            "sourceImageId": str(source_image_id),
            "limit": 1,
        },
    )

    assert response.status_code == 200
    assert [item["sequenceNumber"] for item in response.json()["items"]] == [10]
    assert response.json()["counts"]["total"] == 2
    assert response.json()["items"][0]["sourceImageId"] == str(source_image_id)
    assert response.json()["items"][0]["positionIndex"] == 0
    assert response.json()["items"][0]["assetMode"] == "virtual_source"
    assert response.json()["items"][0]["boardConfidence"] == 0.91

    conflict = client.get(
        f"/api/v1/admin/games/{game_id}/grid-reviews",
        params={
            "view": "all",
            "sourceImageId": str(other_source_image_id),
            "afterCursor": response.json()["nextCursor"],
        },
    )

    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IMAGE_GRID_REVIEW_CURSOR_SCOPE_INVALID"


def test_grid_geometry_response_uses_the_pinned_topology_for_row_major_indices() -> None:
    revision = ImageReviewGeometryRevision(
        id=uuid4(),
        review_item_id=uuid4(),
        recognized_board_id=uuid4(),
        revision=1,
        idempotency_key=uuid4(),
        command_sha256="1" * 64,
        decision_checksum_sha256="2" * 64,
        corners=(
            ImageReviewGeometryPoint(0, 0),
            ImageReviewGeometryPoint(80, 0),
            ImageReviewGeometryPoint(80, 20),
            ImageReviewGeometryPoint(0, 20),
        ),
        board_relative_path="boards/board.png",
        board_checksum_sha256="3" * 64,
        cropper_version="topology-aware-test-v1",
        cells=tuple(
            ImageReviewGeometryCellArtifact(
                row_index=index // 4,
                column_index=index % 4,
                crop_relative_path=f"cells/{index}.png",
                crop_checksum_sha256=f"{index + 10:064x}",
            )
            for index in range(8)
        ),
        corrected_by="local-admin",
        created_at=datetime(2026, 8, 28, tzinfo=UTC),
    )

    response = to_image_grid_review_geometry_response(
        revision=revision,
        grid_rows=2,
        grid_columns=4,
        created=True,
    )

    assert response.geometry_revision.grid_rows == 2
    assert response.geometry_revision.grid_columns == 4
    assert [cell.cell_index for cell in response.geometry_revision.cells] == list(range(8))
