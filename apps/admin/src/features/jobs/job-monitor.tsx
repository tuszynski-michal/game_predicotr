'use client';

import type {
  ImageDiagnosticExportResponse,
  ImageJobOperationsResponse,
  ImageStorageInventoryResponse,
  JobResponse,
  JobStatus,
} from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';
import {
  type JobsClient,
  cancelJob,
  createImageDiagnosticExport,
  downloadImageDiagnosticExport,
  loadImageDiagnosticExports,
  loadImageJobOperations,
  loadImageStorageInventory,
  loadJobs,
  retryImageJobFile,
  retryJob,
} from '@/features/jobs/job-actions';
import {
  JOB_STATUS_OPTIONS,
  canCancelJob,
  canRetryJob,
  formatJobTimestamp,
  formatElapsedSeconds,
  formatImageThroughput,
  formatStorageBytes,
  isActiveJob,
  isImageImportJob,
  jobContextLabel,
  jobErrorSummary,
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
    [api, statusFilter],
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
          <h1>Joby</h1>
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
              api={api}
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
  api,
  cancelConfirmation,
  job,
  mutating,
  onCancel,
  onCancelConfirmation,
  onCancelConfirmationClose,
  onRetry,
}: {
  readonly api: JobsClient;
  readonly cancelConfirmation: boolean;
  readonly job: JobResponse;
  readonly mutating: boolean;
  readonly onCancel: () => void;
  readonly onCancelConfirmation: () => void;
  readonly onCancelConfirmationClose: () => void;
  readonly onRetry: () => void;
}) {
  const percent = jobProgressPercent(job);
  const errorSummary = jobErrorSummary(job);
  const cancellationPending =
    job.status === 'processing' && job.cancelRequestedAt !== null;

  return (
    <details className={`jobCard jobCard-${job.status}`}>
      <summary className="jobCardSummary">
        <span className="jobTypeMark" aria-hidden="true">
          {job.jobType.slice(0, 2).toUpperCase()}
        </span>
        <span className="jobSummaryIdentity">
          <strong>{jobTypeLabel(job.jobType)}</strong>
          <code title={job.id}>{job.id}</code>
          <small title={jobContextLabel(job)}>{jobContextLabel(job)}</small>
        </span>
        <span className={`jobStatus jobStatus-${job.status}`}>
          {jobStatusLabel(job.status)}
        </span>
        <span className="jobSummaryProgress">
          <span>
            <strong>{jobProgressLabel(job)}</strong>
            <small>
              {percent === null ? 'Rozmiar nieznany' : `${percent.toFixed(1)}%`}
            </small>
          </span>
          <span
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
          </span>
        </span>
        <span className="jobSummaryCreated">
          <small>Utworzono</small>
          <time dateTime={job.createdAt}>
            {formatJobTimestamp(job.createdAt)}
          </time>
        </span>
        <span className="jobSummaryChevron" aria-hidden="true">
          +
        </span>
        {errorSummary ? (
          <span className="jobErrorSummary" title={errorSummary}>
            {errorSummary}
          </span>
        ) : null}
      </summary>

      <div className="jobCardDetails">
        <div className="jobCardHeader">
          <p className="jobStage">
            Etap: <strong>{jobStageLabel(job.progress.stage)}</strong>
          </p>
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
          <JobTime label="Rozpoczęto" value={job.startedAt} />
          <JobTime label="Zakończono" value={job.finishedAt} />
          <JobTime label="Heartbeat" value={job.heartbeatAt} />
          <JobTime label="Lease do" value={job.leaseExpiresAt} />
          <div>
            <dt>Worker</dt>
            <dd>{job.workerVersion ?? '—'}</dd>
          </div>
        </dl>
        {isImageImportJob(job) ? (
          <ImageJobOperationsPanel api={api} job={job} />
        ) : null}
      </div>
    </details>
  );
}

function ImageJobOperationsPanel({
  api,
  job,
}: {
  readonly api: JobsClient;
  readonly job: JobResponse;
}) {
  const [expanded, setExpanded] = useState(false);
  const [operations, setOperations] =
    useState<ImageJobOperationsResponse | null>(null);
  const [storage, setStorage] = useState<ImageStorageInventoryResponse | null>(
    null,
  );
  const [diagnosticExports, setDiagnosticExports] = useState<
    readonly ImageDiagnosticExportResponse[]
  >([]);
  const [state, setState] = useState<'idle' | 'loading' | 'ready' | 'error'>(
    'idle',
  );
  const [error, setError] = useState('');
  const [retryingFileKey, setRetryingFileKey] = useState<string | null>(null);
  const [creatingExport, setCreatingExport] = useState(false);
  const [downloadingChecksum, setDownloadingChecksum] = useState<string | null>(
    null,
  );
  const [feedback, setFeedback] = useState('');
  const requestInProgress = useRef(false);
  const pipelineFingerprint =
    'pipelineFingerprint' in job.inputPayload
      ? job.inputPayload.pipelineFingerprint
      : '—';

  const refresh = useCallback(async () => {
    if (requestInProgress.current) return;
    requestInProgress.current = true;
    setState((current) => (current === 'ready' ? 'ready' : 'loading'));
    setError('');
    const [result, storageResult, exportsResult] = await Promise.all([
      loadImageJobOperations(api, job.id),
      loadImageStorageInventory(api),
      loadImageDiagnosticExports(api, job.id),
    ]);
    requestInProgress.current = false;
    if (!result.ok) {
      setError(result.error);
      setState((current) => (current === 'ready' ? 'ready' : 'error'));
      return;
    }
    if (!storageResult.ok) {
      setError(storageResult.error);
      setState((current) => (current === 'ready' ? 'ready' : 'error'));
      return;
    }
    if (!exportsResult.ok) {
      setError(exportsResult.error);
      setState((current) => (current === 'ready' ? 'ready' : 'error'));
      return;
    }
    setOperations(result.operations);
    setStorage(storageResult.inventory);
    setDiagnosticExports(exportsResult.exports);
    setState('ready');
  }, [api, job.id]);

  useEffect(() => {
    if (expanded) queueMicrotask(() => void refresh());
  }, [expanded, job.updatedAt, refresh]);

  async function retryFile(
    fileExecutionKey: string,
    failedStage: string | null,
  ) {
    if (retryingFileKey !== null || failedStage === null) return;
    setRetryingFileKey(fileExecutionKey);
    setError('');
    const result = await retryImageJobFile(
      api,
      job.id,
      fileExecutionKey,
      failedStage,
    );
    setRetryingFileKey(null);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setOperations(result.operations);
    setState('ready');
  }

  async function createDiagnosticExport() {
    if (creatingExport) return;
    setCreatingExport(true);
    setError('');
    setFeedback('');
    const result = await createImageDiagnosticExport(api, job.id);
    setCreatingExport(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    const exported = result.creation.export;
    setDiagnosticExports((current) => [
      exported,
      ...current.filter(
        (item) => item.checksumSha256 !== exported.checksumSha256,
      ),
    ]);
    setFeedback(
      result.creation.created
        ? 'Utworzono niezmienny eksport diagnostyczny.'
        : 'Stan joba się nie zmienił — użyto istniejącego eksportu.',
    );
  }

  async function downloadDiagnosticExport(
    diagnosticExport: ImageDiagnosticExportResponse,
  ) {
    if (downloadingChecksum !== null) return;
    setDownloadingChecksum(diagnosticExport.checksumSha256);
    setError('');
    setFeedback('');
    const result = await downloadImageDiagnosticExport(
      api,
      job.id,
      diagnosticExport.checksumSha256,
    );
    setDownloadingChecksum(null);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    const url = URL.createObjectURL(result.artifact);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `image-job-${job.id}-diagnostics-${diagnosticExport.checksumSha256.slice(0, 12)}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
    setFeedback('Pobrano eksport zweryfikowany sumą SHA-256.');
  }

  return (
    <section className="imageJobOperations">
      <div className="imageJobOperationsHeader">
        <div>
          <h3>Import zdjęć</h3>
          <p>
            Pipeline <code>{pipelineFingerprint}</code>
          </p>
        </div>
        <button
          aria-expanded={expanded}
          className="secondaryButton"
          onClick={() => setExpanded((value) => !value)}
          type="button"
        >
          {expanded ? 'Ukryj szczegóły' : 'Pokaż szczegóły'}
        </button>
      </div>

      {expanded ? (
        state === 'loading' ? (
          <p className="imageJobInlineState" role="status">
            Pobieram statystyki plików…
          </p>
        ) : state === 'error' ? (
          <div className="imageJobInlineError" role="alert">
            <p>{error}</p>
            <button
              className="secondaryButton"
              onClick={() => void refresh()}
              type="button"
            >
              Spróbuj ponownie
            </button>
          </div>
        ) : operations === null ? null : (
          <>
            {error ? (
              <p className="imageJobInlineError" role="alert">
                {error}
              </p>
            ) : null}
            <dl className="imageJobSummary">
              <div>
                <dt>Poprawne</dt>
                <dd>{operations.succeeded.toLocaleString('pl-PL')}</dd>
              </div>
              <div>
                <dt>Błędy</dt>
                <dd>{operations.failed.toLocaleString('pl-PL')}</dd>
              </div>
              <div>
                <dt>Review</dt>
                <dd>{operations.review.toLocaleString('pl-PL')}</dd>
              </div>
              <div>
                <dt>Oczekujące</dt>
                <dd>{operations.waiting.toLocaleString('pl-PL')}</dd>
              </div>
              <div>
                <dt>Czas</dt>
                <dd>{formatElapsedSeconds(operations.elapsedSeconds)}</dd>
              </div>
              <div>
                <dt>Przepustowość</dt>
                <dd>{formatImageThroughput(operations.filesPerMinute)}</dd>
              </div>
            </dl>

            <div className="imageJobStages" aria-label="Pliki według etapu">
              {operations.stageCounts.map((item) => (
                <span key={item.stage}>
                  {jobStageLabel(item.stage)}: <strong>{item.count}</strong>
                </span>
              ))}
            </div>

            {storage === null ? null : (
              <section className="imageStorageSummary">
                <div className="imageStorageHeader">
                  <div>
                    <h4>Magazyn plików</h4>
                    <p>
                      Zarządzany katalog <code>{storage.rootName}</code> ·{' '}
                      {storage.totalFileCount.toLocaleString('pl-PL')} plików ·{' '}
                      {formatStorageBytes(storage.totalSizeBytes)}
                    </p>
                  </div>
                  <strong>Automatyczne usuwanie: wyłączone</strong>
                </div>
                <p className="imageStoragePolicy">
                  Panel pokazuje retencję, ale niczego nie usuwa. Oryginały,
                  dane treningowe, modele i eksporty są chronione.
                </p>
                <div
                  aria-label="Przestrzenie magazynu obrazów"
                  className="imageStorageNamespaces"
                >
                  {storage.namespaces.map((namespace) => (
                    <div key={namespace.name}>
                      <strong>{namespace.name}</strong>
                      <span>
                        {namespace.fileCount.toLocaleString('pl-PL')} plików ·{' '}
                        {formatStorageBytes(namespace.sizeBytes)}
                      </span>
                      <small>{namespace.retentionPolicy}</small>
                    </div>
                  ))}
                </div>
              </section>
            )}

            <section className="imageDiagnosticExports">
              <div className="imageDiagnosticExportsHeader">
                <div>
                  <h4>Eksporty diagnostyczne</h4>
                  <p>
                    Tylko metadane i błędy; bez obrazów, sekretów i ścieżek
                    bezwzględnych.
                  </p>
                </div>
                <button
                  className="secondaryButton"
                  disabled={creatingExport}
                  onClick={() => void createDiagnosticExport()}
                  type="button"
                >
                  {creatingExport ? 'Tworzenie…' : 'Utwórz eksport'}
                </button>
              </div>
              {feedback ? (
                <p className="imageJobInlineFeedback" role="status">
                  {feedback}
                </p>
              ) : null}
              {diagnosticExports.length === 0 ? (
                <p className="imageJobInlineState">
                  Nie utworzono jeszcze eksportu dla tego joba.
                </p>
              ) : (
                <div className="imageDiagnosticExportList">
                  {diagnosticExports.map((diagnosticExport) => (
                    <article key={diagnosticExport.checksumSha256}>
                      <div>
                        <strong>
                          {formatJobTimestamp(diagnosticExport.sourceUpdatedAt)}
                        </strong>
                        <code title={diagnosticExport.checksumSha256}>
                          {diagnosticExport.checksumSha256.slice(0, 16)}…
                        </code>
                        <small>
                          {diagnosticExport.exportedErrorCount.toLocaleString(
                            'pl-PL',
                          )}{' '}
                          z{' '}
                          {diagnosticExport.errorCount.toLocaleString('pl-PL')}{' '}
                          błędów ·{' '}
                          {formatStorageBytes(diagnosticExport.sizeBytes)}
                          {diagnosticExport.truncated
                            ? ' · wynik ograniczony'
                            : ''}
                        </small>
                      </div>
                      <button
                        className="secondaryButton"
                        disabled={downloadingChecksum !== null}
                        onClick={() =>
                          void downloadDiagnosticExport(diagnosticExport)
                        }
                        type="button"
                      >
                        {downloadingChecksum === diagnosticExport.checksumSha256
                          ? 'Pobieranie…'
                          : 'Pobierz JSON'}
                      </button>
                    </article>
                  ))}
                </div>
              )}
            </section>

            {operations.files.length === 0 ? (
              <p className="imageJobInlineState">
                Job nie ma jeszcze zarejestrowanych plików.
              </p>
            ) : (
              <div className="imageJobFileTableWrap">
                <table className="imageJobFileTable">
                  <thead>
                    <tr>
                      <th scope="col">#</th>
                      <th scope="col">Plik</th>
                      <th scope="col">Stan / etap</th>
                      <th scope="col">Retry</th>
                      <th scope="col">Operacja</th>
                    </tr>
                  </thead>
                  <tbody>
                    {operations.files.map((file) => (
                      <tr key={file.fileExecutionKey}>
                        <td>{file.orderIndex + 1}</td>
                        <td>
                          <span title={file.sourceRelativePath}>
                            {file.sourceRelativePath}
                          </span>
                          {file.error ? (
                            <small className="imageJobFileError">
                              {file.error.code}: {file.error.message}
                            </small>
                          ) : null}
                        </td>
                        <td>
                          <strong>{file.status.replaceAll('_', ' ')}</strong>
                          <small>
                            {jobStageLabel(file.failedStage ?? file.nextStage)}
                          </small>
                        </td>
                        <td>{file.retryCount}</td>
                        <td>
                          {file.status === 'failed' &&
                          file.failedStage !== null ? (
                            <button
                              className="primaryButton"
                              disabled={retryingFileKey !== null}
                              onClick={() =>
                                void retryFile(
                                  file.fileExecutionKey,
                                  file.failedStage,
                                )
                              }
                              type="button"
                            >
                              {retryingFileKey === file.fileExecutionKey
                                ? 'Ponawianie…'
                                : `Ponów ${jobStageLabel(file.failedStage)}`}
                            </button>
                          ) : (
                            '—'
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {operations.hasMoreFiles ? (
                  <p className="imageJobInlineState">
                    Pokazano pierwsze {operations.fileLimit} plików z{' '}
                    {operations.total.toLocaleString('pl-PL')}.
                  </p>
                ) : null}
              </div>
            )}
          </>
        )
      ) : null}
    </section>
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
