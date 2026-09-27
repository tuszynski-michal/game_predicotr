"""Isolated atomic symbol history with geometry-first locking."""

import base64
import hashlib
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .annotation_contracts import AnnotationState, BackupResult
from .annotations import AnnotationStore, digest, exclusive, read_checked, write_atomic
from .snapshot import canonical, reject_links, safe_file
from .symbol_contracts import (
    CropBinding,
    CropRequest,
    DbCropPreview,
    DbCropRequest,
    DictionaryApprove,
    DictionaryDraft,
    DictionaryPage,
    DictionaryView,
    LabCropPreview,
    LabCropRequest,
    LabelDecide,
    LabelWithdraw,
    SymbolPage,
    SymbolRequest,
    SymbolResult,
    SymbolRow,
)
from .symbol_crops import geometry_for, render_crop, render_spec
from .symbol_labels import holdout_reason, qualify_symbol_sample
from .symbol_snapshot import SymbolSnapshot


def publish_file(path: Path, data: bytes) -> None:
    reject_links(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError("SYMBOL_ARTIFACT_INTEGRITY_ERROR")
        return
    fd, name = tempfile.mkstemp(prefix=".symbol-", dir=path.parent)
    temporary = Path(name)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.link(temporary, path)  # create-only atomic publication, including Windows
    except FileExistsError:
        if path.read_bytes() != data:
            raise ValueError("SYMBOL_ARTIFACT_INTEGRITY_ERROR") from None
    finally:
        temporary.unlink(missing_ok=True)


class SymbolLabelStore:
    def __init__(self, root: Path, annotations: AnnotationStore, protected: tuple[Path, ...] = ()):
        self.annotations = annotations
        self.catalog = annotations.catalog
        self.root = root.absolute()
        self.protected = protected
        reject_links(self.root)
        roots = (annotations.root, self.catalog.root, *protected)
        for other in roots:
            if other is not None:
                reject_links(other)
                a, b = self.root.resolve(), other.resolve()
                if a.is_relative_to(b) or b.is_relative_to(a):
                    raise ValueError("SYMBOL_DIRECTORY_OVERLAP")
        self.snapshot = SymbolSnapshot(self.catalog)

    def empty(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "snapshot_manifest_id": self.snapshot.id,
            "catalog_digest": self.annotations.snapshot_id,
            "revision": 0,
            "dictionaries": [],
            "dictionary_approvals": [],
            "decisions": [],
            "receipts": {},
            "history": [],
        }

    def load(self) -> dict[str, Any]:
        payload = (
            read_checked(self.root / "state.json")
            if (self.root / "state.json").exists()
            else self.empty()
        )
        if payload.keys() != self.empty().keys() or payload["schema_version"] != 1:
            raise ValueError("SYMBOL_STORE_INTEGRITY_ERROR")
        if (
            payload["snapshot_manifest_id"] != self.snapshot.id
            or payload["catalog_digest"] != self.annotations.snapshot_id
        ):
            raise ValueError("SYMBOL_SNAPSHOT_CONFLICT")
        return payload

    @contextmanager
    def locked(
        self, write: bool = False
    ) -> Iterator[tuple[dict[str, Any], AnnotationState, dict[str, Any]]]:
        # Geometry writers also use this lock. Never call AnnotationStore.read here.
        with (
            exclusive(self.annotations.root),
            exclusive(self.root) if write or self.root.exists() else nullcontext(),
        ):
            self.snapshot.validate_metadata()
            geometry = self.annotations._load()
            state = self.annotations._view(AnnotationState.model_validate(geometry["state"]))
            yield self.load(), state, geometry

    def token(self, payload: dict[str, Any], geometry: dict[str, Any], filters: object) -> str:
        return digest(
            [
                "symbols-view-v1",
                payload["revision"],
                geometry,
                self.annotations.snapshot_id,
                self.snapshot.manifest_digest,
                filters,
            ]
        )

    @staticmethod
    def dictionaries(payload: dict[str, Any], game: str | None = None) -> list[DictionaryView]:
        result = []
        approvals = {(a["game_id"], a["version"]): a for a in payload["dictionary_approvals"]}
        for version in payload["dictionaries"]:
            if game is not None and version["game_id"] != game:
                continue
            approval = approvals.get((version["game_id"], version["version"]))
            active = max((v for g, v in approvals if g == version["game_id"]), default=0)
            result.append(
                DictionaryView(
                    game_id=version["game_id"],
                    version=version["version"],
                    digest=version["digest"],
                    entries=version["entries"],
                    status="approved" if approval else "draft",
                    approved_at=approval["decided_at"] if approval else None,
                    active=version["version"] == active,
                )
            )
        return result

    def dictionary(self, game_id: str, version: int) -> DictionaryView:
        with self.locked() as (payload, _, _geometry):
            for value in self.dictionaries(payload, game_id):
                if value.version == version:
                    return value
        raise KeyError("SYMBOL_DICTIONARY_NOT_FOUND")

    @staticmethod
    def validate_page(offset: int, limit: int, supplied: str | None, token: str) -> None:
        if offset < 0 or not 1 <= limit <= 100:
            raise ValueError("SYMBOL_PAGE_INVALID")
        if (offset and supplied is None) or (supplied is not None and supplied != token):
            raise ValueError("PAGE_VIEW_CHANGED")

    def list_dictionaries(
        self,
        game_id: str | None = None,
        offset: int = 0,
        limit: int = 50,
        read_token: str | None = None,
    ) -> DictionaryPage:
        with self.locked() as (payload, _state, geometry):
            token = self.token(payload, geometry, ["dictionaries", game_id])
            self.validate_page(offset, limit, read_token, token)
            values = self.dictionaries(payload, game_id)
            values += [
                d for g, d in self.snapshot.dictionaries.items() if game_id is None or g == game_id
            ]
            values.sort(key=lambda d: (d.game_id, d.origin, d.version or 0))
            items = [
                v.model_copy(update={"entries": None}) for v in values[offset : offset + limit]
            ]
            return DictionaryPage(
                items=items, total=len(values), revision=payload["revision"], read_token=token
            )

    def local_row(
        self, decision: dict[str, Any], payload: dict[str, Any], state: AnnotationState
    ) -> SymbolRow:
        b = CropBinding.model_validate(decision["binding"])
        reasons = []
        if decision["action"] != "approve":
            reasons.append("SYMBOL_NOT_APPROVED")
        current = next(
            d
            for d in reversed(payload["decisions"])
            if (d["binding"]["source_id"], d["binding"]["board_index"], d["binding"]["cell_index"])
            == (b.source_id, b.board_index, b.cell_index)
        )
        if current["decision_id"] != decision["decision_id"]:
            reasons.append("SYMBOL_DECISION_SUPERSEDED")
        dictionary = next((d for d in self.dictionaries(payload, b.game_id) if d.active), None)
        if (
            dictionary is None
            or dictionary.version != decision["dictionary_version"]
            or dictionary.digest != decision["dictionary_digest"]
        ):
            reasons.append("SYMBOL_DICTIONARY_STALE")
        elif decision["symbol_id"] not in {e.id for e in dictionary.entries or []}:
            reasons.append("SYMBOL_CLASS_UNKNOWN")
        try:
            annotation = geometry_for(
                state,
                self.catalog,
                LabCropRequest(
                    kind="lab_cell",
                    source_id=b.source_id,
                    board_index=b.board_index,
                    cell_index=b.cell_index,
                    expected_geometry_revision=b.geometry_revision,
                ),
            )
            if digest(annotation.model_dump()) != b.geometry_digest:
                reasons.append("SYMBOL_GEOMETRY_STALE")
        except ValueError as error:
            reasons.append(str(error))
        if b.render_spec != render_spec() or digest(b.render_spec) != b.render_spec_digest:
            reasons.append("SYMBOL_RENDERER_STALE")
        source = self.catalog.sources[b.source_id]
        source_path = self.catalog.paths[source.asset_id]
        reject_links(source_path)
        with source_path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != b.source_sha256:
                raise ValueError("SYMBOL_SOURCE_INTEGRITY_ERROR")
        if holdout_reason(state, self.catalog, b.source_id) or source.role == "comparison_only":
            reasons.append("SYMBOL_PIXEL_CHECK_DEFERRED")
        else:
            with safe_file(self.root, f"crops/{b.byte_sha256}.png").open("rb") as stream:
                data = stream.read(256 * 1024 + 1)
            if len(data) > 256 * 1024 or hashlib.sha256(data).hexdigest() != b.byte_sha256:
                raise ValueError("SYMBOL_ARTIFACT_INTEGRITY_ERROR")
        validity = qualify_symbol_sample(reasons, state, self.catalog, b.source_id)
        return SymbolRow(
            **validity.model_dump(),
            sample_id=decision["decision_id"],
            origin="lab_human_approved",
            game_id=b.game_id,
            source_id=b.source_id,
            board_id=str(b.board_index),
            cell_index=b.cell_index,
            symbol_id=decision["symbol_id"],
            action=decision["action"],
            metadata=decision,
        )

    def rows(self, payload: dict[str, Any], state: AnnotationState) -> list[SymbolRow]:
        current = {}
        for decision in payload["decisions"]:
            binding = decision["binding"]
            current[(binding["source_id"], binding["board_index"], binding["cell_index"])] = (
                decision
            )
        return [self.local_row(d, payload, state) for d in current.values()] + self.snapshot.rows(
            state
        )

    def list_labels(
        self,
        game_id: str | None = None,
        source_id: str | None = None,
        offset: int = 0,
        limit: int = 50,
        read_token: str | None = None,
    ) -> SymbolPage:
        with self.locked() as (payload, state, geometry):
            token = self.token(payload, geometry, ["labels", game_id, source_id])
            self.validate_page(offset, limit, read_token, token)
            current: dict[tuple[str, int, int], dict[str, Any]] = {}
            for decision in payload["decisions"]:
                b = decision["binding"]
                current[(b["source_id"], b["board_index"], b["cell_index"])] = decision
            descriptors: list[tuple[str, str, int, str, str, dict[str, Any] | None]] = []
            for (sid, board, cell), decision in current.items():
                if (game_id is None or decision["binding"]["game_id"] == game_id) and (
                    source_id is None or sid == source_id
                ):
                    descriptors.append(
                        (
                            sid,
                            str(board),
                            cell,
                            "lab_human_approved",
                            decision["decision_id"],
                            decision,
                        )
                    )
            for sample_id, label in self.snapshot.labels.items():
                p = label["projection"]
                if (game_id is None or p["gameId"] == game_id) and (
                    source_id is None or p["sourceImageId"] == source_id
                ):
                    descriptors.append(
                        (
                            p["sourceImageId"],
                            p["boardId"],
                            p["cellIndex"],
                            "db_approved",
                            sample_id,
                            None,
                        )
                    )
            descriptors.sort(key=lambda d: d[:5])
            selected = descriptors[offset : offset + limit]
            database = {
                row.sample_id: row
                for row in self.snapshot.rows(
                    state, {d[4] for d in selected if d[3] == "db_approved"}
                )
            }
            rows = [
                self.local_row(d[5], payload, state) if d[5] is not None else database[d[4]]
                for d in selected
            ]
            return SymbolPage(
                items=rows,
                total=len(descriptors),
                revision=payload["revision"],
                read_token=token,
                availability=self.snapshot.availability,
            )

    def preview(self, request: CropRequest) -> LabCropPreview | DbCropPreview:
        with self.locked() as (_payload, state, _geometry):
            if isinstance(request, DbCropRequest):
                return self.snapshot.preview(request.sample_id, state)
            binding, data = render_crop(
                state, self.catalog, self.snapshot.id, self.annotations.snapshot_id, request
            )
            return LabCropPreview(binding=binding, png_base64=base64.b64encode(data).decode())

    def mutate(self, request: SymbolRequest) -> SymbolResult:
        with self.locked(write=True) as (payload, state, _geometry):
            fingerprint = digest(request.model_dump())
            if receipt := payload["receipts"].get(request.request_id):
                if receipt["fingerprint"] != fingerprint:
                    raise ValueError("REQUEST_ID_CONFLICT")
                return self.result(
                    payload,
                    state,
                    receipt["result_id"],
                    request.request_id,
                    receipt["revision"],
                    True,
                )
            if request.expected_revision != payload["revision"]:
                raise ValueError("SYMBOL_REVISION_CONFLICT")
            now = datetime.now(UTC).isoformat()
            result_id = fingerprint
            if isinstance(request, DictionaryDraft):
                if request.game_id not in {s.game_id for s in self.catalog.sources.values()}:
                    raise KeyError("SYMBOL_GAME_NOT_FOUND")
                previous = [v for v in payload["dictionaries"] if v["game_id"] == request.game_id]
                latest = max((v["version"] for v in previous), default=None)
                if latest != request.base_version:
                    raise ValueError("DICTIONARY_VERSION_CONFLICT")
                entries = [e.model_dump() for e in request.entries]
                if len({e["id"] for e in entries}) != len(entries) or len(
                    {e["code"] for e in entries}
                ) != len(entries):
                    raise ValueError("DICTIONARY_CLASS_CONFLICT")
                old_entries = [e for v in previous for e in v["entries"]]
                if any(
                    (e["id"] == o["id"]) != (e["code"] == o["code"])
                    for e in entries
                    for o in old_entries
                ):
                    raise ValueError("DICTIONARY_CLASS_CONFLICT")
                version = {
                    "game_id": request.game_id,
                    "version": (latest or 0) + 1,
                    "entries": entries,
                    "actor": request.actor,
                    "created_at": now,
                }
                version["digest"] = digest(version)
                payload["dictionaries"].append(version)
            elif isinstance(request, DictionaryApprove):
                versions = [v for v in payload["dictionaries"] if v["game_id"] == request.game_id]
                latest = max(versions, key=lambda v: v["version"], default=None)
                if (
                    not latest
                    or latest["version"] != request.version
                    or latest["digest"] != request.digest
                ):
                    raise ValueError("DICTIONARY_VERSION_CONFLICT")
                if not latest["entries"] or any(
                    a["game_id"] == request.game_id and a["version"] == request.version
                    for a in payload["dictionary_approvals"]
                ):
                    raise ValueError("DICTIONARY_APPROVAL_INVALID")
                payload["dictionary_approvals"].append(
                    {
                        "game_id": request.game_id,
                        "version": request.version,
                        "dictionary_digest": request.digest,
                        "actor": request.actor,
                        "decided_at": now,
                        "revision": payload["revision"] + 1,
                        "request_id": request.request_id,
                    }
                )
            elif isinstance(request, LabelDecide):
                b = request.binding
                dictionary = next(
                    (d for d in self.dictionaries(payload, b.game_id) if d.active), None
                )
                if (
                    not dictionary
                    or dictionary.version != request.dictionary_version
                    or dictionary.digest != request.dictionary_digest
                ):
                    raise ValueError("SYMBOL_DICTIONARY_STALE")
                if request.action == "approve" and request.symbol_id not in {
                    e.id for e in dictionary.entries or []
                }:
                    raise ValueError("SYMBOL_CLASS_UNKNOWN")
                actual, data = render_crop(
                    state,
                    self.catalog,
                    self.snapshot.id,
                    self.annotations.snapshot_id,
                    LabCropRequest(
                        kind="lab_cell",
                        source_id=b.source_id,
                        board_index=b.board_index,
                        cell_index=b.cell_index,
                        expected_geometry_revision=b.geometry_revision,
                    ),
                )
                if actual != b:
                    raise ValueError("SYMBOL_CROP_CHANGED")
                publish_file(self.root / "crops" / f"{b.byte_sha256}.png", data)
                payload["decisions"].append(
                    {
                        **request.model_dump(exclude={"op", "request_id", "expected_revision"}),
                        "origin": "lab_human_approved",
                        "decision_id": result_id,
                        "revision": payload["revision"] + 1,
                        "decided_at": now,
                    }
                )
            elif isinstance(request, LabelWithdraw):
                old = next(
                    (d for d in payload["decisions"] if d["decision_id"] == request.decision_id),
                    None,
                )
                if old is None:
                    raise KeyError("SYMBOL_DECISION_NOT_FOUND")
                latest = next(
                    d
                    for d in reversed(payload["decisions"])
                    if (
                        d["binding"]["source_id"],
                        d["binding"]["board_index"],
                        d["binding"]["cell_index"],
                    )
                    == (
                        old["binding"]["source_id"],
                        old["binding"]["board_index"],
                        old["binding"]["cell_index"],
                    )
                )
                if latest["decision_id"] != old["decision_id"] or old["action"] == "withdraw":
                    raise ValueError("SYMBOL_DECISION_STALE")
                payload["decisions"].append(
                    {
                        **old,
                        "action": "withdraw",
                        "symbol_id": None,
                        "decision_id": result_id,
                        "revision": payload["revision"] + 1,
                        "decided_at": now,
                    }
                )
            payload["revision"] += 1
            payload["history"].append(
                {"request": request.model_dump(), "result_id": result_id, "decided_at": now}
            )
            payload["receipts"][request.request_id] = {
                "fingerprint": fingerprint,
                "result_id": result_id,
                "revision": payload["revision"],
            }
            if (
                len(
                    {
                        (
                            d["binding"]["source_id"],
                            d["binding"]["board_index"],
                            d["binding"]["cell_index"],
                        )
                        for d in payload["decisions"]
                    }
                )
                > 10000
            ):
                raise ValueError("STORE_LIMIT_REACHED")
            result = self.result(
                payload, state, result_id, request.request_id, payload["revision"], False
            )
            write_atomic(self.root / "state.json", payload)
            return result

    def result(
        self,
        payload: dict[str, Any],
        state: AnnotationState,
        result_id: str,
        request_id: str,
        revision: int,
        replayed: bool,
    ) -> SymbolResult:
        decision = next((d for d in payload["decisions"] if d["decision_id"] == result_id), None)
        validity = self.local_row(decision, payload, state) if decision else None
        return SymbolResult(
            revision=revision,
            request_id=request_id,
            result_id=result_id,
            replayed=replayed,
            **(
                {k: getattr(validity, k) for k in ("label_valid", "reasons", "training_blockers")}
                if validity
                else {}
            ),
        )

    def backup(self) -> BackupResult:
        with self.locked(write=True) as (payload, _state, _geometry):
            backup_id = digest(payload)
            target = self.root / "backups" / backup_id
            self.copy_bundle(payload, self.root, target)
            return BackupResult(backup_id=backup_id, revision=payload["revision"])

    def copy_bundle(self, payload: dict[str, Any], source: Path, target: Path) -> None:
        reject_links(target)
        files = {"state.json": canonical({"payload": payload, "sha256": digest(payload)})}
        for decision in payload["decisions"]:
            checksum = decision["binding"]["byte_sha256"]
            relative = f"crops/{checksum}.png"
            data = safe_file(source, relative).read_bytes()
            if hashlib.sha256(data).hexdigest() != checksum:
                raise ValueError("SYMBOL_ARTIFACT_INTEGRITY_ERROR")
            files[relative] = data
        inventory = {
            "snapshot_manifest_id": self.snapshot.id,
            "manifest_digest": self.snapshot.manifest_digest,
            "snapshot_files": self.snapshot.manifest["files"],
            "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
        }
        files["inventory.json"] = canonical({"payload": inventory, "sha256": digest(inventory)})
        if target.exists():
            if {
                p.relative_to(target).as_posix()
                for p in target.rglob("*")
                if p.is_file() and p.name != ".lock"
            } != set(files):
                raise ValueError("SYMBOL_BACKUP_CONFLICT")
            for name, data in files.items():
                if safe_file(target, name).read_bytes() != data:
                    raise ValueError("SYMBOL_BACKUP_CONFLICT")
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".symbol-bundle-", dir=target.parent))
        for name, data in files.items():
            publish_file(stage / name, data)
        stage.rename(target)

    def restore(self, backup_id: str, destination: Path) -> "SymbolLabelStore":
        if len(backup_id) != 64 or any(c not in "0123456789abcdef" for c in backup_id):
            raise ValueError("SYMBOL_BACKUP_INVALID")
        restored = SymbolLabelStore(destination, self.annotations, (self.root, *self.protected))
        with self.locked() as (_payload, _state, _geometry):
            source = safe_file(self.root, f"backups/{backup_id}")
            payload = read_checked(source / "state.json")
            inventory = read_checked(source / "inventory.json")
            if (
                digest(payload) != backup_id
                or inventory["snapshot_manifest_id"] != self.snapshot.id
                or inventory["manifest_digest"] != self.snapshot.manifest_digest
            ):
                raise ValueError("SYMBOL_BACKUP_CONFLICT")
            for name, checksum in inventory["files"].items():
                if hashlib.sha256(safe_file(source, name).read_bytes()).hexdigest() != checksum:
                    raise ValueError("SYMBOL_ARTIFACT_INTEGRITY_ERROR")
            self.copy_bundle(payload, source, destination)
        return restored
