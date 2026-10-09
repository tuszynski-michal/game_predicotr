"""Use cases and HTTP contract of super game series (TASK-0933, D-535)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.application.super_game_series import (
    DerivationStart,
    GameSuperGameContext,
    PublicationOutcome,
    PublicationStatus,
    SeriesBoardDocument,
    SuperGameKindParameters,
    SuperGameSeriesDerivation,
    SuperGameSeriesFilter,
    SuperGameSeriesRecord,
    SuperGameSeriesService,
    SuperSymbolCandidate,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.super_game_series import (
    BoardTrigger,
    DerivedSuperGameSeries,
    RunVerification,
    SeriesCompleteness,
    SuperGameSeriesConflictError,
    SuperGameState,
)
from game_predictor_api.main import create_app

NOW = datetime(2026, 10, 9, tzinfo=UTC)


def _series(game_id: UUID, trigger: int, **changes: object) -> SuperGameSeriesRecord:
    record = SuperGameSeriesRecord(
        id=uuid4(),
        game_id=game_id,
        trigger_sequence_number=trigger,
        start_sequence_number=trigger + 1,
        length=10,
        retrigger_sequence_numbers=(),
        completeness=SeriesCompleteness.COMPLETE,
        run_verification=RunVerification.VERIFIED,
        super_symbol_id=None,
        defined_by=None,
        defined_at=None,
        revision=0,
        generation_id=uuid4(),
        updated_at=NOW,
    )
    return replace(record, **changes)  # type: ignore[arg-type]


class MemorySeriesRepository:
    def __init__(self, *, kind: str = "wild_super_spins") -> None:
        self.game_id = uuid4()
        self.kind = kind
        self.series: dict[UUID, SuperGameSeriesRecord] = {}
        self.symbols: dict[UUID, SuperSymbolCandidate] = {}
        self.documents: dict[int, SeriesBoardDocument] = {}
        self.input_version = 3
        self.generation_input_version: int | None = 3
        self.queued_job: UUID | None = None
        self.audit: list[tuple[UUID, UUID | None, int]] = []
        self.snapshots = 0

    def game_context(self, game_id: UUID) -> GameSuperGameContext | None:
        if game_id != self.game_id:
            return None
        return GameSuperGameContext(
            game_id=game_id,
            super_game_kind=self.kind,
            has_super_game=self.kind != "none",
            expected_layout_count=500_000,
        )

    def state(self, context: GameSuperGameContext) -> SuperGameState:
        return SuperGameState(
            input_version=self.input_version,
            generation_input_version=self.generation_input_version,
            has_super_game=context.has_super_game,
        )

    def list_series(
        self,
        game_id: UUID,
        *,
        filters: SuperGameSeriesFilter,
        after_trigger: int | None,
        limit: int,
    ) -> list[SuperGameSeriesRecord]:
        rows = sorted(self.series.values(), key=lambda item: item.trigger_sequence_number)
        return [
            row
            for row in rows
            if (after_trigger is None or row.trigger_sequence_number > after_trigger)
            and (filters.completeness is None or row.completeness is filters.completeness)
            and (
                filters.run_verification is None or row.run_verification is filters.run_verification
            )
            and (filters.defined is None or (row.super_symbol_id is not None) is filters.defined)
        ][:limit]

    def get_series(
        self, game_id: UUID, series_id: UUID, *, for_update: bool = False
    ) -> SuperGameSeriesRecord | None:
        return self.series.get(series_id)

    def symbol(self, game_id: UUID, symbol_id: UUID) -> SuperSymbolCandidate | None:
        return self.symbols.get(symbol_id)

    def define_super_symbol(
        self, series: SuperGameSeriesRecord, *, symbol_id: UUID | None, actor: str
    ) -> SuperGameSeriesRecord:
        updated = replace(
            series,
            super_symbol_id=symbol_id,
            revision=series.revision + 1,
            defined_by=actor,
            defined_at=NOW,
        )
        self.series[series.id] = updated
        self.audit.append((series.id, symbol_id, updated.revision))
        return updated

    def board_documents(
        self, game_id: UUID, sequence_numbers: Sequence[int]
    ) -> dict[int, SeriesBoardDocument]:
        return {n: self.documents[n] for n in sequence_numbers if n in self.documents}

    def begin_read_snapshot(self) -> None:
        self.snapshots += 1

    def enqueue_derive(self, game_id: UUID) -> tuple[UUID, bool]:
        if self.queued_job is not None:
            return self.queued_job, False
        self.queued_job = uuid4()
        return self.queued_job, True


def _client(repository: MemorySeriesRepository) -> TestClient:
    def dependency() -> SuperGameSeriesService:
        return SuperGameSeriesService(repository)  # type: ignore[arg-type]

    app = create_app(
        ApiSettings.from_environment({}),
        super_game_series_service_dependency=dependency,
    )
    return TestClient(app)


def _url(repository: MemorySeriesRepository, suffix: str = "") -> str:
    return f"/api/v1/admin/games/{repository.game_id}/super-game-series{suffix}"


def test_list_paginates_by_trigger_and_carries_state() -> None:
    repository = MemorySeriesRepository()
    for trigger in (300, 100, 200):
        record = _series(repository.game_id, trigger)
        repository.series[record.id] = record
    repository.input_version = 4
    client = _client(repository)

    first = client.get(_url(repository), params={"limit": 2})
    assert first.status_code == 200
    body = first.json()
    assert [item["triggerSequenceNumber"] for item in body["items"]] == [100, 200]
    assert body["items"][0]["endSequenceNumber"] == 110
    assert body["nextCursor"] == "200"
    assert body["superGameState"] == {
        "fresh": False,
        "inputVersion": 4,
        "generationInputVersion": 3,
    }
    second = client.get(_url(repository), params={"limit": 2, "cursor": body["nextCursor"]})
    assert [item["triggerSequenceNumber"] for item in second.json()["items"]] == [300]
    assert second.json()["nextCursor"] is None


def test_list_filters() -> None:
    repository = MemorySeriesRepository()
    symbol = uuid4()
    for record in (
        _series(repository.game_id, 10, completeness=SeriesCompleteness.INCOMPLETE),
        _series(repository.game_id, 50, run_verification=RunVerification.UNVERIFIED),
        _series(repository.game_id, 90, super_symbol_id=symbol, defined_by="x", defined_at=NOW),
    ):
        repository.series[record.id] = record
    client = _client(repository)

    def triggers(**params: str) -> list[int]:
        response = client.get(_url(repository), params=params)
        assert response.status_code == 200, response.text
        return [item["triggerSequenceNumber"] for item in response.json()["items"]]

    assert triggers(completeness="incomplete") == [10]
    assert triggers(runVerification="unverified") == [50]
    assert triggers(defined="true") == [90]
    assert triggers(defined="false") == [10, 50]
    assert client.get(_url(repository), params={"completeness": "x"}).status_code == 422


def test_game_without_super_game_lists_nothing_and_is_fresh() -> None:
    repository = MemorySeriesRepository(kind="none")
    record = _series(repository.game_id, 10)
    repository.series[record.id] = record
    repository.generation_input_version = None
    client = _client(repository)
    body = client.get(_url(repository)).json()
    assert body["items"] == [] and body["superGameKind"] == "none"
    assert body["superGameState"]["fresh"] is True
    assert client.get(_url(repository, f"/{record.id}/boards")).status_code == 404


def test_boards_cover_trigger_to_last_spin_and_mark_missing() -> None:
    repository = MemorySeriesRepository()
    record = _series(repository.game_id, 100, retrigger_sequence_numbers=(105,), length=20)
    repository.series[record.id] = record
    for position in range(100, 121):
        if position == 103:
            continue
        repository.documents[position] = SeriesBoardDocument(
            sequence_number=position,
            asset_mode="operational_review",
            review_item_id=uuid4(),
            recognized_board_id=uuid4(),
            import_job_id=uuid4(),
            status="pending",
            board_checksum_sha256="a" * 64,
        )
    body = _client(repository).get(_url(repository, f"/{record.id}/boards")).json()
    boards = body["boards"]
    assert [board["sequenceNumber"] for board in boards] == list(range(100, 121))
    assert boards[0]["role"] == "trigger" and boards[0]["spinIndex"] is None
    assert boards[5]["role"] == "retrigger" and boards[5]["spinIndex"] == 5
    missing = boards[3]
    assert missing["missing"] is True and missing["boardChecksumSha256"] is None
    assert boards[4]["missing"] is False and boards[4]["assetMode"] == "operational_review"
    assert body["series"]["endSequenceNumber"] == 120
    assert repository.snapshots == 1  # audit P0-5: one read snapshot per request


def test_super_symbol_cas_and_validation() -> None:
    repository = MemorySeriesRepository()
    record = _series(repository.game_id, 100)
    repository.series[record.id] = record
    ordinary, wild, trigger = uuid4(), uuid4(), uuid4()
    repository.symbols[ordinary] = SuperSymbolCandidate(ordinary, False, None, "active")
    repository.symbols[wild] = SuperSymbolCandidate(wild, True, None, "active")
    repository.symbols[trigger] = SuperSymbolCandidate(trigger, False, 3, "active")
    client = _client(repository)
    url = _url(repository, f"/{record.id}/super-symbol")

    saved = client.put(url, json={"symbolId": str(ordinary), "expectedRevision": 0})
    assert saved.status_code == 200, saved.text
    assert saved.json()["revision"] == 1 and saved.json()["superSymbolId"] == str(ordinary)
    assert saved.json()["definedBy"] == "local-admin"

    stale = client.put(url, json={"symbolId": None, "expectedRevision": 0})
    assert stale.status_code == 409
    assert stale.json()["code"] == "SUPER_GAME_SERIES_REVISION_CONFLICT"
    assert repository.series[record.id].super_symbol_id == ordinary
    assert len(repository.audit) == 1

    for symbol_id, code in (
        (wild, "SUPER_SYMBOL_NOT_ORDINARY"),
        (trigger, "SUPER_SYMBOL_NOT_ORDINARY"),
        (uuid4(), "SUPER_SYMBOL_NOT_FOUND"),
    ):
        rejected = client.put(url, json={"symbolId": str(symbol_id), "expectedRevision": 1})
        assert rejected.status_code == 422 and rejected.json()["code"] == code

    cleared = client.put(url, json={"symbolId": None, "expectedRevision": 1})
    assert cleared.status_code == 200 and cleared.json()["superSymbolId"] is None
    assert (
        client.put(
            _url(repository, f"/{uuid4()}/super-symbol"),
            json={"symbolId": None, "expectedRevision": 0},
        ).status_code
        == 404
    )


def test_derive_request_is_deduplicated_per_game() -> None:
    repository = MemorySeriesRepository()
    client = _client(repository)
    first = client.post(_url(repository, "/derive"))
    second = client.post(_url(repository, "/derive"))
    assert first.status_code == 202 and second.status_code == 202
    assert first.json()["deduplicated"] is False
    assert second.json() | {"deduplicated": False} == first.json()
    assert client.get(_url(repository, "/state")).json()["fresh"] is True
    assert client.get(f"/api/v1/admin/games/{uuid4()}/super-game-series/state").status_code == 404


class RecordingStore:
    def __init__(self, *, kind: str = "wild_super_spins", reject: bool = False) -> None:
        self.kind = kind
        self.reject = reject
        self.read_ranges: list[tuple[int, int]] = []
        self.written: list[list[DerivedSuperGameSeries]] = []
        self.published = 0
        self.boards = {100: True, 105: False, 300: True, 990: True}

    def begin_generation(self, game_id: UUID) -> DerivationStart:
        length = 10 if self.kind != "none" else 0
        return DerivationStart(
            game_id=game_id,
            generation_id=uuid4(),
            input_version=7,
            expected_layout_count=1_000,
            kind=SuperGameKindParameters(self.kind, length, length),
            trigger_thresholds={uuid4(): 3},
            discarded_generation_rows=0,
        )

    def next_trigger_candidate(
        self, start: DerivationStart, *, after_sequence_number: int
    ) -> int | None:
        return min((p for p in self.boards if p > after_sequence_number), default=None)

    def read_trigger_boards(
        self, start: DerivationStart, *, after_sequence_number: int, until_sequence_number: int
    ) -> list[BoardTrigger]:
        self.read_ranges.append((after_sequence_number, until_sequence_number))
        return [
            BoardTrigger(sequence_number=position, human_verified=verified)
            for position, verified in sorted(self.boards.items())
            if after_sequence_number < position <= until_sequence_number
        ]

    def last_known_sequence_number(self, start: DerivationStart, *, window: int) -> int | None:
        return 995

    def write_generation_rows(
        self, start: DerivationStart, rows: Sequence[DerivedSuperGameSeries]
    ) -> None:
        self.written.append(list(rows))

    def publish_generation(self, start: DerivationStart, *, actor: str) -> PublicationOutcome:
        self.published += 1
        if self.reject:
            return PublicationOutcome(PublicationStatus.REJECTED, 8, rerun_job_id=uuid4())
        return PublicationOutcome(PublicationStatus.PUBLISHED, 7, inserted=3)


def test_derivation_reads_in_position_batches_and_writes_in_row_batches() -> None:
    store = RecordingStore()
    progress: list[tuple[int, int, int]] = []
    report = SuperGameSeriesDerivation(store, position_batch_size=400, write_batch_size=1).derive(
        uuid4(), progress=lambda *values: progress.append(values)
    )
    # Empty stretches are skipped: each window starts at the next candidate.
    assert store.read_ranges == [(99, 499), (989, 1_000)]
    assert [len(batch) for batch in store.written] == [1, 1, 1]
    triggers = [row.trigger_sequence_number for batch in store.written for row in batch]
    assert triggers == [100, 300, 990]
    assert store.written[0][0].run_verification is RunVerification.UNVERIFIED
    assert store.written[-1][0].completeness is SeriesCompleteness.INCOMPLETE
    assert report.status is PublicationStatus.PUBLISHED and report.series_count == 3
    assert progress[-1][:2] == (1_000, 1_000)


def test_derivation_without_super_game_publishes_an_empty_generation() -> None:
    store = RecordingStore(kind="none")
    report = SuperGameSeriesDerivation(store).derive(uuid4())
    assert store.read_ranges == [] and store.written == [] and store.published == 1
    assert report.series_count == 0


def test_rejected_candidate_is_reported() -> None:
    report = SuperGameSeriesDerivation(RecordingStore(reject=True)).derive(uuid4())
    assert report.status is PublicationStatus.REJECTED
    assert report.expected_input_version == 7 and report.current_input_version == 8
    assert report.rerun_job_id is not None


def test_service_rejects_bad_cursor_and_limit() -> None:
    repository = MemorySeriesRepository()
    service = SuperGameSeriesService(repository)  # type: ignore[arg-type]
    with pytest.raises(Exception, match="cursor"):
        service.list(repository.game_id, cursor="abc")
    with pytest.raises(Exception, match="limit"):
        service.list(repository.game_id, limit=0)
    record = _series(repository.game_id, 5, revision=2)
    repository.series[record.id] = record
    with pytest.raises(SuperGameSeriesConflictError):
        service.set_super_symbol(
            repository.game_id, record.id, symbol_id=None, expected_revision=1, actor="a"
        )
