"""The already-applied cleanup prerequisite must be reproducible from Git."""

from io import StringIO
from typing import cast

from alembic import command
from alembic.config import Config
from game_predictor_api.storage.models import ImageSymbolReviewCellModel
from sqlalchemy import Table


def test_prediction_revision_fk_index_is_additive_and_matches_orm() -> None:
    output = StringIO()
    config = Config("alembic.ini", output_buffer=output)
    config.set_main_option("sqlalchemy.url", "postgresql+psycopg://unused/unused")
    command.upgrade(
        config,
        "0101_symbol_cell_source_availability:0102_index_symbol_review_prediction_revision",
        sql=True,
    )
    sql = output.getvalue().lower()
    name = "ix_image_symbol_review_cells_prediction_revision_id"
    assert f"create index {name} on image_symbol_review_cells (prediction_revision_id)" in sql
    assert "delete from" not in sql
    assert "update image_symbol_review_cells" not in sql
    index = next(
        index for index in cast(Table, ImageSymbolReviewCellModel.__table__).indexes
        if index.name == name
    )
    assert [column.name for column in index.columns] == ["prediction_revision_id"]
