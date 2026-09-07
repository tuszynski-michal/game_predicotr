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

from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.geometry_qualification import (
    GeometryQualification,
    GeometryQualificationError,
    parse_slot_qualifications,
)
from game_predictor_api.domain.image_geometry_v2 import (
    ImageGeometryContractError,
    SourceImageBounds,
    SourcePoint,
    SourceQuad,
    resolve_manual_geometry_qualification,
)
from game_predictor_api.domain.jobs import JobConflictError, JobError
from game_predictor_api.domain.page_geometry_overrides import (
    ImagePageGeometryOverride,
    ImagePageSourceExclusion,
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

    def get_exclusion(
        self, *, browser_selection_id: UUID, source_checksum_sha256: str
    ) -> ImagePageSourceExclusion | None: ...

    def list_exclusions(
        self, *, browser_selection_id: UUID
    ) -> tuple[ImagePageSourceExclusion, ...]: ...

    def append_exclusion(self, value: ImagePageSourceExclusion) -> ImagePageSourceExclusion: ...


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
        slot_qualifications: object = None,
        expected_override_revision: int | None = None,
    ) -> tuple[ImagePageGeometryOverride, bool]:
        try:
            qualifications = parse_slot_qualifications(
                slot_qualifications, expected_board_count=expected_board_count
            )
        except GeometryQualificationError as error:
            raise JobError(error.code, str(error)) from error
        parsed = _parse_and_validate(
            final_quads,
            image_width=image_width,
            image_height=image_height,
            expected_board_count=expected_board_count,
            qualifications=qualifications,
        )
        if qualifications is not None:
            try:
                qualifications = tuple(
                    resolve_manual_geometry_qualification(
                        SourceQuad(
                            cast(
                                tuple[SourcePoint, SourcePoint, SourcePoint, SourcePoint],
                                tuple(SourcePoint(**point) for point in quad),
                            )
                        ),
                        source=SourceImageBounds(image_width, image_height),
                        topology=BoardTopology(3, 5),
                        qualification=qualification,
                    )
                    for quad, qualification in zip(parsed, qualifications, strict=True)
                )
            except ImageGeometryContractError as error:
                raise JobError(error.code, str(error)) from error
        checksum = _checksum(
            source_checksum_sha256,
            image_width,
            image_height,
            final_quads,
            None if qualifications is None else [item.to_dict() for item in qualifications],
        )
        current = self._repository.get_current(
            game_id=game_id,
            source_checksum_sha256=source_checksum_sha256,
        )
        if (
            current is not None
            and current.slot_qualifications is not None
            and qualifications is None
        ):
            raise JobError(
                "IMAGE_PAGE_GEOMETRY_QUALIFICATION_REQUIRED",
                "A qualified page revision requires explicit slot qualifications on every update.",
            )
        if current is not None and current.decision_checksum_sha256 == checksum:
            return current, False
        if expected_override_revision is not None and expected_override_revision != (
            0 if current is None else current.revision
        ):
            raise JobConflictError(
                "IMAGE_PAGE_GEOMETRY_REVISION_CONFLICT",
                "The page geometry changed after this draft was opened. Reload or reset the draft.",
            )
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
            slot_qualifications=qualifications,
        )
        return self._repository.append(value), True

    def snapshot(self, *, game_id: UUID) -> dict[str, object]:
        """Return an immutable input snapshot for a geometry-preflight job."""

        entries: dict[str, object] = {}
        for value in self._repository.list_current(game_id=game_id):
            entry: dict[str, object] = {
                "actor": value.actor,
                "decisionChecksumSha256": value.decision_checksum_sha256,
                "imageHeight": value.image_height,
                "imageWidth": value.image_width,
                "expectedBoardCount": len(value.final_quads),
                "overrideId": str(value.id),
                "quads": value.final_quads,
                "revision": value.revision,
            }
            if value.slot_qualifications is not None:
                entry["slotQualifications"] = [item.to_dict() for item in value.slot_qualifications]
            entries[value.source_checksum_sha256] = entry
        return dict(sorted(entries.items()))

    def exclude_source(
        self,
        *,
        game_id: UUID,
        browser_selection_id: UUID,
        geometry_preflight_job_id: UUID,
        source_manifest_checksum_sha256: str,
        geometry_manifest_checksum_sha256: str,
        source_checksum_sha256: str,
        source_relative_path: str,
        actor: str,
    ) -> tuple[ImagePageSourceExclusion, bool]:
        for checksum_value, code in (
            (source_manifest_checksum_sha256, "IMAGE_SEQUENCE_MANIFEST_INVALID"),
            (geometry_manifest_checksum_sha256, "IMAGE_PAGE_GEOMETRY_MANIFEST_STALE"),
            (source_checksum_sha256, "IMAGE_PAGE_GEOMETRY_SOURCE_INVALID"),
        ):
            if re.fullmatch(r"[0-9a-f]{64}", checksum_value) is None:
                raise JobError(code, "The source exclusion checksum is invalid.")
        normalized_path = source_relative_path.strip().replace("\\", "/")
        if (
            not normalized_path
            or normalized_path.startswith("/")
            or ".." in normalized_path.split("/")
        ):
            raise JobError(
                "IMAGE_PAGE_GEOMETRY_SOURCE_INVALID",
                "The source exclusion path is invalid.",
            )
        if not actor.strip():
            raise JobError(
                "IMAGE_PAGE_GEOMETRY_ACTOR_REQUIRED",
                "A non-empty actor is required for a source exclusion.",
            )
        payload = {
            "browserSelectionId": str(browser_selection_id),
            "gameId": str(game_id),
            "geometryManifestChecksumSha256": geometry_manifest_checksum_sha256,
            "geometryPreflightJobId": str(geometry_preflight_job_id),
            "sourceChecksumSha256": source_checksum_sha256,
            "sourceManifestChecksumSha256": source_manifest_checksum_sha256,
            "sourceRelativePath": normalized_path,
        }
        checksum = hashlib.sha256(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("ascii")
        ).hexdigest()
        current = self._repository.get_exclusion(
            browser_selection_id=browser_selection_id,
            source_checksum_sha256=source_checksum_sha256,
        )
        if current is not None:
            if current.decision_checksum_sha256 != checksum:
                raise JobError(
                    "IMAGE_PAGE_SOURCE_EXCLUSION_CONFLICT",
                    "This staged source already has a different exclusion decision.",
                )
            return current, False
        exclusion = ImagePageSourceExclusion(
            id=uuid4(),
            game_id=game_id,
            browser_selection_id=browser_selection_id,
            geometry_preflight_job_id=geometry_preflight_job_id,
            source_manifest_checksum_sha256=source_manifest_checksum_sha256,
            geometry_manifest_checksum_sha256=geometry_manifest_checksum_sha256,
            source_checksum_sha256=source_checksum_sha256,
            source_relative_path=normalized_path,
            actor=actor.strip(),
            decision_checksum_sha256=checksum,
            created_at=datetime.now(UTC),
        )
        return self._repository.append_exclusion(exclusion), True

    def exclusion_snapshot(self, *, browser_selection_id: UUID) -> dict[str, object]:
        entries: dict[str, object] = {}
        for value in self._repository.list_exclusions(browser_selection_id=browser_selection_id):
            entries[value.source_checksum_sha256] = {
                "decisionChecksumSha256": value.decision_checksum_sha256,
                "sourceRelativePath": value.source_relative_path,
            }
        return dict(sorted(entries.items()))


def _parse_and_validate(
    raw_quads: Sequence[Sequence[Mapping[str, object]]],
    *,
    image_width: int,
    image_height: int,
    expected_board_count: int,
    qualifications: tuple[GeometryQualification, ...] | None = None,
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
    for slot, raw_quad in enumerate(raw_quads):
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
        partial = (
            qualifications is not None
            and qualifications[slot].completeness_status == "pending_partial"
        )
        if any(
            not (-image_width if partial else 0)
            <= point.x
            <= (2 * image_width if partial else image_width - 1)
            or not (-image_height if partial else 0)
            <= point.y
            <= (2 * image_height if partial else image_height - 1)
            for point in points
        ):
            raise JobError(
                "IMAGE_PAGE_GEOMETRY_INVALID",
                "The slot corners exceed their permitted source bounds.",
            )
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
    allow_partial = qualifications is not None and any(
        q.completeness_status == "pending_partial" for q in qualifications
    )
    validation_quads = (
        tuple(
            cast(Quad, tuple(Point(p.x + image_width, p.y + image_height) for p in quad))
            for quad in quads
        )
        if allow_partial
        else tuple(quads)
    )
    if not is_ordered_active_grid(
        validation_quads,
        tuple(range(expected_board_count)),
        3 * image_width + 1 if allow_partial else image_width,
        3 * image_height + 1 if allow_partial else image_height,
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
    slot_qualifications: list[dict[str, object]] | None = None,
) -> str:
    if re.fullmatch(r"[0-9a-f]{64}", source_checksum_sha256) is None:
        raise JobError(
            "IMAGE_PAGE_GEOMETRY_SOURCE_INVALID",
            "The page geometry source checksum is invalid.",
        )
    payload: dict[str, object] = {
        "imageHeight": image_height,
        "imageWidth": image_width,
        "quads": final_quads,
        "sourceChecksumSha256": source_checksum_sha256,
    }
    if slot_qualifications is not None:
        payload["slotQualifications"] = slot_qualifications
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
