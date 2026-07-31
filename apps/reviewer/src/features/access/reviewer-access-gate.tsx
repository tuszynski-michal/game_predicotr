'use client';

import type { ReviewerSessionScopeResponse } from '@game-predictor/admin-api-client';
import { useMemo, useState } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';
import { apiErrorMessage } from '@/features/catalog/catalog-api-error';
import { OperationalReviewWorkspace } from '@/features/operational-reviews/operational-review-workspace';

export function ReviewerAccessGate({
  apiBaseUrl,
  sessionId,
}: {
  readonly apiBaseUrl: string;
  readonly sessionId: string;
}) {
  const api = useMemo(
    () => createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl],
  );
  const [accessCode, setAccessCode] = useState('');
  const [scope, setScope] = useState<ReviewerSessionScopeResponse | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function unlock() {
    if (sessionId === '' || accessCode.trim() === '' || busy) return;
    setBusy(true);
    setError('');
    try {
      const result = await api.unlockReviewerSession(sessionId, {
        accessCode: accessCode.trim(),
      });
      if (result.error !== undefined || result.data === undefined) {
        setError(
          apiErrorMessage(
            result.error,
            'Nie udało się otworzyć sesji zatwierdzania.',
          ),
        );
        return;
      }
      setScope(result.data);
      setAccessCode('');
    } catch {
      setError('Nie udało się połączyć z serwerem aplikacji.');
    } finally {
      setBusy(false);
    }
  }

  if (scope !== null) {
    return (
      <main className="reviewerShell">
        <OperationalReviewWorkspace
          apiBaseUrl={apiBaseUrl}
          gameId={scope.gameId}
          importJobId={scope.importJobId}
        />
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
            <span>Reviewer</span>
          </div>
        </div>
        <p className="eyebrow">Prywatna sesja zatwierdzania</p>
        <h1>Podaj kod dostępu</h1>
        <p className="lead">
          Kod jest wyświetlany osobno w panelu administratora i nie znajduje się
          w linku.
        </p>
        {sessionId === '' ? (
          <p className="reviewerAccessError" role="alert">
            Link nie zawiera identyfikatora sesji. Utwórz nowy link w panelu
            admina.
          </p>
        ) : (
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void unlock();
            }}
          >
            <label htmlFor="reviewer-access-code">Unikalny kod</label>
            <input
              autoComplete="one-time-code"
              autoFocus
              id="reviewer-access-code"
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
              disabled={accessCode.trim() === '' || busy}
              type="submit"
            >
              {busy ? 'Sprawdzanie…' : 'Otwórz aplikację'}
            </button>
          </form>
        )}
        {error ? (
          <p className="reviewerAccessError" role="alert">
            {error}
          </p>
        ) : null}
        <small>Dostęp ograniczony kodem, grą i wybranym importem</small>
      </section>
    </main>
  );
}
