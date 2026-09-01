from __future__ import annotations

import hashlib
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from game_predictor_api.application.image_symbol_review_backfill import (
    SymbolCellReviewBackfillService,
    SymbolCellReviewProjectionStart,
    SymbolCellReviewProjectionStatus,
)
from game_predictor_api.application.image_symbol_review_bulk_operations import (
    SymbolCellReviewBulkOperation,
    SymbolCellReviewBulkOperationService,
    SymbolCellReviewBulkOperationStatus,
    SymbolCellReviewBulkPreview,
    SymbolCellReviewBulkRequest,
)
from game_predictor_api.application.image_symbol_review_mutations import (
    SymbolCellReviewMutationCommand,
    SymbolCellReviewMutationResult,
    SymbolCellReviewMutationService,
)
from game_predictor_api.application.image_symbol_reviews import (
    SymbolCellReviewListSlice,
    SymbolCellReviewQueryService,
)
from game_predictor_api.application.unreadable_board_reviews import (
    ResolveUnreadableCellCommand,
    UnreadableBoardReviewCell,
    UnreadableBoardReviewDetail,
    UnreadableBoardReviewListItem,
    UnreadableBoardReviewService,
    UnreadableBoardReviewSlice,
    UnreadableBoardReviewView,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.image_geometry_v2 import canonical_json_bytes
from game_predictor_api.domain.image_symbol_reviews import (
    SymbolCellCropApprovalState,
    SymbolCellQualityIssue,
    SymbolCellReviewAsset,
    SymbolCellReviewCounts,
    SymbolCellReviewError,
    SymbolCellReviewFilterState,
    SymbolCellReviewListFilter,
    SymbolCellReviewListItem,
    SymbolCellReviewState,
)
from game_predictor_api.domain.jobs import JobType, create_job
from game_predictor_api.main import create_app
from game_predictor_worker.images.normalization import (
    CanonicalSourceLoader,
    rgb_pixel_checksum_sha256,
)
from game_predictor_worker.images.virtual_cell_extraction import source_direct_warp_rgb
from PIL import Image


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
        self.limits: list[int] = []

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
        after_key: tuple[int, int, UUID] | None,
        before_key: tuple[int, int, UUID] | None,
        limit: int,
    ) -> SymbolCellReviewListSlice:
        self.filters.append(review_filter)
        self.limits.append(limit)
        filtered = tuple(
            item
            for item in self.items
            if (
                review_filter.include_all_symbols
                or item.assigned_symbol_id == review_filter.symbol_id
            )
            and (
                review_filter.state is SymbolCellReviewFilterState.ALL
                or item.review_state.value == review_filter.state.value
            )
            and (
                review_filter.min_confidence is None
                or (
                    item.prediction_confidence is not None
                    and item.prediction_confidence >= review_filter.min_confidence
                )
            )
            and (
                review_filter.max_confidence is None
                or (
                    item.prediction_confidence is not None
                    and item.prediction_confidence <= review_filter.max_confidence
                )
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
            item
            for item in self.items
            if (
                review_filter.include_all_symbols
                or item.assigned_symbol_id == review_filter.symbol_id
            )
            and (
                review_filter.state is SymbolCellReviewFilterState.ALL
                or item.review_state.value == review_filter.state.value
            )
            and (
                review_filter.min_confidence is None
                or (
                    item.prediction_confidence is not None
                    and item.prediction_confidence >= review_filter.min_confidence
                )
            )
            and (
                review_filter.max_confidence is None
                or (
                    item.prediction_confidence is not None
                    and item.prediction_confidence <= review_filter.max_confidence
                )
            )
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

    def get_assets(
        self,
        *,
        game_id: UUID,
        cell_review_ids: tuple[UUID, ...],
    ) -> tuple[SymbolCellReviewAsset, ...]:
        if game_id != self.game_id or self.asset_value is None:
            return ()
        return tuple(
            self.asset_value
            for cell_review_id in cell_review_ids
            if cell_review_id == self.asset_value.cell_review_id
        )


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
                7 if request.filter_selection is None else request.filter_selection.catalog_revision
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


class MemorySymbolCellReviewMutationRepository:
    def __init__(self, *, error: SymbolCellReviewError | None = None) -> None:
        self.commands: list[SymbolCellReviewMutationCommand] = []
        self.error = error

    def apply_mutation(
        self,
        command: SymbolCellReviewMutationCommand,
    ) -> SymbolCellReviewMutationResult:
        self.commands.append(command)
        if self.error is not None:
            raise self.error
        return SymbolCellReviewMutationResult(
            cell_review_id=command.cell_review_id,
            review_item_id=uuid4(),
            sequence_number=10,
            cell_revision=command.expected_revision + 1,
            review_state=SymbolCellReviewState.APPROVED,
            assigned_symbol_id=command.target_symbol_id,
            has_grid_issue=False,
            quality_issue=(
                SymbolCellQualityIssue.UNREADABLE
                if command.action.value == "mark_unreadable"
                else None
            ),
            board_status="pending",
            board_resolution_action=None,
            board_reopened=False,
            catalog_revision=18,
        )

    def apply_board_mutations(
        self,
        commands: tuple[SymbolCellReviewMutationCommand, ...],
    ) -> tuple[SymbolCellReviewMutationResult, ...]:
        return tuple(self.apply_mutation(command) for command in commands)


class MemorySymbolCellReviewBackfillRepository:
    def __init__(self, *, game_id: UUID) -> None:
        self.game_id = game_id
        self.job = None
        self.start_count = 0

    def status(self, game_id: UUID) -> SymbolCellReviewProjectionStatus:
        assert game_id == self.game_id
        return SymbolCellReviewProjectionStatus(
            game_id=game_id,
            status="not_started" if self.job is None else "rebuilding",
            expected_board_count=2,
            expected_cell_count=30,
            processed_board_count=0,
            persisted_cell_count=0,
            missing_sequence_count=0,
            invalid_crop_count=0,
            invalid_geometry_count=0,
            failure_message=None,
            sample_problem_review_item_ids=(),
            active_job_id=None if self.job is None else self.job.id,
            table_bytes_before=0,
            index_bytes_before=0,
            table_bytes_current=0,
            index_bytes_current=0,
            database_free_bytes_current=1_000_000,
        )

    def start(self, game_id: UUID) -> SymbolCellReviewProjectionStart:
        assert game_id == self.game_id
        created = self.job is None
        if self.job is None:
            self.start_count += 1
            self.job = create_job(
                JobType.IMAGE_SYMBOL_REVIEW_BACKFILL,
                game_id=game_id,
                input_payload={
                    "schema_version": 1,
                    "workflow": "image_symbol_review_backfill",
                    "generation": 1,
                },
            )
        return SymbolCellReviewProjectionStart(
            status=self.status(game_id),
            job=self.job,
            created=created,
        )


class MemoryUnreadableBoardReviewRepository:
    def __init__(self, *, game_id: UUID) -> None:
        self.game_id = game_id
        self.review_item_id = uuid4()
        self.board_id = uuid4()
        self.import_job_id = uuid4()
        self.commands: list[ResolveUnreadableCellCommand] = []

    def require_ready_game(self, game_id: UUID) -> None:
        assert game_id == self.game_id

    def list_boards(
        self,
        *,
        game_id: UUID,
        view: UnreadableBoardReviewView,
        after_key: tuple[int, str] | None,
        limit: int,
    ) -> UnreadableBoardReviewSlice:
        assert game_id == self.game_id
        assert after_key is None
        assert limit == 25
        return UnreadableBoardReviewSlice(
            items=(
                UnreadableBoardReviewListItem(
                    review_item_id=self.review_item_id,
                    recognized_board_id=self.board_id,
                    import_job_id=self.import_job_id,
                    sequence_number=41,
                    board_status="pending",
                    grid_rows=2,
                    grid_columns=4,
                    unreadable_count=1,
                    pending_unreadable_count=1 if view is UnreadableBoardReviewView.PENDING else 0,
                ),
            ),
            has_next=False,
        )

    def get_board(
        self,
        *,
        game_id: UUID,
        review_item_id: UUID,
    ) -> UnreadableBoardReviewDetail | None:
        if game_id != self.game_id or review_item_id != self.review_item_id:
            return None
        return UnreadableBoardReviewDetail(
            review_item_id=review_item_id,
            recognized_board_id=self.board_id,
            import_job_id=self.import_job_id,
            sequence_number=41,
            board_status="pending",
            grid_rows=2,
            grid_columns=4,
            cells=tuple(
                UnreadableBoardReviewCell(
                    cell_review_id=uuid4(),
                    cell_index=index,
                    row_index=index // 4,
                    column_index=index % 4,
                    assigned_symbol_id=None,
                    assigned_symbol_code=None,
                    assigned_symbol_name=None,
                    prediction_symbol_code="cherry",
                    review_state="pending" if index == 3 else "approved",
                    quality_issue="unreadable" if index == 3 else None,
                    revision=2,
                    geometry_revision=1,
                    crop_sample_id="b" * 64,
                    crop_checksum_sha256="a" * 64,
                )
                for index in range(8)
            ),
        )

    def resolve_cell(
        self,
        command: ResolveUnreadableCellCommand,
    ) -> SymbolCellReviewMutationResult:
        self.commands.append(command)
        return SymbolCellReviewMutationResult(
            cell_review_id=uuid4(),
            review_item_id=command.review_item_id,
            sequence_number=41,
            cell_revision=command.expected_revision + 1,
            review_state=SymbolCellReviewState.APPROVED,
            assigned_symbol_id=command.target_symbol_id,
            has_grid_issue=False,
            quality_issue=SymbolCellQualityIssue.UNREADABLE,
            board_status="corrected",
            board_resolution_action="corrected",
            board_reopened=False,
            catalog_revision=19,
        )


def _item(
    *,
    game_id: UUID,
    symbol_id: UUID | None,
    sequence_number: int,
    cell_index: int,
    review_item_id: UUID,
    prediction_confidence: float | None = None,
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
        quality_issue=None,
        crop_approval_state=SymbolCellCropApprovalState.UNVERIFIED,
        revision=2,
        geometry_revision=0,
        crop_sample_id="b" * 64,
        crop_checksum_sha256="a" * 64,
        board_status="pending",
        prediction_confidence=prediction_confidence,
    )


def _client(
    repository: MemorySymbolCellReviewRepository,
    *,
    artifact_root: Path,
    bulk_repository: MemorySymbolCellReviewBulkRepository | None = None,
    mutation_repository: MemorySymbolCellReviewMutationRepository | None = None,
    backfill_repository: MemorySymbolCellReviewBackfillRepository | None = None,
    unreadable_repository: MemoryUnreadableBoardReviewRepository | None = None,
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
        symbol_cell_review_mutation_service_dependency=(
            None
            if mutation_repository is None
            else lambda: SymbolCellReviewMutationService(mutation_repository)
        ),
        symbol_cell_review_bulk_operation_service_dependency=(
            None
            if bulk_repository is None
            else lambda: SymbolCellReviewBulkOperationService(bulk_repository)
        ),
        symbol_cell_review_backfill_service_dependency=(
            None
            if backfill_repository is None
            else lambda: SymbolCellReviewBackfillService(backfill_repository)
        ),
        unreadable_board_review_service_dependency=(
            None
            if unreadable_repository is None
            else lambda: UnreadableBoardReviewService(unreadable_repository)
        ),
    )
    return TestClient(app)


def _virtual_source_asset(
    artifact_root: Path,
    *,
    cell_review_id: UUID,
) -> SymbolCellReviewAsset:
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
    pixel_checksum = rgb_pixel_checksum_sha256(rgb)
    render_spec = {
        "boardSlot": 0,
        "cellIndex": 0,
        "columnIndex": 0,
        "configuration": {
            "extractorVersion": "direct-perspective-cell-v1",
            "outputHeight": 64,
            "outputWidth": 64,
        },
        "coordinateSpace": "exif-normalized-rgb-pixels-v1",
        "geometryFingerprintSha256": "a" * 64,
        "geometryRevision": 0,
        "logicalCellKeySha256": "b" * 64,
        "paddedSourceQuad": quad,
        "renderedPixelChecksumSha256": pixel_checksum,
        "rowIndex": 0,
        "schemaVersion": "virtual-cell-render-spec-v1",
        "sourceChecksumSha256": source_checksum,
    }
    source_geometry_revision_id = uuid4()
    return SymbolCellReviewAsset(
        cell_review_id=cell_review_id,
        crop_relative_path=None,
        crop_checksum_sha256=pixel_checksum,
        geometry_revision=0,
        current_geometry_revision=0,
        revision=2,
        asset_mode="virtual_source",
        source_checksum_sha256=source_checksum,
        normalized_pixel_checksum_sha256=frame.source.normalized_pixel_checksum_sha256,
        source_geometry_revision_id=source_geometry_revision_id,
        current_source_geometry_revision_id=source_geometry_revision_id,
        geometry_checksum_sha256="c" * 64,
        logical_cell_key="b" * 64,
        render_spec=render_spec,
        render_spec_checksum_sha256=hashlib.sha256(canonical_json_bytes(render_spec)).hexdigest(),
        rendered_pixel_checksum_sha256=pixel_checksum,
        extractor_version="direct-perspective-cell-v1",
    )


def test_unreadable_board_endpoints_preserve_topology_and_assignment_kind(
    tmp_path: Path,
) -> None:
    game_id, symbol_id = uuid4(), uuid4()
    repository = MemorySymbolCellReviewRepository(
        game_id=game_id,
        symbol_id=symbol_id,
        items=(),
    )
    unreadable = MemoryUnreadableBoardReviewRepository(game_id=game_id)
    with _client(
        repository,
        artifact_root=tmp_path,
        unreadable_repository=unreadable,
    ) as client:
        page = client.get(f"/api/v1/admin/games/{game_id}/unreadable-board-reviews")
        detail = client.get(
            f"/api/v1/admin/games/{game_id}/unreadable-board-reviews/{unreadable.review_item_id}"
        )
        unknown = client.post(
            f"/api/v1/admin/games/{game_id}/unreadable-board-reviews/"
            f"{unreadable.review_item_id}/cells/3/resolve",
            json={
                "assignment": {"kind": "unknown"},
                "expectedRevision": 2,
                "expectedGeometryRevision": 1,
                "expectedCropSampleId": "b" * 64,
                "expectedCropChecksumSha256": "a" * 64,
            },
        )
        symbol = client.post(
            f"/api/v1/admin/games/{game_id}/unreadable-board-reviews/"
            f"{unreadable.review_item_id}/cells/3/resolve",
            json={
                "assignment": {"kind": "symbol", "symbolId": str(symbol_id)},
                "expectedRevision": 2,
                "expectedGeometryRevision": 1,
                "expectedCropSampleId": "b" * 64,
                "expectedCropChecksumSha256": "a" * 64,
            },
        )

    assert page.status_code == 200
    assert page.json()["items"][0]["pendingUnreadableCount"] == 1
    assert detail.status_code == 200
    assert detail.json()["gridRows"] == 2
    assert detail.json()["gridColumns"] == 4
    assert len(detail.json()["cells"]) == 8
    assert unknown.status_code == 200
    assert symbol.status_code == 200
    assert unreadable.commands[0].target_symbol_id is None
    assert unreadable.commands[1].target_symbol_id == symbol_id


def test_projection_status_and_start_are_idempotent(tmp_path: Path) -> None:
    game_id, symbol_id = uuid4(), uuid4()
    repository = MemorySymbolCellReviewRepository(
        game_id=game_id,
        symbol_id=symbol_id,
        items=(),
    )
    backfill = MemorySymbolCellReviewBackfillRepository(game_id=game_id)

    with _client(
        repository,
        artifact_root=tmp_path,
        backfill_repository=backfill,
    ) as client:
        initial = client.get(f"/api/v1/admin/games/{game_id}/symbol-cell-review-projection")
        first = client.post(f"/api/v1/admin/games/{game_id}/symbol-cell-review-projection")
        second = client.post(f"/api/v1/admin/games/{game_id}/symbol-cell-review-projection")

    assert initial.status_code == 200
    assert initial.json() == {
        "gameId": str(game_id),
        "status": "not_started",
        "expectedBoardCount": 2,
        "expectedCellCount": 30,
        "processedBoardCount": 0,
        "persistedCellCount": 0,
        "missingSequenceCount": 0,
        "invalidCropCount": 0,
        "invalidGeometryCount": 0,
        "failureMessage": None,
        "sampleProblemReviewItemIds": [],
        "activeJobId": None,
        "tableBytesBefore": 0,
        "indexBytesBefore": 0,
        "tableBytesCurrent": 0,
        "indexBytesCurrent": 0,
        "databaseFreeBytesCurrent": 1_000_000,
    }
    assert first.status_code == 200
    assert first.json()["created"] is True
    assert second.status_code == 200
    assert second.json()["created"] is False
    assert second.json()["jobId"] == first.json()["jobId"]
    assert second.json()["projection"]["activeJobId"] == first.json()["jobId"]
    assert backfill.start_count == 1


def test_list_endpoint_uses_keyset_cursors_without_duplicates(tmp_path: Path) -> None:
    game_id, symbol_id = uuid4(), uuid4()
    items = tuple(
        _item(
            game_id=game_id,
            symbol_id=symbol_id,
            sequence_number=sequence,
            cell_index=cell_index,
            review_item_id=UUID(int=index + 1),
            state=(SymbolCellReviewState.APPROVED if index == 2 else SymbolCellReviewState.PENDING),
        )
        for index, (sequence, cell_index) in enumerate(((1, 0), (1, 1), (2, 0)), start=1)
    )
    repository = MemorySymbolCellReviewRepository(game_id=game_id, symbol_id=symbol_id, items=items)

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
        counts = client.get(
            f"/api/v1/admin/games/{game_id}/symbol-cell-review-counts",
            params={
                "symbolId": str(symbol_id),
                "catalogRevision": first.json()["catalogRevision"],
            },
        )
        approved = client.get(
            f"/api/v1/admin/games/{game_id}/symbol-cell-reviews",
            params={"symbolId": str(symbol_id), "state": "approved"},
        )
        all_symbols = client.get(
            f"/api/v1/admin/games/{game_id}/symbol-cell-reviews",
            params={"symbolId": "all", "state": "all"},
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert previous.status_code == 200
    first_ids = [item["id"] for item in first.json()["items"]]
    second_ids = [item["id"] for item in second.json()["items"]]
    assert len(set(first_ids).intersection(second_ids)) == 0
    assert [item["id"] for item in previous.json()["items"]] == first_ids
    assert "counts" not in first.json()
    assert counts.status_code == 200
    assert counts.json() == {
        "catalogRevision": 17,
        "counts": {"allCount": 2, "approvedCount": 0, "pendingCount": 2},
    }
    assert first.json()["items"][0]["cropSampleId"] == "b" * 64
    assert approved.status_code == 200
    assert [item["reviewState"] for item in approved.json()["items"]] == ["approved"]
    assert all_symbols.status_code == 200
    assert len(all_symbols.json()["items"]) == 3
    assert repository.filters[-1].include_all_symbols is True


def test_counts_endpoint_rejects_a_stale_catalog_revision(tmp_path: Path) -> None:
    game_id, symbol_id = uuid4(), uuid4()
    repository = MemorySymbolCellReviewRepository(
        game_id=game_id,
        symbol_id=symbol_id,
        items=(),
    )

    with _client(repository, artifact_root=tmp_path) as client:
        response = client.get(
            f"/api/v1/admin/games/{game_id}/symbol-cell-review-counts",
            params={
                "symbolId": str(symbol_id),
                "catalogRevision": 16,
            },
        )

    assert response.status_code == 409
    assert response.json()["code"] == "SYMBOL_CELL_REVIEW_CATALOG_REVISION_STALE"


def test_list_endpoint_rejects_a_page_size_above_five_hundred(
    tmp_path: Path,
) -> None:
    game_id, symbol_id = uuid4(), uuid4()
    items = tuple(
        _item(
            game_id=game_id,
            symbol_id=symbol_id,
            sequence_number=(index // 15) + 1,
            cell_index=index % 15,
            review_item_id=UUID(int=index + 1),
        )
        for index in range(501)
    )
    repository = MemorySymbolCellReviewRepository(
        game_id=game_id,
        symbol_id=symbol_id,
        items=items,
    )

    with _client(repository, artifact_root=tmp_path) as client:
        response = client.get(
            f"/api/v1/admin/games/{game_id}/symbol-cell-reviews",
            params={"symbolId": str(symbol_id), "limit": 501},
        )

    assert response.status_code == 422
    assert repository.limits == []


def test_list_endpoint_binds_confidence_filter_to_keyset_cursor(tmp_path: Path) -> None:
    game_id, symbol_id = uuid4(), uuid4()
    items = tuple(
        _item(
            game_id=game_id,
            symbol_id=symbol_id,
            sequence_number=index,
            cell_index=0,
            prediction_confidence=confidence,
            review_item_id=UUID(int=index),
        )
        for index, confidence in ((1, 0.2), (2, 0.55), (3, 0.65), (4, 0.95))
    )
    repository = MemorySymbolCellReviewRepository(
        game_id=game_id,
        symbol_id=symbol_id,
        items=items,
    )

    with _client(repository, artifact_root=tmp_path) as client:
        first = client.get(
            f"/api/v1/admin/games/{game_id}/symbol-cell-reviews",
            params={
                "symbolId": str(symbol_id),
                "limit": 1,
                "minConfidence": 0.5,
                "maxConfidence": 0.8,
            },
        )
        invalid_scope = client.get(
            f"/api/v1/admin/games/{game_id}/symbol-cell-reviews",
            params={
                "symbolId": str(symbol_id),
                "afterCursor": first.json()["nextCursor"],
                "minConfidence": 0.8,
            },
        )

    assert first.status_code == 200
    assert [item["sequenceNumber"] for item in first.json()["items"]] == [2]
    assert first.json()["items"][0]["predictionConfidence"] == 0.55
    assert invalid_scope.status_code == 409
    assert invalid_scope.json()["code"] == "SYMBOL_CELL_REVIEW_CURSOR_SCOPE_INVALID"


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
    assert unknown_response.json()["items"][0]["isUnknown"] is True
    assert unknown_response.json()["items"][0]["qualityIssue"] is None
    assert unknown_response.json()["items"][0]["cropApprovalState"] == "unverified"
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
    crop = tmp_path / "data" / "crops" / "cell.png"
    crop.parent.mkdir(parents=True)
    Image.new("RGB", (420, 260), color=(180, 10, 30)).save(crop, format="PNG")
    content = crop.read_bytes()
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
        atlas_batch = client.post(
            f"/api/v1/admin/games/{game_id}/symbol-cell-preview-batches",
            json={
                "previewSize": 100,
                "cells": [
                    {
                        "cellReviewId": str(item.cell_review_id),
                        "expectedRevision": asset.revision,
                        "expectedCropChecksumSha256": checksum,
                    }
                ],
            },
        )
        atlas = client.get(atlas_batch.json()["atlasUrl"])
        crop.write_bytes(b"changed")
        changed_file = client.get(
            f"/api/v1/admin/games/{game_id}/symbol-cell-reviews/{item.cell_review_id}/asset",
            params={"expectedCropChecksumSha256": checksum},
        )

    assert success.status_code == 200
    assert success.headers["content-type"] == "image/webp"
    assert success.headers["cache-control"] == "private, immutable, max-age=31536000"
    with Image.open(BytesIO(success.content)) as thumbnail:
        assert thumbnail.width <= 100
        assert thumbnail.height <= 100
    assert len(success.content) < len(content)
    assert stale.status_code == 409
    assert stale.json()["code"] == "SYMBOL_CELL_REVIEW_CROP_DRIFT"
    assert changed_file.status_code == 409
    assert changed_file.json()["code"] == "SYMBOL_CELL_REVIEW_ASSET_CHECKSUM_MISMATCH"
    assert atlas_batch.status_code == 200
    assert atlas_batch.json()["rendererMode"] == "current"
    assert atlas_batch.json()["rendererVersion"] == "symbol-review-current-crop-renderer-v1"
    assert atlas_batch.json()["availableCount"] == 1
    assert atlas_batch.json()["unavailableCellReviewIds"] == []
    assert atlas.headers["cache-control"] == "private, immutable, max-age=31536000"


def test_structured_v0_10_preview_never_falls_back_to_a_legacy_crop(tmp_path: Path) -> None:
    crop = tmp_path / "data" / "crops" / "legacy.png"
    crop.parent.mkdir(parents=True)
    Image.new("RGB", (90, 70), color=(90, 40, 10)).save(crop, format="PNG")
    checksum = hashlib.sha256(crop.read_bytes()).hexdigest()
    game_id, symbol_id = uuid4(), uuid4()
    item = _item(
        game_id=game_id,
        symbol_id=symbol_id,
        sequence_number=1,
        cell_index=0,
        review_item_id=UUID(int=1),
    )
    repository = MemorySymbolCellReviewRepository(
        game_id=game_id,
        symbol_id=symbol_id,
        items=(item,),
        asset=SymbolCellReviewAsset(
            cell_review_id=item.cell_review_id,
            crop_relative_path="data/crops/legacy.png",
            crop_checksum_sha256=checksum,
            geometry_revision=0,
            current_geometry_revision=0,
        ),
    )

    with _client(repository, artifact_root=tmp_path) as client:
        response = client.post(
            f"/api/v1/admin/games/{game_id}/symbol-cell-preview-batches",
            json={
                "rendererMode": "structured_v0_10",
                "cells": [
                    {
                        "cellReviewId": str(item.cell_review_id),
                        "expectedRevision": 0,
                        "expectedCropChecksumSha256": checksum,
                    }
                ],
            },
        )

    assert response.status_code == 200
    assert response.json()["rendererMode"] == "structured_v0_10"
    assert response.json()["rendererVersion"] == "symbol-review-structured-v0.10-renderer-v1"
    assert response.json()["availableCount"] == 0
    assert response.json()["batchKey"] is None
    assert response.json()["atlasUrl"] is None
    assert response.json()["tiles"] == []
    assert response.json()["unavailableCellReviewIds"] == [str(item.cell_review_id)]


def test_virtual_preview_batch_endpoint_uses_current_render_provenance(tmp_path: Path) -> None:
    game_id, symbol_id = uuid4(), uuid4()
    item = _item(
        game_id=game_id,
        symbol_id=symbol_id,
        sequence_number=1,
        cell_index=0,
        review_item_id=UUID(int=1),
    )
    asset = _virtual_source_asset(tmp_path, cell_review_id=item.cell_review_id)
    repository = MemorySymbolCellReviewRepository(
        game_id=game_id,
        symbol_id=symbol_id,
        items=(item,),
        asset=asset,
    )
    body = {
        "previewSize": 80,
        "cells": [
            {
                "cellReviewId": str(item.cell_review_id),
                "expectedRevision": asset.revision,
                "expectedRenderSpecChecksumSha256": asset.render_spec_checksum_sha256,
            }
        ],
    }

    with _client(repository, artifact_root=tmp_path) as client:
        created = client.post(
            f"/api/v1/admin/games/{game_id}/virtual-cell-preview-batches",
            json=body,
        )
        atlas = client.get(created.json()["atlasUrl"])
        legacy_route = client.get(
            f"/api/v1/admin/games/{game_id}/symbol-cell-reviews/{item.cell_review_id}/asset",
            params={
                "expectedCropChecksumSha256": asset.crop_checksum_sha256,
                "expectedRenderSpecChecksumSha256": asset.render_spec_checksum_sha256,
            },
        )
        stale = client.post(
            f"/api/v1/admin/games/{game_id}/virtual-cell-preview-batches",
            json={
                **body,
                "cells": [{**body["cells"][0], "expectedRevision": asset.revision + 1}],
            },
        )
        shared = client.post(
            f"/api/v1/admin/games/{game_id}/symbol-cell-preview-batches",
            json={
                "previewSize": 80,
                "cells": [
                    {
                        "cellReviewId": str(item.cell_review_id),
                        "expectedRevision": asset.revision,
                        "expectedCropChecksumSha256": asset.crop_checksum_sha256,
                        "expectedRenderSpecChecksumSha256": (asset.render_spec_checksum_sha256),
                    }
                ],
            },
        )
        shared_atlas = client.get(shared.json()["atlasUrl"])
        experimental = client.post(
            f"/api/v1/admin/games/{game_id}/symbol-cell-preview-batches",
            json={
                "rendererMode": "structured_v0_10",
                "previewSize": 80,
                "cells": [
                    {
                        "cellReviewId": str(item.cell_review_id),
                        "expectedRevision": asset.revision,
                        "expectedCropChecksumSha256": asset.crop_checksum_sha256,
                        "expectedRenderSpecChecksumSha256": (asset.render_spec_checksum_sha256),
                    }
                ],
            },
        )

    assert created.status_code == 200
    assert created.json()["tiles"] == [
        {
            "cellReviewId": str(item.cell_review_id),
            "x": 0,
            "y": 0,
            "width": 80,
            "height": 80,
        }
    ]
    assert atlas.status_code == 200
    assert atlas.headers["content-type"] == "image/webp"
    assert atlas.headers["cache-control"] == "private, max-age=900, must-revalidate"
    assert legacy_route.status_code == 200
    assert legacy_route.headers["content-type"] == "image/webp"
    assert stale.status_code == 409
    assert stale.json()["code"] == "SYMBOL_CELL_REVIEW_CROP_DRIFT"
    assert shared.status_code == 200
    assert shared_atlas.headers["cache-control"] == ("private, immutable, max-age=31536000")
    assert experimental.status_code == 200
    assert experimental.json()["availableCount"] == 1
    assert experimental.json()["rendererMode"] == "structured_v0_10"
    assert (
        experimental.json()["rendererFingerprintSha256"]
        != shared.json()["rendererFingerprintSha256"]
    )


def test_single_cell_decision_applies_directly_without_bulk_job(tmp_path: Path) -> None:
    game_id, source_symbol_id, target_symbol_id = uuid4(), uuid4(), uuid4()
    item = _item(
        game_id=game_id,
        symbol_id=source_symbol_id,
        sequence_number=10,
        cell_index=4,
        review_item_id=UUID(int=1),
    )
    reviews = MemorySymbolCellReviewRepository(
        game_id=game_id,
        symbol_id=source_symbol_id,
        items=(item,),
    )
    mutations = MemorySymbolCellReviewMutationRepository()

    with _client(
        reviews,
        artifact_root=tmp_path,
        mutation_repository=mutations,
    ) as client:
        response = client.post(
            f"/api/v1/admin/games/{game_id}/symbol-cell-reviews/{item.cell_review_id}/decision",
            json={
                "action": "reassign",
                "expectedRevision": item.revision,
                "expectedGeometryRevision": item.geometry_revision,
                "expectedCropSampleId": item.crop_sample_id,
                "expectedCropChecksumSha256": item.crop_checksum_sha256,
                "targetSymbolId": str(target_symbol_id),
            },
        )

    assert response.status_code == 200
    assert response.json()["cellReviewId"] == str(item.cell_review_id)
    assert response.json()["assignedSymbolId"] == str(target_symbol_id)
    assert response.json()["cellRevision"] == item.revision + 1
    assert len(mutations.commands) == 1
    assert mutations.commands[0].actor == "local-admin"
    assert mutations.commands[0].target_symbol_id == target_symbol_id


def test_single_cell_decision_routes_mark_unreadable_without_unknown_assignment(
    tmp_path: Path,
) -> None:
    game_id, symbol_id = uuid4(), uuid4()
    item = _item(
        game_id=game_id,
        symbol_id=symbol_id,
        sequence_number=10,
        cell_index=4,
        review_item_id=UUID(int=1),
    )
    reviews = MemorySymbolCellReviewRepository(
        game_id=game_id,
        symbol_id=symbol_id,
        items=(item,),
    )
    mutations = MemorySymbolCellReviewMutationRepository()

    with _client(
        reviews,
        artifact_root=tmp_path,
        mutation_repository=mutations,
    ) as client:
        response = client.post(
            f"/api/v1/admin/games/{game_id}/symbol-cell-reviews/{item.cell_review_id}/decision",
            json={
                "action": "mark_unreadable",
                "expectedRevision": item.revision,
                "expectedGeometryRevision": item.geometry_revision,
                "expectedCropSampleId": item.crop_sample_id,
                "expectedCropChecksumSha256": item.crop_checksum_sha256,
            },
        )

    assert response.status_code == 200
    assert response.json()["qualityIssue"] == "unreadable"
    assert mutations.commands[0].action.value == "mark_unreadable"
    assert mutations.commands[0].target_symbol_id is None


def test_single_cell_decision_returns_conflict_for_stale_revision(tmp_path: Path) -> None:
    game_id, source_symbol_id, target_symbol_id = uuid4(), uuid4(), uuid4()
    item = _item(
        game_id=game_id,
        symbol_id=source_symbol_id,
        sequence_number=10,
        cell_index=4,
        review_item_id=UUID(int=1),
    )
    reviews = MemorySymbolCellReviewRepository(
        game_id=game_id,
        symbol_id=source_symbol_id,
        items=(item,),
    )
    mutations = MemorySymbolCellReviewMutationRepository(
        error=SymbolCellReviewError(
            "SYMBOL_CELL_REVIEW_REVISION_CONFLICT",
            "The symbol-cell review changed after it was loaded.",
        )
    )

    with _client(
        reviews,
        artifact_root=tmp_path,
        mutation_repository=mutations,
    ) as client:
        response = client.post(
            f"/api/v1/admin/games/{game_id}/symbol-cell-reviews/{item.cell_review_id}/decision",
            json={
                "action": "reassign",
                "expectedRevision": item.revision,
                "expectedGeometryRevision": item.geometry_revision,
                "expectedCropSampleId": item.crop_sample_id,
                "expectedCropChecksumSha256": item.crop_checksum_sha256,
                "targetSymbolId": str(target_symbol_id),
            },
        )

    assert response.status_code == 409
    assert response.json()["code"] == "SYMBOL_CELL_REVIEW_REVISION_CONFLICT"


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
            "minConfidence": 0.5,
            "maxConfidence": 0.8,
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
    selection = bulk.requests[0].filter_selection
    assert selection is not None
    assert selection.min_confidence == 0.5
    assert selection.max_confidence == 0.8


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


def test_bulk_operation_accepts_mark_unreadable_action(tmp_path: Path) -> None:
    game_id, symbol_id = uuid4(), uuid4()
    item = _item(
        game_id=game_id,
        symbol_id=symbol_id,
        sequence_number=10,
        cell_index=4,
        review_item_id=UUID(int=1),
    )
    reviews = MemorySymbolCellReviewRepository(
        game_id=game_id,
        symbol_id=symbol_id,
        items=(item,),
    )
    bulk = MemorySymbolCellReviewBulkRepository(game_id=game_id)

    with _client(reviews, artifact_root=tmp_path, bulk_repository=bulk) as client:
        response = client.post(
            f"/api/v1/admin/games/{game_id}/symbol-cell-review-operations/preview",
            json={
                "action": "mark_unreadable",
                "selection": {
                    "kind": "explicit",
                    "targets": [
                        {
                            "cellReviewId": str(item.cell_review_id),
                            "expectedRevision": item.revision,
                            "expectedGeometryRevision": item.geometry_revision,
                            "expectedCropSampleId": item.crop_sample_id,
                            "expectedCropChecksumSha256": item.crop_checksum_sha256,
                        }
                    ],
                },
            },
        )

    assert response.status_code == 200
    assert response.json()["action"] == "mark_unreadable"
    assert bulk.requests[0].action.value == "mark_unreadable"
