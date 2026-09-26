"""Versioned human decisions; proposals never imply approval."""

from typing import Literal

from pydantic import Field

from .contracts import Contract, Point, Topology


class Mutation(Contract):
    request_id: str = Field(min_length=8, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    expected_revision: int = Field(ge=0)
    actor: str = Field(min_length=1, max_length=100)


class GeometryAnnotation(Contract):
    source_id: str
    board_index: int = Field(ge=0, le=100)
    topology: Topology
    presence: Literal["present", "absent", "occluded", "unreadable"] = "present"
    corners: list[Point] = Field(default_factory=list, max_length=4)
    nodes: list[Point] = Field(default_factory=list, max_length=24)
    revision: int = 0
    source_sha256: str = ""
    location_approved: bool = False
    full_approved: bool = False
    geometry_sha256: str = ""
    actor: str = ""
    decided_at: str = ""


class AnnotationRequest(Mutation):
    annotation: GeometryAnnotation
    action: Literal["draft", "approve_location", "approve_full"]
    reviewed_all_nodes: bool = False
    activity_intervals_ms: list[int] = Field(default_factory=list, max_length=10000)
    correction_count: int = Field(default=0, ge=0, le=10000)


class FamilyDecision(Contract):
    source_ids: list[str] = Field(min_length=1, max_length=10000)
    family_id: str = Field(min_length=1, max_length=100)
    evidence: str = Field(min_length=5, max_length=2000)
    related_source_ids: list[str] = Field(default_factory=list, max_length=10000)
    provenance: Literal["unresolved", "verified", "777_v2_verified"] = "unresolved"
    declaration: str = Field(default="", max_length=2000)
    checksum_reviewed: bool = False
    similarity_reviewed: bool = False


class FamilyRequest(Mutation):
    decision: FamilyDecision


class SplitRequest(Mutation):
    unseen_game_id: str
    seed: int = Field(ge=0, le=2147483647)
    measurement_source_ids: list[str] = Field(default_factory=list, max_length=10000)
    difficulties: dict[str, str] = Field(default_factory=dict)


class StoredFamily(FamilyDecision):
    actor: str
    decided_at: str


class Timing(Contract):
    source_id: str
    game_id: str
    active_ms: int
    corrections: int


class FrozenSplit(Contract):
    fingerprint: str
    revision: int
    unseen_game_id: str
    seed: int
    assignments: dict[str, str]
    measurement: dict[str, str]
    annotation_fingerprints: dict[str, str]
    exclusions: dict[str, str]


class AnnotationState(Contract):
    snapshot_id: str
    revision: int = 0
    annotations: dict[str, GeometryAnnotation] = Field(default_factory=dict)
    families: dict[str, StoredFamily] = Field(default_factory=dict)
    timings: list[Timing] = Field(default_factory=list)
    split: FrozenSplit | None = None
    split_stale: bool = False


class BackupResult(Contract):
    backup_id: str
    revision: int


class BackupRequest(Contract):
    """An explicit JSON request, required by the local mutation boundary."""


class TimingReport(Contract):
    game_id: str
    measured_sources: int
    active_ms: int
    estimated_remaining_ms: int | None
    target_sources: int
