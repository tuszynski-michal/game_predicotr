from dataclasses import replace
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.cleanup import (
    BoardSourceCleanupSelection,
    CleanupCommand,
    CleanupCount,
    CleanupResult,
    CleanupSnapshot,
    cleanup_preview,
)
from game_predictor_api.main import create_app


class FakeCleanupService:
    def __init__(self) -> None:
        self.game_id = uuid4()
        self.release_id = uuid4()
        self.last_command: CleanupCommand | None = None

    def _snapshot(self, kind: str, target_id: UUID) -> CleanupSnapshot:
        return CleanupSnapshot(
            kind=kind,  # type: ignore[arg-type]
            target_id=target_id,
            target_label="controlled-target",
            confirmation_target=str(target_id),
            counts=(CleanupCount("layouts", 12),),
            artifact_paths=("data/crops/test.jpg",),
            retained_shared_artifact_count=2,
            blockers=(),
        )

    def preview_release(self, target_id: UUID):
        return cleanup_preview(self._snapshot("mobile_release", target_id))

    def preview_game_reset(self, target_id: UUID):
        return cleanup_preview(self._snapshot("game_layout_data", target_id))

    def delete_release(self, target_id: UUID, command: CleanupCommand):
        return self._result("mobile_release", target_id, command)

    def reset_game(self, target_id: UUID, command: CleanupCommand):
        return self._result("game_layout_data", target_id, command)

    def preview_board_sources(
        self,
        target_id: UUID,
        selection: BoardSourceCleanupSelection,
    ):
        snapshot = self._snapshot("board_source_ranges", target_id)
        snapshot = replace(
            snapshot,
            confirmation_target=f"{target_id}:1-9",
            target_label=",".join(str(value) for value in selection.sequence_numbers),
        )
        return cleanup_preview(snapshot)

    def delete_board_sources(
        self,
        target_id: UUID,
        selection: BoardSourceCleanupSelection,
        command: CleanupCommand,
    ):
        assert selection.sequence_numbers == tuple(range(1, 10))
        return self._result("board_source_ranges", target_id, command)

    def _result(self, kind: str, target_id: UUID, command: CleanupCommand):
        self.last_command = command
        return CleanupResult(
            kind=kind,  # type: ignore[arg-type]
            target_id=target_id,
            target_label="controlled-target",
            preview_token=command.preview_token,
            deleted_counts=(CleanupCount("layouts", 12),),
            deleted_artifact_count=1,
            retained_shared_artifact_count=2,
        )


def test_cleanup_preview_and_execution_contracts() -> None:
    service = FakeCleanupService()
    app = create_app(
        ApiSettings.from_environment({}),
        cleanup_service_dependency=lambda: service,
    )
    with TestClient(app) as client:
        preview_response = client.get(
            f"/api/v1/admin/games/{service.game_id}/layout-data-reset-preview"
        )
        assert preview_response.status_code == 200
        preview = preview_response.json()
        assert preview["confirmationTarget"] == str(service.game_id)
        assert preview["counts"] == [{"name": "layouts", "count": 12}]
        assert preview["retainedSharedArtifactCount"] == 2

        executed = client.request(
            "DELETE",
            f"/api/v1/admin/games/{service.game_id}/layout-data",
            json={
                "previewToken": preview["previewToken"],
                "confirmationTarget": str(service.game_id),
                "confirmed": True,
            },
        )
        assert executed.status_code == 200
        assert executed.json()["deletedArtifactCount"] == 1
        assert service.last_command is not None
        assert service.last_command.confirmation_target == str(service.game_id)

        release_preview = client.get(
            f"/api/v1/admin/mobile-releases/{service.release_id}/deletion-preview"
        )
        assert release_preview.status_code == 200
        assert release_preview.json()["kind"] == "mobile_release"


def test_cleanup_request_rejects_incomplete_confirmation_body() -> None:
    service = FakeCleanupService()
    with TestClient(
        create_app(
            ApiSettings.from_environment({}),
            cleanup_service_dependency=lambda: service,
        )
    ) as client:
        response = client.request(
            "DELETE",
            f"/api/v1/admin/mobile-releases/{service.release_id}",
            json={"confirmed": True},
        )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_board_source_cleanup_contract_normalizes_selection_and_requires_preview() -> None:
    service = FakeCleanupService()
    with TestClient(
        create_app(
            ApiSettings.from_environment({}),
            cleanup_service_dependency=lambda: service,
        )
    ) as client:
        preview_response = client.post(
            f"/api/v1/admin/games/{service.game_id}/board-source-cleanup-preview",
            json={"sequenceNumbers": [9, 1, 2, 3, 4, 5, 6, 7, 8, 1]},
        )
        assert preview_response.status_code == 200
        preview = preview_response.json()
        assert preview["kind"] == "board_source_ranges"
        assert preview["confirmationTarget"] == f"{service.game_id}:1-9"

        executed = client.request(
            "DELETE",
            f"/api/v1/admin/games/{service.game_id}/board-sources",
            json={
                "sequenceNumbers": list(range(1, 10)),
                "previewToken": preview["previewToken"],
                "confirmationTarget": preview["confirmationTarget"],
                "confirmed": True,
            },
        )
        assert executed.status_code == 200
        assert executed.json()["kind"] == "board_source_ranges"
