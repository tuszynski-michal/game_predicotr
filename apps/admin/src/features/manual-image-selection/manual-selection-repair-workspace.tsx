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
  type ManualImageListingProgress,
} from './manual-image-selection-fsa-adapter.ts';
import { ManualImageViewer, useManualImageViewer } from './manual-image-viewer';
import {
  deleteRepairFile,
  inspectRepairDirectory,
  ManualSelectionRepairStore,
  writeRepairFile,
  writeRepairManifest,
  type ManualSelectionRepairLocalState,
  type RepairDirectorySnapshot,
} from './manual-selection-repair-storage.ts';

const FILL_NAVIGATION_STEPS = [1, 2, 5, 10, 20, 50, 100] as const;
const MAXIMUM_FILL_UNDOS = 2;
const MAXIMUM_QUEUED_SINGLE_REPAIRS = 10;

type RepairWorkspacePhase =
  | 'idle'
  | 'restoring'
  | 'selecting_selected'
  | 'inspecting_selected'
  | 'selecting_source'
  | 'listing_source';

type BulkDeleteResult = {
  readonly error: string | null;
  readonly fileName: string;
};

type QueuedSingleRepair =
  | {
      readonly kind: 'fill';
      readonly localStateAfter: ManualSelectionRepairLocalState;
      readonly source: ManualImageFile;
      readonly sourceIndex: number;
      readonly target: SequenceRange;
    }
  | {
      readonly fileName: string;
      readonly kind: 'delete';
      readonly localStateAfter: ManualSelectionRepairLocalState;
      readonly sourceIndex: number | null;
      readonly sourcePath: string | null;
    };

export function ManualSelectionRepairWorkspace() {
  const store = useMemo(() => new ManualSelectionRepairStore(), []);
  const operationQueueRef = useRef<Promise<void>>(Promise.resolve());
  const localStateSaveQueueRef = useRef<Promise<void>>(Promise.resolve());
  const snapshotRef = useRef<RepairDirectorySnapshot | null>(null);
  const durableSnapshotRef = useRef<RepairDirectorySnapshot | null>(null);
  const singleRepairQueueRef = useRef<QueuedSingleRepair[]>([]);
  const singleRepairWriterActiveRef = useRef(false);
  const pendingSingleRepairCountRef = useRef(0);
  const busyRef = useRef(false);
  const backgroundDeletePendingRef = useRef(false);
  const backgroundFillPendingRef = useRef(false);
  const localStateRef = useRef<ManualSelectionRepairLocalState | null>(null);
  const viewStartedAtRef = useRef(0);
  const recoveryGenerationRef = useRef(0);
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
  const viewReadyRef = useRef(false);
  const [backgroundDeletePending, setBackgroundDeletePending] = useState(false);
  const [backgroundDeleteBlocked, setBackgroundDeleteBlocked] = useState(false);
  const [backgroundFillPending, setBackgroundFillPending] = useState(false);
  const [backgroundFillBlocked, setBackgroundFillBlocked] = useState(false);
  const [pendingSingleRepairCount, setPendingSingleRepairCount] = useState(0);
  const [undoFillOperationIds, setUndoFillOperationIds] = useState<
    readonly string[]
  >([]);
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false);
  const [bulkDeleteQuery, setBulkDeleteQuery] = useState('');
  const [bulkDeleteFileNames, setBulkDeleteFileNames] = useState<
    readonly string[]
  >([]);
  const [bulkDeleteConfirmed, setBulkDeleteConfirmed] = useState(false);
  const [bulkDeleteResults, setBulkDeleteResults] = useState<
    readonly BulkDeleteResult[]
  >([]);
  const [bulkDeleteRunning, setBulkDeleteRunning] = useState(false);
  const [workPhase, setWorkPhase] = useState<RepairWorkspacePhase>('idle');
  const [sourceListingProgress, setSourceListingProgress] =
    useState<ManualImageListingProgress | null>(null);
  const [sourceListingDirectoryName, setSourceListingDirectoryName] = useState<
    string | null
  >(null);
  const sourceCursor = localState?.sourceCursor ?? 0;
  const mode = localState?.mode ?? null;
  const backgroundMutationPending =
    backgroundDeletePending || backgroundFillPending;
  const backgroundMutationBlocked =
    backgroundDeleteBlocked || backgroundFillBlocked;
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
  const bulkDeleteCandidates = useMemo(() => {
    const prefix = bulkDeleteQuery.trim();
    if (prefix === '' || snapshot === null) return [];
    return snapshot.files
      .filter(
        (file) =>
          String(file.start).startsWith(prefix) &&
          !bulkDeleteFileNames.includes(file.fileName),
      )
      .slice(0, 50);
  }, [bulkDeleteFileNames, bulkDeleteQuery, snapshot]);
  const bulkDeleteFiles = useMemo(
    () =>
      snapshot?.files.filter((file) =>
        bulkDeleteFileNames.includes(file.fileName),
      ) ?? [],
    [bulkDeleteFileNames, snapshot],
  );
  const workPhaseMessage = repairWorkspacePhaseMessage(
    workPhase,
    sourceListingProgress,
    sourceListingDirectoryName,
  );
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
    undefined,
    undefined,
    snapshot === null
      ? undefined
      : `${snapshot.repairManifest.repairKey}:${mode}`,
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
          ).listImages(undefined, { includeSubdirectories: false });
        }
        if (
          !cancelled &&
          recoveryGeneration === recoveryGenerationRef.current
        ) {
          replaceSnapshot(restored, true);
          setSourceImages(sources);
          setUndoFillOperationIds(recentFillOperationIds(restored));
          const restoredState = {
            ...saved,
            mode:
              saved.mode === 'fill' && sources.length === 0 ? null : saved.mode,
            sourceCursor:
              saved.mode === 'fill' && sources.length > 0
                ? clamp(saved.sourceCursor, 0, sources.length - 1)
                : saved.sourceCursor,
          };
          localStateRef.current = restoredState;
          setLocalState(restoredState);
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
    queueMicrotask(() => setRepairViewReady(false));
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
      setRepairViewReady(true);
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
        mode === 'fill' &&
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
      replaceSnapshot(inspected, true);
      setSourceImages([]);
      localStateRef.current = reboundState;
      setLocalState(reboundState);
      setBackgroundDeleteBlocked(false);
      setBackgroundFillBlocked(false);
      setUndoFillOperationIds([]);
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
    if (
      snapshot === null ||
      localState === null ||
      backgroundMutationPending ||
      backgroundMutationBlocked
    )
      return;
    if (gaps.length === 0) {
      setNotice('Katalog nie zawiera luk do uzupełnienia.');
      return;
    }
    const recoveryGeneration = beginWorkPhase('selecting_source');
    setError(null);
    try {
      const sourceDirectory = await pickDirectory(
        'read',
        'gp-manual-repair-source',
      );
      if (recoveryGeneration !== recoveryGenerationRef.current) return;
      setSourceListingDirectoryName(sourceDirectory.name);
      setWorkPhase('listing_source');
      setSourceListingProgress({ imageCount: 0, visitedEntries: 0 });
      const images = await new FileSystemManualSelectionSourceAdapter(
        sourceDirectory,
      ).listImages(
        (progress) => {
          if (recoveryGeneration !== recoveryGenerationRef.current) return;
          setSourceListingProgress(progress);
        },
        { includeSubdirectories: false },
      );
      if (recoveryGeneration !== recoveryGenerationRef.current) return;
      if (images.length === 0)
        throw new Error(
          `Wybrany katalog „${sourceDirectory.name}” nie zawiera bezpośrednio zdjęć JPG/JPEG. Wskaż folder z właściwymi zdjęciami, nie katalog nadrzędny.`,
        );
      setSourceImages(images);
      const nextLocalState = applyLocalState({
        ...localState,
        gapCursor: 0,
        mode: 'fill',
        sourceCursor: 0,
        sourceDirectory,
      });
      void persistLocalState(nextLocalState).catch(() => {
        if (recoveryGeneration !== recoveryGenerationRef.current) return;
        setNotice(
          'Katalog bazowy jest gotowy, ale jego uchwyt nie zapisał się lokalnie. Po restarcie wskaż go ponownie.',
        );
      });
      setUndoFillOperationIds(recentFillOperationIds(snapshot));
      setNotice(null);
    } catch (cause) {
      if (!isPickerCancelled(cause)) setError(errorMessage(cause));
    } finally {
      if (recoveryGeneration === recoveryGenerationRef.current)
        setSourceListingProgress(null);
      finishWorkPhase(recoveryGeneration);
    }
  }

  async function startDelete(): Promise<void> {
    if (
      snapshot === null ||
      localState === null ||
      interactiveWorkInProgress ||
      backgroundMutationPending ||
      backgroundMutationBlocked
    )
      return;
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

  function openBulkDelete(): void {
    if (
      snapshot === null ||
      busy ||
      interactiveWorkInProgress ||
      backgroundMutationPending ||
      backgroundMutationBlocked
    )
      return;
    setBulkDeleteOpen(true);
    setBulkDeleteQuery('');
    setBulkDeleteFileNames([]);
    setBulkDeleteConfirmed(false);
    setBulkDeleteResults([]);
  }

  function addBulkDeleteFile(fileName: string): void {
    setBulkDeleteFileNames((current) =>
      current.includes(fileName) ? current : [...current, fileName],
    );
    setBulkDeleteQuery('');
  }

  async function deleteSelectedSequences(): Promise<void> {
    if (
      snapshot === null ||
      localState === null ||
      !bulkDeleteConfirmed ||
      bulkDeleteFiles.length === 0 ||
      bulkDeleteRunning ||
      backgroundMutationPending ||
      backgroundMutationBlocked
    )
      return;
    setBulkDeleteRunning(true);
    setBulkDeleteResults([]);
    try {
      await serialize(async () => {
        let currentSnapshot = snapshot;
        let currentLocalState = localState;
        for (const selectedFile of bulkDeleteFiles) {
          let result;
          let outputItem;
          let filledGap;
          try {
            outputItem = currentSnapshot.outputManifest?.items.find(
              (item) => item.outputName === selectedFile.fileName,
            );
            filledGap = currentSnapshot.repairManifest.filledGapEntries.find(
              (entry) => entry.fileName === selectedFile.fileName,
            );
            result = await deleteRepairFile({
              directory: currentSnapshot.directory,
              fileName: selectedFile.fileName,
              kind: 'delete',
              manifest: currentSnapshot.repairManifest,
              outputManifest: currentSnapshot.outputManifest,
              sourceIndex: filledGap?.sourceIndex ?? null,
              sourcePath:
                filledGap?.sourcePath ?? outputItem?.imagePath ?? null,
            });
          } catch (cause) {
            setBulkDeleteResults((current) => [
              ...current,
              { error: errorMessage(cause), fileName: selectedFile.fileName },
            ]);
            if (isCriticalBulkDeleteFailure(cause)) throw cause;
            continue;
          }

          try {
            currentSnapshot = removeSnapshotFile(
              currentSnapshot,
              selectedFile.fileName,
              result.manifest,
              result.outputManifest,
            );
            currentLocalState = {
              ...currentLocalState,
              fileCursor: clamp(
                currentLocalState.fileCursor,
                0,
                Math.max(0, currentSnapshot.files.length - 1),
              ),
            };
            replaceSnapshot(currentSnapshot, true);
            await updateLocalState(currentLocalState);
            setBulkDeleteResults((current) => [
              ...current,
              { error: null, fileName: selectedFile.fileName },
            ]);
          } catch (cause) {
            setBulkDeleteResults((current) => [
              ...current,
              { error: errorMessage(cause), fileName: selectedFile.fileName },
            ]);
            throw cause;
          }
        }
      });
    } catch (cause) {
      setError(
        `Usuwanie zbiorcze zatrzymano, aby zachować spójność stanu luk: ${errorMessage(
          cause,
        )}`,
      );
    } finally {
      setBulkDeleteRunning(false);
    }
  }

  async function returnToModeSelection(): Promise<void> {
    if (
      localState === null ||
      busyRef.current ||
      interactiveWorkInProgress ||
      backgroundMutationPending ||
      backgroundDeletePendingRef.current ||
      backgroundFillPendingRef.current
    )
      return;
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
    const actionableSnapshot = snapshotRef.current;
    const actionableState = localStateRef.current;
    if (
      actionableSnapshot === null ||
      actionableState === null ||
      !viewReadyRef.current ||
      backgroundDeletePendingRef.current ||
      backgroundMutationBlocked ||
      pendingSingleRepairCountRef.current >= MAXIMUM_QUEUED_SINGLE_REPAIRS
    )
      return;
    const actionableGaps = findGaps(actionableSnapshot);
    const actionableGap =
      actionableGaps[
        clamp(
          actionableState.gapCursor,
          0,
          Math.max(0, actionableGaps.length - 1),
        )
      ];
    const actionableSource = sourceImages[actionableState.sourceCursor];
    if (actionableGap === undefined || actionableSource === undefined) return;
    const optimisticSnapshot: RepairDirectorySnapshot = {
      ...actionableSnapshot,
      repairManifest: addFileToRepairManifest(
        actionableSnapshot.repairManifest,
        actionableGap,
      ),
    };
    const nextLocalState = {
      ...actionableState,
      sourceCursor: clamp(
        actionableState.sourceCursor + 1,
        0,
        sourceImages.length - 1,
      ),
      updatedAt: new Date().toISOString(),
    };
    setError(null);
    setRepairViewReady(false);
    replaceSnapshot(optimisticSnapshot);
    applyLocalState(nextLocalState);
    enqueueSingleRepair({
      kind: 'fill',
      localStateAfter: nextLocalState,
      source: actionableSource,
      sourceIndex: actionableState.sourceCursor,
      target: actionableGap,
    });
  }

  async function undoLastFill(): Promise<void> {
    if (
      snapshot === null ||
      localState === null ||
      backgroundMutationPending ||
      backgroundMutationBlocked
    )
      return;
    const fillOperationId = undoFillOperationIds.at(-1);
    if (fillOperationId === undefined) return;
    const fill = snapshot.repairManifest.filledGapEntries.find(
      (entry) => entry.fillOperationId === fillOperationId,
    );
    if (fill === undefined) {
      setUndoFillOperationIds((current) =>
        current.filter((operationId) => operationId !== fillOperationId),
      );
      return;
    }
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
      const refreshed = removeSnapshotFile(
        snapshot,
        fill.fileName,
        result.manifest,
        result.outputManifest,
      );
      replaceSnapshot(refreshed, true);
      setUndoFillOperationIds((current) =>
        current.filter((operationId) => operationId !== fill.fillOperationId),
      );
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
            sameRange(gap, { end: fill.end, start: fill.start }),
          ),
        ),
        sourceCursor: fill.sourceIndex ?? localState.sourceCursor,
      });
    });
  }

  async function deleteCurrentSequence(): Promise<void> {
    const actionableSnapshot = snapshotRef.current;
    const actionableState = localStateRef.current;
    if (
      actionableSnapshot === null ||
      actionableState === null ||
      backgroundFillPendingRef.current ||
      backgroundMutationBlocked ||
      pendingSingleRepairCountRef.current >= MAXIMUM_QUEUED_SINGLE_REPAIRS
    )
      return;
    const actionableCursor = clamp(
      actionableState.fileCursor,
      0,
      Math.max(0, actionableSnapshot.files.length - 1),
    );
    const actionableSelected = actionableSnapshot.files[actionableCursor];
    if (actionableSelected === undefined) return;
    const outputItem = actionableSnapshot.outputManifest?.items.find(
      (item) => item.outputName === actionableSelected.fileName,
    );
    const filledGap = actionableSnapshot.repairManifest.filledGapEntries.find(
      (entry) => entry.fileName === actionableSelected.fileName,
    );
    const sourceIndex = filledGap?.sourceIndex ?? null;
    const sourcePath = filledGap?.sourcePath ?? outputItem?.imagePath ?? null;
    const optimisticManifest = removeFileFromRepairManifest(
      actionableSnapshot.repairManifest,
      actionableSelected,
    );
    const optimisticSnapshot = removeSnapshotFile(
      actionableSnapshot,
      actionableSelected.fileName,
      optimisticManifest,
      actionableSnapshot.outputManifest,
    );
    const nextLocalState = {
      ...actionableState,
      fileCursor: clamp(
        actionableCursor,
        0,
        Math.max(0, optimisticSnapshot.files.length - 1),
      ),
      updatedAt: new Date().toISOString(),
    };
    replaceSnapshot(optimisticSnapshot);
    applyLocalState(nextLocalState);
    enqueueSingleRepair({
      fileName: actionableSelected.fileName,
      kind: 'delete',
      localStateAfter: nextLocalState,
      sourceIndex,
      sourcePath,
    });
  }

  function enqueueSingleRepair(repair: QueuedSingleRepair): void {
    singleRepairQueueRef.current.push(repair);
    pendingSingleRepairCountRef.current += 1;
    setPendingSingleRepairCount(pendingSingleRepairCountRef.current);
    if (repair.kind === 'fill') {
      backgroundFillPendingRef.current = true;
      setBackgroundFillPending(true);
      setNotice('Uzupełnienia zapisują się kolejno w tle.');
    } else {
      backgroundDeletePendingRef.current = true;
      setBackgroundDeletePending(true);
      setNotice('Usunięcia zapisują się kolejno w tle.');
    }
    void runSingleRepairQueue();
  }

  async function runSingleRepairQueue(): Promise<void> {
    if (singleRepairWriterActiveRef.current) return;
    const repair = singleRepairQueueRef.current.shift();
    if (repair === undefined) return;
    singleRepairWriterActiveRef.current = true;
    try {
      const persisted = await persistSingleRepair(repair);
      durableSnapshotRef.current = persisted;
      if (repair.kind === 'fill') {
        const fileName = `seq_${repair.target.start}-${repair.target.end}.jpg`;
        const fill = persisted.repairManifest.filledGapEntries.find(
          (entry) => entry.fileName === fileName,
        );
        if (fill !== undefined) {
          setUndoFillOperationIds((current) =>
            rememberFillOperation(current, fill.fillOperationId),
          );
        }
      }
      void persistLocalState(repair.localStateAfter).catch(() => {
        setNotice(
          'Plik został zapisany, ale nie udało się zapamiętać kursora lokalnie. Po odświeżeniu wskaż katalog ponownie.',
        );
      });
      completeSingleRepair();
    } catch (cause) {
      failSingleRepair(repair, cause);
    } finally {
      singleRepairWriterActiveRef.current = false;
      if (pendingSingleRepairCountRef.current > 0) void runSingleRepairQueue();
    }
  }

  async function persistSingleRepair(
    repair: QueuedSingleRepair,
  ): Promise<RepairDirectorySnapshot> {
    const durableSnapshot = durableSnapshotRef.current;
    if (durableSnapshot === null) throw new Error('REPAIR_SNAPSHOT_MISSING');
    if (repair.kind === 'fill') {
      const result = await writeRepairFile({
        directory: durableSnapshot.directory,
        kind: 'fill',
        manifest: durableSnapshot.repairManifest,
        outputManifest: durableSnapshot.outputManifest,
        source: repair.source.handle,
        sourceIndex: repair.sourceIndex,
        sourcePath: repair.source.relativePath,
        target: repair.target,
      });
      return addSnapshotFile(
        durableSnapshot,
        {
          end: repair.target.end,
          fileName: `seq_${repair.target.start}-${repair.target.end}.jpg`,
          handle: result.fileHandle,
          start: repair.target.start,
        },
        result.manifest,
        result.outputManifest,
      );
    }
    const result = await deleteRepairFile({
      directory: durableSnapshot.directory,
      fileName: repair.fileName,
      kind: 'delete',
      manifest: durableSnapshot.repairManifest,
      outputManifest: durableSnapshot.outputManifest,
      sourceIndex: repair.sourceIndex,
      sourcePath: repair.sourcePath,
    });
    return removeSnapshotFile(
      durableSnapshot,
      repair.fileName,
      result.manifest,
      result.outputManifest,
    );
  }

  function completeSingleRepair(): void {
    pendingSingleRepairCountRef.current -= 1;
    setPendingSingleRepairCount(pendingSingleRepairCountRef.current);
    if (pendingSingleRepairCountRef.current > 0) return;
    const durableSnapshot = durableSnapshotRef.current;
    if (durableSnapshot !== null) replaceSnapshot(durableSnapshot, true);
    backgroundFillPendingRef.current = false;
    backgroundDeletePendingRef.current = false;
    setBackgroundFillPending(false);
    setBackgroundDeletePending(false);
    setNotice(null);
  }

  function failSingleRepair(repair: QueuedSingleRepair, cause: unknown): void {
    const cancelledCount = singleRepairQueueRef.current.length;
    singleRepairQueueRef.current = [];
    pendingSingleRepairCountRef.current = 0;
    setPendingSingleRepairCount(0);
    backgroundFillPendingRef.current = false;
    backgroundDeletePendingRef.current = false;
    setBackgroundFillPending(false);
    setBackgroundDeletePending(false);
    const durableSnapshot = durableSnapshotRef.current;
    if (durableSnapshot !== null) replaceSnapshot(durableSnapshot, true);
    const restored = restoreLocalStateAfterSingleRepairFailure(
      localStateRef.current,
      durableSnapshot,
      repair,
    );
    if (restored !== null) {
      applyLocalState(restored);
      void persistLocalState(restored).catch(() => undefined);
    }
    if (repair.kind === 'fill') setBackgroundFillBlocked(true);
    else setBackgroundDeleteBlocked(true);
    setError(
      `${repair.kind === 'fill' ? 'Nie udało się zapisać uzupełnienia' : 'Nie udało się zapisać usunięcia'}. Anulowano ${cancelledCount} oczekujących operacji i wrócono do tej pozycji. Otwórz ponownie ten katalog przed kolejną zmianą. ${errorMessage(cause)}`,
    );
  }

  function replaceSnapshot(
    next: RepairDirectorySnapshot,
    durable = false,
  ): void {
    snapshotRef.current = next;
    if (durable) durableSnapshotRef.current = next;
    setSnapshot(next);
  }

  function setRepairViewReady(next: boolean): void {
    viewReadyRef.current = next;
    setViewReady(next);
  }

  async function updateLocalState(
    next: ManualSelectionRepairLocalState,
  ): Promise<void> {
    const updated = applyLocalState(next);
    await persistLocalState(updated);
  }

  function applyLocalState(
    next: ManualSelectionRepairLocalState,
  ): ManualSelectionRepairLocalState {
    const updated = { ...next, updatedAt: new Date().toISOString() };
    localStateRef.current = updated;
    setLocalState(updated);
    return updated;
  }

  function persistLocalState(
    state: ManualSelectionRepairLocalState,
  ): Promise<void> {
    const saved = localStateSaveQueueRef.current
      .catch(() => undefined)
      .then(() => store.save(state));
    localStateSaveQueueRef.current = saved.catch(() => undefined);
    return saved;
  }

  async function serialize(operation: () => Promise<void>): Promise<void> {
    if (
      busyRef.current ||
      backgroundDeletePendingRef.current ||
      backgroundFillPendingRef.current ||
      backgroundMutationBlocked
    )
      return;
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
            <p>
              Źródło: {localState.sourceDirectory?.name} ·{' '}
              {sourceImages.length.toLocaleString('pl-PL')} zdjęć
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
            disabled={
              busy || interactiveWorkInProgress || backgroundMutationPending
            }
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
            disabled={
              busy ||
              interactiveWorkInProgress ||
              backgroundMutationPending ||
              backgroundMutationBlocked ||
              undoFillOperationIds.length === 0
            }
            onClick={() => void undoLastFill()}
            type="button"
          >
            Cofnij uzupełnienie ({undoFillOperationIds.length}/2) A / Ctrl+Z
          </button>
          <button
            className="primaryButton"
            disabled={
              busy ||
              interactiveWorkInProgress ||
              !viewReady ||
              backgroundDeletePending ||
              backgroundMutationBlocked ||
              pendingSingleRepairCount >= MAXIMUM_QUEUED_SINGLE_REPAIRS ||
              currentGap === null ||
              currentSource === undefined
            }
            onClick={() => void fillCurrentGap()}
            type="button"
          >
            Uzupełnij lukę Enter/F
          </button>
        </div>
        {backgroundFillPending ? (
          <p className="manualImageSelectionStatus" role="status">
            Zapisuję uzupełnienia w tle: {pendingSingleRepairCount}/
            {MAXIMUM_QUEUED_SINGLE_REPAIRS}. Kolejne są wykonywane po kolei.
          </p>
        ) : null}
        {error !== null ? (
          <p className="formError" role="alert">
            {error}
          </p>
        ) : null}
        <p className="manualImageSelectionHelp">
          ←/→ zdjęcie · ↑/↓ zmienia skok · Enter/F uzupełnia · A/Ctrl+A/Ctrl+Z
          cofa jedno z 2 ostatnich zapisanych uzupełnień
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
          Usunięcie jest trwałe. Następny obraz pojawia się od razu, a zapis
          stanu luk kończy się w tle.
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
            disabled={
              busy || interactiveWorkInProgress || backgroundDeletePending
            }
            onClick={() => void returnToModeSelection()}
            type="button"
          >
            Wróć do wyboru trybu
          </button>
          <button
            className="dangerButton"
            disabled={
              busy ||
              interactiveWorkInProgress ||
              backgroundFillPending ||
              backgroundDeleteBlocked ||
              pendingSingleRepairCount >= MAXIMUM_QUEUED_SINGLE_REPAIRS ||
              currentSelected === undefined
            }
            onClick={() => void deleteCurrentSequence()}
            type="button"
          >
            Usuń sekwencję F
          </button>
        </div>
        {backgroundDeletePending ? (
          <p className="manualImageSelectionStatus" role="status">
            Zapisuję usunięcia w tle: {pendingSingleRepairCount}/
            {MAXIMUM_QUEUED_SINGLE_REPAIRS}. Kolejne są wykonywane po kolei.
          </p>
        ) : null}
        {notice !== null ? (
          <p className="manualImageSelectionStatus">{notice}</p>
        ) : null}
        {error !== null ? (
          <p className="formError" role="alert">
            {error}
          </p>
        ) : null}
        <p className="manualImageSelectionHelp">
          ←/→ przechodzi o jeden plik · F usuwa trwale
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
              backgroundMutationPending ||
              backgroundMutationBlocked ||
              snapshot === null
            }
            onClick={() => void startFill()}
            type="button"
          >
            Uzupełnij luki
          </button>
          <button
            className="secondaryButton"
            disabled={
              busy ||
              interactiveWorkInProgress ||
              backgroundMutationPending ||
              backgroundMutationBlocked ||
              snapshot === null
            }
            onClick={openBulkDelete}
            type="button"
          >
            Usuń wybrane
          </button>
          <button
            className="secondaryButton"
            disabled={
              busy ||
              interactiveWorkInProgress ||
              backgroundMutationPending ||
              backgroundMutationBlocked ||
              snapshot === null
            }
            onClick={() => void startDelete()}
            type="button"
          >
            Usuń pojedynczo
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
      {bulkDeleteOpen && snapshot !== null ? (
        <dialog aria-modal="true" className="manualRepairBulkDeleteDialog" open>
          <header className="manualRepairBulkDeleteHeader">
            <div>
              <p className="eyebrow">Lokalnie · bez cofania</p>
              <h2>Usuń wybrane sekwencje</h2>
              <p>
                Wpisz początek numeru planszy. Wyszukiwanie dotyczy wyłącznie
                pierwszego numeru zakresu `seq_*`.
              </p>
            </div>
          </header>
          <label className="manualRepairBulkDeleteSearch">
            Numer początkowy zakresu
            <input
              autoFocus
              inputMode="numeric"
              onChange={(event) =>
                setBulkDeleteQuery(
                  event.currentTarget.value.replace(/[^0-9]/g, ''),
                )
              }
              onKeyDown={(event) => {
                if (
                  event.key === 'Enter' &&
                  bulkDeleteCandidates[0] !== undefined
                ) {
                  event.preventDefault();
                  addBulkDeleteFile(bulkDeleteCandidates[0].fileName);
                }
              }}
              placeholder="np. 456"
              value={bulkDeleteQuery}
            />
          </label>
          {bulkDeleteCandidates.length > 0 ? (
            <ul className="manualRepairBulkDeleteSuggestions" role="listbox">
              {bulkDeleteCandidates.map((file) => (
                <li key={file.fileName}>
                  <button
                    onClick={() => addBulkDeleteFile(file.fileName)}
                    type="button"
                  >
                    {file.fileName}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
          <section
            aria-label="Wybrane pliki"
            className="manualRepairBulkDeleteList"
          >
            <div className="manualRepairBulkDeleteListHeader">
              <span>Nazwa pliku</span>
            </div>
            {bulkDeleteFiles.map((file) => (
              <div className="manualRepairBulkDeleteRow" key={file.fileName}>
                <span>{file.fileName}</span>
                <button
                  aria-label={`Usuń ${file.fileName} z wyboru`}
                  disabled={bulkDeleteRunning}
                  onClick={() =>
                    setBulkDeleteFileNames((current) =>
                      current.filter((name) => name !== file.fileName),
                    )
                  }
                  type="button"
                >
                  🗑
                </button>
              </div>
            ))}
          </section>
          {bulkDeleteResults.length > 0 ? (
            <ul className="manualRepairBulkDeleteResults" role="status">
              {bulkDeleteResults.map((result) => (
                <li key={result.fileName}>
                  {result.error === null
                    ? `${result.fileName} — usunięto`
                    : `${result.fileName} — błąd: ${result.error}`}
                </li>
              ))}
            </ul>
          ) : null}
          <label className="manualRepairBulkDeleteConfirm">
            <input
              checked={bulkDeleteConfirmed}
              disabled={bulkDeleteRunning}
              onChange={(event) =>
                setBulkDeleteConfirmed(event.currentTarget.checked)
              }
              type="checkbox"
            />
            Rozumiem, że wybrane pliki zostaną usunięte bez kosza i bez
            możliwości cofnięcia.
          </label>
          <footer className="manualImageSelectionActions">
            <button
              className="secondaryButton"
              disabled={bulkDeleteRunning}
              onClick={() => setBulkDeleteOpen(false)}
              type="button"
            >
              Zamknij
            </button>
            <button
              className="dangerButton"
              disabled={
                bulkDeleteRunning ||
                !bulkDeleteConfirmed ||
                bulkDeleteFiles.length === 0
              }
              onClick={() => void deleteSelectedSequences()}
              type="button"
            >
              {bulkDeleteRunning
                ? `Usuwanie ${bulkDeleteResults.length}/${bulkDeleteFiles.length}…`
                : 'Usuń wybrane'}
            </button>
          </footer>
        </dialog>
      ) : null}
    </section>
  );
}

async function pickDirectory(
  mode: 'read' | 'readwrite',
  id = 'gp-manual-repair',
) {
  return pickLocalDirectory({ id, mode });
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
  sourceListingProgress: ManualImageListingProgress | null,
  sourceListingDirectoryName: string | null,
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
    case 'listing_source': {
      const directoryLabel =
        sourceListingDirectoryName === null
          ? 'katalogu bazowego'
          : `katalogu „${sourceListingDirectoryName}”`;
      return sourceListingProgress === null
        ? `Wczytuję zdjęcia bezpośrednio z ${directoryLabel}…`
        : `Wczytuję zdjęcia bezpośrednio z ${directoryLabel}… sprawdzono ${sourceListingProgress.visitedEntries.toLocaleString('pl-PL')} wpisów, znaleziono ${sourceListingProgress.imageCount.toLocaleString('pl-PL')} obrazów.`;
    }
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

function findGaps(snapshot: RepairDirectorySnapshot): readonly SequenceRange[] {
  return findSequenceGaps(
    {
      end: snapshot.repairManifest.collectionEnd,
      start: snapshot.repairManifest.collectionStart,
    },
    snapshot.repairManifest.activeFiles,
    snapshot.repairManifest.deletedRanges,
  );
}

function restoreLocalStateAfterSingleRepairFailure(
  localState: ManualSelectionRepairLocalState | null,
  durableSnapshot: RepairDirectorySnapshot | null,
  repair: QueuedSingleRepair,
): ManualSelectionRepairLocalState | null {
  if (localState === null || durableSnapshot === null) return localState;
  if (repair.kind === 'fill') {
    const gapCursor = findGaps(durableSnapshot).findIndex((gap) =>
      sameRange(gap, repair.target),
    );
    return {
      ...localState,
      gapCursor: Math.max(0, gapCursor),
      sourceCursor: repair.sourceIndex,
      updatedAt: new Date().toISOString(),
    };
  }
  const fileCursor = durableSnapshot.files.findIndex(
    (file) => file.fileName === repair.fileName,
  );
  return {
    ...localState,
    fileCursor: Math.max(0, fileCursor),
    updatedAt: new Date().toISOString(),
  };
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

function addFileToRepairManifest(
  manifest: RepairDirectorySnapshot['repairManifest'],
  range: SequenceRange,
): RepairDirectorySnapshot['repairManifest'] {
  const fileName = `seq_${range.start}-${range.end}.jpg`;
  return {
    ...manifest,
    activeFiles: [
      ...manifest.activeFiles.filter((file) => file.fileName !== fileName),
      { checksumSha256: null, end: range.end, fileName, start: range.start },
    ].sort(
      (left, right) =>
        left.start - right.start ||
        left.end - right.end ||
        left.fileName.localeCompare(right.fileName),
    ),
    deletedRanges: manifest.deletedRanges.filter(
      (deleted) => !sameRange(deleted, range),
    ),
    deletedSources: manifest.deletedSources.filter(
      (deleted) => deleted.fileName !== fileName,
    ),
  };
}

function removeFileFromRepairManifest(
  manifest: RepairDirectorySnapshot['repairManifest'],
  file: SequenceRange & { readonly fileName: string },
): RepairDirectorySnapshot['repairManifest'] {
  const hasDeletedRange = manifest.deletedRanges.some((range) =>
    sameRange(range, file),
  );
  return {
    ...manifest,
    activeFiles: manifest.activeFiles.filter(
      (active) => active.fileName !== file.fileName,
    ),
    deletedRanges: hasDeletedRange
      ? manifest.deletedRanges
      : [...manifest.deletedRanges, { end: file.end, start: file.start }],
    filledGapEntries: manifest.filledGapEntries.filter(
      (entry) => entry.fileName !== file.fileName,
    ),
  };
}

function sameRange(left: SequenceRange, right: SequenceRange): boolean {
  return left.start === right.start && left.end === right.end;
}

function recentFillOperationIds(
  snapshot: RepairDirectorySnapshot,
): readonly string[] {
  return [...snapshot.repairManifest.filledGapEntries]
    .sort(
      (left, right) =>
        left.filledAt.localeCompare(right.filledAt) ||
        left.fillOperationId.localeCompare(right.fillOperationId),
    )
    .slice(-MAXIMUM_FILL_UNDOS)
    .map((fill) => fill.fillOperationId);
}

function rememberFillOperation(
  current: readonly string[],
  operationId: string,
): readonly string[] {
  return [
    ...current.filter(
      (currentOperationId) => currentOperationId !== operationId,
    ),
    operationId,
  ].slice(-MAXIMUM_FILL_UNDOS);
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

function isCriticalBulkDeleteFailure(cause: unknown): boolean {
  const message = errorMessage(cause);
  return !(
    message.startsWith('REPAIR_FILE_CHECKSUM_MISMATCH:') ||
    message === 'REPAIR_FILE_NOT_MANAGED'
  );
}
