"""Current managed-source support for the v3 automatic finalizer."""

from collections.abc import Mapping
from pathlib import Path

from sqlalchemy.orm import Session

from .source_image_crop_models import SourceImageCropModel


def current_variant_source_box(
    session: Session,
    *,
    pin: object,
    source_sha256: str,
    width: int,
    height: int,
    artifact_root: Path | None,
    source_relative_path: str | None,
    normalized_pixel_sha256: str | None,
) -> tuple[int, ...] | None:
    if not isinstance(pin, Mapping):
        return None
    qualification = pin.get("automaticQualification")
    profile = qualification.get("profile") if isinstance(qualification, Mapping) else None
    if not isinstance(profile, Mapping) or profile.get("version") != "full-board-auto-profile-v3":
        return None  # No additional SQL or serialization changes for historical policies.
    # An impossible expected box blocks every stamp; unknown provenance is never full support.
    if artifact_root is None or source_relative_path is None or normalized_pixel_sha256 is None:
        return ()
    import hashlib

    from game_predictor_worker.images.normalization import CanonicalSourceLoader

    from game_predictor_api.domain.source_crop import encode_attestation

    data = (artifact_root / "data").resolve()
    path = (data / source_relative_path).resolve()
    if not path.is_relative_to(data):
        return ()
    try:
        frame = CanonicalSourceLoader(allow_crop=True).load(
            path, expected_source_checksum_sha256=source_sha256
        )
    except (OSError, ValueError):
        return ()
    if (frame.source.width, frame.source.height) != (
        width,
        height,
    ) or frame.source.normalized_pixel_checksum_sha256 != normalized_pixel_sha256:
        return ()
    crop = session.get(SourceImageCropModel, source_sha256)
    if crop is not None and (
        crop.original_width != width
        or crop.original_height != height
        or crop.original_normalized_pixel_checksum_sha256 != normalized_pixel_sha256
    ):
        return ()
    if frame.crop is None:
        # A current independently verified copy remains usable if an older original was deleted.
        return (0, 0, width, height)
    if (
        crop is None
        or crop.state != "original_deleted"
        or crop.original_deleted_at is None
        or tuple(crop.crop_box) != tuple(frame.crop.valid_box.as_list())
        or crop.attestation_sha256
        != hashlib.sha256(encode_attestation(frame.crop.attestation)).hexdigest()
    ):
        return ()
    return tuple(crop.crop_box)
