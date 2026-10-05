"""Recognize the proposed audit crops without changing geometry or symbol approvals.

Run bounded rounds with ``python -m scripts.recognize_grid_audit_symbols``.
Each completed board is published atomically with a checksum manifest. The
frozen library and model are recovered after a process restart.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from uuid import UUID

import numpy as np
from game_predictor_api.application.grid_audit_symbol_suggestions import (
    SYMBOL_ALGORITHM_VERSION,
    SYMBOL_SUGGESTIONS_DIRECTORY,
    SYMBOL_SUGGESTIONS_SCHEMA,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.schemas.image_grid_reviews import ImageGridReviewGeometryPreviewCommand
from game_predictor_api.security.local_admin import ADMIN_INTENT_HEADER, ADMIN_INTENT_VALUE
from game_predictor_worker.symbols.reference_library import (
    CROP_SIZE,
    combined_descriptor,
    decide,
    descriptor_matrix,
    hint_candidates,
    normalize_rows,
    vote_batch,
)
from numpy.typing import NDArray
from PIL import Image

from scripts import evaluate_symbol_reference_library as reference

Json = dict[str, Any]
DISPLAY_POLICY = "best-candidate-v1"


def write_json(path: Path, value: object) -> str:
    content = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)
    return hashlib.sha256(content).hexdigest()


def request(base: str, path: str, body: Mapping[str, object] | None = None) -> bytes:
    command = Request(
        base + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Content-Type": "application/json", ADMIN_INTENT_HEADER: ADMIN_INTENT_VALUE},
        method="GET" if body is None else "POST",
    )
    with urlopen(command, timeout=10) as response:
        return cast(bytes, response.read())


def read_json(base: str, path: str) -> Any:
    return json.loads(request(base, path))


def preview_command(view: Mapping[str, Any]) -> Json:
    item = view["reviewItem"]
    qualification = item.get("geometryQualification")
    partial = qualification is not None and qualification["completenessStatus"] == "pending_partial"
    corners = [
        {
            "x": point["x"] if partial else min(max(point["x"], 0), item["sourceWidth"] - 1),
            "y": point["y"] if partial else min(max(point["y"], 0), item["sourceHeight"] - 1),
        }
        for point in view["proposal"]["corners"]
    ]
    # The existing unqualified full-board workflow sends null. Explicit
    # qualifications retain the flags the operator would see on opening.
    if qualification is not None:
        qualification = {
            **qualification,
            "version": "manual-geometry-qualification-v2",
            "includeInPartialGridTraining": bool(qualification.get("includeInPartialGridTraining")),
        }
    raw = {
        "corners": corners,
        "geometryQualification": qualification,
        **{
            "expected" + key[0].upper() + key[1:]: item[key]
            for key in (
                "geometryRevision",
                "resolutionRevision",
                "sourceChecksumSha256",
                "sourceWidth",
                "sourceHeight",
                "gridRows",
                "gridColumns",
            )
        },
    }
    return cast(
        Json,
        ImageGridReviewGeometryPreviewCommand.model_validate(raw).model_dump(
            by_alias=True, mode="json"
        ),
    )


def contact_sheet_crops(content: bytes, rows: int, columns: int) -> NDArray[np.uint8]:
    with Image.open(io.BytesIO(content)) as image:
        if image.format != "PNG" or image.size != (columns * CROP_SIZE, rows * CROP_SIZE):
            raise ValueError("The preview must contain lossless 64 x 64 RGB crops.")
        rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    return cast(
        NDArray[np.uint8],
        np.stack(
            [
                rgb[
                    row * CROP_SIZE : (row + 1) * CROP_SIZE,
                    column * CROP_SIZE : (column + 1) * CROP_SIZE,
                ]
                for row in range(rows)
                for column in range(columns)
            ]
        ),
    )


def publish(directory: Path, item_id: str, document: Json) -> str:
    sha256 = write_json(directory / f"{item_id}.json", document)
    write_json(directory / f"{item_id}.manifest.json", {"sha256": sha256})
    return sha256


def completed(
    directory: Path,
    item_id: str,
    audit_sha: str,
    command: Json,
    display_policy: str | None = None,
) -> bool:
    manifest = directory / f"{item_id}.manifest.json"
    path = directory / f"{item_id}.json"
    if not manifest.is_file():
        return False
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != json.loads(manifest.read_bytes())["sha256"]:
        raise ValueError(f"Suggestion checksum mismatch: {item_id}")
    document = json.loads(content)
    return bool(
        document["auditSha256"] == audit_sha
        and document["previewCommand"] == command
        and (display_policy is None or document.get("displayPolicy") == display_policy)
    )


def frozen_library(
    arguments: argparse.Namespace,
    audit: Json,
    deadline: float,
) -> tuple[reference.ActiveModel, NDArray[np.int64], reference.FloatArray, reference.FloatArray]:
    output = cast(Path, arguments.output_dir)
    metadata_path = output / "library.json"
    arrays_path = output / "library.npz"
    if metadata_path.is_file():
        metadata = json.loads(metadata_path.read_bytes())
        if metadata["auditSha256"] != audit["artifactSha256"]:
            raise ValueError("The frozen library belongs to another audit.")
        if hashlib.sha256(arrays_path.read_bytes()).hexdigest() != metadata["arraysSha256"]:
            raise ValueError("The frozen library arrays differ from their checksum.")
        model = reference.ActiveModel(
            metadata["iterationId"],
            Path(metadata["checkpointPath"]),
            metadata["checkpointSha256"],
            tuple(metadata["classCodes"]),
        )
        if (
            hashlib.sha256(model.checkpoint_path.read_bytes()).hexdigest()
            != model.checkpoint_sha256
        ):
            raise ValueError("The frozen model checkpoint differs from its checksum.")
        with np.load(arrays_path, allow_pickle=False) as archive:
            return model, archive["labels"], archive["shape"], archive["combined"]
    settings = ApiSettings.from_environment()
    root = (arguments.artifact_root or settings.artifact_root).resolve()
    snapshot = reference._read_snapshot(
        settings,
        arguments.game_code,
        root,
        {"min_confidence": 0.0, "max_confidence": 0.0, "per_symbol": 0, "order_salt": ""},
        reference_policy="no-bulk-approve-v2",
        references_per_group=40,
    )
    if snapshot.game_id != arguments.game_id:
        raise ValueError("The game code and game id identify different games.")
    source_content = (
        root / "grid-audit-proposals" / arguments.game_id / audit["auditId"] / "proposals.json"
    ).read_bytes()
    if hashlib.sha256(source_content).hexdigest() != audit["artifactSha256"]:
        raise ValueError("The audit file differs from the API snapshot.")
    source_document = json.loads(source_content)
    excluded = {
        (entry["importJobId"], entry["sequenceNumber"]) for entry in source_document["items"]
    }
    references = [
        cell
        for cell in snapshot.references
        if (cell.import_job_id, cell.sequence_number) not in excluded
    ]
    cache, remaining = reference._render(
        references,
        artifact_root=root,
        cache_path=cast(Path, arguments.library_cache),
        deadline=deadline,
    )
    if remaining:
        raise TimeoutError("Library crops remain; resume the same command.")
    library = reference._build_library(references, cache, snapshot.model)
    output.mkdir(parents=True, exist_ok=True)
    temporary_arrays = output / "library.tmp.npz"
    np.savez(
        temporary_arrays, labels=library.labels, shape=library.shape, combined=library.combined
    )
    temporary_arrays.replace(arrays_path)
    write_json(
        metadata_path,
        {
            "auditSha256": audit["artifactSha256"],
            "arraysSha256": hashlib.sha256(arrays_path.read_bytes()).hexdigest(),
            "iterationId": snapshot.model.iteration_id,
            "checkpointPath": str(snapshot.model.checkpoint_path),
            "checkpointSha256": snapshot.model.checkpoint_sha256,
            "classCodes": snapshot.model.class_codes,
            "references": len(library.cells),
            "excludedAuditedReferences": len(snapshot.references) - len(references),
            "referencePolicy": "no-bulk-approve-v2",
        },
    )
    return snapshot.model, library.labels, library.shape, library.combined


def run(arguments: argparse.Namespace) -> int:
    arguments.game_id = str(UUID(arguments.game_id))
    started = time.monotonic()
    deadline = started + arguments.max_seconds
    output = cast(Path, arguments.output_dir).resolve()
    arguments.output_dir = output
    base = arguments.api_base_url.rstrip("/")
    origin = urlsplit(base)
    if origin.scheme != "http" or origin.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("Only the local HTTP Admin API is supported.")
    collection = f"/api/v1/admin/games/{arguments.game_id}/grid-audit-proposals"
    first = cast(Json, read_json(base, collection + "?limit=50"))
    root = (arguments.artifact_root or ApiSettings.from_environment().artifact_root).resolve()
    directory = (
        root
        / "grid-audit-proposals"
        / arguments.game_id
        / first["auditId"]
        / SYMBOL_SUGGESTIONS_DIRECTORY
    )
    model, labels, reference_shape, reference_combined = frozen_library(arguments, first, deadline)
    symbols = {
        entry["code"]: entry["id"]
        for entry in read_json(base, f"/api/v1/admin/games/{arguments.game_id}/symbols")
        if entry["status"] == "active"
    }
    counts = {
        "processed": 0,
        "recovered": 0,
        "confident": 0,
        "tentative": 0,
        "uncertain": 0,
        "changedMeanwhile": 0,
    }
    state_path = output / "cursor.json"
    state = json.loads(state_path.read_bytes()) if state_path.is_file() else {}
    if state and state["auditSha256"] != first["artifactSha256"]:
        raise ValueError("The saved cursor belongs to another audit.")
    if state.get("displayPolicy") != DISPLAY_POLICY:
        state = {}
    page = (
        first
        if not state or state.get("afterOrdinal") is None
        else cast(
            Json,
            read_json(
                base,
                collection + "?" + urlencode({"limit": 50, "afterOrdinal": state["afterOrdinal"]}),
            ),
        )
    )

    def checkpoint(entry: Json) -> None:
        write_json(
            state_path,
            {
                "auditSha256": first["artifactSha256"],
                "afterOrdinal": entry["ordinal"],
                "displayPolicy": DISPLAY_POLICY,
            },
        )

    print(
        json.dumps(
            {
                "started": True,
                "openBoards": first["counts"]["open"],
                "afterOrdinal": state.get("afterOrdinal"),
            }
        ),
        flush=True,
    )
    while True:
        for entry in page["items"]:
            if time.monotonic() >= deadline - 5:
                write_json(
                    output / "status.json",
                    {
                        "complete": False,
                        "counts": counts,
                        "elapsedSeconds": round(time.monotonic() - started, 2),
                    },
                )
                print(json.dumps({"complete": False, **counts}), flush=True)
                return 3
            view = cast(Json, read_json(base, collection + "/" + entry["itemId"]))
            if view["reviewItem"] is None or view["proposal"] is None:
                counts["changedMeanwhile"] += 1
                checkpoint(entry)
                continue
            command = preview_command(view)
            if completed(
                directory, entry["itemId"], first["artifactSha256"], command, DISPLAY_POLICY
            ):
                counts["recovered"] += 1
                checkpoint(entry)
                continue
            item = view["reviewItem"]
            query = urlencode({"gameId": arguments.game_id, "importJobId": item["importJobId"]})
            try:
                content = request(
                    base,
                    f"/api/v1/admin/image-reviews/{item['reviewItemId']}/geometry-preview?{query}",
                    command,
                )
            except HTTPError as error:
                if error.code == 409:
                    current = read_json(base, collection + "/" + entry["itemId"])
                    if current["reviewItem"] is None:
                        counts["changedMeanwhile"] += 1
                        checkpoint(entry)
                        continue
                raise
            crops = contact_sheet_crops(content, item["gridRows"], item["gridColumns"])
            shape, hue = descriptor_matrix(list(crops))
            combined = normalize_rows(
                combined_descriptor(shape, reference._feature_maps(model, crops), hue)
            )
            proposals = [
                decide(shape_vote, combined_vote)
                for shape_vote, combined_vote in zip(
                    vote_batch(shape, reference_shape, labels, class_count=len(model.class_codes)),
                    vote_batch(
                        combined, reference_combined, labels, class_count=len(model.class_codes)
                    ),
                    strict=True,
                )
            ]
            unavailable = set(
                (command["geometryQualification"] or {}).get("unavailableCellIndices", [])
            )
            cells = []
            for index, proposal in enumerate(proposals):
                candidate_index = proposal.class_index
                is_tentative = False
                if candidate_index is None:
                    candidates = hint_candidates(proposal, 1)
                    if candidates:
                        candidate_index = candidates[0]
                        is_tentative = True
                code = (
                    None
                    if candidate_index is None or index in unavailable
                    else model.class_codes[candidate_index]
                )
                symbol_id = symbols.get(code) if code is not None else None
                cells.append(
                    {
                        "cellIndex": index,
                        "symbolId": symbol_id,
                        "symbolCode": code,
                        "isTentative": is_tentative and symbol_id is not None,
                        "reason": proposal.reason
                        if index not in unavailable
                        else "unavailable_pixels",
                    }
                )
                category = (
                    "uncertain"
                    if symbol_id is None
                    else ("tentative" if is_tentative else "confident")
                )
                counts[category] += 1
            publish(
                directory,
                entry["itemId"],
                {
                    "schema": SYMBOL_SUGGESTIONS_SCHEMA,
                    "algorithmVersion": SYMBOL_ALGORITHM_VERSION,
                    "displayPolicy": DISPLAY_POLICY,
                    "gameId": arguments.game_id,
                    "auditId": first["auditId"],
                    "auditSha256": first["artifactSha256"],
                    "itemId": entry["itemId"],
                    "reviewItemId": item["reviewItemId"],
                    "previewCommand": command,
                    "generatedAt": datetime.now(UTC).isoformat(),
                    "cells": cells,
                    "previewSha256": hashlib.sha256(content).hexdigest(),
                    "checkpointSha256": model.checkpoint_sha256,
                },
            )
            counts["processed"] += 1
            checkpoint(entry)
            if counts["processed"] % 10 == 0:
                print(json.dumps(counts), flush=True)
        after = page["nextAfterOrdinal"]
        if after is None:
            break
        page = cast(
            Json,
            read_json(base, collection + "?" + urlencode({"limit": 50, "afterOrdinal": after})),
        )
        if page["artifactSha256"] != first["artifactSha256"]:
            raise ValueError("The audit changed during recognition.")
    # Re-read the complete open queue after the last page. A lost response or
    # an externally removed artifact cannot make a cursor claim completion.
    coverage = cast(Json, read_json(base, collection + "?limit=50"))
    missing: list[str] = []
    covered = 0
    while True:
        for entry in coverage["items"]:
            manifest_path = directory / f"{entry['itemId']}.manifest.json"
            if not manifest_path.is_file():
                missing.append(entry["itemId"])
                continue
            content = (directory / f"{entry['itemId']}.json").read_bytes()
            document = json.loads(content)
            if (
                hashlib.sha256(content).hexdigest()
                != json.loads(manifest_path.read_bytes())["sha256"]
            ):
                raise ValueError(f"Suggestion checksum mismatch: {entry['itemId']}")
            if (
                document["auditSha256"] != first["artifactSha256"]
                or document.get("displayPolicy") != DISPLAY_POLICY
            ):
                missing.append(entry["itemId"])
            else:
                covered += 1
        if coverage["nextAfterOrdinal"] is None:
            break
        coverage = cast(
            Json,
            read_json(
                base,
                collection
                + "?"
                + urlencode({"limit": 50, "afterOrdinal": coverage["nextAfterOrdinal"]}),
            ),
        )
    if missing:
        write_json(
            state_path,
            {
                "auditSha256": first["artifactSha256"],
                "afterOrdinal": None,
                "displayPolicy": DISPLAY_POLICY,
            },
        )
        raise ValueError(
            f"The open queue has {len(missing)} unrecognized boards; resume to recover them."
        )
    counts["coveredOpenBoards"] = covered
    write_json(
        output / "status.json",
        {
            "complete": True,
            "counts": counts,
            "elapsedSeconds": round(time.monotonic() - started, 2),
        },
    )
    print(json.dumps({"complete": True, **counts}), flush=True)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-id", required=True)
    parser.add_argument("--game-code", required=True)
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--library-cache", required=True, type=Path)
    parser.add_argument("--max-seconds", type=int, default=80, choices=range(10, 101))
    try:
        return run(parser.parse_args(argv))
    except TimeoutError as error:
        print(str(error), flush=True)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
