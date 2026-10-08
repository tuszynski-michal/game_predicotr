from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from game_predictor_api.application.board_search_share_access import (
    BoardSearchShareAccessService,
    assert_board_search_share_ready,
)
from game_predictor_api.domain.board_search import BoardSearchError
from game_predictor_api.domain.board_search_shares import (
    BoardSearchShareAuthenticationError,
    BoardSearchShareConflictError,
    BoardSearchShareError,
    BoardSearchShareNotFoundError,
    BoardSearchShareStatus,
    BoardSearchShareUnavailableError,
)
from game_predictor_api.storage.board_search_share_repository import (
    InMemoryBoardSearchShareRepository,
    validate_board_search_share_audit_payload,
)

GAME_ID = UUID(int=7)
START = datetime(2099, 9, 30, 10, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now


def _service(
    *,
    enabled: bool = True,
    readiness_error: Exception | None = None,
) -> tuple[BoardSearchShareAccessService, InMemoryBoardSearchShareRepository, Clock, list[UUID]]:
    repository = InMemoryBoardSearchShareRepository()
    clock = Clock()
    checked: list[UUID] = []

    def readiness(game_id: UUID) -> None:
        checked.append(game_id)
        if readiness_error is not None:
            raise readiness_error

    service = BoardSearchShareAccessService(
        repository, readiness=readiness, enabled=enabled, now=clock
    )
    return service, repository, clock, checked


def test_create_stores_only_hashes_and_returns_the_code_once() -> None:
    service, repository, _clock, checked = _service()
    created = service.create(game_id=GAME_ID, lifetime_minutes=480, label="  Dla  Ani ")

    assert checked == [GAME_ID]
    record = repository.records[created.session.session_id]
    assert record.label == "Dla Ani"
    assert created.access_code not in repr(record)
    assert len(record.code_hash) == 32 and len(record.code_salt) == 16
    assert record.token_hash is None
    assert record.expires_at == START + timedelta(hours=8)
    assert created.session.status is BoardSearchShareStatus.ACTIVE
    assert repository.audit_events == [
        {
            "sessionId": record.id,
            "eventType": "created",
            "outcomeCode": "BOARD_SEARCH_SHARE_CREATED",
            "payload": {"lifetimeMinutes": 480},
            "createdAt": START,
        }
    ]
    # The list never carries the code or hashes.
    listed = service.list_sessions()
    assert [view.session_id for view in listed] == [record.id]
    assert not hasattr(listed[0], "code_hash")


@pytest.mark.parametrize("minutes", [4, 4321, 0, -5])
def test_lifetime_outside_5_minutes_to_72_hours_is_rejected(minutes: int) -> None:
    service, repository, _clock, _checked = _service()
    with pytest.raises(BoardSearchShareError) as error:
        service.create(game_id=GAME_ID, lifetime_minutes=minutes, label=None)
    assert error.value.code == "BOARD_SEARCH_SHARE_LIFETIME_INVALID"
    assert repository.records == {}


def test_label_longer_than_100_characters_is_rejected_and_blank_means_none() -> None:
    service, _repository, _clock, _checked = _service()
    with pytest.raises(BoardSearchShareError) as error:
        service.create(game_id=GAME_ID, lifetime_minutes=60, label="x" * 101)
    assert error.value.code == "BOARD_SEARCH_SHARE_LABEL_INVALID"
    created = service.create(game_id=GAME_ID, lifetime_minutes=60, label="   ")
    assert created.session.label is None


def test_a_game_that_is_not_ready_gets_no_link() -> None:
    service, repository, _clock, _checked = _service(
        readiness_error=BoardSearchError(
            "APPROXIMATE_WIN_RULES_NOT_PUBLISHED", "No published rules."
        )
    )
    with pytest.raises(BoardSearchError) as error:
        service.assert_can_create(game_id=GAME_ID, lifetime_minutes=60, label=None)
    assert error.value.code == "APPROXIMATE_WIN_RULES_NOT_PUBLISHED"
    with pytest.raises(BoardSearchError):
        service.create(game_id=GAME_ID, lifetime_minutes=60, label=None)
    assert repository.records == {}


def test_sixth_active_session_conflicts_but_ended_sessions_do_not_count() -> None:
    service, _repository, clock, _checked = _service()
    sessions = [service.create(game_id=GAME_ID, lifetime_minutes=60, label=None) for _ in range(5)]
    with pytest.raises(BoardSearchShareConflictError) as error:
        service.assert_can_create(game_id=GAME_ID, lifetime_minutes=60, label=None)
    assert error.value.code == "BOARD_SEARCH_SHARE_ACTIVE_LIMIT"
    with pytest.raises(BoardSearchShareConflictError):
        service.create(game_id=GAME_ID, lifetime_minutes=60, label=None)

    service.revoke(sessions[0].session.session_id)
    service.create(game_id=GAME_ID, lifetime_minutes=5, label=None)
    clock.now += timedelta(minutes=6)
    # The 5-minute session expired: a new one fits again.
    service.create(game_id=GAME_ID, lifetime_minutes=60, label=None)


def test_unlock_rotates_the_token_and_only_the_latest_token_authenticates() -> None:
    service, repository, clock, _checked = _service()
    created = service.create(game_id=GAME_ID, lifetime_minutes=60, label=None)
    session_id = created.session.session_id

    first = service.unlock(session_id=session_id, access_code=created.access_code.lower())
    assert first.context.game_id == GAME_ID
    assert service.authenticate(first.access_token).session_id == session_id

    clock.now += timedelta(minutes=1)
    second = service.unlock(session_id=session_id, access_code=created.access_code)
    assert second.access_token != first.access_token
    assert service.authenticate(second.access_token).game_id == GAME_ID
    with pytest.raises(BoardSearchShareAuthenticationError) as error:
        service.authenticate(first.access_token)
    assert error.value.code == "BOARD_SEARCH_SHARE_TOKEN_INVALID"
    assert repository.records[session_id].last_unlocked_at == START + timedelta(minutes=1)


def test_five_wrong_codes_lock_the_session_and_clear_its_token() -> None:
    service, repository, _clock, _checked = _service()
    created = service.create(game_id=GAME_ID, lifetime_minutes=60, label=None)
    session_id = created.session.session_id
    unlocked = service.unlock(session_id=session_id, access_code=created.access_code)

    for attempt in range(1, 5):
        with pytest.raises(BoardSearchShareAuthenticationError) as error:
            service.unlock(session_id=session_id, access_code="AAAA-AAAA")
        assert error.value.code == "BOARD_SEARCH_SHARE_CODE_INVALID"
        assert repository.records[session_id].failed_attempts == attempt
    with pytest.raises(BoardSearchShareAuthenticationError) as error:
        service.unlock(session_id=session_id, access_code="AAAA-AAAA")
    assert error.value.code == "BOARD_SEARCH_SHARE_LOCKED"

    record = repository.records[session_id]
    assert record.locked_at is not None and record.token_hash is None
    with pytest.raises(BoardSearchShareAuthenticationError):
        service.authenticate(unlocked.access_token)
    # Even the right code no longer opens a locked session.
    with pytest.raises(BoardSearchShareAuthenticationError) as error:
        service.unlock(session_id=session_id, access_code=created.access_code)
    assert error.value.code == "BOARD_SEARCH_SHARE_LOCKED"
    assert service.list_sessions()[0].status is BoardSearchShareStatus.LOCKED
    assert [event["eventType"] for event in repository.audit_events] == [
        "created",
        "unlocked",
        "unlock_failed",
        "unlock_failed",
        "unlock_failed",
        "unlock_failed",
        "locked",
    ]


def test_a_correct_code_resets_the_failed_attempt_counter() -> None:
    service, repository, _clock, _checked = _service()
    created = service.create(game_id=GAME_ID, lifetime_minutes=60, label=None)
    session_id = created.session.session_id
    for _ in range(4):
        with pytest.raises(BoardSearchShareAuthenticationError):
            service.unlock(session_id=session_id, access_code="AAAA-AAAA")
    service.unlock(session_id=session_id, access_code=created.access_code)
    assert repository.records[session_id].failed_attempts == 0


def test_unlock_and_tokens_stop_at_expiry() -> None:
    service, _repository, clock, _checked = _service()
    created = service.create(game_id=GAME_ID, lifetime_minutes=60, label=None)
    session_id = created.session.session_id
    unlocked = service.unlock(session_id=session_id, access_code=created.access_code)

    clock.now = START + timedelta(minutes=60)
    with pytest.raises(BoardSearchShareAuthenticationError):
        service.authenticate(unlocked.access_token)
    with pytest.raises(BoardSearchShareNotFoundError) as error:
        service.unlock(session_id=session_id, access_code=created.access_code)
    assert error.value.code == "BOARD_SEARCH_SHARE_NOT_FOUND"
    assert service.list_sessions()[0].status is BoardSearchShareStatus.EXPIRED


def test_revoke_clears_the_token_is_idempotent_and_blocks_unlock() -> None:
    service, repository, _clock, _checked = _service()
    created = service.create(game_id=GAME_ID, lifetime_minutes=60, label=None)
    session_id = created.session.session_id
    unlocked = service.unlock(session_id=session_id, access_code=created.access_code)

    revoked = service.revoke(session_id)
    assert revoked.status is BoardSearchShareStatus.REVOKED
    assert repository.records[session_id].token_hash is None
    assert service.revoke(session_id).revoked_at == revoked.revoked_at
    with pytest.raises(BoardSearchShareAuthenticationError):
        service.authenticate(unlocked.access_token)
    with pytest.raises(BoardSearchShareAuthenticationError) as error:
        service.unlock(session_id=session_id, access_code=created.access_code)
    assert error.value.code == "BOARD_SEARCH_SHARE_REVOKED"
    assert [event["eventType"] for event in repository.audit_events].count("revoked") == 1
    with pytest.raises(BoardSearchShareNotFoundError):
        service.revoke(uuid4())


def test_disabled_sharing_blocks_create_unlock_and_access_but_not_revoke() -> None:
    enabled, repository, _clock, _checked = _service()
    created = enabled.create(game_id=GAME_ID, lifetime_minutes=60, label=None)
    unlocked = enabled.unlock(
        session_id=created.session.session_id, access_code=created.access_code
    )
    disabled = BoardSearchShareAccessService(
        repository, readiness=lambda _game_id: None, enabled=False, now=lambda: START
    )
    for action in (
        lambda: disabled.create(game_id=GAME_ID, lifetime_minutes=60, label=None),
        lambda: disabled.unlock(
            session_id=created.session.session_id, access_code=created.access_code
        ),
        lambda: disabled.authenticate(unlocked.access_token),
    ):
        with pytest.raises(BoardSearchShareUnavailableError) as error:
            action()
        assert error.value.code == "BOARD_SEARCH_SHARE_DISABLED"
    assert disabled.revoke(created.session.session_id).status is BoardSearchShareStatus.REVOKED
    assert len(disabled.list_sessions()) == 1


def test_list_filters_by_game_and_orders_newest_first() -> None:
    service, _repository, clock, _checked = _service()
    first = service.create(game_id=GAME_ID, lifetime_minutes=60, label="a")
    clock.now += timedelta(seconds=1)
    other = service.create(game_id=UUID(int=8), lifetime_minutes=60, label="b")
    clock.now += timedelta(seconds=1)
    last = service.create(game_id=GAME_ID, lifetime_minutes=60, label="c")

    assert [view.session_id for view in service.list_sessions(game_id=GAME_ID)] == [
        last.session.session_id,
        first.session.session_id,
    ]
    assert len(service.list_sessions()) == 3
    assert other.session.game_id == UUID(int=8)
    with pytest.raises(BoardSearchShareError) as error:
        service.list_sessions(limit=101)
    assert error.value.code == "BOARD_SEARCH_SHARE_LIST_LIMIT_INVALID"


def test_audit_payload_rejects_secret_looking_keys() -> None:
    validate_board_search_share_audit_payload({"failedAttempts": 2, "lifetimeMinutes": 60})
    for key in ("accessCode", "token", "codeHash", "salt"):
        with pytest.raises(ValueError):
            validate_board_search_share_audit_payload({key: "x"})
    with pytest.raises(ValueError):
        validate_board_search_share_audit_payload({"nested": {"a": 1}})


class ReadinessRepository:
    def __init__(self, *, rules: object | None, error: BoardSearchError | None = None) -> None:
        self._rules = rules
        self._error = error
        self.ranges: list[tuple[int, int]] = []

    def range_documents(
        self, *, game_id: UUID, first_sequence_number: int, last_sequence_number: int
    ) -> tuple[object, tuple[object, ...]]:
        self.ranges.append((first_sequence_number, last_sequence_number))
        if self._error is not None:
            raise self._error
        return object(), ()

    def latest_published_rules(self, game_id: UUID) -> object | None:
        return self._rules

    def game_sequence_length(self, game_id: UUID) -> int:
        return 0


def test_readiness_needs_a_ready_search_source_and_published_rules() -> None:
    ready = ReadinessRepository(rules=object())
    assert_board_search_share_ready(ready, GAME_ID)  # type: ignore[arg-type]
    assert ready.ranges == [(1, 0)]

    with pytest.raises(BoardSearchError) as error:
        assert_board_search_share_ready(
            ReadinessRepository(  # type: ignore[arg-type]
                rules=object(),
                error=BoardSearchError("BOARD_SEARCH_PROJECTION_INCOMPLETE", "Not ready."),
            ),
            GAME_ID,
        )
    assert error.value.code == "BOARD_SEARCH_PROJECTION_INCOMPLETE"
    with pytest.raises(BoardSearchError) as error:
        assert_board_search_share_ready(ReadinessRepository(rules=None), GAME_ID)  # type: ignore[arg-type]
    assert error.value.code == "APPROXIMATE_WIN_RULES_NOT_PUBLISHED"
