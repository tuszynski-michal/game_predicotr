from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest
from game_predictor_api.domain.jobs import JobExecutionSlot, JobType
from game_predictor_worker import cli
from game_predictor_worker.jobs.runtime import JobExecutionResult
from game_predictor_worker.semi_automatic_selection.job import (
    SemiAutomaticImageSelectionJobHandler,
)


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
        self.options = kwargs
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


class FakeLaneHeartbeat:
    instances: list[FakeLaneHeartbeat] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.options = kwargs
        self.entered = False
        self.exited = False
        self.__class__.instances.append(self)

    def __enter__(self) -> FakeLaneHeartbeat:
        self.entered = True
        return self

    def __exit__(self, *_args: object) -> None:
        self.exited = True


@pytest.fixture(autouse=True)
def reset_fake_worker() -> None:
    FakeWorker.instances.clear()
    FakeLaneHeartbeat.instances.clear()


def _replace_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    engine: FakeEngine,
    owner_engine: FakeEngine | None = None,
) -> None:
    resolved_owner_engine = owner_engine or FakeEngine()
    monkeypatch.setattr(
        cli.ApiSettings,
        "from_environment",
        lambda: SimpleNamespace(
            import_root=Path("imports").resolve(),
            import_max_bytes=1024 * 1024,
            remote_selection_materialization_lease_seconds=60,
            remote_selection_materialization_max_attempts=5,
            remote_selection_materialization_max_actions_per_cycle=4,
            remote_selection_deselect_enabled=True,
            remote_selection_recovery_enabled=True,
            remote_selection_upload_timeout_seconds=120,
            remote_selection_recovery_limit=100,
            # Read when the handlers are built: the three v7_* settings by the V7 pilot
            # artifacts (added with the V7 integration, TASK-0920, v1.7.250) and
            # grid_shadow_enabled by the grid shadow handler (TASK-0805, v1.7.191).
            v7_label_geometry_runtime_root=Path(".runtime").resolve(),
            v7_selection_ocr_model_root=Path(".runtime/ocr").resolve(),
            v7_pilot_acceptance_scope=None,
            grid_shadow_enabled=False,
        ),
    )
    monkeypatch.setattr(cli, "create_database_engine", lambda _settings: engine)
    monkeypatch.setattr(
        cli, "create_owner_database_engine", lambda _settings: resolved_owner_engine
    )
    monkeypatch.setattr(cli, "create_owner_session_factory", lambda owner: ("owner-factory", owner))
    monkeypatch.setattr(cli, "require_alembic_head", lambda _engine: None)
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
    monkeypatch.setattr(cli, "WorkerLaneHeartbeat", FakeLaneHeartbeat)


def test_cli_runs_one_claim_attempt_and_disposes_engine(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    engine = FakeEngine()
    owner_engine = FakeEngine()
    _replace_dependencies(monkeypatch, engine, owner_engine)

    assert cli.main(["--worker-id", "test-worker"]) == 0

    assert capsys.readouterr().out.strip() == "no_job"
    assert len(FakeWorker.instances) == 1
    assert JobType.PAYOUT in FakeWorker.instances[0].handlers
    assert JobType.IMPORT in FakeWorker.instances[0].handlers
    assert JobType.VALIDATE in FakeWorker.instances[0].handlers
    assert JobType.STORAGE_PIPELINE_COMPACTION in FakeWorker.instances[0].handlers
    assert JobType.SUPER_GAME_SERIES_DERIVE in FakeWorker.instances[0].handlers
    assert JobType.IMAGE_SELECTION not in FakeWorker.instances[0].handlers
    assert FakeWorker.instances[0].options["execution_slot"] is JobExecutionSlot.GENERAL
    assert callable(FakeWorker.instances[0].options["auxiliary_work"])
    validation_handler = FakeWorker.instances[0].handlers[JobType.VALIDATE]
    assert validation_handler._page_geometry_handler._registration_workers == 7  # noqa: SLF001
    assert FakeLaneHeartbeat.instances[0].options["thread_budget"] == 7
    assert FakeLaneHeartbeat.instances[0].entered
    assert FakeLaneHeartbeat.instances[0].exited
    assert engine.disposed is True
    # TASK-0795: only VACUUM and ANALYZE steps get the schema-owner engine.
    compaction = FakeWorker.instances[0].handlers[JobType.STORAGE_PIPELINE_COMPACTION]
    assert compaction._engine is owner_engine  # noqa: SLF001
    backfill = FakeWorker.instances[0].handlers[JobType.IMAGE_SYMBOL_REVIEW_BACKFILL]
    assert backfill._statistics_session_factory == ("owner-factory", owner_engine)  # noqa: SLF001


def test_cli_refuses_a_database_schema_other_than_the_code_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from game_predictor_api.storage import schema_readiness

    engine = FakeEngine()
    _replace_dependencies(monkeypatch, engine)
    monkeypatch.setattr(cli, "require_alembic_head", schema_readiness.require_alembic_head)
    monkeypatch.setattr(
        schema_readiness, "database_alembic_revision", lambda _engine: "0130_previous"
    )

    with pytest.raises(schema_readiness.AlembicHeadMismatchError) as error:
        cli.main(["--worker-id", "test-worker"])

    assert error.value.code == "ALEMBIC_HEAD_MISMATCH"
    assert FakeWorker.instances == []
    assert engine.disposed is True


def test_remote_host_action_cycle_runs_recovery_removal_and_materialization_in_order() -> None:
    calls: list[str] = []
    recovery = SimpleNamespace(run_bounded_cycle=lambda: calls.append("recover"))
    removal = SimpleNamespace(run_bounded_cycle=lambda: calls.append("remove"))
    materialization = SimpleNamespace(run_bounded_cycle=lambda: calls.append("materialize"))

    cli._remote_host_action_cycle(  # type: ignore[arg-type]  # noqa: SLF001
        recovery,
        removal,
        materialization,
    )()

    assert calls == ["recover", "remove", "materialize"]


def test_cli_runs_image_selection_in_its_dedicated_lane(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = FakeEngine()
    _replace_dependencies(monkeypatch, engine)

    assert (
        cli.main(
            [
                "--lane",
                "image-selection",
                "--worker-id",
                "selection-worker",
            ]
        )
        == 0
    )

    worker = FakeWorker.instances[0]
    assert set(worker.handlers) == {
        JobType.IMAGE_SELECTION,
        JobType.SEMI_AUTOMATIC_IMAGE_SELECTION,
    }
    assert worker.options["execution_slot"] is JobExecutionSlot.IMAGE_SELECTION
    assert worker.options["auxiliary_work"] is None
    selection_handler = worker.handlers[JobType.IMAGE_SELECTION]
    assert selection_handler._scan_workers == 4  # noqa: SLF001
    assert selection_handler._verification_workers == 1  # noqa: SLF001
    assert isinstance(
        worker.handlers[JobType.SEMI_AUTOMATIC_IMAGE_SELECTION],
        SemiAutomaticImageSelectionJobHandler,
    )
    assert FakeLaneHeartbeat.instances[0].options["thread_budget"] == 5
    assert engine.disposed is True


def test_cli_respects_explicit_image_selection_thread_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = FakeEngine()
    _replace_dependencies(monkeypatch, engine)

    assert (
        cli.main(
            [
                "--lane",
                "image-selection",
                "--cpu-thread-budget",
                "4",
                "--worker-id",
                "selection-worker",
            ]
        )
        == 0
    )

    selection_handler = FakeWorker.instances[0].handlers[JobType.IMAGE_SELECTION]
    assert selection_handler._scan_workers == 3  # noqa: SLF001
    assert selection_handler._verification_workers == 1  # noqa: SLF001
    assert FakeLaneHeartbeat.instances[0].options["thread_budget"] == 4
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
