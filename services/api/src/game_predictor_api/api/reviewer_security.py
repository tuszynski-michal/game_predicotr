"""Shared bearer-token authorization for the public Reviewer surface."""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from game_predictor_api.application.reviewer_access import (
    ReviewerAccessError,
    ReviewerAccessService,
    ReviewerAccessSession,
)

ReviewerAccessServiceDependency = Callable[..., object]
_bearer = HTTPBearer(auto_error=False, scheme_name="ReviewerBearer")


def create_optional_reviewer_session_dependency(
    service_dependency: ReviewerAccessServiceDependency,
) -> Callable[..., ReviewerAccessSession | None]:
    credentials_parameter = Depends(_bearer)
    service_parameter = Depends(service_dependency)

    def optional_reviewer_session(
        credentials: Annotated[
            HTTPAuthorizationCredentials | None,
            credentials_parameter,
        ],
        service: Annotated[ReviewerAccessService, service_parameter],
    ) -> ReviewerAccessSession | None:
        if credentials is None:
            return None
        if credentials.scheme.lower() != "bearer":
            raise ReviewerAccessError(
                "REVIEWER_TOKEN_INVALID",
                "Reviewer access token is invalid or has expired.",
            )
        return service.authenticate(credentials.credentials)

    return optional_reviewer_session


def create_required_reviewer_session_dependency(
    service_dependency: ReviewerAccessServiceDependency,
) -> Callable[..., ReviewerAccessSession]:
    optional_dependency = create_optional_reviewer_session_dependency(service_dependency)
    session_parameter = Depends(optional_dependency)

    def required_reviewer_session(
        session: Annotated[ReviewerAccessSession | None, session_parameter],
    ) -> ReviewerAccessSession:
        if session is None:
            raise ReviewerAccessError(
                "REVIEWER_TOKEN_REQUIRED",
                "Reviewer access token is required.",
            )
        return session

    return required_reviewer_session


__all__ = [
    "ReviewerAccessServiceDependency",
    "create_optional_reviewer_session_dependency",
    "create_required_reviewer_session_dependency",
]
