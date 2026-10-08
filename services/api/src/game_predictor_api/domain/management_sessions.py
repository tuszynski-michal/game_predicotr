"""Independent whole-panel capabilities; never a one-game Reviewer session."""

from typing import Final

MANAGEMENT_COOKIE: Final = "gp_management_token"
MANAGEMENT_COOKIE_PATH: Final = "/management-api"
MANAGEMENT_PROXY_HEADER: Final = "X-Management-Public-Proxy"
MANAGEMENT_PROXY_INTENT: Final = "reviewer-management-v1"
MANAGEMENT_EXPECTED_SESSION_HEADER: Final = "X-Management-Session"
MANAGEMENT_LIFETIMES: Final = (60, 240, 480, 1440, 2880, 4320)


class ManagementAccessError(Exception):
    """Separate from recoverable ManagementError: auth never becomes stale success."""

    def __init__(self, code: str, message: str, status: int = 401) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def invalid_access() -> ManagementAccessError:
    return ManagementAccessError(
        "MANAGEMENT_TOKEN_INVALID", "Panel access expired or changed. Enter the code again."
    )
