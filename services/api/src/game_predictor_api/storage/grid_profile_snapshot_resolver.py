"""Resolve the exact active grid profile pinned to a new curated import."""

from __future__ import annotations

import hashlib
import json
from uuid import UUID

from game_predictor_worker.images.page_geometry_registration import (
    build_verified_page_registration_profile,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from game_predictor_api.application.jobs import (
    GridProfileSnapshotResolver,
    _baseline_grid_profile_snapshot,
)
from game_predictor_api.domain.grid_calibration import GridProfileStatus
from game_predictor_api.domain.jobs import JobConflictError
from game_predictor_api.storage.models import (
    GameGridProfileActivationModel,
    GridCalibrationProfileModel,
    GridGeometryCohortModel,
)


class SqlAlchemyGridProfileSnapshotResolver(GridProfileSnapshotResolver):
    def __init__(self, session: Session) -> None:
        self._session = session

    def resolve(self, *, game_id: UUID) -> dict[str, object]:
        activation = self._session.scalar(
            select(GameGridProfileActivationModel)
            .where(GameGridProfileActivationModel.game_id == game_id)
            .order_by(GameGridProfileActivationModel.activation_number.desc())
            .limit(1)
        )
        if activation is None:
            return _baseline_grid_profile_snapshot()
        profile = self._session.get(GridCalibrationProfileModel, activation.profile_id)
        if (
            profile is None
            or profile.game_id != game_id
            or profile.status != GridProfileStatus.CANDIDATE_READY.value
        ):
            raise JobConflictError(
                "GRID_PROFILE_ACTIVE_PROFILE_INVALID",
                "The active grid profile is unavailable or no longer eligible.",
            )
        canonical_profile = json.dumps(
            profile.profile_payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        if hashlib.sha256(canonical_profile).hexdigest() != profile.profile_checksum_sha256:
            raise JobConflictError(
                "GRID_PROFILE_ACTIVE_PROFILE_DRIFT",
                "The active grid profile checksum changed.",
            )
        cohort = self._session.get(GridGeometryCohortModel, profile.cohort_id)
        if cohort is None or cohort.game_id != game_id:
            raise JobConflictError(
                "GRID_PROFILE_ACTIVE_COHORT_INVALID",
                "The active grid profile has no valid immutable geometry cohort.",
            )
        anchor_checksums = profile.profile_payload.get("anchorSourceChecksums")
        selected_anchors = (
            tuple(value for value in anchor_checksums if isinstance(value, str))
            if isinstance(anchor_checksums, list)
            else None
        )
        registration_profile = build_verified_page_registration_profile(
            cohort.manifest_payload,
            anchor_source_checksums=selected_anchors,
        )
        if selected_anchors is not None:
            raw_anchors = registration_profile.get("anchors")
            resolved_checksums = (
                tuple(
                    anchor.get("sourceChecksumSha256")
                    for anchor in raw_anchors
                    if isinstance(anchor, dict)
                    and isinstance(anchor.get("sourceChecksumSha256"), str)
                )
                if isinstance(raw_anchors, list)
                else ()
            )
            if resolved_checksums != selected_anchors:
                raise JobConflictError(
                    "GRID_PROFILE_ACTIVE_ANCHOR_DRIFT",
                    "The active 36-corner anchor set differs from its immutable cohort.",
                )
        value: dict[str, object] = {
            "profileId": str(profile.id),
            "profileVersion": f"grid-calibration-v{profile.profile_number}",
            "profileChecksumSha256": profile.profile_checksum_sha256,
            "activationId": str(activation.id),
            "profilePayload": dict(profile.profile_payload),
            # The offset calibration remains immutable and replayable.  Page
            # registration is a separately versioned projection of its
            # reviewed cohort, pinned beside it in each import job.
            "pageRegistrationProfile": registration_profile,
        }
        canonical = json.dumps(
            value,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        value["inferenceFingerprint"] = hashlib.sha256(canonical).hexdigest()
        return value


__all__ = ["SqlAlchemyGridProfileSnapshotResolver"]
