"""TASK-0814: bulk refresh of stale board-search documents."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import UUID, uuid4

import pytest
from game_predictor_api.application.board_search_board_detail import (
    BoardSearchStaleDocumentRefresh,
)
from game_predictor_api.domain.board_search import BoardSearchAssetMode
from game_predictor_api.domain.board_search_board_detail import (
    BoardSearchBoardDocument,
    BoardSearchBoardViewSource,
)

GAME_ID = UUID("bfc4f949-5c14-4850-b02a-db99610bcfa5")


def _document(sequence_number: int, checksum: str) -> BoardSearchBoardDocument:
    return BoardSearchBoardDocument(
        sequence_number=sequence_number,
        status="pending",
        board_checksum_sha256=checksum,
        asset_mode=BoardSearchAssetMode.OPERATIONAL_REVIEW,
        review_item_id=uuid4(),
        mobile_codes=(None,) * 15,
    )


class _Repository:
    """Documents by position plus each board's current identity checksum.

    `refresh_board_document` rewrites the document with the current checksum,
    removes it for positions in `removes`, and leaves positions in `sticks`
    unchanged (a refresh that cannot catch up).
    """

    def __init__(
        self,
        current: dict[int, str],
        documents: dict[int, str],
        *,
        removes: frozenset[int] = frozenset(),
        sticks: frozenset[int] = frozenset(),
    ) -> None:
        self.current = current
        self.documents = {
            sequence: _document(sequence, checksum) for sequence, checksum in documents.items()
        }
        self.removes = removes
        self.sticks = sticks
        self.refreshed: list[int] = []

    def stale_document_sequence_numbers(
        self, *, game_id: UUID, after_sequence_number: int, limit: int
    ) -> tuple[int, ...]:
        assert game_id == GAME_ID
        return tuple(
            sorted(
                sequence
                for sequence, document in self.documents.items()
                if sequence > after_sequence_number
                and self.current[sequence] != document.board_checksum_sha256
            )[:limit]
        )

    def board_document(
        self, *, game_id: UUID, sequence_number: int
    ) -> tuple[BoardSearchAssetMode, BoardSearchBoardDocument | None]:
        return BoardSearchAssetMode.OPERATIONAL_REVIEW, self.documents.get(sequence_number)

    def board_view_source(
        self, *, game_id: UUID, document: BoardSearchBoardDocument
    ) -> BoardSearchBoardViewSource | None:
        return BoardSearchBoardViewSource(
            image_relative_path="page.jpg",
            image_checksum_sha256="a" * 64,
            geometry={},
            current_board_checksum_sha256=self.current[document.sequence_number],
        )

    def refresh_board_document(self, *, game_id: UUID, document: BoardSearchBoardDocument) -> None:
        sequence = document.sequence_number
        self.refreshed.append(sequence)
        if sequence in self.removes:
            del self.documents[sequence]
        elif sequence not in self.sticks:
            self.documents[sequence] = replace(
                document, board_checksum_sha256=self.current[sequence]
            )


def _repository() -> _Repository:
    current = {1: "new1", 2: "same2", 3: "new3", 4: "new4", 5: "new5"}
    documents = {1: "old1", 2: "same2", 3: "old3", 4: "old4", 5: "old5"}
    return _Repository(current, documents, removes=frozenset({4}), sticks=frozenset({5}))


def test_refresh_batch_reports_each_outcome_and_never_touches_fresh_documents() -> None:
    repository = _repository()
    service = BoardSearchStaleDocumentRefresh(repository)

    batch = service.refresh_batch(game_id=GAME_ID, after_sequence_number=0, limit=10)

    assert repository.refreshed == [1, 3, 4, 5]
    assert batch.refreshed == (1, 3)
    assert batch.removed == (4,)
    assert batch.still_stale == (5,)
    assert batch.last_sequence_number == 5
    # Only the board whose refresh could not catch up stays selected.
    assert service.stale_sequence_numbers(game_id=GAME_ID, after_sequence_number=0, limit=10) == (
        5,
    )


def test_refresh_batch_is_bounded_and_ends_after_the_cursor() -> None:
    repository = _repository()
    service = BoardSearchStaleDocumentRefresh(repository)

    first = service.refresh_batch(game_id=GAME_ID, after_sequence_number=0, limit=2)
    assert (first.refreshed, first.last_sequence_number) == ((1, 3), 3)
    after_end = service.refresh_batch(game_id=GAME_ID, after_sequence_number=5, limit=2)
    assert after_end.last_sequence_number is None
    assert after_end.refreshed == after_end.removed == after_end.still_stale == ()
    with pytest.raises(ValueError):
        service.refresh_batch(game_id=GAME_ID, after_sequence_number=0, limit=0)


def _script() -> ModuleType:
    path = Path(__file__).parents[3] / "scripts" / "refresh_stale_board_search_documents.py"
    spec = spec_from_file_location("refresh_stale_board_search_documents", path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Session:
    def __init__(self, log: list[str]) -> None:
        self.log = log

    def commit(self) -> None:
        self.log.append("commit")

    def rollback(self) -> None:
        self.log.append("rollback")


def _wire(monkeypatch: pytest.MonkeyPatch, script: ModuleType, repository: _Repository) -> Any:
    log: list[str] = []
    monkeypatch.setattr(
        script, "_service", lambda session: BoardSearchStaleDocumentRefresh(repository)
    )

    @contextmanager
    def sessions() -> Any:
        log.append("open")
        yield _Session(log)

    return sessions, log


def test_preview_counts_without_refreshing(monkeypatch: pytest.MonkeyPatch) -> None:
    script = _script()
    repository = _repository()
    sessions, log = _wire(monkeypatch, script, repository)

    report = script.preview(sessions, GAME_ID)

    assert report["staleCount"] == 4
    assert report["sample"] == [1, 3, 4, 5]
    assert repository.refreshed == []
    assert "commit" not in log


def test_apply_commits_each_batch_and_reports_totals(monkeypatch: pytest.MonkeyPatch) -> None:
    script = _script()
    repository = _repository()
    sessions, log = _wire(monkeypatch, script, repository)
    progress: list[dict[str, object]] = []

    report = script.apply(
        sessions, GAME_ID, batch_size=2, max_boards=None, progress=progress.append
    )

    assert repository.refreshed == [1, 3, 4, 5]
    assert report["batches"] == 2
    assert (report["refreshedCount"], report["removedCount"], report["stillStaleCount"]) == (
        2,
        1,
        1,
    )
    assert report["stillStaleSample"] == [5]
    assert [line["cursor"] for line in progress] == [3, 5]
    # Two batches plus the empty probe that ends the run, each committed.
    assert log.count("commit") == 3


def test_apply_stops_at_max_boards_and_a_rerun_resumes(monkeypatch: pytest.MonkeyPatch) -> None:
    script = _script()
    repository = _repository()
    sessions, _log = _wire(monkeypatch, script, repository)

    first = script.apply(sessions, GAME_ID, batch_size=10, max_boards=1, progress=lambda _: None)
    assert first["refreshedCount"] == 1 and repository.refreshed == [1]

    rerun = script.apply(sessions, GAME_ID, batch_size=10, max_boards=None, progress=lambda _: None)
    assert repository.refreshed == [1, 3, 4, 5]
    assert (rerun["refreshedCount"], rerun["removedCount"], rerun["stillStaleCount"]) == (1, 1, 1)
