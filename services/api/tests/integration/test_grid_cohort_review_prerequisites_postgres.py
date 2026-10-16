"""Two-source proof of real projection readiness, issue and case-A revert guards."""

import copy
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from _application_role_database import application_role_database
from game_predictor_api.application.geometry_correction_reverts import (
    GeometryCorrectionRevertService,
    VirtualRestoredRenderVerifier,
)
from game_predictor_api.application.image_symbol_review_mutations import (
    SymbolCellReviewMutationService,
)
from game_predictor_api.application.virtual_grid_geometry import (
    VirtualGridGeometryService,
    VirtualGridGeometrySourceCommand,
)
from game_predictor_api.domain.image_geometry_completeness import SourceImageGeometryStatus
from game_predictor_api.domain.image_geometry_v2 import SourceLatticeNodes, SourcePoint
from game_predictor_api.domain.image_reviews import ImageReviewGeometryPoint
from game_predictor_api.domain.image_symbol_reviews import SymbolCellReviewError
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.geometry_correction_revert_repository import (
    SqlAlchemyGeometryCorrectionRevertRepository,
)
from game_predictor_api.storage.image_symbol_review_repository import (
    SqlAlchemyImageSymbolReviewRepository,
    SqlAlchemySymbolCellReviewMutationRepository,
)
from game_predictor_api.storage.models import SourceImageModel, SymbolModel
from game_predictor_api.storage.virtual_grid_geometry_repository import (
    SqlAlchemyVirtualGridGeometryRepository,
)
from sqlalchemy import text
from test_grid_training_cohort_e2e_postgres import (
    _check_cleanup,
    _nodes,
    _save_source,
    _write_pattern,
)
from test_source_recording_groups_postgres import seed_source
from test_virtual_deferred_resolution_postgres import _factory

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit exact-owned two-source prerequisite fixture only",
)


def _plain_source(db, root, game):
    factory = _factory(db.owner_engine)
    with patch("test_virtual_deferred_resolution_postgres._write_source", _write_pattern):
        seed = seed_source(
            factory, game, root, label="plain-first", slot_count=1, sequence_base=100
        )
    nodes = _nodes(0)
    with game_storage_scope(game), factory.begin() as session:
        source = session.get(SourceImageModel, seed.source_image_id)
        command = VirtualGridGeometrySourceCommand(
            review_item_id=None,
            pending_geometry_id=seed.pending_ids[0],
            expected_geometry_revision=0,
            expected_resolution_revision=0,
            expected_source_checksum_sha256=source.checksum_sha256,
            expected_source_width=source.oriented_width,
            expected_source_height=source.oriented_height,
            expected_grid_rows=3,
            expected_grid_columns=5,
            corners=tuple(
                ImageReviewGeometryPoint(round(nodes[i].x), round(nodes[i].y))
                for i in (0, 5, 23, 18)
            ),
            lattice_nodes=SourceLatticeNodes(nodes),
            # Ordinary full-board case A. No optional qualification is
            # submitted or erased after publication.
        )
        result = VirtualGridGeometryService(
            SqlAlchemyVirtualGridGeometryRepository(session), root
        ).save_source(
            game_id=game,
            import_job_id=seed.import_job_id,
            commands=(command,),
            idempotency_key=uuid4(),
            actor="fixture-human:0995-prerequisite",
            created_at=datetime.now(UTC),
        )
        assert result.created and result.revisions[0].revision == 1
    return seed.source_image_id, seed.import_job_id, [[point.x, point.y] for point in nodes]


def _plain_recorrect(db, root, game, job, source):
    with game_storage_scope(game), _factory(db.app_engine).begin() as session:
        row = session.execute(
            text(
                "SELECT i.id,i.resolution_revision,b.geometry_revision,b.geometry_qualification "
                "FROM image_review_items i JOIN recognized_boards b "
                "ON b.game_id=i.game_id AND b.id=i.recognized_board_id "
                "WHERE b.game_id=:g AND b.source_image_id=:s"
            ),
            {"g": game, "s": source},
        ).one()
        assert row.geometry_revision == 1 and row.geometry_qualification is None
        nodes = list(_nodes(0))
        nodes[8] = SourcePoint(nodes[8].x + 0.25, nodes[8].y)
        result = VirtualGridGeometryService(
            SqlAlchemyVirtualGridGeometryRepository(
                session,
                source_snapshot_policy="current_live_slots",
            ),
            root,
        ).save_review_item(
            game_id=game,
            import_job_id=job,
            review_item_id=row.id,
            idempotency_key=uuid4(),
            expected_geometry_revision=1,
            expected_resolution_revision=row.resolution_revision,
            corners=tuple(
                ImageReviewGeometryPoint(round(nodes[i].x), round(nodes[i].y))
                for i in (0, 5, 23, 18)
            ),
            lattice_nodes=SourceLatticeNodes(tuple(nodes)),
            actor="fixture-human:0995-prerequisite",
            created_at=datetime.now(UTC),
        )
        assert result.created and result.revision.revision == 2


def _actual_issue(session, game, source):
    cell = (
        session.execute(
            text(
                "SELECT c.id,c.revision,c.geometry_revision,"
                "c.crop_sample_id,c.crop_checksum_sha256 "
                "FROM image_symbol_review_cells c JOIN recognized_boards b "
                "ON b.game_id=c.game_id AND b.id=c.recognized_board_id "
                "WHERE b.game_id=:g AND b.source_image_id=:s ORDER BY c.cell_index LIMIT 1"
            ),
            {"g": game, "s": source},
        )
        .mappings()
        .one()
    )
    return SymbolCellReviewMutationService(
        SqlAlchemySymbolCellReviewMutationRepository(
            session,
        )
    ).mark_grid_issue(
        game_id=game,
        cell_review_id=cell["id"],
        expected_revision=cell["revision"],
        expected_geometry_revision=cell["geometry_revision"],
        expected_crop_sample_id=cell["crop_sample_id"],
        expected_crop_checksum_sha256=cell["crop_checksum_sha256"],
        actor="fixture-human:0995-prerequisite",
    )


def _real_projection(factory, game, checkpoint):
    with game_storage_scope(game), factory.begin() as session:
        report = SqlAlchemyImageSymbolReviewRepository(session).start_or_resume_backfill(game)
        assert report.status == "rebuilding"
    for index in range(4):
        with game_storage_scope(game), factory.begin() as session:
            step = SqlAlchemyImageSymbolReviewRepository(session).backfill_next_batch(
                game,
                batch_size=10,
                finalize_when_exhausted=False,
            )
        assert step.report.status != "failed", step.report
        checkpoint(f"actual_backfill_{index}")
        if not step.has_more:
            break
    else:
        pytest.fail("The two-board backfill exceeded its bounded batch count")
    with game_storage_scope(game), factory.begin() as session:
        SqlAlchemyImageSymbolReviewRepository(session).begin_reconciliation_pass(game)
    for index in range(4):
        with game_storage_scope(game), factory.begin() as session:
            step = SqlAlchemyImageSymbolReviewRepository(session).reconcile_next_batch(
                game,
                batch_size=10,
            )
        assert step.report.status != "failed", step.report
        checkpoint(f"actual_reconciliation_{index}")
        if not step.has_more:
            break
    else:
        pytest.fail("The two-board reconciliation exceeded its bounded batch count")
    with game_storage_scope(game), factory.begin() as session:
        report = SqlAlchemyImageSymbolReviewRepository(session).finalize_backfill(game)
        assert report.status == "ready", report
    for index in range(4):
        with game_storage_scope(game), factory.begin() as session:
            ready = SqlAlchemyImageSymbolReviewRepository(
                session
            ).ensure_current_count_projection_next_batch(
                game,
                batch_size=100,
            )
        checkpoint(f"actual_count_publication_{index}")
        if ready:
            break
    else:
        pytest.fail("The thirty-cell count publication exceeded its bounded batch count")
    with game_storage_scope(game), factory() as session:
        state = session.execute(
            text(
                "SELECT status,count_projection_status,count_projection "
                "FROM image_symbol_review_states "
                "WHERE game_id=:g"
            ),
            {"g": game},
        ).one()
        assert state[0] == state[1] == "ready" and state[2]["_semantics"] == {"version": 2}
    return {"status": state[0], "countStatus": state[1], "countProjection": state[2]}


def test_exact_owned_real_review_projection_issue_and_revert(monkeypatch):
    evidence = (
        Path(__file__).resolve().parents[4]
        / "artifacts/audits"
        / ("TASK-0995_REVIEW_PREREQUISITE_" + uuid4().hex)
    )
    evidence.mkdir(parents=True)
    monkeypatch.setenv("GAME_PREDICTOR_RECORDING_TEST_RESOURCE_ROOT", str(evidence / "resources"))
    started, progress, retained = time.monotonic(), [], None

    def checkpoint(label):
        elapsed = round(time.monotonic() - started, 3)
        progress.append({"phase": label, "elapsedSeconds": elapsed})
        (evidence / "progress.json").write_text(json.dumps(progress, indent=2), encoding="utf-8")
        print(f"0995 prerequisite {label} {elapsed}s", flush=True)
        assert elapsed < 60, "The two-source prerequisite fixture exceeded its soft budget"

    try:
        with application_role_database("t0995e", ("cohort-review-prerequisite",)) as db:
            retained = db
            checkpoint("fixture_ready")
            game = next(iter(db.games.values()))
            with db.owner_engine.begin() as connection:
                connection.execute(
                    text(
                        "UPDATE public.games SET shape_geometry_configuration='neural_grid_v3' "
                        "WHERE id=:g"
                    ),
                    {"g": game},
                )
            with game_storage_scope(game), _factory(db.owner_engine).begin() as session:
                for index, code in enumerate(("CYTRYNA", "WISNIA"), 1):
                    session.add(
                        SymbolModel(
                            game_id=game,
                            code=code,
                            name=code,
                            mobile_code=index,
                            display_order=index,
                            status="active",
                        )
                    )
            expected = {}
            first, first_job, baseline_nodes = _plain_source(db, evidence, game)
            second, _, _ = _save_source(db, evidence, game, 1, 1, expected)
            checkpoint("two_actual_manual_sources")
            factory = _factory(db.app_engine)
            with game_storage_scope(game), factory() as session:
                with pytest.raises(SymbolCellReviewError) as rejected:
                    _actual_issue(session, game, second)
                assert rejected.value.code == "SYMBOL_CELL_REVIEW_PROJECTION_INCOMPLETE"
                session.rollback()
            checkpoint("rebuilding_guard_reproduced_without_neural_bypass")
            projection = _real_projection(factory, game, checkpoint)
            (evidence / "projection.json").write_text(
                json.dumps(projection, indent=2), encoding="utf-8"
            )
            baseline_nodes = copy.deepcopy(baseline_nodes)
            _plain_recorrect(db, evidence, game, first_job, first)
            checkpoint("actual_existing_board_revision_1_to_2")
            with game_storage_scope(game), factory.begin() as session:
                issue = _actual_issue(session, game, second)
                assert issue.has_grid_issue and issue.quality_issue.value == "grid_issue"
            checkpoint("actual_issue_after_real_ready_projection")
            with game_storage_scope(game), factory.begin() as session:
                service = GeometryCorrectionRevertService(
                    SqlAlchemyGeometryCorrectionRevertRepository(session),
                    render_verifier=VirtualRestoredRenderVerifier(evidence),
                )
                entries = service.list_recent(game_id=game, import_job_id=first_job)
                assert entries and entries[0].geometry_revision == 2
                preview = service.preview(
                    game_id=game,
                    import_job_id=first_job,
                    board_geometry_revision_id=entries[0].board_geometry_revision_id,
                )
                entry = preview.correction
                proof = {
                    "kind": entry.kind.value,
                    "revertable": entry.revertable,
                    "blockingReason": None
                    if entry.blocking_reason is None
                    else entry.blocking_reason.value,
                    "restoredSourceGeometryRevisionId": str(
                        preview.restored_source_geometry_revision_id
                    ),
                }
                (evidence / "preview.json").write_text(
                    json.dumps(proof, indent=2), encoding="utf-8"
                )
                assert entry.revertable, proof
                reverted = service.revert(
                    game_id=game,
                    import_job_id=first_job,
                    board_geometry_revision_id=entry.board_geometry_revision_id,
                    idempotency_key=uuid4(),
                    expected_geometry_revision=entry.geometry_revision,
                    expected_resolution_revision=entry.resolution_revision,
                    actor="fixture-human:0995-prerequisite",
                    reverted_at=datetime.now(UTC),
                )
                assert reverted.created and reverted.kind.value == "board_revision"
                assert reverted.restored_geometry_revision == 3
                assert reverted.restored_cell_decision_count == 15
                assert (
                    reverted.source_image_geometry_status
                    is SourceImageGeometryStatus.GEOMETRY_COMPLETE
                )
            checkpoint("actual_case_a_revert_committed")
            with game_storage_scope(game), factory() as session:
                geometry = session.scalar(
                    text(
                        "SELECT board_geometry FROM recognized_boards "
                        "WHERE game_id=:g AND source_image_id=:s"
                    ),
                    {"g": game, "s": first},
                )
                assert geometry["latticeNodes"] == [{"x": x, "y": y} for x, y in baseline_nodes]
                assert (
                    session.scalar(
                        text(
                            "SELECT count(*) FROM image_geometry_correction_reverts "
                            "WHERE game_id=:g"
                        ),
                        {"g": game},
                    )
                    == 1
                )
            checkpoint("restart_restored_exact_nodes")
    finally:
        _check_cleanup(retained, evidence)
