from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import Mock
from uuid import UUID

import pytest
from game_predictor_api.application.verified_training_cohorts import (
    VerifiedTrainingCohortArtifactStore,
    VerifiedTrainingCohortService,
)
from game_predictor_api.domain.image_reviews import ImageReviewConflictError
from game_predictor_api.domain.verified_training_cohorts import SymbolCellTrainingExclusionCounts
from game_predictor_api.storage import symbol_cell_training_source_repository as source_repository
from game_predictor_api.storage.symbol_cell_training_source_repository import (
    SqlAlchemySymbolCellTrainingSourceRepository,
)
from game_predictor_worker.symbols import protected_sources as protection
from game_predictor_worker.symbols import training_dataset as datasets
from PIL import Image


def _original(root: Path, name: str, color: int, *, alias: bool = False) -> tuple[str, str, str]:
    relative = f"originals/{name}.jpg"
    path = root / "data" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (12, 9), (color, 10, 20)).save(path, "JPEG")
    content = path.read_bytes()
    if alias:
        # JPEG COM adds bytes without changing any decoded pixel.
        content = content[:2] + b"\xff\xfe\x00\x07alias" + content[2:]
        path.write_bytes(content)
    checksum = hashlib.sha256(content).hexdigest()
    pixels = protection.source_pixel_identity(root / "data", relative, checksum)
    return relative, checksum, pixels


def _descriptor(root: Path, monkeypatch: pytest.MonkeyPatch) -> protection.ProtectedSources:
    relative, checksum, pixels = _original(root, "protected", 20)
    payload = {
        "rows": [
            {
                "sourceRelativePath": relative,
                "sourceByteSha256": checksum,
                "normalizedPixelChecksumSha256": pixels,
            }
        ]
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    monkeypatch.setattr(protection, "DESCRIPTOR_SHA256", digest)
    path = root / "data" / protection.DESCRIPTOR_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"payload": payload, "sha256": digest}))
    protected = protection.load_protected_sources(root, protection.MUMIE_GAME_ID)
    assert protected is not None
    return protected


def test_missing_descriptor_blocks_only_pilot(tmp_path: Path) -> None:
    assert protection.load_protected_sources(tmp_path, "777") is None
    with pytest.raises(protection.ProtectedSourceError, match="unavailable"):
        protection.load_protected_sources(tmp_path, protection.MUMIE_GAME_ID)


def test_reencoded_alias_is_protected_and_new_loader_detects_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    protected = _descriptor(tmp_path, monkeypatch)
    relative, checksum, pixels = _original(tmp_path, "alias", 20, alias=True)
    assert checksum not in protected.byte_checksums
    assert protected.excludes(checksum, pixels)
    assert protection.load_protected_sources(tmp_path, protection.MUMIE_GAME_ID) == protected
    (tmp_path / "data" / "originals/protected.jpg").write_bytes(b"changed")
    with pytest.raises(protection.ProtectedSourceError) as caught:
        protection.load_protected_sources(tmp_path, protection.MUMIE_GAME_ID)
    assert caught.value.code == "PROTECTED_SOURCE_DRIFT"


def test_descriptor_tampering_and_historical_cohort_are_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    protected = _descriptor(tmp_path, monkeypatch)
    with pytest.raises(protection.ProtectedSourceError) as caught:
        protection.require_frozen_reference(protected, {"gameId": protection.MUMIE_GAME_ID})
    assert caught.value.code == "PROTECTED_SOURCE_COHORT_UNQUALIFIED"
    path = tmp_path / "data" / protection.DESCRIPTOR_PATH
    envelope = json.loads(path.read_text())
    envelope["payload"]["rows"] = []
    path.write_text(json.dumps(envelope))
    with pytest.raises(protection.ProtectedSourceError) as caught:
        protection.load_protected_sources(tmp_path, protection.MUMIE_GAME_ID)
    assert caught.value.code == "PROTECTED_SOURCE_DESCRIPTOR_DRIFT"


def test_guard_decodes_the_same_bytes_it_hashes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    relative, checksum, expected_pixels = _original(tmp_path, "source", 40)
    path = tmp_path / "data" / relative
    original_read = Path.read_bytes

    def read_and_replace(candidate: Path) -> bytes:
        content = original_read(candidate)
        if candidate == path:
            candidate.write_bytes(b"replacement after read")
        return content

    monkeypatch.setattr(Path, "read_bytes", read_and_replace)
    assert (
        protection.source_pixel_identity(tmp_path / "data", relative, checksum) == expected_pixels
    )
    with pytest.raises(protection.ProtectedSourceError) as caught:
        protection.source_pixel_identity(tmp_path / "data", relative, checksum)
    assert caught.value.code == "PROTECTED_SOURCE_DRIFT"


def test_preview_excludes_whole_alias_before_pool_and_freeze_rechecks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    protected = _descriptor(tmp_path, monkeypatch)
    source_result = Mock()
    source_result.scalar_one.return_value = 15
    pooled_result = Mock()
    pooled_result.mappings.return_value = ()
    session = Mock()
    session.execute.side_effect = (source_result, pooled_result)
    session.scalars.return_value.all.return_value = ("A",)
    decode = Mock(side_effect=AssertionError("Unselected photographs must not be decoded."))
    monkeypatch.setattr(source_repository.VirtualSymbolCellImageRenderer, "attest_source", decode)
    repository = SqlAlchemySymbolCellTrainingSourceRepository(session, tmp_path)
    monkeypatch.setattr(
        repository, "_exclusion_counts", lambda _: SymbolCellTrainingExclusionCounts()
    )
    service = VerifiedTrainingCohortService(
        Mock(), Mock(), VerifiedTrainingCohortArtifactStore(tmp_path), repository
    )
    preview = service.preview(game_id=UUID(protection.MUMIE_GAME_ID))
    assert preview.cell_sample_count == 0
    assert "PROTECTED_EVALUATION_SOURCE:15" in preview.warnings
    assert preview.manifest["protectedSourceExclusions"] == protected.reference()
    pool_call = session.execute.call_args_list[1]
    assert pool_call.args[1]["protected_pixels"] == sorted(protected.pixel_checksums)
    assert pool_call.args[1]["protected_bytes"] == sorted(protected.byte_checksums)
    statement = str(pool_call.args[0])
    assert statement.index("ANY(CAST(:protected_pixels") < statement.index(
        "source_rank <= :source_cap"
    )
    assert "c.source_geometry_revision_id = rb.source_geometry_revision_id" in statement
    assert "c.quality_issue IS NULL" in statement
    assert "s.status = 'active'" in statement
    decode.assert_not_called()
    (tmp_path / "data" / "originals/protected.jpg").write_bytes(b"changed after preview")
    with pytest.raises(ImageReviewConflictError) as caught:
        VerifiedTrainingCohortArtifactStore(tmp_path).write(preview)
    assert caught.value.code == "PROTECTED_SOURCE_DRIFT"


def test_live_pool_gate_rejects_protected_alias_with_forged_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _descriptor(tmp_path, monkeypatch)
    relative, checksum, _ = _original(tmp_path, "forged-alias", 20, alias=True)
    count_result = Mock()
    count_result.scalar_one.return_value = 0
    pooled_result = Mock()
    pooled_result.mappings.return_value = (
        {
            "source_relative_path": relative,
            "source_checksum_sha256": checksum,
            "normalized_pixel_checksum_sha256": "0" * 64,
        },
    )
    session = Mock()
    session.execute.side_effect = (count_result, pooled_result)
    repository = SqlAlchemySymbolCellTrainingSourceRepository(session, tmp_path)
    monkeypatch.setattr(
        repository, "_exclusion_counts", lambda _: SymbolCellTrainingExclusionCounts()
    )
    monkeypatch.setattr(
        source_repository, "_with_manifest_render_specs", lambda *_, **kw: kw["rows"]
    )
    render = Mock()
    monkeypatch.setattr(source_repository.VirtualSymbolCellImageRenderer, "render", render)
    with pytest.raises(ImageReviewConflictError) as caught:
        repository.inventory(game_id=UUID(protection.MUMIE_GAME_ID), lock_game=False)
    assert caught.value.code == "PROTECTED_EVALUATION_SOURCE"
    render.assert_not_called()


def test_live_pool_gate_decodes_each_selected_photo_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _descriptor(tmp_path, monkeypatch)
    relative, checksum, pixels = _original(tmp_path, "eligible", 75)
    count_result = Mock()
    count_result.scalar_one.return_value = 0
    row = {
        "source_relative_path": relative,
        "source_checksum_sha256": checksum,
        "normalized_pixel_checksum_sha256": pixels,
    }
    pooled_result = Mock()
    pooled_result.mappings.return_value = (row, row)
    session = Mock()
    session.execute.side_effect = (count_result, pooled_result)
    repository = SqlAlchemySymbolCellTrainingSourceRepository(session, tmp_path)
    monkeypatch.setattr(
        repository, "_exclusion_counts", lambda _: SymbolCellTrainingExclusionCounts()
    )
    monkeypatch.setattr(
        source_repository, "_with_manifest_render_specs", lambda *_, **kw: kw["rows"]
    )
    monkeypatch.setattr(repository, "_candidate_or_missing", lambda *_, **__: None)
    from game_predictor_api.application.virtual_cell_previews import VirtualSymbolCellImageRenderer

    original = VirtualSymbolCellImageRenderer.attest_source
    calls = []

    def decode(renderer, path, expected):
        calls.append((path, expected))
        return original(renderer, path, expected)

    monkeypatch.setattr(VirtualSymbolCellImageRenderer, "attest_source", decode)
    inventory = repository.inventory(game_id=UUID(protection.MUMIE_GAME_ID), lock_game=True)
    assert inventory.protected_cell_count == 0
    assert calls == [(tmp_path / "data" / relative, checksum)]


def _builder(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    protected: protection.ProtectedSources,
    *,
    protected_alias: bool = False,
) -> datasets.TrainingDatasetArtifact:
    cohort = {
        "gameId": protection.MUMIE_GAME_ID,
        "schemaVersion": 4,
        "protectedSourceExclusions": protected.reference(),
    }
    monkeypatch.setattr(datasets, "_read_cohort", lambda *_: cohort)
    monkeypatch.setattr(datasets, "_validate_declared_counts", lambda *_: None)
    samples = []
    for index in range(6):
        color = 20 if protected_alias else (60 if index < 2 else 60 + index * 20)
        relative, checksum, _ = _original(root, f"new-{index}", color, alias=index == 1)
        crop = root / f"crop-{index}.png"
        Image.new("RGB", (2, 2), (index, 0, 0)).save(crop)
        crop_checksum = hashlib.sha256(crop.read_bytes()).hexdigest()
        # Copy path stem is the checksum in the existing legacy materializer.
        content_path = root / f"{crop_checksum}.png"
        content_path.write_bytes(crop.read_bytes())
        samples.append(
            datasets._Sample(
                str(index),
                crop_checksum,
                content_path,
                "",
                "A",
                "A",
                checksum,
                str(index),
                checksum,
                relative,
                "job",
                "review",
                index + 1,
                0,
            )
        )
    monkeypatch.setattr(datasets, "_parse_samples", lambda *_, **__: tuple(samples))
    return datasets.build_cumulative_training_dataset(
        cohort_path=root / "cohort.json",
        expected_cohort_checksum_sha256="a" * 64,
        artifact_root=root,
        game_code="mumie",
        symbols=(datasets.TrainingSymbol("A", "A"),),
    )


def test_builder_rejects_protected_alias_before_materializing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    protected = _descriptor(tmp_path, monkeypatch)
    materialize = Mock()
    monkeypatch.setattr(datasets, "_materialize_sample_asset", materialize)
    with pytest.raises(datasets.TrainingDatasetBuildError) as caught:
        _builder(tmp_path, monkeypatch, protected, protected_alias=True)
    assert caught.value.code == "PROTECTED_EVALUATION_SOURCE"
    materialize.assert_not_called()


def test_new_pilot_split_groups_decoded_aliases_with_different_crops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    protected = _descriptor(tmp_path, monkeypatch)
    result = _builder(tmp_path, monkeypatch, protected)
    assert result.source_family_count == 5
    rows = result.manifest["samples"]
    assert isinstance(rows, list)
    first, alias = rows[:2]
    assert first["cropChecksumSha256"] != alias["cropChecksumSha256"]
    assert first["sourceImageChecksumSha256"] != alias["sourceImageChecksumSha256"]
    assert first["sourceFamily"] == alias["sourceFamily"]
    assert first["split"] == alias["split"]
    assert result.manifest["protectedSourceExclusions"] == protected.reference()
    replay = _builder(tmp_path, monkeypatch, protected)
    assert replay.reused
    assert replay.manifest_checksum_sha256 == result.manifest_checksum_sha256


def test_builder_rechecks_protected_sources_after_materialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    protected = _descriptor(tmp_path, monkeypatch)
    materialize = datasets._materialize_sample_asset

    def write_and_change(sample: datasets._Sample, destination: Path) -> None:
        materialize(sample, destination)
        (tmp_path / "data" / "originals/protected.jpg").write_bytes(b"changed while materializing")

    monkeypatch.setattr(datasets, "_materialize_sample_asset", write_and_change)
    with pytest.raises(datasets.TrainingDatasetBuildError) as caught:
        _builder(tmp_path, monkeypatch, protected)
    assert caught.value.code == "PROTECTED_SOURCE_DRIFT"


def _installer_module():
    script = Path(__file__).resolve().parents[3] / "scripts/install_mumie_feedback_controls.py"
    spec = importlib.util.spec_from_file_location("feedback_control_installer_test", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _install_inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module = _installer_module()
    source_root = tmp_path / "inputs"
    relative, byte, pixels = _original(source_root, "source", 90)
    proof = source_root / "proof.json"
    proof.write_text('{"immutable":"test-proof"}')
    proof_sha = hashlib.sha256(proof.read_bytes()).hexdigest()
    payload = {
        "gameId": protection.MUMIE_GAME_ID,
        "rows": [
            {
                "sourceByteSha256": byte,
                "normalizedPixelChecksumSha256": pixels,
                "sourceRelativePath": "training/protected/source.jpg",
            }
        ],
        "controlTruthProofs": [
            {"relativePath": "training/proofs/proof.json", "fileChecksumSha256": proof_sha}
        ],
        "controlTruthRows": [],
    }
    digest = module._digest(payload)
    monkeypatch.setattr(protection, "DESCRIPTOR_SHA256", digest)
    descriptor = source_root / "descriptor.json"
    descriptor.write_text(json.dumps({"payload": payload, "sha256": digest}))
    inventory_payload = {
        "rows": [{"sourceByteSha256": byte, "sourcePath": str(source_root / "data" / relative)}]
    }
    inventory = source_root / "inventory.json"
    inventory.write_text(
        json.dumps({"payload": inventory_payload, "sha256": module._digest(inventory_payload)})
    )
    plan = source_root / "copy-plan.json"
    plan.write_text(
        json.dumps(
            {
                "descriptorChecksumSha256": digest,
                "proofs": [
                    {
                        "relativePath": "training/proofs/proof.json",
                        "fileChecksumSha256": proof_sha,
                        "sourcePath": str(proof),
                    }
                ],
            }
        )
    )
    monkeypatch.setattr(
        module,
        "load_control_truth",
        lambda *args: ((), protection.ProtectedSources(frozenset(), frozenset()).reference()),
    )
    return module, {
        "artifact_root": tmp_path / "target",
        "descriptor": descriptor,
        "source_inventory": inventory,
        "proof_copy_plan": plan,
    }


def test_controls_installer_preview_writes_nothing_and_apply_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installer, inputs = _install_inputs(tmp_path, monkeypatch)
    preview = installer.install_controls(**inputs)
    assert preview["mode"] == "preview" and preview["filesToCreate"] == 3
    assert not inputs["artifact_root"].exists()
    applied = installer.install_controls(**inputs, apply=True)
    assert applied["filesCreated"] == 3
    replay = installer.install_controls(**inputs, apply=True)
    assert replay["filesCreated"] == 0 and replay["existingVerifiedFiles"] == 3
    assert replay["databaseWrites"] == 0


def test_controls_installer_rejects_existing_drift_without_any_new_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installer, inputs = _install_inputs(tmp_path, monkeypatch)
    target = inputs["artifact_root"] / "data/training/proofs/proof.json"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"existing-different-proof")
    before = sorted(
        path.relative_to(inputs["artifact_root"]) for path in inputs["artifact_root"].rglob("*")
    )
    with pytest.raises(ValueError, match="checksum changed"):
        installer.install_controls(**inputs, apply=True)
    assert target.read_bytes() == b"existing-different-proof"
    assert (
        sorted(
            path.relative_to(inputs["artifact_root"]) for path in inputs["artifact_root"].rglob("*")
        )
        == before
    )


def test_controls_installer_rejects_changed_inputs_and_unsafe_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installer, inputs = _install_inputs(tmp_path, monkeypatch)
    plan = json.loads(inputs["proof_copy_plan"].read_text())
    plan["proofs"][0]["relativePath"] = "../outside.json"
    inputs["proof_copy_plan"].write_text(json.dumps(plan))
    with pytest.raises(ValueError, match="differs from immutable"):
        installer.install_controls(**inputs, apply=True)
    assert not inputs["artifact_root"].exists()
    with pytest.raises(ValueError, match="Unsafe"):
        installer._target(tmp_path / "data", "a:stream")
    descriptor = json.loads(inputs["descriptor"].read_text())
    descriptor["payload"]["rows"] = []
    inputs["descriptor"].write_text(json.dumps(descriptor))
    with pytest.raises(ValueError, match="envelope checksum"):
        installer.install_controls(**inputs)


def test_controls_installer_recovers_partial_install_without_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installer, inputs = _install_inputs(tmp_path, monkeypatch)
    publish = installer._publish
    calls = 0

    def interrupt_after_source(copy, data_root):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated interruption")
        return publish(copy, data_root)

    monkeypatch.setattr(installer, "_publish", interrupt_after_source)
    with pytest.raises(OSError, match="simulated interruption"):
        installer.install_controls(**inputs, apply=True)
    assert not (inputs["artifact_root"] / "data" / protection.DESCRIPTOR_PATH).exists()
    monkeypatch.setattr(installer, "_publish", publish)
    receipt = installer.install_controls(**inputs, apply=True)
    assert receipt["existingVerifiedFiles"] == 1 and receipt["filesCreated"] == 2


def test_controls_installer_atomic_publish_cannot_overwrite_racing_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installer, inputs = _install_inputs(tmp_path, monkeypatch)
    descriptor = inputs["descriptor"]
    checksum = hashlib.sha256(descriptor.read_bytes()).hexdigest()
    target = inputs["artifact_root"] / "data" / protection.DESCRIPTOR_PATH
    link = installer.os.link

    def race(source, destination):
        Path(destination).write_bytes(b"another-writer")
        return link(source, destination)

    monkeypatch.setattr(installer.os, "link", race)
    with pytest.raises(ValueError, match="checksum changed"):
        installer._publish(
            installer._Copy(descriptor, protection.DESCRIPTOR_PATH, checksum),
            inputs["artifact_root"] / "data",
        )
    assert target.read_bytes() == b"another-writer"
    assert not tuple(target.parent.glob(".feedback-*"))
