"""Run the local Admin API on its validated loopback address."""

import uvicorn

from game_predictor_api.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "game_predictor_api.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
