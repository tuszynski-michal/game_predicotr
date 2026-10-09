"""OpenAPI schemas of the super game markers of board-search reads (TASK-0935).

``SuperGamePublicMarkerResponse`` is the marker as the online share and the
management panel show it (no series identity); ``SuperGameMarkerResponse`` adds
the ``seriesId`` that links a board to the Admin's series view.  Public routes
return the former: separate result models for search, ``response_model_exclude``
(:data:`PUBLIC_APPROXIMATE_WIN_EXCLUDE`) for the shared approximate-win model.
"""

from __future__ import annotations

from typing import Any, Final
from uuid import UUID

from pydantic import Field

from game_predictor_api.domain.super_game_markers import (
    SuperGameMarker,
    SuperGameMarkerKind,
    SuperGameMarkers,
)
from game_predictor_api.domain.super_game_series import RunVerification, SeriesCompleteness
from game_predictor_api.schemas.catalog import ApiModel


class SuperGamePublicMarkerResponse(ApiModel):
    """The super game role of a board in the published series generation.

    Absent on a board means base mode according to that generation (see the
    response's ``superGameState`` for whether the generation is current).
    """

    kind: SuperGameMarkerKind
    spin_index: int | None = Field(
        default=None,
        ge=1,
        description="1-based spin of the series; null for the trigger board.",
    )
    series_length: int = Field(ge=1)
    super_symbol_code: str | None = Field(
        default=None,
        description="Code of the defined super symbol; null while it is still to be defined.",
    )
    completeness: SeriesCompleteness
    run_verification: RunVerification


class SuperGameMarkerResponse(SuperGamePublicMarkerResponse):
    series_id: UUID | None = Field(
        default=None,
        description=(
            "Series identity for the Admin series view. Always set by the Admin "
            "routes; omitted from the online share and management panel responses "
            "(a public marker is therefore also a valid marker without a link)."
        ),
    )


PUBLIC_APPROXIMATE_WIN_EXCLUDE: Final[dict[str, Any]] = {
    "rows": {"__all__": {"super_game": {"series_id"}}}
}
"""`response_model_exclude` of the approximate-win routes that serve the online
share and the management panel: the shared row model keeps `seriesId` for the
Admin only."""


def to_super_game_marker_response(marker: SuperGameMarker) -> SuperGameMarkerResponse:
    return SuperGameMarkerResponse(
        kind=marker.kind,
        series_id=marker.series_id,
        spin_index=marker.spin_index,
        series_length=marker.series_length,
        super_symbol_code=marker.super_symbol_code,
        completeness=marker.completeness,
        run_verification=marker.run_verification,
    )


def marker_response_at(
    markers: SuperGameMarkers | None, position: int
) -> SuperGameMarkerResponse | None:
    """The Admin marker of ``position``, or ``None`` (base mode / no source)."""

    marker = None if markers is None else markers.marker(position)
    return None if marker is None else to_super_game_marker_response(marker)


def to_super_game_public_marker_response(
    marker: SuperGamePublicMarkerResponse,
) -> SuperGamePublicMarkerResponse:
    """The marker without its series identity (accepts the Admin marker)."""

    return SuperGamePublicMarkerResponse(
        kind=marker.kind,
        spin_index=marker.spin_index,
        series_length=marker.series_length,
        super_symbol_code=marker.super_symbol_code,
        completeness=marker.completeness,
        run_verification=marker.run_verification,
    )


__all__ = [
    "PUBLIC_APPROXIMATE_WIN_EXCLUDE",
    "SuperGameMarkerResponse",
    "SuperGamePublicMarkerResponse",
    "marker_response_at",
    "to_super_game_marker_response",
    "to_super_game_public_marker_response",
]
