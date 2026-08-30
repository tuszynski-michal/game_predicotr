"""Lifecycle contract for finalized browser image staging."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ManagedOriginalsHandoff:
    upload_id: UUID
    game_id: UUID
    import_job_id: UUID
    manifest_relative_path: str
    manifest_checksum_sha256: str
    completed_at: datetime


class BrowserStagingRetention(Protocol):
    def record_ready(
        self,
        *,
        upload_id: UUID,
        game_id: UUID | None,
        display_name: str,
        manifest_checksum_sha256: str,
        finalized_at: datetime,
    ) -> None: ...

    def record_in_use(
        self,
        *,
        upload_id: UUID,
        game_id: UUID,
        job_id: UUID,
        used_at: datetime,
    ) -> None: ...

    def record_ingested(self, handoff: ManagedOriginalsHandoff) -> None: ...

    def discard_unused(self, *, upload_id: UUID) -> None:
        """Remove database state created only while preparing an unused staging.

        Implementations must fail closed when the staging produced reviewable,
        canonical, or otherwise externally referenced domain data.
        """
        ...


__all__ = ["BrowserStagingRetention", "ManagedOriginalsHandoff"]
