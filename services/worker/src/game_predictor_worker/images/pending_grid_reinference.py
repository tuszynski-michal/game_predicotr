"""Pending-only grid and crop refresh.

This job deliberately operates on review rows that are still ``pending``.  It
never reopens a human decision and stores a new geometry revision instead of
mutating the immutable cell observations from the original import.
"""

from __future__ import annotations

import hashlib
import io
import json
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import cast
from uuid import NAMESPACE_URL, uuid5

import numpy as np
from game_predictor_api.domain.jobs import Job
from game_predictor_api.storage.models import (
    ImageBoardGeometryRevisionModel,
    ImageReviewItemModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
)
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from game_predictor_worker.jobs.runtime import JobExecutionContext, JobHandlerError

from .geometry import ClassicalPageBoardDetector
from .production_workflow import _calibrated_quad
from .rectification import BoardGeometry, PageGeometry
from .source_direct_crops import SourceDirectBoardCellCropper


class PendingGridReinferenceHandler:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        artifact_root: Path,
    ) -> None:
        self._session_factory = session_factory
        self._artifact_root = artifact_root.resolve()
        self._detector = ClassicalPageBoardDetector()
        self._cropper = SourceDirectBoardCellCropper(cell_output_size=224)

    def __call__(self, context: JobExecutionContext, job: Job) -> None:
        if job.game_id is None:
            raise JobHandlerError("IMAGE_GRID_REINFERENCE_GAME_MISSING", "The game is missing.")
        profile, fingerprint = _profile_from_payload(job)
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
                )
            except (OSError, UnidentifiedImageError, ValueError) as error:
                failures += 1
                context.checkpoint(
                    checkpoint_payload={
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
                locked_board = session.get(
                    RecognizedBoardModel, board.id, with_for_update=True
                )
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
                    processed += 1
            context.checkpoint(
                checkpoint_payload={
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

    def _refresh_board(
        self,
        source: SourceImageModel,
        *,
        position_index: int,
        profile: Mapping[str, object],
        fingerprint: str,
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
        calibrated = _calibrated_quad(
            selected.quad,
            profile=profile,
            image_selection_run_id=None,
            position_index=position_index,
            image_width=int(rgb.shape[1]),
            image_height=int(rgb.shape[0]),
        )
        page = PageGeometry(
            status="detected",
            image_width=int(rgb.shape[1]),
            image_height=int(rgb.shape[0]),
            boards=(BoardGeometry(position_index=position_index, quad=calibrated),),
        )
        cropped = self._cropper.crop(rgb, page)
        if cropped.status != "cropped" or len(cropped.boards) != 1:
            raise ValueError("The refreshed grid could not be cropped.")
        result = cropped.boards[0]
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


__all__ = ["PendingGridReinferenceHandler"]
