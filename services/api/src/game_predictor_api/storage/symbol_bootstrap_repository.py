"""SQLAlchemy persistence for symbol-catalog bootstrap runs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import Float, String, and_, or_, select
from sqlalchemy import cast as sql_cast
from sqlalchemy.orm import Session

from game_predictor_api.application.symbol_bootstrap import SymbolBootstrapRepository
from game_predictor_api.domain.catalog import (
    CatalogConflictError,
    CatalogNotFoundError,
    Symbol,
    SymbolStatus,
)
from game_predictor_api.domain.symbol_bootstrap import (
    SymbolBootstrapCandidate,
    SymbolBootstrapDefinition,
    SymbolBootstrapObservation,
    SymbolBootstrapRun,
    SymbolBootstrapStatus,
    SymbolImageCandidate,
)
from game_predictor_api.storage.models import (
    CellObservationModel,
    GameModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
    SymbolBootstrapRunModel,
    SymbolModel,
)


class SqlAlchemySymbolBootstrapRepository(SymbolBootstrapRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def game_exists(self, game_id: UUID) -> bool:
        return self._session.get(GameModel, game_id) is not None

    def game_has_symbols(self, game_id: UUID) -> bool:
        return (
            self._session.scalar(
                select(SymbolModel.id).where(SymbolModel.game_id == game_id).limit(1)
            )
            is not None
        )

    def list_observations(self, game_id: UUID) -> Sequence[SymbolBootstrapObservation]:
        rows = self._session.execute(
            select(CellObservationModel)
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == CellObservationModel.recognized_board_id,
            )
            .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
            .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
            .where(
                JobModel.game_id == game_id,
                RecognizedBoardModel.status != "rejected",
            )
            .order_by(
                CellObservationModel.crop_checksum_sha256,
                CellObservationModel.crop_relative_path,
                CellObservationModel.id,
            )
        ).scalars()
        observations: list[SymbolBootstrapObservation] = []
        for row in rows:
            prediction = cast(Mapping[str, object], row.prediction)
            code = prediction.get("symbolCode")
            confidence = prediction.get("confidence")
            if (
                not isinstance(code, str)
                or not isinstance(confidence, int | float)
                or isinstance(confidence, bool)
            ):
                raise CatalogConflictError(
                    "SYMBOL_BOOTSTRAP_PREDICTION_INVALID",
                    "An imported crop has no valid symbol prediction.",
                )
            observations.append(
                SymbolBootstrapObservation(
                    crop_checksum_sha256=row.crop_checksum_sha256,
                    crop_relative_path=row.crop_relative_path,
                    predicted_symbol_code=code,
                    confidence=float(confidence),
                )
            )
        return observations

    def get_latest_run(self, game_id: UUID) -> SymbolBootstrapRun | None:
        record = self._session.scalar(
            select(SymbolBootstrapRunModel)
            .where(SymbolBootstrapRunModel.game_id == game_id)
            .order_by(SymbolBootstrapRunModel.created_at.desc(), SymbolBootstrapRunModel.id.desc())
            .limit(1)
        )
        return None if record is None else _to_run(record)

    def get_run(self, game_id: UUID, run_id: UUID) -> SymbolBootstrapRun | None:
        record = self._session.scalar(
            select(SymbolBootstrapRunModel).where(
                SymbolBootstrapRunModel.id == run_id,
                SymbolBootstrapRunModel.game_id == game_id,
            )
        )
        return None if record is None else _to_run(record)

    def add_run(
        self,
        *,
        game_id: UUID,
        expected_symbol_count: int,
        source_state_sha256: str,
        status: SymbolBootstrapStatus,
        candidates: tuple[SymbolBootstrapCandidate, ...],
        created_by: str,
        created_at: datetime,
    ) -> SymbolBootstrapRun:
        existing = self._session.scalar(
            select(SymbolBootstrapRunModel).where(
                SymbolBootstrapRunModel.game_id == game_id,
                SymbolBootstrapRunModel.source_state_sha256 == source_state_sha256,
                SymbolBootstrapRunModel.expected_symbol_count == expected_symbol_count,
            )
        )
        if existing is not None:
            return _to_run(existing)
        record = SymbolBootstrapRunModel(
            game_id=game_id,
            expected_symbol_count=expected_symbol_count,
            detected_cluster_count=len(candidates),
            source_state_sha256=source_state_sha256,
            status=status.value,
            candidates=[_candidate_payload(item) for item in candidates],
            resolution=None,
            created_by=created_by,
            created_at=created_at,
            applied_at=None,
        )
        self._session.add(record)
        self._session.flush()
        return _to_run(record)

    def apply_run(
        self,
        run: SymbolBootstrapRun,
        definitions: tuple[SymbolBootstrapDefinition, ...],
        *,
        applied_at: datetime,
    ) -> SymbolBootstrapRun:
        record = self._session.scalar(
            select(SymbolBootstrapRunModel)
            .where(SymbolBootstrapRunModel.id == run.id)
            .with_for_update()
        )
        if record is None:
            raise RuntimeError("Symbol bootstrap run disappeared during apply.")
        payload = [_definition_payload(item) for item in definitions]
        if record.status == SymbolBootstrapStatus.APPLIED.value:
            if record.resolution == payload:
                return _to_run(record)
            raise CatalogConflictError(
                "SYMBOL_BOOTSTRAP_ALREADY_APPLIED",
                "The symbol bootstrap run was already applied.",
            )
        if self.game_has_symbols(run.game_id):
            raise CatalogConflictError(
                "SYMBOL_BOOTSTRAP_CATALOG_NOT_EMPTY",
                "Symbol bootstrap requires an empty game catalog.",
            )
        for definition in definitions:
            self._session.add(
                SymbolModel(
                    game_id=run.game_id,
                    mobile_code=definition.mobile_code,
                    code=definition.code,
                    name=definition.name.strip(),
                    image_path=definition.image_path,
                    is_wildcard=False,
                    display_order=definition.mobile_code - 1,
                    status=SymbolStatus.ACTIVE,
                )
            )
        record.status = SymbolBootstrapStatus.APPLIED.value
        record.resolution = payload
        record.applied_at = applied_at
        self._session.flush()
        return _to_run(record)

    def list_image_candidates(
        self,
        *,
        game_id: UUID,
        symbol_id: UUID,
        after_key: tuple[float, str, str] | None,
        limit: int,
    ) -> Sequence[SymbolImageCandidate]:
        codes = self._prediction_codes(game_id, symbol_id)
        confidence = sql_cast(CellObservationModel.prediction["confidence"].as_string(), Float)
        predicted_code = CellObservationModel.prediction["symbolCode"].as_string()
        query = (
            select(CellObservationModel, confidence.label("confidence"))
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == CellObservationModel.recognized_board_id,
            )
            .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
            .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
            .where(
                JobModel.game_id == game_id,
                RecognizedBoardModel.status != "rejected",
                predicted_code.in_(codes),
            )
        )
        if after_key is not None:
            negative_confidence, checksum, observation_id = after_key
            boundary_confidence = -negative_confidence
            query = query.where(
                or_(
                    confidence < boundary_confidence,
                    and_(
                        confidence == boundary_confidence,
                        CellObservationModel.crop_checksum_sha256 > checksum,
                    ),
                    and_(
                        confidence == boundary_confidence,
                        CellObservationModel.crop_checksum_sha256 == checksum,
                        sql_cast(CellObservationModel.id, String) > observation_id,
                    ),
                )
            )
        rows = self._session.execute(
            query.order_by(
                confidence.desc(),
                CellObservationModel.crop_checksum_sha256,
                sql_cast(CellObservationModel.id, String),
            ).limit(limit)
        ).all()
        return [
            SymbolImageCandidate(
                observation_id=row.id,
                crop_relative_path=row.crop_relative_path,
                crop_checksum_sha256=row.crop_checksum_sha256,
                confidence=float(confidence_value),
            )
            for row, confidence_value in rows
        ]

    def get_image_candidate(
        self, *, game_id: UUID, symbol_id: UUID, observation_id: UUID
    ) -> SymbolImageCandidate | None:
        codes = self._prediction_codes(game_id, symbol_id)
        confidence = sql_cast(CellObservationModel.prediction["confidence"].as_string(), Float)
        predicted_code = CellObservationModel.prediction["symbolCode"].as_string()
        result = self._session.execute(
            select(CellObservationModel, confidence.label("confidence"))
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == CellObservationModel.recognized_board_id,
            )
            .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
            .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
            .where(
                CellObservationModel.id == observation_id,
                JobModel.game_id == game_id,
                RecognizedBoardModel.status != "rejected",
                predicted_code.in_(codes),
            )
        ).first()
        if result is None:
            return None
        row, confidence_value = result
        return SymbolImageCandidate(
            observation_id=row.id,
            crop_relative_path=row.crop_relative_path,
            crop_checksum_sha256=row.crop_checksum_sha256,
            confidence=float(confidence_value),
        )

    def get_selected_image_candidate(
        self, *, game_id: UUID, symbol_id: UUID
    ) -> SymbolImageCandidate | None:
        symbol = self._session.scalar(
            select(SymbolModel).where(
                SymbolModel.id == symbol_id,
                SymbolModel.game_id == game_id,
            )
        )
        if symbol is None:
            raise CatalogNotFoundError(
                "SYMBOL_NOT_FOUND",
                "Symbol does not exist in this game.",
            )
        if symbol.image_path is None:
            return None
        codes = self._prediction_codes(game_id, symbol_id)
        confidence = sql_cast(CellObservationModel.prediction["confidence"].as_string(), Float)
        predicted_code = CellObservationModel.prediction["symbolCode"].as_string()
        result = self._session.execute(
            select(CellObservationModel, confidence.label("confidence"))
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == CellObservationModel.recognized_board_id,
            )
            .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
            .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
            .where(
                JobModel.game_id == game_id,
                RecognizedBoardModel.status != "rejected",
                CellObservationModel.crop_relative_path == symbol.image_path,
                predicted_code.in_(codes),
            )
            .order_by(sql_cast(CellObservationModel.id, String))
            .limit(1)
        ).first()
        if result is None:
            return None
        row, confidence_value = result
        return SymbolImageCandidate(
            observation_id=row.id,
            crop_relative_path=row.crop_relative_path,
            crop_checksum_sha256=row.crop_checksum_sha256,
            confidence=float(confidence_value),
        )

    def select_image_candidate(
        self,
        *,
        game_id: UUID,
        symbol_id: UUID,
        candidate: SymbolImageCandidate,
        name: str,
    ) -> Symbol:
        symbol = self._session.scalar(
            select(SymbolModel).where(
                SymbolModel.id == symbol_id,
                SymbolModel.game_id == game_id,
            )
        )
        if symbol is None:
            raise CatalogNotFoundError(
                "SYMBOL_NOT_FOUND",
                "Symbol does not exist in this game.",
            )
        symbol.image_path = candidate.crop_relative_path
        symbol.name = name
        self._session.flush()
        return _to_symbol(symbol)

    def _prediction_codes(self, game_id: UUID, symbol_id: UUID) -> tuple[str, ...]:
        symbol = self._session.scalar(
            select(SymbolModel).where(
                SymbolModel.id == symbol_id,
                SymbolModel.game_id == game_id,
            )
        )
        if symbol is None:
            raise CatalogNotFoundError(
                "SYMBOL_NOT_FOUND",
                "Symbol does not exist in this game.",
            )
        run = self._session.scalar(
            select(SymbolBootstrapRunModel)
            .where(
                SymbolBootstrapRunModel.game_id == game_id,
                SymbolBootstrapRunModel.status == SymbolBootstrapStatus.APPLIED.value,
            )
            .order_by(SymbolBootstrapRunModel.applied_at.desc())
            .limit(1)
        )
        if run is None:
            return (symbol.code,)
        resolution = next(
            (item for item in run.resolution or [] if item.get("mobileCode") == symbol.mobile_code),
            None,
        )
        if resolution is None:
            return (symbol.code,)
        candidate_ids = set(cast(Sequence[str], resolution["candidateIds"]))
        codes = tuple(
            cast(str, candidate["predictedSymbolCode"])
            for candidate in run.candidates
            if candidate.get("candidateId") in candidate_ids
        )
        return codes or (symbol.code,)


def _candidate_payload(value: SymbolBootstrapCandidate) -> dict[str, object]:
    return {
        "candidateId": value.candidate_id,
        "meanConfidence": value.mean_confidence,
        "predictedSymbolCode": value.predicted_symbol_code,
        "proposedCode": value.proposed_code,
        "proposedName": value.proposed_name,
        "representativeCropChecksumSha256": value.representative_crop_checksum_sha256,
        "representativeCropRelativePath": value.representative_crop_relative_path,
        "sampleCount": value.sample_count,
    }


def _definition_payload(value: SymbolBootstrapDefinition) -> dict[str, object]:
    return {
        "candidateIds": list(value.candidate_ids),
        "code": value.code,
        "imagePath": value.image_path,
        "mobileCode": value.mobile_code,
        "name": value.name,
    }


def _to_symbol(record: SymbolModel) -> Symbol:
    return Symbol(
        id=record.id,
        game_id=record.game_id,
        mobile_code=record.mobile_code,
        code=record.code,
        name=record.name,
        image_path=record.image_path,
        is_wildcard=record.is_wildcard,
        display_order=record.display_order,
        status=SymbolStatus(record.status),
    )


def _to_run(record: SymbolBootstrapRunModel) -> SymbolBootstrapRun:
    candidates = tuple(_candidate_from_payload(item) for item in record.candidates)
    resolution = tuple(_definition_from_payload(item) for item in (record.resolution or []))
    return SymbolBootstrapRun(
        id=record.id,
        game_id=record.game_id,
        expected_symbol_count=record.expected_symbol_count,
        detected_cluster_count=record.detected_cluster_count,
        source_state_sha256=record.source_state_sha256,
        status=SymbolBootstrapStatus(record.status),
        candidates=candidates,
        resolution=resolution,
        created_by=record.created_by,
        created_at=record.created_at,
        applied_at=record.applied_at,
    )


def _candidate_from_payload(raw: Mapping[str, object]) -> SymbolBootstrapCandidate:
    return SymbolBootstrapCandidate(
        candidate_id=cast(str, raw["candidateId"]),
        predicted_symbol_code=cast(str, raw["predictedSymbolCode"]),
        proposed_code=cast(str, raw["proposedCode"]),
        proposed_name=cast(str, raw["proposedName"]),
        sample_count=cast(int, raw["sampleCount"]),
        mean_confidence=float(cast(float, raw["meanConfidence"])),
        representative_crop_relative_path=cast(str, raw["representativeCropRelativePath"]),
        representative_crop_checksum_sha256=cast(str, raw["representativeCropChecksumSha256"]),
    )


def _definition_from_payload(raw: Mapping[str, object]) -> SymbolBootstrapDefinition:
    return SymbolBootstrapDefinition(
        mobile_code=cast(int, raw["mobileCode"]),
        code=cast(str, raw["code"]),
        name=cast(str, raw["name"]),
        candidate_ids=tuple(cast(Sequence[str], raw["candidateIds"])),
        image_path=cast(str, raw["imagePath"]),
    )


__all__ = ["SqlAlchemySymbolBootstrapRepository"]
