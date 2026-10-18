"""Pure eligibility of a managed original for a lossless crop (plan R5, D-562).

A managed original (blob) may back sources of several imports and games. It
qualifies only when every one of them qualifies and they agree on the image
identity; the protected quads are the union over all of them. Facts come from
a read-only query; this module only decides.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from game_predictor_api.domain.source_crop import (
    SOURCE_CROP_COORDINATE_SPACE,
    SUPPORTED_ORIENTATIONS,
    SourceCropError,
    protected_points_from_geometry,
)

# D-563: the review trigger moves an import between these two states by its
# pending review count; neither runs the import. A retry makes it ``created``.
SETTLED_IMPORT_STATUSES = frozenset({"completed", "waiting_for_review"})


class CropExclusion(StrEnum):
    """Stable reasons why a blob is not cropped; any reason excludes it."""

    UNMANAGED_PATH = "UNMANAGED_PATH"
    NO_COORDINATE_METADATA = "NO_COORDINATE_METADATA"
    ORIENTATION_UNSUPPORTED = "ORIENTATION_UNSUPPORTED"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    GAME_STORAGE_NOT_ACTIVE = "GAME_STORAGE_NOT_ACTIVE"
    IMPORT_NOT_SETTLED = "IMPORT_NOT_SETTLED"
    GEOMETRY_INCOMPLETE = "GEOMETRY_INCOMPLETE"
    NO_ACTIVE_BOARDS = "NO_ACTIVE_BOARDS"
    GEOMETRY_NOT_APPROVED = "GEOMETRY_NOT_APPROVED"
    BOARD_NOT_COMPLETE = "BOARD_NOT_COMPLETE"
    SOURCE_REVISION_NOT_ACCEPTED = "SOURCE_REVISION_NOT_ACCEPTED"
    PENDING_GEOMETRY_CORRECTION = "PENDING_GEOMETRY_CORRECTION"
    GRID_ISSUE = "GRID_ISSUE"
    PENDING_GRID_PROPOSAL = "PENDING_GRID_PROPOSAL"
    ACTIVE_IMAGE_JOB = "ACTIVE_IMAGE_JOB"
    PAGE_REGISTRATION_ANCHOR = "PAGE_REGISTRATION_ANCHOR"
    PAGE_SOURCE_EXCLUDED = "PAGE_SOURCE_EXCLUDED"
    NO_PROTECTED_QUADS = "NO_PROTECTED_QUADS"
    PROTECTED_QUADS_INVALID = "PROTECTED_QUADS_INVALID"
    BOARD_GEOMETRY_MISSING = "BOARD_GEOMETRY_MISSING"


@dataclass(frozen=True, slots=True)
class CropSourceFacts:
    """Read-only facts about one ``source_images`` row of a blob."""

    game_id: UUID
    source_image_id: UUID
    import_job_id: UUID
    checksum_sha256: str
    relative_path: str
    coordinate_space: str | None
    oriented_width: int | None
    oriented_height: int | None
    exif_orientation: int | None
    normalized_pixel_checksum_sha256: str | None
    geometry_completeness_status: str | None
    game_storage_status: str | None
    import_status: str
    active_board_count: int
    unapproved_board_count: int
    incomplete_board_count: int
    unaccepted_revision_board_count: int
    pending_geometry_count: int
    grid_issue_count: int
    pending_proposal_count: int
    page_exclusion_count: int
    active_image_job_count: int
    # Page-registration anchors match ORB features on the whole frame (plan rev. 2).
    registration_anchor_count: int


@dataclass(frozen=True, slots=True)
class CropBoardGeometry:
    """Stored geometry documents of one active (non-rejected) board."""

    source_image_id: UUID
    board_id: UUID
    documents: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class CropBlobEligibility:
    original_checksum_sha256: str
    original_relative_path: str
    oriented_width: int | None
    oriented_height: int | None
    exif_orientation: int | None
    normalized_pixel_checksum_sha256: str | None
    source_image_ids: tuple[UUID, ...]
    game_ids: tuple[UUID, ...]
    exclusions: tuple[CropExclusion, ...]
    protected_points: tuple[tuple[float, float], ...]

    @property
    def eligible(self) -> bool:
        return not self.exclusions


def managed_original_relative_path(checksum_sha256: str) -> str:
    """The content-addressed path of a managed original, relative to ``data``."""

    return f"originals/{checksum_sha256[:2]}/{checksum_sha256}.jpg"


def classify_blob(
    checksum_sha256: str,
    sources: Sequence[CropSourceFacts],
    boards: Iterable[CropBoardGeometry],
) -> CropBlobEligibility:
    """Decide one blob from the facts of all its sources and their boards.

    Every active board must carry its own protected quads: the union of the
    other boards' quads would otherwise hide a board the crop cannot keep.
    """

    if not sources or any(source.checksum_sha256 != checksum_sha256 for source in sources):
        raise ValueError("classify_blob needs the sources of exactly this blob")
    reasons: set[CropExclusion] = set()
    expected_path = managed_original_relative_path(checksum_sha256)
    for source in sources:
        reasons.update(_source_reasons(source, expected_path))
    identities = {
        (
            source.oriented_width,
            source.oriented_height,
            source.exif_orientation,
            source.normalized_pixel_checksum_sha256,
        )
        for source in sources
    }
    if len(identities) != 1:
        reasons.add(CropExclusion.IDENTITY_MISMATCH)
    points: list[tuple[float, float]] = []
    boards_by_source: dict[UUID, int] = {}
    source_ids = {source.source_image_id for source in sources}
    for board in boards:
        if board.source_image_id not in source_ids:
            raise ValueError("classify_blob received a board of another source")
        boards_by_source[board.source_image_id] = boards_by_source.get(board.source_image_id, 0) + 1
        try:
            board_points = protected_points_from_geometry(list(board.documents))
        except SourceCropError:
            reasons.add(CropExclusion.PROTECTED_QUADS_INVALID)
            continue
        if not board_points:
            reasons.add(CropExclusion.BOARD_GEOMETRY_MISSING)
        points.extend(board_points)
    if any(
        boards_by_source.get(source.source_image_id, 0) != source.active_board_count
        for source in sources
    ):
        reasons.add(CropExclusion.BOARD_GEOMETRY_MISSING)
    if not points and not reasons & {
        CropExclusion.PROTECTED_QUADS_INVALID,
        CropExclusion.BOARD_GEOMETRY_MISSING,
    }:
        reasons.add(CropExclusion.NO_PROTECTED_QUADS)
    first = sources[0]
    return CropBlobEligibility(
        original_checksum_sha256=checksum_sha256,
        original_relative_path=expected_path,
        oriented_width=first.oriented_width,
        oriented_height=first.oriented_height,
        exif_orientation=first.exif_orientation,
        normalized_pixel_checksum_sha256=first.normalized_pixel_checksum_sha256,
        source_image_ids=tuple(sorted(source.source_image_id for source in sources)),
        game_ids=tuple(sorted({source.game_id for source in sources})),
        exclusions=tuple(sorted(reasons)),
        protected_points=tuple(points) if not reasons else (),
    )


def _source_reasons(source: CropSourceFacts, expected_path: str) -> set[CropExclusion]:
    reasons: set[CropExclusion] = set()
    if source.relative_path != expected_path:
        reasons.add(CropExclusion.UNMANAGED_PATH)
    if (
        source.coordinate_space != SOURCE_CROP_COORDINATE_SPACE
        or not source.oriented_width
        or not source.oriented_height
        or source.normalized_pixel_checksum_sha256 is None
    ):
        reasons.add(CropExclusion.NO_COORDINATE_METADATA)
    if (
        source.exif_orientation is not None
        and source.exif_orientation not in SUPPORTED_ORIENTATIONS
    ):
        reasons.add(CropExclusion.ORIENTATION_UNSUPPORTED)
    if source.game_storage_status != "active":
        reasons.add(CropExclusion.GAME_STORAGE_NOT_ACTIVE)
    if source.import_status not in SETTLED_IMPORT_STATUSES:
        reasons.add(CropExclusion.IMPORT_NOT_SETTLED)
    if source.geometry_completeness_status != "geometry_complete":
        reasons.add(CropExclusion.GEOMETRY_INCOMPLETE)
    if source.active_board_count < 1:
        reasons.add(CropExclusion.NO_ACTIVE_BOARDS)
    for count, reason in (
        (source.unapproved_board_count, CropExclusion.GEOMETRY_NOT_APPROVED),
        (source.incomplete_board_count, CropExclusion.BOARD_NOT_COMPLETE),
        (source.unaccepted_revision_board_count, CropExclusion.SOURCE_REVISION_NOT_ACCEPTED),
        (source.pending_geometry_count, CropExclusion.PENDING_GEOMETRY_CORRECTION),
        (source.grid_issue_count, CropExclusion.GRID_ISSUE),
        (source.pending_proposal_count, CropExclusion.PENDING_GRID_PROPOSAL),
        (source.page_exclusion_count, CropExclusion.PAGE_SOURCE_EXCLUDED),
        (source.active_image_job_count, CropExclusion.ACTIVE_IMAGE_JOB),
        (source.registration_anchor_count, CropExclusion.PAGE_REGISTRATION_ANCHOR),
    ):
        if count:
            reasons.add(reason)
    return reasons
