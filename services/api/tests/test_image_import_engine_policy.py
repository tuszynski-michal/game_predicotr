from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.image_import_engine_policy import (
    DEFAULT_CELL_ASSET_MODE,
    DEFAULT_GEOMETRY_MODE,
    DEFAULT_IMAGE_IMPORT_ENGINE_POLICY,
    LEGACY_IMAGE_IMPORT_ENGINE_POLICY_ERROR,
    ImageImportEnginePolicy,
    engine_policy_preview_token,
    policy_from_rollout_modes,
    policy_rollout_modes,
)
from game_predictor_api.main import create_app
from game_predictor_api.schemas.image_geometry_rollout import (
    ImageImportEnginePolicyPreviewRequest,
    ImageImportEnginePolicyUpdateRequest,
)
from game_predictor_api.schemas.image_imports import BrowserImageImportStart
from pydantic import ValidationError


def test_only_virtual_engine_policies_remain() -> None:
    # D-467 (TASK-0790): verified_v19 and structured_shadow were removed.
    assert {value.value for value in ImageImportEnginePolicy} == {
        "structured_default",
        "structured_lattice_v3",
    }
    assert policy_rollout_modes(ImageImportEnginePolicy.STRUCTURED_DEFAULT) == (
        "structured_default",
        "virtual_default",
    )
    assert policy_rollout_modes(ImageImportEnginePolicy.STRUCTURED_LATTICE_V3) == (
        "structured_lattice_v3",
        "virtual_default",
    )
    assert policy_from_rollout_modes("structured_default", "virtual_default") is (
        ImageImportEnginePolicy.STRUCTURED_DEFAULT
    )
    assert policy_from_rollout_modes("structured_lattice_v3", "virtual_default") is (
        ImageImportEnginePolicy.STRUCTURED_LATTICE_V3
    )
    for pair in (
        ("legacy", "legacy_files"),
        ("structured_shadow", "virtual_shadow"),
        ("structured_review", "virtual_shadow"),
    ):
        with pytest.raises(ValueError):
            policy_from_rollout_modes(*pair)


def test_new_game_default_is_the_virtual_lattice_v3_policy() -> None:
    assert DEFAULT_IMAGE_IMPORT_ENGINE_POLICY is ImageImportEnginePolicy.STRUCTURED_LATTICE_V3
    assert (DEFAULT_GEOMETRY_MODE, DEFAULT_CELL_ASSET_MODE) == (
        "structured_lattice_v3",
        "virtual_default",
    )


@pytest.mark.parametrize("removed", ("verified_v19", "structured_shadow"))
def test_requests_name_a_removed_policy_with_its_explicit_code(removed: str) -> None:
    requests = (
        lambda: ImageImportEnginePolicyPreviewRequest.model_validate({"targetPolicy": removed}),
        lambda: ImageImportEnginePolicyUpdateRequest.model_validate(
            {"targetPolicy": removed, "expectedRevision": 0, "previewToken": "a" * 64}
        ),
        lambda: BrowserImageImportStart.model_validate(
            {
                "gameId": str(uuid4()),
                "manifestChecksumSha256": "a" * 64,
                "preflightChecksumSha256": "b" * 64,
                "boardCellProcessingMode": removed,
            }
        ),
        lambda: BrowserImageImportStart.model_validate(
            {
                "gameId": str(uuid4()),
                "manifestChecksumSha256": "a" * 64,
                "preflightChecksumSha256": "b" * 64,
                "imageEnginePolicy": removed,
            }
        ),
    )
    for build in requests:
        with pytest.raises(ValidationError) as error:
            build()
        assert [item["type"] for item in error.value.errors()] == [
            LEGACY_IMAGE_IMPORT_ENGINE_POLICY_ERROR
        ]


def test_policy_preview_token_is_deterministic_and_revision_bound() -> None:
    game_id = uuid4()
    values = dict(
        game_id=game_id,
        current_revision=2,
        current_geometry_mode="structured_default",
        current_cell_asset_mode="virtual_default",
        target_policy=ImageImportEnginePolicy.STRUCTURED_LATTICE_V3,
    )
    token = engine_policy_preview_token(**values)
    assert token == engine_policy_preview_token(**values)
    assert token != engine_policy_preview_token(**{**values, "current_revision": 3})


def test_admin_api_returns_the_explicit_legacy_policy_code(tmp_path: Path) -> None:
    app = create_app(
        ApiSettings.from_environment(
            {
                "GAME_PREDICTOR_DATABASE_URL": (
                    "postgresql+psycopg://unused:unused@localhost:5432/unused"
                ),
                "GAME_PREDICTOR_ARTIFACT_ROOT": str(tmp_path),
            }
        ),
        image_geometry_rollout_service_dependency=lambda: object(),
    )
    endpoint = f"/api/v1/admin/games/{uuid4()}/image-import-engine-policy"

    with TestClient(app) as client:
        preview = client.post(f"{endpoint}/preview", json={"targetPolicy": "verified_v19"})
        update = client.put(
            endpoint,
            json={
                "targetPolicy": "structured_shadow",
                "expectedRevision": 0,
                "previewToken": "a" * 64,
            },
        )
        unknown = client.post(f"{endpoint}/preview", json={"targetPolicy": "nonexistent"})

    for response in (preview, update):
        assert response.status_code == 422
        assert response.json()["code"] == LEGACY_IMAGE_IMPORT_ENGINE_POLICY_ERROR
    assert unknown.status_code == 422
    assert unknown.json()["code"] == "VALIDATION_ERROR"
