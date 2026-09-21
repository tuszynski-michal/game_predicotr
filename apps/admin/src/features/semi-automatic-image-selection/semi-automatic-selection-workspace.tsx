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
  createV7SelectionFromLocalSource,
  loadSemiAutomaticReviewSourceFiles,
  pickSemiAutomaticOutputDirectory,
  selectSemiAutomaticLocalSource,
  type SemiAutomaticLocalSourceSelection,
  type SemiAutomaticReviewSourceFile,
  type SemiAutomaticSelectionClient,
} from './semi-automatic-selection-actions.ts';
import {
  IndexedDbSemiAutomaticSelectionLocalSessionStore,
  restoreSemiAutomaticSelectionLocalSession,
  type SemiAutomaticOutputDirectoryHandle,
  type SemiAutomaticSelectionLocalUiState,
} from './semi-automatic-selection-output-storage.ts';
import { SemiAutomaticSelectionReviewWorkspace } from './semi-automatic-selection-review-workspace';
import { SelectedImageCropWorkspace } from './selected-image-crop-workspace';
import { V7SelectionReviewWorkspace } from './v7-selection-review-workspace';
import {
  deriveV7OutputDirectory,
  formatV7PageBoundary,
  normalizeV7SelectionForm,
  v7SelectionFormErrorMessage,
  type V7BorderStyle,
  type V7SelectionMode,
} from './v7-selection-form.ts';

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
      | 'listSemiAutomaticImageSelectionSources'
      | 'pauseSemiAutomaticImageSelection'
      | 'resumeSemiAutomaticImageSelection'
      | 'selectSemiAutomaticImageSelectionSourceFolder'
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
  const [sourceSelection, setSourceSelection] =
    useState<SemiAutomaticLocalSourceSelection | null>(null);
  const [sourceFiles, setSourceFiles] = useState<
    readonly SemiAutomaticReviewSourceFile[]
  >([]);
  const [outputDirectory, setOutputDirectory] =
    useState<SemiAutomaticOutputDirectoryHandle | null>(null);
  const [firstSequenceNumber, setFirstSequenceNumber] = useState('');
  const [lastSequenceNumber, setLastSequenceNumber] = useState('');
  const [direction, setDirection] = useState<'ascending' | 'descending'>(
    'ascending',
  );
  const [v7Mode, setV7Mode] = useState<V7SelectionMode>('semi_automatic');
  const [v7BorderStyle, setV7BorderStyle] =
    useState<V7BorderStyle>('top_and_sides');
  const [run, setRun] = useState<SemiAutomaticSelectionRunResponse | null>(
    null,
  );
  const [sourceLoading, setSourceLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [restoredUi, setRestoredUi] =
    useState<SemiAutomaticSelectionLocalUiState | null>(null);
  const [restoreComplete, setRestoreComplete] = useState(
    () =>
      typeof window === 'undefined' ||
      window.localStorage.getItem(RUN_STORAGE_KEY) === null,
  );
  const pollDeadlineRef = useRef<number | null>(null);

  const normalizedV7 = normalizeV7SelectionForm({
    borderStyle: v7BorderStyle,
    direction,
    firstPage: firstSequenceNumber,
    lastPage: lastSequenceNumber,
    mode: v7Mode,
  });
  const v7Summary = normalizedV7.ok
    ? `Powstaną ${normalizedV7.value.expectedRangeCount.toLocaleString('pl-PL')} oczekiwane zakresy od ${formatV7PageBoundary(normalizedV7.value.firstPage)} do ${formatV7PageBoundary(normalizedV7.value.lastPage)}.`
    : v7SelectionFormErrorMessage(normalizedV7.code);
  const capabilitiesLoading = capabilities === null && error === '';
  const configurationEnabled = Boolean(capabilities?.enabled);
  const v7StartEnabled = Boolean(capabilities?.v7.startEnabled);

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
      const firstPage = result.data.firstSequenceNumber;
      const lastPage = result.data.lastSequenceNumber - 8;
      setFirstSequenceNumber(
        result.data.direction === 'descending'
          ? String(lastPage)
          : String(firstPage),
      );
      setLastSequenceNumber(
        result.data.direction === 'descending'
          ? String(firstPage)
          : String(lastPage),
      );
      setDirection(result.data.direction);
      if (
        result.data.v7Configuration !== null &&
        result.data.v7Configuration !== undefined
      ) {
        setV7Mode(result.data.v7Configuration.mode);
        setV7BorderStyle(result.data.v7Configuration.borderStyle);
      }
      const restoredFiles = await loadSemiAutomaticReviewSourceFiles(
        api,
        result.data.id,
      );
      if (cancelled) return;
      setSourceFiles(restoredFiles);
      const restored = await restoreSemiAutomaticSelectionLocalSession(
        localSessionStore,
        runId,
      );
      if (cancelled || restored === null) return;
      setOutputDirectory(restored.outputDirectory);
      setRestoredUi(restored.ui);
      setNotice(
        'Przywrócono run i katalog wyniku. Analiza może być dalej monitorowana.',
      );
    })()
      .catch(() => {
        if (!cancelled) {
          setNotice(
            'Przywrócono identyfikator runu, ale katalog wyniku wymaga ponownego wskazania.',
          );
        }
      })
      .finally(() => {
        if (!cancelled) setRestoreComplete(true);
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
    if (busy || sourceLoading || !v7StartEnabled) return;
    setSourceLoading(true);
    setError('');
    try {
      const source = await selectSemiAutomaticLocalSource(api);
      if (source === null) return;
      setSourceSelection(source);
      setSourceFiles([]);
      setNotice(
        `Znaleziono ${source.supportedFileCount.toLocaleString('pl-PL')} JPEG-ów. Źródła nie będą kopiowane do stagingu.`,
      );
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : 'Nie udało się odczytać katalogu źródłowego.',
      );
    } finally {
      setSourceLoading(false);
    }
  }

  async function startAnalysis(): Promise<void> {
    if (
      busy ||
      !v7StartEnabled ||
      sourceSelection === null ||
      !normalizedV7.ok
    ) {
      return;
    }
    setBusy(true);
    setError('');
    setNotice('Tworzę manifest źródła bez kopiowania zdjęć do stagingu…');
    try {
      const result = await createV7SelectionFromLocalSource({
        api,
        configuration: normalizedV7.value,
        source: sourceSelection,
      });
      const files = await loadSemiAutomaticReviewSourceFiles(
        api,
        result.run.id,
      );
      setSourceFiles(files);
      setRun(result.run);
      window.localStorage.setItem(RUN_STORAGE_KEY, result.run.id);
      await localSessionStore.save({
        outputDirectory: null,
        outputManifestChecksumSha256: null,
        runId: result.run.id,
        sourceDirectory: null,
        ui: defaultLocalUi(),
        updatedAt: new Date().toISOString(),
      });
      setRestoredUi(defaultLocalUi());
      setNotice(
        result.created
          ? 'Run został utworzony. Worker rozpozna wyłącznie zakresy widoczne na zdjęciach.'
          : 'Przywrócono istniejący run dla dokładnie tego samego źródła i zakresu.',
      );
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : 'Nie udało się rozpocząć półautomatycznej selekcji.',
      );
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

  async function chooseHistoricalOutputDirectory(): Promise<void> {
    const historicalRun = run;
    if (
      busy ||
      historicalRun === null ||
      historicalRun.workflowMode === 'v7_selection'
    ) {
      return;
    }
    setBusy(true);
    setError('');
    try {
      const directory = await pickSemiAutomaticOutputDirectory();
      const current = await localSessionStore.load(historicalRun.id);
      const ui = current?.ui ?? restoredUi ?? defaultLocalUi();
      await localSessionStore.save({
        outputDirectory: directory,
        outputManifestChecksumSha256:
          current?.outputManifestChecksumSha256 ?? null,
        runId: historicalRun.id,
        sourceDirectory: current?.sourceDirectory ?? null,
        ui,
        updatedAt: new Date().toISOString(),
      });
      setOutputDirectory(directory);
      setRestoredUi(ui);
      setNotice('Katalog wyniku historycznego został przywrócony.');
    } catch (cause) {
      if (!isPickerCancellation(cause)) {
        setError(
          cause instanceof Error
            ? cause.message
            : 'Nie udało się wskazać katalogu wyniku historycznego.',
        );
      }
    } finally {
      setBusy(false);
    }
  }

  const persistReviewUi = useCallback(
    async (
      ui: SemiAutomaticSelectionLocalUiState,
      outputManifestChecksumSha256: string | null,
    ): Promise<void> => {
      if (run === null) return;
      const current = await localSessionStore.load(run.id);
      await localSessionStore.save({
        outputDirectory: outputDirectory ?? current?.outputDirectory ?? null,
        outputManifestChecksumSha256:
          outputManifestChecksumSha256 ??
          current?.outputManifestChecksumSha256 ??
          null,
        runId: run.id,
        sourceDirectory: null,
        ui,
        updatedAt: new Date().toISOString(),
      });
      setRestoredUi(ui);
    },
    [localSessionStore, outputDirectory, run],
  );
  const persistV7ReviewUi = useCallback(
    async (ui: SemiAutomaticSelectionLocalUiState): Promise<void> =>
      persistReviewUi(ui, null),
    [persistReviewUi],
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
            Automatyczna i półautomatyczna selekcja zdjęć V7
          </h1>
          <p>
            Zakres jest potwierdzany wyłącznie przez numery widoczne na własnym
            zdjęciu. Przed odbiorem V7 nie uruchamia analizy produkcyjnej.
          </p>
        </div>
        {capabilities !== null ? (
          <span
            className={
              capabilities.v7.startEnabled
                ? 'semiAutomaticSelectionCapability enabled'
                : 'semiAutomaticSelectionCapability disabled'
            }
          >
            {capabilities.v7.startEnabled
              ? 'V7 dostępne'
              : 'V7 oczekuje na odbiór'}
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
      {capabilities !== null && !capabilities.v7.startEnabled ? (
        <p className="feedbackBanner feedbackBannerError" role="alert">
          V7 jest zablokowane: {capabilities.v7.reason}
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
            <h2>V7: folder i zakresy stron</h2>
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
            Pierwszy zakres w nagraniu
            <input
              disabled={busy || capabilitiesLoading || !configurationEnabled}
              onChange={(event) => setFirstSequenceNumber(event.target.value)}
              placeholder="np. 1-9 albo 1"
              type="text"
              value={firstSequenceNumber}
            />
          </label>
          <label>
            Ostatni zakres w nagraniu
            <input
              disabled={busy || capabilitiesLoading || !configurationEnabled}
              onChange={(event) => setLastSequenceNumber(event.target.value)}
              placeholder="np. 19-27 albo 19"
              type="text"
              value={lastSequenceNumber}
            />
          </label>
          <label>
            Kolejność numeracji
            <select
              disabled={busy || capabilitiesLoading || !configurationEnabled}
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
            Tryb pracy
            <select
              disabled={busy || capabilitiesLoading || !configurationEnabled}
              onChange={(event) =>
                setV7Mode(event.target.value as V7SelectionMode)
              }
              value={v7Mode}
            >
              <option value="semi_automatic">Półautomat</option>
              <option value="automatic">Automat</option>
            </select>
          </label>
          <label>
            Styl obramowania
            <select
              disabled={busy || capabilitiesLoading || !configurationEnabled}
              onChange={(event) =>
                setV7BorderStyle(event.target.value as V7BorderStyle)
              }
              value={v7BorderStyle}
            >
              <option value="top_and_sides">Góra oraz boki</option>
              <option value="full_frame">Pełna ramka</option>
              <option value="irregular_or_none">
                Brak regularnej ramki / dekoracyjna
              </option>
            </select>
          </label>
          <div className="semiAutomaticSelectionFolderButtons">
            <button
              className="secondaryButton"
              disabled={
                busy || sourceLoading || capabilitiesLoading || !v7StartEnabled
              }
              onClick={() => void chooseSourceDirectory()}
              type="button"
            >
              {sourceLoading
                ? 'Odczytywanie źródła…'
                : sourceSelection === null
                  ? 'Wybierz katalog źródłowy'
                  : `Źródło: ${sourceSelection.displayName}`}
            </button>
          </div>
        </div>
        <p className="semiAutomaticSelectionSummary">
          {sourceSelection !== null
            ? `${sourceSelection.supportedFileCount.toLocaleString('pl-PL')} JPEG-ów w źródle.`
            : run !== null && sourceFiles.length > 0
              ? `${sourceFiles.length.toLocaleString('pl-PL')} JPEG-ów w źródle.`
              : 'Wybierz katalog ze zdjęciami JPG/JPEG.'}{' '}
          {v7Summary}{' '}
          {sourceSelection === null
            ? 'Katalog wynikowy zostanie wyprowadzony po wskazaniu źródła.'
            : `Wynik: ${deriveV7OutputDirectory(sourceSelection.path)}.`}
        </p>
        <button
          aria-busy={busy}
          className="primaryButton"
          disabled={
            busy ||
            sourceLoading ||
            capabilitiesLoading ||
            !v7StartEnabled ||
            sourceSelection === null ||
            !normalizedV7.ok
          }
          onClick={() => void startAnalysis()}
          type="button"
        >
          {busy
            ? 'Przygotowywanie runu…'
            : v7StartEnabled
              ? 'Rozpocznij analizę V7'
              : 'V7 czeka na odbiór'}
        </button>
      </section>

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
            {run.workflowMode !== 'v7_selection' && outputDirectory === null ? (
              <button
                className="secondaryButton"
                disabled={busy}
                onClick={() => void chooseHistoricalOutputDirectory()}
                type="button"
              >
                Wskaż katalog wyniku historycznego
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
      run.workflowMode !== 'v7_selection' &&
      outputDirectory !== null &&
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
      {run !== null &&
      run.workflowMode === 'v7_selection' &&
      restoreComplete &&
      sourceFiles.length > 0 ? (
        <V7SelectionReviewWorkspace
          initialUi={restoredUi}
          onPersistUi={persistV7ReviewUi}
          run={run}
          sourceFiles={sourceFiles}
        />
      ) : null}
      <SelectedImageCropWorkspace />
    </section>
  );
}

function defaultLocalUi(): SemiAutomaticSelectionLocalUiState {
  return {
    activeExpectedIndex: null,
    mode: 'configuration',
    scanSourceIndex: null,
    sequenceExpectedIndex: null,
    scrollLeft: 0,
    scrollTop: 0,
    viewSourceIndex: null,
    zoomPercent: 100,
  };
}

function isPickerCancellation(cause: unknown): boolean {
  return (
    cause instanceof DOMException &&
    (cause.name === 'AbortError' || cause.name === 'NotAllowedError')
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
