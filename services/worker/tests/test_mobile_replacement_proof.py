"""Release workflow never treats restored (no slots) as proof of an old dataset."""

from contextlib import contextmanager

import pytest
from game_predictor_api.domain.mobile_releases import (
    MobileReleaseConflictError,
    MobileReleaseStatus,
)
from game_predictor_worker.jobs.runtime import JobHandlerError
from test_release_workflow import _handler_fixture


@pytest.mark.parametrize("boundary", ["before_snapshot", "before_ready"])
def test_retirement_and_restored_between_stages_still_blocks_old_proof(
    tmp_path, monkeypatch, boundary
):
    handler, store, context, _, publisher, builder, job = _handler_fixture(
        tmp_path, payouts_ready=True
    )
    state = {"retired": False, "slots": False}

    @contextmanager
    def proof_fence(release):
        assert not state["slots"]  # Restoration has already removed every reservation.
        if state["retired"]:
            raise MobileReleaseConflictError(
                "MOBILE_RELEASE_SOURCE_PROOF_STALE", "Dataset proof is stale."
            )
        yield

    monkeypatch.setattr(store, "publication_fence", proof_fence)
    if boundary == "before_snapshot":
        original = store.require_current_sources

        def initial(release):
            original(release)
            state["retired"] = True

        monkeypatch.setattr(store, "require_current_sources", initial)
    else:
        original_build = builder.build

        def build(*args, **kwargs):
            artifact = original_build(*args, **kwargs)
            state["retired"] = True
            return artifact

        monkeypatch.setattr(builder, "build", build)
    with pytest.raises(JobHandlerError) as error:
        handler(context, job)
    assert error.value.code == "MOBILE_RELEASE_SOURCE_PROOF_STALE"
    assert publisher.calls == (0 if boundary == "before_snapshot" else 1)
    assert store.release.status is MobileReleaseStatus.FAILED


def test_finished_release_job_replay_preserves_historical_receipt_without_publication(tmp_path):
    handler, store, context, _, publisher, builder, job = _handler_fixture(
        tmp_path, payouts_ready=True
    )
    handler(context, job)
    ready = store.release
    assert ready.status is MobileReleaseStatus.READY
    calls = publisher.calls
    store.fail_at = "publication"
    handler(context, job)
    assert store.release == ready
    assert publisher.calls == calls
    assert store.mark_failed_calls == 0
