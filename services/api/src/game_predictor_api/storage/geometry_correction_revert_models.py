"""ORM mapping of the geometry correction revert audit (migration 0153, TASK-0945).

The table is game-partitioned in ``game_data_v2`` (manifest v7); the ORM name
stays unqualified and resolves through the game route's ``search_path``, like
every other game-owned mapping. Rows are append-only. The audit deliberately
has no foreign key to the rows a revert deletes (board, review item, cells,
board geometry revision); their content is kept in ``snapshot``.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from game_predictor_api.storage.metadata import Base


class ImageGeometryCorrectionRevertModel(Base):
    """One reverted manual grid-geometry correction with its snapshot."""

    __tablename__ = "image_geometry_correction_reverts"
    __table_args__ = (
        UniqueConstraint(
            "game_id",
            "idempotency_key",
            name="uq_image_geometry_correction_reverts_idempotency",
        ),
        UniqueConstraint(
            "game_id",
            "reverted_board_geometry_revision_id",
            name="uq_image_geometry_correction_reverts_revision",
        ),
        CheckConstraint(
            "kind IN ('pending_slot', 'board_revision')",
            name="ck_image_geometry_correction_reverts_kind",
        ),
        CheckConstraint(
            "sequence_number > 0 AND position_index BETWEEN 0 AND 8 "
            "AND reverted_geometry_revision >= 1 "
            "AND length(btrim(actor)) > 0 "
            "AND snapshot_checksum_sha256 ~ '^[0-9a-f]{64}$' "
            "AND jsonb_typeof(snapshot) = 'object' "
            "AND ((kind = 'pending_slot' AND pending_geometry_id IS NOT NULL "
            "AND restored_geometry_revision IS NULL) "
            "OR (kind = 'board_revision' "
            "AND restored_geometry_revision > reverted_geometry_revision))",
            name="ck_image_geometry_correction_reverts_shape",
        ),
        Index(
            "ix_image_geometry_correction_reverts_import",
            "game_id",
            "import_job_id",
            text("created_at DESC"),
        ),
        Index(
            "ix_image_geometry_correction_reverts_reverted_key",
            "game_id",
            "reverted_idempotency_key",
        ),
    )

    game_id: Mapped[UUID] = mapped_column(
        ForeignKey("games.id", ondelete="RESTRICT"), primary_key=True
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    import_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=False
    )
    source_image_id: Mapped[UUID] = mapped_column(nullable=False)
    sequence_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    position_index: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    pending_geometry_id: Mapped[UUID | None] = mapped_column(nullable=True)
    recognized_board_id: Mapped[UUID] = mapped_column(nullable=False)
    review_item_id: Mapped[UUID] = mapped_column(nullable=False)
    reverted_geometry_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    reverted_board_geometry_revision_id: Mapped[UUID] = mapped_column(nullable=False)
    reverted_source_geometry_revision_id: Mapped[UUID] = mapped_column(nullable=False)
    restored_source_geometry_revision_id: Mapped[UUID] = mapped_column(nullable=False)
    restored_geometry_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reverted_idempotency_key: Mapped[UUID] = mapped_column(nullable=False)
    idempotency_key: Mapped[UUID] = mapped_column(nullable=False)
    snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    snapshot_checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


__all__ = ["ImageGeometryCorrectionRevertModel"]
