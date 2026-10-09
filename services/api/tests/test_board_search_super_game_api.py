"""Super game markers in board search and approximate win (TASK-0935, D-535)."""

from __future__ import annotations

from collections.abc import Collection, Iterator
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from game_predictor_api.api.management_public_stakes import create_management_public_stake_router
from game_predictor_api.api.management_stakes import create_management_stake_router
from game_predictor_api.application.board_search import BoardSearchService
from game_predictor_api.application.board_search_approximate_win import (
    BoardSearchApproximateWinService,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.board_search import (
    BoardSearchAssetMode,
    BoardSearchQueryCell,
    BoardSearchResult,
    BoardSearchScope,
    BoardSearchScore,
)
from game_predictor_api.domain.super_game_markers import (
    SuperGameMarker,
    SuperGameMarkerKind,
    SuperGameMarkers,
    marker_for_position,
)
from game_predictor_api.domain.super_game_series import (
    RunVerification,
    SeriesCompleteness,
    SuperGameState,
)
from game_predictor_api.main import create_app
from game_predictor_api.schemas.board_search_approximate_win import (
    ApproximateWinResponse,
    apply_super_game_markers,
    to_approximate_win_response,
)
from game_predictor_api.storage.management_result_snapshots import expand_result, freeze_result
from test_board_search_approximate_win_api import (
    _GAME_ID,
    MemoryBoardSearchApproximateWinRepository,
    _configuration,
    _document,
)
from test_board_search_share_public_api import (
    BASE,
    PROXY,
    Harness,
    _forbidden_keys,
    _harness,
    _signed_in,
)

GAME_ID = _GAME_ID
SERIES_ID = UUID(int=0x5E81E5)
OTHER_SERIES_ID = UUID(int=0x5E81E6)


@dataclass(frozen=True)
class SeriesFixture:
    id: UUID
    trigger: int
    length: int
    symbol_code: str | None
    completeness: SeriesCompleteness = SeriesCompleteness.COMPLETE
    run_verification: RunVerification = RunVerification.VERIFIED


class MemoryMarkerSource:
    """The published generation in memory; the SQL twin is covered on PostgreSQL."""

    def __init__(
        self,
        series: tuple[SeriesFixture, ...] = (),
        *,
        state: SuperGameState | None = None,
    ) -> None:
        self._series = series
        self._state = state or SuperGameState(
            input_version=7, generation_input_version=7, has_super_game=True
        )
        self.calls: list[tuple[UUID, tuple[int, ...]]] = []

    def markers(self, game_id: UUID, positions: Collection[int]) -> SuperGameMarkers:
        self.calls.append((game_id, tuple(sorted(positions))))
        found: dict[int, SuperGameMarker] = {}
        if self._state.has_super_game:
            for position in positions:
                for series in self._series:
                    marker = marker_for_position(
                        position=position,
                        series_id=series.id,
                        trigger_sequence_number=series.trigger,
                        series_length=series.length,
                        super_symbol_code=series.symbol_code,
                        completeness=series.completeness,
                        run_verification=series.run_verification,
                    )
                    if marker is not None:
                        found[position] = marker
        return SuperGameMarkers(state=self._state, by_position=MappingProxyType(found))


class MemorySearchRepository:
    def __init__(self, sequence_numbers: tuple[int, ...]) -> None:
        self._sequence_numbers = sequence_numbers

    def search(
        self,
        *,
        game_id: UUID,
        query: tuple[BoardSearchQueryCell, ...],
        scope: BoardSearchScope,
        limit: int,
    ) -> tuple[BoardSearchResult, ...]:
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
                    unknown_count=0,
                ),
            )
            for sequence_number in self._sequence_numbers
        )


def _search_client(source: MemoryMarkerSource, sequence_numbers: tuple[int, ...]) -> TestClient:
    app = create_app(
        ApiSettings.from_environment(
            {"GAME_PREDICTOR_REMOTE_SELECTION_HOST_MAPPING_ENABLED": "false"}
        ),
        board_search_service_dependency=lambda: BoardSearchService(
            MemorySearchRepository(sequence_numbers), source
        ),
    )
    return TestClient(app)


def _range_client(source: MemoryMarkerSource) -> TestClient:
    repository = MemoryBoardSearchApproximateWinRepository(
        GAME_ID,
        sequence_length=300,
        configuration=_configuration(),
        documents=(
            _document(100, (1,) * 15),
            _document(105, (1,) * 15),
            _document(120, (1,) * 15),
            _document(150, (1,) * 15),
        ),
    )
    app = create_app(
        ApiSettings.from_environment(
            {"GAME_PREDICTOR_REMOTE_SELECTION_HOST_MAPPING_ENABLED": "false"}
        ),
        board_search_approximate_win_service_dependency=(
            lambda: BoardSearchApproximateWinService(repository, source)
        ),
    )
    return TestClient(app)


def _search(client: TestClient) -> dict[str, Any]:
    response = client.get(
        f"/api/v1/admin/games/{GAME_ID}/board-search", params={"cell": "0:A", "limit": "10"}
    )
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


def _range(client: TestClient) -> dict[str, Any]:
    response = client.get(
        f"/api/v1/admin/games/{GAME_ID}/board-search/approximate-win",
        params={"startSequenceNumber": 99, "spinCount": 60},
    )
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


SERIES = (SeriesFixture(SERIES_ID, 100, 10, "K"),)


def test_marker_covers_the_trigger_the_spins_and_the_last_spin_only() -> None:
    def marker(position: int) -> SuperGameMarker | None:
        return marker_for_position(
            position=position,
            series_id=SERIES_ID,
            trigger_sequence_number=100,
            series_length=10,
            super_symbol_code=None,
            completeness=SeriesCompleteness.COMPLETE,
            run_verification=RunVerification.UNVERIFIED,
        )

    assert marker(99) is None
    trigger = marker(100)
    assert trigger is not None
    assert (trigger.kind, trigger.spin_index) == (SuperGameMarkerKind.TRIGGER, None)
    first = marker(101)
    assert first is not None
    assert (first.kind, first.spin_index) == (SuperGameMarkerKind.IN_SERIES, 1)
    last = marker(110)
    assert last is not None
    assert last.spin_index == 10
    assert marker(111) is None


def test_search_marks_the_trigger_and_a_spin_of_the_series() -> None:
    source = MemoryMarkerSource(SERIES)
    with _search_client(source, (100, 105, 130)) as client:
        payload = _search(client)

    by_position = {item["sequenceNumber"]: item for item in payload["results"]}
    assert by_position[100]["superGame"] == {
        "kind": "trigger",
        "seriesId": str(SERIES_ID),
        "spinIndex": None,
        "seriesLength": 10,
        "superSymbolCode": "K",
        "completeness": "complete",
        "runVerification": "verified",
    }
    assert by_position[105]["superGame"]["kind"] == "in_series"
    assert by_position[105]["superGame"]["spinIndex"] == 5
    assert by_position[105]["superGame"]["seriesId"] == str(SERIES_ID)
    assert by_position[130]["superGame"] is None
    assert payload["superGameState"] == {
        "fresh": True,
        "inputVersion": 7,
        "generationInputVersion": 7,
    }
    assert source.calls == [(GAME_ID, (100, 105, 130))]


def test_an_undefined_super_symbol_is_null_and_an_incomplete_series_says_so() -> None:
    source = MemoryMarkerSource(
        (
            SeriesFixture(
                SERIES_ID,
                100,
                10,
                None,
                SeriesCompleteness.INCOMPLETE,
                RunVerification.UNVERIFIED,
            ),
        )
    )
    with _search_client(source, (103,)) as client:
        marker = _search(client)["results"][0]["superGame"]

    assert marker["superSymbolCode"] is None
    assert marker["completeness"] == "incomplete"
    assert marker["runVerification"] == "unverified"
    assert marker["spinIndex"] == 3


def test_a_new_trigger_before_the_job_shows_no_marker_but_a_stale_state() -> None:
    # Position 130 became a trigger after the last generation was derived.
    source = MemoryMarkerSource(
        SERIES,
        state=SuperGameState(input_version=9, generation_input_version=7, has_super_game=True),
    )
    with _search_client(source, (130, 105)) as client:
        payload = _search(client)

    by_position = {item["sequenceNumber"]: item for item in payload["results"]}
    assert by_position[130]["superGame"] is None
    # The last generation is still served for the positions it covers.
    assert by_position[105]["superGame"]["spinIndex"] == 5
    assert payload["superGameState"] == {
        "fresh": False,
        "inputVersion": 9,
        "generationInputVersion": 7,
    }


def test_a_game_without_a_super_game_kind_has_no_markers_and_is_fresh() -> None:
    source = MemoryMarkerSource(
        SERIES,
        state=SuperGameState(input_version=4, generation_input_version=None, has_super_game=False),
    )
    with _search_client(source, (100, 105)) as client:
        payload = _search(client)
    with _range_client(source) as client:
        win = _range(client)

    assert all(item["superGame"] is None for item in payload["results"])
    assert payload["superGameState"] == {
        "fresh": True,
        "inputVersion": 4,
        "generationInputVersion": None,
    }
    assert all(row["superGame"] is None for row in win["rows"])
    assert win["superGameState"]["fresh"] is True


def test_search_without_a_marker_source_is_fresh_and_unmarked() -> None:
    app = create_app(
        ApiSettings.from_environment(
            {"GAME_PREDICTOR_REMOTE_SELECTION_HOST_MAPPING_ENABLED": "false"}
        ),
        board_search_service_dependency=lambda: BoardSearchService(MemorySearchRepository((100,))),
    )
    with TestClient(app) as client:
        payload = _search(client)

    assert payload["results"][0]["superGame"] is None
    assert payload["superGameState"] == {
        "fresh": True,
        "inputVersion": 0,
        "generationInputVersion": None,
    }


def test_approximate_win_rows_carry_markers_and_the_state() -> None:
    source = MemoryMarkerSource(SERIES)
    with _range_client(source) as client:
        payload = _range(client)

    rows = {row["sequenceNumber"]: row for row in payload["rows"]}
    assert sorted(rows) == [100, 105, 120, 150]
    assert rows[100]["superGame"]["kind"] == "trigger"
    assert rows[100]["superGame"]["seriesId"] == str(SERIES_ID)
    assert rows[105]["superGame"]["kind"] == "in_series"
    assert rows[105]["superGame"]["spinIndex"] == 5
    assert rows[120]["superGame"] is None
    assert rows[150]["superGame"] is None
    assert payload["superGameState"] == {
        "fresh": True,
        "inputVersion": 7,
        "generationInputVersion": 7,
    }
    # One marker read covers every evaluated position (the per-position mode
    # projection of TASK-0936) and so also the winning rows.
    assert len(source.calls) == 1
    assert source.calls[0][0] == GAME_ID
    assert {100, 105, 120, 150} <= set(source.calls[0][1])


def test_approximate_win_with_a_stale_generation_warns_for_rows_without_markers() -> None:
    source = MemoryMarkerSource(
        SERIES,
        state=SuperGameState(input_version=3, generation_input_version=None, has_super_game=True),
    )
    with _range_client(source) as client:
        payload = _range(client)

    assert payload["superGameState"] == {
        "fresh": False,
        "inputVersion": 3,
        "generationInputVersion": None,
    }


def test_public_share_search_and_range_never_carry_the_series_identity(tmp_path: Path) -> None:
    markers = SuperGameMarkers(
        state=SuperGameState(input_version=2, generation_input_version=1, has_super_game=True),
        by_position=MappingProxyType(
            {
                11: marker_for_position(
                    position=11,
                    series_id=SERIES_ID,
                    trigger_sequence_number=10,
                    series_length=10,
                    super_symbol_code="K",
                    completeness=SeriesCompleteness.COMPLETE,
                    run_verification=RunVerification.VERIFIED,
                ),
                2: marker_for_position(
                    position=2,
                    series_id=SERIES_ID,
                    trigger_sequence_number=2,
                    series_length=10,
                    super_symbol_code=None,
                    completeness=SeriesCompleteness.COMPLETE,
                    run_verification=RunVerification.VERIFIED,
                ),
            }
        ),
    )
    harness: Harness = _harness(tmp_path, super_game=markers)
    with TestClient(harness.app, base_url="https://testserver") as client:
        _signed_in(client, harness, GAME_ID)
        search = client.get(f"{BASE}/search", params={"cell": "0:A"}, headers=PROXY)
        win = client.get(
            f"{BASE}/approximate-win",
            params={"startSequenceNumber": 1, "spinCount": 5},
            headers=PROXY,
        )

    assert search.status_code == 200, search.text
    found = {item["sequenceNumber"]: item for item in search.json()["results"]}
    assert found[11]["superGame"] == {
        "kind": "in_series",
        "spinIndex": 1,
        "seriesLength": 10,
        "superSymbolCode": "K",
        "completeness": "complete",
        "runVerification": "verified",
    }
    assert found[12]["superGame"] is None
    assert search.json()["superGameState"] == {
        "fresh": False,
        "inputVersion": 2,
        "generationInputVersion": 1,
    }
    assert win.status_code == 200, win.text
    body = win.json()
    row = next(item for item in body["rows"] if item["sequenceNumber"] == 2)
    assert row["superGame"] == {
        "kind": "trigger",
        "spinIndex": None,
        "seriesLength": 10,
        "superSymbolCode": None,
        "completeness": "complete",
        "runVerification": "verified",
    }
    assert body["superGameState"]["fresh"] is False
    assert _forbidden_keys(search.json()) == set()
    assert _forbidden_keys(body) == set()
    assert "seriesId" not in search.text and "seriesId" not in win.text


class _PreviewService:
    """A management service returning one live preview with a marker."""

    def __init__(self, response: ApproximateWinResponse) -> None:
        self._response = response

    def preview(self, machine_id: UUID, game_id: UUID, start: int, count: int) -> Any:
        return self._response


def _preview_response() -> ApproximateWinResponse:
    repository = MemoryBoardSearchApproximateWinRepository(
        GAME_ID,
        sequence_length=300,
        configuration=_configuration(),
        documents=(_document(100, (1,) * 15), _document(105, (1,) * 15)),
    )
    plain = to_approximate_win_response(
        BoardSearchApproximateWinService(repository).calculate(
            game_id=GAME_ID, start_sequence_number=99, requested_spin_count=10
        )
    )
    assert plain.super_game_state is None
    return apply_super_game_markers(plain, MemoryMarkerSource(SERIES).markers(GAME_ID, {100, 105}))


def test_management_preview_keeps_the_series_identity_only_for_the_admin_route() -> None:
    response = _preview_response()
    public = FastAPI()
    public.include_router(create_management_public_stake_router(lambda: _PreviewService(response)))
    admin = FastAPI()
    admin.include_router(create_management_stake_router(lambda: _PreviewService(response)))
    machine = uuid4()
    path = f"/machines/{machine}/game/{GAME_ID}/approximate-win"

    with TestClient(public) as client:
        public_body = client.get(
            f"/api/v1/management-public{path}",
            params={"startSequenceNumber": 99, "spinCount": 10},
        )
    with TestClient(admin) as client:
        admin_body = client.get(
            f"/api/v1/admin/management{path}",
            params={"startSequenceNumber": 99, "spinCount": 10},
        )

    assert public_body.status_code == 200, public_body.text
    assert admin_body.status_code == 200, admin_body.text
    public_rows = {row["sequenceNumber"]: row for row in public_body.json()["rows"]}
    admin_rows = {row["sequenceNumber"]: row for row in admin_body.json()["rows"]}
    assert public_rows[105]["superGame"]["spinIndex"] == 5
    assert "seriesId" not in public_body.text
    assert admin_rows[105]["superGame"]["seriesId"] == str(SERIES_ID)
    assert public_body.json()["superGameState"]["fresh"] is True


def test_frozen_management_results_ignore_markers_and_state() -> None:
    configuration = _configuration()
    marked = _preview_response()
    plain = marked.model_copy(
        update={
            "super_game_state": None,
            "rows": tuple(row.model_copy(update={"super_game": None}) for row in marked.rows),
        }
    )

    marked_digest, marked_payload, _ = freeze_result(marked, configuration, ("A",) * 15, "a" * 64)
    plain_digest, plain_payload, _ = freeze_result(plain, configuration, ("A",) * 15, "a" * 64)

    assert marked_digest == plain_digest
    assert marked_payload == plain_payload
    assert "superGameState" not in marked_payload["calculation"]  # type: ignore[operator]
    assert expand_result(marked_payload).super_game_state is None


@pytest.fixture
def _openapi() -> Iterator[dict[str, Any]]:
    app = create_app(
        ApiSettings.from_environment(
            {"GAME_PREDICTOR_REMOTE_SELECTION_HOST_MAPPING_ENABLED": "false"}
        )
    )
    yield app.openapi()


def test_openapi_exposes_the_series_identity_only_on_the_admin_marker(
    _openapi: dict[str, Any],
) -> None:
    schemas = _openapi["components"]["schemas"]
    assert "seriesId" in schemas["SuperGameMarkerResponse"]["properties"]
    assert "seriesId" not in schemas["SuperGamePublicMarkerResponse"]["properties"]
    public_result = schemas["BoardSearchSharePublicSearchResultResponse"]["properties"]
    assert "$ref" in str(public_result["superGame"])
    assert "SuperGamePublicMarkerResponse" in str(public_result["superGame"])
    assert "SuperGameMarkerResponse" in str(schemas["BoardSearchResultResponse"]["properties"])
