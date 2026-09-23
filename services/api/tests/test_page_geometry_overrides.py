from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from game_predictor_api.api.image_imports import create_image_imports_router
from game_predictor_api.application.page_geometry_overrides import (
    PageGeometryOverrideService,
)
from game_predictor_api.domain.geometry_qualification import GeometryQualification
from game_predictor_api.domain.jobs import JobError
from game_predictor_api.domain.page_geometry_overrides import (
    ImagePageGeometryOverride,
    ImagePageSourceExclusion,
)
from PIL import Image


class MemoryPageGeometryOverrideRepository:
    def __init__(self) -> None:
        self.values: list[ImagePageGeometryOverride] = []
        self.exclusions: list[ImagePageSourceExclusion] = []

    def get_current(
        self,
        *,
        game_id: UUID,
        source_checksum_sha256: str,
    ) -> ImagePageGeometryOverride | None:
        matches = [
            value
            for value in self.values
            if value.game_id == game_id and value.source_checksum_sha256 == source_checksum_sha256
        ]
        return max(matches, key=lambda value: value.revision, default=None)

    def list_current(self, *, game_id: UUID) -> tuple[ImagePageGeometryOverride, ...]:
        checksums = {
            value.source_checksum_sha256 for value in self.values if value.game_id == game_id
        }
        return tuple(
            current
            for checksum in sorted(checksums)
            if (current := self.get_current(game_id=game_id, source_checksum_sha256=checksum))
            is not None
        )

    def append(self, value: ImagePageGeometryOverride) -> ImagePageGeometryOverride:
        self.values.append(value)
        return value

    def get_exclusion(
        self,
        *,
        game_id: UUID,
        browser_selection_id: UUID,
        source_checksum_sha256: str,
    ) -> ImagePageSourceExclusion | None:
        return next(
            (
                value
                for value in self.exclusions
                if value.game_id == game_id
                and value.browser_selection_id == browser_selection_id
                and value.source_checksum_sha256 == source_checksum_sha256
            ),
            None,
        )

    def list_exclusions(
        self, *, game_id: UUID, browser_selection_id: UUID
    ) -> tuple[ImagePageSourceExclusion, ...]:
        return tuple(
            value
            for value in self.exclusions
            if value.game_id == game_id and value.browser_selection_id == browser_selection_id
        )

    def append_exclusion(self, value: ImagePageSourceExclusion) -> ImagePageSourceExclusion:
        self.exclusions.append(value)
        return value


def _quads() -> tuple[tuple[dict[str, int], ...], ...]:
    result: list[tuple[dict[str, int], ...]] = []
    for row in range(3):
        for column in range(3):
            left, top = column * 100 + 5, row * 100 + 5
            right, bottom = left + 90, top + 90
            result.append(
                (
                    {"x": left, "y": top},
                    {"x": right, "y": top},
                    {"x": right, "y": bottom},
                    {"x": left, "y": bottom},
                )
            )
    return tuple(result)


def _frame_quads() -> tuple[tuple[dict[str, int], ...], ...]:
    result: list[tuple[dict[str, int], ...]] = []
    for row in range(3):
        for column in range(3):
            left, top = column * 100 + 1, row * 100 + 1
            right, bottom = left + 98, top + 98
            result.append(
                (
                    {"x": left, "y": top},
                    {"x": right, "y": top},
                    {"x": right, "y": bottom},
                    {"x": left, "y": bottom},
                )
            )
    return tuple(result)


def test_v12_partial_slot_may_have_a_frame_outside_the_source() -> None:
    frames = list(_frame_quads())
    frames[0] = tuple({"x": point["x"] - 4, "y": point["y"]} for point in frames[0])
    decisions = [GeometryQualification().to_dict() for _ in range(9)]
    decisions[0] = GeometryQualification(
        "pending_partial", (0,), True, "missing_pixels"
    ).to_dict()
    service = PageGeometryOverrideService(MemoryPageGeometryOverrideRepository())
    value, created = service.save(
        game_id=uuid4(),
        source_checksum_sha256="b" * 64,
        image_width=320,
        image_height=320,
        expected_board_count=9,
        final_quads=_quads(),
        board_frame_quads=tuple(frames),
        symbol_grid_quads=_quads(),
        slot_qualifications=decisions,
        actor="local-owner",
    )
    assert created
    assert value.board_frame_quads[0][0]["x"] == -3


def test_slot_decisions_survive_retry_and_change_revision_without_changing_quads() -> None:
    repository = MemoryPageGeometryOverrideRepository()
    service = PageGeometryOverrideService(repository)
    game_id = uuid4()
    arguments = dict(
        game_id=game_id,
        source_checksum_sha256="a" * 64,
        image_width=320,
        image_height=320,
        expected_board_count=9,
        final_quads=_quads(),
        actor="local-owner",
    )
    legacy, _ = service.save(**arguments)
    assert legacy.slot_qualifications is None
    assert "slotQualifications" not in service.snapshot(game_id=game_id)["a" * 64]
    decisions = [GeometryQualification().to_dict() for _ in range(9)]
    decisions[5] = GeometryQualification(
        "pending_partial", tuple(range(15)), True, "missing_pixels"
    ).to_dict()
    first, created = service.save(**arguments, slot_qualifications=decisions)
    restored, duplicate = PageGeometryOverrideService(repository).save(
        **arguments, slot_qualifications=decisions
    )
    assert created and not duplicate
    assert first == restored
    assert first.revision == 2
    assert first.final_quads == legacy.final_quads
    assert first.decision_checksum_sha256 != legacy.decision_checksum_sha256
    # `resolve_manual_geometry_qualification` always mints the current
    # qualification version once a slot declares any missing cell, so the
    # persisted snapshot legitimately outgrows the submitted v1 request.
    assert first.slot_qualifications is not None
    expected = [item.to_dict() for item in first.slot_qualifications]
    assert service.snapshot(game_id=game_id)["a" * 64]["slotQualifications"] == expected
    with pytest.raises(JobError) as missing:
        PageGeometryOverrideService(repository).save(**arguments)
    assert missing.value.code == "IMAGE_PAGE_GEOMETRY_QUALIFICATION_REQUIRED"
    assert len(repository.values) == 2
    assert service.snapshot(game_id=game_id)["a" * 64]["slotQualifications"] == expected


def test_page_revision_conflict_and_lost_response_preserve_newer_decision() -> None:
    repository = MemoryPageGeometryOverrideRepository()
    arguments = dict(
        game_id=uuid4(),
        source_checksum_sha256="a" * 64,
        image_width=320,
        image_height=320,
        expected_board_count=9,
        final_quads=_quads(),
        actor="owner",
        expected_override_revision=0,
    )
    first, created = PageGeometryOverrideService(repository).save(**arguments)
    replay, created_again = PageGeometryOverrideService(repository).save(**arguments)
    assert created and not created_again and replay == first
    decisions = [
        GeometryQualification(
            exclude_from_geometry_training=True, exclusion_reason="manual_exclusion"
        ).to_dict()
        for _ in range(9)
    ]
    with pytest.raises(JobError) as error:
        PageGeometryOverrideService(repository).save(**arguments, slot_qualifications=decisions)
    assert error.value.code == "IMAGE_PAGE_GEOMETRY_REVISION_CONFLICT"
    assert len(repository.values) == 1


def test_page_override_http_roundtrip_preserves_slot_metadata(tmp_path: Path) -> None:
    source_path = tmp_path / "source.jpg"
    Image.new("RGB", (320, 320)).save(source_path)
    game_id, upload_id = uuid4(), uuid4()
    ready = SimpleNamespace(
        upload=SimpleNamespace(path=tmp_path),
        manifest=SimpleNamespace(
            files=[
                SimpleNamespace(
                    checksum_sha256="a" * 64,
                    stored_file_name="source.jpg",
                    relative_path="seq_1-9.jpg",
                )
            ]
        ),
    )
    browser = SimpleNamespace(bind_ready_game=lambda *_: ready)
    repository = MemoryPageGeometryOverrideRepository()
    service = PageGeometryOverrideService(repository)
    app = FastAPI()
    app.include_router(
        create_image_imports_router(
            browser_selection_service_dependency=lambda: browser,
            job_service_dependency=lambda: None,
            iterative_import_service_dependency=lambda: None,
            page_geometry_override_service_dependency=lambda: service,
            image_sequence_canonical_service_dependency=lambda: None,
            image_import_geometry_guard_service_dependency=lambda: None,
        )
    )
    decisions = [GeometryQualification().to_dict() for _ in range(9)]
    decisions[5] = GeometryQualification(
        "pending_partial", (0, 1), True, "missing_pixels"
    ).to_dict()
    body = {
        "gameId": str(game_id),
        "sourceChecksumSha256": "a" * 64,
        "imageWidth": 320,
        "imageHeight": 320,
        "finalQuads": _quads(),
        "boardFrameQuads": _frame_quads(),
        "symbolGridQuads": _quads(),
        "actor": "local-owner",
        "slotQualifications": decisions,
    }
    client = TestClient(app)
    endpoint = f"/admin/image-imports/browser-selections/{upload_id}/page-geometry-overrides"
    response = client.post(endpoint, json=body)
    assert response.status_code == 201, response.text
    # `resolve_manual_geometry_qualification` always mints the current
    # qualification version once a slot declares any missing cell, and the
    # HTTP response projects that back onto the client-facing v1/v2 contract.
    saved = repository.values[0].slot_qualifications
    assert saved is not None
    assert response.json()["slotQualifications"] == [item.to_client_dict() for item in saved]
    repeated = client.post(endpoint, json=body)
    assert repeated.json()["id"] == response.json()["id"]
    assert repeated.json()["created"] is False
    assert len(repository.values) == 1
    assert repository.values[0].board_frame_quads == _frame_quads()
    assert repository.values[0].symbol_grid_quads == _quads()
    # Signed corners are legal only on explicitly partial slots. The server expands the mask.
    clipped = list(_quads())
    clipped[0] = tuple({"x": p["x"], "y": p["y"] - 15} for p in clipped[0])
    body.pop("boardFrameQuads")
    body.pop("symbolGridQuads")
    decisions[0] = GeometryQualification("pending_partial", (0,), True, "missing_pixels").to_dict()
    body["finalQuads"] = clipped
    partial = client.post(endpoint, json=body)
    assert partial.status_code == 201, partial.text
    assert partial.json()["slotQualifications"][0]["unavailableCellIndices"] == list(range(5))
    decisions[0] = GeometryQualification().to_dict()
    with pytest.raises(JobError) as refused:
        client.post(endpoint, json=body)
    assert refused.value.code == "IMAGE_PAGE_GEOMETRY_INVALID"
    assert len(repository.values) == 2


def test_page_geometry_override_is_idempotent_and_pinned_in_snapshot() -> None:
    game_id = uuid4()
    checksum = "a" * 64
    repository = MemoryPageGeometryOverrideRepository()
    service = PageGeometryOverrideService(repository)

    first, created = service.save(
        game_id=game_id,
        source_checksum_sha256=checksum,
        image_width=320,
        image_height=320,
        expected_board_count=9,
        final_quads=_quads(),
        actor="local-owner",
    )
    replay, replay_created = service.save(
        game_id=game_id,
        source_checksum_sha256=checksum,
        image_width=320,
        image_height=320,
        expected_board_count=9,
        final_quads=_quads(),
        actor="local-owner",
    )

    assert created is True
    assert replay_created is False
    assert replay.id == first.id
    assert first.revision == 1
    assert first.created_at <= datetime.now(UTC)
    assert service.snapshot(game_id=game_id) == {
        checksum: {
            "actor": "local-owner",
            "decisionChecksumSha256": first.decision_checksum_sha256,
            "imageHeight": 320,
            "imageWidth": 320,
            "expectedBoardCount": 9,
            "overrideId": str(first.id),
            "quads": first.final_quads,
            "revision": 1,
        }
    }


def test_v12_frame_grid_pair_is_snapshot_bound_and_cannot_escape_the_board_frame() -> None:
    game_id = uuid4()
    checksum = "b" * 64
    repository = MemoryPageGeometryOverrideRepository()
    service = PageGeometryOverrideService(repository)
    frames = _frame_quads()
    grids = _quads()

    saved, created = service.save(
        game_id=game_id,
        source_checksum_sha256=checksum,
        image_width=320,
        image_height=320,
        expected_board_count=9,
        final_quads=grids,
        board_frame_quads=frames,
        symbol_grid_quads=grids,
        actor="local-owner",
    )

    assert created is True
    assert saved.final_quads == grids
    assert saved.board_frame_quads == frames
    assert saved.symbol_grid_quads == grids
    snapshot = service.snapshot(game_id=game_id)[checksum]
    assert snapshot["boardFrameQuads"] == frames
    assert snapshot["symbolGridQuads"] == grids
    profile = service.contrast_frame_grid_v12_profile(game_id=game_id)
    assert profile["sampleSourceCount"] == 1
    assert profile["sampleCount"] == 9

    outside = list(grids)
    outside[0] = tuple({"x": point["x"] - 5, "y": point["y"]} for point in outside[0])
    with pytest.raises(JobError) as error:
        service.save(
            game_id=game_id,
            source_checksum_sha256="c" * 64,
            image_width=320,
            image_height=320,
            expected_board_count=9,
            final_quads=outside,
            board_frame_quads=frames,
            symbol_grid_quads=outside,
            actor="local-owner",
        )
    assert error.value.code == "IMAGE_PAGE_GEOMETRY_V12_GRID_OUTSIDE_FRAME"


def test_partial_training_profile_uses_only_latest_opted_in_source_revisions() -> None:
    game_id = uuid4()
    repository = MemoryPageGeometryOverrideRepository()
    service = PageGeometryOverrideService(repository)
    mask = (0, 5, 10)

    def decisions(*, opted_in: bool) -> list[dict[str, object]]:
        values = [
            GeometryQualification(version="manual-geometry-qualification-v2").to_dict()
            for _ in range(9)
        ]
        values[0] = GeometryQualification(
            completeness_status="pending_partial",
            unavailable_cell_indices=mask,
            exclude_from_geometry_training=True,
            exclusion_reason="missing_pixels",
            include_in_partial_grid_training=opted_in,
            version="manual-geometry-qualification-v2",
        ).to_dict()
        return values

    for source_checksum in ("a" * 64, "b" * 64, "c" * 64):
        service.save(
            game_id=game_id,
            source_checksum_sha256=source_checksum,
            image_width=320,
            image_height=320,
            expected_board_count=9,
            final_quads=_quads(),
            actor="local-owner",
            slot_qualifications=decisions(opted_in=True),
        )

    ready = service.partial_grid_training_profile(game_id=game_id)
    assert ready is not None
    assert ready["sampleCount"] == 3
    assert ready["sourceCount"] == 3
    assert ready["readyPatternCount"] == 1

    service.save(
        game_id=game_id,
        source_checksum_sha256="c" * 64,
        image_width=320,
        image_height=320,
        expected_board_count=9,
        final_quads=_quads(),
        actor="local-owner",
        slot_qualifications=decisions(opted_in=False),
    )

    current = service.partial_grid_training_profile(game_id=game_id)
    assert current is not None
    assert current["sampleCount"] == 2
    assert current["sourceCount"] == 2
    assert current["readyPatternCount"] == 0


def test_page_geometry_override_accepts_attested_five_board_final_page() -> None:
    game_id = uuid4()
    checksum = "b" * 64
    service = PageGeometryOverrideService(MemoryPageGeometryOverrideRepository())

    saved, created = service.save(
        game_id=game_id,
        source_checksum_sha256=checksum,
        image_width=320,
        image_height=320,
        expected_board_count=5,
        final_quads=_quads()[:5],
        actor="local-owner",
    )

    assert created is True
    assert len(saved.final_quads) == 5
    assert service.snapshot(game_id=game_id)[checksum]["expectedBoardCount"] == 5


def test_page_geometry_override_rejects_count_different_from_attested_range() -> None:
    service = PageGeometryOverrideService(MemoryPageGeometryOverrideRepository())

    with pytest.raises(JobError) as error:
        service.save(
            game_id=uuid4(),
            source_checksum_sha256="c" * 64,
            image_width=320,
            image_height=320,
            expected_board_count=5,
            final_quads=_quads(),
            actor="local-owner",
        )

    assert error.value.code == "IMAGE_PAGE_GEOMETRY_INVALID"


def test_page_source_exclusion_is_staging_scoped_and_idempotent() -> None:
    repository = MemoryPageGeometryOverrideRepository()
    service = PageGeometryOverrideService(repository)
    game_id = uuid4()
    staging_id = uuid4()
    values = {
        "game_id": game_id,
        "browser_selection_id": staging_id,
        "geometry_preflight_job_id": uuid4(),
        "source_manifest_checksum_sha256": "a" * 64,
        "geometry_manifest_checksum_sha256": "b" * 64,
        "source_checksum_sha256": "c" * 64,
        "source_relative_path": "cut/seq_10-18.jpg",
        "actor": "local-owner",
    }

    first, created = service.exclude_source(**values)
    replay, replay_created = service.exclude_source(**values)

    assert created is True
    assert replay_created is False
    assert replay.id == first.id
    assert service.exclusion_snapshot(game_id=game_id, browser_selection_id=staging_id) == {
        "c" * 64: {
            "decisionChecksumSha256": first.decision_checksum_sha256,
            "sourceRelativePath": "cut/seq_10-18.jpg",
        }
    }
    assert service.exclusion_snapshot(game_id=game_id, browser_selection_id=uuid4()) == {}
