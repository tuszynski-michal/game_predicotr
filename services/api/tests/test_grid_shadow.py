"""Request replay and typed correction handoff without an operator database."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from game_predictor_api.api.grid_shadow import create_grid_shadow_router
from game_predictor_api.application.grid_shadow import GridShadowService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.catalog import GameShapeGeometryConfiguration
from game_predictor_api.domain.grid_engine_profiles import (
    GridEngineModelError,
    GridEngineModelVersion,
)
from game_predictor_api.domain.grid_shadow import (
    GridShadowError,
    GridShadowResult,
    shadow_digest,
    validate_shadow_output,
)
from game_predictor_api.domain.image_grid_reviews import (
    ImageGridReviewListItem,
    ImageGridReviewSlotKind,
    ImageGridReviewState,
)
from game_predictor_api.domain.jobs import Job
from game_predictor_api.schemas.grid_shadow import GridShadowJobCreate, to_grid_shadow_result
from pydantic import ValidationError


class Repository:
    def __init__(self) -> None:
        self.configuration = GameShapeGeometryConfiguration.GRID_PROFILE_MUMIE_V1
        self.jobs: list[Job] = []
        self.source_revision = 1
        self.results: dict[UUID, GridShadowResult] = {}
        self.topology_error = False

    def require_game_for_update(self, game_id: UUID) -> GameShapeGeometryConfiguration:
        return self.configuration

    def find_request(self, game_id: UUID, request_id: UUID) -> Job | None:
        return next(
            (
                job
                for job in self.jobs
                if job.game_id == game_id and job.input_payload["request_id"] == str(request_id)
            ),
            None,
        )

    def pin_source(self, game_id: UUID, source_image_id: UUID) -> dict[str, object]:
        if self.topology_error:
            raise GridShadowError("GRID_SHADOW_TOPOLOGY_UNSUPPORTED", "5 × 3 required")
        binding: dict[str, object] = {
            "source_image_id": str(source_image_id),
            "sequence_range_start": 1,
            "bindings_sha256": str(self.source_revision),
            "active_board_slots": [0],
        }
        return binding

    def add_job(self, job: Job) -> Job:
        self.jobs.append(job)
        return job

    def get_result(self, game_id: UUID, result_id: UUID) -> GridShadowResult | None:
        result = self.results.get(result_id)
        return result if result is not None and result.game_id == game_id else None

    def list_results(
        self, game_id: UUID, *, source_image_id: UUID | None, after_id: UUID | None, limit: int
    ) -> tuple[GridShadowResult, ...]:
        return tuple(result for result in self.results.values() if result.game_id == game_id)[
            :limit
        ]

    def review_items(
        self, game_id: UUID, source_image_id: UUID
    ) -> tuple[ImageGridReviewListItem, ...]:
        return ()


class ModelStore:
    def __init__(self) -> None:
        self.available = True
        self.calls = 0

    def require(self, version: GridEngineModelVersion) -> object:
        self.calls += 1
        if not self.available:
            raise GridEngineModelError("GRID_ENGINE_MODEL_MISSING", "Missing model", details={})
        return object()


def service(enabled: bool = True) -> tuple[GridShadowService, Repository, ModelStore]:
    repository, store = Repository(), ModelStore()
    return GridShadowService(repository, store, enabled), repository, store


def output() -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "status": "needs_review",
        "reasons": ["NEURAL_GRID_GATE_UNCALIBRATED"],
        "slots": [
            {
                "positionIndex": 0,
                "sequenceNumber": 1,
                "baselineNodes24": None,
                "neuralNodes24": None,
                "state": "missing",
                "reasonCodes": ["GRID_MISSING"],
                "cellVisibility": ["outside"] * 15,
            }
        ],
        "unassignedDetections": [],
    }


def result(game_id: UUID, source_id: UUID) -> GridShadowResult:
    return GridShadowResult(
        uuid4(),
        game_id,
        uuid4(),
        source_id,
        "a" * 64,
        uuid4(),
        1,
        "b" * 64,
        100,
        100,
        "grid_profile_mumie_v1",
        "v1",
        "c" * 64,
        {"bindings_sha256": "1"},
        {},
        "needs_review",
        ("GRID_MISSING",),
        output(),
        shadow_digest(output()),
        datetime.now(UTC),
    )


def test_off_is_default_and_blocks_before_model_or_storage_write() -> None:
    assert not ApiSettings.from_environment({}).grid_shadow_enabled
    assert ApiSettings.from_environment(
        {"GAME_PREDICTOR_GRID_SHADOW_ENABLED": "true"}
    ).grid_shadow_enabled
    assert not ApiSettings.from_environment(
        {"GAME_PREDICTOR_GRID_SHADOW_ENABLED": "invalid"}
    ).grid_shadow_enabled
    current, repository, store = service(False)
    with pytest.raises(GridShadowError, match="disabled"):
        current.start(game_id=uuid4(), request_id=uuid4(), source_ids=(uuid4(),))
    assert repository.jobs == [] and store.calls == 0


def test_response_lost_replay_precedes_model_and_geometry_drift() -> None:
    current, repository, store = service()
    game_id, request_id, source_id = uuid4(), uuid4(), uuid4()
    first = current.start(game_id=game_id, request_id=request_id, source_ids=(source_id,))
    repository.source_revision += 1
    repository.topology_error = True
    repository.configuration = GameShapeGeometryConfiguration.GRID_PROFILE_777_V2
    store.available = False
    repeated = current.start(game_id=game_id, request_id=request_id, source_ids=(source_id,))
    assert repeated.id == first.id and len(repository.jobs) == 1 and store.calls == 1
    with pytest.raises(GridShadowError, match="different sources"):
        current.start(game_id=game_id, request_id=request_id, source_ids=(uuid4(),))


def test_request_order_is_canonical_and_cross_game_request_ids_are_independent() -> None:
    current, repository, _store = service()
    game_id, request_id, ids = uuid4(), uuid4(), (uuid4(), uuid4())
    first = current.start(game_id=game_id, request_id=request_id, source_ids=ids)
    assert (
        current.start(game_id=game_id, request_id=request_id, source_ids=ids[::-1]).id == first.id
    )
    assert current.start(game_id=uuid4(), request_id=request_id, source_ids=ids).id != first.id
    assert len(repository.jobs) == 2


@pytest.mark.parametrize("reason", ["model", "topology"])
def test_failure_before_job_creation(reason: str) -> None:
    current, repository, store = service()
    store.available = reason != "model"
    repository.topology_error = reason == "topology"
    with pytest.raises(GridShadowError):
        current.start(game_id=uuid4(), request_id=uuid4(), source_ids=(uuid4(),))
    assert not repository.jobs


def test_stale_result_has_no_correction_handoff_and_other_game_cannot_read_it() -> None:
    current, repository, _store = service()
    game_id, source_id = uuid4(), uuid4()
    stored = result(game_id, source_id)
    repository.results[stored.id] = stored
    assert not current.get(game_id=game_id, result_id=stored.id).stale
    repository.source_revision = 2
    response = to_grid_shadow_result(current.get(game_id=game_id, result_id=stored.id))
    assert response.stale and all(slot.review_item is None for slot in response.output.slots)
    with pytest.raises(GridShadowError) as error:
        current.get(game_id=uuid4(), result_id=stored.id)
    assert error.value.status_code == 404


def test_duplicate_or_unbounded_sources_and_client_pins_are_rejected() -> None:
    source_id = uuid4()
    with pytest.raises(ValidationError):
        GridShadowJobCreate(request_id=uuid4(), source_image_ids=(source_id, source_id))
    with pytest.raises(ValidationError):
        GridShadowJobCreate(request_id=uuid4(), source_image_ids=tuple(uuid4() for _ in range(21)))
    with pytest.raises(ValidationError):
        GridShadowJobCreate.model_validate(
            {
                "requestId": str(uuid4()),
                "sourceImageIds": [str(source_id)],
                "model": {"profile": "fake"},
            }
        )


def test_router_request_job_response_and_result_are_generated_contracts() -> None:
    current, repository, _store = service()
    app = FastAPI()
    app.include_router(create_grid_shadow_router(lambda: current), prefix="/api/v1")
    game_id, source_id = uuid4(), uuid4()
    stored = result(game_id, source_id)
    repository.results[stored.id] = stored
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/admin/games/{game_id}/grid-shadow-jobs",
            json={"requestId": str(uuid4()), "sourceImageIds": [str(source_id)]},
        )
        assert response.status_code == 200
        assert response.json()["inputPayload"]["validationKind"] == "grid_geometry_shadow_v3"
        assert (
            client.get(f"/api/v1/admin/games/{game_id}/grid-shadow-results/{stored.id}").status_code
            == 200
        )
        assert (
            client.get(f"/api/v1/admin/games/{game_id}/grid-shadow-results?limit=21").status_code
            == 422
        )
    assert "GridShadowJobCreate" in app.openapi()["components"]["schemas"]


def test_output_preserves_every_slot_and_finite_geometry() -> None:
    pinned = {"active_board_slots": [0], "sequence_range_start": 1}
    value = output()
    validate_shadow_output(value, pinned)
    slots = cast(list[dict[str, object]], value["slots"])
    slots[0]["positionIndex"] = 1
    with pytest.raises(GridShadowError):
        validate_shadow_output(value, pinned)
    slots[0]["positionIndex"] = 0
    slots[0]["neuralNodes24"] = [{"x": float("nan"), "y": 0}] * 24
    with pytest.raises(GridShadowError):
        validate_shadow_output(value, pinned)


def test_second_review_read_cannot_attach_new_revisions_to_old_output() -> None:
    game_id, source_id, slot_id = uuid4(), uuid4(), uuid4()
    item = ImageGridReviewListItem(
        slot_id=slot_id,
        slot_kind=ImageGridReviewSlotKind.CURRENT_REVIEW,
        review_item_id=slot_id,
        game_id=game_id,
        import_job_id=uuid4(),
        recognized_board_id=uuid4(),
        pending_geometry_id=None,
        source_image_id=source_id,
        position_index=0,
        sequence_number=1,
        source_checksum_sha256="a" * 64,
        source_width=100,
        source_height=100,
        geometry_revision=1,
        approved_geometry_revision=None,
        resolution_revision=0,
        topology=BoardTopology(rows=3, columns=5),
        geometry={},
        asset_mode="virtual_source",
        geometry_engine_name="manual",
        geometry_engine_version="v1",
        board_confidence=1,
        reason_codes=(),
        state=ImageGridReviewState.NEEDS_VALIDATION,
    )

    class ChangingRepository(Repository):
        def review_items(
            self, game_id: UUID, source_image_id: UUID
        ) -> tuple[ImageGridReviewListItem, ...]:
            return (replace(item, geometry_revision=2),)

    repository = ChangingRepository()
    current = GridShadowService(repository, ModelStore(), True)
    stored = replace(
        result(game_id, source_id),
        source_binding={
            "bindings_sha256": "1",
            "baseline_slots": [
                {
                    "position_index": 0,
                    "sequence_number": 1,
                    "slot_id": str(slot_id),
                    "slot_kind": "current_review",
                    "recognized_board_id": str(item.recognized_board_id),
                    "geometry_revision": 1,
                    "resolution_revision": 0,
                    "geometry": {},
                    "grid_rows": 3,
                    "grid_columns": 5,
                }
            ],
        },
    )
    repository.results[stored.id] = stored
    view = current.get(game_id=game_id, result_id=stored.id)
    assert view.stale and view.review_items == ()
