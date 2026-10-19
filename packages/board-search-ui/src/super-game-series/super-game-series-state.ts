/**
 * Pure state of the super game series view (TASK-0934, D-535; shared since
 * TASK-1058): the carousel of positions, the cas-protected super symbol
 * choice, the retrigger review before a save, the badges and the errors of
 * the series routes. Everything here is free of React and the DOM so that it
 * is covered by `node --test`. The Admin's list (filters, pagination, derive)
 * stays in the Admin and re-exports this module.
 */
import type {
  SuperGameSeriesBoardResponse,
  SuperGameSeriesBoardsResponse,
  SuperGameSeriesResponse,
  SuperGameStateResponse,
  SymbolResponse,
} from '@game-predictor/admin-api-client';

/** The state of the published generation is polled while it is stale. */
export const SERIES_STATE_POLL_INTERVAL_MS = 5000;

// --- Filters shared by the list and the "next series" search -------------

export type CompletenessFilter = 'all' | 'complete' | 'incomplete';
export type RunVerificationFilter = 'all' | 'verified' | 'unverified';
export type DefinedFilter = 'all' | 'defined' | 'undefined';

export interface SeriesFilters {
  readonly completeness: CompletenessFilter;
  readonly runVerification: RunVerificationFilter;
  readonly defined: DefinedFilter;
  /**
   * Range of the trigger board numbers (TASK-1055), both ends included;
   * `null` (or a missing field) leaves that end open.
   */
  readonly fromSequence?: number | null;
  readonly toSequence?: number | null;
}

export const DEFAULT_SERIES_FILTERS: SeriesFilters = Object.freeze({
  completeness: 'all',
  defined: 'all',
  fromSequence: null,
  runVerification: 'all',
  toSequence: null,
});

export interface SeriesBoardRange {
  readonly from: number | null;
  readonly to: number | null;
}

export function seriesBoardRange(filters: SeriesFilters): SeriesBoardRange {
  return { from: filters.fromSequence ?? null, to: filters.toSequence ?? null };
}

export function hasSeriesBoardRange(filters: SeriesFilters): boolean {
  const range = seriesBoardRange(filters);
  return range.from !== null || range.to !== null;
}

/** Whether the trigger of a series lies in the board range of the filters. */
export function seriesInBoardRange(
  series: Pick<SuperGameSeriesResponse, 'triggerSequenceNumber'>,
  filters: SeriesFilters,
): boolean {
  const { from, to } = seriesBoardRange(filters);
  return (
    (from === null || series.triggerSequenceNumber >= from) &&
    (to === null || series.triggerSequenceNumber <= to)
  );
}

/** The range as a short label, e.g. „#1–#1000”, „od #500”, „do #1000”. */
export function seriesBoardRangeLabel(filters: SeriesFilters): string | null {
  const { from, to } = seriesBoardRange(filters);
  if (from !== null && to !== null) return `#${from}–#${to}`;
  if (from !== null) return `od #${from}`;
  if (to !== null) return `do #${to}`;
  return null;
}

/**
 * The first listed series other than the opened one, without a symbol and
 * inside the board range of the list, or `null`.
 */
export function pickNextUndefinedSeries(
  items: readonly SuperGameSeriesResponse[],
  openedSeriesId: string,
  filters: SeriesFilters = DEFAULT_SERIES_FILTERS,
): SuperGameSeriesResponse | null {
  return (
    items.find(
      (item) =>
        item.id !== openedSeriesId &&
        item.superSymbolId === null &&
        seriesInBoardRange(item, filters),
    ) ?? null
  );
}

/** Whether the list filters narrow the search for the next series. */
export function nextUndefinedSeriesFiltered(filters: SeriesFilters): boolean {
  return (
    filters.completeness !== 'all' ||
    filters.runVerification !== 'all' ||
    hasSeriesBoardRange(filters)
  );
}

/** The notice when no other series without a super symbol is left. */
export function noUndefinedSeriesLeftMessage(filters: SeriesFilters): string {
  const range = seriesBoardRangeLabel(filters);
  if (range !== null) {
    return `Nie ma innej serii bez super symbolu w zakresie plansz ${range} (i w pozostałych filtrach wybranych na liście).`;
  }
  return nextUndefinedSeriesFiltered(filters)
    ? 'Nie ma innej serii bez super symbolu w filtrach kompletności i wiarygodności przebiegu wybranych na liście.'
    : 'Nie ma innej serii bez super symbolu. Wszystkie pozostałe serie mają super symbol.';
}

/** The toast when the search went back to the beginning of the list. */
export function undefinedSeriesWrappedMessage(
  fromTrigger: number,
  next: Pick<SuperGameSeriesResponse, 'triggerSequenceNumber'>,
): string {
  return `Za serią od #${fromTrigger} nie ma już serii bez super symbolu. Otwieram pierwszą od początku listy: seria od #${next.triggerSequenceNumber}.`;
}

/** The notice that blocks leaving a series with an unsaved symbol choice. */
export const UNSAVED_SUPER_SYMBOL_NOTICE =
  'Wybrany symbol nie jest zapisany. Zapisz go (Enter) albo anuluj (Esc), zanim przejdziesz do następnej serii.';

// --- State of the published generation ---------------------------------

export function isSeriesGenerationStale(
  superGameState: SuperGameStateResponse | null,
): boolean {
  return superGameState !== null && !superGameState.fresh;
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
  /**
   * Sequence numbers of the retrigger boards the operator confirmed with
   * `Enter` before a symbol is saved (TASK-1053). Screen state only.
   */
  readonly confirmedRetriggers: readonly number[];
}

export function createSeriesViewState(
  response: SuperGameSeriesBoardsResponse,
): SeriesViewState {
  return Object.freeze({
    activeIndex: 0,
    candidateSymbolId: response.series.superSymbolId,
    cards: buildSeriesPositionCards(response.series, response.boards),
    confirmedRetriggers: Object.freeze([]),
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

/** The index of the card of a sequence number, or `null` when not listed. */
export function seriesCardIndexOf(
  state: Pick<SeriesViewState, 'cards'>,
  sequenceNumber: number,
): number | null {
  const index = state.cards.findIndex(
    (card) => card.sequenceNumber === sequenceNumber,
  );
  return index >= 0 ? index : null;
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
 * saved symbol so that a stale choice is never saved over a newer one. The
 * boards may have changed, so retrigger confirmations start again.
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
    confirmedRetriggers: Object.freeze([]),
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

// --- Retrigger review before a save (TASK-1053) -------------------------

export interface RetriggerReviewStep {
  /** Index of the retrigger card to show next. */
  readonly index: number;
  /** 1-based number of that retrigger among all retriggers of the series. */
  readonly ordinal: number;
  readonly total: number;
  /** The active card is the retrigger itself: `Enter` confirms it. */
  readonly confirmsActive: boolean;
  /** No other retrigger is left after this one: its `Enter` also saves. */
  readonly last: boolean;
}

/** Card indexes of the retrigger boards of the series, in order. */
export function retriggerCardIndexes(state: SeriesViewState): number[] {
  return state.cards.flatMap((card, index) =>
    card.role === 'retrigger' ? [index] : [],
  );
}

/**
 * What the next `Enter` does before a symbol is saved: a chosen symbol is
 * saved only after every retrigger board was shown and confirmed. `null`
 * means the save goes ahead (no retriggers left, or the symbol is cleared).
 */
export function nextRetriggerReviewStep(
  state: SeriesViewState,
): RetriggerReviewStep | null {
  if (state.candidateSymbolId === null) return null;
  const retriggers = retriggerCardIndexes(state);
  const confirmed = new Set(state.confirmedRetriggers);
  const pending = retriggers.filter(
    (index) => !confirmed.has(state.cards[index]?.sequenceNumber ?? -1),
  );
  const active = state.cards[state.activeIndex];
  const confirmsActive =
    active?.role === 'retrigger' && !confirmed.has(active.sequenceNumber);
  const target = confirmsActive ? state.activeIndex : pending[0];
  if (target === undefined) return null;
  return {
    confirmsActive,
    index: target,
    last: confirmsActive && pending.length === 1,
    ordinal: retriggers.indexOf(target) + 1,
    total: retriggers.length,
  };
}

/**
 * One `Enter` of the retrigger review: the active unconfirmed retrigger is
 * confirmed, then the next unconfirmed retrigger is shown. `null` means
 * every retrigger is confirmed and the symbol can be saved now.
 */
export function advanceRetriggerReview(
  state: SeriesViewState,
): SeriesViewState | null {
  const step = nextRetriggerReviewStep(state);
  if (step === null) return null;
  const confirmedRetriggers = step.confirmsActive
    ? Object.freeze([
        ...state.confirmedRetriggers,
        state.cards[state.activeIndex]?.sequenceNumber ?? -1,
      ])
    : state.confirmedRetriggers;
  const confirmedState = Object.freeze({ ...state, confirmedRetriggers });
  const next = nextRetriggerReviewStep(confirmedState);
  if (next === null) return null;
  const card = confirmedState.cards[next.index];
  return Object.freeze({
    ...confirmedState,
    activeIndex: next.index,
    notice: {
      kind: 'info' as const,
      text: `Retrigger ${next.ordinal} z ${next.total} (#${card?.sequenceNumber ?? '?'}): sprawdź planszę i potwierdź klawiszem Enter. Symbol zostanie zapisany po potwierdzeniu ostatniego retriggera.`,
    },
  });
}

/** The label of the save button for the next `Enter`. */
export function superSymbolSaveLabel(state: SeriesViewState): string {
  if (state.saving) return 'Zapisuję…';
  const step = isSuperSymbolCandidateDirty(state)
    ? nextRetriggerReviewStep(state)
    : null;
  if (step === null) return 'Zapisz (Enter)';
  if (!step.confirmsActive) {
    return `Do retriggera ${step.ordinal} z ${step.total} (Enter)`;
  }
  return step.last
    ? `Potwierdź retrigger ${step.ordinal} z ${step.total} i zapisz (Enter)`
    : `Potwierdź retrigger ${step.ordinal} z ${step.total} (Enter)`;
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

/** The confirmation of a saved (or cleared) super symbol. */
export function superSymbolSavedMessage(
  updated: Pick<
    SuperGameSeriesResponse,
    'superSymbolId' | 'triggerSequenceNumber'
  >,
  symbols: readonly Pick<SymbolResponse, 'id' | 'name'>[],
): string {
  const symbol = symbols.find((item) => item.id === updated.superSymbolId);
  return updated.superSymbolId === null
    ? `Wyczyszczono super symbol serii od #${updated.triggerSequenceNumber}.`
    : `Zapisano super symbol ${symbol?.name ?? updated.superSymbolId} dla serii od #${updated.triggerSequenceNumber}.`;
}

export function applySuperSymbolSaved(
  state: SeriesViewState,
  updated: SuperGameSeriesResponse,
  symbols: readonly SymbolResponse[],
): SeriesViewState {
  return Object.freeze({
    ...state,
    candidateSymbolId: updated.superSymbolId,
    notice: {
      kind: 'success' as const,
      text: superSymbolSavedMessage(updated, symbols),
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
          title:
            'Super symbol wybrany przez operatora albo odbiorcę linku udostępniania.',
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
