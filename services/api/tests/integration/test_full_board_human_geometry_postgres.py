"""Ordinary automatic boards become GT only through actual guarded human commands."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from game_predictor_api.application.virtual_grid_geometry import VirtualGridGeometryService
from game_predictor_api.domain.geometry_qualification import GeometryQualification
from game_predictor_api.domain.image_geometry_v2 import SourceLatticeNodes, SourcePoint
from game_predictor_api.domain.image_reviews import ImageReviewGeometryPoint
from game_predictor_api.storage.game_storage_routing import (
    GameStorageIntent,
    GameStorageRouter,
    game_storage_scope,
)
from game_predictor_api.storage.grid_diagnostic_readiness import summarize_capture
from game_predictor_api.storage.grid_quality_observations import current_targets
from game_predictor_api.storage.grid_training_cohort_evidence import GridCohortEvidenceReader
from game_predictor_api.storage.virtual_grid_geometry_repository import (
    SqlAlchemyVirtualGridGeometryRepository,
)
from test_grid_quality_measurements_postgres import database as _database_fixture
from test_grid_quality_measurements_postgres import pytestmark, seed  # noqa: F401
from test_v3_engine_acceptance_postgres import current_partition_budget  # noqa: F401


@pytest.fixture(scope="module")
def database():
    yield from _database_fixture.__wrapped__()


def test_ordinary_good_geometry_saved_qualifies_nine_boards_only_after_last_human_save(
    database, tmp_path
):
    game, sessions, source, root = seed(database, tmp_path, slot_count=9)
    from game_predictor_api.storage.models import SymbolModel

    with game_storage_scope(game), sessions.begin() as session:
        session.add(
            SymbolModel(
                game_id=game,
                code="ORDINARY",
                name="Ordinary",
                mobile_code=1,
                display_order=1,
                status="active",
            )
        )

    def readiness():
        with game_storage_scope(game), sessions.begin() as session:
            capture = GridCohortEvidenceReader(session, root).capture(
                game,
                source.source_image_id,
                0,
                {"qualification": "unresolved", "role": None, "reasonCodes": []},
                "grid-only",
            )
            return summarize_capture(capture)

    before = readiness()
    assert before["qualifiedHumanBoards"] == 0 and not before["fullyHumanAnnotated"]
    with game_storage_scope(game), sessions.begin() as session:
        GameStorageRouter().bind(session, game, intent=GameStorageIntent.READ)
        targets = current_targets(session, game, source.source_image_id)
    assert set(targets) == set(range(9))
    for position in range(9):
        with game_storage_scope(game), sessions.begin() as session:
            GameStorageRouter().bind(session, game, intent=GameStorageIntent.WRITE)
            current = current_targets(session, game, source.source_image_id)[position]
            board, review = current["board"], current["review"]
            nodes = tuple(
                SourcePoint(p["x"], p["y"]) for p in board["board_geometry"]["latticeNodes"]
            )
            key = uuid4()
            kwargs = dict(
                game_id=game,
                import_job_id=source.import_job_id,
                review_item_id=UUID(review["id"]),
                idempotency_key=key,
                expected_geometry_revision=board["geometry_revision"],
                expected_resolution_revision=review["resolution_revision"],
                corners=tuple(
                    ImageReviewGeometryPoint(round(nodes[i].x), round(nodes[i].y))
                    for i in (0, 5, 23, 18)
                ),
                lattice_nodes=SourceLatticeNodes(nodes),
                geometry_qualification=GeometryQualification(),
                expected_proposal_checksum_sha256=board["board_geometry"].get(
                    "neuralProposalChecksumSha256"
                ),
                actor="local-owner",
                created_at=datetime.now(UTC),
            )
            service = VirtualGridGeometryService(
                SqlAlchemyVirtualGridGeometryRepository(
                    session, source_snapshot_policy="current_live_slots"
                ),
                root,
            )
            saved = service.save_review_item(**kwargs)
            assert saved.created
            assert not service.save_review_item(**kwargs).created  # lost-reply replay is identical
        observed = readiness()
        assert observed["qualifiedHumanBoards"] == position + 1
        assert observed["fullyHumanAnnotated"] == (position == 8)
    # No quality measurement or invented issue was needed to reach human GT.
