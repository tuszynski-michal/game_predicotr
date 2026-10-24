"""Bound the actual streamed search body before FastAPI parses JSON."""

import re

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from game_predictor_api.domain.board_search_sequence import SEQUENCE_REQUEST_MAX_BYTES

_PATH = re.compile(r"^/api/v1/(?:admin/games/[^/]+/board-search|board-search-shares/search)$")


def is_sequence_search(scope: Scope) -> bool:
    return scope.get("method") == "POST" and bool(_PATH.fullmatch(scope.get("path", "")))


class BoardSearchSequenceBodyMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not is_sequence_search(scope):
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        status = 0
        code = "BOARD_SEARCH_SEQUENCE_INVALID"
        if scope.get("query_string"):
            status = 422
        elif (
            headers.get(b"content-type", b"").split(b";", 1)[0].strip().lower()
            != b"application/json"
        ):
            status, code = 415, "BOARD_SEARCH_SEQUENCE_CONTENT_TYPE_INVALID"
        try:
            declared = int(headers.get(b"content-length", b"0"))
            if declared < 0 or declared > SEQUENCE_REQUEST_MAX_BYTES:
                status, code = 413, "BOARD_SEARCH_SEQUENCE_BODY_TOO_LARGE"
        except ValueError:
            status, code = 413, "BOARD_SEARCH_SEQUENCE_BODY_TOO_LARGE"
        chunks = bytearray()
        while not status:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(chunks) + len(chunk) > SEQUENCE_REQUEST_MAX_BYTES:
                status, code = 413, "BOARD_SEARCH_SEQUENCE_BODY_TOO_LARGE"
                break
            chunks.extend(chunk)
            if not message.get("more_body", False):
                break
        if status:
            await JSONResponse(
                status_code=status,
                content={
                    "code": code,
                    "message": "Invalid sequence search request.",
                    "details": {},
                },
            )(scope, receive, send)
            return
        consumed = False

        async def replay() -> Message:
            nonlocal consumed
            if consumed:
                return await receive()
            consumed = True
            return {"type": "http.request", "body": bytes(chunks), "more_body": False}

        await self.app(scope, replay, send)
