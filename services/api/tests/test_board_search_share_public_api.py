"""Public board-search share surface (TASK-0767, D-471, D-472)."""

import hashlib
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from game_predictor_api.application.board_search_approximate_win import (
    BoardSearchApproximateWinService,
)
from game_predictor_api.application.board_search_board_detail import (
    BoardSearchBoardDetailService,
)
from game_predictor_api.application.board_search_share_access import (
    BoardSearchShareAccessService,
)
from game_predictor_api.application.board_search_share_queries import (
    BoardSearchShareRateLimiter,
    BoardSearchShareRequestKind,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.board_search import (
    BoardSearchAssetMode,
    BoardSearchResult,
    BoardSearchScore,
)
from game_predictor_api.domain.board_search_shares import (
    BOARD_SEARCH_SHARE_COOKIE_NAME,
    BOARD_SEARCH_SHARE_PROXY_HEADER,
    BOARD_SEARCH_SHARE_PROXY_INTENT,
)
from game_predictor_api.domain.catalog import CatalogNotFoundError, Symbol, SymbolStatus
from game_predictor_api.main import create_app
from game_predictor_api.storage.board_search_share_query_repository import (
    InMemoryBoardSearchShareQueryLog,
)
from game_predictor_api.storage.board_search_share_repository import (
    InMemoryBoardSearchShareRepository,
)
from test_board_search_approximate_win_api import (
    _GAME_ID as RANGE_GAME_ID,
)
from test_board_search_approximate_win_api import (
    MemoryBoardSearchApproximateWinRepository,
)
from test_board_search_approximate_win_api import (
    _configuration as range_configuration,
)
from test_board_search_approximate_win_api import (
    _document as range_document,
)
from test_board_search_board_detail_api import (
    _GAME_ID as DETAIL_GAME_ID,
)
from test_board_search_board_detail_api import (
    A,
    B,
    MemoryBoardDetailRepository,
)
from test_board_search_board_detail_api import (
    _configuration as detail_configuration,
)
from test_board_search_board_detail_api import (
    _document as detail_document,
)

NOW = datetime(2099, 9, 30, 10, 0, tzinfo=UTC)
BASE = "/api/v1/board-search-shares"
PROXY = {BOARD_SEARCH_SHARE_PROXY_HEADER: BOARD_SEARCH_SHARE_PROXY_INTENT}
SYMBOL_ID = UUID(int=301)
IMAGE_BYTES = b"\x89PNG\r\n\x1a\nsymbol"
IMAGE_SHA = hashlib.sha256(IMAGE_BYTES).hexdigest()
# Internal identities and storage details a recipient must never receive.
FORBIDDEN_KEYS = frozenset(
    {
        "reviewitemid",
        "recognizedboardid",
        "importjobid",
        "jobid",
        "cellreviewid",
        "cropsampleid",
        "cropchecksumsha256",
        "imagepath",
        "imagerelativepath",
        "relativepath",
        "hostbasepath",
        "accesstoken",
        "tokenhash",
        "codehash",
        "codesalt",
    }
)


def _forbidden_keys(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in FORBIDDEN_KEYS:
                found.add(str(key))
            found |= _forbidden_keys(item)
    elif isinstance(value, list):
        for item in value:
            found |= _forbidden_keys(item)
    return found


class FakeCatalog:
    def get_game(self, game_id: UUID) -> Any:
        @dataclass
        class Game:
            name: str

        return Game(name=f"Gra {str(game_id)[-4:]}")

    def list_symbols(self, game_id: UUID) -> list[Symbol]:
        return [
            Symbol(
                id=SYMBOL_ID,
                game_id=game_id,
                mobile_code=1,
                code="A",
                name="Wiśnia",
                image_path="data/symbol-references/a.png",
                is_wildcard=False,
                display_order=0,
                status=SymbolStatus.ACTIVE,
            ),
            Symbol(
                id=UUID(int=302),
                game_id=game_id,
                mobile_code=2,
                code="B",
                name="Bez obrazu",
                image_path=None,
                is_wildcard=False,
                display_order=1,
                status=SymbolStatus.ACTIVE,
            ),
        ]


class FakeReferences:
    def reference(self, game_id: UUID, symbol_id: UUID) -> Any:
        if symbol_id != SYMBOL_ID:
            raise CatalogNotFoundError("SYMBOL_REFERENCE_NOT_FOUND", "No reference.")

        @dataclass
        class Reference:
            image_relative_path: str
            image_checksum_sha256: str

        return Reference("data/symbol-references/a.png", IMAGE_SHA)


class FakeSearch:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def search(self, *, game_id: UUID, cells: Any, scope: Any, limit: int) -> Any:
        self.calls.append({"gameId": game_id, "cells": cells, "limit": limit})
        return tuple(
            BoardSearchResult(
                asset_mode=BoardSearchAssetMode.OPERATIONAL_REVIEW,
                review_item_id=uuid4(),
                recognized_board_id=uuid4(),
                import_job_id=uuid4(),
                sequence_number=sequence_number,
                status="pending",
                board_checksum_sha256="a" * 64,
                score=BoardSearchScore(
                    score=80.0,
                    exact_match_count=2,
                    alternative_match_count=0,
                    weighted_alternative_score=0.0,
                    mismatch_count=0,
                    unknown_count=1,
                ),
            )
            for sequence_number in (11, 12, 13, 14, 15, 16)
        )


class FakeView:
    def view(self, **_kwargs: object) -> Any:
        @dataclass
        class Asset:
            revision: str
            content: bytes
            media_type: str

        return Asset(revision="e" * 64, content=b"RIFFwebp", media_type="image/webp")


@dataclass
class Harness:
    app: FastAPI
    shares: BoardSearchShareAccessService
    log: InMemoryBoardSearchShareQueryLog
    search: FakeSearch
    clock: list[datetime]


def _harness(
    tmp_path: Path,
    *,
    limits: dict[BoardSearchShareRequestKind, int] | None = None,
) -> Harness:
    clock = [NOW]
    repository = InMemoryBoardSearchShareRepository()
    shares = BoardSearchShareAccessService(
        repository, readiness=lambda game_id: None, enabled=True, now=lambda: clock[0]
    )
    log = InMemoryBoardSearchShareQueryLog()
    search = FakeSearch()
    range_repository = MemoryBoardSearchApproximateWinRepository(
        RANGE_GAME_ID,
        configuration=range_configuration(),
        documents=(range_document(2, (1, 1, 1)),),
    )
    detail_repository = MemoryBoardDetailRepository(
        document=detail_document((A, A, A, A, A, B, B, B, A, A, A, B, A, B, A)),
        configuration=detail_configuration(),
    )
    image = tmp_path / "data" / "symbol-references" / "a.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(IMAGE_BYTES)
    app = create_app(
        ApiSettings(
            host="127.0.0.1",
            port=8000,
            admin_origin="http://127.0.0.1:3000",
            artifact_root=tmp_path,
        ),
        board_search_share_access_service_dependency=lambda: shares,
        board_search_share_query_log=log,
        board_search_share_rate_limiter=BoardSearchShareRateLimiter(limits_per_minute=limits),
        catalog_service_dependency=FakeCatalog,
        symbol_reference_service_dependency=FakeReferences,
        board_search_service_dependency=lambda: search,
        board_search_approximate_win_service_dependency=(
            lambda: BoardSearchApproximateWinService(range_repository)
        ),
        board_search_board_detail_service_dependency=(
            lambda: BoardSearchBoardDetailService(detail_repository)
        ),
        board_search_board_view_service_dependency=FakeView,
    )
    return Harness(app=app, shares=shares, log=log, search=search, clock=clock)


def _share(harness: Harness, game_id: UUID) -> tuple[UUID, str]:
    created = harness.shares.create(game_id=game_id, lifetime_minutes=60, label="Dla Ani")
    return created.session.session_id, created.access_code


@pytest.fixture
def client(tmp_path: Path) -> Iterator[tuple[TestClient, Harness]]:
    harness = _harness(tmp_path)
    with TestClient(harness.app, base_url="https://testserver") as test_client:
        yield test_client, harness


def _unlock(client: TestClient, session_id: UUID, code: str) -> Any:
    return client.post(
        f"{BASE}/sessions/{session_id}/unlock", json={"accessCode": code}, headers=PROXY
    )


def _keep_cookie(client: TestClient, response: Any) -> None:
    # The cookie is scoped to the Reviewer's `/board-search-api` path; the
    # proxy maps that path to these API routes, so the test sends it here.
    token = response.cookies.get(BOARD_SEARCH_SHARE_COOKIE_NAME)
    assert token
    client.cookies.set(BOARD_SEARCH_SHARE_COOKIE_NAME, token)


def _signed_in(client: TestClient, harness: Harness, game_id: UUID) -> UUID:
    session_id, code = _share(harness, game_id)
    response = _unlock(client, session_id, code)
    assert response.status_code == 200, response.text
    _keep_cookie(client, response)
    return session_id


def test_requests_outside_the_proxy_or_without_the_cookie_are_refused(
    client: tuple[TestClient, Harness],
) -> None:
    test_client, harness = client
    session_id, code = _share(harness, DETAIL_GAME_ID)
    no_proxy = test_client.post(f"{BASE}/sessions/{session_id}/unlock", json={"accessCode": code})
    assert no_proxy.status_code == 403
    assert no_proxy.json()["code"] == "BOARD_SEARCH_SHARE_PROXY_REQUIRED"
    no_cookie = test_client.get(f"{BASE}/context", headers=PROXY)
    assert no_cookie.status_code == 401
    assert no_cookie.json()["code"] == "BOARD_SEARCH_SHARE_TOKEN_REQUIRED"
    forged = test_client.get(
        f"{BASE}/context",
        headers={**PROXY, "Cookie": f"{BOARD_SEARCH_SHARE_COOKIE_NAME}=forged"},
    )
    assert forged.status_code == 401
    assert harness.log.entries == []


def test_unlock_sets_a_strict_cookie_and_returns_the_context_without_ids(
    client: tuple[TestClient, Harness],
) -> None:
    test_client, harness = client
    session_id, code = _share(harness, DETAIL_GAME_ID)
    wrong = _unlock(test_client, session_id, "AAAA-AAAA")
    assert wrong.status_code == 401
    response = _unlock(test_client, session_id, code)
    assert response.status_code == 200, response.text
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{BOARD_SEARCH_SHARE_COOKIE_NAME}=")
    for attribute in ("HttpOnly", "Secure", "SameSite=strict", "Path=/board-search-api"):
        assert attribute.lower() in cookie.lower()
    body = response.json()
    assert body["label"] == "Dla Ani"
    assert body["gameName"].startswith("Gra ")
    assert "gameId" not in body and "accessToken" not in body
    _keep_cookie(test_client, response)
    context = test_client.get(f"{BASE}/context", headers=PROXY)
    assert context.status_code == 200
    assert context.json()["sessionId"] == str(session_id)


def test_a_game_parameter_is_refused(client: tuple[TestClient, Harness]) -> None:
    test_client, harness = client
    _signed_in(test_client, harness, DETAIL_GAME_ID)
    response = test_client.get(
        f"{BASE}/search",
        params={"cell": "0:A", "gameId": str(RANGE_GAME_ID)},
        headers=PROXY,
    )
    assert response.status_code == 422
    assert response.json()["code"] == "BOARD_SEARCH_SHARE_PARAMETER_FORBIDDEN"
    assert harness.search.calls == []


def test_search_reads_only_the_session_game_and_logs_the_full_pattern(
    client: tuple[TestClient, Harness],
) -> None:
    test_client, harness = client
    session_id = _signed_in(test_client, harness, DETAIL_GAME_ID)
    response = test_client.get(
        f"{BASE}/search",
        params=[("cell", "3:?"), ("cell", "0:A"), ("scope", "approved_only"), ("limit", "6")],
        headers=PROXY,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert _forbidden_keys(body) == set()
    assert [item["sequenceNumber"] for item in body["results"]] == [11, 12, 13, 14, 15, 16]
    assert harness.search.calls[0]["gameId"] == DETAIL_GAME_ID
    assert harness.log.entries == [
        {
            "sessionId": session_id,
            "gameId": DETAIL_GAME_ID,
            "kind": "search",
            "request": {"cells": ["0:A", "3:?"], "scope": "approved_only", "limit": 6},
            "resultSummary": {"resultCount": 6, "firstSequenceNumbers": [11, 12, 13, 14, 15]},
            "outcomeCode": "ok",
            "occurredAt": harness.log.entries[0]["occurredAt"],
        }
    ]


def test_a_token_of_another_session_reads_only_its_own_game(tmp_path: Path) -> None:
    harness = _harness(tmp_path)
    other_game = UUID(int=999)
    with TestClient(harness.app, base_url="https://testserver") as first:
        _signed_in(first, harness, DETAIL_GAME_ID)
        with TestClient(harness.app, base_url="https://testserver") as second:
            _signed_in(second, harness, other_game)
            assert (
                second.get(f"{BASE}/search", params={"cell": "0:A"}, headers=PROXY).status_code
                == 200
            )
            assert (
                first.get(f"{BASE}/search", params={"cell": "0:A"}, headers=PROXY).status_code
                == 200
            )
    assert [call["gameId"] for call in harness.search.calls] == [other_game, DETAIL_GAME_ID]
    assert [entry["gameId"] for entry in harness.log.entries] == [other_game, DETAIL_GAME_ID]


def test_board_detail_has_no_cell_records_and_is_logged(
    client: tuple[TestClient, Harness],
) -> None:
    test_client, harness = client
    _signed_in(test_client, harness, DETAIL_GAME_ID)
    response = test_client.get(f"{BASE}/boards/42", headers=PROXY)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["cells"] is None
    assert body["matches"]
    assert _forbidden_keys(body) == set()
    assert harness.log.entries[-1]["kind"] == "board_detail"
    assert harness.log.entries[-1]["request"] == {"sequenceNumber": 42}
    assert harness.log.entries[-1]["resultSummary"] == {
        "payoutCredits": body["payoutCredits"],
        "documentStale": False,
    }


def test_a_failed_query_is_logged_with_its_error_code(
    client: tuple[TestClient, Harness],
) -> None:
    test_client, harness = client
    _signed_in(test_client, harness, DETAIL_GAME_ID)
    response = test_client.get(f"{BASE}/boards/7", headers=PROXY)
    assert response.status_code == 404
    assert len(harness.log.entries) == 1
    assert harness.log.entries[0]["outcomeCode"] == "BOARD_SEARCH_BOARD_NOT_FOUND"
    assert harness.log.entries[0]["resultSummary"] == {}


def test_approximate_win_is_logged_with_its_summary(tmp_path: Path) -> None:
    harness = _harness(tmp_path)
    with TestClient(harness.app, base_url="https://testserver") as test_client:
        _signed_in(test_client, harness, RANGE_GAME_ID)
        response = test_client.get(
            f"{BASE}/approximate-win",
            params={"startSequenceNumber": 1, "spinCount": 5},
            headers=PROXY,
        )
    assert response.status_code == 200, response.text
    assert _forbidden_keys(response.json()) == set()
    entry = harness.log.entries[-1]
    assert entry["kind"] == "approximate_win"
    assert entry["request"] == {"startSequenceNumber": 1, "spinCount": 5}
    summary = entry["resultSummary"]
    assert isinstance(summary, dict)
    assert summary["evaluatedSpinCount"] == 5
    assert set(summary) == {
        "evaluatedSpinCount",
        "recognizedPayoutCredits",
        "spinCostCredits",
        "balanceCredits",
        "rowCount",
    }


def test_a_query_log_failure_returns_no_data(client: tuple[TestClient, Harness]) -> None:
    test_client, harness = client
    _signed_in(test_client, harness, DETAIL_GAME_ID)
    harness.log.fail = True
    response = test_client.get(f"{BASE}/search", params={"cell": "0:A"}, headers=PROXY)
    assert response.status_code == 503
    assert response.json()["code"] == "BOARD_SEARCH_SHARE_QUERY_LOG_UNAVAILABLE"
    assert "results" not in response.text and "sequenceNumber" not in response.text


def test_revoking_the_link_stops_the_next_request(client: tuple[TestClient, Harness]) -> None:
    test_client, harness = client
    session_id = _signed_in(test_client, harness, DETAIL_GAME_ID)
    assert test_client.get(f"{BASE}/context", headers=PROXY).status_code == 200
    harness.shares.revoke(session_id)
    response = test_client.get(f"{BASE}/search", params={"cell": "0:A"}, headers=PROXY)
    assert response.status_code == 401
    assert response.json()["code"] == "BOARD_SEARCH_SHARE_TOKEN_INVALID"


def test_expired_access_is_refused(client: tuple[TestClient, Harness]) -> None:
    test_client, harness = client
    _signed_in(test_client, harness, DETAIL_GAME_ID)
    harness.clock[0] = NOW + timedelta(minutes=61)
    assert test_client.get(f"{BASE}/context", headers=PROXY).status_code == 401


def test_request_limits_answer_429(tmp_path: Path) -> None:
    harness = _harness(
        tmp_path,
        limits={
            BoardSearchShareRequestKind.JSON: 2,
            BoardSearchShareRequestKind.IMAGE: 1,
            BoardSearchShareRequestKind.APPROXIMATE_WIN: 1,
        },
    )
    with TestClient(harness.app, base_url="https://testserver") as test_client:
        _signed_in(test_client, harness, DETAIL_GAME_ID)
        assert test_client.get(f"{BASE}/context", headers=PROXY).status_code == 200
        assert test_client.get(f"{BASE}/context", headers=PROXY).status_code == 200
        limited = test_client.get(f"{BASE}/context", headers=PROXY)
        view = f"{BASE}/boards/42/view?expectedBoardChecksumSha256={'c' * 64}"
        assert test_client.get(view, headers=PROXY).status_code == 200
        limited_image = test_client.get(view, headers=PROXY)
    assert limited.status_code == 429
    assert limited.json()["code"] == "BOARD_SEARCH_SHARE_RATE_LIMITED"
    assert limited_image.status_code == 429


def test_one_range_calculation_at_a_time_per_session() -> None:
    limiter = BoardSearchShareRateLimiter()
    session_id = uuid4()
    with limiter.calculation_slot(session_id):
        with pytest.raises(Exception) as error, limiter.calculation_slot(session_id):
            pass
        assert getattr(error.value, "code", None) == "BOARD_SEARCH_SHARE_RATE_LIMITED"
        with limiter.calculation_slot(uuid4()):
            pass
    with limiter.calculation_slot(session_id):
        pass


def test_symbols_expose_image_revisions_not_paths_and_images_are_checksum_bound(
    client: tuple[TestClient, Harness],
) -> None:
    test_client, harness = client
    _signed_in(test_client, harness, DETAIL_GAME_ID)
    symbols = test_client.get(f"{BASE}/symbols", headers=PROXY)
    assert symbols.status_code == 200, symbols.text
    body = symbols.json()
    assert _forbidden_keys(body) == set()
    assert [item["imageRevision"] for item in body] == [IMAGE_SHA, None]
    image = test_client.get(
        f"{BASE}/symbols/{SYMBOL_ID}/image", params={"revision": IMAGE_SHA}, headers=PROXY
    )
    assert image.status_code == 200
    assert image.content == IMAGE_BYTES
    assert image.headers["cache-control"] == "private, immutable, max-age=86400"
    changed = test_client.get(
        f"{BASE}/symbols/{SYMBOL_ID}/image", params={"revision": "f" * 64}, headers=PROXY
    )
    assert changed.status_code == 409
    # Symbols and images are not data queries.
    assert harness.log.entries == []


def test_board_view_is_cacheable_only_with_its_revision(
    client: tuple[TestClient, Harness],
) -> None:
    test_client, harness = client
    _signed_in(test_client, harness, DETAIL_GAME_ID)
    base = f"{BASE}/boards/42/view?expectedBoardChecksumSha256={'c' * 64}"
    pinned = test_client.get(f"{base}&viewRevision={'e' * 64}", headers=PROXY)
    assert pinned.status_code == 200
    assert pinned.headers["cache-control"] == "private, immutable, max-age=86400"
    unpinned = test_client.get(base, headers=PROXY)
    assert unpinned.headers["cache-control"] == "private, no-cache"
    revalidated = test_client.get(base, headers={**PROXY, "If-None-Match": f'"{"e" * 64}"'})
    assert revalidated.status_code == 304
    assert harness.log.entries == []


def test_query_entries_are_validated_per_kind_and_size() -> None:
    from game_predictor_api.domain.board_search_share_queries import (
        BoardSearchShareQueryKind,
        build_board_search_share_query_entry,
        search_query_request,
    )

    entry = build_board_search_share_query_entry(
        kind=BoardSearchShareQueryKind.BOARD_DETAIL,
        request={"sequenceNumber": 4},
        result_summary=None,
        outcome_code="BOARD_SEARCH_BOARD_NOT_FOUND",
    )
    assert entry.result_summary == {}
    for kind, request, summary, outcome in (
        (BoardSearchShareQueryKind.SEARCH, {"sequenceNumber": 1}, None, "ok"),
        (BoardSearchShareQueryKind.BOARD_DETAIL, {"sequenceNumber": 1}, {"a": 1}, "FAILED"),
        (BoardSearchShareQueryKind.BOARD_DETAIL, {"sequenceNumber": 1}, None, " "),
        (
            BoardSearchShareQueryKind.SEARCH,
            {"cells": ["0:" + "x" * 5000], "scope": "all", "limit": 1},
            None,
            "ok",
        ),
        (BoardSearchShareQueryKind.BOARD_DETAIL, {"sequenceNumber": 1}, {"x": "y" * 3000}, "ok"),
    ):
        with pytest.raises(ValueError):
            build_board_search_share_query_entry(
                kind=kind, request=request, result_summary=summary, outcome_code=outcome
            )
    assert search_query_request(cells=[(5, None), (1, "A")], scope="all", limit=3) == {
        "cells": ["1:A", "5:?"],
        "scope": "all",
        "limit": 3,
    }


def test_an_oversized_pattern_is_refused_before_any_search_or_log(
    client: tuple[TestClient, Harness],
) -> None:
    test_client, harness = client
    _signed_in(test_client, harness, DETAIL_GAME_ID)
    long_code = test_client.get(f"{BASE}/search", params={"cell": "0:" + "x" * 4200}, headers=PROXY)
    too_many = test_client.get(
        f"{BASE}/search",
        params=[("cell", f"{index % 15}:A") for index in range(16)],
        headers=PROXY,
    )
    for response in (long_code, too_many):
        assert response.status_code == 422
        assert response.json()["code"] == "BOARD_SEARCH_SHARE_QUERY_INVALID"
    assert harness.search.calls == []
    assert harness.log.entries == []


def test_default_limits_and_range_calculation_limit(tmp_path: Path) -> None:
    from game_predictor_api.application.board_search_share_queries import (
        _DEFAULT_LIMITS_PER_MINUTE,
    )

    assert _DEFAULT_LIMITS_PER_MINUTE == {
        BoardSearchShareRequestKind.JSON: 120,
        BoardSearchShareRequestKind.IMAGE: 600,
        BoardSearchShareRequestKind.APPROXIMATE_WIN: 30,
    }
    harness = _harness(
        tmp_path,
        limits={
            BoardSearchShareRequestKind.JSON: 100,
            BoardSearchShareRequestKind.IMAGE: 100,
            BoardSearchShareRequestKind.APPROXIMATE_WIN: 1,
        },
    )
    with TestClient(harness.app, base_url="https://testserver") as test_client:
        _signed_in(test_client, harness, RANGE_GAME_ID)
        params = {"startSequenceNumber": 1, "spinCount": 5}
        first = test_client.get(f"{BASE}/approximate-win", params=params, headers=PROXY)
        second = test_client.get(f"{BASE}/approximate-win", params=params, headers=PROXY)
    assert first.status_code == 200, first.text
    assert second.status_code == 429
    assert second.json()["code"] == "BOARD_SEARCH_SHARE_RATE_LIMITED"
