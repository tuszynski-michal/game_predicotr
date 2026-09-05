from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from game_predictor_api.application.page_geometry_overrides import (
    PageGeometryOverrideService,
)
from game_predictor_api.domain.jobs import JobError
from game_predictor_api.domain.page_geometry_overrides import ImagePageGeometryOverride


class MemoryPageGeometryOverrideRepository:
    def __init__(self) -> None:
        self.values: list[ImagePageGeometryOverride] = []

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
