"""Explicit public projections, including recursive fail-closed frozen payload checks."""

import re
from typing import Any
from uuid import UUID

from game_predictor_api.domain.management_sessions import ManagementAccessError
from game_predictor_api.schemas.board_search_shares import BoardSearchSharePublicSearchResponse
from game_predictor_api.schemas.catalog import ApiModel


class ManagementPublicSearchResponse(ApiModel):
    search_context_id: UUID
    search: BoardSearchSharePublicSearchResponse


_FORBIDDEN = frozenset(
    {
        "accesscode",
        "accesstoken",
        "token",
        "tokenhash",
        "codehash",
        "codesalt",
        "secret",
        "password",
        "authorization",
        "cookie",
        "reviewitemid",
        "recognizedboardid",
        "importjobid",
        "cellreviewid",
        "cropsampleid",
        "cropchecksumsha256",
        "imagepath",
        "imagerelativepath",
        "relativepath",
        "absolutepath",
        "basepath",
        "hostbasepath",
    }
)
_TEXT = frozenset(
    {"name", "namepl", "nameen", "gamename", "label", "paylinename", "city", "street", "actor"}
)
_PATH = re.compile(r"(?:^|[\s\"'])(?:[a-zA-Z]:[\\/]|[\\/]{2}|/(?:home|var|tmp|Users|mnt|opt)/)")


def public_payload(value: Any, key: str = "") -> Any:
    """Reject unknown accidental secrets/paths rather than return partial history."""
    if isinstance(value, dict):
        result = {}
        for name, child in value.items():
            normalized = str(name).replace("_", "").replace("-", "").lower()
            if normalized in _FORBIDDEN:
                raise ManagementAccessError(
                    "MANAGEMENT_PUBLIC_PAYLOAD_INVALID", "Panel data is unavailable.", 503
                )
            result[name] = public_payload(child, normalized)
        return result
    if isinstance(value, list | tuple):
        return [public_payload(child) for child in value]
    if isinstance(value, str) and key not in _TEXT and _PATH.search(value):
        raise ManagementAccessError(
            "MANAGEMENT_PUBLIC_PAYLOAD_INVALID", "Panel data is unavailable.", 503
        )
    return value


def named_actor(actor: str) -> str:
    if actor.startswith("management-share:"):
        parts = actor.split(":", 2)
        return parts[2] if len(parts) == 3 else actor
    return actor
