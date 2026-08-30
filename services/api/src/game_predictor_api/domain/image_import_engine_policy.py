"""Safe per-game policy for creating new image-import jobs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class ImageImportEnginePolicy(StrEnum):
    VERIFIED_V19 = "verified_v19"
    STRUCTURED_SHADOW = "structured_shadow"


@dataclass(frozen=True, slots=True)
class ImageImportEnginePolicySnapshot:
    game_id: UUID
    policy: ImageImportEnginePolicy
    geometry_mode: str
    cell_asset_mode: str
    revision: int


@dataclass(frozen=True, slots=True)
class ImageImportEnginePolicyPreview:
    current: ImageImportEnginePolicySnapshot
    target: ImageImportEnginePolicySnapshot
    preview_token: str
    changes_existing_jobs: bool = False


def policy_rollout_modes(policy: ImageImportEnginePolicy) -> tuple[str, str]:
    if policy is ImageImportEnginePolicy.VERIFIED_V19:
        return "legacy", "legacy_files"
    return "structured_shadow", "virtual_shadow"


def policy_from_rollout_modes(
    geometry_mode: str,
    cell_asset_mode: str,
) -> ImageImportEnginePolicy:
    pair = (geometry_mode, cell_asset_mode)
    if pair == ("legacy", "legacy_files"):
        return ImageImportEnginePolicy.VERIFIED_V19
    if pair == ("structured_shadow", "virtual_shadow"):
        return ImageImportEnginePolicy.STRUCTURED_SHADOW
    raise ValueError("The rollout state is not a user-selectable image engine policy.")


def engine_policy_preview_token(
    *,
    game_id: UUID,
    current_revision: int,
    current_geometry_mode: str,
    current_cell_asset_mode: str,
    target_policy: ImageImportEnginePolicy,
) -> str:
    payload = {
        "currentCellAssetMode": current_cell_asset_mode,
        "currentGeometryMode": current_geometry_mode,
        "currentRevision": current_revision,
        "gameId": str(game_id),
        "schemaVersion": "image-import-engine-policy-preview-v1",
        "targetPolicy": target_policy.value,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "ImageImportEnginePolicy",
    "ImageImportEnginePolicyPreview",
    "ImageImportEnginePolicySnapshot",
    "engine_policy_preview_token",
    "policy_from_rollout_modes",
    "policy_rollout_modes",
]
