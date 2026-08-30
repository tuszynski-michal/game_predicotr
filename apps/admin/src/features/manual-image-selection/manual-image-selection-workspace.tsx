'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

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
import { readRepairManifest } from './manual-selection-repair-storage.ts';

interface DirectoryPickerWindow extends Window {
  showDirectoryPicker?: (options?: {
    readonly mode?: 'read' | 'readwrite';
  }) => Promise<FileSystemDirectoryHandle>;
}

type ResumeRecoveryTarget = 'source' | 'output';

const CURSOR_PREFIX = 'game-predictor:manual-image-selection-cursor:';

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
    </div>
  );
}

function LocalManualImageSelectionWorkspace() {
  const workspaceId = INDEPENDENT_MANUAL_SELECTION_ID;
  const store = useMemo(() => new ManualImageSelectionStore(), []);
  const busyRef = useRef(false);
  const folderPickerActiveRef = useRef(false);
  const stateRef = useRef<ManualSelectionState | null>(null);
  const saveQueueRef = useRef<Promise<void>>(Promise.resolve());
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
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resumeNotice, setResumeNotice] = useState<string | null>(null);
  const [resumeRecovery, setResumeRecovery] =
    useState<ResumeRecoveryTarget | null>(null);
  const [state, setState] = useState<ManualSelectionState | null>(null);
  const [rangeEditorOpen, setRangeEditorOpen] = useState(false);
  const [rangeStartDraft, setRangeStartDraft] = useState('');
  const [rangeEndDraft, setRangeEndDraft] = useState('');
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
    if (record === null || state === null) return;
    const cursor = {
      currentIndex: state.currentIndex,
      direction: state.direction,
      firstLayout: state.firstLayout,
      nextRangeStart: state.nextRangeStart,
      sourceDirectoryName: record.sourceDirectoryName,
      updatedAt: state.updatedAt,
    };
    window.localStorage.setItem(
      `${CURSOR_PREFIX}${workspaceId}`,
      JSON.stringify(cursor),
    );
  }, [record, state, workspaceId]);

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
    const picker = (window as DirectoryPickerWindow).showDirectoryPicker;
    if (picker === undefined) {
      throw new Error(
        'Ta przeglądarka nie obsługuje wyboru folderu lokalnego.',
      );
    }
    if (folderPickerActiveRef.current) {
      throw new Error(
        'Wybór folderu jest już aktywny. Zamknij bieżące okno wyboru folderu i spróbuj ponownie.',
      );
    }
    folderPickerActiveRef.current = true;
    try {
      return await picker({ mode });
    } catch (cause) {
      if (
        cause instanceof DOMException &&
        (cause.name === 'InvalidStateError' ||
          cause.message.toLowerCase().includes('file picker already active'))
      ) {
        throw new Error(
          'Okno wyboru folderu jest już otwarte. Zamknij je i spróbuj ponownie.',
        );
      }
      throw cause;
    } finally {
      folderPickerActiveRef.current = false;
    }
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
      setRecord(null);
      setState(null);
      stateRef.current = null;
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
    setRecord(nextRecord);
    setState(next);
    stateRef.current = next;
    setSavedRecord(null);
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
      setSavedRecord(synchronizedRecord);
      setSourceDirectory(sourceHandle);
      setOutputDirectory(outputHandle);
      setImages(found);
      setRecord(synchronizedRecord);
      setState(resumedState);
      stateRef.current = resumedState;
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
    if (record === null) return;
    const nextRecord = {
      ...record,
      cursorImagePath:
        images[next.currentIndex]?.relativePath ?? record.cursorImagePath,
      cursorSemantics: MANUAL_SELECTION_CURSOR_SEMANTICS,
      state: next,
    };
    stateRef.current = next;
    setRecord(nextRecord);
    setState(next);
    const save = saveQueueRef.current
      .catch(() => undefined)
      .then(() => store.save(nextRecord));
    saveQueueRef.current = save;
    await save;
  }

  function openRangeEditor(): void {
    const currentState = stateRef.current;
    if (currentState === null) return;
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
      record === null ||
      stateRef.current === null ||
      outputDirectory === null ||
      busyRef.current ||
      stateRef.current.selectionComplete === true
    )
      return;
    const currentState = stateRef.current;
    const current = images[currentState.currentIndex];
    if (current === undefined) return;
    busyRef.current = true;
    setBusy(true);
    setError(null);
    const range = rangeForStart(
      currentState.nextRangeStart,
      currentState.sequenceUpperBound ?? null,
    );
    try {
      const output = await new FileSystemManualSelectionOutputAdapter(
        outputDirectory,
      ).writeAcceptedOutput(current, range.start, range.end);
      const decision: ManualSelectionDecision = {
        action: 'accepted',
        imageChecksum: output.checksum,
        imagePath: current.relativePath,
        outputName: output.name,
        rangeEnd: range.end,
        rangeStart: range.start,
      };
      const nextState = nextManualSelectionState(
        currentState,
        decision,
        moveManualSelectionCursor(currentState.currentIndex, images.length, 1),
      );
      await persist(nextState);
      await new FileSystemManualSelectionOutputAdapter(
        outputDirectory,
      ).writeOutputManifest({ ...record, state: nextState });
      await appendDecisionTrace(
        'accepted',
        current,
        range,
        output,
        currentState.decisions.length,
      );
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : 'Nie udało się zapisać zdjęcia.',
      );
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }

  async function skipCurrent(): Promise<void> {
    const currentState = stateRef.current;
    if (
      record === null ||
      currentState === null ||
      busyRef.current ||
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
      if (outputDirectory !== null) {
        await new FileSystemManualSelectionOutputAdapter(
          outputDirectory,
        ).writeOutputManifest({ ...record, state: nextState });
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
    if (record === null || currentState === null || busyRef.current) return;
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
      if (outputDirectory !== null) {
        await new FileSystemManualSelectionOutputAdapter(
          outputDirectory,
        ).writeOutputManifest({ ...record, state: previous });
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
  ): Promise<void> {
    if (record === null) return;
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
      sessionKey: record.key,
      sourceIndex: images.indexOf(image),
      visibleMilliseconds: 0,
    });
  }

  async function exportTrainingTrace(): Promise<void> {
    if (record === null || outputDirectory === null || busyRef.current) return;
    setBusy(true);
    setError(null);
    try {
      const events = await store.loadTraceEvents(workspaceId, record.key);
      await new FileSystemManualSelectionOutputAdapter(
        outputDirectory,
      ).writeTraceManifest(record, events);
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
    if (currentState === null || busyRef.current || images.length === 0) return;
    const navigationStep = normalizeNavigationStep(currentState.navigationStep);
    const nextIndex = moveManualSelectionCursor(
      currentState.currentIndex,
      images.length,
      delta * navigationStep,
    );
    if (nextIndex === currentState.currentIndex || record === null) return;
    void persist({
      ...currentState,
      currentIndex: nextIndex,
      updatedAt: new Date().toISOString(),
    });
  }

  function changeNavigationStep(value: string): void {
    const currentState = stateRef.current;
    if (currentState === null || record === null || busyRef.current) return;
    const navigationStep = normalizeNavigationStep(Number.parseInt(value, 10));
    void persist({
      ...currentState,
      navigationStep,
      updatedAt: new Date().toISOString(),
    });
  }

  function changeNavigationStepByDirection(direction: -1 | 1): void {
    const currentState = stateRef.current;
    if (currentState === null || record === null || busyRef.current) return;
    const navigationStep = adjacentManualNavigationStep(
      currentState.navigationStep,
      direction,
    );
    if (navigationStep === currentState.navigationStep) return;
    void persist({
      ...currentState,
      navigationStep,
      updatedAt: new Date().toISOString(),
    });
  }

  useEffect(() => {
    if (state === null) return undefined;
    const onKeyDown = (event: KeyboardEvent) => {
      if (busyRef.current || rangeEditorOpen) return;
      const action = resolveManualSelectionShortcut({
        altKey: event.altKey,
        ctrlKey: event.ctrlKey,
        key: event.key,
        metaKey: event.metaKey,
        repeat: event.repeat,
        target: event.target as HTMLElement | null,
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
              disabled={loading}
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
              disabled={loading}
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
              disabled={busy || state.selectionComplete === true}
              onClick={openRangeEditor}
              type="button"
            >
              {range.start}–{range.end}
            </button>{' '}
            · zdjęcie {currentImagePosition} / {images.length}
          </p>
          {state.selectionComplete === true ? (
            <p className="manualImageSelectionStatus" role="status">
              Osiągnięto granicę numeracji. Możesz cofnąć ostatnią decyzję albo
              zakończyć pracę.
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
              state.decisions.filter(
                (decision) => decision.action === 'accepted',
              ).length
            }
          </span>
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
        busy={busy}
        currentLabel={`Zakres ${range.start}–${range.end}`}
        currentPosition={currentImagePosition}
        currentRelativePath={current?.relativePath ?? null}
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
              disabled={busy}
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
          disabled={busy || state.decisions.length === 0}
          onClick={() => void undoLast()}
          type="button"
        >
          Cofnij A / Ctrl+Z
        </button>
        <button
          className="secondaryButton"
          disabled={busy || state.selectionComplete === true}
          onClick={() => void skipCurrent()}
          type="button"
        >
          Pomiń Tab
        </button>
        <button
          className="primaryButton"
          disabled={
            busy || current === undefined || state.selectionComplete === true
          }
          onClick={() => void acceptCurrent()}
          type="button"
        >
          Zapisz Enter/F jako seq_{range.start}-{range.end}.jpg
        </button>
        <button
          className="secondaryButton"
          disabled={busy}
          onClick={() => void exportTrainingTrace()}
          type="button"
        >
          Eksportuj ślad uczenia
        </button>
      </div>
      {error !== null ? (
        <p className="formError" role="alert">
          {error}
        </p>
      ) : null}
      <p className="manualImageSelectionHelp">
        ←/→ zdjęcie · Enter/F zapisuje i przechodzi dalej · Tab pomija zakres ·
        A/Ctrl+Z cofa ostatnią decyzję
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
