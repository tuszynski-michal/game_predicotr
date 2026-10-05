import type {
  ApproximateWinResponse,
  BoardSearchSharePublicBoardDetailResponse,
  BoardSearchShareCellCorrectionRequest,
  BoardSearchShareCellCorrectionResponse,
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
 * (D-492). Public correction uses opaque cell versions; no refresh or full-photo
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
  readonly sessionId?: string;
  readonly storage?: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;
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
    {
      readonly expiresAt: number;
      readonly value: BoardSearchResponse;
      readonly searchContextId: string | null;
    }
  >();
  const detailCache = new Map<
    number,
    BoardSearchSharePublicBoardDetailResponse
  >();
  let searchContextId: string | null = null;
  let storage = options.storage;
  if (storage === undefined && typeof window !== 'undefined') {
    try {
      storage = window.sessionStorage;
    } catch {
      /* Reading remains available. */
    }
  }
  const pendingKey = `board-search-share-correction:${options.sessionId ?? 'unspecified'}`;
  type Pending = {
    sequenceNumber: number;
    cellIndex: number;
    body: BoardSearchShareCellCorrectionRequest;
  };
  let pending: Pending | null = null;
  let inFlight = false;
  try {
    const raw = storage?.getItem(pendingKey);
    if (raw) {
      const candidate = JSON.parse(raw) as Pending;
      if (
        Number.isInteger(candidate.sequenceNumber) &&
        Number.isInteger(candidate.cellIndex) &&
        typeof candidate.body?.operationId === 'string'
      )
        pending = candidate;
    }
  } catch {
    /* An unavailable storage is reported before a write. */
  }

  function clearData() {
    searchCache.clear();
    detailCache.clear();
    rangeFingerprint = null;
  }

  async function sendCorrection(
    operation: Pending,
  ): Promise<Result<BoardSearchShareCellCorrectionResponse>> {
    if (inFlight)
      return { error: { message: 'Poprzedni zapis jeszcze trwa.' } };
    inFlight = true;
    try {
      const response = await fetchImplementation(
        `${BOARD_SEARCH_SHARE_API_BASE}/boards/${operation.sequenceNumber}/cells/${operation.cellIndex}/decision`,
        {
          method: 'POST',
          cache: 'no-store',
          credentials: 'same-origin',
          headers: {
            Accept: 'application/json',
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(operation.body),
        },
      );
      let receipt: BoardSearchShareCellCorrectionResponse | undefined;
      if (response.ok) {
        receipt =
          (await response.json()) as BoardSearchShareCellCorrectionResponse;
        if (
          receipt.saved !== true ||
          receipt.sequenceNumber !== operation.sequenceNumber ||
          receipt.cellIndex !== operation.cellIndex ||
          typeof receipt.cellVersion !== 'string'
        ) {
          throw new Error('Invalid correction receipt');
        }
      }
      if (
        response.ok ||
        (response.status >= 400 &&
          response.status < 500 &&
          response.status !== 429)
      ) {
        try {
          storage?.removeItem(pendingKey);
        } catch {
          /* A stale durable receipt can safely be retried. */
        }
        pending = null;
        clearData();
      }
      if (response.status === 401) {
        clearData();
        options.onUnauthorized?.();
      }
      return receipt !== undefined
        ? { data: receipt }
        : { error: await errorBody(response) };
    } finally {
      inFlight = false;
    }
  }
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
    if (response.status === 401) {
      clearData();
      options.onUnauthorized?.();
    }
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
        searchContextId = cached.searchContextId;
        return { data: cached.value };
      }
      searchCache.delete(key);
      const result = await get<BoardSearchSharePublicSearchResponse>(
        `/search?${searchQuery(searchOptions)}`,
      );
      if (result.data === undefined) return { error: result.error };
      const value = toAdminSearch(result.data);
      searchContextId = result.data.searchContextId ?? null;
      searchCache.set(key, {
        expiresAt: now() + SEARCH_CACHE_TTL_MS,
        value,
        searchContextId,
      });
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
      const result = await get<BoardSearchSharePublicBoardDetailResponse>(
        `/boards/${sequenceNumber}`,
      );
      if (result.data !== undefined)
        detailCache.set(sequenceNumber, result.data);
      return result;
    },

    hasPendingBoardSearchCell: (_gameId, sequenceNumber) =>
      pending?.sequenceNumber === sequenceNumber,
    retryBoardSearchCell: async (_gameId, sequenceNumber) => {
      if (pending === null || pending.sequenceNumber !== sequenceNumber)
        return { error: { message: 'Brak zapisu do potwierdzenia.' } };
      return sendCorrection(pending);
    },
    correctBoardSearchCell: async (
      _gameId,
      sequenceNumber,
      cellIndex,
      request,
    ) => {
      const body = { ...request, searchContextId };
      if (pending !== null) {
        const { operationId: _operationId, ...previous } = pending.body;
        if (
          pending.sequenceNumber !== sequenceNumber ||
          pending.cellIndex !== cellIndex ||
          JSON.stringify(previous) !== JSON.stringify(body)
        ) {
          return {
            error: {
              message: `Najpierw sprawdź ostatni zapis na planszy #${pending.sequenceNumber}.`,
            },
          };
        }
      } else {
        const operation = {
          sequenceNumber,
          cellIndex,
          body: { ...body, operationId: globalThis.crypto.randomUUID() },
        };
        try {
          if (storage === undefined || options.sessionId === undefined)
            throw new Error('Missing durable session storage');
          storage.setItem(pendingKey, JSON.stringify(operation));
        } catch {
          return {
            error: {
              message:
                'Przeglądarka nie pozwala zachować zapisu do ponowienia. Włącz pamięć sesji.',
            },
          };
        }
        pending = operation;
      }
      return sendCorrection(pending);
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
