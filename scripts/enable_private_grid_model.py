"""Enable a game-owned grid family after explicit operator confirmation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import UUID

# A shared editable virtualenv can point at a different checkout.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
for source_directory in ("services/worker/src", "services/api/src"):
    sys.path.insert(0, str(REPOSITORY_ROOT / source_directory))

from game_predictor_api.application.grid_model_registry import (  # noqa: E402
    GridModelRegistryService,
)
from game_predictor_api.application.new_game_geometry import NewGameGeometryService  # noqa: E402
from game_predictor_api.config import ApiSettings  # noqa: E402
from game_predictor_api.domain.grid_model_registry import GridModelRegistryError  # noqa: E402
from game_predictor_api.security.local_admin import ADMIN_ACTOR  # noqa: E402
from game_predictor_api.storage.database import (  # noqa: E402
    create_database_engine,
    create_session_factory,
)
from game_predictor_api.storage.game_create_receipts import (  # noqa: E402
    SqlAlchemyGameCreateReceiptRepository,
)
from game_predictor_api.storage.grid_model_registry import (  # noqa: E402
    GridModelArtifactInspector,
    SqlAlchemyGridModelRegistryRepository,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-id", type=UUID, required=True)
    parser.add_argument("--expected-revision", type=int, required=True)
    parser.add_argument("--idempotency-key", type=UUID, required=True)
    parser.add_argument("--confirm-private-model", action="store_true", required=True)
    options = parser.parse_args()
    if options.expected_revision < 1:
        parser.error("--expected-revision must identify an existing assignment")

    settings = ApiSettings.from_environment()
    engine = create_database_engine(settings)
    session_factory = create_session_factory(engine)
    try:
        with session_factory.begin() as session:
            registry = GridModelRegistryService(
                SqlAlchemyGridModelRegistryRepository(session),
                GridModelArtifactInspector(settings.artifact_root),
            )
            result = NewGameGeometryService(
                None, SqlAlchemyGameCreateReceiptRepository(session), registry
            ).enable_private_model(
                game_id=options.game_id,
                key=options.idempotency_key,
                expected_revision=options.expected_revision,
                actor=ADMIN_ACTOR,
            )
    except GridModelRegistryError as error:
        parser.exit(
            1,
            json.dumps({"code": error.code, "message": error.message, "details": error.details})
            + "\n",
        )
    finally:
        engine.dispose()
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
