from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from game_predictor_api.api.image_grid_reviews import create_image_grid_reviews_router
from game_predictor_api.application.image_geometry_rollout import (
    ImageGeometryRolloutService,
    ImageGeometryRolloutStart,
    ImageGeometryRolloutStatus,
)
from game_predictor_api.application.image_grid_reviews import (
    ImageGridReviewListSlice,
    ImageGridReviewRepository,
    ImageGridReviewService,
)
from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.image_grid_reviews import (
    ImageGridReviewCounts,
    ImageGridReviewError,
    ImageGridReviewListFilter,
    ImageGridReviewListItem,
    ImageGridReviewSlotKind,
    ImageGridReviewSourceAsset,
    ImageGridReviewState,
    ImageGridReviewView,
)
from game_predictor_api.domain.image_import_engine_policy import (
    ImageImportEnginePolicy,
    ImageImportEnginePolicyPreview,
    ImageImportEnginePolicySnapshot,
    engine_policy_preview_token,
    policy_rollout_modes,
)
from game_predictor_api.domain.image_reviews import (
    ImageReviewGeometryCellArtifact,
    ImageReviewGeometryPoint,
    ImageReviewGeometryRevision,
)
from game_predictor_api.domain.jobs import Job, JobType, create_job
from game_predictor_api.schemas.image_grid_reviews import (
    to_image_grid_review_counts_response,
    to_image_grid_review_geometry_response,
    to_image_grid_review_item_response,
)
from game_predictor_api.storage.game_storage_routing import current_game_storage_scope
from game_predictor_api.storage.image_grid_review_repository import (
    SqlAlchemyImageGridReviewRepository,
    _confirmed_partial_expression,
    _pending_automatic_proposal_expression,
)
from game_predictor_worker.images.lateral_partial_contract import (
    LateralPartialGeometrySnapshot,
)
from sqlalchemy.dialects import postgresql

SOURCE_BYTES = b"source"
SHA = hashlib.sha256(SOURCE_BYTES).hexdigest()


def test_counts_separate_automatic_partial_validation_from_manual_correction() -> None:
    response = to_image_grid_review_counts_response(
        ImageGridReviewCounts(
            needs_validation=2,
            needs_correction=1,
            approved=2,
            full_grids=2,
            lateral_partial_proposals=1,
            confirmed_partial_grids=1,
        )
    )

    assert response.full_grids == 2
    assert response.lateral_partial_proposals == 1
    assert response.confirmed_partial_grids == 1
    assert response.manual_correction == 1


def test_pending_automatic_proposal_sql_requires_metadata_and_four_corner_grid() -> None:
    sql = str(
        _pending_automatic_proposal_expression().compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "automaticPartialProposal" in sql
    assert "automaticFrameProposal" in sql
    assert "symbolGridQuad" in sql
    assert "jsonb_array_length" in sql
    assert "CASE WHEN" in sql


def test_confirmed_partial_sql_uses_mask_and_persisted_qualification() -> None:
    sql = str(
        _confirmed_partial_expression().compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "completeness_status" in sql
    assert "unavailable_cell_indices" in sql
    assert "geometry_qualification" in sql
    assert "completenessStatus" in sql


class MemoryGridReviewRepository(ImageGridReviewRepository):
    def __init__(self, items: tuple[ImageGridReviewListItem, ...], source_path: str) -> None:
        self.items = items
        self.source_path = source_path

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
            and (
                review_filter.view.value == "all"
                or item.state.value == review_filter.view.value
                or (
                    review_filter.view.value == "correction"
                    and item.state is ImageGridReviewState.NEEDS_CORRECTION
                )
            )
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
            correction=sum(item.state is ImageGridReviewState.NEEDS_CORRECTION for item in items),
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
            source_image_id=item.source_image_id,
            source_relative_path=self.source_path,
            source_checksum_sha256=item.source_checksum_sha256,
            source_width=item.source_width,
            source_height=item.source_height,
            geometry_revision=item.geometry_revision,
            resolution_revision=item.resolution_revision,
            topology=item.topology,
        )


class UnusedOperationalService:
    pass


class MemoryImageGeometryRolloutRepository:
    def __init__(self, game_id: UUID) -> None:
        self.game_id = game_id
        self.job: Job | None = None
        self.policy = ImageImportEnginePolicy.STRUCTURED_LATTICE_V3
        self.revision = 0

    def engine_policy(self, game_id: UUID) -> ImageImportEnginePolicySnapshot:
        assert game_id == self.game_id
        geometry, assets = policy_rollout_modes(self.policy)
        return ImageImportEnginePolicySnapshot(
            game_id, self.policy, geometry, assets, self.revision
        )

    def preview_engine_policy(
        self, game_id: UUID, *, target: ImageImportEnginePolicy
    ) -> ImageImportEnginePolicyPreview:
        current = self.engine_policy(game_id)
        geometry, assets = policy_rollout_modes(target)
        return ImageImportEnginePolicyPreview(
            current=current,
            target=ImageImportEnginePolicySnapshot(
                game_id, target, geometry, assets, self.revision + int(target is not self.policy)
            ),
            preview_token=engine_policy_preview_token(
                game_id=game_id,
                current_revision=self.revision,
                current_geometry_mode=current.geometry_mode,
                current_cell_asset_mode=current.cell_asset_mode,
                target_policy=target,
            ),
        )

    def apply_engine_policy(
        self,
        game_id: UUID,
        *,
        target: ImageImportEnginePolicy,
        expected_revision: int,
        preview_token: str,
    ) -> ImageImportEnginePolicySnapshot:
        preview = self.preview_engine_policy(game_id, target=target)
        assert expected_revision == self.revision
        assert preview_token == preview.preview_token
        if target is not self.policy:
            self.policy = target
            self.revision += 1
        return self.engine_policy(game_id)

    def status(self, game_id: UUID) -> ImageGeometryRolloutStatus:
        assert game_id == self.game_id
        return ImageGeometryRolloutStatus(
            game_id=game_id,
            geometry_mode="structured_review",
            cell_asset_mode="virtual_source",
            rollout_revision=1,
            backfill_status="processing" if self.job is not None else "not_started",
            source_count=100,
            processed_source_count=0,
            virtual_source_count=0,
            active_job_id=None if self.job is None else self.job.id,
            last_source_image_id=None,
            failure_code=None,
            failure_message=None,
        )

    def start(self, game_id: UUID) -> ImageGeometryRolloutStart:
        assert game_id == self.game_id
        created = self.job is None
        if self.job is None:
            self.job = create_job(
                JobType.IMAGE_GEOMETRY_ROLLOUT_BACKFILL,
                game_id=game_id,
                input_payload={
                    "schema_version": 1,
                    "workflow": "image_geometry_rollout_backfill",
                    "generation": 1,
                    "rollout_revision": 1,
                    "geometry_mode": "structured_review",
                    "cell_asset_mode": "virtual_source",
                },
            )
        return ImageGeometryRolloutStart(
            rollout=self.status(game_id),
            job=self.job,
            created=created,
        )


def _item(
    game_id: UUID,
    import_job_id: UUID,
    sequence_number: int,
    state: ImageGridReviewState,
    *,
    source_image_id: UUID | None = None,
    position_index: int = 0,
) -> ImageGridReviewListItem:
    review_item_id = uuid4()
    return ImageGridReviewListItem(
        slot_id=review_item_id,
        slot_kind=ImageGridReviewSlotKind.CURRENT_REVIEW,
        review_item_id=review_item_id,
        game_id=game_id,
        import_job_id=import_job_id,
        recognized_board_id=uuid4(),
        pending_geometry_id=None,
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
    rollout_repository = MemoryImageGeometryRolloutRepository(game_id)
    app = FastAPI()
    app.include_router(
        create_image_grid_reviews_router(
            lambda: ImageGridReviewService(repository),
            lambda: UnusedOperationalService(),
            lambda: ImageGeometryRolloutService(rollout_repository),
            lambda: UnusedOperationalService(),
            tmp_path,
        ),
        prefix="/api/v1",
    )

    @app.exception_handler(ImageGridReviewError)
    async def handle_error(_request: Request, error: ImageGridReviewError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"code": error.code, "message": error.message})

    return TestClient(app), repository, items


def test_grid_review_response_exposes_explicit_geometry_roles() -> None:
    analysis = [
        {"x": 1, "y": 1},
        {"x": 101, "y": 1},
        {"x": 101, "y": 81},
        {"x": 1, "y": 81},
    ]
    lattice = [
        {"x": 5, "y": 6},
        {"x": 97, "y": 6},
        {"x": 97, "y": 75},
        {"x": 5, "y": 75},
    ]
    item = _item(uuid4(), uuid4(), 1, ImageGridReviewState.NEEDS_VALIDATION)
    item = replace(
        item,
        geometry={
            "analysisQuad": analysis,
            "boardFrameQuad": analysis,
            "symbolGridQuad": lattice,
            "localLatticeStatus": "estimated",
            "localLatticeVersion": "lattice-test-v1",
        },
    )

    response = to_image_grid_review_item_response(item)

    assert response.analysis_quad is not None
    assert response.analysis_quad[0].x == 1
    assert response.symbol_grid_quad is not None
    assert response.symbol_grid_quad[0].x == 5
    assert response.local_lattice_status == "estimated"
    assert response.local_lattice_version == "lattice-test-v1"


def test_grid_review_response_does_not_replace_explicitly_deferred_lattice_with_frame() -> None:
    frame = [
        {"x": 1, "y": 1},
        {"x": 101, "y": 1},
        {"x": 101, "y": 81},
        {"x": 1, "y": 81},
    ]
    item = _item(uuid4(), uuid4(), 1, ImageGridReviewState.NEEDS_VALIDATION)
    item = replace(
        item,
        geometry={
            "quad": frame,
            "analysisQuad": frame,
            "symbolGridQuad": None,
            "localLatticeStatus": "needs_review",
            "localLatticeVersion": "lattice-test-v1",
        },
    )

    response = to_image_grid_review_item_response(item)

    assert response.analysis_quad is not None
    assert response.symbol_grid_quad is None


def test_grid_review_response_exposes_unconfirmed_selective_draft() -> None:
    draft = [
        {"x": 5, "y": 6},
        {"x": 97, "y": 6},
        {"x": 97, "y": 75},
        {"x": 5, "y": 75},
    ]
    item = replace(
        _item(uuid4(), uuid4(), 1, ImageGridReviewState.NEEDS_CORRECTION),
        geometry_revision=0,
        geometry={
            "reviewDraftQuad": draft,
            "reviewDraftOrigin": "page_projection_confident_neighbors_v1",
            "reviewUncertaintyReason": "local_symbol_grid_unavailable",
            "symbolGridQuad": None,
            "manualGeometryRequired": True,
        },
    )
    response = to_image_grid_review_item_response(item)
    assert response.review_draft_quad is not None
    assert response.review_draft_quad[0].x == 5
    assert response.review_draft_origin == "page_projection_confident_neighbors_v1"
    assert response.review_uncertainty_reason == "local_symbol_grid_unavailable"
    assert response.symbol_grid_quad is None


def test_grid_review_response_exposes_complete_weak_frame_proposal() -> None:
    lattice = [
        {"x": 5, "y": 6},
        {"x": 97, "y": 6},
        {"x": 97, "y": 75},
        {"x": 5, "y": 75},
    ]
    policy = LateralPartialGeometrySnapshot(frame_support_review=True)
    qualification = {
        "version": "manual-geometry-qualification-v2",
        "completenessStatus": "complete",
        "unavailableCellIndices": [],
        "excludeFromGeometryTraining": True,
        "exclusionReason": "manual_exclusion",
        "includeInPartialGridTraining": False,
    }
    item = replace(
        _item(uuid4(), uuid4(), 1, ImageGridReviewState.NEEDS_VALIDATION),
        geometry_revision=0,
        geometry={
            "analysisQuad": lattice,
            "symbolGridQuad": lattice,
            "localLatticeStatus": "pending_review",
            "localLatticeVersion": policy.policy_version,
            "automaticFrameProposal": {
                "version": "automatic-frame-geometry-proposal-v1",
                "origin": "automatic_proposal",
                "sourceChecksumSha256": SHA,
                "positionIndex": 1,
                "policyVersion": policy.policy_version,
                "policyChecksumSha256": policy.checksum_sha256,
                "requiresManualConfirmation": True,
                "reasonCode": "board_frame_support_incomplete",
                "geometryQualification": qualification,
            },
        },
    )

    response = to_image_grid_review_item_response(item)

    assert response.symbol_grid_quad is not None
    assert response.automatic_frame_proposal is not None
    assert response.automatic_frame_proposal.requires_manual_confirmation is True
    assert (
        response.automatic_frame_proposal.geometry_qualification.completeness_status == "complete"
    )


def test_geometry_rollout_start_is_idempotent_and_reports_progress(tmp_path: Path) -> None:
    client, _repository, items = _client(tmp_path)
    endpoint = f"/api/v1/admin/games/{items[0].game_id}/image-geometry-rollout"

    initial = client.get(endpoint)
    first = client.post(endpoint)
    second = client.post(endpoint)

    assert initial.status_code == 200
    assert initial.json()["backfillStatus"] == "not_started"
    assert initial.json()["sourceCount"] == 100
    assert first.status_code == 202
    assert first.json()["created"] is True
    assert first.json()["job"]["jobType"] == "image_geometry_rollout_backfill"
    assert second.status_code == 202
    assert second.json()["created"] is False
    assert second.json()["job"]["id"] == first.json()["job"]["id"]


def test_image_import_engine_policy_requires_preview_and_is_per_game(tmp_path: Path) -> None:
    client, _repository, items = _client(tmp_path)
    endpoint = f"/api/v1/admin/games/{items[0].game_id}/image-import-engine-policy"

    current = client.get(endpoint)
    # D-467 (TASK-0790): the removed legacy policies are refused explicitly.
    legacy_previews = [
        client.post(f"{endpoint}/preview", json={"targetPolicy": removed})
        for removed in ("verified_v19", "structured_shadow")
    ]
    legacy_update = client.put(
        endpoint,
        json={
            "targetPolicy": "verified_v19",
            "expectedRevision": 0,
            "previewToken": "a" * 64,
        },
    )

    assert current.json()["policy"] == "structured_lattice_v3"
    assert current.json()["geometryEngineVariants"] == [
        {
            "variant": "structured_lattice_v4_partial_sides",
            "label": "v1.0 — niepełne boki",
            "enabled": True,
            "blockerCode": None,
            "blockerMessage": None,
        },
        {
            "variant": "selective_board_review_v1_1",
            "label": "v1.1 — korekta plansz",
            "enabled": True,
            "blockerCode": None,
            "blockerMessage": None,
        },
        {
            "variant": "contrast_frame_grid_v1_2",
            "label": "v1.2 — kontrastowa ramka i siatka (test)",
            "enabled": True,
            "blockerCode": None,
            "blockerMessage": None,
        },
    ]
    for response in (*legacy_previews, legacy_update):
        assert response.status_code == 422
        assert [error["type"] for error in response.json()["detail"]] == [
            "IMAGE_ENGINE_POLICY_LEGACY_UNSUPPORTED"
        ]

    production_preview = client.post(
        f"{endpoint}/preview", json={"targetPolicy": "structured_default"}
    )
    production = client.put(
        endpoint,
        json={
            "targetPolicy": "structured_default",
            "expectedRevision": 0,
            "previewToken": production_preview.json()["previewToken"],
        },
    )

    assert production_preview.status_code == 200
    assert production_preview.json()["changesExistingJobs"] is False
    assert production_preview.json()["target"]["geometryMode"] == "structured_default"
    assert production_preview.json()["target"]["cellAssetMode"] == "virtual_default"
    assert production.status_code == 200
    assert production.json()["policy"] == "structured_default"
    assert production.json()["revision"] == 1

    v3_preview = client.post(f"{endpoint}/preview", json={"targetPolicy": "structured_lattice_v3"})
    v3 = client.put(
        endpoint,
        json={
            "targetPolicy": "structured_lattice_v3",
            "expectedRevision": 1,
            "previewToken": v3_preview.json()["previewToken"],
        },
    )

    assert v3_preview.status_code == 200
    assert v3_preview.json()["target"]["geometryMode"] == "structured_lattice_v3"
    assert v3_preview.json()["changesExistingJobs"] is False
    assert v3.status_code == 200
    assert v3.json()["policy"] == "structured_lattice_v3"
    assert v3.json()["revision"] == 2


def test_grid_review_api_lists_keyset_page_and_serves_the_source(tmp_path: Path) -> None:
    client, _repository, items = _client(tmp_path)
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
        "fullGrids": 2,
        "lateralPartialProposals": 0,
        "confirmedPartialGrids": 0,
        "manualCorrection": 1,
        "correction": 1,
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
    asset = client.get(
        f"/api/v1/admin/image-reviews/{target.review_item_id}/source-asset",
        params={
            "gameId": str(target.game_id),
            "expectedSourceChecksumSha256": target.source_checksum_sha256,
        },
    )
    assert asset.status_code == 200
    assert asset.content == SOURCE_BYTES


def test_grid_review_read_paths_filter_the_import_and_serve_the_source(
    tmp_path: Path,
) -> None:
    client, repository, items = _client(tmp_path)
    target = replace(items[0], source_image_id=uuid4())
    repository.items = (target,)

    listing = client.get(
        f"/api/v1/admin/games/{target.game_id}/grid-reviews",
        params={"view": "all", "importJobId": str(target.import_job_id), "limit": 1},
    )
    asset = client.get(
        f"/api/v1/admin/image-reviews/{target.review_item_id}/source-asset",
        params={
            "gameId": str(target.game_id),
            "expectedSourceChecksumSha256": target.source_checksum_sha256,
        },
    )
    assert listing.status_code == 200
    assert [item["importJobId"] for item in listing.json()["items"]] == [str(target.import_job_id)]
    assert asset.status_code == 200
    assert asset.content == SOURCE_BYTES


def test_grid_approval_and_whole_source_save_paths_are_removed(tmp_path: Path) -> None:
    """D-462 / TASK-0727: no board, photo or whole-source approval exists."""

    client, _repository, items = _client(tmp_path)
    target = items[0]
    removed = (
        f"/api/v1/admin/image-reviews/{target.review_item_id}/geometry-approval"
        f"?gameId={target.game_id}",
        f"/api/v1/admin/games/{target.game_id}/grid-reviews/source-geometry-approval",
        f"/api/v1/admin/games/{target.game_id}/grid-reviews/source-geometry-revisions"
        f"?importJobId={target.import_job_id}",
    )
    for path in removed:
        assert client.post(path, json={}).status_code in {404, 405}, path


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


def test_item_scoped_grid_review_routes_bind_the_query_game_storage(tmp_path: Path) -> None:
    """Regression for TASK-0637 / D-442.

    Routes under `/image-reviews/{review_item_id}/...` carry `gameId` only in
    the query string, so the storage-routing middleware (path-based) never
    binds `game_storage_scope`. Every repository call these routes make must
    observe an active scope for the query game, otherwise a fresh session
    would silently fall back to the `public` schema for V2 games.
    """

    client, repository, items = _client(tmp_path)
    target = items[0]

    observed_scopes: list[object] = []
    original_require_game = repository.require_game
    original_get_source_asset = repository.get_grid_review_source_asset

    def require_game(game_id: UUID) -> None:
        observed_scopes.append(current_game_storage_scope())
        original_require_game(game_id)

    def get_grid_review_source_asset(
        *, game_id: UUID, review_item_id: UUID
    ) -> ImageGridReviewSourceAsset | None:
        observed_scopes.append(current_game_storage_scope())
        return original_get_source_asset(game_id=game_id, review_item_id=review_item_id)

    repository.require_game = require_game  # type: ignore[method-assign]
    repository.get_grid_review_source_asset = get_grid_review_source_asset  # type: ignore[method-assign]

    corners = [{"x": 0, "y": 0}, {"x": 100, "y": 0}, {"x": 100, "y": 100}, {"x": 0, "y": 100}]

    asset = client.get(
        f"/api/v1/admin/image-reviews/{target.review_item_id}/source-asset",
        params={
            "gameId": str(target.game_id),
            "expectedSourceChecksumSha256": target.source_checksum_sha256,
        },
    )
    assert asset.status_code == 200

    # Mismatched expected width forces a deterministic 409 (SOURCE_DRIFT)
    # right after the source lookup, without reaching the geometry engines
    # (which this fixture does not wire up) — scope is already observed by
    # that point.
    preview = client.post(
        f"/api/v1/admin/image-reviews/{target.review_item_id}/geometry-preview",
        params={"gameId": str(target.game_id), "importJobId": str(target.import_job_id)},
        json={
            "expectedGeometryRevision": target.geometry_revision,
            "expectedResolutionRevision": target.resolution_revision,
            "corners": corners,
            "expectedSourceChecksumSha256": target.source_checksum_sha256,
            "expectedSourceWidth": target.source_width + 1,
            "expectedSourceHeight": target.source_height,
            "expectedGridRows": target.topology.rows,
            "expectedGridColumns": target.topology.columns,
        },
    )
    assert preview.status_code == 409
    assert preview.json()["code"] == "IMAGE_GRID_REVIEW_SOURCE_DRIFT"

    revision = client.post(
        f"/api/v1/admin/image-reviews/{target.review_item_id}/geometry-revisions",
        params={"gameId": str(target.game_id), "importJobId": str(target.import_job_id)},
        json={
            "idempotencyKey": str(uuid4()),
            "expectedGeometryRevision": target.geometry_revision,
            "expectedResolutionRevision": target.resolution_revision,
            "corners": corners,
            "expectedSourceChecksumSha256": target.source_checksum_sha256,
            "expectedSourceWidth": target.source_width + 1,
            "expectedSourceHeight": target.source_height,
            "expectedGridRows": target.topology.rows,
            "expectedGridColumns": target.topology.columns,
        },
    )
    assert revision.status_code == 409
    assert revision.json()["code"] == "IMAGE_GRID_REVIEW_SOURCE_DRIFT"

    assert len(observed_scopes) == 6
    assert all(scope is not None for scope in observed_scopes)
    assert all(scope.game_id == target.game_id for scope in observed_scopes)  # type: ignore[union-attr]


def test_correction_view_lists_reported_boards_with_their_cells(tmp_path: Path) -> None:
    client, repository, items = _client(tmp_path)
    repository.items = tuple(
        replace(item, reported_cell_indices=(2, 7))
        if item.state is ImageGridReviewState.NEEDS_CORRECTION
        else item
        for item in items
    )

    page = client.get(
        f"/api/v1/admin/games/{items[0].game_id}/grid-reviews",
        params={"view": "correction", "limit": 1},
    )

    # D-462 R4: one queue for manual correction, naming the reported cells.
    assert page.status_code == 200
    assert page.json()["view"] == "correction"
    assert [item["sequenceNumber"] for item in page.json()["items"]] == [3]
    assert page.json()["items"][0]["reportedCellIndices"] == [2, 7]
    assert page.json()["counts"]["correction"] == 1


def test_correction_view_sql_keeps_one_entry_per_board_slot() -> None:
    session = MagicMock()
    repository = SqlAlchemyImageGridReviewRepository(session)
    correction = ImageGridReviewListFilter(
        game_id=uuid4(),
        view=ImageGridReviewView.CORRECTION,
        import_job_id=None,
    )
    current_sql = str(
        repository._visible_statement(review_filter=correction).compile(
            dialect=postgresql.dialect()
        )
    ).lower()
    pending_sql = str(
        repository._pending_statement(review_filter=correction).compile(
            dialect=postgresql.dialect()
        )
    ).lower()

    # A reported board is listed; a deferred slot only while no live board
    # owns it, with or without an automatic proposal (D-462 R4).
    assert "image_symbol_review_cells.quality_issue" in current_sql
    assert "not (exists" in pending_sql
    assert "recognized_boards.source_image_id = image_board_geometry_pending.source_image_id" in (
        pending_sql
    )
    assert "recognized_boards.position_index = image_board_geometry_pending.position_index" in (
        pending_sql
    )
    assert "automaticpartialproposal" not in pending_sql
