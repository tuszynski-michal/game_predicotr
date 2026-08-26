"""Pending-only grid and crop refresh.

This job deliberately operates on review rows that are still ``pending``.  It
never reopens a human decision and stores a new geometry revision instead of
mutating the immutable cell observations from the original import.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import cast
from uuid import NAMESPACE_URL, UUID, uuid5

import numpy as np
from game_predictor_api.domain.jobs import Job, JobStatus
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
)
from game_predictor_api.storage.image_symbol_review_repository import (
    SymbolCellReviewWriteThroughCoordinator,
)
from game_predictor_api.storage.models import (
    ImageBoardGeometryRevisionModel,
    ImageImportJobFileModel,
    ImageReviewItemModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
)
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import and_, select
from sqlalchemy.orm import Session, sessionmaker

from game_predictor_worker.jobs.runtime import JobExecutionContext, JobHandlerError

from .board_cell_geometry_activation import (
    BoardCellRecropSnapshotError,
    validate_board_cell_recrop_snapshot,
)
from .board_cell_geometry_contract import (
    BOARD_CELL_COORDINATE_SPACE,
    BOARD_CELL_CORNER_SEMANTICS,
    BOARD_CELL_GEOMETRY_VERSION,
    BoardCellGeometryEntry,
)
from .board_cell_geometry_crops import (
    CROPPER_VERSION,
    BoardCellGeometrySourceDirectCropper,
)
from .board_cell_geometry_estimator import ESTIMATOR_VERSION, estimate_board_cell_geometry
from .geometry import ClassicalPageBoardDetector
from .geometry import Point as DetectorPoint
from .production_workflow import _calibrated_quad
from .rectification import BoardGeometry, PageGeometry
from .source_direct_crops import SourceDirectBoardCellCropper

_V19_CORRECTED_BY = "pending-board-cell-recrop-v19"


@dataclass(frozen=True, slots=True)
class _PendingBoardSnapshot:
    review_item_id: UUID
    resolution_revision: int
    recognized_board_id: UUID
    geometry_revision: int
    source_image_id: UUID
    import_job_id: UUID
    source_order_index: int | None
    sequence_number: int | None
    position_index: int
    board_geometry: dict[str, object]
    board_relative_path: str
    board_checksum_sha256: str
    source_relative_path: str
    source_checksum_sha256: str
    source_width: int
    source_height: int


@dataclass(frozen=True, slots=True)
class _PreparedCell:
    row_index: int
    column_index: int
    png: bytes
    checksum_sha256: str
    source_quad: tuple[tuple[float, float], ...]
    padded_source_quad: tuple[tuple[float, float], ...]


@dataclass(frozen=True, slots=True)
class _PreparedV19Refresh:
    geometry: dict[str, object]
    lattice_bounds_quad: tuple[tuple[float, float], ...]
    cells: tuple[_PreparedCell, ...]
    command_sha256: str


class _V19NeedsReview(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class PendingGridReinferenceHandler:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        artifact_root: Path,
    ) -> None:
        self._session_factory = session_factory
        self._artifact_root = artifact_root.resolve()
        self._detector = ClassicalPageBoardDetector()

    def __call__(self, context: JobExecutionContext, job: Job) -> None:
        schema_version = job.input_payload.get("schema_version")
        if schema_version == 1:
            self._run_v1(context, job)
            return
        if schema_version == 2:
            self._run_v2(context, job)
            return
        raise JobHandlerError(
            "IMAGE_GRID_REINFERENCE_SCHEMA_UNSUPPORTED",
            "The pending grid reinference schema is unsupported.",
        )

    def _run_v1(self, context: JobExecutionContext, job: Job) -> None:
        """Reproduce historical queued jobs without changing their adapter contract."""

        if job.game_id is None:
            raise JobHandlerError("IMAGE_GRID_REINFERENCE_GAME_MISSING", "The game is missing.")
        profile, fingerprint = _profile_from_payload(job)
        cell_output_size = _cell_output_size_from_payload(job)
        with self._session_factory() as session:
            rows = list(
                session.execute(
                    select(ImageReviewItemModel, RecognizedBoardModel, SourceImageModel)
                    .join(
                        RecognizedBoardModel,
                        RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
                    )
                    .join(
                        SourceImageModel,
                        SourceImageModel.id == RecognizedBoardModel.source_image_id,
                    )
                    .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
                    .where(
                        JobModel.game_id == job.game_id,
                        JobModel.status == JobStatus.WAITING_FOR_REVIEW,
                        ImageReviewItemModel.status == "pending",
                    )
                    .order_by(ImageReviewItemModel.created_at, ImageReviewItemModel.id)
                )
                .tuples()
                .all()
            )
        total = len(rows)
        processed = 0
        skipped = 0
        failures = 0
        for item, board, source in rows:
            try:
                geometry, board_path, board_checksum, crops = self._refresh_board(
                    source,
                    position_index=board.position_index,
                    profile=profile,
                    fingerprint=fingerprint,
                    cell_output_size=cell_output_size,
                )
            except (OSError, UnidentifiedImageError, ValueError) as error:
                failures += 1
                context.checkpoint(
                    checkpoint_payload={
                        "schema_version": 1,
                        "kind": "pending-grid-reinference-v1",
                        "processed": processed,
                        "skippedConcurrentResolution": skipped,
                        "failures": failures,
                        "lastError": str(error),
                    },
                    stage="grid_reinference",
                    current=processed + skipped + failures,
                    total=total,
                    success_count=processed,
                    failure_count=failures,
                    review_count=0,
                )
                continue
            with self._session_factory() as session, session.begin():
                locked = session.scalar(
                    select(ImageReviewItemModel)
                    .where(ImageReviewItemModel.id == item.id)
                    .with_for_update()
                )
                locked_board = session.get(RecognizedBoardModel, board.id, with_for_update=True)
                if (
                    locked is None
                    or locked.status != "pending"
                    or locked_board is None
                    or locked_board.geometry_revision != board.geometry_revision
                ):
                    skipped += 1
                else:
                    revision = locked_board.geometry_revision + 1
                    command_sha = hashlib.sha256(
                        json.dumps(
                            {
                                "boardId": str(board.id),
                                "profile": fingerprint,
                                "board": board_checksum,
                            },
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode("ascii")
                    ).hexdigest()
                    idempotency_key = uuid5(
                        NAMESPACE_URL,
                        f"image-grid-reinference:{board.id}:{fingerprint}",
                    )
                    existing = session.scalar(
                        select(ImageBoardGeometryRevisionModel).where(
                            ImageBoardGeometryRevisionModel.review_item_id == item.id,
                            ImageBoardGeometryRevisionModel.idempotency_key == idempotency_key,
                        )
                    )
                    if existing is None:
                        session.add(
                            ImageBoardGeometryRevisionModel(
                                review_item_id=item.id,
                                recognized_board_id=board.id,
                                revision=revision,
                                idempotency_key=idempotency_key,
                                command_sha256=command_sha,
                                corners=cast(list[dict[str, int]], geometry["quad"]),
                                geometry=geometry,
                                board_relative_path=board_path,
                                board_checksum_sha256=board_checksum,
                                cropper_version="board-cell-crops-v17-source-direct-model-input-v1",
                                crop_artifacts=crops,
                                corrected_by="grid-reinference",
                            )
                        )
                        locked_board.geometry_revision = revision
                        locked_board.board_geometry = geometry
                        locked_board.board_relative_path = board_path
                        locked_board.board_checksum_sha256 = board_checksum
                        session.flush()
                        SqlAlchemyBoardSearchProjectionRepository(session).sync_review_item(item.id)
                        SymbolCellReviewWriteThroughCoordinator(
                            session
                        ).synchronize_after_geometry_change(
                            game_id=job.game_id,
                            review_item_id=item.id,
                            actor="system:pending-grid-reinference-v1",
                        )
                    processed += 1
            context.checkpoint(
                checkpoint_payload={
                    "schema_version": 1,
                    "kind": "pending-grid-reinference-v1",
                    "processed": processed,
                    "skippedConcurrentResolution": skipped,
                    "failures": failures,
                },
                stage="grid_reinference",
                current=processed + skipped + failures,
                total=total,
                success_count=processed,
                failure_count=failures,
                review_count=0,
            )

    def _run_v2(self, context: JobExecutionContext, job: Job) -> None:
        """Persist accepted v19 crops only while the review item is still pending."""

        if job.game_id is None:
            raise JobHandlerError("IMAGE_GRID_REINFERENCE_GAME_MISSING", "The game is missing.")
        cell_output_size = _cell_output_size_from_payload(job)
        try:
            recrop_snapshot = validate_board_cell_recrop_snapshot(
                job.input_payload.get("board_cell_recrop"),
                cell_output_size=cell_output_size,
            )
        except (BoardCellRecropSnapshotError, TypeError, ValueError) as error:
            raise JobHandlerError(
                "IMAGE_BOARD_CELL_RECROP_SNAPSHOT_INVALID",
                "The accepted v19 board-cell recrop snapshot is invalid.",
            ) from error
        fingerprint = cast(str, recrop_snapshot["configurationFingerprintSha256"])
        cropper = BoardCellGeometrySourceDirectCropper(cell_output_size=cell_output_size)
        rows = self._pending_v19_rows(job.game_id)
        total = len(rows)
        processed = 0
        already_current = 0
        skipped = 0
        needs_review = 0
        failures = 0
        last_error: str | None = None
        cached_source_id: UUID | None = None
        cached_source_rgb: np.ndarray | None = None
        if total == 0:
            self._checkpoint_v2(
                context,
                total=0,
                processed=0,
                already_current=0,
                skipped=0,
                needs_review=0,
                failures=0,
                last_error=None,
            )
            return
        for snapshot in rows:
            if _is_current_v19_geometry(snapshot.board_geometry):
                already_current += 1
                self._checkpoint_v2(
                    context,
                    total=total,
                    processed=processed,
                    already_current=already_current,
                    skipped=skipped,
                    needs_review=needs_review,
                    failures=failures,
                    last_error=last_error,
                )
                continue
            try:
                if cached_source_id != snapshot.source_image_id:
                    cached_source_rgb = self._load_verified_source(snapshot)
                    cached_source_id = snapshot.source_image_id
                assert cached_source_rgb is not None
                prepared = self._prepare_v19_refresh(
                    snapshot,
                    cropper=cropper,
                    configuration_fingerprint=fingerprint,
                    source_rgb=cached_source_rgb,
                )
                result = self._commit_v19_refresh(
                    snapshot,
                    prepared=prepared,
                    configuration_fingerprint=fingerprint,
                )
                if result == "processed":
                    processed += 1
                elif result == "current":
                    already_current += 1
                else:
                    skipped += 1
            except _V19NeedsReview as error:
                needs_review += 1
                last_error = error.code
            except (OSError, UnidentifiedImageError, ValueError) as error:
                failures += 1
                last_error = str(error)
            self._checkpoint_v2(
                context,
                total=total,
                processed=processed,
                already_current=already_current,
                skipped=skipped,
                needs_review=needs_review,
                failures=failures,
                last_error=last_error,
            )

    def _pending_v19_rows(self, game_id: UUID) -> list[_PendingBoardSnapshot]:
        with self._session_factory() as session:
            rows = session.execute(
                select(
                    ImageReviewItemModel,
                    RecognizedBoardModel,
                    SourceImageModel,
                    ImageImportJobFileModel.order_index,
                )
                .join(
                    RecognizedBoardModel,
                    RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
                )
                .join(
                    SourceImageModel,
                    SourceImageModel.id == RecognizedBoardModel.source_image_id,
                )
                .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
                .outerjoin(
                    ImageImportJobFileModel,
                    and_(
                        ImageImportJobFileModel.job_id == SourceImageModel.import_job_id,
                        ImageImportJobFileModel.file_execution_key
                        == SourceImageModel.file_execution_key,
                    ),
                )
                .where(
                    JobModel.game_id == game_id,
                    JobModel.status == JobStatus.WAITING_FOR_REVIEW,
                    ImageReviewItemModel.status == "pending",
                )
                .order_by(
                    ImageImportJobFileModel.order_index,
                    RecognizedBoardModel.position_index,
                    ImageReviewItemModel.id,
                )
            ).tuples()
            return [
                _PendingBoardSnapshot(
                    review_item_id=item.id,
                    resolution_revision=item.resolution_revision,
                    recognized_board_id=board.id,
                    geometry_revision=board.geometry_revision,
                    source_image_id=source.id,
                    import_job_id=source.import_job_id,
                    source_order_index=order_index,
                    sequence_number=board.sequence_number,
                    position_index=board.position_index,
                    board_geometry=dict(board.board_geometry),
                    board_relative_path=board.board_relative_path,
                    board_checksum_sha256=board.board_checksum_sha256,
                    source_relative_path=source.relative_path,
                    source_checksum_sha256=source.checksum_sha256,
                    source_width=source.width,
                    source_height=source.height,
                )
                for item, board, source, order_index in rows
            ]

    def _prepare_v19_refresh(
        self,
        snapshot: _PendingBoardSnapshot,
        *,
        cropper: BoardCellGeometrySourceDirectCropper,
        configuration_fingerprint: str,
        source_rgb: np.ndarray | None = None,
    ) -> _PreparedV19Refresh:
        if snapshot.source_order_index is None:
            raise _V19NeedsReview("BOARD_CELL_RECROP_SOURCE_ORDER_MISSING")
        if snapshot.sequence_number is None:
            raise _V19NeedsReview("BOARD_CELL_RECROP_SEQUENCE_UNRESOLVED")
        rgb = self._load_verified_source(snapshot) if source_rgb is None else source_rgb
        image_height, image_width = rgb.shape[:2]
        board_quad = _board_quad_from_geometry(snapshot.board_geometry)
        estimate = estimate_board_cell_geometry(rgb, board_quad)
        if (
            estimate.status != "estimated"
            or estimate.lattice_bounds_quad is None
            or estimate.evidence is None
            or len(estimate.cells) != 15
        ):
            raise _V19NeedsReview(
                estimate.fallback_reason or "BOARD_CELL_GEOMETRY_AUTOMATIC_EVIDENCE_INSUFFICIENT"
            )
        entry = BoardCellGeometryEntry(
            source_order_index=snapshot.source_order_index,
            image_id=str(snapshot.source_image_id),
            source_image_checksum_sha256=snapshot.source_checksum_sha256,
            source_image_relative_path=snapshot.source_relative_path,
            source_image_width=image_width,
            source_image_height=image_height,
            source_group=str(snapshot.import_job_id),
            condition_tags=("pending-only-recrop",),
            sequence_number=snapshot.sequence_number,
            position_index=snapshot.position_index,
            lattice_bounds_quad=estimate.lattice_bounds_quad,
            cells=estimate.cells,
            evidence=estimate.evidence,
        )
        cropped = cropper.crop(rgb, entry)
        if cropped.status != "cropped" or len(cropped.cells) != 15:
            raise _V19NeedsReview(
                cropped.review_reasons[0]
                if cropped.review_reasons
                else "BOARD_CELL_CROP_RESULT_INCOMPLETE"
            )
        cells = tuple(
            _PreparedCell(
                row_index=cell.row_index,
                column_index=cell.column_index,
                png=(png := _png_bytes(cell.rgb)),
                checksum_sha256=hashlib.sha256(png).hexdigest(),
                source_quad=cell.source_quad,
                padded_source_quad=cell.padded_source_quad,
            )
            for cell in cropped.cells
        )
        geometry = _v19_geometry_payload(
            snapshot,
            entry=entry,
            cells=cells,
            cropper=cropper,
            configuration_fingerprint=configuration_fingerprint,
        )
        command_sha256 = _sha256_payload(
            {
                "boardId": str(snapshot.recognized_board_id),
                "configurationFingerprintSha256": configuration_fingerprint,
                "expectedGeometryRevision": snapshot.geometry_revision,
                "expectedResolutionRevision": snapshot.resolution_revision,
                "geometry": geometry,
                "sourceImageChecksumSha256": snapshot.source_checksum_sha256,
            }
        )
        return _PreparedV19Refresh(
            geometry=geometry,
            lattice_bounds_quad=entry.lattice_bounds_quad,
            cells=cells,
            command_sha256=command_sha256,
        )

    def _load_verified_source(self, snapshot: _PendingBoardSnapshot) -> np.ndarray:
        source_path = _source_path(self._artifact_root, snapshot.source_relative_path)
        source_content = source_path.read_bytes()
        if hashlib.sha256(source_content).hexdigest() != snapshot.source_checksum_sha256:
            raise ValueError("The pending board source checksum changed before recropping.")
        with Image.open(io.BytesIO(source_content)) as image:
            rgb = cast(
                np.ndarray,
                np.asarray(
                    ImageOps.exif_transpose(image).convert("RGB"),
                    dtype=np.uint8,
                ),
            )
        image_height, image_width = rgb.shape[:2]
        if (image_width, image_height) != (snapshot.source_width, snapshot.source_height):
            raise ValueError("The pending board source dimensions changed before recropping.")
        return rgb

    def _commit_v19_refresh(
        self,
        snapshot: _PendingBoardSnapshot,
        *,
        prepared: _PreparedV19Refresh,
        configuration_fingerprint: str,
    ) -> str:
        idempotency_key = uuid5(
            NAMESPACE_URL,
            f"pending-board-cell-recrop-v19:{snapshot.recognized_board_id}:"
            f"{configuration_fingerprint}",
        )
        with self._session_factory() as session, session.begin():
            locked_item = session.scalar(
                select(ImageReviewItemModel)
                .where(ImageReviewItemModel.id == snapshot.review_item_id)
                .with_for_update()
            )
            locked_board = session.get(
                RecognizedBoardModel,
                snapshot.recognized_board_id,
                with_for_update=True,
            )
            if not _pending_projection_matches(
                snapshot,
                item=locked_item,
                board=locked_board,
            ):
                return "skipped"
            assert locked_board is not None
            if _is_current_v19_geometry(locked_board.board_geometry):
                return "current"
            existing = session.scalar(
                select(ImageBoardGeometryRevisionModel).where(
                    ImageBoardGeometryRevisionModel.review_item_id == snapshot.review_item_id,
                    ImageBoardGeometryRevisionModel.idempotency_key == idempotency_key,
                )
            )
            if existing is not None:
                if existing.command_sha256 != prepared.command_sha256:
                    raise ValueError("The v19 recrop idempotency key represents another command.")
                raise ValueError(
                    "The persisted v19 recrop revision is not the current board projection."
                )
            revision = locked_board.geometry_revision + 1
            crop_artifacts = _persist_v19_cells(
                self._artifact_root,
                snapshot=snapshot,
                revision=revision,
                cells=prepared.cells,
            )
            session.add(
                ImageBoardGeometryRevisionModel(
                    review_item_id=snapshot.review_item_id,
                    recognized_board_id=snapshot.recognized_board_id,
                    revision=revision,
                    idempotency_key=idempotency_key,
                    command_sha256=prepared.command_sha256,
                    corners=[
                        {"x": round(x), "y": round(y)} for x, y in prepared.lattice_bounds_quad
                    ],
                    geometry=prepared.geometry,
                    board_relative_path=snapshot.board_relative_path,
                    board_checksum_sha256=snapshot.board_checksum_sha256,
                    cropper_version=CROPPER_VERSION,
                    crop_artifacts=crop_artifacts,
                    corrected_by=_V19_CORRECTED_BY,
                )
            )
            locked_board.geometry_revision = revision
            locked_board.board_geometry = prepared.geometry
            session.flush()
            job = session.get(JobModel, snapshot.import_job_id)
            if job is None or job.game_id is None:
                raise ValueError("The v19 crop refresh lost its import-game context.")
            SqlAlchemyBoardSearchProjectionRepository(session).sync_review_item(
                snapshot.review_item_id
            )
            SymbolCellReviewWriteThroughCoordinator(session).synchronize_after_geometry_change(
                game_id=job.game_id,
                review_item_id=snapshot.review_item_id,
                actor=_V19_CORRECTED_BY,
            )
            return "processed"

    @staticmethod
    def _checkpoint_v2(
        context: JobExecutionContext,
        *,
        total: int,
        processed: int,
        already_current: int,
        skipped: int,
        needs_review: int,
        failures: int,
        last_error: str | None,
    ) -> None:
        payload: dict[str, object] = {
            "schema_version": 1,
            "kind": "pending-board-cell-recrop-v19-v1",
            "processed": processed,
            "alreadyCurrentV19": already_current,
            "skippedConcurrentResolution": skipped,
            "needsManualGeometry": needs_review,
            "failures": failures,
        }
        if last_error is not None:
            payload["lastError"] = last_error
        context.checkpoint(
            checkpoint_payload=payload,
            stage="board_cell_recrop_v19",
            current=processed + already_current + skipped + needs_review + failures,
            total=total,
            success_count=processed + already_current,
            failure_count=failures,
            review_count=needs_review,
        )

    def _refresh_board(
        self,
        source: SourceImageModel,
        *,
        position_index: int,
        profile: Mapping[str, object],
        fingerprint: str,
        cell_output_size: int,
    ) -> tuple[dict[str, object], str, str, list[dict[str, object]]]:
        path = _source_path(self._artifact_root, source.relative_path)
        with Image.open(path) as image:
            rgb = np.asarray(ImageOps.exif_transpose(image).convert("RGB"), dtype=np.uint8)
        detected = self._detector.detect(
            rgb,
            allow_grid_recovery=True,
            allow_occluded_grid_recovery=True,
            allow_partial_grid_recovery=True,
        )
        if detected.status != "detected" or len(detected.layout_hypotheses) > 1:
            raise ValueError("Grid detection did not yield a unique layout.")
        selected = next(
            (board for board in detected.boards if board.position_index == position_index),
            None,
        )
        if selected is None:
            raise ValueError("The pending board position is absent from the refreshed grid.")
        calibrated_boards = tuple(
            BoardGeometry(
                position_index=detected_board.position_index,
                quad=_calibrated_quad(
                    detected_board.quad,
                    profile=profile,
                    image_selection_run_id=None,
                    position_index=detected_board.position_index,
                    image_width=int(rgb.shape[1]),
                    image_height=int(rgb.shape[0]),
                ),
            )
            for detected_board in detected.boards
        )
        calibrated = next(
            board.quad for board in calibrated_boards if board.position_index == position_index
        )
        page = PageGeometry(
            status="detected",
            image_width=int(rgb.shape[1]),
            image_height=int(rgb.shape[0]),
            boards=calibrated_boards,
        )
        cropped = SourceDirectBoardCellCropper(cell_output_size=cell_output_size).crop(rgb, page)
        if cropped.status != "cropped":
            raise ValueError("The refreshed grid could not be cropped.")
        result = next(
            (
                candidate
                for candidate in cropped.boards
                if candidate.position_index == position_index
            ),
            None,
        )
        if result is None:
            raise ValueError("The refreshed grid crop is missing the pending position.")
        root = PurePosixPath(
            "crops",
            "grid-reinference",
            fingerprint[:16],
            source.checksum_sha256[:2],
            source.checksum_sha256,
            f"board-{position_index:02d}",
        )
        board_relative = (root / "source-context.png").as_posix()
        board_checksum = _write_png(self._artifact_root, board_relative, result.context_rgb)
        crop_artifacts: list[dict[str, object]] = []
        for cell in result.cells:
            relative = (
                root / "cells" / f"r{cell.row_index:02d}-c{cell.column_index:02d}.png"
            ).as_posix()
            crop_artifacts.append(
                {
                    "columnIndex": cell.column_index,
                    "cropChecksumSha256": _write_png(self._artifact_root, relative, cell.rgb),
                    "cropRelativePath": relative,
                    "rowIndex": cell.row_index,
                }
            )
        geometry: dict[str, object] = {
            "detectorQuad": [point.to_dict() for point in selected.quad],
            "quad": [point.to_dict() for point in calibrated],
            "displayAssetKind": "source_context",
            "sourceContextBounds": result.context_bounds.to_dict(),
            "gridProfileFingerprint": fingerprint,
        }
        return geometry, board_relative, board_checksum, crop_artifacts


def _board_quad_from_geometry(
    geometry: Mapping[str, object],
) -> tuple[DetectorPoint, DetectorPoint, DetectorPoint, DetectorPoint]:
    raw = geometry.get("pageBoardQuad") or geometry.get("quad")
    if not isinstance(raw, list | tuple) or len(raw) != 4:
        raise _V19NeedsReview("BOARD_CELL_RECROP_PAGE_QUAD_MISSING")
    points: list[DetectorPoint] = []
    for value in raw:
        if not isinstance(value, Mapping):
            raise _V19NeedsReview("BOARD_CELL_RECROP_PAGE_QUAD_INVALID")
        try:
            x = float(value["x"])
            y = float(value["y"])
        except (KeyError, TypeError, ValueError, OverflowError) as error:
            raise _V19NeedsReview("BOARD_CELL_RECROP_PAGE_QUAD_INVALID") from error
        if not math.isfinite(x) or not math.isfinite(y) or x < 0 or y < 0:
            raise _V19NeedsReview("BOARD_CELL_RECROP_PAGE_QUAD_INVALID")
        points.append(DetectorPoint(round(x), round(y)))
    return cast(
        tuple[DetectorPoint, DetectorPoint, DetectorPoint, DetectorPoint],
        tuple(points),
    )


def _v19_geometry_payload(
    snapshot: _PendingBoardSnapshot,
    *,
    entry: BoardCellGeometryEntry,
    cells: tuple[_PreparedCell, ...],
    cropper: BoardCellGeometrySourceDirectCropper,
    configuration_fingerprint: str,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "cellOutputSize": cropper.cell_output_size,
        "cells": [
            {
                "columnIndex": cell.column_index,
                "cropChecksumSha256": cell.checksum_sha256,
                "paddedSourceQuad": _quad_payload(cell.padded_source_quad),
                "rowIndex": cell.row_index,
                "sourceQuad": _quad_payload(cell.source_quad),
            }
            for cell in cells
        ],
        "configurationFingerprintSha256": configuration_fingerprint,
        "coordinateSpace": BOARD_CELL_COORDINATE_SPACE,
        "cornerSemantics": BOARD_CELL_CORNER_SEMANTICS,
        "cropperFingerprintSha256": cropper.fingerprint_sha256,
        "cropperVersion": CROPPER_VERSION,
        "estimatorVersion": ESTIMATOR_VERSION,
        "evidence": entry.evidence.to_dict(),
        "geometryVersion": BOARD_CELL_GEOMETRY_VERSION,
        "imageHeight": entry.source_image_height,
        "imageWidth": entry.source_image_width,
        "latticeBoundsQuad": _quad_payload(entry.lattice_bounds_quad),
        "pageBoardQuad": _quad_payload(
            tuple(
                (float(point.x), float(point.y))
                for point in _board_quad_from_geometry(snapshot.board_geometry)
            )
        ),
        "positionIndex": entry.position_index,
        "sequenceNumber": entry.sequence_number,
        "source": "automatic",
        "sourceGroup": entry.source_group,
        "sourceImageChecksumSha256": entry.source_image_checksum_sha256,
        "sourceImageId": entry.image_id,
        "sourceImageRelativePath": entry.source_image_relative_path,
        "sourceOrderIndex": entry.source_order_index,
    }
    for key in (
        "attestedRangeEnd",
        "attestedRangeStart",
        "displayAssetKind",
        "sequenceLabelQuad",
        "sequenceSource",
        "sourceContextBounds",
    ):
        value = snapshot.board_geometry.get(key)
        if value is not None:
            payload[key] = value
    return payload


def _pending_projection_matches(
    snapshot: _PendingBoardSnapshot,
    *,
    item: ImageReviewItemModel | None,
    board: RecognizedBoardModel | None,
) -> bool:
    return bool(
        item is not None
        and item.status == "pending"
        and item.resolution_revision == snapshot.resolution_revision
        and board is not None
        and board.id == snapshot.recognized_board_id
        and board.source_image_id == snapshot.source_image_id
        and board.geometry_revision == snapshot.geometry_revision
        and board.position_index == snapshot.position_index
        and board.sequence_number == snapshot.sequence_number
        and board.board_relative_path == snapshot.board_relative_path
        and board.board_checksum_sha256 == snapshot.board_checksum_sha256
        and dict(board.board_geometry) == snapshot.board_geometry
    )


def _is_current_v19_geometry(
    geometry: Mapping[str, object],
) -> bool:
    return bool(
        geometry.get("geometryVersion") == BOARD_CELL_GEOMETRY_VERSION
        and geometry.get("cropperVersion") == CROPPER_VERSION
    )


def _persist_v19_cells(
    root: Path,
    *,
    snapshot: _PendingBoardSnapshot,
    revision: int,
    cells: tuple[_PreparedCell, ...],
) -> list[dict[str, object]]:
    board_key = hashlib.sha256(str(snapshot.recognized_board_id).encode("ascii")).hexdigest()[:16]
    namespace = PurePosixPath(
        "image-review-board-cell-geometry-v19",
        board_key,
        f"r{revision}",
    )
    artifacts: list[dict[str, object]] = []
    for cell in cells:
        relative = str(
            namespace / (f"cell-r{cell.row_index}-c{cell.column_index}-{cell.checksum_sha256}.png")
        )
        _write_immutable_bytes(root, relative, cell.png)
        artifacts.append(
            {
                "columnIndex": cell.column_index,
                "cropChecksumSha256": cell.checksum_sha256,
                "cropRelativePath": relative,
                "rowIndex": cell.row_index,
            }
        )
    return artifacts


def _quad_payload(
    quad: tuple[tuple[float, float], ...],
) -> list[dict[str, float]]:
    return [{"x": round(x, 4), "y": round(y, 4)} for x, y in quad]


def _sha256_payload(value: Mapping[str, object]) -> str:
    content = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return hashlib.sha256(content).hexdigest()


def _png_bytes(rgb: np.ndarray) -> bytes:
    output = io.BytesIO()
    Image.fromarray(rgb, mode="RGB").save(
        output,
        format="PNG",
        optimize=False,
        compress_level=6,
    )
    return output.getvalue()


def _write_immutable_bytes(root: Path, relative: str, content: bytes) -> None:
    path = _source_path(root, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError("An immutable v19 board-cell crop contains different bytes.")
        return
    path.write_bytes(content)


def _source_path(root: Path, relative: str) -> Path:
    candidate = PurePosixPath(relative)
    if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise ValueError("Source path is unsafe.")
    path = (root / "data" / Path(*candidate.parts)).resolve()
    data_root = (root / "data").resolve()
    if not path.is_relative_to(data_root):
        raise ValueError("Source path escapes artifact storage.")
    return path


def _write_png(root: Path, relative: str, rgb: np.ndarray) -> str:
    path = _source_path(root, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    output = io.BytesIO()
    Image.fromarray(rgb, mode="RGB").save(output, format="PNG", optimize=False, compress_level=6)
    content = output.getvalue()
    checksum = hashlib.sha256(content).hexdigest()
    if path.exists() and path.read_bytes() != content:
        raise ValueError("An immutable grid crop already contains different bytes.")
    if not path.exists():
        path.write_bytes(content)
    return checksum


def _profile_from_payload(job: Job) -> tuple[Mapping[str, object], str]:
    raw = job.input_payload.get("grid_profile")
    if not isinstance(raw, Mapping):
        raise JobHandlerError("IMAGE_GRID_PROFILE_SNAPSHOT_INVALID", "The grid profile is missing.")
    profile = raw.get("profilePayload")
    fingerprint = raw.get("inferenceFingerprint")
    if (
        not isinstance(profile, Mapping)
        or not isinstance(fingerprint, str)
        or len(fingerprint) != 64
    ):
        raise JobHandlerError("IMAGE_GRID_PROFILE_SNAPSHOT_INVALID", "The grid profile is invalid.")
    return profile, fingerprint


def _cell_output_size_from_payload(job: Job) -> int:
    value = job.input_payload.get("cell_output_size", 64)
    if isinstance(value, bool) or not isinstance(value, int) or value < 16:
        raise JobHandlerError(
            "IMAGE_GRID_REINFERENCE_CELL_SIZE_INVALID",
            "The pending grid crop output size is invalid.",
        )
    return cast(int, value)


__all__ = ["PendingGridReinferenceHandler"]
