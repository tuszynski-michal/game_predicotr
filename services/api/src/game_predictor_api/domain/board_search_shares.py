"""Online, read-only board-search share sessions (D-471).

A share session exposes one game's board search through the Reviewer proxy
to a person holding the link and a separate access code. It never widens the
Reviewer or remote-selection sessions and has no write capability.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

BOARD_SEARCH_SHARE_MIN_LIFETIME_MINUTES: Final = 5
BOARD_SEARCH_SHARE_MAX_LIFETIME_MINUTES: Final = 24 * 60
BOARD_SEARCH_SHARE_DEFAULT_LIFETIME_MINUTES: Final = 8 * 60
BOARD_SEARCH_SHARE_MAX_FAILED_ATTEMPTS: Final = 5
BOARD_SEARCH_SHARE_MAX_ACTIVE_SESSIONS: Final = 5
BOARD_SEARCH_SHARE_LABEL_MAX_LENGTH: Final = 100

BOARD_SEARCH_SHARE_COOKIE_NAME: Final = "gp_board_search_token"
BOARD_SEARCH_SHARE_COOKIE_PATH: Final = "/board-search-api"
BOARD_SEARCH_SHARE_PROXY_HEADER: Final = "X-Board-Search-Share-Proxy"
BOARD_SEARCH_SHARE_PROXY_INTENT: Final = "reviewer-board-search-v1"
BOARD_SEARCH_SHARE_REVIEWER_PATH: Final = "/board-search"


class BoardSearchShareStatus(StrEnum):
    """Projected status of a share session at one moment."""

    ACTIVE = "active"
    LOCKED = "locked"
    EXPIRED = "expired"
    REVOKED = "revoked"


class BoardSearchShareAuditEventType(StrEnum):
    CREATED = "created"
    UNLOCK_FAILED = "unlock_failed"
    UNLOCKED = "unlocked"
    LOCKED = "locked"
    REVOKED = "revoked"


class BoardSearchShareError(Exception):
    """Base error with a stable code for the share boundary."""

    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details: dict[str, object] = details or {}


class BoardSearchShareNotFoundError(BoardSearchShareError):
    pass


class BoardSearchShareAuthenticationError(BoardSearchShareError):
    pass


class BoardSearchShareAuthorizationError(BoardSearchShareError):
    pass


class BoardSearchShareConflictError(BoardSearchShareError):
    pass


class BoardSearchShareRateLimitError(BoardSearchShareError):
    pass


class BoardSearchShareUnavailableError(BoardSearchShareError):
    pass


def validate_board_search_share_lifetime(lifetime_minutes: int) -> int:
    if not (
        BOARD_SEARCH_SHARE_MIN_LIFETIME_MINUTES
        <= lifetime_minutes
        <= BOARD_SEARCH_SHARE_MAX_LIFETIME_MINUTES
    ):
        raise BoardSearchShareError(
            "BOARD_SEARCH_SHARE_LIFETIME_INVALID",
            "Share lifetime must be between 5 minutes and 24 hours.",
        )
    return lifetime_minutes


def normalize_board_search_share_label(label: str | None) -> str | None:
    """Collapse whitespace; `None` or blank means no label."""

    if label is None:
        return None
    normalized = " ".join(label.split())
    if not normalized:
        return None
    if len(normalized) > BOARD_SEARCH_SHARE_LABEL_MAX_LENGTH:
        raise BoardSearchShareError(
            "BOARD_SEARCH_SHARE_LABEL_INVALID",
            "Share label must contain at most 100 characters.",
        )
    return normalized


__all__ = [
    "BOARD_SEARCH_SHARE_COOKIE_NAME",
    "BOARD_SEARCH_SHARE_COOKIE_PATH",
    "BOARD_SEARCH_SHARE_DEFAULT_LIFETIME_MINUTES",
    "BOARD_SEARCH_SHARE_LABEL_MAX_LENGTH",
    "BOARD_SEARCH_SHARE_MAX_ACTIVE_SESSIONS",
    "BOARD_SEARCH_SHARE_MAX_FAILED_ATTEMPTS",
    "BOARD_SEARCH_SHARE_MAX_LIFETIME_MINUTES",
    "BOARD_SEARCH_SHARE_MIN_LIFETIME_MINUTES",
    "BOARD_SEARCH_SHARE_PROXY_HEADER",
    "BOARD_SEARCH_SHARE_PROXY_INTENT",
    "BOARD_SEARCH_SHARE_REVIEWER_PATH",
    "BoardSearchShareAuditEventType",
    "BoardSearchShareAuthenticationError",
    "BoardSearchShareAuthorizationError",
    "BoardSearchShareConflictError",
    "BoardSearchShareError",
    "BoardSearchShareNotFoundError",
    "BoardSearchShareRateLimitError",
    "BoardSearchShareStatus",
    "BoardSearchShareUnavailableError",
    "normalize_board_search_share_label",
    "validate_board_search_share_lifetime",
]
