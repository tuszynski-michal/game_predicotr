from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
COMPOSE_PATH = REPOSITORY_ROOT / "infra" / "docker" / "compose.yaml"


def test_postgres_compose_is_pinned_local_and_persistent() -> None:
    compose = COMPOSE_PATH.read_text(encoding="utf-8")

    assert "image: postgres:18.4-alpine3.24" in compose
    assert "127.0.0.1:${GAME_PREDICTOR_POSTGRES_PORT:-5432}:5432" in compose
    assert "pg_isready" in compose
    assert "game_predictor_postgres_data:/var/lib/postgresql" in compose
    assert "/var/lib/postgresql/data" not in compose
