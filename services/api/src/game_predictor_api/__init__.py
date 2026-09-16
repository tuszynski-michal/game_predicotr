"""Local administrative API for Game Predictor."""

def create_app() -> object:
    """Construct the ASGI app without forcing it during domain-package imports."""

    from game_predictor_api.main import create_app as _create_app

    return _create_app()

__all__ = ["create_app"]
