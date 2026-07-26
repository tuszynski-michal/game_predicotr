"""Shared SQLAlchemy metadata for canonical PostgreSQL models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base for future domain models.

    TASK-0016 intentionally declares no domain tables.
    """
