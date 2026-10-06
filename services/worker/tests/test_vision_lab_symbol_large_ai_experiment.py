"""Multi-reference exact rasters, immutable proofs and separate AI provenance."""

import hashlib
import io
import os
import stat
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from game_predictor_worker.vision_lab import symbol_large_ai_experiment as module
from game_predictor_worker.vision_lab.annotations import digest, read_checked, write_atomic
from game_predictor_worker.vision_lab.geometry import crop_cell
from game_predictor_worker.vision_lab.snapshot import canonical, sha
from game_predictor_worker.vision_lab.symbol_ai_experiment import consensus
from game_predictor_worker.vision_lab.symbol_training_manifest import SymbolTrainingInputs
from PIL import Image
from test_vision_lab_symbol_ai_experiment import cohort as cohort


@pytest.fixture
def larger(request, tmp_path, monkeypatch):
    c = request.getfixturevalue("cohort")
    # The legacy adapter is covered by its original suite. This fixture isolates
    # new packet/proof semantics while using actual rendered PNG/source bytes.
    payload = deepcopy(c.inputs.payload)
    payload.update(batch=str(read_checked(c.selection)["batch"]), ai_sample_ids=[], ai_audit_ids=[])
    prior = SymbolTrainingInputs("legacy", payload, c.inputs.preparation, c.inputs.bundle)
    monkeypatch.setattr(
        module, "SymbolAiExperimentAdapter", lambda _: SimpleNamespace(validate=lambda: prior)
    )
    monkeypatch.setattr(module, "validate_batch", lambda _: c.batch)
    root = tmp_path / "large-proof"
    root.mkdir()
    groups = {}
    for row in c.batch["rows"]:
        with Image.open(row["path"]) as image:
            groups[row["sha256"]] = digest(
                [image.size, hashlib.sha256(image.tobytes()).hexdigest()]
            )
    selected_cases, prepared = [], []
    for i in range(101):
        source = c.batch["rows"][i % 2]
        x, y = float(2 + (i % 10) * 3), float(10 + (i // 10) * 3)
        quad = [[x, y], [x + 90, y], [x + 90, y + 90], [x, y + 90]]
        with Image.open(source["path"]) as image:
            raster = crop_cell(np.asarray(image), np.asarray(quad, dtype=np.float32))
        buffer = io.BytesIO()
        Image.fromarray(raster).save(buffer, format="PNG", compress_level=6)
        data = buffer.getvalue()
        case = {
            "case_id": digest(["large", i]),
            "source": source,
            "quad": quad,
            "board": i // 15 + 1,
            "field": i % 15 + 1,
            "byte_sha256": hashlib.sha256(data).hexdigest(),
            "pixel_sha256": hashlib.sha256(raster.tobytes()).hexdigest(),
            "category": "blind",
            "photo_url": "http://localhost/review",
        }
        selected_cases.append(
            {
                "source": source,
                "quad": quad,
                "board": case["board"],
                "field": case["field"],
                "photo_index": i % 2,
                "crop_pixel_sha256": case["pixel_sha256"],
                "human_approved": False,
            }
        )
        prepared.append((case, data))
    pins = {str(c.base): sha(c.base), **{row["path"]: row["sha256"] for row in c.batch["rows"]}}
    base_receipt = root / "qualified-frozen.json"
    write_atomic(base_receipt, {"manifest_id": c.base.stem, "manifest": str(c.base)})
    pins[str(base_receipt)] = sha(base_receipt)
    monkeypatch.setattr(module, "BASE_MANIFEST_ID", c.base.stem)
    monkeypatch.setattr(module, "BASE_QUALIFICATION_SHA", sha(base_receipt))
    selection = {
        "format": "mumie-large-candidate-selection-v1",
        "training_targets_created": 0,
        "human_labels_written": 0,
        "cnn_started": False,
        "accuracy": None,
        "packets": 2,
        "selected": 101,
        "cases": selected_cases,
        "batch": str(read_checked(c.selection)["batch"]),
        "batch_id": digest(c.batch),
        "classes": [e["display_name"] for e in prior.preparation["dictionary"]["entries"]],
        "forbidden_pixels": [
            s["decision"]["binding"]["pixel_sha256"] for s in prior.preparation["samples"]
        ],
        "protected_sources": [],
        "protected_photo_groups": [],
        "withheld_photo_indices": [],
        "third_photo_groups": groups,
        "pins": dict(pins),
    }
    selection_path = root / "selection.json"
    write_atomic(selection_path, selection)
    pins[str(selection_path)] = sha(selection_path)
    proofs, all_rows = [], []
    review_paths = []
    for index, cases in enumerate((prepared[:100], prepared[100:])):
        ref = {**deepcopy(c.ref), "cases": [case for case, _ in cases]}
        reference = root / "references" / digest(ref)
        (reference / "crops").mkdir(parents=True)
        write_atomic(reference / "reference.json", ref)
        packet_pins = {
            str(selection_path): sha(selection_path),
            str(reference / "reference.json"): sha(reference / "reference.json"),
        }
        for case, data in cases:
            path = reference / "crops" / (case["byte_sha256"] + ".png")
            path.write_bytes(data)
            packet_pins[str(path)] = sha(path)
        reviews = []
        for name in ("a", "b"):
            report = deepcopy(read_checked(c.reviews[0]))
            report["reviewer"] = name
            report["reference_id"] = reference.name
            report["items"] = [
                {
                    **report["items"][0],
                    "index": i + 1,
                    "case_id": case["case_id"],
                    "byte_sha256": case["byte_sha256"],
                    "pixel_sha256": case["pixel_sha256"],
                }
                for i, (case, _data) in enumerate(cases)
            ]
            path = root / f"review-{index}-{name}.json"
            write_atomic(path, report)
            reviews.append(path)
            packet_pins[str(path)] = sha(path)
        rows = [
            dict(row, case=case)
            for row, (case, _data) in zip(consensus(ref, reviews), cases, strict=True)
        ]
        proof = {
            "format": "mumie-large-packet-assessment-v1",
            "packet_index": index,
            "selection_id": digest(selection),
            "selection_sha256": sha(selection_path),
            "origin": "ai_visual_assessment",
            "human_approved": False,
            "human_labels_written": 0,
            "super_targets": 0,
            "cnn_started": False,
            "reference": str(reference),
            "reference_id": reference.name,
            "reviews": [str(p) for p in reviews],
            "rows": rows,
            "pins": packet_pins,
        }
        path = root / f"proof-{index}.json"
        write_atomic(path, proof)
        proofs.append({"path": str(path), "id": digest(proof), "sha256": sha(path)})
        all_rows.extend(rows)
        pins.update(packet_pins)
        pins[str(path)] = sha(path)
        review_paths.extend(reviews)
    qualified = {
        "format": "mumie-large-visual-qualification-v1",
        "origin": "ai_visual_assessment",
        "human_approved": False,
        "human_labels_written": 0,
        "super_targets": 0,
        "cnn_started": False,
        "accuracy": None,
        "selection": str(selection_path),
        "selection_id": digest(selection),
        "selected": 101,
        "assessed_twice": 101,
        "references": proofs,
        "pins": pins,
        "rows": all_rows,
        "counts": {"A": 101},
        "accepted": 101,
        "rejected": 0,
    }
    path = root / (digest(qualified) + ".json")
    write_atomic(path, qualified)
    pointer = root / "qualified-visual.json"
    write_atomic(pointer, {"path": str(path), "id": digest(qualified)})
    descriptor = {
        "pointer": str(pointer),
        "pointer_sha256": sha(pointer),
        "id": digest(qualified),
        "file_sha256": sha(path),
    }
    return SimpleNamespace(
        base=c.base,
        descriptor=descriptor,
        output=tmp_path / "large-output",
        prior=prior,
        qualified=qualified,
        selection=selection,
        reviews=review_paths,
    )


def test_101_cases_span_two_unchanged_reference_limits_and_preserve_humans(larger):
    before = canonical(larger.prior.preparation)
    manifest = module.freeze(larger.base, larger.descriptor, larger.output)
    assert module.freeze(larger.base, larger.descriptor, larger.output) == manifest
    inputs = module.LargeAiExperimentAdapter(manifest).validate()
    assert canonical(larger.prior.preparation) == before
    assert inputs.preparation["samples"][:3] == larger.prior.preparation["samples"]
    assert inputs.payload["counts"]["new_ai_development"] == 101
    assert inputs.payload["feedback_sample_ids"] == larger.prior.payload["feedback_sample_ids"]
    assert all(
        s["decision"]["origin"] == "ai_visual_assessment"
        and s["decision"]["human_approved"] is False
        and s["decision"]["trainable"] is False
        for s in inputs.preparation["samples"][3:]
    )


def test_resigned_review_drift_is_detected_before_recomposition(larger):
    manifest = module.freeze(larger.base, larger.descriptor, larger.output)
    review = read_checked(larger.reviews[0])
    review["items"][0]["class"] = "B"
    write_atomic(larger.reviews[0], review)
    with pytest.raises(ValueError, match="INPUT_DRIFT"):
        module.LargeAiExperimentAdapter(manifest).validate()


def test_resigned_qualification_cannot_claim_human_origin(larger):
    pointer = read_checked(Path(larger.descriptor["pointer"]))
    value = deepcopy(larger.qualified)
    value["human_approved"] = True
    path = Path(pointer["path"])
    write_atomic(path, value)
    with pytest.raises(ValueError, match="INPUT_DRIFT"):
        module.compose(larger.base, larger.descriptor, larger.output / "runs")


def test_publication_cannot_overlap_its_exact_source_inputs(larger):
    with pytest.raises(ValueError, match="DIRECTORY_OVERLAP"):
        module.freeze(larger.base, larger.descriptor, larger.base.parent / "output")


def republish_qualification(larger, value):
    pointer = Path(larger.descriptor["pointer"])
    path = pointer.parent / (digest(value) + ".json")
    write_atomic(path, value)
    write_atomic(pointer, {"path": str(path), "id": digest(value)})
    return {
        "pointer": str(pointer),
        "pointer_sha256": sha(pointer),
        "id": digest(value),
        "file_sha256": sha(path),
    }


def test_another_correctly_pinned_base_cannot_replace_accepted_r2(larger):
    alternative = larger.base.parent / ("b" * 64 + ".json")
    alternative.write_bytes(larger.base.read_bytes())
    qualified = deepcopy(larger.qualified)
    qualified["pins"][str(alternative)] = sha(alternative)
    descriptor = republish_qualification(larger, qualified)
    with pytest.raises(ValueError, match="ACCEPTED_R2_BASE_REQUIRED"):
        module.compose(alternative, descriptor, larger.output / "runs")


def test_cache_is_defensive_and_revalidates_actual_inputs(larger):
    manifest = module.freeze(larger.base, larger.descriptor, larger.output)
    adapter = module.LargeAiExperimentAdapter(manifest)
    first = adapter.validate()
    first.preparation["samples"].clear()
    first.payload["ai_sample_ids"].clear()
    assert len(adapter.validate().preparation["samples"]) == 104
    review = read_checked(larger.reviews[0])
    review["items"][0]["class"] = "B"
    write_atomic(larger.reviews[0], review)
    with pytest.raises(ValueError, match="INPUT_DRIFT"):
        adapter.validate()


def resign_selection(larger, selected):
    qualified = deepcopy(larger.qualified)
    selection_path = Path(qualified["selection"])
    write_atomic(selection_path, selected)
    qualified["selection_id"] = digest(selected)
    qualified["pins"][str(selection_path)] = sha(selection_path)
    for marker in qualified["references"]:
        path = Path(marker["path"])
        proof = read_checked(path)
        proof["selection_id"] = digest(selected)
        proof["selection_sha256"] = sha(selection_path)
        proof["pins"][str(selection_path)] = sha(selection_path)
        write_atomic(path, proof)
        marker.update(id=digest(proof), sha256=sha(path))
        qualified["pins"][str(path)] = sha(path)
    return republish_qualification(larger, qualified)


@pytest.mark.parametrize("exclusion", ["human", "pixel", "decoded_photo", "quad"])
def test_resigned_graph_cannot_admit_human_claims_or_protected_crops(larger, exclusion):
    selected = deepcopy(larger.selection)
    first = selected["cases"][0]
    if exclusion == "human":
        first["human_approved"] = True
    elif exclusion == "pixel":
        selected["forbidden_pixels"].append(first["crop_pixel_sha256"])
    elif exclusion == "decoded_photo":
        selected["protected_photo_groups"].append(
            selected["third_photo_groups"][first["source"]["sha256"]]
        )
    else:
        first["quad"][0][0] += 1
    descriptor = resign_selection(larger, selected)
    with pytest.raises(ValueError, match="CASE_EXCLUSION_INVALID|PROTECTED_PHOTO_ALIAS"):
        module.compose(larger.base, descriptor, larger.output / "runs")


def test_batched_link_guard_rechecks_ancestor_after_hashing(tmp_path, monkeypatch):
    source = tmp_path / "source.png"
    source.write_bytes(b"frozen")
    real_lstat = Path.lstat
    visits = []

    def altered(path, *args, **kwargs):
        if path == tmp_path:
            visits.append(path)
            if len(visits) == 2:
                return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=1024)
        return real_lstat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", altered)
    with pytest.raises(ValueError, match="REPARSE_POINT"):
        module.pins_valid({str(source): sha(source)})


@pytest.mark.skipif(os.name != "nt", reason="Windows case-insensitive Path aliases")
def test_case_alias_cannot_discard_conflicting_pin(tmp_path):
    source = tmp_path / "source.png"
    source.write_bytes(b"frozen")
    with pytest.raises(ValueError, match="INPUT_DRIFT"):
        module.pins_valid({str(source): "0" * 64, str(source).swapcase(): sha(source)})
