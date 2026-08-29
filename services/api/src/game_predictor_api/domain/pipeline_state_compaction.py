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


__all__ = [
    "DISPOSABLE_STAGE_PAYLOADS",
    "PIPELINE_COMPACTION_SCHEMA",
    "PipelineStageDigest",
    "canonical_json_bytes",
    "manifest_checksum",
    "stage_digest",
    "terminal_manifest_payload",
]
