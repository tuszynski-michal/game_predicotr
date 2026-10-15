"""Geometry recording qualification; declarations never manufacture independence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

POLICY = "geometry-recording-resolution-v1"
PAGE_SIZE = 200
MAX_COMPONENT_GROUPS = 4096
MAX_COMPONENT_DEPTH = 64
PROTECTED_ROLES = frozenset(
    {
        "VALIDATION",
        "REGRESSION",
        "final_test",
        "unseen_game",
        "Reels",
        "Treasure",
        "declared_holdouts",
    }
)


class RecordingError(ValueError):
    def __init__(self, code: str, message: str, status: int = 409) -> None:
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def canonical_recording_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def recording_sha256(value: object) -> str:
    return hashlib.sha256(canonical_recording_json(value).encode("utf-8")).hexdigest()


def protected_recording_mapping(value: object) -> bool:
    if not isinstance(value, list) or len(value) > MAX_COMPONENT_GROUPS:
        return False
    seen: set[str] = set()
    for item in value:
        if (
            not isinstance(item, dict)
            or set(item) != {"groupId", "role"}
            or item.get("role") not in PROTECTED_ROLES | {"TRAIN"}
        ):
            return False
        try:
            identifier = str(UUID(item["groupId"]))
        except (ValueError, TypeError, AttributeError):
            return False
        if identifier in seen:
            return False
        seen.add(identifier)
    return True


@dataclass(frozen=True)
class AncestorResolution:
    """A complete result requires a trusted provider for every pinned ancestor."""

    complete: bool
    lineage_sha256: str
    references: tuple[dict[str, Any], ...]
    blockers: tuple[str, ...]


def resolve_ancestor_references(
    lineage: dict[str, Any], providers: dict[str, dict[str, Any]]
) -> AncestorResolution:
    blockers: set[str] = set()
    references: list[dict[str, Any]] = []
    ancestors = lineage.get("ancestors")
    if not isinstance(ancestors, list) or not ancestors or len(ancestors) > 64:
        blockers.add("RECORDING_ANCESTOR_EXCLUSIONS_UNRESOLVED")
        ancestors = []
    seen: set[str] = set()
    for ancestor in ancestors:
        identifier = str(ancestor.get("versionId", ""))
        if not identifier or identifier in seen:
            blockers.add("RECORDING_ANCESTOR_EXCLUSIONS_UNRESOLVED")
            continue
        seen.add(identifier)
        provider = providers.get(identifier)
        if (
            provider is None
            or provider.get("schemaVersion") != "recording-ancestor-provider-v1"
            or provider.get("ancestor") != ancestor
            or provider.get("complete") is not True
            or provider.get("recordingIdentityAvailable") is not True
            or not protected_recording_mapping(provider.get("recordingGroups"))
        ):
            blockers.add("RECORDING_ANCESTOR_EXCLUSIONS_UNRESOLVED")
            continue
        references.append({**provider, "providerSha256": recording_sha256(provider)})
    return AncestorResolution(
        not blockers, recording_sha256(lineage), tuple(references), tuple(sorted(blockers))
    )
