"""Independent quality labels never imply symbol-name approval."""

import hashlib
import json
from collections.abc import Mapping
from typing import Any
from uuid import UUID

GAME_ID = UUID("6e20a58f-88f3-4a9c-87b5-ae3297ed4fbf")
BASE_ID = "9afa868a-70f8-42df-9f15-f2833cd98c10"
CHECKPOINT_SHA = "29fbc9862c347e472eb2c256ab58c2ad34feb06e91db7fab9a5c0c739598649d"
DATASET_SHA = "696cac7e444436569bb7804917e40941ab01277951451e491bbd86a2d78180aa"
CHECKPOINT_PATH = f"data/models/777a2/{BASE_ID}/checkpoints/trained-0040-{CHECKPOINT_SHA}.pt"
DATASET_PATH = (
    "data/training/777a2/d01db572f4eef1e98a51f0e5996e910003528c9b290a8b447a8a831edeb70e3a/"
    f"manifests/{DATASET_SHA}.json"
)


class ReadabilityWorkflowError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str
        ).encode()
    ).hexdigest()


def crop_identity(snapshot: Mapping[str, Any]) -> str:
    return digest(
        {
            key: snapshot.get(key)
            for key in (
                "cell_id",
                "source_id",
                "source_sha256",
                "geometry_revision",
                "source_geometry_revision_id",
                "crop_sample_id",
                "crop_checksum_sha256",
                "render_spec_checksum_sha256",
                "rendered_pixel_checksum_sha256",
                "render_identity_v2_sha256",
            )
        }
    )


def identity_is_current(snapshot: Mapping[str, Any], current: Mapping[str, Any] | None) -> bool:
    return bool(
        current is not None
        and crop_identity(snapshot) == crop_identity(current)
        and current["geometry_revision"] == current["board_geometry_revision"]
        and current["source_geometry_revision_id"] == current["board_source_geometry_revision_id"]
        and current["board_status"] != "rejected"
    )


def confirmed_for_replacement(state: str, *, current: bool) -> bool:
    return current and state == "unreadable"
