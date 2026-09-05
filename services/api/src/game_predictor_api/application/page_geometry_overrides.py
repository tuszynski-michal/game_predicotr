"""Application service for page-level geometry corrections."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Protocol, cast
from uuid import UUID, uuid4

from game_predictor_worker.images.geometry import Point, Quad
from game_predictor_worker.images.page_geometry_registration import is_ordered_active_grid

from game_predictor_api.domain.jobs import JobError
from game_predictor_api.domain.page_geometry_overrides import (
    ImagePageGeometryOverride,
    PageGeometryQuads,
)


class PageGeometryOverrideRepository(Protocol):
    def get_current(
        self,
        *,
        game_id: UUID,
        source_checksum_sha256: str,
    ) -> ImagePageGeometryOverride | None: ...

    def list_current(self, *, game_id: UUID) -> tuple[ImagePageGeometryOverride, ...]: ...

    def append(self, value: ImagePageGeometryOverride) -> ImagePageGeometryOverride: ...


class PageGeometryOverrideService:
    def __init__(self, repository: PageGeometryOverrideRepository) -> None:
        self._repository = repository

    def save(
        self,
        *,
        game_id: UUID,
        source_checksum_sha256: str,
        image_width: int,
        image_height: int,
        expected_board_count: int,
        final_quads: Sequence[Sequence[Mapping[str, object]]],
        actor: str,
    ) -> tuple[ImagePageGeometryOverride, bool]:
        checksum = _checksum(source_checksum_sha256, image_width, image_height, final_quads)
        parsed = _parse_and_validate(
            final_quads,
            image_width=image_width,
            image_height=image_height,
            expected_board_count=expected_board_count,
        )
        current = self._repository.get_current(
            game_id=game_id,
            source_checksum_sha256=source_checksum_sha256,
        )
        if current is not None and current.decision_checksum_sha256 == checksum:
            return current, False
        if not actor.strip():
            raise JobError(
                "IMAGE_PAGE_GEOMETRY_ACTOR_REQUIRED",
                "A non-empty actor is required for a page geometry correction.",
            )
        value = ImagePageGeometryOverride(
            id=uuid4(),
            game_id=game_id,
            source_checksum_sha256=source_checksum_sha256,
            image_width=image_width,
            image_height=image_height,
            final_quads=parsed,
            revision=1 if current is None else current.revision + 1,
            actor=actor.strip(),
            decision_checksum_sha256=checksum,
            created_at=datetime.now(UTC),
        )
        return self._repository.append(value), True

    def snapshot(self, *, game_id: UUID) -> dict[str, object]:
        """Return an immutable input snapshot for a geometry-preflight job."""

        entries: dict[str, object] = {}
        for value in self._repository.list_current(game_id=game_id):
            entries[value.source_checksum_sha256] = {
                "actor": value.actor,
                "decisionChecksumSha256": value.decision_checksum_sha256,
                "imageHeight": value.image_height,
                "imageWidth": value.image_width,
                "expectedBoardCount": len(value.final_quads),
                "overrideId": str(value.id),
                "quads": value.final_quads,
                "revision": value.revision,
            }
        return dict(sorted(entries.items()))


def _parse_and_validate(
    raw_quads: Sequence[Sequence[Mapping[str, object]]],
    *,
    image_width: int,
    image_height: int,
    expected_board_count: int,
) -> PageGeometryQuads:
    if (
        image_width < 1
        or image_height < 1
        or not 1 <= expected_board_count <= 9
        or len(raw_quads) != expected_board_count
    ):
        raise JobError(
            "IMAGE_PAGE_GEOMETRY_INVALID",
            "A page override must contain exactly the attested number of board quads.",
        )
    quads: list[Quad] = []
    canonical: list[tuple[dict[str, int], dict[str, int], dict[str, int], dict[str, int]]] = []
    for raw_quad in raw_quads:
        if len(raw_quad) != 4:
            raise JobError(
                "IMAGE_PAGE_GEOMETRY_INVALID",
                "Each page-board override must contain exactly four points.",
            )
        points: list[Point] = []
        json_points: list[dict[str, int]] = []
        for point in raw_quad:
            x, y = point.get("x"), point.get("y")
            if (
                not isinstance(x, int)
                or isinstance(x, bool)
                or not isinstance(y, int)
                or isinstance(y, bool)
            ):
                raise JobError(
                    "IMAGE_PAGE_GEOMETRY_INVALID",
                    "Each geometry point must use integer source coordinates.",
                )
            points.append(Point(x, y))
            json_points.append({"x": x, "y": y})
        quads.append(cast(Quad, tuple(points)))
        canonical.append(
            cast(
                tuple[
                    dict[str, int],
                    dict[str, int],
                    dict[str, int],
                    dict[str, int],
                ],
                tuple(json_points),
            )
        )
    if not is_ordered_active_grid(
        tuple(quads),
        tuple(range(expected_board_count)),
        image_width,
        image_height,
    ):
        raise JobError(
            "IMAGE_PAGE_GEOMETRY_INVALID",
            "The corrected geometry must be an ordered and non-overlapping board prefix.",
        )
    return cast(PageGeometryQuads, tuple(canonical))


def _checksum(
    source_checksum_sha256: str,
    image_width: int,
    image_height: int,
    final_quads: Sequence[Sequence[Mapping[str, object]]],
) -> str:
    if re.fullmatch(r"[0-9a-f]{64}", source_checksum_sha256) is None:
        raise JobError(
            "IMAGE_PAGE_GEOMETRY_SOURCE_INVALID",
            "The page geometry source checksum is invalid.",
        )
    payload = {
        "imageHeight": image_height,
        "imageWidth": image_width,
        "quads": final_quads,
        "sourceChecksumSha256": source_checksum_sha256,
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return hashlib.sha256(canonical).hexdigest()


__all__ = [
    "PageGeometryOverrideRepository",
    "PageGeometryOverrideService",
]
