"""TASK-0947: HTTP contract of listing, previewing and reverting geometry corrections.

The service is the real ``GeometryCorrectionRevertService`` over an in-memory
repository, so request validation, CAS pass-through, actor selection, the
response mapping and the error envelope are exercised end to end without a
database. Rule evaluation itself is covered by the TASK-0945/0946 suites.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.application.geometry_correction_reverts import (
    GeometryCorrectionEntry,
    GeometryCorrectionRevertPreview,
    GeometryCorrectionRevertRepository,
    GeometryCorrectionRevertResult,
    GeometryCorrectionRevertService,
    RestoredRenderVerifier,
    VirtualRestoredRenderVerifier,
)
from game_predictor_api.application.reviewer_access import ReviewerAccessError
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.geometry_correction_reverts import (
    GEOMETRY_CORRECTION_NOT_FOUND,
    GEOMETRY_REVERT_IDEMPOTENCY_CONFLICT,
    GEOMETRY_REVERT_RENDER_FAILED,
    GEOMETRY_REVERT_RENDERER_UNAVAILABLE,
    GeometryCorrectionKind,
    RejectionTarget,
    RevertBlockingReason,
    blocking_reason_message,
)
from game_predictor_api.domain.image_geometry_completeness import SourceImageGeometryStatus
from game_predictor_api.domain.image_reviews import (
    ImageReviewConflictError,
    ImageReviewNotFoundError,
)
from game_predictor_api.main import create_app

GAME_ID = uuid4()
IMPORT_JOB_ID = uuid4()
NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)


def _entry(
    *,
    minutes: int = 0,
    kind: GeometryCorrectionKind = GeometryCorrectionKind.PENDING_SLOT,
    blocking: RevertBlockingReason | None = None,
    sequence_number: int = 69004,
) -> GeometryCorrectionEntry:
    return GeometryCorrectionEntry(
        board_geometry_revision_id=uuid4(),
        kind=kind,
        recognized_board_id=uuid4(),
        review_item_id=uuid4(),
        pending_geometry_id=uuid4() if kind is GeometryCorrectionKind.PENDING_SLOT else None,
        source_image_id=uuid4(),
        sequence_number=sequence_number,
        position_index=2,
        created_at=NOW - timedelta(minutes=minutes),
        actor="local-admin",
        geometry_revision=1,
        resolution_revision=3,
        blocking_reason=blocking,
    )


class MemoryRevertRepository(GeometryCorrectionRevertRepository):
    """Records every call; ``revert`` mimics idempotent replay and CAS refusal."""

    def __init__(self) -> None:
        self.entries: list[GeometryCorrectionEntry] = []
        self.list_calls: list[int] = []
        self.revert_calls: list[dict[str, object]] = []
        self.results: dict[UUID, GeometryCorrectionRevertResult] = {}
        self.raise_on_revert: Exception | None = None
        self.verifiers: list[RestoredRenderVerifier | None] = []

    def list_recent(
        self, *, game_id: UUID, import_job_id: UUID, limit: int
    ) -> tuple[GeometryCorrectionEntry, ...]:
        self.list_calls.append(limit)
        ordered = sorted(self.entries, key=lambda entry: entry.created_at, reverse=True)
        return tuple(ordered[:limit])

    def _find(self, board_geometry_revision_id: UUID) -> GeometryCorrectionEntry:
        for entry in self.entries:
            if entry.board_geometry_revision_id == board_geometry_revision_id:
                return entry
        raise ImageReviewNotFoundError(GEOMETRY_CORRECTION_NOT_FOUND, "Nie znaleziono korekty.")

    def preview(
        self, *, game_id: UUID, import_job_id: UUID, board_geometry_revision_id: UUID
    ) -> GeometryCorrectionRevertPreview:
        entry = self._find(board_geometry_revision_id)
        return GeometryCorrectionRevertPreview(
            correction=entry,
            removes_board=entry.kind is GeometryCorrectionKind.PENDING_SLOT,
            removed_cell_count=15,
            repointed_board_count=1,
            restored_cell_decision_count=0,
            reverted_source_geometry_revision_id=(
                None if entry.kind is GeometryCorrectionKind.REJECTION else uuid4()
            ),
            restored_source_geometry_revision_id=uuid4(),
            restored_source_engine_kind="neural_grid_v1",
            restored_source_status="current",
        )

    def revert(  # type: ignore[no-untyped-def]
        self,
        *,
        game_id,
        import_job_id,
        board_geometry_revision_id,
        idempotency_key,
        expected_geometry_revision,
        expected_resolution_revision,
        actor,
        reverted_at,
        render_verifier=None,
    ):
        self.revert_calls.append(
            {
                "idempotency_key": idempotency_key,
                "expected_geometry_revision": expected_geometry_revision,
                "expected_resolution_revision": expected_resolution_revision,
                "actor": actor,
                "render_verifier": render_verifier,
            }
        )
        if self.raise_on_revert is not None:
            raise self.raise_on_revert
        entry = self._find(board_geometry_revision_id)
        previous = self.results.get(idempotency_key)
        if previous is not None:
            if previous.board_geometry_revision_id != board_geometry_revision_id:
                raise ImageReviewConflictError(
                    GEOMETRY_REVERT_IDEMPOTENCY_CONFLICT, "Klucz użyty dla innej korekty."
                )
            return replace(previous, created=False)
        result = GeometryCorrectionRevertResult(
            revert_id=uuid4(),
            created=True,
            kind=entry.kind,
            board_geometry_revision_id=board_geometry_revision_id,
            pending_geometry_id=entry.pending_geometry_id,
            recognized_board_id=entry.recognized_board_id,
            review_item_id=entry.review_item_id,
            reverted_source_geometry_revision_id=uuid4(),
            restored_source_geometry_revision_id=uuid4(),
            repointed_board_ids=(uuid4(),),
            removed_cell_count=15,
            source_image_geometry_status=SourceImageGeometryStatus.GEOMETRY_INCOMPLETE,
            snapshot_checksum_sha256="a" * 64,
            created_at=reverted_at,
        )
        self.results[idempotency_key] = result
        return result


class VerifierStub:
    def rendered_pixel_checksums(self, request):  # type: ignore[no-untyped-def]
        return {}


class ScopedReviewerAccess:
    def __init__(self) -> None:
        self.session_id = uuid4()
        self._session = type(
            "ScopedSession",
            (),
            {"id": self.session_id, "game_id": GAME_ID, "import_job_id": IMPORT_JOB_ID},
        )()

    def authenticate(self, access_token: str):  # type: ignore[no-untyped-def]
        if access_token != "scoped-token":
            raise ReviewerAccessError("REVIEWER_TOKEN_INVALID", "Invalid token.")
        return self._session

    def authorize_scope(self, session, *, game_id, import_job_id):  # type: ignore[no-untyped-def]
        if session.game_id != game_id or session.import_job_id != import_job_id:
            raise ReviewerAccessError("REVIEWER_SCOPE_FORBIDDEN", "Foreign scope.")


def _settings(tmp_path: Path) -> ApiSettings:
    return ApiSettings.from_environment(
        {
            "GAME_PREDICTOR_DATABASE_URL": (
                "postgresql+psycopg://unused:unused@localhost:5432/unused"
            ),
            "GAME_PREDICTOR_ARTIFACT_ROOT": str(tmp_path),
        }
    )


def _client(
    tmp_path: Path,
    repository: MemoryRevertRepository,
    *,
    reviewer_access: ScopedReviewerAccess | None = None,
) -> TestClient:
    service = GeometryCorrectionRevertService(repository, render_verifier=VerifierStub())
    kwargs: dict[str, object] = {}
    if reviewer_access is not None:
        kwargs["reviewer_access_service_dependency"] = lambda: reviewer_access
    app = create_app(
        _settings(tmp_path),
        geometry_correction_revert_service_dependency=lambda: service,
        **kwargs,  # type: ignore[arg-type]
    )
    return TestClient(app)


def _base(game_id: UUID = GAME_ID) -> str:
    return f"/api/v1/admin/games/{game_id}/image-imports/{IMPORT_JOB_ID}/geometry-corrections"


def _command(key: UUID | None = None, geometry: int = 1, resolution: int = 3) -> dict[str, object]:
    return {
        "idempotencyKey": str(key or uuid4()),
        "expectedGeometryRevision": geometry,
        "expectedResolutionRevision": resolution,
    }


def test_list_is_empty_for_an_import_without_corrections(tmp_path: Path) -> None:
    repository = MemoryRevertRepository()
    with _client(tmp_path, repository) as client:
        response = client.get(_base())

    assert response.status_code == 200
    assert response.json() == {"items": []}
    assert repository.list_calls == [20]


def test_list_orders_newest_first_applies_limit_and_reports_blocking(tmp_path: Path) -> None:
    repository = MemoryRevertRepository()
    oldest = _entry(minutes=30)
    blocked = _entry(minutes=10, blocking=RevertBlockingReason.CELLS_CHANGED)
    newest = _entry(minutes=1, kind=GeometryCorrectionKind.BOARD_REVISION)
    repository.entries = [oldest, newest, blocked]
    with _client(tmp_path, repository) as client:
        full = client.get(_base())
        limited = client.get(_base(), params={"limit": 2})
        maximum = client.get(_base(), params={"limit": 50})
        too_many = client.get(_base(), params={"limit": 51})
        zero = client.get(_base(), params={"limit": 0})

    items = full.json()["items"]
    assert [item["boardGeometryRevisionId"] for item in items] == [
        str(newest.board_geometry_revision_id),
        str(blocked.board_geometry_revision_id),
        str(oldest.board_geometry_revision_id),
    ]
    assert items[0]["kind"] == "board_revision"
    assert items[0]["revertable"] is True
    assert items[0]["blockingReasonCode"] is None
    assert items[0]["blockingReasonMessage"] is None
    assert items[1]["revertable"] is False
    assert items[1]["blockingReasonCode"] == "GEOMETRY_REVERT_CELLS_CHANGED"
    assert items[1]["blockingReasonMessage"] == blocking_reason_message(
        RevertBlockingReason.CELLS_CHANGED
    )
    assert {"sequenceNumber", "positionIndex", "createdAt", "actor", "geometryRevision"} <= set(
        items[0]
    )
    assert items[0]["resolutionRevision"] == 3
    assert len(limited.json()["items"]) == 2
    assert maximum.status_code == 200
    assert too_many.status_code == 422
    assert zero.status_code == 422
    assert repository.list_calls == [20, 2, 50]


def test_preview_returns_effects_and_cas_tokens_without_writing(tmp_path: Path) -> None:
    repository = MemoryRevertRepository()
    entry = _entry()
    repository.entries = [entry]
    with _client(tmp_path, repository) as client:
        response = client.get(f"{_base()}/{entry.board_geometry_revision_id}/revert-preview")
        missing = client.get(f"{_base()}/{uuid4()}/revert-preview")

    assert response.status_code == 200
    body = response.json()
    assert body["removesBoard"] is True
    assert body["removedCellCount"] == 15
    assert body["repointedBoardCount"] == 1
    assert body["restoredCellDecisionCount"] == 0
    assert body["restoredSourceEngineKind"] == "neural_grid_v1"
    assert body["restoredSourceStatus"] == "current"
    assert body["expectedGeometryRevision"] == 1
    assert body["expectedResolutionRevision"] == 3
    assert body["correction"]["boardGeometryRevisionId"] == str(entry.board_geometry_revision_id)
    assert repository.revert_calls == []
    assert missing.status_code == 404
    assert missing.json()["code"] == GEOMETRY_CORRECTION_NOT_FOUND


def test_revert_succeeds_and_replay_with_the_same_key_returns_the_stored_result(
    tmp_path: Path,
) -> None:
    repository = MemoryRevertRepository()
    entry = _entry()
    repository.entries = [entry]
    key = uuid4()
    url = f"{_base()}/{entry.board_geometry_revision_id}/revert"
    with _client(tmp_path, repository) as client:
        first = client.post(url, json=_command(key))
        replay = client.post(url, json=_command(key))
        other_target = client.post(
            f"{_base()}/{_entry().board_geometry_revision_id}/revert", json=_command(key)
        )

    assert first.status_code == 200
    body = first.json()
    assert body["created"] is True
    assert body["kind"] == "pending_slot"
    assert body["boardGeometryRevisionId"] == str(entry.board_geometry_revision_id)
    assert body["removedCellCount"] == 15
    assert body["sourceImageGeometryStatus"] == "geometry_incomplete"
    assert body["snapshotChecksumSha256"] == "a" * 64
    assert len(body["repointedBoardIds"]) == 1
    assert replay.status_code == 200
    assert replay.json()["created"] is False
    assert replay.json()["revertId"] == body["revertId"]
    assert other_target.status_code == 404
    first_call = repository.revert_calls[0]
    assert first_call["actor"] == "local-admin"
    assert first_call["expected_geometry_revision"] == 1
    assert first_call["expected_resolution_revision"] == 3
    assert first_call["render_verifier"] is not None


def test_revert_with_a_key_used_for_another_correction_conflicts(tmp_path: Path) -> None:
    repository = MemoryRevertRepository()
    first_entry, second_entry = _entry(), _entry(minutes=5)
    repository.entries = [first_entry, second_entry]
    key = uuid4()
    with _client(tmp_path, repository) as client:
        client.post(
            f"{_base()}/{first_entry.board_geometry_revision_id}/revert", json=_command(key)
        )
        conflict = client.post(
            f"{_base()}/{second_entry.board_geometry_revision_id}/revert", json=_command(key)
        )

    assert conflict.status_code == 409
    assert conflict.json()["code"] == GEOMETRY_REVERT_IDEMPOTENCY_CONFLICT


@pytest.mark.parametrize("reason", list(RevertBlockingReason))
def test_every_blocking_code_maps_to_409_with_code_and_polish_message(
    tmp_path: Path, reason: RevertBlockingReason
) -> None:
    repository = MemoryRevertRepository()
    entry = _entry()
    repository.entries = [entry]
    repository.raise_on_revert = ImageReviewConflictError(
        reason.value, blocking_reason_message(reason)
    )
    with _client(tmp_path, repository) as client:
        response = client.post(
            f"{_base()}/{entry.board_geometry_revision_id}/revert", json=_command()
        )

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == reason.value
    assert body["message"] == blocking_reason_message(reason)


def test_stale_cas_history_incomplete_and_renderer_errors_map_to_409(
    tmp_path: Path,
) -> None:
    repository = MemoryRevertRepository()
    entry = _entry()
    repository.entries = [entry]
    url = f"{_base()}/{entry.board_geometry_revision_id}/revert"
    codes = [
        RevertBlockingReason.STALE.value,
        RevertBlockingReason.HISTORY_INCOMPLETE.value,
        GEOMETRY_REVERT_RENDERER_UNAVAILABLE,
        GEOMETRY_REVERT_RENDER_FAILED,
    ]
    seen: list[tuple[int, str, str]] = []
    with _client(tmp_path, repository) as client:
        for code in codes:
            repository.raise_on_revert = ImageReviewConflictError(code, "Komunikat.")
            response = client.post(url, json=_command(geometry=99))
            body = response.json()
            seen.append((response.status_code, body["code"], body["message"]))

    assert seen == [(409, code, "Komunikat.") for code in codes]
    assert repository.revert_calls[0]["expected_geometry_revision"] == 99


def test_revert_validation_errors_are_422(tmp_path: Path) -> None:
    repository = MemoryRevertRepository()
    entry = _entry()
    repository.entries = [entry]
    url = f"{_base()}/{entry.board_geometry_revision_id}/revert"
    with _client(tmp_path, repository) as client:
        missing_key = client.post(url, json={"expectedGeometryRevision": 1})
        bad_key = client.post(url, json={**_command(), "idempotencyKey": "not-a-uuid"})
        negative = client.post(url, json=_command(geometry=-1))
        extra = client.post(url, json={**_command(), "unexpected": True})
        bad_id = client.post(f"{_base()}/not-a-uuid/revert", json=_command())

    for response in (missing_key, bad_key, negative, extra, bad_id):
        assert response.status_code == 422
    assert repository.revert_calls == []


def test_reviewer_session_is_the_actor_and_foreign_scope_is_refused(tmp_path: Path) -> None:
    repository = MemoryRevertRepository()
    entry = _entry()
    repository.entries = [entry]
    reviewer_access = ScopedReviewerAccess()
    reviewer = {"Authorization": "Bearer scoped-token"}
    url = f"{_base()}/{entry.board_geometry_revision_id}/revert"
    with _client(tmp_path, repository, reviewer_access=reviewer_access) as client:
        allowed = client.post(url, json=_command(), headers=reviewer)
        listed = client.get(_base(), headers=reviewer)
        foreign_list = client.get(_base(uuid4()), headers=reviewer)
        foreign_revert = client.post(
            f"{_base(uuid4())}/{entry.board_geometry_revision_id}/revert",
            json=_command(),
            headers=reviewer,
        )

    assert allowed.status_code == 200
    assert repository.revert_calls[0]["actor"] == f"reviewer-session:{reviewer_access.session_id}"
    assert listed.status_code == 200
    assert foreign_list.status_code >= 400
    assert foreign_revert.status_code >= 400
    assert len(repository.revert_calls) == 1


def _find_route(routes: Iterable[object], name: str) -> object | None:
    for route in routes:
        if getattr(route, "name", None) == name:
            return route
        nested = getattr(getattr(route, "original_router", None), "routes", None)
        if nested is not None:
            found = _find_route(nested, name)
            if found is not None:
                return found
    return None


def test_default_wiring_gives_the_service_a_virtual_render_verifier(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    route = _find_route(app.routes, "list_geometry_corrections")
    assert route is not None
    service_dependency = next(
        dependency
        for dependency in route.dependant.dependencies  # type: ignore[attr-defined]
        if dependency.name == "service"
    )
    generator = service_dependency.call()  # type: ignore[misc]
    try:
        service = next(generator)
        assert isinstance(service, GeometryCorrectionRevertService)
        verifier = service._render_verifier  # noqa: SLF001
        assert isinstance(verifier, VirtualRestoredRenderVerifier)
    finally:
        generator.close()


def _rejection_entry(
    *, target: RejectionTarget, reason: str = "cropped"
) -> GeometryCorrectionEntry:
    slot = target is RejectionTarget.PENDING_SLOT
    return replace(
        _entry(kind=GeometryCorrectionKind.REJECTION),
        recognized_board_id=None if slot else uuid4(),
        review_item_id=None if slot else uuid4(),
        pending_geometry_id=uuid4() if slot else None,
        rejection_target=target,
        rejection_reason=reason,
        rejection_note="Ucięty górny rząd" if reason == "other" else None,
    )


def test_list_and_preview_describe_a_rejection_without_a_board_or_source_revision(
    tmp_path: Path,
) -> None:
    repository = MemoryRevertRepository()
    slot = _rejection_entry(target=RejectionTarget.PENDING_SLOT, reason="other")
    board = replace(
        _rejection_entry(target=RejectionTarget.REVIEW_ITEM),
        blocking_reason=RevertBlockingReason.REPLACED,
        created_at=NOW - timedelta(minutes=5),
    )
    repository.entries = [board, slot]
    with _client(tmp_path, repository) as client:
        listed = client.get(_base())
        preview = client.get(f"{_base()}/{slot.board_geometry_revision_id}/revert-preview")

    first, second = listed.json()["items"]
    assert first["kind"] == "rejection" and first["rejectionTarget"] == "pending_slot"
    assert first["recognizedBoardId"] is None and first["reviewItemId"] is None
    assert first["pendingGeometryId"] == str(slot.pending_geometry_id)
    assert first["rejectionReason"] == "other"
    assert first["rejectionNote"] == "Ucięty górny rząd"
    assert second["rejectionTarget"] == "review_item"
    assert second["recognizedBoardId"] == str(board.recognized_board_id)
    assert second["pendingGeometryId"] is None
    assert second["rejectionNote"] is None
    assert second["revertable"] is False
    assert second["blockingReasonCode"] == "GEOMETRY_REVERT_REPLACED"
    assert preview.status_code == 200
    assert preview.json()["revertedSourceGeometryRevisionId"] is None
    assert preview.json()["correction"]["kind"] == "rejection"


def test_a_rejection_revert_result_has_no_board_or_source_revision(tmp_path: Path) -> None:
    repository = MemoryRevertRepository()
    slot = _rejection_entry(target=RejectionTarget.PENDING_SLOT)
    repository.entries = [slot]
    result = GeometryCorrectionRevertResult(
        revert_id=uuid4(),
        created=True,
        kind=GeometryCorrectionKind.REJECTION,
        board_geometry_revision_id=slot.board_geometry_revision_id,
        pending_geometry_id=slot.pending_geometry_id,
        recognized_board_id=None,
        review_item_id=None,
        reverted_source_geometry_revision_id=None,
        restored_source_geometry_revision_id=None,
        repointed_board_ids=(),
        removed_cell_count=0,
        source_image_geometry_status=SourceImageGeometryStatus.GEOMETRY_INCOMPLETE,
        snapshot_checksum_sha256="a" * 64,
        created_at=NOW,
    )
    command = _command()
    repository.results[UUID(str(command["idempotencyKey"]))] = result
    with _client(tmp_path, repository) as client:
        response = client.post(f"{_base()}/{slot.board_geometry_revision_id}/revert", json=command)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kind"] == "rejection"
    assert body["recognizedBoardId"] is None and body["reviewItemId"] is None
    assert body["revertedSourceGeometryRevisionId"] is None
    assert body["restoredSourceGeometryRevisionId"] is None
    assert body["pendingGeometryId"] == str(slot.pending_geometry_id)
