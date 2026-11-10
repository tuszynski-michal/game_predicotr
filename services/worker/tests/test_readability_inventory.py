from types import SimpleNamespace
from uuid import uuid4

import pytest
from game_predictor_api.domain.symbol_readability import ReadabilityWorkflowError
from game_predictor_worker.symbols import readability_inventory
from game_predictor_worker.symbols.readability_inventory import candidate_snapshots, source_batches


class Stream:
    def __init__(self, cells):
        self.cells = cells
        self.closed = False

    def __iter__(self):
        for start in range(0, len(self.cells), 250):
            yield self.cells[start : start + 250]

    def close(self):
        self.closed = True


class Session:
    def __init__(self, count=501, missing=False):
        self.stream = Stream([uuid4() for _ in range(count)])
        self.batches = []
        self.missing = missing

    def execute(self, statement, params, **options):
        self.batches.append(params["cells"])
        rows = [{"cell_id": str(cell)} for cell in reversed(params["cells"])]
        return SimpleNamespace(scalars=lambda: rows[1:] if self.missing else rows)


def test_late_hydration_is_bounded_and_preserves_order(monkeypatch):
    session = Session()
    monkeypatch.setattr(
        readability_inventory, "candidate_id_pages", lambda *a, **kw: session.stream
    )
    rows = list(
        candidate_snapshots(session, uuid4(), "seed", audit=False, replacement_fences=False)
    )
    assert [row["cell_id"] for row in rows] == list(map(str, session.stream.cells))
    assert list(map(len, session.batches)) == [250, 250, 1]
    assert session.stream.closed


def test_early_close_does_not_hydrate_remaining_pages(monkeypatch):
    session = Session()
    monkeypatch.setattr(
        readability_inventory, "candidate_id_pages", lambda *a, **kw: session.stream
    )
    stream = candidate_snapshots(session, uuid4(), "seed", audit=False, replacement_fences=False)
    next(stream)
    stream.close()
    assert len(session.batches) == 1
    assert session.stream.closed


def test_missing_current_snapshot_stops_and_closes_cursor(monkeypatch):
    session = Session(missing=True)
    monkeypatch.setattr(
        readability_inventory, "candidate_id_pages", lambda *a, **kw: session.stream
    )
    with pytest.raises(ReadabilityWorkflowError) as error:
        list(candidate_snapshots(session, uuid4(), "seed", audit=False, replacement_fences=False))
    assert error.value.code == "READABILITY_CROP_STALE"
    assert session.stream.closed


def test_audit_filters_ineligible_superset_without_reordering(monkeypatch):
    session = Session(count=3, missing=True)
    monkeypatch.setattr(
        readability_inventory, "candidate_id_pages", lambda *a, **kw: session.stream
    )
    rows = list(candidate_snapshots(session, uuid4(), "seed", audit=True, replacement_fences=True))
    assert [row["cell_id"] for row in rows] == list(map(str, session.stream.cells[:-1]))
    assert session.stream.closed


def test_source_hash_ties_stay_in_one_batch(monkeypatch):
    monkeypatch.setattr(readability_inventory, "SOURCE_PAGE_SIZE", 2)
    sources = [uuid4() for _ in range(5)]
    rows = zip(sources, ["a", "b", "b", "b", "c"], strict=True)
    assert list(source_batches(iter(rows))) == [sources[:4], sources[4:]]


def test_fence_fast_path_refuses_missing_ownership_lock():
    # No query may execute when the required transaction lock is absent.
    with pytest.raises(ReadabilityWorkflowError) as error:
        readability_inventory.has_replacement_fences(SimpleNamespace(), uuid4())
    assert error.value.code == "READABILITY_INVENTORY_LOCK_REQUIRED"
