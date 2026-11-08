"""One byte contract for the new, self-contained content experiment bundle."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

CONTENT_BUNDLE_MAX_BYTES = 16 * 1024 * 1024


class ContentBundleTooLarge(ValueError):
    code = "CONTENT_EXPERIMENT_BUNDLE_TOO_LARGE"

    def __init__(self, actual_bytes: int, limit_bytes: int) -> None:
        self.actual_bytes, self.limit_bytes = actual_bytes, limit_bytes
        super().__init__(f"{self.code}: {actual_bytes} bytes exceed {limit_bytes} bytes")


def require_content_bundle_bytes(size: int) -> None:
    if size > CONTENT_BUNDLE_MAX_BYTES:
        raise ContentBundleTooLarge(size, CONTENT_BUNDLE_MAX_BYTES)


def require_content_bundle_size(document: Mapping[str, Any]) -> None:
    # Exactly the serialization used by grid_training_child.write_json_atomic.
    size = len(json.dumps(dict(document), indent=2, sort_keys=True).encode("utf-8"))
    require_content_bundle_bytes(size)


def require_content_bundle_inputs(
    plan: Mapping[str, Any], inputs: Mapping[str, Any], bank: Mapping[str, Any] | None = None
) -> None:
    """Reject an already impossible export before training; this is a lower bound.

    Future exposure, selection and parity are not yet known. The complete export
    is checked again, without dropping any source or shortening its evidence.
    """
    proof: dict[str, Any] = {"plan": plan, "inputs": inputs}
    if bank is not None:
        proof["bank"] = bank
    require_content_bundle_size({"provenance": {"contentExperiment": proof}})
