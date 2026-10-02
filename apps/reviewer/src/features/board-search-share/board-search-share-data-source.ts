import type {
  ApproximateWinResponse,
  BoardSearchBoardDetailResponse,
  BoardSearchResponse,
  BoardSearchSharePublicContextResponse,
  BoardSearchSharePublicSearchResponse,
  BoardSearchSharePublicSymbolResponse,
  GetBoardSearchApproximateWinOptions,
  SearchGameBoardsOptions,
  SymbolResponse,
} from '@game-predictor/admin-api-client';
import type { BoardSearchDataSource } from '@game-predictor/board-search-ui';

/**
 * The shared board search section's data source over the Reviewer proxy
 * (D-471). Read-only: no cell correction, no refresh, no full-photo
 * fallback. Client caches follow plan §4.5.
 */

export const BOARD_SEARCH_SHARE_API_BASE =
  '/board-search-api/api/v1/board-search-shares';
/** The section passes a game id through; the share's game is fixed. */
export const BOARD_SEARCH_SHARE_GAME_ID = 'shared';
export const SEARCH_CACHE_TTL_MS = 5 * 60 * 1000;
export const SEARCH_CACHE_MAX_ENTRIES = 50;

type Result<T> = { readonly data?: T; readonly error?: unknown };

export type BoardSearchShareDataSourceOptions = {
  readonly fetchImplementation?: typeof globalThis.fetch;
  readonly now?: () => number;
  /** Called when the proxy answers 401: the access expired or was stopped. */
  readonly onUnauthorized?: () => void;
};

export type BoardSearchShareDataSource = BoardSearchDataSource & {
  readonly context: () => Promise<
    Result<BoardSearchSharePublicContextResponse>
  >;
};

export function createBoardSearchShareDataSource(
  options: BoardSearchShareDataSourceOptions = {},
): BoardSearchShareDataSource {
  const fetchImplementation = options.fetchImplementation ?? globalThis.fetch;
  const now = options.now ?? (() => Date.now());
  const searchCache = new Map<
    string,
    { readonly expiresAt: number; readonly value: BoardSearchResponse }
  >();
  const detailCache = new Map<number, BoardSearchBoardDetailResponse>();
  let rangeFingerprint: string | null = null;
  let symbols: Promise<Result<SymbolResponse[]>> | null = null;
  const imageRevisions = new Map<string, string>();

  async function get<T>(path: string): Promise<Result<T>> {
    const response = await fetchImplementation(
      `${BOARD_SEARCH_SHARE_API_BASE}${path}`,
      {
        cache: 'no-store',
        credentials: 'same-origin',
        headers: { Accept: 'application/json' },
      },
    );
    if (response.ok) return { data: (await response.json()) as T };
    if (response.status === 401) options.onUnauthorized?.();
    return { error: await errorBody(response) };
  }

  return {
    context: () => get<BoardSearchSharePublicContextResponse>('/context'),

    listSymbols: () => {
      // One read per unlocked page: the catalogue does not change while a
      // recipient searches, and icons are bound to their revisions.
      if (symbols === null) {
        symbols = get<BoardSearchSharePublicSymbolResponse[]>('/symbols').then(
          (result) => {
            if (result.data === undefined) {
              symbols = null;
              return { error: result.error };
            }
            imageRevisions.clear();
            for (const symbol of result.data) {
              if (symbol.imageRevision !== null) {
                imageRevisions.set(symbol.id, symbol.imageRevision);
              }
            }
            return { data: result.data.map(toAdminSymbol) };
          },
          (error: unknown) => {
            symbols = null;
            throw error;
          },
        );
      }
      return symbols;
    },

    symbolImageAssetUrl: (_gameId, symbolId) =>
      `${BOARD_SEARCH_SHARE_API_BASE}/symbols/${encodeURIComponent(symbolId)}/image?revision=${
        imageRevisions.get(symbolId) ?? ''
      }`,

    searchGameBoards: async (_gameId, searchOptions) => {
      const key = searchCacheKey(searchOptions);
      const cached = searchCache.get(key);
      if (cached !== undefined && cached.expiresAt > now()) {
        // Refresh the entry's recency for the size limit.
        searchCache.delete(key);
        searchCache.set(key, cached);
        return { data: cached.value };
      }
      searchCache.delete(key);
      const result = await get<BoardSearchSharePublicSearchResponse>(
        `/search?${searchQuery(searchOptions)}`,
      );
      if (result.data === undefined) return { error: result.error };
      const value = toAdminSearch(result.data);
      searchCache.set(key, { expiresAt: now() + SEARCH_CACHE_TTL_MS, value });
      while (searchCache.size > SEARCH_CACHE_MAX_ENTRIES) {
        const oldest = searchCache.keys().next().value;
        if (oldest === undefined) break;
        searchCache.delete(oldest);
      }
      return { data: value };
    },

    getBoardSearchApproximateWin: async (
      _gameId,
      rangeOptions: GetBoardSearchApproximateWinOptions,
    ) => {
      // Never cached: the section recalculates on every expansion (D-462).
      const parameters = new URLSearchParams({
        spinCount: String(rangeOptions.spinCount),
        startSequenceNumber: String(rangeOptions.startSequenceNumber),
      });
      const result = await get<ApproximateWinResponse>(
        `/approximate-win?${parameters}`,
      );
      if (result.data !== undefined) {
        const fingerprint = result.data.dataFingerprintSha256;
        if (fingerprint !== rangeFingerprint) {
          // Board details are valid for one data state of the range.
          detailCache.clear();
          rangeFingerprint = fingerprint;
        }
      }
      return result;
    },

    recordBoardSearchApproximateWinStake: async (_gameId, stakeOptions) => {
      const parameters = new URLSearchParams({
        spinCount: String(stakeOptions.spinCount),
        startSequenceNumber: String(stakeOptions.startSequenceNumber),
      });
      // The base stake is recorded by leaving the parameter out (D-487).
      if (stakeOptions.stakeGrosze !== null) {
        parameters.set('stakeGrosze', String(stakeOptions.stakeGrosze));
      }
      const result = await get<{ recorded: boolean }>(
        `/approximate-win/stake?${parameters}`,
      );
      return result.data === undefined
        ? { error: result.error }
        : { data: undefined };
    },

    getBoardSearchBoardDetail: async (_gameId, sequenceNumber) => {
      const cached = detailCache.get(sequenceNumber);
      if (cached !== undefined) return { data: cached };
      const result = await get<BoardSearchBoardDetailResponse>(
        `/boards/${sequenceNumber}`,
      );
      if (result.data !== undefined)
        detailCache.set(sequenceNumber, result.data);
      return result;
    },

    boardSearchBoardViewUrl: (
      _gameId,
      sequenceNumber,
      checksum,
      viewRevision,
    ) => {
      const parameters = new URLSearchParams({
        expectedBoardChecksumSha256: checksum,
      });
      if (viewRevision !== undefined)
        parameters.set('viewRevision', viewRevision);
      return `${BOARD_SEARCH_SHARE_API_BASE}/boards/${sequenceNumber}/view?${parameters}`;
    },
  };
}

function searchCacheKey(options: SearchGameBoardsOptions): string {
  return JSON.stringify([
    [...options.cells]
      .map((cell) => `${cell.cellIndex}:${cell.symbolCode ?? '?'}`)
      .sort(),
    options.scope ?? 'all_searchable',
    options.limit ?? 100,
  ]);
}

function searchQuery(options: SearchGameBoardsOptions): URLSearchParams {
  const parameters = new URLSearchParams();
  for (const cell of options.cells) {
    parameters.append('cell', `${cell.cellIndex}:${cell.symbolCode ?? '?'}`);
  }
  if (options.scope !== undefined) parameters.set('scope', options.scope);
  if (options.limit !== undefined)
    parameters.set('limit', String(options.limit));
  return parameters;
}

function toAdminSymbol(
  symbol: BoardSearchSharePublicSymbolResponse,
): SymbolResponse {
  return {
    code: symbol.code,
    displayOrder: symbol.displayOrder,
    gameId: BOARD_SEARCH_SHARE_GAME_ID,
    id: symbol.id,
    // The section only asks whether an image exists; the URL carries the
    // revision instead of a path.
    imagePath: symbol.imageRevision === null ? null : 'shared',
    isWildcard: symbol.isWildcard,
    mobileCode: symbol.mobileCode,
    name: symbol.name,
    nameEn: symbol.nameEn,
    namePl: symbol.namePl,
    status: symbol.status === 'archived' ? 'archived' : 'active',
  };
}

function toAdminSearch(
  value: BoardSearchSharePublicSearchResponse,
): BoardSearchResponse {
  return {
    gameId: BOARD_SEARCH_SHARE_GAME_ID,
    queryCellCount: value.queryCellCount,
    results: value.results.map((result) => ({
      assetMode: 'operational_review',
      boardChecksumSha256: result.boardChecksumSha256,
      importJobId: null,
      recognizedBoardId: null,
      reviewItemId: null,
      score: result.score,
      sequenceNumber: result.sequenceNumber,
      status: result.status,
    })),
    scope: value.scope,
  };
}

async function errorBody(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return undefined;
  }
}
