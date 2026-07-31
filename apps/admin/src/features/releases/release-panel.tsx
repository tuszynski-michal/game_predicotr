'use client';

import type {
  JobResponse,
  MobileReleaseResponse,
} from '@game-predictor/admin-api-client';
import {
  type FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';
import { CleanupControl } from '@/features/cleanup/cleanup-control';
import {
  createAndStartRelease,
  downloadReleaseApk,
  loadReleaseWorkspace,
  refreshRelease,
  retryReleaseBuild,
  startReleaseBuild,
  type ReleasesClient,
} from '@/features/releases/release-actions';
import {
  createInitialSelections,
  formatReleaseTimestamp,
  hasCompatibleReleasePair,
  releaseStatusLabel,
  type ReleaseGameSelection,
  type ReleaseGameSource,
  selectControlledReleaseGame,
  upsertRelease,
  validateReleaseDraft,
} from '@/features/releases/release-state';
import {
  canRetryJob,
  isActiveJob,
  jobStatusLabel,
} from '@/features/jobs/job-state';

type LoadState = 'loading' | 'ready' | 'error';

interface ReleasePanelProps {
  readonly apiBaseUrl: string;
  readonly client?: ReleasesClient;
  readonly onOpenJobs?: () => void;
  readonly pollIntervalMs?: number;
}

export function ReleasePanel({
  apiBaseUrl,
  client,
  onOpenJobs,
  pollIntervalMs = 2000,
}: ReleasePanelProps) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const [sources, setSources] = useState<readonly ReleaseGameSource[]>([]);
  const [releases, setReleases] = useState<readonly MobileReleaseResponse[]>(
    [],
  );
  const [selections, setSelections] = useState<readonly ReleaseGameSelection[]>(
    [],
  );
  const [version, setVersion] = useState('');
  const [selectedReleaseId, setSelectedReleaseId] = useState<string | null>(
    null,
  );
  const [selectedJob, setSelectedJob] = useState<JobResponse | null>(null);
  const [selectedJobReleaseId, setSelectedJobReleaseId] = useState<
    string | null
  >(null);
  const [loadState, setLoadState] = useState<LoadState>('loading');
  const [error, setError] = useState('');
  const [feedback, setFeedback] = useState('');
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [isBuilding, setIsBuilding] = useState(false);
  const [isRetrying, setIsRetrying] = useState(false);
  const [downloadingReleaseId, setDownloadingReleaseId] = useState<
    string | null
  >(null);
  const mounted = useRef(true);
  const requestId = useRef(0);
  const refreshInProgress = useRef<string | null>(null);
  const selectedReleaseIdRef = useRef(selectedReleaseId);

  const selectedRelease =
    releases.find((release) => release.id === selectedReleaseId) ?? null;
  const visibleJob =
    selectedJobReleaseId === selectedReleaseId ? selectedJob : null;
  const selectedSelection =
    selections.find((selection) => selection.included) ?? null;
  const selectedSource =
    sources.find((source) => source.game.id === selectedSelection?.gameId) ??
    null;
  const selectedDataset =
    selectedSource?.datasets.find(
      (dataset) => dataset.id === selectedSelection?.datasetVersionId,
    ) ?? null;
  const selectedRules =
    selectedSource?.rulesVersions.find(
      (rules) => rules.id === selectedSelection?.rulesVersionId,
    ) ?? null;

  const loadWorkspace = useCallback(async () => {
    const currentRequest = ++requestId.current;
    setLoadState('loading');
    setError('');
    const result = await loadReleaseWorkspace(api);
    if (!mounted.current || currentRequest !== requestId.current) return;
    if (!result.ok) {
      setError(result.error);
      setLoadState('error');
      return;
    }
    setSources(result.sources);
    setSelections(createInitialSelections(result.sources));
    setReleases(result.releases);
    setSelectedReleaseId((current) => {
      if (
        current &&
        result.releases.some((release) => release.id === current)
      ) {
        return current;
      }
      return (
        result.releases.find(
          (release) =>
            release.status === 'building' || release.status === 'failed',
        )?.id ??
        result.releases[0]?.id ??
        null
      );
    });
    setLoadState('ready');
  }, [api]);

  useEffect(() => {
    mounted.current = true;
    queueMicrotask(() => void loadWorkspace());
    return () => {
      mounted.current = false;
      requestId.current += 1;
    };
  }, [loadWorkspace]);

  const refreshSelected = useCallback(
    async (showSpinner: boolean) => {
      if (
        selectedReleaseId === null ||
        refreshInProgress.current === selectedReleaseId
      ) {
        return;
      }
      const releaseId = selectedReleaseId;
      refreshInProgress.current = releaseId;
      if (showSpinner) setIsRefreshing(true);
      const result = await refreshRelease(api, releaseId);
      if (refreshInProgress.current === releaseId) {
        refreshInProgress.current = null;
      }
      if (!mounted.current || selectedReleaseIdRef.current !== releaseId) {
        return;
      }
      setIsRefreshing(false);
      if (!result.ok) {
        setError(result.error);
        return;
      }
      setReleases((current) => upsertRelease(current, result.release));
      setSelectedJob(result.job);
      setSelectedJobReleaseId(result.release.id);
    },
    [api, selectedReleaseId],
  );

  useEffect(() => {
    selectedReleaseIdRef.current = selectedReleaseId;
  }, [selectedReleaseId]);

  useEffect(() => {
    if (selectedReleaseId !== null) {
      queueMicrotask(() => void refreshSelected(false));
    }
  }, [refreshSelected, selectedReleaseId]);

  const shouldPoll =
    selectedRelease?.status === 'building' ||
    (visibleJob !== null && isActiveJob(visibleJob));

  useEffect(() => {
    if (!shouldPoll || pollIntervalMs <= 0) return;
    const interval = window.setInterval(() => {
      void refreshSelected(false);
    }, pollIntervalMs);
    return () => window.clearInterval(interval);
  }, [pollIntervalMs, refreshSelected, shouldPoll]);

  function onGameChanged(gameId: string) {
    setSelections(selectControlledReleaseGame(sources, gameId || null));
  }

  async function onCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isCreating) return;
    setError('');
    setFeedback('');
    const validation = validateReleaseDraft({ selections, version }, sources);
    if (!validation.valid) {
      setError(validation.error);
      return;
    }
    setIsCreating(true);
    const result = await createAndStartRelease(api, validation.body);
    if (!mounted.current) return;
    if (!result.ok) {
      setIsCreating(false);
      if (result.release === null) {
        setError(result.error);
        return;
      }
      const preservedDraft = result.release;
      setReleases((current) => upsertRelease(current, preservedDraft));
      setSelectedReleaseId(preservedDraft.id);
      setVersion('');
      setError(
        `Draft ${preservedDraft.version} został zachowany. ${result.error}`,
      );
      return;
    }
    setReleases((current) => upsertRelease(current, result.release));
    setSelectedReleaseId(result.release.id);
    setVersion('');
    setIsCreating(false);
    const buildingRelease = {
      ...result.release,
      buildJobId: result.build.jobId,
      status: 'building' as const,
    };
    setReleases((current) => upsertRelease(current, buildingRelease));
    setFeedback(
      `Wydanie ${result.release.version} utworzono i przekazano do kontrolowanego workflow.`,
    );
    queueMicrotask(() => void refreshSelected(false));
  }

  async function onBuild(release: MobileReleaseResponse) {
    if (isBuilding || release.status !== 'draft') return;
    setError('');
    setFeedback('');
    setIsBuilding(true);
    const result = await startReleaseBuild(api, release.id);
    if (!mounted.current) return;
    setIsBuilding(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    const buildingRelease = {
      ...release,
      buildJobId: result.build.jobId,
      status: 'building' as const,
    };
    setReleases((current) => upsertRelease(current, buildingRelease));
    setSelectedReleaseId(release.id);
    setFeedback(
      `Workflow ${release.version} trafił do lokalnej kolejki. Panel będzie odświeżał status.`,
    );
    queueMicrotask(() => void refreshSelected(false));
  }

  async function onRetry() {
    if (isRetrying || visibleJob === null || !canRetryJob(visibleJob)) {
      return;
    }
    setError('');
    setFeedback('');
    setIsRetrying(true);
    const result = await retryReleaseBuild(api, visibleJob.id);
    if (!mounted.current) return;
    setIsRetrying(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setSelectedJob(result.job);
    setSelectedJobReleaseId(selectedReleaseId);
    setFeedback(
      'Ten sam job wrócił do kolejki. Bezpieczny checkpoint zostanie użyty ponownie.',
    );
  }

  async function copyArtifactPath(path: string) {
    try {
      await navigator.clipboard.writeText(path);
      setFeedback(`Skopiowano ścieżkę: ${path}`);
      setError('');
    } catch {
      setError('Przeglądarka nie pozwoliła skopiować ścieżki.');
    }
  }

  async function onDownload(release: MobileReleaseResponse) {
    if (
      downloadingReleaseId !== null ||
      release.status !== 'ready' ||
      release.apk === null
    ) {
      return;
    }
    setDownloadingReleaseId(release.id);
    setError('');
    setFeedback('');
    const result = await downloadReleaseApk(api, release.id);
    if (!mounted.current) return;
    setDownloadingReleaseId(null);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    const url = URL.createObjectURL(result.artifact);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `game-predictor-${release.version}.apk`;
    anchor.click();
    URL.revokeObjectURL(url);
    setFeedback(`Pobrano zweryfikowany APK ${release.version}.`);
  }

  function onReleaseDeleted(releaseId: string) {
    setReleases((current) => {
      const remaining = current.filter((release) => release.id !== releaseId);
      setSelectedReleaseId(remaining[0]?.id ?? null);
      return remaining;
    });
    setSelectedJob(null);
    setSelectedJobReleaseId(null);
    setFeedback('Wydanie i jego dedykowane artefakty zostały usunięte.');
    setError('');
  }

  return (
    <section className="catalogSection" id="releases">
      <header className="pageHeader releasePageHeader">
        <div>
          <p className="eyebrow">M3.4 · prywatny Android</p>
          <h1>Wydania Android</h1>
          <p className="lead">
            Zamroź opublikowane dane, uruchom jeden kontrolowany workflow i
            pobierz zweryfikowany APK do ręcznej instalacji. Panel nie przyjmuje
            komend ani dowolnych ścieżek.
          </p>
        </div>
        <button
          className="secondaryButton"
          disabled={loadState === 'loading'}
          onClick={() => void loadWorkspace()}
          type="button"
        >
          Odśwież wszystko
        </button>
      </header>

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
        <ReleaseState
          text="Pobieram aktywne gry, opublikowane źródła i historię wydań…"
          title="Wczytywanie"
        />
      ) : loadState === 'error' ? (
        <ReleaseState
          error
          onRetry={() => void loadWorkspace()}
          text={error}
          title="Nie udało się wczytać wydań"
        />
      ) : (
        <>
          <form className="releaseComposer" onSubmit={onCreate}>
            <div className="releaseComposerHeader">
              <div>
                <p className="eyebrow">Jedna kontrolowana gra</p>
                <h2>Przygotuj testowe wydanie</h2>
              </div>
              <label className="releaseVersionField">
                Wersja wydania
                <input
                  maxLength={100}
                  onChange={(event) => setVersion(event.target.value)}
                  placeholder="np. m3.4.1"
                  value={version}
                />
              </label>
            </div>

            {sources.length === 0 ? (
              <ReleaseState
                text="Aktywuj grę i opublikuj dla niej zgodny dataset oraz wersję reguł."
                title="Brak aktywnych gier"
              />
            ) : (
              <div className="releaseControlledSource">
                <label className="releaseGameField">
                  Gra testowa
                  <select
                    onChange={(event) => onGameChanged(event.target.value)}
                    value={selectedSelection?.gameId ?? ''}
                  >
                    <option value="">Wybierz gotową grę</option>
                    {sources.map((source) => (
                      <option
                        disabled={!hasCompatibleReleasePair(source)}
                        key={source.game.id}
                        value={source.game.id}
                      >
                        {source.game.name} · {source.game.code}
                        {!hasCompatibleReleasePair(source)
                          ? ' · brak gotowych źródeł'
                          : ''}
                      </option>
                    ))}
                  </select>
                </label>
                {selectedSource && selectedDataset && selectedRules ? (
                  <dl className="releaseSourceSummary">
                    <div>
                      <dt>Dataset</dt>
                      <dd>
                        v{selectedDataset.version} ·{' '}
                        {selectedDataset.layoutCount.toLocaleString('pl-PL')}{' '}
                        layoutów
                      </dd>
                    </div>
                    <div>
                      <dt>Reguły</dt>
                      <dd>
                        v{selectedRules.version} · koszt{' '}
                        {selectedRules.spinCost}
                      </dd>
                    </div>
                    <div>
                      <dt>Plansza</dt>
                      <dd>
                        {selectedDataset.rows}×{selectedDataset.columns}
                      </dd>
                    </div>
                  </dl>
                ) : (
                  <p className="releaseSourceWarning">
                    Wybrana gra wymaga zgodnego opublikowanego datasetu i reguł.
                  </p>
                )}
              </div>
            )}

            <div className="releaseComposerFooter">
              <p>
                Najnowsza zgodna para dataset/reguły zostanie zamrożona
                automatycznie.
              </p>
              <button
                className="primaryButton"
                disabled={isCreating || selectedSelection === null}
                type="submit"
              >
                {isCreating
                  ? 'Uruchamianie workflow…'
                  : 'Utwórz i uruchom wydanie'}
              </button>
            </div>
          </form>

          <details className="releaseHistoryDisclosure" open>
            <summary>
              <span>Historia wydań</span>
              <strong>{releases.length}</strong>
            </summary>
            <div className="releaseWorkspace">
              <div className="releaseHistoryPanel">
                <div className="listHeader">
                  <div>
                    <p className="eyebrow">Historia</p>
                    <h2>Wydania</h2>
                  </div>
                  <p>
                    Najnowsze pierwsze · poprzednie artefakty pozostają dostępne
                  </p>
                </div>
                {releases.length === 0 ? (
                  <ReleaseState
                    text="Utwórz pierwszy draft z formularza powyżej."
                    title="Brak wydań"
                  />
                ) : (
                  <div className="releaseHistoryList">
                    {releases.map((release) => (
                      <button
                        aria-pressed={release.id === selectedReleaseId}
                        className={`releaseHistoryItem ${
                          release.id === selectedReleaseId
                            ? 'releaseHistoryItemSelected'
                            : ''
                        }`}
                        key={release.id}
                        onClick={() => setSelectedReleaseId(release.id)}
                        type="button"
                      >
                        <span>
                          <strong>{release.version}</strong>
                          <small>
                            {formatReleaseTimestamp(release.createdAt)}
                          </small>
                        </span>
                        <span
                          className={`releaseStatus releaseStatus-${release.status}`}
                        >
                          {releaseStatusLabel(release.status)}
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {selectedRelease === null ? (
                <ReleaseState
                  text="Wybierz lub utwórz wydanie, aby zobaczyć jego niezmienny skład."
                  title="Brak wybranego wydania"
                />
              ) : (
                <ReleaseDetail
                  apiBaseUrl={apiBaseUrl}
                  cleanupClient={api}
                  isBuilding={isBuilding}
                  isDownloading={downloadingReleaseId === selectedRelease.id}
                  isRefreshing={isRefreshing}
                  isRetrying={isRetrying}
                  job={visibleJob}
                  onBuild={() => void onBuild(selectedRelease)}
                  onCopy={(path) => void copyArtifactPath(path)}
                  onDownload={() => void onDownload(selectedRelease)}
                  onDeleted={() => onReleaseDeleted(selectedRelease.id)}
                  onOpenJobs={onOpenJobs}
                  onRefresh={() => void refreshSelected(true)}
                  onRetry={() => void onRetry()}
                  release={selectedRelease}
                />
              )}
            </div>
          </details>
        </>
      )}
    </section>
  );
}

function ReleaseDetail({
  apiBaseUrl,
  cleanupClient,
  isBuilding,
  isDownloading,
  isRefreshing,
  isRetrying,
  job,
  onBuild,
  onCopy,
  onDownload,
  onDeleted,
  onOpenJobs,
  onRefresh,
  onRetry,
  release,
}: {
  readonly apiBaseUrl: string;
  readonly cleanupClient: ReleasesClient;
  readonly isBuilding: boolean;
  readonly isDownloading: boolean;
  readonly isRefreshing: boolean;
  readonly isRetrying: boolean;
  readonly job: JobResponse | null;
  readonly onBuild: () => void;
  readonly onCopy: (path: string) => void;
  readonly onDownload: () => void;
  readonly onDeleted: () => void;
  readonly onOpenJobs?: () => void;
  readonly onRefresh: () => void;
  readonly onRetry: () => void;
  readonly release: MobileReleaseResponse;
}) {
  return (
    <article className="releaseDetailPanel">
      <header className="releaseDetailHeader">
        <div>
          <p className="eyebrow">Wybrane wydanie</p>
          <h2>{release.version}</h2>
          <code title={release.id}>{release.id}</code>
        </div>
        <div className="releaseDetailActions">
          <span className={`releaseStatus releaseStatus-${release.status}`}>
            {releaseStatusLabel(release.status)}
          </span>
          <button
            className="secondaryButton"
            disabled={isRefreshing}
            onClick={onRefresh}
            type="button"
          >
            {isRefreshing ? 'Odświeżanie…' : 'Odśwież'}
          </button>
          {release.status === 'draft' ? (
            <button
              className="primaryButton"
              disabled={isBuilding}
              onClick={onBuild}
              type="button"
            >
              {isBuilding ? 'Uruchamianie…' : 'Uruchom build'}
            </button>
          ) : null}
        </div>
      </header>

      <dl className="releaseMetadata">
        <div>
          <dt>Algorytm</dt>
          <dd>{release.algorithmVersion}</dd>
        </div>
        <div>
          <dt>Schema snapshotu</dt>
          <dd>{release.snapshotSchemaVersion}</dd>
        </div>
        <div>
          <dt>Utworzono</dt>
          <dd>{formatReleaseTimestamp(release.createdAt)}</dd>
        </div>
        <div>
          <dt>Gotowe</dt>
          <dd>{formatReleaseTimestamp(release.readyAt)}</dd>
        </div>
      </dl>

      <div className="releaseGamesTableWrap">
        <table className="releaseGamesTable">
          <thead>
            <tr>
              <th>Gra</th>
              <th>Dataset</th>
              <th>Reguły</th>
              <th>Layouty</th>
              <th>Plansza</th>
            </tr>
          </thead>
          <tbody>
            {release.games.map((game) => (
              <tr key={game.gameId}>
                <td>
                  <strong>{game.gameCode}</strong>
                  <code>{game.gameId}</code>
                </td>
                <td>
                  v{game.datasetVersion}
                  <code>{game.datasetVersionId}</code>
                </td>
                <td>
                  v{game.rulesVersion}
                  <code>{game.rulesVersionId}</code>
                </td>
                <td>{game.layoutCount.toLocaleString('pl-PL')}</td>
                <td>
                  {game.rows}×{game.columns}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {job ? (
        <ReleaseJob
          isRetrying={isRetrying}
          job={job}
          onOpenJobs={onOpenJobs}
          onRetry={onRetry}
        />
      ) : release.buildJobId ? (
        <p className="releaseJobPlaceholder">
          Pobieram powiązany job <code>{release.buildJobId}</code>…
        </p>
      ) : null}

      <div className="releaseArtifacts">
        <ArtifactCard
          checksum={release.snapshot?.checksum ?? null}
          kind="Snapshot SQLite"
          onCopy={onCopy}
          path={release.snapshot?.relativePath ?? null}
        />
        <ArtifactCard
          checksum={release.apk?.checksum ?? null}
          download={
            release.status === 'ready' && release.apk !== null
              ? { busy: isDownloading, onDownload }
              : null
          }
          kind="Android APK"
          onCopy={onCopy}
          path={release.apk?.relativePath ?? null}
        />
      </div>

      <CleanupControl
        apiBaseUrl={apiBaseUrl}
        client={cleanupClient}
        onCompleted={onDeleted}
        target={{ id: release.id, kind: 'mobile-release' }}
        targetLabel={`Wydanie ${release.version}`}
      />
    </article>
  );
}

function ReleaseJob({
  isRetrying,
  job,
  onOpenJobs,
  onRetry,
}: {
  readonly isRetrying: boolean;
  readonly job: JobResponse;
  readonly onOpenJobs?: () => void;
  readonly onRetry: () => void;
}) {
  return (
    <section className={`releaseJob releaseJob-${job.status}`}>
      <div className="releaseJobHeader">
        <div>
          <p className="eyebrow">Powiązany job</p>
          <strong>{jobStatusLabel(job.status)}</strong>
          <code>{job.id}</code>
        </div>
        <div className="rowActions">
          {onOpenJobs ? (
            <button
              className="secondaryButton"
              onClick={onOpenJobs}
              type="button"
            >
              Pokaż w Jobach
            </button>
          ) : null}
          {canRetryJob(job) ? (
            <button
              className="primaryButton"
              disabled={isRetrying}
              onClick={onRetry}
              type="button"
            >
              {isRetrying ? 'Ponawianie…' : 'Wznów ten sam job'}
            </button>
          ) : null}
        </div>
      </div>
      <p>Pełny postęp, etap i diagnostyka są dostępne w workspace `Joby`.</p>
      {job.error ? (
        <div className="jobError" role="alert">
          <strong>{job.error.code}</strong>
          <p>{job.error.message}</p>
        </div>
      ) : null}
    </section>
  );
}

function ArtifactCard({
  checksum,
  download = null,
  kind,
  onCopy,
  path,
}: {
  readonly checksum: string | null;
  readonly download?: {
    readonly busy: boolean;
    readonly onDownload: () => void;
  } | null;
  readonly kind: string;
  readonly onCopy: (path: string) => void;
  readonly path: string | null;
}) {
  return (
    <section className={`artifactCard ${path ? 'artifactCardReady' : ''}`}>
      <div>
        <p className="eyebrow">Artefakt</p>
        <h3>{kind}</h3>
      </div>
      {path && checksum ? (
        <>
          <dl>
            <div>
              <dt>Ścieżka względna</dt>
              <dd>
                <code>{path}</code>
              </dd>
            </div>
            <div>
              <dt>SHA-256</dt>
              <dd>
                <code>{checksum}</code>
              </dd>
            </div>
          </dl>
          <div className="artifactActions">
            <button
              className="secondaryButton"
              onClick={() => onCopy(path)}
              type="button"
            >
              Kopiuj ścieżkę
            </button>
            {download ? (
              <button
                className="primaryButton"
                disabled={download.busy}
                onClick={download.onDownload}
                type="button"
              >
                {download.busy ? 'Pobieranie…' : 'Pobierz APK'}
              </button>
            ) : null}
          </div>
        </>
      ) : (
        <p className="artifactPending">
          Artefakt pojawi się dopiero po zweryfikowanym checkpointcie workflow.
        </p>
      )}
    </section>
  );
}

function ReleaseState({
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
      <span aria-hidden="true">{error ? '!' : '…'}</span>
      <div>
        <h2>{title}</h2>
        <p>{text}</p>
      </div>
      {onRetry ? (
        <button className="secondaryButton" onClick={onRetry} type="button">
          Spróbuj ponownie
        </button>
      ) : null}
    </div>
  );
}
