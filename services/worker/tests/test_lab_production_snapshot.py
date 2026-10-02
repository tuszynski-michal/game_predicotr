from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path

import pytest
from game_predictor_worker.vision_lab import production_snapshot as snapshot
from game_predictor_worker.vision_lab import production_split as split
from lab_production_fixtures import HEIGHT, WIDTH, Dataset, jpeg_bytes, standard_dataset
from PIL import Image, ImageOps

CONFIG = split.SplitConfig(seed=7, training_per_level=8, development_per_level=2)


def build(data: Dataset, output: Path, **kwargs: object) -> snapshot.BuildResult:
    return snapshot.build_snapshot(
        data.write(), data.artifacts, output, CONFIG, preview=False, log=lambda _m: None, **kwargs
    )


def test_production_snapshot_publishes_and_verifies(tmp_path: Path) -> None:
    data = standard_dataset(tmp_path)
    result = build(data, tmp_path / "out")
    assert result.status == "published" and not result.blockers
    root = tmp_path / "out" / str(result.snapshot_id)
    manifest = snapshot.verify_snapshot(root)
    assert manifest["format"] == snapshot.FORMAT
    assert manifest["policy"]["filter"]["maxLowQualityConfidence"] == 0.8
    assert [p.name for p in (tmp_path / "out").iterdir()] == [result.snapshot_id]
    samples = [json.loads(line) for line in (root / "samples.jsonl").read_bytes().splitlines()]
    roles = {s["imageId"]: s["role"] for s in samples}
    assert roles["gold-full"] == "gold"
    sample = next(s for s in samples if s["role"] == "training")
    assert len(sample["boards"]) == 3 and len(sample["boards"][0]["nodes"]) == 24
    assert sample["boards"][0]["trainingTarget"] is True
    assert sample["boards"][0]["contrast"]["rmsContrast"] > 0
    assert sample["exifOrientation"] == 1
    image_bytes = (root / sample["imagePath"]).read_bytes()
    assert hashlib.sha256(image_bytes).hexdigest() == sample["sourceChecksumSha256"]
    gold = next(s for s in samples if s["imageId"] == "gold-mixed")
    assert [b["evaluationTarget"] for b in gold["boards"]] == [True, False, False]
    assert isinstance(gold["familySeenInTraining"], bool)
    split_document = json.loads((root / "split.json").read_bytes())
    assert split_document["samplesSha256"] == manifest["files"]["samples.jsonl"]
    report = json.loads((root / "report.json").read_bytes())
    assert report["roles"]["training"]["images"] == 16
    assert "checks/visual-training.jpg" in manifest["files"]


def test_production_snapshot_same_seed_identical_manifest(tmp_path: Path) -> None:
    data = standard_dataset(tmp_path)
    first = build(data, tmp_path / "one")
    second = build(data, tmp_path / "two")
    assert first.snapshot_id == second.snapshot_id
    one = (tmp_path / "one" / str(first.snapshot_id) / "manifest.json").read_bytes()
    two = (tmp_path / "two" / str(second.snapshot_id) / "manifest.json").read_bytes()
    assert one == two


def test_production_snapshot_rerun_leaves_published_snapshot_untouched(tmp_path: Path) -> None:
    data = standard_dataset(tmp_path)
    first = build(data, tmp_path / "out")
    root = tmp_path / "out" / str(first.snapshot_id)
    before = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in root.rglob("*") if p.is_file()}
    again = build(data, tmp_path / "out")
    assert again.status == "already_published_verified"
    after = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in root.rglob("*") if p.is_file()}
    assert before == after
    (root / "report.json").write_bytes(b"{}\n")
    with pytest.raises(ValueError, match="SNAPSHOT_CHECKSUM_MISMATCH"):
        build(data, tmp_path / "out")


def test_production_snapshot_integrity_exclusions_with_reason(tmp_path: Path) -> None:
    data = standard_dataset(tmp_path, per_level=5)
    data.photo("selection:fam0", ["G", "G", "G"], image_id="gold-missing", write=False)
    wrong = data.photo("selection:fam1", ["G", "G", "G"], image_id="gold-wrong-sha")
    row = next(r for r in data.rows if r["sourceImageId"] == wrong)
    path = data.artifacts / "data" / row["sourceRelativePath"]
    path.write_bytes(jpeg_bytes(4242))
    result = build(data, tmp_path / "out")
    assert result.status == "published"
    root = tmp_path / "out" / str(result.snapshot_id)
    exclusions = [
        json.loads(line) for line in (root / "exclusions.jsonl").read_bytes().splitlines()
    ]
    assert {e["imageId"]: e["reason"] for e in exclusions} == {
        "gold-missing": snapshot.INTEGRITY_FILE_MISSING,
        "gold-wrong-sha": snapshot.INTEGRITY_CHECKSUM_MISMATCH,
    }
    samples = (root / "samples.jsonl").read_text(encoding="utf-8")
    assert "gold-missing" not in samples and "gold-wrong-sha" not in samples


def test_production_snapshot_publication_is_atomic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = standard_dataset(tmp_path)

    def broken(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(snapshot, "_write_stage", broken)
    with pytest.raises(OSError, match="disk full"):
        build(data, tmp_path / "out")
    assert list((tmp_path / "out").iterdir()) == []


def test_production_snapshot_preview_copies_nothing(tmp_path: Path) -> None:
    data = standard_dataset(tmp_path)
    result = snapshot.build_snapshot(
        data.write(), data.artifacts, tmp_path / "out", CONFIG, preview=True, log=lambda _m: None
    )
    assert result.status == "preview" and result.selected_bytes > 0
    assert not (tmp_path / "out").exists()


def test_production_snapshot_blocks_when_targets_or_size_fail(tmp_path: Path) -> None:
    data = standard_dataset(tmp_path)
    result = build(data, tmp_path / "out", max_copy_bytes=10)
    assert result.status == "blocked"
    assert any(b.startswith("COPY_SIZE_ABOVE_LIMIT") for b in result.blockers)
    assert not (tmp_path / "out").exists()


def test_production_snapshot_exif_orientation_kept_and_nodes_in_oriented_space(
    tmp_path: Path,
) -> None:
    data = Dataset(tmp_path)
    # Orientation 6 rotates the stored 90 x 120 photo to an oriented 120 x 90 one.
    rotated = jpeg_bytes(1, size=(HEIGHT, WIDTH), orientation=6)
    data.photo("selection:a", ["G", "G", "G"], image_id="rotated", data=rotated)
    unrotated_size = jpeg_bytes(2, size=(HEIGHT, WIDTH))
    data.photo("selection:a", ["G", "G", "G"], image_id="raw-size-mismatch", data=unrotated_size)
    for family in ("selection:a", "selection:b", "selection:c", "selection:d", "selection:e"):
        for _ in range(3):
            data.photo(family, ["S", "S", "S"])
            data.photo(family, ["B", "B", "B"])
    config = split.SplitConfig(seed=1, training_per_level=4, development_per_level=1)
    result = snapshot.build_snapshot(
        data.write(), data.artifacts, tmp_path / "out", config, preview=False, log=lambda _m: None
    )
    root = tmp_path / "out" / str(result.snapshot_id)
    samples = {
        s["imageId"]: s
        for s in (json.loads(line) for line in (root / "samples.jsonl").read_bytes().splitlines())
    }
    assert samples["rotated"]["exifOrientation"] == 6
    stored = root / samples["rotated"]["imagePath"]
    assert stored.read_bytes() == rotated  # copied without re-encoding
    with Image.open(stored) as image:
        assert image.size == (HEIGHT, WIDTH)
        assert ImageOps.exif_transpose(image).size == (WIDTH, HEIGHT)
    assert "raw-size-mismatch" not in samples
    report = json.loads((root / "report.json").read_bytes())
    assert report["integrityExclusionsByReason"] == {snapshot.INTEGRITY_SIZE_MISMATCH: 1}
    assert "checks/visual-exif.jpg" in json.loads((root / "manifest.json").read_bytes())["files"]


def test_production_snapshot_contrast_definition() -> None:
    import numpy as np

    flat = np.full((20, 20), 128.0)
    assert snapshot.polygon_rms_contrast(flat, [(2, 2), (10, 2), (10, 10), (2, 10)]) == 0.0
    stripes = np.zeros((20, 20))
    stripes[:, ::2] = 255.0
    value = snapshot.polygon_rms_contrast(stripes, [(0, 0), (19, 0), (19, 19), (0, 19)])
    assert value is not None and abs(value - 0.5) < 0.01
    assert snapshot.polygon_rms_contrast(flat, [(30, 30), (40, 30), (40, 40), (30, 40)]) is None


@pytest.mark.skipif(
    not os.environ.get("VISION_LAB_PRODUCTION_SNAPSHOT"),
    reason="set VISION_LAB_PRODUCTION_SNAPSHOT to a published snapshot to check real files",
)
def test_production_snapshot_real_files_grid_hits_oriented_photo() -> None:
    root = Path(os.environ["VISION_LAB_PRODUCTION_SNAPSHOT"])
    with (root / "samples.jsonl").open("rb") as stream:
        records = [json.loads(next(stream)) for _ in range(25)]
    for record in records:
        data = (root / record["imagePath"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == record["sourceChecksumSha256"]
        with Image.open(io.BytesIO(data)) as image:
            assert snapshot.exif_orientation(image) == record["exifOrientation"]
            oriented = ImageOps.exif_transpose(image)
            assert oriented.size == (record["orientedWidth"], record["orientedHeight"])
        for board in record["boards"]:
            assert all(
                -1 <= x <= record["orientedWidth"] and -1 <= y <= record["orientedHeight"]
                for x, y in board["nodes"]
            )
