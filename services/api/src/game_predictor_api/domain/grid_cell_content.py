"""Independent source-pixel content labels; geometry is measurement, never identity."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Annotated, Any, Final, Literal
from uuid import UUID

from pydantic import Field, model_validator

from .grid_training_cohorts import digest
from .grid_visibility_contract import (
    BoardContentReference,
    CellContentReference,
    Point,
    Sha,
    VisibilityClosed,
)

CONTENT_VERSION: Final = "source-cell-content-v1"
REPEATABILITY_VERSION = "cell-content-repeatability-v1"
REGRESSION_SEED = 20261108
MAX_SESSION_BOARDS = 900
ContentCells = Annotated[tuple[CellContentReference, ...], Field(min_length=15, max_length=15)]
GeometryNodes = Annotated[tuple[Point, ...], Field(min_length=24, max_length=24)]


class ContentError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.code, self.message, self.status_code = code, message, status_code
        self.report: dict[str, object] | None = None


def require_human(actor: str) -> None:
    """Transport must authenticate first; arbitrary actors are not human evidence."""
    if actor != "local-owner" and not actor.startswith("reviewer-session:"):
        raise ContentError("CONTENT_HUMAN_REQUIRED", "A validated human actor is required.", 403)
    if actor.startswith("reviewer-session:"):
        try:
            UUID(actor.removeprefix("reviewer-session:"))
        except ValueError as error:
            raise ContentError("CONTENT_HUMAN_REQUIRED", "Invalid reviewer actor.", 403) from error


class ContentSource(VisibilityClosed):
    sourceId: UUID
    sourceSha256: Sha
    sourceRepresentativeSha256: Sha
    width: Annotated[int, Field(strict=True, gt=0)]
    height: Annotated[int, Field(strict=True, gt=0)]
    coordinateSpace: Literal["exif-normalized-rgb-pixels-v1"] = "exif-normalized-rgb-pixels-v1"
    normalizationAdapterVersion: Literal["image-normalization-v2-in-memory-source-v1"] = (
        "image-normalization-v2-in-memory-source-v1"
    )
    exifOrientation: Annotated[int, Field(strict=True, ge=1, le=8)] | None = None


def content_source_identity(source: Mapping[str, Any]) -> ContentSource:
    try:
        return ContentSource(
            sourceId=source["id"],
            sourceSha256=source["checksum_sha256"],
            sourceRepresentativeSha256=source["normalized_pixel_checksum_sha256"],
            width=source["oriented_width"],
            height=source["oriented_height"],
            coordinateSpace=source["coordinate_space"],
            normalizationAdapterVersion=source["normalization_adapter_version"],
            exifOrientation=source.get("exif_orientation"),
        )
    except (ValueError, KeyError) as error:
        raise ContentError(
            "CONTENT_SOURCE_IDENTITY_UNRESOLVED", "Canonical source identity is incomplete."
        ) from error


def same_content_frame(first: ContentSource, second: ContentSource) -> bool:
    """Aliases share normalized pixels, not byte encoding/UUID/EXIF provenance."""
    return all(
        getattr(first, name) == getattr(second, name)
        for name in (
            "sourceRepresentativeSha256",
            "width",
            "height",
            "coordinateSpace",
            "normalizationAdapterVersion",
        )
    )


def require_content_bounds(source: ContentSource, cells: Sequence[CellContentReference]) -> None:
    """Validate request coordinates before Pydantic wraps model invariant errors."""
    if any(
        cell.quad is not None
        and any(not 0 <= x <= source.width or not 0 <= y <= source.height for x, y in cell.quad)
        for cell in cells
    ):
        raise ContentError("CONTENT_QUAD_OUTSIDE_SOURCE", "The quad exceeds the source frame.", 422)


class ContentRevision(VisibilityClosed):
    version: Literal["source-cell-content-v1"] = CONTENT_VERSION
    source: ContentSource
    reference: BoardContentReference
    sequenceNumber: Annotated[int, Field(strict=True, ge=1)]
    origin: Literal["manual", "manual_blind", "ai_proposal"]
    actor: str
    approvedBy: str | None = None
    approvedAt: datetime | None = None
    recordedAt: datetime
    proposalSha256: Sha | None = None
    sessionId: UUID | None = None
    passNumber: Literal[1, 2] | None = None
    measuredNodes: GeometryNodes | None = None

    @model_validator(mode="after")
    def provenance(self) -> ContentRevision:
        require_human(self.actor)
        if self.reference.sourceRepresentativeSha256 != self.source.sourceRepresentativeSha256:
            raise ValueError("CONTENT_SOURCE_IDENTITY_CONFLICT")
        if self.reference.humanApproved != (
            self.approvedBy is not None and self.approvedAt is not None
        ):
            raise ValueError("CONTENT_APPROVAL_INVALID")
        if (self.approvedBy is None) != (self.approvedAt is None):
            raise ValueError("CONTENT_APPROVAL_INVALID")
        if self.approvedBy is not None:
            require_human(self.approvedBy)
            if self.approvedBy != self.actor:
                raise ValueError("CONTENT_APPROVAL_ACTOR_CONFLICT")
        if (self.origin == "ai_proposal") != (self.proposalSha256 is not None):
            raise ValueError("CONTENT_PROPOSAL_PROVENANCE_REQUIRED")
        if self.origin == "manual_blind":
            if not self.reference.humanApproved or any(
                value is None for value in (self.sessionId, self.passNumber, self.measuredNodes)
            ):
                raise ValueError("CONTENT_BLIND_EVIDENCE_REQUIRED")
        elif any(
            value is not None for value in (self.sessionId, self.passNumber, self.measuredNodes)
        ):
            raise ValueError("CONTENT_BLIND_PROVENANCE_CONFLICT")
        # A non-visible quad is only observed remaining pixels, never a guessed full sign.
        for cell in self.reference.cells:
            if cell.quad is not None and any(
                not 0 <= x <= self.source.width or not 0 <= y <= self.source.height
                for x, y in cell.quad
            ):
                raise ValueError("CONTENT_QUAD_OUTSIDE_SOURCE")
        return self

    @property
    def sha256(self) -> str:
        return digest(self.model_dump(mode="json"))


class ContentTarget(VisibilityClosed):
    """Exact projection from a trusted frozen cohort; no independently assignable role."""

    gameId: UUID
    source: ContentSource
    positionIndex: Annotated[int, Field(strict=True, ge=0, le=8)]
    sequenceNumber: Annotated[int, Field(strict=True, ge=1)]
    role: Literal["TRAIN", "A", "B", "REGRESSION"]
    fullPhoto: bool
    targetSha256: Sha
    roleProofSha256: Sha

    @property
    def key(self) -> tuple[str, str, int]:
        return str(self.gameId), self.source.sourceRepresentativeSha256, self.positionIndex


def require_reference(target: ContentTarget, revision: ContentRevision) -> None:
    if (
        revision.reference.gameId != target.gameId
        or revision.source != target.source
        or revision.reference.positionIndex != target.positionIndex
        or revision.sequenceNumber != target.sequenceNumber
    ):
        raise ContentError("CONTENT_TARGET_CONFLICT", "The source or logical board differs.")


def content_readiness(
    targets: Sequence[ContentTarget],
    revisions: Sequence[ContentRevision],
    required_games: Sequence[UUID],
    *,
    unresolved_photos: Mapping[tuple[str, str], int] | None = None,
    report_live_conflicts: bool = False,
) -> dict[str, object]:
    """The frozen target denominator includes absent/unapproved annotations as unknown."""
    refs: dict[tuple[str, str, int], ContentRevision] = {}
    for revision in revisions:
        key = (
            str(revision.reference.gameId),
            revision.source.sourceRepresentativeSha256,
            revision.reference.positionIndex,
        )
        if key in refs and refs[key] != revision:
            raise ContentError(
                "CONTENT_ALIAS_CONFLICT", "Conflicting content references on a copy."
            )
        refs[key] = revision
    unique: dict[tuple[str, str, int], ContentTarget] = {}
    for target in targets:
        prior = unique.get(target.key)
        if prior is not None and (prior.role != target.role or prior.fullPhoto != target.fullPhoto):
            raise ContentError("CONTENT_ROLE_CONFLICT", "Copies have conflicting frozen roles.")
        unique[target.key] = target
    if not refs.keys() <= unique.keys():
        raise ContentError(
            "CONTENT_MEMBERSHIP_CONFLICT", "References exceed the frozen population."
        )
    games: dict[str, object] = {}
    qualified = bool(required_games)
    for game in sorted({str(value) for value in required_games}):
        roles: dict[str, object] = {}
        for role in ("TRAIN", "A", "B", "REGRESSION"):
            members = [t for t in unique.values() if str(t.gameId) == game and t.role == role]
            counts = dict.fromkeys(("visible", "occluded", "out_of_frame", "unknown"), 0)
            unapproved = 0
            conflicts: set[str] = set()
            full: dict[str, set[int]] = {}
            for target in members:
                current_ref = refs.get(target.key)
                if current_ref is None or not current_ref.reference.humanApproved:
                    counts["unknown"] += 15
                    unapproved += 15
                    continue
                # Copy UUIDs can differ, but their frame/slot and label must agree.
                frame_conflict = not same_content_frame(current_ref.source, target.source)
                sequence_conflict = current_ref.sequenceNumber != target.sequenceNumber
                if frame_conflict or sequence_conflict:
                    if not report_live_conflicts:
                        raise ContentError("CONTENT_FRAME_CONFLICT", "Copy frames differ.")
                    # A stale live board is unknown progress, not a failure to read
                    # independent immutable pins. Keep all 15 slots in the population.
                    counts["unknown"] += 15
                    unapproved += 15
                    conflicts.add(
                        "CONTENT_FRAME_CONFLICT" if frame_conflict else "CONTENT_SEQUENCE_CONFLICT"
                    )
                    continue
                for cell in current_ref.reference.cells:
                    counts[cell.state] += 1
                if target.fullPhoto and all(
                    c.state != "unknown" for c in current_ref.reference.cells
                ):
                    full.setdefault(target.source.sourceRepresentativeSha256, set()).add(
                        target.positionIndex
                    )
            total = len(members) * 15
            complete = sum(slots == set(range(9)) for slots in full.values())
            reasons = sorted(conflicts)
            unresolved = (unresolved_photos or {}).get((game, role), 0)
            if unresolved:
                reasons.append("CONTENT_ROLE_MEMBERSHIP_INCOMPLETE")
            if not total:
                reasons.append("CONTENT_LABELS_MISSING")
            elif counts["unknown"] / total > 0.10:
                reasons.append("CONTENT_UNKNOWN_LIMIT")
            if role == "REGRESSION" and complete < 5:
                reasons.append("CONTENT_REG_FULL_PHOTOS_MISSING")
            qualified = qualified and not reasons
            roles[role] = {
                "state": "not_evaluable" if reasons else "evaluable",
                "reasonCodes": reasons,
                "boards": len(members),
                "slots": total,
                "unapprovedSlots": unapproved,
                "unresolvedPhotos": unresolved,
                "states": counts,
                "fullPhotos": complete,
                "missingFullPhotos": max(0, 5 - complete) if role == "REGRESSION" else 0,
            }
        games[game] = roles
    return {
        "version": CONTENT_VERSION,
        "state": "evaluable" if qualified else "not_evaluable",
        "games": games,
    }


def content_readiness_views(
    targets: Sequence[ContentTarget],
    live: Sequence[ContentRevision],
    frozen: Sequence[ContentRevision],
    required_games: Sequence[UUID],
    *,
    unresolved_photos: Mapping[tuple[str, str], int] | None = None,
) -> dict[str, object]:
    """Live progress cannot upgrade immutable training/evaluation input coverage."""
    coverage = content_readiness(
        targets, frozen, required_games, unresolved_photos=unresolved_photos
    )
    progress = content_readiness(
        targets,
        live,
        required_games,
        unresolved_photos=unresolved_photos,
        report_live_conflicts=True,
    )
    return {
        **coverage,
        "basis": "frozen_content_pins",
        "annotationProgress": progress,
        "frozenPinCoverage": coverage,
    }


def oracle_qualification(states: Sequence[str]) -> dict[str, Any]:
    """No visible reference is not clipping and never proves full-content preservation."""
    blocked = sum(state == "render_contract_blocked" for state in states)
    unchecked = sum(state not in {"checked", "render_contract_blocked"} for state in states)
    return {
        "boards": len(states),
        "checkedBoards": sum(state == "checked" for state in states),
        "blockedBoards": blocked,
        "notEvaluableBoards": unchecked,
        "qualificationState": "render_contract_blocked"
        if blocked
        else ("not_evaluable" if unchecked or not states else "ready"),
    }


def content_capture_counts(
    canonical_boards: int, positions: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Expose optional coverage and rejected identity proofs without rewriting role counts."""
    labels = [p["label"] for p in positions if p["label"] is not None]
    qualified = sum("contentAnnotation" in label for label in labels)
    reasons = Counter(
        p["reason"] for p in positions if str(p.get("reason", "")).startswith("CONTENT_")
    )
    absent = sum("contentAnnotation" not in label for label in labels)
    if absent:
        reasons["CONTENT_LABELS_MISSING"] += absent
    return {
        "canonicalBoards": canonical_boards,
        "contentUsedBoards": len(labels),
        "contentQualifiedBoards": qualified,
        "contentMissingBoards": max(0, canonical_boards - qualified),
        "contentReasonCounts": dict(sorted(reasons.items())),
    }
