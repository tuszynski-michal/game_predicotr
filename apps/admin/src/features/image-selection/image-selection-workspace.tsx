'use client';

import type {
  ImageSelectionGroupResponse,
  ImageSelectionHandoffResponse,
  ImageSelectionRunResponse,
} from '@game-predictor/admin-api-client';
import { type ChangeEvent, useEffect, useMemo, useRef, useState } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';
import { apiErrorMessage } from '@/features/catalog/catalog-api-error';
import {
  formatElapsedSeconds,
  jobProgressLabel,
  jobProgressPercent,
  jobStageLabel,
  jobStatusLabel,
} from '@/features/jobs/job-state';

import {
  type ImageSelectionClient,
  type ImageSelectionUploadProgress,
  type OutputDirectoryHandle,
  type ResumableImageSelectionUpload,
  cancelPhotoSelectionUpload,
  continueWithAutomaticallySelectedImages,
  loadAllImageSelectionGroups,
  loadManualImageSelectionGroups,
  pickImageSelectionOutputDirectory,
  saveFinalizedImageSelectionGroups,
  saveImageSelectionOutputToFolder,
  uploadPhotoSelectionFolder,
} from './image-selection-actions';
import { ManualImageSelectionModal } from './manual-image-selection-modal';

interface ImageSelectionWorkspaceProps {
  readonly apiBaseUrl: string;
  readonly client?: ImageSelectionClient;
  readonly gameId: string;
  readonly gameName: string;
  readonly onOpenImports: (handoff: ImageSelectionHandoffResponse) => void;
}

const EMPTY_PROGRESS: ImageSelectionUploadProgress = {
  totalBytes: 0,
  totalFiles: 0,
  uploadedBytes: 0,
  uploadedFiles: 0,
};

const RUN_POLL_INTERVAL_MS = 2_000;
const RUN_POLL_REQUEST_TIMEOUT_MS = 10_000;
const RUN_POLL_MAX_DURATION_MS = 45 * 60 * 1_000;
const RUN_POLL_ERROR_THRESHOLD = 3;
const MAX_IMAGE_SELECTION_FILES = 100_000;

export function ImageSelectionWorkspace({
  apiBaseUrl,
  client,
  gameId,
  gameName,
  onOpenImports,
}: ImageSelectionWorkspaceProps) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const folderInputRef = useRef<HTMLInputElement | null>(null);
  const outputDirectoryRef = useRef<OutputDirectoryHandle | null>(null);
  const savedGroupOrdersRef = useRef(new Set<number>());
  const progressiveSaveRunningRef = useRef(false);
  const pollingWindowRef = useRef<{
    readonly deadline: number;
    readonly runId: string;
  } | null>(null);
  const [progress, setProgress] = useState(EMPTY_PROGRESS);
  const [resume, setResume] = useState<ResumableImageSelectionUpload | null>(
    null,
  );
  const [run, setRun] = useState<ImageSelectionRunResponse | null>(null);
  const [manualGroups, setManualGroups] = useState<
    ImageSelectionGroupResponse[]
  >([]);
  const [manualOpen, setManualOpen] = useState(false);
  const [manualLoading, setManualLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [preparingFolder, setPreparingFolder] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [rerunning, setRerunning] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [refreshWarning, setRefreshWarning] = useState('');
  const [outputFolderName, setOutputFolderName] = useState('');
  const [sequenceDirection, setSequenceDirection] = useState<
    'ascending' | 'descending'
  >('ascending');
  const [firstSequenceNumber, setFirstSequenceNumber] = useState('');
  const activeRunId = run?.id ?? null;
  const activeRunStatus = run?.job.status ?? null;

  useEffect(() => {
    let cancelled = false;
    const runId = window.localStorage.getItem(storageKey(gameId));
    if (runId === null) return () => undefined;
    queueMicrotask(async () => {
      try {
        const result = await getImageSelectionWithTimeout(api, runId);
        if (
          !cancelled &&
          result.error === undefined &&
          result.data !== undefined
        ) {
          setRun(result.data);
        } else if (!cancelled && result.error !== undefined) {
          window.localStorage.removeItem(storageKey(gameId));
        }
      } catch {
        if (!cancelled) {
          setError('Nie udało się przywrócić ostatniego procesu tej gry.');
        }
      }
    });
    return () => {
      cancelled = true;
    };
  }, [api, gameId]);

  useEffect(() => {
    if (activeRunId === null || activeRunStatus === null) {
      return;
    }
    if (!isPollableRunStatus(activeRunStatus)) {
      pollingWindowRef.current = null;
      return;
    }

    let cancelled = false;
    let timerId: number | null = null;
    let consecutiveFailures = 0;
    if (pollingWindowRef.current?.runId !== activeRunId) {
      pollingWindowRef.current = {
        deadline: Date.now() + RUN_POLL_MAX_DURATION_MS,
        runId: activeRunId,
      };
    }
    const deadline = pollingWindowRef.current.deadline;

    const schedule = () => {
      if (cancelled) return;
      if (Date.now() >= deadline) {
        setRefreshWarning(
          'Automatyczne odświeżanie zatrzymano po 45 minutach. Odśwież stronę, aby ponownie sprawdzić proces.',
        );
        return;
      }
      timerId = window.setTimeout(() => void poll(), RUN_POLL_INTERVAL_MS);
    };

    const poll = async () => {
      try {
        const result = await getImageSelectionWithTimeout(api, activeRunId);
        if (cancelled) return;
        if (result.error !== undefined || result.data === undefined) {
          consecutiveFailures += 1;
        } else {
          consecutiveFailures = 0;
          setRefreshWarning('');
          setRun(result.data);
          if (!isPollableRunStatus(result.data.job.status)) return;
        }
      } catch {
        if (cancelled) return;
        consecutiveFailures += 1;
      }

      if (consecutiveFailures >= RUN_POLL_ERROR_THRESHOLD) {
        setRefreshWarning(
          'Nie udało się odświeżyć procesu. Panel spróbuje ponownie automatycznie.',
        );
      }
      schedule();
    };

    schedule();
    return () => {
      cancelled = true;
      if (timerId !== null) window.clearTimeout(timerId);
    };
  }, [activeRunId, activeRunStatus, api, gameId]);

  useEffect(() => {
    if (run === null) return;
    let cancelled = false;
    queueMicrotask(async () => {
      try {
        const groups = await loadManualImageSelectionGroups(api, run.id);
        if (!cancelled) setManualGroups(groups);
      } catch {
        if (!cancelled) {
          setError('Nie udało się odczytać wyjątków ręcznej selekcji.');
        }
      }
    });
    return () => {
      cancelled = true;
    };
  }, [api, run]);

  useEffect(() => {
    if (
      activeRunId === null ||
      outputDirectoryRef.current === null ||
      progressiveSaveRunningRef.current
    ) {
      return;
    }
    let cancelled = false;
    progressiveSaveRunningRef.current = true;
    queueMicrotask(async () => {
      try {
        const groups = await loadAllImageSelectionGroups(api, activeRunId);
        if (cancelled || outputDirectoryRef.current === null) return;
        const result = await saveFinalizedImageSelectionGroups(
          api,
          activeRunId,
          groups,
          outputDirectoryRef.current,
          savedGroupOrdersRef.current,
        );
        if (!cancelled && result.error !== null) setError(result.error);
        if (!cancelled && result.savedCount > 0) {
          setNotice(
            `Zapisano na bieżąco ${result.savedCount.toLocaleString('pl-PL')} nowych zdjęć.`,
          );
        }
      } catch {
        if (!cancelled) {
          setRefreshWarning('Nie udało się zapisać nowych wyników do folderu.');
        }
      } finally {
        progressiveSaveRunningRef.current = false;
      }
    });
    return () => {
      cancelled = true;
    };
  }, [activeRunId, api, run]);

  async function startUpload(files: readonly File[], activeResume = resume) {
    if (busy) return;
    setBusy(true);
    setError('');
    setNotice('');
    const result = await uploadPhotoSelectionFolder(api, gameId, files, {
      onProgress: setProgress,
      resume: activeResume,
      sequenceDirection,
      firstSequenceNumber:
        firstSequenceNumber.trim() === '' ? null : Number(firstSequenceNumber),
    });
    if (!result.ok) {
      setError(result.error);
      setResume(result.resume);
      setBusy(false);
      return;
    }
    setResume(null);
    setRun(result.created.run);
    setProgress(EMPTY_PROGRESS);
    window.localStorage.setItem(storageKey(gameId), result.created.run.id);
    setNotice(
      result.created.created
        ? 'Folder zapisany. Proces selekcji jest gotowy do uruchomienia przez worker.'
        : 'Ten sam folder był już zapisany. Przywrócono istniejący proces.',
    );
    setBusy(false);
  }

  async function chooseFolder(event: ChangeEvent<HTMLInputElement>) {
    const input = event.currentTarget;
    setBusy(true);
    setPreparingFolder(true);
    setError('');
    setNotice('Przygotowywanie listy zdjęć z wybranego folderu…');
    setProgress(EMPTY_PROGRESS);
    await waitForBrowserPaint();
    try {
      const selectedFiles = Array.from(input.files ?? []).filter((file) =>
        /\.jpe?g$/i.test(file.name),
      );
      input.value = '';
      if (selectedFiles.length === 0) {
        setError('Wybrany folder nie zawiera plików JPEG.');
        setNotice('');
        setBusy(false);
        return;
      }
      if (selectedFiles.length > MAX_IMAGE_SELECTION_FILES) {
        setError(
          'Selekcja zdjęć obsługuje maksymalnie 100 000 plików JPEG na run.',
        );
        setNotice('');
        setBusy(false);
        return;
      }
      setNotice(
        `Przygotowano ${selectedFiles.length.toLocaleString('pl-PL')} zdjęć. Rozpoczynanie uploadu…`,
      );
      setPreparingFolder(false);
      await waitForBrowserPaint();
      await startUpload(selectedFiles, null);
    } catch {
      input.value = '';
      setError('Nie udało się przygotować wybranego folderu zdjęć.');
      setNotice('');
      setBusy(false);
    } finally {
      setPreparingFolder(false);
    }
  }

  async function chooseOutputFolder() {
    if (busy) return;
    setError('');
    try {
      const directory = await pickImageSelectionOutputDirectory();
      outputDirectoryRef.current = directory;
      savedGroupOrdersRef.current.clear();
      setOutputFolderName(directory.name ?? 'Wybrany folder');
      setNotice('Folder wynikowy wybrany. Teraz wybierz folder ze zdjęciami.');
    } catch (error) {
      if (!(error instanceof DOMException) || error.name !== 'AbortError') {
        setError(
          'Nie udało się wybrać folderu wynikowego. Użyj aktualnej wersji Chrome lub Edge.',
        );
      }
    }
  }

  async function cancelUpload() {
    if (resume === null || busy) return;
    setBusy(true);
    try {
      await cancelPhotoSelectionUpload(api, resume);
      setResume(null);
      setProgress(EMPTY_PROGRESS);
      setError('');
      setNotice('Niedokończony staging został usunięty.');
    } catch {
      setError('Nie udało się anulować niedokończonego uploadu.');
    } finally {
      setBusy(false);
    }
  }

  async function handoffToImport() {
    if (run === null || run.outputManifestSha256 === null || busy) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const result = await api.handoffImageSelection(run.id);
      if (result.error !== undefined || result.data === undefined) {
        setError('Nie udało się zweryfikować paczki wybranych zdjęć.');
        return;
      }
      onOpenImports(result.data);
    } catch {
      setError('Połączenie z lokalnym Admin API zostało przerwane.');
    } finally {
      setBusy(false);
    }
  }

  async function rerunExistingSelection() {
    if (run === null || busy || isPollableRunStatus(run.job.status)) {
      return;
    }
    setBusy(true);
    setRerunning(true);
    setError('');
    setNotice('');
    const previousStatus = run.job.status;
    try {
      const result = await api.rerunImageSelection(run.id);
      if (result.error !== undefined || result.data === undefined) {
        setError(
          apiErrorMessage(
            result.error,
            'Nie udało się ponownie przeliczyć załadowanych zdjęć.',
          ),
        );
        return;
      }
      setRun(result.data.run);
      setManualGroups([]);
      setManualOpen(false);
      pollingWindowRef.current = null;
      window.localStorage.setItem(storageKey(gameId), result.data.run.id);
      setNotice(
        !result.data.created &&
          (previousStatus === 'cancelled' || previousStatus === 'failed')
          ? 'Wznowiono selekcję od ostatniego trwałego checkpointu. Ponowny upload nie był potrzebny.'
          : result.data.created
            ? 'Uruchomiono najnowszy selektor dla wcześniej załadowanych zdjęć. Ponowny upload nie był potrzebny.'
            : 'Najnowszy selektor był już uruchomiony dla tego zestawu. Przywrócono jego run.',
      );
    } catch {
      setError('Połączenie z lokalnym Admin API zostało przerwane.');
    } finally {
      setRerunning(false);
      setBusy(false);
    }
  }

  async function saveOutputToFolder() {
    if (
      run === null ||
      run.outputManifestSha256 === null ||
      busy ||
      exporting
    ) {
      return;
    }
    setExporting(true);
    setError('');
    setNotice('');
    try {
      const result = await saveImageSelectionOutputToFolder(api, run.id);
      if (result.error !== null) {
        setError(result.error);
      } else if (!result.cancelled) {
        setNotice(
          `Zapisano ${result.savedCount.toLocaleString('pl-PL')} wybranych zdjęć. Nazwa selection_<grupa>.jpg oznacza kolejność techniczną, a seq_<od>-<do>.jpg rozpoznany zakres.`,
        );
      }
    } catch {
      setError('Połączenie z lokalnym Admin API zostało przerwane.');
    } finally {
      setExporting(false);
    }
  }

  async function openManualReview() {
    if (run === null || manualLoading) return;
    setManualLoading(true);
    setError('');
    try {
      const groups = await loadManualImageSelectionGroups(api, run.id);
      setManualGroups(groups);
      if (groups.length === 0) {
        setNotice('Ten run nie ma grup wymagających ręcznej decyzji.');
      } else {
        setManualOpen(true);
      }
    } catch {
      setError('Nie udało się odczytać wyjątków ręcznej selekcji.');
    } finally {
      setManualLoading(false);
    }
  }

  async function continueWithSelectedImages() {
    if (run === null || busy || manualLoading) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const groups = await loadManualImageSelectionGroups(api, run.id);
      const result = await continueWithAutomaticallySelectedImages(
        api,
        run.id,
        groups,
      );
      if (result.error !== null) {
        setError(result.error);
        return;
      }
      setManualGroups((current) =>
        current.map(
          (group) =>
            result.updatedGroups.find((updated) => updated.id === group.id) ??
            group,
        ),
      );
      const refreshed = await getImageSelectionWithTimeout(api, run.id);
      if (refreshed.error !== undefined || refreshed.data === undefined) {
        setRefreshWarning(
          'Wyjątki zostały pominięte, ale nie udało się odświeżyć procesu.',
        );
        return;
      }
      setRun(refreshed.data);
      setNotice(
        result.skippedCount === 0
          ? 'Nie ma nierozpoznanych zestawów. Przygotowuję wybrane zdjęcia.'
          : `Pominięto ${result.skippedCount.toLocaleString('pl-PL')} nierozpoznanych zestawów. Przygotowuję wybrane zdjęcia.`,
      );
    } catch {
      setError('Połączenie z lokalnym Admin API zostało przerwane.');
    } finally {
      setBusy(false);
    }
  }

  function updateManualGroup(updated: ImageSelectionGroupResponse) {
    setManualGroups((groups) =>
      groups.map((group) => (group.id === updated.id ? updated : group)),
    );
    if (activeRunId !== null) {
      void refreshRunAfterManualApproval(activeRunId);
    }
  }

  async function refreshRunAfterManualApproval(runId: string) {
    try {
      const result = await getImageSelectionWithTimeout(api, runId);
      if (
        result.error !== undefined ||
        result.data === undefined ||
        window.localStorage.getItem(storageKey(gameId)) !== runId
      ) {
        setRefreshWarning(
          'Decyzja została zapisana, ale nie udało się odświeżyć procesu.',
        );
        return;
      }
      setRefreshWarning('');
      setRun(result.data);
    } catch {
      setRefreshWarning(
        'Decyzja została zapisana, ale nie udało się odświeżyć procesu.',
      );
    }
  }

  const percentage =
    progress.totalBytes === 0
      ? 0
      : Math.min(100, (progress.uploadedBytes / progress.totalBytes) * 100);
  const runProgressPercent = run === null ? null : jobProgressPercent(run.job);
  const selectionProgress = run?.job.progress.imageSelection ?? null;
  const missingImageGroups = manualGroups.filter(
    (group) => group.status === 'missing_image',
  );
  const unresolvedGroupCount = manualGroups.filter(
    (group) => group.status === 'manual_required',
  ).length;

  return (
    <section
      className="imageSelectionWorkspace"
      aria-labelledby="image-selection-title"
    >
      <header className="imageSelectionHeader">
        <div>
          <p className="eyebrow">Aktywna gra · {gameName}</p>
          <h1 id="image-selection-title">Selekcja zdjęć</h1>
          <p>
            Wybierz duży folder. Moduł zapisze bezpieczny staging bez
            uruchamiania pełnego pipeline&apos;u layoutów.
          </p>
        </div>
        <input
          accept=".jpg,.jpeg,image/jpeg"
          hidden
          multiple
          onChange={(event) => void chooseFolder(event)}
          ref={(node) => {
            folderInputRef.current = node;
            if (node !== null) {
              node.webkitdirectory = true;
              node.setAttribute('webkitdirectory', '');
            }
          }}
          type="file"
        />
        <div className="imageSelectionStartControls">
          <label>
            Kolejność
            <select
              disabled={busy}
              onChange={(event) =>
                setSequenceDirection(
                  event.target.value as 'ascending' | 'descending',
                )
              }
              value={sequenceDirection}
            >
              <option value="ascending">Rosnąco</option>
              <option value="descending">Malejąco</option>
            </select>
          </label>
          <label>
            Pierwszy numer (opcjonalnie)
            <input
              disabled={busy}
              min={1}
              onChange={(event) => setFirstSequenceNumber(event.target.value)}
              placeholder="Rozpoznaj automatycznie"
              type="number"
              value={firstSequenceNumber}
            />
          </label>
          <button
            className="secondaryButton"
            disabled={busy}
            onClick={() => void chooseOutputFolder()}
            type="button"
          >
            {outputFolderName === ''
              ? '1. Wybierz folder zapisu'
              : `Folder zapisu: ${outputFolderName}`}
          </button>
          <button
            aria-busy={busy}
            className="primaryButton"
            disabled={busy || outputFolderName === ''}
            onClick={() => folderInputRef.current?.click()}
            type="button"
          >
            {preparingFolder
              ? 'Przygotowywanie…'
              : busy
                ? 'Przesyłanie…'
                : '2. Wybierz folder zdjęć'}
          </button>
        </div>
      </header>

      {preparingFolder ? (
        <p aria-live="polite" className="imageSelectionPreparing" role="status">
          <span aria-hidden="true" className="imageSelectionSpinner" />
          Analizowanie plików w folderze. Przy dużym zestawie może to potrwać
          chwilę.
        </p>
      ) : null}

      {error ? (
        <p className="feedbackBanner feedbackBannerError" role="alert">
          {error}
        </p>
      ) : null}
      {refreshWarning ? (
        <p className="feedbackBanner" role="status">
          {refreshWarning}
        </p>
      ) : null}
      {notice ? <p className="feedbackBanner">{notice}</p> : null}

      {progress.totalFiles > 0 ? (
        <section className="imageSelectionProgress" aria-label="Postęp uploadu">
          <div>
            <strong>
              {progress.uploadedFiles.toLocaleString('pl-PL')} /{' '}
              {progress.totalFiles.toLocaleString('pl-PL')} plików
            </strong>
            <span>
              {formatBytes(progress.uploadedBytes)} /{' '}
              {formatBytes(progress.totalBytes)}
            </span>
          </div>
          <progress max={100} value={percentage} />
          {resume !== null ? (
            <div className="imageSelectionRecoveryActions">
              <button
                className="primaryButton"
                disabled={busy}
                onClick={() => void startUpload(resume.files, resume)}
                type="button"
              >
                Ponów brakujące pliki
              </button>
              <button
                className="secondaryButton"
                disabled={busy}
                onClick={() => void cancelUpload()}
                type="button"
              >
                Anuluj staging
              </button>
            </div>
          ) : null}
        </section>
      ) : null}

      {run !== null ? (
        <section
          className="imageSelectionRunCard"
          aria-label="Bieżący proces selekcji"
        >
          <div className="imageSelectionRunSummary">
            <p className="eyebrow">Bieżący run</p>
            <span className={`jobStatus jobStatus-${run.job.status}`}>
              {jobStatusLabel(run.job.status)}
            </span>
            <h2>{jobStageLabel(run.job.progress.stage)}</h2>
          </div>
          <div className="imageSelectionRunBody">
            <div className="imageSelectionRunProgress">
              <div>
                <strong>{jobProgressLabel(run.job)}</strong>
                <span>
                  {runProgressPercent === null
                    ? 'Rozmiar nieznany'
                    : `${runProgressPercent.toFixed(1)}%`}
                </span>
              </div>
              <progress
                aria-label={`Postęp: ${jobProgressLabel(run.job)}`}
                max={100}
                value={runProgressPercent ?? undefined}
              />
            </div>

            <dl className="imageSelectionMetrics">
              <Metric label="Grupy" value={selectionProgress?.groups} />
              <Metric
                label="Wybrane grupy"
                value={selectionProgress?.selected}
              />
              <Metric
                label={
                  isPollableRunStatus(run.job.status)
                    ? 'Roboczo bez numerów'
                    : 'Nierozpoznane zestawy'
                }
                value={selectionProgress?.manual}
              />
              <Metric
                label="Pominięte grupy-duplikaty"
                value={selectionProgress?.skipped}
              />
              <Metric label="Błędy" value={selectionProgress?.errors} />
              <Metric
                label="Weryfikacje"
                value={selectionProgress?.verifications}
              />
              <Metric
                label="Upload"
                value={formatElapsedSeconds(
                  selectionProgress?.uploadDurationSeconds ?? null,
                )}
              />
              <Metric
                label="Obliczenia"
                value={formatElapsedSeconds(
                  selectionProgress?.processingDurationSeconds ?? null,
                )}
              />
            </dl>
            {isPollableRunStatus(run.job.status) &&
            (selectionProgress?.manual ?? 0) > 0 ? (
              <p className="fieldHint">
                To licznik tymczasowy. Grupy są automatycznie rozliczane, gdy
                selektor znajdzie kolejną pewną kotwicę numerów.
              </p>
            ) : null}

            <details className="imageSelectionTechnicalDetails">
              <summary>Szczegóły techniczne</summary>
              <dl>
                <div>
                  <dt>Job</dt>
                  <dd>{run.job.id.slice(0, 8)}</dd>
                </div>
                <div>
                  <dt>Kolejność</dt>
                  <dd>{run.orderingPolicy}</dd>
                </div>
                <div>
                  <dt>Manifest wejścia</dt>
                  <dd>{run.inputManifestSha256.slice(0, 12)}…</dd>
                </div>
                <div>
                  <dt>Selektor</dt>
                  <dd>{run.selectorFingerprint.slice(0, 12)}…</dd>
                </div>
              </dl>
            </details>

            <div className="imageSelectionRecoveryActions">
              <button
                aria-busy={rerunning}
                className="secondaryButton"
                disabled={busy || isPollableRunStatus(run.job.status)}
                onClick={() => void rerunExistingSelection()}
                type="button"
              >
                {rerunning
                  ? 'Uruchamianie…'
                  : 'Przelicz ponownie załadowane zdjęcia'}
              </button>
              {run.job.status === 'waiting_for_review' ? (
                <button
                  aria-busy={busy}
                  className="primaryButton"
                  disabled={busy || manualLoading}
                  onClick={() => void continueWithSelectedImages()}
                  type="button"
                >
                  {busy
                    ? 'Przygotowywanie…'
                    : 'Kontynuuj z wybranymi zdjęciami'}
                </button>
              ) : null}
              {manualGroups.some(
                (group) => group.status === 'manual_required',
              ) ? (
                <button
                  className="secondaryButton"
                  disabled={busy || manualLoading}
                  onClick={() => void openManualReview()}
                  type="button"
                >
                  {manualLoading
                    ? 'Odczytywanie…'
                    : `Sprawdź nierozpoznane zestawy (${unresolvedGroupCount})`}
                </button>
              ) : null}
              <button
                aria-busy={busy}
                className="primaryButton"
                disabled={busy || run.outputManifestSha256 === null}
                onClick={() => void handoffToImport()}
                type="button"
              >
                {busy ? 'Weryfikowanie…' : 'Przekaż do Importu layoutów'}
              </button>
              <button
                aria-busy={exporting}
                className="secondaryButton"
                disabled={
                  busy || exporting || run.outputManifestSha256 === null
                }
                onClick={() => void saveOutputToFolder()}
                type="button"
              >
                {exporting
                  ? 'Zapisywanie…'
                  : 'Zapisz wybrane zdjęcia do folderu'}
              </button>
              {run.outputManifestSha256 === null ? (
                <span>
                  Akcje będą dostępne po opublikowaniu zweryfikowanego wyniku.
                </span>
              ) : null}
            </div>
            {missingImageGroups.length > 0 ? (
              <div className="imageSelectionMissingRanges" role="status">
                <strong>Zestawy pominięte bez zdjęcia:</strong>{' '}
                {missingImageGroups.length}. To liczba zestawów zdjęć, nie
                pojedynczych zdjęć ani layoutów.
              </div>
            ) : null}
          </div>
        </section>
      ) : null}
      {manualOpen && run !== null && manualGroups.length > 0 ? (
        <ManualImageSelectionModal
          apiBaseUrl={apiBaseUrl}
          client={api}
          groups={manualGroups}
          onClose={() => setManualOpen(false)}
          onGroupUpdated={updateManualGroup}
          runId={run.id}
        />
      ) : null}
    </section>
  );
}

function Metric({
  label,
  value,
}: {
  readonly label: string;
  readonly value: number | string | undefined;
}) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>
        {typeof value === 'number'
          ? value.toLocaleString('pl-PL')
          : (value ?? '—')}
      </dd>
    </div>
  );
}

function storageKey(gameId: string): string {
  return `game-predictor:image-selection-run:${gameId}`;
}

function isPollableRunStatus(status: string): boolean {
  return status === 'created' || status === 'processing';
}

function waitForBrowserPaint(): Promise<void> {
  return new Promise((resolve) => {
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => resolve());
    });
  });
}

async function getImageSelectionWithTimeout(
  api: ImageSelectionClient,
  runId: string,
) {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(
    () => controller.abort(),
    RUN_POLL_REQUEST_TIMEOUT_MS,
  );
  try {
    return await api.getImageSelection(runId, { signal: controller.signal });
  } finally {
    window.clearTimeout(timeoutId);
  }
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 * 1024 * 1024) {
    return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  }
  return `${(value / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}
