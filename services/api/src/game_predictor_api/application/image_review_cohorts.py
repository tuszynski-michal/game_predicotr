"""Application boundary for immutable verified review cohort exports."""

from __future__ import annotations

import hashlib
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from typing import Protocol
from uuid import UUID

from game_predictor_api.domain.image_review_cohorts import (
    ImageVerifiedCohortExport,
    VerifiedCohortSource,
    build_verified_cohort_payload,
    build_verified_cohort_source,
    validate_cohort_actor,
)
from game_predictor_api.domain.image_reviews import (
    ImageReviewConflictError,
    ImageReviewCounts,
    ImageReviewItem,
)


class VerifiedCohortSourceRepository(Protocol):
    def lock_verified_snapshot(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
    ) -> tuple[Sequence[ImageReviewItem], ImageReviewCounts]: ...


class VerifiedCohortExportRepository(Protocol):
    def find_by_state(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        input_state_sha256: str,
    ) -> ImageVerifiedCohortExport | None: ...

    def next_version(self, *, game_id: UUID, import_job_id: UUID) -> int: ...

    def save(
        self,
        *,
        source: VerifiedCohortSource,
        version: int,
        payload_sha256: str,
        artifact_relative_path: str,
        created_by: str,
    ) -> ImageVerifiedCohortExport: ...

    def list(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        limit: int,
    ) -> Sequence[ImageVerifiedCohortExport]: ...


class VerifiedCohortArtifactStore:
    def __init__(self, artifact_root: Path) -> None:
        self._managed_root = artifact_root.resolve() / "data"

    def write(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        payload_sha256: str,
        payload_bytes: bytes,
    ) -> str:
        if hashlib.sha256(payload_bytes).hexdigest() != payload_sha256:
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_COHORT_CHECKSUM_INVALID",
                "The verified cohort payload checksum does not match its bytes.",
            )
        relative = PurePosixPath(
            "cohorts",
            f"{game_id.hex[:8]}{import_job_id.hex[:8]}",
            f"{payload_sha256}.json",
        )
        destination = self._managed_root.joinpath(*relative.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            self._verify(destination, payload_sha256)
            return relative.as_posix()
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=destination.parent,
                prefix=".tmp-",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_name = handle.name
                handle.write(payload_bytes)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, destination)
            temporary_name = None
        finally:
            if temporary_name is not None:
                Path(temporary_name).unlink(missing_ok=True)
        self._verify(destination, payload_sha256)
        return relative.as_posix()

    def verify(self, artifact_relative_path: str, payload_sha256: str) -> None:
        relative = PurePosixPath(artifact_relative_path)
        if relative.is_absolute() or ".." in relative.parts or "\\" in artifact_relative_path:
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_COHORT_ARTIFACT_UNSAFE",
                "The verified cohort artifact path is unsafe.",
            )
        candidate = self._managed_root.joinpath(*relative.parts).resolve()
        if not candidate.is_relative_to(self._managed_root) or candidate.is_symlink():
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_COHORT_ARTIFACT_UNSAFE",
                "The verified cohort artifact path is outside managed storage.",
            )
        self._verify(candidate, payload_sha256)

    @staticmethod
    def _verify(path: Path, payload_sha256: str) -> None:
        if not path.is_file():
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_COHORT_ARTIFACT_MISSING",
                "The immutable verified cohort artifact is unavailable.",
            )
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        if digest.hexdigest() != payload_sha256:
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_COHORT_ARTIFACT_CHANGED",
                "The immutable verified cohort artifact checksum changed.",
            )


class VerifiedCohortService:
    def __init__(
        self,
        source_repository: VerifiedCohortSourceRepository,
        export_repository: VerifiedCohortExportRepository,
        artifact_store: VerifiedCohortArtifactStore,
    ) -> None:
        self._source_repository = source_repository
        self._export_repository = export_repository
        self._artifact_store = artifact_store

    def freeze(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        created_by: str,
    ) -> tuple[ImageVerifiedCohortExport, bool]:
        actor = validate_cohort_actor(created_by)
        items, counts = self._source_repository.lock_verified_snapshot(
            game_id=game_id,
            import_job_id=import_job_id,
        )
        source = build_verified_cohort_source(
            game_id=game_id,
            import_job_id=import_job_id,
            items=items,
            counts=counts,
        )
        existing = self._export_repository.find_by_state(
            game_id=game_id,
            import_job_id=import_job_id,
            input_state_sha256=source.input_state_sha256,
        )
        if existing is not None:
            self._artifact_store.verify(
                existing.artifact_relative_path,
                existing.payload_sha256,
            )
            return existing, False
        version = self._export_repository.next_version(
            game_id=game_id,
            import_job_id=import_job_id,
        )
        _payload, payload_bytes, payload_sha256 = build_verified_cohort_payload(
            source,
            version=version,
        )
        artifact_relative_path = self._artifact_store.write(
            game_id=game_id,
            import_job_id=import_job_id,
            payload_sha256=payload_sha256,
            payload_bytes=payload_bytes,
        )
        return (
            self._export_repository.save(
                source=source,
                version=version,
                payload_sha256=payload_sha256,
                artifact_relative_path=artifact_relative_path,
                created_by=actor,
            ),
            True,
        )

    def list(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        limit: int = 50,
    ) -> Sequence[ImageVerifiedCohortExport]:
        if not 1 <= limit <= 100:
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_COHORT_LIMIT_INVALID",
                "Verified cohort export limit must be between 1 and 100.",
            )
        return self._export_repository.list(
            game_id=game_id,
            import_job_id=import_job_id,
            limit=limit,
        )


__all__ = [
    "VerifiedCohortArtifactStore",
    "VerifiedCohortExportRepository",
    "VerifiedCohortService",
    "VerifiedCohortSourceRepository",
]
