'use client';

import type {
  AdminApiClient,
  SemiAutomaticSelectionCapabilitiesResponse,
  SemiAutomaticSelectionRunResponse,
} from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';
import { apiErrorMessage } from '@/features/catalog/catalog-api-error';
import {
  jobProgressLabel,
  jobProgressPercent,
  jobStageLabel,
  jobStatusLabel,
} from '@/features/jobs/job-state';

import {
  cancelSemiAutomaticSelectionUpload,
  collectSemiAutomaticSourceFiles,
  pickSemiAutomaticOutputDirectory,
  pickSemiAutomaticSourceDirectory,
  uploadSemiAutomaticSelectionFolder,
  type BrowserDirectoryHandle,
  type ResumableSemiAutomaticSelectionUpload,
  type SemiAutomaticSelectionClient,
  type SemiAutomaticSelectionUploadProgress,
} from './semi-automatic-selection-actions.ts';
import {
  IndexedDbSemiAutomaticSelectionLocalSessionStore,
  restoreSemiAutomaticSelectionLocalSession,
  type SemiAutomaticOutputDirectoryHandle,
  type SemiAutomaticSelectionLocalUiState,
} from './semi-automatic-selection-output-storage.ts';
import { SemiAutomaticSelectionReviewWorkspace } from './semi-automatic-selection-review-workspace';

const EMPTY_UPLOAD_PROGRESS: SemiAutomaticSelectionUploadProgress = {
  totalBytes: 0,
  totalFiles: 0,
  uploadedBytes: 0,
  uploadedFiles: 0,
};
const RUN_STORAGE_KEY = 'game-predictor:semi-automatic-selection:last-run';
const POLL_INTERVAL_MS = 2_000;
const POLL_MAX_DURATION_MS = 45 * 60 * 1_000;

interface SemiAutomaticSelectionWorkspaceProps {
  readonly apiBaseUrl: string;
  readonly client?: SemiAutomaticSelectionClient &
    Pick<
      AdminApiClient,
      | 'acknowledgeSemiAutomaticImageSelectionOutput'
      | 'cancelSemiAutomaticImageSelection'
      | 'getSemiAutomaticImageSelection'
      | 'getSemiAutomaticImageSelectionCapabilities'
      | 'getSemiAutomaticImageSelectionSourceAsset'
      | 'listSemiAutomaticImageSelectionRanges'
      | 'pauseSemiAutomaticImageSelection'
      | 'resumeSemiAutomaticImageSelection'
    >;
}

export function SemiAutomaticSelectionWorkspace({
  apiBaseUrl,
  client,
}: SemiAutomaticSelectionWorkspaceProps) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const localSessionStore = useMemo(
    () => new IndexedDbSemiAutomaticSelectionLocalSessionStore(),
    [],
  );
  const [capabilities, setCapabilities] =
    useState<SemiAutomaticSelectionCapabilitiesResponse | null>(null);
  const [sourceDirectory, setSourceDirectory] =
    useState<BrowserDirectoryHandle | null>(null);
  const [sourceFiles, setSourceFiles] = useState<
    Awaited<ReturnType<typeof collectSemiAutomaticSourceFiles>>
  >([]);
  const [outputDirectory, setOutputDirectory] =
    useState<SemiAutomaticOutputDirectoryHandle | null>(null);
  const [firstSequenceNumber, setFirstSequenceNumber] = useState('');
  const [lastSequenceNumber, setLastSequenceNumber] = useState('');
  const [direction, setDirection] = useState<'ascending' | 'descending'>(
    'ascending',
  );
  const [recognizerVariant, setRecognizerVariant] = useState<
    'default_v3' | 'five_anchor_v6'
  >('default_v3');
  const [run, setRun] = useState<SemiAutomaticSelectionRunResponse | null>(
    null,
  );
  const [resume, setResume] =
    useState<ResumableSemiAutomaticSelectionUpload | null>(null);
  const [uploadProgress, setUploadProgress] = useState(EMPTY_UPLOAD_PROGRESS);
  const [sourceLoading, setSourceLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [restoredUi, setRestoredUi] =
    useState<SemiAutomaticSelectionLocalUiState | null>(null);
  const pollDeadlineRef = useRef<number | null>(null);

  const first = parsePositiveInteger(firstSequenceNumber);
  const last = parsePositiveInteger(lastSequenceNumber);
  const validBounds = first !== null && last !== null && first <= last;
  const expectedRangeCount =
    validBounds && capabilities !== null
      ? Math.floor((last - first) / capabilities.fullRangeSize) + 1
      : null;
  const uploadPercentage =
    uploadProgress.totalBytes === 0
      ? 0
      : Math.min(
          100,
          (uploadProgress.uploadedBytes / uploadProgress.totalBytes) * 100,
        );
  const capabilitiesLoading = capabilities === null && error === '';

  useEffect(() => {
    let cancelled = false;
    void api.getSemiAutomaticImageSelectionCapabilities().then((result) => {
      if (cancelled) return;
      if (result.error !== undefined || result.data === undefined) {
        setError(
          apiErrorMessage(
            result.error,
            'Nie udało się odczytać możliwości półautomatycznej selekcji.',
          ),
        );
        return;
      }
      setCapabilities(result.data);
      const defaultVariant = result.data.selectionRecognizerVariants.find(
        (variant) => variant.default,
      );
      if (defaultVariant !== undefined) {
        setRecognizerVariant(defaultVariant.id);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [api]);

  useEffect(() => {
    const runId = window.localStorage.getItem(RUN_STORAGE_KEY);
    if (runId === null) return undefined;
    let cancelled = false;
    void (async () => {
      const result = await api.getSemiAutomaticImageSelection(runId);
      if (cancelled) return;
      if (result.error !== undefined || result.data === undefined) {
        window.localStorage.removeItem(RUN_STORAGE_KEY);
        return;
      }
      setRun(result.data);
      setFirstSequenceNumber(String(result.data.firstSequenceNumber));
      setLastSequenceNumber(String(result.data.lastSequenceNumber));
      setDirection(result.data.direction);
      const restored = await restoreSemiAutomaticSelectionLocalSession(
        localSessionStore,
        runId,
      );
      if (cancelled || restored === null) return;
      setSourceDirectory(restored.sourceDirectory as BrowserDirectoryHandle);
      setOutputDirectory(restored.outputDirectory);
      setRestoredUi(restored.ui);
      const restoredFiles = await collectSemiAutomaticSourceFiles(
        restored.sourceDirectory as BrowserDirectoryHandle,
      );
      if (cancelled) return;
      setSourceFiles(restoredFiles);
      setNotice(
        'Przywrócono run i lokalne foldery. Analiza może być dalej monitorowana.',
      );
    })().catch(() => {
      if (!cancelled) {
        setNotice(
          'Przywrócono identyfikator runu, ale lokalne foldery wymagają ponownego wskazania.',
        );
      }
    });
    return () => {
      cancelled = true;
    };
  }, [api, localSessionStore]);

  useEffect(() => {
    if (run === null || !isActiveRun(run)) {
      pollDeadlineRef.current = null;
      return undefined;
    }
    const deadline =
      pollDeadlineRef.current ?? Date.now() + POLL_MAX_DURATION_MS;
    pollDeadlineRef.current = deadline;
    let cancelled = false;
    let timer: number | null = null;

    const poll = async (): Promise<void> => {
      const result = await api.getSemiAutomaticImageSelection(run.id);
      if (cancelled) return;
      if (result.error !== undefined || result.data === undefined) {
        setNotice('Nie udało się odświeżyć runu. Próba zostanie ponowiona.');
      } else {
        setRun(result.data);
        if (!isActiveRun(result.data)) return;
      }
      if (!cancelled && Date.now() < deadline) {
        timer = window.setTimeout(() => void poll(), POLL_INTERVAL_MS);
      } else if (!cancelled) {
        setNotice(
          'Automatyczne odświeżanie zatrzymano po 45 minutach. Odśwież stronę, aby monitorować dalej.',
        );
      }
    };

    timer = window.setTimeout(() => void poll(), POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      if (timer !== null) window.clearTimeout(timer);
    };
  }, [api, run]);

  async function chooseSourceDirectory(): Promise<void> {
    if (busy || sourceLoading || capabilities?.enabled !== true) return;
    setSourceLoading(true);
    setError('');
    try {
      const directory = await pickSemiAutomaticSourceDirectory();
      const files = await collectSemiAutomaticSourceFiles(directory);
      if (files.length === 0) {
        setError('Wybrany folder nie zawiera plików JPEG.');
        return;
      }
      setSourceDirectory(directory);
      setSourceFiles(files);
      setResume(null);
      setUploadProgress(EMPTY_UPLOAD_PROGRESS);
      setNotice(
        `Znaleziono ${files.length.toLocaleString('pl-PL')} JPEG-ów. Zdjęcia zostaną wysłane wyłącznie do lokalnego Admin API.`,
      );
    } catch (cause) {
      if (!isPickerCancellation(cause)) {
        setError(
          cause instanceof Error
            ? cause.message
            : 'Nie udało się odczytać katalogu źródłowego.',
        );
      }
    } finally {
      setSourceLoading(false);
    }
  }

  async function chooseOutputDirectory(): Promise<void> {
    if (busy || capabilities?.enabled !== true) return;
    setError('');
    try {
      const directory = await pickSemiAutomaticOutputDirectory();
      setOutputDirectory(directory);
      setNotice(
        `Wybrano katalog docelowy „${directory.name}”. Automatyczne pliki zostaną do niego zapisane po analizie.`,
      );
    } catch (cause) {
      if (!isPickerCancellation(cause)) {
        setError(
          'Nie udało się wybrać katalogu docelowego. Użyj aktualnego Chrome lub Edge.',
        );
      }
    }
  }

  async function startUpload(
    activeResume = resume,
    activeSourceDirectory = sourceDirectory,
    activeSourceFiles = sourceFiles,
  ): Promise<void> {
    if (
      busy ||
      capabilities?.enabled !== true ||
      activeSourceDirectory === null ||
      outputDirectory === null ||
      first === null ||
      last === null ||
      first > last
    ) {
      return;
    }
    setBusy(true);
    setError('');
    setNotice('Tworzę staging i przesyłam JPEG-i do lokalnego Admin API…');
    try {
      const result = await uploadSemiAutomaticSelectionFolder({
        api,
        direction,
        files: activeSourceFiles,
        firstSequenceNumber: first,
        lastSequenceNumber: last,
        onProgress: setUploadProgress,
        recognizerVariant,
        resume: activeResume,
        sourceDirectory: activeSourceDirectory,
      });
      if (!result.ok) {
        setError(result.error);
        setResume(result.resume);
        return;
      }
      setResume(null);
      setRun(result.created.run);
      window.localStorage.setItem(RUN_STORAGE_KEY, result.created.run.id);
      await localSessionStore.save({
        outputDirectory,
        outputManifestChecksumSha256: null,
        runId: result.created.run.id,
        sourceDirectory: activeSourceDirectory,
        ui: {
          activeExpectedIndex: null,
          mode: 'configuration',
          scrollLeft: 0,
          scrollTop: 0,
          zoomPercent: 100,
        },
        updatedAt: new Date().toISOString(),
      });
      setRestoredUi({
        activeExpectedIndex: null,
        mode: 'configuration',
        scrollLeft: 0,
        scrollTop: 0,
        zoomPercent: 100,
      });
      setNotice(
        result.created.created
          ? 'Run został utworzony. Worker rozpozna wyłącznie zakresy widoczne na zdjęciach.'
          : 'Przywrócono istniejący run dla dokładnie tego samego stagingu i zakresu.',
      );
    } catch {
      setError('Nie udało się rozpocząć półautomatycznej selekcji.');
    } finally {
      setBusy(false);
    }
  }

  async function resumeUpload(): Promise<void> {
    if (resume === null) return;
    setSourceDirectory(resume.sourceDirectory);
    setSourceFiles(resume.files);
    await startUpload(resume, resume.sourceDirectory, resume.files);
  }

  async function cancelUpload(): Promise<void> {
    if (resume === null || busy) return;
    setBusy(true);
    try {
      await cancelSemiAutomaticSelectionUpload(api, resume);
      setResume(null);
      setUploadProgress(EMPTY_UPLOAD_PROGRESS);
      setNotice('Niedokończony staging został anulowany.');
    } catch {
      setError('Nie udało się anulować niedokończonego stagingu.');
    } finally {
      setBusy(false);
    }
  }

  async function controlRun(action: 'pause' | 'resume' | 'cancel') {
    if (run === null || busy) return;
    setBusy(true);
    setError('');
    try {
      const result =
        action === 'pause'
          ? await api.pauseSemiAutomaticImageSelection(run.id)
          : action === 'resume'
            ? await api.resumeSemiAutomaticImageSelection(run.id)
            : await api.cancelSemiAutomaticImageSelection(run.id);
      if (result.error !== undefined || result.data === undefined) {
        setError(
          apiErrorMessage(result.error, 'Nie udało się zmienić stanu runu.'),
        );
        return;
      }
      setRun(result.data);
      setNotice(
        action === 'pause'
          ? 'Run został wstrzymany po trwałym checkpointcie.'
          : action === 'resume'
            ? 'Run został wznowiony od trwałego checkpointu.'
            : 'Run został anulowany. Żaden lokalny plik nie został usunięty.',
      );
    } catch {
      setError('Połączenie z lokalnym Admin API zostało przerwane.');
    } finally {
      setBusy(false);
    }
  }

  const persistReviewUi = useCallback(
    async (
      ui: SemiAutomaticSelectionLocalUiState,
      outputManifestChecksumSha256: string | null,
    ): Promise<void> => {
      if (run === null || sourceDirectory === null || outputDirectory === null)
        return;
      const current = await localSessionStore.load(run.id);
      await localSessionStore.save({
        outputDirectory,
        outputManifestChecksumSha256:
          outputManifestChecksumSha256 ??
          current?.outputManifestChecksumSha256 ??
          null,
        runId: run.id,
        sourceDirectory,
        ui,
        updatedAt: new Date().toISOString(),
      });
      setRestoredUi(ui);
    },
    [localSessionStore, outputDirectory, run, sourceDirectory],
  );

  return (
    <section
      aria-labelledby="semi-automatic-selection-title"
      className="semiAutomaticSelectionWorkspace"
    >
      <header className="semiAutomaticSelectionHeader">
        <div>
          <p className="eyebrow">Niezależnie od gry · lokalnie</p>
          <h1 id="semi-automatic-selection-title">
            Półautomatyczny wybór zdjęć
          </h1>
          <p>
            Algorytm rozpoznaje wyłącznie zakres na zdjęciu i wybiera środek
            jego grupy. Nie ocenia geometrii plansz ani symboli.
          </p>
        </div>
        {capabilities !== null ? (
          <span
            className={
              capabilities.enabled
                ? 'semiAutomaticSelectionCapability enabled'
                : 'semiAutomaticSelectionCapability disabled'
            }
          >
            {capabilities.enabled ? 'Moduł dostępny' : 'Moduł wyłączony'}
          </span>
        ) : (
          <span className="semiAutomaticSelectionCapability loading">
            {error === ''
              ? 'Sprawdzanie dostępności…'
              : 'Brak połączenia z API'}
          </span>
        )}
      </header>

      {capabilities !== null && !capabilities.enabled ? (
        <p className="feedbackBanner feedbackBannerError" role="alert">
          Półautomatyczna selekcja jest wyłączona przez lokalną flagę serwera.
          Ustawienie interfejsu nie może jej obejść.
        </p>
      ) : null}
      {error !== '' ? (
        <p className="feedbackBanner feedbackBannerError" role="alert">
          {error}
        </p>
      ) : null}
      {notice !== '' ? <p className="feedbackBanner">{notice}</p> : null}

      <section
        className="semiAutomaticSelectionSetup"
        aria-label="Konfiguracja runu"
      >
        <div className="semiAutomaticSelectionSetupHeader">
          <div>
            <p className="eyebrow">1. Konfiguracja</p>
            <h2>Foldery i zakres numeracji</h2>
          </div>
          {capabilities !== null ? (
            <small>
              {capabilities.rangeConvention} · pełny zakres:{' '}
              {capabilities.fullRangeSize} plansz
            </small>
          ) : null}
        </div>
        <div className="semiAutomaticSelectionForm">
          <label>
            Pierwsza plansza
            <input
              disabled={
                busy || capabilitiesLoading || capabilities?.enabled !== true
              }
              min="1"
              onChange={(event) => setFirstSequenceNumber(event.target.value)}
              placeholder="np. 1"
              type="number"
              value={firstSequenceNumber}
            />
          </label>
          <label>
            Ostatnia plansza
            <input
              disabled={
                busy || capabilitiesLoading || capabilities?.enabled !== true
              }
              min={firstSequenceNumber || '1'}
              onChange={(event) => setLastSequenceNumber(event.target.value)}
              placeholder="np. 19809"
              type="number"
              value={lastSequenceNumber}
            />
          </label>
          <label>
            Kolejność numeracji
            <select
              disabled={
                busy || capabilitiesLoading || capabilities?.enabled !== true
              }
              onChange={(event) =>
                setDirection(event.target.value as 'ascending' | 'descending')
              }
              value={direction}
            >
              <option value="ascending">Rosnąco</option>
              <option value="descending">Malejąco</option>
            </select>
          </label>
          <label>
            Wariant OCR zakresu
            <select
              disabled={
                busy || capabilitiesLoading || capabilities?.enabled !== true
              }
              onChange={(event) =>
                setRecognizerVariant(
                  event.target.value as 'default_v3' | 'five_anchor_v6',
                )
              }
              value={recognizerVariant}
            >
              {capabilities?.selectionRecognizerVariants.map((variant) => (
                <option key={variant.id} value={variant.id}>
                  {variant.label}
                </option>
              ))}
            </select>
            {capabilities?.selectionRecognizerVariants.find(
              (variant) => variant.id === recognizerVariant,
            )?.experimental ? (
              <small>
                Wariant testowy: tworzy osobny, checksum-bound run i nie zmienia
                istniejących wyników.
              </small>
            ) : null}
          </label>
          <div className="semiAutomaticSelectionFolderButtons">
            <button
              className="secondaryButton"
              disabled={
                busy ||
                sourceLoading ||
                capabilitiesLoading ||
                capabilities?.enabled !== true
              }
              onClick={() => void chooseSourceDirectory()}
              type="button"
            >
              {sourceLoading
                ? 'Odczytywanie źródła…'
                : sourceDirectory === null
                  ? 'Wybierz katalog źródłowy'
                  : `Źródło: ${sourceDirectory.name}`}
            </button>
            <button
              className="secondaryButton"
              disabled={
                busy || capabilitiesLoading || capabilities?.enabled !== true
              }
              onClick={() => void chooseOutputDirectory()}
              type="button"
            >
              {outputDirectory === null
                ? 'Wybierz katalog docelowy'
                : `Wynik: ${outputDirectory.name}`}
            </button>
          </div>
        </div>
        <p className="semiAutomaticSelectionSummary">
          {sourceFiles.length > 0
            ? `${sourceFiles.length.toLocaleString('pl-PL')} JPEG-ów w źródle.`
            : 'Wybierz katalog ze zdjęciami JPG/JPEG.'}{' '}
          {expectedRangeCount === null
            ? 'Podaj poprawny zakres, aby wyliczyć oczekiwane grupy.'
            : `Powstanie ${expectedRangeCount.toLocaleString('pl-PL')} oczekiwanych zakresów po maksymalnie ${capabilities?.fullRangeSize ?? 9} plansz.`}
        </p>
        <button
          aria-busy={busy}
          className="primaryButton"
          disabled={
            busy ||
            sourceLoading ||
            capabilitiesLoading ||
            capabilities?.enabled !== true ||
            sourceDirectory === null ||
            outputDirectory === null ||
            sourceFiles.length === 0 ||
            !validBounds
          }
          onClick={() => void startUpload()}
          type="button"
        >
          {busy ? 'Przygotowywanie runu…' : 'Prześlij i rozpocznij analizę'}
        </button>
      </section>

      {uploadProgress.totalFiles > 0 ? (
        <section
          className="semiAutomaticSelectionUpload"
          aria-label="Postęp uploadu"
        >
          <div>
            <strong>
              {uploadProgress.uploadedFiles.toLocaleString('pl-PL')} /{' '}
              {uploadProgress.totalFiles.toLocaleString('pl-PL')} plików
            </strong>
            <span>
              {formatBytes(uploadProgress.uploadedBytes)} /{' '}
              {formatBytes(uploadProgress.totalBytes)}
            </span>
          </div>
          <progress max={100} value={uploadPercentage} />
          {resume !== null ? (
            <div className="semiAutomaticSelectionActions">
              <button
                className="primaryButton"
                disabled={busy}
                onClick={() => void resumeUpload()}
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
          className="semiAutomaticSelectionRun"
          aria-label="Postęp analizy zakresów"
        >
          <div className="semiAutomaticSelectionRunHeading">
            <div>
              <p className="eyebrow">2. Analiza zakresów</p>
              <h2>
                {jobStageLabel(run.job.progress.stage, run.job.inputPayload)}
              </h2>
              <p>
                {run.firstSequenceNumber}–{run.lastSequenceNumber} ·{' '}
                {run.direction === 'ascending' ? 'rosnąco' : 'malejąco'}
              </p>
            </div>
            <span className={`jobStatus jobStatus-${run.job.status}`}>
              {jobStatusLabel(run.job.status)}
            </span>
          </div>
          <div className="semiAutomaticSelectionRunBody">
            <div className="semiAutomaticSelectionRunProgress">
              <div>
                <strong>{jobProgressLabel(run.job)}</strong>
                <span>
                  {jobProgressPercent(run.job) === null
                    ? 'Postęp oczekuje na worker'
                    : `${jobProgressPercent(run.job)?.toFixed(1)}%`}
                </span>
              </div>
              <progress max={100} value={jobProgressPercent(run.job) ?? 0} />
            </div>
            <dl>
              <Counter label="Źródła" value={run.source.sourceCount} />
              <Counter
                label="Zeskanowane"
                value={counter(run, ['scanned', 'sourcesScanned', 'processed'])}
              />
              <Counter
                label="Wybory"
                value={counter(run, ['selected', 'autoSelected'])}
              />
              <Counter label="Luki" value={counter(run, ['missing', 'gaps'])} />
              <Counter label="Konflikty" value={counter(run, ['conflicts'])} />
              <Counter
                label="Błędy"
                value={counter(run, ['errors', 'sourceErrors'])}
              />
            </dl>
          </div>
          <div className="semiAutomaticSelectionActions">
            {run.job.status === 'processing' ? (
              <button
                className="secondaryButton"
                disabled={busy}
                onClick={() => void controlRun('pause')}
                type="button"
              >
                Wstrzymaj po checkpointcie
              </button>
            ) : null}
            {run.job.status === 'waiting_for_review' &&
            run.status === 'paused' ? (
              <button
                className="primaryButton"
                disabled={busy}
                onClick={() => void controlRun('resume')}
                type="button"
              >
                Wznów analizę
              </button>
            ) : null}
            {run.job.status === 'created' ||
            run.job.status === 'processing' ||
            run.job.status === 'waiting_for_review' ? (
              <button
                className="secondaryButton"
                disabled={busy}
                onClick={() => void controlRun('cancel')}
                type="button"
              >
                Anuluj run
              </button>
            ) : null}
          </div>
          {!isActiveRun(run) &&
          run.job.status !== 'failed' &&
          run.job.status !== 'cancelled' ? (
            <p className="semiAutomaticSelectionNextStep">
              Analiza jest gotowa. Przegląd automatycznych wyborów i ręczne
              uzupełnianie luk zostaną udostępnione w kolejnym kroku workflow.
            </p>
          ) : null}
        </section>
      ) : null}
      {run !== null &&
      outputDirectory !== null &&
      sourceDirectory !== null &&
      sourceFiles.length > 0 &&
      [
        'analysis_complete',
        'syncing_output',
        'review_mode',
        'edit_source_mode',
        'completed',
      ].includes(run.status) ? (
        <SemiAutomaticSelectionReviewWorkspace
          client={api}
          initialUi={restoredUi}
          onPersistUi={persistReviewUi}
          outputDirectory={outputDirectory}
          run={run}
          sourceFiles={sourceFiles}
        />
      ) : null}
    </section>
  );
}

function Counter({
  label,
  value,
}: {
  readonly label: string;
  readonly value: number | null;
}) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value === null ? '—' : value.toLocaleString('pl-PL')}</dd>
    </div>
  );
}

function counter(
  run: SemiAutomaticSelectionRunResponse,
  keys: readonly string[],
): number | null {
  for (const key of keys) {
    const value = run.counters[key];
    if (typeof value === 'number' && Number.isFinite(value)) return value;
  }
  return null;
}

function isActiveRun(run: SemiAutomaticSelectionRunResponse): boolean {
  return run.job.status === 'created' || run.job.status === 'processing';
}

function parsePositiveInteger(value: string): number | null {
  if (!/^\d+$/u.test(value.trim())) return null;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed >= 1 ? parsed : null;
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KiB`;
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MiB`;
  return `${(value / 1024 ** 3).toFixed(2)} GiB`;
}

function isPickerCancellation(cause: unknown): boolean {
  return cause instanceof DOMException && cause.name === 'AbortError';
}
