"""An absent EXIF tag must not turn complete canonical metadata into a repair."""

from dataclasses import replace

import pytest
from game_predictor_api.domain.source_canonical_metadata import (
    SourceCanonicalMetadata,
    compare_source_metadata,
)

COMPLETE = SourceCanonicalMetadata(
    raw_width=40,
    raw_height=30,
    oriented_width=40,
    oriented_height=30,
    exif_orientation=None,
    coordinate_space="exif-normalized-rgb-pixels-v1",
    normalization_adapter_version="image-normalization-v2-in-memory-source-v1",
    normalized_pixel_checksum_sha256="a" * 64,
)


def test_all_null_can_complete_but_complete_without_exif_is_unchanged():
    empty = SourceCanonicalMetadata()
    assert compare_source_metadata(empty, COMPLETE) == "complete"
    assert compare_source_metadata(COMPLETE, COMPLETE) == "unchanged"
    assert SourceCanonicalMetadata.from_mapping(COMPLETE.to_dict()) == COMPLETE
    assert empty == SourceCanonicalMetadata()


@pytest.mark.parametrize("field", COMPLETE.to_dict())
def test_any_existing_mismatch_conflicts_instead_of_completing(field):
    value = getattr(COMPLETE, field)
    different = 6 if field == "exif_orientation" else None
    assert value != different
    current = replace(COMPLETE, **{field: different})
    assert compare_source_metadata(current, COMPLETE) == "conflict"


def test_partial_metadata_and_changed_pixel_identity_are_never_repaired():
    assert compare_source_metadata(SourceCanonicalMetadata(raw_width=40), COMPLETE) == "conflict"
    changed = replace(COMPLETE, normalized_pixel_checksum_sha256="b" * 64)
    assert compare_source_metadata(changed, COMPLETE) == "conflict"
