'use client';

import type {
  AdminApiClient,
  FilenameRangeVerificationItemResponse,
  SemiAutomaticSelectionRunResponse,
} from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';
import { apiErrorMessage } from '@/features/catalog/catalog-api-error';
import {
  jobProgressLabel,
  jobProgressPercent,
} from '@/features/jobs/job-state';
import {
  uploadSemiAutomaticSelectionFolder,
  type BrowserDirectoryHandle,
  type SemiAutomaticSelectionClient,
  type SemiAutomaticSelectionUploadProgress,
  type SemiAutomaticSourceFile,
} from '@/features/semi-automatic-image-selection/semi-automatic-selection-actions.ts';
import { resolveAdminApiBaseUrl } from '@/config/admin-api';
import {
  isLocalDirectoryPickerActive,
  pickLocalDirectory,
  subscribeLocalDirectoryPickerActive,
} from '../../lib/local-directory-picker.ts';

import {
  directoryPermissionIsGranted,
  FilenameRangeVerificationStore,
  type FilenameRangeVerificationLocalState,
  type FilenameVerificationRejectedSource,
} from './filename-range-verification-store';
import { ManualImageViewer, useManualImageViewer } from './manual-image-viewer';
import {
  deleteRepairFile,
  inspectRepairDirectory,
  writeRepairManifest,
  type RepairDirectorySnapshot,
} from './manual-selection-repair-storage.ts';

const EMPTY_UPLOAD: SemiAutomaticSelectionUploadProgress = {
  totalBytes: 0,
  totalFiles: 0,
  uploadedBytes: 0,
  uploadedFiles: 0,
};
const HISTORY_LIMIT = 20;
const LAST_RUN_KEY = 'game-predictor:filename-range-verification:last-run-id';
const POLL_INTERVAL_MS = 2_000;

type ReviewView = 'pending' | 'all';
type VerificationClient = SemiAutomaticSelectionClient &
  Pick<
    AdminApiClient,
    | 'decideSemiAutomaticFilenameRangeVerification'
    | 'getSemiAutomaticImageSelection'
    | 'getSemiAutomaticImageSelectionCapabilities'
    | 'listSemiAutomaticFilenameRangeVerifications'
    | 'listSemiAutomaticImageSelections'
    | 'retryJob'
  >;

export function ManualSelectionRangeVerificationWorkspace({
  apiBaseUrl,
  client,
}: {
  readonly apiBaseUrl: string;
  readonly client?: VerificationClient;
}) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const apiOrigin = useMemo(
    () => resolveAdminApiBaseUrl(apiBaseUrl),
    [apiBaseUrl],
  );
  const store = useMemo(() => new FilenameRangeVerificationStore(), []);
  const busyRef = useRef(false);
  const selectedRunRef = useRef<string | null>(null);
  const localStateRestoredRunRef = useRef<string | null>(null);
  const historyRequestRef = useRef(0);
  const [snapshot, setSnapshot] = useState<RepairDirectorySnapshot | null>(
    null,
  );
  const [run, setRun] = useState<SemiAutomaticSelectionRunResponse | null>(
    null,
  );
  const [runs, setRuns] = useState<
    readonly SemiAutomaticSelectionRunResponse[]
  >([]);
  const [items, setItems] = useState<
    readonly FilenameRangeVerificationItemResponse[]
  >([]);
  const [cursor, setCursor] = useState(0);
  const [reviewView, setReviewView] = useState<ReviewView>('pending');
  const [upload, setUpload] = useState(EMPTY_UPLOAD);
  const [busy, setBusy] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [directoryPickerActive, setDirectoryPickerActive] = useState(
    isLocalDirectoryPickerActive,
  );
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const flagged = useMemo(
    () => items.filter((item) => item.verificationStatus !== 'verified'),
    [items],
  );
  const reviewItems = useMemo(
    () =>
      flagged.filter(
        (item) =>
          reviewView === 'all' ||
          item.reviewDecision === null ||
          item.reviewDecision === undefined,
      ),
    [flagged, reviewView],
  );
  const safeCursor = Math.min(cursor, Math.max(0, reviewItems.length - 1));
  const current = reviewItems[safeCursor];
  const handleViewerError = useCallback(
    (message: string) => setError(message),
    [],
  );
  const remoteImages = useMemo(() => {
    if (run === null) return [];
    return reviewItems.map((item) => ({
      handle: remoteAssetHandle(apiOrigin, run.id, item),
      relativePath: item.sourceRelativePath,
    }));
  }, [apiOrigin, reviewItems, run]);
  const viewer = useManualImageViewer(
    remoteImages,
    current === undefined ? -1 : safeCursor,
    handleViewerError,
  );

  const persistLocalState = useCallback(
    async (
      activeRun: SemiAutomaticSelectionRunResponse,
      nextCursor: number,
      pendingDecision:
        | FilenameRangeVerificationLocalState['pendingDecision']
        | undefined = undefined,
      localSnapshot: RepairDirectorySnapshot | null = snapshot,
      rejectedSources:
        readonly FilenameVerificationRejectedSource[] | undefined = undefined,
    ): Promise<void> => {
      const previous = await store.load(activeRun.id);
      await store.save({
        runId: activeRun.id,
        directory: localSnapshot?.directory ?? previous?.directory ?? null,
        sourceFingerprint: activeRun.source.sourceFingerprint,
        sourceManifestChecksumSha256: activeRun.source.manifestChecksumSha256,
        cursor: nextCursor,
        pendingDecision:
          pendingDecision === undefined
            ? (previous?.pendingDecision ?? null)
            : pendingDecision,
        rejectedSources: rejectedSources ?? previous?.rejectedSources ?? [],
        updatedAt: new Date().toISOString(),
      });
    },
    [snapshot, store],
  );

  const loadItems = useCallback(
    async (targetRun: SemiAutomaticSelectionRunResponse): Promise<void> => {
      if (!isReviewable(targetRun)) {
        setItems([]);
        return;
      }
      const loaded = await fetchVerificationItems(api, targetRun.id);
      if (selectedRunRef.current !== targetRun.id) return;
      if (loaded.error !== null) {
        setError(loaded.error);
        return;
      }
      setItems(loaded.items);
    },
    [api],
  );

  const restoreRunLocalState = useCallback(
    async (targetRun: SemiAutomaticSelectionRunResponse): Promise<void> => {
      const local = await store.load(targetRun.id);
      if (selectedRunRef.current !== targetRun.id || local === null) return;
      setCursor(local.cursor);
      let pendingDeleteApplied = false;
      if (local.pendingDecision !== null && local.directory === null) {
        setNotice(
          'Lokalne usunięcie czeka na ponowne połączenie katalogu przed zapisem decyzji.',
        );
        return;
      }
      if (local.directory !== null) {
        if (!(await directoryPermissionIsGranted(local.directory))) {
          if (local.pendingDecision !== null) {
            setNotice(
              'Lokalne usunięcie czeka na potwierdzenie katalogu przed zapisem decyzji.',
            );
          }
          return;
        }
        try {
          const inspected = await inspectRepairDirectory(local.directory);
          pendingDeleteApplied =
            local.pendingDecision !== null &&
            pendingDeleteWasApplied(inspected, local.pendingDecision);
          const expectedRejected =
            local.pendingDecision !== null && pendingDeleteApplied
              ? appendRejectedSource(
                  local.rejectedSources,
                  local.pendingDecision,
                )
              : local.rejectedSources;
          if (
            await sourceDirectoryMatchesRun(
              inspected,
              targetRun,
              expectedRejected,
            )
          ) {
            setSnapshot(inspected);
          } else if (local.pendingDecision !== null) {
            setNotice(
              'Lokalny katalog nie potwierdza bezpiecznie wcześniejszego usunięcia.',
            );
            return;
          }
        } catch {
          if (local.pendingDecision !== null) {
            setNotice(
              'Lokalny journal usunięcia wymaga sprawdzenia przed zapisem decyzji.',
            );
          }
          return;
        }
      }
      if (local.pendingDecision !== null && !pendingDeleteApplied) {
        await store.save({
          ...local,
          pendingDecision: null,
          updatedAt: new Date().toISOString(),
        });
        setNotice(
          'Usunięcie nie zostało wykonane; decyzja nie została wysłana.',
        );
        return;
      }
      if (local.pendingDecision !== null && pendingDeleteApplied) {
        const repair = await api.decideSemiAutomaticFilenameRangeVerification(
          targetRun.id,
          local.pendingDecision.sourceIndex,
          {
            decision: 'reject',
            expectedRevision: local.pendingDecision.expectedRevision,
            expectedSourceChecksumSha256:
              local.pendingDecision.sourceChecksumSha256,
          },
        );
        if (repair.error === undefined && repair.data !== undefined) {
          await store.save({
            ...local,
            pendingDecision: null,
            rejectedSources: appendRejectedSource(
              local.rejectedSources,
              local.pendingDecision,
            ),
            updatedAt: new Date().toISOString(),
          });
          setNotice(
            'Dokończono zapis decyzji po wcześniejszym lokalnym usunięciu.',
          );
        } else {
          setNotice('Lokalne usunięcie czeka na potwierdzenie serwera.');
        }
      }
    },
    [api, store],
  );

  const selectRun = useCallback(
    async (targetRun: SemiAutomaticSelectionRunResponse): Promise<void> => {
      selectedRunRef.current = targetRun.id;
      localStateRestoredRunRef.current = null;
      window.localStorage.setItem(LAST_RUN_KEY, targetRun.id);
      setRun(targetRun);
      setItems([]);
      setCursor(0);
      setSnapshot(null);
      setError('');
      await restoreRunLocalState(targetRun);
      if (selectedRunRef.current !== targetRun.id) return;
      localStateRestoredRunRef.current = targetRun.id;
      await loadItems(targetRun);
    },
    [loadItems, restoreRunLocalState],
  );

  const loadHistory = useCallback(async (): Promise<void> => {
    const request = historyRequestRef.current + 1;
    historyRequestRef.current = request;
    setHistoryLoading(true);
    const result = await api.listSemiAutomaticImageSelections(
      'filename_verification',
      0,
      HISTORY_LIMIT,
    );
    if (historyRequestRef.current !== request) return;
    setHistoryLoading(false);
    if (result.error !== undefined || result.data === undefined) {
      setError(
        apiErrorMessage(
          result.error,
          'Nie udało się pobrać historii weryfikacji.',
        ),
      );
      return;
    }
    setRuns(result.data.items);
    if (selectedRunRef.current !== null) return;
    const savedId = window.localStorage.getItem(LAST_RUN_KEY);
    const preferred =
      result.data.items.find((item) => item.id === savedId) ??
      result.data.items.find(isActive) ??
      result.data.items[0];
    if (preferred !== undefined) await selectRun(preferred);
  }, [api, selectRun]);

  useEffect(() => {
    void Promise.resolve().then(loadHistory);
  }, [loadHistory]);

  useEffect(() => {
    return subscribeLocalDirectoryPickerActive(() => {
      setDirectoryPickerActive(isLocalDirectoryPickerActive());
    });
  }, []);

  useEffect(() => {
    if (run === null || !isActive(run)) return undefined;
    const runId = run.id;
    let cancelled = false;
    let timer: number | null = null;
    const poll = async (): Promise<void> => {
      const result = await api.getSemiAutomaticImageSelection(runId);
      if (cancelled || selectedRunRef.current !== runId) return;
      if (result.error !== undefined || result.data === undefined) {
        setNotice('Nie udało się odświeżyć progresu. Ponawiam próbę.');
      } else {
        setRun(result.data);
        setRuns((existing) => replaceRun(existing, result.data));
        if (!isActive(result.data)) {
          await loadItems(result.data);
          return;
        }
      }
      timer = window.setTimeout(() => void poll(), POLL_INTERVAL_MS);
    };
    timer = window.setTimeout(() => void poll(), POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      if (timer !== null) window.clearTimeout(timer);
    };
  }, [api, loadItems, run]);

  useEffect(() => {
    if (run === null || localStateRestoredRunRef.current !== run.id) return;
    void persistLocalState(run, cursor);
  }, [cursor, persistLocalState, run]);

  async function chooseDirectory(): Promise<void> {
    if (busyRef.current) return;
    setError('');
    try {
      const directory = await pickReadWriteDirectory();
      const inspected = await inspectRepairDirectory(directory);
      if (run !== null) {
        const local = await store.load(run.id);
        if (
          !(await sourceDirectoryMatchesRun(
            inspected,
            run,
            local?.rejectedSources ?? [],
          ))
        ) {
          throw new Error(
            'Wybrany katalog nie odpowiada fingerprintowi źródeł tego procesu.',
          );
        }
      }
      await writeRepairManifest(directory, inspected.repairManifest);
      setSnapshot(inspected);
      setUpload(EMPTY_UPLOAD);
      if (run !== null) {
        await persistLocalState(run, cursor, undefined, inspected);
        setNotice(
          `Połączono ${inspected.files.length.toLocaleString('pl-PL')} plików seq_* dla usuwania.`,
        );
      } else {
        setNotice(
          `Wybrano ${inspected.files.length.toLocaleString('pl-PL')} plików seq_*.`,
        );
      }
    } catch (cause) {
      if (!isPickerCancellation(cause)) setError(errorMessage(cause));
    }
  }

  async function start(): Promise<void> {
    if (snapshot === null || busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError('');
    setNotice('Przygotowuję bezpieczny staging i uruchamiam OCR zakresów.');
    try {
      const files: SemiAutomaticSourceFile[] = await Promise.all(
        snapshot.files.map(async (item) => ({
          file: await item.handle.getFile(),
          handle: item.handle,
          relativePath: item.fileName,
        })),
      );
      const result = await uploadSemiAutomaticSelectionFolder({
        api,
        direction: 'ascending',
        files,
        firstSequenceNumber: snapshot.repairManifest.collectionStart,
        lastSequenceNumber: snapshot.repairManifest.collectionEnd,
        mode: 'filename_verification',
        onProgress: setUpload,
        sourceDirectory: snapshot.directory as BrowserDirectoryHandle,
      });
      if (!result.ok) {
        setError(result.error);
        return;
      }
      setRuns((existing) => [
        result.created.run,
        ...existing.filter((item) => item.id !== result.created.run.id),
      ]);
      await selectRun(result.created.run);
      await persistLocalState(result.created.run, 0, undefined, snapshot);
      setNotice(
        'Weryfikacja działa w tle. Jej status pozostanie na liście po odświeżeniu strony.',
      );
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }

  async function retryAnalysis(): Promise<void> {
    if (run === null || run.job.status !== 'failed' || busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError('');
    try {
      const result = await api.retryJob(run.job.id);
      if (result.error !== undefined || result.data === undefined) {
        setError(apiErrorMessage(result.error, 'Nie udało się wznowić analizy.'));
        return;
      }
      // The worker turns the durable run back to `running` at its first
      // checkpoint.  Reflect the requeued job now so the existing poller
      // starts immediately instead of leaving a failed view frozen.
      const resumed = { ...run, job: result.data, status: 'running' as const };
      setRun(resumed);
      setRuns((existing) => replaceRun(existing, resumed));
      setNotice(
        'Wznowiono analizę z zapisanych obserwacji OCR — obrazy nie będą odczytywane ponownie.',
      );
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }

  async function decideCurrent(decision: 'keep' | 'reject'): Promise<void> {
    if (run === null || current === undefined || busyRef.current) return;
    if (decision === 'reject' && snapshot === null) {
      setNotice(
        'Aby usunąć plik, najpierw wybierz i zweryfikuj lokalny katalog seq_*.',
      );
      return;
    }
    busyRef.current = true;
    setBusy(true);
    setError('');
    const expectedRevision = current.reviewRevision ?? 0;
    try {
      if (decision === 'reject') {
        const selected = findLocalFile(snapshot!, current);
        if (selected === undefined) {
          throw new Error(
            'Plik wskazany przez wynik OCR nie istnieje już w katalogu.',
          );
        }
        await persistLocalState(
          run,
          safeCursor,
          {
            sourceIndex: current.sourceIndex,
            sourceChecksumSha256: current.sourceChecksumSha256,
            sourceRelativePath: current.sourceRelativePath,
            sourceSizeBytes: current.sourceSizeBytes,
            expectedRevision,
          },
          snapshot,
        );
        const result = await deleteRepairFile({
          directory: snapshot!.directory,
          expectedChecksumSha256: current.sourceChecksumSha256,
          fileName: selected.fileName,
          kind: 'delete',
          manifest: snapshot!.repairManifest,
          outputManifest: snapshot!.outputManifest,
          sourceIndex: current.sourceIndex,
          sourcePath: current.sourceRelativePath,
        });
        setSnapshot({
          ...snapshot!,
          files: snapshot!.files.filter(
            (file) => file.fileName !== selected.fileName,
          ),
          outputManifest: result.outputManifest,
          repairManifest: result.manifest,
        });
      }
      const response = await api.decideSemiAutomaticFilenameRangeVerification(
        run.id,
        current.sourceIndex,
        {
          decision,
          expectedRevision,
          expectedSourceChecksumSha256: current.sourceChecksumSha256,
        },
      );
      if (response.error !== undefined || response.data === undefined) {
        if (decision === 'reject') {
          setNotice(
            'Plik został lokalnie usunięty; serwerowe potwierdzenie zostanie naprawione po ponownym wejściu.',
          );
        }
        setError(
          apiErrorMessage(response.error, 'Nie udało się zapisać decyzji.'),
        );
        return;
      }
      setItems((existing) =>
        existing.map((item) =>
          item.sourceIndex === current.sourceIndex
            ? {
                ...item,
                reviewDecision: response.data.decision,
                reviewRevision: response.data.revision,
              }
            : item,
        ),
      );
      const nextCursor = Math.min(
        safeCursor,
        Math.max(0, reviewItems.length - 2),
      );
      setCursor(nextCursor);
      await persistLocalState(
        run,
        nextCursor,
        null,
        undefined,
        decision === 'reject'
          ? appendRejectedSource(
              (await store.load(run.id))?.rejectedSources ?? [],
              {
                sourceIndex: current.sourceIndex,
                sourceChecksumSha256: current.sourceChecksumSha256,
                sourceRelativePath: current.sourceRelativePath,
                sourceSizeBytes: current.sourceSizeBytes,
              },
            )
          : undefined,
      );
      setNotice(
        decision === 'keep'
          ? 'Zapisano decyzję „Zostaw plik”.'
          : 'Usunięto plik i zapisano decyzję „Odrzuć”.',
      );
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if (isEditable(event.target) || current === undefined || busyRef.current)
        return;
      if (event.key.toLocaleLowerCase('en-US') === 'k') {
        event.preventDefault();
        void decideCurrent('keep');
      }
      if (event.key.toLocaleLowerCase('en-US') === 'f') {
        event.preventDefault();
        void decideCurrent('reject');
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  });

  const uploadPercent =
    upload.totalBytes === 0
      ? 0
      : (upload.uploadedBytes / upload.totalBytes) * 100;
  const runPercent = run === null ? null : jobProgressPercent(run.job);
  const hasReview = run !== null && isReviewable(run) && items.length > 0;

  return (
    <section className="manualImageSelectionWorkspace manualSelectionRepairSetup">
      <header className="manualImageSelectionHeader">
        <div>
          <p className="eyebrow">Niezależnie od gry · staging serwera</p>
          <h2>Weryfikacja zakresów</h2>
          <p>
            Sprawdź OCR zakresów plików seq_*. Podgląd działa od razu ze
            stagingu; lokalny katalog jest wymagany dopiero do usunięcia pliku.
          </p>
        </div>
      </header>

      <div className="manualImageSelectionSetup">
        <button
          className="secondaryButton"
          disabled={busy || directoryPickerActive}
          onClick={() => void chooseDirectory()}
          type="button"
        >
          {run === null
            ? 'Wybierz katalog z plikami seq_*'
            : 'Połącz katalog seq_*'}
        </button>
        {snapshot !== null ? (
          <p className="manualImageSelectionReady">
            {snapshot.directory.name} ·{' '}
            {snapshot.files.length.toLocaleString('pl-PL')} plików
          </p>
        ) : null}
        {run === null ? (
          <button
            className="primaryButton"
            disabled={busy || snapshot === null}
            onClick={() => void start()}
            type="button"
          >
            Start
          </button>
        ) : null}
        {upload.totalFiles > 0 && run === null ? (
          <Progress
            label={`${upload.uploadedFiles} / ${upload.totalFiles}`}
            value={uploadPercent}
          />
        ) : null}
        {run !== null ? (
          <Progress label={jobProgressLabel(run.job)} value={runPercent} />
        ) : null}
        {notice !== '' ? (
          <p className="manualImageSelectionStatus">{notice}</p>
        ) : null}
        {error !== '' ? (
          <p className="formError" role="alert">
            {error}
          </p>
        ) : null}
      </div>

      <section
        className="manualSelectionRepairHistory"
        aria-label="Zapisane procesy weryfikacji zakresów"
      >
        <h3>Zapisane procesy</h3>
        {historyLoading ? <p>Ładowanie historii…</p> : null}
        {!historyLoading && runs.length === 0 ? (
          <p>Brak zapisanych procesów weryfikacji zakresów.</p>
        ) : null}
        <div className="manualSelectionRepairHistoryList">
          {runs.map((candidate) => (
            <button
              className={
                candidate.id === run?.id
                  ? 'manualSelectionRepairHistoryItem selected'
                  : 'manualSelectionRepairHistoryItem'
              }
              key={candidate.id}
              onClick={() => void selectRun(candidate)}
              type="button"
            >
              <strong>{candidate.source.displayName}</strong>
              <span>
                {new Date(candidate.createdAt).toLocaleString('pl-PL')} ·{' '}
                {candidate.source.sourceCount.toLocaleString('pl-PL')} zdjęć
              </span>
              <span>
                {jobProgressLabel(candidate.job)} ·{' '}
                {formatPercent(jobProgressPercent(candidate.job))}
              </span>
            </button>
          ))}
        </div>
      </section>

      {run !== null && !isReviewable(run) ? (
        <div className="manualImageSelectionActions">
          <p className="manualImageSelectionStatus">
            Ten proces ma status „{jobProgressLabel(run.job)}”. Wyniki review będą
            dostępne po poprawnym zakończeniu.
          </p>
          {run.job.status === 'failed' ? (
            <button
              className="primaryButton"
              disabled={busy}
              onClick={() => void retryAnalysis()}
              type="button"
            >
              Wznów analizę
            </button>
          ) : null}
        </div>
      ) : null}
      {run !== null && isReviewable(run) ? (
        <section className="manualImageSelectionActive">
          {hasReview ? (
            <div className="manualImageSelectionActions">
              <button
                className={
                  reviewView === 'pending' ? 'primaryButton' : 'secondaryButton'
                }
                onClick={() => {
                  setReviewView('pending');
                  setCursor(0);
                }}
                type="button"
              >
                Nierozpatrzone (
                {
                  flagged.filter(
                    (item) =>
                      item.reviewDecision === null ||
                      item.reviewDecision === undefined,
                  ).length
                }
                )
              </button>
              <button
                className={
                  reviewView === 'all' ? 'primaryButton' : 'secondaryButton'
                }
                onClick={() => {
                  setReviewView('all');
                  setCursor(0);
                }}
                type="button"
              >
                Wszystkie oznaczone ({flagged.length})
              </button>
            </div>
          ) : null}
          {hasReview ? (
            <p>
              {current === undefined
                ? 'Brak pozycji w tym widoku.'
                : `Do ręcznej kontroli: ${safeCursor + 1} z ${reviewItems.length}`}
            </p>
          ) : null}
          {current !== undefined ? (
            <>
              <p className="manualSelectionRepairWarning" role="status">
                {verificationMessage(current)}
                {current.reviewDecision === 'keep'
                  ? ' · pozostawiono.'
                  : current.reviewDecision === 'reject'
                    ? ' · usunięto (tylko odczyt).'
                    : ''}
              </p>
              <ManualImageViewer
                busy={busy}
                currentLabel={`Nazwa: ${formatRange(current.expectedRange)} · OCR: ${formatRange(current.observedRange)}`}
                currentPosition={safeCursor + 1}
                currentRelativePath={current.sourceRelativePath}
                imageCount={reviewItems.length}
                navigationStepLabel="skok: 1"
                nextDisabled={safeCursor >= reviewItems.length - 1}
                onNext={() =>
                  setCursor((value) =>
                    Math.min(reviewItems.length - 1, value + 1),
                  )
                }
                onPrevious={() => setCursor((value) => Math.max(0, value - 1))}
                previousDisabled={safeCursor <= 0}
                state={viewer}
                toolbarStart={
                  <span className="manualImageSelectionStep">skok: 1</span>
                }
              />
              {current.reviewDecision === null ||
              current.reviewDecision === undefined ? (
                <div className="manualImageSelectionActions">
                  <button
                    className="secondaryButton"
                    disabled={busy}
                    onClick={() => void decideCurrent('keep')}
                    type="button"
                  >
                    Zostaw plik K
                  </button>
                  <button
                    className="dangerButton"
                    disabled={busy || snapshot === null}
                    onClick={() => void decideCurrent('reject')}
                    type="button"
                  >
                    Odrzuć i usuń F
                  </button>
                </div>
              ) : null}
              {snapshot === null &&
              (current.reviewDecision === null ||
                current.reviewDecision === undefined) ? (
                <p className="manualImageSelectionStatus">
                  Usunięcie wymaga przycisku „Połącz katalog seq_*”; podgląd
                  pozostaje dostępny ze stagingu.
                </p>
              ) : null}
            </>
          ) : null}
          <ReviewCounters items={items} />
          {!hasReview ? (
            <p className="manualImageSelectionStatus">
              Wszystkie zakresy tego procesu zostały zgodnie odczytane
              automatycznie.
            </p>
          ) : null}
        </section>
      ) : null}
    </section>
  );
}

function Progress({
  label,
  value,
}: {
  readonly label: string;
  readonly value: number | null;
}) {
  return (
    <div className="jobProgressSection">
      <div className="jobProgressSummary">
        <strong>{label}</strong>
        <span>{formatPercent(value)}</span>
      </div>
      <progress max={100} value={value ?? 0} />
    </div>
  );
}

function ReviewCounters({
  items,
}: {
  readonly items: readonly FilenameRangeVerificationItemResponse[];
}) {
  const flagged = items.filter(
    (item) => item.verificationStatus !== 'verified',
  );
  const verified = items.length - flagged.length;
  const kept = flagged.filter((item) => item.reviewDecision === 'keep').length;
  const rejected = flagged.filter(
    (item) => item.reviewDecision === 'reject',
  ).length;
  const remaining = flagged.length - kept - rejected;
  return (
    <p className="manualImageSelectionStatus">
      Zgodne automatycznie: {verified} · do sprawdzenia: {flagged.length} ·
      pozostawione: {kept} · usunięte: {rejected} · pozostałe: {remaining}
    </p>
  );
}

async function fetchVerificationItems(
  api: VerificationClient,
  runId: string,
): Promise<{
  readonly items: readonly FilenameRangeVerificationItemResponse[];
  readonly error: string | null;
}> {
  const items: FilenameRangeVerificationItemResponse[] = [];
  let after: number | undefined;
  do {
    const result = await api.listSemiAutomaticFilenameRangeVerifications(
      runId,
      after,
      500,
    );
    if (result.error !== undefined || result.data === undefined)
      return {
        items: [],
        error: apiErrorMessage(
          result.error,
          'Nie udało się pobrać wyników weryfikacji.',
        ),
      };
    items.push(...result.data.items);
    after = result.data.nextAfterSourceIndex ?? undefined;
  } while (after !== undefined);
  return { items, error: null };
}

function remoteAssetHandle(
  apiOrigin: string,
  runId: string,
  item: FilenameRangeVerificationItemResponse,
): FileSystemFileHandle {
  const name = baseName(item.sourceRelativePath);
  return {
    kind: 'file',
    name,
    async getFile(): Promise<File> {
      const url = new URL(
        `/api/v1/admin/semi-automatic-image-selections/${runId}/sources/${item.sourceIndex}/asset`,
        apiOrigin,
      );
      url.searchParams.set(
        'expected_checksum_sha256',
        item.sourceChecksumSha256,
      );
      const response = await fetch(url, {
        headers: { 'X-Admin-Intent': 'local-owner' },
      });
      if (!response.ok)
        throw new Error(`SOURCE_ASSET_UNAVAILABLE:${response.status}`);
      return new File([await response.blob()], name, { type: 'image/jpeg' });
    },
  } as FileSystemFileHandle;
}

async function sourceDirectoryMatchesRun(
  snapshot: RepairDirectorySnapshot,
  run: SemiAutomaticSelectionRunResponse,
  rejectedSources: readonly FilenameVerificationRejectedSource[] = [],
): Promise<boolean> {
  if (snapshot.files.length + rejectedSources.length !== run.source.sourceCount)
    return false;
  const rejectedByIndex = new Map(
    rejectedSources.map((source) => [source.sourceIndex, source]),
  );
  if (rejectedByIndex.size !== rejectedSources.length) return false;
  const payload: Array<{
    checksumSha256: string;
    relativePath: string;
    sizeBytes: number;
    sourceIndex: number;
  }> = [];
  let fileCursor = 0;
  for (
    let sourceIndex = 0;
    sourceIndex < run.source.sourceCount;
    sourceIndex += 1
  ) {
    const rejected = rejectedByIndex.get(sourceIndex);
    if (rejected !== undefined) {
      payload.push({
        checksumSha256: rejected.sourceChecksumSha256,
        relativePath: rejected.sourceRelativePath,
        sizeBytes: rejected.sourceSizeBytes,
        sourceIndex,
      });
      continue;
    }
    const item = snapshot.files[fileCursor];
    if (item === undefined) return false;
    const file = await item.handle.getFile();
    payload.push({
      checksumSha256: await sha256Hex(file),
      relativePath: item.fileName,
      sizeBytes: file.size,
      sourceIndex,
    });
    fileCursor += 1;
  }
  if (fileCursor !== snapshot.files.length) return false;
  return (
    (await sha256Hex(new Blob([JSON.stringify(payload)]))) ===
    run.source.sourceFingerprint
  );
}

function appendRejectedSource(
  existing: readonly FilenameVerificationRejectedSource[],
  source: FilenameVerificationRejectedSource,
): readonly FilenameVerificationRejectedSource[] {
  return [
    ...existing.filter((item) => item.sourceIndex !== source.sourceIndex),
    source,
  ].sort((left, right) => left.sourceIndex - right.sourceIndex);
}

function pendingDeleteWasApplied(
  snapshot: RepairDirectorySnapshot,
  pending: FilenameRangeVerificationLocalState['pendingDecision'],
): boolean {
  if (pending === null) return false;
  const fileName = baseName(pending.sourceRelativePath).toLocaleLowerCase(
    'en-US',
  );
  const missing = !snapshot.files.some(
    (file) => file.fileName.toLocaleLowerCase('en-US') === fileName,
  );
  return (
    missing &&
    snapshot.repairManifest.operations.some(
      (operation) =>
        operation.kind === 'delete' &&
        operation.sourceIndex === pending.sourceIndex &&
        operation.sourcePath === pending.sourceRelativePath &&
        operation.checksumSha256 === pending.sourceChecksumSha256,
    )
  );
}

async function sha256Hex(input: Blob): Promise<string> {
  const digest = await crypto.subtle.digest(
    'SHA-256',
    await input.arrayBuffer(),
  );
  return [...new Uint8Array(digest)]
    .map((value) => value.toString(16).padStart(2, '0'))
    .join('');
}

function findLocalFile(
  snapshot: RepairDirectorySnapshot,
  item: FilenameRangeVerificationItemResponse,
) {
  const name = baseName(item.sourceRelativePath).toLocaleLowerCase('en-US');
  return snapshot.files.find(
    (file) => file.fileName.toLocaleLowerCase('en-US') === name,
  );
}

function replaceRun(
  existing: readonly SemiAutomaticSelectionRunResponse[],
  replacement: SemiAutomaticSelectionRunResponse,
) {
  return existing.map((item) =>
    item.id === replacement.id ? replacement : item,
  );
}
function isActive(run: SemiAutomaticSelectionRunResponse): boolean {
  return ['ready', 'running', 'paused', 'syncing_output'].includes(run.status);
}
function isReviewable(run: SemiAutomaticSelectionRunResponse): boolean {
  return ['analysis_complete', 'review_mode', 'completed'].includes(run.status);
}
function baseName(path: string): string {
  return path.replaceAll('\\', '/').split('/').at(-1) ?? path;
}
function formatRange(
  range: { readonly start: number; readonly end: number } | null,
): string {
  return range === null ? 'nie odczytano' : `${range.start}–${range.end}`;
}
function formatPercent(value: number | null): string {
  return value === null ? 'w toku' : `${value.toFixed(1)}%`;
}
function verificationMessage(
  item: FilenameRangeVerificationItemResponse,
): string {
  if (item.verificationStatus === 'mismatch')
    return 'OCR odczytał inny zakres niż nazwa pliku.';
  if (item.verificationStatus === 'invalid_filename')
    return 'Nazwa pliku nie zawiera poprawnego zakresu seq_*.';
  return 'Nie uzyskano pewnego dowodu z pięciu punktów obrazu. Sprawdź zdjęcie ręcznie.';
}
function errorMessage(cause: unknown): string {
  return cause instanceof Error
    ? cause.message
    : 'Nie udało się wykonać operacji.';
}
function isPickerCancellation(cause: unknown): boolean {
  return cause instanceof DOMException && cause.name === 'AbortError';
}
function isEditable(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable ||
      ['INPUT', 'SELECT', 'TEXTAREA'].includes(target.tagName))
  );
}
async function pickReadWriteDirectory(): Promise<FileSystemDirectoryHandle> {
  return pickLocalDirectory({ id: 'gp-range-verify', mode: 'readwrite' });
}
