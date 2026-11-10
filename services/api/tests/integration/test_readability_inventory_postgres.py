"""Small owned corpus proves the exact legacy order and snapshot equivalence."""

import json
from datetime import UTC, datetime
from uuid import uuid4

from game_predictor_api.domain.jobs import JobStatus
from game_predictor_api.domain.symbol_readability import GAME_ID
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
)
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.image_symbol_review_repository import (
    SqlAlchemyImageSymbolReviewRepository,
)
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.models import JobModel
from game_predictor_api.storage.sequence_ownership_lock import acquire_sequence_ownership_lock
from game_predictor_api.storage.symbol_readability import SNAPSHOT_SQL
from game_predictor_worker.images.orchestration_store import SqlAlchemyImageBatchStore
from game_predictor_worker.symbols.readability_inventory import (
    candidate_snapshots,
    has_replacement_fences,
)
from sqlalchemy import text
from test_image_batch_store import PIPELINE, _add_review_projection_source, _image_job
from test_symbol_readability_postgres import database as database  # noqa: F401
from test_symbol_readability_postgres import pytestmark as pytestmark


def test_inventory_order_and_snapshots_match_legacy_for_pilot_and_audit(database, monkeypatch):  # noqa: F811
    from game_predictor_worker.symbols import readability_inventory

    monkeypatch.setattr(readability_inventory, "SOURCE_PAGE_SIZE", 2)
    factory = create_session_factory(database)
    now = datetime.now(UTC)
    with factory() as session, session.begin():
        session.execute(
            text("""INSERT INTO public.symbols
(id,game_id,mobile_code,code,name,is_wildcard,display_order,status)
VALUES(:id,:game,1,'test','Test',false,0,'active')"""),
            {"id": uuid4(), "game": GAME_ID},
        )
        job = SqlAlchemyJobRepository(session).add_job(_image_job(GAME_ID, PIPELINE, now))
    for index in range(4):
        sha = str(index + 1) * 64
        execution = SqlAlchemyImageBatchStore(factory).register_file(
            job.id,
            source_checksum_sha256=sha,
            pipeline_fingerprint=PIPELINE,
            source_relative_path=f"inventory-{index}.jpg",
            order_index=index,
            registered_at=now,
        )
        with game_storage_scope(GAME_ID), factory() as session, session.begin():
            _add_review_projection_source(
                session,
                job_id=job.id,
                file_execution_key=execution.file_execution_key,
                source_checksum=sha,
                source_name=f"inventory-{index}.jpg",
                position_index=0,
                sequence_number=100 + index,
                status="pending",
                created_at=now,
            )
    with game_storage_scope(GAME_ID), factory() as session, session.begin():
        session.get(JobModel, job.id).status = JobStatus.WAITING_FOR_REVIEW
        SqlAlchemyBoardSearchProjectionRepository(session).rebuild_game(GAME_ID)
        projection = SqlAlchemyImageSymbolReviewRepository(session)
        projection.start_or_resume_backfill(GAME_ID)
        result = projection.backfill_next_batch(GAME_ID, batch_size=100)
        assert result.report.cell_count == 60
        session.execute(
            text(
                "UPDATE image_symbol_review_cells SET quality_issue='unreadable' "
                "WHERE game_id=:game AND cell_index%3=0"
            ),
            {"game": GAME_ID},
        )
    legacy_pilot = (
        "SELECT snapshot FROM (SELECT snapshot,row_number() OVER (PARTITION BY "
        "snapshot->>'source_id',snapshot->>'import_job_id',snapshot->>'symbol_class' "
        "ORDER BY md5(:seed||(snapshot->>'cell_id'))) AS position FROM ("
        + SNAPSHOT_SQL
        + " AND c.source_available AND c.asset_mode='virtual_source' AND "
        "c.geometry_revision=b.geometry_revision "
        "AND c.source_geometry_revision_id=b.source_geometry_revision_id"
        + ") inventory) strata ORDER BY position,"
        "md5(:seed||(snapshot->>'source_id')),md5(:seed||(snapshot->>'cell_id'))"
    )
    legacy_audit = (
        SNAPSHOT_SQL + " AND c.source_available AND c.asset_mode='virtual_source' AND "
        "c.quality_issue IS NULL AND c.geometry_revision=b.geometry_revision "
        "AND c.source_geometry_revision_id=b.source_geometry_revision_id "
        "AND NOT EXISTS(SELECT 1 FROM symbol_readability_items old WHERE "
        "old.game_id=c.game_id AND old.ever_labelled AND "
        "old.snapshot->>'rendered_pixel_checksum_sha256'="
        "c.rendered_pixel_checksum_sha256) ORDER BY md5(:seed||c.id::text),c.id"
    )
    with game_storage_scope(GAME_ID), factory() as session, session.begin():
        acquire_sequence_ownership_lock(session, game_id=GAME_ID)
        assert not has_replacement_fences(session, GAME_ID)
        stale_id = None
        labelled_rgb = None

        def assert_parity(*, fences, excluded_sources=()):
            for seed in ("first", "second", "third"):
                for audit, query in ((False, legacy_pilot), (True, legacy_audit)):
                    expected = list(
                        session.execute(text(query), {"game": GAME_ID, "seed": seed}).scalars()
                    )
                    assert expected
                    assert not {row["source_id"] for row in expected} & set(excluded_sources)
                    assert stale_id not in {row["cell_id"] for row in expected}
                    if audit and labelled_rgb is not None:
                        assert all(
                            row["rendered_pixel_checksum_sha256"] != labelled_rgb
                            for row in expected
                        )
                    actual = list(
                        candidate_snapshots(
                            session, GAME_ID, seed, audit=audit, replacement_fences=fences
                        )
                    )
                    assert actual == expected

        assert_parity(fences=False)
        assert_parity(fences=True)
        baseline = list(
            session.execute(text(legacy_pilot), {"game": GAME_ID, "seed": "first"}).scalars()
        )
        assert len(baseline) == 60
        sources = sorted({row["source_id"] for row in baseline})
        rejected = sources[0]
        remaining = [row for row in baseline if row["source_id"] == sources[1]]
        stale = next(row for row in remaining if row["cell_index"] == 1)
        labelled = next(row for row in remaining if row["cell_index"] == 2)
        stale_id = stale["cell_id"]
        # Backfill fixtures do not decode real crops. Supply a non-null RGB
        # identity so the ever_labelled exclusion is actually discriminating.
        labelled_rgb = "a" * 64
        session.execute(
            text(
                "UPDATE image_symbol_review_cells SET rendered_pixel_checksum_sha256=:rgb "
                "WHERE game_id=:game AND id=:cell"
            ),
            {"game": GAME_ID, "cell": labelled["cell_id"], "rgb": labelled_rgb},
        )
        labelled["rendered_pixel_checksum_sha256"] = labelled_rgb
        assert labelled["rendered_pixel_checksum_sha256"] is not None
        session.execute(
            text(
                "UPDATE image_review_items SET status='rejected',resolved_at=now(),"
                "resolved_by='fixture',resolution_revision=1,resolved_value='{}' "
                "WHERE game_id=:game AND id=:review"
            ),
            {
                "game": GAME_ID,
                "review": next(
                    row["review_item_id"] for row in baseline if row["source_id"] == rejected
                ),
            },
        )
        session.execute(
            text(
                "UPDATE image_symbol_review_cells SET geometry_revision=geometry_revision+1 "
                "WHERE game_id=:game AND id=:cell"
            ),
            {"game": GAME_ID, "cell": stale["cell_id"]},
        )
        run = uuid4()
        session.execute(
            text(
                "INSERT INTO symbol_readability_runs(game_id,id,kind,status,job_id,seed) "
                "VALUES(:game,:run,'pilot','created',:job,'fixture')"
            ),
            {"game": GAME_ID, "run": run, "job": job.id},
        )
        session.execute(
            text("""INSERT INTO symbol_readability_items
(game_id,run_id,cell_id,source_id,sequence_number,cell_index,snapshot,identity,
sample_kind,historical_unreadable,ever_labelled)
VALUES(:game,:run,:cell,:source,:seq,:index,CAST(:snapshot AS jsonb),repeat('a',64),
'pilot',false,true)"""),
            dict(
                game=GAME_ID,
                run=run,
                cell=labelled["cell_id"],
                source=labelled["source_id"],
                seq=labelled["sequence_number"],
                index=labelled["cell_index"],
                snapshot=json.dumps(labelled),
            ),
        )
        assert_parity(fences=False, excluded_sources=(rejected,))
        for mode in ("retired", "reserved", "restored"):
            # Each history type alone must disable the empty-history fast path.
            with session.begin_nested() as savepoint:
                old, target = sources[2:]
                batch, entry = uuid4(), uuid4()
                params = dict(
                    game=GAME_ID,
                    batch=batch,
                    entry=entry,
                    old=old,
                    target=target,
                    sha=next(row["source_sha256"] for row in baseline if row["source_id"] == old),
                    phase="restored" if mode == "restored" else "gap_open",
                    document=json.dumps(
                        {
                            "replacementAdmission": {"sourceId": target},
                            "restoration": {"canonicalReviewIds": []},
                        }
                    ),
                )
                session.execute(
                    text("""INSERT INTO source_replacement_batches
(game_id,id,revision,status,preview_token,document)
VALUES(:game,:batch,1,:phase,repeat('a',64),'{}')"""),
                    params,
                )
                session.execute(
                    text("""INSERT INTO source_replacement_entries
(game_id,id,batch_id,source_id,source_sha256,phase,document)
VALUES(:game,:entry,:batch,:old,:sha,:phase,CAST(:document AS jsonb))"""),
                    params,
                )
                if mode == "retired":
                    session.execute(
                        text("""INSERT INTO source_replacement_retired
(game_id,source_id,entry_id,source_sha256,document)
VALUES(:game,:old,:entry,:sha,'{}')"""),
                        params,
                    )
                    excluded = old
                elif mode == "reserved":
                    session.execute(
                        text("""INSERT INTO source_replacement_slots
(game_id,sequence_number,entry_id,batch_id,state,new_source_id,new_sha256,revision,document)
VALUES(:game,999,:entry,:batch,'reserved',:target,repeat('f',64),1,'{}')"""),
                        params,
                    )
                    excluded = target
                else:
                    excluded = target
                assert has_replacement_fences(session, GAME_ID)
                assert_parity(fences=True, excluded_sources=(rejected, excluded))
                savepoint.rollback()
            assert not has_replacement_fences(session, GAME_ID)
