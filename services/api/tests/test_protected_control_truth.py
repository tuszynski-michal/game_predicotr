from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import numpy as np
import pytest
from game_predictor_api.domain.jobs import JobConflictError
from game_predictor_api.domain.lab_symbol_candidate import MUMIE_CLASS_CODES, MUMIE_CLASS_LABELS
from game_predictor_api.domain.protected_control_truth import (
    TRUTH_VERSION,
    ControlTruth,
    CurrentControlDecision,
    compare_control_truth,
)
from game_predictor_api.storage import protected_control_truth as storage
from game_predictor_worker.images.normalization import rgb_pixel_checksum_sha256
from PIL import Image


def truth() -> ControlTruth:
    return ControlTruth(
        "a" * 64,
        "b" * 64,
        "c" * 64,
        100,
        100,
        0,
        2,
        ((0.0, 0.0), (96.0, 0.0), (96.0, 96.0), (0.0, 96.0)),
        "d" * 64,
        str(uuid4()),
        "10",
        "lab_human_approved",
        "e" * 64,
        "f" * 64,
    )


def current(t: ControlTruth) -> CurrentControlDecision:
    return CurrentControlDecision(
        str(uuid4()),
        t.source_pixel_sha256,
        t.source_width,
        t.source_height,
        t.position_index,
        t.cell_index,
        t.source_quad,
        t.crop_pixel_sha256,
        str(uuid4()),
        t.symbol_code,
        7,
        str(uuid4()),
    )


def test_no_current_human_approval_is_not_open() -> None:
    assert compare_control_truth((truth(),), ())["status"] == "NO_CONFLICT"
    assert compare_control_truth((truth(),), ())["comparisons"] == 0


def test_explicit_symbol_code_mapping_ignores_unrelated_lab_and_db_uuids() -> None:
    t = truth()
    assert compare_control_truth((t,), (current(t),))["status"] == "NO_CONFLICT"
    report = compare_control_truth((t,), (replace(current(t), symbol_code="J"),))
    assert report["status"] == "OPEN"
    assert report["comparisons"] == 1
    assert report["conflicts"][0]["expectedSymbolCode"] == "10"


@pytest.mark.parametrize(
    "changes",
    [
        {"position_index": 1},
        {"cell_index": 3},
        {"source_quad": ((1.0, 0.0), (96.0, 0.0), (96.0, 96.0), (0.0, 96.0))},
        {"crop_pixel_sha256": "0" * 64},
        {"source_pixel_sha256": "0" * 64},
    ],
)
def test_different_geometry_slot_or_pixels_are_not_same_control(changes: dict) -> None:
    t = truth()
    assert (
        compare_control_truth((t,), (replace(current(t), symbol_code="J", **changes),))[
            "comparisons"
        ]
        == 0
    )


def install_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[dict, Path]:
    t = truth()
    rgb = np.zeros((96, 96, 3), dtype=np.uint8)
    output = BytesIO()
    Image.fromarray(rgb).save(output, format="PNG")
    png = output.getvalue()
    crop_sha = hashlib.sha256(png).hexdigest()
    ids = [t.symbol_id, *[str(uuid4()) for _ in range(9)]]
    entries = [
        {"id": sid, "code": "symbol_" + sid, "display_name": label}
        for sid, label in zip(ids, MUMIE_CLASS_LABELS, strict=True)
    ]
    binding = {
        "source_sha256": t.source_byte_sha256,
        "board_index": 0,
        "cell_index": 2,
        "quad": [list(p) for p in t.source_quad],
        "pixel_sha256": hashlib.sha256(rgb.tobytes()).hexdigest(),
        "byte_sha256": crop_sha,
    }
    decision = {
        "decision_id": t.decision_id,
        "binding": binding,
        "symbol_id": t.symbol_id,
        "origin": t.origin,
        "actor": "operator",
        "action": "approve",
        "revision": 1,
    }
    proof = json.dumps(
        {"dictionary": {"entries": entries}, "samples": [{"decision": decision}]}
    ).encode()
    proof_sha = hashlib.sha256(proof).hexdigest()
    data = tmp_path / "data"
    data.mkdir()
    (data / "proof.json").write_bytes(proof)
    (data / "crop.png").write_bytes(png)
    row = {
        "controlId": t.control_id,
        "sourceByteSha256": t.source_byte_sha256,
        "normalizedPixelChecksumSha256": t.source_pixel_sha256,
        "sourceWidth": 100,
        "sourceHeight": 100,
        "positionIndex": 0,
        "cellIndex": 2,
        "sourceQuad": [list(p) for p in t.source_quad],
        "renderedPixelChecksumSha256": rgb_pixel_checksum_sha256(rgb),
        "expectedSymbolId": t.symbol_id,
        "expectedSymbolCode": "10",
        "origin": t.origin,
        "actor": "operator",
        "action": "approve",
        "decisionId": t.decision_id,
        "decisionRevision": 1,
        "proofId": proof_sha,
        "cropProofId": crop_sha,
    }
    payload = {
        "controlTruthVersion": TRUTH_VERSION,
        "controlTruthRows": [row],
        "controlTruthProofs": [
            {
                "proofId": proof_sha,
                "kind": "preparation",
                "fileChecksumSha256": proof_sha,
                "relativePath": "proof.json",
            },
            {
                "proofId": crop_sha,
                "kind": "crop_png",
                "fileChecksumSha256": crop_sha,
                "relativePath": "crop.png",
            },
        ],
        "controlTruthSymbolMappings": [
            {
                "labSymbolId": e["id"],
                "labCode": e["code"],
                "labDisplayName": e["display_name"],
                "dbSymbolCode": code,
                "proofId": proof_sha,
            }
            for e, code in zip(entries, MUMIE_CLASS_CODES, strict=True)
        ],
    }
    (data / "descriptor.json").write_text(json.dumps(payload))
    protected = SimpleNamespace(
        byte_checksums={t.source_byte_sha256},
        pixel_checksums={t.source_pixel_sha256},
        reference=lambda: {"checksumSha256": "pinned"},
    )
    monkeypatch.setattr(storage.protections, "load_protected_sources", lambda *_: protected)
    monkeypatch.setattr(storage.protections, "DESCRIPTOR_PATH", "descriptor.json")
    monkeypatch.setattr(storage.protections, "DESCRIPTOR_SHA256", storage._digest(payload))
    return payload, data


def test_proof_roundtrip_repeat_and_missing_png_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, data = install_fixture(tmp_path, monkeypatch)
    first = storage.load_control_truth(tmp_path, uuid4())
    assert storage.load_control_truth(tmp_path, uuid4()) == first
    (data / "crop.png").unlink()
    with pytest.raises(JobConflictError) as error:
        storage.load_control_truth(tmp_path, uuid4())
    assert error.value.code == "PROTECTED_CONTROL_TRUTH_PROOF_INVALID"
    assert error.value.details["status"] == "PROOF_INVALID"


def test_descriptor_label_or_mapping_drift_is_not_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload, data = install_fixture(tmp_path, monkeypatch)
    payload["controlTruthRows"][0]["expectedSymbolCode"] = "J"
    (data / "descriptor.json").write_text(json.dumps(payload))
    monkeypatch.setattr(storage.protections, "DESCRIPTOR_SHA256", storage._digest(payload))
    with pytest.raises(JobConflictError, match="zamrożonego") as error:
        storage.load_control_truth(tmp_path, uuid4())
    assert error.value.details["status"] == "PROOF_INVALID"


def test_promotion_requires_current_comparison_and_exact_candidate_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    t = truth()
    monkeypatch.setattr(storage, "load_control_truth", lambda *_: ((t,), {"sha": "fixed"}))
    monkeypatch.setattr(storage, "current_control_decisions", lambda *_, **__: ())
    assert (
        storage.require_control_truth_promotion(
            None,
            Path("unused"),
            uuid4(),
            {"protectedSourceExclusions": {"sha": "fixed"}},
            lock=False,
        )["comparisons"]
        == 0
    )
    with pytest.raises(JobConflictError) as error:
        storage.require_control_truth_promotion(None, Path("unused"), uuid4(), {}, lock=True)
    assert error.value.code == "PROTECTED_CONTROL_CANDIDATE_UNQUALIFIED"
    monkeypatch.setattr(
        storage,
        "current_control_decisions",
        lambda *_, **__: (replace(current(t), symbol_code="J"),),
    )
    with pytest.raises(JobConflictError) as error:
        storage.require_control_truth_promotion(
            None,
            Path("unused"),
            uuid4(),
            {"protectedSourceExclusions": {"sha": "fixed"}},
            lock=True,
        )
    assert error.value.code == "PROTECTED_CONTROL_TRUTH_CONFLICT_OPEN"


def test_promotion_query_locks_pending_rows_and_alias_pixel_owner() -> None:
    class Session:
        def execute(self, query, params):
            assert "FOR SHARE OF c, rb, src, sgr, d" in str(query)
            assert "normalized_pixel_checksum_sha256" in str(query)
            assert "review_state = 'approved'" not in str(query)
            assert params["pixel_checksums"] == ["c" * 64]
            return SimpleNamespace(mappings=lambda: ())

    assert (
        storage.current_control_decisions(
            Session(),
            Path("unused"),
            UUID(storage.protections.MUMIE_GAME_ID),
            (truth(),),
            lock=True,
        )
        == ()
    )


def current_row(t: ControlTruth) -> dict:
    row = {
        "id": uuid4(),
        "revision": 7,
        "review_state": "approved",
        "assignment_source": "human",
        "assigned_symbol_id": uuid4(),
        "assigned_symbol_code": "J",
        "source_available": True,
        "asset_mode": "virtual_source",
        "crop_sample_id": uuid4(),
        "crop_checksum_sha256": "1" * 64,
        "geometry_revision": 4,
        "source_geometry_revision_id": uuid4(),
        "render_spec_checksum_sha256": "2" * 64,
        "rendered_pixel_checksum_sha256": t.crop_pixel_sha256,
        "source_checksum_sha256": "9" * 64,
        "source_relative_path": "originals/alias.jpg",
        "normalized_pixel_checksum_sha256": t.source_pixel_sha256,
        "source_width": t.source_width,
        "source_height": t.source_height,
        "position_index": t.position_index,
        "cell_index": t.cell_index,
        "render_spec": {"paddedSourceQuad": [list(p) for p in t.source_quad]},
    }
    for field in (
        "asset_mode",
        "crop_sample_id",
        "crop_checksum_sha256",
        "geometry_revision",
        "source_geometry_revision_id",
        "render_spec_checksum_sha256",
        "rendered_pixel_checksum_sha256",
    ):
        row["approved_" + field] = row[field]
    row["current_geometry_revision"] = row["geometry_revision"]
    row["current_source_geometry_revision_id"] = row["source_geometry_revision_id"]
    return row


def mock_current(monkeypatch: pytest.MonkeyPatch, row: dict, pixels: str):
    monkeypatch.setattr(storage, "_with_manifest_render_specs", lambda *_, **kw: kw["rows"])
    monkeypatch.setattr(storage.protections, "source_pixel_identity", lambda *_: pixels)
    monkeypatch.setattr(storage, "_virtual_asset", lambda r: r)
    calls = []
    monkeypatch.setattr(
        storage, "render_virtual_symbol_cell_png", lambda **kw: calls.append(kw["asset"])
    )
    return SimpleNamespace(execute=lambda *_: SimpleNamespace(mappings=lambda: (row,))), calls


def test_reencoded_alias_exact_binding_reads_current_human_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    t = truth()
    row = current_row(t)
    session, calls = mock_current(monkeypatch, row, t.source_pixel_sha256)
    decisions = storage.current_control_decisions(session, Path("unused"), uuid4(), (t,), lock=True)
    assert len(calls) == 1
    assert compare_control_truth((t,), decisions)["status"] == "OPEN"


@pytest.mark.parametrize(
    "changes",
    [
        {"assignment_source": "model"},
        {"review_state": "pending"},
        {"approved_geometry_revision": 3},
        {
            "rendered_pixel_checksum_sha256": "7" * 64,
            "approved_rendered_pixel_checksum_sha256": "7" * 64,
        },
    ],
)
def test_nonhuman_or_different_current_binding_does_not_invent_conflict(
    monkeypatch: pytest.MonkeyPatch, changes: dict
) -> None:
    t = truth()
    row = {**current_row(t), **changes}
    session, calls = mock_current(monkeypatch, row, t.source_pixel_sha256)
    assert (
        storage.current_control_decisions(session, Path("unused"), uuid4(), (t,), lock=False) == ()
    )
    assert calls == []


def test_persisted_source_pixel_drift_fails_guard_before_comparison(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    t = truth()
    session, calls = mock_current(monkeypatch, current_row(t), "0" * 64)
    with pytest.raises(JobConflictError) as error:
        storage.current_control_decisions(session, Path("unused"), uuid4(), (t,), lock=True)
    assert error.value.code == "PROTECTED_CONTROL_CURRENT_PROVENANCE_INVALID"
    assert error.value.details["status"] == "PROVENANCE_INVALID"
    assert calls == []
