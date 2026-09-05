'use client';

import type {
  AdminApiClient,
  SemiAutomaticSelectionRangeResponse,
  SemiAutomaticSelectionRunResponse,
} from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useMemo, useState } from 'react';

import {
  ManualImageViewer,
  useManualImageViewer,
} from '@/features/manual-image-selection/manual-image-viewer';

import type { SemiAutomaticSourceFile } from './semi-automatic-selection-actions.ts';
import type {
  SemiAutomaticOutputDirectoryHandle,
  SemiAutomaticSelectionLocalUiState,
} from './semi-automatic-selection-output-storage.ts';
import { synchronizeSemiAutomaticSelectionOutput } from './semi-automatic-selection-output-sync.ts';
import type { SemiAutomaticSelectionOutputManifestV1 } from './semi-automatic-selection-output.ts';
import {
  isFormInteractionTarget,
  loadAllSemiAutomaticSelectionRanges,
  manualEditSourceStartIndex,
  writeManualSemiAutomaticSelection,
} from './semi-automatic-selection-review.ts';

type ReviewClient = Pick<
  AdminApiClient,
  | 'acknowledgeSemiAutomaticImageSelectionOutput'
  | 'getSemiAutomaticImageSelectionSourceAsset'
  | 'listSemiAutomaticImageSelectionRanges'
>;

interface Props {
  readonly client: ReviewClient;
  readonly initialUi: SemiAutomaticSelectionLocalUiState | null;
  readonly onPersistUi: (
    ui: SemiAutomaticSelectionLocalUiState,
    manifestChecksumSha256: string | null,
  ) => Promise<void>;
  readonly outputDirectory: SemiAutomaticOutputDirectoryHandle;
  readonly run: SemiAutomaticSelectionRunResponse;
  readonly sourceFiles: readonly SemiAutomaticSourceFile[];
}

type WorkspaceMode = 'idle' | 'syncing_output' | 'review' | 'edit_source';

export function SemiAutomaticSelectionReviewWorkspace({
  client,
  initialUi,
  onPersistUi,
  outputDirectory,
  run,
  sourceFiles,
}: Props) {
  const [mode, setMode] = useState<WorkspaceMode>('idle');
  const [ranges, setRanges] = useState<
    readonly SemiAutomaticSelectionRangeResponse[]
  >([]);
  const [manifest, setManifest] =
    useState<SemiAutomaticSelectionOutputManifestV1 | null>(null);
  const [activeExpectedIndex, setActiveExpectedIndex] = useState(
    initialUi?.activeExpectedIndex ?? 0,
  );
  const [sourceIndex, setSourceIndex] = useState(0);
  const [syncProgress, setSyncProgress] = useState({ processed: 0, total: 0 });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const viewerFiles = useMemo(
    () =>
      sourceFiles.map((source) => ({
        handle: source.handle,
        relativePath: source.relativePath,
      })),
    [sourceFiles],
  );
  const onViewerError = useCallback((message: string) => setError(message), []);
  const viewer = useManualImageViewer(viewerFiles, sourceIndex, onViewerError, {
    scrollLeft: initialUi?.scrollLeft ?? 0,
    scrollTop: initialUi?.scrollTop ?? 0,
    zoom: (initialUi?.zoomPercent ?? 100) / 100,
  });
  const activeRange = ranges[activeExpectedIndex] ?? null;
  const activeSelection =
    manifest?.selections.find(
      (selection) => selection.expectedIndex === activeExpectedIndex,
    ) ?? null;
  const activeConflict =
    manifest?.conflicts.find(
      (conflict) => conflict.expectedIndex === activeExpectedIndex,
    ) ?? null;

  useEffect(() => {
    if (mode !== 'review' && mode !== 'edit_source') return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (busy || isFormInteractionTarget(event.target)) return;
      if (mode === 'review') {
        if (event.key === 'ArrowLeft') moveExpectedRange(-1);
        else if (event.key === 'ArrowRight') moveExpectedRange(1);
        else if (event.key.toLowerCase() === 'f') enterEditSource();
        else return;
      } else if (event.key === 'ArrowLeft') {
        moveSource(-1);
      } else if (event.key === 'ArrowRight') {
        moveSource(1);
      } else if (event.key === 'Enter' || event.key.toLowerCase() === 'f') {
        void acceptSource();
      } else if (event.key === 'Escape') {
        setMode('review');
      } else return;
      event.preventDefault();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  });

  useEffect(() => {
    if (mode !== 'review' && mode !== 'edit_source') return;
    void onPersistUi(
      {
        activeExpectedIndex,
        mode,
        scrollLeft: viewer.imageViewportRef.current?.scrollLeft ?? 0,
        scrollTop: viewer.imageViewportRef.current?.scrollTop ?? 0,
        zoomPercent: Math.round(viewer.zoom * 100),
      },
      null,
    );
  }, [
    activeExpectedIndex,
    mode,
    onPersistUi,
    viewer.imageViewportRef,
    viewer.zoom,
  ]);

  async function prepareReview(): Promise<void> {
    if (busy || sourceFiles.length !== run.source.sourceCount) {
      if (sourceFiles.length !== run.source.sourceCount) {
        setError(
          'Katalog źródłowy nie odpowiada stagingowi. Wskaż ponownie dokładne źródło runu.',
        );
      }
      return;
    }
    setBusy(true);
    setError('');
    setNotice('Synchronizuję automatyczne wybory z katalogiem docelowym…');
    try {
      const snapshot = await loadAllSemiAutomaticSelectionRanges(
        client,
        run.id,
      );
      setSyncProgress({ processed: 0, total: snapshot.length });
      const synchronized = await synchronizeSemiAutomaticSelectionOutput({
        client,
        directory: outputDirectory,
        onProgress: (processed, total) => setSyncProgress({ processed, total }),
        ranges: snapshot,
        run,
      });
      const refreshed = await loadAllSemiAutomaticSelectionRanges(
        client,
        run.id,
      );
      const requestedIndex = Math.min(
        Math.max(initialUi?.activeExpectedIndex ?? 0, 0),
        Math.max(0, refreshed.length - 1),
      );
      setRanges(refreshed);
      setManifest(synchronized.manifest);
      setActiveExpectedIndex(requestedIndex);
      const nextMode = hasSource(refreshed[requestedIndex])
        ? 'review'
        : 'edit_source';
      setMode(nextMode);
      setSourceIndex(
        manualEditSourceStartIndex(
          refreshed,
          requestedIndex,
          sourceFiles.length,
        ),
      );
      await onPersistUi(
        {
          activeExpectedIndex: requestedIndex,
          mode: nextMode,
          scrollLeft: viewer.imageViewportRef.current?.scrollLeft ?? 0,
          scrollTop: viewer.imageViewportRef.current?.scrollTop ?? 0,
          zoomPercent: initialUi?.zoomPercent ?? 100,
        },
        synchronized.manifestChecksumSha256,
      );
      setNotice(
        synchronized.gapCount === 0
          ? 'Wszystkie zakresy mają zdjęcie. Możesz przejrzeć lub zastąpić każdy wybór.'
          : `Do ręcznego uzupełnienia pozostało ${synchronized.gapCount.toLocaleString('pl-PL')} zakresów.`,
      );
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : 'Nie udało się przygotować przeglądu.',
      );
    } finally {
      setBusy(false);
    }
  }

  function moveExpectedRange(delta: -1 | 1): void {
    if (ranges.length === 0) return;
    const next = Math.max(
      0,
      Math.min(ranges.length - 1, activeExpectedIndex + delta),
    );
    setActiveExpectedIndex(next);
    setSourceIndex(
      manualEditSourceStartIndex(ranges, next, sourceFiles.length),
    );
    setMode(hasSource(ranges[next]) ? 'review' : 'edit_source');
  }

  function enterEditSource(): void {
    if (activeRange === null) return;
    setSourceIndex(
      manualEditSourceStartIndex(
        ranges,
        activeExpectedIndex,
        sourceFiles.length,
      ),
    );
    setMode('edit_source');
  }

  function moveSource(delta: -1 | 1): void {
    setSourceIndex((current) =>
      Math.max(0, Math.min(sourceFiles.length - 1, current + delta)),
    );
  }

  async function acceptSource(): Promise<void> {
    if (
      busy ||
      mode !== 'edit_source' ||
      activeRange === null ||
      manifest === null
    )
      return;
    const source = sourceFiles[sourceIndex];
    if (source === undefined) return;
    setBusy(true);
    setError('');
    try {
      const currentFile = await source.handle.getFile();
      const saved = await writeManualSemiAutomaticSelection({
        client,
        directory: outputDirectory,
        manifest,
        range: activeRange,
        runId: run.id,
        source: {
          file: currentFile,
          relativePath: source.relativePath,
          sourceIndex,
        },
      });
      const nextRanges = ranges.map((range) =>
        range.expectedIndex === saved.range.expectedIndex ? saved.range : range,
      );
      const nextIndex = Math.min(activeExpectedIndex + 1, ranges.length - 1);
      setRanges(nextRanges);
      setManifest(saved.manifest);
      setActiveExpectedIndex(nextIndex);
      setSourceIndex(
        manualEditSourceStartIndex(nextRanges, nextIndex, sourceFiles.length),
      );
      setMode(hasSource(nextRanges[nextIndex]) ? 'review' : 'edit_source');
      await onPersistUi(
        {
          activeExpectedIndex: nextIndex,
          mode: hasSource(nextRanges[nextIndex]) ? 'review' : 'edit_source',
          scrollLeft: initialUi?.scrollLeft ?? 0,
          scrollTop: initialUi?.scrollTop ?? 0,
          zoomPercent: Math.round(viewer.zoom * 100),
        },
        saved.manifestChecksumSha256,
      );
      setNotice(
        activeSelection === null
          ? 'Luka została uzupełniona i zweryfikowana.'
          : 'Źródło zakresu zostało bezpiecznie zastąpione.',
      );
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : 'Nie udało się zapisać ręcznego wyboru.',
      );
    } finally {
      setBusy(false);
    }
  }

  if (mode === 'idle' || mode === 'syncing_output') {
    const percentage =
      syncProgress.total === 0
        ? 0
        : (syncProgress.processed / syncProgress.total) * 100;
    return (
      <section
        className="semiAutomaticSelectionReview"
        aria-label="Przegląd wyborów"
      >
        <div>
          <p className="eyebrow">3. Weryfikacja wyborów</p>
          <h2>Sprawdź zakresy i uzupełnij luki</h2>
          <p>
            Najpierw zapiszę automatyczne wybory jako niezmienione JPEG-i, a
            następnie pokażę wszystkie zakresy po kolei.
          </p>
        </div>
        {syncProgress.total > 0 ? (
          <div className="semiAutomaticSelectionRunProgress">
            <div>
              <strong>
                {syncProgress.processed.toLocaleString('pl-PL')} /{' '}
                {syncProgress.total.toLocaleString('pl-PL')} zakresów
              </strong>
              <span>{percentage.toFixed(1)}%</span>
            </div>
            <progress max={100} value={percentage} />
          </div>
        ) : null}
        {error !== '' ? (
          <p className="feedbackBanner feedbackBannerError" role="alert">
            {error}
          </p>
        ) : null}
        <button
          className="primaryButton"
          disabled={busy}
          onClick={() => {
            setMode('syncing_output');
            void prepareReview();
          }}
          type="button"
        >
          {busy ? 'Przygotowywanie przeglądu…' : 'Przygotuj przegląd'}
        </button>
      </section>
    );
  }

  return (
    <section
      className="semiAutomaticSelectionReview"
      aria-label="Review zakresów"
    >
      <div className="semiAutomaticSelectionReviewHeading">
        <div>
          <p className="eyebrow">
            {mode === 'review' ? 'REVIEW MODE' : 'EDIT SOURCE MODE'}
          </p>
          <h2>
            {activeRange === null
              ? 'Brak zakresu'
              : `${activeRange.rangeStart}–${activeRange.rangeEnd}`}
          </h2>
          <p>
            Zakres {activeExpectedIndex + 1} z {ranges.length} · plik{' '}
            {activeRange?.fileName ?? '—'}
          </p>
        </div>
        <span className="semiAutomaticSelectionCapability enabled">
          {activeRange === null
            ? 'Brak danych'
            : hasSource(activeRange)
              ? (activeSelection?.status ?? activeRange.status)
              : 'Luka — wybierz zdjęcie'}
        </span>
      </div>
      {error !== '' ? (
        <p className="feedbackBanner feedbackBannerError" role="alert">
          {error}
        </p>
      ) : null}
      {notice !== '' ? <p className="feedbackBanner">{notice}</p> : null}
      <ManualImageViewer
        busy={busy}
        currentLabel={
          activeRange === null
            ? 'Brak zakresu'
            : `Zakres ${activeRange.rangeStart}–${activeRange.rangeEnd}`
        }
        currentPosition={sourceIndex + 1}
        currentRelativePath={sourceFiles[sourceIndex]?.relativePath ?? null}
        imageCount={sourceFiles.length}
        navigationStepLabel={
          mode === 'review'
            ? '←/→: zakres · F: zmień źródło'
            : '←/→: zdjęcie · Enter/F: zapisz · Esc: anuluj'
        }
        nextDisabled={
          mode === 'review'
            ? activeExpectedIndex >= ranges.length - 1
            : sourceIndex >= sourceFiles.length - 1
        }
        onNext={() =>
          mode === 'review' ? moveExpectedRange(1) : moveSource(1)
        }
        onPrevious={() =>
          mode === 'review' ? moveExpectedRange(-1) : moveSource(-1)
        }
        previousDisabled={
          mode === 'review' ? activeExpectedIndex <= 0 : sourceIndex <= 0
        }
        state={viewer}
        toolbarStart={
          mode === 'review' ? (
            <button
              className="primaryButton"
              disabled={busy || activeRange === null}
              onClick={enterEditSource}
              type="button"
            >
              Zmień źródło (F)
            </button>
          ) : (
            <div className="semiAutomaticSelectionActions">
              <button
                className="secondaryButton"
                disabled={busy}
                onClick={() => setMode('review')}
                type="button"
              >
                Anuluj (Esc)
              </button>
              <button
                className="primaryButton"
                disabled={busy || activeRange === null}
                onClick={() => void acceptSource()}
                type="button"
              >
                {busy ? 'Zapisywanie…' : 'Użyj tego zdjęcia (Enter / F)'}
              </button>
            </div>
          )
        }
      />
      <dl className="semiAutomaticSelectionReviewDetails">
        <div>
          <dt>Źródło</dt>
          <dd>{activeRange?.sourceRelativePath ?? 'brak — ręczna luka'}</dd>
        </div>
        <div>
          <dt>Indeks źródła</dt>
          <dd>{activeRange?.sourceIndex ?? '—'}</dd>
        </div>
        <div>
          <dt>Pewność</dt>
          <dd>
            {activeRange?.rangeConfidence == null
              ? '—'
              : `${(activeRange.rangeConfidence * 100).toFixed(1)}%`}
          </dd>
        </div>
        <div>
          <dt>Metoda</dt>
          <dd>{activeRange?.selectionMethod ?? 'brak wyboru'}</dd>
        </div>
        <div>
          <dt>Konflikt</dt>
          <dd>{activeConflict?.reason ?? 'brak'}</dd>
        </div>
      </dl>
    </section>
  );
}

function hasSource(
  range: SemiAutomaticSelectionRangeResponse | undefined,
): boolean {
  return range?.sourceIndex !== null && range?.sourceIndex !== undefined;
}
