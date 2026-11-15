'use client';

import type {
  AdminApiClient,
  JobResponse,
} from '@game-predictor/admin-api-client';
import { useEffect, useRef, useState } from 'react';

import { apiErrorMessage } from '../catalog/catalog-api-error';

export type CorrectedGridSymbolReinferenceClient = Pick<
  AdminApiClient,
  'previewPendingSymbolReinference' | 'startPendingSymbolReinference' | 'getJob'
>;

/** Explicit local-owner operation; never starts as a side effect of a save. */
export function CorrectedGridSymbolReinference({
  api,
  gameId,
  importJobId,
  refreshKey,
}: {
  readonly api: CorrectedGridSymbolReinferenceClient;
  readonly gameId: string;
  readonly importJobId?: string | undefined;
  readonly refreshKey: number;
}) {
  const [count, setCount] = useState<number | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [job, setJob] = useState<JobResponse | null>(null);
  const submitting = useRef(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    void api
      .previewPendingSymbolReinference(gameId, {
        correctedGeometry: true,
        ...(importJobId === undefined ? {} : { importJobId }),
        signal: controller.signal,
      })
      .then((result) => {
        if (!active) return;
        if (result.error !== undefined || result.data === undefined) {
          setCount(null);
          setError(
            apiErrorMessage(
              result.error,
              'Nie udało się pobrać liczby plansz.',
            ),
          );
        } else {
          setCount(result.data.pendingCount);
          setError('');
        }
      })
      .catch(() => {
        if (active) {
          setCount(null);
          setError('Nie udało się pobrać liczby poprawionych plansz.');
        }
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [api, gameId, importJobId, refreshKey, refresh]);

  const activeJob =
    job !== null && !['completed', 'failed', 'cancelled'].includes(job.status);
  const start = async () => {
    if (submitting.current || !count || activeJob) return;
    submitting.current = true;
    setBusy(true);
    setError('');
    try {
      const result = await api.startPendingSymbolReinference(gameId, {
        correctedGeometry: true,
        ...(importJobId === undefined ? {} : { importJobId }),
      });
      if (!mounted.current) return;
      if (result.error !== undefined || result.data === undefined) {
        const previousId = existingJobId(result.error);
        if (previousId !== null) {
          const previous = await api.getJob(previousId);
          if (!mounted.current) return;
          if (previous.data !== undefined && previous.error === undefined) {
            setJob(previous.data);
          } else {
            setError(
              `Ten zakres ma już zadanie ${previousId}. Sprawdź je w Adminie.`,
            );
          }
        } else {
          setError(
            apiErrorMessage(result.error, 'Nie udało się uruchomić zadania.'),
          );
        }
      } else {
        setJob(result.data);
      }
    } catch {
      if (mounted.current)
        setError(
          'Nie otrzymano odpowiedzi. Sprawdź listę zadań w Adminie przed ponowieniem.',
        );
    } finally {
      submitting.current = false;
      if (mounted.current) setBusy(false);
    }
  };

  const refreshJob = async () => {
    if (job === null || submitting.current) return;
    submitting.current = true;
    setBusy(true);
    try {
      const result = await api.getJob(job.id);
      if (!mounted.current) return;
      if (result.error !== undefined || result.data === undefined) {
        setError(
          apiErrorMessage(result.error, 'Nie udało się odświeżyć zadania.'),
        );
      } else {
        setJob(result.data);
        setError('');
        setRefresh((value) => value + 1);
      }
    } catch {
      if (mounted.current) setError('Nie udało się odświeżyć postępu zadania.');
    } finally {
      submitting.current = false;
      if (mounted.current) setBusy(false);
    }
  };

  const statusLabel: Readonly<Record<string, string>> = {
    created: 'Oczekuje',
    queued: 'Oczekuje',
    running: 'Przetwarzanie',
    completed: 'Zakończone',
    failed: 'Błąd',
    cancelled: 'Anulowane',
    waiting_for_review: 'Oczekuje na weryfikację',
    cancelling: 'Anulowanie',
  };
  return (
    <section
      aria-label="Rozpoznawanie symboli po korekcie"
      className="deferredGeometryComplete"
    >
      <h3>Symbole po korekcie siatek</h3>
      <p>
        {count === null
          ? error
            ? 'Liczba plansz niedostępna.'
            : 'Pobieram liczbę plansz…'
          : `Poprawione plansze z polami do weryfikacji: ${count}.`}{' '}
        Zakres:{' '}
        {importJobId === undefined ? 'cała wybrana gra' : 'wybrany import'}. Job
        ponownie rozpozna symbole z zapisanych wycinków i zachowa ręczne
        decyzje. Zapis geometrii nie uruchamia tego joba. Ponowny odczyt nie
        jest ręcznym zatwierdzeniem.
      </p>
      <button
        className="secondaryButton"
        type="button"
        disabled={busy || count === null || count === 0 || activeJob}
        onClick={() => void start()}
      >
        {busy ? 'Przetwarzanie…' : 'Rozpoznaj symbole poprawionych plansz'}
      </button>
      <button
        className="secondaryButton"
        type="button"
        disabled={busy}
        onClick={() => setRefresh((value) => value + 1)}
      >
        Odśwież liczbę plansz
      </button>
      {job ? (
        <div role="status">
          <p>
            Zadanie {job.id}: {statusLabel[job.status] ?? job.status}.
            Przetworzono: {job.progress.current} / {job.progress.total ?? '—'}.
          </p>
          <button
            className="secondaryButton"
            type="button"
            disabled={busy}
            onClick={() => void refreshJob()}
          >
            Odśwież postęp zadania
          </button>
        </div>
      ) : null}
      {error ? <p role="alert">{error}</p> : null}
    </section>
  );
}

function existingJobId(error: unknown): string | null {
  if (
    typeof error !== 'object' ||
    error === null ||
    !('code' in error) ||
    error.code !== 'JOB_INPUT_ALREADY_EXISTS' ||
    !('details' in error) ||
    typeof error.details !== 'object' ||
    error.details === null ||
    !('existingJobId' in error.details) ||
    typeof error.details.existingJobId !== 'string'
  )
    return null;
  return error.details.existingJobId;
}
