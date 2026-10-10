'use client';

import type { BoardSearchSharePublicContextResponse } from '@game-predictor/admin-api-client';
import { BoardSearchWorkspace } from '@game-predictor/board-search-ui';
import {
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react';

import {
  BOARD_SEARCH_SHARE_API_BASE,
  BOARD_SEARCH_SHARE_GAME_ID,
  createBoardSearchShareDataSource,
} from './board-search-share-data-source';
import {
  formatShareTimeLeft,
  shareErrorMessage,
} from './board-search-share-state';

type GateState =
  | { readonly kind: 'checking' }
  | { readonly kind: 'locked' }
  | {
      readonly kind: 'ready';
      readonly context: BoardSearchSharePublicContextResponse;
    }
  | { readonly kind: 'ended'; readonly reason: 'expired' | 'stopped' };

/**
 * Code gate and the shared board search (D-471). The recipient is told
 * before entering the code that their queries are recorded and visible to
 * the link's owner (D-472).
 */
export function BoardSearchShareGate({
  sessionId,
}: {
  readonly sessionId: string;
}) {
  const [state, setState] = useState<GateState>({ kind: 'checking' });
  const [accessCode, setAccessCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const dataSource = useMemo(
    () =>
      createBoardSearchShareDataSource({
        sessionId,
        onUnauthorized: () =>
          setState((current) =>
            current.kind === 'ready'
              ? { kind: 'ended', reason: 'stopped' }
              : current,
          ),
      }),
    // A new data source (and fresh caches) for each unlocked session.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [sessionId, state.kind === 'ready' ? state.context.sessionId : null],
  );

  const loadContext = useCallback(async () => {
    try {
      const result = await dataSource.context();
      if (result.data === undefined) {
        setState({ kind: 'locked' });
        return;
      }
      if (result.data.sessionId !== sessionId) {
        setState({ kind: 'locked' });
        setError(
          'Ta przeglądarka ma dostęp do innego linku. Podaj kod tego linku.',
        );
        return;
      }
      setState({ context: result.data, kind: 'ready' });
    } catch {
      setState({ kind: 'locked' });
      setError('Nie udało się połączyć z serwerem aplikacji.');
    }
  }, [dataSource, sessionId]);

  useEffect(() => {
    if (sessionId === '') return;
    const timeout = window.setTimeout(() => void loadContext(), 0);
    return () => window.clearTimeout(timeout);
    // Only the first visit checks an existing cookie.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  async function unlock() {
    if (sessionId === '' || accessCode.trim() === '' || busy) return;
    setBusy(true);
    setError('');
    try {
      const response = await fetch(
        `${BOARD_SEARCH_SHARE_API_BASE}/sessions/${sessionId}/unlock`,
        {
          body: JSON.stringify({ accessCode: accessCode.trim().toUpperCase() }),
          cache: 'no-store',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          method: 'POST',
        },
      );
      if (!response.ok) {
        setError(
          shareErrorMessage(await response.json().catch(() => undefined)),
        );
        return;
      }
      const context =
        (await response.json()) as BoardSearchSharePublicContextResponse;
      if (context.sessionId !== sessionId) {
        setError(
          'Serwer zwrócił dostęp do innego linku. Dostęp został odrzucony.',
        );
        return;
      }
      setAccessCode('');
      setState({ context, kind: 'ready' });
    } catch {
      setError('Nie udało się połączyć z serwerem aplikacji.');
    } finally {
      setBusy(false);
    }
  }

  if (sessionId === '') {
    return (
      <ShareShell>
        <p className="eyebrow">Udostępniona wyszukiwarka plansz</p>
        <h1>Nieprawidłowy link</h1>
        <p className="lead">
          Poproś osobę, która udostępniła wyszukiwarkę, o nowy link.
        </p>
      </ShareShell>
    );
  }

  if (state.kind === 'checking') {
    return (
      <ShareShell>
        <p className="eyebrow">Udostępniona wyszukiwarka plansz</p>
        <h1>Sprawdzanie dostępu…</h1>
      </ShareShell>
    );
  }

  if (state.kind === 'ended') {
    return (
      <ShareShell>
        <p className="eyebrow">Udostępniona wyszukiwarka plansz</p>
        <h1>
          {state.reason === 'expired'
            ? 'Dostęp wygasł'
            : 'Dostęp został zakończony'}
        </h1>
        <p className="lead">
          {state.reason === 'expired'
            ? 'Czas dostępu do tej wyszukiwarki minął.'
            : 'Link został zatrzymany albo dostęp wygasł.'}{' '}
          Poproś osobę, która udostępniła wyszukiwarkę, o nowy link.
        </p>
      </ShareShell>
    );
  }

  if (state.kind === 'locked') {
    return (
      <ShareShell>
        <p className="eyebrow">Udostępniona wyszukiwarka plansz</p>
        <h1>Podaj kod dostępu</h1>
        <p className="lead">
          Kod otrzymasz od osoby, która udostępniła wyszukiwarkę.
        </p>
        <p className="boardSearchShareNotice" role="note">
          Zapytania wykonane przez ten link (wzór planszy, parametry i czas) są
          zapisywane i widoczne dla osoby, która go udostępniła. Poprawki
          symboli zapisują się od razu w bazie i trafiają do jej przeglądu.
        </p>
        <form
          className="boardSearchShareForm"
          onSubmit={(event) => {
            event.preventDefault();
            void unlock();
          }}
        >
          <label>
            <span>Kod dostępu</span>
            <input
              autoComplete="off"
              autoFocus
              maxLength={16}
              onChange={(event) => setAccessCode(event.currentTarget.value)}
              placeholder="XXXX-XXXX"
              spellCheck={false}
              value={accessCode}
            />
          </label>
          <button
            className="primaryButton"
            disabled={busy || accessCode.trim() === ''}
            type="submit"
          >
            {busy ? 'Sprawdzanie…' : 'Otwórz wyszukiwarkę'}
          </button>
        </form>
        {error ? (
          <p className="reviewerAccessError" role="alert">
            {error}
          </p>
        ) : null}
      </ShareShell>
    );
  }

  return (
    <main className="boardSearchShareApp">
      <header className="boardSearchShareHeader">
        <div>
          <p className="eyebrow">Udostępniona wyszukiwarka plansz</p>
          <strong>{state.context.gameName}</strong>
          {state.context.label ? <span> · {state.context.label}</span> : null}
        </div>
        <ShareExpiry
          expiresAt={state.context.expiresAt}
          onExpired={() => setState({ kind: 'ended', reason: 'expired' })}
        />
      </header>
      <BoardSearchWorkspace
        client={dataSource}
        gameId={BOARD_SEARCH_SHARE_GAME_ID}
      />
    </main>
  );
}

/** Its own component: the 30 s tick must not re-render the workspace. */
function ShareExpiry({
  expiresAt,
  onExpired,
}: {
  readonly expiresAt: string;
  readonly onExpired: () => void;
}) {
  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => {
    const tick = () => {
      const current = Date.now();
      setNowMs(current);
      if (new Date(expiresAt).getTime() <= current) onExpired();
    };
    const interval = window.setInterval(tick, 30_000);
    const first = window.setTimeout(tick, 0);
    return () => {
      window.clearInterval(interval);
      window.clearTimeout(first);
    };
  }, [expiresAt, onExpired]);
  return (
    <p role="status">
      Dostęp wygasa za {formatShareTimeLeft(expiresAt, nowMs)} · zapytania są
      zapisywane wraz z poprawkami symboli
    </p>
  );
}

function ShareShell({ children }: { readonly children: ReactNode }) {
  return (
    <main className="reviewerAccessShell">
      <section className="reviewerAccessCard" aria-live="polite">
        {children}
      </section>
    </main>
  );
}
