from __future__ import annotations

import math
import sqlite3
from pathlib import Path

from game_predictor_api.application.grid_diagnostics import (
    GRID_DIAGNOSTICS_LOW_CONFIDENCE_THRESHOLD,
    missing_reason_diagnostics,
)
from game_predictor_api.domain.board_import_coverage import (
    MissingReason,
    ReasonSpan,
    SequenceInterval,
)
from game_predictor_api.storage.grid_diagnostics_repository import (
    _BOARDS_SQL,
    _CELLS_SQL,
    _SLOT_COVERAGE_SQL,
)


def test_secondary_reasons_intersect_only_missing_unique_sequences() -> None:
    signals, overlaps = missing_reason_diagnostics(
        expected=10,
        added=[SequenceInterval(3, 5)],
        reasons=[
            ReasonSpan(SequenceInterval(1, 7), MissingReason.WAITING_FOR_GEOMETRY),
            ReasonSpan(SequenceInterval(2, 6), MissingReason.WAITING_FOR_GEOMETRY),
            ReasonSpan(SequenceInterval(4, 9), MissingReason.REJECTED),
            ReasonSpan(SequenceInterval(6, 6), MissingReason.PARTIAL_SOURCE),
        ],
    )
    assert signals == {"waiting_for_geometry": 4, "rejected": 4, "partial_source": 1}
    assert overlaps == {
        "waiting_for_geometry&partial_source": 1,
        "waiting_for_geometry&rejected": 2,
        "partial_source&rejected": 1,
    }


def test_empty_and_out_of_range_signals_do_not_create_missing_boards() -> None:
    assert missing_reason_diagnostics(expected=10, added=[], reasons=[]) == ({}, {})
    assert missing_reason_diagnostics(
        expected=2,
        added=[SequenceInterval(1, 2)],
        reasons=[ReasonSpan(SequenceInterval(1, 50), MissingReason.FAILED)],
    ) == ({"failed": 0}, {})


def test_sql_populations_duplicates_canonical_and_current_symbol_problems(tmp_path: Path) -> None:
    """Execute production aggregate SQL on a small independent relational fixture.

    Unknown cells never participate in the existence predicate. Rejected and
    stale crops are retained in storage but excluded from current cell counts.
    """
    database_path = tmp_path / "diagnostics.sqlite"
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.executescript("""
      CREATE TABLE image_review_items (id TEXT, game_id TEXT, recognized_board_id TEXT,
        sequence_number INTEGER, status TEXT);
      CREATE TABLE recognized_boards (id TEXT, game_id TEXT, completeness_status TEXT,
        geometry_revision INTEGER, approved_geometry_revision INTEGER,
        source_geometry_revision_id TEXT);
      CREATE TABLE image_sequence_canonical (game_id TEXT, sequence_number INTEGER);
      CREATE TABLE image_source_geometry_revisions (id TEXT, game_id TEXT, status TEXT);
      CREATE TABLE image_board_geometry_pending
        (game_id TEXT, sequence_number INTEGER, status TEXT);
      CREATE TABLE image_symbol_review_cells
        (review_item_id TEXT, recognized_board_id TEXT, game_id TEXT,
        geometry_revision INTEGER, source_available BOOLEAN, source_visibility TEXT,
        assigned_symbol_id TEXT, quality_issue TEXT, review_state TEXT,
        prediction_confidence REAL);
      INSERT INTO image_source_geometry_revisions VALUES ('r','g','proposed');
      INSERT INTO recognized_boards VALUES
        ('b1','g','complete',2,NULL,'r'), ('b2','g','complete',2,2,'r'),
        ('b3','g','pending_partial',2,NULL,'r'), ('b4','g','complete',2,NULL,'r'),
        ('other','other','complete',2,NULL,'r');
      INSERT INTO image_review_items VALUES
        ('i1','g','b1',1,'pending'), ('i2','g','b2',1,'accepted'),
        ('i3','g','b3',2,'pending'), ('i4','g','b4',3,'rejected'),
        ('i5','g','b4',4,'superseded'), ('foreign','other','other',1,'pending');
      INSERT INTO image_sequence_canonical VALUES ('g',1),('g',5),('other',1);
      INSERT INTO image_board_geometry_pending VALUES
        ('g',1,'pending'), ('g',2,'pending'), ('g',2,'pending'),
        ('g',6,'pending'), ('g',NULL,'pending'), ('g',3,'rejected'), ('other',3,'pending');
      INSERT INTO image_symbol_review_cells VALUES
        ('i1','b1','g',2,1,'full',NULL,'grid_issue','pending',0.2),
        ('i1','b1','g',2,1,'full','known','grid_issue','pending',0.3),
        ('i1','b1','g',2,1,'full',NULL,'unreadable','approved',NULL),
        ('i1','b1','g',2,0,'outside',NULL,NULL,'pending',NULL),
        ('i1','b1','g',1,1,'full',NULL,'grid_issue','pending',0.1),
        ('i4','b4','g',2,1,'full',NULL,'grid_issue','pending',0.1),
        ('i5','b4','g',2,1,'full',NULL,'grid_issue','pending',0.1),
        ('foreign','other','other',2,1,'full',NULL,'grid_issue','pending',0.1);
    """)
    params = {
        "game_id": "g",
        "expected": 5,
        "threshold": GRID_DIAGNOSTICS_LOW_CONFIDENCE_THRESHOLD,
    }
    rows = connection.execute(_BOARDS_SQL, params).fetchall()
    statuses = {row["status"]: dict(row) for row in rows}
    assert statuses["pending"]["rows"] == 2
    assert statuses["pending"]["qualifying_rows"] == 1
    assert statuses["accepted"]["qualifying_sequences"] == 1
    assert statuses["accepted"]["overlap"] == 1
    assert statuses["rejected"]["qualifying_rows"] == 0
    assert statuses["superseded"]["qualifying_rows"] == 0
    cells = dict(connection.execute(_CELLS_SQL, params).fetchone())
    assert dict(connection.execute(_SLOT_COVERAGE_SQL, params).fetchone()) == {
        "unnumbered": 1,
        "out_of_range": 1,
        "already_added": 1,
        "missing_slots": 2,
        "missing_unique_sequences": 1,
    }
    assert cells == {
        "total": 4,
        "unknown": 3,
        "pending": 3,
        "approved": 1,
        "unreadable": 1,
        "outside": 1,
        "low_confidence": 2,
        "unknown_pending": 2,
        "unreadable_pending": 0,
        "unknown_low": 2,
        "flagged": 1,
        "unconfirmed": 1,
        "flagged_unconfirmed": 1,
    }
    threshold = GRID_DIAGNOSTICS_LOW_CONFIDENCE_THRESHOLD
    connection.executemany(
        "INSERT INTO image_symbol_review_cells VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            ("i2", "b2", "g", 2, 1, "full", "known", None, "pending", confidence)
            for confidence in (
                math.nextafter(threshold, -math.inf),
                threshold,
                math.nextafter(threshold, math.inf),
            )
        ],
    )
    cells = dict(connection.execute(_CELLS_SQL, params).fetchone())
    assert cells["low_confidence"] == 3  # below counts; exact/above do not
    connection.commit()
    connection.close()
    # Reopening the persisted fixture proves counters do not depend on a
    # session cache, and retain the same rejected/stale exclusions.
    with sqlite3.connect(database_path) as restarted:
        restarted.row_factory = sqlite3.Row
        assert dict(restarted.execute(_CELLS_SQL, params).fetchone()) == cells
