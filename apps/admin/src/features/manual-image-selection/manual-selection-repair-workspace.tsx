'use client';

import {
  findSequenceGaps,
  type SequenceRange,
} from '@game-predictor/manual-image-selection-core/repair';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import {
  isLocalDirectoryPickerActive,
  pickLocalDirectory,
  subscribeLocalDirectoryPickerActive,
} from '../../lib/local-directory-picker.ts';

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

type RepairWorkspacePhase =
  | 'idle'
  | 'restoring'
  | 'selecting_selected'
  | 'inspecting_selected'
  | 'selecting_source'
  | 'listing_source';

export function ManualSelectionRepairWorkspace() {
  const store = useMemo(() => new ManualSelectionRepairStore(), []);
  const operationQueueRef = useRef<Promise<void>>(Promise.resolve());
  const busyRef = useRef(false);
  const traceIndexRef = useRef(0);
  const viewStartedAtRef = useRef(0);
  const recoveryGenerationRef = useRef(0);
  const deleteUndoRef = useRef<{
    readonly file: File;
    readonly fileName: string;
    readonly range: SequenceRange;
    readonly sourceIndex: number | null;
    readonly sourcePath: string | null;
  } | null>(null);
  const [snapshot, setSnapshot] = useState<RepairDirectorySnapshot | null>(
    null,
  );
  const [sourceImages, setSourceImages] = useState<ManualImageFile[]>([]);
  const [localState, setLocalState] =
    useState<ManualSelectionRepairLocalState | null>(null);
  const [busy, setBusy] = useState(false);
  const [directoryPickerActive, setDirectoryPickerActive] = useState(
    isLocalDirectoryPickerActive,
  );
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [viewReady, setViewReady] = useState(false);
  const [deleteUndoAvailable, setDeleteUndoAvailable] = useState(false);
  const [workPhase, setWorkPhase] = useState<RepairWorkspacePhase>('idle');
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
  const selectedImages = useMemo(
    () =>
      snapshot?.files.map((file) => ({
        handle: file.handle,
        name: file.fileName,
        relativePath: file.fileName,
      })) ?? [],
    [snapshot],
  );
  const deleteCursor = Math.min(
    localState?.fileCursor ?? 0,
    Math.max(0, selectedImages.length - 1),
  );
  const currentSelected = snapshot?.files[deleteCursor];
  const workPhaseMessage = repairWorkspacePhaseMessage(workPhase);
  const interactiveWorkInProgress =
    workPhase !== 'idle' && workPhase !== 'restoring';
  const handleViewerError = useCallback(
    (message: string) => setError(message),
    [],
  );
  const viewer = useManualImageViewer(
    mode === 'fill' ? sourceImages : mode === 'delete' ? selectedImages : [],
    mode === 'fill' ? sourceCursor : mode === 'delete' ? deleteCursor : -1,
    handleViewerError,
  );

  useEffect(() => {
    return subscribeLocalDirectoryPickerActive(() => {
      setDirectoryPickerActive(isLocalDirectoryPickerActive());
    });
  }, []);

  useEffect(() => {
    let cancelled = false;
    const recoveryGeneration = ++recoveryGenerationRef.current;
    void (async () => {
      const saved = await store.loadLatest();
      if (
        cancelled ||
        recoveryGeneration !== recoveryGenerationRef.current ||
        saved === null
      )
        return;
      setWorkPhase('restoring');
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
        if (
          !cancelled &&
          recoveryGeneration === recoveryGenerationRef.current
        ) {
          setSnapshot(restored);
          setSourceImages(sources);
          setLocalState({
            ...saved,
            mode:
              saved.mode === 'fill' && sources.length === 0 ? null : saved.mode,
          });
        }
      } catch {
        if (
          !cancelled &&
          recoveryGeneration === recoveryGenerationRef.current
        ) {
          setNotice(
            'Nie udało się przywrócić poprzedniego katalogu. Wskaż go ponownie.',
          );
        }
      }
    })().finally(() => {
      if (!cancelled && recoveryGeneration === recoveryGenerationRef.current) {
        setWorkPhase('idle');
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
    if (mode === null) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (
        busyRef.current ||
        interactiveWorkInProgress ||
        isEditable(event.target)
      )
        return;
      const key = event.key.toLowerCase();
      if (key === 'arrowleft' || key === 'arrowright') {
        event.preventDefault();
        if (mode === 'fill') moveSource(key === 'arrowleft' ? -1 : 1);
        else moveSelected(key === 'arrowleft' ? -1 : 1);
      } else if (
        mode === 'fill' &&
        (key === 'arrowup' || key === 'arrowdown')
      ) {
        event.preventDefault();
        changeStep(key === 'arrowup' ? -1 : 1);
      } else if (
        mode === 'fill' &&
        (key === 'enter' || key === 'f') &&
        !event.repeat
      ) {
        event.preventDefault();
        void fillCurrentGap();
      } else if (mode === 'delete' && key === 'f' && !event.repeat) {
        event.preventDefault();
        void deleteCurrentSequence();
      } else if (
        !event.repeat &&
        (key === 'a' ||
          (mode === 'fill' && key === 'z' && (event.ctrlKey || event.metaKey)))
      ) {
        event.preventDefault();
        if (mode === 'fill') void undoLastFill();
        else void restoreLastSequence();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  });

  async function chooseSelectedDirectory(): Promise<void> {
    const recoveryGeneration = beginWorkPhase('selecting_selected');
    setError(null);
    try {
      const directory = await pickDirectory('readwrite');
      if (recoveryGeneration !== recoveryGenerationRef.current) return;
      setWorkPhase('inspecting_selected');
      const inspected = await inspectRepairDirectory(directory);
      if (recoveryGeneration !== recoveryGenerationRef.current) return;
      await writeRepairManifest(directory, inspected.repairManifest);
      const saved = await store.load(inspected.repairManifest.repairKey);
      if (recoveryGeneration !== recoveryGenerationRef.current) return;
      const reboundState: ManualSelectionRepairLocalState = {
        ...(saved ?? createInitialLocalState(inspected, directory)),
        mode: null,
        selectedDirectory: directory,
        updatedAt: new Date().toISOString(),
      };
      await store.save(reboundState);
      if (recoveryGeneration !== recoveryGenerationRef.current) return;
      setSnapshot(inspected);
      setSourceImages([]);
      setLocalState(reboundState);
      setNotice(
        `${inspected.files.length.toLocaleString('pl-PL')} plików · zakres ${inspected.repairManifest.collectionStart}–${inspected.repairManifest.collectionEnd}.`,
      );
    } catch (cause) {
      if (!isPickerCancelled(cause)) setError(errorMessage(cause));
    } finally {
      finishWorkPhase(recoveryGeneration);
    }
  }

  async function startFill(): Promise<void> {
    if (snapshot === null || localState === null) return;
    if (gaps.length === 0) {
      setNotice('Katalog nie zawiera luk do uzupełnienia.');
      return;
    }
    const recoveryGeneration = beginWorkPhase('selecting_source');
    setError(null);
    try {
      const sourceDirectory = await pickDirectory('read');
      if (recoveryGeneration !== recoveryGenerationRef.current) return;
      setWorkPhase('listing_source');
      const images = await new FileSystemManualSelectionSourceAdapter(
        sourceDirectory,
      ).listImages();
      if (recoveryGeneration !== recoveryGenerationRef.current) return;
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
    } finally {
      finishWorkPhase(recoveryGeneration);
    }
  }

  async function startDelete(): Promise<void> {
    if (snapshot === null || localState === null || interactiveWorkInProgress)
      return;
    deleteUndoRef.current = null;
    setDeleteUndoAvailable(false);
    setSourceImages([]);
    await updateLocalState({
      ...localState,
      fileCursor: clamp(
        localState.fileCursor,
        0,
        Math.max(0, snapshot.files.length - 1),
      ),
      mode: 'delete',
    });
    setNotice(null);
  }

  async function returnToModeSelection(): Promise<void> {
    if (localState === null || busyRef.current || interactiveWorkInProgress)
      return;
    deleteUndoRef.current = null;
    setDeleteUndoAvailable(false);
    await updateLocalState({ ...localState, mode: null });
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

  function moveSelected(direction: -1 | 1): void {
    if (localState === null || selectedImages.length === 0) return;
    const next = clamp(deleteCursor + direction, 0, selectedImages.length - 1);
    if (next !== deleteCursor)
      void updateLocalState({ ...localState, fileCursor: next });
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
      const result = await writeRepairFile({
        directory: snapshot.directory,
        kind: 'fill',
        manifest: snapshot.repairManifest,
        outputManifest: snapshot.outputManifest,
        source: currentSource.handle,
        sourceIndex: sourceCursor,
        sourcePath: currentSource.relativePath,
        target: currentGap,
      });
      const manifest = result.manifest;
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
      setSnapshot(
        addSnapshotFile(
          snapshot,
          {
            end: currentGap.end,
            fileName: `seq_${currentGap.start}-${currentGap.end}.jpg`,
            handle: result.fileHandle,
            start: currentGap.start,
          },
          result.manifest,
          result.outputManifest,
        ),
      );
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
      const refreshed = removeSnapshotFile(
        snapshot,
        fill.fileName,
        result.manifest,
        result.outputManifest,
      );
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

  async function deleteCurrentSequence(): Promise<void> {
    if (
      snapshot === null ||
      localState === null ||
      currentSelected === undefined
    )
      return;
    await serialize(async () => {
      const outputItem = snapshot.outputManifest?.items.find(
        (item) => item.outputName === currentSelected.fileName,
      );
      const priorOperation = [...snapshot.repairManifest.operations]
        .reverse()
        .find((operation) => operation.fileName === currentSelected.fileName);
      const result = await deleteRepairFile({
        directory: snapshot.directory,
        fileName: currentSelected.fileName,
        kind: 'delete',
        manifest: snapshot.repairManifest,
        outputManifest: snapshot.outputManifest,
        sourceIndex: priorOperation?.sourceIndex ?? null,
        sourcePath: priorOperation?.sourcePath ?? outputItem?.imagePath ?? null,
      });
      deleteUndoRef.current = {
        file: result.file,
        fileName: currentSelected.fileName,
        range: { end: currentSelected.end, start: currentSelected.start },
        sourceIndex: priorOperation?.sourceIndex ?? null,
        sourcePath: priorOperation?.sourcePath ?? outputItem?.imagePath ?? null,
      };
      setDeleteUndoAvailable(true);
      await appendRepairTraceEvent(
        snapshot.directory,
        result.manifest.repairKey,
        {
          decoded: true,
          eventIndex: traceIndexRef.current++,
          imageChecksum:
            result.manifest.operations[result.manifest.operations.length - 1]
              ?.checksumSha256 ?? null,
          kind: 'delete',
          outputName: currentSelected.fileName,
          rangeEnd: currentSelected.end,
          rangeStart: currentSelected.start,
          recordedAt: new Date().toISOString(),
          repairKey: result.manifest.repairKey,
          sourceIndex: deleteUndoRef.current.sourceIndex,
          sourcePath: deleteUndoRef.current.sourcePath,
          visibleMilliseconds: 0,
        },
      );
      const refreshed = removeSnapshotFile(
        snapshot,
        currentSelected.fileName,
        result.manifest,
        result.outputManifest,
      );
      setSnapshot(refreshed);
      await updateLocalState({
        ...localState,
        fileCursor: clamp(
          deleteCursor,
          0,
          Math.max(0, refreshed.files.length - 1),
        ),
      });
    });
  }

  async function restoreLastSequence(): Promise<void> {
    if (snapshot === null || localState === null) return;
    const undo = deleteUndoRef.current;
    if (undo === null) return;
    await serialize(async () => {
      const sourceHandle = {
        getFile: async () => undo.file,
        kind: 'file',
        name: undo.file.name,
      } as FileSystemFileHandle;
      const result = await writeRepairFile({
        directory: snapshot.directory,
        kind: 'restore',
        manifest: snapshot.repairManifest,
        outputManifest: snapshot.outputManifest,
        source: sourceHandle,
        sourceIndex: undo.sourceIndex,
        sourcePath: undo.sourcePath ?? undo.fileName,
        target: undo.range,
      });
      const manifest = result.manifest;
      await appendRepairTraceEvent(snapshot.directory, manifest.repairKey, {
        decoded: true,
        eventIndex: traceIndexRef.current++,
        imageChecksum:
          manifest.activeFiles.find((file) => file.fileName === undo.fileName)
            ?.checksumSha256 ?? null,
        kind: 'restore',
        outputName: undo.fileName,
        rangeEnd: undo.range.end,
        rangeStart: undo.range.start,
        recordedAt: new Date().toISOString(),
        repairKey: manifest.repairKey,
        sourceIndex: undo.sourceIndex,
        sourcePath: undo.sourcePath,
        visibleMilliseconds: 0,
      });
      deleteUndoRef.current = null;
      setDeleteUndoAvailable(false);
      const refreshed = addSnapshotFile(
        snapshot,
        {
          end: undo.range.end,
          fileName: undo.fileName,
          handle: result.fileHandle,
          start: undo.range.start,
        },
        result.manifest,
        result.outputManifest,
      );
      setSnapshot(refreshed);
      await updateLocalState({
        ...localState,
        fileCursor: Math.max(
          0,
          refreshed.files.findIndex((file) => file.fileName === undo.fileName),
        ),
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

  function beginWorkPhase(
    phase: Exclude<RepairWorkspacePhase, 'idle'>,
  ): number {
    const generation = ++recoveryGenerationRef.current;
    setWorkPhase(phase);
    return generation;
  }

  function finishWorkPhase(generation: number): void {
    if (generation === recoveryGenerationRef.current) setWorkPhase('idle');
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
          busy={busy || interactiveWorkInProgress}
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
                disabled={busy || interactiveWorkInProgress}
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
            disabled={busy || interactiveWorkInProgress}
            onClick={() => void returnToModeSelection()}
            type="button"
          >
            Wróć do wyboru trybu
          </button>
          <button
            className="secondaryButton"
            disabled={busy || interactiveWorkInProgress || gapCursor <= 0}
            onClick={() =>
              void updateLocalState({ ...localState, gapCursor: gapCursor - 1 })
            }
            type="button"
          >
            Poprzednia luka
          </button>
          <button
            className="secondaryButton"
            disabled={
              busy || interactiveWorkInProgress || gapCursor >= gaps.length - 1
            }
            onClick={() =>
              void updateLocalState({ ...localState, gapCursor: gapCursor + 1 })
            }
            type="button"
          >
            Następna luka
          </button>
          <button
            className="secondaryButton"
            disabled={busy || interactiveWorkInProgress}
            onClick={() => void undoLastFill()}
            type="button"
          >
            Cofnij uzupełnienie A / Ctrl+Z
          </button>
          <button
            className="primaryButton"
            disabled={
              busy ||
              interactiveWorkInProgress ||
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

  if (mode === 'delete' && snapshot !== null && localState !== null) {
    return (
      <section
        className="manualImageSelectionWorkspace manualImageSelectionActive"
        aria-labelledby="repair-delete-title"
      >
        <header className="manualImageSelectionHeader">
          <div>
            <p className="eyebrow">Niezależnie od gry · lokalnie</p>
            <h2 id="repair-delete-title">Usuń sekwencje</h2>
            <p>
              {currentSelected === undefined
                ? 'Katalog nie zawiera już plików seq_*.'
                : `${currentSelected.start}–${currentSelected.end} · ${deleteCursor + 1} z ${selectedImages.length}`}
            </p>
          </div>
        </header>
        <p className="manualSelectionRepairWarning" role="status">
          Przywrócić można wyłącznie ostatnio usunięty plik. Możliwość
          przywrócenia znika po zamknięciu lub odświeżeniu karty, a kolejne
          usunięcie zastępuje poprzednią kopię w pamięci.
        </p>
        <ManualImageViewer
          busy={busy || interactiveWorkInProgress}
          currentLabel={
            currentSelected === undefined
              ? 'Brak sekwencji'
              : `Zakres ${currentSelected.start}–${currentSelected.end}`
          }
          currentPosition={selectedImages.length === 0 ? 0 : deleteCursor + 1}
          currentRelativePath={currentSelected?.fileName ?? null}
          imageCount={selectedImages.length}
          navigationStepLabel="skok: 1"
          nextDisabled={deleteCursor >= selectedImages.length - 1}
          onNext={() => moveSelected(1)}
          onPrevious={() => moveSelected(-1)}
          previousDisabled={deleteCursor <= 0}
          state={viewer}
          toolbarStart={
            <span className="manualImageSelectionStep">skok: 1</span>
          }
        />
        <div className="manualImageSelectionActions">
          <button
            className="secondaryButton"
            disabled={busy || interactiveWorkInProgress}
            onClick={() => void returnToModeSelection()}
            type="button"
          >
            Wróć do wyboru trybu
          </button>
          <button
            className="secondaryButton"
            disabled={busy || interactiveWorkInProgress || !deleteUndoAvailable}
            onClick={() => void restoreLastSequence()}
            type="button"
          >
            Przywróć ostatnie A / Ctrl+A
          </button>
          <button
            className="dangerButton"
            disabled={
              busy || interactiveWorkInProgress || currentSelected === undefined
            }
            onClick={() => void deleteCurrentSequence()}
            type="button"
          >
            Usuń sekwencję F
          </button>
        </div>
        {error !== null ? (
          <p className="formError" role="alert">
            {error}
          </p>
        ) : null}
        <p className="manualImageSelectionHelp">
          ←/→ przechodzi o jeden plik · F usuwa · A/Ctrl+A przywraca ostatni
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
          disabled={busy || directoryPickerActive || interactiveWorkInProgress}
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
            disabled={
              busy ||
              directoryPickerActive ||
              interactiveWorkInProgress ||
              snapshot === null
            }
            onClick={() => void startFill()}
            type="button"
          >
            Uzupełnij luki
          </button>
          <button
            className="secondaryButton"
            disabled={busy || interactiveWorkInProgress || snapshot === null}
            onClick={() => void startDelete()}
            type="button"
          >
            Usuń sekwencje
          </button>
        </div>
        {notice !== null ? (
          <p className="manualImageSelectionStatus">{notice}</p>
        ) : null}
        {workPhaseMessage !== null ? (
          <p className="manualImageSelectionStatus" role="status">
            {workPhaseMessage}
          </p>
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
  return pickLocalDirectory({ id: 'gp-manual-repair', mode });
}

function createInitialLocalState(
  snapshot: RepairDirectorySnapshot,
  directory: FileSystemDirectoryHandle,
): ManualSelectionRepairLocalState {
  return {
    fileCursor: 0,
    gapCursor: 0,
    mode: null,
    navigationStep: 1,
    repairKey: snapshot.repairManifest.repairKey,
    scrollTop: 0,
    selectedDirectory: directory,
    sourceCursor: 0,
    sourceDirectory: null,
    updatedAt: new Date().toISOString(),
    zoom: 1,
  };
}

function repairWorkspacePhaseMessage(
  phase: RepairWorkspacePhase,
): string | null {
  switch (phase) {
    case 'restoring':
      return 'Przywracam poprzednią sesję i sprawdzam zapisane pliki…';
    case 'selecting_selected':
      return 'Wybierz katalog z plikami seq_* w otwartym oknie systemowym.';
    case 'inspecting_selected':
      return 'Sprawdzam nazwy i checksumy wybranego katalogu…';
    case 'selecting_source':
      return 'Wybierz bazowy katalog zdjęć w otwartym oknie systemowym.';
    case 'listing_source':
      return 'Wczytuję listę zdjęć z katalogu bazowego…';
    case 'idle':
      return null;
  }
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

function addSnapshotFile(
  snapshot: RepairDirectorySnapshot,
  file: RepairDirectorySnapshot['files'][number],
  repairManifest: RepairDirectorySnapshot['repairManifest'],
  outputManifest: RepairDirectorySnapshot['outputManifest'],
): RepairDirectorySnapshot {
  return {
    ...snapshot,
    files: [...snapshot.files, file].sort(
      (left, right) =>
        left.start - right.start ||
        left.end - right.end ||
        left.fileName.localeCompare(right.fileName),
    ),
    outputManifest,
    repairManifest,
  };
}

function removeSnapshotFile(
  snapshot: RepairDirectorySnapshot,
  fileName: string,
  repairManifest: RepairDirectorySnapshot['repairManifest'],
  outputManifest: RepairDirectorySnapshot['outputManifest'],
): RepairDirectorySnapshot {
  return {
    ...snapshot,
    files: snapshot.files.filter((file) => file.fileName !== fileName),
    outputManifest,
    repairManifest,
  };
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
  if (
    cause instanceof Error &&
    cause.message.startsWith('MANUAL_OUTPUT_MANIFEST_CHECKSUM_MISMATCH:')
  ) {
    const fileName = cause.message.slice(
      'MANUAL_OUTPUT_MANIFEST_CHECKSUM_MISMATCH:'.length,
    );
    return `Plik ${fileName} ma inną zawartość niż zapisana w manifeście pierwotnej selekcji. Narzędzie nie przejmie zmienionego pliku bez jawnego potwierdzenia nowej checksummy.`;
  }
  return cause instanceof Error
    ? cause.message
    : 'Nie udało się poprawić selekcji.';
}
