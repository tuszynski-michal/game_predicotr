"""Safe per-game policy for creating new image-import jobs.

D-467 (TASK-0790): only virtual policies remain.  ``verified_v19`` (legacy
geometry with file crops) and ``structured_shadow`` (legacy primary with a
virtual shadow) were removed; a request naming them is rejected with
``IMAGE_ENGINE_POLICY_LEGACY_UNSUPPORTED``.  A new game starts on
``structured_lattice_v3``, the engine every browser import pins.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class ImageImportEnginePolicy(StrEnum):
    STRUCTURED_DEFAULT = "structured_default"
    STRUCTURED_LATTICE_V3 = "structured_lattice_v3"


DEFAULT_IMAGE_IMPORT_ENGINE_POLICY = ImageImportEnginePolicy.STRUCTURED_LATTICE_V3
"""Policy of a game without a rollout state (and of every new game)."""

LEGACY_IMAGE_IMPORT_ENGINE_POLICY_ERROR = "IMAGE_ENGINE_POLICY_LEGACY_UNSUPPORTED"
"""Explicit code returned when a request names a removed legacy policy."""

REMOVED_IMAGE_IMPORT_ENGINE_POLICIES = frozenset({"verified_v19", "structured_shadow"})
"""Former policy values; kept only to recognize and reject them explicitly."""


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
    if policy is ImageImportEnginePolicy.STRUCTURED_LATTICE_V3:
        return "structured_lattice_v3", "virtual_default"
    return "structured_default", "virtual_default"


def default_rollout_modes() -> tuple[str, str]:
    """Rollout modes of a game that has no explicit policy yet."""

    return policy_rollout_modes(DEFAULT_IMAGE_IMPORT_ENGINE_POLICY)


DEFAULT_GEOMETRY_MODE, DEFAULT_CELL_ASSET_MODE = default_rollout_modes()
"""Rollout state columns of a new game (also the 0133 migration target)."""


def policy_from_rollout_modes(
    geometry_mode: str,
    cell_asset_mode: str,
) -> ImageImportEnginePolicy:
    pair = (geometry_mode, cell_asset_mode)
    if pair == ("structured_default", "virtual_default"):
        return ImageImportEnginePolicy.STRUCTURED_DEFAULT
    if pair == ("structured_lattice_v3", "virtual_default"):
        return ImageImportEnginePolicy.STRUCTURED_LATTICE_V3
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
    "DEFAULT_CELL_ASSET_MODE",
    "DEFAULT_GEOMETRY_MODE",
    "DEFAULT_IMAGE_IMPORT_ENGINE_POLICY",
    "LEGACY_IMAGE_IMPORT_ENGINE_POLICY_ERROR",
    "REMOVED_IMAGE_IMPORT_ENGINE_POLICIES",
    "ImageImportEnginePolicy",
    "ImageImportEnginePolicyPreview",
    "ImageImportEnginePolicySnapshot",
    "default_rollout_modes",
    "engine_policy_preview_token",
    "policy_from_rollout_modes",
    "policy_rollout_modes",
]
