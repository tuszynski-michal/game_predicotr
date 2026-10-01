/**
 * Turning a share-link query log entry into a board search replay
 * (D-472, TASK-0771). Pure: the section applies the plan.
 */

export const BOARD_SEARCH_REPLAY_PARAMETER = 'boardSearchReplay';

export type BoardSearchReplayScope = 'all_searchable' | 'approved_only';

export type BoardSearchReplayPlan = {
  /** Changes for every replay, so the same entry can be replayed again. */
  readonly id: string;
  readonly cells: readonly {
    readonly cellIndex: number;
    readonly symbolCode: string | null;
  }[];
  readonly scope: BoardSearchReplayScope;
  readonly limit: number;
  readonly approximateWin: {
    readonly startSequenceNumber: number;
    readonly spinCount: number;
  } | null;
  readonly boardSequenceNumber: number | null;
};

export type BoardSearchReplayResult =
  | { readonly kind: 'plan'; readonly plan: BoardSearchReplayPlan }
  | { readonly kind: 'no_search'; readonly message: string };

type ReplayEvent = {
  readonly id: string;
  readonly kind: string;
  readonly request: Readonly<Record<string, unknown>>;
};

export type BoardSearchReplaySource = {
  readonly event: ReplayEvent;
  readonly search: ReplayEvent | null;
  readonly approximateWin: ReplayEvent | null;
};

const CELL = /^(\d{1,2}):(.+)$/;

/**
 * The pattern cells in the order they were recorded (`cellIndex:code|?`),
 * scope and limit of the search to run, plus the range and board to open.
 */
export function boardSearchReplayPlan(
  source: BoardSearchReplaySource,
  nonce: string,
): BoardSearchReplayResult {
  const search = source.search;
  if (search === null) {
    return {
      kind: 'no_search',
      message: describeMissingSearch(source.event),
    };
  }
  const cells = parseCells(search.request.cells);
  if (cells === null) {
    return {
      kind: 'no_search',
      message: 'Wzoru z tego wpisu nie da się odczytać.',
    };
  }
  const scope =
    search.request.scope === 'approved_only'
      ? 'approved_only'
      : 'all_searchable';
  const limit = positiveInteger(search.request.limit, 100) ?? 100;
  const range = source.approximateWin;
  const approximateWin =
    range === null
      ? null
      : (() => {
          const start = positiveInteger(range.request.startSequenceNumber);
          const spins = positiveInteger(range.request.spinCount);
          return start === null || spins === null
            ? null
            : { spinCount: spins, startSequenceNumber: start };
        })();
  const boardSequenceNumber =
    source.event.kind === 'board_detail'
      ? positiveInteger(source.event.request.sequenceNumber)
      : null;
  return {
    kind: 'plan',
    plan: {
      approximateWin,
      boardSequenceNumber,
      cells,
      id: `${source.event.id}:${nonce}`,
      limit,
      scope,
    },
  };
}

function describeMissingSearch(event: ReplayEvent): string {
  if (event.kind === 'approximate_win') {
    const start = positiveInteger(event.request.startSequenceNumber);
    const spins = positiveInteger(event.request.spinCount);
    return `Ten link nie wykonał wcześniej udanego wyszukiwania, więc wzoru nie da się odtworzyć. Parametry wpisu: plansza startowa #${start ?? '?'}, zakres ${spins ?? '?'} spinów.`;
  }
  if (event.kind === 'board_detail') {
    const board = positiveInteger(event.request.sequenceNumber);
    return `Ten link nie wykonał wcześniej udanego wyszukiwania, więc wzoru nie da się odtworzyć. Wpis dotyczy planszy #${board ?? '?'}.`;
  }
  return 'Wzoru z tego wpisu nie da się odczytać.';
}

function parseCells(
  value: unknown,
): { readonly cellIndex: number; readonly symbolCode: string | null }[] | null {
  if (!Array.isArray(value) || value.length === 0 || value.length > 15)
    return null;
  const cells: { cellIndex: number; symbolCode: string | null }[] = [];
  const seen = new Set<number>();
  for (const item of value) {
    if (typeof item !== 'string') return null;
    const match = CELL.exec(item);
    if (match === null) return null;
    const cellIndex = Number(match[1]);
    if (!Number.isInteger(cellIndex) || cellIndex < 0 || cellIndex > 14)
      return null;
    if (seen.has(cellIndex)) return null;
    seen.add(cellIndex);
    const code = match[2] ?? '';
    cells.push({ cellIndex, symbolCode: code === '?' ? null : code });
  }
  return cells;
}

function positiveInteger(value: unknown, max?: number): number | null {
  if (typeof value !== 'number' || !Number.isInteger(value) || value < 1)
    return null;
  if (max !== undefined && value > max) return null;
  return value;
}

/** The Admin URL that opens a replay (`?boardSearchReplay=<eventId>`). */
export function boardSearchReplayHref(
  currentHref: string,
  eventId: string,
): string {
  const url = new URL(currentHref);
  url.searchParams.set(BOARD_SEARCH_REPLAY_PARAMETER, eventId);
  return `${url.pathname}${url.search}${url.hash}`;
}

const EVENT_ID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function readBoardSearchReplayParameter(search: string): string | null {
  const value = new URLSearchParams(search).get(BOARD_SEARCH_REPLAY_PARAMETER);
  return value !== null && EVENT_ID.test(value) ? value : null;
}

export type BoardSearchReplayHandoff = {
  readonly gameId: string;
  readonly plan: BoardSearchReplayPlan | null;
  readonly message: string | null;
};

/**
 * The section took the plan over: drop it (a remount must not replay
 * again) and keep only a message that is still worth showing.
 */
export function consumeBoardSearchReplay(
  current: BoardSearchReplayHandoff | null,
  appliedId: string,
): BoardSearchReplayHandoff | null {
  if (
    current === null ||
    current.plan === null ||
    current.plan.id !== appliedId
  ) {
    return current;
  }
  return current.message === null ? null : { ...current, plan: null };
}
