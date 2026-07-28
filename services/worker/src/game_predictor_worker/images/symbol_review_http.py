"""Loopback-only HTTP adapter for the M6 bootstrap symbol review tool."""

from __future__ import annotations

import json
import re
import secrets
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Literal, cast
from urllib.parse import parse_qs, urlsplit

from .symbol_review import BootstrapSymbolReview, SymbolReviewError

_MAX_REQUEST_BYTES = 64 * 1024
_SAMPLE_ID_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
}


class SymbolReviewHttpError(ValueError):
    """Stable client-facing error raised by the local HTTP adapter."""

    def __init__(self, status: HTTPStatus, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


def is_loopback_host(host: str) -> bool:
    """Return whether a host is explicitly safe for the single-owner tool."""

    return host in {"127.0.0.1", "localhost"}


class ReviewHttpApplication:
    """Owns routing state without exposing arbitrary filesystem paths."""

    def __init__(
        self,
        review: BootstrapSymbolReview,
        static_root: Path,
        *,
        token: str | None = None,
    ) -> None:
        self.review = review
        self.static_root = static_root.resolve(strict=True)
        self.token = token or secrets.token_urlsafe(32)
        self.allowed_origin = ""

    def bind_origin(self, host: str, port: int) -> None:
        self.allowed_origin = f"http://{host}:{port}"

    def bootstrap(self) -> dict[str, object]:
        return {"token": self.token}

    def state(self, query: dict[str, list[str]]) -> dict[str, object]:
        status = _single_query_value(query, "status", "pending")
        offset = _integer_query_value(query, "offset", 0)
        limit = _integer_query_value(query, "limit", 24)
        return self.review.state(
            offset=offset,
            limit=limit,
            status=cast(Literal["all", "pending", "accepted", "rejected"], status),
        )

    def static_file(self, path: str) -> tuple[bytes, str]:
        value = _STATIC_FILES.get(path)
        if value is None:
            raise SymbolReviewHttpError(
                HTTPStatus.NOT_FOUND,
                "SYMBOL_REVIEW_HTTP_NOT_FOUND",
                "Resource not found.",
            )
        filename, content_type = value
        candidate = (self.static_root / filename).resolve(strict=True)
        if not candidate.is_relative_to(self.static_root):
            raise SymbolReviewHttpError(
                HTTPStatus.NOT_FOUND,
                "SYMBOL_REVIEW_HTTP_NOT_FOUND",
                "Resource not found.",
            )
        return candidate.read_bytes(), content_type

    def crop(self, sample_id: str) -> tuple[bytes, str]:
        if not _SAMPLE_ID_PATTERN.fullmatch(sample_id):
            raise SymbolReviewHttpError(
                HTTPStatus.NOT_FOUND,
                "SYMBOL_REVIEW_HTTP_NOT_FOUND",
                "Crop not found.",
            )
        path, checksum = self.review.resolve_crop(sample_id)
        return path.read_bytes(), checksum

    def post(self, path: str, body: dict[str, object]) -> dict[str, object]:
        if path == "/api/configure":
            symbol_codes = body.get("symbolCodes")
            if not isinstance(symbol_codes, list) or not all(
                isinstance(value, str) for value in symbol_codes
            ):
                raise _invalid_request("symbolCodes must be an array of strings.")
            configuration_changed = self.review.configure(
                game_code=_required_string(body, "gameCode"),
                reviewed_by=_required_string(body, "reviewedBy"),
                symbol_codes=symbol_codes,
            )
            return {"changed": configuration_changed}
        if path == "/api/decision":
            decision = body.get("decision")
            if decision not in {"accepted", "rejected"}:
                raise _invalid_request("decision must be accepted or rejected.")
            symbol_code = body.get("symbolCode")
            if symbol_code is not None and not isinstance(symbol_code, str):
                raise _invalid_request("symbolCode must be a string or null.")
            decision_count = self.review.decide(
                sample_id=_required_string(body, "sampleId"),
                decision=cast(Literal["accepted", "rejected"], decision),
                symbol_code=symbol_code,
                apply_to_identical=_optional_boolean(body, "applyToIdentical"),
            )
            return {"changed": decision_count}
        if path == "/api/clear":
            cleared_count = self.review.clear(
                sample_id=_required_string(body, "sampleId"),
                apply_to_identical=_optional_boolean(body, "applyToIdentical"),
            )
            return {"changed": cleared_count}
        raise SymbolReviewHttpError(
            HTTPStatus.NOT_FOUND,
            "SYMBOL_REVIEW_HTTP_NOT_FOUND",
            "Resource not found.",
        )


def create_review_server(
    review: BootstrapSymbolReview,
    static_root: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    token: str | None = None,
) -> ThreadingHTTPServer:
    """Create a loopback server. The caller owns serve/close lifecycle."""

    if not is_loopback_host(host):
        raise SymbolReviewHttpError(
            HTTPStatus.BAD_REQUEST,
            "SYMBOL_REVIEW_HTTP_NON_LOOPBACK",
            "The review server may bind only to localhost.",
        )
    application = ReviewHttpApplication(review, static_root, token=token)
    handler = _handler_factory(application)
    server = ThreadingHTTPServer((host, port), handler)
    bound_host, bound_port = server.server_address[:2]
    application.bind_origin(str(bound_host), int(bound_port))
    return server


def _handler_factory(
    application: ReviewHttpApplication,
) -> Callable[..., BaseHTTPRequestHandler]:
    class ReviewRequestHandler(BaseHTTPRequestHandler):
        server_version = "M6SymbolReview/1"

        def do_GET(self) -> None:  # noqa: N802
            try:
                parsed = urlsplit(self.path)
                if parsed.path == "/api/bootstrap":
                    self._send_json(HTTPStatus.OK, application.bootstrap())
                    return
                if parsed.path == "/api/state":
                    self._send_json(
                        HTTPStatus.OK,
                        application.state(parse_qs(parsed.query, keep_blank_values=True)),
                    )
                    return
                crop_prefix = "/api/crops/"
                if parsed.path.startswith(crop_prefix):
                    content, checksum = application.crop(parsed.path[len(crop_prefix) :])
                    self._send_bytes(
                        HTTPStatus.OK,
                        content,
                        "image/png",
                        cache_control="private, max-age=31536000, immutable",
                        extra_headers={"ETag": f'"{checksum}"'},
                    )
                    return
                content, content_type = application.static_file(parsed.path)
                self._send_bytes(
                    HTTPStatus.OK,
                    content,
                    content_type,
                    cache_control="no-store",
                )
            except Exception as error:  # boundary maps stable public errors
                self._send_error(error)

        def do_POST(self) -> None:  # noqa: N802
            try:
                self._authorize(application)
                parsed = urlsplit(self.path)
                result = application.post(parsed.path, self._json_body())
                self._send_json(HTTPStatus.OK, result)
            except Exception as error:  # boundary maps stable public errors
                self._send_error(error)

        def log_message(self, format: str, *args: object) -> None:
            return

        def _authorize(self, app: ReviewHttpApplication) -> None:
            if self.headers.get("X-Review-Token") != app.token:
                raise SymbolReviewHttpError(
                    HTTPStatus.FORBIDDEN,
                    "SYMBOL_REVIEW_HTTP_FORBIDDEN",
                    "Missing or invalid review token.",
                )
            origin = self.headers.get("Origin")
            if origin is not None and origin != app.allowed_origin:
                raise SymbolReviewHttpError(
                    HTTPStatus.FORBIDDEN,
                    "SYMBOL_REVIEW_HTTP_ORIGIN_REJECTED",
                    "Foreign browser origin is not allowed.",
                )
            content_type = self.headers.get_content_type()
            if content_type != "application/json":
                raise SymbolReviewHttpError(
                    HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                    "SYMBOL_REVIEW_HTTP_CONTENT_TYPE",
                    "Content-Type must be application/json.",
                )

        def _json_body(self) -> dict[str, object]:
            try:
                content_length = int(self.headers.get("Content-Length", ""))
            except ValueError as error:
                raise _invalid_request("Content-Length must be an integer.") from error
            if content_length <= 0 or content_length > _MAX_REQUEST_BYTES:
                raise SymbolReviewHttpError(
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                    "SYMBOL_REVIEW_HTTP_BODY_SIZE",
                    f"JSON body must contain 1-{_MAX_REQUEST_BYTES} bytes.",
                )
            try:
                value = json.loads(self.rfile.read(content_length))
            except (json.JSONDecodeError, UnicodeDecodeError) as error:
                raise _invalid_request("Body must contain valid UTF-8 JSON.") from error
            if not isinstance(value, dict):
                raise _invalid_request("JSON body must be an object.")
            return value

        def _send_error(self, error: Exception) -> None:
            if isinstance(error, SymbolReviewHttpError):
                status = error.status
                code = error.code
                message = str(error)
            elif isinstance(error, SymbolReviewError):
                status = HTTPStatus.BAD_REQUEST
                code = error.code
                message = str(error)
            elif isinstance(error, FileNotFoundError | OSError):
                status = HTTPStatus.NOT_FOUND
                code = "SYMBOL_REVIEW_HTTP_NOT_FOUND"
                message = "Resource not found."
            else:
                status = HTTPStatus.INTERNAL_SERVER_ERROR
                code = "SYMBOL_REVIEW_HTTP_INTERNAL"
                message = "The local review server failed."
            self._send_json(status, {"code": code, "message": message})

        def _send_json(self, status: HTTPStatus, value: object) -> None:
            content = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
            self._send_bytes(
                status,
                content,
                "application/json; charset=utf-8",
                cache_control="no-store",
            )

        def _send_bytes(
            self,
            status: HTTPStatus,
            content: bytes,
            content_type: str,
            *,
            cache_control: str,
            extra_headers: dict[str, str] | None = None,
        ) -> None:
            self.send_response(status)
            self.send_header("Cache-Control", cache_control)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Content-Type", content_type)
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; img-src 'self'; script-src 'self'; "
                "style-src 'self'; connect-src 'self'; object-src 'none'; "
                "base-uri 'none'; frame-ancestors 'none'",
            )
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            if extra_headers:
                for name, value in extra_headers.items():
                    self.send_header(name, value)
            self.end_headers()
            self.wfile.write(content)

    return ReviewRequestHandler


def _single_query_value(
    query: dict[str, list[str]],
    name: str,
    default: str,
) -> str:
    values = query.get(name)
    if values is None:
        return default
    if len(values) != 1:
        raise _invalid_request(f"{name} must occur once.")
    return values[0]


def _integer_query_value(
    query: dict[str, list[str]],
    name: str,
    default: int,
) -> int:
    value = _single_query_value(query, name, str(default))
    try:
        return int(value)
    except ValueError as error:
        raise _invalid_request(f"{name} must be an integer.") from error


def _required_string(body: dict[str, object], name: str) -> str:
    value = body.get(name)
    if not isinstance(value, str):
        raise _invalid_request(f"{name} must be a string.")
    return value


def _optional_boolean(body: dict[str, object], name: str) -> bool:
    value = body.get(name, False)
    if not isinstance(value, bool):
        raise _invalid_request(f"{name} must be a boolean.")
    return value


def _invalid_request(message: str) -> SymbolReviewHttpError:
    return SymbolReviewHttpError(
        HTTPStatus.BAD_REQUEST,
        "SYMBOL_REVIEW_HTTP_REQUEST_INVALID",
        message,
    )
