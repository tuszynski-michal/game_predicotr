"""Tiny generated CPU-only snapshots; no operator images, models or training."""

from __future__ import annotations

import copy
import hashlib
import io
import json
import shutil
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest
from game_predictor_api.domain.canonical_source import (
    CANONICAL_SOURCE_LOADER_VERSION,
    RGB_PIXEL_CHECKSUM_VERSION,
    decode_canonical_source_bytes,
)
from game_predictor_api.domain.grid_model_registry import descriptor_sha256, historical_catalogue
from game_predictor_worker.filesystem import long_path_aware
from game_predictor_worker.images import grid_cohort_dataset as grid_dataset
from game_predictor_worker.images.grid_cohort_dataset import (
    GridBoardDataset,
    GridCohortDatasetError,
    GridCohortSnapshot,
    GridScreenDataset,
)
from PIL import Image


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


class SnapshotFixture:
    def __init__(self, root: Path):
        self.root, self.game, self.cohort = root, str(uuid4()), str(uuid4())
        self.directory = f"data/grid-training-cohorts/{self.game}/{self.cohort}"
        self.base = copy.deepcopy(historical_catalogue()[0])
        self.sources = []
        self.page_size = 5

    def pin(self, relative, content):
        path = long_path_aware(self.root / relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return {
            "path": relative,
            "sha256": hashlib.sha256(content).hexdigest(),
            "bytes": len(content),
        }

    def source(self, role="TRAIN", *, full=False, used=True, origin="human_corrected"):
        output = io.BytesIO()
        Image.new("RGB", (64, 48), (len(self.sources) * 10, 70, 90)).save(output, format="JPEG")
        content = output.getvalue()
        raw_sha = hashlib.sha256(content).hexdigest()
        normalized = decode_canonical_source_bytes(
            content, expected_source_checksum_sha256=raw_sha
        ).source
        nodes = [
            {"x": float(col * 7 + 1), "y": float(row * 8 + 1)}
            for row in range(4)
            for col in range(6)
        ]
        nodes[8]["x"] += 0.375  # Inner deformation must survive without a fitted quadrilateral.
        source = {
            "sourceId": str(uuid4()),
            "role": role,
            "used": used,
            "reasons": [],
            "sourceIdentity": {
                "checksum_sha256": raw_sha,
                "normalized_pixel_checksum_sha256": normalized.normalized_pixel_checksum_sha256,
                "normalization_adapter_version": CANONICAL_SOURCE_LOADER_VERSION,
                "oriented_width": normalized.width,
                "oriented_height": normalized.height,
                "exif_orientation": normalized.exif_orientation,
            },
            "original": self.pin(f"{self.directory}/originals/{len(self.sources)}.jpg", content)
            if used
            else None,
            "targets": [
                {
                    "positionIndex": position,
                    "sequenceNumber": position + 17,
                    "nodes": copy.deepcopy(nodes),
                    "approval": {
                        "origin": origin,
                        "weight": 4 if origin == "human_corrected" else 1,
                    },
                    "render": {"configuration": {"renderer": "source-lattice-test-v1"}},
                }
                for position in range(9 if full else 1)
            ],
            "screenEligible": full,
        }
        self.sources.append(source)
        return source

    def publish(self, *, mode="grid-only", change=None):
        pages, counts = (
            [],
            {
                role: {"boards": 0, "photos": 0, "fullPhotos": 0}
                for role in ("TRAIN", "VALIDATION", "REGRESSION")
            },
        )
        for after in range(0, len(self.sources), self.page_size):
            rows = self.sources[after : after + self.page_size]
            used = [source for source in rows if source["used"]]
            for source in used:
                if source["role"] in counts:
                    count = counts[source["role"]]
                    count["boards"] += len(source["targets"])
                    count["photos"] += 1
                    count["fullPhotos"] += int(source["screenEligible"])
            page = self.pin(
                f"{self.directory}/pages/{after}.json",
                canonical(
                    {"firstOrdinal": after, "lastOrdinal": after + len(rows) - 1, "sources": rows}
                ),
            )
            pages.append(
                {
                    **page,
                    "boardCount": sum(len(source["targets"]) for source in used),
                    "screenCount": sum(source["screenEligible"] for source in used),
                }
            )
        index = self.pin(
            f"{self.directory}/index.jsonl", b"".join(canonical(page) + b"\n" for page in pages)
        )
        root = {
            "schemaVersion": "application-grid-snapshot-v1",
            "policyVersion": "application-grid-cohort-v1",
            "weightPolicy": "correction-weight-4-to-1-v1",
            "gameId": self.game,
            "cohortId": self.cohort,
            "familyId": str(uuid4()),
            "mode": mode,
            "base": {
                "versionId": self.base["versionId"],
                "familyId": self.base["familyId"],
                "manifestSha256": descriptor_sha256(self.base),
                "manifest": self.base,
            },
            "decoder": {
                "adapterVersion": CANONICAL_SOURCE_LOADER_VERSION,
                "pixelAlgorithm": RGB_PIXEL_CHECKSUM_VERSION,
                "pillowVersion": Image.__version__,
            },
            "preprocessing": {
                key: self.base[key]
                for key in ("preprocessingVersion", "decodingPolicyVersion", "inferenceManifest")
            },
            "pageIndex": index,
            "pageCount": len(pages),
            "counts": counts,
        }
        if change:
            change(root)
        pin = self.pin(f"{self.directory}/manifest.json", canonical(root))
        self.manifest_pin, self.pages = pin, pages
        return GridCohortSnapshot(self.root, pin["path"], pin["sha256"])


def test_grid_only_partial_photo_preserves_deformed_nodes_and_weights(tmp_path):
    fixture = SnapshotFixture(tmp_path)
    corrected = fixture.source()
    fixture.source(origin="human_checked_unchanged")
    snapshot = fixture.publish()
    dataset = GridBoardDataset(snapshot)
    assert len(dataset) == 2 and len(GridScreenDataset(snapshot)) == 0
    item = dataset[0]
    assert item["sourceRgb"].dtype == np.uint8 and item["sourceRgb"].shape == (48, 64, 3)
    np.testing.assert_array_equal(
        item["nodes"], [[p["x"], p["y"]] for p in corrected["targets"][0]["nodes"]]
    )
    assert item["nodes"][8, 0] == 15.375
    assert item["sampleWeight"] == 4 and dataset[1]["sampleWeight"] == 1
    assert item["positionIndex"] == 0 and item["sequenceNumber"] == 17
    assert not item["sourceRgb"].flags.writeable


def test_roles_and_excluded_members_are_checked_before_pixel_access(tmp_path, monkeypatch):
    fixture = SnapshotFixture(tmp_path)
    fixture.source()
    control = fixture.source("VALIDATION", full=True)
    excluded = fixture.source(None, used=False)
    excluded["targets"] = []
    excluded["reasons"] = ["RECORDING_MEMBERSHIP_REQUIRED"]
    snapshot = fixture.publish()
    (tmp_path / control["original"]["path"]).unlink()
    assert len(GridBoardDataset(snapshot)) == 1
    assert GridBoardDataset(snapshot)[0]["role"] == "TRAIN"
    with pytest.raises(IndexError):
        GridBoardDataset(snapshot)[1]
    assert len(GridBoardDataset(snapshot, "VALIDATION")) == 9
    with pytest.raises(GridCohortDatasetError, match="unavailable"):
        GridBoardDataset(snapshot, "VALIDATION")[0]
    monkeypatch.setattr(
        snapshot, "_read", lambda *_: pytest.fail("Role guard must run before file access")
    )
    with pytest.raises(GridCohortDatasetError) as error:
        snapshot.frame(control, "TRAIN")
    assert error.value.code == "ROLE_MISMATCH"
    with pytest.raises(GridCohortDatasetError):
        snapshot.frame(excluded, "TRAIN")


def test_screen_dataset_requires_all_nine_targets_and_keeps_physical_order(tmp_path):
    fixture = SnapshotFixture(tmp_path)
    source = fixture.source(full=True)
    source["targets"].reverse()
    dataset = GridScreenDataset(fixture.publish(mode="screen+grid"))
    assert len(dataset) == 1
    item = dataset[0]
    assert item["nodes"].shape == (9, 24, 2)
    assert [target["positionIndex"] for target in item["targets"]] == list(range(9))
    source["targets"].pop()
    with pytest.raises(GridCohortDatasetError) as error:
        len(GridScreenDataset(fixture.publish(mode="screen+grid")))
    assert error.value.code == "FULL_PHOTO_REQUIRED"


@pytest.mark.parametrize(
    "change,code",
    [
        (lambda root: root.update(policyVersion="unknown"), "POLICY_UNSUPPORTED"),
        (lambda root: root["base"].update(manifestSha256="0" * 64), "BASE_MANIFEST_MISMATCH"),
        (lambda root: root["base"].update(versionId=str(uuid4())), "BASE_MANIFEST_MISMATCH"),
        (lambda root: root["base"].update(familyId=str(uuid4())), "BASE_MANIFEST_MISMATCH"),
        (
            lambda root: root["preprocessing"].update(preprocessingVersion="unknown"),
            "PREPROCESSING_MISMATCH",
        ),
        (lambda root: root["decoder"].update(pillowVersion="unknown"), "DECODER_UNSUPPORTED"),
    ],
)
def test_base_policy_and_preprocessing_pins_are_checked_before_pixels(tmp_path, change, code):
    fixture = SnapshotFixture(tmp_path)
    fixture.source()
    with pytest.raises(GridCohortDatasetError) as error:
        fixture.publish(change=change)
    assert error.value.code == code


def test_catalogue_checksum_preserves_existing_ascii_algorithm(tmp_path):
    fixture = SnapshotFixture(tmp_path)
    fixture.base["familyLabel"] = "Rodzina żółta"
    fixture.source()
    snapshot = fixture.publish()
    assert snapshot.manifest["base"]["manifestSha256"] == descriptor_sha256(fixture.base)
    assert (
        snapshot.manifest["base"]["manifestSha256"]
        != hashlib.sha256(canonical(fixture.base)).hexdigest()
    )


def test_corrupt_root_index_page_and_source_remain_distinct_failures(tmp_path):
    fixture = SnapshotFixture(tmp_path)
    source = fixture.source()
    snapshot = fixture.publish()
    root_path = tmp_path / fixture.manifest_pin["path"]
    original_root = root_path.read_bytes()
    root_path.write_bytes(original_root + b" ")
    with pytest.raises(GridCohortDatasetError) as error:
        GridCohortSnapshot(tmp_path, fixture.manifest_pin["path"], fixture.manifest_pin["sha256"])
    assert error.value.code == "CHECKSUM_MISMATCH"
    root_path.write_bytes(original_root)
    page = tmp_path / fixture.pages[0]["path"]
    page.write_bytes(page.read_bytes() + b" ")
    with pytest.raises(GridCohortDatasetError):
        len(GridBoardDataset(snapshot))
    snapshot = fixture.publish()
    pixel_path = tmp_path / source["original"]["path"]
    content = pixel_path.read_bytes()
    dataset = GridBoardDataset(snapshot)
    dataset[0]  # A cached decode must not hide later raw-byte drift.
    pixel_path.write_bytes(content[:-1] + bytes([content[-1] ^ 1]))
    with pytest.raises(GridCohortDatasetError) as error:
        dataset[0]
    assert error.value.code == "CHECKSUM_MISMATCH"
    pixel_path.write_bytes(content)
    index = tmp_path / snapshot.manifest["pageIndex"]["path"]
    index.write_bytes(index.read_bytes() + b" ")
    with pytest.raises(GridCohortDatasetError):
        len(dataset)


def test_pixel_identity_mismatch_and_missing_snapshot_never_become_new_labels(tmp_path):
    fixture = SnapshotFixture(tmp_path)
    source = fixture.source()
    source["sourceIdentity"]["normalized_pixel_checksum_sha256"] = "0" * 64
    dataset = GridBoardDataset(fixture.publish())
    with pytest.raises(GridCohortDatasetError) as error:
        dataset[0]
    assert error.value.code == "SOURCE_IDENTITY_MISMATCH"
    (tmp_path / source["original"]["path"]).unlink()
    with pytest.raises(GridCohortDatasetError) as error:
        dataset[0]
    assert error.value.code == "DATASET_ASSET_UNAVAILABLE"


def test_file_backed_reader_retains_one_page_and_frame_and_no_corpus_index(tmp_path, monkeypatch):
    fixture = SnapshotFixture(tmp_path)
    for _ in range(3):
        fixture.source()
    fixture.page_size = 1
    snapshot = fixture.publish()
    calls = []
    decode = grid_dataset.decode_canonical_source_bytes
    monkeypatch.setattr(
        grid_dataset,
        "decode_canonical_source_bytes",
        lambda *a, **kw: (calls.append(True), decode(*a, **kw))[1],
    )
    dataset = GridBoardDataset(snapshot)
    assert len(dataset) == 3
    dataset[0]
    dataset[0]
    assert len(calls) == 1
    dataset[2]
    assert len(calls) == 2
    assert snapshot._page_cache["firstOrdinal"] == 2
    assert snapshot._frame_key[0] == fixture.sources[2]["original"]["path"]
    assert not any(isinstance(value, list) for value in vars(snapshot).values())
    restarted = GridBoardDataset(
        GridCohortSnapshot(tmp_path, fixture.manifest_pin["path"], fixture.manifest_pin["sha256"])
    )
    np.testing.assert_array_equal(restarted[0]["nodes"], dataset[0]["nodes"])


def test_non_human_weight_and_unsafe_path_are_rejected_without_pixels(tmp_path):
    fixture = SnapshotFixture(tmp_path)
    source = fixture.source()
    source["targets"][0]["approval"]["origin"] = "automatic"
    with pytest.raises(GridCohortDatasetError) as error:
        GridBoardDataset(fixture.publish())[0]
    assert error.value.code == "TARGET_PROOF_INVALID"
    source["targets"][0]["approval"]["origin"] = "human_corrected"
    source["original"]["path"] = "../outside.jpg"
    with pytest.raises(GridCohortDatasetError) as error:
        GridBoardDataset(fixture.publish())[0]
    assert error.value.code in {"COHORT_PATH_MISMATCH", "PATH_UNSAFE"}


def test_long_artifact_root_reads_in_a_fresh_process_without_services(tmp_path):
    owned_base = tmp_path / ("long-root-" + "a" * 70)
    root = owned_base / ("snapshot-" + "b" * 70) / ("depth-" + "c" * 70)
    target = long_path_aware(root)
    assert not long_path_aware(owned_base).exists() and root.absolute().is_relative_to(
        tmp_path.absolute()
    )
    target.mkdir(parents=True)
    owner = str(uuid4())
    (target / "fixture-owner").write_text(owner, encoding="utf-8")
    identity = target.stat().st_dev, target.stat().st_ino
    base_identity = (
        long_path_aware(owned_base).stat().st_dev,
        long_path_aware(owned_base).stat().st_ino,
    )
    try:
        fixture = SnapshotFixture(root)
        fixture.source()
        snapshot = fixture.publish()
        assert len(str(root / fixture.manifest_pin["path"])) > 260
        assert GridBoardDataset(snapshot)[0]["nodes"].shape == (24, 2)
        script = """import sys
from pathlib import Path
from game_predictor_worker.images.grid_cohort_dataset import GridCohortSnapshot, GridBoardDataset
assert 'torch' not in sys.modules and 'sqlalchemy' not in sys.modules
assert not any(name.startswith('game_predictor_worker.vision_lab') for name in sys.modules)
snapshot = GridCohortSnapshot(Path(sys.argv[1]), sys.argv[2], sys.argv[3])
dataset = GridBoardDataset(snapshot)
assert len(dataset) == 1 and dataset[0]['nodes'].shape == (24, 2)
print('CPU_GRID_SNAPSHOT_OK:24')
"""
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                script,
                str(root),
                fixture.manifest_pin["path"],
                fixture.manifest_pin["sha256"],
            ],
            timeout=10,
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.strip() == "CPU_GRID_SNAPSHOT_OK:24"
    finally:
        assert root.absolute().is_relative_to(tmp_path.absolute())
        assert identity == (target.stat().st_dev, target.stat().st_ino)
        assert (target / "fixture-owner").read_text(encoding="utf-8") == owner
        cleanup = long_path_aware(owned_base)
        assert owned_base.absolute().is_relative_to(tmp_path.absolute())
        assert base_identity == (cleanup.stat().st_dev, cleanup.stat().st_ino)
        assert all(
            not p.is_symlink() and not p.is_junction() for p in (cleanup, *cleanup.rglob("*"))
        )
        shutil.rmtree(cleanup)
