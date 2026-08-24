'use client';

import { useCallback, useEffect, useState } from 'react';
import { RemoteManualSelectionWorkspaceFoundation } from './remote-manual-selection-workspace-foundation';
import {
  fetchRemoteSelectionWithTimeout,
  readOrCreateRemoteSelectionClientInstance,
} from './remote-selection-client-runtime';

const CLIENT_INSTANCE_KEY = 'gp.remote-manual-selection.client-instance.v1';
const API_BASE = '/selection-api/api/v1/remote-manual-selections';
const HEARTBEAT_INTERVAL_MS = 20_000;
const CONTEXT_REFRESH_INTERVAL_MS = 10_000;
let cachedClientInstanceId = '';

type RemoteSelectionContext = {
  readonly expiresAt: string;
  readonly isWriter: boolean;
  readonly revision: number;
  readonly sessionId: string;
  readonly status: 'active';
  readonly writerActive: boolean;
  readonly writerLeaseExpiresAt: string | null;
  readonly lastHeartbeatAt: string | null;
};

type ApiError = {
  readonly code?: string;
  readonly message?: string;
};

export function RemoteManualSelectionAccessGate({
  sessionId,
}: {
  readonly sessionId: string;
}) {
  const [accessCode, setAccessCode] = useState('');
  const [clientInstanceId] = useState(() =>
    typeof window === 'undefined' ? '' : readClientInstance(),
  );
  const [context, setContext] = useState<RemoteSelectionContext | null>(null);
  const [checkingSession, setCheckingSession] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const loadContext = useCallback(
    async (silent = false) => {
      if (clientInstanceId === '' || sessionId === '') {
        setCheckingSession(false);
        return;
      }
      try {
        const response = await fetchRemoteSelectionWithTimeout(
          `${API_BASE}/context`,
          {
            cache: 'no-store',
            credentials: 'same-origin',
            headers: { 'X-Remote-Selection-Client': clientInstanceId },
          },
        );
        if (response.status === 401) {
          setContext(null);
          if (!silent) setError('');
          return;
        }
        if (!response.ok) {
          if (!silent) setError(await responseError(response));
          return;
        }
        const nextContext = (await response.json()) as RemoteSelectionContext;
        if (nextContext.sessionId !== sessionId) {
          setContext(null);
          if (!silent) {
            setError(
              'Ta przeglądarka ma dostęp do innej sesji. Podaj kod bieżącej sesji.',
            );
          }
          return;
        }
        setContext(nextContext);
        if (!silent) setError('');
      } catch {
        if (!silent) setError('Nie udało się połączyć z serwerem aplikacji.');
      } finally {
        if (!silent) setCheckingSession(false);
      }
    },
    [clientInstanceId, sessionId],
  );

  useEffect(() => {
    const timeout = window.setTimeout(() => void loadContext(), 0);
    return () => window.clearTimeout(timeout);
  }, [loadContext]);

  const heartbeatLease = useCallback(async () => {
    if (clientInstanceId === '' || sessionId === '') return;
    try {
      const response = await fetchRemoteSelectionWithTimeout(
        `${API_BASE}/sessions/${sessionId}/writer-lease/heartbeat`,
        {
          body: JSON.stringify({ clientInstanceId }),
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          method: 'POST',
        },
      );
      if (response.status === 401 || response.status === 409) {
        await loadContext(true);
        setError(await responseError(response));
        return;
      }
      if (!response.ok) return;
      setContext((await response.json()) as RemoteSelectionContext);
    } catch {
      // A later heartbeat retries. Durable local decisions remain in IndexedDB.
    }
  }, [clientInstanceId, loadContext, sessionId]);

  const hasContext = context !== null;
  const isWriter = context?.isWriter === true;
  useEffect(() => {
    if (!hasContext || clientInstanceId === '') return;
    const interval = window.setInterval(
      () => {
        if (isWriter) {
          void heartbeatLease();
        } else {
          void loadContext(true);
        }
      },
      isWriter ? HEARTBEAT_INTERVAL_MS : CONTEXT_REFRESH_INTERVAL_MS,
    );
    return () => window.clearInterval(interval);
  }, [clientInstanceId, hasContext, heartbeatLease, isWriter, loadContext]);

  async function unlock() {
    if (
      sessionId === '' ||
      clientInstanceId === '' ||
      accessCode.trim() === '' ||
      busy
    ) {
      return;
    }
    setBusy(true);
    setError('');
    try {
      const response = await fetchRemoteSelectionWithTimeout(
        `${API_BASE}/sessions/${sessionId}/unlock`,
        {
          body: JSON.stringify({
            accessCode: accessCode.trim().toUpperCase(),
            clientInstanceId,
          }),
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          method: 'POST',
        },
      );
      if (!response.ok) {
        setError(await responseError(response));
        return;
      }
      const nextContext = (await response.json()) as RemoteSelectionContext;
      if (nextContext.sessionId !== sessionId) {
        setError(
          'Serwer zwrócił kontekst innej sesji. Dostęp został odrzucony.',
        );
        return;
      }
      setContext(nextContext);
      setAccessCode('');
    } catch {
      setError('Nie udało się połączyć z serwerem aplikacji.');
    } finally {
      setBusy(false);
      setCheckingSession(false);
    }
  }

  async function updateLease(action: 'heartbeat' | 'takeover', silent = false) {
    if (context === null || clientInstanceId === '' || (busy && !silent))
      return;
    if (!silent) {
      setBusy(true);
      setError('');
    }
    try {
      const response = await fetchRemoteSelectionWithTimeout(
        `${API_BASE}/sessions/${context.sessionId}/writer-lease/${action}`,
        {
          body: JSON.stringify({ clientInstanceId }),
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          method: 'POST',
        },
      );
      if (!response.ok) {
        if (response.status === 401) setContext(null);
        if (!silent) setError(await responseError(response));
        return;
      }
      setContext((await response.json()) as RemoteSelectionContext);
    } catch {
      if (!silent) setError('Nie udało się odświeżyć prawa do zapisu.');
    } finally {
      if (!silent) setBusy(false);
    }
  }

  if (checkingSession) {
    return (
      <main className="reviewerAccessShell">
        <section className="reviewerAccessCard" aria-live="polite">
          <p className="eyebrow">Zdalna ręczna selekcja</p>
          <h1>Sprawdzanie sesji…</h1>
        </section>
      </main>
    );
  }

  if (context !== null) {
    return (
      <main className="reviewerAccessShell">
        <section className="reviewerAccessCard remoteSelectionReadyCard">
          <div className="brand">
            <span className="brandMark" aria-hidden="true">
              GP
            </span>
            <div>
              <strong>Game Predictor</strong>
              <span>Ręczna selekcja zdjęć</span>
            </div>
          </div>
          <p className="eyebrow">Sesja aktywna</p>
          <h1>
            {context.isWriter
              ? 'Możesz rozpocząć pracę'
              : 'Tryb tylko do odczytu'}
          </h1>
          <p className="lead">
            {context.isWriter
              ? 'Ta karta posiada wyłączne prawo zapisu.'
              : context.writerActive
                ? 'Inna karta ma obecnie prawo zapisu. Przejęcie będzie możliwe po wygaśnięciu lease.'
                : 'Prawo zapisu jest wolne i może zostać bezpiecznie przejęte.'}
          </p>
          {!context.isWriter ? (
            <button
              className="primaryButton"
              disabled={busy || context.writerActive}
              onClick={() => void updateLease('takeover')}
              type="button"
            >
              {busy ? 'Przejmowanie…' : 'Przejmij prawo zapisu'}
            </button>
          ) : null}
          {error ? (
            <p className="reviewerAccessError" role="alert">
              {error}
            </p>
          ) : null}
          <RemoteManualSelectionWorkspaceFoundation
            clientInstanceId={clientInstanceId}
            serverWriter={context.isWriter}
            sessionId={context.sessionId}
          />
        </section>
      </main>
    );
  }

  return (
    <main className="reviewerAccessShell">
      <section className="reviewerAccessCard">
        <div className="brand">
          <span className="brandMark" aria-hidden="true">
            GP
          </span>
          <div>
            <strong>Game Predictor</strong>
            <span>Ręczna selekcja zdjęć</span>
          </div>
        </div>
        <p className="eyebrow">Prywatna sesja selekcji</p>
        <h1>Podaj kod dostępu</h1>
        <p className="lead">
          Kod nie znajduje się w linku. Odbierz go od właściciela aplikacji
          osobnym kanałem.
        </p>
        {sessionId === '' ? (
          <p className="reviewerAccessError" role="alert">
            Link nie zawiera prawidłowego identyfikatora sesji.
          </p>
        ) : (
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void unlock();
            }}
          >
            <label htmlFor="remote-selection-access-code">Kod dostępu</label>
            <input
              autoComplete="one-time-code"
              autoFocus
              id="remote-selection-access-code"
              maxLength={32}
              onChange={(event) =>
                setAccessCode(event.target.value.toUpperCase())
              }
              placeholder="XXXX-XXXX"
              spellCheck={false}
              value={accessCode}
            />
            <button
              className="primaryButton"
              disabled={
                accessCode.trim() === '' || clientInstanceId === '' || busy
              }
              type="submit"
            >
              {busy ? 'Sprawdzanie…' : 'Otwórz selekcję'}
            </button>
          </form>
        )}
        {error ? (
          <p className="reviewerAccessError" role="alert">
            {error}
          </p>
        ) : null}
        <small>
          Dostęp jest ograniczony do jednej purpose-scoped sesji selekcji.
        </small>
      </section>
    </main>
  );
}

async function responseError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as ApiError;
    if (typeof payload.message === 'string' && payload.message.trim() !== '') {
      return payload.message;
    }
  } catch {
    // A stable local fallback is safer than rendering an upstream HTML body.
  }
  return `Żądanie nie powiodło się (${response.status}).`;
}

function readClientInstance(): string {
  if (cachedClientInstanceId !== '') return cachedClientInstanceId;
  cachedClientInstanceId = readOrCreateRemoteSelectionClientInstance(
    CLIENT_INSTANCE_KEY,
    window.sessionStorage,
    window.crypto,
  );
  return cachedClientInstanceId;
}
