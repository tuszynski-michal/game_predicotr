"""Source-only setup metadata retains scope, paging and independent write fences."""

import hashlib
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from game_predictor_api.api.grid_cell_content import (
    content_error_response,
    create_grid_cell_content_router,
)
from game_predictor_api.application.grid_cell_content import GridCellContentService
from game_predictor_api.domain.grid_cell_content import ContentError
from game_predictor_api.storage import grid_cell_content_targets as targets_module
from game_predictor_api.storage.grid_cell_content import SqlAlchemyGridCellContentRepository
from game_predictor_api.storage.grid_training_cohort_artifacts import GridCohortError
from test_grid_cell_content import GAME, target


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    cohort = uuid4()
    members = [target(1, 2), target(1, 0), target(2, 0, role="B")]
    sources = []
    boards = {}
    for member in (members[0], members[2]):
        source = member.source
        content = b"pinned-original-" + str(source.sourceId).encode()
        # The boundary checks exact file bytes; raster decoding belongs to capture.
        sha = hashlib.sha256(content).hexdigest()
        source = source.model_copy(update={"sourceSha256": sha})
        path = f"data/grid-training-cohorts/{GAME}/{cohort}/originals/{source.sourceId}.jpg"
        absolute = tmp_path / path
        absolute.parent.mkdir(parents=True, exist_ok=True)
        absolute.write_bytes(content)
        sources.append(
            {
                "sourceId": str(source.sourceId),
                "used": True,
                "role": "TRAIN" if member.role == "TRAIN" else "VALIDATION",
                "validationPurpose": None if member.role == "TRAIN" else "B",
                "sourceIdentity": {
                    "id": str(source.sourceId),
                    "checksum_sha256": sha,
                    "normalized_pixel_checksum_sha256": source.sourceRepresentativeSha256,
                    "oriented_width": source.width,
                    "oriented_height": source.height,
                    "coordinate_space": source.coordinateSpace,
                    "normalization_adapter_version": source.normalizationAdapterVersion,
                    "relative_path": "private/internal/path.jpg",
                },
                "original": {"path": path, "sha256": sha, "bytes": len(content)},
                "targets": [
                    {
                        "positionIndex": value.positionIndex,
                        "sequenceNumber": value.sequenceNumber,
                        "nodes": "NEVER_EXPOSE_NODES",
                        "contentAnnotation": "NEVER_EXPOSE_CONTENT",
                        "predictions": "NEVER_EXPOSE_HINTS",
                    }
                    for value in members
                    if value.source.sourceId == source.sourceId
                ],
            }
        )
        boards[source.sourceId] = {
            value.positionIndex: {
                "board": {
                    "id": str(uuid4()),
                    "status": "accepted",
                    "sequence_number": value.sequenceNumber,
                },
                "review": {"status": "accepted"},
                "owner": None,
                "foreignOwner": None,
            }
            for value in members
            if value.source.sourceId == source.sourceId
        }
    calls = []
    logical_names = {UUID(sources[0]["sourceId"]): "logical/folder/photo.jpg"}

    class Repository(SqlAlchemyGridCellContentRepository):
        def bind(self, game, **_kwargs):
            calls.append(("bind", game))

        def snapshot(self, game, identifier, manifest):
            calls.append(("snapshot", game, identifier, manifest))
            if game != GAME or identifier != cohort or manifest != "a" * 64:
                raise ContentError(
                    "CONTENT_FROZEN_COHORT_REQUIRED", "The exact cohort is required."
                )
            return SimpleNamespace(
                manifest={"gameId": str(GAME), "cohortId": str(cohort)},
                sources=lambda: iter(sources),
            )

        def current_source(self, _game, source, **_kwargs):
            from game_predictor_api.storage.grid_cell_content import source_identity

            return source_identity(
                next(
                    value["sourceIdentity"] for value in sources if value["sourceId"] == str(source)
                )
            )

    monkeypatch.setattr(
        targets_module, "current_targets", lambda _session, _game, source: boards[source]
    )

    def names(_repo, game, selected_sources):
        calls.append(("names", game, list(selected_sources)))
        return {
            source: targets_module._display_name(logical_names.get(source))
            for source in selected_sources
        }

    monkeypatch.setattr(targets_module, "_logical_names", names)
    repo = Repository(None, tmp_path)
    return SimpleNamespace(repo=repo, cohort=cohort, sources=sources, boards=boards, calls=calls)


def test_target_pages_are_source_only_and_sequence_conflict_does_not_hide_other_boards(fixture):
    value = fixture
    value.boards[UUID(value.sources[0]["sourceId"])][2]["board"]["sequence_number"] = 999
    first = value.repo.list_targets(GAME, value.cohort, "a" * 64, 2, 0)
    assert first["nextOffset"] == 2
    assert [item["positionIndex"] for item in first["items"]] == [0, 2]
    assert first["items"][0]["state"] == "ready"
    bad = first["items"][1]
    assert bad["sequenceNumber"] is None and bad["reasonCodes"] == ["CONTENT_SEQUENCE_CONFLICT"]
    assert bad["state"] == "unresolved"
    assert first["items"][0]["displayName"] == "photo.jpg"
    second = value.repo.list_targets(GAME, value.cohort, "a" * 64, 2, 2)
    assert second["nextOffset"] is None and second["items"][0]["role"] == "B"
    assert second["items"][0]["displayName"] is None
    assert set(bad) == {
        "source",
        "displayName",
        "positionIndex",
        "sequenceNumber",
        "role",
        "state",
        "reasonCodes",
    }
    assert "NEVER_EXPOSE" not in str(first)
    assert "private/internal" not in str(first)
    assert [call for call in value.calls if call[0] == "names"][0][2] == [
        UUID(value.sources[0]["sourceId"])
    ]
    assert value.repo.list_targets(GAME, value.cohort, "a" * 64, 2, 100)["items"] == []


def test_logical_name_batch_uses_own_page_identity_and_never_storage_path():
    sources = {
        member.source.sourceId: member.source for member in (target(1), target(2), target(3))
    }
    calls = []
    first, second, third = sources.values()
    rows = [
        {
            "id": first.sourceId,
            "checksum_sha256": first.sourceSha256,
            "normalized_pixel_checksum_sha256": first.sourceRepresentativeSha256,
            "logical_name": "folder\\photo.jpg",
        },
        {
            "id": second.sourceId,
            "checksum_sha256": "f" * 64,
            "normalized_pixel_checksum_sha256": second.sourceRepresentativeSha256,
            "logical_name": "drift.jpg",
        },
        {
            "id": third.sourceId,
            "checksum_sha256": third.sourceSha256,
            "normalized_pixel_checksum_sha256": third.sourceRepresentativeSha256,
            "logical_name": None,
        },
    ]

    def execute(statement, parameters):
        calls.append((str(statement), parameters))
        return SimpleNamespace(mappings=lambda: rows)

    repo = SimpleNamespace(session=SimpleNamespace(execute=execute))
    assert targets_module._logical_names(repo, GAME, sources) == {
        first.sourceId: "photo.jpg",
        third.sourceId: None,
    }
    assert len(calls) == 1
    assert calls[0][1] == {"game": GAME, "sources": list(sources)}
    assert "f.source_relative_path" in calls[0][0]
    assert "s.relative_path" not in calls[0][0]
    assert targets_module._logical_names(repo, GAME, {}) == {}
    assert len(calls) == 1


def test_target_source_is_exact_scoped_pinned_asset_and_checks_no_other_jpeg(fixture):
    value = fixture
    first, second = value.sources
    # A broken unrelated JPEG cannot break this source's asset read.
    (value.repo.root / second["original"]["path"]).unlink()
    path = value.repo.target_source_asset(GAME, value.cohort, "a" * 64, UUID(first["sourceId"]))
    assert hashlib.sha256(path.read_bytes()).hexdigest() == first["original"]["sha256"]
    for game, cohort, sha, source in (
        (uuid4(), value.cohort, "a" * 64, UUID(first["sourceId"])),
        (GAME, uuid4(), "a" * 64, UUID(first["sourceId"])),
        (GAME, value.cohort, "b" * 64, UUID(first["sourceId"])),
        (GAME, value.cohort, "a" * 64, uuid4()),
    ):
        with pytest.raises(ContentError):
            value.repo.target_source_asset(game, cohort, sha, source)
    path.write_bytes(b"different")
    with pytest.raises(GridCohortError):
        value.repo.target_source_asset(GAME, value.cohort, "a" * 64, UUID(first["sourceId"]))


def test_expected_source_conflicts_are_unresolved_but_infrastructure_failures_propagate(
    fixture, monkeypatch
):
    def missing(*_args, **_kwargs):
        raise ContentError("CONTENT_SOURCE_RETIRED", "Retired")

    monkeypatch.setattr(fixture.repo, "current_source", missing)
    page = fixture.repo.list_targets(GAME, fixture.cohort, "a" * 64, 2, 0)
    assert all(item["sequenceNumber"] is None for item in page["items"])
    assert page["items"][0]["reasonCodes"] == ["CONTENT_SOURCE_RETIRED"]

    def broken(*_args, **_kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(fixture.repo, "current_source", broken)
    with pytest.raises(RuntimeError, match="database unavailable"):
        fixture.repo.list_targets(GAME, fixture.cohort, "a" * 64, 2, 0)


def test_target_http_reader_and_asset_keep_pins_validation_and_no_store(fixture):
    value = fixture
    app = FastAPI()

    @app.exception_handler(ContentError)
    async def handle(_request, error):
        return content_error_response(error)

    service = SimpleNamespace(grid_cell_content=GridCellContentService(value.repo))
    app.include_router(create_grid_cell_content_router(lambda: service), prefix="/api/v1")
    path = f"/api/v1/admin/games/{GAME}/grid-quality-measurements/content-targets"
    pins = {"cohortId": str(value.cohort), "manifestSha256": "a" * 64}
    with TestClient(app) as client:
        assert client.get(path).status_code == 422
        for options in ({"limit": 51}, {"limit": 0}, {"offset": -1}, {"manifestSha256": "bad"}):
            assert client.get(path, params={**pins, **options}).status_code == 422
        response = client.get(path, params={**pins, "limit": 1})
        assert response.status_code == 200
        assert response.json()["version"] == "source-cell-content-targets-v1"
        assert response.json()["nextOffset"] == 1
        source = value.sources[0]["sourceId"]
        asset = client.get(f"{path}/sources/{source}/asset", params=pins)
        assert asset.status_code == 200
        assert asset.headers["cache-control"] == "no-store"
        assert asset.headers["x-content-type-options"] == "nosniff"
        assert hashlib.sha256(asset.content).hexdigest() == value.sources[0]["original"]["sha256"]
        denied = client.get(
            f"{path}/sources/{source}/asset", params={**pins, "manifestSha256": "b" * 64}
        )
        assert denied.status_code == 409
        assert denied.json()["code"] == "CONTENT_FROZEN_COHORT_REQUIRED"


@pytest.mark.parametrize("problem", ["missing", "foreign_owner", "sequence", "rejected"])
def test_shared_current_board_guard_keeps_ordinary_write_boundary_strict(
    fixture, monkeypatch, problem
):
    from game_predictor_api.storage import grid_cell_content

    source = fixture.repo.current_source(GAME, UUID(fixture.sources[0]["sourceId"]))
    targets = fixture.boards[source.sourceId]
    if problem == "missing":
        targets = {}
    elif problem == "foreign_owner":
        targets[0]["foreignOwner"] = {"recognized_board_id": str(uuid4())}
    elif problem == "sequence":
        targets[0]["board"]["sequence_number"] = 999
    else:
        targets[0]["board"]["status"] = "rejected"
    monkeypatch.setattr(grid_cell_content, "current_targets", lambda *_args: targets)
    with pytest.raises(ContentError) as error:
        fixture.repo.require_board(GAME, source, 0, 1)
    assert error.value.code in {"CONTENT_TARGET_UNAVAILABLE", "CONTENT_SEQUENCE_CONFLICT"}
