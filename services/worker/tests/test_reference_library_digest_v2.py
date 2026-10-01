"""TASK-0794: slim prediction revisions and the reference-library digest v2 (D-466)."""

from __future__ import annotations

import copy
import hashlib
import json
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from game_predictor_api.domain.prediction_revisions import (
    PredictionRevisionShapeError,
    has_virtual_render_spec,
    predictions_digest,
    predictions_digest_v1,
    predictions_match,
    require_slim_predictions,
    slim_predictions,
)
from game_predictor_api.storage.models import ImageSymbolPredictionRevisionModel
from game_predictor_worker.symbols import reference_library_writer as writer
from game_predictor_worker.symbols.reference_library_writer import (
    MODEL_VERSION,
    BoardPlan,
    TargetCell,
    apply_board,
    revert_board,
    revert_checksum,
)


def _full() -> list[dict[str, Any]]:
    return [
        {
            "rowIndex": index // 5,
            "columnIndex": index % 5,
            "symbolCode": "ARBUZ",
            "confidence": 0.71,
            "alternatives": [{"symbolCode": "ARBUZ", "confidence": 0.71}],
            "virtualCell": {
                "cropChecksumSha256": f"{index:064x}",
                "extractorVersion": "virtual-cell-renderer-source-direct-v4",
                "logicalCellKeySha256": f"{index + 100:064x}",
                "renderSpec": {"cellIndex": index, "paddedSourceQuad": [[0.5, 1.25]] * 4},
                "renderSpecChecksumSha256": f"{index + 200:064x}",
                "renderedPixelChecksumSha256": f"{index:064x}",
            },
        }
        for index in range(15)
    ]


def _old_digest(predictions: list[dict[str, Any]]) -> str:
    """The pre-TASK-0794 ``predictions_digest`` (v1), copied verbatim."""

    canonical = json.dumps(
        list(predictions), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def test_v2_digest_is_the_same_for_the_full_and_the_slim_revision() -> None:
    full = _full()
    slim = slim_predictions(full)
    assert has_virtual_render_spec(full) and not has_virtual_render_spec(slim)
    assert full[0]["virtualCell"]["renderSpec"] == {
        "cellIndex": 0,
        "paddedSourceQuad": [[0.5, 1.25]] * 4,
    }
    assert {key for key in slim[0]["virtualCell"]} == {
        "cropChecksumSha256",
        "extractorVersion",
        "logicalCellKeySha256",
        "renderSpecChecksumSha256",
        "renderedPixelChecksumSha256",
    }
    assert predictions_digest(full) == predictions_digest(slim)
    assert predictions_digest_v1(full) == _old_digest(full)
    assert predictions_digest_v1(full) != predictions_digest(full)
    assert predictions_digest_v1(slim) == predictions_digest(slim)
    # Only renderSpec goes: any other change still changes the digest.
    changed = copy.deepcopy(slim)
    changed[3]["virtualCell"]["renderSpecChecksumSha256"] = "f" * 64
    assert predictions_digest(changed) != predictions_digest(slim)


def test_a_planned_digest_matches_v2_v1_or_the_kept_legacy_digest() -> None:
    full = _full()
    slim = slim_predictions(full)
    v1 = _old_digest(full)
    v2 = predictions_digest(full)
    assert predictions_match(full, legacy_predictions_sha256=None, expected_sha256=v1)
    assert predictions_match(full, legacy_predictions_sha256=None, expected_sha256=v2)
    assert predictions_match(slim, legacy_predictions_sha256=v1, expected_sha256=v1)
    assert predictions_match(slim, legacy_predictions_sha256=v1, expected_sha256=v2)
    assert not predictions_match(slim, legacy_predictions_sha256=None, expected_sha256=v1)
    assert not predictions_match(slim, legacy_predictions_sha256=v1, expected_sha256="0" * 64)


def test_new_revisions_reject_a_render_spec_copy() -> None:
    with pytest.raises(PredictionRevisionShapeError) as raised:
        require_slim_predictions(_full())
    assert raised.value.code == "PREDICTION_REVISION_RENDER_SPEC_PRESENT"
    with pytest.raises(PredictionRevisionShapeError):
        ImageSymbolPredictionRevisionModel(predictions=_full())
    slim = slim_predictions(_full())
    assert ImageSymbolPredictionRevisionModel(predictions=slim).predictions == slim
    with pytest.raises(PredictionRevisionShapeError) as invalid:
        require_slim_predictions({"cells": []})
    assert invalid.value.code == "PREDICTION_REVISION_PREDICTIONS_INVALID"


class _Session:
    """Answers the lock queries of apply/revert in call order."""

    def __init__(self, scalars: list[object], revisions: dict[object, object]) -> None:
        self._scalars = scalars
        self._revisions = revisions

    def scalar(self, _statement: object) -> object:
        return self._scalars.pop(0)

    def get(self, _model: object, identity: object) -> object:
        return self._revisions.get(identity)

    def scalars(self, _statement: object) -> list[object]:
        return []


def _plan(revision_id: object, digest: str) -> BoardPlan:
    return BoardPlan(
        review_item_id=uuid4(),
        recognized_board_id=uuid4(),
        prediction_revision_id=revision_id,  # type: ignore[arg-type]
        predictions_sha256=digest,
        targets=(
            TargetCell(
                cell_review_id=uuid4(),
                cell_index=7,
                rendered_pixel_checksum_sha256=f"{7:064x}",
                old_symbol="ARBUZ",
                new_symbol="CYTRYNA",
                shape_votes=9,
                combined_votes=10,
            ),
        ),
    )


def _revision(
    predictions: list[dict[str, Any]], *, legacy: str | None, **values: object
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        predictions=predictions,
        legacy_predictions_sha256=legacy,
        model_version="symbol-model-v7",
        model_checksum_sha256="a" * 64,
        crop_manifest_checksum_sha256="c" * 64,
        source_job_id=uuid4(),
        model_iteration_id=uuid4(),
        **values,
    )


@pytest.mark.parametrize("digest_version", ("v1", "v2"))
@pytest.mark.parametrize("slimmed", (False, True))
def test_apply_accepts_v1_and_v2_manifests_and_writes_a_slim_revision(
    monkeypatch: pytest.MonkeyPatch, digest_version: str, slimmed: bool
) -> None:
    full = _full()
    legacy = _old_digest(full)
    latest = _revision(
        slim_predictions(full) if slimmed else full, legacy=legacy if slimmed else None
    )
    digest = legacy if digest_version == "v1" else predictions_digest(full)
    plan = _plan(latest.id, digest)
    written: list[ImageSymbolPredictionRevisionModel] = []

    def write(_session: object, **kwargs: Any) -> None:
        written.append(kwargs["revision"])

    monkeypatch.setattr(writer, "_lock_cells", lambda *_a, **_k: _target_cells(plan, latest))
    monkeypatch.setattr(writer, "_write_revision", write)
    session = _Session([object(), object(), latest, None], {})

    result = apply_board(
        session,  # type: ignore[arg-type]
        game_id=uuid4(),
        plan=plan,
        library_checksum_sha256="b" * 64,
    )

    assert result == "applied"
    assert len(written) == 1
    assert not has_virtual_render_spec(written[0].predictions)
    assert written[0].predictions[7]["symbolCode"] == "CYTRYNA"
    assert written[0].crop_manifest_checksum_sha256 == latest.crop_manifest_checksum_sha256


def test_apply_refuses_a_slimmed_revision_without_its_legacy_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    full = _full()
    latest = _revision(slim_predictions(full), legacy=None)
    plan = _plan(latest.id, _old_digest(full))
    monkeypatch.setattr(writer, "_write_revision", lambda *_a, **_k: None)
    session = _Session([object(), object(), latest], {})
    assert (
        apply_board(
            session,  # type: ignore[arg-type]
            game_id=uuid4(),
            plan=plan,
            library_checksum_sha256="b" * 64,
        )
        == "stale:predictions_changed"
    )


@pytest.mark.parametrize("digest_version", ("v1", "v2"))
def test_revert_finds_its_slimmed_anchor_and_restores_a_slim_copy(
    monkeypatch: pytest.MonkeyPatch, digest_version: str
) -> None:
    full = _full()
    legacy = _old_digest(full)
    # The anchor (replaced model revision) was slimmed after the run.
    previous = _revision(slim_predictions(full), legacy=legacy)
    library_checksum = "b" * 64
    library = _revision(slim_predictions(full), legacy=None)
    library.model_version = MODEL_VERSION
    library.model_checksum_sha256 = library_checksum
    digest = legacy if digest_version == "v1" else predictions_digest(full)
    plan = _plan(previous.id, digest)
    written: list[ImageSymbolPredictionRevisionModel] = []

    def write(_session: object, **kwargs: Any) -> None:
        written.append(kwargs["revision"])

    monkeypatch.setattr(writer, "_write_revision", write)
    session = _Session([object(), object(), library, None], {previous.id: previous})

    result = revert_board(
        session,  # type: ignore[arg-type]
        game_id=uuid4(),
        plan=plan,
        library_checksum_sha256=library_checksum,
    )

    assert result == "reverted"
    assert written[0].model_checksum_sha256 == revert_checksum(library_checksum)
    assert written[0].predictions == slim_predictions(full)


def test_revert_of_a_full_anchor_writes_the_slim_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    full = _full()
    previous = _revision(full, legacy=None)
    library = _revision(slim_predictions(full), legacy=None)
    library.model_version = MODEL_VERSION
    library.model_checksum_sha256 = "b" * 64
    written: list[ImageSymbolPredictionRevisionModel] = []
    monkeypatch.setattr(
        writer, "_write_revision", lambda _s, **kwargs: written.append(kwargs["revision"])
    )
    session = _Session([object(), object(), library, None], {previous.id: previous})
    assert (
        revert_board(
            session,  # type: ignore[arg-type]
            game_id=uuid4(),
            plan=_plan(previous.id, _old_digest(full)),
            library_checksum_sha256="b" * 64,
        )
        == "reverted"
    )
    assert not has_virtual_render_spec(written[0].predictions)


def _target_cells(plan: BoardPlan, latest: SimpleNamespace) -> dict[object, object]:
    target = plan.targets[0]
    return {
        target.cell_review_id: SimpleNamespace(
            id=target.cell_review_id,
            cell_index=target.cell_index,
            review_state="pending",
            assignment_source="model",
            quality_issue=None,
            rendered_pixel_checksum_sha256=target.rendered_pixel_checksum_sha256,
            prediction_revision_id=latest.id,
            prediction_symbol_code=target.old_symbol,
        )
    }
