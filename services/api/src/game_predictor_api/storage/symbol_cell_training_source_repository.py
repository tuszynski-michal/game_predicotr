"""Bounded source query for approved symbol-cell training candidates."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from game_predictor_worker.symbols.protected_sources import (
    ProtectedSourceError,
    load_protected_sources,
    source_pixel_identity,
)
from PIL import Image, ImageStat
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from game_predictor_api.application.verified_training_cohorts import (
    SymbolCellTrainingSourceInventory,
    SymbolCellTrainingSourceRepository,
)
from game_predictor_api.application.virtual_cell_previews import render_virtual_symbol_cell_png
from game_predictor_api.domain.catalog import SymbolStatus
from game_predictor_api.domain.image_reviews import ImageReviewConflictError
from game_predictor_api.domain.image_symbol_reviews import (
    SymbolCellApprovedCropIdentity,
    SymbolCellAssignmentSource,
    SymbolCellCropIdentity,
    SymbolCellReview,
    SymbolCellReviewAsset,
    SymbolCellReviewError,
    SymbolCellReviewState,
    is_symbol_cell_training_eligible,
)
from game_predictor_api.domain.symbol_cell_training_cohorts import (
    ApprovedSymbolCellCandidate,
)
from game_predictor_api.domain.verified_training_cohorts import (
    SymbolCellTrainingExclusionCounts,
)
from game_predictor_api.storage.cell_render_specs import (
    CellRenderSpecKey,
    load_cell_render_specs,
)
from game_predictor_api.storage.models import GameModel, SymbolModel

_SOURCE_SAMPLE_CAP = 64
_SYMBOL_PREPOOL_CAP = 4_000
_MAX_DESCRIPTOR_WORKERS = 7


class SqlAlchemySymbolCellTrainingSourceRepository(SymbolCellTrainingSourceRepository):
    def __init__(self, session: Session, artifact_root: Path) -> None:
        self._session = session
        self._artifact_root = artifact_root.resolve()

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

    def inventory(self, *, game_id: UUID, lock_game: bool) -> SymbolCellTrainingSourceInventory:
        game_query = select(GameModel).where(GameModel.id == game_id)
        if lock_game:
            game_query = game_query.with_for_update()
        if self._session.scalar(game_query) is None:
            raise ImageReviewConflictError(
                "VERIFIED_TRAINING_COHORT_GAME_NOT_FOUND",
                "The selected training cohort game does not exist.",
            )
        exclusions = self._exclusion_counts(game_id)
        try:
            protected = load_protected_sources(self._artifact_root, str(game_id))
            protected_bytes = [] if protected is None else sorted(protected.byte_checksums)
            protected_pixels = [] if protected is None else sorted(protected.pixel_checksums)
            protected_cell_count = 0
            if protected is not None:
                protected_cell_count = int(
                    self._session.execute(
                        text("""
                    SELECT count(c.id)
                    FROM source_images src
                    JOIN recognized_boards rb ON rb.source_image_id = src.id
                    JOIN image_symbol_review_cells c ON c.recognized_board_id = rb.id
                    LEFT JOIN image_source_geometry_revisions sgr
                      ON sgr.id = c.source_geometry_revision_id
                    WHERE c.game_id = :game_id AND c.review_state = 'approved'
                      AND (src.checksum_sha256 = ANY(CAST(:protected_bytes AS text[]))
                        OR (sgr.source_checksum_sha256 = src.checksum_sha256
                          AND sgr.normalized_pixel_checksum_sha256 =
                            ANY(CAST(:protected_pixels AS text[]))))
                """),
                        {
                            "game_id": game_id,
                            "protected_bytes": protected_bytes,
                            "protected_pixels": protected_pixels,
                        },
                    ).scalar_one()
                )
        except ProtectedSourceError as error:
            raise ImageReviewConflictError(error.code, str(error)) from error
        selected = tuple(
            self._session.execute(
                text(
                    """
                WITH eligible AS (
                  -- D-467 S7: explicit columns; the render specification is
                  -- read from the board render manifest below, not the cell.
                  SELECT c.id, c.game_id, c.import_job_id, c.review_item_id, c.recognized_board_id,
                         c.sequence_number, c.cell_index, c.revision, c.asset_mode,
                         c.source_geometry_revision_id, c.logical_cell_key,
                         c.logical_cell_key_v2, c.render_identity_v2_sha256,
                         c.render_spec_checksum_sha256, c.rendered_pixel_checksum_sha256,
                         c.extractor_version, c.crop_sample_id, c.crop_relative_path,
                         c.crop_checksum_sha256, c.geometry_revision, c.cropper_version,
                         c.prediction_symbol_code, c.assigned_symbol_id,
                         c.approved_crop_sample_id, c.approved_crop_checksum_sha256,
                         c.approved_geometry_revision,
                         s.code AS symbol_code,
                         rb.source_image_id AS source_image_id,
                         rb.geometry_revision AS current_geometry_revision,
                         rb.source_geometry_revision_id AS current_source_geometry_revision_id,
                         src.relative_path AS source_relative_path,
                         src.checksum_sha256 AS source_checksum_sha256,
                         sgr.normalized_pixel_checksum_sha256 AS normalized_pixel_checksum_sha256,
                         sgr.geometry_checksum_sha256 AS geometry_checksum_sha256,
                         row_number() OVER (
                           PARTITION BY c.assigned_symbol_id, rb.source_image_id
                           ORDER BY (c.prediction_symbol_code IS DISTINCT FROM s.code) DESC,
                                    c.sequence_number, c.cell_index, c.id
                         ) AS source_rank
                  FROM image_symbol_review_cells c
                  JOIN symbols s ON s.id = c.assigned_symbol_id
                  JOIN recognized_boards rb ON rb.id = c.recognized_board_id
                  JOIN source_images src ON src.id = rb.source_image_id
                  LEFT JOIN image_source_geometry_revisions sgr
                    ON sgr.id = c.source_geometry_revision_id
                  JOIN image_board_search_fast_documents d
                    ON d.game_id = c.game_id
                   AND d.sequence_number = c.sequence_number
                   AND d.review_item_id = c.review_item_id
                  WHERE c.game_id = :game_id
                    AND NOT (src.checksum_sha256 = ANY(CAST(:protected_bytes AS text[])))
                    AND NOT COALESCE(
                      sgr.source_checksum_sha256 = src.checksum_sha256
                      AND sgr.normalized_pixel_checksum_sha256 =
                        ANY(CAST(:protected_pixels AS text[])), false)
                    AND (:protected_enabled = false OR (
                      c.source_geometry_revision_id = rb.source_geometry_revision_id
                      AND sgr.source_checksum_sha256 = src.checksum_sha256
                      AND sgr.normalized_pixel_checksum_sha256 ~ '^[0-9a-f]{64}$'
                    ))
                    AND c.source_available = true
                    AND (c.source_visibility IS NULL OR c.source_visibility = 'full')
                    AND c.geometry_revision = rb.geometry_revision
                    AND c.review_state = 'approved'
                    AND c.quality_issue IS NULL
                    AND c.approved_crop_sample_id = c.crop_sample_id
                    AND c.approved_crop_checksum_sha256 = c.crop_checksum_sha256
                    AND c.approved_geometry_revision = c.geometry_revision
                    -- D-467 S6 (TASK-0796): only virtual renders exist.
                    AND c.asset_mode = 'virtual_source'
                    AND c.approved_asset_mode = 'virtual_source'
                    AND c.approved_source_geometry_revision_id = c.source_geometry_revision_id
                    AND c.approved_render_spec_checksum_sha256 = c.render_spec_checksum_sha256
                    AND c.approved_rendered_pixel_checksum_sha256 =
                        c.rendered_pixel_checksum_sha256
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
                    "protected_bytes": protected_bytes,
                    "protected_pixels": protected_pixels,
                    "protected_enabled": protected is not None,
                },
            ).mappings()
        )
        # Only the existing bounded pool pays for managed-original reads. SQL
        # uses checksum-bound geometry metadata to exclude complete protected
        # photographs before either cap; live reads independently attest it.
        if protected is not None:
            identities: dict[tuple[str, str], str] = {}
            try:
                for row in selected:
                    key = (str(row["source_relative_path"]), str(row["source_checksum_sha256"]))
                    if key not in identities:
                        identities[key] = source_pixel_identity(self._artifact_root / "data", *key)
                    pixels = identities[key]
                    if protected.excludes(key[1], pixels):
                        raise ProtectedSourceError(
                            "PROTECTED_EVALUATION_SOURCE",
                            "A protected source failed its exclusion metadata binding.",
                        )
                    if pixels != row["normalized_pixel_checksum_sha256"]:
                        raise ProtectedSourceError(
                            "PROTECTED_SOURCE_IDENTITY_DRIFT",
                            "Selected source pixels differ from checksum-bound geometry metadata.",
                        )
            except ProtectedSourceError as error:
                raise ImageReviewConflictError(error.code, str(error)) from error
        rows = _with_manifest_render_specs(self._session, game_id=game_id, rows=selected)
        worker_count = min(
            _MAX_DESCRIPTOR_WORKERS,
            max(1, os.cpu_count() or 1),
            max(1, len(rows)),
        )
        with ThreadPoolExecutor(
            max_workers=worker_count,
            thread_name_prefix="symbol-cohort-descriptor",
        ) as executor:
            candidates = tuple(
                candidate
                for candidate in executor.map(
                    lambda row: self._candidate_or_missing(row, allow_cached=not lock_game),
                    rows,
                )
                if candidate is not None
            )
        return SymbolCellTrainingSourceInventory(
            candidates=candidates,
            protected_source_exclusions=None if protected is None else protected.reference(),
            protected_cell_count=protected_cell_count,
            exclusions=SymbolCellTrainingExclusionCounts(
                unknown=exclusions.unknown,
                unreadable=exclusions.unreadable,
                grid_issue=exclusions.grid_issue,
                changed_crop=exclusions.changed_crop,
                missing_asset=exclusions.missing_asset + (len(rows) - len(candidates)),
            ),
        )

    def _exclusion_counts(self, game_id: UUID) -> SymbolCellTrainingExclusionCounts:
        values = (
            self._session.execute(
                text(
                    """
                WITH current_cells AS (
                  SELECT c.quality_issue, c.assigned_symbol_id, c.review_state,
                         c.crop_sample_id, c.crop_checksum_sha256, c.geometry_revision,
                         c.asset_mode, c.source_geometry_revision_id,
                         c.render_spec_checksum_sha256, c.rendered_pixel_checksum_sha256,
                         c.approved_crop_sample_id, c.approved_crop_checksum_sha256,
                         c.approved_geometry_revision, c.approved_asset_mode,
                         c.approved_source_geometry_revision_id,
                         c.approved_render_spec_checksum_sha256,
                         c.approved_rendered_pixel_checksum_sha256,
                         s.status AS symbol_status
                  FROM image_symbol_review_cells c
                  JOIN image_board_search_fast_documents d
                    ON d.game_id = c.game_id
                   AND d.sequence_number = c.sequence_number
                   AND d.review_item_id = c.review_item_id
                  LEFT JOIN symbols s ON s.id = c.assigned_symbol_id
                  WHERE c.game_id = :game_id
                    AND c.source_available = true
                    AND (c.source_visibility IS NULL OR c.source_visibility = 'full')
                )
                SELECT
                  count(*) FILTER (
                    WHERE quality_issue IS NULL
                      AND assigned_symbol_id IS NULL
                  ) AS unknown_count,
                  count(*) FILTER (WHERE quality_issue = 'unreadable') AS unreadable_count,
                  count(*) FILTER (WHERE quality_issue = 'grid_issue') AS grid_issue_count,
                  count(*) FILTER (
                    WHERE review_state = 'approved'
                      AND quality_issue IS NULL
                      AND assigned_symbol_id IS NOT NULL
                      AND symbol_status = 'active'
                      AND (
                        approved_crop_sample_id IS DISTINCT FROM crop_sample_id
                        OR approved_crop_checksum_sha256 IS DISTINCT FROM crop_checksum_sha256
                        OR approved_geometry_revision IS DISTINCT FROM geometry_revision
                        OR approved_asset_mode IS DISTINCT FROM asset_mode
                        OR (
                          asset_mode = 'virtual_source'
                          AND (
                            approved_source_geometry_revision_id IS DISTINCT FROM
                              source_geometry_revision_id
                            OR approved_render_spec_checksum_sha256 IS DISTINCT FROM
                              render_spec_checksum_sha256
                            OR approved_rendered_pixel_checksum_sha256 IS DISTINCT FROM
                              rendered_pixel_checksum_sha256
                          )
                        )
                      )
                  ) AS changed_crop_count
                FROM current_cells
                """
                ),
                {"game_id": game_id},
            )
            .mappings()
            .one()
        )
        return SymbolCellTrainingExclusionCounts(
            unknown=int(values["unknown_count"]),
            unreadable=int(values["unreadable_count"]),
            grid_issue=int(values["grid_issue_count"]),
            changed_crop=int(values["changed_crop_count"]),
        )

    def _candidate_or_missing(
        self, values: Mapping[str, Any], *, allow_cached: bool
    ) -> ApprovedSymbolCellCandidate | None:
        try:
            return self._candidate(values, allow_cached=allow_cached)
        except ImageReviewConflictError as error:
            if error.code in {
                "SYMBOL_CELL_TRAINING_CROP_MISSING",
                "SYMBOL_CELL_TRAINING_CROP_CHANGED",
                "SYMBOL_CELL_TRAINING_CROP_INVALID",
            }:
                return None
            raise

    def candidates(
        self, *, game_id: UUID, lock_game: bool
    ) -> tuple[ApprovedSymbolCellCandidate, ...]:
        """Compatibility adapter for callers that do not need diagnostics."""

        return self.inventory(game_id=game_id, lock_game=lock_game).candidates

    def _candidate(
        self, values: Mapping[str, Any], *, allow_cached: bool
    ) -> ApprovedSymbolCellCandidate:
        expected = str(values["crop_checksum_sha256"])
        asset_mode = str(values["asset_mode"])
        if asset_mode != "virtual_source":
            raise ImageReviewConflictError(
                "SYMBOL_CELL_TRAINING_CROP_INVALID",
                "An approved symbol crop has an unsupported asset mode.",
            )
        asset = _virtual_asset(values)
        perceptual_hash, mean_rgb = (
            _cached_verified_virtual_visual_descriptor(
                str(self._artifact_root),
                str(asset.cell_review_id),
                asset.revision,
                asset.geometry_revision,
                asset.current_geometry_revision,
                str(asset.source_geometry_revision_id),
                str(asset.current_source_geometry_revision_id),
                str(asset.source_checksum_sha256),
                str(asset.normalized_pixel_checksum_sha256),
                str(asset.geometry_checksum_sha256),
                str(asset.logical_cell_key),
                json.dumps(asset.render_spec, separators=(",", ":"), sort_keys=True),
                str(asset.render_spec_checksum_sha256),
                str(asset.rendered_pixel_checksum_sha256),
                str(asset.extractor_version),
                expected,
            )
            if allow_cached
            else _verified_virtual_visual_descriptor(self._artifact_root, asset, expected)
        )
        candidate = ApprovedSymbolCellCandidate(
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
            crop_relative_path=None,
            crop_checksum_sha256=expected,
            approved_crop_sample_id=str(values["approved_crop_sample_id"]),
            approved_crop_checksum_sha256=str(values["approved_crop_checksum_sha256"]),
            approved_geometry_revision=int(values["approved_geometry_revision"]),
            source_checksum_sha256=str(values["source_checksum_sha256"]),
            source_relative_path=str(values["source_relative_path"]),
            cropper_version=str(values["cropper_version"]),
            prediction_symbol_code=values["prediction_symbol_code"],
            perceptual_hash_64=perceptual_hash,
            mean_rgb=mean_rgb,
            asset_mode=asset_mode,
            source_geometry_revision_id=values.get("source_geometry_revision_id"),
            normalized_pixel_checksum_sha256=values.get("normalized_pixel_checksum_sha256"),
            geometry_checksum_sha256=values.get("geometry_checksum_sha256"),
            logical_cell_key=values.get("logical_cell_key"),
            logical_cell_key_v2=values.get("logical_cell_key_v2"),
            render_identity_v2_sha256=values.get("render_identity_v2_sha256"),
            render_spec=values.get("render_spec"),
            render_spec_checksum_sha256=values.get("render_spec_checksum_sha256"),
            rendered_pixel_checksum_sha256=values.get("rendered_pixel_checksum_sha256"),
            extractor_version=values.get("extractor_version"),
        )
        review = SymbolCellReview(
            crop=SymbolCellCropIdentity(
                cell_index=candidate.cell_index,
                crop_sample_id=candidate.crop_sample_id,
                crop_relative_path=candidate.crop_relative_path,
                crop_checksum_sha256=candidate.crop_checksum_sha256,
                geometry_revision=candidate.geometry_revision,
                cropper_version=candidate.cropper_version,
                asset_mode=candidate.asset_mode,
            ),
            predicted_symbol_code=candidate.prediction_symbol_code,
            assigned_symbol_code=candidate.symbol_code,
            review_state=SymbolCellReviewState.APPROVED,
            has_grid_issue=False,
            assignment_source=SymbolCellAssignmentSource.HUMAN,
            revision=candidate.cell_revision,
            approved_crop=SymbolCellApprovedCropIdentity(
                crop_sample_id=candidate.approved_crop_sample_id,
                crop_checksum_sha256=candidate.approved_crop_checksum_sha256,
                geometry_revision=candidate.approved_geometry_revision,
            ),
        )
        if not is_symbol_cell_training_eligible(
            review,
            active_symbol_codes=(candidate.symbol_code,),
            is_current_owner=True,
            asset_checksum_verified=True,
        ):
            raise ImageReviewConflictError(
                "SYMBOL_CELL_TRAINING_ELIGIBILITY_DRIFT",
                "A persisted candidate failed the shared training-eligibility predicate.",
            )
        return candidate


def _with_manifest_render_specs(
    session: Session,
    *,
    game_id: UUID,
    rows: Sequence[Mapping[Any, Any]],
) -> tuple[Mapping[str, Any], ...]:
    """Attach the manifest render specification to every virtual row (D-467 S7).

    One batched manifest read for the whole inventory; a missing manifest or a
    checksum mismatch aborts the inventory (``CellRenderSpecError``) instead of
    silently excluding the cell.
    """

    keys = {
        index: CellRenderSpecKey(
            recognized_board_id=_uuid(row["recognized_board_id"]),
            geometry_revision=int(row["geometry_revision"]),
            cell_index=int(row["cell_index"]),
            render_spec_checksum_sha256=str(row["render_spec_checksum_sha256"]),
        )
        for index, row in enumerate(rows)
        if row.get("asset_mode") == "virtual_source"
    }
    specs = load_cell_render_specs(session, game_id=game_id, keys=keys.values())
    return tuple(
        {**row, "render_spec": specs[keys[index]] if index in keys else None}
        for index, row in enumerate(rows)
    )


def _uuid(value: object) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _visual_descriptor(content: bytes) -> tuple[int, tuple[int, int, int]]:
    try:
        with Image.open(BytesIO(content)) as image:
            rgb = image.convert("RGB")
            grayscale = rgb.convert("L").resize((9, 8), Image.Resampling.BILINEAR)
            pixels = tuple(cast(Sequence[int], grayscale.get_flattened_data()))
            value = 0
            for row in range(8):
                for column in range(8):
                    value = (value << 1) | int(
                        pixels[row * 9 + column] > pixels[row * 9 + column + 1]
                    )
            red, green, blue = ImageStat.Stat(rgb.resize((1, 1))).mean
    except OSError as error:
        raise ImageReviewConflictError(
            "SYMBOL_CELL_TRAINING_CROP_INVALID",
            "An approved symbol crop is not a decodable image.",
        ) from error
    return value, (round(red), round(green), round(blue))


def _virtual_asset(values: Mapping[str, Any]) -> SymbolCellReviewAsset:
    try:
        return SymbolCellReviewAsset(
            cell_review_id=values["id"],
            crop_relative_path=None,
            crop_checksum_sha256=str(values["crop_checksum_sha256"]),
            geometry_revision=int(values["geometry_revision"]),
            current_geometry_revision=int(values["current_geometry_revision"]),
            revision=int(values["revision"]),
            asset_mode="virtual_source",
            source_checksum_sha256=str(values["source_checksum_sha256"]),
            normalized_pixel_checksum_sha256=str(values["normalized_pixel_checksum_sha256"]),
            source_geometry_revision_id=values["source_geometry_revision_id"],
            current_source_geometry_revision_id=values["current_source_geometry_revision_id"],
            geometry_checksum_sha256=str(values["geometry_checksum_sha256"]),
            logical_cell_key=str(values["logical_cell_key"]),
            render_spec=cast(Mapping[str, object], values["render_spec"]),
            render_spec_checksum_sha256=str(values["render_spec_checksum_sha256"]),
            rendered_pixel_checksum_sha256=str(values["rendered_pixel_checksum_sha256"]),
            extractor_version=str(values["extractor_version"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ImageReviewConflictError(
            "SYMBOL_CELL_TRAINING_CROP_INVALID",
            "An approved virtual symbol crop has incomplete render provenance.",
        ) from error


def _verified_virtual_visual_descriptor(
    artifact_root: Path,
    asset: SymbolCellReviewAsset,
    expected_checksum_sha256: str,
) -> tuple[int, tuple[int, int, int]]:
    if (
        asset.rendered_pixel_checksum_sha256 != expected_checksum_sha256
        or asset.crop_checksum_sha256 != expected_checksum_sha256
    ):
        raise ImageReviewConflictError(
            "SYMBOL_CELL_TRAINING_CROP_CHANGED",
            "An approved virtual symbol crop differs from its persisted pixel checksum.",
        )
    try:
        return _visual_descriptor(
            render_virtual_symbol_cell_png(artifact_root=artifact_root, asset=asset)
        )
    except SymbolCellReviewError as error:
        code = (
            "SYMBOL_CELL_TRAINING_CROP_MISSING"
            if error.code == "SYMBOL_CELL_REVIEW_PREVIEW_SOURCE_UNAVAILABLE"
            else "SYMBOL_CELL_TRAINING_CROP_CHANGED"
        )
        raise ImageReviewConflictError(code, str(error)) from error


@lru_cache(maxsize=32_768)
def _cached_verified_virtual_visual_descriptor(
    artifact_root_text: str,
    cell_review_id: str,
    revision: int,
    geometry_revision: int,
    current_geometry_revision: int,
    source_geometry_revision_id: str,
    current_source_geometry_revision_id: str,
    source_checksum_sha256: str,
    normalized_pixel_checksum_sha256: str,
    geometry_checksum_sha256: str,
    logical_cell_key: str,
    render_spec_json: str,
    render_spec_checksum_sha256: str,
    rendered_pixel_checksum_sha256: str,
    extractor_version: str,
    expected_checksum_sha256: str,
) -> tuple[int, tuple[int, int, int]]:
    asset = SymbolCellReviewAsset(
        cell_review_id=UUID(cell_review_id),
        crop_relative_path=None,
        crop_checksum_sha256=expected_checksum_sha256,
        geometry_revision=geometry_revision,
        current_geometry_revision=current_geometry_revision,
        revision=revision,
        asset_mode="virtual_source",
        source_checksum_sha256=source_checksum_sha256,
        normalized_pixel_checksum_sha256=normalized_pixel_checksum_sha256,
        source_geometry_revision_id=UUID(source_geometry_revision_id),
        current_source_geometry_revision_id=UUID(current_source_geometry_revision_id),
        geometry_checksum_sha256=geometry_checksum_sha256,
        logical_cell_key=logical_cell_key,
        render_spec=cast(Mapping[str, object], json.loads(render_spec_json)),
        render_spec_checksum_sha256=render_spec_checksum_sha256,
        rendered_pixel_checksum_sha256=rendered_pixel_checksum_sha256,
        extractor_version=extractor_version,
    )
    return _verified_virtual_visual_descriptor(
        Path(artifact_root_text), asset, expected_checksum_sha256
    )


__all__ = ["SqlAlchemySymbolCellTrainingSourceRepository"]
