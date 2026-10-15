'use client';

import { useEffect, useState } from 'react';
import { archivePendingCommand } from './new-game-create-command';

export function PendingCommandRecovery({
  namespace,
  onRecovered,
  refreshToken,
}: {
  readonly namespace: string;
  readonly refreshToken?: unknown;
  readonly onRecovered: () => void;
}) {
  const [present, setPresent] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    let cancelled = false;
    Promise.resolve().then(() => {
      if (cancelled) return;
      try {
        setPresent(localStorage.getItem(namespace) !== null);
      } catch {
        setError(
          'Nie można odczytać pamięci poleceń. Nie wysłano nowego polecenia.',
        );
      }
    });
    return () => {
      cancelled = true;
    };
  }, [namespace, refreshToken]);
  function abandon() {
    try {
      archivePendingCommand(localStorage, namespace);
      setPresent(false);
      setConfirming(false);
      setError('');
      onRecovered();
    } catch {
      setError(
        'Nie udało się trwale zachować archiwum lub usunąć wpisu. Polecenie pozostaje; nie wysłano nowego.',
      );
    }
  }
  return (
    <aside aria-label="Odzyskiwanie zapisanego polecenia">
      {error ? <p role="alert">{error}</p> : null}
      {!present ? null : confirming ? (
        <>
          <p>
            Gra lub przypisanie mogły już zostać zapisane na serwerze.
            Porzucenie lokalnego polecenia nie cofnie zapisu. Najpierw zachowamy
            surową treść w archiwum tej przeglądarki. Sprawdź katalog gier przed
            nowym tworzeniem.
          </p>
          <button type="button" onClick={abandon}>
            Potwierdzam: zachowaj archiwum i porzuć polecenie
          </button>
          <button type="button" onClick={() => setConfirming(false)}>
            Wróć do ponawiania
          </button>
        </>
      ) : (
        <button type="button" onClick={() => setConfirming(true)}>
          Porzuć zapisane polecenie…
        </button>
      )}
    </aside>
  );
}
