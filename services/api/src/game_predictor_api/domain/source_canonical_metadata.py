"""Canonical source metadata completion without persistence or lease ownership."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, cast


@dataclass(frozen=True, slots=True)
class SourceCanonicalMetadata:
    """The complete coordinate metadata group; absent EXIF remains a valid None."""

    raw_width: int | None = None
    raw_height: int | None = None
    oriented_width: int | None = None
    oriented_height: int | None = None
    exif_orientation: int | None = None
    coordinate_space: str | None = None
    normalization_adapter_version: str | None = None
    normalized_pixel_checksum_sha256: str | None = None

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> SourceCanonicalMetadata:
        """Read every existing field without converting or repairing its values."""

        return cls(
            raw_width=cast(int | None, values["raw_width"]),
            raw_height=cast(int | None, values["raw_height"]),
            oriented_width=cast(int | None, values["oriented_width"]),
            oriented_height=cast(int | None, values["oriented_height"]),
            exif_orientation=cast(int | None, values["exif_orientation"]),
            coordinate_space=cast(str | None, values["coordinate_space"]),
            normalization_adapter_version=cast(str | None, values["normalization_adapter_version"]),
            normalized_pixel_checksum_sha256=cast(
                str | None, values["normalized_pixel_checksum_sha256"]
            ),
        )

    def to_dict(self) -> dict[str, int | str | None]:
        return {
            "raw_width": self.raw_width,
            "raw_height": self.raw_height,
            "oriented_width": self.oriented_width,
            "oriented_height": self.oriented_height,
            "exif_orientation": self.exif_orientation,
            "coordinate_space": self.coordinate_space,
            "normalization_adapter_version": self.normalization_adapter_version,
            "normalized_pixel_checksum_sha256": self.normalized_pixel_checksum_sha256,
        }


def compare_source_metadata(
    current: SourceCanonicalMetadata, expected: SourceCanonicalMetadata
) -> Literal["complete", "unchanged", "conflict"]:
    """Preserve the pipeline's all-NULL completion or exact equality rule."""

    if all(value is None for value in current.to_dict().values()):
        return "complete"
    if current == expected:
        return "unchanged"
    return "conflict"
