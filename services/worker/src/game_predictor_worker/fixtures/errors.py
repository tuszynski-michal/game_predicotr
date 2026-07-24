"""Stable failures raised while validating build-time fixtures."""

from __future__ import annotations

from enum import StrEnum


class FixtureErrorCode(StrEnum):
    DUPLICATE_INTEGRITY_ERROR = "duplicate_integrity_error"
    FIXTURE_METADATA_ERROR = "fixture_metadata_error"
    GAME_CONFIG_ERROR = "game_config_error"
    LAYOUT_INTEGRITY_ERROR = "layout_integrity_error"
    PAYOUT_INTEGRITY_ERROR = "payout_integrity_error"
    PREFIX_INTEGRITY_ERROR = "prefix_integrity_error"
    SEQUENCE_INTEGRITY_ERROR = "sequence_integrity_error"
    SIGNATURE_INTEGRITY_ERROR = "signature_integrity_error"


class FixtureValidationError(ValueError):
    """A deterministic failure of the build-time fixture contract."""

    def __init__(self, code: FixtureErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
