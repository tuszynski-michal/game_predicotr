from __future__ import annotations

from uuid import uuid4

import pytest

from scripts.backfill_v09_schema import _read_checkpoint, _write_checkpoint


def test_v09_backfill_checkpoint_round_trip(tmp_path) -> None:
    game_id = uuid4()
    board_id = uuid4()
    checkpoint = tmp_path / "checkpoint.json"

    _write_checkpoint(checkpoint, game_id=game_id, board_id=board_id)

    assert _read_checkpoint(checkpoint, game_id) == board_id


def test_v09_backfill_checkpoint_rejects_another_game(tmp_path) -> None:
    checkpoint = tmp_path / "checkpoint.json"
    _write_checkpoint(checkpoint, game_id=uuid4(), board_id=uuid4())

    with pytest.raises(ValueError, match="different game"):
        _read_checkpoint(checkpoint, uuid4())
