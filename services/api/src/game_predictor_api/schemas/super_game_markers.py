"""OpenAPI schemas of the super game markers of board-search reads (TASK-0935).

``SuperGamePublicMarkerResponse`` is the marker as the management panel shows
it (no series identity); ``SuperGameMarkerResponse`` adds the ``seriesId`` that
links a board to a series view.  The Admin and, since D-564, the online
board-search share return the latter (the share opens the series of a marked
board); the management panel drops the identity with ``response_model_exclude``
(:data:`PUBLIC_APPROXIMATE_WIN_EXCLUDE`, :data:`PUBLIC_SEARCH_EXCLUDE`).
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
            "Series identity for the series view. Set by the Admin routes and, "
            "since D-564, by the online board-search share (the recipient opens "
            "the series); omitted from the management panel responses only."
        ),
    )


PUBLIC_APPROXIMATE_WIN_EXCLUDE: Final[dict[str, Any]] = {
    "rows": {"__all__": {"super_game": {"series_id"}}}
}
"""`response_model_exclude` of the management panel's approximate-win route:
the shared row model keeps `seriesId` for the Admin and the share."""

PUBLIC_SEARCH_EXCLUDE: Final[dict[str, Any]] = {
    "search": {"results": {"__all__": {"super_game": {"series_id"}}}}
}
"""`response_model_exclude` of the management panel's search route (its
payload guard refuses any `seriesId` key, even a null one)."""


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


__all__ = [
    "PUBLIC_APPROXIMATE_WIN_EXCLUDE",
    "PUBLIC_SEARCH_EXCLUDE",
    "SuperGameMarkerResponse",
    "SuperGamePublicMarkerResponse",
    "marker_response_at",
    "to_super_game_marker_response",
]
