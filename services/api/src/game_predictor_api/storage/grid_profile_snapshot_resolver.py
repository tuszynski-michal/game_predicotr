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
from game_predictor_api.domain.geometry_qualification import geometry_training_exclusion_reason
from game_predictor_api.domain.grid_calibration import (
    GridProfileStatus,
    grid_profile_end_to_end_gate_is_current,
)
from game_predictor_api.domain.grid_model_registry import GridModelRegistryError, descriptor_sha256
from game_predictor_api.domain.grid_model_snapshots import uses_neural_grid
from game_predictor_api.domain.jobs import JobConflictError
from game_predictor_api.domain.neural_grid_proposal import NeuralGridSnapshot
from game_predictor_api.storage.grid_engine_model_store import ManagedGridEngineModelStore
from game_predictor_api.storage.grid_model_registry import SqlAlchemyGridModelRegistryRepository
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
        """Pin the explicit assignment once; never infer a default or static current."""
        game = self._session.get(GameModel, game_id)
        if game is None or not uses_neural_grid(game.shape_geometry_configuration):
            return None
        if game.code == "7":
            raise JobConflictError(
                "GRID_MODEL_HISTORICAL_GAME_PROTECTED", "Historical 777 cannot enter V3."
            )
        if self._artifact_root is None:
            raise JobConflictError(
                "GRID_ENGINE_MODEL_STORE_UNAVAILABLE", "The managed model store is unavailable."
            )
        snapshot = self._assigned_snapshot(game)
        ManagedGridEngineModelStore(self._artifact_root).require(snapshot.version)
        return snapshot.to_payload()

    def _assigned_snapshot(self, game: GameModel) -> NeuralGridSnapshot:
        configuration = game.shape_geometry_configuration
        if not isinstance(configuration, str) or not uses_neural_grid(configuration):
            raise JobConflictError("GRID_MODEL_FORMAT_UNSUPPORTED", "The game does not use V3.")
        repository = SqlAlchemyGridModelRegistryRepository(self._session)
        try:
            assignment, _ = repository.assignment(game.id)
            if assignment is None:
                raise JobConflictError(
                    "GRID_MODEL_ASSIGNMENT_REQUIRED",
                    "V3 import requires an explicit model assignment.",
                )
            record = repository.version(assignment.version_id)
            if record is None:
                raise JobConflictError(
                    "GRID_MODEL_REGISTRY_CORRUPT", "Assigned model version is missing."
                )
            descriptor = json.loads(record.manifest_json)
            if not isinstance(descriptor, dict):
                raise ValueError("Assigned descriptor must be an object.")
            if (
                descriptor_sha256(descriptor) != record.manifest_sha256
                or descriptor.get("versionId") != str(record.id)
                or record.id != assignment.version_id
                or descriptor.get("familyId") != str(record.family_id)
                or descriptor.get("version") != record.version
            ):
                raise JobConflictError(
                    "GRID_MODEL_REGISTRY_CORRUPT", "Assigned model descriptor differs."
                )
            snapshot = NeuralGridSnapshot.from_catalogue(
                game_id=str(game.id),
                game_configuration=configuration,
                expected_layout_count=game.expected_layout_count,
                descriptor=descriptor,
            )
            if snapshot.version.catalogue_manifest_json != record.manifest_json:
                raise JobConflictError(
                    "GRID_MODEL_REGISTRY_CORRUPT", "Assigned descriptor is not canonical."
                )
            return snapshot
        except JobConflictError:
            raise
        except GridModelRegistryError as error:
            raise JobConflictError(error.code, error.message) from error
        except (ValueError, TypeError, KeyError) as error:
            raise JobConflictError(
                "GRID_MODEL_REGISTRY_CORRUPT", "Assigned descriptor is invalid."
            ) from error

    def neural_grid_profile(self, *, game_id: UUID) -> str | None:
        game = self._session.get(GameModel, game_id)
        if (
            game is None
            or game.code == "7"
            or not uses_neural_grid(game.shape_geometry_configuration)
        ):
            return None
        return game.shape_geometry_configuration

    def uses_neural_grid_pilot(self, *, game_id: UUID) -> bool:
        return self.neural_grid_profile(game_id=game_id) is not None

    def require_neural_grid_assignment(self, *, game_id: UUID) -> bool:
        if not self.uses_neural_grid_pilot(game_id=game_id):
            return False
        game = self._session.get(GameModel, game_id)
        assert game is not None
        self._assigned_snapshot(game)
        return True

    def neural_snapshot_matches_game(self, *, game_id: UUID, snapshot: NeuralGridSnapshot) -> bool:
        configuration = self.neural_grid_profile(game_id=game_id)
        if snapshot.game_id is not None:
            return snapshot.game_id == str(game_id) and snapshot.game_configuration == configuration
        return snapshot.profile.value == configuration

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
