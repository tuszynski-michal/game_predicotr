"""Real keyset navigation after a deferred position receives a review UUID."""

from dataclasses import replace
from pathlib import Path
from uuid import UUID

import pytest
import test_virtual_deferred_resolution_postgres as deferred_fixture
from game_predictor_api.application.image_grid_reviews import ImageGridReviewService
from game_predictor_api.domain.image_grid_reviews import (
    ImageGridReviewCountsMode,
    ImageGridReviewView,
)
from game_predictor_api.storage import game_partition_lifecycle
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.image_geometry_completeness_state_repository import (
    SqlAlchemyImageGeometryCompletenessStateRepository,
)
from game_predictor_api.storage.image_grid_review_repository import (
    SqlAlchemyImageGridReviewRepository,
)
from game_predictor_api.storage.models import ImageBoardGeometryPendingModel
from test_virtual_deferred_resolution_postgres import (
    _Database,
    _factory,
    _provision_game,
    _resolve_via_reviewer_endpoint,
    _seed,
    database,  # noqa: F401
    pytestmark,  # noqa: F401
)


@pytest.mark.parametrize("pending_key", [UUID(int=1), UUID(int=2**128 - 1)])
def test_saved_position_does_not_hide_the_next_position_in_a_fresh_session(
    database: _Database,  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pending_key: UUID,
) -> None:
    # The reused fixture's loop budget predates the current manifest. Use the
    # actual production manifest for its bounded provisioning loop.
    monkeypatch.setattr(deferred_fixture, "CREATE_TABLES", game_partition_lifecycle.CREATE_TABLES)
    game = _provision_game(database.engine, "task1174-cursor")
    factory = _factory(database.engine)
    seed = _seed(factory, game, tmp_path, label="cursor", slot_count=2)
    # uuid4 materialization must sort after the minimum key and before the
    # maximum key. Both cursor branches are exercised deterministically.
    with game_storage_scope(game), factory.begin() as session:
        pending = session.get(ImageBoardGeometryPendingModel, seed.pending_ids[0])
        assert pending is not None
        pending.id = pending_key
    seed = replace(seed, pending_ids=(pending_key, *seed.pending_ids[1:]))

    def read(after: str | None = None):
        # No ORM identity map or in-process queue is carried between requests.
        with game_storage_scope(game), factory() as session:
            return ImageGridReviewService(SqlAlchemyImageGridReviewRepository(session)).list(
                game_id=game,
                import_job_id=seed.import_job_id,
                source_image_id=seed.source_image_id,
                view=ImageGridReviewView.ALL,
                counts=ImageGridReviewCountsMode.NONE,
                limit=1,
                after_cursor=after,
                before_cursor=None,
            )

    first = read()
    assert first.items[0].pending_geometry_id == seed.pending_ids[0]
    assert first.next_cursor is not None
    saved = _resolve_via_reviewer_endpoint(database, tmp_path, seed)
    assert UUID(saved["reviewItemId"]) != first.items[0].slot_id
    # This two-position fixture is not a complete nine-board page. An explicit
    # test-only source exception materializes the saved board's real projection.
    with game_storage_scope(game), factory.begin() as session:
        SqlAlchemyImageGeometryCompletenessStateRepository(session).set_exception(
            game, seed.source_image_id, reason="two-position test fixture", actor="test-owner"
        )
    current = read()
    assert current.items[0].review_item_id == UUID(saved["reviewItemId"])
    assert (
        current.items[0].import_job_id,
        current.items[0].source_image_id,
        current.items[0].position_index,
    ) == (
        first.items[0].import_job_id,
        first.items[0].source_image_id,
        first.items[0].position_index,
    )
    following = read(first.next_cursor)
    # UUID ordering can place the newly materialized item after its old key.
    if following.items[0].position_index == first.items[0].position_index:
        assert pending_key == UUID(int=1)
        assert following.items[0].review_item_id == UUID(saved["reviewItemId"])
        assert following.next_cursor is not None
        following = read(following.next_cursor)
    else:
        assert pending_key == UUID(int=2**128 - 1)
    assert len(following.items) == 1
    assert following.items[0].pending_geometry_id == seed.pending_ids[1]
    assert following.items[0].sequence_number == first.items[0].sequence_number + 1
    assert following.next_cursor is None
    assert following.counts.total == 0
