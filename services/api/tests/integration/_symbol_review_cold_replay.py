"""Fresh interpreter replay against the explicitly owned test database only."""

import json
import os
import sys
from pathlib import Path
from uuid import UUID

from game_predictor_api.storage.database import GameStorageSession
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.grid_reinference import SqlAlchemyGridReinferenceRepository
from game_predictor_api.storage.models import ImageSymbolReviewCellModel
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

url = make_url(os.environ["GAME_PREDICTOR_DATABASE_URL"])
assert url.database.startswith("game_predictor_task0760_") and url.database.endswith("_test")
body = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
engine = create_engine(
    url, connect_args={"connect_timeout": 5, "options": "-c statement_timeout=10000"}
)
try:
    factory = sessionmaker(engine, class_=GameStorageSession)
    game = UUID(body["game"])
    with game_storage_scope(game), factory.begin() as session:
        view = SqlAlchemyGridReinferenceRepository(session, Path(body["root"])).execute(
            game, UUID(body["operation"]), "start", body["command"], "fixture-operator"
        )
        count = session.scalar(
            select(func.count())
            .select_from(ImageSymbolReviewCellModel)
            .where(
                ImageSymbolReviewCellModel.game_id == game,
                ImageSymbolReviewCellModel.review_state == "pending",
            )
        )
        Path(sys.argv[2]).write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "state": view["state"],
                    "jobId": view["jobId"],
                    "pendingCount": count,
                }
            ),
            encoding="utf-8",
        )
finally:
    engine.dispose()
