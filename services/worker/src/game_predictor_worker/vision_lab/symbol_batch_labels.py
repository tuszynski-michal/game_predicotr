"""Exact crop review of independent inference; never whole-board approval."""

import argparse
import base64
import hashlib
import html
import io
import os
import tempfile
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .annotations import digest, exclusive_bounded, read_checked, write_atomic
from .geometry import crop_cell
from .snapshot import canonical, reject_links, safe_file, sha
from .symbol_batch import load_photo, result_path, validate_batch, validate_result
from .symbol_contracts import (
    BatchCasePreview,
    BatchLabelDecide,
    BatchQueuePreview,
    DictionaryView,
    SymbolResult,
)
from .symbol_crops import render_spec
from .symbol_store import publish_file
from .symbol_training_manifest import SymbolTrainingAdapter

FORMAT = "lab-symbol-batch-review-v1"
BLOCKERS = ["SYMBOL_BATCH_GEOMETRY_NOT_APPROVED", "SYMBOL_SPLIT_NOT_FROZEN"]


def separate(root: Path, protected: list[Path]) -> None:
    if not root.is_absolute():
        raise ValueError("SYMBOL_BATCH_ABSOLUTE_PATH_REQUIRED")
    reject_links(root)
    for other in protected:
        reject_links(other)
        a, b = root.resolve(), other.resolve()
        if a.is_relative_to(b) or b.is_relative_to(a):
            raise ValueError("SYMBOL_BATCH_REVIEW_DIRECTORY_OVERLAP")


def prepare(batch: Path, cases_path: Path, output: Path) -> Path:
    """Freeze only cases already bound to the qualified independent batch."""
    payload = validate_batch(batch)
    training = Path(payload["training_manifest"])
    provenance: dict[str, str] = {}
    if payload.get("generation") == 3:
        from .symbol_batch_inputs import batch_inputs

        cohort = batch_inputs(training, 3).inputs
        inputs = SymbolTrainingAdapter(Path(cohort.payload["base_manifest"])).validate()
        if cohort.preparation["dictionary"] != inputs.preparation["dictionary"]:
            raise ValueError("SYMBOL_BATCH_REVIEW_DICTIONARY_MISMATCH")
        # Review approves only these case rasters. Keep full cohort validation at
        # preparation and base approval/history guards in the resulting UI packet.
        provenance[str(training)] = sha(training)
        provenance[str(cohort.bundle / "preparation.json")] = sha(
            cohort.bundle / "preparation.json"
        )
    else:
        inputs = SymbolTrainingAdapter(training).validate()
    evidence = read_checked(cases_path)
    if (
        evidence.get("format") != "mumie-targeted-review-evidence-v1"
        or evidence["candidate_batch_id"] != digest(payload)
        or not 1 <= len(evidence["cases"]) <= 100
        or evidence["human_labels_written"] != 0
    ):
        raise ValueError("SYMBOL_BATCH_REVIEW_EVIDENCE_INVALID")
    separate(
        output,
        [
            batch,
            cases_path.parent,
            inputs.bundle,
            *[Path(p).parent for p in inputs.payload["live_bindings"]],
        ],
    )
    # Reuse original approval provenance; preparation is not a new dictionary approval.
    dictionary = inputs.preparation["dictionary"]
    entries = dictionary["entries"]
    if [e["display_name"] for e in entries] != payload["classes"]:
        raise ValueError("SYMBOL_BATCH_REVIEW_DICTIONARY_MISMATCH")
    live = {**inputs.payload["live_bindings"], **provenance}
    for path in [
        cases_path,
        batch / "manifest.json",
        Path(payload["training_manifest"]),
        inputs.bundle / "manifest.json",
    ]:
        live[str(path)] = sha(path)
    cases, pngs = [], {}
    photos: dict[int, Image.Image] = {}
    for case in evidence["cases"]:
        index = case["photo_index"]
        result = validate_result(batch, payload, index)
        if (
            case["source"] != result["row"]
            or case["source"]["sha256"] in payload["excluded_sha256"]
        ):
            raise ValueError("SYMBOL_BATCH_REVIEW_SOURCE_EXCLUDED")
        cell = next(
            c
            for c in result["cells"]
            if c["board_index"] == case["board"] - 1 and c["cell_index"] == case["field"] - 1
        )
        if (
            case["quad"] != cell["quad"]
            or case["crop_pixel_sha256"] != cell["crop_pixel_sha256"]
            or case["human_approved"]
        ):
            raise ValueError("SYMBOL_BATCH_REVIEW_BINDING_MISMATCH")
        if index not in photos:
            photos[index] = load_photo(case["source"], payload["training_photo_pixel_groups"])
        crop = crop_cell(np.asarray(photos[index]), np.asarray(case["quad"], dtype=np.float32))
        if crop is None or hashlib.sha256(crop.tobytes()).hexdigest() != case["crop_pixel_sha256"]:
            raise ValueError("SYMBOL_BATCH_REVIEW_PIXEL_DRIFT")
        stream = io.BytesIO()
        Image.fromarray(crop).save(stream, format="PNG", compress_level=6)
        data = stream.getvalue()
        byte_sha = hashlib.sha256(data).hexdigest()
        item = {
            "source": case["source"],
            "board": case["board"],
            "field": case["field"],
            "quad": case["quad"],
            "pixel_sha256": case["crop_pixel_sha256"],
            "byte_sha256": byte_sha,
            "category": case["category"],
            "photo_url": f"http://127.0.0.1:8108/{batch.name}/photos/{index:04d}/review.html",
        }
        item["case_id"] = digest(item)
        cases.append(item)
        pngs[byte_sha] = data
        path = result_path(batch, index)
        live[str(path)] = sha(path)
    if len({c["case_id"] for c in cases}) != len(cases):
        raise ValueError("SYMBOL_BATCH_REVIEW_DUPLICATE_CASE")
    reference = {
        "format": FORMAT,
        "batch_id": digest(payload),
        "dictionary": dictionary,
        "cases": cases,
        "render_spec": render_spec(),
        "live_bindings": live,
        "guard_roots": [
            str(Path(p).parent)
            for p in inputs.payload["live_bindings"]
            if Path(p).name == "state.json"
        ],
        "forbidden_photo_pixels": payload["training_photo_pixel_groups"],
        "trainable": False,
    }
    root = output / digest(reference)
    for checksum, data in pngs.items():
        publish_file(root / "crops" / (checksum + ".png"), data)
    publish_file(
        root / "reference.json", canonical({"payload": reference, "sha256": digest(reference)})
    )
    return root


class BatchReviewStore:
    def __init__(self, reference: Path, root: Path, protected: tuple[Path, ...] = ()):
        self.reference, self.root = reference, root
        reject_links(reference)
        payload = self.reference_payload()
        separate(
            root,
            [
                reference,
                *protected,
                *[Path(p).parent for p in payload["live_bindings"]],
                *[Path(c["source"]["path"]).parent for c in payload["cases"]],
            ],
        )
        self.guards = [Path(p) for p in payload["guard_roots"]]
        if len(self.guards) != len(set(self.guards)):
            raise ValueError("SYMBOL_BATCH_REVIEW_INTEGRITY_ERROR")

    def reference_payload(self) -> dict[str, Any]:
        payload = read_checked(self.reference / "reference.json")
        if (
            payload.get("format") != FORMAT
            or self.reference.name != digest(payload)
            or not 1 <= len(payload["cases"]) <= 100
        ):
            raise ValueError("SYMBOL_BATCH_REVIEW_INTEGRITY_ERROR")
        return payload

    @contextmanager
    def locked(self) -> Iterator[None]:
        # Original geometry first, then original symbols, then the independent decisions.
        with ExitStack() as stack:
            for root in [*self.guards, self.root]:
                stack.enter_context(exclusive_bounded(root))
            yield

    def state(self, reference_id: str) -> dict[str, Any]:
        empty = {
            "format": FORMAT,
            "reference_id": reference_id,
            "revision": 0,
            "decisions": [],
            "receipts": {},
            "history": [],
        }
        path = self.root / "state.json"
        state = read_checked(path) if path.exists() else empty
        if (
            state.keys() != empty.keys()
            or state["format"] != FORMAT
            or state["reference_id"] != reference_id
        ):
            raise ValueError("SYMBOL_BATCH_REVIEW_INTEGRITY_ERROR")
        return state

    def validate_live(self, payload: dict[str, Any]) -> None:
        if payload["render_spec"] != render_spec():
            raise ValueError("SYMBOL_BATCH_REVIEW_RENDERER_DRIFT")
        for name, expected in payload["live_bindings"].items():
            path = Path(name)
            reject_links(path)
            if sha(path) != expected:
                raise ValueError("SYMBOL_BATCH_REVIEW_INPUT_DRIFT")

    def png(self, case: dict[str, Any], payload: dict[str, Any], *, render: bool = False) -> bytes:
        # Check actual source before exposing even the frozen crop.
        source = case["source"]
        path = Path(source["path"])
        reject_links(path)
        if sha(path) != source["sha256"]:
            raise ValueError("SYMBOL_BATCH_REVIEW_SOURCE_DRIFT")
        data = safe_file(self.reference, "crops/" + case["byte_sha256"] + ".png").read_bytes()
        if len(data) > 256 * 1024 or hashlib.sha256(data).hexdigest() != case["byte_sha256"]:
            raise ValueError("SYMBOL_BATCH_REVIEW_CROP_INTEGRITY_ERROR")
        with Image.open(io.BytesIO(data)) as image:
            if (
                image.mode != "RGB"
                or image.size != (96, 96)
                or hashlib.sha256(image.tobytes()).hexdigest() != case["pixel_sha256"]
            ):
                raise ValueError("SYMBOL_BATCH_REVIEW_CROP_INTEGRITY_ERROR")
        if render:
            source_image = load_photo(source, payload["forbidden_photo_pixels"])
            crop = crop_cell(np.asarray(source_image), np.asarray(case["quad"], dtype=np.float32))
            if crop is None or hashlib.sha256(crop.tobytes()).hexdigest() != case["pixel_sha256"]:
                raise ValueError("SYMBOL_BATCH_REVIEW_PIXEL_DRIFT")
        return data

    def preview(self) -> BatchQueuePreview:
        with self.locked():
            payload = self.reference_payload()
            self.validate_live(payload)
            state = self.state(digest(payload))
            current = {d["case_id"]: d for d in state["decisions"]}
            items = []
            for case in payload["cases"]:
                decision = current.get(case["case_id"], {})
                items.append(
                    BatchCasePreview(
                        case_id=case["case_id"],
                        filename=case["source"]["filename"],
                        board=case["board"],
                        field=case["field"],
                        category=case["category"],
                        png_base64=base64.b64encode(self.png(case, payload)).decode("ascii"),
                        pixel_sha256=case["pixel_sha256"],
                        photo_url=case["photo_url"],
                        action=decision.get("action"),
                        symbol_id=decision.get("symbol_id"),
                        decision_id=decision.get("decision_id"),
                    )
                )
            dictionary = payload["dictionary"]
            return BatchQueuePreview(
                reference_id=digest(payload),
                revision=state["revision"],
                dictionary=DictionaryView(
                    game_id=dictionary["game_id"],
                    version=dictionary["version"],
                    digest=dictionary["digest"],
                    status="approved",
                    active=True,
                    entries=dictionary["entries"],
                ),
                items=items,
            )

    def mutate(self, request: BatchLabelDecide) -> SymbolResult:
        with self.locked():
            payload = self.reference_payload()
            reference_id = digest(payload)
            if request.reference_id != reference_id:
                raise ValueError("SYMBOL_BATCH_REVIEW_REFERENCE_CONFLICT")
            state = self.state(reference_id)
            fingerprint = digest(request.model_dump())
            if receipt := state["receipts"].get(request.request_id):
                if receipt["fingerprint"] != fingerprint:
                    raise ValueError("REQUEST_ID_CONFLICT")
                return SymbolResult.model_validate({**receipt["result"], "replayed": True})
            if state["revision"] != request.expected_revision:
                raise ValueError("SYMBOL_REVISION_CONFLICT")
            self.validate_live(payload)
            case = next((c for c in payload["cases"] if c["case_id"] == request.case_id), None)
            if case is None:
                raise ValueError("SYMBOL_BATCH_REVIEW_CASE_CONFLICT")
            if request.action == "approve" and request.symbol_id not in {
                e["id"] for e in payload["dictionary"]["entries"]
            }:
                raise ValueError("SYMBOL_CLASS_INVALID")
            self.png(case, payload, render=True)
            if len(state["decisions"]) >= 10000:
                raise ValueError("STORE_LIMIT_REACHED")
            revision = state["revision"] + 1
            decision = {
                **request.model_dump(),
                "origin": "batch_crop_review",
                "decision_id": fingerprint,
                "revision": revision,
                "decided_at": datetime.now(UTC).isoformat(),
                "trainable": False,
            }
            result = SymbolResult(
                revision=revision,
                request_id=request.request_id,
                result_id=fingerprint,
                decision_ids=[fingerprint],
                reasons=[BLOCKERS[0]],
                training_blockers=BLOCKERS,
            )
            state["revision"] = revision
            state["decisions"].append(decision)
            state["history"].append(
                {"request_id": request.request_id, "decision_id": fingerprint, "revision": revision}
            )
            state["receipts"][request.request_id] = {
                "fingerprint": fingerprint,
                "result": result.model_dump(),
            }
            write_atomic(self.root / "state.json", state)
            return result


def publish_portal(reference: Path, destination: Path) -> None:
    """Replace the derivative diagnostic page, keeping its original immutable copy."""
    payload = read_checked(reference / "reference.json")
    if reference.name != digest(payload) or payload["format"] != FORMAT:
        raise ValueError("SYMBOL_BATCH_REVIEW_INTEGRITY_ERROR")
    allowed = {
        Path(p).parent / "review.html"
        for p in payload["live_bindings"]
        if Path(p).name == "cases.json"
    }
    if destination not in allowed:
        raise ValueError("SYMBOL_BATCH_REVIEW_PORTAL_PATH_INVALID")
    reject_links(destination)
    if destination.exists():
        original = destination.with_name("review.before-editing.html")
        if not original.exists():
            publish_file(original, destination.read_bytes())
    cards = []
    for index, case in enumerate(payload["cases"]):
        png = safe_file(reference, "crops/" + case["byte_sha256"] + ".png").read_bytes()
        if hashlib.sha256(png).hexdigest() != case["byte_sha256"]:
            raise ValueError("SYMBOL_BATCH_REVIEW_CROP_INTEGRITY_ERROR")
        href = "http://127.0.0.1:3102/symbols/batch?case=" + case["case_id"]
        encoded = base64.b64encode(png).decode("ascii")
        photo_url = html.escape(case["photo_url"], quote=True)
        cards.append(
            f'<article><a href="{href}"><img width="96" height="96" '
            f'alt="Popraw symbol {index + 1}" src="data:image/png;base64,{encoded}"></a>'
            f"<b>{html.escape(case['source']['filename'])}</b>"
            f"<p>Plansza {case['board']}, pole {case['field']}</p>"
            f'<p><a href="{href}">Popraw symbol</a></p>'
            f'<p><a href="{photo_url}" target="_blank" rel="noreferrer">'
            "Pokaż całe zdjęcie</a></p></article>"
        )
    document = (
        '<!doctype html><html lang="pl"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>Mumie — korekta symboli</title><style>"
        "body{font:16px system-ui;background:#111827;color:#f8fafc;"
        "margin:24px;max-width:1200px}a{color:#93c5fd}"
        ".cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}"
        "article{background:#1f2937;padding:14px;border-radius:8px}"
        "img{display:block;margin-bottom:12px}p{line-height:1.5}</style>"
        "<h1>Mumie — korekta symboli</h1><p>Kliknij wycinek albo „Popraw symbol”. "
        "W edytorze wybierz klasę i naciśnij „Zapisz symbol”. "
        "Nie trzeba zmieniać poprawnej siatki.</p>"
        '<p><a href="http://127.0.0.1:3102/symbols/batch">'
        'Otwórz edytor wszystkich wycinków</a></p><div class="cards">'
        + "".join(cards)
        + "</div></html>"
    )
    descriptor, name = tempfile.mkstemp(prefix=".portal-", dir=destination.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(document.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=Path)
    parser.add_argument("--cases", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--gallery", type=Path)
    args = parser.parse_args()
    if not all(
        p.is_absolute()
        for p in (args.batch, args.cases, args.output, args.reference, args.gallery)
        if p is not None
    ):
        parser.error("Absolute paths required")
    if args.reference is not None:
        if (
            any(p is not None for p in (args.batch, args.cases, args.output))
            or args.gallery is None
        ):
            parser.error("Reference-only operation requires --gallery and no preparation arguments")
        root = args.reference
    else:
        if any(p is None for p in (args.batch, args.cases, args.output)):
            parser.error("Preparation requires --batch, --cases, --output")
        root = prepare(args.batch, args.cases, args.output)
    if args.gallery is not None:
        publish_portal(root, args.gallery)
    print(root)


if __name__ == "__main__":
    main()
