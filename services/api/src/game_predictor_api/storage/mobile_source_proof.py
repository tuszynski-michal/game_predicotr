"""Revalidate immutable layout lineage against replacement history, never timestamps.

Callers hold the game's SHARED ownership fence through capture/publication. Historical
GET/download does not call this guard. Games without replacement retain their flow.
"""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from game_predictor_api.domain.mobile_releases import MobileReleaseConflictError

_AFFECTED = """
WITH affected AS (
 SELECT DISTINCT CAST(value AS bigint) AS sequence_number
 FROM source_replacement_retired r
 CROSS JOIN LATERAL jsonb_array_elements_text(
   r.document #> '{prior,sequence_numbers}') AS seq(value)
 WHERE r.game_id=:game
), current_source AS (
 SELECT c.sequence_number, c.recognized_board_id, staging.cells
 FROM image_sequence_canonical c
 JOIN image_review_items i ON i.game_id=c.game_id AND i.id=c.review_item_id
   AND i.recognized_board_id=c.recognized_board_id
   AND i.resolution_revision=c.resolution_revision AND i.status=c.status
 JOIN recognized_boards b ON b.game_id=c.game_id AND b.id=c.recognized_board_id
   AND b.source_image_id=c.source_image_id
 JOIN source_images s ON s.game_id=c.game_id AND s.id=c.source_image_id
   AND s.checksum_sha256=c.source_checksum_sha256
 JOIN image_layout_staging_rows staging ON staging.game_id=c.game_id
   AND staging.review_item_id=c.review_item_id
   AND staging.recognized_board_id=c.recognized_board_id
   AND staging.sequence_number=c.sequence_number
 WHERE c.game_id=:game AND public.source_replacement_current_v1(
   c.game_id,s.id,s.checksum_sha256,c.sequence_number,i.id)
)
"""


def require_no_replacement_slots(session: Session, game_id: UUID) -> None:
    if session.scalar(
        text("SELECT EXISTS(SELECT 1 FROM source_replacement_slots WHERE game_id=:game)"),
        {"game": game_id},
    ):
        raise MobileReleaseConflictError(
            "SOURCE_REPLACEMENT_RESERVED",
            "Gra ma otwartą rezerwację wymiany zdjęcia.",
            details={"gameId": str(game_id)},
        )


def _has_retired_sources(session: Session, game_id: UUID) -> bool:
    return bool(
        session.scalar(
            text("SELECT EXISTS(SELECT 1 FROM source_replacement_retired WHERE game_id=:game)"),
            {"game": game_id},
        )
    )


def require_current_dataset_sources(
    session: Session, *, game_id: UUID, dataset_version_id: UUID
) -> None:
    """Null/missing lineage in a replacement sequence requires a new dataset.

    The layout's immutable board reference prevents a pre-retirement dataset from
    becoming current merely because restoration removed reservations. Equal symbols
    in a replacement photo are not evidence that the old photo became current.
    """
    require_no_replacement_slots(session, game_id)
    if not _has_retired_sources(session, game_id):
        return
    stale = session.execute(
        text(
            _AFFECTED
            + """
SELECT l.sequence_number FROM layouts l
JOIN dataset_versions d ON d.id=l.dataset_version_id AND d.game_id=:game
LEFT JOIN current_source c ON c.sequence_number=l.sequence_number
LEFT JOIN recognized_boards b ON b.game_id=:game AND b.id=l.source_board_id
LEFT JOIN source_images s ON s.game_id=:game AND s.id=b.source_image_id
WHERE l.dataset_version_id=:dataset AND (
 (l.sequence_number IN (SELECT sequence_number FROM affected) AND
  (l.source_board_id IS DISTINCT FROM c.recognized_board_id
   OR c.recognized_board_id IS NULL OR l.cells IS DISTINCT FROM c.cells))
 OR EXISTS(SELECT 1 FROM source_replacement_retired r WHERE r.game_id=:game
   AND (r.source_id=s.id OR r.source_sha256=s.checksum_sha256)))
ORDER BY l.sequence_number LIMIT 1
"""
        ),
        {"game": game_id, "dataset": dataset_version_id},
    ).first()
    if stale is not None:
        raise MobileReleaseConflictError(
            "MOBILE_RELEASE_SOURCE_PROOF_STALE",
            "Dataset zawiera wycofane źródło lub nie ma jego bieżącego dowodu. "
            "Opublikuj nowy dataset z aktualnych zweryfikowanych plansz.",
            details={
                "gameId": str(game_id),
                "datasetVersionId": str(dataset_version_id),
                "sequenceNumber": int(stale[0]),
            },
        )


def capture_replacement_dataset_sources(
    session: Session, *, game_id: UUID, dataset_version_id: UUID
) -> None:
    """Capture only a newly inserted staging dataset, in its publication transaction."""
    require_no_replacement_slots(session, game_id)
    if not _has_retired_sources(session, game_id):
        return
    session.execute(
        text(
            _AFFECTED
            + """
UPDATE layouts l SET source_board_id=c.recognized_board_id
FROM current_source c, dataset_versions d
WHERE d.id=:dataset AND d.game_id=:game AND d.status='staging'
 AND l.dataset_version_id=d.id AND l.sequence_number=c.sequence_number
 AND l.sequence_number IN (SELECT sequence_number FROM affected)
 AND l.cells=c.cells AND l.source_board_id IS NULL
"""
        ),
        {"game": game_id, "dataset": dataset_version_id},
    )
    require_current_dataset_sources(session, game_id=game_id, dataset_version_id=dataset_version_id)
