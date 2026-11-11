"""Real pre-freeze labels/fresh REG/capture and SQL role freeze in an owned database.

The five REG photographs use genuine JPEGs and geometry writers. The additional
TRAIN/A rows are metadata-only SQL minimum fixtures, not a training dataset or
human repeatability proof. No training or operator database is used.
"""

import json
import os
import subprocess
import sys
from uuid import uuid4

import pytest
from _application_role_database import application_role_database
from game_predictor_api.domain.grid_correction_split import CorrectionSplitSource
from game_predictor_api.domain.grid_training_cohorts import digest
from game_predictor_api.schemas.grid_cell_content import ContentWriteCommand
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.grid_cell_content import SqlAlchemyGridCellContentRepository
from game_predictor_api.storage.grid_content_sampling import (
    ContentSamplingPreparationError,
    constrain_content_regression,
    resolve_content_sampling,
)
from game_predictor_api.storage.grid_correction_split import contexts
from game_predictor_api.storage.grid_quality_observations import read_source
from game_predictor_api.storage.grid_training_cohort_evidence import GridCohortEvidenceReader
from game_predictor_api.storage.grid_training_cohort_repository import (
    SqlAlchemyGridTrainingCohortRepository,
)
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_grid_training_cohort_e2e_postgres import _install_base, _providers, _save_source

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit task-owned disposable PostgreSQL only",
)

COLD = r"""
import json,os
from pathlib import Path
from uuid import UUID,uuid4
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url
from game_predictor_api.domain.grid_training_cohorts import digest
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.grid_cell_content import SqlAlchemyGridCellContentRepository
url=os.environ['ANNOTATION_TEST_URL']
assert make_url(url).database.startswith('game_predictor_t1185ann_')
assert make_url(url).database.endswith('_test')
engine=create_engine(url,connect_args={'connect_timeout':5})
game,cohort=UUID(os.environ['ANNOTATION_GAME']),UUID(os.environ['ANNOTATION_COHORT'])
with game_storage_scope(game),create_session_factory(engine)() as session:
 repo=SqlAlchemyGridCellContentRepository(session,Path(os.environ['ANNOTATION_ROOT']))
 repo.bind(game)
 row=session.execute(text('SELECT status,manifest_path,manifest_sha256 '
  'FROM grid_training_cohorts WHERE game_id=:g AND id=:c'),{'g':game,'c':cohort}).one()
 assert row.status=='frozen'
 capture=json.loads((repo.root/row.manifest_path).read_text())
 assert digest(capture)==row.manifest_sha256
 members=session.scalars(text("SELECT frozen FROM grid_training_cohort_members "
  "WHERE game_id=:g AND cohort_id=:c AND role='REGRESSION' ORDER BY ordinal"),
  {'g':game,'c':cohort}).all()
 assert len(members)==5 and members==capture['regressionSources']
 for member in members:
  for position in member['positions']:
   label=position['label']; assert label and label['contentReferenceRevision']==1
   annotation=repo.get(game,UUID(member['sourceId']),label['positionIndex'])
   assert annotation['contentReferenceSha256']==label['contentReferenceSha256']
   assert label['contentAnnotation']['origin']=='manual'
   assert label['contentAnnotation']['reference']['humanApproved'] is True
 request={'kind':'validate_cohort_use','cohortId':str(cohort),'expectedRevision':5,
  'idempotencyKey':str(uuid4()),'manifestSha256':row.manifest_sha256}
 session.scalar(text("SELECT public.recording_cohort_command_v7"
  "(:g,CAST(:q AS jsonb),'fixture')"),{'g':game,'q':json.dumps(request)})
engine.dispose()
print('COLD_PREFREEZE_CONTENT_CAPTURE_PASS',flush=True)
"""


def test_prefreeze_ordinary_labels_keep_fresh_reg_and_are_captured_before_real_role_freeze(
    tmp_path,
):
    with application_role_database("t1185ann", ("annotation", "foreign")) as db:
        game, foreign = db.games.values()
        base, family = _install_base(db, game)
        providers = _providers(db, tmp_path, base)
        factory = create_session_factory(db.app_engine)
        real = [_save_source(db, tmp_path, game, ordinal, 9, {}) for ordinal in range(1, 6)]
        source_ids = [entry[0] for entry in real]
        print("T1185 five real originals / 45 geometry boards ready", flush=True)
        with game_storage_scope(game), factory() as session:
            repo = SqlAlchemyGridCellContentRepository(session, tmp_path)
            repo.bind(game)
            population = [
                CorrectionSplitSource(
                    source_id=str(source),
                    import_id=str(job),
                    byte_sha256=sha[0],
                    pixel_sha256=sha[1],
                    logical_filename=f"photo-{index}.jpg",
                    eligible_boards=9,
                    board_bindings=tuple((slot, 110 + index * 10 + slot) for slot in range(9)),
                )
                for index, (source, sha, job) in enumerate(real)
            ]
            facts = contexts(repo, game, list(map(str, source_ids)), purpose_aware=True)
            policy = resolve_content_sampling(
                SqlAlchemyGridTrainingCohortRepository(session, tmp_path),
                game,
                base,
                family,
                providers.index_sha256,
            )
            with pytest.raises(ContentSamplingPreparationError) as missing:
                constrain_content_regression(repo, game, population, facts, policy)
            assert set(missing.value.report["sourceIds"]) == set(map(str, source_ids))
            assert missing.value.report["fullPhotos"] == 0
            before_population = missing.value.report["populationSha256"]
            with db.owner_engine.connect() as owner:
                assert owner.scalar(text("SELECT count(*) FROM public.recording_photo_uses")) == 0
        commands = []
        for source, _sha, _job in real:
            with game_storage_scope(game), factory() as session:
                repo = SqlAlchemyGridCellContentRepository(session, tmp_path)
                page = repo.list_source_targets(game, [source], 20, 0)
                assert len(page["items"]) == 9
                assert all(
                    item["state"] == "ready" and item["role"] is None for item in page["items"]
                )
                identity = page["items"][0]["source"]
                asset = repo.annotation_source_asset(
                    game, source, identity["sourceSha256"], identity["sourceRepresentativeSha256"]
                )
                assert asset.is_file()
                assert repo.get(game, source, 0)["annotation"] is None
            for target in page["items"]:
                # Non-visible cells have observed absence, not invented symbol bounds.
                command = ContentWriteCommand(
                    idempotencyKey=uuid4(),
                    sourceId=source,
                    expectedSourceSha256=identity["sourceSha256"],
                    expectedPixelSha256=identity["sourceRepresentativeSha256"],
                    positionIndex=target["positionIndex"],
                    sequenceNumber=target["sequenceNumber"],
                    expectedRevision=0,
                    humanApproval=True,
                    cells=[{"state": "out_of_frame"} for _ in range(15)],
                )
                with game_storage_scope(game), factory.begin() as session:
                    result = SqlAlchemyGridCellContentRepository(session, tmp_path).write(
                        game, command, "local-owner"
                    )
                commands.append((command, result))
        with game_storage_scope(game), factory.begin() as session:
            assert (
                SqlAlchemyGridCellContentRepository(session, tmp_path).write(
                    game, commands[0][0], "local-owner"
                )
                == commands[0][1]
            )  # Lost response retains the exact request/receipt.
        with game_storage_scope(game), factory() as session:
            repo = SqlAlchemyGridCellContentRepository(session, tmp_path)
            repo.bind(game)
            facts = contexts(repo, game, list(map(str, source_ids)), purpose_aware=True)
            assert all(value["priorRoles"] == [] for value in facts.values())
            _constrained, selected = constrain_content_regression(
                repo, game, population, facts, policy
            )
            assert selected["state"] == "ready" and selected["fullPhotos"] == 5
            assert selected["populationSha256"] == before_population
            assert set(selected["sourceIds"]) == set(map(str, source_ids))
            assert selected["roleWrites"] is False
            with db.owner_engine.connect() as owner:
                assert owner.scalar(text("SELECT count(*) FROM public.recording_photo_uses")) == 0
            captured = [
                GridCohortEvidenceReader(session, tmp_path).capture(
                    game,
                    source,
                    index,
                    {
                        "role": "REGRESSION",
                        "qualification": "eligible",
                        "reasonCodes": [],
                        "evidenceLevel": "photo-only",
                        "assessmentPolicy": "human-labeled-targets-v1",
                        "contentSamplingPolicy": "full-symbol-content-sampling-v1",
                    },
                    "grid-only",
                )
                for index, source in enumerate(source_ids)
            ]
            assert all(source["boardEligibleCount"] == 9 for source in captured)
            assert all(
                p["label"]["contentReferenceRevision"] == 1
                for s in captured
                for p in s["positions"]
            )
            identities = [read_source(session, game, source) for source in source_ids]
        # The SQL freeze minimum fixture has no trained dataset or blind-A claim.
        # REG members above are real captured evidence; other role rows only exercise
        # the existing capability's role minima and immutable registration boundary.
        _freeze_registered_capture(db, tmp_path, game, family, real, identities, captured)


def _freeze_registered_capture(db, root, game, family, real, identities, captured):
    cohort = uuid4()
    extra = [uuid4() for _ in range(15)]
    job = real[0][2]
    with Session(db.owner_engine) as session, session.begin(), game_storage_scope(game):
        repo = SqlAlchemyGridCellContentRepository(session, root)
        repo.bind(game, write=True)
        for source in extra:
            sha = source.hex * 2
            session.execute(
                text(
                    "INSERT INTO public.image_file_executions(file_execution_key,"
                    "source_checksum_sha256,pipeline_fingerprint,checkpoint_payload,status) "
                    "VALUES(:s,:s,:s,'{}','completed')"
                ),
                {"s": sha},
            )
            session.execute(
                text("""INSERT INTO source_images(game_id,id,import_job_id,file_execution_key,
                relative_path,checksum_sha256,width,height,status,raw_width,raw_height,oriented_width,
                oriented_height,coordinate_space,normalization_adapter_version,normalized_pixel_checksum_sha256)
                VALUES(:g,:s,:j,:sha,'metadata-only-fixture.jpg',:sha,100,100,'completed',100,100,100,100,
                'exif-normalized-rgb-pixels-v1','fixture-v1',:sha)"""),
                {"g": game, "s": source, "j": job, "sha": sha},
            )
        ids = extra + [entry[0] for entry in real]
        facts = contexts(repo, game, list(map(str, ids)), purpose_aware=True)
        roles = ["TRAIN"] * 10 + ["VALIDATION"] * 5 + ["REGRESSION"] * 5
        pins = []
        for index, source in enumerate(ids):
            identity = identities[index - 15] if index >= 15 else None
            pins.append(
                {
                    "sourceId": str(source),
                    "importId": str(real[index - 15][2] if index >= 15 else job),
                    "sourceSha256": identity["checksum_sha256"] if identity else source.hex * 2,
                    "pixelSha256": identity["normalized_pixel_checksum_sha256"]
                    if identity
                    else source.hex * 2,
                    "role": roles[index],
                    "buffer": False,
                    "validationPurpose": "A" if roles[index] == "VALIDATION" else None,
                    "registryProofSha256": facts[str(source)]["proofSha256"],
                }
            )
        document = {
            "policyVersion": "application-grid-corrections-v4",
            "mode": "screen+grid",
            "familyId": str(family),
            "photoSplit": {
                "sha256": digest(pins),
                "sources": pins,
                "contentSampling": {"policy": "full-symbol-content-sampling-v1"},
                "learningMaterial": {"version": "effective-grid-learning-material-v1"},
            },
        }
        session.execute(
            text(
                "INSERT INTO grid_training_cohorts(game_id,id,status,document,created_by) "
                "VALUES(:g,:c,'preparing',CAST(:d AS jsonb),'fixture')"
            ),
            {"g": game, "c": cohort, "d": json.dumps(document)},
        )
        for index, source in enumerate(ids):
            frozen = (
                captured[index - 15]
                if index >= 15
                else {
                    "used": True,
                    "boardEligibleCount": 9,
                    "screenEligible": True,
                    "positions": [{"label": {}} for _ in range(9)],
                    "recording": {
                        "qualification": "eligible",
                        "evidenceLevel": "photo-only",
                        "validationPurpose": "A" if roles[index] == "VALIDATION" else None,
                    },
                }
            )
            session.execute(
                text(
                    "INSERT INTO grid_training_cohort_members(game_id,cohort_id,source_id,"
                    "live_source_image_id,ordinal,role,frozen) "
                    "VALUES(:g,:c,:s,:s,:o,:r,CAST(:f AS jsonb))"
                ),
                {
                    "g": game,
                    "c": cohort,
                    "s": source,
                    "o": index,
                    "r": roles[index],
                    "f": json.dumps(frozen),
                },
            )
        capture = {"version": "prefreeze-annotation-capture-test-v1", "regressionSources": captured}
        relative = f"data/annotation-test-capture-{cohort}.json"
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(capture), encoding="utf-8")
        for revision, status in enumerate(("preview_ready", "materializing", "ready_to_freeze"), 2):
            session.execute(
                text(
                    "UPDATE grid_training_cohorts SET status=:s,revision=:r,manifest_path=:p,"
                    "manifest_sha256=:h WHERE game_id=:g AND id=:c"
                ),
                {
                    "g": game,
                    "c": cohort,
                    "s": status,
                    "r": revision,
                    "p": relative,
                    "h": digest(capture),
                },
            )
    with game_storage_scope(game), create_session_factory(db.app_engine).begin() as session:
        SqlAlchemyGridCellContentRepository(session, root).bind(game, write=True)
        request = json.dumps(
            {
                "kind": "register_cohort_use",
                "cohortId": str(cohort),
                "expectedRevision": 4,
                "idempotencyKey": str(uuid4()),
                "manifestSha256": digest(capture),
            }
        )
        session.scalar(
            text("SELECT public.recording_cohort_command_v7(:g,CAST(:q AS jsonb),'fixture')"),
            {"g": game, "q": request},
        )
        session.execute(
            text(
                "UPDATE grid_training_cohorts SET status='frozen',revision=5 "
                "WHERE game_id=:g AND id=:c"
            ),
            {"g": game, "c": cohort},
        )
    result = subprocess.run(
        [sys.executable, "-c", COLD],
        env=db.subprocess_environment(
            ANNOTATION_TEST_URL=db.app_url.render_as_string(hide_password=False),
            ANNOTATION_GAME=str(game),
            ANNOTATION_COHORT=str(cohort),
            ANNOTATION_ROOT=str(root),
        ),
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "COLD_PREFREEZE_CONTENT_CAPTURE_PASS" in result.stdout
