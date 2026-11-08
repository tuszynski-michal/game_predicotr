"""Real exact-pixel aliases retain revision provenance and independent target pins."""

from __future__ import annotations

import json
import os
import time
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from _application_role_database import application_role_database
from game_predictor_api.domain.grid_cell_content import ContentError
from game_predictor_api.domain.grid_training_cohorts import GridCohortError
from game_predictor_api.domain.grid_visibility_contract import CellContentReference
from game_predictor_api.schemas.grid_cell_content import ContentSamplingPreview, ContentWriteCommand
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.grid_cell_content import SqlAlchemyGridCellContentRepository
from game_predictor_api.storage.grid_cell_content_pins import content_pin
from game_predictor_api.storage.grid_quality_observations import current_targets, read_source
from game_predictor_api.storage.grid_training_cohort_artifacts import GridCohortArtifactStore
from game_predictor_api.storage.grid_training_cohort_evidence import GridCohortEvidenceReader
from game_predictor_api.storage.models import SymbolModel
from game_predictor_worker.images.grid_cell_content_reference import frozen_content_reference
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_grid_training_cohort_e2e_postgres import (
    _install_base,
    _nodes,
    _providers,
    _save_source,
    _write_pattern,
    seed_source,
)
from test_v3_engine_acceptance_postgres import current_partition_budget  # noqa: F401

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit task-owned disposable PostgreSQL only",
)

POLICY = "full-symbol-content-sampling-v1"


def _alias_jpeg(root, relative_path, seed):
    # Change only fixture bytes BEFORE canonical loading/attestation/guarded save.
    # A real JPEG COM segment changes byte SHA without changing decoded pixels.
    path = _write_pattern(root, relative_path, 41)
    original = path.read_bytes()
    comment = relative_path.encode("utf-8")
    assert original[:2] == b"\xff\xd8"
    path.write_bytes(
        original[:2] + b"\xff\xfe" + (len(comment) + 2).to_bytes(2, "big") + comment + original[2:]
    )
    return path


def _alias_seed(*args, **kwargs):
    # Both own occurrences describe the same attested physical board sequence.
    base = 110 if kwargs["sequence_base"] == 120 else kwargs["sequence_base"]
    return seed_source(*args, **{**kwargs, "sequence_base": base})


def _cells(position):
    nodes = _nodes(position)
    return tuple(
        CellContentReference(
            state="visible",
            quad=(
                (p.x + 5, p.y + 5),
                (p.x + 25, p.y + 5),
                (p.x + 25, p.y + 25),
                (p.x + 5, p.y + 25),
            ),
        )
        for p in (nodes[(index // 5) * 6 + index % 5] for index in range(15))
    )


def _command(source, position, expected_revision):
    return ContentWriteCommand(
        idempotencyKey=uuid4(),
        sourceId=source.sourceId,
        expectedSourceSha256=source.sourceSha256,
        expectedPixelSha256=source.sourceRepresentativeSha256,
        positionIndex=position,
        sequenceNumber=110 + position,
        expectedRevision=expected_revision,
        cells=_cells(position),
        humanApproval=True,
    )


def _capture(factory, root, game, sources):
    captured = []
    with game_storage_scope(game), factory() as session:
        SqlAlchemyGridCellContentRepository(session, root).bind(game)
        reader = GridCohortEvidenceReader(session, root)
        for ordinal, source in enumerate(sources):
            # Read-only capture, with no invented role or cohort qualification.
            value = reader.capture(
                game,
                source.sourceId,
                ordinal,
                {"role": None, "qualification": "unresolved", "contentSamplingPolicy": POLICY},
                "grid-only",
            )
            assert value["used"] is False
            print(
                "ALIAS_CAPTURE",
                value["sourceId"],
                [(p["positionIndex"], p["reason"]) for p in value["positions"]],
                flush=True,
            )
            captured.append(value)
    return captured


def _project_real_pins(factory, root, game, sources):
    """Exercise alias pinning separately; this does not grant cohort admission."""
    result = []
    with game_storage_scope(game), factory() as session:
        SqlAlchemyGridCellContentRepository(session, root).bind(game)
        for identity in sources:
            source = read_source(session, game, identity.sourceId)
            assert source is not None
            targets = current_targets(session, game, identity.sourceId)
            positions = []
            for index, current in sorted(targets.items()):
                target = {
                    "positionIndex": index,
                    "sequenceNumber": current["board"]["sequence_number"],
                }
                target.update(content_pin(session, game, source, target, purpose=""))
                positions.append({"label": target})
            assert len(positions) == 9
            result.append(
                {"sourceId": str(identity.sourceId), "source": source, "positions": positions}
            )
    return result


def _verify_reader(root, game, captured, provenance, revision):
    artifacts = GridCohortArtifactStore(root)
    documents = []
    for value in captured:
        # Actual production byte/pixel/EXIF verification and immutable file copy.
        original = artifacts.copy_source(game, uuid4(), value["source"])
        source = {
            "sourceId": value["sourceId"],
            "sourceIdentity": value["source"],
            "original": original,
        }
        targets = [p["label"] for p in value["positions"]]
        for target in targets:
            annotation = target["contentAnnotation"]
            assert annotation["source"]["sourceId"] == str(provenance.sourceId)
            assert annotation["source"]["sourceSha256"] == provenance.sourceSha256
            pin = target["contentTargetSource"]
            assert pin["sourceId"] == source["sourceId"]
            assert pin["sourceSha256"] == source["sourceIdentity"]["checksum_sha256"]
            assert pin["sourceRepresentativeSha256"] == provenance.sourceRepresentativeSha256
            ref = frozen_content_reference(game, source, target)
            assert ref is not None and ref.revision == revision
            assert ref.cells == _cells(target["positionIndex"])
        documents.append((source, targets))
    # Both legal target identities resolve the same independent revision/contents.
    assert [t["contentReferenceSha256"] for t in documents[0][1]] == [
        t["contentReferenceSha256"] for t in documents[1][1]
    ]
    return documents


def _preview(factory, root, game, base, family, imports, provider_sha):
    command = ContentSamplingPreview(
        baseVersionId=base,
        familyId=family,
        importJobIds=imports,
    )
    with game_storage_scope(game), factory() as session:
        return SqlAlchemyGridCellContentRepository(session, root, provider_sha).sampling_preview(
            game,
            command,
        )


def test_real_pixel_aliases_share_content_without_cross_source_conflict_or_role_writes(tmp_path):
    started = time.monotonic()

    def stage(message):
        print(f"T1165 aliases +{time.monotonic() - started:.2f}s: {message}", flush=True)

    with application_role_database("t1165alias", ("content-alias", "content-other")) as db:
        stage("owned database migrated")
        receipt = Path("artifacts/TASK-1165-content-alias-owned.json")
        receipt.parent.mkdir(exist_ok=True)
        receipt.write_text(json.dumps({"database": db.owner_url.database, "role": db.role}))
        game, other = db.games.values()
        base, family = _install_base(db, game)
        providers = _providers(db, tmp_path, base)
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
        source_ids, imports = [], []
        with (
            patch("test_grid_training_cohort_e2e_postgres._write_pattern", _alias_jpeg),
            patch("test_grid_training_cohort_e2e_postgres.seed_source", _alias_seed),
        ):
            for ordinal in (1, 2):
                source, _, import_id = _save_source(db, tmp_path, game, ordinal, 9, {})
                source_ids.append(source)
                imports.append(import_id)
        factory = create_session_factory(db.app_engine)
        with game_storage_scope(game), factory() as session:
            repo = SqlAlchemyGridCellContentRepository(session, tmp_path)
            repo.bind(game)
            sources = [repo.current_source(game, source_id) for source_id in source_ids]
        first, second = sources
        assert first.sourceId != second.sourceId and first.sourceSha256 != second.sourceSha256
        assert first.sourceRepresentativeSha256 == second.sourceRepresentativeSha256
        assert (first.width, first.height, first.exifOrientation) == (
            second.width,
            second.height,
            second.exifOrientation,
        )
        stage("two guarded occurrences: different bytes, same normalized pixels and sequence")

        for field in ("expectedSourceSha256", "expectedPixelSha256"):
            with (
                pytest.raises(ContentError) as rejected,
                game_storage_scope(game),
                factory.begin() as session,
            ):
                SqlAlchemyGridCellContentRepository(session, tmp_path).write(
                    game,
                    _command(first, 0, 0).model_copy(update={field: "0" * 64}),
                    "local-owner",
                )
            assert rejected.value.code == "CONTENT_SOURCE_IDENTITY_CONFLICT"

        with game_storage_scope(game), factory.begin() as session:
            repo = SqlAlchemyGridCellContentRepository(session, tmp_path)
            for position in range(9):
                repo.write(game, _command(first, position, 0), "local-owner")
        captured = _capture(factory, tmp_path, game, sources)
        assert all(p["reason"] is None and p["label"] is not None for p in captured[0]["positions"])
        assert all(
            p["reason"] == "CURRENT_OWNER_UNAVAILABLE" and p["label"] is None
            for p in captured[1]["positions"]
        )
        projected = _project_real_pins(factory, tmp_path, game, sources)
        documents = _verify_reader(tmp_path, game, projected, first, 1)
        assert [p["label"]["contentReferenceSha256"] for p in captured[0]["positions"]] == [
            t["contentReferenceSha256"] for t in documents[0][1]
        ]
        preview = _preview(factory, tmp_path, game, base, family, imports, providers.index_sha256)
        reversed_preview = _preview(
            factory,
            tmp_path,
            game,
            base,
            family,
            list(reversed(imports)),
            providers.index_sha256,
        )
        assert preview == reversed_preview
        assert preview["state"] == "not_evaluable" and preview["roleWrites"] is False
        selection = preview["selection"]
        assert selection["fullPhotos"] == 1 and selection["missingFullPhotos"] == 4
        assert set(selection["sourceIds"]) == {str(source_id) for source_id in source_ids}
        assert selection["populationCellSlots"] == 135 and selection["unknownCellSlots"] == 0
        with (
            pytest.raises(ContentError) as unavailable,
            game_storage_scope(game),
            factory.begin() as session,
        ):
            SqlAlchemyGridCellContentRepository(session, tmp_path).write(
                game,
                _command(second, 0, 1),
                "local-owner",
            )
        assert unavailable.value.code == "CONTENT_TARGET_UNAVAILABLE"
        assert _project_real_pins(factory, tmp_path, game, sources) == projected
        for source, targets in documents:
            assert all(frozen_content_reference(game, source, t).revision == 1 for t in targets)
        stage("actual owner capture, both alias pins/readers, guarded approval and preview passed")

        # A third actual occurrence has conflicting upfront sequence evidence.
        # No saved canonical field, annotation or production helper is modified.
        with (
            patch("test_grid_training_cohort_e2e_postgres._write_pattern", _alias_jpeg),
            patch("test_grid_training_cohort_e2e_postgres.seed_source", _alias_seed),
        ):
            incompatible, _, incompatible_import = _save_source(db, tmp_path, game, 3, 1, {})
        with game_storage_scope(game), factory() as session:
            SqlAlchemyGridCellContentRepository(session, tmp_path).bind(game)
            rejected_capture = GridCohortEvidenceReader(session, tmp_path).capture(
                game,
                incompatible,
                0,
                {"role": None, "qualification": "unresolved", "contentSamplingPolicy": POLICY},
                "grid-only",
            )
            assert rejected_capture["positions"][0]["label"] is None
            assert (
                rejected_capture["positions"][0]["reason"] == "CONTENT_REFERENCE_IDENTITY_CONFLICT"
            )
        incompatible_preview = _preview(
            factory,
            tmp_path,
            game,
            base,
            family,
            imports + [incompatible_import],
            providers.index_sha256,
        )
        assert incompatible_preview["state"] == "not_evaluable"
        assert incompatible_preview["roleWrites"] is False

        source, targets = documents[1]
        for field, value in (
            ("sourceSha256", "0" * 64),
            ("sourceRepresentativeSha256", "0" * 64),
            ("width", second.width + 1),
        ):
            altered = deepcopy(targets[0])
            altered["contentTargetSource"][field] = value
            with pytest.raises(ContentError):
                frozen_content_reference(game, source, altered)
        with pytest.raises(GridCohortError):
            GridCohortArtifactStore(tmp_path).copy_source(
                game,
                uuid4(),
                {**captured[1]["source"], "checksum_sha256": "0" * 64},
            )
        with game_storage_scope(other), factory() as session:
            SqlAlchemyGridCellContentRepository(session, tmp_path).bind(other)
            assert session.scalar(text("SELECT count(*) FROM grid_cell_content_revisions")) == 0
        with game_storage_scope(game), factory() as session:
            SqlAlchemyGridCellContentRepository(session, tmp_path).bind(game)
            assert session.scalar(text("SELECT count(*) FROM grid_cell_content_revisions")) == 9
        with db.owner_engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM public.recording_photo_uses")) == 0
            assert (
                connection.scalar(text("SELECT count(*) FROM game_data_v2.grid_training_cohorts"))
                == 0
            )
        stage("bad checksums/pins rejected, RLS isolated and no role/cohort leaked")
    stage("owned database and role cleaned")
