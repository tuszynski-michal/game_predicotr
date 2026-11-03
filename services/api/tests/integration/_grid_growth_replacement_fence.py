"""Actual currentness fence through the replacement-aware registry capability."""

import json
from uuid import uuid4

import pytest
from game_predictor_api.domain.source_replacement import SourceReplacementError
from game_predictor_api.storage.game_storage_routing import GameStorageIntent, GameStorageRouter
from game_predictor_api.storage.source_replacement_guards import require_unreferenced_sources
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session


def assert_replacement_fence(db):
    game = next(iter(db.games.values()))
    with Session(db.owner_engine) as session, session.begin():
        savepoint = session.begin_nested()
        GameStorageRouter().bind(session, game, intent=GameStorageIntent.WRITE)
        session.execute(
            text(
                "UPDATE public.games SET shape_geometry_configuration='neural_grid_v3' WHERE id=:g"
            ),
            {"g": game},
        )
        source, job, cohort, batch, entry, key = (uuid4() for _ in range(6))
        params = dict(g=game, s=source, j=job, c=cohort, b=batch, e=entry, sha=source.hex * 2)
        session.execute(
            text("""INSERT INTO public.jobs
         (id,game_id,job_type,status,input_payload,input_key)
         VALUES(:j,:g,'import','completed','{}',:sha)"""),
            params,
        )
        session.execute(
            text("""INSERT INTO public.image_file_executions
         (file_execution_key,source_checksum_sha256,pipeline_fingerprint,checkpoint_payload,status)
         VALUES(:sha,:sha,:sha,'{}','completed')"""),
            params,
        )
        session.execute(
            text("""INSERT INTO source_images
         (game_id,id,import_job_id,file_execution_key,relative_path,checksum_sha256,
          width,height,status,normalized_pixel_checksum_sha256)
         VALUES(:g,:s,:j,:sha,'fence.jpg',:sha,100,100,'completed',:sha)"""),
            params,
        )
        session.execute(
            text("""INSERT INTO grid_training_cohorts
         (game_id,id,status,document,created_by,manifest_sha256,manifest_path)
         VALUES(:g,:c,'preparing','{"policyVersion":"application-grid-corrections-v1",
          "mode":"grid-only"}','fixture:1147',:sha,'fixture.json')"""),
            params,
        )
        session.execute(
            text("""INSERT INTO grid_training_cohort_members
         (game_id,cohort_id,source_id,live_source_image_id,ordinal,role,frozen)
         VALUES(:g,:c,:s,:s,0,'TRAIN',jsonb_build_object('used',false))"""),
            params,
        )
        session.execute(
            text("""INSERT INTO source_replacement_batches
         (game_id,id,revision,status,preview_token,document)
         VALUES(:g,:b,1,'planned',:sha,'{}')"""),
            params,
        )
        session.execute(
            text("""INSERT INTO source_replacement_entries
         (game_id,id,batch_id,source_id,source_sha256,phase,document)
         VALUES(:g,:e,:b,:s,:sha,'planned','{}')"""),
            params,
        )
        session.execute(
            text("""INSERT INTO source_replacement_sources
         (game_id,entry_id,source_id) VALUES(:g,:e,:s)"""),
            params,
        )
        with pytest.raises(SourceReplacementError) as retained:
            require_unreferenced_sources(session, game, [source])
        assert retained.value.code == "SOURCE_REPLACEMENT_REFERENCED"
        request = dict(
            kind="validate_cohort_use",
            cohortId=str(cohort),
            idempotencyKey=str(key),
            expectedRevision=1,
            manifestSha256=params["sha"],
        )
        query = {"g": game, "q": json.dumps(request)}
        quote = session.get_bind().dialect.identifier_preparer.quote
        for state in ("reserved", "retired"):
            staged = session.begin_nested()
            if state == "reserved":
                session.execute(
                    text("""INSERT INTO source_replacement_slots
                 (game_id,sequence_number,entry_id,batch_id,state,new_source_id,
                  new_sha256,revision,document)
                 VALUES(:g,1,:e,:b,'reserved',:s,:sha,1,'{}')"""),
                    params,
                )
            else:
                session.execute(
                    text("""INSERT INTO source_replacement_retired
                 (game_id,source_id,entry_id,source_sha256,document)
                 VALUES(:g,:s,:e,:sha,'{}')"""),
                    params,
                )
            assert (
                session.scalar(
                    text("SELECT public.source_replacement_source_current_v1(:g,:s,:sha)"), params
                )
                is False
            )
            # The public wrapper is tested as the real runtime role; the private
            # photo function is tested directly as owner to cover both SQL bodies.
            for function in ("recording_cohort_command_v3", "recording_photo_cohort_v1"):
                if function == "recording_cohort_command_v3":
                    session.execute(text(f"SET LOCAL ROLE {quote(db.role)}"))
                with (
                    pytest.raises(DBAPIError, match="SOURCE_REPLACEMENT_" + state.upper()),
                    session.begin_nested(),
                ):
                    session.scalar(
                        text(f"SELECT public.{function}(:g,CAST(:q AS jsonb),'fixture')"), query
                    )
                session.execute(text("SET LOCAL ROLE NONE"))
            staged.rollback()
        assert (
            session.scalar(
                text("SELECT public.source_replacement_source_current_v1(:g,:s,:sha)"), params
            )
            is True
        )
        assert session.scalar(text("SELECT count(*) FROM public.recording_photo_uses")) == 0
        savepoint.rollback()
