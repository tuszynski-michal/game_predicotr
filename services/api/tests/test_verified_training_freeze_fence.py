"""Slow attestation precedes the write fence; drift never produces a cohort."""

from dataclasses import replace
from uuid import uuid4

import pytest
from game_predictor_api.application.verified_training_cohorts import (
    SymbolCellTrainingFreezeFence,
    SymbolCellTrainingSourceInventory,
)
from game_predictor_api.domain.image_reviews import ImageReviewConflictError
from game_predictor_api.domain.verified_training_cohorts import SymbolCellTrainingExclusionCounts
from test_symbol_cell_training_cohorts_domain import _candidate
from test_verified_training_cohorts import _service


class PreparedSymbols:
    supports_unlocked_attestation = True

    def __init__(self):
        self.events = []
        self.fence = SymbolCellTrainingFreezeFence(3, "a" * 64, "b" * 64)
        self.candidate = _candidate(1)
        self.change_during_prepare = False
        self.busy = False

    def active_symbol_codes(self, game_id):
        return ("cherry",)

    def capture_freeze_fence(self, *, game_id):
        self.events.append("capture")
        return self.fence

    def inventory(self, *, game_id, lock_game):
        assert not lock_game, "Originals must be read without an ownership lock"
        self.events.append("attest")
        if self.change_during_prepare:
            self.fence = replace(self.fence, catalog_revision=self.fence.catalog_revision + 1)
        return SymbolCellTrainingSourceInventory(
            candidates=(self.candidate,), exclusions=SymbolCellTrainingExclusionCounts()
        )

    def require_freeze_fence(self, *, game_id, expected):
        self.events.append("validate")
        if self.busy:
            raise ImageReviewConflictError("VERIFIED_TRAINING_COHORT_WRITE_BUSY", "Busy")
        if expected != self.fence:
            raise ImageReviewConflictError("VERIFIED_TRAINING_COHORT_PREVIEW_STALE", "Changed")


@pytest.mark.parametrize("failure", [None, "concurrent_edit", "busy", "changed_preview"])
def test_attestation_is_outside_lock_and_drift_is_never_silently_accepted(tmp_path, failure):
    service, _source, cohorts, game = _service(tmp_path)
    symbols = PreparedSymbols()
    service._symbol_cell_source_repository = symbols
    preview = service.preview(game_id=game)
    symbols.events.clear()
    if failure == "concurrent_edit":
        symbols.change_during_prepare = True
    if failure == "busy":
        symbols.busy = True
    if failure == "changed_preview":
        symbols.candidate = _candidate(2)
    command = dict(
        game_id=game,
        idempotency_key=uuid4(),
        created_by="operator",
        expected_manifest_checksum_sha256=preview.manifest_checksum_sha256,
    )
    if failure:
        with pytest.raises(ImageReviewConflictError) as error:
            service.freeze(**command)
        assert error.value.code == (
            "VERIFIED_TRAINING_COHORT_WRITE_BUSY"
            if failure == "busy"
            else "VERIFIED_TRAINING_COHORT_PREVIEW_STALE"
        )
        assert not cohorts.values
        assert not list((tmp_path / "data").rglob("cohort.json"))
    else:
        first, created = service.freeze(**command)
        assert created
        assert symbols.events == ["capture", "attest", "validate"]
        # Lost response returns the persisted cohort without another attestation.
        replay, created = service.freeze(**command)
        assert replay == first and not created
        assert symbols.events == ["capture", "attest", "validate"]
    assert symbols.events == (
        ["capture", "attest"] if failure == "changed_preview" else ["capture", "attest", "validate"]
    )
