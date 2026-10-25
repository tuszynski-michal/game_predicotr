from game_predictor_api.application.board_search import BoardSearchService
from game_predictor_api.domain.board_search_pattern_identity import (
    search_pattern_fingerprint,
    search_pattern_key,
)
from game_predictor_api.domain.board_search_share_queries import sequence_search_query_request
from test_board_search_sequence_api import PATTERN, Repository
from test_board_search_share_public_api import (
    BASE,
    DETAIL_GAME_ID,
    PROXY,
    _forbidden_keys,
    _signed_in,
)
from test_board_search_share_public_api import client as _shared_client_fixture

shared_client = _shared_client_fixture


def test_public_sequence_is_logged_and_recursively_private(shared_client, monkeypatch):
    client, harness = shared_client
    session_id = _signed_in(client, harness, DETAIL_GAME_ID)
    service = BoardSearchService(Repository())
    monkeypatch.setattr(
        harness.search,
        "search_sequence_with_super_game",
        service.search_sequence_with_super_game,
        raising=False,
    )
    response = client.post(BASE + "/search", json={"patterns": [PATTERN, PATTERN]}, headers=PROXY)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert not _forbidden_keys(payload)
    assert "gameId" not in payload
    assert len(payload["results"][0]["boards"]) == 2
    entry = harness.log.entries[-1]
    assert entry["sessionId"] == session_id
    assert entry["request"]["version"] == 2
    assert entry["resultSummary"] == {
        "resultCount": 1,
        "patternCount": 2,
        "firstEndSequenceNumbers": [2],
    }
    assert payload["searchContextId"] == str(entry["id"])


def test_public_sequence_still_fails_closed_if_log_is_unavailable(shared_client, monkeypatch):
    client, harness = shared_client
    _signed_in(client, harness, DETAIL_GAME_ID)
    monkeypatch.setattr(
        harness.search,
        "search_sequence_with_super_game",
        BoardSearchService(Repository()).search_sequence_with_super_game,
        raising=False,
    )
    harness.log.fail = True
    response = client.post(BASE + "/search", json={"patterns": [PATTERN, PATTERN]}, headers=PROXY)
    assert response.status_code == 503
    assert response.json()["code"] == "BOARD_SEARCH_SHARE_QUERY_LOG_UNAVAILABLE"
    assert "results" not in response.json()


def test_ordered_pattern_identity_and_legacy_hashes_remain_distinct():
    from game_predictor_api.storage.board_search_share_correction_repository import (
        pattern_fingerprint,
    )

    def request(codes):
        return sequence_search_query_request(
            patterns=[[(0, code)] for code in codes], scope="all_searchable", limit=15
        )

    ab, ba, ac = [request(codes) for codes in [("A", "B"), ("B", "A"), ("A", "C")]]
    assert len({search_pattern_key(value) for value in (ab, ba, ac)}) == 3
    assert len({search_pattern_fingerprint(value) for value in (ab, ba, ac)}) == 3
    legacy = request(["A"])
    assert "version" not in legacy
    assert search_pattern_key(legacy) == '["0:A"]'
    assert search_pattern_fingerprint(legacy) == pattern_fingerprint(["0:A"])
    assert search_pattern_key({**ab, "limit": 99}) == search_pattern_key(ab)


def test_sequence_timeout_is_logged_with_its_stable_code(shared_client, monkeypatch):
    from game_predictor_api.domain.board_search_sequence import BoardSearchSequenceError

    client, harness = shared_client
    _signed_in(client, harness, DETAIL_GAME_ID)

    def timeout(**kwargs):
        raise BoardSearchSequenceError("BOARD_SEARCH_SEQUENCE_TIMEOUT", "Timed out.")

    monkeypatch.setattr(harness.search, "search_sequence_with_super_game", timeout, raising=False)
    response = client.post(BASE + "/search", json={"patterns": [PATTERN, PATTERN]}, headers=PROXY)
    assert response.status_code == 503
    assert response.json()["code"] == "BOARD_SEARCH_SEQUENCE_TIMEOUT"
    assert harness.log.entries[-1]["outcomeCode"] == "BOARD_SEARCH_SEQUENCE_TIMEOUT"
    assert "results" not in response.json()


def test_group_delete_and_replay_use_the_entire_ordered_sequence():
    from game_predictor_api.application.board_search_share_queries import (
        BoardSearchShareQueryLogService,
    )
    from game_predictor_api.domain.board_search_share_queries import BoardSearchShareQueryKind
    from test_board_search_share_query_log import SESSION, MemoryQueryRepository, _event

    def event(minute, codes):
        return _event(
            BoardSearchShareQueryKind.SEARCH,
            minute,
            request=sequence_search_query_request(
                patterns=[[(0, code)] for code in codes], scope="all_searchable", limit=15
            ),
        )

    ab1, ba, ac, ab2 = [
        event(i, codes)
        for i, codes in enumerate([("A", "B"), ("B", "A"), ("A", "C"), ("A", "B")], 1)
    ]
    repo = MemoryQueryRepository([ab1, ba, ac, ab2])
    service = BoardSearchShareQueryLogService(repo)
    page = service.list(
        session_id=SESSION, kind=BoardSearchShareQueryKind.SEARCH, group_by_pattern=True
    )
    assert len(page.entries) == 3
    assert page.entries[0].occurrence_times == (ab2.occurred_at, ab1.occurred_at)
    assert service.replay(ab2.id).search.request == ab2.request
    assert service.delete(ab2.id, whole_pattern=True) == 2
    assert {item.id for item in repo.events} == {ba.id, ac.id}
