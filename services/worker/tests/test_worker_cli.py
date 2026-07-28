from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest
from game_predictor_api.domain.jobs import JobType
from game_predictor_worker import cli
from game_predictor_worker.jobs.runtime import JobExecutionResult


class FakeEngine:
    def __init__(self) -> None:
        self.disposed = False

    def dispose(self) -> None:
        self.disposed = True


class FakeWorker:
    instances: list[FakeWorker] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.run_forever_calls: list[float] = []
        self.handlers = args[1]
        self.__class__.instances.append(self)

    def run_once(self) -> JobExecutionResult:
        return JobExecutionResult.NO_JOB

    def run_forever(
        self,
        *,
        should_stop: Callable[[], bool],
        poll_interval_seconds: float,
    ) -> None:
        self.run_forever_calls.append(poll_interval_seconds)


@pytest.fixture(autouse=True)
def reset_fake_worker() -> None:
    FakeWorker.instances.clear()


def _replace_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    engine: FakeEngine,
) -> None:
    monkeypatch.setattr(
        cli.ApiSettings,
        "from_environment",
        lambda: SimpleNamespace(
            import_root=Path("imports").resolve(),
            import_max_bytes=1024 * 1024,
        ),
    )
    monkeypatch.setattr(cli, "create_database_engine", lambda _settings: engine)
    monkeypatch.setattr(
        cli,
        "create_session_factory",
        lambda _engine: object(),
    )
    monkeypatch.setattr(
        cli,
        "SqlAlchemyWorkerJobStore",
        lambda _factory: object(),
    )
    monkeypatch.setattr(cli, "LocalJobWorker", FakeWorker)


def test_cli_runs_one_claim_attempt_and_disposes_engine(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    engine = FakeEngine()
    _replace_dependencies(monkeypatch, engine)

    assert cli.main(["--worker-id", "test-worker"]) == 0

    assert capsys.readouterr().out.strip() == "no_job"
    assert len(FakeWorker.instances) == 1
    assert JobType.PAYOUT in FakeWorker.instances[0].handlers
    assert JobType.IMPORT in FakeWorker.instances[0].handlers
    assert JobType.VALIDATE in FakeWorker.instances[0].handlers
    assert engine.disposed is True


def test_cli_supports_continuous_polling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = FakeEngine()
    _replace_dependencies(monkeypatch, engine)

    assert (
        cli.main(
            [
                "--poll",
                "--poll-interval",
                "0.25",
                "--worker-id",
                "test-worker",
            ]
        )
        == 0
    )

    assert FakeWorker.instances[0].run_forever_calls == [0.25]
    assert engine.disposed is True
