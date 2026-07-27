import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.jobs import Job, JobType, create_job
from game_predictor_api.domain.mobile_releases import (
    MobileRelease,
    MobileReleaseConflictError,
    MobileReleaseGame,
    MobileReleaseGameInput,
    MobileReleaseNotFoundError,
    MobileReleaseStatus,
)
from game_predictor_api.main import create_app


class FakeMobileReleaseService:
    def __init__(self) -> None:
        self.items: dict[UUID, MobileRelease] = {}
        self.last_games: tuple[MobileReleaseGameInput, ...] = ()

    def list_mobile_releases(self) -> list[MobileRelease]:
        return list(self.items.values())

    def get_mobile_release(self, mobile_release_id: UUID) -> MobileRelease:
        release = self.items.get(mobile_release_id)
        if release is None:
            raise MobileReleaseNotFoundError(
                "MOBILE_RELEASE_NOT_FOUND",
                "Mobile release does not exist.",
            )
        return release

    def create_mobile_release(
        self,
        *,
        version: str,
        games: tuple[MobileReleaseGameInput, ...],
    ) -> MobileRelease:
        if any(item.version == version for item in self.items.values()):
            raise MobileReleaseConflictError(
                "MOBILE_RELEASE_VERSION_ALREADY_EXISTS",
                "A mobile release with this version already exists.",
            )
        self.last_games = games
        release = MobileRelease(
            id=uuid4(),
            version=version,
            status=MobileReleaseStatus.DRAFT,
            algorithm_version="payout-v2",
            snapshot_schema_version=2,
            snapshot_path=None,
            snapshot_checksum=None,
            apk_path=None,
            apk_checksum=None,
            build_job_id=None,
            created_at=datetime.now(UTC),
            ready_at=None,
            games=tuple(
                MobileReleaseGame(
                    game_id=game.game_id,
                    game_code=f"game-{index}",
                    dataset_version_id=game.dataset_version_id,
                    dataset_version=index,
                    rules_version_id=game.rules_version_id,
                    rules_version=index + 10,
                    rows=3,
                    columns=5,
                    layout_count=index * 1000,
                )
                for index, game in enumerate(games, start=1)
            ),
        )
        self.items[release.id] = release
        return release

    def start_mobile_release_build(self, mobile_release_id: UUID) -> Job:
        release = self.get_mobile_release(mobile_release_id)
        if release.build_job_id is not None:
            raise MobileReleaseConflictError(
                "MOBILE_RELEASE_BUILD_ALREADY_STARTED",
                "The build already started.",
            )
        job = create_job(
            JobType.ANDROID_BUILD,
            game_id=None,
            input_payload={
                "schema_version": 1,
                "mobile_release_id": str(mobile_release_id),
            },
        )
        self.items[mobile_release_id] = replace(
            release,
            status=MobileReleaseStatus.BUILDING,
            build_job_id=job.id,
        )
        return job


def _client(
    service: FakeMobileReleaseService,
    *,
    artifact_root: Path | None = None,
) -> TestClient:
    settings = ApiSettings.from_environment({})
    if artifact_root is not None:
        settings = replace(settings, artifact_root=artifact_root)
    return TestClient(
        create_app(
            settings,
            mobile_release_service_dependency=lambda: service,
        )
    )


def test_create_list_and_get_mobile_release_contract() -> None:
    service = FakeMobileReleaseService()
    game_id = uuid4()
    dataset_id = uuid4()
    rules_id = uuid4()

    with _client(service) as client:
        created = client.post(
            "/api/v1/admin/mobile-releases",
            json={
                "version": "m3.4.1",
                "games": [
                    {
                        "gameId": str(game_id),
                        "datasetVersionId": str(dataset_id),
                        "rulesVersionId": str(rules_id),
                    }
                ],
            },
        )
        assert created.status_code == 201
        body = created.json()
        assert {
            "version": body["version"],
            "status": body["status"],
            "algorithmVersion": body["algorithmVersion"],
            "snapshotSchemaVersion": body["snapshotSchemaVersion"],
            "snapshot": body["snapshot"],
            "apk": body["apk"],
            "buildJobId": body["buildJobId"],
            "readyAt": body["readyAt"],
        } == {
            "version": "m3.4.1",
            "status": "draft",
            "algorithmVersion": "payout-v2",
            "snapshotSchemaVersion": 2,
            "snapshot": None,
            "apk": None,
            "buildJobId": None,
            "readyAt": None,
        }
        assert body["games"] == [
            {
                "gameId": str(game_id),
                "gameCode": "game-1",
                "datasetVersionId": str(dataset_id),
                "datasetVersion": 1,
                "rulesVersionId": str(rules_id),
                "rulesVersion": 11,
                "rows": 3,
                "columns": 5,
                "layoutCount": 1000,
            }
        ]
        assert service.last_games == (MobileReleaseGameInput(game_id, dataset_id, rules_id),)

        release_id = body["id"]
        listed = client.get("/api/v1/admin/mobile-releases")
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()] == [release_id]

        detail = client.get(f"/api/v1/admin/mobile-releases/{release_id}")
        assert detail.status_code == 200
        assert detail.json() == body


def test_mobile_release_api_maps_validation_conflict_and_missing() -> None:
    service = FakeMobileReleaseService()
    game = {
        "gameId": str(uuid4()),
        "datasetVersionId": str(uuid4()),
        "rulesVersionId": str(uuid4()),
    }

    with _client(service) as client:
        invalid = client.post(
            "/api/v1/admin/mobile-releases",
            json={"version": "release-1", "games": []},
        )
        assert invalid.status_code == 422
        assert invalid.json()["code"] == "VALIDATION_ERROR"

        first = client.post(
            "/api/v1/admin/mobile-releases",
            json={"version": "release-1", "games": [game]},
        )
        assert first.status_code == 201

        conflict = client.post(
            "/api/v1/admin/mobile-releases",
            json={"version": "release-1", "games": [game]},
        )
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "MOBILE_RELEASE_VERSION_ALREADY_EXISTS"

        missing = client.get(f"/api/v1/admin/mobile-releases/{uuid4()}")
        assert missing.status_code == 404
        assert missing.json()["code"] == "MOBILE_RELEASE_NOT_FOUND"


def test_mobile_release_build_endpoint_returns_one_typed_job() -> None:
    service = FakeMobileReleaseService()
    game = {
        "gameId": str(uuid4()),
        "datasetVersionId": str(uuid4()),
        "rulesVersionId": str(uuid4()),
    }
    with _client(service) as client:
        created = client.post(
            "/api/v1/admin/mobile-releases",
            json={"version": "release-build-api", "games": [game]},
        ).json()
        response = client.post(f"/api/v1/admin/mobile-releases/{created['id']}/build")

        assert response.status_code == 201
        assert response.json()["status"] == "created"
        assert UUID(response.json()["jobId"])
        release = service.items[UUID(created["id"])]
        assert release.status is MobileReleaseStatus.BUILDING
        assert release.build_job_id == UUID(response.json()["jobId"])

        duplicate = client.post(f"/api/v1/admin/mobile-releases/{created['id']}/build")
        assert duplicate.status_code == 409
        assert duplicate.json()["code"] == "MOBILE_RELEASE_BUILD_ALREADY_STARTED"


def test_ready_apk_download_is_controlled_by_release_identity(
    tmp_path: Path,
) -> None:
    service = FakeMobileReleaseService()
    game = {
        "gameId": str(uuid4()),
        "datasetVersionId": str(uuid4()),
        "rulesVersionId": str(uuid4()),
    }
    with _client(service, artifact_root=tmp_path) as client:
        created = client.post(
            "/api/v1/admin/mobile-releases",
            json={"version": "release-download", "games": [game]},
        ).json()
        release_id = UUID(created["id"])

        unavailable = client.get(f"/api/v1/admin/mobile-releases/{release_id}/apk")
        assert unavailable.status_code == 409
        assert unavailable.json()["code"] == "MOBILE_RELEASE_APK_NOT_READY"

        apk_bytes = b"verified-test-apk"
        relative_path = "android-releases/release-download/app-release.apk"
        apk_path = tmp_path.joinpath(*relative_path.split("/"))
        apk_path.parent.mkdir(parents=True)
        apk_path.write_bytes(apk_bytes)
        checksum = hashlib.sha256(apk_bytes).hexdigest()
        service.items[release_id] = replace(
            service.items[release_id],
            status=MobileReleaseStatus.READY,
            apk_path=relative_path,
            apk_checksum=checksum,
            ready_at=datetime.now(UTC),
        )

        response = client.get(f"/api/v1/admin/mobile-releases/{release_id}/apk")
        assert response.status_code == 200
        assert response.content == apk_bytes
        assert response.headers["content-type"] == ("application/vnd.android.package-archive")
        assert "game-predictor-release-download.apk" in response.headers["content-disposition"]

        service.items[release_id] = replace(
            service.items[release_id],
            apk_checksum="0" * 64,
        )
        changed = client.get(f"/api/v1/admin/mobile-releases/{release_id}/apk")
        assert changed.status_code == 409
        assert changed.json()["code"] == "MOBILE_RELEASE_APK_CHECKSUM_MISMATCH"
