"""Versioned human geometry decisions, independent of render and training policy."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, cast

type GeometryQualificationVersion = Literal[
    "manual-geometry-qualification-v1", "manual-geometry-qualification-v2"
]
GEOMETRY_QUALIFICATION_VERSION_V1: GeometryQualificationVersion = "manual-geometry-qualification-v1"
GEOMETRY_QUALIFICATION_VERSION: GeometryQualificationVersion = "manual-geometry-qualification-v2"
type CompletenessStatus = Literal["complete", "pending_partial"]
type GeometryExclusionReason = Literal["missing_pixels", "manual_exclusion"]


class GeometryQualificationError(ValueError):
    code = "IMAGE_GEOMETRY_QUALIFICATION_INVALID"


@dataclass(frozen=True, slots=True)
class GeometryQualification:
    completeness_status: CompletenessStatus = "complete"
    unavailable_cell_indices: tuple[int, ...] = ()
    exclude_from_geometry_training: bool = False
    exclusion_reason: GeometryExclusionReason | None = None
    include_in_partial_grid_training: bool = False
    version: GeometryQualificationVersion = GEOMETRY_QUALIFICATION_VERSION_V1

    def __post_init__(self) -> None:
        indices = self.unavailable_cell_indices
        if (
            not isinstance(self.completeness_status, str)
            or self.completeness_status not in {"complete", "pending_partial"}
            or type(self.exclude_from_geometry_training) is not bool
            or type(self.include_in_partial_grid_training) is not bool
            or self.version
            not in {
                GEOMETRY_QUALIFICATION_VERSION_V1,
                GEOMETRY_QUALIFICATION_VERSION,
            }
            or not isinstance(indices, tuple)
            or any(type(index) is not int or not 0 <= index < 15 for index in indices)
            or indices != tuple(sorted(set(indices)))
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
        if self.include_in_partial_grid_training and self.version != GEOMETRY_QUALIFICATION_VERSION:
            raise GeometryQualificationError(
                "Partial-grid training opt-in requires geometry qualification v2."
            )

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "version": self.version,
            "completenessStatus": self.completeness_status,
            "unavailableCellIndices": list(self.unavailable_cell_indices),
            "excludeFromGeometryTraining": self.exclude_from_geometry_training,
            "exclusionReason": self.exclusion_reason,
        }
        if self.version == GEOMETRY_QUALIFICATION_VERSION:
            payload["includeInPartialGridTraining"] = self.include_in_partial_grid_training
        return payload

    @classmethod
    def from_dict(cls, raw: object) -> GeometryQualification:
        base_keys = {
            "version",
            "completenessStatus",
            "unavailableCellIndices",
            "excludeFromGeometryTraining",
            "exclusionReason",
        }
        if not isinstance(raw, Mapping):
            raise GeometryQualificationError(
                "Geometry qualification fields are incomplete or unknown."
            )
        version = raw.get("version")
        keys = base_keys | (
            {"includeInPartialGridTraining"} if version == GEOMETRY_QUALIFICATION_VERSION else set()
        )
        if set(raw) != keys:
            raise GeometryQualificationError(
                "Geometry qualification fields are incomplete or unknown."
            )
        if version not in {GEOMETRY_QUALIFICATION_VERSION_V1, GEOMETRY_QUALIFICATION_VERSION}:
            raise GeometryQualificationError("Unsupported geometry qualification version.")
        indices = raw["unavailableCellIndices"]
        if not isinstance(indices, Sequence) or isinstance(indices, str | bytes):
            raise GeometryQualificationError("Unavailable cell indices must be an array.")
        return cls(
            completeness_status=cast(CompletenessStatus, raw["completenessStatus"]),
            unavailable_cell_indices=tuple(indices),
            exclude_from_geometry_training=raw["excludeFromGeometryTraining"],
            exclusion_reason=raw["exclusionReason"],
            include_in_partial_grid_training=(
                raw["includeInPartialGridTraining"]
                if version == GEOMETRY_QUALIFICATION_VERSION
                else False
            ),
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
