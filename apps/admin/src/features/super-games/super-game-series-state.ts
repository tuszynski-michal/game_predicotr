/**
 * Pure state of the „Supergry” section (TASK-0934, D-535): the series list
 * with cursor pagination and filters, and the series view with its carousel
 * of positions and the cas-protected super symbol choice. Everything here is
 * free of React and the DOM so that it is covered by `node --test`.
 */
import type {
  ListSuperGameSeriesData,
  SuperGameSeriesBoardResponse,
  SuperGameSeriesBoardsResponse,
  SuperGameSeriesCountsResponse,
  SuperGameSeriesDeriveResponse,
  SuperGameSeriesListResponse,
  SuperGameSeriesResponse,
  SuperGameStateResponse,
  SymbolResponse,
} from '@game-predictor/admin-api-client';

export const SERIES_PAGE_LIMIT = 50;
/** The state of the published generation is polled while it is stale. */
export const SERIES_STATE_POLL_INTERVAL_MS = 5000;

// --- List: filters, query and pagination -------------------------------

export type CompletenessFilter = 'all' | 'complete' | 'incomplete';
export type RunVerificationFilter = 'all' | 'verified' | 'unverified';
export type DefinedFilter = 'all' | 'defined' | 'undefined';

export interface SeriesFilters {
  readonly completeness: CompletenessFilter;
  readonly runVerification: RunVerificationFilter;
  readonly defined: DefinedFilter;
}

export const DEFAULT_SERIES_FILTERS: SeriesFilters = Object.freeze({
  completeness: 'all',
  defined: 'all',
  runVerification: 'all',
});

export const COMPLETENESS_FILTER_OPTIONS: readonly {
  readonly value: CompletenessFilter;
  readonly label: string;
}[] = [
  { value: 'all', label: 'Wszystkie' },
  { value: 'complete', label: 'Kompletne' },
  { value: 'incomplete', label: 'Niekompletne' },
];

export const RUN_VERIFICATION_FILTER_OPTIONS: readonly {
  readonly value: RunVerificationFilter;
  readonly label: string;
}[] = [
  { value: 'all', label: 'Wszystkie' },
  { value: 'verified', label: 'Zweryfikowane' },
  { value: 'unverified', label: 'Niezweryfikowane' },
];

export const DEFINED_FILTER_OPTIONS: readonly {
  readonly value: DefinedFilter;
  readonly label: string;
}[] = [
  { value: 'all', label: 'Wszystkie' },
  { value: 'defined', label: 'Z super symbolem' },
  { value: 'undefined', label: 'Do zdefiniowania' },
];

export function seriesFiltersKey(filters: SeriesFilters): string {
  return `${filters.completeness}|${filters.runVerification}|${filters.defined}`;
}

export type SeriesListQuery = NonNullable<ListSuperGameSeriesData['query']>;

/** Maps the filters and a cursor to the API query; `all` is simply omitted. */
export function seriesListQuery(
  filters: SeriesFilters,
  cursor: string | null,
  limit: number = SERIES_PAGE_LIMIT,
): SeriesListQuery {
  const query: SeriesListQuery = { limit };
  if (filters.completeness !== 'all') {
    query.completeness = filters.completeness;
  }
  if (filters.runVerification !== 'all') {
    query.runVerification = filters.runVerification;
  }
  if (filters.defined !== 'all') {
    query.defined = filters.defined === 'defined';
  }
  if (cursor !== null) query.cursor = cursor;
  return query;
}

/**
 * The counter of series without a super symbol. Every list page carries the
 * exact counts of all published series of the game, whatever the filters.
 */
export function undefinedSeriesCountLabel(
  counts: SuperGameSeriesCountsResponse | null,
): string {
  return counts === null ? '—' : String(counts.undefined);
}

export function seriesCountsCaption(
  counts: SuperGameSeriesCountsResponse | null,
): string {
  return counts === null
    ? 'serii bez super symbolu'
    : `z ${counts.total} serii bez super symbolu`;
}

export type SeriesListStatus = 'loading' | 'ready' | 'error';

export interface SeriesListState {
  readonly filters: SeriesFilters;
  readonly filtersKey: string;
  /**
   * Load generation: changes on every filter change and every reload. A page
   * or an error that belongs to an earlier generation is discarded.
   */
  readonly generation: number;
  readonly items: readonly SuperGameSeriesResponse[];
  readonly nextCursor: string | null;
  readonly status: SeriesListStatus;
  readonly error: string | null;
  readonly superGameState: SuperGameStateResponse | null;
  readonly counts: SuperGameSeriesCountsResponse | null;
}

export function createSeriesListState(
  filters: SeriesFilters = DEFAULT_SERIES_FILTERS,
  generation = 0,
): SeriesListState {
  return Object.freeze({
    counts: null,
    error: null,
    filters,
    filtersKey: seriesFiltersKey(filters),
    generation,
    items: Object.freeze([]),
    nextCursor: null,
    status: 'loading',
    superGameState: null,
  });
}

/** New filters start a new list; the counter and the state banner stay. */
export function changeSeriesFilters(
  state: SeriesListState,
  filters: SeriesFilters,
): SeriesListState {
  if (seriesFiltersKey(filters) === state.filtersKey) return state;
  return Object.freeze({
    ...createSeriesListState(filters, state.generation + 1),
    counts: state.counts,
    superGameState: state.superGameState,
  });
}

/** Restarts the list with the same filters (after „Przelicz serie”). */
export function reloadSeriesList(state: SeriesListState): SeriesListState {
  return Object.freeze({
    ...createSeriesListState(state.filters, state.generation + 1),
    counts: state.counts,
    superGameState: state.superGameState,
  });
}

/**
 * Starts the next page. After a failed page the same cursor can be retried
 * (`error` keeps `nextCursor`); a failed first page has no cursor and needs
 * a refresh instead.
 */
export function startLoadingMoreSeries(
  state: SeriesListState,
): SeriesListState {
  return (state.status === 'ready' || state.status === 'error') &&
    state.nextCursor !== null
    ? Object.freeze({ ...state, error: null, status: 'loading' })
    : state;
}

export interface SeriesListPage {
  /** The load generation the request was started in. */
  readonly generation: number;
  /** The cursor the request was made with; `null` for the first page. */
  readonly cursor: string | null;
  readonly response: SuperGameSeriesListResponse;
}

/**
 * Applies one page. A page of an earlier generation (other filters or a
 * reload since the request started), a repeated page and a page whose cursor
 * is not the current `nextCursor` are late answers and are ignored.
 */
export function applySeriesListPage(
  state: SeriesListState,
  page: SeriesListPage,
): SeriesListState {
  if (page.generation !== state.generation) return state;
  if (page.cursor === null) {
    if (state.items.length > 0 && state.status === 'ready') return state;
    return Object.freeze({
      ...state,
      counts: page.response.counts,
      error: null,
      items: Object.freeze([...page.response.items]),
      nextCursor: page.response.nextCursor,
      status: 'ready',
      superGameState: page.response.superGameState,
    });
  }
  if (page.cursor !== state.nextCursor) return state;
  const known = new Set(state.items.map((item) => item.id));
  return Object.freeze({
    ...state,
    counts: page.response.counts,
    error: null,
    items: Object.freeze([
      ...state.items,
      ...page.response.items.filter((item) => !known.has(item.id)),
    ]),
    nextCursor: page.response.nextCursor,
    status: 'ready',
    superGameState: page.response.superGameState,
  });
}

/** An error of an earlier generation is discarded like its page. */
export function failSeriesList(
  state: SeriesListState,
  generation: number,
  message: string,
): SeriesListState {
  if (generation !== state.generation) return state;
  return Object.freeze({ ...state, error: message, status: 'error' });
}

export function applySeriesListSuperGameState(
  state: SeriesListState,
  superGameState: SuperGameStateResponse,
): SeriesListState {
  return Object.freeze({ ...state, superGameState });
}

/** Whether a series belongs on a list loaded with these filters. */
export function seriesMatchesFilters(
  series: Pick<
    SuperGameSeriesResponse,
    'completeness' | 'runVerification' | 'superSymbolId'
  >,
  filters: SeriesFilters,
): boolean {
  if (
    filters.completeness !== 'all' &&
    series.completeness !== filters.completeness
  ) {
    return false;
  }
  if (
    filters.runVerification !== 'all' &&
    series.runVerification !== filters.runVerification
  ) {
    return false;
  }
  if (filters.defined === 'defined') return series.superSymbolId !== null;
  if (filters.defined === 'undefined') return series.superSymbolId === null;
  return true;
}

/**
 * A changed series replaces its row; a row that no longer matches the active
 * filters (a symbol was set under „Do zdefiniowania” or cleared under „Z super
 * symbolem”) is removed. `nextCursor` stays valid: it is the trigger number of
 * the last row of the loaded pages, not an offset.
 */
export function replaceSeriesInList(
  state: SeriesListState,
  series: SuperGameSeriesResponse,
): SeriesListState {
  if (!state.items.some((item) => item.id === series.id)) return state;
  const matches = seriesMatchesFilters(series, state.filters);
  return Object.freeze({
    ...state,
    items: Object.freeze(
      matches
        ? state.items.map((item) => (item.id === series.id ? series : item))
        : state.items.filter((item) => item.id !== series.id),
    ),
  });
}

// --- State of the published generation ---------------------------------

export function isSeriesGenerationStale(
  superGameState: SuperGameStateResponse | null,
): boolean {
  return superGameState !== null && !superGameState.fresh;
}

/** The banner of a stale generation; `null` when the series are current. */
export function superGameStateBanner(
  superGameState: SuperGameStateResponse | null,
): string | null {
  return isSeriesGenerationStale(superGameState)
    ? 'Serie w trakcie przeliczania. Widać ostatnią opublikowaną generację; wynik może się zmienić po przeliczeniu.'
    : null;
}

export function shouldPollSeriesState(
  superGameState: SuperGameStateResponse | null,
): boolean {
  return isSeriesGenerationStale(superGameState);
}

/** The text of the toast after „Przelicz serie”. */
export function deriveResultMessage(
  response: Pick<SuperGameSeriesDeriveResponse, 'deduplicated' | 'jobId'>,
): string {
  return response.deduplicated
    ? `Przeliczanie serii jest już zakolejkowane (job ${response.jobId}).`
    : `Zakolejkowano przeliczanie serii (job ${response.jobId}).`;
}

// --- Series view: carousel of positions --------------------------------

export type SeriesPositionRole = 'trigger' | 'retrigger' | 'spin';

export interface SeriesPositionCard {
  readonly sequenceNumber: number;
  readonly role: SeriesPositionRole;
  /** 0 for the trigger, then 1… in series order (retriggers included). */
  readonly positionInSeries: number;
  /** The position has no board (a known gap or beyond the layouts). */
  readonly missing: boolean;
  /** The API returned no entry: the position lies beyond the last layout. */
  readonly outOfRange: boolean;
  readonly board: SuperGameSeriesBoardResponse | null;
}

/**
 * One card per position `trigger … start + length − 1`, in order. Positions
 * the API left out (beyond `expectedLayoutCount`) become empty cards too, so
 * the carousel always shows the whole series.
 */
export function buildSeriesPositionCards(
  series: Pick<
    SuperGameSeriesResponse,
    | 'length'
    | 'retriggerSequenceNumbers'
    | 'startSequenceNumber'
    | 'triggerSequenceNumber'
  >,
  boards: readonly SuperGameSeriesBoardResponse[],
): readonly SeriesPositionCard[] {
  const bySequence = new Map(
    boards.map((board) => [board.sequenceNumber, board] as const),
  );
  const retriggers = new Set(series.retriggerSequenceNumbers);
  const last = series.startSequenceNumber + series.length - 1;
  const cards: SeriesPositionCard[] = [];
  for (
    let sequenceNumber = series.triggerSequenceNumber;
    sequenceNumber <= last;
    sequenceNumber += 1
  ) {
    const board = bySequence.get(sequenceNumber) ?? null;
    const role: SeriesPositionRole =
      sequenceNumber === series.triggerSequenceNumber
        ? 'trigger'
        : retriggers.has(sequenceNumber)
          ? 'retrigger'
          : 'spin';
    cards.push(
      Object.freeze({
        board: board !== null && !board.missing ? board : null,
        missing: board === null || board.missing,
        outOfRange: board === null,
        positionInSeries: sequenceNumber - series.triggerSequenceNumber,
        role,
        sequenceNumber,
      }),
    );
  }
  return Object.freeze(cards);
}

export function seriesPositionCardLabel(card: SeriesPositionCard): string {
  const base =
    card.role === 'trigger'
      ? 'Wyzwalacz'
      : card.role === 'retrigger'
        ? `Retrigger · pozycja ${card.positionInSeries}`
        : `Spin ${card.positionInSeries}`;
  return `${base} · #${card.sequenceNumber}`;
}

export function missingCardLabel(card: SeriesPositionCard): string {
  return card.outOfRange
    ? 'brak planszy (poza zakresem układów gry)'
    : 'brak planszy';
}

export type SeriesNotice = {
  readonly kind: 'success' | 'error' | 'info';
  readonly text: string;
};

export interface SeriesViewState {
  readonly series: SuperGameSeriesResponse;
  readonly cards: readonly SeriesPositionCard[];
  readonly activeIndex: number;
  /** The symbol chosen but not yet saved; `null` means „no symbol”. */
  readonly candidateSymbolId: string | null;
  readonly saving: boolean;
  readonly notice: SeriesNotice | null;
  readonly superGameState: SuperGameStateResponse | null;
}

export function createSeriesViewState(
  response: SuperGameSeriesBoardsResponse,
): SeriesViewState {
  return Object.freeze({
    activeIndex: 0,
    candidateSymbolId: response.series.superSymbolId,
    cards: buildSeriesPositionCards(response.series, response.boards),
    notice: null,
    saving: false,
    series: response.series,
    superGameState: response.superGameState,
  });
}

export function activeSeriesCard(
  state: SeriesViewState,
): SeriesPositionCard | null {
  return state.cards[state.activeIndex] ?? null;
}

export function moveSeriesPosition(
  state: SeriesViewState,
  direction: -1 | 1,
): SeriesViewState {
  return goToSeriesPosition(state, state.activeIndex + direction);
}

export function goToSeriesPosition(
  state: SeriesViewState,
  index: number,
): SeriesViewState {
  if (state.cards.length === 0) return state;
  const activeIndex = Math.min(state.cards.length - 1, Math.max(0, index));
  return activeIndex === state.activeIndex
    ? state
    : Object.freeze({ ...state, activeIndex });
}

/** Indexes of the cards next to the active one, to prefetch their images. */
export function seriesNeighbourIndexes(
  state: SeriesViewState,
): readonly number[] {
  return [-1, 1]
    .map((offset) => state.activeIndex + offset)
    .filter((index) => index >= 0 && index < state.cards.length);
}

/**
 * A fresh answer for the opened series (after a conflict or a refresh): the
 * active position is kept by sequence number, the candidate is reset to the
 * saved symbol so that a stale choice is never saved over a newer one.
 */
export function applySeriesRefresh(
  state: SeriesViewState,
  response: SuperGameSeriesBoardsResponse,
): SeriesViewState {
  const cards = buildSeriesPositionCards(response.series, response.boards);
  const active = state.cards[state.activeIndex];
  const index =
    active === undefined
      ? 0
      : cards.findIndex(
          (card) => card.sequenceNumber === active.sequenceNumber,
        );
  return Object.freeze({
    ...state,
    activeIndex: index >= 0 ? index : 0,
    candidateSymbolId: response.series.superSymbolId,
    cards,
    saving: false,
    series: response.series,
    superGameState: response.superGameState,
  });
}

export function applySeriesViewSuperGameState(
  state: SeriesViewState,
  superGameState: SuperGameStateResponse,
): SeriesViewState {
  return Object.freeze({ ...state, superGameState });
}

// --- Super symbol choice ------------------------------------------------

/**
 * Only ordinary symbols can be a super symbol: active, not Wild and not a
 * super game trigger. Catalog order, which is the order of the shortcuts.
 */
export function ordinarySuperSymbols(
  symbols: readonly SymbolResponse[],
): readonly SymbolResponse[] {
  return symbols
    .filter(
      (symbol) =>
        symbol.status === 'active' &&
        !symbol.isWildcard &&
        symbol.superGameTriggerCount === null,
    )
    .sort((a, b) => a.displayOrder - b.displayOrder);
}

/** The active symbols that start the super game, whose cells are marked. */
export function triggerSymbols(
  symbols: readonly SymbolResponse[],
): readonly SymbolResponse[] {
  return symbols.filter(
    (symbol) =>
      symbol.status === 'active' && symbol.superGameTriggerCount !== null,
  );
}

/** Indexes (0–14, row-major) of the board cells that hold a trigger symbol. */
export function triggerCellIndexes(
  symbolCodes: readonly (string | null)[],
  triggerCodes: readonly string[],
): readonly number[] {
  const codes = new Set(triggerCodes);
  const indexes: number[] = [];
  symbolCodes.forEach((code, index) => {
    if (code !== null && codes.has(code)) indexes.push(index);
  });
  return indexes;
}

export function selectSuperSymbolCandidate(
  state: SeriesViewState,
  symbolId: string | null,
): SeriesViewState {
  if (state.saving || state.candidateSymbolId === symbolId) return state;
  return Object.freeze({ ...state, candidateSymbolId: symbolId, notice: null });
}

export function cancelSuperSymbolCandidate(
  state: SeriesViewState,
): SeriesViewState {
  if (state.saving) return state;
  if (
    state.candidateSymbolId === state.series.superSymbolId &&
    state.notice === null
  ) {
    return state;
  }
  return Object.freeze({
    ...state,
    candidateSymbolId: state.series.superSymbolId,
    notice: null,
  });
}

export function isSuperSymbolCandidateDirty(state: SeriesViewState): boolean {
  return state.candidateSymbolId !== state.series.superSymbolId;
}

export type SuperSymbolSaveBlock =
  | { readonly reason: 'saving'; readonly message: string }
  | { readonly reason: 'unchanged'; readonly message: string }
  | { readonly reason: 'unknown_symbol'; readonly message: string }
  | { readonly reason: 'not_ordinary'; readonly message: string };

/**
 * Why the candidate cannot be saved, or `null` when it can. A trigger symbol
 * or Wild can be picked as a candidate (shortcuts follow the catalog) but
 * never saved: the API refuses it too (`SUPER_SYMBOL_NOT_ORDINARY`).
 */
export function superSymbolSaveBlock(
  state: SeriesViewState,
  symbols: readonly SymbolResponse[],
): SuperSymbolSaveBlock | null {
  if (state.saving) {
    return { message: 'Zapis jest w toku.', reason: 'saving' };
  }
  if (!isSuperSymbolCandidateDirty(state)) {
    return { message: 'Brak zmiany do zapisania.', reason: 'unchanged' };
  }
  if (state.candidateSymbolId === null) return null;
  const symbol = symbols.find((item) => item.id === state.candidateSymbolId);
  if (symbol === undefined) {
    return {
      message: 'Wybrany symbol nie należy do tej gry.',
      reason: 'unknown_symbol',
    };
  }
  if (
    symbol.status !== 'active' ||
    symbol.isWildcard ||
    symbol.superGameTriggerCount !== null
  ) {
    return {
      message: `Symbol ${symbol.name} (${symbol.code}) jest Wild, uruchamia supergrę albo jest zarchiwizowany. Super symbolem może być tylko zwykły symbol.`,
      reason: 'not_ordinary',
    };
  }
  return null;
}

export interface SuperSymbolSaveRequest {
  readonly symbolId: string | null;
  readonly expectedRevision: number;
}

/** Starts a save: the request is bound to the revision shown on screen. */
export function beginSuperSymbolSave(
  state: SeriesViewState,
  symbols: readonly SymbolResponse[],
): { state: SeriesViewState; request: SuperSymbolSaveRequest } | null {
  if (superSymbolSaveBlock(state, symbols) !== null) return null;
  return {
    request: {
      expectedRevision: state.series.revision,
      symbolId: state.candidateSymbolId,
    },
    state: Object.freeze({ ...state, notice: null, saving: true }),
  };
}

/** Same blocking as `beginSuperSymbolSave`, as a notice for the operator. */
export function blockSuperSymbolSave(
  state: SeriesViewState,
  block: SuperSymbolSaveBlock,
): SeriesViewState {
  if (block.reason === 'unchanged' || block.reason === 'saving') return state;
  return Object.freeze({
    ...state,
    notice: { kind: 'error' as const, text: block.message },
  });
}

export function applySuperSymbolSaved(
  state: SeriesViewState,
  updated: SuperGameSeriesResponse,
  symbols: readonly SymbolResponse[],
): SeriesViewState {
  const symbol = symbols.find((item) => item.id === updated.superSymbolId);
  return Object.freeze({
    ...state,
    candidateSymbolId: updated.superSymbolId,
    notice: {
      kind: 'success' as const,
      text:
        updated.superSymbolId === null
          ? `Wyczyszczono super symbol serii od #${updated.triggerSequenceNumber}.`
          : `Zapisano super symbol ${symbol?.name ?? updated.superSymbolId} dla serii od #${updated.triggerSequenceNumber}.`,
    },
    saving: false,
    series: updated,
  });
}

/**
 * A revision conflict: nothing was written. The candidate returns to the
 * saved symbol until the fresh series arrives (`applySeriesRefresh`).
 */
export function applySuperSymbolConflict(
  state: SeriesViewState,
): SeriesViewState {
  return Object.freeze({
    ...state,
    candidateSymbolId: state.series.superSymbolId,
    notice: {
      kind: 'error' as const,
      text: 'Seria została zmieniona w międzyczasie. Nic nie zapisano; pokazuję aktualny stan, wybierz symbol ponownie.',
    },
    saving: false,
  });
}

export function applySuperSymbolFailure(
  state: SeriesViewState,
  message: string,
): SeriesViewState {
  return Object.freeze({
    ...state,
    notice: { kind: 'error' as const, text: message },
    saving: false,
  });
}

export function setSeriesNotice(
  state: SeriesViewState,
  notice: SeriesNotice | null,
): SeriesViewState {
  return Object.freeze({ ...state, notice });
}

// --- Three independent badges ------------------------------------------

export type SeriesBadgeTone = 'ok' | 'warning' | 'neutral';

export interface SeriesBadge {
  readonly id: 'completeness' | 'symbol' | 'verification';
  readonly label: string;
  readonly tone: SeriesBadgeTone;
  readonly title: string;
}

/**
 * Completeness, symbol and run verification are independent: saving a symbol
 * changes only the second one.
 */
export function seriesBadges(
  series: Pick<
    SuperGameSeriesResponse,
    'completeness' | 'runVerification' | 'superSymbolId'
  >,
  symbols: readonly Pick<SymbolResponse, 'code' | 'id' | 'name'>[],
): readonly [SeriesBadge, SeriesBadge, SeriesBadge] {
  const symbol =
    series.superSymbolId === null
      ? undefined
      : symbols.find((item) => item.id === series.superSymbolId);
  return [
    series.completeness === 'complete'
      ? {
          id: 'completeness',
          label: 'Kompletna',
          title: 'Wszystkie pozycje serii mają znane plansze.',
          tone: 'ok',
        }
      : {
          id: 'completeness',
          label: 'Niekompletna',
          title:
            'Seria ma pozycje bez planszy albo kończy się za ostatnią znaną planszą.',
          tone: 'warning',
        },
    series.superSymbolId === null
      ? {
          id: 'symbol',
          label: 'Do zdefiniowania',
          title: 'Super symbol tej serii nie został jeszcze wybrany.',
          tone: 'warning',
        }
      : {
          id: 'symbol',
          label: `Symbol: ${symbol?.name ?? 'zdefiniowany'}`,
          title: 'Super symbol wybrany przez operatora.',
          tone: 'ok',
        },
    series.runVerification === 'verified'
      ? {
          id: 'verification',
          label: 'Przebieg zweryfikowany',
          title:
            'Wyzwalacz i retriggery opierają się wyłącznie na decyzjach człowieka.',
          tone: 'ok',
        }
      : {
          id: 'verification',
          label: 'Przebieg niezweryfikowany',
          title:
            'Wyzwalacz albo retrigger opiera się na predykcji symboli, nie na decyzji człowieka.',
          tone: 'warning',
        },
  ];
}

/** Short row label of a series in the list. */
export function seriesRangeLabel(
  series: Pick<
    SuperGameSeriesResponse,
    'endSequenceNumber' | 'startSequenceNumber' | 'triggerSequenceNumber'
  >,
): string {
  return `#${series.triggerSequenceNumber} → #${series.startSequenceNumber}–${series.endSequenceNumber}`;
}

// --- Errors -------------------------------------------------------------

const SERIES_ERROR_MESSAGES: Readonly<Record<string, string>> = {
  BOARD_SEARCH_PROJECTION_INCOMPLETE:
    'Projekcja wyszukiwania plansz tej gry nie jest gotowa. Dokończ przeliczanie projekcji i spróbuj ponownie.',
  SUPER_GAME_SERIES_NOT_FOUND:
    'Seria nie istnieje (mogła zniknąć po przeliczeniu serii).',
  SUPER_SYMBOL_NOT_FOUND: 'Wybrany symbol nie należy do tej gry.',
  SUPER_SYMBOL_NOT_ORDINARY:
    'Super symbolem może być tylko zwykły symbol: nie Wild, nie symbol uruchamiający supergrę i nie zarchiwizowany.',
};

export const SUPER_GAME_SERIES_REVISION_CONFLICT =
  'SUPER_GAME_SERIES_REVISION_CONFLICT';

function errorCode(error: unknown): string | null {
  return typeof error === 'object' &&
    error !== null &&
    'code' in error &&
    typeof error.code === 'string'
    ? error.code
    : null;
}

export function isSeriesRevisionConflict(error: unknown): boolean {
  return errorCode(error) === SUPER_GAME_SERIES_REVISION_CONFLICT;
}

export function isSeriesNotFound(error: unknown): boolean {
  return errorCode(error) === 'SUPER_GAME_SERIES_NOT_FOUND';
}

/** Polish message of an API error of the series routes. */
export function superGameSeriesErrorMessage(
  error: unknown,
  fallback: string,
): string {
  const code = errorCode(error);
  if (code === null) return fallback;
  const known = SERIES_ERROR_MESSAGES[code];
  if (known !== undefined) return `${known} (${code})`;
  const message =
    typeof error === 'object' &&
    error !== null &&
    'message' in error &&
    typeof error.message === 'string'
      ? error.message
      : null;
  return message === null ? fallback : `${message} (${code})`;
}

// --- Rules version used to read the board symbols ----------------------

/**
 * The board detail needs a rules version. The Admin uses its newest draft,
 * else its newest published version (as the main workspace does), so that
 * trigger cells can be marked also in a game that has no published rules.
 */
export function pickSeriesRulesVersion(
  versions: readonly {
    readonly id: string;
    readonly status: string;
    readonly version: number;
  }[],
): string | null {
  const newest = (status: string) =>
    versions
      .filter((version) => version.status === status)
      .sort((a, b) => b.version - a.version)[0];
  return (newest('draft') ?? newest('published'))?.id ?? null;
}

export interface SeriesRulesVersionOption {
  readonly id: string;
  readonly version: number;
  readonly status: 'draft' | 'published';
}

/** Draft and published rules versions, newest first, for the lines window. */
export function seriesRulesVersionOptions(
  versions: readonly {
    readonly id: string;
    readonly status: string;
    readonly version: number;
  }[],
): readonly SeriesRulesVersionOption[] {
  return versions
    .flatMap<SeriesRulesVersionOption>((version) =>
      version.status === 'draft' || version.status === 'published'
        ? [{ id: version.id, status: version.status, version: version.version }]
        : [],
    )
    .sort((a, b) => b.version - a.version);
}
