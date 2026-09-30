import type { BoardSearchResultResponse } from '@game-predictor/admin-api-client';

/** Existing technical limit enforced by the board-search API (`limit=1..100`). */
export const BOARD_SEARCH_LIMIT_MAX = 100;
export const BOARD_SEARCH_LIMIT_DEFAULT = 5;

export interface BoardSearchResultsState {
  readonly activeIndex: number;
  readonly results: readonly BoardSearchResultResponse[];
}

export function createBoardSearchResultsState(
  results: readonly BoardSearchResultResponse[],
): BoardSearchResultsState {
  return Object.freeze({
    activeIndex: 0,
    results: Object.freeze([...results]),
  });
}

/**
 * Stable identity of a board-search result, independent of ranking position.
 * Matches the historical `resultKey` used to remount the carousel.
 */
export function boardSearchResultIdentity(
  result: BoardSearchResultResponse,
): string {
  return `${result.assetMode}:${result.sequenceNumber}:${result.boardChecksumSha256}`;
}

/**
 * Build a fresh results state that keeps the previously active board selected
 * when it is still present in the new results (e.g. after only the result
 * limit changed). Falls back to the first result otherwise, matching the
 * default behaviour of a brand-new search.
 */
export function reconcileBoardSearchResultsState(
  previous: BoardSearchResultsState,
  results: readonly BoardSearchResultResponse[],
): BoardSearchResultsState {
  const previousActive = previous.results[previous.activeIndex];
  const previousIdentity =
    previousActive === undefined
      ? null
      : boardSearchResultIdentity(previousActive);
  const preservedIndex =
    previousIdentity === null
      ? -1
      : results.findIndex(
          (result) => boardSearchResultIdentity(result) === previousIdentity,
        );
  return Object.freeze({
    activeIndex: preservedIndex >= 0 ? preservedIndex : 0,
    results: Object.freeze([...results]),
  });
}

export type ParsedBoardSearchLimit =
  | { readonly ok: true; readonly value: number }
  | { readonly ok: false; readonly error: string };

/**
 * Validate the "Liczba wyników" input: a positive integer within the
 * existing technical limit, matching the API's `limit` query parameter.
 */
export function parseBoardSearchLimit(text: string): ParsedBoardSearchLimit {
  const trimmed = text.trim();
  if (trimmed === '') {
    return { error: 'Podaj liczbę wyników.', ok: false };
  }
  if (!/^\d+$/.test(trimmed)) {
    return { error: 'Liczba wyników musi być liczbą całkowitą.', ok: false };
  }
  const value = Number.parseInt(trimmed, 10);
  if (value < 1 || value > BOARD_SEARCH_LIMIT_MAX) {
    return {
      error: `Liczba wyników musi być z zakresu 1–${BOARD_SEARCH_LIMIT_MAX}.`,
      ok: false,
    };
  }
  return { ok: true, value };
}

export function activeBoardSearchResult(
  state: BoardSearchResultsState,
): BoardSearchResultResponse | null {
  return state.results[state.activeIndex] ?? null;
}

export function moveBoardSearchResult(
  state: BoardSearchResultsState,
  direction: -1 | 1,
): BoardSearchResultsState {
  if (state.results.length === 0) {
    return state;
  }
  const activeIndex = Math.min(
    state.results.length - 1,
    Math.max(0, state.activeIndex + direction),
  );
  if (activeIndex === state.activeIndex) {
    return state;
  }
  return Object.freeze({ ...state, activeIndex });
}

export function boardSearchNeighbourIndexes(
  state: BoardSearchResultsState,
): readonly number[] {
  return [-1, 1]
    .map((offset) => state.activeIndex + offset)
    .filter((index) => index >= 0 && index < state.results.length);
}

// --- Board crop preview -----------------------------------------------
//
// `operational_review` results whose game uses virtual (geometry-only)
// board storage have no persistent per-board bitmap: the "board" asset is
// deliberately the whole source photo (storage/image_review_repository.py,
// `_item_from_records`'s `virtual_source` branch — "Structured boards
// deliberately have no persistent board bitmap. The Reviewer displays a
// bounded source context for this mode."). The functions below compute a
// client-side CSS crop around the board's own quad (already exposed by the
// existing `getOperationalImageReviewItem` response's `geometry` field) so
// the carousel shows just that board with some padding instead of the
// entire page. Purely cosmetic: any unexpected shape falls back to `null`,
// and the caller then renders the full image exactly as before this
// feature existed.

export interface BoardCropPoint {
  readonly x: number;
  readonly y: number;
}

/** Padding added on every side of the board's own bounding box, as a
 * fraction of that box's own width/height. 20% keeps the found board large
 * while still showing enough of its neighbours for orientation. */
const BOARD_CROP_PADDING_FACTOR = 0.2;

/**
 * Extract the board's quad (4 `{x, y}` pixel points in the source image's
 * own coordinate space) from an `OperationalImageReviewItemResponse.geometry`
 * value. Returns `null` for anything that is not exactly a 4-point quad of
 * finite numeric coordinates — including a genuinely absent field, which is
 * expected for boards that are not virtual-source.
 */
export function parseBoardCropQuad(
  geometry: unknown,
): readonly BoardCropPoint[] | null {
  if (typeof geometry !== 'object' || geometry === null) {
    return null;
  }
  const record = geometry as Record<string, unknown>;
  const raw = record.sourceQuad ?? record.quad;
  if (!Array.isArray(raw) || raw.length !== 4) {
    return null;
  }
  const points: BoardCropPoint[] = [];
  for (const entry of raw) {
    if (typeof entry !== 'object' || entry === null) {
      return null;
    }
    const point = entry as Record<string, unknown>;
    const x = point.x;
    const y = point.y;
    if (
      typeof x !== 'number' ||
      typeof y !== 'number' ||
      !Number.isFinite(x) ||
      !Number.isFinite(y)
    ) {
      return null;
    }
    points.push({ x, y });
  }
  return points;
}

export interface BoardCropTransform {
  /** `paddedWidth / paddedHeight`, to be set as the crop container's CSS
   * `aspect-ratio` so the percentage-based image sizing below is undistorted. */
  readonly aspectRatioWidth: number;
  readonly aspectRatioHeight: number;
  readonly imageWidthPercent: number;
  readonly imageHeightPercent: number;
  readonly imageLeftPercent: number;
  readonly imageTopPercent: number;
}

/**
 * Compute a pure-CSS crop-and-zoom transform: a container whose
 * `aspect-ratio` is `aspectRatioWidth / aspectRatioHeight`, holding an
 * absolutely positioned image sized/offset by the returned percentages.
 * Because the container's aspect ratio matches the padded box exactly, the
 * two independent horizontal/vertical percentage scales below never
 * distort the image (`containerWidth / paddedWidth == containerHeight /
 * paddedHeight` follows directly from that aspect-ratio constraint).
 *
 * Returns `null` for a degenerate quad (zero width/height bounding box) or
 * non-positive image dimensions, so the caller can fall back to showing the
 * full, unmodified image.
 */
export function computeBoardCropTransform(
  quad: readonly BoardCropPoint[],
  naturalWidth: number,
  naturalHeight: number,
): BoardCropTransform | null {
  if (quad.length !== 4 || naturalWidth <= 0 || naturalHeight <= 0) {
    return null;
  }
  const xs = quad.map((point) => point.x);
  const ys = quad.map((point) => point.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const boardWidth = maxX - minX;
  const boardHeight = maxY - minY;
  if (boardWidth <= 0 || boardHeight <= 0) {
    return null;
  }
  const padX = boardWidth * BOARD_CROP_PADDING_FACTOR;
  const padY = boardHeight * BOARD_CROP_PADDING_FACTOR;
  const cropX = minX - padX;
  const cropY = minY - padY;
  const cropWidth = boardWidth + 2 * padX;
  const cropHeight = boardHeight + 2 * padY;

  return {
    aspectRatioHeight: cropHeight,
    aspectRatioWidth: cropWidth,
    imageHeightPercent: (naturalHeight / cropHeight) * 100,
    imageLeftPercent: (-cropX / cropWidth) * 100,
    imageTopPercent: (-cropY / cropHeight) * 100,
    imageWidthPercent: (naturalWidth / cropWidth) * 100,
  };
}
