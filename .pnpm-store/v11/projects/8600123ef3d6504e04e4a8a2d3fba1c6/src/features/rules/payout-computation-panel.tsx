'use client';

import type {
  DatasetVersionResponse,
  JobResponse,
  RulesVersionResponse,
} from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import {
  type PayoutComputationClient,
  loadPayoutWorkspace,
  refreshPayoutJob,
  retryPayoutComputation,
  startPayoutComputation,
} from './payout-computation-actions';
import {
  PAYOUT_ALGORITHM_VERSION,
  assessPayoutReadiness,
  isPayoutJobActive,
  payoutProgressPercent,
  selectPayoutJob,
} from './payout-computation-state';

type LoadState = 'loading' | 'ready' | 'error';

const STATUS_LABELS: Readonly<Record<JobResponse['status'], string>> = {
  cancelled: 'Anulowane',
  completed: 'Gotowe',
  created: 'Oczekuje',
  failed: 'Błąd',
  processing: 'Przeliczanie',
  waiting_for_review: 'Wymaga uwagi',
};

interface PayoutComputationPanelProps {
  readonly api: PayoutComputationClient;
  readonly gameId: string;
  readonly rulesVersion: RulesVersionResponse;
  readonly pollIntervalMs?: number;
}

export function PayoutComputationPanel({
  api,
  gameId,
  rulesVersion,
  pollIntervalMs = 2000,
}: PayoutComputationPanelProps) {
  const [datasets, setDatasets] = useState<readonly DatasetVersionResponse[]>(
    [],
  );
  const [jobs, setJobs] = useState<readonly JobResponse[]>([]);
  const [loadState, setLoadState] = useState<LoadState>('loading');
  const [error, setError] = useState('');
  const [feedback, setFeedback] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const mounted = useRef(true);
  const mutationInProgress = useRef(false);
  const requestId = useRef(0);

  const load = useCallback(async () => {
    const currentRequest = ++requestId.current;
    setLoadState('loading');
    setError('');
    const result = await loadPayoutWorkspace(api, gameId);
    if (!mounted.current || currentRequest !== requestId.current) return;
    if (!result.ok) {
      setError(result.error);
      setLoadState('error');
      return;
    }
    setDatasets(result.datasets);
    setJobs(result.jobs);
    setLoadState('ready');
  }, [api, gameId]);

  useEffect(() => {
    mounted.current = true;
    queueMicrotask(() => void load());
    return () => {
      mounted.current = false;
      requestId.current += 1;
    };
  }, [load, rulesVersion.id]);

  const readiness = useMemo(
    () => assessPayoutReadiness(rulesVersion, datasets),
    [datasets, rulesVersion],
  );
  const currentJob = useMemo(
    () =>
      readiness.ready
        ? selectPayoutJob(jobs, readiness.dataset.id, rulesVersion.id)
        : null,
    [jobs, readiness, rulesVersion.id],
  );

  useEffect(() => {
    if (
      !isPayoutJobActive(currentJob) ||
      currentJob === null ||
      pollIntervalMs <= 0
    ) {
      return;
    }
    let polling = false;
    const interval = window.setInterval(() => {
      if (polling) return;
      polling = true;
      void refreshPayoutJob(api, currentJob.id).then((result) => {
        polling = false;
        if (!mounted.current) return;
        if (!result.ok) {
          setError(result.error);
          return;
        }
        setJobs((items) => [
          result.job,
          ...items.filter((item) => item.id !== result.job.id),
        ]);
      });
    }, pollIntervalMs);
    return () => window.clearInterval(interval);
  }, [api, currentJob, pollIntervalMs]);

  async function start() {
    if (mutationInProgress.current || !readiness.ready || currentJob !== null) {
      return;
    }
    mutationInProgress.current = true;
    setIsSubmitting(true);
    setError('');
    setFeedback('');
    const result = await startPayoutComputation(
      api,
      gameId,
      readiness.dataset.id,
      rulesVersion.id,
    );
    mutationInProgress.current = false;
    if (!mounted.current) return;
    setIsSubmitting(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setJobs((items) => [result.job, ...items]);
    setFeedback(
      'Przeliczanie dodano do kolejki. Postęp odświeża się automatycznie.',
    );
  }

  async function retry() {
    if (
      mutationInProgress.current ||
      currentJob === null ||
      (currentJob.status !== 'failed' &&
        currentJob.status !== 'waiting_for_review')
    ) {
      return;
    }
    mutationInProgress.current = true;
    setIsSubmitting(true);
    setError('');
    setFeedback('');
    const result = await retryPayoutComputation(api, currentJob.id);
    mutationInProgress.current = false;
    if (!mounted.current) return;
    setIsSubmitting(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setJobs((items) => [
      result.job,
      ...items.filter((item) => item.id !== result.job.id),
    ]);
    setFeedback('Wznowiono ten sam job od bezpiecznego checkpointu.');
  }

  const progress = currentJob ? payoutProgressPercent(currentJob) : null;

  return (
    <section
      className="payoutComputationPanel"
      aria-label="Przeliczanie layoutów"
    >
      <header>
        <div>
          <p className="eyebrow">Precomputed payout</p>
          <h3>Przelicz layouty</h3>
        </div>
        <span className="algorithmBadge">{PAYOUT_ALGORITHM_VERSION}</span>
      </header>

      {loadState === 'loading' ? (
        <p className="mutedText">Sprawdzam dataset i dotychczasowy job…</p>
      ) : loadState === 'error' ? (
        <div className="payoutBlocker" role="alert">
          <p>{error}</p>
          <button
            className="secondaryButton"
            onClick={() => void load()}
            type="button"
          >
            Spróbuj ponownie
          </button>
        </div>
      ) : (
        <>
          {readiness.ready ? (
            <dl className="payoutSourceSummary">
              <div>
                <dt>Dataset</dt>
                <dd>Wersja {readiness.dataset.version}</dd>
              </div>
              <div>
                <dt>Layouty</dt>
                <dd>
                  {readiness.dataset.layoutCount.toLocaleString('pl-PL')} /{' '}
                  {readiness.dataset.expectedLayoutCount.toLocaleString(
                    'pl-PL',
                  )}
                </dd>
              </div>
              <div>
                <dt>Wymiary</dt>
                <dd>
                  {readiness.dataset.rows} × {readiness.dataset.columns}
                </dd>
              </div>
            </dl>
          ) : (
            <p className="payoutBlocker">{readiness.reason}</p>
          )}

          {currentJob ? (
            <div className="payoutJobStatus" aria-live="polite">
              <div>
                <strong>{STATUS_LABELS[currentJob.status]}</strong>
                <span>
                  {currentJob.progress.current.toLocaleString('pl-PL')}
                  {currentJob.progress.total === null
                    ? ' przeliczonych'
                    : ` / ${currentJob.progress.total.toLocaleString('pl-PL')}`}
                </span>
              </div>
              {progress === null ? null : (
                <progress max="100" value={progress}>
                  {progress.toFixed(0)}%
                </progress>
              )}
              <p>
                Etap:{' '}
                {currentJob.progress.stage?.replaceAll('_', ' ') ?? 'oczekuje'}
              </p>
              {currentJob.error ? (
                <p className="formError" role="alert">
                  {currentJob.error.message} ({currentJob.error.code})
                </p>
              ) : null}
              {currentJob.status === 'failed' ||
              currentJob.status === 'waiting_for_review' ? (
                <button
                  className="primaryButton"
                  disabled={isSubmitting}
                  onClick={() => void retry()}
                  type="button"
                >
                  {isSubmitting ? 'Wznawianie…' : 'Wznów przeliczanie'}
                </button>
              ) : null}
            </div>
          ) : readiness.ready ? (
            <button
              className="primaryButton"
              disabled={isSubmitting}
              onClick={() => void start()}
              type="button"
            >
              {isSubmitting ? 'Dodawanie do kolejki…' : 'Przelicz layouty'}
            </button>
          ) : null}
        </>
      )}

      {feedback ? <p className="feedbackBanner">{feedback}</p> : null}
      {error && loadState === 'ready' ? (
        <p className="feedbackBanner feedbackBannerError" role="alert">
          {error}
        </p>
      ) : null}
      <p className="rulesWorkspaceNote">
        Pełną historię i diagnostykę znajdziesz w zakładce Joby.
      </p>
    </section>
  );
}
