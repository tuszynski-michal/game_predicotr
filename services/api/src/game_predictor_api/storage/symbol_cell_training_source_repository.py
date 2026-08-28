"""Bounded source query for approved symbol-cell training candidates."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID

from PIL import Image, ImageStat
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from game_predictor_api.application.verified_training_cohorts import (
    SymbolCellTrainingSourceRepository,
)
from game_predictor_api.domain.catalog import SymbolStatus
from game_predictor_api.domain.image_reviews import ImageReviewConflictError
from game_predictor_api.domain.symbol_cell_training_cohorts import (
    ApprovedSymbolCellCandidate,
)
from game_predictor_api.storage.models import GameModel, SymbolModel

_SOURCE_SAMPLE_CAP = 64
_SYMBOL_PREPOOL_CAP = 4_000
_MAX_DESCRIPTOR_WORKERS = 7


class SqlAlchemySymbolCellTrainingSourceRepository(SymbolCellTrainingSourceRepository):
    def __init__(self, session: Session, artifact_root: Path) -> None:
        self._session = session
        self._managed_root = artifact_root.resolve() / "data"

    def active_symbol_codes(self, game_id: UUID) -> tuple[str, ...]:
        return tuple(
            self._session.scalars(
                select(SymbolModel.code)
                .where(
                    SymbolModel.game_id == game_id,
                    SymbolModel.status == SymbolStatus.ACTIVE,
                )
                .order_by(SymbolModel.display_order, SymbolModel.code)
            ).all()
        )

    def candidates(
        self, *, game_id: UUID, lock_game: bool
    ) -> tuple[ApprovedSymbolCellCandidate, ...]:
        game_query = select(GameModel).where(GameModel.id == game_id)
        if lock_game:
            game_query = game_query.with_for_update()
        if self._session.scalar(game_query) is None:
            raise ImageReviewConflictError(
                "VERIFIED_TRAINING_COHORT_GAME_NOT_FOUND",
                "The selected training cohort game does not exist.",
            )
        rows = tuple(
            self._session.execute(
                text(
                    """
                WITH eligible AS (
                  SELECT c.*, s.code AS symbol_code,
                         rb.source_image_id AS source_image_id,
                         src.relative_path AS source_relative_path,
                         src.checksum_sha256 AS source_checksum_sha256,
                         row_number() OVER (
                           PARTITION BY c.assigned_symbol_id, rb.source_image_id
                           ORDER BY (c.prediction_symbol_code IS DISTINCT FROM s.code) DESC,
                                    c.sequence_number, c.cell_index, c.id
                         ) AS source_rank
                  FROM image_symbol_review_cells c
                  JOIN symbols s ON s.id = c.assigned_symbol_id
                  JOIN recognized_boards rb ON rb.id = c.recognized_board_id
                  JOIN source_images src ON src.id = rb.source_image_id
                  JOIN image_board_search_fast_documents d
                    ON d.game_id = c.game_id
                   AND d.sequence_number = c.sequence_number
                   AND d.review_item_id = c.review_item_id
                  WHERE c.game_id = :game_id
                    AND c.review_state = 'approved'
                    AND c.has_grid_issue = false
                    AND c.quality_issue IS NULL
                    AND s.status = 'active'
                ), pooled AS (
                  SELECT *, row_number() OVER (
                    PARTITION BY assigned_symbol_id
                    ORDER BY (prediction_symbol_code IS DISTINCT FROM symbol_code) DESC,
                             source_rank, sequence_number, cell_index, id
                  ) AS symbol_rank
                  FROM eligible WHERE source_rank <= :source_cap
                )
                SELECT * FROM pooled WHERE symbol_rank <= :symbol_cap
                ORDER BY symbol_code, symbol_rank
                """
                ),
                {
                    "game_id": game_id,
                    "source_cap": _SOURCE_SAMPLE_CAP,
                    "symbol_cap": _SYMBOL_PREPOOL_CAP,
                },
            ).mappings()
        )
        worker_count = min(
            _MAX_DESCRIPTOR_WORKERS,
            max(1, os.cpu_count() or 1),
            max(1, len(rows)),
        )
        with ThreadPoolExecutor(
            max_workers=worker_count,
            thread_name_prefix="symbol-cohort-descriptor",
        ) as executor:
            return tuple(
                executor.map(
                    lambda row: self._candidate(row, allow_cached=not lock_game),
                    rows,
                )
            )

    def _candidate(
        self, values: Mapping[str, Any], *, allow_cached: bool
    ) -> ApprovedSymbolCellCandidate:
        relative_text = str(values["crop_relative_path"])
        relative = PurePosixPath(relative_text)
        if relative.is_absolute() or ".." in relative.parts or "\\" in relative_text:
            raise ImageReviewConflictError(
                "SYMBOL_CELL_TRAINING_CROP_UNSAFE",
                "An approved symbol crop has an unsafe managed path.",
            )
        path = self._managed_root.joinpath(*relative.parts).resolve()
        if not path.is_relative_to(self._managed_root) or path.is_symlink():
            raise ImageReviewConflictError(
                "SYMBOL_CELL_TRAINING_CROP_UNSAFE",
                "An approved symbol crop is outside managed storage.",
            )
        expected = str(values["crop_checksum_sha256"])
        perceptual_hash, mean_rgb = (
            _cached_verified_visual_descriptor(str(path), expected)
            if allow_cached
            else _verified_visual_descriptor(path, expected)
        )
        return ApprovedSymbolCellCandidate(
            cell_review_id=values["id"],
            review_item_id=values["review_item_id"],
            recognized_board_id=values["recognized_board_id"],
            source_image_id=values["source_image_id"],
            import_job_id=values["import_job_id"],
            assigned_symbol_id=values["assigned_symbol_id"],
            symbol_code=str(values["symbol_code"]),
            sequence_number=int(values["sequence_number"]),
            cell_index=int(values["cell_index"]),
            cell_revision=int(values["revision"]),
            geometry_revision=int(values["geometry_revision"]),
            crop_sample_id=str(values["crop_sample_id"]),
            crop_relative_path=relative.as_posix(),
            crop_checksum_sha256=expected,
            source_checksum_sha256=str(values["source_checksum_sha256"]),
            source_relative_path=str(values["source_relative_path"]),
            cropper_version=str(values["cropper_version"]),
            prediction_symbol_code=values["prediction_symbol_code"],
            perceptual_hash_64=perceptual_hash,
            mean_rgb=mean_rgb,
        )


def _visual_descriptor(content: bytes) -> tuple[int, tuple[int, int, int]]:
    try:
        with Image.open(BytesIO(content)) as image:
            rgb = image.convert("RGB")
            grayscale = rgb.convert("L").resize((9, 8), Image.Resampling.BILINEAR)
            pixels = tuple(grayscale.get_flattened_data())
            value = 0
            for row in range(8):
                for column in range(8):
                    value = (value << 1) | int(
                        pixels[row * 9 + column] > pixels[row * 9 + column + 1]
                    )
            mean = ImageStat.Stat(rgb.resize((1, 1))).mean
    except OSError as error:
        raise ImageReviewConflictError(
            "SYMBOL_CELL_TRAINING_CROP_INVALID",
            "An approved symbol crop is not a decodable image.",
        ) from error
    return value, tuple(round(channel) for channel in mean)  # type: ignore[return-value]


def _verified_visual_descriptor(
    path: Path, expected_checksum_sha256: str
) -> tuple[int, tuple[int, int, int]]:
    try:
        content = path.read_bytes()
    except OSError as error:
        raise ImageReviewConflictError(
            "SYMBOL_CELL_TRAINING_CROP_MISSING",
            "An approved symbol crop cannot be read.",
        ) from error
    if hashlib.sha256(content).hexdigest() != expected_checksum_sha256:
        raise ImageReviewConflictError(
            "SYMBOL_CELL_TRAINING_CROP_CHANGED",
            "An approved symbol crop differs from its persisted checksum.",
        )
    return _visual_descriptor(content)


@lru_cache(maxsize=32_768)
def _cached_verified_visual_descriptor(
    path_text: str, expected_checksum_sha256: str
) -> tuple[int, tuple[int, int, int]]:
    return _verified_visual_descriptor(Path(path_text), expected_checksum_sha256)


__all__ = ["SqlAlchemySymbolCellTrainingSourceRepository"]
