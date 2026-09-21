"""Shared HTTP projections for catalog domain records."""

from dataclasses import asdict

from game_predictor_api.application.catalog import CatalogService
from game_predictor_api.domain.catalog import Game
from game_predictor_api.schemas.catalog import GameResponse


def to_game_response(service: CatalogService, game: Game) -> GameResponse:
    """Attach the current geometry-readiness projection to a catalog game."""

    return GameResponse.model_validate(
        {
            **asdict(game),
            "shape_geometry_readiness": service.shape_geometry_readiness(game),
        }
    )
