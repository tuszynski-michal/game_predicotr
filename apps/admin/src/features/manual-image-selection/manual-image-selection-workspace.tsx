'use client';

import { useEffect, useMemo, useRef, useState } from 'react';

import {
  createManualSelectionState,
  listManualImages,
  nextManualSelectionState,
  previousManualSelectionState,
  rangeForStart,
  removeManagedManualOutput,
  writeManualOutputManifest,
  writeManualTraceManifest,
  type ManualImageFile,
  type ManualSelectionDecision,
  type ManualSelectionSessionRecord,
  type ManualSelectionState,
  type ManualSelectionTraceEvent,
  writeManualOutput,
} from './manual-image-selection';
import { ManualImageSelectionStore } from './manual-image-selection-store';

interface ManualImageSelectionWorkspaceProps {
  readonly gameId: string;
  readonly gameName: string;
}

interface DirectoryPickerWindow extends Window {
  showDirectoryPicker?: (options?: {
    readonly mode?: 'read' | 'readwrite';
  }) => Promise<FileSystemDirectoryHandle>;
}

const CURSOR_PREFIX = 'game-predictor:manual-image-selection-cursor:';
const NAVIGATION_STEPS = [1, 2, 5, 7, 10, 15, 20] as const;

export function ManualImageSelectionWorkspace({
  gameId,
  gameName,
}: ManualImageSelectionWorkspaceProps) {
  const store = useMemo(() => new ManualImageSelectionStore(), []);
  const busyRef = useRef(false);
  const folderPickerActiveRef = useRef(false);
  const viewerRef = useRef<HTMLDivElement | null>(null);
  const stateRef = useRef<ManualSelectionState | null>(null);
  const saveQueueRef = useRef<Promise<void>>(Promise.resolve());
  const imageUrlCacheRef = useRef<Map<number, string>>(new Map());
  const imageUrlLoadRef = useRef<Map<number, Promise<string>>>(new Map());
  const imageCacheGenerationRef = useRef(0);
  const traceEventIndexRef = useRef(0);
  const viewTimerRef = useRef<number | null>(null);
  const [firstLayout, setFirstLayout] = useState('1');
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
  const [state, setState] = useState<ManualSelectionState | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [imageUrlIndex, setImageUrlIndex] = useState(-1);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [zoom, setZoom] = useState(1);
  const currentImageIndex = state?.currentIndex ?? -1;
  const currentRangeStart = state?.nextRangeStart ?? -1;

  useEffect(() => {
    let cancelled = false;
    void store
      .load(gameId)
      .then((loaded) => {
        if (!cancelled) setSavedRecord(loaded);
      })
      .catch(() => {
        if (!cancelled) setSavedRecord(null);
      });
    return () => {
      cancelled = true;
    };
  }, [gameId, store]);

  useEffect(() => {
    const cache = imageUrlCacheRef.current;
    const pendingLoads = imageUrlLoadRef.current;
    imageCacheGenerationRef.current += 1;
    for (const url of cache.values()) {
      URL.revokeObjectURL(url);
    }
    cache.clear();
    pendingLoads.clear();
    let cancelled = false;
    queueMicrotask(() => {
      if (!cancelled) {
        setImageUrl(null);
        setImageUrlIndex(-1);
      }
    });
    return () => {
      cancelled = true;
      imageCacheGenerationRef.current += 1;
      for (const url of cache.values()) {
        URL.revokeObjectURL(url);
      }
      cache.clear();
      pendingLoads.clear();
    };
  }, [images]);

  useEffect(() => {
    let cancelled = false;
    if (currentImageIndex < 0 || images[currentImageIndex] === undefined) {
      queueMicrotask(() => {
        if (!cancelled) {
          setImageUrl(null);
          setImageUrlIndex(-1);
        }
      });
      return () => {
        cancelled = true;
      };
    }

    const generation = imageCacheGenerationRef.current;
    const keepFrom = Math.max(0, currentImageIndex - 3);
    const keepTo = Math.min(images.length - 1, currentImageIndex + 3);
    for (const [index, url] of imageUrlCacheRef.current.entries()) {
      if (index < keepFrom || index > keepTo) {
        URL.revokeObjectURL(url);
        imageUrlCacheRef.current.delete(index);
      }
    }

    const loadUrl = (index: number): Promise<string> => {
      const cached = imageUrlCacheRef.current.get(index);
      if (cached !== undefined) return Promise.resolve(cached);
      const pending = imageUrlLoadRef.current.get(index);
      if (pending !== undefined) return pending;
      const image = images[index];
      if (image === undefined)
        return Promise.reject(new Error('IMAGE_OUT_OF_BOUNDS'));
      const load = image.handle
        .getFile()
        .then(async (file) => {
          const url = URL.createObjectURL(file);
          const preview = new Image();
          preview.src = url;
          await preview.decode().catch(() => undefined);
          if (generation !== imageCacheGenerationRef.current) {
            URL.revokeObjectURL(url);
            throw new Error('STALE_IMAGE_CACHE');
          }
          const latestIndex =
            stateRef.current?.currentIndex ?? currentImageIndex;
          if (Math.abs(index - latestIndex) > 3) {
            URL.revokeObjectURL(url);
            throw new Error('STALE_IMAGE_WINDOW');
          }
          imageUrlCacheRef.current.set(index, url);
          return url;
        })
        .finally(() => imageUrlLoadRef.current.delete(index));
      imageUrlLoadRef.current.set(index, load);
      return load;
    };

    const neighbours = [
      currentImageIndex + 1,
      currentImageIndex - 1,
      currentImageIndex + 2,
      currentImageIndex - 2,
      currentImageIndex + 3,
      currentImageIndex - 3,
    ].filter((index) => index >= 0 && index < images.length);

    void loadUrl(currentImageIndex)
      .then((url) => {
        if (!cancelled) {
          setImageUrl(url);
          setImageUrlIndex(currentImageIndex);
        }
      })
      .catch((cause: unknown) => {
        if (!cancelled && !isStaleImageLoad(cause)) {
          setError('Nie udało się odczytać bieżącego zdjęcia.');
        }
      })
      .finally(() => {
        if (!cancelled) {
          void Promise.allSettled(neighbours.map((index) => loadUrl(index)));
        }
      });

    return () => {
      cancelled = true;
    };
  }, [currentImageIndex, images]);

  useEffect(() => {
    const onFullscreenChange = () => {
      setIsFullscreen(document.fullscreenElement === viewerRef.current);
    };
    document.addEventListener('fullscreenchange', onFullscreenChange);
    return () =>
      document.removeEventListener('fullscreenchange', onFullscreenChange);
  }, []);

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
      `${CURSOR_PREFIX}${gameId}`,
      JSON.stringify(cursor),
    );
  }, [gameId, record, state]);

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
      imageUrlIndex !== currentImageIndex ||
      imageUrl === null
    ) {
      return;
    }
    const range = rangeForStart(currentRangeStart);
    const startedAt = performance.now();
    viewTimerRef.current = window.setTimeout(() => {
      if (stateRef.current?.currentIndex !== currentImageIndex) return;
      if (stateRef.current?.nextRangeStart !== currentRangeStart) return;
      const event: ManualSelectionTraceEvent = {
        decoded: true,
        eventIndex: traceEventIndexRef.current++,
        gameId,
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
    gameId,
    imageUrl,
    imageUrlIndex,
    images,
    record?.key,
    store,
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
      const found = await listManualImages(directory);
      if (found.length === 0)
        throw new Error('Wybrany folder nie zawiera plików JPG/JPEG.');
      setSourceDirectory(directory);
      setImages(direction === 'ascending' ? found : [...found].reverse());
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
    if (!Number.isSafeInteger(parsed) || parsed < 1) {
      setError('Pierwszy numer layoutu musi być dodatnią liczbą całkowitą.');
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
    const next = createManualSelectionState(parsed, direction);
    const nextRecord: ManualSelectionSessionRecord = {
      gameId,
      key: `${gameId}:${Date.now()}`,
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
    setLoading(true);
    try {
      await requestPermission(savedRecord.sourceDirectory, 'read');
      await requestPermission(savedRecord.outputDirectory, 'readwrite');
      const found = await listManualImages(savedRecord.sourceDirectory);
      if (found.length === 0)
        throw new Error('Folder źródłowy nie zawiera już zdjęć JPG/JPEG.');
      setSourceDirectory(savedRecord.sourceDirectory);
      setOutputDirectory(savedRecord.outputDirectory);
      setImages(
        savedRecord.state.direction === 'ascending'
          ? found
          : [...found].reverse(),
      );
      setRecord(savedRecord);
      setState(savedRecord.state);
      stateRef.current = savedRecord.state;
      const events = await store.loadTraceEvents(gameId, savedRecord.key);
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
    const nextRecord = { ...record, state: next };
    stateRef.current = next;
    setRecord(nextRecord);
    setState(next);
    const save = saveQueueRef.current
      .catch(() => undefined)
      .then(() => store.save(nextRecord));
    saveQueueRef.current = save;
    await save;
  }

  async function acceptCurrent(): Promise<void> {
    if (
      record === null ||
      stateRef.current === null ||
      outputDirectory === null ||
      busyRef.current
    )
      return;
    const currentState = stateRef.current;
    const current = images[currentState.currentIndex];
    if (current === undefined) return;
    busyRef.current = true;
    setBusy(true);
    setError(null);
    const range = rangeForStart(currentState.nextRangeStart);
    try {
      const output = await writeManualOutput(
        outputDirectory,
        current,
        range.start,
        range.end,
      );
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
        Math.min(currentState.currentIndex + 1, images.length - 1),
      );
      await persist(nextState);
      await writeManualOutputManifest(outputDirectory, {
        ...record,
        state: nextState,
      });
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
    if (record === null || currentState === null || busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    const current = images[currentState.currentIndex];
    if (current === undefined) {
      busyRef.current = false;
      setBusy(false);
      return;
    }
    const range = rangeForStart(currentState.nextRangeStart);
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
        await writeManualOutputManifest(outputDirectory, {
          ...record,
          state: nextState,
        });
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
        await removeManagedManualOutput(outputDirectory, last);
      }
      await persist(previous);
      if (outputDirectory !== null) {
        await writeManualOutputManifest(outputDirectory, {
          ...record,
          state: previous,
        });
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
      gameId,
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
      const events = await store.loadTraceEvents(gameId, record.key);
      await writeManualTraceManifest(outputDirectory, record, events);
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
    const nextIndex = Math.max(
      0,
      Math.min(
        images.length - 1,
        currentState.currentIndex + delta * navigationStep,
      ),
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

  async function toggleFullscreen(): Promise<void> {
    const viewer = viewerRef.current;
    if (viewer === null) return;
    setError(null);
    try {
      if (document.fullscreenElement === viewer) {
        await document.exitFullscreen();
      } else {
        if (document.fullscreenElement !== null)
          await document.exitFullscreen();
        await viewer.requestFullscreen();
      }
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : 'Nie udało się otworzyć podglądu pełnoekranowego.',
      );
    }
  }

  useEffect(() => {
    if (state === null) return undefined;
    const onKeyDown = (event: KeyboardEvent) => {
      if (busyRef.current) return;
      const target = event.target as HTMLElement | null;
      if (target?.tagName === 'BUTTON') return;
      if (event.key === 'ArrowRight') {
        event.preventDefault();
        moveImage(1);
      } else if (event.key === 'ArrowLeft') {
        event.preventDefault();
        moveImage(-1);
      } else if (event.key === 'Enter') {
        event.preventDefault();
        void acceptCurrent();
      } else if (event.key === 'Tab') {
        event.preventDefault();
        void skipCurrent();
      } else if (event.ctrlKey && event.key.toLowerCase() === 'z') {
        event.preventDefault();
        void undoLast();
      }
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
            <p className="eyebrow">{gameName} · lokalnie</p>
            <h1 id="manual-image-selection-title">Ręczna selekcja zdjęć</h1>
            <p>
              Wybierz pierwszy layout i dwa foldery. Zdjęcia pozostają na dysku;
              aplikacja nie wykonuje uploadu ani OCR.
            </p>
          </div>
        </header>
        <div className="manualImageSelectionSetup">
          <label>
            Pierwszy layout
            <input
              min="1"
              onChange={(event) => setFirstLayout(event.target.value)}
              type="number"
              value={firstLayout}
            />
            <span>
              Zakres zostanie wyliczony jako{' '}
              {rangeForStart(Number.parseInt(firstLayout, 10) || 1).start}–
              {rangeForStart(Number.parseInt(firstLayout, 10) || 1).end}.
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
              {sourceDirectory === null
                ? 'Wybierz folder źródłowy'
                : `Źródło: ${sourceDirectory.name}`}
            </button>
            <button
              className="secondaryButton"
              disabled={loading}
              onClick={() => void chooseOutput()}
              type="button"
            >
              {outputDirectory === null
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
              loading || sourceDirectory === null || outputDirectory === null
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
              Wznów poprzednią sesję ({savedRecord.state.decisions.length}{' '}
              decyzji, zdjęcie {savedRecord.state.currentIndex + 1})
            </button>
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
  const range = rangeForStart(state.nextRangeStart);
  const navigationStep = normalizeNavigationStep(state.navigationStep);
  const visibleImageUrl =
    imageUrlIndex === state.currentIndex ? imageUrl : null;
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
            <strong>
              {range.start}–{range.end}
            </strong>{' '}
            · zdjęcie {state.currentIndex + 1} / {images.length}
          </p>
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
      <div className="manualImageSelectionViewerToolbar">
        <label className="manualImageSelectionStep">
          Skok strzałki
          <select
            disabled={busy}
            onChange={(event) => changeNavigationStep(event.target.value)}
            value={navigationStep}
          >
            {NAVIGATION_STEPS.map((step) => (
              <option key={step} value={step}>
                co {step}{' '}
                {step === 1 ? 'zdjęcie' : step === 2 ? 'zdjęcia' : 'zdjęć'}
              </option>
            ))}
          </select>
        </label>
        <div
          className="manualImageSelectionZoom"
          aria-label="Powiększenie zdjęcia"
        >
          <button
            aria-label="Pomniejsz zdjęcie"
            className="secondaryButton"
            disabled={zoom <= 1 || busy}
            onClick={() => setZoom((value) => Math.max(1, value - 0.25))}
            type="button"
          >
            −
          </button>
          <span>{Math.round(zoom * 100)}%</span>
          <button
            aria-label="Powiększ zdjęcie"
            className="secondaryButton"
            disabled={zoom >= 2 || busy}
            onClick={() => setZoom((value) => Math.min(2, value + 0.25))}
            type="button"
          >
            +
          </button>
        </div>
        <button
          className="secondaryButton"
          disabled={busy}
          onClick={() => void toggleFullscreen()}
          type="button"
        >
          {isFullscreen ? 'Zamknij pełny ekran' : 'Pełny ekran'}
        </button>
      </div>
      <div className="manualImageSelectionViewer" ref={viewerRef}>
        <div className="manualImageSelectionFullscreenInfo" aria-live="polite">
          <strong>
            Zakres {range.start}–{range.end}
          </strong>
          <span>
            zdjęcie {state.currentIndex + 1} / {images.length}
          </span>
          <span>skok strzałki: {navigationStep}</span>
          <span>{current?.relativePath ?? 'brak zdjęcia'}</span>
        </div>
        <button
          aria-label="Poprzednie zdjęcie"
          className="manualImageSelectionNav"
          disabled={state.currentIndex === 0 || busy}
          onClick={() => moveImage(-1)}
          type="button"
        >
          ←
        </button>
        <div className="manualImageSelectionImageFrame">
          {visibleImageUrl === null ? (
            <p>Wczytywanie zdjęcia…</p>
          ) : (
            <img
              alt={current?.relativePath ?? 'Bieżące zdjęcie'}
              style={{ transform: `scale(${zoom})` }}
              src={visibleImageUrl}
            />
          )}
          <p className="manualImageSelectionFilename">
            {current?.relativePath ?? 'brak zdjęcia'}
          </p>
        </div>
        <button
          aria-label="Następne zdjęcie"
          className="manualImageSelectionNav"
          disabled={state.currentIndex >= images.length - 1 || busy}
          onClick={() => moveImage(1)}
          type="button"
        >
          →
        </button>
      </div>
      <div className="manualImageSelectionActions">
        <button
          className="secondaryButton"
          disabled={busy || state.decisions.length === 0}
          onClick={() => void undoLast()}
          type="button"
        >
          Cofnij Ctrl+Z
        </button>
        <button
          className="secondaryButton"
          disabled={busy}
          onClick={() => void skipCurrent()}
          type="button"
        >
          Pomiń Tab
        </button>
        <button
          className="primaryButton"
          disabled={busy || current === undefined}
          onClick={() => void acceptCurrent()}
          type="button"
        >
          Zapisz Enter jako seq_{range.start}-{range.end}.jpg
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
        ←/→ zdjęcie · Enter zapisuje i przechodzi dalej · Tab pomija zakres ·
        Ctrl+Z cofa ostatnią decyzję
      </p>
    </section>
  );
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

function isStaleImageLoad(cause: unknown): boolean {
  return (
    cause instanceof Error &&
    (cause.message === 'STALE_IMAGE_CACHE' ||
      cause.message === 'STALE_IMAGE_WINDOW')
  );
}

function normalizeNavigationStep(value: number | undefined): number {
  return NAVIGATION_STEPS.includes(value as (typeof NAVIGATION_STEPS)[number])
    ? (value as number)
    : 1;
}
