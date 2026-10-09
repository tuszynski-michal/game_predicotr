"""PostgreSQL read of super game markers for board search (TASK-0935, D-535).

One statement reads the game's super game kind, the derivation state and the
published series covering the requested positions.  A single statement sees
one snapshot, so the series and the `fresh` flag always come from the same
generation, whatever the isolation level of the caller's transaction (the
publication of a generation updates both in one transaction).

A position is covered by the published series with the greatest trigger not
above it, when the position does not lie beyond that series' last spin
(``trigger + length``).  Published series never overlap, so one index probe
per position on ``uq_super_game_series_trigger`` (``game_id``,
``trigger_sequence_number``) finds it; no extra index is needed.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Final
from uuid import UUID

from game_predictor_worker.domain.super_games import (
    get_super_game_kind,
    is_known_super_game_kind,
)
from sqlalchemy import text
from sqlalchemy.orm import Session

from game_predictor_api.domain.super_game_markers import (
    NO_SUPER_GAME_STATE,
    SuperGameMarker,
    SuperGameMarkers,
    marker_for_position,
)
from game_predictor_api.domain.super_game_series import (
    RunVerification,
    SeriesCompleteness,
    SuperGameState,
)
from game_predictor_api.storage.game_storage_routing import (
    GameStorageIntent,
    GameStorageRouter,
)

_MARKERS_SQL: Final = text("""
WITH g AS (
    SELECT super_game_kind FROM games WHERE id = :game_id
), st AS (
    SELECT input_version, input_version_of_generation
    FROM super_game_derivation_state WHERE game_id = :game_id
), cov AS (
    SELECT p.pos AS position, s.id AS series_id,
           s.trigger_sequence_number, s.length, s.completeness, s.run_verification,
           sym.code AS super_symbol_code
    FROM unnest(CAST(:positions AS integer[])) AS p(pos)
    JOIN LATERAL (
        SELECT x.id, x.game_id, x.trigger_sequence_number, x.length, x.completeness,
               x.run_verification, x.super_symbol_id
        FROM super_game_series x
        WHERE x.game_id = :game_id AND x.trigger_sequence_number <= p.pos
        ORDER BY x.trigger_sequence_number DESC
        LIMIT 1
    ) s ON p.pos <= s.trigger_sequence_number + s.length
    LEFT JOIN symbols sym ON sym.game_id = s.game_id AND sym.id = s.super_symbol_id
)
SELECT g.super_game_kind, st.input_version, st.input_version_of_generation,
       cov.position, cov.series_id, cov.trigger_sequence_number, cov.length,
       cov.completeness, cov.run_verification, cov.super_symbol_code
FROM g
LEFT JOIN st ON true
LEFT JOIN cov ON true
""")


def _has_super_game(kind_code: str) -> bool:
    return is_known_super_game_kind(kind_code) and get_super_game_kind(kind_code).series_length > 0


class SqlAlchemySuperGameMarkerRepository:
    """Request-session adapter; read-only, never commits."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def markers(self, game_id: UUID, positions: Collection[int]) -> SuperGameMarkers:
        if self._session.get_bind().dialect.name != "postgresql":
            # The series tables exist only on PostgreSQL (manifest v6).
            return SuperGameMarkers(state=NO_SUPER_GAME_STATE)
        GameStorageRouter().bind(self._session, game_id, intent=GameStorageIntent.READ)
        rows = self._session.execute(
            _MARKERS_SQL,
            {"game_id": game_id, "positions": sorted({int(value) for value in positions})},
        ).all()
        if not rows:
            # Unknown game: nothing was derived.
            return SuperGameMarkers(state=NO_SUPER_GAME_STATE)
        first = rows[0]
        has_super_game = _has_super_game(str(first[0]))
        state = SuperGameState(
            input_version=0 if first[1] is None else int(first[1]),
            generation_input_version=None if first[2] is None else int(first[2]),
            has_super_game=has_super_game,
        )
        if not has_super_game:
            return SuperGameMarkers(state=state)
        by_position: dict[int, SuperGameMarker] = {}
        for row in rows:
            if row[3] is None:
                continue
            position = int(row[3])
            marker = marker_for_position(
                position=position,
                series_id=row[4],
                trigger_sequence_number=int(row[5]),
                series_length=int(row[6]),
                super_symbol_code=None if row[9] is None else str(row[9]),
                completeness=SeriesCompleteness(str(row[7])),
                run_verification=RunVerification(str(row[8])),
            )
            if marker is not None:
                by_position[position] = marker
        return SuperGameMarkers(state=state, by_position=by_position)


__all__ = ["SqlAlchemySuperGameMarkerRepository"]
