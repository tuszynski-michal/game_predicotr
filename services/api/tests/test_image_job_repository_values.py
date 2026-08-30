from __future__ import annotations

import pytest
from game_predictor_api.storage.image_job_repository import _non_negative_snapshot_count


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, 0),
        (7, 7),
        (-1, 0),
        (True, 0),
        ("7", 0),
        (None, 0),
    ],
)
def test_non_negative_snapshot_count_rejects_coercion(
    value: object,
    expected: int,
) -> None:
    assert _non_negative_snapshot_count(value) == expected
