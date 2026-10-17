"""Bounded, checksum-verified index of the original pinned neural manifest.

The derived SQLite file is disposable. It contains no images or inference.
One streaming pass indexes a manifest, never one whole-manifest scan per source.
"""

from __future__ import annotations

import codecs
import hashlib
import json
import os
import sqlite3
import time
from collections.abc import Iterator, Mapping
from pathlib import Path, PurePosixPath
from typing import BinaryIO, cast

_CHUNK = 65536
_MAX_ENTRY = 2 * 1024 * 1024
HISTORICAL_EVIDENCE_INDEX_VERSION = "historical-neural-evidence-index-v1"


def _sqlite_path(path: Path) -> str:
    value = str(path.resolve())
    return "\\\\?\\" + value if os.name == "nt" and not value.startswith("\\\\?\\") else value


class HistoricalEvidenceUnavailable(ValueError):
    pass


class _ObjectStream:
    def __init__(self, file: BinaryIO) -> None:
        self.file = file
        self.buffer = ""
        self.digest = hashlib.sha256()
        self.decoder = codecs.getincrementaldecoder("utf-8")()
        self.eof = False
        self.deadline = time.monotonic() + 15

    def fill(self) -> None:
        if time.monotonic() > self.deadline:
            raise HistoricalEvidenceUnavailable("HISTORICAL_EVIDENCE_INDEX_TIME_LIMIT")
        raw = self.file.read(_CHUNK)
        self.digest.update(raw)
        self.eof = not raw
        self.buffer += self.decoder.decode(raw, final=self.eof)

    def peek(self) -> str:
        while True:
            self.buffer = self.buffer.lstrip()
            if self.buffer or self.eof:
                return self.buffer[:1]
            self.fill()

    def token(self, expected: str) -> None:
        if self.peek() != expected:
            raise HistoricalEvidenceUnavailable("HISTORICAL_MODEL_PROVENANCE_INVALID")
        self.buffer = self.buffer[1:]

    def value(self) -> object:
        self.peek()
        while True:
            try:
                value, end = json.JSONDecoder().raw_decode(self.buffer)
                if end > _MAX_ENTRY:
                    raise HistoricalEvidenceUnavailable("HISTORICAL_EVIDENCE_ENTRY_TOO_LARGE")
                if end == len(self.buffer) and not self.eof:
                    self.fill()
                    continue
                self.buffer = self.buffer[end:]
                return value
            except json.JSONDecodeError as error:
                if self.eof or len(self.buffer) > _MAX_ENTRY:
                    raise HistoricalEvidenceUnavailable(
                        "HISTORICAL_MODEL_PROVENANCE_INVALID"
                    ) from error
                self.fill()

    def object_keys(self, *, opened: bool = False, first: bool = True) -> Iterator[str]:
        if not opened:
            self.token("{")
            first = True
        while self.peek() != "}":
            if not first:
                self.token(",")
            first = False
            key = self.value()
            if not isinstance(key, str):
                raise HistoricalEvidenceUnavailable("HISTORICAL_MODEL_PROVENANCE_INVALID")
            self.token(":")
            yield key
        self.token("}")


def _signature(path: Path) -> dict[str, object]:
    stat = path.stat()
    return {
        "path": str(path),
        "size": stat.st_size,
        "mtime": stat.st_mtime_ns,
        "ctime": stat.st_ctime_ns,
    }


MAX_ENTRIES_PER_STEP = 1000
INDEX_STEP_SECONDS = 15


def _offset(parser: _ObjectStream) -> int:
    pending, _ = parser.decoder.getstate()
    return parser.file.tell() - len(parser.buffer.encode("utf-8")) - len(pending)


def _verify(path: Path, expected: str) -> None:
    # Hashing bytes is a separate phase from JSON indexing. It never runs under
    # source locks; the index is unpublished until this completes.
    digest = hashlib.sha256()
    deadline = time.monotonic() + 30
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            if time.monotonic() >= deadline:
                raise HistoricalEvidenceUnavailable("HISTORICAL_EVIDENCE_VERIFICATION_TIME_LIMIT")
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise HistoricalEvidenceUnavailable("HISTORICAL_MODEL_PROVENANCE_DRIFT")


def _prepare_index(path: Path, index: Path, checksum: str, signature: dict[str, object]) -> bool:
    from contextlib import closing

    building = index.with_suffix(".building.sqlite")
    state: dict[str, object] = {
        "version": HISTORICAL_EVIDENCE_INDEX_VERSION,
        "signature": signature,
        "headers": {},
        "offset": 0,
        "phase": "indexing",
        "entries_started": False,
    }
    if building.exists():
        try:
            with closing(sqlite3.connect(_sqlite_path(building), timeout=2)) as database:
                previous = json.loads(database.execute("SELECT value FROM metadata").fetchone()[0])
            if (
                previous.get("signature") == signature
                and previous.get("version") == HISTORICAL_EVIDENCE_INDEX_VERSION
            ):
                state = previous
            else:
                building.unlink()
        except (sqlite3.DatabaseError, json.JSONDecodeError, TypeError):
            building.unlink(missing_ok=True)
    with closing(sqlite3.connect(_sqlite_path(building), timeout=2)) as database:
        database.execute(
            "CREATE TABLE IF NOT EXISTS entries (checksum TEXT PRIMARY KEY, value TEXT)"
        )
        database.execute("CREATE TABLE IF NOT EXISTS metadata (value TEXT NOT NULL)")
        database.execute("BEGIN IMMEDIATE")
        # Re-read after obtaining the SQLite writer lock. Parallel preview calls
        # never roll an index cursor backward or publish a partial index.
        prior = database.execute("SELECT value FROM metadata").fetchone()
        if prior:
            state = json.loads(prior[0])
        if state["signature"] != signature:
            raise HistoricalEvidenceUnavailable("HISTORICAL_MODEL_PROVENANCE_DRIFT")
        if state["phase"] == "indexing":
            with path.open("rb") as file:
                file.seek(cast(int, state["offset"]))
                parser = _ObjectStream(file)
                # Budget is checked between complete entries, so a partial JSON
                # object never replaces the durable boundary checkpoint.
                parser.deadline = float("inf")
                headers = dict(cast(Mapping[str, object], state["headers"]))
                deadline, processed = time.monotonic() + INDEX_STEP_SECONDS, 0
                top = parser.object_keys(opened=bool(state["entries_started"]), first=False)
                if state["entries_started"]:
                    entries = parser.object_keys(opened=True, first=False)
                else:
                    entries = None
                    for key in top:
                        if key == "entries":
                            entries = parser.object_keys()
                            state["entries_started"] = True
                            break
                        if key in headers:
                            raise HistoricalEvidenceUnavailable(
                                "HISTORICAL_MODEL_PROVENANCE_INVALID"
                            )
                        headers[key] = parser.value()
                if entries is None:
                    raise HistoricalEvidenceUnavailable("HISTORICAL_MODEL_PROVENANCE_MISSING")
                exhausted = False
                for processed, source_key in enumerate(entries, start=1):
                    entry = parser.value()
                    database.execute(
                        "INSERT INTO entries VALUES (?, ?)",
                        (source_key, json.dumps(entry, separators=(",", ":"))),
                    )
                    state["offset"] = _offset(parser)
                    if processed >= MAX_ENTRIES_PER_STEP or time.monotonic() >= deadline:
                        exhausted = True
                        break
                if not exhausted:
                    if state["offset"]:
                        top = parser.object_keys(opened=True, first=False)
                    for key in top:
                        if key in headers or key == "entries":
                            raise HistoricalEvidenceUnavailable(
                                "HISTORICAL_MODEL_PROVENANCE_INVALID"
                            )
                        headers[key] = parser.value()
                    if parser.peek():
                        raise HistoricalEvidenceUnavailable("HISTORICAL_MODEL_PROVENANCE_INVALID")
                    state["phase"] = "verifying"
                state["headers"] = headers
                if _signature(path) != signature:
                    raise HistoricalEvidenceUnavailable("HISTORICAL_MODEL_PROVENANCE_DRIFT")
            database.execute("DELETE FROM metadata")
            database.execute("INSERT INTO metadata VALUES (?)", (json.dumps(state),))
            database.commit()
            return False
        _verify(path, checksum)
        if _signature(path) != signature:
            raise HistoricalEvidenceUnavailable("HISTORICAL_MODEL_PROVENANCE_DRIFT")
        state["phase"], state["sha256"] = "ready", checksum
        database.execute("DELETE FROM metadata")
        database.execute("INSERT INTO metadata VALUES (?)", (json.dumps(state),))
        database.commit()
    os.replace(building, index)
    return True


def original_neural_evidence(
    artifact_root: Path,
    payload: Mapping[str, object],
    *,
    game_id: str,
    source_sha256: str,
    build: bool = True,
) -> tuple[object, object]:
    from contextlib import closing

    descriptor = payload.get("page_geometry_manifest")
    if not isinstance(descriptor, Mapping):
        raise HistoricalEvidenceUnavailable("HISTORICAL_MODEL_PROVENANCE_MISSING")
    checksum, relative = descriptor.get("checksumSha256"), descriptor.get("relativePath")
    if (
        not isinstance(checksum, str)
        or len(checksum) != 64
        or any(char not in "0123456789abcdef" for char in checksum)
        or not isinstance(relative, str)
        or not relative.startswith("data/")
    ):
        raise HistoricalEvidenceUnavailable("HISTORICAL_MODEL_PROVENANCE_INVALID")
    path = (artifact_root / Path(*PurePosixPath(relative).parts)).resolve()
    if not path.is_relative_to((artifact_root / "data").resolve()):
        raise HistoricalEvidenceUnavailable("HISTORICAL_MODEL_PROVENANCE_INVALID")
    try:
        signature = _signature(path)
        directory = artifact_root / "data" / "historical-grid-acceptance-index"
        directory.mkdir(parents=True, exist_ok=True)
        index = directory / f"{checksum}.sqlite"
        metadata: dict[str, object] | None = None
        if index.exists():
            try:
                with closing(sqlite3.connect(_sqlite_path(index))) as database:
                    metadata = json.loads(
                        database.execute("SELECT value FROM metadata").fetchone()[0]
                    )
            except (sqlite3.DatabaseError, json.JSONDecodeError, TypeError):
                metadata = None
        if (
            metadata is None
            or metadata.get("signature") != signature
            or metadata.get("version") != HISTORICAL_EVIDENCE_INDEX_VERSION
        ):
            if not build:
                raise HistoricalEvidenceUnavailable("HISTORICAL_EVIDENCE_INDEX_UNAVAILABLE")
            if not _prepare_index(path, index, checksum, signature):
                raise HistoricalEvidenceUnavailable("HISTORICAL_EVIDENCE_PREPARING")
            return original_neural_evidence(
                artifact_root, payload, game_id=game_id, source_sha256=source_sha256, build=False
            )
        if metadata.get("sha256") != checksum or metadata.get("phase") != "ready":
            raise HistoricalEvidenceUnavailable("HISTORICAL_MODEL_PROVENANCE_DRIFT")
        headers = metadata["headers"]
        if not isinstance(headers, Mapping) or (
            headers.get("gameId") != game_id
            or headers.get("sourceSelectionId") != str(payload.get("source_selection_id"))
            or headers.get("sourceManifestChecksumSha256") != payload.get("source_manifest_sha256")
        ):
            raise HistoricalEvidenceUnavailable("HISTORICAL_MODEL_PROVENANCE_DRIFT")
        with closing(sqlite3.connect(_sqlite_path(index))) as database:
            row = database.execute(
                "SELECT value FROM entries WHERE checksum = ?", (source_sha256,)
            ).fetchone()
        if row is None:
            raise HistoricalEvidenceUnavailable("HISTORICAL_MODEL_PROVENANCE_MISSING")
        entry = json.loads(row[0])
        if not isinstance(entry, Mapping) or entry.get("status") != "review_required":
            raise HistoricalEvidenceUnavailable("HISTORICAL_MODEL_PROVENANCE_INVALID")
        return entry.get("neuralProposal"), entry.get("neuralProposalBinding")
    except (OSError, UnicodeDecodeError, sqlite3.DatabaseError, json.JSONDecodeError) as error:
        raise HistoricalEvidenceUnavailable("HISTORICAL_MODEL_PROVENANCE_UNREADABLE") from error
