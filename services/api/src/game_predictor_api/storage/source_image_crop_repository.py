"""Crop eligibility reader and crop registry writes (TASK-1044, D-562).

Eligibility must see every game that shares a managed original, so it runs on
a schema-owner session and names ``game_data_v2`` explicitly; it never binds a
single game (no parameter is named like a game id). It only reads. The registry
writes go to the shared ``public.source_image_crops`` table.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from game_predictor_api.domain.source_crop import (
    SourceCropAttestation,
    cropped_original_relative_paths,
)
from game_predictor_api.domain.source_crop_eligibility import (
    CropBlobEligibility,
    CropBoardGeometry,
    CropSourceFacts,
    classify_blob,
    managed_original_relative_path,
)
from game_predictor_api.storage.source_image_crop_models import SourceImageCropModel

MAX_ELIGIBILITY_PAGE = 500
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
# Job types that never read or rewrite managed originals or their geometry.
# Any other created or processing job in the game (or a global one) may, so it
# excludes the game's originals; an unknown future type is excluded by default.
NON_IMAGE_JOB_TYPES = (
    "payout",
    "snapshot",
    "android_build",
    "validate",
    "super_game_series_derive",
    "storage_inventory",
)
_SNAPSHOT_ISOLATION = frozenset({"repeatable read", "serializable"})

_CANDIDATE_BLOBS_SQL = """
SELECT s.checksum_sha256
FROM game_data_v2.source_images s
WHERE (CAST(:after_checksum AS varchar) IS NULL OR s.checksum_sha256 > :after_checksum)
  AND (CAST(:scope_game AS uuid) IS NULL OR s.game_id = :scope_game)
  AND (CAST(:only_checksums AS varchar[]) IS NULL OR s.checksum_sha256 = ANY(:only_checksums))
GROUP BY s.checksum_sha256
ORDER BY s.checksum_sha256
LIMIT :page_size
"""

# Every source of the selected blobs, in every game: one non-eligible source
# excludes the shared original for all of them.
_SOURCE_FACTS_SQL = """
SELECT s.game_id, s.id AS source_image_id, s.import_job_id, s.checksum_sha256,
  s.relative_path, s.coordinate_space, s.oriented_width, s.oriented_height,
  s.exif_orientation, s.normalized_pixel_checksum_sha256, s.geometry_completeness_status,
  loc.status AS game_storage_status, j.status AS import_status,
  (SELECT count(*) FROM game_data_v2.recognized_boards b
    WHERE b.game_id = s.game_id AND b.source_image_id = s.id AND b.status <> 'rejected')
    AS active_board_count,
  (SELECT count(*) FROM game_data_v2.recognized_boards b
    WHERE b.game_id = s.game_id AND b.source_image_id = s.id AND b.status <> 'rejected'
      AND b.approved_geometry_revision IS DISTINCT FROM b.geometry_revision)
    AS unapproved_board_count,
  (SELECT count(*) FROM game_data_v2.recognized_boards b
    WHERE b.game_id = s.game_id AND b.source_image_id = s.id AND b.status <> 'rejected'
      AND b.completeness_status <> 'complete')
    AS incomplete_board_count,
  (SELECT count(*) FROM game_data_v2.recognized_boards b
    LEFT JOIN game_data_v2.image_source_geometry_revisions r
      ON r.game_id = b.game_id AND r.id = b.source_geometry_revision_id
    WHERE b.game_id = s.game_id AND b.source_image_id = s.id AND b.status <> 'rejected'
      AND r.status IS DISTINCT FROM 'accepted')
    AS unaccepted_revision_board_count,
  (SELECT count(*) FROM game_data_v2.image_board_geometry_pending p
    WHERE p.game_id = s.game_id AND p.source_image_id = s.id AND p.status = 'pending')
    AS pending_geometry_count,
  (SELECT count(*) FROM game_data_v2.recognized_boards b
    JOIN game_data_v2.image_symbol_review_cells c
      ON c.game_id = b.game_id AND c.recognized_board_id = b.id
    WHERE b.game_id = s.game_id AND b.source_image_id = s.id AND c.quality_issue = 'grid_issue')
    AS grid_issue_count,
  (SELECT count(*) FROM game_data_v2.grid_geometry_proposals g
    WHERE g.game_id = s.game_id AND g.import_job_id = s.import_job_id AND g.state = 'pending')
    AS pending_proposal_count,
  (SELECT count(*) FROM game_data_v2.image_page_source_exclusions e
    WHERE e.game_id = s.game_id AND e.source_checksum_sha256 = s.checksum_sha256)
    AS page_exclusion_count,
  (SELECT count(*) FROM public.jobs a
    WHERE a.status IN ('created', 'processing')
      AND (a.game_id = s.game_id OR a.game_id IS NULL)
      AND a.job_type::text <> ALL(CAST(:non_image_job_types AS text[])))
    AS active_image_job_count
FROM game_data_v2.source_images s
JOIN public.jobs j ON j.id = s.import_job_id
LEFT JOIN public.game_storage_locations loc ON loc.game_id = s.game_id
WHERE s.checksum_sha256 = ANY(:checksums)
ORDER BY s.checksum_sha256, s.game_id, s.id
"""

# The quads of the current geometry of every active board (the P1 selection).
_GEOMETRY_SQL = """
SELECT s.checksum_sha256, s.id AS source_image_id, b.id AS board_id, b.board_geometry,
  jsonb_path_query_first(r.board_geometries, '$[*] ? (@.positionIndex == $position)',
    jsonb_build_object('position', b.position_index)) AS source_entry,
  rv.corners, rv.geometry AS revision_geometry, rv.virtual_render_spec,
  m.cells AS render_manifest
FROM game_data_v2.source_images s
JOIN game_data_v2.recognized_boards b
  ON b.game_id = s.game_id AND b.source_image_id = s.id AND b.status <> 'rejected'
LEFT JOIN game_data_v2.image_source_geometry_revisions r
  ON r.game_id = b.game_id AND r.id = b.source_geometry_revision_id
LEFT JOIN game_data_v2.image_board_geometry_revisions rv
  ON rv.game_id = b.game_id AND rv.recognized_board_id = b.id
  AND rv.revision = b.geometry_revision
LEFT JOIN game_data_v2.board_render_manifests m
  ON m.game_id = b.game_id AND m.recognized_board_id = b.id
  AND m.geometry_revision = b.geometry_revision
WHERE s.checksum_sha256 = ANY(:checksums)
ORDER BY s.checksum_sha256, s.game_id, b.position_index
"""


class SourceImageCropRepository:
    """Reads eligibility across games and records verified crops."""

    def __init__(self, owner_session: Session) -> None:
        self._session = owner_session

    def eligibility(
        self,
        *,
        page_size: int = 100,
        after_checksum: str | None = None,
        scope_game: UUID | None = None,
        only_checksums: Sequence[str] | None = None,
    ) -> list[CropBlobEligibility]:
        """Classify one page of blobs, ordered by checksum (keyset pagination).

        Facts and geometry are read by separate statements, so the caller's
        transaction must be one snapshot (REPEATABLE READ or SERIALIZABLE);
        a READ COMMITTED session is refused rather than mixing two states.
        """

        if not 1 <= page_size <= MAX_ELIGIBILITY_PAGE:
            raise ValueError("page_size must be between 1 and 500")
        for checksum in (
            *(only_checksums or ()),
            *(() if after_checksum is None else (after_checksum,)),
        ):
            if _SHA256.fullmatch(checksum) is None:
                raise ValueError("checksums must be lowercase SHA-256")
        isolation = self._session.scalar(text("SELECT current_setting('transaction_isolation')"))
        if isolation not in _SNAPSHOT_ISOLATION:
            raise ValueError("SOURCE_CROP_ELIGIBILITY_SNAPSHOT_REQUIRED")
        checksums = list(
            self._session.scalars(
                text(_CANDIDATE_BLOBS_SQL),
                {
                    "after_checksum": after_checksum,
                    "scope_game": scope_game,
                    "only_checksums": None if only_checksums is None else list(only_checksums),
                    "page_size": page_size,
                },
            )
        )
        if not checksums:
            return []
        facts: dict[str, list[CropSourceFacts]] = defaultdict(list)
        for row in self._session.execute(
            text(_SOURCE_FACTS_SQL),
            {"checksums": checksums, "non_image_job_types": list(NON_IMAGE_JOB_TYPES)},
        ).mappings():
            facts[str(row["checksum_sha256"])].append(
                CropSourceFacts(
                    game_id=row["game_id"],
                    source_image_id=row["source_image_id"],
                    import_job_id=row["import_job_id"],
                    checksum_sha256=str(row["checksum_sha256"]),
                    relative_path=str(row["relative_path"]),
                    coordinate_space=row["coordinate_space"],
                    oriented_width=row["oriented_width"],
                    oriented_height=row["oriented_height"],
                    exif_orientation=row["exif_orientation"],
                    normalized_pixel_checksum_sha256=row["normalized_pixel_checksum_sha256"],
                    geometry_completeness_status=row["geometry_completeness_status"],
                    game_storage_status=row["game_storage_status"],
                    import_status=str(row["import_status"]),
                    active_board_count=int(row["active_board_count"]),
                    unapproved_board_count=int(row["unapproved_board_count"]),
                    incomplete_board_count=int(row["incomplete_board_count"]),
                    unaccepted_revision_board_count=int(row["unaccepted_revision_board_count"]),
                    pending_geometry_count=int(row["pending_geometry_count"]),
                    grid_issue_count=int(row["grid_issue_count"]),
                    pending_proposal_count=int(row["pending_proposal_count"]),
                    page_exclusion_count=int(row["page_exclusion_count"]),
                    active_image_job_count=int(row["active_image_job_count"]),
                )
            )
        boards: dict[str, list[CropBoardGeometry]] = defaultdict(list)
        for row in self._session.execute(text(_GEOMETRY_SQL), {"checksums": checksums}).mappings():
            boards[str(row["checksum_sha256"])].append(
                CropBoardGeometry(
                    source_image_id=row["source_image_id"],
                    board_id=row["board_id"],
                    documents=tuple(
                        row[key]
                        for key in (
                            "board_geometry",
                            "source_entry",
                            "corners",
                            "revision_geometry",
                            "virtual_render_spec",
                            "render_manifest",
                        )
                        if row[key] is not None
                    ),
                )
            )
        return [
            classify_blob(checksum, facts[checksum], boards[checksum]) for checksum in checksums
        ]

    def get(self, original_checksum_sha256: str) -> SourceImageCropModel | None:
        return self._session.get(SourceImageCropModel, original_checksum_sha256)

    def record_verified(
        self,
        attestation: SourceCropAttestation,
        *,
        attestation_sha256: str,
        job_id: UUID | None,
        verified_at: datetime,
    ) -> SourceImageCropModel:
        """Insert the registry row for a crop whose files were verified."""

        checksum = attestation.original_checksum_sha256
        crop_path, attestation_path = cropped_original_relative_paths(checksum)
        row = SourceImageCropModel(
            original_checksum_sha256=checksum,
            original_relative_path=managed_original_relative_path(checksum),
            original_size_bytes=attestation.original_size_bytes,
            original_normalized_pixel_checksum_sha256=(
                attestation.original_normalized_pixel_checksum_sha256
            ),
            original_width=attestation.original_width,
            original_height=attestation.original_height,
            original_exif_orientation=attestation.original_exif_orientation,
            crop_relative_path=crop_path.as_posix(),
            attestation_relative_path=attestation_path.as_posix(),
            crop_checksum_sha256=attestation.crop_checksum_sha256,
            crop_size_bytes=attestation.crop_size_bytes,
            crop_normalized_pixel_checksum_sha256=attestation.crop_normalized_pixel_checksum_sha256,
            canvas_pixel_checksum_sha256=attestation.canvas_pixel_checksum_sha256,
            attestation_sha256=attestation_sha256,
            crop_box=attestation.crop_box.as_list(),
            raw_crop_box=attestation.raw_crop_box.as_list(),
            protected_box=attestation.protected_box.as_list(),
            margin_px=attestation.margin_px,
            imcu_width=attestation.imcu_width,
            imcu_height=attestation.imcu_height,
            edge_mismatch_pixels=attestation.edge_mismatch_pixels,
            tool_version=attestation.tool_version,
            policy_version=attestation.policy_version,
            state="verified",
            job_id=job_id,
            verified_at=verified_at,
            original_deleted_at=None,
        )
        self._session.add(row)
        self._session.flush()
        return row

    def mark_original_deleted(self, original_checksum_sha256: str, *, deleted_at: datetime) -> None:
        """Record that the original file is gone; only a verified row may move."""

        row = self._session.scalar(
            select(SourceImageCropModel)
            .where(SourceImageCropModel.original_checksum_sha256 == original_checksum_sha256)
            .with_for_update()
        )
        if row is None or row.state != "verified":
            raise ValueError("SOURCE_IMAGE_CROP_NOT_VERIFIED")
        row.state = "original_deleted"
        row.original_deleted_at = deleted_at
        self._session.flush()
