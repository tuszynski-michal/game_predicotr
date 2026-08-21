from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from game_predictor_api.application.reviewer_access import ReviewerAccessService
from game_predictor_api.application.reviewer_ingress import ReviewerIngressStatus
from game_predictor_api.application.reviewer_work_assignments import (
    ReviewerWorkAssignmentService,
)
from game_predictor_api.application.reviewer_work_lifecycle import (
    ReviewerWorkLifecycleService,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.main import create_app


class _SharedIngress:
    def __init__(self) -> None:
        self.online = False
        self.ready = False
        self.instance_id: UUID | None = None
        self.start_count = 0
        self.stop_count = 0

    def status(self) -> ReviewerIngressStatus:
        return self._status()

    def start(self) -> ReviewerIngressStatus:
        self.start_count += 1
        self.online = True
        self.ready = True
        self.instance_id = self.instance_id or uuid4()
        return self._status()

    def start_local(self) -> ReviewerIngressStatus:
        self.ready = True
        return self._status()

    def stop_if_current(self, instance_id: UUID) -> ReviewerIngressStatus:
        if self.instance_id == instance_id:
            self.online = False
            self.instance_id = None
            self.stop_count += 1
        return self._status()

    def _status(self) -> ReviewerIngressStatus:
        return ReviewerIngressStatus(
            state="running" if self.online else "stopped",
            public_origin=("https://shared-reviewer.trycloudflare.com" if self.online else None),
            target="http://127.0.0.1:3001",
            started_at=datetime.now(UTC) if self.ready else None,
            reviewer_ready=self.ready,
            instance_id=self.instance_id,
        )


def _client() -> tuple[TestClient, _SharedIngress]:
    ingress = _SharedIngress()
    lifecycle = ReviewerWorkLifecycleService(
        ReviewerWorkAssignmentService(),
        ReviewerAccessService("http://127.0.0.1:3001"),
        ingress,
    )
    app = create_app(
        ApiSettings.from_environment({}),
        reviewer_work_lifecycle_service_dependency=lambda: lifecycle,
    )
    return TestClient(app), ingress


def _open_path(game_id: UUID, import_job_id: UUID, mode: str) -> str:
    return f"/api/v1/admin/games/{game_id}/imports/{import_job_id}/reviewer-work-assignments/{mode}"


def test_online_open_is_idempotent_and_list_never_returns_secrets() -> None:
    client, ingress = _client()
    game_id = uuid4()
    import_job_id = uuid4()

    with client:
        first = client.post(
            _open_path(game_id, import_job_id, "online"),
            json={"lifetimeMinutes": 480},
        )
        repeated = client.post(
            _open_path(game_id, import_job_id, "online"),
            json={"lifetimeMinutes": 480},
        )
        overview = client.get(f"/api/v1/admin/games/{game_id}/reviewer-work-assignments")

    assert first.status_code == 200
    assert first.json()["created"] is True
    assert len(first.json()["accessCode"]) == 9
    assert repeated.status_code == 200
    assert repeated.json()["created"] is False
    assert repeated.json()["accessCode"] is None
    assert (
        repeated.json()["assignment"]["assignmentId"] == first.json()["assignment"]["assignmentId"]
    )
    assert overview.status_code == 200
    assert overview.json()["activeOnlineCount"] == 1
    serialized = overview.text
    assert "accessCode" not in serialized
    assert "leaseToken" not in serialized
    assert "reviewerAccessSessionId" not in serialized
    assert ingress.online is True


def test_closing_one_assignment_keeps_other_online_scope_and_local_work() -> None:
    client, ingress = _client()
    game_id = uuid4()
    first_job_id = uuid4()
    second_job_id = uuid4()
    local_job_id = uuid4()

    with client:
        first = client.post(
            _open_path(game_id, first_job_id, "online"),
            json={"lifetimeMinutes": 480},
        ).json()
        client.post(
            _open_path(game_id, second_job_id, "online"),
            json={"lifetimeMinutes": 480},
        )
        local = client.post(
            _open_path(game_id, local_job_id, "local"),
            json={"lifetimeMinutes": 480},
        )
        closed = client.post(
            f"/api/v1/admin/reviewer-work-assignments/{first['assignment']['assignmentId']}/close",
            json={"confirmed": True},
        )
        overview = client.get(f"/api/v1/admin/games/{game_id}/reviewer-work-assignments").json()

    assert local.status_code == 200
    assert local.json()["assignment"]["ready"] is True
    assert local.json()["assignment"]["assignmentType"] == "local"
    assert closed.status_code == 200
    assert closed.json()["closeReason"] == "owner_stopped"
    assert overview["activeOnlineCount"] == 1
    assert len(overview["assignments"]) == 2
    assert ingress.online is True
    assert ingress.stop_count == 0


def test_heartbeat_and_close_are_scoped_to_existing_assignment() -> None:
    client, _ingress = _client()
    game_id = uuid4()
    import_job_id = uuid4()

    with client:
        opened = client.post(
            _open_path(game_id, import_job_id, "local"),
            json={"lifetimeMinutes": 480},
        ).json()
        assignment_id = opened["assignment"]["assignmentId"]
        heartbeat = client.post(
            f"/api/v1/admin/reviewer-work-assignments/{assignment_id}/heartbeat",
            json={"confirmed": True},
        )
        closed = client.post(
            f"/api/v1/admin/reviewer-work-assignments/{assignment_id}/close",
            json={"confirmed": True},
        )
        stale_heartbeat = client.post(
            f"/api/v1/admin/reviewer-work-assignments/{assignment_id}/heartbeat",
            json={"confirmed": True},
        )

    assert heartbeat.status_code == 200
    assert heartbeat.json()["assignmentId"] == assignment_id
    assert closed.status_code == 200
    assert stale_heartbeat.status_code == 409
    assert stale_heartbeat.json()["code"] == "REVIEWER_ASSIGNMENT_LEASE_LOST"


def test_three_online_and_one_local_scope_share_one_reviewer_across_reload() -> None:
    client, ingress = _client()
    game_id = uuid4()
    online_job_ids = [uuid4() for _index in range(3)]
    local_job_id = uuid4()

    with client:
        first = client.post(
            _open_path(game_id, online_job_ids[0], "online"),
            json={"lifetimeMinutes": 480},
        )

        def open_second_scope() -> dict[str, object]:
            response = client.post(
                _open_path(game_id, online_job_ids[1], "online"),
                json={"lifetimeMinutes": 480},
            )
            assert response.status_code == 200
            return response.json()

        with ThreadPoolExecutor(max_workers=2) as executor:
            repeated_second = list(executor.map(lambda _index: open_second_scope(), range(2)))

        third = client.post(
            _open_path(game_id, online_job_ids[2], "online"),
            json={"lifetimeMinutes": 480},
        )
        local = client.post(
            _open_path(game_id, local_job_id, "local"),
            json={"lifetimeMinutes": 480},
        )

    assert first.status_code == 200
    assert third.status_code == 200
    assert local.status_code == 200
    assert sorted(item["created"] for item in repeated_second) == [False, True]
    assert len(
        {item["assignment"]["assignmentId"] for item in repeated_second}  # type: ignore[index]
    ) == 1
    assert ingress.start_count == 1

    restarted_client = TestClient(client.app)
    with restarted_client:
        overview = restarted_client.get(
            f"/api/v1/admin/games/{game_id}/reviewer-work-assignments"
        )

    assert overview.status_code == 200
    overview_payload = overview.json()
    assert overview_payload["activeOnlineCount"] == 3
    assert overview_payload["maximumOnlineCount"] == 3
    assert len(overview_payload["assignments"]) == 4
    assert sorted(
        assignment["assignmentType"] for assignment in overview_payload["assignments"]
    ) == ["local", "online", "online", "online"]
    assert all(assignment["ready"] is True for assignment in overview_payload["assignments"])
    serialized = overview.text
    assert "accessCode" not in serialized
    assert "leaseToken" not in serialized
    assert "reviewerAccessSessionId" not in serialized

    online_assignments = [
        assignment
        for assignment in overview_payload["assignments"]
        if assignment["assignmentType"] == "online"
    ]
    with restarted_client:
        for index, assignment in enumerate(online_assignments):
            closed = restarted_client.post(
                f"/api/v1/admin/reviewer-work-assignments/{assignment['assignmentId']}/close",
                json={"confirmed": True},
            )
            assert closed.status_code == 200
            assert ingress.stop_count == (1 if index == 2 else 0)
        final_overview = restarted_client.get(
            f"/api/v1/admin/games/{game_id}/reviewer-work-assignments"
        ).json()

    assert final_overview["activeOnlineCount"] == 0
    assert len(final_overview["assignments"]) == 1
    assert final_overview["assignments"][0]["assignmentType"] == "local"
    assert ingress.online is False
