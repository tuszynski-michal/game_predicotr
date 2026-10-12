from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
from game_predictor_api.domain.jobs import JobConflictError
from game_predictor_api.domain.symbol_model_iterations import (
    SymbolModelIterationStatus,
    SymbolTrainingConfiguration,
)
from game_predictor_api.storage import symbol_model_iteration_repository as iteration_storage
from game_predictor_api.storage.models import JobModel, SymbolModelIterationModel
from game_predictor_api.storage.symbol_model_iteration_repository import (
    SqlAlchemySymbolModelIterationRepository,
    _can_inherit_training_split,
    _cohort_source_checksums,
    _cohort_source_symbol_counts,
)
from game_predictor_worker.symbols.training_dataset import build_class_stratified_source_assignments


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


@pytest.mark.parametrize("status", ["rejected", "failed", "cancelled"])
def test_terminal_pretraining_split_is_not_a_reference(status: str) -> None:
    record = SimpleNamespace(status=status, last_completed_epoch=0)
    assert not _can_inherit_training_split(cast(Any, record))


@pytest.mark.parametrize("status", ["rejected", "failed", "cancelled", "candidate_ready"])
def test_trained_reference_remains_stable_including_quality_rejection(status: str) -> None:
    record = SimpleNamespace(status=status, last_completed_epoch=1)
    assert _can_inherit_training_split(cast(Any, record))


def test_rejected_reference_cannot_consume_all_training_examples_after_restart() -> None:
    # Four full-class photos were all assigned to controls by a rejected attempt;
    # additional approved photos contain only B. The same immutable input is
    # repaired by a fresh process without moving a previously trained reference.
    profiles = {f"{index:064x}": {"A": 3, "B": 5} for index in range(4)}
    profiles.update({f"{index:064x}": {"B": 2} for index in range(4, 11)})
    bad = {
        f"{index:064x}": split
        for index, split in enumerate(("regression", "validation", "test", "regression"))
    }
    inherited = dict(build_class_stratified_source_assignments(profiles, existing=bad))
    assert all(inherited[source] != "train" for source in bad)
    record = SimpleNamespace(
        status=SymbolModelIterationStatus.REJECTED.value, last_completed_epoch=0
    )
    previous = bad if _can_inherit_training_split(cast(Any, record)) else {}
    repaired = dict(build_class_stratified_source_assignments(profiles, existing=previous))
    for split in ("train", "validation", "test", "regression"):
        assert {
            code for source in profiles if repaired[source] == split for code in profiles[source]
        } == {"A", "B"}
    assert repaired == dict(build_class_stratified_source_assignments(profiles))


class _TrainingSession:
    """Persist records across fresh repository instances, without a live DB."""

    def __init__(self) -> None:
        self.game_id, self.cohort_id = uuid4(), uuid4()
        self.iterations: list[SymbolModelIterationModel] = []
        self.jobs: list[JobModel] = []
        self.scalar_index = 0

    def get(self, _model: object, _identity: object) -> object:
        return SimpleNamespace(game_id=self.game_id, manifest_checksum_sha256="a" * 64)

    def execute(self, statement: Any) -> Any:
        self.scalar_index = 0
        values = statement.compile().params.values()
        found = next(
            (
                (iteration, job)
                for iteration in self.iterations
                for job in self.jobs
                if job.id == iteration.job_id and job.input_payload["idempotency_key"] in values
            ),
            None,
        )
        return SimpleNamespace(first=lambda: found)

    def scalars(self, _statement: object) -> Any:
        return SimpleNamespace(all=lambda: list(reversed(self.iterations)))

    def scalar(self, statement: Any) -> Any:
        index = self.scalar_index
        self.scalar_index += 1
        values = statement.compile().params.values()
        if index == 0:
            return next((r for r in self.iterations if r.configuration_fingerprint in values), None)
        if index == 1:
            return next((j for j in self.jobs if j.input_key in values), None)
        if index == 2:
            return None
        assert index == 3
        return len(self.iterations)

    def add(self, record: Any) -> None:
        if isinstance(record, JobModel):
            self.jobs.append(record)
        else:
            assert isinstance(record, SymbolModelIterationModel)
            self.iterations.append(record)

    def flush(self) -> None:
        keys = [(r.cohort_id, r.configuration_fingerprint) for r in self.iterations]
        assert len(keys) == len(set(keys)), "immutable cohort/configuration uniqueness"


def test_rejected_retry_and_lost_response_replay_survive_new_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _TrainingSession()
    monkeypatch.setattr(
        iteration_storage,
        "_cohort_source_symbol_counts",
        lambda *_: {f"{index:064x}": {"A": 3, "B": 5} for index in range(4)},
    )
    monkeypatch.setattr(iteration_storage, "_to_domain", lambda record: record)
    monkeypatch.setattr(iteration_storage, "job_from_record", lambda record: record)

    def run(key: Any, config: SymbolTrainingConfiguration | None = None) -> Any:
        return SqlAlchemySymbolModelIterationRepository(cast(Any, session)).create_training(
            game_id=session.game_id,
            cohort_id=session.cohort_id,
            idempotency_key=key,
            configuration=config or SymbolTrainingConfiguration(),
        )

    first_key, next_key = uuid4(), uuid4()
    original, original_job, created = run(first_key)
    assert created
    original.status = "rejected"
    replay, replay_job, created = run(first_key)
    assert not created and replay.id == original.id and replay_job.id == original_job.id

    retried, new_job, created = run(next_key)
    assert created and retried.id != original.id and new_job.id != original_job.id
    assert retried.configuration_payload["retryNonce"] == str(next_key)
    replay, replay_job, created = run(next_key)
    assert not created and replay.id == retried.id and replay_job.id == new_job.id
    assert len(session.iterations) == 2

    with pytest.raises(JobConflictError, match="another configuration"):
        run(next_key, SymbolTrainingConfiguration(epochs=41))
