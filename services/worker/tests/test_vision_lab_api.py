"""Standalone gallery, snapshot integrity and HTTP boundary regressions."""

import ast
import hashlib
import io
import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from game_predictor_worker.vision_lab import catalog as catalog_module
from game_predictor_worker.vision_lab import snapshot as snapshot_module
from game_predictor_worker.vision_lab.api import create_app
from game_predictor_worker.vision_lab.catalog import Catalog, encode
from game_predictor_worker.vision_lab.contracts import Board, GeometryResult, Point, Topology
from game_predictor_worker.vision_lab.geometry import BaselineEngine, cell_quads, crop_cell
from game_predictor_worker.vision_lab.snapshot import canonical, import_folder, safe_file
from PIL import Image


def make_snapshot(tmp_path: Path) -> Path:
    source = tmp_path / "input"
    (source / "777").mkdir(parents=True)
    Image.new("RGB", (121, 81), "red").save(source / "777" / "one__1.jpg")
    (source / "777" / "two__1.jpg").write_bytes((source / "777" / "one__1.jpg").read_bytes())
    (source / "777" / "broken.jpg").write_bytes(b"not an image")
    return import_folder(source, tmp_path / "snapshots")


def board(topology: Topology) -> Board:
    return Board(
        position_index=0,
        status="needs_review",
        nodes=[
            Point(x=column * 20, y=row * 20)
            for row in range(topology.rows + 1)
            for column in range(topology.columns + 1)
        ],
    )


class FakeEngine:
    def detect(self, source_id, rgb, topology):
        return GeometryResult(
            source_id=source_id,
            topology=topology,
            model_version="test",
            status="detected",
            boards=[board(topology)],
            width=rgb.shape[1],
            height=rgb.shape[0],
        )


@pytest.mark.parametrize("columns", [3, 5])
def test_manual_preview_uses_current_nodes_and_cropper_without_persisting(
    tmp_path: Path, columns: int
) -> None:
    input_root = tmp_path / "textured"
    (input_root / "game").mkdir(parents=True)
    pixels = np.zeros((81, 121, 3), dtype=np.uint8)
    pixels[:, :, 0] = np.arange(121, dtype=np.uint8)[None, :] * 2
    pixels[:, :, 1] = np.arange(81, dtype=np.uint8)[:, None] * 3
    Image.fromarray(pixels).save(input_root / "game" / "grid.jpg")
    registry = Catalog(import_folder(input_root, tmp_path / "snapshots"), FakeEngine())
    source = next(iter(registry.sources.values()))
    topology = Topology(columns=columns)
    edited = board(topology)
    for point in edited.nodes:
        point.x += 7
        point.y += 8
    root = tmp_path / "annotations"
    client = TestClient(create_app(registry, root), base_url="http://127.0.0.1:8102")
    body = {
        "source_id": source.id,
        "topology": topology.model_dump(),
        "preview_board": edited.model_dump(),
    }
    response = client.post("/geometry", json=body, headers={"Origin": "http://127.0.0.1:3102"})
    assert response.status_code == 200
    result = response.json()
    assert result["model_version"] == "manual-preview"
    assert result["boards"][0]["nodes"] == edited.model_dump()["nodes"]
    rgb = np.asarray(registry.image(source), dtype=np.uint8)
    for cell, quad in zip(result["boards"][0]["cells"], cell_quads(edited, topology), strict=True):
        crop = crop_cell(rgb, quad)
        assert crop is not None
        assert registry.asset(cell["asset_id"]) == encode(Image.fromarray(crop))
    assert not root.exists()
    edited.nodes[0], edited.nodes[1] = edited.nodes[1], edited.nodes[0]
    bad = registry.detect(source.id, topology, edited)
    assert bad.status == "failed" and not bad.boards
    edited.nodes = []
    assert registry.detect(source.id, topology, edited).status == "failed"
    edited.status = "absent"
    assert not registry.detect(source.id, topology, edited).boards[0].cells
    baseline = registry.detect(source.id, topology)
    assert baseline.model_version == "test"
    assert baseline.boards[0].cells[0].asset_id != result["boards"][0]["cells"][0]["asset_id"]


def test_snapshot_restart_duplicates_and_tamper(tmp_path: Path) -> None:
    snapshot = make_snapshot(tmp_path)
    assert import_folder(tmp_path / "input", tmp_path / "snapshots") == snapshot
    first, second = Catalog(snapshot), Catalog(snapshot)
    assert first.sources == second.sources
    assert len(first.sources) == 3
    assert sorted(s.duplicate_count for s in first.sources.values()) == [1, 2, 2]
    assert all(
        s.role == "comparison_only" and not s.training_eligible for s in first.sources.values()
    )
    manifest = json.loads((snapshot / "manifest.json").read_bytes())
    manifest["entries"][0]["role"] = "data"
    (snapshot / "manifest.json").write_bytes(canonical(manifest))
    with pytest.raises(ValueError, match="IDENTITY"):
        Catalog(snapshot)


@pytest.mark.parametrize("columns,count,cells", [(5, 24, 15), (3, 16, 9)])
def test_topology_crop_and_order(columns: int, count: int, cells: int) -> None:
    topology = Topology(columns=columns)
    grid = board(topology)
    assert len(grid.nodes) == count
    quads = cell_quads(grid, topology)
    assert len(quads) == cells
    rgb = np.zeros((81, 121, 3), dtype=np.uint8)
    rgb[:, :, 0] = 200
    crop = crop_cell(rgb, quads[0])
    assert crop is not None and crop.shape == (96, 96, 3) and crop[40, 40, 0] == 200
    grid.nodes[0], grid.nodes[1] = grid.nodes[1], grid.nodes[0]
    with pytest.raises(ValueError, match="GRID_"):
        cell_quads(grid, topology)


def test_api_boundaries_and_broken_neighbor(tmp_path: Path) -> None:
    registry = Catalog(make_snapshot(tmp_path), FakeEngine())
    client = TestClient(create_app(registry), base_url="http://127.0.0.1:8102")
    headers = {"Origin": "http://127.0.0.1:3102"}
    response = client.get("/sources?limit=100")
    assert response.status_code == 200 and response.json()["total"] == 3
    for source in registry.sources.values():
        result = client.post("/geometry", json={"source_id": source.id}, headers=headers)
        assert result.status_code == 200
        expected = "invalid_image" if source.filename.endswith("broken.jpg") else "detected"
        assert result.json()["status"] == expected
        if expected == "detected":
            crop = result.json()["boards"][0]["cells"][0]["asset_id"]
            assert client.get(f"/assets/{crop}").status_code == 200
    assert client.get("/sources", headers={"Host": "evil.test"}).status_code == 403
    assert client.get("/sources", headers={"Origin": "http://evil.test"}).status_code == 403
    assert client.post("/geometry", json={}).status_code == 403
    assert client.post("/geometry", content="{}", headers=headers).status_code == 415
    assert client.post("/geometry", json={"path": "C:/private"}, headers=headers).status_code == 422
    assert client.get("/assets/secret").status_code == 404
    assert client.get("/assets/" + "a" * 64).status_code == 404
    assert client.get("/admin").status_code == 404


def test_baseline_rejects_3_by_3() -> None:
    result = BaselineEngine().detect(
        "test", np.zeros((60, 60, 3), dtype=np.uint8), Topology(columns=3)
    )
    assert result.status == "unsupported" and result.boards == []


def test_asset_canonical_exif_and_corruption(tmp_path: Path) -> None:
    folder = tmp_path / "input"
    folder.mkdir()
    exif = Image.Exif()
    exif[274] = 6
    Image.new("RGB", (30, 20), "red").save(folder / "test.jpg", exif=exif)
    registry = Catalog(import_folder(folder, tmp_path / "snapshots"))
    source = next(iter(registry.sources.values()))
    assert registry.image(source).size == (20, 30)
    registry.paths[source.asset_id].write_bytes(b"changed")
    with pytest.raises(ValueError, match="CHECKSUM"):
        registry.detect(source.id, Topology())


def test_path_and_inventory_rejected(tmp_path: Path) -> None:
    snapshot = make_snapshot(tmp_path)
    for relative in ["../secret", "C:/secret", "images\\secret"]:
        with pytest.raises(ValueError):
            safe_file(snapshot, relative)
    (snapshot / "unknown.txt").write_text("x")
    with pytest.raises(ValueError, match="INVENTORY"):
        Catalog(snapshot)


def test_db_snapshot_common_catalog(tmp_path: Path) -> None:
    root = tmp_path / "db"
    root.mkdir()
    data = b"not decoded until requested"
    digest = hashlib.sha256(data).hexdigest()
    relative = f"images/{digest[:2]}/{digest}.jpg"
    (root / relative).parent.mkdir(parents=True)
    (root / relative).write_bytes(data)
    manifest = {
        "schemaVersion": 1,
        "exporterVersion": "test",
        "input": {
            "entries": [
                {
                    "sourceImageId": "db-source",
                    "gameId": "db-game",
                    "expectedSourceSha256": digest,
                    "sourceFamilyId": "db-family",
                    "role": "data",
                }
            ]
        },
        "files": {relative: digest},
    }
    manifest["snapshotId"] = hashlib.sha256(
        canonical({"input": manifest["input"], "exporterVersion": "test", "rows": []})
    ).hexdigest()
    frozen = canonical({"snapshotId": manifest["snapshotId"], "rows": []})
    (root / "frozen_identity.json").write_bytes(frozen)
    manifest["files"]["frozen_identity.json"] = hashlib.sha256(frozen).hexdigest()
    (root / "manifest.json").write_bytes(canonical(manifest))
    registry = Catalog(root)
    assert registry.sources["db-source"].source_kind == "database"
    assert not registry.sources["db-source"].training_eligible


def test_interrupted_copy_never_publishes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "input"
    source.mkdir()
    (source / "one.jpg").write_bytes(b"source bytes")
    output = tmp_path / "snapshots"
    real_copy = snapshot_module.shutil.copyfileobj

    def interrupted(*args, **kwargs):
        raise OSError("interrupted")

    monkeypatch.setattr(snapshot_module.shutil, "copyfileobj", interrupted)
    with pytest.raises(OSError, match="interrupted"):
        import_folder(source, output)
    assert list(output.iterdir()) == []
    monkeypatch.setattr(snapshot_module.shutil, "copyfileobj", real_copy)
    assert (import_folder(source, output) / "manifest.json").exists()


def test_missing_source_is_infrastructure_failure(tmp_path: Path) -> None:
    registry = Catalog(make_snapshot(tmp_path), FakeEngine())
    source = next(s for s in registry.sources.values() if not s.filename.endswith("broken.jpg"))
    registry.paths[source.asset_id].unlink()
    with pytest.raises(FileNotFoundError):
        registry.detect(source.id, Topology())


def test_duplicate_changed_during_copy_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "input"
    source.mkdir()
    for name in ("one.jpg", "two.jpg"):
        (source / name).write_bytes(b"same bytes")
    real_copy = snapshot_module.shutil.copyfileobj

    def changing(*args, **kwargs):
        real_copy(*args, **kwargs)
        (source / "two.jpg").write_bytes(b"changed duplicate")

    monkeypatch.setattr(snapshot_module.shutil, "copyfileobj", changing)
    with pytest.raises(ValueError, match="SOURCE_CHANGED"):
        import_folder(source, tmp_path / "snapshots")
    assert list((tmp_path / "snapshots").iterdir()) == []


def test_lab_has_no_production_storage_imports() -> None:
    root = Path(snapshot_module.__file__).parent
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            assert all(
                not any(part in name.split(".") for part in ("storage", "psycopg", "training_job"))
                for name in modules
            )


@pytest.mark.parametrize("status", ["absent", "occluded", "unreadable"])
def test_no_geometry_observation_preserved(tmp_path: Path, status: str) -> None:
    class ObservationEngine:
        def detect(self, source_id, rgb, topology):
            return GeometryResult(
                source_id=source_id,
                topology=topology,
                model_version="test",
                status="detected",
                boards=[
                    Board(position_index=0, status=status, nodes=[], reasons=["OBSERVATION_ONLY"])
                ],
            )

    registry = Catalog(make_snapshot(tmp_path), ObservationEngine())
    source = next(s for s in registry.sources.values() if not s.filename.endswith("broken.jpg"))
    result = registry.detect(source.id, Topology())
    assert result.boards[0].status == status
    assert result.boards[0].reasons == ["OBSERVATION_ONLY"]
    assert result.boards[0].cells == []
    assert registry.assets == {}
    with pytest.raises(ValueError, match="GRID_NODE_COUNT"):
        GeometryResult(
            source_id="test",
            topology=Topology(),
            model_version="test",
            status="detected",
            boards=[Board(position_index=0, status="complete", nodes=[])],
        )


@pytest.mark.parametrize("operation", ["image", "asset", "detect"])
def test_image_decodes_exact_verified_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    registry = Catalog(make_snapshot(tmp_path), FakeEngine())
    source = next(s for s in registry.sources.values() if not s.filename.endswith("broken.jpg"))
    path = registry.paths[source.asset_id]
    verified_bytes = path.read_bytes()
    replacement = io.BytesIO()
    Image.new("RGB", (121, 81), "blue").save(replacement, "JPEG")
    real_open = Path.open
    reads = 0

    def replace_after_read(candidate, *args, **kwargs):
        nonlocal reads
        if candidate == path and args and args[0] == "rb":
            reads += 1
            with real_open(path, "wb") as stream:
                stream.write(replacement.getvalue())
            return io.BytesIO(verified_bytes)
        return real_open(candidate, *args, **kwargs)

    monkeypatch.setattr(Path, "open", replace_after_read)
    if operation == "image":
        image = registry.image(source)
    elif operation == "asset":
        image = Image.open(io.BytesIO(registry.asset(source.asset_id)))
    else:
        result = registry.detect(source.id, Topology())
        image = Image.open(io.BytesIO(registry.assets[result.boards[0].cells[0].asset_id]))
    assert image.getpixel((20, 20))[0] > 200
    assert reads == 1


def test_reparse_rechecked_after_catalog_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = Catalog(make_snapshot(tmp_path))
    source = next(iter(registry.sources.values()))

    def reject_replaced(path):
        raise ValueError("SNAPSHOT_REPARSE_POINT")

    monkeypatch.setattr(catalog_module, "reject_links", reject_replaced)
    with pytest.raises(ValueError, match="REPARSE"):
        registry.asset(source.asset_id)
