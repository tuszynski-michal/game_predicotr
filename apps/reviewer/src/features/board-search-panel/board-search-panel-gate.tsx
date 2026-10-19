'use client';

import type { BoardSearchPanelContextResponse } from '@game-predictor/admin-api-client';
import { BoardSearchWorkspace } from '@game-predictor/board-search-ui';
import { useEffect, useMemo, useRef, useState } from 'react';
import { createBoardSearchShareDataSource } from '../board-search-share/board-search-share-data-source';
import {
  formatShareTimeLeft,
  shareErrorMessage,
} from '../board-search-share/board-search-share-state';

export function BoardSearchPanelGate({
  panelId,
}: {
  readonly panelId: string;
}) {
  const [context, setContext] =
    useState<BoardSearchPanelContextResponse | null>(null);
  const [sessionId, setSessionId] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);
  const [now, setNow] = useState(() => Date.now());
  const linkKey = useRef<string | null>(null);
  const base = `/board-search-panel-api/panels/${panelId}`;
  useEffect(() => {
    let cancelled = false;
    async function open() {
      if (!panelId) {
        setError('Nieprawidłowy link. Poproś o nowy.');
        setLoading(false);
        return;
      }
      if (linkKey.current === null) {
        const fragment = new URLSearchParams(window.location.hash.slice(1));
        linkKey.current = fragment.get('key');
        if (window.location.hash)
          window.history.replaceState(
            window.history.state,
            '',
            window.location.pathname + window.location.search,
          );
      }
      setLoading(true);
      setError('');
      try {
        const key = linkKey.current;
        const response = await fetch(`${base}/${key ? 'open' : 'context'}`, {
          method: key ? 'POST' : 'GET',
          credentials: 'same-origin',
          cache: 'no-store',
          signal: AbortSignal.timeout(12_000),
          ...(key
            ? {
                body: JSON.stringify({ linkKey: key }),
                headers: { 'Content-Type': 'application/json' },
              }
            : {}),
        });
        const data = await response.json();
        if (!response.ok)
          throw new Error(
            response.status === 401 || response.status === 404
              ? 'Link wygasł lub został zatrzymany. Otwórz otrzymany link ponownie.'
              : shareErrorMessage(data),
          );
        if (
          data.panelId !== panelId ||
          !Array.isArray(data.games) ||
          data.games.length === 0
        )
          throw new Error('Serwer zwrócił nieprawidłowy panel.');
        if (!cancelled) {
          setContext(data);
          setSessionId(data.games[0].sessionId);
          linkKey.current = null;
        }
      } catch (cause) {
        if (!cancelled)
          setError(
            cause instanceof Error
              ? cause.message
              : 'Nie udało się połączyć z panelem.',
          );
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void open();
    return () => {
      cancelled = true;
    };
  }, [panelId, base, attempt]);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 30_000);
    return () => window.clearInterval(timer);
  }, []);
  const source = useMemo(
    () =>
      createBoardSearchShareDataSource({
        sessionId,
        apiBase: `${base}/games/${sessionId}/api/v1/board-search-shares`,
        fetchImplementation: (input, init) =>
          fetch(input, { ...init, signal: AbortSignal.timeout(120_000) }),
        onUnauthorized: () =>
          setError(
            'Dostęp wygasł lub został zatrzymany. Otwórz otrzymany link ponownie.',
          ),
      }),
    [base, sessionId],
  );
  if (loading)
    return (
      <main className="reviewerAccessShell">
        <p role="status">Otwieranie panelu…</p>
      </main>
    );
  if (error || !context || new Date(context.expiresAt).getTime() <= now)
    return (
      <main className="reviewerAccessShell">
        <section className="reviewerAccessCard">
          <h1>Panel niedostępny</h1>
          <p role="alert">{error || 'Dostęp wygasł.'}</p>
          <button
            className="primaryButton"
            type="button"
            onClick={() => setAttempt((n) => n + 1)}
          >
            Spróbuj ponownie
          </button>
        </section>
      </main>
    );
  return (
    <main className="boardSearchShareApp">
      <header className="boardSearchShareHeader">
        <div>
          <strong>{context.label || 'Udostępnione gry'}</strong>
          <label className="boardSearchPanelGame">
            Gra{' '}
            <select
              aria-label="Gra"
              value={sessionId}
              onChange={(event) => {
                setSessionId(event.target.value);
              }}
            >
              {context.games.map((game) => (
                <option key={game.sessionId} value={game.sessionId}>
                  {game.gameName}
                </option>
              ))}
            </select>
          </label>
        </div>
        <p role="status">
          Dostęp wygasa za {formatShareTimeLeft(context.expiresAt, now)}.
          Zapytania i poprawki symboli są zapisywane.
        </p>
      </header>
      <BoardSearchWorkspace
        key={sessionId}
        client={source}
        gameId="shared"
        scopeKey={`panel:${panelId}:${sessionId}`}
        superGameSeries={{ client: source }}
      />
    </main>
  );
}
