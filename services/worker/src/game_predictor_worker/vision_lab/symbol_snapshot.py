"""Read the existing exporter projection without a database dependency."""

import base64
import hashlib
import io
import json
from typing import Any

from PIL import Image, UnidentifiedImageError

from .annotation_contracts import AnnotationState
from .annotations import digest
from .catalog import Catalog
from .snapshot import VERSION, reject_links, safe_file
from .symbol_contracts import DbCropPreview, DictionaryEntry, DictionaryView, SymbolRow
from .symbol_labels import guard_pixels, holdout_reason, qualify_symbol_sample


class SymbolSnapshot:
    def __init__(self, catalog: Catalog) -> None:
        if catalog.root is None:
            raise ValueError("SYMBOL_SNAPSHOT_REQUIRED")
        self.catalog = catalog
        self.root = catalog.root
        self.manifest = json.loads(safe_file(self.root, "manifest.json").read_bytes())
        self.id = self.manifest["snapshotId"]
        self.manifest_digest = digest(self.manifest)
        self.labels: dict[str, dict[str, Any]] = {}
        self.dictionaries: dict[str, DictionaryView] = {}
        self.availability = "DB_LABELS_UNAVAILABLE"
        if self.manifest.get("format") == VERSION:
            return
        self.availability = "DB_METADATA_AVAILABLE"
        games = sorted({s.game_id for s in catalog.sources.values()})
        projections = self.read_json("approved_labels.json", required=False)
        if projections is None:
            self.availability = "DB_METADATA_UNSUPPORTED"
            return
        if not isinstance(projections, list) or len(projections) > 100000:
            raise ValueError("SYMBOL_SNAPSHOT_INTEGRITY_ERROR")
        for game in games:
            tables = {}
            for name in (
                "symbols",
                "rules_version_symbols",
                "rules_versions",
                "image_symbol_review_cells",
                "recognized_boards",
                "image_board_search_fast_documents",
            ):
                tables[name] = self.read_json(f"records/{game}/{name}.jsonl", required=False)
            if any(value is None for value in tables.values()):
                self.availability = "DB_METADATA_UNSUPPORTED"
                continue
            raw_symbols = tables["symbols"]
            dictionary_digest = digest(
                [tables[n] for n in ("symbols", "rules_version_symbols", "rules_versions")]
            )
            dictionary_error = len(raw_symbols) > 256
            entries = (
                []
                if dictionary_error
                else [
                    DictionaryEntry(
                        id=str(r["id"]),
                        code=str(r["code"]),
                        display_name=str(r.get("name") or r["code"]),
                    )
                    for r in raw_symbols
                ]
            )
            dictionary = DictionaryView(
                origin="db_snapshot",
                game_id=game,
                digest=dictionary_digest,
                status="snapshot",
                entries=entries,
            )
            self.dictionaries[game] = dictionary
            boards = {r["id"]: r for r in tables["recognized_boards"]}
            symbols = {r["id"]: r for r in raw_symbols}
            owners = {r["sequence_number"]: r for r in tables["image_board_search_fast_documents"]}
            for projection in (p for p in projections if p["gameId"] == game):
                sample_id = digest([self.id, projection])
                matches = [
                    r
                    for r in tables["image_symbol_review_cells"]
                    if r["recognized_board_id"] == projection["boardId"]
                    and r["cell_index"] == projection["cellIndex"]
                ]
                if len(matches) != 1 or projection["sourceImageId"] not in catalog.sources:
                    raise ValueError("SYMBOL_SNAPSHOT_INTEGRITY_ERROR")
                cell = matches[0]
                board = boards.get(projection["boardId"])
                if board is None:
                    raise ValueError("SYMBOL_SNAPSHOT_INTEGRITY_ERROR")
                symbol = symbols.get(cell["assigned_symbol_id"])
                owner = owners.get(cell["sequence_number"])
                valid = (
                    cell["game_id"] == game
                    and cell["source_available"] is True
                    and cell["geometry_revision"] == board["geometry_revision"]
                    and cell["review_state"] == "approved"
                    and cell["quality_issue"] is None
                    and cell["approved_crop_sample_id"] == cell["crop_sample_id"]
                    and cell["approved_crop_checksum_sha256"] == cell["crop_checksum_sha256"]
                    and cell["approved_geometry_revision"] == cell["geometry_revision"]
                    and cell["asset_mode"] == "legacy_file"
                    and cell["approved_asset_mode"] in (None, "legacy_file")
                    and cell["crop_relative_path"] is not None
                    and symbol is not None
                    and symbol["game_id"] == game
                    and symbol["status"] == "active"
                    and owner is not None
                    and owner["review_item_id"] == cell["review_item_id"]
                    and owner["recognized_board_id"] == board["id"]
                )
                expected = {
                    "gameId": game,
                    "sourceImageId": board["source_image_id"],
                    "boardId": board["id"],
                    "cellIndex": cell["cell_index"],
                    "geometryRevision": cell["geometry_revision"],
                    "cropSampleId": cell["crop_sample_id"],
                    "cropSha256": cell["crop_checksum_sha256"],
                    "symbolId": cell["assigned_symbol_id"],
                    "reviewRevision": cell["revision"],
                    "reviewedAt": cell["last_reviewed_at"],
                }
                if projection != expected:
                    raise ValueError("SYMBOL_SNAPSHOT_INTEGRITY_ERROR")
                reasons = [] if valid else ["DB_APPROVAL_INVALID"]
                if cell["asset_mode"] != "legacy_file":
                    reasons.append("DB_ASSET_MODE_UNSUPPORTED")
                if dictionary_error:
                    reasons.append("DB_DICTIONARY_UNSUPPORTED")
                relative = (
                    f"assets/{cell['crop_relative_path']}" if cell["crop_relative_path"] else None
                )
                self.labels[sample_id] = {
                    "projection": projection,
                    "relative": relative,
                    "reasons": reasons,
                    "dictionary": dictionary,
                }

    def read_bytes(self, relative: str, limit: int) -> bytes:
        if ":" in relative:
            raise ValueError("SYMBOL_SNAPSHOT_INTEGRITY_ERROR")
        checksum = self.manifest["files"].get(relative)
        if not checksum:
            raise ValueError("SYMBOL_SNAPSHOT_INTEGRITY_ERROR")
        with safe_file(self.root, relative).open("rb") as stream:
            data = stream.read(limit + 1)
        if len(data) > limit or hashlib.sha256(data).hexdigest() != checksum:
            raise ValueError("SYMBOL_SNAPSHOT_INTEGRITY_ERROR")
        return data

    def validate_metadata(self) -> None:
        manifest = json.loads(safe_file(self.root, "manifest.json").read_bytes())
        if manifest != self.manifest:
            raise ValueError("SYMBOL_SNAPSHOT_INTEGRITY_ERROR")
        for relative in self.manifest["files"]:
            if relative.endswith((".json", ".jsonl")):
                self.read_bytes(relative, 64 * 1024 * 1024)

    def read_json(self, relative: str, required: bool = True) -> Any:
        if relative not in self.manifest["files"] and not required:
            return None
        data = self.read_bytes(relative, 64 * 1024 * 1024)
        try:
            result = (
                [json.loads(line) for line in data.splitlines()]
                if relative.endswith(".jsonl")
                else json.loads(data)
            )
        except (ValueError, UnicodeError) as error:
            raise ValueError("SYMBOL_SNAPSHOT_INTEGRITY_ERROR") from error
        if isinstance(result, list) and len(result) > 100000:
            raise ValueError("SYMBOL_SNAPSHOT_INTEGRITY_ERROR")
        return result

    def rows(self, state: AnnotationState, sample_ids: set[str] | None = None) -> list[SymbolRow]:
        rows = []
        for sample_id, label in self.labels.items():
            if sample_ids is not None and sample_id not in sample_ids:
                continue
            p = label["projection"]
            self.verify_source(p["sourceImageId"])
            reasons = list(label["reasons"])
            blocked = holdout_reason(state, self.catalog, p["sourceImageId"])
            if blocked or self.catalog.sources[p["sourceImageId"]].role == "comparison_only":
                reasons.append("SYMBOL_PIXEL_CHECK_DEFERRED")
            elif label["relative"]:
                data = self.read_bytes(label["relative"], 4 * 1024 * 1024)
                if hashlib.sha256(data).hexdigest() != p["cropSha256"]:
                    raise ValueError("SYMBOL_SNAPSHOT_INTEGRITY_ERROR")
            else:
                reasons.append("DB_CROP_MISSING")
            validity = qualify_symbol_sample(reasons, state, self.catalog, p["sourceImageId"])
            rows.append(
                SymbolRow(
                    **validity.model_dump(),
                    sample_id=sample_id,
                    origin="db_approved",
                    game_id=p["gameId"],
                    source_id=p["sourceImageId"],
                    board_id=p["boardId"],
                    cell_index=p["cellIndex"],
                    symbol_id=p["symbolId"],
                    action="approve",
                    metadata=p,
                )
            )
        return rows

    def preview(self, sample_id: str, state: AnnotationState) -> DbCropPreview:
        if sample_id not in self.labels:
            raise KeyError("SYMBOL_SAMPLE_NOT_FOUND")
        label = self.labels[sample_id]
        p = label["projection"]
        guard_pixels(state, self.catalog, p["sourceImageId"])
        self.verify_source(p["sourceImageId"])
        if label["reasons"]:
            raise ValueError(label["reasons"][0])
        data = self.read_bytes(label["relative"], 4 * 1024 * 1024)
        if hashlib.sha256(data).hexdigest() != p["cropSha256"]:
            raise ValueError("SYMBOL_SNAPSHOT_INTEGRITY_ERROR")
        try:
            with Image.open(io.BytesIO(data)) as image:
                media = {"PNG": "image/png", "JPEG": "image/jpeg"}.get(image.format or "")
                image.verify()
        except (OSError, UnidentifiedImageError) as error:
            raise ValueError("DB_CROP_FORMAT_UNSUPPORTED") from error
        if not media:
            raise ValueError("DB_CROP_FORMAT_UNSUPPORTED")
        return DbCropPreview(
            sample_id=sample_id,
            provenance={"snapshot_manifest_id": self.id, **p},
            byte_sha256=p["cropSha256"],
            media_type=media,
            crop_bytes_base64=base64.b64encode(data).decode(),
            dictionary=label["dictionary"],
        )

    def verify_source(self, source_id: str) -> None:
        source = self.catalog.sources[source_id]
        path = self.catalog.paths[source.asset_id]
        reject_links(path)
        try:
            with path.open("rb") as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
        except OSError as error:
            raise ValueError("SYMBOL_SOURCE_INTEGRITY_ERROR") from error
        if actual != source.sha256:
            raise ValueError("SYMBOL_SOURCE_INTEGRITY_ERROR")
