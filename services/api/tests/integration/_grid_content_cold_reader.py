"""Fresh-process proof: only the explicitly owned disposable database is accepted."""

import os
import re
from pathlib import Path
from uuid import UUID

from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.grid_cell_content import SqlAlchemyGridCellContentRepository
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

url = make_url(os.environ["CONTENT_TEST_DATABASE_URL"])
if not re.fullmatch(r"game_predictor_t1165_[0-9a-f]{12}_test", url.database or ""):
    raise RuntimeError("A task-owned disposable database is required.")
game, source = UUID(os.environ["CONTENT_TEST_GAME"]), UUID(os.environ["CONTENT_TEST_SOURCE"])
engine = create_engine(url, connect_args={"connect_timeout": 5})
try:
    factory = create_session_factory(engine)
    with game_storage_scope(game), factory() as session:
        view = SqlAlchemyGridCellContentRepository(
            session, Path(os.environ["CONTENT_TEST_ROOT"])
        ).get(game, source, 0)
        assert view["revision"] == 1
        assert view["contentReferenceSha256"] == os.environ["CONTENT_TEST_REFERENCE_SHA"]
        assert view["annotation"]["reference"]["humanApproved"] is True
    print("COLD_CONTENT_READ_PASS", flush=True)
finally:
    engine.dispose()
