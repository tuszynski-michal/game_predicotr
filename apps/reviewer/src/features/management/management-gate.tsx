'use client';

import type { ManagementSessionContext } from '@game-predictor/admin-api-client';
import { ManagementWorkspace } from '@game-predictor/board-search-ui/management';
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  createManagementPublicAdapter,
  type ManagementPublicAdapter,
} from './management-public-adapter';
import {
  managementAccessMessage,
  managementStorageNamespace,
} from './management-access-state';
import { formatShareTimeLeft } from '../board-search-share/board-search-share-state';

/** Ending access keeps the same mounted workspace, its draft and acknowledged history. */
export function ManagementGate({
  sessionId,
  adapter: injected,
}: {
  sessionId: string;
  adapter?: ManagementPublicAdapter;
}) {
  const [context, setContext] = useState<ManagementSessionContext | null>(null);
  const [state, setState] = useState<'checking' | 'locked' | 'ready' | 'ended'>(
    'checking',
  );
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const adapter = useMemo(
    () =>
      injected ??
      createManagementPublicAdapter({
        sessionId,
        onEnded: () => setState('ended'),
      }),
    [injected, sessionId],
  );
  useEffect(() => {
    let active = true;
    if (!sessionId) return;
    void adapter
      .context()
      .then((result) => {
        if (!active) return;
        if (result.data?.sessionId === sessionId) {
          setContext(result.data);
          setState('ready');
        } else setState('locked');
      })
      .catch(() => {
        if (active) {
          setState('locked');
          setError('Nie udało się sprawdzić dostępu.');
        }
      });
    return () => {
      active = false;
    };
  }, [adapter, sessionId]);
  useEffect(() => {
    if (!context) return;
    const tick = () => {
      if (!adapter.active() || Date.parse(context.expiresAt) <= Date.now()) {
        adapter.end();
        setState('ended');
      }
    };
    tick();
    const interval = window.setInterval(tick, 1000);
    return () => window.clearInterval(interval);
  }, [adapter, context]);
  const unlock = async () => {
    if (!sessionId || !code.trim() || busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError('');
    try {
      const result = await adapter.unlock(code.trim().toUpperCase());
      if (!result.data || result.data.sessionId !== sessionId) {
        setError(managementAccessMessage(result.error));
        return;
      }
      setCode('');
      setContext(result.data);
      setState('ready');
    } catch {
      setError('Nie udało się połączyć z aplikacją.');
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };
  if (!sessionId || !context)
    return (
      <main className="reviewerAccessShell management-access-gate">
        <section className="reviewerAccessCard" aria-live="polite">
          <p className="eyebrow">Panel Administracyjny</p>
          {!sessionId ? (
            <>
              <h1>Nieprawidłowy link</h1>
              <p>Poproś o nowy link.</p>
            </>
          ) : state === 'checking' ? (
            <h1>Sprawdzanie dostępu…</h1>
          ) : (
            <>
              <h1>Podaj kod dostępu</h1>
              <p>
                Osoba udostępniająca panel przekazuje kod osobno. Zmiany i
                wyszukiwania są zapisywane z nazwą tego linku.
              </p>
              <p>
                Poprawki symboli zapisują się od razu w bieżących danych gry.
                Układ, zakres i przypięte spiny zapisuje przycisk „Zapisz
                układ”.
              </p>
              <form
                className="boardSearchShareForm"
                onSubmit={(event) => {
                  event.preventDefault();
                  void unlock();
                }}
              >
                <label>
                  Kod dostępu
                  <input
                    autoComplete="off"
                    maxLength={16}
                    placeholder="XXXX-XXXX"
                    spellCheck={false}
                    value={code}
                    onChange={(event) => setCode(event.target.value)}
                  />
                </label>
                <button
                  className="primaryButton"
                  disabled={busy || !code.trim()}
                >
                  {busy ? 'Sprawdzanie…' : 'Otwórz panel'}
                </button>
              </form>
              {error && <p role="alert">{error}</p>}
            </>
          )}
        </section>
      </main>
    );
  return (
    <main className="boardSearchShareApp management-public-panel">
      <header className="boardSearchShareHeader">
        <strong>{context.label}</strong>
        <ManagementExpiry expiresAt={context.expiresAt} />
      </header>
      {state === 'ended' && (
        <p className="feedbackBanner" role="alert">
          Dostęp zakończony. Zachowano wyświetlone wyniki, historię, szkic i
          oczekujący zapis. Poproś o nowy dostęp.
        </p>
      )}
      <ManagementWorkspace
        client={adapter.client}
        gameClientForMachine={adapter.forMachine}
        storageNamespace={managementStorageNamespace(sessionId)}
        accessAllowed={state === 'ready'}
      />
    </main>
  );
}
function ManagementExpiry({ expiresAt }: { expiresAt: string }) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const interval = window.setInterval(() => setNow(Date.now()), 30000);
    return () => window.clearInterval(interval);
  }, []);
  return (
    <p role="status">Dostęp wygasa za {formatShareTimeLeft(expiresAt, now)}</p>
  );
}
