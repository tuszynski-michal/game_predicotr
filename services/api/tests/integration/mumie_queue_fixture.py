"""One ranked target in a real two-board disposable import."""

from dataclasses import replace
from uuid import uuid4

from game_predictor_api.domain import mumie_suspicious_batch as policy
from game_predictor_api.domain.symbol_model_snapshots import bootstrap_symbol_model_snapshot
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.image_grid_review_repository import (
    SqlAlchemyImageGridReviewRepository,
)
from game_predictor_api.storage.models import (
    GameModel,
    ImageSymbolPredictionRevisionModel,
    ImageSymbolReviewCellModel,
    RecognizedBoardModel,
    SymbolModel,
    SymbolStatus,
)
from game_predictor_api.storage.symbol_model_snapshot_resolver import (
    SqlAlchemySymbolModelSnapshotResolver,
)
from game_predictor_worker.images.manual_board_cell_symbol_prediction import (
    ManualBoardCellSymbolPrediction,
    ManualBoardCellSymbolPredictor,
)
from sqlalchemy import select


def queue_command(game, factory, monkeypatch):
    monkeypatch.setattr(policy, "GAME", game)
    classifier = replace(
        bootstrap_symbol_model_snapshot(), class_codes=("CYTRYNA", "WISNIA")
    ).with_full_cell_crops()
    monkeypatch.setattr(
        SqlAlchemySymbolModelSnapshotResolver, "resolve", lambda self, game_id: classifier
    )

    def classify(self, cells, snapshot):
        assert snapshot == classifier and len(cells) == 15 and all(c.rgb.size for c in cells)
        return ManualBoardCellSymbolPrediction(
            None,
            classifier.manifest_checksum_sha256,
            classifier.model_version,
            1.0,
            tuple(
                {
                    "symbolCode": "CYTRYNA",
                    "confidence": 1.0,
                    "alternatives": [{"symbolCode": "CYTRYNA", "confidence": 1.0}],
                    "rowIndex": c.row_index,
                    "columnIndex": c.column_index,
                }
                for c in cells
            ),
        )

    monkeypatch.setattr(ManualBoardCellSymbolPredictor, "predict_rendered_cells", classify)
    with game_storage_scope(game), factory.begin() as session:
        session.get(GameModel, game).code = "mumie-aktu2"
        for i, code in enumerate(classifier.class_codes, 1):
            if not session.scalar(
                select(SymbolModel.id).where(SymbolModel.game_id == game, SymbolModel.code == code)
            ):
                session.add(
                    SymbolModel(
                        game_id=game,
                        mobile_code=i,
                        code=code,
                        name=code,
                        display_order=i,
                        status=SymbolStatus.ACTIVE,
                    )
                )
        session.flush()
        # The old import already assigned all cells to a known, different symbol.
        from game_predictor_api.storage.board_search_projection_repository import (
            SqlAlchemyBoardSearchProjectionRepository,
        )
        from game_predictor_api.storage.image_symbol_review_repository import (
            SymbolCellReviewWriteThroughCoordinator,
        )
        from game_predictor_api.storage.models import (
            ImageBoardSearchFastDocumentModel,
            ImageReviewItemModel,
        )

        board = session.scalars(
            select(RecognizedBoardModel).where(RecognizedBoardModel.sequence_number == 100)
        ).one()
        item = session.scalars(
            select(ImageReviewItemModel).where(ImageReviewItemModel.recognized_board_id == board.id)
        ).one()
        board.cells_prediction = {
            **board.cells_prediction,
            "cells": [
                {
                    **cell,
                    "symbolCode": "WISNIA",
                    "confidence": 1.0,
                    "alternatives": [{"symbolCode": "WISNIA", "confidence": 1.0}],
                }
                for cell in board.cells_prediction["cells"]
            ],
        }
        session.flush()
        assert SymbolCellReviewWriteThroughCoordinator(
            session
        ).synchronize_after_prediction_refresh(game_id=game, review_item_id=item.id)
        SqlAlchemyBoardSearchProjectionRepository(session).sync_review_item(item.id)
        old = session.get(ImageBoardSearchFastDocumentModel, (game, 100))
        assert old.primary_symbol_mobile_codes == [2] * 15
        items = SqlAlchemyImageGridReviewRepository(session).suspicious_at_sequences(game, [100])
        assert len(items) == 1
        pins = [policy.board_pin(items[0])]
    return {
        "idempotencyKey": str(uuid4()),
        "modelVersionId": str(policy.VERSION),
        "selector": {"categories": ["unconfirmed"]},
        "suspiciousBatch": pins,
        "executionScope": "pilot",
    }


def verify_saved_batch(session, view):
    assert view["state"] == "completed" and view["outcomes"] == {"automatic_written": 1}
    boards = session.scalars(
        select(RecognizedBoardModel).order_by(RecognizedBoardModel.sequence_number)
    ).all()
    assert [(b.sequence_number, b.geometry_revision) for b in boards] == [(100, 1), (101, 0)]
    rev = session.scalars(select(ImageSymbolPredictionRevisionModel)).one()
    assert rev.recognized_board_id == boards[0].id and len(rev.predictions) == 15
    cells = session.scalars(
        select(ImageSymbolReviewCellModel).where(
            ImageSymbolReviewCellModel.prediction_revision_id == rev.id
        )
    ).all()
    assert len(cells) == 15 and {c.prediction_symbol_code for c in cells} == {"CYTRYNA"}
    from game_predictor_api.storage.models import ImageBoardSearchFastDocumentModel

    found = session.get(ImageBoardSearchFastDocumentModel, (rev.game_id, 100))
    assert (
        found.recognized_board_id == boards[0].id and found.primary_symbol_mobile_codes == [1] * 15
    )


def run_second_batch(game, factory, root, worker, repository, monkeypatch):
    """Drive the normal CLI transitions through a second batch on the same photo."""
    import json
    from contextlib import closing
    from unittest.mock import patch

    from game_predictor_worker.jobs.runtime import JobExecutionResult

    from scripts import mumie_suspicious_queue as queue

    monkeypatch.setattr(queue, "SqlAlchemyGridReinferenceRepository", repository)
    with game_storage_scope(game), factory.begin() as session:
        gallery = SqlAlchemyImageGridReviewRepository(session)
        (second,) = gallery.suspicious_at_sequences(game, [101])
        pin = policy.board_pin(second)
    db_path = root.parent / "second-batch.sqlite3"
    with closing(queue.ledger(db_path)) as db, db:
        db.execute(
            "INSERT INTO boards(sequence,score,pin) VALUES(?,?,?)",
            (101, pin["score"], json.dumps(pin)),
        )
        db.execute("UPDATE control SET sealed=1")
    with game_storage_scope(game), closing(queue.ledger(db_path)) as db:
        batch = queue.reserve(db)
        assert queue.advance(db, factory, root, batch) == "preparing"
        assert worker.run_once() is JobExecutionResult.WAITING_FOR_REVIEW
        assert queue.advance(db, factory, root, batch) == "prepared"
        assert queue.advance(db, factory, root, batch) == "frozen"
        with patch(
            "game_predictor_worker.images.grid_reinference_handler.ManagedGridEngineModelStore.require",
            return_value=root / "fixture-bundle.json",
        ):
            assert worker.run_once() is JobExecutionResult.COMPLETED
        assert queue.advance(db, factory, root, batch) == "completed"
        assert queue.status(db)["boards"] == {"automatic_written": 1}
        assert queue.reserve(db) is None
        with factory.begin() as session:
            boards = session.scalars(
                select(RecognizedBoardModel).order_by(RecognizedBoardModel.sequence_number)
            ).all()
            assert [(b.sequence_number, b.geometry_revision) for b in boards] == [
                (100, 1),
                (101, 1),
            ]
            assert len(session.scalars(select(ImageSymbolPredictionRevisionModel)).all()) == 2
