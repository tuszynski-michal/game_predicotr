"""Bound content bundle allocation before decoding or parsing JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from game_predictor_api.domain import grid_content_bundle as contract


def read_content_bundle_bytes(path: Path, *, limit: int | None = None) -> bytes:
    bound = contract.CONTENT_BUNDLE_MAX_BYTES if limit is None else limit
    size = path.stat().st_size
    if size > bound:
        raise contract.ContentBundleTooLarge(size, bound)
    with path.open("rb") as stream:
        payload = stream.read(bound + 1)
    # Also catches growth after stat, without allocating the entire growing file.
    if len(payload) > bound:
        raise contract.ContentBundleTooLarge(len(payload), bound)
    return payload


def read_content_bundle(path: Path, *, limit: int | None = None) -> Any:
    return json.loads(read_content_bundle_bytes(path, limit=limit))
