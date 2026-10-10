"""Typed server-pinned neural proposal and explicit source assignment DTOs."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from game_predictor_api.schemas.catalog import ApiModel
from game_predictor_api.schemas.source_lattice_geometry import (
    SourceLatticeNodesPayload,
    SourceLatticePoint,
)

Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class NeuralGridModelFilePayload(ApiModel):
    name: str
    sha256: Sha256
    size_bytes: int = Field(ge=0, strict=True)


class NeuralGridModelReportPayload(ApiModel):
    dataset: str
    result: str


class NeuralGridModelManifestPayload(ApiModel):
    schema_version: Literal["grid-engine-model-manifest-v1"]
    profile: Literal["grid_profile_mumie_v1"]
    version: str
    model_kind: Literal["neural_grid"]
    model_version: str
    bundle_format: str
    run_id: str
    export_id: str
    preset: str
    preset_fingerprint: Sha256
    weights_sha256: Sha256
    checkpoint_sha256: Sha256
    snapshot_id: Sha256
    frozen_on: str
    selection_reason: str
    report: str
    report_results: tuple[NeuralGridModelReportPayload, ...]
    files: tuple[NeuralGridModelFilePayload, ...]


class NeuralGridSnapshotPayload(ApiModel):
    contract_version: Literal["neural-grid-proposal-snapshot-v1"]
    expected_layout_count: int = Field(ge=1, le=10000000, strict=True)
    model: NeuralGridModelManifestPayload


class NeuralSourceRangePayload(ApiModel):
    sequence_range_start: int = Field(ge=1, strict=True)
    sequence_range_end: int = Field(ge=1, strict=True)


class NeuralDetectionPayload(ApiModel):
    detection_id: str
    score: float = Field(ge=0, le=1, strict=True)
    lattice_nodes: SourceLatticeNodesPayload | None
    cell_quads: tuple[
        tuple[SourceLatticePoint, SourceLatticePoint, SourceLatticePoint, SourceLatticePoint], ...
    ] = Field(max_length=15)
    cell_visibility: tuple[Literal["full", "partial", "outside", "unknown"], ...] = Field(
        min_length=15, max_length=15
    )
    structurally_valid: Annotated[bool, Field(strict=True)]
    reason_codes: tuple[str, ...]


class NeuralSourceProposalPayload(ApiModel):
    contract_version: Literal["neural-source-proposal-v1"]
    game_id: UUID
    source_selection_id: UUID
    source_checksum_sha256: Sha256
    source_width: int = Field(gt=0, strict=True)
    source_height: int = Field(gt=0, strict=True)
    original_range: NeuralSourceRangePayload
    engine_snapshot: NeuralGridSnapshotPayload
    detections: tuple[NeuralDetectionPayload, ...] = Field(max_length=256)
    proposal_checksum_sha256: Sha256


class NeuralSourceAssignmentPayload(ApiModel):
    detection_id: str
    position_index: int = Field(ge=0, le=8, strict=True)


class NeuralSourceBindingPayload(ApiModel):
    contract_version: Literal["neural-source-binding-v1"]
    game_id: UUID
    source_selection_id: UUID
    source_checksum_sha256: Sha256
    source_width: int = Field(gt=0, strict=True)
    source_height: int = Field(gt=0, strict=True)
    proposal_checksum_sha256: Sha256
    original_range: NeuralSourceRangePayload
    confirmed_range: NeuralSourceRangePayload
    assignments: tuple[NeuralSourceAssignmentPayload, ...] = Field(max_length=9)
    missing_position_indexes: tuple[Annotated[int, Field(ge=0, le=8, strict=True)], ...] = Field(
        max_length=9
    )
    ignored_detection_ids: tuple[str, ...] = Field(max_length=256)
