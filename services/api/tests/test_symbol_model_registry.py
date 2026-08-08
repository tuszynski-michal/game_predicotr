from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from game_predictor_api.application.symbol_model_registry import SymbolModelRegistryService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.symbol_model_registry import (
    SymbolModelActivation,
    SymbolModelActivationAction,
    SymbolModelActivationPreview,
)
from game_predictor_api.main import create_app


class MemoryRegistry:
    def __init__(self, game_id: UUID, iteration_id: UUID, checksum: str) -> None:
        self.game_id = game_id
        self.iteration_id = iteration_id
        self.checksum = checksum
        self.current_id: UUID | None = None
        self.values: dict[UUID, SymbolModelActivation] = {}

    def preview(
        self,
        *,
        game_id: UUID,
        model_iteration_id: UUID,
        action: SymbolModelActivationAction,
    ) -> SymbolModelActivationPreview:
        assert game_id == self.game_id
        assert model_iteration_id == self.iteration_id
        return SymbolModelActivationPreview(
            game_id=game_id,
            model_iteration_id=model_iteration_id,
            candidate_manifest_checksum_sha256=self.checksum,
            current_model_iteration_id=self.current_id,
            action=action,
            can_activate=True,
        )

    def activate(
        self,
        *,
        game_id: UUID,
        model_iteration_id: UUID,
        expected_manifest_checksum_sha256: str,
        expected_current_model_iteration_id: UUID | None,
        action: SymbolModelActivationAction,
        actor: str,
        reason: str | None,
        idempotency_key: UUID,
        command_sha256: str,
    ) -> tuple[SymbolModelActivation, bool]:
        assert game_id == self.game_id
        assert model_iteration_id == self.iteration_id
        assert expected_manifest_checksum_sha256 == self.checksum
        existing = self.values.get(idempotency_key)
        if existing is not None:
            assert existing.command_sha256 == command_sha256
            return existing, False
        assert expected_current_model_iteration_id == self.current_id
        value = SymbolModelActivation(
            id=uuid4(),
            game_id=game_id,
            model_iteration_id=model_iteration_id,
            previous_model_iteration_id=self.current_id,
            action=action,
            activation_number=len(self.values) + 1,
            actor=actor,
            reason=reason,
            idempotency_key=idempotency_key,
            command_sha256=command_sha256,
            created_at=datetime.now(UTC),
        )
        self.values[idempotency_key] = value
        self.current_id = model_iteration_id
        return value, True

    def list(self, *, game_id: UUID, limit: int) -> tuple[SymbolModelActivation, ...]:
        assert game_id == self.game_id
        return tuple(reversed(tuple(self.values.values())))[:limit]


def _settings(tmp_path: Path) -> ApiSettings:
    return ApiSettings.from_environment(
        {
            "GAME_PREDICTOR_DATABASE_URL": (
                "postgresql+psycopg://unused:unused@localhost:5432/unused"
            ),
            "GAME_PREDICTOR_ARTIFACT_ROOT": str(tmp_path),
        }
    )


def test_activation_requires_preview_and_is_idempotent_and_auditable(tmp_path: Path) -> None:
    game_id = uuid4()
    iteration_id = uuid4()
    checksum = "a" * 64
    idempotency_key = uuid4()
    repository = MemoryRegistry(game_id, iteration_id, checksum)
    app = create_app(
        _settings(tmp_path),
        symbol_model_registry_service_dependency=lambda: SymbolModelRegistryService(repository),
    )
    body = {
        "actor": "local-owner",
        "expectedCurrentModelIterationId": None,
        "expectedManifestChecksumSha256": checksum,
        "idempotencyKey": str(idempotency_key),
        "reason": "owner acceptance",
    }
    with TestClient(app) as client:
        preview = client.get(
            f"/api/v1/admin/games/{game_id}/symbol-model-iterations/"
            f"{iteration_id}/activation-preview"
        )
        first = client.post(
            f"/api/v1/admin/games/{game_id}/symbol-model-iterations/{iteration_id}/activate",
            json=body,
        )
        second = client.post(
            f"/api/v1/admin/games/{game_id}/symbol-model-iterations/{iteration_id}/activate",
            json=body,
        )
        history = client.get(
            f"/api/v1/admin/games/{game_id}/symbol-model-iterations/registry/activations"
        )

    assert preview.status_code == 200
    assert preview.json()["candidateManifestChecksumSha256"] == checksum
    assert preview.json()["currentModelIterationId"] is None
    assert first.status_code == 200
    assert first.json()["created"] is True
    assert first.json()["activation"]["action"] == "activate"
    assert first.json()["activation"]["activationNumber"] == 1
    assert second.status_code == 200
    assert second.json()["created"] is False
    assert second.json()["activation"]["id"] == first.json()["activation"]["id"]
    assert history.status_code == 200
    assert [item["id"] for item in history.json()] == [first.json()["activation"]["id"]]
