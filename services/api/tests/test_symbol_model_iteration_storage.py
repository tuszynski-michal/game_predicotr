from __future__ import annotations

from typing import Any, cast
from uuid import uuid4

from game_predictor_api.storage.symbol_model_iteration_repository import (
    _cohort_source_checksums,
    _cohort_source_symbol_counts,
)


class _ScalarValues:
    def __init__(self, values: tuple[str, ...]) -> None:
        self._values = values

    def all(self) -> list[str]:
        return list(self._values)


class _SourceChecksumSession:
    def __init__(self) -> None:
        self.calls = 0

    def scalars(self, _statement: object) -> _ScalarValues:
        self.calls += 1
        if self.calls == 1:
            return _ScalarValues(("a" * 64,))
        return _ScalarValues(("b" * 64, "c" * 64, "b" * 64))


class _Rows:
    def __init__(self, values: list[tuple[object, object]]) -> None:
        self._values = values

    def all(self) -> list[tuple[object, object]]:
        return self._values


class _SourceSymbolSession:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self, _statement: object) -> _Rows:
        self.calls += 1
        if self.calls == 1:
            return _Rows(
                [
                    (
                        "a" * 64,
                        {"cells": [{"symbolCode": "A"}, {"symbolCode": "B"}]},
                    )
                ]
            )
        return _Rows([("b" * 64, "A"), ("b" * 64, "A"), ("c" * 64, "C")])


def test_cohort_source_checksums_include_individually_approved_cells() -> None:
    session = _SourceChecksumSession()

    result = _cohort_source_checksums(cast(Any, session), uuid4())

    assert session.calls == 2
    assert result == ("a" * 64, "b" * 64, "c" * 64)


def test_cohort_source_symbol_counts_include_legacy_and_individual_cells() -> None:
    session = _SourceSymbolSession()

    result = _cohort_source_symbol_counts(cast(Any, session), uuid4())

    assert session.calls == 2
    assert result == {
        "a" * 64: {"A": 1, "B": 1},
        "b" * 64: {"A": 2},
        "c" * 64: {"C": 1},
    }
