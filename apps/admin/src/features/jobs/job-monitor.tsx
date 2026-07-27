'use client';

import type {
  JobResponse,
  JobStatus,
  JobType,
} from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';
import {
  type JobsClient,
  cancelJob,
  loadJobs,
  retryJob,
} from '@/features/jobs/job-actions';
import {
  JOB_STATUS_OPTIONS,
  JOB_TYPE_OPTIONS,
  canCancelJob,
  canRetryJob,
  formatJobTimestamp,
  isActiveJob,
  jobProgressLabel,
  jobProgressPercent,
  jobStageLabel,
  jobStatusLabel,
  jobTypeLabel,
  replaceJob,
} from '@/features/jobs/job-state';

type LoadState = 'loading' | 'ready' | 'error';

interface JobMonitorProps {
  readonly apiBaseUrl: string;
  readonly client?: JobsClient;
  readonly pollIntervalMs?: number;
}

export function JobMonitor({
  apiBaseUrl,
  client,
  pollIntervalMs = 2000,
}: JobMonitorProps) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const [jobs, setJobs] = useState<readonly JobResponse[]>([]);
  const [statusFilter, setStatusFilter] = useState<JobStatus | ''>('');
  const [typeFilter, setTypeFilter] = useState<JobType | ''>('');
  const [loadState, setLoadState] = useState<LoadState>('loading');
  const [error, setError] = useState('');
  const [feedback, setFeedback] = useState('');
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [mutatingJobId, setMutatingJobId] = useState<string | null>(null);
  const [cancelCandidateId, setCancelCandidateId] = useState<string | null>(
    null,
  );
  const requestInProgress = useRef(false);
  const requestId = useRef(0);
  const mutationInProgress = useRef(false);
  const mounted = useRef(true);
  const hasLoadedSuccessfully = useRef(false);

  const refresh = useCallback(
    async (initial: boolean) => {
      if (requestInProgress.current && !initial) return;
      const currentRequest = ++requestId.current;
      requestInProgress.current = true;
      if (initial) setLoadState('loading');
      else setIsRefreshing(true);
      setError('');
      const result = await loadJobs(api, {
        ...(statusFilter === '' ? {} : { status: statusFilter }),
        ...(typeFilter === '' ? {} : { jobType: typeFilter }),
      });
      if (!mounted.current || currentRequest !== requestId.current) return;
      requestInProgress.current = false;
      setIsRefreshing(false);
      if (!result.ok) {
        setError(result.error);
        if (initial || !hasLoadedSuccessfully.current) setLoadState('error');
        return;
      }
      hasLoadedSuccessfully.current = true;
      setJobs(result.jobs);
      setLoadState('ready');
    },
    [api, statusFilter, typeFilter],
  );

  useEffect(() => {
    mounted.current = true;
    queueMicrotask(() => void refresh(true));
    return () => {
      mounted.current = false;
    };
  }, [refresh]);

  const hasActiveJob = jobs.some(isActiveJob);

  useEffect(() => {
    if (!hasActiveJob || pollIntervalMs <= 0) return;
    const interval = window.setInterval(() => {
      void refresh(false);
    }, pollIntervalMs);
    return () => window.clearInterval(interval);
  }, [hasActiveJob, pollIntervalMs, refresh]);

  async function confirmCancel(job: JobResponse) {
    if (mutationInProgress.current || !canCancelJob(job)) return;
    mutationInProgress.current = true;
    setMutatingJobId(job.id);
    setError('');
    setFeedback('');
    const result = await cancelJob(api, job.id);
    mutationInProgress.current = false;
    if (!mounted.current) return;
    setMutatingJobId(null);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setJobs((current) => replaceJob(current, result.job));
    setCancelCandidateId(null);
    setFeedback(
      result.job.status === 'cancelled'
        ? 'Zadanie zostało anulowane.'
        : 'Zapisano żądanie anulowania. Worker zatrzyma się w bezpiecznym punkcie.',
    );
  }

  async function onRetry(job: JobResponse) {
    if (mutationInProgress.current || !canRetryJob(job)) return;
    mutationInProgress.current = true;
    setMutatingJobId(job.id);
    setError('');
    setFeedback('');
    const result = await retryJob(api, job.id);
    mutationInProgress.current = false;
    if (!mounted.current) return;
    setMutatingJobId(null);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setJobs((current) => replaceJob(current, result.job));
    setFeedback(
      `Zadanie ${jobTypeLabel(result.job.jobType)} wróciło do kolejki bez duplikowania wejścia.`,
    );
  }

  return (
    <section className="catalogSection" id="jobs">
      <header className="pageHeader jobsPageHeader">
        <div>
          <p className="eyebrow">M3.1 · lokalny worker</p>
          <h1>Jobs</h1>
          <p className="lead">
            Obserwuj etap, postęp i lease długich operacji. Anulowanie aktywnego
            zadania następuje dopiero w bezpiecznym checkpointcie workera.
          </p>
        </div>
        <button
          className="secondaryButton"
          disabled={isRefreshing || loadState === 'loading'}
          onClick={() => void refresh(false)}
          type="button"
        >
          {isRefreshing ? 'Odświeżanie…' : 'Odśwież'}
        </button>
      </header>

      <div className="jobFilters" aria-label="Filtry zadań">
        <label>
          Status
          <select
            onChange={(event) =>
              setStatusFilter(event.target.value as JobStatus | '')
            }
            value={statusFilter}
          >
            <option value="">Wszystkie statusy</option>
            {JOB_STATUS_OPTIONS.map((status) => (
              <option key={status} value={status}>
                {jobStatusLabel(status)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Typ
          <select
            onChange={(event) =>
              setTypeFilter(event.target.value as JobType | '')
            }
            value={typeFilter}
          >
            <option value="">Wszystkie typy</option>
            {JOB_TYPE_OPTIONS.map((jobType) => (
              <option key={jobType} value={jobType}>
                {jobTypeLabel(jobType)}
              </option>
            ))}
          </select>
        </label>
        <p aria-live="polite">
          {hasActiveJob
            ? 'Automatyczne odświeżanie aktywne · co 2 sekundy'
            : 'Automatyczne odświeżanie zatrzymane'}
        </p>
      </div>

      {feedback ? (
        <p className="feedbackBanner" role="status">
          {feedback}
        </p>
      ) : null}
      {error && loadState !== 'error' ? (
        <p className="feedbackBanner feedbackBannerError" role="alert">
          {error}
        </p>
      ) : null}

      {loadState === 'loading' ? (
        <JobState
          text="Pobieram najnowsze zadania z lokalnego Admin API…"
          title="Wczytywanie"
        />
      ) : loadState === 'error' ? (
        <JobState
          error
          onRetry={() => void refresh(true)}
          text={error}
          title="Nie udało się wczytać jobs"
        />
      ) : jobs.length === 0 ? (
        <JobState
          text="Brak zadań pasujących do wybranych filtrów."
          title="Pusta kolejka"
        />
      ) : (
        <div className="jobList" aria-label="Lista zadań">
          {jobs.map((job) => (
            <JobCard
              cancelConfirmation={cancelCandidateId === job.id}
              job={job}
              key={job.id}
              mutating={mutatingJobId === job.id}
              onCancel={() => setCancelCandidateId(job.id)}
              onCancelConfirmation={() => void confirmCancel(job)}
              onCancelConfirmationClose={() => setCancelCandidateId(null)}
              onRetry={() => void onRetry(job)}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function JobCard({
  cancelConfirmation,
  job,
  mutating,
  onCancel,
  onCancelConfirmation,
  onCancelConfirmationClose,
  onRetry,
}: {
  readonly cancelConfirmation: boolean;
  readonly job: JobResponse;
  readonly mutating: boolean;
  readonly onCancel: () => void;
  readonly onCancelConfirmation: () => void;
  readonly onCancelConfirmationClose: () => void;
  readonly onRetry: () => void;
}) {
  const percent = jobProgressPercent(job);
  const cancellationPending =
    job.status === 'processing' && job.cancelRequestedAt !== null;

  return (
    <article className={`jobCard jobCard-${job.status}`}>
      <div className="jobCardHeader">
        <div>
          <div className="jobTitleLine">
            <span className="jobTypeMark" aria-hidden="true">
              {job.jobType.slice(0, 2).toUpperCase()}
            </span>
            <div>
              <h2>{jobTypeLabel(job.jobType)}</h2>
              <code title={job.id}>{job.id}</code>
            </div>
            <span className={`jobStatus jobStatus-${job.status}`}>
              {jobStatusLabel(job.status)}
            </span>
          </div>
          <p className="jobStage">
            Etap: <strong>{jobStageLabel(job.progress.stage)}</strong>
          </p>
        </div>
        <div className="jobActions">
          {cancelConfirmation ? (
            <>
              <span>Czy na pewno?</span>
              <button
                className="textButton"
                disabled={mutating}
                onClick={onCancelConfirmationClose}
                type="button"
              >
                Wróć
              </button>
              <button
                className="dangerButton"
                disabled={mutating}
                onClick={onCancelConfirmation}
                type="button"
              >
                {mutating ? 'Anulowanie…' : 'Potwierdź'}
              </button>
            </>
          ) : (
            <>
              {canRetryJob(job) ? (
                <button
                  className="primaryButton"
                  disabled={mutating}
                  onClick={onRetry}
                  type="button"
                >
                  {mutating ? 'Ponawianie…' : 'Ponów'}
                </button>
              ) : null}
              {canCancelJob(job) ? (
                <button
                  className="dangerButton"
                  disabled={mutating}
                  onClick={onCancel}
                  type="button"
                >
                  Anuluj
                </button>
              ) : null}
            </>
          )}
        </div>
      </div>

      {cancellationPending ? (
        <p className="jobCancellationNotice" role="status">
          Żądanie anulowania zapisane. Oczekiwanie na bezpieczny checkpoint.
        </p>
      ) : null}

      <div className="jobProgressSection">
        <div className="jobProgressSummary">
          <strong>{jobProgressLabel(job)}</strong>
          <span>
            {percent === null
              ? 'Całkowity rozmiar nieznany'
              : `${percent.toFixed(1)}%`}
          </span>
        </div>
        <div
          aria-label={`Postęp: ${jobProgressLabel(job)}`}
          aria-valuemax={job.progress.total ?? undefined}
          aria-valuemin={0}
          aria-valuenow={job.progress.current}
          className={`jobProgressTrack ${
            percent === null ? 'jobProgressTrackIndeterminate' : ''
          }`}
          role="progressbar"
        >
          <span style={{ width: percent === null ? '35%' : `${percent}%` }} />
        </div>
        <dl className="jobCounters">
          <div>
            <dt>Poprawne</dt>
            <dd>{job.progress.succeeded.toLocaleString('pl-PL')}</dd>
          </div>
          <div>
            <dt>Błędy</dt>
            <dd>{job.progress.failed.toLocaleString('pl-PL')}</dd>
          </div>
          <div>
            <dt>Review</dt>
            <dd>{job.progress.review.toLocaleString('pl-PL')}</dd>
          </div>
          <div>
            <dt>Próba</dt>
            <dd>{job.attemptCount}</dd>
          </div>
        </dl>
      </div>

      {job.error ? (
        <div className="jobError" role="alert">
          <strong>{job.error.code}</strong>
          <p>{job.error.message}</p>
        </div>
      ) : null}

      <dl className="jobMetadata">
        <JobTime label="Utworzono" value={job.createdAt} />
        <JobTime label="Rozpoczęto" value={job.startedAt} />
        <JobTime label="Zakończono" value={job.finishedAt} />
        <JobTime label="Heartbeat" value={job.heartbeatAt} />
        <JobTime label="Lease do" value={job.leaseExpiresAt} />
        <div>
          <dt>Worker</dt>
          <dd>{job.workerVersion ?? '—'}</dd>
        </div>
      </dl>
    </article>
  );
}

function JobTime({
  label,
  value,
}: {
  readonly label: string;
  readonly value: string | null;
}) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>
        {value === null ? (
          '—'
        ) : (
          <time dateTime={value}>{formatJobTimestamp(value)}</time>
        )}
      </dd>
    </div>
  );
}

function JobState({
  error = false,
  onRetry,
  text,
  title,
}: {
  readonly error?: boolean;
  readonly onRetry?: () => void;
  readonly text: string;
  readonly title: string;
}) {
  return (
    <div className={`statePanel ${error ? 'statePanelError' : ''}`}>
      <span className={title === 'Wczytywanie' ? 'loadingMark' : 'stateIcon'}>
        {title === 'Wczytywanie' ? '' : error ? '!' : '0'}
      </span>
      <div>
        <h2>{title}</h2>
        <p>{text}</p>
        {onRetry ? (
          <button className="secondaryButton" onClick={onRetry} type="button">
            Spróbuj ponownie
          </button>
        ) : null}
      </div>
    </div>
  );
}
