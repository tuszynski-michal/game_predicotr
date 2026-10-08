"""Shared pytest fixtures for the API test suite."""

import logging

import pytest


@pytest.fixture(autouse=True)
def _reenable_application_loggers() -> None:
    """Undo the logger disabling done by in-process Alembic runs.

    TASK-0940: ``alembic/env.py`` calls ``fileConfig`` with its default
    ``disable_existing_loggers=True``, so any test that runs a migration in
    this process silences every application logger created before it, and
    later ``caplog`` assertions then see no records. Re-enabling the
    application loggers before each test removes that order dependence
    without touching the migration environment.
    """

    for name, candidate in list(logging.root.manager.loggerDict.items()):
        if name.startswith("game_predictor_") and isinstance(candidate, logging.Logger):
            candidate.disabled = False
