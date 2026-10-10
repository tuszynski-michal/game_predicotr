"""ORM mappings of the super game series tables (migration 0152, TASK-0933).

The tables are game-partitioned in ``game_data_v2`` (manifest v6); the ORM
names stay unqualified and resolve through the game route's ``search_path``,
like every other game-owned mapping.
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
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from game_predictor_api.storage.metadata import Base


def _series_checks(prefix: str) -> tuple[CheckConstraint, ...]:
    return (
        CheckConstraint(
            "trigger_sequence_number BETWEEN 1 AND 10000000 "
            "AND start_sequence_number = trigger_sequence_number + 1 "
            "AND length BETWEEN 1 AND 10000000",
            name=f"ck_{prefix}_positions",
        ),
        CheckConstraint(
            "completeness IN ('complete', 'incomplete')", name=f"ck_{prefix}_completeness"
        ),
        CheckConstraint(
            "run_verification IN ('verified', 'unverified')",
            name=f"ck_{prefix}_run_verification",
        ),
    )


class SuperGameSeriesModel(Base):
    """Published series; identity ``(game_id, trigger_sequence_number)``."""

    __tablename__ = "super_game_series"
    __table_args__ = (
        UniqueConstraint("game_id", "trigger_sequence_number", name="uq_super_game_series_trigger"),
        *_series_checks("super_game_series"),
        CheckConstraint(
            "(defined_by IS NULL) = (defined_at IS NULL) "
            "AND (super_symbol_id IS NULL OR defined_by IS NOT NULL)",
            name="ck_super_game_series_definition",
        ),
        CheckConstraint("revision >= 0", name="ck_super_game_series_revision"),
    )

    game_id: Mapped[UUID] = mapped_column(
        ForeignKey("games.id", ondelete="RESTRICT"), primary_key=True
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    trigger_sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    start_sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    length: Mapped[int] = mapped_column(Integer, nullable=False)
    retrigger_sequence_numbers: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False, default=list, server_default=text("'{}'")
    )
    completeness: Mapped[str] = mapped_column(String(20), nullable=False)
    run_verification: Mapped[str] = mapped_column(String(20), nullable=False)
    super_symbol_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("symbols.id", ondelete="RESTRICT"), nullable=True
    )
    defined_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    defined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revision: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    generation_id: Mapped[UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SuperGameSeriesGenerationRowModel(Base):
    """Working row of an unpublished generation; never served by the API."""

    __tablename__ = "super_game_series_generation_rows"
    __table_args__ = _series_checks("super_game_generation_rows")

    game_id: Mapped[UUID] = mapped_column(
        ForeignKey("games.id", ondelete="RESTRICT"), primary_key=True
    )
    generation_id: Mapped[UUID] = mapped_column(primary_key=True)
    trigger_sequence_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    start_sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    length: Mapped[int] = mapped_column(Integer, nullable=False)
    retrigger_sequence_numbers: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False, default=list, server_default=text("'{}'")
    )
    completeness: Mapped[str] = mapped_column(String(20), nullable=False)
    run_verification: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SuperGameDerivationStateModel(Base):
    """Per-game input counter; staleness is derived, never stored."""

    __tablename__ = "super_game_derivation_state"
    __table_args__ = (
        CheckConstraint(
            "input_version >= 0 "
            "AND (current_generation_id IS NULL) = (input_version_of_generation IS NULL) "
            "AND (input_version_of_generation IS NULL "
            "OR input_version_of_generation BETWEEN 0 AND input_version)",
            name="ck_super_game_derivation_state_versions",
        ),
    )

    game_id: Mapped[UUID] = mapped_column(
        ForeignKey("games.id", ondelete="RESTRICT"), primary_key=True
    )
    input_version: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default=text("0")
    )
    current_generation_id: Mapped[UUID | None] = mapped_column(nullable=True)
    input_version_of_generation: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SuperGameSeriesAuditEventModel(Base):
    """Super symbol changes and removed series; survives the series row."""

    __tablename__ = "super_game_series_audit_events"
    __table_args__ = (
        CheckConstraint(
            "event_kind IN ('super_symbol_defined', 'series_removed')",
            name="ck_super_game_series_audit_kind",
        ),
        CheckConstraint(
            "trigger_sequence_number >= 1 AND length(btrim(actor)) > 0 "
            "AND (event_kind <> 'super_symbol_defined' "
            "OR (previous_revision IS NOT NULL AND revision = previous_revision + 1)) "
            "AND (event_kind <> 'series_removed' "
            "OR (generation_id IS NOT NULL AND super_symbol_id IS NULL))",
            name="ck_super_game_series_audit_shape",
        ),
        Index("ix_super_game_series_audit_series", "game_id", "series_id", "created_at", "id"),
    )

    game_id: Mapped[UUID] = mapped_column(
        ForeignKey("games.id", ondelete="RESTRICT"), primary_key=True
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    series_id: Mapped[UUID] = mapped_column(nullable=False)
    trigger_sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    event_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    previous_super_symbol_id: Mapped[UUID | None] = mapped_column(nullable=True)
    super_symbol_id: Mapped[UUID | None] = mapped_column(nullable=True)
    previous_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    generation_id: Mapped[UUID | None] = mapped_column(nullable=True)
    actor: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


__all__ = [
    "SuperGameDerivationStateModel",
    "SuperGameSeriesAuditEventModel",
    "SuperGameSeriesGenerationRowModel",
    "SuperGameSeriesModel",
]
