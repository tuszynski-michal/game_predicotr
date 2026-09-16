"""Measure one real symbol-review page without creating synthetic data.

The command reads the current local PostgreSQL projection and renders only the
same bounded preview atlases requested by Admin. It never mutates domain data.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import UUID

from game_predictor_api.application.image_symbol_reviews import SymbolCellReviewQueryService
from game_predictor_api.application.virtual_cell_previews import (
    DEFAULT_VIRTUAL_CELL_PREVIEW_SIZE,
    SymbolCellPreviewTarget,
    VirtualCellPreviewService,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.image_symbol_reviews import (
    SymbolCellReviewFilterState,
    SymbolCellReviewListItem,
)
from game_predictor_api.storage.database import create_database_engine, create_session_factory
from game_predictor_api.storage.image_symbol_review_repository import (
    SqlAlchemySymbolCellReviewQueryRepository,
)

_ATLAS_BATCH_SIZE = 100


@dataclass(frozen=True, slots=True)
class Measurement:
    game_id: str
    symbol_id: str
    state: str
    page_size: int
    legacy_file_count: int
    virtual_source_count: int
    metadata_seconds: tuple[float, ...]
    metadata_p95_seconds: float
    first_atlas_seconds: float
    full_page_atlas_seconds: float
    warm_page_atlas_seconds: float
    atlas_request_count: int
    atlas_bytes: int
    unique_batch_keys: int
    cache_keys_reused: bool


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-id", required=True, type=UUID)
    parser.add_argument("--symbol-id", required=True, type=UUID)
    parser.add_argument(
        "--state",
        choices=tuple(state.value for state in SymbolCellReviewFilterState),
        default=SymbolCellReviewFilterState.PENDING.value,
    )
    parser.add_argument("--limit", type=int, default=500, choices=range(1, 501))
    parser.add_argument("--metadata-runs", type=int, default=10, choices=range(1, 31))
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def _p95(values: tuple[float, ...]) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]


def _targets(
    items: tuple[SymbolCellReviewListItem, ...],
) -> tuple[SymbolCellPreviewTarget, ...]:
    return tuple(
        SymbolCellPreviewTarget(
            cell_review_id=item.cell_review_id,
            expected_revision=item.revision,
            expected_crop_checksum_sha256=item.crop_checksum_sha256,
            expected_render_spec_checksum_sha256=item.render_spec_checksum_sha256,
        )
        for item in items
    )


def _render_page(
    *,
    game_id: UUID,
    service: SymbolCellReviewQueryService,
    preview_service: VirtualCellPreviewService,
    items: tuple[SymbolCellReviewListItem, ...],
) -> tuple[float, tuple[str, ...], int, tuple[float, ...]]:
    started = time.perf_counter()
    keys: list[str] = []
    atlas_bytes = 0
    chunk_seconds: list[float] = []
    for offset in range(0, len(items), _ATLAS_BATCH_SIZE):
        chunk_started = time.perf_counter()
        targets = _targets(items[offset : offset + _ATLAS_BATCH_SIZE])
        assets = service.preview_assets(game_id=game_id, targets=targets)
        batch = preview_service.render_batch(
            game_id=game_id,
            assets=assets,
            preview_size=DEFAULT_VIRTUAL_CELL_PREVIEW_SIZE,
            renderer_mode="current",
        )
        cached = preview_service.read_atlas(game_id=game_id, batch_key=batch.batch_key)
        keys.append(batch.batch_key)
        atlas_bytes += len(cached.content)
        chunk_seconds.append(time.perf_counter() - chunk_started)
    return time.perf_counter() - started, tuple(keys), atlas_bytes, tuple(chunk_seconds)


def main() -> int:
    args = _parse_args()
    settings = ApiSettings.from_environment()
    engine = create_database_engine(settings)
    session_factory = create_session_factory(engine)
    try:
        with session_factory() as session:
            service = SymbolCellReviewQueryService(
                SqlAlchemySymbolCellReviewQueryRepository(session)
            )
            metadata_times: list[float] = []
            page = None
            for _ in range(args.metadata_runs):
                started = time.perf_counter()
                page = service.list(
                    game_id=args.game_id,
                    symbol_id=args.symbol_id,
                    state=SymbolCellReviewFilterState(args.state),
                    after_cursor=None,
                    before_cursor=None,
                    limit=args.limit,
                )
                metadata_times.append(time.perf_counter() - started)
            assert page is not None
            if len(page.items) != args.limit:
                raise RuntimeError(f"Expected {args.limit} real rows, received {len(page.items)}.")

            preview_service = VirtualCellPreviewService(settings.artifact_root)
            first_total, first_keys, atlas_bytes, first_chunks = _render_page(
                game_id=args.game_id,
                service=service,
                preview_service=preview_service,
                items=page.items,
            )
            warm_total, warm_keys, _warm_bytes, _warm_chunks = _render_page(
                game_id=args.game_id,
                service=service,
                preview_service=preview_service,
                items=page.items,
            )
            result = Measurement(
                game_id=str(args.game_id),
                symbol_id=str(args.symbol_id),
                state=args.state,
                page_size=len(page.items),
                legacy_file_count=sum(item.asset_mode == "legacy_file" for item in page.items),
                virtual_source_count=sum(
                    item.asset_mode == "virtual_source" for item in page.items
                ),
                metadata_seconds=tuple(round(value, 6) for value in metadata_times),
                metadata_p95_seconds=round(_p95(tuple(metadata_times)), 6),
                first_atlas_seconds=round(first_chunks[0], 6),
                full_page_atlas_seconds=round(first_total, 6),
                warm_page_atlas_seconds=round(warm_total, 6),
                atlas_request_count=len(first_keys),
                atlas_bytes=atlas_bytes,
                unique_batch_keys=len(set(first_keys)),
                cache_keys_reused=first_keys == warm_keys,
            )
    finally:
        engine.dispose()

    output = json.dumps(asdict(result), indent=2, sort_keys=True)
    print(output)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{output}\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
