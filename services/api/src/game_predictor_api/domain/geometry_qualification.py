"""Versioned human geometry decisions, independent of render and training policy."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, cast

type GeometryQualificationVersion = Literal[
    "manual-geometry-qualification-v1",
    "manual-geometry-qualification-v2",
    "manual-geometry-qualification-v3",
]
GEOMETRY_QUALIFICATION_VERSION_V1: GeometryQualificationVersion = "manual-geometry-qualification-v1"
GEOMETRY_QUALIFICATION_VERSION: GeometryQualificationVersion = "manual-geometry-qualification-v2"
# v3 is deliberately not the "current" client-submittable version: an
# operator never declares which of their unavailable cells are fully vs
# partially out of frame. Only the backend (resolve_manual_geometry_
# qualification) mints v3, after it has recomputed that split from the
# actual quad. Request/response schemas and the Admin frontend stay on v2.
GEOMETRY_QUALIFICATION_VERSION_V3: GeometryQualificationVersion = "manual-geometry-qualification-v3"
type CompletenessStatus = Literal["complete", "pending_partial"]
type GeometryExclusionReason = Literal["missing_pixels", "manual_exclusion"]

_BASE_KEYS = frozenset(
    {
        "version",
        "completenessStatus",
        "unavailableCellIndices",
        "excludeFromGeometryTraining",
        "exclusionReason",
    }
)
_VERSION_KEYS: dict[GeometryQualificationVersion, frozenset[str]] = {
    GEOMETRY_QUALIFICATION_VERSION_V1: _BASE_KEYS,
    GEOMETRY_QUALIFICATION_VERSION: _BASE_KEYS | {"includeInPartialGridTraining"},
    GEOMETRY_QUALIFICATION_VERSION_V3: _BASE_KEYS
    | {"includeInPartialGridTraining", "fullyUnavailableCellIndices"},
}


class GeometryQualificationError(ValueError):
    code = "IMAGE_GEOMETRY_QUALIFICATION_INVALID"


def _valid_cell_index_mask(indices: object) -> bool:
    return (
        isinstance(indices, tuple)
        and all(type(index) is int and 0 <= index < 15 for index in indices)
        and indices == tuple(sorted(set(indices)))
    )


@dataclass(frozen=True, slots=True)
class GeometryQualification:
    completeness_status: CompletenessStatus = "complete"
    unavailable_cell_indices: tuple[int, ...] = ()
    exclude_from_geometry_training: bool = False
    exclusion_reason: GeometryExclusionReason | None = None
    include_in_partial_grid_training: bool = False
    version: GeometryQualificationVersion = GEOMETRY_QUALIFICATION_VERSION_V1
    fully_unavailable_cell_indices: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        indices = self.unavailable_cell_indices
        fully_unavailable = self.fully_unavailable_cell_indices
        if (
            not isinstance(self.completeness_status, str)
            or self.completeness_status not in {"complete", "pending_partial"}
            or type(self.exclude_from_geometry_training) is not bool
            or type(self.include_in_partial_grid_training) is not bool
            or self.version not in _VERSION_KEYS
            or not _valid_cell_index_mask(indices)
            or not _valid_cell_index_mask(fully_unavailable)
            or not set(fully_unavailable).issubset(indices)
        ):
            raise GeometryQualificationError("Invalid completeness or unavailable-cell mask.")
        if self.completeness_status == "pending_partial":
            if (
                not indices
                or not self.exclude_from_geometry_training
                or self.exclusion_reason != "missing_pixels"
            ):
                raise GeometryQualificationError(
                    "Partial geometry requires missing cells and mandatory training exclusion."
                )
            if self.include_in_partial_grid_training and not _is_lateral_partial_mask(indices):
                raise GeometryQualificationError(
                    "Partial-grid training accepts only one or two complete lateral columns."
                )
        elif indices or self.exclusion_reason != (
            "manual_exclusion" if self.exclude_from_geometry_training else None
        ):
            raise GeometryQualificationError(
                "Complete geometry requires an empty mask and a consistent exclusion reason."
            )
        if (
            self.include_in_partial_grid_training
            and self.version == GEOMETRY_QUALIFICATION_VERSION_V1
        ):
            raise GeometryQualificationError(
                "Partial-grid training opt-in requires geometry qualification v2 or later."
            )
        if fully_unavailable and self.version != GEOMETRY_QUALIFICATION_VERSION_V3:
            raise GeometryQualificationError(
                "Fully-unavailable cell tracking requires geometry qualification v3."
            )

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "version": self.version,
            "completenessStatus": self.completeness_status,
            "unavailableCellIndices": list(self.unavailable_cell_indices),
            "excludeFromGeometryTraining": self.exclude_from_geometry_training,
            "exclusionReason": self.exclusion_reason,
        }
        if self.version in {GEOMETRY_QUALIFICATION_VERSION, GEOMETRY_QUALIFICATION_VERSION_V3}:
            payload["includeInPartialGridTraining"] = self.include_in_partial_grid_training
        if self.version == GEOMETRY_QUALIFICATION_VERSION_V3:
            payload["fullyUnavailableCellIndices"] = list(self.fully_unavailable_cell_indices)
        return payload

    def to_client_dict(self) -> dict[str, object]:
        """Project onto the client-facing v1/v2 contract for HTTP responses.

        v3 is backend-only (see ``GEOMETRY_QUALIFICATION_VERSION_V3``): the
        Admin frontend and request/response schemas only understand v1/v2, so
        any endpoint that echoes back a persisted qualification must drop the
        v3-only ``fully_unavailable_cell_indices`` enrichment rather than
        serialize it through the v1/v2-only ``GeometryQualificationPayload``.
        """
        if self.version != GEOMETRY_QUALIFICATION_VERSION_V3:
            return self.to_dict()
        return GeometryQualification(
            completeness_status=self.completeness_status,
            unavailable_cell_indices=self.unavailable_cell_indices,
            exclude_from_geometry_training=self.exclude_from_geometry_training,
            exclusion_reason=self.exclusion_reason,
            include_in_partial_grid_training=self.include_in_partial_grid_training,
            version=GEOMETRY_QUALIFICATION_VERSION,
        ).to_dict()

    @classmethod
    def from_dict(cls, raw: object) -> GeometryQualification:
        if not isinstance(raw, Mapping):
            raise GeometryQualificationError(
                "Geometry qualification fields are incomplete or unknown."
            )
        version = raw.get("version")
        keys = _VERSION_KEYS.get(cast(GeometryQualificationVersion, version))
        if keys is None:
            raise GeometryQualificationError("Unsupported geometry qualification version.")
        if set(raw) != keys:
            raise GeometryQualificationError(
                "Geometry qualification fields are incomplete or unknown."
            )
        indices = raw["unavailableCellIndices"]
        if not isinstance(indices, Sequence) or isinstance(indices, str | bytes):
            raise GeometryQualificationError("Unavailable cell indices must be an array.")
        fully_unavailable: Sequence[object] = ()
        if version == GEOMETRY_QUALIFICATION_VERSION_V3:
            fully_unavailable = raw["fullyUnavailableCellIndices"]
            if not isinstance(fully_unavailable, Sequence) or isinstance(
                fully_unavailable, str | bytes
            ):
                raise GeometryQualificationError(
                    "Fully-unavailable cell indices must be an array."
                )
        return cls(
            completeness_status=cast(CompletenessStatus, raw["completenessStatus"]),
            unavailable_cell_indices=tuple(indices),
            exclude_from_geometry_training=raw["excludeFromGeometryTraining"],
            exclusion_reason=raw["exclusionReason"],
            include_in_partial_grid_training=(
                raw["includeInPartialGridTraining"]
                if version in {GEOMETRY_QUALIFICATION_VERSION, GEOMETRY_QUALIFICATION_VERSION_V3}
                else False
            ),
            fully_unavailable_cell_indices=tuple(cast("Sequence[int]", fully_unavailable)),
            version=cast(GeometryQualificationVersion, version),
        )


def _is_lateral_partial_mask(indices: tuple[int, ...]) -> bool:
    missing_columns = {
        column for column in range(5) if all(row * 5 + column in indices for row in range(3))
    }
    expected = tuple(row * 5 + column for row in range(3) for column in sorted(missing_columns))
    return (
        indices == tuple(sorted(expected))
        and len(missing_columns) in {1, 2}
        and (
            missing_columns == set(range(len(missing_columns)))
            or missing_columns == set(range(5 - len(missing_columns), 5))
        )
    )


def parse_slot_qualifications(
    raw: object, *, expected_board_count: int
) -> tuple[GeometryQualification, ...] | None:
    """Array order is the attested row-major slot order, never detection order."""
    if raw is None:
        return None
    if (
        not isinstance(raw, Sequence)
        or isinstance(raw, str | bytes)
        or not 1 <= expected_board_count <= 9
        or len(raw) != expected_board_count
    ):
        raise GeometryQualificationError("Qualification must describe every active source slot.")
    return tuple(GeometryQualification.from_dict(item) for item in raw)


def qualification_from_geometry(
    geometry: Mapping[str, object],
    *,
    completeness_status: str = "complete",
    unavailable_cell_indices: tuple[int, ...] = (),
) -> GeometryQualification:
    """Read a revision without rewriting legacy payloads or their fingerprints."""
    raw = geometry.get("geometryQualification")
    if raw is not None:
        return GeometryQualification.from_dict(raw)
    return GeometryQualification(
        completeness_status=cast(CompletenessStatus, completeness_status),
        unavailable_cell_indices=unavailable_cell_indices,
        exclude_from_geometry_training=completeness_status == "pending_partial",
        exclusion_reason="missing_pixels" if completeness_status == "pending_partial" else None,
    )


def geometry_training_exclusion_reason(
    geometry: Mapping[str, object],
    *,
    completeness_status: str = "complete",
    unavailable_cell_indices: tuple[int, ...] = (),
) -> GeometryExclusionReason | None:
    """Eligibility for a new cohort; never edits an already frozen profile."""
    qualification = qualification_from_geometry(
        geometry,
        completeness_status=completeness_status,
        unavailable_cell_indices=unavailable_cell_indices,
    )
    return qualification.exclusion_reason


def page_anchor_exclusion_reason(raw: object, *, expected_board_count: int = 9) -> str | None:
    qualifications = parse_slot_qualifications(raw, expected_board_count=expected_board_count)
    if qualifications is not None and any(q.exclude_from_geometry_training for q in qualifications):
        return "incomplete_anchor"
    return None
