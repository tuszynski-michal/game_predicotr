"""Direct local V7 does not touch historical browser-staging retention."""

from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from game_predictor_api.application.semi_automatic_image_selections import (
    SemiAutomaticImageSelectionService,
)
from game_predictor_api.domain.semi_automatic_image_selections import (
    SemiAutomaticSelectionConflictError,
    SemiAutomaticSelectionDirection,
    SemiAutomaticSelectionError,
    SemiAutomaticSelectionWorkflowMode,
    create_semi_automatic_selection_run,
    create_v7_selection_configuration,
)
from game_predictor_api.storage.models import BrowserSelectionRetentionModel
from game_predictor_api.storage.semi_automatic_image_selection_repository import (
    SqlAlchemySemiAutomaticSelectionRepository,
)
from sqlalchemy.orm import Session
from test_semi_automatic_image_selection_repository import (
    _ForeignKeyOrderingSession,
    _source_manifest,
)
from test_v7_selection_delivery import _gate
from test_v7_selection_delivery_api import V7MemoryRepository


def local_run(root):
    gate = _gate(root)
    configuration = create_v7_selection_configuration(
        first_sequence_number=1,
        last_sequence_number=18,
        calibration_fingerprint=gate.profile_fingerprint,
        localizer_fingerprint=gate.observer_fingerprint,
        pilot=gate.snapshot_for(root, "a" * 64),
    )
    run, ranges = create_semi_automatic_selection_run(
        source=replace(_source_manifest(), source_fingerprint="a" * 64),
        first_sequence_number=1,
        last_sequence_number=18,
        direction=SemiAutomaticSelectionDirection.ASCENDING,
        recognizer_fingerprint="3" * 64,
        grouping_policy_fingerprint="e" * 64,
        workflow_mode=SemiAutomaticSelectionWorkflowMode.V7_SELECTION,
        v7_configuration=configuration,
        local_source_manifest_relative_path="exports/local/fixture/source-manifest.json",
    )
    return gate, run, ranges


class LocalOnlySession(_ForeignKeyOrderingSession):
    def get(self, model, *_args, **_kwargs):
        if model is BrowserSelectionRetentionModel:
            raise AssertionError("Direct V7 must not query browser retention.")
        raise AssertionError("Unexpected model read.")


def test_v7_add_preserves_parent_range_flush_order_without_browser_query(tmp_path):
    _, run, ranges = local_run(tmp_path)
    session = LocalOnlySession()
    repository = SqlAlchemySemiAutomaticSelectionRepository(cast(Session, session))
    repository.get = lambda _run_id: run
    assert repository.add(run, ranges, identity_key="a" * 64) is run
    assert session.events == [
        "JobModel",
        "SemiAutomaticImageSelectionRunModel",
        "flush",
        "ranges",
        "flush",
    ]


def test_v7_failed_child_flush_keeps_nested_transaction_rollback(tmp_path):
    _, run, ranges = local_run(tmp_path)

    class FailingSession(LocalOnlySession):
        rolled_back = False

        @contextmanager
        def begin_nested(self):
            try:
                yield
            except RuntimeError:
                self.events.clear()
                self.rolled_back = True
                raise

        def flush(self):
            super().flush()
            if self._children_pending:
                raise RuntimeError("Child flush failed.")

    session = FailingSession()
    repository = SqlAlchemySemiAutomaticSelectionRepository(cast(Session, session))
    with pytest.raises(RuntimeError, match="Child flush failed"):
        repository.add(run, ranges, identity_key="a" * 64)
    assert session.rolled_back and session.events == []


@pytest.mark.parametrize(
    "workflow",
    [
        SemiAutomaticSelectionWorkflowMode.SELECTION,
        SemiAutomaticSelectionWorkflowMode.FILENAME_VERIFICATION,
    ],
)
def test_legacy_still_pins_browser_retention(tmp_path, workflow):
    _, run, _ = local_run(tmp_path)
    run = replace(run, workflow_mode=workflow, v7_configuration=None)
    retention = SimpleNamespace(game_id=None, state="ready", import_job_id=None)
    calls = []

    def get(model, upload_id, **kwargs):
        calls.append((model, upload_id, kwargs))
        return retention

    repository = SqlAlchemySemiAutomaticSelectionRepository(cast(Session, SimpleNamespace(get=get)))
    repository._pin_global_staging(run)
    assert calls == [
        (BrowserSelectionRetentionModel, run.source.upload_id, {"with_for_update": True})
    ]
    assert retention.import_job_id == run.job.id
    assert retention.state == "in_use" and retention.eligible_at is None
    assert retention.last_dependency_at == retention.updated_at == run.created_at
    assert retention.blocked_reason is None


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"game_id": 777}, "SEMI_AUTOMATIC_SELECTION_SOURCE_SCOPE_INVALID"),
        ({"state": "blocked"}, "SEMI_AUTOMATIC_SELECTION_SOURCE_CLEANUP_ACTIVE"),
        ({"import_job_id": uuid4()}, "SEMI_AUTOMATIC_SELECTION_SOURCE_IN_USE"),
    ],
)
def test_legacy_browser_retention_conflicts_are_preserved(tmp_path, changes, code):
    _, run, _ = local_run(tmp_path)
    run = replace(
        run, workflow_mode=SemiAutomaticSelectionWorkflowMode.SELECTION, v7_configuration=None
    )
    values = {"game_id": None, "state": "ready", "import_job_id": None, **changes}
    retention = SimpleNamespace(**values)
    session = SimpleNamespace(get=lambda *_args, **_kwargs: retention)
    repository = SqlAlchemySemiAutomaticSelectionRepository(cast(Session, session))
    with pytest.raises(SemiAutomaticSelectionConflictError) as error:
        repository._pin_global_staging(run)
    assert error.value.code == code
    assert vars(retention) == values


def test_active_v7_still_refuses_browser_upload_before_any_source_access(tmp_path):
    gate, _, _ = local_run(tmp_path)
    repository = V7MemoryRepository(gate)
    service = SemiAutomaticImageSelectionService(
        repository,
        object(),
        enabled=True,
        v7_artifacts=SimpleNamespace(validate=lambda _gate: None),
    )
    before = dict(repository.runs)
    with pytest.raises(SemiAutomaticSelectionError) as error:
        service.create(
            upload_id=uuid4(),
            first_sequence_number=1,
            last_sequence_number=18,
            direction=SemiAutomaticSelectionDirection.ASCENDING,
            mode="v7_selection",
        )
    assert error.value.code == "SEMI_AUTOMATIC_SELECTION_LOCAL_SOURCE_REQUIRED"
    assert repository.runs == before and repository.operations == {}
