'use client';

import {
  findSequenceGaps,
  type SequenceRange,
} from '@game-predictor/manual-image-selection-core/repair';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import {
  FileSystemManualSelectionSourceAdapter,
  type ManualImageFile,
} from './manual-image-selection-fsa-adapter.ts';
import { ManualImageViewer, useManualImageViewer } from './manual-image-viewer';
import {
  appendRepairTraceEvent,
  deleteRepairFile,
  inspectRepairDirectory,
  ManualSelectionRepairStore,
  writeRepairFile,
  writeRepairManifest,
  type ManualSelectionRepairLocalState,
  type RepairDirectorySnapshot,
} from './manual-selection-repair-storage.ts';

const FILL_NAVIGATION_STEPS = [1, 2, 5, 10, 20, 50, 100] as const;

interface DirectoryPickerWindow extends Window {
  showDirectoryPicker?: (options?: {
    readonly mode?: 'read' | 'readwrite';
  }) => Promise<FileSystemDirectoryHandle>;
}

export function ManualSelectionRepairWorkspace() {
  const store = useMemo(() => new ManualSelectionRepairStore(), []);
  const operationQueueRef = useRef<Promise<void>>(Promise.resolve());
  const busyRef = useRef(false);
  const traceIndexRef = useRef(0);
  const viewStartedAtRef = useRef(0);
  const [snapshot, setSnapshot] = useState<RepairDirectorySnapshot | null>(
    null,
  );
  const [sourceImages, setSourceImages] = useState<ManualImageFile[]>([]);
  const [localState, setLocalState] =
    useState<ManualSelectionRepairLocalState | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [viewReady, setViewReady] = useState(false);
  const sourceCursor = localState?.sourceCursor ?? 0;
  const mode = localState?.mode ?? null;
  const gaps = useMemo(
    () =>
      snapshot === null
        ? []
        : findSequenceGaps(
            {
              end: snapshot.repairManifest.collectionEnd,
              start: snapshot.repairManifest.collectionStart,
            },
            snapshot.repairManifest.activeFiles,
            snapshot.repairManifest.deletedRanges,
          ),
    [snapshot],
  );
  const gapCursor = Math.min(
    localState?.gapCursor ?? 0,
    Math.max(0, gaps.length - 1),
  );
  const currentGap = gaps[gapCursor] ?? null;
  const currentSource = sourceImages[sourceCursor];
  const handleViewerError = useCallback(
    (message: string) => setError(message),
    [],
  );
  const viewer = useManualImageViewer(
    mode === 'fill' ? sourceImages : [],
    mode === 'fill' ? sourceCursor : -1,
    handleViewerError,
  );

  useEffect(() => {
    let cancelled = false;
    void store.loadLatest().then(async (saved) => {
      if (cancelled || saved === null) return;
      try {
        if (!(await hasPermission(saved.selectedDirectory, 'readwrite')))
          return;
        const restored = await inspectRepairDirectory(saved.selectedDirectory);
        let sources: ManualImageFile[] = [];
        if (
          saved.mode === 'fill' &&
          saved.sourceDirectory !== null &&
          (await hasPermission(saved.sourceDirectory, 'read'))
        ) {
          sources = await new FileSystemManualSelectionSourceAdapter(
            saved.sourceDirectory,
          ).listImages();
        }
        if (!cancelled) {
          setSnapshot(restored);
          setSourceImages(sources);
          setLocalState({
            ...saved,
            mode:
              saved.mode === 'fill' && sources.length === 0 ? null : saved.mode,
          });
        }
      } catch {
        // Stale handles are recovered explicitly by choosing the folders again.
      }
    });
    return () => {
      cancelled = true;
    };
  }, [store]);

  useEffect(() => {
    queueMicrotask(() => setViewReady(false));
    if (
      mode !== 'fill' ||
      snapshot === null ||
      currentGap === null ||
      currentSource === undefined ||
      viewer.visibleImageUrl === null
    )
      return;
    viewStartedAtRef.current = performance.now();
    const timer = window.setTimeout(() => {
      const visibleMilliseconds = Math.round(
        performance.now() - viewStartedAtRef.current,
      );
      setViewReady(true);
      void appendRepairTraceEvent(
        snapshot.directory,
        snapshot.repairManifest.repairKey,
        {
          decoded: true,
          eventIndex: traceIndexRef.current++,
          imageChecksum: null,
          kind: 'viewed',
          outputName: null,
          rangeEnd: currentGap.end,
          rangeStart: currentGap.start,
          recordedAt: new Date().toISOString(),
          repairKey: snapshot.repairManifest.repairKey,
          sourceIndex: sourceCursor,
          sourcePath: currentSource.relativePath,
          visibleMilliseconds,
        },
      ).catch(() => undefined);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [
    currentGap,
    currentSource,
    mode,
    snapshot,
    sourceCursor,
    viewer.visibleImageUrl,
  ]);

  useEffect(() => {
    if (mode !== 'fill') return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (busyRef.current || isEditable(event.target)) return;
      const key = event.key.toLowerCase();
      if (key === 'arrowleft' || key === 'arrowright') {
        event.preventDefault();
        moveSource(key === 'arrowleft' ? -1 : 1);
      } else if (key === 'arrowup' || key === 'arrowdown') {
        event.preventDefault();
        changeStep(key === 'arrowup' ? -1 : 1);
      } else if ((key === 'enter' || key === 'f') && !event.repeat) {
        event.preventDefault();
        void fillCurrentGap();
      } else if (
        !event.repeat &&
        (key === 'a' || (key === 'z' && (event.ctrlKey || event.metaKey)))
      ) {
        event.preventDefault();
        void undoLastFill();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  });

  async function chooseSelectedDirectory(): Promise<void> {
    setError(null);
    try {
      const directory = await pickDirectory('readwrite');
      const inspected = await inspectRepairDirectory(directory);
      await writeRepairManifest(directory, inspected.repairManifest);
      const saved = await store.load(inspected.repairManifest.repairKey);
      setSnapshot(inspected);
      setLocalState(
        saved ?? {
          fileCursor: 0,
          gapCursor: 0,
          mode: null,
          navigationStep: 1,
          repairKey: inspected.repairManifest.repairKey,
          scrollTop: 0,
          selectedDirectory: directory,
          sourceCursor: 0,
          sourceDirectory: null,
          updatedAt: new Date().toISOString(),
          zoom: 1,
        },
      );
      setNotice(
        `${inspected.files.length.toLocaleString('pl-PL')} plików · zakres ${inspected.repairManifest.collectionStart}–${inspected.repairManifest.collectionEnd}.`,
      );
    } catch (cause) {
      if (!isPickerCancelled(cause)) setError(errorMessage(cause));
    }
  }

  async function startFill(): Promise<void> {
    if (snapshot === null || localState === null) return;
    if (gaps.length === 0) {
      setNotice('Katalog nie zawiera luk do uzupełnienia.');
      return;
    }
    try {
      const sourceDirectory = await pickDirectory('read');
      const images = await new FileSystemManualSelectionSourceAdapter(
        sourceDirectory,
      ).listImages();
      if (images.length === 0)
        throw new Error('Bazowy katalog nie zawiera zdjęć JPG/JPEG.');
      setSourceImages(images);
      await updateLocalState({
        ...localState,
        gapCursor: 0,
        mode: 'fill',
        sourceCursor: 0,
        sourceDirectory,
      });
      setNotice(null);
    } catch (cause) {
      if (!isPickerCancelled(cause)) setError(errorMessage(cause));
    }
  }

  function moveSource(direction: -1 | 1): void {
    if (localState === null || sourceImages.length === 0) return;
    const next = clamp(
      sourceCursor + direction * localState.navigationStep,
      0,
      sourceImages.length - 1,
    );
    if (next !== sourceCursor)
      void updateLocalState({ ...localState, sourceCursor: next });
  }

  function changeStep(direction: -1 | 1): void {
    if (localState === null) return;
    const index = FILL_NAVIGATION_STEPS.indexOf(
      localState.navigationStep as (typeof FILL_NAVIGATION_STEPS)[number],
    );
    const nextIndex = clamp(
      (index < 0 ? 0 : index) + direction,
      0,
      FILL_NAVIGATION_STEPS.length - 1,
    );
    void updateLocalState({
      ...localState,
      navigationStep: FILL_NAVIGATION_STEPS[nextIndex]!,
    });
  }

  async function fillCurrentGap(): Promise<void> {
    if (
      snapshot === null ||
      localState === null ||
      currentGap === null ||
      currentSource === undefined ||
      !viewReady
    )
      return;
    await serialize(async () => {
      const manifest = await writeRepairFile({
        directory: snapshot.directory,
        kind: 'fill',
        manifest: snapshot.repairManifest,
        outputManifest: snapshot.outputManifest,
        source: currentSource.handle,
        sourceIndex: sourceCursor,
        sourcePath: currentSource.relativePath,
        target: currentGap,
      });
      await appendRepairTraceEvent(snapshot.directory, manifest.repairKey, {
        decoded: true,
        eventIndex: traceIndexRef.current++,
        imageChecksum:
          manifest.activeFiles.find(
            (file) =>
              file.start === currentGap.start && file.end === currentGap.end,
          )?.checksumSha256 ?? null,
        kind: 'fill',
        outputName: `seq_${currentGap.start}-${currentGap.end}.jpg`,
        rangeEnd: currentGap.end,
        rangeStart: currentGap.start,
        recordedAt: new Date().toISOString(),
        repairKey: manifest.repairKey,
        sourceIndex: sourceCursor,
        sourcePath: currentSource.relativePath,
        visibleMilliseconds: Math.max(
          300,
          Math.round(performance.now() - viewStartedAtRef.current),
        ),
      });
      const refreshed = await inspectRepairDirectory(snapshot.directory);
      setSnapshot(refreshed);
      await updateLocalState({
        ...localState,
        sourceCursor: clamp(sourceCursor + 1, 0, sourceImages.length - 1),
      });
    });
  }

  async function undoLastFill(): Promise<void> {
    if (snapshot === null || localState === null) return;
    const operations = snapshot.repairManifest.operations;
    const undone = new Set(
      operations
        .filter((operation) => operation.kind === 'undo_fill')
        .map((operation) => operation.fileName),
    );
    const fill = [...operations]
      .reverse()
      .find(
        (operation) =>
          operation.kind === 'fill' && !undone.has(operation.fileName),
      );
    if (fill === undefined) return;
    await serialize(async () => {
      const result = await deleteRepairFile({
        directory: snapshot.directory,
        fileName: fill.fileName,
        kind: 'undo_fill',
        manifest: snapshot.repairManifest,
        outputManifest: snapshot.outputManifest,
        sourceIndex: fill.sourceIndex,
        sourcePath: fill.sourcePath,
      });
      await appendRepairTraceEvent(
        snapshot.directory,
        result.manifest.repairKey,
        {
          decoded: true,
          eventIndex: traceIndexRef.current++,
          imageChecksum: fill.checksumSha256,
          kind: 'undo_fill',
          outputName: fill.fileName,
          rangeEnd: fill.rangeEnd,
          rangeStart: fill.rangeStart,
          recordedAt: new Date().toISOString(),
          repairKey: result.manifest.repairKey,
          sourceIndex: fill.sourceIndex,
          sourcePath: fill.sourcePath,
          visibleMilliseconds: 0,
        },
      );
      const refreshed = await inspectRepairDirectory(snapshot.directory);
      setSnapshot(refreshed);
      const nextGaps = findSequenceGaps(
        {
          end: refreshed.repairManifest.collectionEnd,
          start: refreshed.repairManifest.collectionStart,
        },
        refreshed.repairManifest.activeFiles,
        refreshed.repairManifest.deletedRanges,
      );
      await updateLocalState({
        ...localState,
        gapCursor: Math.max(
          0,
          nextGaps.findIndex((gap) =>
            sameRange(gap, { end: fill.rangeEnd, start: fill.rangeStart }),
          ),
        ),
        sourceCursor: fill.sourceIndex ?? localState.sourceCursor,
      });
    });
  }

  async function updateLocalState(
    next: ManualSelectionRepairLocalState,
  ): Promise<void> {
    const updated = { ...next, updatedAt: new Date().toISOString() };
    setLocalState(updated);
    await store.save(updated);
  }

  async function serialize(operation: () => Promise<void>): Promise<void> {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError(null);
    const queued = operationQueueRef.current
      .catch(() => undefined)
      .then(operation);
    operationQueueRef.current = queued;
    try {
      await queued;
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }

  if (mode === 'fill' && snapshot !== null && localState !== null) {
    return (
      <section
        className="manualImageSelectionWorkspace manualImageSelectionActive"
        aria-labelledby="repair-fill-title"
      >
        <header className="manualImageSelectionHeader">
          <div>
            <p className="eyebrow">Niezależnie od gry · lokalnie</p>
            <h2 id="repair-fill-title">Uzupełnij luki</h2>
            <p>
              {currentGap === null
                ? 'Wszystkie luki zostały uzupełnione.'
                : `Luka ${gapCursor + 1} z ${gaps.length} · zakres ${currentGap.start}–${currentGap.end}`}
            </p>
          </div>
        </header>
        <ManualImageViewer
          busy={busy}
          currentLabel={
            currentGap === null
              ? 'Brak luk'
              : `Luka ${currentGap.start}–${currentGap.end}`
          }
          currentPosition={sourceCursor + 1}
          currentRelativePath={currentSource?.relativePath ?? null}
          imageCount={sourceImages.length}
          navigationStepLabel={`skok zdjęcia: ${localState.navigationStep}`}
          nextDisabled={sourceCursor >= sourceImages.length - 1}
          onNext={() => moveSource(1)}
          onPrevious={() => moveSource(-1)}
          previousDisabled={sourceCursor <= 0}
          state={viewer}
          toolbarStart={
            <label className="manualImageSelectionStep">
              Skok zdjęcia
              <select
                disabled={busy}
                onChange={(event) =>
                  void updateLocalState({
                    ...localState,
                    navigationStep: Number(event.target.value),
                  })
                }
                value={localState.navigationStep}
              >
                {FILL_NAVIGATION_STEPS.map((step) => (
                  <option key={step} value={step}>
                    co {step}
                  </option>
                ))}
              </select>
            </label>
          }
        />
        <div className="manualImageSelectionActions">
          <button
            className="secondaryButton"
            disabled={busy || gapCursor <= 0}
            onClick={() =>
              void updateLocalState({ ...localState, gapCursor: gapCursor - 1 })
            }
            type="button"
          >
            Poprzednia luka
          </button>
          <button
            className="secondaryButton"
            disabled={busy || gapCursor >= gaps.length - 1}
            onClick={() =>
              void updateLocalState({ ...localState, gapCursor: gapCursor + 1 })
            }
            type="button"
          >
            Następna luka
          </button>
          <button
            className="secondaryButton"
            disabled={busy}
            onClick={() => void undoLastFill()}
            type="button"
          >
            Cofnij uzupełnienie A / Ctrl+Z
          </button>
          <button
            className="primaryButton"
            disabled={
              busy ||
              !viewReady ||
              currentGap === null ||
              currentSource === undefined
            }
            onClick={() => void fillCurrentGap()}
            type="button"
          >
            Uzupełnij lukę Enter/F
          </button>
        </div>
        {error !== null ? (
          <p className="formError" role="alert">
            {error}
          </p>
        ) : null}
        <p className="manualImageSelectionHelp">
          ←/→ zdjęcie · ↑/↓ zmienia skok · Enter/F uzupełnia · A/Ctrl+A/Ctrl+Z
          cofa
        </p>
      </section>
    );
  }

  return (
    <section
      className="manualImageSelectionWorkspace manualSelectionRepairSetup"
      aria-labelledby="manual-selection-repair-title"
    >
      <header className="manualImageSelectionHeader">
        <div>
          <p className="eyebrow">Niezależnie od gry · lokalnie</p>
          <h2 id="manual-selection-repair-title">Popraw selekcję</h2>
          <p>
            Uzupełnij luki albo usuń błędnie wybrane sekwencje bez wysyłania
            zdjęć.
          </p>
        </div>
      </header>
      <div className="manualImageSelectionSetup">
        <button
          className="secondaryButton"
          disabled={busy}
          onClick={() => void chooseSelectedDirectory()}
          type="button"
        >
          Wybierz katalog z plikami seq_*
        </button>
        {snapshot !== null ? (
          <p className="manualImageSelectionReady">
            {snapshot.directory.name} ·{' '}
            {snapshot.files.length.toLocaleString('pl-PL')} plików ·{' '}
            {gaps.length.toLocaleString('pl-PL')} luk
          </p>
        ) : null}
        <div className="manualImageSelectionFolderActions">
          <button
            className="primaryButton"
            disabled={busy || snapshot === null}
            onClick={() => void startFill()}
            type="button"
          >
            Uzupełnij luki
          </button>
          <button className="secondaryButton" disabled type="button">
            Usuń sekwencje
          </button>
        </div>
        {notice !== null ? (
          <p className="manualImageSelectionStatus">{notice}</p>
        ) : null}
        {error !== null ? (
          <p className="formError" role="alert">
            {error}
          </p>
        ) : null}
      </div>
    </section>
  );
}

async function pickDirectory(mode: 'read' | 'readwrite') {
  const picker = (window as DirectoryPickerWindow).showDirectoryPicker;
  if (picker === undefined)
    throw new Error('Ta przeglądarka nie obsługuje wyboru folderu lokalnego.');
  return picker({ mode });
}

async function hasPermission(
  directory: FileSystemDirectoryHandle,
  mode: 'read' | 'readwrite',
): Promise<boolean> {
  const handle = directory as FileSystemDirectoryHandle & {
    queryPermission?: (descriptor: {
      mode: 'read' | 'readwrite';
    }) => Promise<PermissionState>;
  };
  return (
    handle.queryPermission === undefined ||
    (await handle.queryPermission({ mode })) === 'granted'
  );
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}

function sameRange(left: SequenceRange, right: SequenceRange): boolean {
  return left.start === right.start && left.end === right.end;
}

function isEditable(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable ||
      ['INPUT', 'SELECT', 'TEXTAREA'].includes(target.tagName))
  );
}

function isPickerCancelled(cause: unknown): boolean {
  return cause instanceof DOMException && cause.name === 'AbortError';
}

function errorMessage(cause: unknown): string {
  return cause instanceof Error
    ? cause.message
    : 'Nie udało się poprawić selekcji.';
}
