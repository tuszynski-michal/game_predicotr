"""Resolve the exact active grid profile pinned to a new curated import."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import UUID

from game_predictor_worker.images.page_geometry_registration import (
    build_verified_page_registration_profile,
)
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from game_predictor_api.application.jobs import (
    GridProfileSnapshotResolver,
    _baseline_grid_profile_snapshot,
)
from game_predictor_api.domain.catalog import GameShapeGeometryConfiguration
from game_predictor_api.domain.geometry_qualification import geometry_training_exclusion_reason
from game_predictor_api.domain.grid_calibration import (
    GridProfileStatus,
    grid_profile_end_to_end_gate_is_current,
)
from game_predictor_api.domain.grid_engine_profiles import grid_engine_profile_for
from game_predictor_api.domain.jobs import JobConflictError
from game_predictor_api.domain.neural_grid_proposal import NeuralGridSnapshot
from game_predictor_api.storage.grid_engine_model_store import ManagedGridEngineModelStore
from game_predictor_api.storage.models import (
    GameGridProfileActivationModel,
    GameModel,
    GridCalibrationProfileModel,
    GridGeometryCohortModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
)


class SqlAlchemyGridProfileSnapshotResolver(GridProfileSnapshotResolver):
    def __init__(self, session: Session, artifact_root: Path | None = None) -> None:
        self._session = session
        self._artifact_root = artifact_root

    def resolve_neural_grid_proposal(self, *, game_id: UUID) -> dict[str, object] | None:
        """Only the explicitly selected Mumie profile enables the neural pilot."""
        game = self._session.get(GameModel, game_id)
        if (
            game is None
            or game.shape_geometry_configuration
            != GameShapeGeometryConfiguration.GRID_PROFILE_MUMIE_V1.value
        ):
            return None
        if self._artifact_root is None:
            raise JobConflictError(
                "GRID_ENGINE_MODEL_STORE_UNAVAILABLE", "The managed model store is unavailable."
            )
        profile = grid_engine_profile_for(GameShapeGeometryConfiguration.GRID_PROFILE_MUMIE_V1)
        if profile is None:
            raise JobConflictError(
                "GRID_ENGINE_PROFILE_UNAVAILABLE", "The Mumie grid profile is unavailable."
            )
        version = profile.current
        ManagedGridEngineModelStore(self._artifact_root).require(version)
        return NeuralGridSnapshot.for_game(game.expected_layout_count, version).to_payload()

    def uses_neural_grid_pilot(self, *, game_id: UUID) -> bool:
        game = self._session.get(GameModel, game_id)
        return (
            game is not None
            and game.shape_geometry_configuration
            == GameShapeGeometryConfiguration.GRID_PROFILE_MUMIE_V1.value
        )

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
        if not grid_profile_end_to_end_gate_is_current(
            dict(profile.profile_payload),
            dict(profile.gate_metrics),
        ):
            raise JobConflictError(
                "GRID_PROFILE_END_TO_END_REVALIDATION_REQUIRED",
                "The active schema-v2 profile has no current end-to-end page and cell gate.",
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
        # Qualification affects a new page-registration snapshot, never the
        # frozen calibration/profile bytes or an already pinned job.
        raw_anchors = registration_profile.get("anchors")
        if isinstance(raw_anchors, list):
            checksums = tuple(
                anchor["sourceChecksumSha256"]
                for anchor in raw_anchors
                if isinstance(anchor, dict) and isinstance(anchor.get("sourceChecksumSha256"), str)
            )
            excluded: set[str] = set()
            if checksums:
                for checksum, board in self._session.execute(
                    select(SourceImageModel.checksum_sha256, RecognizedBoardModel)
                    .join(
                        RecognizedBoardModel,
                        RecognizedBoardModel.source_image_id == SourceImageModel.id,
                    )
                    .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
                    .where(
                        JobModel.game_id == game_id,
                        SourceImageModel.checksum_sha256.in_(checksums),
                        or_(
                            RecognizedBoardModel.geometry_qualification.is_not(None),
                            RecognizedBoardModel.completeness_status == "pending_partial",
                        ),
                    )
                ):
                    geometry = dict(board.board_geometry)
                    if board.geometry_qualification is not None:
                        geometry["geometryQualification"] = board.geometry_qualification
                    if (
                        geometry_training_exclusion_reason(
                            geometry,
                            completeness_status=board.completeness_status,
                            unavailable_cell_indices=tuple(board.unavailable_cell_indices),
                        )
                        is not None
                    ):
                        excluded.add(checksum)
            if excluded:
                registration_profile = {
                    **registration_profile,
                    "anchors": [
                        anchor
                        for anchor in raw_anchors
                        if anchor.get("sourceChecksumSha256") not in excluded
                    ],
                }
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
