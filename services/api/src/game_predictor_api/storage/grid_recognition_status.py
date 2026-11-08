"""Read current exact game evidence without minting operation pins or writing state."""

from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.exc import DataError, DBAPIError, InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.orm import Session, sessionmaker

from game_predictor_api.domain.grid_model_registry import GridModelRegistryError
from game_predictor_api.domain.grid_recognition_status import (
    decision,
    unavailable_game_recognition_status,
)
from game_predictor_api.domain.neural_grid_operation_pin import (
    NeuralOperationPinError,
    model_capabilities,
)
from game_predictor_api.domain.neural_grid_proposal import (
    NeuralGridProposalError,
    NeuralGridSnapshot,
)

from .game_storage_routing import (
    GameStorageIntent,
    GameStorageRouter,
    GameStorageRoutingError,
    game_storage_scope,
)
from .models import GameModel
from .neural_grid_operation_qualification import _UNQUALIFIED, _automatic_evidence, _evidence


def routed_game_recognition_status(
    sessions: sessionmaker[Session], root: Path, game_id: UUID, view: dict[str, Any]
) -> dict[str, Any]:
    """A bounded read projection cannot bind or abort the catalogue transaction."""
    try:
        with game_storage_scope(game_id), sessions() as session, session.begin():
            session.connection().exec_driver_sql("SET TRANSACTION READ ONLY")
            GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.READ)
            return read_game_recognition_status(session, root, game_id, view)
    except (
        GridModelRegistryError,
        NeuralGridProposalError,
        NeuralOperationPinError,
        GameStorageRoutingError,
    ) as error:
        return unavailable_game_recognition_status(error.code)
    except (OperationalError, InterfaceError, PoolTimeoutError):
        return unavailable_game_recognition_status("NEURAL_GRID_STATUS_STORAGE_UNAVAILABLE")
    except DataError:
        return unavailable_game_recognition_status("NEURAL_GRID_STATUS_DATA_UNAVAILABLE")
    except DBAPIError as error:
        # Missing/denied schema objects are expected deployment/data availability
        # failures. SQL syntax mistakes and Python programming errors still surface.
        if getattr(error.orig, "sqlstate", None) not in {"42P01", "42703", "3F000", "42501"}:
            raise
        return unavailable_game_recognition_status("NEURAL_GRID_STATUS_STORAGE_UNAVAILABLE")


def read_game_recognition_status(
    session: Session, root: Path, game_id: UUID, view: dict[str, Any]
) -> dict[str, Any]:
    game = session.get(GameModel, game_id)
    if game is None:
        raise GridModelRegistryError("GRID_MODEL_GAME_MISSING", "The assigned game is unavailable.")
    configuration = game.shape_geometry_configuration
    if not isinstance(configuration, str):
        raise GridModelRegistryError(
            "GRID_MODEL_FORMAT_UNSUPPORTED",
            "The assigned game requires an explicit V3 configuration.",
        )
    snapshot = NeuralGridSnapshot.from_catalogue(
        game_id=str(game_id),
        game_configuration=configuration,
        expected_layout_count=game.expected_layout_count,
        descriptor=view["manifest"],
    )
    caps = model_capabilities(snapshot)
    evaluation = decision("unqualified", "NEURAL_GRID_GAME_EVALUATION_REQUIRED")
    automatic = decision("unqualified", "NEURAL_GRID_CALIBRATION_REQUIRED")
    if not view["available"]:
        evaluation = decision("unavailable", view["reasonCode"])
        automatic = decision("unavailable", view["reasonCode"])
    else:
        try:
            evidence = _evidence(session, snapshot, game_id, root)
        except GridModelRegistryError as error:
            if error.code not in _UNQUALIFIED:
                raise
            evaluation = decision("stale" if "STALE" in error.code else "unqualified", error.code)
        else:
            evaluation = decision("qualified")
            trusted = _automatic_evidence(session, evidence, snapshot, game_id, root)
            automatic = decision(trusted["state"], *trusted["reasonCodes"])
    return {
        "scope": "current_game",
        "capabilities": {
            k: caps[k] for k in ("boardRows", "boardColumns", "pageRows", "pageColumns")
        },
        "evaluation": evaluation,
        "automatic": automatic,
    }
