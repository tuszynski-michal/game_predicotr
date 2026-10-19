/**
 * Pure state of the „Supergry” section (TASK-0934, D-535): the series list
 * with cursor pagination and filters, the derive request and the rules
 * version of the board reads. The state of the opened series (carousel,
 * super symbol, retrigger review, badges, errors) lives in the shared package
 * since TASK-1058 and is re-exported here. Everything here is free of React
 * and the DOM so that it is covered by `node --test`.
 */
import type {
  ListSuperGameSeriesData,
  SuperGameSeriesCountsResponse,
  SuperGameSeriesDeriveResponse,
  SuperGameSeriesListResponse,
  SuperGameSeriesResponse,
  SuperGameStateResponse,
} from '@game-predictor/admin-api-client';
import {
  DEFAULT_SERIES_FILTERS,
  type SeriesBoardRange,
  type SeriesFilters,
  isSeriesGenerationStale,
  seriesBoardRange,
  seriesInBoardRange,
} from '@game-predictor/board-search-ui/super-game-series/super-game-series-state';

export * from '@game-predictor/board-search-ui/super-game-series/super-game-series-state';

export const SERIES_PAGE_LIMIT = 50;

// --- List: filters, query and pagination -------------------------------

/**
 * The cursor that starts a list at the range: the API returns the series
 * whose trigger is greater than the cursor, so the range starts after
 * `from − 1`. A later cursor (a next page) is kept.
 */
function rangeCursor(
  filters: SeriesFilters,
  cursor: string | null,
): string | null {
  const { from } = seriesBoardRange(filters);
  if (from === null) return cursor;
  const start = from - 1;
  return cursor !== null && Number(cursor) >= start ? cursor : String(start);
}

export type SeriesBoardRangeInput =
  | { readonly ok: true; readonly range: SeriesBoardRange }
  | { readonly ok: false; readonly message: string };

const BOARD_NUMBER_PATTERN = /^[0-9]{1,9}$/;

/** Parses the „Plansze od / do” fields; an empty field is an open end. */
export function parseSeriesBoardRange(
  fromText: string,
  toText: string,
): SeriesBoardRangeInput {
  const parse = (text: string): number | null | 'invalid' => {
    const value = text.trim();
    if (value === '') return null;
    if (!BOARD_NUMBER_PATTERN.test(value)) return 'invalid';
    const number = Number(value);
    return number >= 1 ? number : 'invalid';
  };
  const from = parse(fromText);
  const to = parse(toText);
  if (from === 'invalid' || to === 'invalid') {
    return {
      message: 'Numer planszy musi być liczbą całkowitą od 1.',
      ok: false,
    };
  }
  if (from !== null && to !== null && from > to) {
    return {
      message: 'Początek zakresu nie może być większy niż jego koniec.',
      ok: false,
    };
  }
  return { ok: true, range: { from, to } };
}

export const COMPLETENESS_FILTER_OPTIONS: readonly {
  readonly value: SeriesFilters['completeness'];
  readonly label: string;
}[] = [
  { value: 'all', label: 'Wszystkie' },
  { value: 'complete', label: 'Kompletne' },
  { value: 'incomplete', label: 'Niekompletne' },
];

export const RUN_VERIFICATION_FILTER_OPTIONS: readonly {
  readonly value: SeriesFilters['runVerification'];
  readonly label: string;
}[] = [
  { value: 'all', label: 'Wszystkie' },
  { value: 'verified', label: 'Zweryfikowane' },
  { value: 'unverified', label: 'Niezweryfikowane' },
];

export const DEFINED_FILTER_OPTIONS: readonly {
  readonly value: SeriesFilters['defined'];
  readonly label: string;
}[] = [
  { value: 'all', label: 'Wszystkie' },
  { value: 'defined', label: 'Z super symbolem' },
  { value: 'undefined', label: 'Do zdefiniowania' },
];

export function seriesFiltersKey(filters: SeriesFilters): string {
  const { from, to } = seriesBoardRange(filters);
  return `${filters.completeness}|${filters.runVerification}|${filters.defined}|${from ?? ''}-${to ?? ''}`;
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
  const rangedCursor = rangeCursor(filters, cursor);
  if (rangedCursor !== null) query.cursor = rangedCursor;
  return query;
}

/**
 * A page cut to the end of the board range: series with a later trigger are
 * dropped and, once the range end is reached, there is no next page.
 */
export function clipSeriesPageToRange(
  response: SuperGameSeriesListResponse,
  filters: SeriesFilters,
): SuperGameSeriesListResponse {
  const { to } = seriesBoardRange(filters);
  if (to === null) return response;
  const items = response.items.filter(
    (item) => item.triggerSequenceNumber <= to,
  );
  const last = items[items.length - 1];
  const reachedEnd =
    items.length < response.items.length ||
    (last !== undefined && last.triggerSequenceNumber >= to);
  return {
    ...response,
    items,
    nextCursor: reachedEnd ? null : response.nextCursor,
  };
}

/**
 * The query for the next series without a super symbol (TASK-1053): the
 * completeness and run verification filters of the list are kept, the symbol
 * filter is always „Do zdefiniowania”. The cursor is a trigger number, so
 * `afterTrigger` gives the first such series after it; `null` starts from
 * the beginning of the list. Two rows, so that a search from the beginning
 * still finds another series when the first one is the opened series.
 */
export function nextUndefinedSeriesQuery(
  filters: SeriesFilters,
  afterTrigger: number | null,
): SeriesListQuery {
  return seriesListQuery(
    { ...filters, defined: 'undefined' },
    afterTrigger === null ? null : String(afterTrigger),
    2,
  );
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
  rawPage: SeriesListPage,
): SeriesListState {
  if (rawPage.generation !== state.generation) return state;
  const page = {
    ...rawPage,
    response: clipSeriesPageToRange(rawPage.response, state.filters),
  };
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
    | 'completeness'
    | 'runVerification'
    | 'superSymbolId'
    | 'triggerSequenceNumber'
  >,
  filters: SeriesFilters,
): boolean {
  if (!seriesInBoardRange(series, filters)) return false;
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
