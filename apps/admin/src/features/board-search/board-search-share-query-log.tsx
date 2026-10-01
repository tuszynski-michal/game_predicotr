'use client';

/* Symbol icons are local Admin API assets, not Next static media. */
/* eslint-disable @next/next/no-img-element */

import type {
  AdminApiClient,
  BoardSearchShareQueryEntryResponse,
  SymbolResponse,
} from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useRef, useState } from 'react';

import {
  boardSearchQueryPatternCells,
  describeBoardSearchQueryEntry,
} from './board-search-share-query-log-state';
import {
  boardSearchShareErrorMessage,
  formatBoardSearchShareDate,
} from './board-search-share-state';

export type BoardSearchShareQueryLogClient = Pick<
  AdminApiClient,
  'listBoardSearchShareQueries' | 'listSymbols' | 'symbolImageAssetUrl'
>;

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

/**
 * One share link's query log (D-472): time, kind, the pattern as a 3 × 5
 * mini board, parameters and result, newest first, 50 per page. Every
 * entry can be replayed in this Admin's board search.
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
  const requestId = useRef(0);

  const loadPage = useCallback(
    async (before: string | null) => {
      const current = ++requestId.current;
      try {
        const result = await client.listBoardSearchShareQueries(
          sessionId,
          before === null ? {} : { before },
        );
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
  if (state.entries.length === 0) {
    return (
      <p className="boardSearchShareEmpty">
        Przez ten link nie wykonano jeszcze żadnego zapytania.
      </p>
    );
  }
  const symbolByCode = new Map(symbols.map((symbol) => [symbol.code, symbol]));
  return (
    <div className="boardSearchShareQueryLog">
      <ol>
        {state.entries.map((entry) => {
          const description = describeBoardSearchQueryEntry(entry);
          const pattern = boardSearchQueryPatternCells(entry);
          return (
            <li className="boardSearchShareQuery" key={entry.id}>
              <div className="boardSearchShareQueryHeader">
                <time dateTime={entry.occurredAt}>
                  {formatBoardSearchShareDate(entry.occurredAt)}
                </time>
                <strong>{description.title}</strong>
                {entry.outcomeCode !== 'ok' ? (
                  <span className="boardSearchShareQueryFailed">
                    błąd {entry.outcomeCode}
                  </span>
                ) : null}
              </div>
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
                            src={client.symbolImageAssetUrl(gameId, symbol.id)}
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
              <p className="boardSearchShareQueryDetails">
                {description.details}
              </p>
              <button
                className="textButton"
                onClick={() => onReplay(entry.id)}
                type="button"
              >
                Odtwórz w wyszukiwarce
              </button>
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
          {state.loadingMore ? 'Wczytywanie…' : 'Starsze zapytania'}
        </button>
      ) : null}
    </div>
  );
}
