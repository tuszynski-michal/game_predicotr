"""Shared SQLAlchemy metadata for canonical PostgreSQL models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base for canonical PostgreSQL models."""
