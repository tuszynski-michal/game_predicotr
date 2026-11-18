"""Read-only source, recording, cohort and model adapters for the Mumie A2 pilot."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import numpy as np
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.grid_model_registry import descriptor_sha256
from game_predictor_api.domain.image_geometry_v2 import parse_attested_sequence_range_filename
from game_predictor_api.domain.symbol_model_snapshots import SymbolModelJobSnapshot
from game_predictor_api.storage.job_repository import job_from_record
from game_predictor_api.storage.models import JobModel
from game_predictor_worker.images.normalization import CanonicalSourceLoader
from game_predictor_worker.images.pipeline_contract import (
    SYMBOL_RGB_PREPROCESSING_VERSION,
    VIRTUAL_CELL_RENDERER_VERSION,
)
from game_predictor_worker.images.source_ingestion import ManagedOriginalStore
from game_predictor_worker.images.virtual_cell_extraction import VIRTUAL_CELL_INTERPOLATION_VERSION
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

Document = dict[str, Any]

GAME = "246a1f54-eee8-49d5-b11a-0fde70e5eecd"
IMPORTS = ["5fd0aca9-b703-430b-a666-f5cbf31609df", "02379ba9-d694-4975-8ea7-241a50aa3c09"]


@contextmanager
def database(url: str | None = None) -> Iterator[Connection]:
    engine = create_engine(
        url or ApiSettings.from_environment().owner_database_url,
        isolation_level="REPEATABLE READ",
        connect_args={
            "connect_timeout": 5,
            "options": (
                "-c default_transaction_read_only=on -c statement_timeout=45000 "
                "-c search_path=game_data_v2,public"
            ),
        },
    )
    try:
        with engine.connect() as conn:
            conn.execute(text("select set_config('game_predictor.game_id',:g,true)"), {"g": GAME})
            yield conn
    finally:
        engine.dispose()


def model(conn: Connection, version: str | None = None) -> Document:
    assignment = conn.execute(
        text("select version_id,revision from game_grid_model_assignments where game_id=:g"),
        {"g": GAME},
    ).one()
    identity = version or str(assignment.version_id)
    row = conn.execute(
        text(
            "select manifest_json,manifest_sha256,created_at "
            "from public.grid_model_versions where id=:v"
        ),
        {"v": identity},
    ).one()
    manifest = json.loads(row.manifest_json)
    if manifest["versionId"] != identity or descriptor_sha256(manifest) != row.manifest_sha256:
        raise ValueError("Niezgodny manifest modelu.")
    return {
        "manifest": manifest,
        "sha256": row.manifest_sha256,
        "registered": row.created_at.isoformat(),
        "active": str(assignment.version_id),
        "revision": assignment.revision,
    }


def render_context(conn: Connection, job: str, *, revision_topology: str | None = None) -> Document:
    payload = conn.execute(
        text("select input_payload from jobs where id=:j and game_id=:g"), {"j": job, "g": GAME}
    ).scalar_one()
    symbol = SymbolModelJobSnapshot.from_payload(payload["symbol_model"])
    topology = (payload.get("neural_grid_operation_pin") or {}).get("topologyRulesVersionId")
    if revision_topology is not None and topology not in (None, revision_topology):
        raise ValueError("Niezgodna topologia importu i zatwierdzonej korekty.")
    if topology is None and revision_topology is None:
        raise ValueError("Brak potwierdzonej topologii importu.")
    return {
        "topologyRulesVersionId": topology or revision_topology,
        "renderConfiguration": {
            "extractorVersion": VIRTUAL_CELL_RENDERER_VERSION,
            "preprocessingVersion": SYMBOL_RGB_PREPROCESSING_VERSION,
            "interpolation": VIRTUAL_CELL_INTERPOLATION_VERSION,
            "outputWidth": symbol.crop_output_size,
            "outputHeight": symbol.crop_output_size,
            "paddingFraction": symbol.crop_padding_fraction,
        },
    }


def imported(conn: Connection, artifacts: Path, jobs: list[str]) -> list[Document]:
    result = []
    for job in jobs:
        # The managed originals manifest predates detection, including completely missed boards.
        with Session(bind=conn) as session:
            record = session.get(JobModel, UUID(job))
            if record is None or str(record.game_id) != GAME:
                raise ValueError("Import spoza zakresu gry.")
            manifest = ManagedOriginalStore(artifacts).load_existing_manifest(
                job_from_record(record)
            )
        rows = conn.execute(
            text("""select id::text id,checksum_sha256 sha,normalized_pixel_checksum_sha256 pix,
          file_execution_key execution
          from source_images where game_id=:g and import_job_id=:j"""),
            {"g": GAME, "j": job},
        ).mappings()
        stored = {row["sha"]: dict(row) for row in rows}
        for o in manifest.originals:
            r = stored.get(o.checksum_sha256)
            if r is None:
                r = {
                    "id": None,
                    "sha": o.checksum_sha256,
                    "pix": None,
                    "execution": None,
                    "excluded": "brak tożsamości źródła w rejestrze",
                }
            result.append(
                {
                    **dict(r),
                    "file": str((artifacts / o.managed_relative_path).resolve()),
                    "start": o.sequence_range_start,
                    "end": o.sequence_range_end,
                    "job": job,
                }
            )
    return result


def recording_context(conn: Connection, rows: list[Document]) -> None:
    rows = [row for row in rows if row["id"] is not None]
    groups = {
        str(v.id)
        for v in conn.execute(
            text("""select id from public.recording_groups
           where membership_complete and declared and independent""")
        )
    }
    exposed_groups = {
        str(group_id)
        for group_id in conn.execute(
            text("""select distinct unnest(group_ids || dependency_group_ids)
              from public.recording_evidence where kind in ('ancestor','use')""")
        ).scalars()
    }
    for i in range(0, len(rows), 200):
        batch = rows[i : i + 200]
        data = conn.execute(
            text("select public.recording_photo_context_data_v3(:g,cast(:ids as uuid[]),false)"),
            {"g": GAME, "ids": [r["id"] for r in batch]},
        ).scalar_one()
        contexts = {c["sourceId"]: c for c in data}
        for r in batch:
            c = contexts[r["id"]]
            group = c["componentIds"]
            r.update(groups=group, aliases=c["aliasComponentIds"], guard=c["proofSha256"])
            if not group or not set(group) <= groups:
                r["excluded"] = "brak potwierdzonego pełnego nagrania"
            elif (
                exposed_groups.intersection(group)
                or c["diagnosticExposed"]
                or c["selectionExposed"]
                or c["photoRoles"]
                or c["usedTrainAliasLabels"]
            ):
                r["excluded"] = "wcześniejsza ekspozycja nagrania lub kopii"
            elif c["allowedRoles"] != ["REGRESSION"]:
                r["excluded"] = "nagranie niechronione przed treningiem"


def fresh_inventory(folder: Path, recording: str) -> list[Document]:
    from uuid import NAMESPACE_URL, uuid5

    group = str(UUID(recording))
    paths = sorted(
        p
        for p in folder.rglob("*")
        if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
    )
    rows = []
    for path in paths:
        if path.is_symlink() or not path.resolve().is_relative_to(folder.resolve()):
            raise ValueError("Zdjęcie poza katalogiem nagrania.")
        seq = parse_attested_sequence_range_filename(path.name)
        with path.open("rb") as stream:
            sha = hashlib.file_digest(stream, "sha256").hexdigest()
        frame = CanonicalSourceLoader().load(path, expected_source_checksum_sha256=sha)
        pix = frame.pixel_checksum_sha256
        rows.append(
            {
                "id": str(uuid5(NAMESPACE_URL, group + "/" + sha)),
                "sha": sha,
                "pix": pix,
                "file": str(path.resolve()),
                "start": seq.start,
                "end": seq.end,
                "job": group,
                "execution": sha,
                "groups": [group],
                "aliases": [],
            }
        )
    return rows


def check_fresh(conn: Connection, rows: list[Document]) -> None:
    # Check the entire sealed recording, including pictures not selected in the exam.
    for i in range(0, len(rows), 200):
        batch = rows[i : i + 200]
        keys = {
            "b": [r["sha"] for r in batch],
            "p": [r["pix"] for r in batch],
            "groups": list({g for r in batch for g in r["groups"]}),
        }
        overlap = conn.execute(
            text("""select exists(
           select 1 from source_images
             where checksum_sha256=any(:b)
                or normalized_pixel_checksum_sha256=any(:p)
           union all
           select 1 from public.recording_occurrences
             where source_sha256=any(:b)
                or pixel_sha256=any(:p)
                or group_id=any(cast(:groups as uuid[]))
           union all
           select 1 from public.recording_photo_uses
             where source_sha256=any(:b)
                or pixel_sha256=any(:p)
                or group_ids && cast(:groups as uuid[])
           union all
           select 1 from public.recording_evidence
             where payload->>'sourceSha256'=any(:b)
                or payload->>'pixelSha256'=any(:p)
                or group_ids && cast(:groups as uuid[])
                or dependency_group_ids && cast(:groups as uuid[])
           union all
           select 1 from grid_training_cohort_members
             where frozen->'source'->>'checksum_sha256'=any(:b)
                or frozen->'source'->>'normalized_pixel_checksum_sha256'=any(:p))"""),
            keys,
        ).scalar_one()
        if overlap:
            raise ValueError(
                "Nagranie lub kopia są już obecne w danych, kohorcie lub historii użycia."
            )


def historical(
    conn: Connection, base: Document, before: datetime | None = None, *, exact_train: bool = False
) -> tuple[Document, list[Document]]:
    query = Path(__file__).with_name("mumie_grid_pilot_history.sql").read_text(encoding="utf8")
    rows = conn.execute(
        text(query), {"g": GAME, "cohort": base["manifest"]["cohortId"], "exact_train": exact_train}
    ).mappings()
    counts: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    accepted = []
    raw = 0
    for row in rows:
        if before is not None and row["created_at"] >= before:
            continue
        raw += 1
        old = [n for slot, n in (row["neighbors"] or []) if int(slot) == row["position_index"]]

        def valid(nodes: Any) -> bool:
            if (
                not isinstance(nodes, list)
                or len(nodes) != 24
                or not all(
                    isinstance(p, dict)
                    and all(
                        isinstance(p.get(d), int | float) and math.isfinite(p[d])
                        for d in ("x", "y")
                    )
                    for p in nodes
                )
            ):
                return False
            grid = np.array([[p["x"], p["y"]] for p in nodes]).reshape(4, 6, 2)
            spans = (
                np.diff(grid, axis=0),
                np.diff(grid, axis=1),
                grid[:, -1] - grid[:, 0],
                grid[-1] - grid[0],
            )
            return all(np.linalg.norm(v, axis=-1).min() >= 1e-6 for v in spans)

        if row["nc"] != 15 or row["np"] != 1 or row["completeness_status"] != "complete":
            counts["incomplete_parent_evidence"] += 1
        elif not row["photo"] or len(old) != 1 or not valid(old[0]) or not valid(row["edited"]):
            counts["unusable_pair"] += 1
        else:
            position = row["cohort_position"] or {}
            label = position.get("label") or {}
            if not position:
                reason = "brak pozycji w kohorcie tej wersji"
            elif not row["used"] or not label:
                reason = " / ".join(
                    row["reasons"] or [position.get("reason") or "poza użytym zbiorem"]
                )
            elif (
                label.get("nodes") != row["edited"]
                or (label.get("approval") or {}).get("geometryRevision") != row["revision"]
                or (label.get("approval") or {}).get("manualRevisionId")
                != row["manual_revision_id"]
            ):
                reason = "inna rewizja lub geometria w kohorcie"
            else:
                reason = "użyta etykieta " + str(row["role"])
            reasons[reason] += 1
            accepted.append(dict(row))
    return {
        "scanned": raw,
        "excludedBeforePair": dict(counts),
        "pairs": len(accepted),
        "photos": len({r["photo"] for r in accepted}),
        "cohort": base["manifest"]["cohortId"],
        "model": base["manifest"]["versionId"],
        "qualificationReasons": dict(reasons),
    }, accepted
