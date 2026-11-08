"""Targeted real crop registry/source support, not the full training workflow."""

import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from _application_role_database import application_role_database
from game_predictor_api.domain.source_crop import (
    cropped_original_relative_paths,
    decode_attestation,
)
from game_predictor_api.storage.full_board_input_variant import current_variant_source_box
from game_predictor_api.storage.source_image_crop_repository import SourceImageCropRepository
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Owned disposable PostgreSQL only",
)
PIN = {"automaticQualification": {"profile": {"version": "full-board-auto-profile-v3"}}}

COLD = """
import json,os
from pathlib import Path
from sqlalchemy import create_engine,text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool
from game_predictor_api.storage.full_board_input_variant import current_variant_source_box
url=os.environ['TEST_DATABASE_URL']; expected=os.environ['TEST_DATABASE_NAME']
assert expected.startswith('game_predictor_t1167stamp_') and expected.endswith('_test')
engine=create_engine(url,poolclass=NullPool)
with engine.connect() as c: assert c.scalar(text('SELECT current_database()'))==expected
value=json.loads(os.environ['STAMP_CASE']); value['artifact_root']=Path(value['artifact_root'])
with Session(engine) as s:
 assert current_variant_source_box(s,**value)==tuple(json.loads(os.environ['STAMP_EXPECTED']))
engine.dispose();print('Cold explicit-owned crop support PASS',flush=True)
"""

CLEAN = """
import os
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool
from game_predictor_api.config import ApiSettings
name=os.environ['TEST_DATABASE_NAME'];role=os.environ['TEST_ROLE_NAME']
assert name.startswith('game_predictor_t1167stamp_') and name.endswith('_test')
assert role.startswith('game_predictor_app_test_')
engine=create_engine(make_url(ApiSettings.from_environment().owner_database_url).set(database='postgres'),poolclass=NullPool)
with engine.connect() as c:
 assert c.scalar(text('SELECT current_database()'))=='postgres'
 counts=(
  c.scalar(text('SELECT count(*) FROM pg_database WHERE datname=:n'),{'n':name}),
  c.scalar(text('SELECT count(*) FROM pg_roles WHERE rolname=:r'),{'r':role}))
 assert counts==(0,0),counts
engine.dispose();print('Fresh cleanup 0 databases / 0 roles',flush=True)
"""


def test_actual_crop_registry_current_source_and_cold_read(tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from test_source_crop_api import _managed

    checksum, _ = _managed(tmp_path, crop=False)
    relative = f"originals/{checksum[:2]}/{checksum}.jpg"
    original = tmp_path / "data" / relative
    content = original.read_bytes()
    _managed(tmp_path, crop=True)
    _, attestation_relative = cropped_original_relative_paths(checksum)
    attestation_bytes = (tmp_path / "data" / attestation_relative).read_bytes()
    attestation = decode_attestation(attestation_bytes, expected_original_checksum_sha256=checksum)
    original.write_bytes(content)
    case = dict(
        pin=PIN,
        source_sha256=checksum,
        width=128,
        height=96,
        artifact_root=tmp_path,
        source_relative_path=relative,
        normalized_pixel_sha256=attestation.original_normalized_pixel_checksum_sha256,
    )
    receipt = {}
    try:
        with application_role_database("t1167stamp", ()) as db:
            receipt = {"database": db.owner_url.database, "role": db.role}
            Path("artifacts/TASK-1167-AC8-stamp-owned.json").write_text(
                json.dumps(receipt), encoding="utf-8"
            )
            assert str(db.app_url.database).startswith("game_predictor_t1167stamp_")
            with db.app_engine.connect() as connection:
                assert connection.scalar(text("SELECT current_database()")) == db.owner_url.database
            print("Owned stamp database migrated", flush=True)
            with Session(db.app_engine) as session:
                assert current_variant_source_box(session, **case) == (0, 0, 128, 96)
            with Session(db.owner_engine) as session, session.begin():
                SourceImageCropRepository(session).record_verified(
                    attestation,
                    attestation_sha256=hashlib.sha256(attestation_bytes).hexdigest(),
                    job_id=None,
                    verified_at=datetime.now(UTC),
                )
            with Session(db.app_engine) as session:
                assert current_variant_source_box(session, **case) == (0, 0, 128, 96)
            # Same physical bytes at a separate live target path, before origin detachment.
            copy = tmp_path / "data" / "live-copy.jpg"
            copy.write_bytes(content)
            original.unlink()
            with Session(db.app_engine) as session:
                assert (
                    current_variant_source_box(session, **case) == ()
                )  # metadata not committed deleted yet
            with Session(db.owner_engine) as session, session.begin():
                SourceImageCropRepository(session).mark_original_deleted(
                    checksum, deleted_at=datetime.now(UTC)
                )
            expected = tuple(attestation.crop_box.as_list())
            with Session(db.app_engine) as session:
                assert current_variant_source_box(session, **case) == expected
                assert current_variant_source_box(
                    session, **{**case, "source_relative_path": "live-copy.jpg"}
                ) == (0, 0, 128, 96)
                assert (
                    current_variant_source_box(
                        session, **{**case, "normalized_pixel_sha256": "0" * 64}
                    )
                    == ()
                )
                assert (
                    current_variant_source_box(session, **{**case, "source_relative_path": None})
                    == ()
                )
            copy.unlink()
            with Session(db.app_engine) as session:
                assert (
                    current_variant_source_box(
                        session, **{**case, "source_relative_path": "live-copy.jpg"}
                    )
                    == ()
                )
            env = {
                **os.environ,
                "TEST_DATABASE_URL": db.app_url.render_as_string(hide_password=False),
                "TEST_DATABASE_NAME": str(db.owner_url.database),
                "STAMP_CASE": json.dumps({**case, "artifact_root": str(tmp_path)}),
                "STAMP_EXPECTED": json.dumps(expected),
            }
            child = subprocess.run(
                [sys.executable, "-c", COLD], env=env, timeout=30, capture_output=True, text=True
            )
            assert child.returncode == 0, child.stdout + child.stderr
            print(child.stdout, flush=True)
            print("Full/crop/inconsistent/live-copy/missing-target checks PASS", flush=True)
    finally:
        if receipt:
            env = {
                **os.environ,
                "TEST_DATABASE_NAME": receipt["database"],
                "TEST_ROLE_NAME": receipt["role"],
            }
            cleanup = subprocess.run(
                [sys.executable, "-c", CLEAN], env=env, timeout=30, capture_output=True, text=True
            )
            assert cleanup.returncode == 0, cleanup.stdout + cleanup.stderr
            print(cleanup.stdout, flush=True)
