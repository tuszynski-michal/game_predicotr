"""Actual oracle + SQL readers + CPU observer; never operator qualification evidence."""

from copy import deepcopy
from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from game_predictor_api.domain.grid_cell_content import (
    ContentRevision,
    ContentTarget,
    oracle_qualification,
)
from game_predictor_api.domain.grid_content_repeatability import repeatability_report
from game_predictor_api.domain.grid_training_cohorts import digest
from game_predictor_api.storage.grid_cell_content_models import (
    GridCellContentRevisionModel as Revision,
)
from game_predictor_api.storage.grid_cell_content_models import (
    GridCellContentSessionModel as Measurement,
)
from game_predictor_api.storage.grid_cell_content_pins import content_pin
from game_predictor_api.storage.production_crop_capture import _measurement
from game_predictor_worker.images.grid_cell_content_reference import run_blind_content_oracle
from game_predictor_worker.images.grid_content_experiment_data import require_render_preflight
from game_predictor_worker.images.normalization import rgb_pixel_checksum_sha256
from game_predictor_worker.images.production_cell_run import ProductionContentRun
from game_predictor_worker.images.production_crop_artifacts import sealed
from game_predictor_worker.images.production_crop_comparison import run_comparison
from sqlalchemy import JSON, Column, MetaData, Table, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session
from test_production_cell_frozen_pipeline import frozen_fixture
from test_production_crop_comparison import setup


def blocked_fixture(tmp_path):
    snapshot, capture, engine, frame, target, nodes, context = setup(tmp_path, role="A")
    game, session_id = UUID(snapshot.manifest["gameId"]), uuid4()
    # Real SQL queries/JSON readers, a small file DB, no PostgreSQL-specific RLS claim.
    sql = create_engine("sqlite:///" + str(tmp_path / "measurement.sqlite"))
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
    metadata.create_all(sql)
    targets, first, second, records, oracle_rows, contexts = [], [], [], [], [], {}
    progress = {"pass1": {}, "pass2": {}}
    for index in range(30):
        pixels = frame.rgb.copy()
        pixels[0, 0, 0] = index
        sha = rgb_pixel_checksum_sha256(pixels)
        actual_frame = replace(
            frame, source=replace(frame.source, normalized_pixel_checksum_sha256=sha), rgb=pixels
        )
        original = deepcopy(target["contentAnnotation"])
        source_id = UUID(original["source"]["sourceId"]) if index == 0 else uuid4()
        original["source"].update(sourceId=str(source_id), sourceRepresentativeSha256=sha)
        original["reference"]["sourceRepresentativeSha256"] = sha
        original.update(
            origin="manual_blind", sessionId=str(session_id), measuredNodes=nodes.tolist()
        )
        pair = []
        for number in (1, 2):
            original["reference"]["revision"] = number
            original["passNumber"] = number
            annotation = ContentRevision.model_validate(original)
            oracle = (
                run_blind_content_oracle(actual_frame, annotation, context) if number == 2 else None
            )
            pair.append(annotation)
            records.append(
                Revision(
                    game_id=game,
                    source_id=source_id,
                    live_source_image_id=source_id,
                    pixel_sha256=sha,
                    position_index=0,
                    revision=number,
                    document=annotation.model_dump(mode="json"),
                    document_sha256=annotation.sha256,
                    oracle=oracle,
                )
            )
            progress[f"pass{number}"][f"{sha}:0"] = number
        first.append(pair[0])
        second.append(pair[1])
        targets.append(
            ContentTarget(
                gameId=game,
                source=pair[1].source,
                positionIndex=0,
                sequenceNumber=1,
                role="A",
                fullPhoto=False,
                targetSha256="a" * 64,
                roleProofSha256="b" * 64,
            )
        )
        assert oracle["state"] == "render_contract_blocked"
        contexts[f"{sha}:0"] = context
        oracle_rows.append(
            {
                "contentReferenceSha256": pair[1].sha256,
                "oracleSha256": oracle["sha256"],
                "state": oracle["state"],
            }
        )
    repeatability = repeatability_report(targets, first, second, [game])
    assert repeatability["state"] == "ready"
    qualification = oracle_qualification([o["state"] for o in oracle_rows])
    summary = {k: v for k, v in qualification.items() if k != "qualificationState"}
    summary["referencesSha256"] = digest(oracle_rows)
    body = {
        **{k: v for k, v in repeatability.items() if k != "sha256"},
        "oracle": summary,
        "qualificationState": qualification["qualificationState"],
    }
    report = {**body, "sha256": digest(body)}
    with Session(sql) as session, session.begin():
        session.add_all(records)
        session.add(
            Measurement(
                game_id=game,
                id=session_id,
                cohort_id=uuid4(),
                revision=3,
                phase="frozen",
                document={
                    "targets": [t.model_dump(mode="json") for t in targets],
                    "oracleContexts": contexts,
                },
                progress=progress,
                report=report,
            )
        )
    return sql, game, session_id, snapshot, capture, engine, target, report


def test_actual_clipping_remains_unqualified_but_can_be_diagnosed(tmp_path):
    sql, game, session_id, snapshot, capture, engine, target, report = blocked_fixture(tmp_path)
    try:
        source = capture["photos"][0]["frozenSource"]["sourceIdentity"]
        source = {**source, "id": capture["photos"][0]["sourceId"]}
        with Session(sql) as session:
            assert _measurement(session, game, {str(session_id)}) == report
            assert content_pin(session, game, source, target, purpose="A") == {}
            diagnostic = content_pin(
                session, game, source, target, purpose="A", diagnostic_mode="render-clipping-only"
            )
            assert diagnostic["contentOracle"]["state"] == "render_contract_blocked"
        target.update(diagnostic)
        ref = target["productionContentReference"]
        ref["measurement"] = {"sessionId": str(session_id), "report": report}
        ref["sha256"] = digest({k: v for k, v in ref.items() if k != "sha256"})
        capture["measurement"] = report
        capture["photos"][0]["measurement"] = report
        capture = sealed({k: v for k, v in capture.items() if k != "sha256"})
        result = run_comparison(
            snapshot,
            capture,
            root=tmp_path / "out",
            repository_root=tmp_path,
            artifact_root=tmp_path,
            engine=engine,
        )
        assert result["state"] == "candidate"
        assert result["diagnosticOnly"] is True and result["qualificationAllowed"] is False
        assert result["photos"][0]["measurementQualificationState"] == "render_contract_blocked"
        assert result["photos"][0]["measurementUse"] == "repeatability-only-render-blocked"
        assert report["qualificationState"] == "render_contract_blocked"

        def configure(_fixture, rows, split):
            for source in rows:
                for frozen_target in source["targets"]:
                    frozen_pin = frozen_target["productionContentReference"]
                    if frozen_pin["measurement"] is not None:
                        frozen_pin["measurement"]["report"] = report
                        frozen_pin["sha256"] = digest(
                            {k: v for k, v in frozen_pin.items() if k != "sha256"}
                        )

        _, training_snapshot, _ = frozen_fixture(tmp_path / "training", configure=configure)
        assert (
            "CONTENT_MEASUREMENT_NOT_EVALUABLE" in ProductionContentRun(training_snapshot).reasons
        )
        with pytest.raises(ValueError, match="CONTENT_SELECTION_REFERENCE_NOT_EVALUABLE"):
            require_render_preflight([training_snapshot])
        assert (
            target["productionContentReference"]["sourceContext"]["renderConfiguration"][
                "paddingFraction"
            ]
            == 0.08
        )
    finally:
        sql.dispose()


@pytest.mark.parametrize(
    "defect", ["missing_oracle", "unknown", "wrong_context", "stale", "bad_pair"]
)
def test_diagnostic_exception_rejects_missing_unknown_stale_or_unbound_evidence(tmp_path, defect):
    sql, game, session_id, *_ = blocked_fixture(tmp_path)
    try:
        with Session(sql) as session, session.begin():
            measured = session.get(Measurement, (game, session_id))
            raw_target = measured.document["targets"][0]
            sha = raw_target["source"]["sourceRepresentativeSha256"]
            row = session.get(Revision, (game, sha, 0, 2))
            oracle = deepcopy(row.oracle)
            if defect == "missing_oracle":
                row.oracle = None
            elif defect == "unknown":
                oracle["cells"][0]["state"] = "not_evaluable"
                oracle["sha256"] = digest({k: v for k, v in oracle.items() if k != "sha256"})
                row.oracle = oracle
            elif defect == "wrong_context":
                oracle["renderConfiguration"]["paddingFraction"] = 0
                oracle["sha256"] = digest({k: v for k, v in oracle.items() if k != "sha256"})
                row.oracle = oracle
            elif defect == "bad_pair":
                session.delete(session.get(Revision, (game, sha, 0, 1)))
            else:
                session.add(
                    Revision(
                        game_id=game,
                        pixel_sha256=sha,
                        position_index=0,
                        revision=3,
                        source_id=row.source_id,
                        document=row.document,
                        document_sha256=row.document_sha256,
                    )
                )
        with Session(sql) as session:
            assert _measurement(session, game, {str(session_id)}) is None
    finally:
        sql.dispose()


def test_global_measurement_prefers_unique_ready_but_exact_scope_stays_blocked(tmp_path):
    sql, game, session_id, *rest = blocked_fixture(tmp_path)
    blocked = rest[-1]
    ready_id = uuid4()
    ready = deepcopy(blocked)
    ready["qualificationState"] = "ready"
    ready["sha256"] = digest({k: v for k, v in ready.items() if k != "sha256"})
    try:
        with Session(sql) as session, session.begin():
            row = session.get(Measurement, (game, session_id))
            session.add(
                Measurement(
                    game_id=game,
                    id=ready_id,
                    cohort_id=row.cohort_id,
                    revision=3,
                    phase="frozen",
                    document={},
                    progress={},
                    report=ready,
                )
            )
        with Session(sql) as session:
            assert _measurement(session, game) == ready
            assert _measurement(session, game, {str(session_id)}) == blocked
            assert _measurement(session, game, {str(ready_id)}) == ready
            assert _measurement(session, game, {str(ready_id), str(session_id)}) is None
    finally:
        sql.dispose()


def test_v2_technical_oracle_failure_has_specific_error_not_contract_drift(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from game_predictor_api.domain.grid_cell_content import ContentError, ContentSource
    from game_predictor_api.schemas.grid_cell_content import ContentSessionAdvance
    from game_predictor_api.storage import grid_content_oracle_context
    from game_predictor_api.storage.grid_cell_content import SqlAlchemyGridCellContentRepository

    sql, game, identifier, *_ = blocked_fixture(tmp_path)
    monkeypatch.setattr(
        grid_content_oracle_context, "require_current_evaluation_contract", lambda *a: None
    )
    try:
        with Session(sql) as session, session.begin():
            measured = session.get(Measurement, (game, identifier))
            measured.phase = "pass2"
            measured.document = {
                **measured.document,
                "evaluationContract": {"test": "pinned"},
                "manifestSha256": "a" * 64,
            }
            raw = measured.document["targets"][0]
            row = session.get(Revision, (game, raw["source"]["sourceRepresentativeSha256"], 0, 2))
            body = {
                "version": "production-cell-content-oracle-v1",
                "state": "render_contract_blocked",
                "reasonCode": "SOURCE_PIXELS_UNAVAILABLE",
                "contentReferenceSha256": row.document_sha256,
            }
            row.oracle = {**body, "sha256": digest(body)}
        with Session(sql) as session:
            repo = SqlAlchemyGridCellContentRepository(session, tmp_path)
            repo.bind = lambda *a, **kw: None
            repo.lock = lambda *a, **kw: None
            repo.begin_command = lambda *a, **kw: None
            repo.snapshot = lambda *a: SimpleNamespace()
            measured = session.get(Measurement, (game, identifier))
            sources = {
                UUID(t["source"]["sourceId"]): ContentSource.model_validate(t["source"])
                for t in measured.document["targets"]
            }
            repo.current_source = lambda game, source, **kw: sources[source]
            with pytest.raises(ContentError) as error:
                repo.advance(
                    game,
                    identifier,
                    ContentSessionAdvance(idempotencyKey=uuid4(), expectedSessionRevision=3),
                    "local-owner",
                )
            assert error.value.code == "CONTENT_ORACLE_RENDER_UNAVAILABLE"
            assert "SOURCE_PIXELS_UNAVAILABLE" in str(error.value)
            saved = session.get(Revision, (game, raw["source"]["sourceRepresentativeSha256"], 0, 2))
            assert "renderConfiguration" not in saved.oracle
    finally:
        sql.dispose()
