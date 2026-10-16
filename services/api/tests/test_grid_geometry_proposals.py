"""Proposal contracts: immutable candidates, actor-free requests and retained schema."""

import importlib
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from game_predictor_api.domain.image_reviews import ImageReviewNotFoundError
from game_predictor_api.schemas.grid_geometry_proposals import (
    ProposalAcceptCommand,
    ProposalCreateCommand,
)
from game_predictor_api.storage import game_data_v2_manifest_v12 as previous
from game_predictor_api.storage import game_data_v2_manifest_v13 as current
from game_predictor_api.storage import game_data_v2_manifest_v16 as runtime
from game_predictor_api.storage.grid_geometry_proposal_models import (
    GridGeometryProposalEventModel,
    GridGeometryProposalModel,
)
from game_predictor_api.storage.grid_geometry_proposals import (
    SqlAlchemyGridGeometryProposalRepository,
)
from game_predictor_api.storage.models import Base
from pydantic import ValidationError


@pytest.mark.parametrize(
    "failure",
    [
        RuntimeError("storage failure"),
        ImageReviewNotFoundError("OTHER_NOT_FOUND", "different error"),
    ],
)
def test_discovery_does_not_swallow_unrelated_failures(failure):
    session = Mock()
    session.scalars.side_effect = [[], [SimpleNamespace(target_result_id=uuid4())]]
    repo = SqlAlchemyGridGeometryProposalRepository(session, Path("unused"))
    with (
        patch.object(repo.reinference, "bind"),
        patch.object(repo, "_candidate", side_effect=failure),
        pytest.raises(type(failure), match=str(failure)),
    ):
        repo.list_proposals(uuid4(), uuid4(), uuid4())


def test_proposal_schema_is_retained_and_central():
    assert set(current.GAME_TABLES) - set(previous.GAME_TABLES) == set(current.ADDED_GAME_TABLES)
    for model in (GridGeometryProposalModel, GridGeometryProposalEventModel):
        assert model.__tablename__ in Base.metadata.tables
        assert not any(
            foreign.column.table.name in {"source_images", "image_review_items"}
            for foreign in model.__table__.foreign_keys
        )
    assert all(
        "game_id" in [col.name for col in model.__table__.primary_key]
        for model in (GridGeometryProposalModel, GridGeometryProposalEventModel)
    )


def test_migration_adds_composite_rls_and_refuses_history_loss():
    output = StringIO()
    config = Config(str(Path(__file__).resolve().parents[3] / "alembic.ini"), output_buffer=output)
    config.set_main_option("sqlalchemy.url", "postgresql+psycopg://unused:unused@localhost/unused")
    command.upgrade(config, "0159_grid_reinference:0160_grid_geometry_proposals", sql=True)
    sql = output.getvalue()
    assert "FOREIGN KEY(game_id,target_result_id)" in sql
    assert "FORCE ROW LEVEL SECURITY" in sql
    assert "proposal_id IS NOT NULL OR" in sql
    assert "snapshot #>> '{review,id}'" in sql
    assert (
        importlib.import_module("game_predictor_api.storage.game_partition_lifecycle").VERSION
        == runtime.VERSION
    )
    output.truncate(0)
    output.seek(0)
    command.downgrade(config, "0160_grid_geometry_proposals:0159_grid_reinference", sql=True)
    assert "GRID_PROPOSAL_DOWNGRADE_HAS_HISTORY" in output.getvalue()


def test_create_has_no_actor_body_and_edit_requires_geometry():
    with pytest.raises(ValidationError):
        ProposalCreateCommand.model_validate(
            {"targetResultId": str(uuid4()), "idempotencyKey": str(uuid4()), "actor": "spoof"}
        )
    base = dict(
        idempotencyKey=str(uuid4()),
        expectedProposalRevision=1,
        expectedGeometryRevision=0,
        expectedResolutionRevision=0,
        originalCandidateSha256="a" * 64,
    )
    ProposalAcceptCommand.model_validate({**base, "mode": "model"})
    with pytest.raises(ValidationError):
        ProposalAcceptCommand.model_validate({**base, "mode": "edited"})
    with pytest.raises(ValidationError):
        ProposalAcceptCommand.model_validate(
            {
                **base,
                "mode": "edited",
                "geometry": {
                    "expectedGeometryRevision": 0,
                    "expectedResolutionRevision": 0,
                    "corners": [
                        {"x": 0, "y": 0},
                        {"x": 10, "y": 0},
                        {"x": 10, "y": 10},
                        {"x": 0, "y": 10},
                    ],
                },
            }
        )
