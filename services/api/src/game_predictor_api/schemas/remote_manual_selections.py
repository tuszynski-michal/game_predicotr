"""Local Admin schemas for host-bound remote manual selection setup."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from game_predictor_api.application.remote_manual_selection_host import (
    RemoteManualSelectionBaseCapability,
)
from game_predictor_api.schemas.catalog import ApiModel


class RemoteManualSelectionBaseCapabilityResponse(ApiModel):
    status: Literal["selected", "cancelled"]
    base_capability: str | None = None
    display_name: str | None = None
    expires_at: datetime | None = None

    @classmethod
    def selected(
        cls,
        value: RemoteManualSelectionBaseCapability,
    ) -> RemoteManualSelectionBaseCapabilityResponse:
        return cls(
            status="selected",
            base_capability=value.capability,
            display_name=value.display_name,
            expires_at=value.expires_at,
        )

    @classmethod
    def cancelled(cls) -> RemoteManualSelectionBaseCapabilityResponse:
        return cls(status="cancelled")


__all__ = ["RemoteManualSelectionBaseCapabilityResponse"]
