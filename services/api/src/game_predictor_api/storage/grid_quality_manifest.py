"""Atomic content-addressed publication of small immutable metadata manifests."""

import hashlib
import os
from pathlib import Path
from uuid import uuid4

from game_predictor_api.domain.grid_quality_measurements import canonical
from game_predictor_api.domain.image_reviews import ImageReviewConflictError


class GridQualityManifestStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def publish(self, document: object) -> tuple[str, str]:
        payload = canonical(document).encode()
        sha = hashlib.sha256(payload).hexdigest()
        relative = f"grid-quality/manifests/{sha}.json"
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            self.verify(relative, sha)
            return relative, sha
        staged = target.with_name(f".{sha}.{uuid4().hex}.staged")
        try:
            with staged.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(staged, target)
        finally:
            staged.unlink(missing_ok=True)
        self.verify(relative, sha)
        return relative, sha

    def verify(self, relative: str, sha: str) -> None:
        expected = f"grid-quality/manifests/{sha}.json"
        if relative != expected:
            raise ImageReviewConflictError(
                "GRID_QUALITY_MANIFEST_INVALID", "Invalid manifest path."
            )
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root) or not path.is_file():
            raise ImageReviewConflictError("GRID_QUALITY_MANIFEST_UNAVAILABLE", "Manifest missing.")
        if hashlib.sha256(path.read_bytes()).hexdigest() != sha:
            raise ImageReviewConflictError(
                "GRID_QUALITY_MANIFEST_CHANGED", "Manifest checksum differs."
            )
