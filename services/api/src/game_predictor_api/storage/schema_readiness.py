"""Fail-closed startup check: the database schema must match this code's head.

The ownership manifest is ``game-data-v2-manifest-v21``.
0177 adds physical source purge to the replacement ownership and closure guards.
API, worker and maintenance
scripts still require the exact supported Alembic head before starting.
One ``SELECT``.
"""

from __future__ import annotations

from typing import Final

from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

# Keep equal to `alembic heads`; test_schema_readiness asserts it.
EXPECTED_ALEMBIC_HEAD: Final = "0179_empty_replacement_search"


class AlembicHeadMismatchError(RuntimeError):
    code = "ALEMBIC_HEAD_MISMATCH"

    def __init__(self, found: str | None) -> None:
        self.found = found
        self.expected = EXPECTED_ALEMBIC_HEAD
        super().__init__(
            f"ALEMBIC_HEAD_MISMATCH: database schema is {found or 'unversioned'}, "
            f"this code requires {EXPECTED_ALEMBIC_HEAD}. Stop every API/worker/reviewer "
            "process, run `npm run db:migrate` with this code, then start again "
            "(or start the code matching the database)."
        )


def database_alembic_revision(engine: Engine) -> str | None:
    with engine.connect() as connection:
        try:
            rows = connection.execute(text("SELECT version_num FROM public.alembic_version")).all()
        except DBAPIError:
            return None
    if len(rows) != 1:
        return None
    return str(rows[0][0])


def require_alembic_head(engine: Engine) -> None:
    """Raise ``AlembicHeadMismatchError`` unless the database is at this code's head."""

    found = database_alembic_revision(engine)
    if found != EXPECTED_ALEMBIC_HEAD:
        raise AlembicHeadMismatchError(found)


__all__ = [
    "EXPECTED_ALEMBIC_HEAD",
    "AlembicHeadMismatchError",
    "database_alembic_revision",
    "require_alembic_head",
]
