"""Bounded shadow starts, durable request replay and read-only result views."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from game_predictor_api.domain.catalog import GameShapeGeometryConfiguration
from game_predictor_api.domain.grid_engine_profiles import (
    GridEngineModelError,
    GridEngineModelVersion,
    grid_engine_manifest,
    grid_engine_profile_for,
)
from game_predictor_api.domain.grid_shadow import (
    GRID_SHADOW_MAX_SOURCES,
    GRID_SHADOW_VALIDATION_KIND,
    GridShadowError,
    GridShadowResult,
    GridShadowResultPage,
    GridShadowResultView,
    request_fingerprint,
    shadow_digest,
)
from game_predictor_api.domain.image_grid_reviews import ImageGridReviewListItem
from game_predictor_api.domain.jobs import Job, JobType, create_job


class GridShadowModelStore(Protocol):
    def require(self, version: GridEngineModelVersion) -> object: ...


class GridShadowRepository(Protocol):
    def require_game_for_update(self, game_id: UUID) -> GameShapeGeometryConfiguration | None: ...
    def find_request(self, game_id: UUID, request_id: UUID) -> Job | None: ...
    def pin_source(self, game_id: UUID, source_image_id: UUID) -> dict[str, object]: ...
    def add_job(self, job: Job) -> Job: ...
    def get_result(self, game_id: UUID, result_id: UUID) -> GridShadowResult | None: ...
    def list_results(
        self, game_id: UUID, *, source_image_id: UUID | None, after_id: UUID | None, limit: int
    ) -> tuple[GridShadowResult, ...]: ...
    def review_items(
        self, game_id: UUID, source_image_id: UUID
    ) -> tuple[ImageGridReviewListItem, ...]: ...


class GridShadowService:
    def __init__(
        self, repository: GridShadowRepository, model_store: GridShadowModelStore, enabled: bool
    ) -> None:
        self._repository = repository
        self._model_store = model_store
        self._enabled = enabled

    def start(self, *, game_id: UUID, request_id: UUID, source_ids: tuple[UUID, ...]) -> Job:
        if not self._enabled:
            raise GridShadowError(
                "GRID_SHADOW_DISABLED", "Grid comparison is disabled.", status_code=409
            )
        fingerprint = request_fingerprint(source_ids)
        configuration = self._repository.require_game_for_update(game_id)
        # Replay precedes current source/model validation. Response loss never
        # repins a request to newer source or profile revisions.
        existing = self._repository.find_request(game_id, request_id)
        if existing is not None:
            if existing.input_payload.get("request_fingerprint_sha256") != fingerprint:
                raise GridShadowError(
                    "GRID_SHADOW_REQUEST_CONFLICT", "Request ID already has different sources."
                )
            return existing
        profile = grid_engine_profile_for(configuration)
        if profile is None:
            raise GridShadowError(
                "GRID_SHADOW_PROFILE_REQUIRED", "Select a registered grid engine profile."
            )
        version = profile.current
        try:
            self._model_store.require(version)
        except GridEngineModelError as error:
            raise GridShadowError(
                error.code, error.message, status_code=503, details=error.details
            ) from error
        sources = tuple(self._repository.pin_source(game_id, value) for value in source_ids)
        sources = tuple(
            sorted(
                sources,
                key=lambda value: (
                    int(str(value["sequence_range_start"])),
                    str(value["source_image_id"]),
                ),
            )
        )
        model: dict[str, object] = {
            "profile": version.profile.value,
            "version": version.version,
            "manifest_checksum_sha256": shadow_digest(grid_engine_manifest(version)),
            "bundle_checksum_sha256": next(
                item.sha256 for item in version.files if item.name == "bundle.json"
            ),
            "weights_sha256": version.weights_sha256,
            "files": [
                {"name": item.name, "sha256": item.sha256, "size_bytes": item.size_bytes}
                for item in version.files
            ],
        }
        payload: dict[str, object] = {
            "schema_version": 1,
            "validation_kind": GRID_SHADOW_VALIDATION_KIND,
            "request_id": str(request_id),
            "request_fingerprint_sha256": fingerprint,
            "model": model,
            "sources": list(sources),
        }
        payload["input_digest_sha256"] = shadow_digest(payload)
        return self._repository.add_job(
            create_job(JobType.VALIDATE, game_id=game_id, input_payload=payload)
        )

    def get(self, *, game_id: UUID, result_id: UUID) -> GridShadowResultView:
        result = self._repository.get_result(game_id, result_id)
        if result is None:
            raise GridShadowError(
                "GRID_SHADOW_RESULT_NOT_FOUND", "Comparison result does not exist.", status_code=404
            )
        return self._view(result)

    def list(
        self,
        *,
        game_id: UUID,
        source_image_id: UUID | None = None,
        cursor: str | None = None,
        limit: int = GRID_SHADOW_MAX_SOURCES,
    ) -> GridShadowResultPage:
        if not 1 <= limit <= GRID_SHADOW_MAX_SOURCES:
            raise GridShadowError(
                "GRID_SHADOW_PAGE_INVALID", "Page limit must be 1–20.", status_code=422
            )
        after_id = None
        if cursor is not None:
            try:
                cursor_game, cursor_source, cursor_id = cursor.split(":")
                if UUID(cursor_game) != game_id or cursor_source != str(source_image_id or "all"):
                    raise ValueError("cursor scope")
                after_id = UUID(cursor_id)
            except ValueError as error:
                raise GridShadowError(
                    "GRID_SHADOW_CURSOR_INVALID",
                    "Cursor does not match this query.",
                    status_code=422,
                ) from error
        results = self._repository.list_results(
            game_id, source_image_id=source_image_id, after_id=after_id, limit=limit + 1
        )
        visible = results[:limit]
        next_cursor = None
        if len(results) > limit:
            next_cursor = f"{game_id}:{source_image_id or 'all'}:{visible[-1].id}"
        return GridShadowResultPage(tuple(self._view(result) for result in visible), next_cursor)

    def _view(self, result: GridShadowResult) -> GridShadowResultView:
        try:
            current = self._repository.pin_source(result.game_id, result.source_image_id)
            stale = current.get("bindings_sha256") != result.source_binding.get("bindings_sha256")
        except GridShadowError:
            stale = True
        current_reviews = self._repository.review_items(result.game_id, result.source_image_id)
        baseline = result.source_binding.get("baseline_slots")
        if not stale and isinstance(baseline, list):
            frozen_slots = {
                int(str(slot["position_index"])): slot
                for slot in baseline
                if isinstance(slot, dict) and slot.get("slot_id") is not None
            }
            if len(current_reviews) != len(frozen_slots) or any(
                not _same_review_binding(item, frozen_slots.get(item.position_index), result)
                for item in current_reviews
            ):
                stale = True
        asset_id = next(
            (
                item.slot_id
                for item in current_reviews
                if item.source_checksum_sha256 == result.source_checksum_sha256
            ),
            None,
        )
        reviews = () if stale else current_reviews
        return GridShadowResultView(result, stale, reviews, asset_id)


def _same_review_binding(
    item: ImageGridReviewListItem, frozen: object, result: GridShadowResult
) -> bool:
    if not isinstance(frozen, dict):
        return False
    return (
        frozen.get("slot_id") == str(item.slot_id)
        and frozen.get("slot_kind") == item.slot_kind.value
        and frozen.get("recognized_board_id")
        == (None if item.recognized_board_id is None else str(item.recognized_board_id))
        and frozen.get("geometry_revision") == item.geometry_revision
        and frozen.get("resolution_revision") == item.resolution_revision
        and frozen.get("sequence_number") == item.sequence_number
        and frozen.get("grid_rows") == item.topology.rows
        and frozen.get("grid_columns") == item.topology.columns
        and frozen.get("geometry") == dict(item.geometry)
        and frozen.get("geometry_engine_name") == item.geometry_engine_name
        and frozen.get("geometry_engine_version") == item.geometry_engine_version
        and item.source_checksum_sha256 == result.source_checksum_sha256
        and (item.source_width, item.source_height) == (result.source_width, result.source_height)
    )
