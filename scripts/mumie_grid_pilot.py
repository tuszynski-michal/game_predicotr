"""Pilot Mumii A2. Run --help for commands. Domain DB is always read-only, inference is CPU only."""

# ruff: noqa: E402
from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.engine import Connection

ROOT = Path(__file__).resolve().parents[1]
for source in (".", "services/api/src", "services/worker/src"):
    sys.path.insert(0, str(ROOT / source))

from game_predictor_api.application.grid_model_publication import GridModelPublicationService
from game_predictor_api.application.grid_model_registry import GridModelRegistryService
from game_predictor_api.domain.grid_correction_evaluation import IMPROVEMENT_POLICY_VERSION
from game_predictor_api.domain.grid_model_registry import GridModelRegistryError
from game_predictor_api.domain.grid_model_snapshots import catalogue_model_version
from game_predictor_api.storage.grid_engine_model_store import ManagedGridEngineModelStore
from game_predictor_api.storage.grid_model_registry import (
    GridModelArtifactInspector,
    SqlAlchemyGridModelRegistryRepository,
)
from PIL import Image
from sqlalchemy import text
from sqlalchemy.orm import Session

from scripts.mumie_grid_pilot_review import (
    choose_sources,
    engine_for,
    frame_for,
    infer,
    score,
    sha,
    tokens,
)
from scripts.mumie_grid_pilot_sources import (
    GAME,
    IMPORTS,
    check_fresh,
    database,
    fresh_inventory,
    historical,
    imported,
    model,
    recording_context,
    render_context,
)

Document = dict[str, Any]


def store(root: Path) -> sqlite3.Connection:
    root.mkdir(parents=True, exist_ok=True)
    ledger = sqlite3.connect(root / "pilot.sqlite", timeout=10, isolation_level="IMMEDIATE")
    ledger.execute(
        "create table if not exists studies(id text primary key, manifest text not null, "
        "mask text, candidate text, public_digest text, decision text)"
    )
    ledger.execute(
        "create table if not exists reservations(token text primary key,study text not null)"
    )
    return ledger


def freeze(
    db: Connection,
    ledger: sqlite3.Connection,
    study: str,
    rows: list[Document],
    scope: Document,
    base: Document,
    context: Document,
) -> Document:
    if context.get("renderConfiguration", {}).get("paddingFraction") != 0:
        raise ValueError(
            "Do oceny nowego modelu wybierz import z zapisem całego pola (wcięcie 0%)."
        )
    with ledger:
        ledger.execute("begin immediate")
        if ledger.execute("select 1 from studies where id=?", (study,)).fetchone():
            raise ValueError("Ten sprawdzian już istnieje.")
        excluded = {r[0] for r in ledger.execute("select token from reservations")}
        selected = choose_sources(rows, excluded)
        protected = rows if scope["type"] == "folder" else selected
        protected_tokens = set().union(*(tokens(r) for r in protected))
        if excluded.intersection(protected_tokens):
            raise ValueError("Nagranie, zdjęcie lub kopia wcześniej zarezerwowane.")
        manifest = {
            "schema": 2,
            "requiredIndependentGameId": GAME,
            "game": GAME,
            "study": study,
            "frozenAt": db.execute(text("select clock_timestamp()")).scalar_one().isoformat(),
            "base": base,
            "context": context,
            "scope": scope,
            "sample": selected,
            "recording": protected,
        }
        ledger.execute(
            "insert into studies(id,manifest) values (?,?)", (study, json.dumps(manifest))
        )
        ledger.executemany(
            "insert into reservations values (?,?)", [(t, study) for t in protected_tokens]
        )
    return {
        "study": study,
        "boards": len(selected),
        "protectedPhotos": len(protected),
        "manifestSha256": sha(manifest),
    }


def current(conn: Connection, m: Document) -> None:
    active = model(conn)
    if (active["sha256"], active["revision"]) != (m["base"]["sha256"], m["base"]["revision"]):
        raise ValueError("Po zamrożeniu zmieniło się przypisanie bazowe.")
    if m["scope"]["type"] == "folder":
        rows = fresh_inventory(Path(m["scope"]["folder"]), m["scope"]["recordingId"])
        if sha(rows) != sha(m["recording"]):
            raise ValueError("Zmieniła się zawartość całego nagrania.")
        check_fresh(conn, rows)
    else:
        rows = [dict(r) for r in m["sample"]]
        recording_context(conn, rows)
        if any(
            r.get("excluded") or r["guard"] != old["guard"]
            for old, r in zip(m["sample"], rows, strict=False)
        ):
            raise ValueError("Zmieniła się ochrona nagrania lub zdjęcia.")


def decision_evidence(
    conn: Connection, m: Document, version: str, artifacts: Path
) -> tuple[Document, bool, str | None]:
    candidate = model(conn, version)
    manifest = candidate["manifest"]
    if (
        manifest["baseVersionId"] != m["base"]["active"]
        or manifest["versionId"] == manifest["baseVersionId"]
    ):
        raise ValueError("Wersja porównawcza kandydata różni się od przypiętej wersji gry.")
    run = conn.execute(
        text("select created_at,input_payload from jobs where id=:id and game_id=:g"),
        {"id": manifest["provenance"]["runId"], "g": GAME},
    ).one()
    if m["schema"] >= 2:
        origin = manifest["provenance"]
        command = run.input_payload
        if (
            m["requiredIndependentGameId"] != GAME
            or origin.get("independentGameId") != GAME
            or origin.get("weightInitialization") not in ("from_scratch", "assigned_weights")
            or origin["weightInitialization"] != command.get("weight_initialization")
            or (command.get("private_learning") or {}).get("gameId") != GAME
        ):
            raise ValueError(
                "Pilot wymaga modelu z potwierdzonym niezależnym początkiem dla Mumii A2."
            )
    if run.created_at <= datetime.fromisoformat(m["frozenAt"]):
        raise ValueError("Zbiór testowy musi być zamrożony przed rozpoczęciem prac nad kandydatem.")
    reports = conn.execute(
        text("""select r.id,r.report_json from public.grid_model_evaluation_reports r
        where r.version_id=:v
        order by r.created_at desc limit 1"""),
        {"v": version},
    ).first()
    if reports is None:
        return candidate, False, None
    report = json.loads(reports.report_json)
    passed = False
    with Session(bind=conn) as session:
        repository = SqlAlchemyGridModelRegistryRepository(session)
        registry = GridModelRegistryService(repository, GridModelArtifactInspector(artifacts))
        publication = GridModelPublicationService(registry, repository)
        try:
            view = publication._version(UUID(version))
            publication._evidence(view, reports.id, UUID(GAME), publishing=True)
            passed = (
                view["ownerGameId"] == GAME
                and report["trainingGameId"] == GAME
                and report["policyVersion"] == IMPROVEMENT_POLICY_VERSION
            )
        except GridModelRegistryError:
            # A stale or inadmissible candidate can still receive a blind score.
            passed = False
    return candidate, passed, str(reports.id)


def fingerprints(directory: Path) -> dict[str, str]:
    checksums = {}
    for path in sorted(directory.rglob("*")):
        if path.is_file():
            with path.open("rb") as stream:
                checksums[path.relative_to(directory).as_posix()] = hashlib.file_digest(
                    stream, "sha256"
                ).hexdigest()
    return checksums


def package(
    args: argparse.Namespace,
    conn: Connection,
    ledger: sqlite3.Connection,
    m: Document,
    prior: tuple[Any, ...],
) -> Document:
    candidate, _, _ = decision_evidence(conn, m, args.candidate, args.artifacts)
    with ledger:
        ledger.execute("begin immediate")
        locked = ledger.execute(
            "select mask,candidate from studies where id=?", (m["study"],)
        ).fetchone()
        if locked[1] and locked[1] != args.candidate:
            raise ValueError("Sprawdzian przypisano już do innego kandydata.")
        mask = (
            json.loads(locked[0])
            if locked[0]
            else [
                {"id": secrets.token_hex(10), "base": secrets.choice(["A", "B"])}
                for _ in m["sample"]
            ]
        )
        ledger.execute(
            "update studies set mask=?, candidate=? where id=?",
            (json.dumps(mask), args.candidate, m["study"]),
        )
    directory = args.root / m["study"] / "ocena"
    if prior[4]:
        if sha(fingerprints(directory)) != prior[4]:
            raise ValueError("Zmienił się zapieczętowany pakiet.")
        return {"package": str(directory / "index.html")}
    directory.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=directory.parent) as temporary:
        staging = Path(temporary) / "ocena"
        staging.mkdir()
        engines = [engine_for(args.artifacts, x) for x in (m["base"], candidate)]
        cards = []
        for row, blind in zip(m["sample"], mask, strict=True):
            frame = frame_for(row)
            path = staging / blind["id"]
            path.mkdir(parents=True, exist_ok=True)
            Image.fromarray(frame.rgb).save(path / "source.png")
            card = {"id": blind["id"], "position": row["position"]}
            for eng, side in zip(
                engines, [blind["base"], "B" if blind["base"] == "A" else "A"], strict=False
            ):
                card[side] = infer(eng, frame, row, m["context"], path / side)
            cards.append(card)
        public = {"id": sha([m["study"], m["frozenAt"], cards]), "cards": cards}
        (staging / "boards.json").write_text(json.dumps(public), encoding="utf8")
        page = (
            Path(__file__)
            .with_name("templates")
            .joinpath("mumie-grid-pilot.html")
            .read_text(encoding="utf8")
        )
        (staging / "index.html").write_text(
            page.replace("__CARDS__", json.dumps(public)), encoding="utf8"
        )
        checksum = sha(fingerprints(staging))
        try:
            staging.rename(directory)
        except OSError:
            if not directory.is_dir() or sha(fingerprints(directory)) != checksum:
                raise
    with ledger:
        ledger.execute(
            "update studies set public_digest=? where id=?",
            (checksum, m["study"]),
        )
    return {"package": str(directory / "index.html"), "boards": len(cards)}


def diagnostic(
    args: argparse.Namespace, conn: Connection, ledger: sqlite3.Connection, m: Document
) -> Document:
    # Use real case-control pairs that are already exposed in the base's TRAIN material.
    summary, history = historical(conn, m["base"], exact_train=True)
    chosen: list[Document] = []
    blocked = set().union(*(tokens(r) for r in m["recording"]))
    for r in history:
        if r["role"] != "TRAIN" or not r["used"] or not (r["cohort_position"] or {}).get("label"):
            continue
        row = {
            "id": r["source_id"],
            "sha": r["checksum_sha256"],
            "pix": r["photo"],
            "start": r["sequence_range_start"],
            "end": r["sequence_range_end"],
            "position": r["position_index"],
            "job": r["import_id"],
            "execution": r["file_execution_key"],
        }
        if row["id"] in {v["id"] for v in chosen}:
            continue
        recording_context(conn, [row])
        if tokens(row).intersection(blocked):
            continue
        if m["scope"]["type"] == "imports" and not row["groups"]:
            continue
        row["humanNodes"] = r["edited"]
        chosen.append(row)
        if len(chosen) == args.limit:
            break
    if not chosen:
        raise ValueError("Brak niezależnego materiału diagnostycznego.")
    # A later exam cannot reuse a recording or duplicate displayed for diagnosis.
    with ledger:
        for row in chosen:
            for token in tokens(row):
                owner = ledger.execute(
                    "select study from reservations where token=?", (token,)
                ).fetchone()
                if owner and owner[0] != m["study"] + "-diag":
                    raise ValueError("Przypadek diagnostyczny pokrywa się z innym sprawdzianem.")
                ledger.execute(
                    "insert or ignore into reservations values (?,?)", (token, m["study"] + "-diag")
                )
    root = args.root / m["study"] / "diagnoza"
    lookup = {
        r["id"]: r for r in imported(conn, args.artifacts, sorted({r["job"] for r in chosen}))
    }
    engine = engine_for(args.artifacts, m["base"])
    cards = []
    for row in chosen:
        row["file"] = lookup[row["id"]]["file"]
        frame = frame_for(row)
        dest = root / row["id"]
        evidence = infer(engine, frame, row, m["context"], dest, diagnostic=True)
        Image.fromarray(frame.rgb).save(dest / "source.png")
        from PIL import ImageDraw

        overlay = Image.fromarray(frame.rgb)
        draw = ImageDraw.Draw(overlay)
        nodes = row["humanNodes"]
        lines = [[nodes[y * 6 + x] for x in range(6)] for y in range(4)] + [
            [nodes[y * 6 + x] for y in range(4)] for x in range(6)
        ]
        for line in lines:
            draw.line([(p["x"], p["y"]) for p in line], fill="lime", width=2)
        overlay.save(dest / "human.png")
        cards.append(
            {
                "id": row["id"],
                "position": row["position"],
                "sequence": row["start"] + row["position"],
                **evidence,
            }
        )
    page = (
        Path(__file__)
        .with_name("templates")
        .joinpath("mumie-grid-diagnosis.html")
        .read_text(encoding="utf8")
    )
    (root / "index.html").write_text(page.replace("__CARDS__", json.dumps(cards)), encoding="utf8")
    return {"diagnosis": str(root / "index.html"), "samples": len(cards), "history": summary}


def run(args: argparse.Namespace) -> Document:
    with database() as conn:
        base = (
            model(conn, args.version)
            if args.command == "training-geometry" and args.version
            else model(conn)
        )
        if args.command == "history":
            return historical(conn, base, args.before)[0]
        if args.command == "training-geometry":
            from scripts.mumie_grid_pilot_geometry import analyse_training

            ledger = store(args.root)
            try:
                return analyse_training(conn, ledger, base, args.artifacts, args.preview)
            finally:
                ledger.close()
        if args.command == "inspect":
            rows = imported(conn, args.artifacts, args.import_ids)
            recording_context(conn, rows)
            return {
                "sources": len(rows),
                "knownRanges": sum(r["start"] is not None and r["end"] is not None for r in rows),
                "reasons": dict(Counter(r.get("excluded", "eligible") for r in rows)),
                "version": base["active"],
                "revision": base["revision"],
            }
        ledger = store(args.root)
        try:
            if args.command == "freeze":
                ManagedGridEngineModelStore(args.artifacts).require(
                    catalogue_model_version(base["manifest"])
                )
                if args.folder is not None:
                    if args.folder.resolve().is_relative_to(args.artifacts.resolve()):
                        raise ValueError("Przenieś świeże nagranie poza katalog artefaktów.")
                    if not args.confirm_complete_fresh_recording:
                        raise ValueError(
                            "Potwierdź jedno pełne nowe nagranie w osobnym folderze "
                            "i jego wyłączenie z importu, uczenia i diagnozy."
                        )
                    recording_id = args.recording_id or args.study
                    rows = fresh_inventory(args.folder, recording_id)
                    check_fresh(conn, rows)
                    scope = {
                        "type": "folder",
                        "folder": str(args.folder.resolve()),
                        "recordingId": recording_id,
                        "wholeFreshRecordingAttested": True,
                    }
                else:
                    rows = imported(conn, args.artifacts, args.import_ids)
                    recording_context(conn, rows)
                    scope = {"type": "imports", "ids": args.import_ids}
                return freeze(
                    conn,
                    ledger,
                    args.study,
                    rows,
                    scope,
                    base,
                    render_context(conn, args.contract_import),
                )
            prior = ledger.execute("select * from studies where id=?", (args.study,)).fetchone()
            if not prior:
                raise ValueError("Najpierw zamroź 100 pozycji.")
            m = json.loads(prior[1])
            current(conn, m)
            if args.command == "diagnose":
                return diagnostic(args, conn, ledger, m)
            if args.command == "blind":
                return package(args, conn, ledger, m, prior)
            if not prior[4]:
                raise ValueError("Brakuje ukończonego pakietu ze sprawdzianem.")
            directory = args.root / m["study"] / "ocena"
            if sha(fingerprints(directory)) != prior[4]:
                raise ValueError("Naruszona integralność arkusza lub obrazów.")
            public = json.loads((directory / "boards.json").read_text())
            votes = json.loads(args.votes.read_text(encoding="utf8"))
            if votes["study"] != public["id"]:
                raise ValueError("Oceny pochodzą z innego sprawdzianu.")
            _, passed, report_id = decision_evidence(conn, m, prior[3], args.artifacts)
            mask = {r["id"]: r["base"] for r in json.loads(prior[2])}
            verdict = score(public["cards"], mask, votes["votes"], passed)
            result = {
                **verdict,
                "reference": m["base"]["active"],
                "candidate": prior[3],
                "evaluation": report_id,
                "votesSha256": sha(votes),
                "manifestSha256": sha(m),
            }
            with ledger:
                ledger.execute(
                    "update studies set decision=coalesce(decision,?) where id=?",
                    (json.dumps(result), m["study"]),
                )
                stored = json.loads(
                    ledger.execute(
                        "select decision from studies where id=?", (m["study"],)
                    ).fetchone()[0]
                )
                if stored != result:
                    raise ValueError("Wynik zapieczętowano wcześniej z inną oceną lub dowodem.")
            return result
        finally:
            ledger.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, default=ROOT / "artifacts")
    sub = parser.add_subparsers(dest="command", required=True)
    history = sub.add_parser("history")
    history.add_argument(
        "--before",
        type=datetime.fromisoformat,
        help="Górny wyłączny czas korekty (ISO 8601 ze strefą).",
    )
    analysis = sub.add_parser("training-geometry")
    analysis.add_argument("--version", type=lambda v: str(UUID(v)), help="Wersja z kohortą TRAIN.")
    analysis.add_argument(
        "--preview", type=Path, help="Nowy katalog na podgląd pól przed i po korekcie."
    )
    inspect = sub.add_parser("inspect")
    inspect.add_argument("--import-ids", nargs="+", default=IMPORTS)
    for name in ("freeze", "diagnose", "blind", "score"):
        p = sub.add_parser(name)
        if name == "freeze":
            p.add_argument(
                "study", nargs="?", default=str(uuid4()), type=lambda value: str(UUID(value))
            )
        else:
            p.add_argument("study", type=lambda value: str(UUID(value)))
        if name == "freeze":
            group = p.add_mutually_exclusive_group(required=True)
            group.add_argument("--folder", type=Path)
            group.add_argument("--import-ids", nargs="+")
            p.add_argument("--recording-id", type=lambda v: str(UUID(v)))
            p.add_argument("--confirm-complete-fresh-recording", action="store_true")
            p.add_argument("--contract-import", default=IMPORTS[0])
        elif name == "diagnose":
            p.add_argument("--limit", type=int, choices=range(1, 21), default=5)
        elif name == "blind":
            p.add_argument("candidate", type=lambda v: str(UUID(v)))
        elif name == "score":
            p.add_argument("votes", type=Path)
    args = parser.parse_args()
    args.root = args.artifacts / "mumie-grid-pilot"
    print(json.dumps(run(args), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
