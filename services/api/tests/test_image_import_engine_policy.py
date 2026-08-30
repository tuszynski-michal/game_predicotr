from uuid import uuid4

import pytest
from game_predictor_api.domain.image_import_engine_policy import (
    ImageImportEnginePolicy,
    engine_policy_preview_token,
    policy_from_rollout_modes,
    policy_rollout_modes,
)


def test_safe_engine_policies_map_only_to_stable_and_shadow_modes() -> None:
    assert policy_rollout_modes(ImageImportEnginePolicy.VERIFIED_V19) == (
        "legacy",
        "legacy_files",
    )
    assert policy_rollout_modes(ImageImportEnginePolicy.STRUCTURED_SHADOW) == (
        "structured_shadow",
        "virtual_shadow",
    )
    assert policy_from_rollout_modes("legacy", "legacy_files") is (
        ImageImportEnginePolicy.VERIFIED_V19
    )
    with pytest.raises(ValueError):
        policy_from_rollout_modes("structured_default", "virtual_default")


def test_policy_preview_token_is_deterministic_and_revision_bound() -> None:
    game_id = uuid4()
    values = dict(
        game_id=game_id,
        current_revision=2,
        current_geometry_mode="legacy",
        current_cell_asset_mode="legacy_files",
        target_policy=ImageImportEnginePolicy.STRUCTURED_SHADOW,
    )
    token = engine_policy_preview_token(**values)
    assert token == engine_policy_preview_token(**values)
    assert token != engine_policy_preview_token(**{**values, "current_revision": 3})
