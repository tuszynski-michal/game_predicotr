"""Domain contracts for human-approved symbol reference images.

This module intentionally does not depend on the legacy bootstrap flow.  A
candidate is scoped to one current canonical review decision and carries every
revision needed to prove that its crop was reviewed by a human.
"""

from __future__ import annotations

import json
import re
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass
from datetime import datetime
from typing import Final
from uuid import UUID

from game_predictor_api.domain.catalog import CatalogConflictError
from game_predictor_api.domain.image_symbol_reviews import SymbolCellReviewAsset

_SHA256: Final = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class ApprovedSymbolReferenceCandidate:
    """One current, human-approved crop eligible as a catalog reference.

    ``crop_checksum_sha256`` identifies the pixels the operator approved.  A
    virtual v0.10 crop has no file at this stage; its exact render contract is
    carried privately in ``virtual_asset`` and is materialized only when the
    operator selects it as the durable catalog reference.
    """

    observation_id: UUID
    review_item_id: UUID
    recognized_board_id: UUID
    sequence_number: int
    cell_index: int
    resolution_revision: int
    geometry_revision: int
    crop_relative_path: str | None
    crop_checksum_sha256: str
    status: str
    asset_mode: str = "legacy_file"
    virtual_asset: SymbolCellReviewAsset | None = None

    def __post_init__(self) -> None:
        if self.asset_mode == "legacy_file":
            if not self.crop_relative_path or self.virtual_asset is not None:
                raise ValueError("legacy reference candidates require one crop path")
            return
        if self.asset_mode != "virtual_source":
            raise ValueError("asset_mode must be legacy_file or virtual_source")
        if self.crop_relative_path is not None or self.virtual_asset is None:
            raise ValueError("virtual reference candidates require render provenance")
        if self.virtual_asset.asset_mode != "virtual_source":
            raise ValueError("virtual reference candidates require a virtual asset")

    @property
    def is_virtual(self) -> bool:
        return self.asset_mode == "virtual_source"

    @property
    def cursor_key(self) -> tuple[int, int, int, str]:
        """Stable order: corrected geometry, sequence, cell, observation."""

        return (
            0 if self.geometry_revision > 0 else 1,
            self.sequence_number,
            self.cell_index,
            str(self.observation_id),
        )


@dataclass(frozen=True, slots=True)
class ApprovedSymbolReferenceCandidatePage:
    items: tuple[ApprovedSymbolReferenceCandidate, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class SymbolReferenceImage:
    """Immutable, checksum-bound copy selected for one catalog symbol."""

    symbol_id: UUID
    source_review_item_id: UUID
    source_recognized_board_id: UUID
    source_observation_id: UUID
    sequence_number: int
    cell_index: int
    resolution_revision: int
    geometry_revision: int
    image_relative_path: str
    image_checksum_sha256: str
    selected_by: str
    selected_at: datetime


def encode_approved_symbol_reference_cursor(
    *, game_id: UUID, symbol_id: UUID, key: tuple[int, int, int, str]
) -> str:
    raw = json.dumps(
        {"gameId": str(game_id), "key": list(key), "symbolId": str(symbol_id)},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_approved_symbol_reference_cursor(
    value: str, *, game_id: UUID, symbol_id: UUID
) -> tuple[int, int, int, str]:
    try:
        payload = json.loads(
            urlsafe_b64decode(value + "=" * (-len(value) % 4)).decode("utf-8")
        )
        key = payload["key"]
        if (
            payload["gameId"] != str(game_id)
            or payload["symbolId"] != str(symbol_id)
            or not isinstance(key, list)
            or len(key) != 4
            or any(not isinstance(item, int) or isinstance(item, bool) for item in key[:3])
            or not isinstance(key[3], str)
            or key[0] not in {0, 1}
            or key[1] <= 0
            or not 0 <= key[2] < 15
        ):
            raise ValueError
        return key[0], key[1], key[2], key[3]
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CatalogConflictError(
            "SYMBOL_REFERENCE_CURSOR_INVALID",
            "The approved symbol reference cursor is invalid for this scope.",
        ) from error


def validate_reference_checksum(value: str) -> str:
    if not _SHA256.fullmatch(value):
        raise CatalogConflictError(
            "SYMBOL_REFERENCE_CHECKSUM_INVALID",
            "The selected symbol reference checksum must be a SHA-256 value.",
        )
    return value


__all__ = [
    "ApprovedSymbolReferenceCandidate",
    "ApprovedSymbolReferenceCandidatePage",
    "SymbolReferenceImage",
    "decode_approved_symbol_reference_cursor",
    "encode_approved_symbol_reference_cursor",
    "validate_reference_checksum",
]
