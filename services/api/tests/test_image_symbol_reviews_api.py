from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from game_predictor_api.application.image_symbol_review_bulk_operations import (
    SymbolCellReviewBulkOperation,
    SymbolCellReviewBulkOperationService,
    SymbolCellReviewBulkOperationStatus,
    SymbolCellReviewBulkPreview,
    SymbolCellReviewBulkRequest,
)
from game_predictor_api.application.image_symbol_reviews import (
    SymbolCellReviewListSlice,
    SymbolCellReviewQueryService,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.image_symbol_reviews import (
    SymbolCellReviewAsset,
    SymbolCellReviewCounts,
    SymbolCellReviewError,
    SymbolCellReviewFilterState,
    SymbolCellReviewListFilter,
    SymbolCellReviewListItem,
    SymbolCellReviewState,
)
from game_predictor_api.main import create_app


class MemorySymbolCellReviewRepository:
    def __init__(
        self,
        *,
        game_id: UUID,
        symbol_id: UUID,
        items: tuple[SymbolCellReviewListItem, ...],
        asset: SymbolCellReviewAsset | None = None,
        ready: bool = True,
    ) -> None:
        self.game_id = game_id
        self.symbol_id = symbol_id
        self.items = tuple(sorted(items, key=lambda item: item.cursor_key))
        self.asset_value = asset
        self.ready = ready
        self.filters: list[SymbolCellReviewListFilter] = []

    def require_ready_game(self, game_id: UUID) -> int:
        if game_id != self.game_id:
            raise SymbolCellReviewError("GAME_NOT_FOUND", "The selected game does not exist.")
        if not self.ready:
            raise SymbolCellReviewError(
                "SYMBOL_CELL_REVIEW_PROJECTION_INCOMPLETE",
                "The symbol-cell review projection is not ready for this game.",
            )
        return 17

    def list_items(
        self,
        *,
        review_filter: SymbolCellReviewListFilter,
        after_key: tuple[int, int, str] | None,
        before_key: tuple[int, int, str] | None,
        limit: int,
    ) -> SymbolCellReviewListSlice:
        self.filters.append(review_filter)
        filtered = tuple(
            item
            for item in self.items
            if (item.assigned_symbol_id == review_filter.symbol_id)
            and (
                review_filter.state is SymbolCellReviewFilterState.ALL
                or item.review_state.value == review_filter.state.value
            )
        )
        if after_key is not None:
            start = next(
                (index + 1 for index, item in enumerate(filtered) if item.cursor_key == after_key),
                len(filtered),
            )
            page = filtered[start : start + limit]
            return SymbolCellReviewListSlice(
                items=page,
                has_previous=start > 0,
                has_next=start + len(page) < len(filtered),
            )
        if before_key is not None:
            end = next(
                (index for index, item in enumerate(filtered) if item.cursor_key == before_key),
                0,
            )
            start = max(0, end - limit)
            return SymbolCellReviewListSlice(
                items=filtered[start:end],
                has_previous=start > 0,
                has_next=end < len(filtered),
            )
        page = filtered[:limit]
        return SymbolCellReviewListSlice(
            items=page,
            has_previous=False,
            has_next=len(page) < len(filtered),
        )

    def counts(self, *, review_filter: SymbolCellReviewListFilter) -> SymbolCellReviewCounts:
        visible = tuple(
            item for item in self.items if item.assigned_symbol_id == review_filter.symbol_id
        )
        approved = sum(item.review_state is SymbolCellReviewState.APPROVED for item in visible)
        pending = len(visible) - approved
        return SymbolCellReviewCounts(
            all_count=len(visible), approved_count=approved, pending_count=pending
        )

    def get_asset(self, *, game_id: UUID, cell_review_id: UUID) -> SymbolCellReviewAsset | None:
        if game_id != self.game_id or self.asset_value is None:
            return None
        return self.asset_value if self.asset_value.cell_review_id == cell_review_id else None


class MemorySymbolCellReviewBulkRepository:
    def __init__(self, *, game_id: UUID) -> None:
        self.game_id = game_id
        self.requests: list[SymbolCellReviewBulkRequest] = []
        self.operations: dict[UUID, SymbolCellReviewBulkOperation] = {}
        self._idempotency: dict[UUID, SymbolCellReviewBulkOperation] = {}

    def preview(
        self,
        *,
        game_id: UUID,
        request: SymbolCellReviewBulkRequest,
    ) -> SymbolCellReviewBulkPreview:
        assert game_id == self.game_id
        self.requests.append(request)
        return SymbolCellReviewBulkPreview(
            action=request.action,
            selection_kind=request.selection_kind,
            catalog_revision=(
                7
                if request.filter_selection is None
                else request.filter_selection.catalog_revision
            ),
            target_count=3,
            board_count=1,
            target_symbol_id=request.target_symbol_id,
        )

    def start(
        self,
        *,
        game_id: UUID,
        request: SymbolCellReviewBulkRequest,
        idempotency_key: UUID,
    ) -> tuple[SymbolCellReviewBulkOperation, bool]:
        assert game_id == self.game_id
        existing = self._idempotency.get(idempotency_key)
        if existing is not None:
            if existing.command_sha256 != request.command_sha256:
                raise SymbolCellReviewError(
                    "SYMBOL_CELL_REVIEW_BULK_IDEMPOTENCY_CONFLICT",
                    "The idempotency key already represents another bulk review command.",
                )
            return existing, False
        self.requests.append(request)
        operation = SymbolCellReviewBulkOperation(
            id=uuid4(),
            job_id=uuid4(),
            game_id=game_id,
            action=request.action,
            target_symbol_id=request.target_symbol_id,
            selection_kind=request.selection_kind,
            status=SymbolCellReviewBulkOperationStatus.CREATED,
            catalog_revision=(
                None
                if request.filter_selection is None
                else request.filter_selection.catalog_revision
            ),
            target_count=3,
            applied_count=0,
            conflict_count=0,
            failed_count=0,
            pending_count=3,
            error_code=None,
            error_message=None,
            command_sha256=request.command_sha256,
        )
        self.operations[operation.id] = operation
        self._idempotency[idempotency_key] = operation
        return operation, True

    def get(self, *, game_id: UUID, operation_id: UUID) -> SymbolCellReviewBulkOperation | None:
        if game_id != self.game_id:
            return None
        return self.operations.get(operation_id)


def _item(
    *,
    game_id: UUID,
    symbol_id: UUID | None,
    sequence_number: int,
    cell_index: int,
    review_item_id: UUID,
    state: SymbolCellReviewState = SymbolCellReviewState.PENDING,
) -> SymbolCellReviewListItem:
    return SymbolCellReviewListItem(
        cell_review_id=uuid4(),
        review_item_id=review_item_id,
        recognized_board_id=uuid4(),
        import_job_id=uuid4(),
        sequence_number=sequence_number,
        cell_index=cell_index,
        row_index=cell_index // 5,
        column_index=cell_index % 5,
        assigned_symbol_id=symbol_id,
        assigned_symbol_code="cherry" if symbol_id is not None else None,
        assigned_symbol_name="Cherry" if symbol_id is not None else None,
        prediction_symbol_code="cherry",
        review_state=state,
        has_grid_issue=False,
        revision=2,
        geometry_revision=0,
        crop_sample_id="b" * 64,
        crop_checksum_sha256="a" * 64,
        board_status="pending",
    )


def _client(
    repository: MemorySymbolCellReviewRepository,
    *,
    artifact_root: Path,
    bulk_repository: MemorySymbolCellReviewBulkRepository | None = None,
) -> TestClient:
    settings = replace(
        ApiSettings.from_environment(
            {"GAME_PREDICTOR_REMOTE_SELECTION_HOST_MAPPING_ENABLED": "false"}
        ),
        artifact_root=artifact_root,
    )
    app = create_app(
        settings,
        symbol_cell_review_query_service_dependency=lambda: SymbolCellReviewQueryService(
            repository
        ),
        symbol_cell_review_bulk_operation_service_dependency=(
            None
            if bulk_repository is None
            else lambda: SymbolCellReviewBulkOperationService(bulk_repository)
        ),
    )
    return TestClient(app)


def test_list_endpoint_uses_keyset_cursors_without_duplicates(tmp_path: Path) -> None:
    game_id, symbol_id = uuid4(), uuid4()
    items = tuple(
        _item(
            game_id=game_id,
            symbol_id=symbol_id,
            sequence_number=sequence,
            cell_index=cell_index,
            review_item_id=UUID(int=index + 1),
            state=(
                SymbolCellReviewState.APPROVED
                if index == 2
                else SymbolCellReviewState.PENDING
            ),
        )
        for index, (sequence, cell_index) in enumerate(((1, 0), (1, 1), (2, 0)), start=1)
    )
    repository = MemorySymbolCellReviewRepository(
        game_id=game_id, symbol_id=symbol_id, items=items
    )

    with _client(repository, artifact_root=tmp_path) as client:
        first = client.get(
            f"/api/v1/admin/games/{game_id}/symbol-cell-reviews",
            params={"symbolId": str(symbol_id), "limit": 2},
        )
        second = client.get(
            f"/api/v1/admin/games/{game_id}/symbol-cell-reviews",
            params={
                "symbolId": str(symbol_id),
                "limit": 2,
                "afterCursor": first.json()["nextCursor"],
            },
        )
        previous = client.get(
            f"/api/v1/admin/games/{game_id}/symbol-cell-reviews",
            params={
                "symbolId": str(symbol_id),
                "limit": 2,
                "beforeCursor": second.json()["previousCursor"],
            },
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert previous.status_code == 200
    first_ids = [item["id"] for item in first.json()["items"]]
    second_ids = [item["id"] for item in second.json()["items"]]
    assert len(set(first_ids).intersection(second_ids)) == 0
    assert [item["id"] for item in previous.json()["items"]] == first_ids
    assert first.json()["counts"] == {"allCount": 3, "approvedCount": 1, "pendingCount": 2}
    assert first.json()["items"][0]["cropSampleId"] == "b" * 64

    with _client(repository, artifact_root=tmp_path) as client:
        approved = client.get(
            f"/api/v1/admin/games/{game_id}/symbol-cell-reviews",
            params={"symbolId": str(symbol_id), "state": "approved"},
        )

    assert approved.status_code == 200
    assert [item["reviewState"] for item in approved.json()["items"]] == ["approved"]


def test_list_endpoint_supports_unknown_and_rejects_cross_scope_cursor(tmp_path: Path) -> None:
    game_id, symbol_id = uuid4(), uuid4()
    unknown = _item(
        game_id=game_id,
        symbol_id=None,
        sequence_number=3,
        cell_index=0,
        review_item_id=UUID(int=1),
    )
    known = _item(
        game_id=game_id,
        symbol_id=symbol_id,
        sequence_number=4,
        cell_index=0,
        review_item_id=UUID(int=2),
    )
    another_known = _item(
        game_id=game_id,
        symbol_id=symbol_id,
        sequence_number=5,
        cell_index=0,
        review_item_id=UUID(int=3),
    )
    repository = MemorySymbolCellReviewRepository(
        game_id=game_id, symbol_id=symbol_id, items=(unknown, known, another_known)
    )

    with _client(repository, artifact_root=tmp_path) as client:
        unknown_response = client.get(
            f"/api/v1/admin/games/{game_id}/symbol-cell-reviews",
            params={"symbolId": "unknown"},
        )
        known_response = client.get(
            f"/api/v1/admin/games/{game_id}/symbol-cell-reviews",
            params={"symbolId": str(symbol_id), "limit": 1},
        )
        wrong_scope = client.get(
            f"/api/v1/admin/games/{game_id}/symbol-cell-reviews",
            params={
                "symbolId": "unknown",
                "afterCursor": known_response.json()["nextCursor"],
            },
        )

    assert unknown_response.status_code == 200
    assert unknown_response.json()["items"][0]["assignedSymbolId"] is None
    assert repository.filters[0].symbol_id is None
    assert wrong_scope.status_code == 409
    assert wrong_scope.json()["code"] in {
        "SYMBOL_CELL_REVIEW_CURSOR_INVALID",
        "SYMBOL_CELL_REVIEW_CURSOR_SCOPE_INVALID",
    }


def test_list_endpoint_reports_projection_not_ready(tmp_path: Path) -> None:
    game_id, symbol_id = uuid4(), uuid4()
    repository = MemorySymbolCellReviewRepository(
        game_id=game_id,
        symbol_id=symbol_id,
        items=(),
        ready=False,
    )

    with _client(repository, artifact_root=tmp_path) as client:
        response = client.get(
            f"/api/v1/admin/games/{game_id}/symbol-cell-reviews",
            params={"symbolId": str(symbol_id)},
        )

    assert response.status_code == 409
    assert response.json()["code"] == "SYMBOL_CELL_REVIEW_PROJECTION_INCOMPLETE"


def test_asset_endpoint_rechecks_expected_and_file_checksum(tmp_path: Path) -> None:
    content = b"current-crop"
    crop = tmp_path / "data" / "crops" / "cell.png"
    crop.parent.mkdir(parents=True)
    crop.write_bytes(content)
    checksum = hashlib.sha256(content).hexdigest()
    game_id, symbol_id = uuid4(), uuid4()
    item = _item(
        game_id=game_id,
        symbol_id=symbol_id,
        sequence_number=1,
        cell_index=0,
        review_item_id=UUID(int=1),
    )
    asset = SymbolCellReviewAsset(
        cell_review_id=item.cell_review_id,
        crop_relative_path="data/crops/cell.png",
        crop_checksum_sha256=checksum,
        geometry_revision=0,
        current_geometry_revision=0,
    )
    repository = MemorySymbolCellReviewRepository(
        game_id=game_id, symbol_id=symbol_id, items=(item,), asset=asset
    )

    with _client(repository, artifact_root=tmp_path) as client:
        success = client.get(
            f"/api/v1/admin/games/{game_id}/symbol-cell-reviews/{item.cell_review_id}/asset",
            params={"expectedCropChecksumSha256": checksum},
        )
        stale = client.get(
            f"/api/v1/admin/games/{game_id}/symbol-cell-reviews/{item.cell_review_id}/asset",
            params={"expectedCropChecksumSha256": "b" * 64},
        )
        crop.write_bytes(b"changed")
        changed_file = client.get(
            f"/api/v1/admin/games/{game_id}/symbol-cell-reviews/{item.cell_review_id}/asset",
            params={"expectedCropChecksumSha256": checksum},
        )

    assert success.status_code == 200
    assert success.content == content
    assert stale.status_code == 409
    assert stale.json()["code"] == "SYMBOL_CELL_REVIEW_CROP_DRIFT"
    assert changed_file.status_code == 409
    assert changed_file.json()["code"] == "SYMBOL_CELL_REVIEW_ASSET_CHECKSUM_MISMATCH"


def test_bulk_operation_endpoints_are_local_actor_bound_and_idempotent(tmp_path: Path) -> None:
    game_id, source_symbol_id, target_symbol_id = uuid4(), uuid4(), uuid4()
    reviews = MemorySymbolCellReviewRepository(
        game_id=game_id,
        symbol_id=source_symbol_id,
        items=(),
    )
    bulk = MemorySymbolCellReviewBulkRepository(game_id=game_id)
    idempotency_key = uuid4()
    payload = {
        "action": "reassign",
        "targetSymbolId": str(target_symbol_id),
        "selection": {
            "kind": "filter",
            "symbolId": str(source_symbol_id),
            "state": "pending",
            "catalogRevision": 17,
            "excludedCellReviewIds": [],
        },
    }

    with _client(reviews, artifact_root=tmp_path, bulk_repository=bulk) as client:
        preview = client.post(
            f"/api/v1/admin/games/{game_id}/symbol-cell-review-operations/preview",
            json=payload,
        )
        created = client.post(
            f"/api/v1/admin/games/{game_id}/symbol-cell-review-operations",
            json={**payload, "idempotencyKey": str(idempotency_key)},
        )
        repeated = client.post(
            f"/api/v1/admin/games/{game_id}/symbol-cell-review-operations",
            json={**payload, "idempotencyKey": str(idempotency_key)},
        )
        operation_id = created.json()["operation"]["id"]
        status = client.get(
            f"/api/v1/admin/games/{game_id}/symbol-cell-review-operations/{operation_id}"
        )

    assert preview.status_code == 200
    assert preview.json()["targetCount"] == 3
    assert created.status_code == 200
    assert created.json()["created"] is True
    assert repeated.status_code == 200
    assert repeated.json()["created"] is False
    assert status.status_code == 200
    assert status.json()["pendingCount"] == 3
    assert {request.actor for request in bulk.requests} == {"local-admin"}


def test_bulk_operation_rejects_approval_of_unknown_filter(tmp_path: Path) -> None:
    game_id, symbol_id = uuid4(), uuid4()
    reviews = MemorySymbolCellReviewRepository(game_id=game_id, symbol_id=symbol_id, items=())
    bulk = MemorySymbolCellReviewBulkRepository(game_id=game_id)

    with _client(reviews, artifact_root=tmp_path, bulk_repository=bulk) as client:
        response = client.post(
            f"/api/v1/admin/games/{game_id}/symbol-cell-review-operations/preview",
            json={
                "action": "approve",
                "selection": {
                    "kind": "filter",
                    "symbolId": "unknown",
                    "state": "pending",
                    "catalogRevision": 17,
                    "excludedCellReviewIds": [],
                },
            },
        )

    assert response.status_code == 422
    assert response.json()["code"] == "SYMBOL_CELL_REVIEW_BULK_UNKNOWN_APPROVAL_FORBIDDEN"
