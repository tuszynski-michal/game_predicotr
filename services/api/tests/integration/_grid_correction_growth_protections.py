"""Metadata fixtures for the real registry's external protection boundary."""

import json
from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session


def assert_copy_target_metadata(db, game, old_cohort, source, scope):
    """Actual registry join follows own-game pixel copies, not arbitrary sessions."""
    from game_predictor_api.storage.grid_correction_split import previously_used_train_boards

    with Session(db.owner_engine) as s, s.begin():
        scope(s, game)
        staged = s.begin_nested()
        alias, cohort = uuid4(), uuid4()
        label = {"positionIndex": 0, "revision": 1, "nodes": [[0, 0], [1, 1]]}
        s.execute(
            text("""INSERT INTO public.image_file_executions
         (file_execution_key,source_checksum_sha256,pipeline_fingerprint,checkpoint_payload,status)
         VALUES(:sha,:sha,:sha,'{}','completed')"""),
            {"sha": alias.hex * 2},
        )
        s.execute(
            text("""INSERT INTO source_images(game_id,id,import_job_id,file_execution_key,
         relative_path,checksum_sha256,width,height,status,normalized_pixel_checksum_sha256)
         SELECT game_id,:alias,import_job_id,:checksum,'copy.jpg',:checksum,
          width,height,status,normalized_pixel_checksum_sha256 FROM source_images
         WHERE game_id=:g AND id=:source"""),
            {"alias": alias, "g": game, "source": source, "checksum": alias.hex * 2},
        )
        s.execute(
            text("""INSERT INTO grid_training_cohorts(game_id,id,status,document,created_by)
         SELECT game_id,:c,'preparing',document,'fixture:1139' FROM grid_training_cohorts
         WHERE game_id=:g AND id=:old"""),
            {"c": cohort, "g": game, "old": old_cohort},
        )
        s.execute(
            text("""INSERT INTO grid_training_cohort_members
         (game_id,cohort_id,source_id,live_source_image_id,ordinal,role,frozen)
         VALUES(:g,:c,:source,:source,0,'TRAIN',CAST(:f AS jsonb))"""),
            {
                "g": game,
                "c": cohort,
                "source": source,
                "f": json.dumps({"used": True, "positions": [{"label": label}]}),
            },
        )
        s.execute(
            text("""INSERT INTO public.recording_photo_uses
         (game_id,cohort_id,source_id,family_id,import_id,source_sha256,pixel_sha256,
          role,group_ids,split_sha256,used_in_cohort)
         SELECT game_id,:c,source_id,family_id,import_id,source_sha256,pixel_sha256,
          role,group_ids,split_sha256,true FROM public.recording_photo_uses
         WHERE game_id=:g AND cohort_id=:old AND source_id=:source"""),
            {"c": cohort, "g": game, "old": old_cohort, "source": source},
        )
        quote = s.get_bind().dialect.identifier_preparer.quote
        s.execute(text(f"SET LOCAL ROLE {quote(db.role)}"))
        facts = s.scalar(
            text("SELECT public.recording_photo_context_v2(:g,CAST(:ids AS uuid[]))"),
            {"g": game, "ids": [source, alias]},
        )
        by_source = {r["sourceId"]: r for r in facts}
        original, copy = by_source[str(source)], by_source[str(alias)]
        assert copy["usedTrainLabels"] == []
        assert copy["usedTrainAliasLabels"] == [
            {"sourcePixelSha256": source.hex * 2, "positionIndex": 0, "nodes": label["nodes"]}
        ]
        assert set(copy["aliasComponentIds"]) & set(original["aliasComponentIds"])
        assert copy["allowedRoles"] == ["TRAIN"]
        assert previously_used_train_boards([label], copy, source.hex * 2) == 1
        assert (
            previously_used_train_boards([{**label, "revision": 2}], original, source.hex * 2) == 0
        )
        s.execute(text("SET LOCAL ROLE NONE"))
        staged.rollback()


def assert_external_protections(db, game, old_cohort, source_ids, scope, command):
    for kind in ("holdout", "ancestor", "use", "role_head", "session", "conflict", "unspecified"):
        with Session(db.owner_engine) as s, s.begin():
            scope(s, game)
            staged = s.begin_nested()
            group, linked_group, event, candidate = (uuid4() for _ in range(4))
            family = s.scalar(
                text(
                    "SELECT family_id FROM public.recording_photo_uses "
                    "WHERE game_id=:g AND cohort_id=:c LIMIT 1"
                ),
                {"g": game, "c": old_cohort},
            )
            for identifier in (group, linked_group):
                s.execute(
                    text("""INSERT INTO public.recording_groups(id,game_id,revision,
                 manifest_id,manifest_sha256,expected_sources,page_count)
                 VALUES(:i,:g,1,:m,:sha,1,1)"""),
                    {"i": identifier, "g": game, "m": uuid4(), "sha": "a" * 64},
                )
            s.execute(
                text("""INSERT INTO public.recording_occurrences(id,group_id,game_id,
             source_id,source_sha256,pixel_sha256,pixel_algorithm,width,height,attestation)
             VALUES(:i,:group,:g,:source,:sha,:sha,'fixture',100,100,'{}')"""),
                {
                    "i": uuid4(),
                    "group": group,
                    "g": game,
                    "source": source_ids[-1],
                    "sha": source_ids[-1].hex * 2,
                },
            )
            s.execute(
                text("""INSERT INTO public.recording_evidence
             (id,kind,group_ids,payload,payload_sha256,actor)
             VALUES(:i,'alias',CAST(:groups AS uuid[]),'{}',:sha,'fixture:1139')"""),
                {"i": uuid4(), "groups": [group, linked_group], "sha": "b" * 64},
            )
            payload = (
                {}
                if kind == "unspecified"
                else {"role": "TRAIN" if kind == "conflict" else "VALIDATION"}
            )
            s.execute(
                text("""INSERT INTO public.recording_evidence
             (id,kind,group_ids,payload,payload_sha256,actor)
             VALUES(:i,:kind,CAST(:groups AS uuid[]),CAST(:p AS jsonb),:sha,'fixture:1139')"""),
                {
                    "i": event,
                    "kind": kind
                    if kind in ("holdout", "ancestor", "use")
                    else "declaration"
                    if kind in ("role_head", "session")
                    else "ancestor",
                    "groups": [linked_group],
                    "p": json.dumps(payload),
                    "sha": "c" * 64,
                },
            )
            if kind == "role_head":
                s.execute(
                    text("""INSERT INTO public.recording_role_heads
                 (family_id,group_id,revision,role,event_id)
                 VALUES(:f,:group,1,'VALIDATION',:e)"""),
                    {"f": family, "group": linked_group, "e": event},
                )
            if kind == "session":
                # Different image bytes, same proven session component: no exact-copy shortcut.
                s.execute(
                    text("""INSERT INTO public.recording_photo_uses
                 (game_id,cohort_id,source_id,family_id,import_id,source_sha256,pixel_sha256,
                  role,group_ids,split_sha256,used_in_cohort)
                 VALUES(:g,:c,:s,:f,:j,:sha,:sha,'VALIDATION',
                  CAST(:groups AS uuid[]),:sha,true)"""),
                    {
                        "g": game,
                        "c": uuid4(),
                        "s": uuid4(),
                        "f": family,
                        "j": uuid4(),
                        "sha": "d" * 64,
                        "groups": [linked_group],
                    },
                )
            contexts = s.scalar(
                text("SELECT public.recording_photo_context_v2(:g,CAST(:ids AS uuid[]))"),
                {"g": game, "ids": source_ids},
            )
            facts = {r["sourceId"]: r for r in contexts}
            protected = facts[str(source_ids[-1])]
            assert protected["allowedRoles"] == (
                [] if kind in ("conflict", "unspecified") else ["VALIDATION"]
            )
            assert protected["priorRoles"] == (
                ["TRAIN", "VALIDATION"] if kind == "conflict" else ["VALIDATION"]
            )
            # Opaque component IDs expose no raw hash from a linked session.
            assert protected["aliasComponentIds"]
            assert not set(protected["aliasComponentIds"]) & {source_ids[-1].hex * 2, "d" * 64}
            assert all(
                not value.startswith(("byte:", "pixel:"))
                for value in protected["aliasComponentIds"]
            )
            doc = deepcopy(
                s.scalar(
                    text("SELECT document FROM grid_training_cohorts WHERE game_id=:g AND id=:c"),
                    {"g": game, "c": old_cohort},
                )
            )
            doc["policyVersion"] = "application-grid-corrections-v2"
            for item in doc["photoSplit"]["sources"]:
                item["registryProofSha256"] = facts[item["sourceId"]]["proofSha256"]
                if item["sourceId"] == str(source_ids[-1]):
                    item["role"] = "TRAIN"
            s.execute(
                text(
                    "INSERT INTO grid_training_cohorts(game_id,id,status,document,created_by) "
                    "VALUES(:g,:c,'preparing',CAST(:d AS jsonb),'fixture:1139')"
                ),
                {"g": game, "c": candidate, "d": json.dumps(doc)},
            )
            s.execute(
                text("""INSERT INTO grid_training_cohort_members
             (game_id,cohort_id,source_id,live_source_image_id,ordinal,role,frozen)
             SELECT game_id,:candidate,source_id,live_source_image_id,ordinal,
              CASE WHEN source_id=:target THEN 'TRAIN' ELSE role END,frozen
             FROM grid_training_cohort_members WHERE game_id=:g AND cohort_id=:old"""),
                {"candidate": candidate, "target": source_ids[-1], "g": game, "old": old_cohort},
            )
            for revision, status in enumerate(
                ("preview_ready", "materializing", "ready_to_freeze"), 2
            ):
                s.execute(
                    text(
                        "UPDATE grid_training_cohorts SET status=:s,revision=:r,"
                        "manifest_sha256=:h,manifest_path='fixture.json' WHERE game_id=:g AND id=:c"
                    ),
                    {"s": status, "r": revision, "h": "a" * 64, "g": game, "c": candidate},
                )
            quote = s.get_bind().dialect.identifier_preparer.quote
            s.execute(text(f"SET LOCAL ROLE {quote(db.role)}"))
            assert s.scalar(text("SELECT current_user")) == db.role
            # SQL's existing contract is RECORDING_ROLE_CONFLICT; the adapter
            # maps ambiguous contexts to GRID_CORRECTION_PROTECTION_CONFLICT.
            with pytest.raises(DBAPIError, match="RECORDING_ROLE_CONFLICT"), s.begin_nested():
                command(s, game, candidate, "register_cohort_use", 4)
            after = s.scalar(
                text("SELECT public.recording_photo_context_v2(:g,CAST(:ids AS uuid[]))"),
                {"g": game, "ids": [source_ids[-1]]},
            )[0]
            assert after == protected
            if kind in ("conflict", "unspecified"):
                with pytest.raises(DBAPIError, match="RECORDING_ROLE_CONFLICT"), s.begin_nested():
                    command(s, game, old_cohort, "validate_cohort_use", 5)
            s.execute(text("SET LOCAL ROLE NONE"))
            assert (
                s.scalar(text("SELECT count(*) FROM public.recording_photo_reservation_releases"))
                == 0
            )
            staged.rollback()
