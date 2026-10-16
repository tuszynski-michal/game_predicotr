"""Exact-owned, CPU-only cohort flow through genuine guarded geometry writers."""

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

import numpy as np
import pytest
from _application_role_database import application_role_database
from game_predictor_api.application.geometry_correction_reverts import (
    GeometryCorrectionRevertService,
    VirtualRestoredRenderVerifier,
)
from game_predictor_api.application.grid_training_cohorts import GridTrainingCohortService
from game_predictor_api.application.image_symbol_review_mutations import (
    SymbolCellReviewMutationService,
)
from game_predictor_api.application.virtual_grid_geometry import (
    VirtualGridGeometryService,
    VirtualGridGeometrySourceCommand,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.geometry_qualification import GeometryQualification
from game_predictor_api.domain.grid_model_registry import (
    canonical_json,
    descriptor_sha256,
    historical_catalogue,
    validate_manifest,
)
from game_predictor_api.domain.grid_training_cohorts import GridCohortError
from game_predictor_api.domain.image_geometry_completeness import SourceImageGeometryStatus
from game_predictor_api.domain.image_geometry_v2 import SourceLatticeNodes, SourcePoint
from game_predictor_api.domain.image_reviews import ImageReviewGeometryPoint
from game_predictor_api.domain.source_recording_groups import recording_sha256
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.geometry_correction_revert_repository import (
    SqlAlchemyGeometryCorrectionRevertRepository,
)
from game_predictor_api.storage.grid_model_registry import SqlAlchemyGridModelRegistryRepository
from game_predictor_api.storage.grid_training_cohort_currentness import inspect_member
from game_predictor_api.storage.grid_training_cohort_models import (
    GridTrainingCohortMemberModel,
    GridTrainingCohortModel,
)
from game_predictor_api.storage.grid_training_cohort_repository import (
    SqlAlchemyGridTrainingCohortRepository,
)
from game_predictor_api.storage.image_symbol_review_repository import (
    SqlAlchemySymbolCellReviewMutationRepository,
)
from game_predictor_api.storage.models import SourceImageModel, SymbolModel
from game_predictor_api.storage.source_recording_lab_import import install_provider_proof
from game_predictor_api.storage.source_recording_providers import (
    TrustedRecordingProviders,
    install_recording_provider,
)
from game_predictor_api.storage.virtual_grid_geometry_repository import (
    SqlAlchemyVirtualGridGeometryRepository,
)
from PIL import Image
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool
from test_source_recording_groups_postgres import execute, seed_source
from test_virtual_deferred_resolution_postgres import _factory

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit exact-owned disposable PostgreSQL and twenty generated JPEGs only",
)


def _install_base(db, game):
    family, version = uuid4(), uuid4()
    base = json.loads(json.dumps(historical_catalogue()[0]))
    base.update(
        familyId=str(family), versionId=str(version), familyCode="fixture_e2e_" + family.hex
    )
    descriptor = validate_manifest(base)
    with db.owner_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE public.games SET shape_geometry_configuration='neural_grid_v3' WHERE id=:g"
            ),
            {"g": game},
        )
        connection.execute(
            text(
                "INSERT INTO public.grid_model_families(id,code,descriptor_json) "
                "VALUES(:id,:code,:doc)"
            ),
            {
                "id": family,
                "code": base["familyCode"],
                "doc": canonical_json(
                    {
                        "id": str(family),
                        "code": base["familyCode"],
                        "label": base["familyLabel"],
                    }
                ),
            },
        )
        connection.execute(
            text(
                "INSERT INTO public.grid_model_versions"
                "(id,family_id,version,manifest_json,manifest_sha256) "
                "VALUES(:id,:f,:v,:doc,:sha)"
            ),
            {
                "id": version,
                "f": family,
                "v": base["version"],
                "doc": descriptor,
                "sha": descriptor_sha256(base),
            },
        )
    return version, family


def _nodes(position):
    left, top = 20 + position % 3 * 200, 15 + position // 3 * 130
    return tuple(
        SourcePoint(
            left + column * 34 + (0.375 if row in (1, 2) and column in (2, 3) else 0),
            top + row * 34,
        )
        for row in range(4)
        for column in range(6)
    )


def _write_pattern(artifact_root, relative_path, seed):
    """Produce distinctive pixels before the existing seed attests any identity."""
    path = artifact_root / "data" / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    y, x = np.indices((420, 620))
    pixels = np.stack(
        (
            (x + seed) % 256,
            (3 * y + 7 * seed) % 256,
            (17 * ((x // 13) ^ (y // 11)) + 13 * seed) % 256,
        ),
        axis=-1,
    ).astype(np.uint8)
    assert np.ptp(pixels[:, :, 0]) > 200 and np.ptp(pixels[:, :, 1]) > 200
    Image.fromarray(pixels).save(path, format="JPEG", quality=95)
    return path


def _providers(db, root, version):
    with Session(db.app_engine) as session:
        lineage = SqlAlchemyGridModelRegistryRepository(session).lineage(version)
    index_sha = None
    for ancestor in lineage["ancestors"]:
        payload = {
            "schemaVersion": "recording-ancestor-provider-v1",
            "ancestor": ancestor,
            "complete": True,
            "recordingIdentityAvailable": True,
            "recordingGroups": [],
        }
        source = root / "installed-provider-input.json"
        source.write_text(json.dumps(payload), encoding="utf-8")
        with db.owner_engine.begin() as connection:
            install_provider_proof(connection, payload, recording_sha256(payload))
        index_sha = install_recording_provider(
            root, source, hashlib.sha256(source.read_bytes()).hexdigest(), index_sha
        )
    return TrustedRecordingProviders(root, index_sha)


def _save_source(db, root, game, ordinal, slot_count, expected):
    factory = _factory(db.owner_engine)
    # Only replace the fixture's file producer. Its real canonical loader and
    # source/geometry publication run after these final JPEG bytes exist.
    with patch("test_virtual_deferred_resolution_postgres._write_source", _write_pattern):
        seed = seed_source(
            factory,
            game,
            root,
            label="e2e" + "x" * (ordinal + 1),
            slot_count=slot_count,
            sequence_base=100 + ordinal * 10,
        )
    if ordinal == 0:
        _complete_first_identity(db, root, game, seed.source_image_id)
    with game_storage_scope(game), factory.begin() as session:
        source = session.get(SourceImageModel, seed.source_image_id)
        assert source is not None
        commands = tuple(
            VirtualGridGeometrySourceCommand(
                review_item_id=None,
                pending_geometry_id=pending,
                expected_geometry_revision=0,
                expected_resolution_revision=0,
                expected_source_checksum_sha256=source.checksum_sha256,
                expected_source_width=source.oriented_width,
                expected_source_height=source.oriented_height,
                expected_grid_rows=3,
                expected_grid_columns=5,
                corners=tuple(
                    ImageReviewGeometryPoint(
                        round(_nodes(position)[i].x), round(_nodes(position)[i].y)
                    )
                    for i in (0, 5, 23, 18)
                ),
                geometry_qualification=None if ordinal == 0 else GeometryQualification(),
                lattice_nodes=SourceLatticeNodes(_nodes(position)),
            )
            for position, pending in enumerate(seed.pending_ids)
        )
        result = VirtualGridGeometryService(
            SqlAlchemyVirtualGridGeometryRepository(session),
            root,
        ).save_source(
            game_id=game,
            import_job_id=seed.import_job_id,
            commands=commands,
            idempotency_key=uuid4(),
            actor="fixture-human:0995-e2e",
            created_at=datetime.now(UTC),
        )
        assert result.created and len(result.revisions) == slot_count
        for position, revision in enumerate(result.revisions):
            # Row 1, column 1 touches deformed inner nodes 8 and 14.
            # Its persisted pixel checksum therefore witnesses the deformation.
            cell = revision.cells[6]
            assert cell.cell_index == 6
            expected[f"{seed.source_image_id}:{position}"] = {
                "nodes": [[point.x, point.y] for point in _nodes(position)],
                "sequenceNumber": 100 + ordinal * 10 + position,
                "cell": {
                    "render_spec": dict(cell.render_spec),
                    "expected_render_spec_checksum_sha256": cell.render_spec_checksum_sha256,
                    "expected_rendered_pixel_checksum_sha256": cell.rendered_pixel_checksum_sha256,
                    "expected_cell_index": cell.cell_index,
                    "expected_row_index": cell.row_index,
                    "expected_column_index": cell.column_index,
                    "expected_logical_cell_key_sha256": cell.logical_cell_key,
                    "expected_logical_cell_key_v2_sha256": cell.logical_cell_key_v2,
                    "expected_extractor_version": cell.extractor_version,
                },
            }
        return (
            seed.source_image_id,
            (
                source.checksum_sha256,
                source.normalized_pixel_checksum_sha256,
            ),
            seed.import_job_id,
        )


def _recording(db, root, game, sources, role, family, version, providers, checkpoint):
    result, _ = execute(db, root, game, "prepare", selection={"sourceIds": list(map(str, sources))})
    checkpoint("recording_" + role + "_prepare")
    group = result["group"]
    for kind, values in (
        ("attach", {"manifestId": group["manifestId"], "pageIndex": 0}),
        ("complete", {}),
        ("declare", {"independenceConfirmed": True}),
        ("assign_role", {"familyId": str(family), "role": role}),
        ("freeze", {"familyId": str(family), "baseVersionId": str(version)}),
    ):
        result, _ = execute(
            db,
            root,
            game,
            kind,
            providers=providers,
            groupId=group["id"],
            expectedRevision=group["revision"],
            **values,
        )
        assert result["statusCode"] == 200, result
        group = result["group"]
        checkpoint("recording_" + role + "_" + kind)
    return {"groupId": group["id"], "role": role}


def _recorrect_first(db, root, game, job, source, expected):
    """Create an ordinary correction of a real, previously committed board."""
    with game_storage_scope(game), _factory(db.owner_engine).begin() as session:
        row = session.execute(
            text(
                "SELECT i.id,i.resolution_revision,b.geometry_revision,b.geometry_qualification "
                "FROM image_review_items i JOIN recognized_boards b "
                "ON b.game_id=i.game_id AND b.id=i.recognized_board_id "
                "WHERE b.game_id=:g AND b.source_image_id=:s AND b.position_index=0"
            ),
            {"g": game, "s": source},
        ).one()
        assert row.geometry_revision == 1 and row.geometry_qualification is None
        assert (
            session.scalar(
                text(
                    "SELECT count(*) FROM image_symbol_review_cells c "
                    "JOIN recognized_boards b ON b.game_id=c.game_id "
                    "AND b.id=c.recognized_board_id "
                    "WHERE b.game_id=:g AND b.source_image_id=:s"
                ),
                {"g": game, "s": source},
            )
            == 15
        )
        assert (
            session.scalar(
                text("SELECT status FROM image_symbol_review_states WHERE game_id=:g"),
                {"g": game},
            )
            == "rebuilding"
        )
        nodes = list(_nodes(0))
        nodes[8] = SourcePoint(nodes[8].x + 0.25, nodes[8].y)
        saved = VirtualGridGeometryService(
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
            actor="fixture-human:0995-e2e",
            created_at=datetime.now(UTC),
        )
        assert saved.created and saved.revision.revision == 2
        cell = saved.revision.cells[6]
        target = expected[f"{source}:0"]
        target["nodes"] = [[point.x, point.y] for point in nodes]
        target["cell"] = {
            "render_spec": dict(cell.render_spec),
            "expected_render_spec_checksum_sha256": cell.render_spec_checksum_sha256,
            "expected_rendered_pixel_checksum_sha256": cell.rendered_pixel_checksum_sha256,
            "expected_cell_index": cell.cell_index,
            "expected_row_index": cell.row_index,
            "expected_column_index": cell.column_index,
            "expected_logical_cell_key_sha256": cell.logical_cell_key,
            "expected_logical_cell_key_v2_sha256": cell.logical_cell_key_v2,
            "expected_extractor_version": cell.extractor_version,
        }
    print("0995 E2E actual_existing_board_correction_1_to_2", flush=True)


def _service(session, root):
    return GridTrainingCohortService(SqlAlchemyGridTrainingCohortRepository(session, root), root)


def _complete_first_identity(db, root, game, source):
    columns = (
        "raw_width",
        "raw_height",
        "oriented_width",
        "oriented_height",
        "exif_orientation",
        "coordinate_space",
        "normalization_adapter_version",
        "normalized_pixel_checksum_sha256",
    )
    with game_storage_scope(game), _factory(db.owner_engine).begin() as session:
        original = session.execute(
            text("SELECT " + ",".join(columns) + " FROM source_images WHERE game_id=:g AND id=:s"),
            {"g": game, "s": source},
        ).one()
        revisions = list(
            session.scalars(
                text(
                    "SELECT to_jsonb(r) FROM image_source_geometry_revisions r "
                    "WHERE game_id=:g AND source_image_id=:s ORDER BY revision"
                ),
                {"g": game, "s": source},
            )
        )
        assert len(revisions) == 1 and original[4] is None
        checksum = session.scalar(
            text("SELECT checksum_sha256 FROM source_images WHERE game_id=:g AND id=:s"),
            {"g": game, "s": source},
        )
        # Exact-owned synthetic legacy setup. The existing real seed geometry
        # witness and its bytes remain unchanged; no import lease is fabricated.
        session.execute(
            text(
                "UPDATE source_images SET "
                + ",".join(key + "=NULL" for key in columns)
                + " WHERE game_id=:g AND id=:s"
            ),
            {"g": game, "s": source},
        )
    body = {
        "idempotencyKey": str(uuid4()),
        "sources": [
            {
                "sourceId": str(source),
                "expectedSourceSha256": checksum,
                "expectedSourceGeometryRevisionId": revisions[0]["id"],
                "expectedGeometrySha256": revisions[0]["geometry_checksum_sha256"],
            }
        ],
    }
    with Session(db.app_engine) as session:
        response = _service(session, root).complete_identities(
            game, body, "fixture-human:0995-identity"
        )
        assert response["receipt"]["results"] == [{"sourceId": str(source), "outcome": "completed"}]
        session.commit()
    with Session(db.app_engine) as session:
        service = _service(session, root)
        assert service.complete_identities(game, body, "fixture-human:0995-identity") == response
        restored = session.execute(
            text("SELECT " + ",".join(columns) + " FROM source_images WHERE game_id=:g AND id=:s"),
            {"g": game, "s": source},
        ).one()
        after = list(
            session.scalars(
                text(
                    "SELECT to_jsonb(r) FROM image_source_geometry_revisions r "
                    "WHERE game_id=:g AND source_image_id=:s ORDER BY revision"
                ),
                {"g": game, "s": source},
            )
        )
        assert restored == original and restored[4] is None and after == revisions
    print("0995 E2E actual_identity_completion_replay_geometry_unchanged", flush=True)


def _issue_change(db, root, game, cohort, source, *, commit=False):
    with _factory(db.app_engine)() as session:
        service = _service(session, root)
        service.repository.bind(game, write=True)
        cell = (
            session.execute(
                text(
                    "SELECT c.id,c.revision,c.geometry_revision,"
                    "c.crop_sample_id,c.crop_checksum_sha256,"
                    "b.id AS board_id,b.approved_geometry_revision "
                    "FROM image_symbol_review_cells c "
                    "JOIN recognized_boards b ON b.game_id=c.game_id "
                    "AND b.id=c.recognized_board_id "
                    "WHERE b.game_id=:g AND b.source_image_id=:s "
                    "ORDER BY b.position_index,c.cell_index LIMIT 1"
                ),
                {"g": game, "s": source},
            )
            .mappings()
            .one()
        )
        assert cell["approved_geometry_revision"] == cell["geometry_revision"]
        mutation = SymbolCellReviewMutationService(
            SqlAlchemySymbolCellReviewMutationRepository(
                session,
                allow_current_manual_neural_board=True,
            )
        ).mark_grid_issue(
            game_id=game,
            cell_review_id=cell["id"],
            expected_revision=cell["revision"],
            expected_geometry_revision=cell["geometry_revision"],
            expected_crop_sample_id=cell["crop_sample_id"],
            expected_crop_checksum_sha256=cell["crop_checksum_sha256"],
            actor="fixture-human:0995-issue",
        )
        assert mutation.has_grid_issue
        session.flush()
        current = session.execute(
            text(
                "SELECT approved_geometry_revision,geometry_revision FROM recognized_boards "
                "WHERE game_id=:g AND id=:b"
            ),
            {"g": game, "b": cell["board_id"]},
        ).one()
        approval_lost = current[0] != current[1]
        facts = service.eligibility(game, cohort)
        assert facts["qualification"] == "blocked", facts
        assert (facts["humanLabelWithdrawn"] is True) == approval_lost, facts
        assert facts["liveSourceLinked"] is True
        if commit:
            session.commit()
        else:
            session.rollback()
    if not commit:
        with Session(db.app_engine) as session:
            assert _service(session, root).eligibility(game, cohort)["qualification"] == "eligible"
    return {"approvalWithdrawnByWriter": approval_lost, "observedFacts": facts}


def _ready_cohort(db, root, game, body, checkpoint, prefix=""):
    with Session(db.app_engine) as session:
        result = _service(session, root).prepare(game, body, "fixture-human:0995-e2e")
        session.commit()
    state, cohort = result["cohort"], UUID(result["cohort"]["id"])
    checkpoint(prefix + "cohort_prepared")
    for kind, cursor_key in (
        ("prepare-page", "nextCaptureCursor"),
        ("materialize-page", "nextMaterializationCursor"),
    ):
        while state[cursor_key] is not None:
            command = {
                "idempotencyKey": str(uuid4()),
                "expectedRevision": state["revision"],
                "cursor": state[cursor_key],
            }
            with Session(db.app_engine) as session:
                result = _service(session, root).command(
                    game, cohort, kind, command, "fixture-human:0995-e2e"
                )
                session.commit()
            state = result["cohort"]
            checkpoint(prefix + kind + "_" + str(command["cursor"]))
    assert state["status"] == "ready_to_freeze", state
    return state, cohort


def _freeze_body(state):
    return {
        "idempotencyKey": str(uuid4()),
        "expectedRevision": state["revision"],
        "expectedManifestSha256": state["manifestSha256"],
        "expectedPreviewSha256": state["previewSha256"],
    }


def _failure_state(db, root, game, cohort):
    parameters = {"g": game, "c": cohort}
    with Session(db.app_engine) as session:
        _service(session, root).repository.bind(game)
        header = session.scalar(
            text("SELECT to_jsonb(c) FROM grid_training_cohorts c WHERE game_id=:g AND id=:c"),
            parameters,
        )
        counts = {
            "appReceipts": session.scalar(
                text(
                    "SELECT count(*) FROM grid_training_cohort_commands "
                    "WHERE game_id=:g AND cohort_id=:c"
                ),
                parameters,
            ),
            "freezeReceipts": session.scalar(
                text(
                    "SELECT count(*) FROM grid_training_cohort_commands "
                    "WHERE game_id=:g AND cohort_id=:c AND kind='freeze'"
                ),
                parameters,
            ),
            "frozenEvents": session.scalar(
                text(
                    "SELECT count(*) FROM grid_training_cohort_events "
                    "WHERE game_id=:g AND cohort_id=:c AND kind='frozen'"
                ),
                parameters,
            ),
        }
    # Assertions inspect only the new exact-owned database. The runtime itself
    # receives no private SELECT grant, and never falls back to the owner.
    with db.owner_engine.connect() as connection:
        counts["privateActualUse"] = connection.scalar(
            text(
                "SELECT count(*) FROM public.recording_evidence WHERE kind='use' "
                "AND payload->>'cohortId'=:c"
            ),
            {"c": str(cohort)},
        )
        counts["privateUseReceipts"] = connection.scalar(
            text(
                "SELECT count(*) FROM public.recording_commands WHERE game_id=:g "
                "AND kind='register_cohort_use' AND command_json->>'cohortId'=:c"
            ),
            {"g": game, "c": str(cohort)},
        )
    return {"header": header, "counts": counts}


def _stale_ready_rollback(db, root, game, body, main_cohort, job, source, checkpoint):
    state, cohort = _ready_cohort(
        db, root, game, {**body, "idempotencyKey": str(uuid4())}, checkpoint, "stale_"
    )
    before = _failure_state(db, root, game, cohort)
    assert all(
        before["counts"][key] == 0
        for key in ("freezeReceipts", "frozenEvents", "privateActualUse", "privateUseReceipts")
    )
    with game_storage_scope(game), _factory(db.app_engine).begin() as session:
        service = GeometryCorrectionRevertService(
            SqlAlchemyGeometryCorrectionRevertRepository(session),
            render_verifier=VirtualRestoredRenderVerifier(root),
        )
        entries = service.list_recent(game_id=game, import_job_id=job)
        assert entries and entries[0].geometry_revision == 2
        preview = service.preview(
            game_id=game,
            import_job_id=job,
            board_geometry_revision_id=entries[0].board_geometry_revision_id,
        )
        entry = preview.correction
        revert = {
            "kind": entry.kind.value,
            "revertable": entry.revertable,
            "blockingReason": None
            if entry.blocking_reason is None
            else entry.blocking_reason.value,
        }
        (root / "revert-preview.json").write_text(json.dumps(revert, indent=2), encoding="utf-8")
        assert entry.revertable, revert
        result = service.revert(
            game_id=game,
            import_job_id=job,
            board_geometry_revision_id=entry.board_geometry_revision_id,
            idempotency_key=uuid4(),
            expected_geometry_revision=entry.geometry_revision,
            expected_resolution_revision=entry.resolution_revision,
            actor="fixture-human:0995-e2e-revert",
            reverted_at=datetime.now(UTC),
        )
        assert result.created and result.kind.value == "board_revision"
        assert result.restored_geometry_revision == 3 and result.restored_cell_decision_count == 15
        assert result.source_image_geometry_status is SourceImageGeometryStatus.GEOMETRY_COMPLETE
        revert.update(restoredGeometryRevision=3, restoredCells=15)
    checkpoint("stale_actual_case_a_revert_committed")
    with Session(db.app_engine) as session:
        service = _service(session, root)
        facts = service.eligibility(game, main_cohort)
        assert facts["qualification"] == "blocked", facts
        assert facts["humanLabelWithdrawn"] is True and facts["liveSourceLinked"] is True, facts
        geometry = session.scalar(
            text(
                "SELECT board_geometry FROM recognized_boards "
                "WHERE game_id=:g AND source_image_id=:s"
            ),
            {"g": game, "s": source},
        )
        assert geometry["latticeNodes"] == [{"x": p.x, "y": p.y} for p in _nodes(0)]
    checkpoint("fresh_metadata_human_withdrawn_live_link_exact_restored_nodes")
    with Session(db.app_engine) as session:
        with pytest.raises(GridCohortError) as failed:
            _service(session, root).command(
                game, cohort, "freeze", _freeze_body(state), "fixture-human:0995-stale"
            )
        session.rollback()
    assert failed.value.code == "GRID_COHORT_LABEL_STALE" and failed.value.status == 409
    after = _failure_state(db, root, game, cohort)
    assert after == before
    return {
        "errorCode": failed.value.code,
        "revert": revert,
        "observedFacts": facts,
        "before": before,
        "after": after,
        "headerExactlyUnchanged": True,
    }


def _revert_rollback(db, root, game, cohort, job, source):
    with _factory(db.app_engine)() as session:
        repo = _service(session, root).repository
        repo.bind(game)
        member = session.scalar(
            select(GridTrainingCohortMemberModel).where(
                GridTrainingCohortMemberModel.game_id == game,
                GridTrainingCohortMemberModel.cohort_id == cohort,
                GridTrainingCohortMemberModel.source_id == source,
            )
        )
        assert member is not None and inspect_member(repo, member).error is None
        service = GeometryCorrectionRevertService(
            SqlAlchemyGeometryCorrectionRevertRepository(session),
            render_verifier=VirtualRestoredRenderVerifier(root),
        )
        entries = service.list_recent(game_id=game, import_job_id=job)
        assert entries
        preview = service.preview(
            game_id=game,
            import_job_id=job,
            board_geometry_revision_id=entries[0].board_geometry_revision_id,
        )
        entry = preview.correction
        if not entry.revertable:
            return {"reverted": False, "blockingReason": entry.blocking_reason.value}
        result = service.revert(
            game_id=game,
            import_job_id=job,
            board_geometry_revision_id=entry.board_geometry_revision_id,
            idempotency_key=uuid4(),
            expected_geometry_revision=entry.geometry_revision,
            expected_resolution_revision=entry.resolution_revision,
            actor="fixture-human:0995-revert",
            reverted_at=datetime.now(UTC),
        )
        assert result.created
        session.flush()
        facts = inspect_member(repo, member)
        assert facts.error is not None and facts.error.code == "GRID_COHORT_LABEL_STALE"
        observed = {
            "errorCode": facts.error.code,
            "humanLabelWithdrawn": facts.human_label_withdrawn,
            "liveSourceLinked": facts.live_source_linked,
        }
        session.rollback()
    with Session(db.app_engine) as session:
        repo = _service(session, root).repository
        repo.bind(game)
        member = session.scalar(
            select(GridTrainingCohortMemberModel).where(
                GridTrainingCohortMemberModel.game_id == game,
                GridTrainingCohortMemberModel.cohort_id == cohort,
                GridTrainingCohortMemberModel.source_id == source,
            )
        )
        assert member is not None and inspect_member(repo, member).error is None
    return {
        "reverted": True,
        "observedFacts": observed,
        "kind": entry.kind.value,
        "restoredSourceGeometryRevisionId": str(preview.restored_source_geometry_revision_id),
    }


_DATASET_CHECK = """
import json,sys
from pathlib import Path
import numpy as np
from game_predictor_worker.images.grid_cohort_dataset import (
    GridCohortSnapshot,GridBoardDataset,GridScreenDataset,
)
from game_predictor_worker.images.virtual_cell_extraction import render_persisted_virtual_cell_rgb
p=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
snapshot=GridCohortSnapshot(Path(p['root']),p['path'],p['sha'])
seen=set()
for role,count,photos in [('TRAIN',30,0),('VALIDATION',45,5),('REGRESSION',45,5)]:
    dataset=GridBoardDataset(snapshot,role)
    assert len(dataset)==count and len(GridScreenDataset(snapshot,role))==photos
    sources={s['sourceId']:s for s in snapshot.sources() if s['role']==role}
    for index in range(count):
        item=dataset[index]
        key=f"{item['sourceId']}:{item['positionIndex']}"
        expected=p['expected'][key]
        np.testing.assert_array_equal(item['nodes'],expected['nodes'])
        assert item['sequenceNumber']==expected['sequenceNumber'] and item['sampleWeight']==4
        frame=snapshot.frame(sources[item['sourceId']],role)
        np.testing.assert_array_equal(item['sourceRgb'],frame.rgb)
        pixels=render_persisted_virtual_cell_rgb(frame,**expected['cell'])
        assert pixels.dtype==np.uint8 and pixels.shape[2]==3
        seen.add(key)
    print('0995 dataset '+role+' '+str(count),flush=True)
assert seen==set(p['expected']) and len(seen)==120
print('0995 dataset exact_nodes_render_parity_120',flush=True)
"""


def _check_cleanup(db, evidence):
    journals = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (evidence / "resources").glob("*.json")
    ]
    if not journals:
        (evidence / "cleanup.json").write_text("[]", encoding="utf-8")
        return
    engine = create_engine(
        (
            db.owner_url
            if db is not None
            else make_url(ApiSettings.from_environment().owner_database_url)
        ).set(database="postgres"),
        poolclass=NullPool,
        connect_args={"connect_timeout": 5, "options": "-c statement_timeout=10000"},
    )
    try:
        with engine.connect() as connection:
            results = []
            for journal in journals:
                name = journal["databaseName"]
                assert journal["databaseCreatedHere"] and name.startswith("game_predictor_t0995e_")
                roles = [
                    journal[key]["name"]
                    for key in ("capabilityRole", "runtimeRole")
                    if journal.get(key) and journal[key]["createdHere"]
                ]
                result = {
                    "database": name,
                    "databaseOid": journal["databaseOid"],
                    "databaseRemaining": connection.scalar(
                        text("SELECT count(*) FROM pg_database WHERE datname=:n"),
                        {"n": name},
                    ),
                    "rolesRemaining": connection.scalar(
                        text("SELECT count(*) FROM pg_roles WHERE rolname=ANY(CAST(:r AS text[]))"),
                        {"r": roles},
                    ),
                    "pids": list(
                        connection.scalars(
                            text("SELECT pid FROM pg_stat_activity WHERE datname=:n"),
                            {"n": name},
                        )
                    ),
                }
                results.append(result)
        (evidence / "cleanup.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        for result in results:
            assert (
                result["databaseRemaining"] == result["rolesRemaining"] == 0 and not result["pids"]
            )
    finally:
        engine.dispose()


def test_exact_owned_genuine_geometry_cohort_restart_dataset(monkeypatch):
    repository = Path(__file__).resolve().parents[4]
    evidence = repository / "artifacts/audits" / ("TASK-0995_E2E_" + uuid4().hex)
    evidence.mkdir(parents=True)
    monkeypatch.setenv("GAME_PREDICTOR_RECORDING_TEST_RESOURCE_ROOT", str(evidence / "resources"))
    started, progress, retained = time.monotonic(), [], None
    compile(_DATASET_CHECK, "cohort-dataset-check", "exec")

    def checkpoint(label):
        elapsed = round(time.monotonic() - started, 3)
        progress.append({"phase": label, "elapsedSeconds": elapsed})
        (evidence / "progress.json").write_text(json.dumps(progress, indent=2), encoding="utf-8")
        print(f"0995 E2E {label} {elapsed}s", flush=True)
        # Collection/imports took about eleven seconds in the measured CPU
        # probe. Reserve that cost plus cleanup under the outer 120s PID limit.
        assert elapsed < 105, "Soft deadline reserves exact-owned cleanup time"

    try:
        with application_role_database("t0995e", ("cohort-e2e",)) as db:
            retained = db
            checkpoint("fixture_ready")
            game = next(iter(db.games.values()))
            version, family = _install_base(db, game)
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
            sources, expected, identities, jobs = {}, {}, [], []
            for ordinal in range(20):
                role = "TRAIN" if ordinal < 10 else "VALIDATION" if ordinal < 15 else "REGRESSION"
                slots = 1 if ordinal == 0 else 5 if ordinal == 1 else 3 if ordinal < 10 else 9
                source, identity, job = _save_source(db, evidence, game, ordinal, slots, expected)
                if ordinal == 0:
                    _recorrect_first(db, evidence, game, job, source, expected)
                sources.setdefault(role, []).append(source)
                identities.append(identity)
                jobs.append(job)
                checkpoint(f"source_{ordinal + 1}_{role}")
            assert (
                len({value[0] for value in identities})
                == len({value[1] for value in identities})
                == 20
            )
            assert len(expected) == 120
            with db.owner_engine.connect() as connection:
                assert (
                    connection.scalar(
                        text(
                            "SELECT count(*) FROM game_data_v2.image_board_geometry_review_events "
                            "WHERE game_id=:g AND action='geometry_saved'"
                        ),
                        {"g": game},
                    )
                    == 121
                )
            checkpoint("120_unique_targets_121_geometry_saved_events")
            providers = _providers(db, evidence, version)
            recordings = [
                _recording(db, evidence, game, values, role, family, version, providers, checkpoint)
                for role, values in sources.items()
            ]
            body = {
                "idempotencyKey": str(uuid4()),
                "familyId": str(family),
                "baseVersionId": str(version),
                "mode": "grid-only",
                "selector": {"sourceIds": [str(s) for values in sources.values() for s in values]},
                "recordings": recordings,
            }
            state, cohort = _ready_cohort(db, evidence, game, body, checkpoint)
            freeze = _freeze_body(state)
            with Session(db.app_engine) as session:
                frozen = _service(session, evidence).command(
                    game, cohort, "freeze", freeze, "fixture-human:0995-e2e"
                )
                session.commit()
            assert frozen["cohort"]["status"] == "frozen"
            checkpoint("frozen_committed")
            with Session(db.app_engine) as session:
                service = _service(session, evidence)
                assert (
                    service.command(game, cohort, "freeze", freeze, "fixture-human:0995-e2e")
                    == frozen
                )
                assert service.get(game, cohort) == frozen["cohort"]
                assert service.eligibility(game, cohort)["qualification"] == "eligible"
                row = session.get(GridTrainingCohortModel, (game, cohort))
                payload = {
                    "root": str(evidence),
                    "path": row.manifest_path,
                    "sha": row.manifest_sha256,
                    "expected": expected,
                }
            checkpoint("restart_replay_eligible")
            child_input = evidence / "dataset-input.json"
            child_input.write_text(json.dumps(payload), encoding="utf-8")
            script = evidence / "dataset-check.py"
            script.write_text(_DATASET_CHECK, encoding="utf-8")
            child = subprocess.run(
                [sys.executable, str(script), str(child_input)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=max(1, min(25, 105 - (time.monotonic() - started))),
                check=False,
                env=db.subprocess_environment(),
            )
            (evidence / "dataset.log").write_text(child.stdout + child.stderr, encoding="utf-8")
            print(child.stdout, flush=True)
            assert child.returncode == 0, child.stderr
            checkpoint("new_process_dataset_passed")
            stale = _stale_ready_rollback(
                db, evidence, game, body, cohort, jobs[0], sources["TRAIN"][0], checkpoint
            )
            (evidence / "stale-ready.json").write_text(
                json.dumps(stale, indent=2), encoding="utf-8"
            )
            checkpoint("stale_ready_zero_use_receipts_header_unchanged")
    finally:
        _check_cleanup(retained, evidence)
