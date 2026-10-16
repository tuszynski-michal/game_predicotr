"""OpenAPI models for local panel ownership and public capability access."""

from datetime import datetime
from urllib.parse import urlencode, urlparse, urlunparse
from uuid import UUID

from pydantic import Field

from game_predictor_api.application.board_search_panels import BoardSearchPanelView
from game_predictor_api.application.reviewer_ingress import (
    ReviewerIngressStatus,
    is_ready_online_reviewer_ingress,
)
from game_predictor_api.schemas.catalog import ApiModel


class BoardSearchPanelCreate(ApiModel):
    game_ids: list[UUID] = Field(min_length=1, max_length=100)
    label: str | None = Field(default=None, max_length=100)
    lifetime_minutes: int = Field(default=480, ge=5, le=4320)


class BoardSearchPanelGameResponse(ApiModel):
    game_id: UUID
    game_name: str
    session_id: UUID


class BoardSearchPanelResponse(ApiModel):
    panel_id: UUID
    label: str | None
    created_at: datetime
    expires_at: datetime
    status: str
    games: list[BoardSearchPanelGameResponse]
    ready: bool
    share_url: str | None

    @classmethod
    def from_view(
        cls, view: BoardSearchPanelView, ingress: ReviewerIngressStatus | None
    ) -> "BoardSearchPanelResponse":
        ready = (
            view.status == "active"
            and ingress is not None
            and is_ready_online_reviewer_ingress(ingress)
        )
        url = None
        if ready and ingress is not None and ingress.public_origin:
            url = urlunparse(
                urlparse(ingress.public_origin)._replace(
                    path="/board-search-panel",
                    query=urlencode({"share": str(view.panel_id)}),
                    fragment="",
                )
            )
        return cls(
            panel_id=view.panel_id,
            label=view.label,
            created_at=view.created_at,
            expires_at=view.expires_at,
            status=view.status,
            ready=ready,
            share_url=url,
            games=[
                BoardSearchPanelGameResponse(
                    game_id=g.game_id, game_name=g.game_name, session_id=g.session_id
                )
                for g in view.games
            ],
        )


class BoardSearchPanelCreatedResponse(ApiModel):
    panel: BoardSearchPanelResponse
    link_key: str = Field(description="Shown once; stored only as a hash on the server.")


class BoardSearchPanelListResponse(ApiModel):
    panels: list[BoardSearchPanelResponse]


class BoardSearchPanelOpen(ApiModel):
    link_key: str = Field(min_length=32, max_length=256, pattern=r"^[A-Za-z0-9_-]+$")


class BoardSearchPanelPublicGameResponse(ApiModel):
    session_id: UUID
    game_name: str


class BoardSearchPanelContextResponse(ApiModel):
    panel_id: UUID
    label: str | None
    expires_at: datetime
    games: list[BoardSearchPanelPublicGameResponse]

    @classmethod
    def from_view(cls, view: BoardSearchPanelView) -> "BoardSearchPanelContextResponse":
        return cls(
            panel_id=view.panel_id,
            label=view.label,
            expires_at=view.expires_at,
            games=[
                BoardSearchPanelPublicGameResponse(session_id=g.session_id, game_name=g.game_name)
                for g in view.games
            ],
        )
