'use client';

/* Symbol icons are local Admin API assets, not Next static media. */
/* eslint-disable @next/next/no-img-element */

import type {
  AdminApiClient,
  ApproximateWinResponse,
  BoardSearchShareQueryEntryResponse,
  SymbolResponse,
} from '@game-predictor/admin-api-client';
import {
  ApproximateWinBalanceChart,
  type BoardSearchDataSource,
} from '@game-predictor/board-search-ui';
import { useCallback, useEffect, useRef, useState } from 'react';

import {
  boardSearchQueryFollowUpRange,
  type BoardSearchQueryRange,
  boardSearchQueryPatternCells,
} from './board-search-share-query-log-state';
import {
  boardSearchShareErrorMessage,
  formatBoardSearchShareDate,
} from './board-search-share-state';

export type BoardSearchShareQueryLogClient = Pick<
  AdminApiClient,
  | 'deleteBoardSearchShareQuery'
  | 'listBoardSearchShareQueries'
  | 'listSymbols'
  | 'symbolImageAssetUrl'
> &
  Pick<BoardSearchDataSource, 'getBoardSearchApproximateWin'>;

type LogState =
  | { readonly kind: 'loading' }
  | { readonly kind: 'error'; readonly message: string }
  | {
      readonly kind: 'ready';
      readonly entries: readonly BoardSearchShareQueryEntryResponse[];
      readonly nextCursor: string | null;
      readonly loadingMore: boolean;
      readonly loadError: string | null;
    };

/** Each entry draws a chart, so the pages are short. */
const PAGE_SIZE = 10;
/** The recipient's stake is not recorded (D-472): base stake, in złote. */
const CHART_DISPLAY = { stakeGrosze: null, unit: 'pln' } as const;

/**
 * One share link's searches (D-472, D-478), newest first: the pattern the
 * recipient entered as a 3 × 5 board and, when they opened the approximate
 * win, its balance chart. An entry can be replayed in this Admin's board
 * search or deleted from the log.
 */
export function BoardSearchShareQueryLog({
  client,
  gameId,
  onReplay,
  sessionId,
}: {
  readonly client: BoardSearchShareQueryLogClient;
  readonly gameId: string;
  readonly onReplay: (eventId: string) => void;
  readonly sessionId: string;
}) {
  const [state, setState] = useState<LogState>({ kind: 'loading' });
  const [symbols, setSymbols] = useState<readonly SymbolResponse[]>([]);
  const [deleteCandidateId, setDeleteCandidateId] = useState<string | null>(
    null,
  );
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const requestId = useRef(0);
  // Range calculations are heavy: the charts load one after another.
  const chartQueue = useRef<Promise<void>>(Promise.resolve());
  const enqueueChart = useCallback((task: () => Promise<void>) => {
    chartQueue.current = chartQueue.current.then(task);
  }, []);

  const loadPage = useCallback(
    async (before: string | null) => {
      const current = ++requestId.current;
      try {
        const result = await client.listBoardSearchShareQueries(sessionId, {
          ...(before === null ? {} : { before }),
          kind: 'search',
          limit: PAGE_SIZE,
        });
        if (current !== requestId.current) return;
        if (result.error !== undefined || result.data === undefined) {
          const message = boardSearchShareErrorMessage(
            result.error,
            'Nie udało się pobrać dziennika zapytań.',
          );
          // A failed older page keeps what is already shown.
          setState((previous) =>
            before !== null && previous.kind === 'ready'
              ? { ...previous, loadError: message, loadingMore: false }
              : { kind: 'error', message },
          );
          return;
        }
        const page = result.data;
        setState((previous) => ({
          entries:
            before !== null && previous.kind === 'ready'
              ? [...previous.entries, ...page.entries]
              : page.entries,
          kind: 'ready',
          loadError: null,
          loadingMore: false,
          nextCursor: page.nextCursor,
        }));
      } catch {
        if (current === requestId.current) {
          const message = 'Połączenie z lokalnym Admin API zostało przerwane.';
          setState((previous) =>
            before !== null && previous.kind === 'ready'
              ? { ...previous, loadError: message, loadingMore: false }
              : { kind: 'error', message },
          );
        }
      }
    },
    [client, sessionId],
  );

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      void loadPage(null);
      void client
        .listSymbols(gameId)
        .then((result) => setSymbols(result.data ?? []))
        .catch(() => setSymbols([]));
    }, 0);
    return () => window.clearTimeout(timeout);
  }, [client, gameId, loadPage]);

  async function confirmDelete(entryId: string) {
    if (deletingId !== null) return;
    setDeletingId(entryId);
    setDeleteError(null);
    let message: string | null = null;
    try {
      const result = await client.deleteBoardSearchShareQuery(entryId);
      if (result.error !== undefined) {
        message = boardSearchShareErrorMessage(
          result.error,
          'Nie udało się usunąć wpisu.',
        );
      }
    } catch {
      message = 'Połączenie z lokalnym Admin API zostało przerwane.';
    }
    setDeletingId(null);
    if (message !== null) {
      setDeleteError(message);
      return;
    }
    setDeleteCandidateId(null);
    setState((previous) =>
      previous.kind === 'ready'
        ? {
            ...previous,
            entries: previous.entries.filter((entry) => entry.id !== entryId),
          }
        : previous,
    );
  }

  if (state.kind === 'loading') {
    return <p role="status">Wczytywanie dziennika…</p>;
  }
  if (state.kind === 'error') {
    return (
      <p className="feedbackBanner feedbackBannerError" role="alert">
        {state.message}
      </p>
    );
  }
  if (state.entries.length === 0 && state.nextCursor === null) {
    return (
      <p className="boardSearchShareEmpty">
        Przez ten link nie wykonano jeszcze żadnego wyszukiwania.
      </p>
    );
  }
  const symbolByCode = new Map(symbols.map((symbol) => [symbol.code, symbol]));
  return (
    <div className="boardSearchShareQueryLog">
      {deleteError !== null ? (
        <p className="feedbackBanner feedbackBannerError" role="alert">
          {deleteError}
        </p>
      ) : null}
      <ol>
        {state.entries.map((entry) => {
          const pattern = boardSearchQueryPatternCells(entry);
          const range = boardSearchQueryFollowUpRange(entry);
          return (
            <li className="boardSearchShareQuery" key={entry.id}>
              <div className="boardSearchShareQueryHeader">
                <time dateTime={entry.occurredAt}>
                  {formatBoardSearchShareDate(entry.occurredAt)}
                </time>
                {entry.outcomeCode !== 'ok' ? (
                  <span className="boardSearchShareQueryFailed">
                    błąd {entry.outcomeCode}
                  </span>
                ) : null}
                <span className="boardSearchShareQueryActions">
                  {deleteCandidateId === entry.id ? (
                    <>
                      <button
                        className="textButton"
                        disabled={deletingId === entry.id}
                        onClick={() => setDeleteCandidateId(null)}
                        type="button"
                      >
                        Anuluj
                      </button>
                      <button
                        className="dangerButton"
                        disabled={deletingId === entry.id}
                        onClick={() => void confirmDelete(entry.id)}
                        type="button"
                      >
                        {deletingId === entry.id ? 'Usuwanie…' : 'Usuń wpis'}
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        className="textButton"
                        onClick={() => onReplay(entry.id)}
                        type="button"
                      >
                        Odtwórz w wyszukiwarce
                      </button>
                      <button
                        className="textButton"
                        onClick={() => {
                          setDeleteError(null);
                          setDeleteCandidateId(entry.id);
                        }}
                        type="button"
                      >
                        Usuń
                      </button>
                    </>
                  )}
                </span>
              </div>
              <div className="boardSearchShareQueryBody">
                {pattern !== null ? (
                  <div
                    aria-label="Wzór zapytania 3 na 5"
                    className="boardSearchShareMiniBoard"
                    role="img"
                  >
                    {pattern.map((code, cellIndex) => {
                      const symbol =
                        code !== null && code !== '?'
                          ? symbolByCode.get(code)
                          : undefined;
                      return (
                        <span
                          className="boardSearchShareMiniCell"
                          key={cellIndex}
                          title={
                            code === null
                              ? 'puste'
                              : code === '?'
                                ? 'nieznany'
                                : (symbol?.name ?? code)
                          }
                        >
                          {symbol?.imagePath ? (
                            <img
                              alt=""
                              src={client.symbolImageAssetUrl(
                                gameId,
                                symbol.id,
                              )}
                            />
                          ) : code === null ? (
                            ''
                          ) : code === '?' ? (
                            '?'
                          ) : (
                            code.slice(0, 2)
                          )}
                        </span>
                      );
                    })}
                  </div>
                ) : null}
                {range !== null ? (
                  <QueryChart
                    client={client}
                    gameId={gameId}
                    enqueue={enqueueChart}
                    range={range}
                  />
                ) : (
                  <p className="boardSearchShareQueryNoChart">
                    Odbiorca nie otworzył wykresu dla tego wyszukiwania.
                  </p>
                )}
              </div>
            </li>
          );
        })}
      </ol>
      {state.loadError !== null ? (
        <p className="feedbackBanner feedbackBannerError" role="alert">
          {state.loadError}
        </p>
      ) : null}
      {state.nextCursor !== null ? (
        <button
          className="secondaryButton"
          disabled={state.loadingMore}
          onClick={() => {
            setState((previous) =>
              previous.kind === 'ready'
                ? { ...previous, loadingMore: true }
                : previous,
            );
            void loadPage(state.nextCursor);
          }}
          type="button"
        >
          {state.loadingMore ? 'Wczytywanie…' : 'Starsze wyszukiwania'}
        </button>
      ) : null}
    </div>
  );
}

type ChartState =
  | { readonly kind: 'loading' }
  | { readonly kind: 'error'; readonly message: string }
  | { readonly kind: 'ready'; readonly result: ApproximateWinResponse };

/** The balance chart of the range the recipient opened, computed now. */
function QueryChart({
  client,
  enqueue,
  gameId,
  range,
}: {
  readonly client: BoardSearchShareQueryLogClient;
  readonly enqueue: (task: () => Promise<void>) => void;
  readonly gameId: string;
  readonly range: BoardSearchQueryRange;
}) {
  const [state, setState] = useState<ChartState>({ kind: 'loading' });
  const { spinCount, startSequenceNumber } = range;

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      if (cancelled) return;
      try {
        const result = await client.getBoardSearchApproximateWin(gameId, {
          spinCount,
          startSequenceNumber,
        });
        if (cancelled) return;
        setState(
          result.error !== undefined || result.data === undefined
            ? {
                kind: 'error',
                message: boardSearchShareErrorMessage(
                  result.error,
                  'Nie udało się policzyć wykresu.',
                ),
              }
            : { kind: 'ready', result: result.data },
        );
      } catch {
        if (!cancelled) {
          setState({
            kind: 'error',
            message: 'Połączenie z lokalnym Admin API zostało przerwane.',
          });
        }
      }
    };
    enqueue(run);
    return () => {
      cancelled = true;
    };
  }, [client, enqueue, gameId, spinCount, startSequenceNumber]);

  return (
    <div className="boardSearchShareQueryChart">
      <p className="boardSearchShareQueryChartCaption">
        Plansza #{startSequenceNumber.toLocaleString('pl-PL')} ·{' '}
        {spinCount.toLocaleString('pl-PL')} spinów · stawka bazowa
      </p>
      {state.kind === 'loading' ? (
        <p role="status">Liczenie wykresu…</p>
      ) : state.kind === 'error' ? (
        <p className="boardSearchShareQueryFailed" role="alert">
          {state.message}
        </p>
      ) : (
        <ApproximateWinBalanceChart
          compact
          display={CHART_DISPLAY}
          result={state.result}
        />
      )}
    </div>
  );
}
