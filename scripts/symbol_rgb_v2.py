"""RGB v2 band index and preview for pending symbol cells (TASK-0870).

Run from the repository root with ``python -m scripts.symbol_rgb_v2``. Every command
reads the database in a READ ONLY transaction and writes only below its output
directory; nothing here changes predictions or approves a cell. Commands are
resumable: exit code 3 means "run the same command again".

* ``index`` exports, per symbol and id-hash shard, every eligible pending cell with
  its current confidence and source and its original model confidence (for cells
  rewritten by the reference library, the confidence of the latest model revision).
* ``preview`` takes one (symbol, band, shard) scope from the index, renders the
  checksum-bound crops, chooses the symbol with RGB v2 (frozen CNN, confirmed by the
  frozen library consensus) and writes rows, a report, an HTML sample and the apply
  manifest of the cells whose symbol or confirmed/tentative status changes.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import numpy as np
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.prediction_revisions import PREDICTIONS_DIGEST_VERSION
from game_predictor_api.storage.database import (
    create_maintenance_database_engine,
    create_session_factory,
)
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_worker.symbols import rgb_v2
from game_predictor_worker.symbols.audit_rgb_classifier import AuditRgbClassifier
from game_predictor_worker.symbols.reference_library import (
    combined_descriptor,
    decide,
    descriptor_matrix,
    normalize_rows,
    vote_batch,
)
from game_predictor_worker.symbols.reference_library_writer import (
    MODEL_VERSION as LIBRARY_MODEL_VERSION,
)
from game_predictor_worker.symbols.reference_library_writer import (
    TARGET_QUALITY_CHANGED,
    BoardPlan,
    ReferenceLibraryWriteError,
    RgbTarget,
    TargetCell,
    apply_board,
    predictions_digest,
    revert_board,
    revert_checksum,
    rgb_v2_policy,
)
from game_predictor_worker.symbols.rgb_v2 import (
    BANDS,
    ENTRY_KEY,
    MODEL_VERSION,
    CurrentPrediction,
    band_of,
    current_status,
    decide_rgb,
    needs_write,
)
from numpy.typing import NDArray
from sqlalchemy import Connection, text
from sqlalchemy.exc import DBAPIError

from scripts import evaluate_symbol_reference_library as reference

EXIT_INCOMPLETE = 3
INDEX_FORMAT = "symbol-rgb-v2-index-v1"
PREVIEW_FORMAT = "symbol-rgb-v2-preview-v1"
MANIFEST_FORMAT = "symbol-rgb-v2-apply-manifest-v1"
SYMBOLS = ("ARBUZ", "CYTRYNA", "GWIAZDA", "POMARANCZ", "SIEDEM", "SLIWKA", "WINOGRON", "WISNIA")
ROWS_CHUNK = 2000
ID_BATCH = 1000

# Same eligibility as the reference-library preview, plus the model assignment the
# writer requires; the shard splits one symbol by a stable hash of the cell id.
_ELIGIBLE = """
  c.game_id = :game_id
  AND c.review_state = 'pending'
  AND c.assignment_source = 'model'
  AND c.asset_mode = 'virtual_source'
  AND c.source_available = true
  AND c.quality_issue IS NULL
  AND (c.source_visibility IS NULL OR c.source_visibility = 'full')
  AND c.render_spec_checksum_sha256 IS NOT NULL
"""
_SHARD = "mod(('x' || left(md5(c.id::text), 7))::bit(28)::int, :shard_count) = :shard_index"
_ENTRY_PATH = "$[*] ? (@.rowIndex == $r && @.columnIndex == $c)"

_INDEX_SQL = f"""
SELECT c.id::text AS id,
       c.prediction_confidence AS confidence,
       CASE WHEN e.entry ? '{ENTRY_KEY}' THEN 'rgb_v2'
            WHEN e.entry ? 'referenceLibrary' THEN 'reference_library'
            ELSE 'model' END AS source,
       CASE WHEN e.entry ? '{ENTRY_KEY}'
              THEN (e.entry -> '{ENTRY_KEY}' ->> 'originalModelConfidence')::float8
            WHEN e.entry ? 'referenceLibrary' THEN o.confidence
            ELSE c.prediction_confidence END AS original_confidence
FROM game_data_v2.image_symbol_review_cells c
JOIN game_data_v2.image_symbol_prediction_revisions r
  ON r.game_id = c.game_id AND r.id = c.prediction_revision_id
CROSS JOIN LATERAL (
  SELECT jsonb_path_query_first(
           r.predictions, '{_ENTRY_PATH}',
           jsonb_build_object('r', c.row_index, 'c', c.column_index)) AS entry
) e
LEFT JOIN LATERAL (
  SELECT (jsonb_path_query_first(
            m.predictions, '{_ENTRY_PATH}',
            jsonb_build_object('r', c.row_index, 'c', c.column_index)) ->> 'confidence'
         )::float8 AS confidence
  FROM game_data_v2.image_symbol_prediction_revisions m
  -- Outer-only qualification first: PostgreSQL turns it into a one-time filter, so
  -- cells without a library entry skip the revision scan.
  WHERE e.entry ? 'referenceLibrary'
    AND NOT e.entry ? '{ENTRY_KEY}'
    AND m.game_id = c.game_id
    AND m.review_item_id = c.review_item_id
    AND m.model_version NOT IN ('{LIBRARY_MODEL_VERSION}', '{MODEL_VERSION}')
    AND m.created_at <= r.created_at
  ORDER BY m.created_at DESC, m.id DESC
  LIMIT 1
) o ON true
WHERE {_ELIGIBLE}
  AND c.prediction_symbol_code = :symbol
  AND {_SHARD}
ORDER BY c.id
"""

_CELLS_SQL = f"""
SELECT {reference._CELL_COLUMNS}, NULL::text AS label
FROM game_data_v2.image_symbol_review_cells c
WHERE {_ELIGIBLE}
  AND c.id = ANY(CAST(:ids AS uuid[]))
ORDER BY c.id
"""

_STATE_SQL = """
SELECT c.id::text AS id, c.review_item_id::text AS review_item_id,
       c.recognized_board_id::text AS recognized_board_id,
       c.prediction_revision_id::text AS prediction_revision_id,
       c.cell_index, c.review_state, c.assignment_source, c.quality_issue,
       c.prediction_symbol_code, c.prediction_confidence,
       c.rendered_pixel_checksum_sha256
FROM game_data_v2.image_symbol_review_cells c
WHERE c.game_id = :game_id AND c.id = ANY(CAST(:ids AS uuid[]))
"""

_LATEST_SQL = """
SELECT DISTINCT ON (p.review_item_id)
       p.review_item_id::text AS review_item_id, p.id::text AS id, p.predictions
FROM game_data_v2.image_symbol_prediction_revisions p
WHERE p.game_id = :game_id AND p.review_item_id = ANY(CAST(:ids AS uuid[]))
ORDER BY p.review_item_id, p.created_at DESC, p.id DESC
"""


class RgbError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def shard_of(cell_id: str, count: int) -> int:
    """Python twin of ``_SHARD``: the first 28 bits of md5(id) modulo ``count``."""

    return int(hashlib.md5(cell_id.encode()).hexdigest()[:7], 16) % count


def _shard(value: str) -> tuple[int, int]:
    index_text, separator, count_text = value.partition("/")
    try:
        index, count = int(index_text), int(count_text)
    except ValueError:
        index, count = -1, 0
    if separator != "/" or not 0 <= index < count:
        raise argparse.ArgumentTypeError(f"invalid shard {value!r}; expected INDEX/COUNT")
    return index, count


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _chunks(values: Sequence[str], size: int) -> list[list[str]]:
    return [list(values[start : start + size]) for start in range(0, len(values), size)]


# ---------------------------------------------------------------- index


def _index_path(output: Path, symbol: str, shard: int, count: int) -> Path:
    return output / symbol / f"shard-{shard:03d}-of-{count:03d}.json"


def index_rows_to_summary(rows: Sequence[Sequence[Any]]) -> dict[str, dict[str, int]]:
    """Counts per band and current source; rows without an original confidence are 'unknown'."""

    summary: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for _, _, source, original in rows:
        band = "unknown" if original is None else band_of(float(original))
        summary[band][str(source)] += 1
    return {band: dict(sorted(counts.items())) for band, counts in sorted(summary.items())}


def run_index(arguments: argparse.Namespace) -> int:
    deadline = time.monotonic() + float(arguments.time_budget_seconds)
    output = cast(Path, arguments.output_dir).resolve()
    count = int(arguments.shards)
    symbols = [arguments.symbol] if arguments.symbol else list(SYMBOLS)
    engine = create_maintenance_database_engine(ApiSettings.from_environment())
    done = 0
    try:
        with engine.connect().execution_options(postgresql_readonly=True) as connection:
            game_id, _ = reference._game(connection, arguments.game_code)
            connection.execute(text("SET statement_timeout = '115s'"))
            for symbol in symbols:
                for shard in range(count):
                    path = _index_path(output, symbol, shard, count)
                    if path.is_file():
                        continue
                    if done and time.monotonic() >= deadline:
                        print(f"INCOMPLETE: stopped before {symbol} shard {shard}.")
                        return EXIT_INCOMPLETE
                    started = time.monotonic()
                    rows = [
                        [row["id"], row["confidence"], row["source"], row["original_confidence"]]
                        for row in connection.execute(
                            text(_INDEX_SQL),
                            {
                                "game_id": game_id,
                                "symbol": symbol,
                                "shard_index": shard,
                                "shard_count": count,
                            },
                        ).mappings()
                    ]
                    path.parent.mkdir(parents=True, exist_ok=True)
                    reference._write_json(
                        path,
                        {
                            "format": INDEX_FORMAT,
                            "gameId": game_id,
                            "symbol": symbol,
                            "shard": f"{shard}/{count}",
                            "columns": ["id", "confidence", "source", "originalConfidence"],
                            "rows": rows,
                        },
                    )
                    done += 1
                    print(
                        f"{symbol} {shard}/{count}: {len(rows)} cells "
                        f"in {time.monotonic() - started:.1f}s"
                    )
    finally:
        engine.dispose()
    summary = {
        symbol: index_rows_to_summary(_load_index(output, symbol, count))
        for symbol in SYMBOLS
        if all(_index_path(output, symbol, k, count).is_file() for k in range(count))
    }
    reference._write_json(output / "summary.json", {"shards": count, "symbols": summary})
    print(json.dumps(summary, indent=1))
    return 0


def _load_index(output: Path, symbol: str, count: int) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for shard in range(count):
        document = json.loads(_index_path(output, symbol, shard, count).read_bytes())
        if document.get("format") != INDEX_FORMAT or document.get("symbol") != symbol:
            raise RgbError("SYMBOL_RGB_INDEX_INVALID", f"Unexpected index file for {symbol}.")
        rows.extend(document["rows"])
    return rows


# ---------------------------------------------------------------- preview


def select_scope(
    rows: Sequence[Sequence[Any]], band: str, shard: tuple[int, int]
) -> list[dict[str, Any]]:
    """Index rows of one band and id-hash shard, ordered by cell id."""

    index, count = shard
    selected = []
    for cell_id, confidence, source, original in rows:
        if original is None or band_of(float(original)) != band:
            continue
        if count > 1 and shard_of(str(cell_id), count) != index:
            continue
        selected.append(
            {
                "id": str(cell_id),
                "confidence": float(confidence),
                "source": str(source),
                "originalConfidence": float(original),
            }
        )
    return sorted(selected, key=lambda row: row["id"])


def _frozen_library(
    directory: Path,
) -> tuple[
    reference.ActiveModel,
    NDArray[np.int64],
    NDArray[np.float32],
    NDArray[np.float32],
    dict[str, str],
]:
    metadata_path = directory / "library.json"
    arrays_path = directory / "library.npz"
    metadata = json.loads(metadata_path.read_bytes())
    arrays_sha = _sha256(arrays_path)
    if arrays_sha != metadata["arraysSha256"]:
        raise RgbError("SYMBOL_RGB_LIBRARY_CHANGED", "The frozen library arrays differ.")
    model = reference.ActiveModel(
        metadata["iterationId"],
        Path(metadata["checkpointPath"]),
        metadata["checkpointSha256"],
        tuple(metadata["classCodes"]),
    )
    with np.load(arrays_path, allow_pickle=False) as archive:
        labels, shape, combined = archive["labels"], archive["shape"], archive["combined"]
    identity = {
        "libraryMetadataSha256": _sha256(metadata_path),
        "libraryArraysSha256": arrays_sha,
        "checkpointSha256": model.checkpoint_sha256,
    }
    return model, labels, shape, combined, identity


def rgb_rows(
    crops: NDArray[np.uint8],
    classifier: AuditRgbClassifier,
    library: tuple[NDArray[np.int64], NDArray[np.float32], NDArray[np.float32]],
) -> list[dict[str, Any]]:
    """The audit decision of ``recognize_grid_audit_symbols`` for a batch of crops."""

    labels, reference_shape, reference_combined = library
    codes = classifier.class_codes
    candidates = classifier.candidates(crops)
    shape, hue = descriptor_matrix(list(crops))
    combined = normalize_rows(combined_descriptor(shape, classifier.reference_features(crops), hue))
    proposals = [
        decide(shape_vote, combined_vote)
        for shape_vote, combined_vote in zip(
            vote_batch(shape, reference_shape, labels, class_count=len(codes)),
            vote_batch(combined, reference_combined, labels, class_count=len(codes)),
            strict=True,
        )
    ]
    result = []
    for candidate, proposal in zip(candidates, proposals, strict=True):
        decision = decide_rgb(codes, int(candidate), proposal.class_index)
        result.append(
            {
                "symbol": decision.symbol_code,
                "status": decision.status,
                "cnnSymbol": decision.cnn_symbol_code,
                "librarySymbol": decision.library_symbol_code,
                "shapeVotes": proposal.shape_vote.agreeing_count,
                "combinedVotes": proposal.combined_vote.agreeing_count,
            }
        )
    return result


def _read_cells(connection: Connection, game_id: str, ids: Sequence[str]) -> list[reference.Cell]:
    rows: list[Mapping[str, Any]] = []
    for chunk in _chunks(ids, ID_BATCH):
        rows.extend(
            dict(row)
            for row in connection.execute(
                text(_CELLS_SQL), {"game_id": game_id, "ids": chunk}
            ).mappings()
        )
    return [reference._cell(row) for row in reference._with_render_specs(connection, game_id, rows)]


def _sample(groups: Mapping[str, list[str]], per_group: int) -> dict[str, list[str]]:
    # Deterministic: the md5 order of the ids, independent of input order.
    return {
        key: sorted(members, key=lambda i: hashlib.md5(i.encode()).hexdigest())[:per_group]
        for key, members in groups.items()
    }


def run_preview(arguments: argparse.Namespace) -> int:
    deadline = time.monotonic() + float(arguments.time_budget_seconds)
    settings = ApiSettings.from_environment()
    artifact_root = (arguments.artifact_root or settings.artifact_root).resolve()
    output = cast(Path, arguments.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    index_dir = cast(Path, arguments.index_dir).resolve()
    symbol, band = str(arguments.symbol), str(arguments.band)
    if band not in {label for label, _, _ in BANDS}:
        raise RgbError("SYMBOL_RGB_BAND_UNKNOWN", f"Unknown band {band}.")
    model, labels, ref_shape, ref_combined, identity = _frozen_library(
        cast(Path, arguments.library_dir).resolve()
    )

    scope_path = output / "scope.json"
    if scope_path.is_file():
        scope = json.loads(scope_path.read_bytes())
    else:
        index_summary = json.loads((index_dir / "summary.json").read_bytes())
        count = int(index_summary["shards"])
        selected = select_scope(_load_index(index_dir, symbol, count), band, arguments.shard)
        if not selected:
            raise RgbError("SYMBOL_RGB_SCOPE_EMPTY", "No index row matches the scope.")
        scope = {
            "format": PREVIEW_FORMAT,
            "symbol": symbol,
            "band": band,
            "shard": f"{arguments.shard[0]}/{arguments.shard[1]}",
            "indexShards": count,
            "indexSha256": {
                str(k): _sha256(_index_path(index_dir, symbol, k, count)) for k in range(count)
            },
            "rows": selected,
        }
        reference._write_json(scope_path, scope)
    by_id = {row["id"]: row for row in scope["rows"]}

    engine = create_maintenance_database_engine(settings)
    try:
        with engine.connect().execution_options(
            isolation_level="REPEATABLE READ", postgresql_readonly=True
        ) as connection:
            game_id, game_name = reference._game(connection, arguments.game_code)
            fingerprint = reference._cell_state_fingerprint(connection, game_id)
            cells = _read_cells(connection, game_id, sorted(by_id))
    finally:
        engine.dispose()
    cache, remaining = reference._render(
        cells,
        artifact_root=artifact_root,
        cache_path=output / "preview-crops.npz",
        deadline=deadline,
        context_size=0,
    )
    if remaining:
        print(f"INCOMPLETE: {remaining} of {len(cells)} crops still to render.")
        return EXIT_INCOMPLETE
    usable, unusable = reference._usable(cells, cache)

    classifier = AuditRgbClassifier(
        model.checkpoint_path, model.checkpoint_sha256, model.class_codes
    )
    rows_key = reference.digest_json(
        {
            "format": PREVIEW_FORMAT,
            "identity": identity,
            "cells": [reference._cache_key(cell) for cell in usable],
        }
    )
    rows_path, partial_path = output / "rows.json", output / "rows-partial.json"
    rows = reference._cached_preview_rows(rows_path, rows_key)
    if rows is None:
        partial = reference._partial_preview_rows(partial_path, rows_key)
        done = {row["cellReviewId"] for row in partial}
        todo = [cell for cell in usable if cell.id not in done]
        for start in range(0, len(todo), ROWS_CHUNK):
            if start and time.monotonic() >= deadline:
                break
            chunk = todo[start : start + ROWS_CHUNK]
            crops = np.stack([cache[reference._cache_key(cell)]["crop"] for cell in chunk])
            for cell, result in zip(
                chunk, rgb_rows(crops, classifier, (labels, ref_shape, ref_combined)), strict=True
            ):
                indexed = by_id[cell.id]
                current = CurrentPrediction(
                    symbol_code=str(cell.prediction_symbol_code),
                    confidence=float(cell.prediction_confidence or 0.0),
                    source=indexed["source"],
                    original_confidence=indexed["originalConfidence"],
                )
                decision = decide_rgb(
                    model.class_codes,
                    model.class_codes.index(result["cnnSymbol"]),
                    None
                    if result["librarySymbol"] is None
                    else model.class_codes.index(result["librarySymbol"]),
                )
                partial.append(
                    {
                        "cellReviewId": cell.id,
                        "renderedPixelChecksumSha256": cell.rendered_pixel_checksum_sha256,
                        "currentSymbol": current.symbol_code,
                        "currentConfidence": current.confidence,
                        "currentStatus": current_status(current.confidence),
                        "currentSource": current.source,
                        "originalConfidence": current.original_confidence,
                        **result,
                        "write": needs_write(current, decision),
                    }
                )
            reference._write_rows_cache(partial_path, rows_key, partial, complete=False)
        if len(partial) < len(usable):
            print(f"INCOMPLETE: {len(usable) - len(partial)} of {len(usable)} proposals left.")
            return EXIT_INCOMPLETE
        rows = sorted(partial, key=lambda row: str(row["cellReviewId"]))
        reference._write_rows_cache(rows_path, rows_key, rows, complete=True)
        partial_path.unlink(missing_ok=True)

    groups: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        if row["write"]:
            groups[f"{row['currentSymbol']}->{row['symbol']}:{row['status']}"].append(
                str(row["cellReviewId"])
            )
    sample = _sample(groups, int(arguments.thumbnails_per_group))
    sampled = {cell_id for members in sample.values() for cell_id in members}
    by_cell = {cell.id: cell for cell in usable}
    context_cache, context_left = reference._render(
        [by_cell[cell_id] for cell_id in sorted(sampled)],
        artifact_root=artifact_root,
        cache_path=output / "preview-context.npz",
        deadline=deadline,
        context_size=reference.PREVIEW_CONTEXT_SIZE,
    )
    if context_left:
        print(f"INCOMPLETE: {context_left} sample thumbnails still to render.")
        return EXIT_INCOMPLETE

    report = {
        "format": PREVIEW_FORMAT,
        "game": {"id": game_id, "code": arguments.game_code, "name": game_name},
        "policy": {"modelVersion": MODEL_VERSION, **identity},
        "scope": {k: scope[k] for k in ("symbol", "band", "shard", "indexShards", "indexSha256")},
        "cellStateFingerprint": fingerprint,
        "cells": len(rows),
        "unusable": unusable,
        "notEligibleAnyMore": len(by_id) - len(cells),
        "status": dict(Counter(str(row["status"]) for row in rows)),
        "writes": sum(1 for row in rows if row["write"]),
        "groups": {key: len(members) for key, members in sorted(groups.items())},
        "rowsSha256": _sha256(rows_path),
    }
    report_sha = reference._write_json(output / "report.json", report)
    (output / "preview.html").write_text(
        _preview_html(report, rows, sample, context_cache, by_cell), encoding="utf-8"
    )
    print(json.dumps({k: report[k] for k in ("cells", "status", "writes", "groups")}))
    print(f"report.json sha256={report_sha}")
    return 0


def run_manifest(arguments: argparse.Namespace) -> int:
    """Build the apply manifest of an approved preview from the current cell state.

    The preview fixes the decisions the operator approved; the manifest binds them to
    the boards' current revisions right before the write, because writing one symbol
    gives every shared board a new revision.
    """

    output = cast(Path, arguments.output_dir).resolve()
    report_path, rows_path = output / "report.json", output / "rows.json"
    report = json.loads(report_path.read_bytes())
    if report.get("format") != PREVIEW_FORMAT or _sha256(rows_path) != report["rowsSha256"]:
        raise RgbError("SYMBOL_RGB_PREVIEW_CHANGED", "The preview rows differ from the report.")
    rows = json.loads(rows_path.read_bytes())["rows"]
    manifest_sha = _write_manifest(output, report, _sha256(report_path), rows)
    print(f"apply-manifest.json sha256={manifest_sha}")
    return 0


def _preview_html(
    report: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    sample: Mapping[str, list[str]],
    context_cache: Mapping[str, Mapping[str, Any]],
    by_cell: Mapping[str, reference.Cell],
) -> str:
    row_by_id = {str(row["cellReviewId"]): row for row in rows}
    sections = []
    for key in sorted(sample, key=lambda k: -cast(int, report["groups"][k])):
        cards = []
        for cell_id in sample[key]:
            entry = context_cache[reference._cache_key(by_cell[cell_id])]
            row = row_by_id[cell_id]
            crop = reference._crop_uri(entry["crop"], 96)
            context = reference._context_uri(entry["context"], entry["context_quad"])
            votes = f"{row['shapeVotes']}/{row['combinedVotes']}"
            cards.append(
                "<figure><div class=pair>"
                f'<img src="{crop}" width=96 height=96 alt="">'
                f'<img src="{context}" width=144 height=144 alt=""></div><figcaption>'
                f"model {row['originalConfidence']:.4f} · obecnie {row['currentConfidence']:.2f}"
                f" ({html.escape(str(row['currentSource']))})<br>"
                f"CNN {html.escape(str(row['cnnSymbol']))} · biblioteka "
                f"{html.escape(str(row['librarySymbol']))} {votes}"
                f"<br><code>{cell_id[:8]}</code></figcaption></figure>"
            )
        current, _, rest = key.partition("->")
        new, _, status = rest.partition(":")
        label = "pewna" if status == "confirmed" else "do przeglądu"
        title = f"{html.escape(current)} → {html.escape(new)} ({label})"
        sections.append(
            f"<details open><summary>{title} <b>{report['groups'][key]}</b></summary>"
            f"<div class=grid>{''.join(cards)}</div></details>"
        )
    scope = report["scope"]
    name = f"{html.escape(scope['symbol'])}, pasmo {html.escape(scope['band'])}"
    statuses = html.escape(json.dumps(report["status"]))
    largest = max((len(v) for v in sample.values()), default=0)
    return (
        "<!doctype html><html lang=pl><head><meta charset=utf-8>"
        '<meta name=viewport content="width=device-width, initial-scale=1">'
        f"<title>RGB v2 {name}</title><style>{_PAGE_CSS}</style></head><body>"
        f"<h1>RGB v2: {name} (część {html.escape(scope['shard'])})</h1>"
        f"<p>{report['cells']} komórek; do zapisu {report['writes']}; statusy {statuses}."
        f" Próbka do {largest} na grupę.</p>{''.join(sections)}</body></html>"
    )


_PAGE_CSS = (
    ":root{--bg:#fafaf9;--fg:#1c1917;--muted:#78716c;--card:#fff;--line:#e7e5e4}"
    "@media (prefers-color-scheme: dark){:root{--bg:#1c1917;--fg:#f5f5f4;"
    "--muted:#a8a29e;--card:#292524;--line:#44403c}}"
    "body{margin:0;padding:16px;background:var(--bg);color:var(--fg);"
    "font:14px/1.4 system-ui,sans-serif}"
    "summary{font-size:16px;font-weight:600;cursor:pointer;padding:8px 0}"
    ".grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:8px}"
    "figure{margin:0;padding:8px;background:var(--card);border:1px solid var(--line);"
    "border-radius:6px}"
    ".pair{display:flex;gap:8px} .pair img{image-rendering:pixelated;border-radius:3px}"
    "figcaption{font-size:12px;color:var(--muted);margin-top:6px} p{color:var(--muted)}"
)


def _write_manifest(
    output: Path, report: Mapping[str, Any], report_sha: str, rows: Sequence[Mapping[str, Any]]
) -> str:
    targets = {str(row["cellReviewId"]): row for row in rows if row["write"]}
    game_id = str(report["game"]["id"])
    engine = create_maintenance_database_engine(ApiSettings.from_environment())
    cells: dict[str, Mapping[str, Any]] = {}
    latest: dict[str, Mapping[str, Any]] = {}
    try:
        with engine.connect().execution_options(
            isolation_level="REPEATABLE READ", postgresql_readonly=True
        ) as connection:
            fingerprint = reference._cell_state_fingerprint(connection, game_id)
            for chunk in _chunks(sorted(targets), ID_BATCH):
                for row in connection.execute(
                    text(_STATE_SQL), {"game_id": game_id, "ids": chunk}
                ).mappings():
                    cells[str(row["id"])] = dict(row)
            items = sorted({str(cell["review_item_id"]) for cell in cells.values()})
            for chunk in _chunks(items, ID_BATCH):
                for row in connection.execute(
                    text(_LATEST_SQL), {"game_id": game_id, "ids": chunk}
                ).mappings():
                    latest[str(row["review_item_id"])] = dict(row)
    finally:
        engine.dispose()
    # No fingerprint gate: other symbols of the band are written in between. Each target
    # is re-checked against its preview row below and again by the writer under lock.
    boards, excluded, moves = build_boards(targets, cells, latest)
    revision_checksum = reference.digest_json(
        {"policy": report["policy"], "scope": report["scope"]}
    )
    manifest = {
        "format": MANIFEST_FORMAT,
        "predictionsDigestVersion": PREDICTIONS_DIGEST_VERSION,
        "writerModelVersion": MODEL_VERSION,
        "revisionChecksumSha256": revision_checksum,
        "game": report["game"],
        "policy": report["policy"],
        "scope": report["scope"],
        "reportSha256": report_sha,
        "cellStateFingerprint": fingerprint,
        "targets": sum(len(board["targets"]) for board in boards),
        "moves": dict(sorted(moves.items())),
        "excluded": dict(sorted(excluded.items())),
        "boards": boards,
    }
    return reference._write_json(output / "apply-manifest.json", manifest)


def build_boards(
    targets: Mapping[str, Mapping[str, Any]],
    cells: Mapping[str, Mapping[str, Any]],
    latest: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], Counter[str], Counter[str]]:
    """Group the write targets by board; a cell that moved since the preview is excluded."""

    excluded: Counter[str] = Counter()
    moves: Counter[str] = Counter()
    boards: dict[str, dict[str, Any]] = {}
    for cell_id, row in sorted(targets.items()):
        cell = cells.get(cell_id)
        revision = None if cell is None else latest.get(str(cell["review_item_id"]))
        if cell is None:
            excluded["cell_missing"] += 1
        elif cell["review_state"] != "pending":
            excluded["not_pending"] += 1
        elif cell["assignment_source"] != "model":
            excluded["assignment_not_model"] += 1
        elif cell["quality_issue"] is not None:
            excluded["quality_issue"] += 1
        elif revision is None or revision["id"] != cell["prediction_revision_id"]:
            excluded["revision_not_current"] += 1
        elif cell["rendered_pixel_checksum_sha256"] != row["renderedPixelChecksumSha256"]:
            excluded["pixels_changed"] += 1
        elif cell["prediction_symbol_code"] != row["currentSymbol"] or float(
            cell["prediction_confidence"] or 0.0
        ) != float(row["currentConfidence"]):
            excluded["prediction_changed"] += 1
        else:
            item_id = str(cell["review_item_id"])
            board = boards.setdefault(
                item_id,
                {
                    "reviewItemId": item_id,
                    "recognizedBoardId": str(cell["recognized_board_id"]),
                    "predictionRevisionId": str(revision["id"]),
                    "predictionsSha256": predictions_digest(revision["predictions"]),
                    "targets": [],
                },
            )
            board["targets"].append(
                {
                    "cellReviewId": cell_id,
                    "cellIndex": int(cell["cell_index"]),
                    "renderedPixelChecksumSha256": row["renderedPixelChecksumSha256"],
                    "oldSymbol": row["currentSymbol"],
                    "oldConfidence": row["currentConfidence"],
                    "oldSource": row["currentSource"],
                    "originalModelConfidence": row["originalConfidence"],
                    "newSymbol": row["symbol"],
                    "status": row["status"],
                    "cnnSymbol": row["cnnSymbol"],
                    "librarySymbol": row["librarySymbol"],
                    "shapeVotes": row["shapeVotes"],
                    "combinedVotes": row["combinedVotes"],
                }
            )
            moves[f"{row['currentSymbol']}->{row['symbol']}:{row['status']}"] += 1
    return [boards[key] for key in sorted(boards)], excluded, moves


# ---------------------------------------------------------------- apply

# Rolled back by the writer; the board is recorded as stale and the run goes on.
# A non-target side effect is a stale cell row outside the run (e.g. outdated
# visibility), not an inconsistency of the written board (plan, D-520).
SKIPPABLE = frozenset({TARGET_QUALITY_CHANGED, "SYMBOL_REFERENCE_WRITE_SIDE_EFFECT"})


def read_manifest(path: Path, expected_sha256: str) -> dict[str, Any]:
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != expected_sha256:
        raise RgbError("SYMBOL_RGB_MANIFEST_MISMATCH", "The manifest differs from its checksum.")
    manifest: Any = json.loads(content)
    if (
        not isinstance(manifest, Mapping)
        or manifest.get("format") != MANIFEST_FORMAT
        or manifest.get("writerModelVersion") != MODEL_VERSION
    ):
        raise RgbError("SYMBOL_RGB_MANIFEST_INVALID", "Unknown manifest.")
    return dict(manifest)


def manifest_policy(manifest: Mapping[str, Any]) -> Any:
    policy = manifest["policy"]
    return rgb_v2_policy(
        {
            "checkpointSha256": str(policy["checkpointSha256"]),
            "libraryArraysSha256": str(policy["libraryArraysSha256"]),
            "libraryMetadataSha256": str(policy["libraryMetadataSha256"]),
            "runChecksumSha256": str(manifest["revisionChecksumSha256"]),
        }
    )


def board_plan(board: Mapping[str, Any]) -> BoardPlan:
    return BoardPlan(
        review_item_id=UUID(str(board["reviewItemId"])),
        recognized_board_id=UUID(str(board["recognizedBoardId"])),
        prediction_revision_id=UUID(str(board["predictionRevisionId"])),
        predictions_sha256=str(board["predictionsSha256"]),
        targets=tuple(
            TargetCell(
                cell_review_id=UUID(str(target["cellReviewId"])),
                cell_index=int(target["cellIndex"]),
                rendered_pixel_checksum_sha256=str(target["renderedPixelChecksumSha256"]),
                old_symbol=str(target["oldSymbol"]),
                new_symbol=str(target["newSymbol"]),
                shape_votes=int(target["shapeVotes"]),
                combined_votes=int(target["combinedVotes"]),
                rgb=RgbTarget(
                    status=target["status"],
                    cnn_symbol=str(target["cnnSymbol"]),
                    library_symbol=None
                    if target["librarySymbol"] is None
                    else str(target["librarySymbol"]),
                    old_confidence=float(target["oldConfidence"]),
                    old_source=target["oldSource"],
                    original_model_confidence=float(target["originalModelConfidence"]),
                ),
            )
            for target in board["targets"]
        ),
    )


def run_apply(arguments: argparse.Namespace, *, revert: bool = False) -> int:
    deadline = time.monotonic() + float(arguments.time_budget_seconds)
    manifest_path = cast(Path, arguments.manifest).resolve()
    manifest = read_manifest(manifest_path, str(arguments.expected_sha256))
    if manifest["game"]["code"] != arguments.game_code:
        raise RgbError("SYMBOL_RGB_GAME_MISMATCH", "Wrong game code.")
    if revert and not arguments.board and not arguments.all:
        raise RgbError(
            "SYMBOL_RGB_REVERT_SCOPE_REQUIRED",
            "Name the boards to revert with --board, or pass --all.",
        )
    prefix = "revert-receipts" if revert else "apply-receipts"
    receipts_path = manifest_path.with_name(f"{prefix}-{str(arguments.expected_sha256)[:12]}.jsonl")
    write_board = revert_board if revert else apply_board
    policy = manifest_policy(manifest)
    run_checksum = str(manifest["revisionChecksumSha256"])
    done = reference._done(reference._receipts(receipts_path))
    pending = [board for board in manifest["boards"] if board["reviewItemId"] not in done]
    if arguments.board:
        selected = set(arguments.board)
        unknown = selected - {str(board["reviewItemId"]) for board in manifest["boards"]}
        if unknown:
            raise RgbError("SYMBOL_RGB_BOARD_UNKNOWN", f"Not in the manifest: {sorted(unknown)}")
        pending = [board for board in pending if board["reviewItemId"] in selected]
    if arguments.limit_boards is not None:
        pending = pending[: int(arguments.limit_boards)]
    game_id = UUID(str(manifest["game"]["id"]))
    engine = create_maintenance_database_engine(ApiSettings.from_environment())
    session_factory = create_session_factory(engine)
    counts: Counter[str] = Counter()
    try:
        with receipts_path.open("a", encoding="utf-8") as receipts:
            for board in pending:
                if time.monotonic() >= deadline:
                    break
                try:
                    with (
                        game_storage_scope(game_id),
                        session_factory() as session,
                        session.begin(),
                    ):
                        status = write_board(
                            session,
                            game_id=game_id,
                            plan=board_plan(board),
                            library_checksum_sha256=run_checksum,
                            policy=policy,
                        )
                except (ReferenceLibraryWriteError, DBAPIError) as error:
                    code = getattr(error, "code", None) or type(error).__name__
                    skippable = (
                        isinstance(error, ReferenceLibraryWriteError)
                        and error.code in SKIPPABLE
                        and not revert
                    )
                    if not skippable:
                        receipts.write(
                            json.dumps(
                                {"reviewItemId": board["reviewItemId"], "status": f"failed:{code}"}
                            )
                            + "\n"
                        )
                        receipts.flush()
                        print(f"FAILED {board['reviewItemId']}: {error}", file=sys.stderr)
                        return 2
                    print(f"SKIPPED {board['reviewItemId']}: {error}", file=sys.stderr)
                    status = f"stale:{code}"
                receipts.write(
                    json.dumps({"reviewItemId": board["reviewItemId"], "status": status}) + "\n"
                )
                receipts.flush()
                counts[status] += 1
    finally:
        engine.dispose()
    receipts_now = reference._receipts(receipts_path)
    remaining = sum(
        1
        for board in manifest["boards"]
        if board["reviewItemId"] not in reference._done(receipts_now)
    )
    print(
        f"this run={dict(counts)} total={dict(sorted(Counter(receipts_now.values()).items()))}"
        f" remaining={remaining}"
    )
    if remaining and arguments.limit_boards is None and not arguments.board:
        print("INCOMPLETE: run the same command again.")
        return EXIT_INCOMPLETE
    return 0


def classify_target(row: Mapping[str, Any], target: Mapping[str, Any], run_checksum: str) -> str:
    """Read-back state of one target cell after a run."""

    expected = rgb_v2.confidence_for(target["status"])
    if row["review_state"] != "pending":
        return "decided_by_operator"
    if row["model_version"] == MODEL_VERSION and row["model_checksum_sha256"] != run_checksum:
        return "other_rgb_run"
    if (
        row["model_version"] == MODEL_VERSION
        and row["prediction_symbol_code"] == target["newSymbol"]
        and float(row["prediction_confidence"]) == expected
    ):
        return "rgb_prediction"
    if row["model_checksum_sha256"] == revert_checksum(run_checksum):
        return "reverted"
    if row["prediction_symbol_code"] == target["oldSymbol"] and float(
        row["prediction_confidence"] or 0.0
    ) == float(target["oldConfidence"]):
        return "unchanged"
    return "other"


def run_verify(arguments: argparse.Namespace) -> int:
    manifest_path = cast(Path, arguments.manifest).resolve()
    manifest = read_manifest(manifest_path, str(arguments.expected_sha256))
    targets = {
        str(target["cellReviewId"]): target
        for board in manifest["boards"]
        for target in board["targets"]
    }
    run_checksum = str(manifest["revisionChecksumSha256"])
    states: Counter[str] = Counter()
    engine = create_maintenance_database_engine(ApiSettings.from_environment())
    try:
        with engine.connect().execution_options(postgresql_readonly=True) as connection:
            for chunk in _chunks(sorted(targets), ID_BATCH):
                for row in connection.execute(
                    text(
                        """
                        SELECT c.id::text AS id, c.review_state, c.prediction_symbol_code,
                               c.prediction_confidence, p.model_version, p.model_checksum_sha256
                        FROM game_data_v2.image_symbol_review_cells c
                        LEFT JOIN game_data_v2.image_symbol_prediction_revisions p
                          ON p.game_id = c.game_id AND p.id = c.prediction_revision_id
                        WHERE c.game_id = :game_id AND c.id = ANY(CAST(:ids AS uuid[]))
                        """
                    ),
                    {"game_id": str(manifest["game"]["id"]), "ids": chunk},
                ).mappings():
                    states[classify_target(dict(row), targets[str(row["id"])], run_checksum)] += 1
    finally:
        engine.dispose()
    sha12 = str(arguments.expected_sha256)[:12]
    report = {
        "manifestSha256": arguments.expected_sha256,
        "targets": len(targets),
        "cellStates": dict(sorted(states.items())),
        "boardReceipts": dict(
            sorted(
                Counter(
                    reference._receipts(
                        manifest_path.with_name(f"apply-receipts-{sha12}.jsonl")
                    ).values()
                ).items()
            )
        ),
        "revertReceipts": dict(
            sorted(
                Counter(
                    reference._receipts(
                        manifest_path.with_name(f"revert-receipts-{sha12}.jsonl")
                    ).values()
                ).items()
            )
        ),
    }
    report_sha = reference._write_json(manifest_path.with_name("apply-verify.json"), report)
    print(json.dumps(report), f"apply-verify.json sha256={report_sha}")
    return 0


# ---------------------------------------------------------------- cli


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    index = commands.add_parser("index", help="Export the band index (read-only).")
    index.add_argument("--game-code", required=True)
    index.add_argument("--output-dir", required=True, type=Path)
    index.add_argument("--shards", type=int, default=32, choices=range(1, 257))
    index.add_argument("--symbol", choices=SYMBOLS)
    index.add_argument("--time-budget-seconds", type=float, default=90.0)
    preview = commands.add_parser("preview", help="RGB v2 preview and apply manifest.")
    preview.add_argument("--game-code", required=True)
    preview.add_argument("--index-dir", required=True, type=Path)
    preview.add_argument("--output-dir", required=True, type=Path)
    preview.add_argument("--library-dir", required=True, type=Path)
    preview.add_argument("--artifact-root", type=Path)
    preview.add_argument("--symbol", required=True, choices=SYMBOLS)
    preview.add_argument("--band", required=True, choices=[label for label, _, _ in BANDS])
    preview.add_argument("--shard", type=_shard, default=(0, 1))
    preview.add_argument("--thumbnails-per-group", type=int, default=40, choices=range(1, 201))
    preview.add_argument("--time-budget-seconds", type=float, default=300.0)
    for name, help_text in (
        ("apply", "Write the manifest's RGB v2 predictions."),
        ("revert", "Restore the predictions an RGB v2 run replaced."),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--game-code", required=True)
        command.add_argument("--manifest", required=True, type=Path)
        command.add_argument("--expected-sha256", required=True)
        command.add_argument("--limit-boards", type=int)
        command.add_argument("--board", action="append", default=[])
        command.add_argument("--time-budget-seconds", type=float, default=240.0)
        if name == "revert":
            command.add_argument("--all", action="store_true")
    manifest = commands.add_parser("manifest", help="Bind an approved preview to the boards.")
    manifest.add_argument("--output-dir", required=True, type=Path)
    verify = commands.add_parser("verify", help="Read back the cells of a manifest.")
    verify.add_argument("--manifest", required=True, type=Path)
    verify.add_argument("--expected-sha256", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parse_args(argv)
    try:
        if arguments.command == "index":
            return run_index(arguments)
        if arguments.command == "preview":
            return run_preview(arguments)
        if arguments.command == "manifest":
            return run_manifest(arguments)
        if arguments.command == "apply":
            return run_apply(arguments)
        if arguments.command == "revert":
            return run_apply(arguments, revert=True)
        return run_verify(arguments)
    except (RgbError, reference.EvaluationError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
