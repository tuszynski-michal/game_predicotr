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


class PhotoReviewRequest(Mutation):
    action: Literal["mark", "withdraw", "accept", "reject"]
    source_id: str
    source_sha256: str = Field(min_length=64, max_length=64)
    expected_board_revisions: dict[str, int]
    board_indices: list[int] = Field(default_factory=list, max_length=101)
    note: str = Field(default="", max_length=1000)


class BoardReviewIssue(Contract):
    status: Literal["needs_correction", "needs_review"]
    note: str = ""
    board_revision: int
    actor: str
    decided_at: str


class PhotoReview(Contract):
    source_id: str
    source_sha256: str
    rejected: bool = False
    accepted_board_revisions: dict[str, int] = Field(default_factory=dict)
    issues: dict[str, BoardReviewIssue] = Field(default_factory=dict)
    actor: str = ""
    decided_at: str = ""


class FamilyRequest(Mutation):
    decision: FamilyDecision


class GeometryQualificationBinding(Contract):
    source_id: str
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_board_revisions: dict[str, int]


class GeometryQualificationRequest(Mutation):
    policy_version: Literal["historical-777-lab-geometry-v1"]
    decision_reference: Literal["D-453"]
    purpose: Literal["geometry"]
    game_id: str = Field(min_length=1)
    bindings: list[GeometryQualificationBinding] = Field(min_length=1, max_length=10000)


class StoredGeometryQualification(GeometryQualificationBinding):
    policy_version: Literal["historical-777-lab-geometry-v1"]
    decision_reference: Literal["D-453"]
    purpose: Literal["geometry"]
    game_id: str
    actor: str
    decided_at: str
    revision: int


GamePartition = Literal["development", "validation", "final_test", "unseen_game"]


class SplitRequest(Mutation):
    purpose: Literal["legacy", "geometry"] = "legacy"
    geometry_policy: (
        Literal["lab-geometry-cohort-777-targets-v2", "lab-geometry-whole-game-pilot-v1"] | None
    ) = None
    game_partitions: dict[str, GamePartition] | None = None
    geometry_source_ids: list[str] | None = Field(default=None, max_length=10000)
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
    purpose: Literal["legacy", "geometry"] = "legacy"
    policy_version: Literal[
        "legacy",
        "lab-geometry-split-v1",
        "lab-geometry-cohort-split-v1",
        "lab-geometry-cohort-777-targets-v2",
        "lab-geometry-whole-game-pilot-v1",
    ] = "legacy"
    game_partitions: dict[str, GamePartition] | None = None
    geometry_source_ids: list[str] | None = None
    leakage_components: dict[str, list[str]] = Field(default_factory=dict)
    leakage_component_fingerprints: dict[str, str] = Field(default_factory=dict)
    geometry_qualification_fingerprints: dict[str, str] = Field(default_factory=dict)
    geometry_target_fingerprints: dict[str, str] = Field(default_factory=dict)
    fingerprint: str
    revision: int
    unseen_game_id: str
    seed: int
    assignments: dict[str, str]
    measurement: dict[str, str]
    annotation_fingerprints: dict[str, str]
    exclusions: dict[str, str]


AssistedOrigin = Literal["proposal_unchanged", "proposal_corrected", "manual"]
AssistedAction = Literal[
    "accept_board",
    "revoke_board",
    "remove_board",
    "dismiss_proposal",
    "restore_proposal",
    "complete_photo",
]


class AssistedBoard(Contract):
    """The latest D-490 workflow decision for one board slot of a photo.

    The record owns the slot only while ``annotation_revision`` equals the revision of
    the stored annotation; any other writer (the T03 editor) takes the slot back.
    """

    board_index: int = Field(ge=0, le=8)
    status: Literal["accepted", "revoked", "removed"]
    origin: AssistedOrigin
    annotation_revision: int = Field(ge=1)
    proposal_set_id: str = ""
    proposal_id: str = ""
    proposal_sha256: str = ""
    max_corner_shift_px: float = Field(default=0, ge=0)
    actor: str
    decided_at: str


class AssistedPhoto(Contract):
    """Completeness of a whole photo (D-484, D-490) bound to its board revisions."""

    source_id: str
    source_sha256: str
    boards: dict[str, AssistedBoard] = Field(default_factory=dict)
    dismissed_proposal_ids: list[str] = Field(default_factory=list, max_length=200)
    confirmed_board_count: int | None = Field(default=None, ge=1, le=9)
    completed_board_revisions: dict[str, int] = Field(default_factory=dict)
    active_ms: int = Field(default=0, ge=0)
    actor: str = ""
    decided_at: str = ""
    completed_at: str = ""


class AssistedRequest(Mutation):
    """One explicit operator decision of the assisted complete-photo workflow."""

    action: AssistedAction
    source_id: str
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    board_index: int | None = Field(default=None, ge=0, le=8)
    expected_board_revision: int = Field(default=0, ge=0)
    origin: AssistedOrigin | None = None
    proposal_set_id: str = Field(default="", max_length=64)
    proposal_id: str = Field(default="", max_length=200)
    proposal_sha256: str = Field(default="", max_length=64)
    max_corner_shift_px: float = Field(default=0, ge=0)
    nodes: list[Point] = Field(default_factory=list, max_length=24)
    confirmed_board_count: int | None = Field(default=None, ge=1, le=9)
    expected_board_revisions: dict[str, int] = Field(default_factory=dict)
    activity_intervals_ms: list[int] = Field(default_factory=list, max_length=10000)
    correction_count: int = Field(default=0, ge=0, le=10000)


class AnnotationState(Contract):
    snapshot_id: str
    revision: int = 0
    annotations: dict[str, GeometryAnnotation] = Field(default_factory=dict)
    families: dict[str, StoredFamily] = Field(default_factory=dict)
    timings: list[Timing] = Field(default_factory=list)
    split: FrozenSplit | None = None
    split_stale: bool = False
    photo_reviews: dict[str, PhotoReview] = Field(default_factory=dict)
    geometry_qualifications: dict[str, StoredGeometryQualification] = Field(default_factory=dict)
    assisted_photos: dict[str, AssistedPhoto] = Field(default_factory=dict)


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
