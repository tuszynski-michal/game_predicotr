"""Detached annotation provenance survives on a live, verified target alias only."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from _application_role_database import application_role_database
from game_predictor_api.domain.grid_cell_content import ContentError
from game_predictor_api.domain.grid_training_cohorts import GridCohortError
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.grid_cell_content import SqlAlchemyGridCellContentRepository
from game_predictor_api.storage.grid_cell_content_pins import (
    content_pin,
    require_current_content_pin,
)
from game_predictor_api.storage.grid_quality_observations import read_source
from game_predictor_api.storage.grid_training_cohort_artifacts import GridCohortArtifactStore
from game_predictor_api.storage.grid_training_cohort_currentness import inspect_member
from game_predictor_api.storage.grid_training_cohort_evidence import GridCohortEvidenceReader
from game_predictor_api.storage.models import SymbolModel
from game_predictor_worker.images.grid_cell_content_reference import frozen_content_reference
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_grid_content_alias_pipeline import POLICY, _alias_jpeg, _alias_seed, _command
from test_grid_training_cohort_e2e_postgres import _install_base, _save_source
from test_v3_engine_acceptance_postgres import current_partition_budget  # noqa: F401

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit task-owned disposable PostgreSQL only",
)


def test_detached_link_retains_alias_pin_but_unavailable_target_is_blocked(tmp_path):
    started = time.monotonic()

    def stage(message):
        print(f"T1166 detached +{time.monotonic() - started:.2f}s: {message}", flush=True)

    with application_role_database(
        "t1166detach", ("content-detach", "content-other"), revision="0182_cell_content_references"
    ) as db:
        Path("artifacts/TASK-1166-detached-owned.json").write_text(
            json.dumps({"database": db.owner_url.database, "role": db.role}), encoding="utf-8"
        )
        stage("owned database migrated")
        game, other = db.games.values()
        _install_base(db, game)
        with Session(db.owner_engine) as session, session.begin():
            session.add(
                SymbolModel(
                    game_id=game,
                    code="FIXTURE",
                    name="Fixture",
                    mobile_code=1,
                    display_order=1,
                    status="active",
                )
            )
        with (
            patch("test_grid_training_cohort_e2e_postgres._write_pattern", _alias_jpeg),
            patch("test_grid_training_cohort_e2e_postgres.seed_source", _alias_seed),
        ):
            origin, _, _ = _save_source(db, tmp_path, game, 1, 1, {})
            alias, _, _ = _save_source(db, tmp_path, game, 2, 1, {})
        factory = create_session_factory(db.app_engine)
        with game_storage_scope(game), factory.begin() as session:
            repo = SqlAlchemyGridCellContentRepository(session, tmp_path)
            repo.bind(game, write=True)
            original_identity = repo.current_source(game, origin)
            target_identity = repo.current_source(game, alias)
            saved = repo.write(game, _command(original_identity, 0, 0), "local-owner")
            source = read_source(session, game, alias)
            target = {"positionIndex": 0, "sequenceNumber": 110}
            target.update(content_pin(session, game, source, target, purpose="TRAIN"))
            require_current_content_pin(session, game, target)
        assert (
            original_identity.sourceRepresentativeSha256
            == target_identity.sourceRepresentativeSha256
        )
        assert original_identity.sourceSha256 != target_identity.sourceSha256
        original_pin = deepcopy(target)
        original_sha = saved["contentReferenceSha256"]
        stage("own approval and distinct target alias pin captured")

        # Guarded source deletion is forbidden; only nullable linkage detachment
        # is allowed. This does not claim physical deletion of the guarded origin.
        with game_storage_scope(game), factory.begin() as session:
            SqlAlchemyGridCellContentRepository(session, tmp_path).bind(game, write=True)
            with (
                pytest.raises(DBAPIError, match="image_board_geometry_pending"),
                session.begin_nested(),
            ):
                session.execute(
                    text("DELETE FROM source_images WHERE game_id=:g AND id=:s"),
                    {"g": game, "s": origin},
                )
            session.execute(
                text(
                    "UPDATE grid_cell_content_revisions SET live_source_image_id=NULL "
                    "WHERE game_id=:g AND source_id=:s"
                ),
                {"g": game, "s": origin},
            )
        with game_storage_scope(game), factory() as session:
            repo = SqlAlchemyGridCellContentRepository(session, tmp_path)
            repo.bind(game)
            retained = repo.latest(game, target_identity.sourceRepresentativeSha256, 0)
            assert retained.live_source_image_id is None
            assert retained.document_sha256 == original_sha
            assert retained.document == original_pin["contentAnnotation"]
            assert read_source(session, game, origin) is not None
            source = read_source(session, game, alias)
            assert source is not None
            recaptured = content_pin(
                session, game, source, {"positionIndex": 0, "sequenceNumber": 110}, purpose="TRAIN"
            )
            assert recaptured == {
                k: v
                for k, v in original_pin.items()
                if k not in {"positionIndex", "sequenceNumber"}
            }
            require_current_content_pin(session, game, original_pin)
            require_current_content_pin(session, game, original_pin, source=source)
            # Legacy pin still identifies its own source and cannot silently
            # borrow a different alias without a target-source binding.
            legacy = {k: v for k, v in original_pin.items() if k != "contentTargetSource"}
            require_current_content_pin(session, game, legacy)
            with pytest.raises(ContentError, match="identity changed"):
                require_current_content_pin(session, game, legacy, source=source)
            with pytest.raises(ContentError):
                require_current_content_pin(session, game, {**original_pin, "sequenceNumber": 111})
            changed = deepcopy(original_pin)
            changed["contentTargetSource"]["sourceSha256"] = "0" * 64
            with pytest.raises(ContentError):
                require_current_content_pin(session, game, changed)
            captured = GridCohortEvidenceReader(session, tmp_path).capture(
                game,
                origin,
                0,
                {"role": "TRAIN", "qualification": "eligible", "contentSamplingPolicy": POLICY},
                "grid-only",
            )
            assert captured["positions"][0]["label"] is not None
            member = SimpleNamespace(
                frozen=captured,
                live_source_image_id=origin,
                source_id=origin,
                game_id=game,
                role="TRAIN",
            )
            assert inspect_member(SimpleNamespace(session=session), member).error is None
        stage("legal linkage detach; actual owner capture and both content pins remain current")

        artifacts = GridCohortArtifactStore(tmp_path)
        copied = artifacts.copy_source(game, uuid4(), source)
        frozen = {"sourceId": str(alias), "sourceIdentity": source, "original": copied}
        assert frozen_content_reference(game, frozen, original_pin) is not None
        cold = """
import json,os
from pathlib import Path
from uuid import UUID
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.grid_cell_content import SqlAlchemyGridCellContentRepository
from game_predictor_api.storage.grid_cell_content_pins import require_current_content_pin
engine=create_engine(os.environ['CONTENT_TEST_APP_URL'])
game=UUID(os.environ['CONTENT_TEST_GAME'])
with game_storage_scope(game), Session(engine) as session:
    SqlAlchemyGridCellContentRepository(session,Path('.')).bind(game)
    require_current_content_pin(session,game,json.loads(os.environ['CONTENT_TEST_PIN']))
engine.dispose()
print('DETACHED_ALIAS_COLD_PASS')
"""
        result = subprocess.run(
            [sys.executable, "-c", cold],
            timeout=30,
            capture_output=True,
            text=True,
            env=db.subprocess_environment(
                CONTENT_TEST_APP_URL=db.app_url.render_as_string(hide_password=False),
                CONTENT_TEST_GAME=str(game),
                CONTENT_TEST_PIN=json.dumps(original_pin),
            ),
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "DETACHED_ALIAS_COLD_PASS" in result.stdout
        with game_storage_scope(other), factory() as session:
            SqlAlchemyGridCellContentRepository(session, tmp_path).bind(other)
            with pytest.raises(ContentError):
                require_current_content_pin(session, other, original_pin)
        target_path = artifacts.safe("data/" + source["relative_path"])
        assert (
            (tmp_path / "data" / source["relative_path"])
            .resolve()
            .is_relative_to(tmp_path.resolve())
        )
        original_bytes = target_path.read_bytes()
        try:
            target_path.unlink()
            # Metadata retention is not proof of available actual target pixels.
            # Production copying must refuse new use when its original is missing.
            with pytest.raises(GridCohortError) as unavailable:
                artifacts.copy_source(game, uuid4(), source)
            assert unavailable.value.code == "SOURCE_BYTES_UNAVAILABLE"
        finally:
            target_path.write_bytes(original_bytes)
        with game_storage_scope(game), factory() as session:
            SqlAlchemyGridCellContentRepository(session, tmp_path).bind(game)
            # A pin for an absent target UUID fails independently of original
            # annotation liveness; it never falls back to the annotation source.
            absent = deepcopy(original_pin)
            absent["contentTargetSource"]["sourceId"] = str(uuid4())
            with pytest.raises(ContentError, match="removed"):
                require_current_content_pin(session, game, absent)
            member.live_source_image_id = None
            assert (
                inspect_member(SimpleNamespace(session=session), member).error.code
                == "SOURCE_REMOVED_NEW_USE_BLOCKED"
            )
            assert session.scalar(text("SELECT count(*) FROM grid_cell_content_revisions")) == 1
        stage("cold process, RLS, missing target file/UUID and detached-member guard verified")
    stage("owned database and role cleaned")
