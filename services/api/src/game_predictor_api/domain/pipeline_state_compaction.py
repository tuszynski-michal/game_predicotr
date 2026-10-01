"""Deterministic contracts for compacting reproducible image-pipeline state."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

PIPELINE_COMPACTION_SCHEMA = "image-pipeline-compaction-preview-v2"
TERMINAL_MANIFEST_SCHEMA = "image-pipeline-terminal-manifest-v2"
DISPOSABLE_STAGE_PAYLOADS = frozenset(
    {"board_cell_geometry", "board_crops", "sequence_ocr", "symbol_inference"}
)


@dataclass(frozen=True, slots=True)
class PipelineStageDigest:
    stage: str
    adapter_version: str
    payload_checksum_sha256: str
    payload_bytes: int


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")


def stage_digest(
    *, stage: str, adapter_version: str, payload: Mapping[str, object]
) -> PipelineStageDigest:
    encoded = canonical_json_bytes(payload)
    return PipelineStageDigest(
        stage=stage,
        adapter_version=adapter_version,
        payload_checksum_sha256=hashlib.sha256(encoded).hexdigest(),
        payload_bytes=len(encoded),
    )


def terminal_manifest_payload(
    *,
    file_execution_key: str,
    source_checksum_sha256: str,
    pipeline_fingerprint: str,
    execution_status: str,
    execution_updated_at: datetime,
    stages: Sequence[PipelineStageDigest],
    source_image_ids: Sequence[str],
    recognized_board_ids: Sequence[str],
) -> dict[str, object]:
    return {
        "schemaVersion": TERMINAL_MANIFEST_SCHEMA,
        "fileExecutionKey": file_execution_key,
        "sourceChecksumSha256": source_checksum_sha256,
        "pipelineFingerprint": pipeline_fingerprint,
        "executionStatus": execution_status,
        "executionUpdatedAt": execution_updated_at.isoformat(),
        "stages": [
            {
                "stage": item.stage,
                "adapterVersion": item.adapter_version,
                "payloadChecksumSha256": item.payload_checksum_sha256,
                "payloadBytes": item.payload_bytes,
                "disposable": item.stage in DISPOSABLE_STAGE_PAYLOADS,
            }
            for item in sorted(stages, key=lambda value: value.stage)
        ],
        "finalResultIds": {
            "sourceImages": sorted(source_image_ids),
            "recognizedBoards": sorted(recognized_board_ids),
        },
    }


def manifest_checksum(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


@dataclass(frozen=True, slots=True)
class GameExecutionReferences:
    """Global file executions that one game store references or protects.

    ``owned_keys`` are executions linked from the game's import associations or
    source images. ``blocked_keys`` are executions the game still needs: an
    active import job, a failed association or unresolved board geometry.
    """

    storage_active: bool
    owned_keys: frozenset[str]
    blocked_keys: frozenset[str]
    source_image_ids: Mapping[str, tuple[str, ...]]
    recognized_board_ids: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class PipelineExecutionReferences:
    """Merged per-game view used for both the preview and the worker re-check."""

    compactable_keys: frozenset[str]
    source_image_ids: Mapping[str, tuple[str, ...]]
    recognized_board_ids: Mapping[str, tuple[str, ...]]


def merge_game_execution_references(
    games: Sequence[GameExecutionReferences],
) -> PipelineExecutionReferences:
    """Fail closed: compact only keys owned by a game and blocked by none.

    A key referenced by no game store is orphaned and stays. Any game that is
    not ``active`` (migrating, deleting, blocked) protects every key it owns.
    """

    owned: set[str] = set()
    blocked: set[str] = set()
    for game in games:
        owned.update(game.owned_keys)
        blocked.update(game.blocked_keys)
        if not game.storage_active:
            blocked.update(game.owned_keys)
    compactable = frozenset(owned - blocked)
    return PipelineExecutionReferences(
        compactable_keys=compactable,
        source_image_ids={
            key: tuple(
                sorted(value for game in games for value in game.source_image_ids.get(key, ()))
            )
            for key in compactable
        },
        recognized_board_ids={
            key: tuple(
                sorted(value for game in games for value in game.recognized_board_ids.get(key, ()))
            )
            for key in compactable
        },
    )


__all__ = [
    "DISPOSABLE_STAGE_PAYLOADS",
    "PIPELINE_COMPACTION_SCHEMA",
    "GameExecutionReferences",
    "PipelineExecutionReferences",
    "PipelineStageDigest",
    "canonical_json_bytes",
    "manifest_checksum",
    "merge_game_execution_references",
    "stage_digest",
    "terminal_manifest_payload",
]
