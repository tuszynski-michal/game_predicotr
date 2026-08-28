"""SQLAlchemy persistence for immutable geometry cohorts and grid profiles."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from game_predictor_api.application.grid_calibration import GridCalibrationRepository
from game_predictor_api.domain.grid_calibration import (
    GeometryCohort,
    GeometryCohortDiagnostics,
    GridCalibrationProfile,
    GridProfileActivation,
    GridProfileActivationAction,
    GridProfileActivationPreview,
    GridProfileStatus,
    NormalizedQuad,
    VerifiedGeometrySample,
    build_geometry_manifest,
    profile_checksum,
    train_grid_profile,
)
from game_predictor_api.domain.jobs import JobConflictError, JobNotFoundError
from game_predictor_api.storage.models import (
    GameGridProfileActivationModel,
    GameModel,
    GridCalibrationProfileModel,
    GridGeometryCohortModel,
    ImageBoardSearchFastDocumentModel,
    ImagePipelineStageResultModel,
    ImageReviewItemModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
)


class SqlAlchemyGridCalibrationRepository(GridCalibrationRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_candidate(
        self, *, game_id: UUID
    ) -> tuple[GeometryCohort, GridCalibrationProfile, bool]:
        if self._session.get(GameModel, game_id) is None:
            raise JobNotFoundError("GAME_NOT_FOUND", "Game does not exist.")
        samples = self._verified_samples(game_id)
        if not samples:
            raise JobConflictError(
                "GRID_CALIBRATION_COHORT_EMPTY",
                "No accepted or corrected geometry is available for calibration.",
            )
        manifest, manifest_checksum = build_geometry_manifest(game_id, samples)
        existing = self._session.scalar(
            select(GridGeometryCohortModel).where(
                GridGeometryCohortModel.game_id == game_id,
                GridGeometryCohortModel.manifest_checksum_sha256 == manifest_checksum,
            )
        )
        if existing is not None:
            profile = self._session.scalar(
                select(GridCalibrationProfileModel).where(
                    GridCalibrationProfileModel.cohort_id == existing.id
                )
            )
            if profile is None:
                raise JobConflictError(
                    "GRID_CALIBRATION_PROFILE_MISSING",
                    "The immutable cohort exists without its profile.",
                )
            return _cohort(existing), _profile(profile), False
        sample_rows = cast(list[dict[str, object]], manifest["samples"])
        training_count = sum(row.get("split") == "training" for row in sample_rows)
        validation_count = len(sample_rows) - training_count
        cohort_record = GridGeometryCohortModel(
            game_id=game_id,
            cohort_number=self._next_cohort_number(game_id),
            manifest_checksum_sha256=manifest_checksum,
            manifest_payload=manifest,
            sample_count=len(samples),
            source_image_count=len({sample.source_image_id for sample in samples}),
            training_count=training_count,
            validation_count=validation_count,
        )
        self._session.add(cohort_record)
        self._session.flush()
        profile_payload, gate_metrics, rejection_reasons = train_grid_profile(manifest)
        profile_record = GridCalibrationProfileModel(
            game_id=game_id,
            cohort_id=cohort_record.id,
            profile_number=self._next_profile_number(game_id),
            status=(
                GridProfileStatus.CANDIDATE_READY.value
                if not rejection_reasons
                else GridProfileStatus.REJECTED.value
            ),
            profile_checksum_sha256=profile_checksum(profile_payload),
            profile_payload=profile_payload,
            gate_metrics=gate_metrics,
            rejection_reasons=list(rejection_reasons),
        )
        self._session.add(profile_record)
        self._session.flush()
        self._session.refresh(cohort_record)
        self._session.refresh(profile_record)
        return _cohort(cohort_record), _profile(profile_record), True

    def cohort_diagnostics(self, *, game_id: UUID) -> GeometryCohortDiagnostics:
        if self._session.get(GameModel, game_id) is None:
            raise JobNotFoundError("GAME_NOT_FOUND", "Game does not exist.")
        rows = self._session.execute(
            select(
                ImageReviewItemModel,
                RecognizedBoardModel,
                SourceImageModel,
                ImagePipelineStageResultModel,
                ImageBoardSearchFastDocumentModel,
            )
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
            )
            .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
            .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
            .join(
                ImageBoardSearchFastDocumentModel,
                (ImageBoardSearchFastDocumentModel.game_id == JobModel.game_id)
                & (ImageBoardSearchFastDocumentModel.review_item_id == ImageReviewItemModel.id),
            )
            .outerjoin(
                ImagePipelineStageResultModel,
                (
                    ImagePipelineStageResultModel.file_execution_key
                    == SourceImageModel.file_execution_key
                )
                & (ImagePipelineStageResultModel.stage == "board_detection"),
            )
            .where(
                JobModel.game_id == game_id,
                RecognizedBoardModel.approved_geometry_revision
                == RecognizedBoardModel.geometry_revision,
                ImageReviewItemModel.status.in_(("pending", "accepted", "corrected")),
            )
        ).all()
        accepted = corrected = missing_detection = incomplete = eligible = 0
        reasons: Counter[str] = Counter()
        sources: set[UUID] = set()
        sequences: list[int] = []
        for _review, board, source, stage, document in rows:
            sources.add(source.id)
            sequences.append(document.sequence_number)
            if board.geometry_revision > 0:
                corrected += 1
            else:
                accepted += 1
            detected = (
                None
                if stage is None
                else _detected_quad(stage.result_payload, board.position_index)
            )
            final = _quad(
                board.board_geometry.get("sourceQuad") or board.board_geometry.get("quad")
            )
            if detected is None:
                missing_detection += 1
                reasons["missing_detection"] += 1
            if final is None:
                incomplete += 1
                reasons["incomplete_geometry"] += 1
            if detected is not None and final is not None:
                eligible += 1
        return GeometryCohortDiagnostics(
            game_id=game_id,
            accepted_geometry_count=accepted,
            corrected_geometry_count=corrected,
            missing_detection_count=missing_detection,
            incomplete_geometry_count=incomplete,
            source_image_count=len(sources),
            first_sequence_number=min(sequences) if sequences else None,
            last_sequence_number=max(sequences) if sequences else None,
            eligible_geometry_count=eligible,
            excluded_geometry_count=len(rows) - eligible,
            exclusion_reason_counts=dict(sorted(reasons.items())),
        )

    def list_profiles(self, *, game_id: UUID, limit: int) -> tuple[GridCalibrationProfile, ...]:
        rows = self._session.scalars(
            select(GridCalibrationProfileModel)
            .where(GridCalibrationProfileModel.game_id == game_id)
            .order_by(GridCalibrationProfileModel.profile_number.desc())
            .limit(limit)
        ).all()
        return tuple(_profile(row) for row in rows)

    def preview_activation(
        self,
        *,
        game_id: UUID,
        profile_id: UUID,
        action: GridProfileActivationAction,
    ) -> GridProfileActivationPreview:
        target = self._eligible_profile(game_id, profile_id)
        current = self._current_activation(game_id)
        self._validate_transition(game_id, profile_id, current, action)
        return GridProfileActivationPreview(
            game_id=game_id,
            profile_id=profile_id,
            profile_checksum_sha256=target.profile_checksum_sha256,
            current_profile_id=None if current is None else current.profile_id,
            action=action,
            can_activate=True,
        )

    def activate(
        self,
        *,
        game_id: UUID,
        profile_id: UUID,
        expected_profile_checksum_sha256: str,
        expected_current_profile_id: UUID | None,
        action: GridProfileActivationAction,
        actor: str,
        reason: str | None,
        idempotency_key: UUID,
        command_sha256: str,
    ) -> tuple[GridProfileActivation, bool]:
        game = self._session.scalar(
            select(GameModel).where(GameModel.id == game_id).with_for_update()
        )
        if game is None:
            raise JobNotFoundError("GAME_NOT_FOUND", "Game does not exist.")
        existing = self._session.scalar(
            select(GameGridProfileActivationModel).where(
                GameGridProfileActivationModel.game_id == game_id,
                GameGridProfileActivationModel.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            if existing.command_sha256 != command_sha256:
                raise JobConflictError(
                    "GRID_PROFILE_ACTIVATION_IDEMPOTENCY_CONFLICT",
                    "The idempotency key was already used for another grid profile command.",
                )
            return _activation(existing), False
        target = self._eligible_profile(game_id, profile_id)
        if target.profile_checksum_sha256 != expected_profile_checksum_sha256:
            raise JobConflictError(
                "GRID_PROFILE_ACTIVATION_PREVIEW_STALE",
                "The profile checksum differs from the confirmed preview.",
            )
        current = self._current_activation(game_id)
        current_id = None if current is None else current.profile_id
        if current_id != expected_current_profile_id:
            raise JobConflictError(
                "GRID_PROFILE_ACTIVATION_PREVIEW_STALE",
                "The active grid profile changed after preview.",
            )
        self._validate_transition(game_id, profile_id, current, action)
        record = GameGridProfileActivationModel(
            game_id=game_id,
            profile_id=profile_id,
            previous_profile_id=current_id,
            action=action.value,
            activation_number=1 if current is None else current.activation_number + 1,
            actor=actor,
            reason=reason,
            idempotency_key=idempotency_key,
            command_sha256=command_sha256,
        )
        self._session.add(record)
        try:
            self._session.flush()
        except IntegrityError as error:
            raise JobConflictError(
                "GRID_PROFILE_ACTIVATION_WRITE_CONFLICT",
                "The grid profile activation changed concurrently; refresh and retry.",
            ) from error
        self._session.refresh(record)
        return _activation(record), True

    def list_activations(self, *, game_id: UUID, limit: int) -> tuple[GridProfileActivation, ...]:
        rows = self._session.scalars(
            select(GameGridProfileActivationModel)
            .where(GameGridProfileActivationModel.game_id == game_id)
            .order_by(GameGridProfileActivationModel.activation_number.desc())
            .limit(limit)
        ).all()
        return tuple(_activation(row) for row in rows)

    def _verified_samples(self, game_id: UUID) -> tuple[VerifiedGeometrySample, ...]:
        rows = self._session.execute(
            select(
                ImageReviewItemModel,
                RecognizedBoardModel,
                SourceImageModel,
                JobModel,
                ImagePipelineStageResultModel,
                ImageBoardSearchFastDocumentModel,
            )
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
            )
            .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
            .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
            .join(
                ImageBoardSearchFastDocumentModel,
                (ImageBoardSearchFastDocumentModel.game_id == JobModel.game_id)
                & (ImageBoardSearchFastDocumentModel.review_item_id == ImageReviewItemModel.id),
            )
            .join(
                ImagePipelineStageResultModel,
                (
                    ImagePipelineStageResultModel.file_execution_key
                    == SourceImageModel.file_execution_key
                )
                & (ImagePipelineStageResultModel.stage == "board_detection"),
            )
            .where(
                JobModel.game_id == game_id,
                RecognizedBoardModel.approved_geometry_revision
                == RecognizedBoardModel.geometry_revision,
                ImageReviewItemModel.status.in_(("pending", "accepted", "corrected")),
            )
            .order_by(SourceImageModel.checksum_sha256, RecognizedBoardModel.position_index)
        ).all()
        output: list[VerifiedGeometrySample] = []
        for review, board, source, job, stage, _document in rows:
            run_id = _uuid(job.input_payload.get("image_selection_run_id"))
            detected = _detected_quad(stage.result_payload, board.position_index)
            final = _quad(
                board.board_geometry.get("sourceQuad") or board.board_geometry.get("quad")
            )
            if detected is None or final is None:
                continue
            output.append(
                VerifiedGeometrySample(
                    board_id=board.id,
                    review_item_id=review.id,
                    source_image_id=source.id,
                    source_checksum_sha256=source.checksum_sha256,
                    image_selection_run_id=run_id,
                    position_index=board.position_index,
                    image_width=source.width,
                    image_height=source.height,
                    geometry_revision=board.geometry_revision,
                    resolution_revision=review.resolution_revision,
                    detected_quad=detected,
                    final_quad=final,
                )
            )
        return tuple(output)

    def _eligible_profile(self, game_id: UUID, profile_id: UUID) -> GridCalibrationProfileModel:
        target = self._session.get(GridCalibrationProfileModel, profile_id)
        if target is None or target.game_id != game_id:
            raise JobNotFoundError(
                "GRID_PROFILE_NOT_FOUND", "Grid calibration profile does not exist."
            )
        if target.status != GridProfileStatus.CANDIDATE_READY.value:
            raise JobConflictError(
                "GRID_PROFILE_CANDIDATE_NOT_READY",
                "Only a profile with a passed quality gate can be activated.",
            )
        return target

    def _current_activation(self, game_id: UUID) -> GameGridProfileActivationModel | None:
        return self._session.scalar(
            select(GameGridProfileActivationModel)
            .where(GameGridProfileActivationModel.game_id == game_id)
            .order_by(GameGridProfileActivationModel.activation_number.desc())
            .limit(1)
        )

    def _validate_transition(
        self,
        game_id: UUID,
        profile_id: UUID,
        current: GameGridProfileActivationModel | None,
        action: GridProfileActivationAction,
    ) -> None:
        current_id = None if current is None else current.profile_id
        if current_id == profile_id:
            raise JobConflictError("GRID_PROFILE_ALREADY_ACTIVE", "The profile is already active.")
        if action is GridProfileActivationAction.ROLLBACK:
            historical = self._session.scalar(
                select(GameGridProfileActivationModel.id)
                .where(
                    GameGridProfileActivationModel.game_id == game_id,
                    GameGridProfileActivationModel.profile_id == profile_id,
                )
                .limit(1)
            )
            if historical is None:
                raise JobConflictError(
                    "GRID_PROFILE_ROLLBACK_TARGET_INVALID",
                    "Rollback target was never active for this game.",
                )

    def _next_cohort_number(self, game_id: UUID) -> int:
        return (
            int(
                self._session.scalar(
                    select(func.coalesce(func.max(GridGeometryCohortModel.cohort_number), 0)).where(
                        GridGeometryCohortModel.game_id == game_id
                    )
                )
                or 0
            )
            + 1
        )

    def _next_profile_number(self, game_id: UUID) -> int:
        return (
            int(
                self._session.scalar(
                    select(
                        func.coalesce(func.max(GridCalibrationProfileModel.profile_number), 0)
                    ).where(GridCalibrationProfileModel.game_id == game_id)
                )
                or 0
            )
            + 1
        )


def _detected_quad(payload: Mapping[str, object], position: int) -> NormalizedQuad | None:
    boards = payload.get("boards")
    if not isinstance(boards, Sequence) or isinstance(boards, str | bytes):
        return None
    for raw in boards:
        if not isinstance(raw, Mapping) or raw.get("positionIndex") != position:
            continue
        geometry = raw.get("geometry")
        if isinstance(geometry, Mapping):
            return _quad(geometry.get("detectorQuad") or geometry.get("quad"))
    return None


def _quad(value: object) -> NormalizedQuad | None:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes) or len(value) != 4:
        return None
    points: list[tuple[float, float]] = []
    for raw in value:
        if not isinstance(raw, Mapping):
            return None
        x = raw.get("x")
        y = raw.get("y")
        if (
            not isinstance(x, int | float)
            or isinstance(x, bool)
            or not isinstance(y, int | float)
            or isinstance(y, bool)
        ):
            return None
        points.append((float(x), float(y)))
    return cast(NormalizedQuad, tuple(points))


def _uuid(value: object) -> UUID | None:
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _cohort(record: GridGeometryCohortModel) -> GeometryCohort:
    return GeometryCohort(
        id=record.id,
        game_id=record.game_id,
        cohort_number=record.cohort_number,
        manifest_checksum_sha256=record.manifest_checksum_sha256,
        manifest=dict(record.manifest_payload),
        sample_count=record.sample_count,
        source_image_count=record.source_image_count,
        training_count=record.training_count,
        validation_count=record.validation_count,
        created_at=record.created_at,
    )


def _profile(record: GridCalibrationProfileModel) -> GridCalibrationProfile:
    return GridCalibrationProfile(
        id=record.id,
        game_id=record.game_id,
        cohort_id=record.cohort_id,
        profile_number=record.profile_number,
        status=GridProfileStatus(record.status),
        profile_checksum_sha256=record.profile_checksum_sha256,
        profile_payload=dict(record.profile_payload),
        gate_metrics=dict(record.gate_metrics),
        rejection_reasons=tuple(record.rejection_reasons),
        created_at=record.created_at,
    )


def _activation(record: GameGridProfileActivationModel) -> GridProfileActivation:
    return GridProfileActivation(
        id=record.id,
        game_id=record.game_id,
        profile_id=record.profile_id,
        previous_profile_id=record.previous_profile_id,
        action=GridProfileActivationAction(record.action),
        activation_number=record.activation_number,
        actor=record.actor,
        reason=record.reason,
        idempotency_key=record.idempotency_key,
        command_sha256=record.command_sha256,
        created_at=record.created_at,
    )


__all__ = ["SqlAlchemyGridCalibrationRepository"]
