'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import {
  isLocalDirectoryPickerActive,
  pickLocalDirectory,
  subscribeLocalDirectoryPickerActive,
} from '../../lib/local-directory-picker.ts';

import {
  adjacentManualNavigationStep,
  createManualSelectionState,
  INDEPENDENT_MANUAL_SELECTION_ID,
  MANUAL_IMAGE_NAVIGATION_STEPS,
  nextManualSelectionState,
  previousManualSelectionState,
  rangeForStart,
  reconcileManualSelectionStateWithOutputManifest,
  resolveManualSelectionShortcut,
  type ManualSelectionDecision,
  type ManualSelectionState,
  type ManualSelectionTraceEvent,
} from '@game-predictor/manual-image-selection-core';
import {
  FileSystemManualSelectionOutputAdapter,
  FileSystemManualSelectionSourceAdapter,
  isMissingManualDirectoryHandleError,
  readManualOutputManifest,
  relinkManualSelectionSession,
  sha256Hex,
  type ManualImageFile,
  type ManualSelectionSessionRecord,
} from './manual-image-selection-fsa-adapter';
import {
  initialManualSelectionCursor,
  MANUAL_SELECTION_CURSOR_SEMANTICS,
  manualSelectionDisplayPosition,
  moveManualSelectionCursor,
  resumeManualSelectionCursor,
} from './manual-image-selection-cursor';
import { ManualImageSelectionStore } from './manual-image-selection-store';
import { ManualImageViewer, useManualImageViewer } from './manual-image-viewer';
import { RemoteManualSelectionHostPanel } from './remote-manual-selection-host-panel';
import { ManualSelectionRepairWorkspace } from './manual-selection-repair-workspace';
import { ManualSelectionRangeVerificationWorkspace } from './manual-selection-range-verification-workspace';
import { readRepairManifest } from './manual-selection-repair-storage.ts';

type ResumeRecoveryTarget = 'source' | 'output';

const CURSOR_PREFIX = 'game-predictor:manual-image-selection-cursor:';
const MAXIMUM_QUEUED_MANUAL_ACCEPTS = 100;

type QueuedManualAcceptance = {
  readonly decision: ManualSelectionDecision;
  readonly nextIndex: number;
  readonly source: ManualImageFile;
};

function hasAcceptedManualImage(
  state: ManualSelectionState,
  relativePath: string,
): boolean {
  return state.decisions.some(
    (decision) =>
      decision.action === 'accepted' && decision.imagePath === relativePath,
  );
}

function isEditableManualSelectionTarget(target: HTMLElement | null): boolean {
  if (target === null) return false;
  return (
    target.isContentEditable ||
    target.tagName === 'INPUT' ||
    target.tagName === 'SELECT' ||
    target.tagName === 'TEXTAREA'
  );
}

export function ManualImageSelectionWorkspace({
  apiBaseUrl,
}: {
  readonly apiBaseUrl: string;
}) {
  return (
    <div className="manualImageSelectionWorkspaceStack">
      <RemoteManualSelectionHostPanel apiBaseUrl={apiBaseUrl} />
      <LocalManualImageSelectionWorkspace />
      <ManualSelectionRepairWorkspace />
      <ManualSelectionRangeVerificationWorkspace apiBaseUrl={apiBaseUrl} />
    </div>
  );
}

function LocalManualImageSelectionWorkspace() {
  const workspaceId = INDEPENDENT_MANUAL_SELECTION_ID;
  const store = useMemo(() => new ManualImageSelectionStore(), []);
  const busyRef = useRef(false);
  const stateRef = useRef<ManualSelectionState | null>(null);
  const durableStateRef = useRef<ManualSelectionState | null>(null);
  const recordRef = useRef<ManualSelectionSessionRecord | null>(null);
  const saveQueueRef = useRef<Promise<void>>(Promise.resolve());
  const acceptedOutputQueueRef = useRef<QueuedManualAcceptance[]>([]);
  const acceptedOutputWriterActiveRef = useRef(false);
  const acceptPreparationRef = useRef(false);
  const pendingAcceptedOutputCountRef = useRef(0);
  const traceEventIndexRef = useRef(0);
  const viewTimerRef = useRef<number | null>(null);
  const [firstLayout, setFirstLayout] = useState('1');
  const [sequenceUpperBound, setSequenceUpperBound] = useState('');
  const [direction, setDirection] = useState<'ascending' | 'descending'>(
    'ascending',
  );
  const [sourceDirectory, setSourceDirectory] =
    useState<FileSystemDirectoryHandle | null>(null);
  const [outputDirectory, setOutputDirectory] =
    useState<FileSystemDirectoryHandle | null>(null);
  const [images, setImages] = useState<ManualImageFile[]>([]);
  const [record, setRecord] = useState<ManualSelectionSessionRecord | null>(
    null,
  );
  const [savedRecord, setSavedRecord] =
    useState<ManualSelectionSessionRecord | null>(null);
  const [loading, setLoading] = useState(false);
  const [directoryPickerActive, setDirectoryPickerActive] = useState(
    isLocalDirectoryPickerActive,
  );
  const [busy, setBusy] = useState(false);
  const [acceptPreparation, setAcceptPreparation] = useState(false);
  const [pendingAcceptedOutputCount, setPendingAcceptedOutputCount] =
    useState(0);
  const [error, setError] = useState<string | null>(null);
  const [resumeNotice, setResumeNotice] = useState<string | null>(null);
  const [resumeRecovery, setResumeRecovery] =
    useState<ResumeRecoveryTarget | null>(null);
  const [queueRecoveryRequired, setQueueRecoveryRequired] = useState(false);
  const [state, setState] = useState<ManualSelectionState | null>(null);
  const [rangeEditorOpen, setRangeEditorOpen] = useState(false);
  const [rangeStartDraft, setRangeStartDraft] = useState('');
  const [rangeEndDraft, setRangeEndDraft] = useState('');
  const manualAcceptanceInProgress =
    acceptPreparation || pendingAcceptedOutputCount > 0;
  const currentImageIndex = state?.currentIndex ?? -1;
  const currentRangeStart = state?.nextRangeStart ?? -1;
  const parsedSetupFirstLayout = Number.parseInt(firstLayout, 10);
  const setupFirstLayout =
    Number.isSafeInteger(parsedSetupFirstLayout) && parsedSetupFirstLayout >= 1
      ? parsedSetupFirstLayout
      : 1;
  const setupUpperBound = Number.parseInt(sequenceUpperBound, 10);
  const setupRange = rangeForStart(
    setupFirstLayout,
    Number.isSafeInteger(setupUpperBound) && setupUpperBound >= setupFirstLayout
      ? setupUpperBound
      : null,
  );
  const currentImagePosition =
    state === null
      ? 0
      : manualSelectionDisplayPosition(state.currentIndex, images.length);
  const handleViewerError = useCallback((message: string) => {
    setError(message);
  }, []);
  const imageViewer = useManualImageViewer(
    images,
    currentImageIndex,
    handleViewerError,
  );

  function replaceVisibleState(next: ManualSelectionState | null): void {
    stateRef.current = next;
    setState(next);
  }

  function replaceDurableRecord(
    next: ManualSelectionSessionRecord | null,
  ): void {
    recordRef.current = next;
    durableStateRef.current = next?.state ?? null;
    setRecord(next);
  }

  useEffect(() => {
    return subscribeLocalDirectoryPickerActive(() => {
      setDirectoryPickerActive(isLocalDirectoryPickerActive());
    });
  }, []);

  useEffect(() => {
    let cancelled = false;
    void store
      .loadIndependent(workspaceId)
      .then((loaded) => {
        if (!cancelled) setSavedRecord(loaded);
      })
      .catch(() => {
        if (!cancelled) setSavedRecord(null);
      });
    return () => {
      cancelled = true;
    };
  }, [store, workspaceId]);

  useEffect(() => {
    if (record === null) return;
    const durableState = record.state;
    const cursor = {
      currentIndex: durableState.currentIndex,
      direction: durableState.direction,
      firstLayout: durableState.firstLayout,
      nextRangeStart: durableState.nextRangeStart,
      sourceDirectoryName: record.sourceDirectoryName,
      updatedAt: durableState.updatedAt,
    };
    window.localStorage.setItem(
      `${CURSOR_PREFIX}${workspaceId}`,
      JSON.stringify(cursor),
    );
  }, [record, workspaceId]);

  useEffect(() => {
    if (viewTimerRef.current !== null) {
      window.clearTimeout(viewTimerRef.current);
      viewTimerRef.current = null;
    }
    const sessionKey = record?.key ?? null;
    const current = images[currentImageIndex];
    if (
      sessionKey === null ||
      current === undefined ||
      currentImageIndex < 0 ||
      currentRangeStart < 1 ||
      imageViewer.visibleImageUrl === null
    ) {
      return;
    }
    const range = rangeForStart(
      currentRangeStart,
      stateRef.current?.sequenceUpperBound ?? null,
    );
    const startedAt = performance.now();
    viewTimerRef.current = window.setTimeout(() => {
      if (stateRef.current?.currentIndex !== currentImageIndex) return;
      if (stateRef.current?.nextRangeStart !== currentRangeStart) return;
      const event: ManualSelectionTraceEvent = {
        decoded: true,
        eventIndex: traceEventIndexRef.current++,
        gameId: workspaceId,
        imagePath: current.relativePath,
        kind: 'viewed',
        rangeEnd: range.end,
        rangeStart: range.start,
        recordedAt: new Date().toISOString(),
        sessionKey,
        sourceIndex: currentImageIndex,
        visibleMilliseconds: Math.round(performance.now() - startedAt),
      };
      void store.appendTraceEvent(event).catch(() => undefined);
    }, 300);
    return () => {
      if (viewTimerRef.current !== null) {
        window.clearTimeout(viewTimerRef.current);
        viewTimerRef.current = null;
      }
    };
  }, [
    currentImageIndex,
    currentRangeStart,
    imageViewer.visibleImageUrl,
    images,
    record?.key,
    store,
    workspaceId,
  ]);

  async function pickDirectory(
    mode: 'read' | 'readwrite',
  ): Promise<FileSystemDirectoryHandle> {
    return pickLocalDirectory({
      id: mode === 'read' ? 'gp-manual-source' : 'gp-manual-output',
      mode,
    });
  }

  async function chooseSource(): Promise<void> {
    setError(null);
    setLoading(true);
    try {
      const directory = await pickDirectory('read');
      const found = await new FileSystemManualSelectionSourceAdapter(
        directory,
      ).listImages();
      if (found.length === 0)
        throw new Error('Wybrany folder nie zawiera plików JPG/JPEG.');
      setSourceDirectory(directory);
      setImages(found);
      replaceDurableRecord(null);
      replaceVisibleState(null);
    } catch (cause) {
      if (!(cause instanceof DOMException && cause.name === 'AbortError')) {
        setError(
          cause instanceof Error
            ? cause.message
            : 'Nie udało się odczytać folderu źródłowego.',
        );
      }
    } finally {
      setLoading(false);
    }
  }

  async function chooseOutput(): Promise<void> {
    setError(null);
    try {
      setOutputDirectory(await pickDirectory('readwrite'));
    } catch (cause) {
      if (!(cause instanceof DOMException && cause.name === 'AbortError')) {
        setError(
          cause instanceof Error
            ? cause.message
            : 'Nie udało się wybrać folderu wynikowego.',
        );
      }
    }
  }

  async function startSession(): Promise<void> {
    if (queueRecoveryRequired) return;
    const parsed = Number.parseInt(firstLayout, 10);
    const parsedUpperBound =
      sequenceUpperBound.trim() === ''
        ? null
        : Number.parseInt(sequenceUpperBound, 10);
    if (!Number.isSafeInteger(parsed) || parsed < 1) {
      setError('Pierwszy numer planszy musi być dodatnią liczbą całkowitą.');
      return;
    }
    if (
      parsedUpperBound !== null &&
      (!Number.isSafeInteger(parsedUpperBound) || parsedUpperBound < parsed)
    ) {
      setError(
        'Ostatni numer planszy musi być liczbą całkowitą nie mniejszą od pierwszej planszy.',
      );
      return;
    }
    if (
      sourceDirectory === null ||
      outputDirectory === null ||
      images.length === 0
    ) {
      setError('Wybierz folder źródłowy i wynikowy.');
      return;
    }
    try {
      if ((await readRepairManifest(outputDirectory)) !== null) {
        setError(
          'Ten katalog był już poprawiany. Kontynuuj w sekcji „Popraw selekcję” poniżej.',
        );
        return;
      }
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : 'Nie udało się zweryfikować manifestu korekty.',
      );
      return;
    }
    const initialState = createManualSelectionState(
      parsed,
      direction,
      parsedUpperBound,
    );
    const next = {
      ...initialState,
      currentIndex: initialManualSelectionCursor(),
    };
    const nextRecord: ManualSelectionSessionRecord = {
      cursorImagePath: images[next.currentIndex]?.relativePath,
      cursorSemantics: MANUAL_SELECTION_CURSOR_SEMANTICS,
      gameId: workspaceId,
      key: `${workspaceId}:${Date.now()}`,
      outputDirectory,
      sourceDirectory,
      sourceDirectoryName: sourceDirectory.name,
      state: next,
    };
    replaceDurableRecord(nextRecord);
    replaceVisibleState(next);
    setSavedRecord(null);
    setQueueRecoveryRequired(false);
    traceEventIndexRef.current = 0;
    await store.save(nextRecord);
  }

  async function resumeSession(): Promise<void> {
    if (savedRecord === null) return;
    setError(null);
    setResumeNotice(null);
    setLoading(true);
    const sourceHandle = sourceDirectory ?? savedRecord.sourceDirectory;
    const outputHandle = outputDirectory ?? savedRecord.outputDirectory;
    try {
      let found: ManualImageFile[];
      try {
        await requestPermission(sourceHandle, 'read');
        found = await new FileSystemManualSelectionSourceAdapter(
          sourceHandle,
        ).listImages();
      } catch (cause) {
        if (isMissingManualDirectoryHandleError(cause)) {
          setResumeRecovery('source');
          setError(
            'Zapisany folder źródłowy nie jest już dostępny. Wybierz go ponownie; zapisane decyzje, zakres i pozycja zostaną zachowane.',
          );
          return;
        }
        throw cause;
      }
      if (found.length === 0)
        throw new Error('Folder źródłowy nie zawiera już zdjęć JPG/JPEG.');
      if (savedRecord.state.currentIndex >= found.length) {
        throw new Error(
          `Wybrany folder zawiera tylko ${found.length.toLocaleString('pl-PL')} zdjęć i nie obejmuje zapisanej pozycji ${savedRecord.state.currentIndex + 1}.`,
        );
      }
      try {
        await requestPermission(outputHandle, 'readwrite');
        await verifyDirectoryHandle(outputHandle);
      } catch (cause) {
        if (isMissingManualDirectoryHandleError(cause)) {
          setResumeRecovery('output');
          setError(
            'Zapisany folder wynikowy nie jest już dostępny. Wybierz go ponownie; żadne decyzje ani istniejące pliki nie zostaną usunięte.',
          );
          return;
        }
        throw cause;
      }
      const repairedRecord = relinkManualSelectionSession(
        savedRecord,
        sourceHandle,
        outputHandle,
      );
      const manifest = await readManualOutputManifest(outputHandle);
      if ((await readRepairManifest(outputHandle)) !== null) {
        throw new Error(
          'Ten katalog był już poprawiany. Wznów pracę w sekcji „Popraw selekcję” poniżej.',
        );
      }
      if (
        manifest !== null &&
        (manifest.sessionKey !== savedRecord.key ||
          manifest.sourceDirectoryName !== repairedRecord.sourceDirectoryName)
      ) {
        throw new Error(
          'Manifest folderu wynikowego nie należy do zapisywanej sesji ręcznej selekcji.',
        );
      }
      const reconciledState =
        manifest === null
          ? savedRecord.state
          : reconcileManualSelectionStateWithOutputManifest(
              savedRecord.state,
              manifest,
            );
      const events = await store.loadTraceEvents(workspaceId, savedRecord.key);
      const resumedCursor = resumeManualSelectionCursor({
        currentImagePath: savedRecord.cursorImagePath,
        cursorSemantics: savedRecord.cursorSemantics,
        currentIndex: reconciledState.currentIndex,
        decisions: reconciledState.decisions,
        direction: reconciledState.direction,
        images: found,
        traceEvents: events,
      });
      const resumedState = {
        ...reconciledState,
        currentIndex: resumedCursor.currentIndex,
      };
      const synchronizedRecord = {
        ...repairedRecord,
        cursorImagePath: resumedCursor.currentImagePath ?? undefined,
        cursorSemantics: resumedCursor.cursorSemantics,
        state: resumedState,
      };
      await store.save(synchronizedRecord);
      setResumeRecovery(null);
      setQueueRecoveryRequired(false);
      setSavedRecord(synchronizedRecord);
      setSourceDirectory(sourceHandle);
      setOutputDirectory(outputHandle);
      setImages(found);
      replaceDurableRecord(synchronizedRecord);
      replaceVisibleState(resumedState);
      if (
        manifest !== null &&
        resumedState.nextRangeStart !== savedRecord.state.nextRangeStart
      ) {
        setResumeNotice(
          resumedState.selectionComplete === true
            ? 'Numeracja została zsynchronizowana z manifestem. Osiągnięto granicę selekcji.'
            : `Numeracja została zsynchronizowana z manifestem. Następny zakres: ${rangeForStart(resumedState.nextRangeStart, resumedState.sequenceUpperBound ?? null).start}–${rangeForStart(resumedState.nextRangeStart, resumedState.sequenceUpperBound ?? null).end}.`,
        );
      }
      traceEventIndexRef.current =
        events.reduce(
          (highest, event) => Math.max(highest, event.eventIndex),
          -1,
        ) + 1;
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : 'Nie udało się wznowić sesji.',
      );
    } finally {
      setLoading(false);
    }
  }

  async function persist(next: ManualSelectionState): Promise<void> {
    const currentRecord = recordRef.current;
    if (currentRecord === null) return;
    const nextRecord = {
      ...currentRecord,
      cursorImagePath:
        images[next.currentIndex]?.relativePath ??
        currentRecord.cursorImagePath,
      cursorSemantics: MANUAL_SELECTION_CURSOR_SEMANTICS,
      state: next,
    };
    replaceDurableRecord(nextRecord);
    replaceVisibleState(next);
    const save = saveQueueRef.current
      .catch(() => undefined)
      .then(() => store.save(nextRecord));
    saveQueueRef.current = save;
    await save;
  }

  function openRangeEditor(): void {
    const currentState = stateRef.current;
    if (
      currentState === null ||
      acceptPreparationRef.current ||
      pendingAcceptedOutputCountRef.current > 0
    )
      return;
    const currentRange = rangeForStart(
      currentState.nextRangeStart,
      currentState.sequenceUpperBound ?? null,
    );
    setRangeStartDraft(String(currentRange.start));
    setRangeEndDraft(String(currentRange.end));
    setRangeEditorOpen(true);
  }

  async function applyRangeEdit(): Promise<void> {
    const currentState = stateRef.current;
    if (
      acceptPreparationRef.current ||
      pendingAcceptedOutputCountRef.current > 0
    )
      return;
    const rangeStart = Number(rangeStartDraft);
    const rangeEnd = Number(rangeEndDraft);
    let expectedRangeEnd: number | null = null;
    if (
      currentState !== null &&
      Number.isSafeInteger(rangeStart) &&
      rangeStart >= 1
    ) {
      try {
        expectedRangeEnd = rangeForStart(
          rangeStart,
          currentState.sequenceUpperBound ?? null,
        ).end;
      } catch {
        expectedRangeEnd = null;
      }
    }
    if (
      currentState === null ||
      !Number.isSafeInteger(rangeStart) ||
      !Number.isSafeInteger(rangeEnd) ||
      rangeStart < 1 ||
      expectedRangeEnd === null ||
      rangeEnd !== expectedRangeEnd
    ) {
      setError(
        'Zakres musi zawierać do 9 kolejnych plansz i respektować ostatni numer sesji.',
      );
      return;
    }
    setError(null);
    await persist({
      ...currentState,
      nextRangeStart: rangeStart,
      selectionComplete: false,
      updatedAt: new Date().toISOString(),
    });
    setRangeEditorOpen(false);
  }

  async function acceptCurrent(): Promise<void> {
    if (
      recordRef.current === null ||
      stateRef.current === null ||
      outputDirectory === null ||
      busyRef.current ||
      acceptPreparationRef.current ||
      rangeEditorOpen ||
      pendingAcceptedOutputCountRef.current >= MAXIMUM_QUEUED_MANUAL_ACCEPTS ||
      stateRef.current.selectionComplete === true
    )
      return;
    const currentState = stateRef.current;
    const current = images[currentState.currentIndex];
    if (current === undefined) return;
    if (hasAcceptedManualImage(currentState, current.relativePath)) {
      setError(
        'To zdjęcie jest już zatwierdzone. Przejdź do kolejnego zdjęcia strzałką →.',
      );
      return;
    }
    acceptPreparationRef.current = true;
    setAcceptPreparation(true);
    setError(null);
    const range = rangeForStart(
      currentState.nextRangeStart,
      currentState.sequenceUpperBound ?? null,
    );
    try {
      const checksum = await sha256Hex(await current.handle.getFile());
      const decision: ManualSelectionDecision = {
        action: 'accepted',
        imageChecksum: checksum,
        imagePath: current.relativePath,
        outputName: `seq_${range.start}-${range.end}.jpg`,
        rangeEnd: range.end,
        rangeStart: range.start,
      };
      const nextState = nextManualSelectionState(
        currentState,
        decision,
        currentState.currentIndex,
      );
      replaceVisibleState(nextState);
      enqueueAcceptedOutput({
        decision,
        nextIndex: nextState.currentIndex,
        source: current,
      });
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : 'Nie udało się przygotować zdjęcia do zapisu.',
      );
    } finally {
      acceptPreparationRef.current = false;
      setAcceptPreparation(false);
    }
  }

  function enqueueAcceptedOutput(acceptance: QueuedManualAcceptance): void {
    acceptedOutputQueueRef.current.push(acceptance);
    pendingAcceptedOutputCountRef.current += 1;
    setPendingAcceptedOutputCount(pendingAcceptedOutputCountRef.current);
    void runAcceptedOutputQueue();
  }

  async function runAcceptedOutputQueue(): Promise<void> {
    if (acceptedOutputWriterActiveRef.current) return;
    const acceptance = acceptedOutputQueueRef.current.shift();
    if (acceptance === undefined) return;
    acceptedOutputWriterActiveRef.current = true;
    try {
      const durableState = durableStateRef.current;
      const durableRecord = recordRef.current;
      if (
        durableState === null ||
        durableRecord === null ||
        outputDirectory === null
      ) {
        throw new Error('Brakuje trwałego stanu sesji do zapisu kolejki.');
      }
      if (durableState.nextRangeStart !== acceptance.decision.rangeStart) {
        throw new Error(
          'Kolejka ręcznej selekcji utraciła zgodność kolejności.',
        );
      }
      const output = await new FileSystemManualSelectionOutputAdapter(
        outputDirectory,
      ).writeAcceptedOutput(
        acceptance.source,
        acceptance.decision.rangeStart,
        acceptance.decision.rangeEnd,
        { expectedChecksum: acceptance.decision.imageChecksum ?? undefined },
      );
      if (output.checksum !== acceptance.decision.imageChecksum) {
        throw new Error(
          'Checksum zapisanego JPEG-a nie odpowiada decyzji kolejki.',
        );
      }
      const nextState = nextManualSelectionState(
        durableState,
        acceptance.decision,
        acceptance.nextIndex,
      );
      const nextRecord: ManualSelectionSessionRecord = {
        ...durableRecord,
        cursorImagePath:
          images[nextState.currentIndex]?.relativePath ??
          durableRecord.cursorImagePath,
        cursorSemantics: MANUAL_SELECTION_CURSOR_SEMANTICS,
        state: nextState,
      };
      await store.save(nextRecord);
      await new FileSystemManualSelectionOutputAdapter(
        outputDirectory,
      ).writeOutputManifest(nextRecord);
      replaceDurableRecord(nextRecord);
      try {
        await appendDecisionTrace(
          'accepted',
          acceptance.source,
          {
            start: acceptance.decision.rangeStart,
            end: acceptance.decision.rangeEnd,
          },
          output,
          durableState.decisions.length,
          nextRecord,
        );
      } catch (cause) {
        setError(
          cause instanceof Error
            ? `Zdjęcie zapisano, ale nie zapisano śladu decyzji: ${cause.message}`
            : 'Zdjęcie zapisano, ale nie zapisano śladu decyzji.',
        );
      }
      pendingAcceptedOutputCountRef.current -= 1;
      setPendingAcceptedOutputCount(pendingAcceptedOutputCountRef.current);
      if (pendingAcceptedOutputCountRef.current === 0) {
        await synchronizeVisibleNavigationAfterQueue();
      }
    } catch (cause) {
      failAcceptedOutputQueue(cause);
    } finally {
      acceptedOutputWriterActiveRef.current = false;
      if (pendingAcceptedOutputCountRef.current > 0) {
        void runAcceptedOutputQueue();
      }
    }
  }

  async function synchronizeVisibleNavigationAfterQueue(): Promise<void> {
    const durableRecord = recordRef.current;
    const visibleState = stateRef.current;
    if (
      durableRecord === null ||
      visibleState === null ||
      visibleState.decisions.length !== durableRecord.state.decisions.length ||
      (visibleState.currentIndex === durableRecord.state.currentIndex &&
        visibleState.navigationStep === durableRecord.state.navigationStep)
    ) {
      return;
    }
    const synchronizedState = {
      ...durableRecord.state,
      currentIndex: visibleState.currentIndex,
      navigationStep: visibleState.navigationStep,
      updatedAt: new Date().toISOString(),
    };
    const synchronizedRecord: ManualSelectionSessionRecord = {
      ...durableRecord,
      cursorImagePath:
        images[synchronizedState.currentIndex]?.relativePath ??
        durableRecord.cursorImagePath,
      state: synchronizedState,
    };
    try {
      await store.save(synchronizedRecord);
      replaceDurableRecord(synchronizedRecord);
      replaceVisibleState(synchronizedState);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? `Wybór zapisano, ale nie utrwalono bieżącej nawigacji: ${cause.message}`
          : 'Wybór zapisano, ale nie utrwalono bieżącej nawigacji.',
      );
    }
  }

  function failAcceptedOutputQueue(cause: unknown): void {
    const cancelledCount = acceptedOutputQueueRef.current.length;
    acceptedOutputQueueRef.current = [];
    pendingAcceptedOutputCountRef.current = 0;
    setPendingAcceptedOutputCount(0);
    const durableRecord = recordRef.current;
    setSavedRecord(durableRecord);
    setQueueRecoveryRequired(true);
    replaceVisibleState(null);
    replaceDurableRecord(null);
    setError(
      `${cause instanceof Error ? cause.message : 'Nie udało się zapisać zdjęcia.'} Anulowano ${cancelledCount.toLocaleString('pl-PL')} oczekujących wyborów. Wznów zapisaną sesję, aby bezpiecznie kontynuować.`,
    );
  }

  async function skipCurrent(): Promise<void> {
    const currentState = stateRef.current;
    if (
      recordRef.current === null ||
      currentState === null ||
      busyRef.current ||
      acceptPreparationRef.current ||
      pendingAcceptedOutputCountRef.current > 0 ||
      currentState.selectionComplete === true
    )
      return;
    busyRef.current = true;
    setBusy(true);
    const current = images[currentState.currentIndex];
    if (current === undefined) {
      busyRef.current = false;
      setBusy(false);
      return;
    }
    const range = rangeForStart(
      currentState.nextRangeStart,
      currentState.sequenceUpperBound ?? null,
    );
    try {
      const nextState = nextManualSelectionState(
        currentState,
        {
          action: 'skipped',
          imageChecksum: null,
          imagePath: null,
          outputName: null,
          rangeEnd: range.end,
          rangeStart: range.start,
        },
        currentState.currentIndex,
      );
      await persist(nextState);
      const persistedRecord = recordRef.current;
      if (outputDirectory !== null && persistedRecord !== null) {
        await new FileSystemManualSelectionOutputAdapter(
          outputDirectory,
        ).writeOutputManifest({ ...persistedRecord, state: nextState });
      }
      await appendDecisionTrace(
        'skipped',
        current,
        range,
        null,
        currentState.decisions.length,
      );
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }

  async function undoLast(): Promise<void> {
    const currentState = stateRef.current;
    if (
      recordRef.current === null ||
      currentState === null ||
      busyRef.current ||
      acceptPreparationRef.current ||
      pendingAcceptedOutputCountRef.current > 0
    )
      return;
    const last = currentState.decisions.at(-1);
    const previous = previousManualSelectionState(currentState);
    if (last === undefined || previous === null) return;
    busyRef.current = true;
    setBusy(true);
    setError(null);
    try {
      if (last.action === 'accepted' && outputDirectory !== null) {
        await new FileSystemManualSelectionOutputAdapter(
          outputDirectory,
        ).removeManagedOutput(last);
      }
      await persist(previous);
      const persistedRecord = recordRef.current;
      if (outputDirectory !== null && persistedRecord !== null) {
        await new FileSystemManualSelectionOutputAdapter(
          outputDirectory,
        ).writeOutputManifest({ ...persistedRecord, state: previous });
      }
      const traceImage =
        (last.imagePath === null
          ? images[currentState.currentIndex]
          : images.find((image) => image.relativePath === last.imagePath)) ??
        images[currentState.currentIndex];
      if (traceImage !== undefined) {
        await appendDecisionTrace(
          'undo',
          traceImage,
          { start: last.rangeStart, end: last.rangeEnd },
          null,
          currentState.decisions.length - 1,
        );
      }
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : 'Nie udało się cofnąć ostatniej decyzji.',
      );
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }

  async function appendDecisionTrace(
    kind: 'accepted' | 'skipped' | 'undo',
    image: ManualImageFile,
    decisionRange: { readonly start: number; readonly end: number },
    output: { readonly checksum: string; readonly name: string } | null,
    decisionOrdinal: number,
    traceRecord: ManualSelectionSessionRecord | null = recordRef.current,
  ): Promise<void> {
    if (traceRecord === null) return;
    await store.appendTraceEvent({
      decoded: true,
      decisionOrdinal: kind === 'undo' ? null : decisionOrdinal,
      eventIndex: traceEventIndexRef.current++,
      gameId: workspaceId,
      imageChecksum: output?.checksum ?? null,
      imagePath: image.relativePath,
      kind,
      outputName: output?.name ?? null,
      rangeEnd: decisionRange.end,
      rangeStart: decisionRange.start,
      recordedAt: new Date().toISOString(),
      revertsDecisionOrdinal: kind === 'undo' ? decisionOrdinal : null,
      sessionKey: traceRecord.key,
      sourceIndex: images.indexOf(image),
      visibleMilliseconds: 0,
    });
  }

  async function exportTrainingTrace(): Promise<void> {
    const currentRecord = recordRef.current;
    if (
      currentRecord === null ||
      outputDirectory === null ||
      busyRef.current ||
      acceptPreparationRef.current ||
      pendingAcceptedOutputCountRef.current > 0
    )
      return;
    setBusy(true);
    setError(null);
    try {
      const events = await store.loadTraceEvents(
        workspaceId,
        currentRecord.key,
      );
      await new FileSystemManualSelectionOutputAdapter(
        outputDirectory,
      ).writeTraceManifest(currentRecord, events);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : 'Nie udało się wyeksportować śladu selekcji.',
      );
    } finally {
      setBusy(false);
    }
  }

  function moveImage(delta: number): void {
    const currentState = stateRef.current;
    if (
      currentState === null ||
      busyRef.current ||
      acceptPreparationRef.current ||
      images.length === 0
    )
      return;
    const navigationStep = normalizeNavigationStep(currentState.navigationStep);
    const nextIndex = moveManualSelectionCursor(
      currentState.currentIndex,
      images.length,
      delta * navigationStep,
    );
    if (nextIndex === currentState.currentIndex || recordRef.current === null)
      return;
    const nextState = {
      ...currentState,
      currentIndex: nextIndex,
      updatedAt: new Date().toISOString(),
    };
    if (pendingAcceptedOutputCountRef.current > 0) {
      replaceVisibleState(nextState);
      return;
    }
    void persist(nextState);
  }

  function changeNavigationStep(value: string): void {
    const currentState = stateRef.current;
    if (
      currentState === null ||
      recordRef.current === null ||
      busyRef.current ||
      acceptPreparationRef.current
    )
      return;
    const navigationStep = normalizeNavigationStep(Number.parseInt(value, 10));
    const nextState = {
      ...currentState,
      navigationStep,
      updatedAt: new Date().toISOString(),
    };
    if (pendingAcceptedOutputCountRef.current > 0) {
      replaceVisibleState(nextState);
      return;
    }
    void persist(nextState);
  }

  function changeNavigationStepByDirection(direction: -1 | 1): void {
    const currentState = stateRef.current;
    if (
      currentState === null ||
      recordRef.current === null ||
      busyRef.current ||
      acceptPreparationRef.current
    )
      return;
    const navigationStep = adjacentManualNavigationStep(
      currentState.navigationStep,
      direction,
    );
    if (navigationStep === currentState.navigationStep) return;
    const nextState = {
      ...currentState,
      navigationStep,
      updatedAt: new Date().toISOString(),
    };
    if (pendingAcceptedOutputCountRef.current > 0) {
      replaceVisibleState(nextState);
      return;
    }
    void persist(nextState);
  }

  useEffect(() => {
    if (state === null) return undefined;
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (event.key === 'Enter' && !isEditableManualSelectionTarget(target)) {
        event.preventDefault();
        return;
      }
      if (busyRef.current || acceptPreparationRef.current || rangeEditorOpen)
        return;
      const action = resolveManualSelectionShortcut({
        altKey: event.altKey,
        ctrlKey: event.ctrlKey,
        key: event.key,
        metaKey: event.metaKey,
        repeat: event.repeat,
        target,
      });
      if (action === null) return;
      event.preventDefault();
      if (action === 'next_image') moveImage(1);
      else if (action === 'previous_image') moveImage(-1);
      else if (action === 'next_step') changeNavigationStepByDirection(1);
      else if (action === 'previous_step') changeNavigationStepByDirection(-1);
      else if (action === 'accept') void acceptCurrent();
      else if (action === 'skip') void skipCurrent();
      else void undoLast();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  });

  if (state === null || record === null) {
    return (
      <section
        className="manualImageSelectionWorkspace"
        aria-labelledby="manual-image-selection-title"
      >
        <header className="manualImageSelectionHeader">
          <div>
            <p className="eyebrow">Niezależnie od gry · lokalnie</p>
            <h1 id="manual-image-selection-title">Ręczna selekcja zdjęć</h1>
            <p>
              Wybierz pierwszą planszę i dwa foldery. Zdjęcia pozostają na
              dysku; aplikacja nie wykonuje uploadu ani OCR.
            </p>
          </div>
        </header>
        <div className="manualImageSelectionSetup">
          <label>
            Pierwsza plansza
            <input
              min="1"
              onChange={(event) => setFirstLayout(event.target.value)}
              type="number"
              value={firstLayout}
            />
            <span>
              Zakres zostanie wyliczony jako {setupRange.start}–{setupRange.end}
              .
            </span>
          </label>
          <label>
            Ostatnia plansza (opcjonalnie)
            <input
              min={firstLayout || '1'}
              onChange={(event) => setSequenceUpperBound(event.target.value)}
              placeholder="np. 500000"
              type="number"
              value={sequenceUpperBound}
            />
            <span>
              Ostatnie zdjęcie może wtedy zapisać krótszy, ciągły zakres.
            </span>
          </label>
          <label>
            Kolejność zdjęć
            <select
              onChange={(event) =>
                setDirection(event.target.value as 'ascending' | 'descending')
              }
              value={direction}
            >
              <option value="ascending">Rosnąca</option>
              <option value="descending">Malejąca</option>
            </select>
          </label>
          <div className="manualImageSelectionFolderActions">
            <button
              className="secondaryButton"
              disabled={loading || directoryPickerActive}
              onClick={() => void chooseSource()}
              type="button"
            >
              {resumeRecovery === 'source'
                ? sourceDirectory === null
                  ? 'Wybierz ponownie folder źródłowy'
                  : `Nowe źródło: ${sourceDirectory.name}`
                : sourceDirectory === null
                  ? 'Wybierz folder źródłowy'
                  : `Źródło: ${sourceDirectory.name}`}
            </button>
            <button
              className="secondaryButton"
              disabled={loading || directoryPickerActive}
              onClick={() => void chooseOutput()}
              type="button"
            >
              {resumeRecovery === 'output'
                ? outputDirectory === null
                  ? 'Wybierz ponownie folder wynikowy'
                  : `Nowy wynik: ${outputDirectory.name}`
                : outputDirectory === null
                  ? 'Wybierz folder wynikowy'
                  : `Wynik: ${outputDirectory.name}`}
            </button>
          </div>
          {loading ? (
            <p className="manualImageSelectionStatus" role="status">
              Odczytuję folder i sortuję pliki JPEG. Przy dużym folderze może to
              potrwać chwilę; nie jest wykonywany upload.
            </p>
          ) : null}
          {images.length > 0 ? (
            <p className="manualImageSelectionReady">
              Znaleziono {images.length.toLocaleString('pl-PL')} zdjęć JPG/JPEG.
            </p>
          ) : null}
          {outputDirectory !== null && !loading ? (
            <p className="manualImageSelectionStatus">
              Folder wynikowy został zapamiętany. Pliki pojawią się dopiero po
              rozpoczęciu sesji i zatwierdzeniu zdjęcia klawiszem Enter.
            </p>
          ) : null}
          <button
            className="primaryButton"
            disabled={
              loading ||
              queueRecoveryRequired ||
              resumeRecovery !== null ||
              sourceDirectory === null ||
              outputDirectory === null
            }
            onClick={() => void startSession()}
            type="button"
          >
            Rozpocznij nową sesję
          </button>
          {savedRecord !== null ? (
            <button
              className="secondaryButton"
              disabled={loading}
              onClick={() => void resumeSession()}
              type="button"
            >
              {resumeRecovery === null
                ? 'Wznów poprzednią sesję'
                : 'Wznów z ponownie wybranymi folderami'}{' '}
              ({savedRecord.state.decisions.length} decyzji, zdjęcie{' '}
              {savedRecord.state.currentIndex + 1})
            </button>
          ) : null}
          {resumeRecovery !== null ? (
            <p className="manualImageSelectionStatus" role="status">
              Postęp sesji jest bezpieczny. Wybierz ponownie folder{' '}
              {resumeRecovery === 'source' ? 'źródłowy' : 'wynikowy'} i kliknij
              przycisk wznowienia.
            </p>
          ) : null}
          {resumeNotice !== null ? (
            <p className="manualImageSelectionStatus" role="status">
              {resumeNotice}
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

  const current = images[state.currentIndex];
  const range = rangeForStart(
    state.nextRangeStart,
    state.sequenceUpperBound ?? null,
  );
  const navigationStep = normalizeNavigationStep(state.navigationStep);
  const currentImageAlreadyAccepted =
    current !== undefined &&
    hasAcceptedManualImage(state, current.relativePath);
  return (
    <section
      className="manualImageSelectionWorkspace manualImageSelectionActive"
      aria-labelledby="manual-image-selection-title"
    >
      <header className="manualImageSelectionHeader">
        <div>
          <p className="eyebrow">
            {record.sourceDirectoryName} ·{' '}
            {state.direction === 'ascending' ? 'rosnąco' : 'malejąco'}
          </p>
          <h1 id="manual-image-selection-title">Ręczna selekcja zdjęć</h1>
          <p>
            Zakres{' '}
            <button
              className="manualImageSelectionRangeButton"
              disabled={
                busy ||
                manualAcceptanceInProgress ||
                state.selectionComplete === true
              }
              onClick={openRangeEditor}
              type="button"
            >
              {range.start}–{range.end}
            </button>{' '}
            · zdjęcie {currentImagePosition} / {images.length}
          </p>
          {state.selectionComplete === true ? (
            <p className="manualImageSelectionStatus" role="status">
              {pendingAcceptedOutputCount > 0
                ? 'Osiągnięto granicę numeracji. Ostatnie wybory zapisują się jeszcze w tle.'
                : 'Osiągnięto granicę numeracji. Możesz cofnąć ostatnią decyzję albo zakończyć pracę.'}
            </p>
          ) : null}
          {rangeEditorOpen ? (
            <form
              className="manualImageSelectionRangeEditor"
              onSubmit={(event) => {
                event.preventDefault();
                void applyRangeEdit().catch((cause) =>
                  setError(
                    cause instanceof Error
                      ? cause.message
                      : 'Nie udało się zapisać zakresu.',
                  ),
                );
              }}
              role="dialog"
            >
              <label>
                Od
                <input
                  min="1"
                  onChange={(event) => setRangeStartDraft(event.target.value)}
                  type="number"
                  value={rangeStartDraft}
                />
              </label>
              <label>
                Do
                <input
                  min="1"
                  onChange={(event) => setRangeEndDraft(event.target.value)}
                  type="number"
                  value={rangeEndDraft}
                />
              </label>
              <button className="primaryButton" type="submit">
                Ustaw
              </button>
              <button
                className="secondaryButton"
                onClick={() => setRangeEditorOpen(false)}
                type="button"
              >
                Anuluj
              </button>
            </form>
          ) : null}
        </div>
        <div className="manualImageSelectionCounters" aria-live="polite">
          <span>
            zatwierdzone:{' '}
            {
              record.state.decisions.filter(
                (decision) => decision.action === 'accepted',
              ).length
            }
          </span>
          {pendingAcceptedOutputCount > 0 ? (
            <span>
              w kolejce: {pendingAcceptedOutputCount}/
              {MAXIMUM_QUEUED_MANUAL_ACCEPTS}
            </span>
          ) : null}
          <span>
            pomiń:{' '}
            {
              state.decisions.filter(
                (decision) => decision.action === 'skipped',
              ).length
            }
          </span>
        </div>
      </header>
      <ManualImageViewer
        busy={busy || acceptPreparation}
        currentLabel={`Zakres ${range.start}–${range.end}`}
        currentPosition={currentImagePosition}
        currentRelativePath={current?.relativePath ?? null}
        fullscreenExtra={
          <strong className="manualImageSelectionFullscreenQueue">
            kolejka: {pendingAcceptedOutputCount}/
            {MAXIMUM_QUEUED_MANUAL_ACCEPTS}
          </strong>
        }
        imageCount={images.length}
        navigationStepLabel={`skok strzałki: ${navigationStep}`}
        nextDisabled={
          moveManualSelectionCursor(state.currentIndex, images.length, 1) ===
          state.currentIndex
        }
        onNext={() => moveImage(1)}
        onPrevious={() => moveImage(-1)}
        previousDisabled={
          moveManualSelectionCursor(state.currentIndex, images.length, -1) ===
          state.currentIndex
        }
        state={imageViewer}
        toolbarStart={
          <label className="manualImageSelectionStep">
            Skok strzałki
            <select
              disabled={busy || acceptPreparation}
              onChange={(event) => changeNavigationStep(event.target.value)}
              value={navigationStep}
            >
              {MANUAL_IMAGE_NAVIGATION_STEPS.map((step) => (
                <option key={step} value={step}>
                  co {step}{' '}
                  {step === 1
                    ? 'zdjęcie'
                    : step >= 2 && step <= 4
                      ? 'zdjęcia'
                      : 'zdjęć'}
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
            busy ||
            manualAcceptanceInProgress ||
            record.state.decisions.length === 0
          }
          onClick={() => void undoLast()}
          type="button"
        >
          Cofnij A / Ctrl+Z
        </button>
        <button
          className="secondaryButton"
          disabled={
            busy ||
            manualAcceptanceInProgress ||
            state.selectionComplete === true
          }
          onClick={() => void skipCurrent()}
          type="button"
        >
          Pomiń Tab
        </button>
        <button
          className="primaryButton"
          disabled={
            busy ||
            acceptPreparation ||
            pendingAcceptedOutputCount >= MAXIMUM_QUEUED_MANUAL_ACCEPTS ||
            currentImageAlreadyAccepted ||
            current === undefined ||
            state.selectionComplete === true
          }
          onClick={() => void acceptCurrent()}
          type="button"
        >
          {currentImageAlreadyAccepted
            ? 'Zdjęcie już zatwierdzone — przejdź →'
            : `Zapisz F jako seq_${range.start}-${range.end}.jpg`}
        </button>
        <button
          className="secondaryButton"
          disabled={busy || manualAcceptanceInProgress}
          onClick={() => void exportTrainingTrace()}
          type="button"
        >
          Eksportuj ślad uczenia
        </button>
      </div>
      {pendingAcceptedOutputCount > 0 ? (
        <p className="manualImageSelectionStatus" role="status">
          Zapisuję wybory w tle: {pendingAcceptedOutputCount}/
          {MAXIMUM_QUEUED_MANUAL_ACCEPTS}. Możesz przejść do kolejnego zdjęcia i
          dodać następny wybór; zapisy są wykonywane po kolei.
        </p>
      ) : null}
      {currentImageAlreadyAccepted ? (
        <p className="manualImageSelectionStatus" role="status">
          To zdjęcie jest już zatwierdzone. Przejdź do kolejnego zdjęcia
          strzałką →, aby wybrać następny zakres.
        </p>
      ) : null}
      {error !== null ? (
        <p className="formError" role="alert">
          {error}
        </p>
      ) : null}
      <p className="manualImageSelectionHelp">
        ←/→ zdjęcie · F dodaje wybór do kolejki i pozostaje na zdjęciu · po
        akceptacji przejdź → · Tab pomija zakres · A/Ctrl+Z cofa ostatnią
        zapisaną decyzję
      </p>
    </section>
  );
}

async function verifyDirectoryHandle(
  directory: FileSystemDirectoryHandle,
): Promise<void> {
  await directory.entries().next();
}

async function requestPermission(
  directory: FileSystemDirectoryHandle,
  mode: 'read' | 'readwrite',
): Promise<void> {
  type PermissionDirectory = FileSystemDirectoryHandle & {
    queryPermission?: (descriptor: {
      mode: 'read' | 'readwrite';
    }) => Promise<PermissionState>;
    requestPermission?: (descriptor: {
      mode: 'read' | 'readwrite';
    }) => Promise<PermissionState>;
  };
  const handle = directory as PermissionDirectory;
  const descriptor = { mode };
  if (
    handle.queryPermission !== undefined &&
    (await handle.queryPermission(descriptor)) === 'granted'
  )
    return;
  if (
    handle.requestPermission === undefined ||
    (await handle.requestPermission(descriptor)) !== 'granted'
  ) {
    throw new Error(`Brak uprawnień do folderu ${directory.name}.`);
  }
}

function normalizeNavigationStep(value: number | undefined): number {
  return MANUAL_IMAGE_NAVIGATION_STEPS.includes(
    value as (typeof MANUAL_IMAGE_NAVIGATION_STEPS)[number],
  )
    ? (value as number)
    : 1;
}
