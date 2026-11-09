"""Actual SQL selectors exercise current labels, independently of model resolution."""

from copy import deepcopy
from uuid import UUID, uuid4

import pytest
from game_predictor_api.domain.grid_cell_content import ContentError
from game_predictor_api.domain.grid_training_cohorts import digest
from game_predictor_api.storage.grid_cell_content_models import (
    GridCellContentRevisionModel as Revision,
)
from game_predictor_api.storage.grid_cell_content_models import (
    GridCellContentSessionModel as Measurement,
)
from game_predictor_api.storage.grid_cell_content_pins import content_pin
from game_predictor_api.storage.grid_render_selection import select_a_render_contract
from sqlalchemy import JSON, Column, MetaData, Table, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session
from test_grid_cell_content import revision, target
from test_grid_render_reference import pin


@pytest.fixture
def sql_selection(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///" + str(tmp_path / "selection.sqlite"))
    metadata = MetaData()
    for model in (Revision, Measurement):
        Table(
            model.__tablename__,
            metadata,
            *[
                Column(
                    c.name,
                    JSON() if isinstance(c.type, JSONB) else c.type,
                    primary_key=c.primary_key,
                )
                for c in model.__table__.columns
            ],
        )
    metadata.create_all(engine)
    game, identifier = UUID(int=1), uuid4()
    contract = pin(monkeypatch, tmp_path)
    targets = [target(i, 0, "A", game=game) for i in (1, 2)]
    progress = {"pass1": {}, "pass2": {}}
    with Session(engine) as session, session.begin():
        for t in targets:
            annotation = revision(t, 2).model_copy(update={"sessionId": identifier})
            progress["pass2"][f"{t.source.sourceRepresentativeSha256}:0"] = 2
            session.add(
                Revision(
                    game_id=game,
                    pixel_sha256=t.source.sourceRepresentativeSha256,
                    position_index=0,
                    revision=2,
                    source_id=t.source.sourceId,
                    document=annotation.model_dump(mode="json"),
                    document_sha256=annotation.sha256,
                )
            )
        body = {"state": "ready", "qualificationState": "ready", "evaluationContract": contract}
        session.add(
            Measurement(
                game_id=game,
                id=identifier,
                cohort_id=uuid4(),
                revision=3,
                phase="frozen",
                document={"evaluationContract": contract},
                progress=progress,
                report={**body, "sha256": digest(body)},
            )
        )
    # Selection SQL is real; full resolver has dedicated pin and PG integration tests.
    monkeypatch.setattr(
        "game_predictor_api.storage.grid_render_selection.require_current_evaluation_contract",
        lambda *a: None,
    )
    split = {
        "sources": [
            {
                "sourceId": str(t.source.sourceId),
                "pixelSha256": t.source.sourceRepresentativeSha256,
                "validationPurpose": "A",
                "representative": True,
                "eligibleBoards": 1,
            }
            for t in targets
        ]
    }
    nodes = {str(t.source.sourceId): {0: []} for t in targets}
    yield engine, game, identifier, contract, targets, split, nodes
    engine.dispose()


@pytest.mark.parametrize(
    "case",
    [
        "blank",
        "current_pass1",
        "v1_v2",
        "two_sessions",
        "different_contract",
        "not_ready",
        "old_empty",
    ],
)
def test_current_sql_a_selection(sql_selection, tmp_path, case):
    engine, game, identifier, contract, targets, split, nodes = sql_selection
    with Session(engine) as session, session.begin():
        measured = session.get(Measurement, (game, identifier))
        row = session.get(Revision, (game, targets[1].source.sourceRepresentativeSha256, 0, 2))
        if case == "blank":
            session.delete(row)
        elif case == "current_pass1":
            annotation = revision(targets[1], 1).model_copy(update={"sessionId": identifier})
            annotation = annotation.model_copy(
                update={"reference": annotation.reference.model_copy(update={"revision": 3})}
            )
            session.add(
                Revision(
                    game_id=game,
                    pixel_sha256=row.pixel_sha256,
                    position_index=0,
                    revision=3,
                    source_id=row.source_id,
                    document=annotation.model_dump(mode="json"),
                    document_sha256=annotation.sha256,
                )
            )
        elif case == "not_ready":
            body = {**measured.report, "qualificationState": "render_contract_blocked"}
            body.pop("sha256")
            measured.report = {**body, "sha256": digest(body)}
        else:
            other = uuid4()
            other_contract = deepcopy(contract)
            if case == "different_contract":
                from dataclasses import replace

                from game_predictor_api.domain.symbol_model_snapshots import SymbolModelJobSnapshot

                other_contract["classifier"] = replace(
                    SymbolModelJobSnapshot.from_payload(other_contract["classifier"]),
                    onnx_checksum_sha256="c" * 64,
                ).to_payload()
                other_contract["sha256"] = digest(
                    {k: v for k, v in other_contract.items() if k != "sha256"}
                )
            body = {"state": "ready", "qualificationState": "ready"}
            if case not in ("v1_v2", "old_empty"):
                body["evaluationContract"] = other_contract
            session.add(
                Measurement(
                    game_id=game,
                    id=other,
                    cohort_id=uuid4(),
                    revision=1,
                    phase="pass1" if case == "old_empty" else "frozen",
                    document={}
                    if case in ("v1_v2", "old_empty")
                    else {"evaluationContract": other_contract},
                    progress={"pass1": {}, "pass2": {}}
                    if case == "old_empty"
                    else measured.progress,
                    report=None if case == "old_empty" else {**body, "sha256": digest(body)},
                )
            )
            if case != "old_empty":
                from game_predictor_api.domain.grid_cell_content import ContentRevision

                annotation = ContentRevision.model_validate(row.document).model_copy(
                    update={"sessionId": other}
                )
                row.document, row.document_sha256 = (
                    annotation.model_dump(mode="json"),
                    annotation.sha256,
                )
    with Session(engine) as session:
        if case == "old_empty":
            assert select_a_render_contract(session, tmp_path, game, split, nodes) == contract
        else:
            with pytest.raises(ContentError) as error:
                select_a_render_contract(session, tmp_path, game, split, nodes)
            assert error.value.code == "CONTENT_A_RENDER_SELECTION_REQUIRED"


def test_content_pin_rejects_other_selected_contract(sql_selection):
    engine, game, _, _, targets, *_ = sql_selection
    t = targets[0]
    source = {
        "id": str(t.source.sourceId),
        "checksum_sha256": t.source.sourceSha256,
        "normalized_pixel_checksum_sha256": t.source.sourceRepresentativeSha256,
        "oriented_width": t.source.width,
        "oriented_height": t.source.height,
        "coordinate_space": t.source.coordinateSpace,
        "normalization_adapter_version": t.source.normalizationAdapterVersion,
    }
    with Session(engine) as session, pytest.raises(ContentError) as error:
        content_pin(
            session,
            game,
            source,
            {"positionIndex": 0, "sequenceNumber": t.sequenceNumber},
            purpose="A",
            evaluation_contract={"different": True},
        )
    assert error.value.code == "CONTENT_A_RENDER_SELECTION_REQUIRED"


@pytest.mark.parametrize("mode", ["strict_none", "diagnostic", "wrong_oracle", "wrong_document"])
def test_diagnostic_a_uses_exact_current_v2_measurement_without_overriding_import(
    sql_selection, monkeypatch, mode
):
    from game_predictor_api.storage import production_cell_reference as module
    from game_predictor_api.storage.production_crop_capture import _measurement

    engine, game, identifier, contract, targets, *_ = sql_selection
    t = targets[0]
    source = {
        "id": str(t.source.sourceId),
        "checksum_sha256": t.source.sourceSha256,
        "normalized_pixel_checksum_sha256": t.source.sourceRepresentativeSha256,
        "oriented_width": 200,
        "oriented_height": 120,
        "coordinate_space": t.source.coordinateSpace,
        "normalization_adapter_version": t.source.normalizationAdapterVersion,
    }
    with Session(engine) as session, session.begin():
        measured = session.get(Measurement, (game, identifier))
        body = {
            **measured.report,
            "version": "cell-content-repeatability-v1",
            "quantile": "nearest-rank-p95-v1",
            "games": {str(game): {"state": "ready", "u": 0.0, "delta": 0.0}},
        }
        body.pop("sha256")
        measured.report = {**body, "sha256": digest(body)}
        row = session.get(Revision, (game, t.source.sourceRepresentativeSha256, 0, 2))
        oracle = {
            "contentReferenceSha256": row.document_sha256,
            "renderConfiguration": contract["renderConfiguration"],
            "classifierSnapshotSha256": digest(
                {
                    "classifier": contract["classifier"],
                    "renderConfiguration": contract["renderConfiguration"],
                }
            ),
        }
        if mode == "wrong_oracle":
            oracle["classifierSnapshotSha256"] = "f" * 64
        row.oracle = {**oracle, "sha256": digest(oracle)}
        if mode == "wrong_document":
            measured.document = {}
    with Session(engine) as session:
        args = {} if mode == "strict_none" else {"diagnostic_mode": "render-clipping-only"}
        target = {"positionIndex": 0, "sequenceNumber": t.sequenceNumber}
        if mode != "diagnostic":
            with pytest.raises(ContentError) as error:
                content_pin(session, game, source, target, purpose="A", **args)
            assert error.value.code == (
                "CONTENT_A_RENDER_SELECTION_REQUIRED"
                if mode == "strict_none"
                else "CONTENT_ORACLE_CONTRACT_CHANGED"
            )
        else:
            target.update(content_pin(session, game, source, target, purpose="A", **args))
            selected = _measurement(session, game, {str(identifier)})
            assert selected["evaluationContract"] == contract
            imported = {
                "state": "available",
                "classifier": {"historical": "import8"},
                "renderConfiguration": {"paddingFraction": 0.08},
            }
            monkeypatch.setattr(module, "capture_oracle_context", lambda *a, **kw: imported)
            captured = module.capture_production_reference(session, game, source, target)
            assert captured["sourceContext"] == imported
            assert captured["measurement"]["report"] == selected
            assert (
                captured["measurement"]["report"]["evaluationContract"]["renderConfiguration"][
                    "paddingFraction"
                ]
                == 0
            )


@pytest.mark.parametrize("purpose", ["TRAIN", "B", "REGRESSION"])
@pytest.mark.parametrize("available", [True, False])
def test_old_blind_labels_outside_a_survive_v2_capture(
    sql_selection, monkeypatch, purpose, available
):
    from game_predictor_api.domain.grid_render_reference import require_reference_v2
    from game_predictor_api.storage import production_cell_reference as module

    engine, game, identifier, contract, targets, *_ = sql_selection
    t = targets[0]
    source = {
        "id": str(t.source.sourceId),
        "checksum_sha256": t.source.sourceSha256,
        "normalized_pixel_checksum_sha256": t.source.sourceRepresentativeSha256,
        "oriented_width": t.source.width,
        "oriented_height": t.source.height,
        "coordinate_space": t.source.coordinateSpace,
        "normalization_adapter_version": t.source.normalizationAdapterVersion,
    }
    provenance = (
        {
            "state": "available",
            "classifier": {"historic": "v1"},
            "renderConfiguration": {"paddingFraction": 0.08},
        }
        if available
        else {"state": "unavailable", "reasonCode": "CONTENT_ORACLE_PROVENANCE_MISSING"}
    )
    monkeypatch.setattr(module, "capture_oracle_context", lambda *a, **kw: deepcopy(provenance))
    with Session(engine) as session, session.begin():
        measured = session.get(Measurement, (game, identifier))
        measured.document = {}
        measured.report = {"qualificationState": "ready", "historical": "v1"}
        label = {"positionIndex": 0, "sequenceNumber": t.sequenceNumber}
        label.update(
            content_pin(session, game, source, label, purpose=purpose, evaluation_contract=contract)
        )
        before = deepcopy(label)
        frozen = module.capture_production_reference(
            session, game, source, label, evaluation_contract=contract
        )
        assert label == before and "contentAnnotation" in label
        assert frozen["measurement"] is None
        assert frozen["importProvenance"] == provenance
        assert frozen["sourceContext"]["state"] == provenance["state"]
        require_reference_v2(frozen, str(game))
        if not available:
            assert frozen["sourceContext"] == provenance
            with pytest.raises(ContentError) as error:
                module.capture_production_reference(
                    session,
                    game,
                    source,
                    {**label, "blindGeometry": {}},
                    evaluation_contract=contract,
                )
            assert error.value.code == "CONTENT_IMPORT_PROVENANCE_REQUIRED"
