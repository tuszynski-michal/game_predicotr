"""Non-destructive history guards are evaluated before any cleanup SQL."""

from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from game_predictor_api.application.cleanup import CleanupService
from game_predictor_api.domain.cleanup import (
    CleanupCommand,
    CleanupConflictError,
    CleanupResult,
)
from game_predictor_api.domain.jobs import JobConflictError
from game_predictor_api.storage.browser_staging_retention_repository import (
    require_no_grid_shadow_history,
)
from game_predictor_api.storage.cleanup_repository import (
    SqlAlchemyCleanupRepository,
    _BoardSourceScope,
    latest_deactivation_selected,
)
from sqlalchemy.orm import Session


class SessionDouble:
    def __init__(self, count: int):
        self.count = count
        self.calls: list[str] = []

    def scalar(self, query):
        self.calls.append(str(query))
        return self.count


def test_unused_staging_preserves_shadow_history_without_deleting_anything() -> None:
    session = SessionDouble(1)
    with pytest.raises(JobConflictError) as error:
        require_no_grid_shadow_history(cast(Session, session), (uuid4(),))
    assert error.value.code == "IMAGE_BROWSER_SELECTION_DELETE_HAS_RESULTS"
    assert error.value.details == {"gridShadowResultCount": 1}
    assert len(session.calls) == 1 and "DELETE" not in session.calls[0]
    require_no_grid_shadow_history(cast(Session, SessionDouble(0)), (uuid4(),))


def test_source_cleanup_preview_explicitly_blocks_preserved_shadow_history() -> None:
    class Repository(SqlAlchemyCleanupRepository):
        def _count(self, sql, **parameters):
            return 1 if "image_geometry_shadow_results" in sql else 0

    repository = Repository(cast(Session, SessionDouble(1)))
    scope = cast(
        _BoardSourceScope, SimpleNamespace(game_id=uuid4(), source_ids=(uuid4(),), release_ids=())
    )
    assert repository._board_source_blockers(scope) == ["GRID_SHADOW_HISTORY_PRESENT"]


def test_source_cleanup_cannot_remove_off_event_and_reveal_older_model() -> None:
    model_b, model_a = uuid4(), uuid4()
    activation_b, activation_a, deactivation = uuid4(), uuid4(), uuid4()
    # B -> A -> deactivate(A). Deleting A's cohort selects the last off
    # event through previous_model_iteration_id, even though its target is null.
    history = [(deactivation, None), (activation_a, model_a), (activation_b, model_b)]
    affected = latest_deactivation_selected(history, (deactivation, activation_a))
    assert affected
    assert not latest_deactivation_selected(history, (activation_a,))

    class Repository(SqlAlchemyCleanupRepository):
        def _count(self, sql, **parameters):
            return 0

    scope = cast(
        _BoardSourceScope,
        SimpleNamespace(
            game_id=uuid4(),
            source_ids=(),
            release_ids=(),
            deactivation_history_affected=affected,
        ),
    )
    assert Repository(cast(Session, SessionDouble(0)))._board_source_blockers(scope) == [
        "SYMBOL_MODEL_DEACTIVATION_HISTORY_PRESENT"
    ]


class GameCleanupSession:
    def __init__(self):
        self.game = SimpleNamespace(id=uuid4(), name="Mumie", code="mumie")

    def scalar(self, query):
        return self.game

    def execute(self, *args):
        pytest.fail("History protection must run before any deletion SQL")


class GameCleanupRepository(SqlAlchemyCleanupRepository):
    has_history = True

    def _game_counts(self, game_id):
        return ()

    def _game_artifacts(self, game_id):
        return ("data/originals/source.jpg",), 0

    def _count(self, sql, **parameters):
        return int(self.has_history and "image_geometry_shadow_results" in sql)

    def _cross_game_count(self, sql, **parameters):
        return 0

    def completed_result(self, *args):
        return None


def test_game_reset_preview_preserves_shadow_history() -> None:
    repository = GameCleanupRepository(cast(Session, GameCleanupSession()))
    preview = CleanupService(repository, cast(object, None)).preview_game_reset(uuid4())
    assert preview.snapshot.blockers == ("GRID_SHADOW_HISTORY_PRESENT",)


def test_game_reset_rechecks_history_before_artifacts_or_sql() -> None:
    class ArtifactStore:
        def delete(self, paths):
            pytest.fail("History protection must run before artifact deletion")

    repository = GameCleanupRepository(cast(Session, GameCleanupSession()))
    repository.has_history = False
    service = CleanupService(repository, ArtifactStore())
    preview = service.preview_game_reset(uuid4())
    repository.has_history = True
    with pytest.raises(CleanupConflictError) as error:
        service.reset_game(
            preview.snapshot.target_id,
            CleanupCommand(
                preview_token=preview.preview_token,
                confirmation_target=preview.snapshot.confirmation_target,
                confirmed=True,
            ),
        )
    assert error.value.code == "CLEANUP_PREVIEW_STALE"
    with pytest.raises(CleanupConflictError) as error:
        repository.reset_game(preview.snapshot, cast(CleanupResult, None))
    assert error.value.details == {"blockers": ["GRID_SHADOW_HISTORY_PRESENT"]}
