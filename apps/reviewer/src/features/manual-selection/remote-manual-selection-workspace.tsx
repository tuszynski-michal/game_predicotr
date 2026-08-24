'use client';

import {
  MANUAL_IMAGE_NAVIGATION_STEPS,
  adjacentManualNavigationStep,
  fitManualImageToViewport,
  resolveManualSelectionShortcut,
  type ManualImageSize,
} from '@game-predictor/manual-image-selection-core';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { RemoteSourceFileReader } from './remote-source-adapter';
import { RemoteSelectionInteractionQueue } from './remote-selection-interaction-queue';
import {
  RemoteSelectionIndexedDbStore,
  RemoteSelectionStoreError,
  remoteSelectionWorkspaceState,
  type RemoteSelectionLocalBatchRecord,
  type RemoteSelectionLocalSessionRecord,
  type RemoteSelectionSourceItemRecord,
  type RemoteSelectionWorkspaceDecision,
} from './remote-selection-store';
import { clampRemoteWorkspaceIndex } from './remote-selection-workspace-model';
import {
  removeOperatorLocalSelection,
  writeOperatorLocalManifest,
  writeOperatorLocalSelection,
} from './operator-local-selection-output';

const PREVIEW_RADIUS = 3;
const SCROLL_POSITION_KEY_PREFIX = 'gp.remote-manual-selection.scroll.v1';
const ZOOM_POSITION_KEY_PREFIX = 'gp.remote-manual-selection.zoom.v1';

export function RemoteManualSelectionWorkspace({
  batch: initialBatch,
  canWrite,
  session,
  sourceReader,
  store,
  outputDirectory,
}: {
  readonly batch: RemoteSelectionLocalBatchRecord;
  readonly canWrite: boolean;
  readonly session: RemoteSelectionLocalSessionRecord;
  readonly sourceReader: RemoteSourceFileReader | null;
  readonly store: RemoteSelectionIndexedDbStore;
  readonly outputDirectory: FileSystemDirectoryHandle;
}) {
  const initialScrollPosition = readStoredScrollPosition(
    initialBatch.sessionId,
    initialBatch.batchId,
  );
  const [batch, setBatch] = useState(initialBatch);
  const [items, setItems] = useState<
    readonly RemoteSelectionSourceItemRecord[]
  >([]);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewOrdinal, setPreviewOrdinal] = useState<number | null>(null);
  const [zoom, setZoom] = useState(() =>
    readStoredZoom(initialBatch.sessionId, initialBatch.batchId),
  );
  const [naturalImageSize, setNaturalImageSize] =
    useState<ManualImageSize | null>(null);
  const [previewViewportSize, setPreviewViewportSize] =
    useState<ManualImageSize | null>(null);
  const [decoded, setDecoded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const batchRef = useRef(batch);
  const busyRef = useRef(false);
  const operationQueue = useRef(Promise.resolve());
  const previewUrls = useRef(new Map<number, string>());
  const activePreview = useRef<{ ordinal: number; url: string } | null>(null);
  const viewport = useRef<HTMLDivElement>(null);
  const previewImage = useRef<HTMLImageElement>(null);
  const savedScrollLeft = useRef(initialScrollPosition.left);
  const savedScrollTop = useRef(initialScrollPosition.top);
  const pendingScrollRestoreOrdinal = useRef<number | null>(
    initialScrollPosition.left > 0 || initialScrollPosition.top > 0
      ? initialBatch.cursorIndex
      : null,
  );
  const viewStartedAt = useRef(performance.now());
  const viewedKey = useRef('');
  const fullscreen = useRef<HTMLDivElement>(null);

  const interactionQueue = useMemo(
    () => new RemoteSelectionInteractionQueue(),
    [],
  );
  const workspace = remoteSelectionWorkspaceState(batch);
  const current =
    items.find((item) => item.ordinal === workspace.currentIndex) ?? null;
  const currentStatus = current
    ? remoteSelectionWorkspaceState(batch).decisions.some(
        (decision) =>
          decision.action === 'accepted' && decision.fileId === current.fileId,
      )
      ? { kind: 'synced' as const, label: 'Zapisano na tym urządzeniu' }
      : { kind: 'unselected' as const, label: 'Niewybrane' }
    : { kind: 'unselected' as const, label: 'Ładowanie podglądu' };
  const hasConflict = false;
  const canEdit = canWrite;
  const acceptedCount = workspace.decisions.filter(
    (decision) => decision.action === 'accepted',
  ).length;
  const zoomedImageSize = fitManualImageToViewport(
    naturalImageSize,
    previewViewportSize,
    zoom / 100,
  );

  const changeZoom = useCallback((delta: number) => {
    setZoom((currentPercent) =>
      Math.min(3000, Math.max(100, currentPercent + delta)),
    );
  }, []);

  const captureNaturalImageSize = useCallback(
    (image: HTMLImageElement | null) => {
      if (
        image === null ||
        !image.complete ||
        image.naturalHeight < 1 ||
        image.naturalWidth < 1
      ) {
        return false;
      }
      setNaturalImageSize({
        height: image.naturalHeight,
        width: image.naturalWidth,
      });
      setDecoded(true);
      return true;
    },
    [],
  );

  useEffect(() => {
    batchRef.current = batch;
  }, [batch]);

  useEffect(() => {
    const persistScrollPosition = () => {
      if (viewport.current !== null) {
        savedScrollLeft.current = viewport.current.scrollLeft;
        savedScrollTop.current = viewport.current.scrollTop;
      }
      storeScrollPosition(
        session.sessionId,
        batchRef.current.batchId,
        savedScrollLeft.current,
        savedScrollTop.current,
      );
    };
    window.addEventListener('pagehide', persistScrollPosition);
    return () => {
      persistScrollPosition();
      window.removeEventListener('pagehide', persistScrollPosition);
    };
  }, [session.sessionId]);

  useEffect(() => {
    try {
      window.localStorage.setItem(
        viewStateKey(
          ZOOM_POSITION_KEY_PREFIX,
          session.sessionId,
          batch.batchId,
        ),
        String(zoom),
      );
    } catch {
      // The active in-memory zoom still works when browser storage is blocked.
    }
  }, [batch.batchId, session.sessionId, zoom]);

  useEffect(() => {
    const element = viewport.current;
    if (element === null) return;
    const update = () =>
      setPreviewViewportSize({
        height: element.clientHeight,
        width: element.clientWidth,
      });
    update();
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (
      previewUrl === null ||
      previewOrdinal !== workspace.currentIndex ||
      captureNaturalImageSize(previewImage.current)
    ) {
      return;
    }
    const animationFrame = window.requestAnimationFrame(() => {
      captureNaturalImageSize(previewImage.current);
    });
    return () => window.cancelAnimationFrame(animationFrame);
  }, [
    captureNaturalImageSize,
    previewOrdinal,
    previewUrl,
    workspace.currentIndex,
  ]);

  const refreshLocalState = useCallback(async () => {
    const restored = await store.restore(session.sessionId, 100);
    if (
      restored.batch === null ||
      restored.batch.batchId !== batchRef.current.batchId
    )
      return;
    const nextItems = await store.loadSourceItemsWindow(
      session.sessionId,
      restored.batch.batchId,
      restored.batch.cursorIndex,
      restored.batch.fileCount,
      PREVIEW_RADIUS,
    );
    setBatch(restored.batch);
    batchRef.current = restored.batch;
    setItems(nextItems);
  }, [session.sessionId, store]);

  useEffect(() => {
    void refreshLocalState().catch((cause) =>
      setError(localErrorMessage(cause)),
    );
  }, [refreshLocalState]);

  useEffect(() => {
    let cancelled = false;
    const keep = new Set(items.map((item) => item.ordinal));
    for (const [ordinal, url] of previewUrls.current) {
      if (!keep.has(ordinal)) {
        URL.revokeObjectURL(url);
        previewUrls.current.delete(ordinal);
      }
    }
    if (sourceReader === null) {
      queueMicrotask(() => {
        if (!cancelled) {
          activePreview.current = null;
          setPreviewUrl(null);
        }
      });
      return;
    }
    void (async () => {
      const ordered = [...items].sort(
        (left, right) =>
          Math.abs(left.ordinal - workspace.currentIndex) -
          Math.abs(right.ordinal - workspace.currentIndex),
      );
      const selectedItem = ordered.find(
        (item) => item.ordinal === workspace.currentIndex,
      );
      if (selectedItem === undefined) return;
      if (!previewUrls.current.has(selectedItem.ordinal)) {
        const file = await sourceReader.fileForEntry(selectedItem);
        if (cancelled) return;
        previewUrls.current.set(
          selectedItem.ordinal,
          URL.createObjectURL(file),
        );
      }
      const selected = previewUrls.current.get(workspace.currentIndex) ?? null;
      const previewChanged =
        selected !== null &&
        (activePreview.current?.ordinal !== workspace.currentIndex ||
          activePreview.current.url !== selected);
      if (!cancelled && previewChanged) {
        activePreview.current = {
          ordinal: workspace.currentIndex,
          url: selected,
        };
        setDecoded(false);
        setPreviewOrdinal(workspace.currentIndex);
        setPreviewUrl(selected);
      }
      for (const item of ordered) {
        if (
          cancelled ||
          item.ordinal === workspace.currentIndex ||
          previewUrls.current.has(item.ordinal)
        )
          continue;
        const file = await sourceReader.fileForEntry(item);
        if (cancelled) return;
        previewUrls.current.set(item.ordinal, URL.createObjectURL(file));
      }
    })().catch((cause) => {
      if (!cancelled) setError(localErrorMessage(cause));
    });
    return () => {
      cancelled = true;
    };
  }, [items, sourceReader, workspace.currentIndex]);

  useEffect(
    () => () => {
      for (const url of previewUrls.current.values()) URL.revokeObjectURL(url);
      previewUrls.current.clear();
    },
    [],
  );

  useEffect(() => {
    if (decoded && current !== null && previewOrdinal === current.ordinal) {
      viewStartedAt.current = performance.now();
      viewedKey.current = `${current.fileId}:${workspace.nextRangeStart}`;
    }
    return undefined;
  }, [current, decoded, previewOrdinal, workspace.nextRangeStart]);

  useEffect(() => {
    if (
      pendingScrollRestoreOrdinal.current !== workspace.currentIndex ||
      !decoded ||
      previewUrl === null ||
      previewOrdinal !== workspace.currentIndex ||
      zoomedImageSize === null
    ) {
      return;
    }
    let animationFrame = 0;
    let attempt = 0;
    const restore = () => {
      if (viewport.current === null) return;
      viewport.current.scrollLeft = savedScrollLeft.current;
      viewport.current.scrollTop = savedScrollTop.current;
      attempt += 1;
      if (attempt < 3) {
        animationFrame = window.requestAnimationFrame(restore);
        return;
      }
      pendingScrollRestoreOrdinal.current = null;
    };
    animationFrame = window.requestAnimationFrame(restore);
    return () => window.cancelAnimationFrame(animationFrame);
  }, [
    decoded,
    previewOrdinal,
    previewUrl,
    workspace.currentIndex,
    zoomedImageSize,
  ]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target instanceof HTMLElement ? event.target : null;
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
      if (action === 'accept') void acceptCurrent();
      else if (action === 'skip') void skipCurrent();
      else if (action === 'undo') void undoLast();
      else if (action === 'previous_image')
        void moveImage(-workspace.navigationStep);
      else if (action === 'next_image')
        void moveImage(workspace.navigationStep);
      else if (action === 'previous_step') void changeStep(-1);
      else if (action === 'next_step') void changeStep(1);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  });

  function enqueueOperation<T>(work: () => Promise<T>): Promise<T> {
    const result = operationQueue.current.catch(() => undefined).then(work);
    operationQueue.current = result.then(
      () => undefined,
      (cause) => setError(localErrorMessage(cause)),
    );
    return result;
  }

  async function persistCursor(nextIndex: number) {
    const currentBatch = batchRef.current;
    const next = {
      ...currentBatch,
      cursorIndex: nextIndex,
      updatedAt: new Date().toISOString(),
    };
    await store.saveBatch(next);
    capturePreviewScroll();
    armPreviewScrollRestore(nextIndex);
    setBatch(next);
    batchRef.current = next;
    setItems(
      await store.loadSourceItemsWindow(
        session.sessionId,
        next.batchId,
        nextIndex,
        next.fileCount,
        PREVIEW_RADIUS,
      ),
    );
  }

  function capturePreviewScroll(): {
    readonly left: number;
    readonly top: number;
  } {
    if (viewport.current !== null) {
      savedScrollLeft.current = viewport.current.scrollLeft;
      savedScrollTop.current = viewport.current.scrollTop;
    }
    storeScrollPosition(
      session.sessionId,
      batchRef.current.batchId,
      savedScrollLeft.current,
      savedScrollTop.current,
    );
    return {
      left: savedScrollLeft.current,
      top: savedScrollTop.current,
    };
  }

  function armPreviewScrollRestore(targetOrdinal: number) {
    pendingScrollRestoreOrdinal.current = targetOrdinal;
  }

  async function moveImage(delta: number) {
    if (busy || batch.fileCount === 0) return;
    const sourceDelta =
      batchRef.current.direction === 'ascending' ? delta : -delta;
    await persistCursor(
      clampRemoteWorkspaceIndex(
        workspace.currentIndex,
        sourceDelta,
        batch.fileCount,
      ),
    );
  }

  async function changeStep(direction: -1 | 1) {
    const currentBatch = batchRef.current;
    const next = {
      ...currentBatch,
      navigationStep: adjacentManualNavigationStep(
        remoteSelectionWorkspaceState(currentBatch).navigationStep,
        direction,
      ),
      updatedAt: new Date().toISOString(),
    };
    await store.saveBatch(next);
    setBatch(next);
    batchRef.current = next;
  }

  function acceptCurrent() {
    if (!canEdit || hasConflict || current === null || sourceReader === null)
      return;
    if (previewUrl === null || previewOrdinal !== current.ordinal || !decoded) {
      setNotice('Poczekaj, aż bieżące zdjęcie zostanie w pełni załadowane.');
      return;
    }
    const requestedCurrent = current;
    const requestedRangeStart = workspace.nextRangeStart;
    const requestedScrollPosition = capturePreviewScroll();
    const nextCursorIndex =
      batchRef.current.direction === 'ascending'
        ? Math.min(requestedCurrent.ordinal + 1, batchRef.current.fileCount - 1)
        : Math.max(requestedCurrent.ordinal - 1, 0);
    armPreviewScrollRestore(nextCursorIndex);
    void interactionQueue
      .enqueue(() =>
        acceptRequestedImage(
          requestedCurrent,
          requestedRangeStart,
          requestedScrollPosition,
          nextCursorIndex,
        ),
      )
      .catch((cause) => setError(localErrorMessage(cause)));
  }

  async function acceptRequestedImage(
    requestedCurrent: RemoteSelectionSourceItemRecord,
    requestedRangeStart: number,
    requestedScrollPosition: { readonly left: number; readonly top: number },
    nextCursorIndex: number,
  ) {
    const requestedWorkspace = remoteSelectionWorkspaceState(batchRef.current);
    if (
      requestedWorkspace.currentIndex !== requestedCurrent.ordinal ||
      requestedWorkspace.nextRangeStart !== requestedRangeStart
    ) {
      setNotice(
        'To polecenie nie zostało zapisane, ponieważ ekran zdążył się zmienić.',
      );
      return;
    }
    if (
      requestedWorkspace.decisions.some(
        (decision) =>
          decision.action === 'accepted' &&
          decision.fileId === requestedCurrent.fileId,
      )
    ) {
      setError(
        'To zdjęcie jest już przypisane do zaakceptowanego zakresu. Cofnij decyzję albo wybierz inne zdjęcie.',
      );
      return;
    }
    savedScrollLeft.current = requestedScrollPosition.left;
    savedScrollTop.current = requestedScrollPosition.top;
    busyRef.current = true;
    setBusy(true);
    setError('');
    try {
      if (sourceReader === null) return;
      const file = await sourceReader.fileForEntry(requestedCurrent);
      const output = await writeOperatorLocalSelection(
        outputDirectory,
        file,
        requestedRangeStart,
      );
      const decision: RemoteSelectionWorkspaceDecision = {
        action: 'accepted',
        fileId: requestedCurrent.fileId,
        imageChecksumSha256: output.checksumSha256,
        imagePath: requestedCurrent.relativePath,
        operationId: crypto.randomUUID(),
        outputName: output.name,
        rangeEnd: requestedRangeStart + 8,
        rangeStart: requestedRangeStart,
        selectionGeneration: 1,
        sourceIndex: requestedCurrent.ordinal,
      };
      let nextBatch: RemoteSelectionLocalBatchRecord;
      try {
        nextBatch = await store.appendLocalWorkspaceDecision({
          batchId: batchRef.current.batchId,
          decision,
          nextCursorIndex,
          sessionId: session.sessionId,
        });
      } catch (cause) {
        if (output.created) {
          await removeOperatorLocalSelection(outputDirectory, decision).catch(
            () => undefined,
          );
        }
        throw cause;
      }
      setBatch(nextBatch);
      batchRef.current = nextBatch;
      await persistOperatorLocalManifest(nextBatch);
      setNotice(`Zapisano ${output.name} na urządzeniu operatora.`);
      await refreshLocalState();
    } catch (cause) {
      if (
        batchRef.current.cursorIndex === requestedCurrent.ordinal &&
        pendingScrollRestoreOrdinal.current === nextCursorIndex
      ) {
        pendingScrollRestoreOrdinal.current = null;
        window.requestAnimationFrame(() => {
          if (viewport.current === null) return;
          viewport.current.scrollLeft = requestedScrollPosition.left;
          viewport.current.scrollTop = requestedScrollPosition.top;
        });
      }
      setError(localErrorMessage(cause));
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }

  function skipCurrent() {
    if (!canEdit || hasConflict || current === null) return;
    const requestedCurrent = current;
    const requestedRangeStart = workspace.nextRangeStart;
    void interactionQueue
      .enqueue(() => skipRequestedRange(requestedCurrent, requestedRangeStart))
      .catch((cause) => setError(localErrorMessage(cause)));
  }

  async function skipRequestedRange(
    requestedCurrent: RemoteSelectionSourceItemRecord,
    requestedRangeStart: number,
  ) {
    const requestedWorkspace = remoteSelectionWorkspaceState(batchRef.current);
    if (
      requestedWorkspace.currentIndex !== requestedCurrent.ordinal ||
      requestedWorkspace.nextRangeStart !== requestedRangeStart
    ) {
      setNotice(
        'To pominięcie nie zostało zapisane, ponieważ ekran zdążył się zmienić.',
      );
      return;
    }
    busyRef.current = true;
    setBusy(true);
    setError('');
    try {
      const nextBatch = await enqueueOperation(async () => {
        const latest = remoteSelectionWorkspaceState(batchRef.current);
        if (
          latest.currentIndex !== requestedCurrent.ordinal ||
          latest.nextRangeStart !== requestedRangeStart
        ) {
          throw new RemoteSelectionStoreError(
            'REMOTE_SELECTION_WORKSPACE_STALE',
            'The local workspace changed before the requested skip was persisted.',
          );
        }
        const operationId = crypto.randomUUID();
        return store.appendLocalWorkspaceDecision({
          batchId: batchRef.current.batchId,
          decision: {
            action: 'skipped',
            fileId: null,
            imageChecksumSha256: null,
            imagePath: null,
            operationId,
            outputName: null,
            rangeEnd: requestedRangeStart + 8,
            rangeStart: requestedRangeStart,
            selectionGeneration: 0,
            sourceIndex: requestedCurrent.ordinal,
          },
          nextCursorIndex: requestedCurrent.ordinal,
          sessionId: session.sessionId,
        });
      });
      setBatch(nextBatch);
      batchRef.current = nextBatch;
      setNotice(
        `Pominięto zakres ${requestedRangeStart}–${requestedRangeStart + 8}.`,
      );
      await persistOperatorLocalManifest(nextBatch);
      await refreshLocalState();
    } catch (cause) {
      setError(localErrorMessage(cause));
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }

  function undoLast() {
    if (!canEdit || hasConflict) return;
    const latest = remoteSelectionWorkspaceState(batchRef.current);
    const last = latest.decisions.at(-1);
    if (last === undefined) return;
    void interactionQueue
      .enqueue(() => undoRequestedDecision(last.operationId))
      .catch((cause) => setError(localErrorMessage(cause)));
  }

  async function undoRequestedDecision(targetOperationId: string) {
    const latest = remoteSelectionWorkspaceState(batchRef.current);
    const last = latest.decisions.at(-1);
    if (last === undefined || last.operationId !== targetOperationId) {
      setNotice(
        'Cofnięcie nie zostało wykonane, ponieważ ostatnia decyzja zdążyła się zmienić.',
      );
      return;
    }
    busyRef.current = true;
    setBusy(true);
    setError('');
    try {
      if (last.action === 'accepted' && last.fileId !== null) {
        await removeOperatorLocalSelection(outputDirectory, last);
      }
      const nextBatch = await enqueueOperation(async () => {
        const currentLast = remoteSelectionWorkspaceState(
          batchRef.current,
        ).decisions.at(-1);
        if (currentLast?.operationId !== targetOperationId) {
          throw new RemoteSelectionStoreError(
            'REMOTE_SELECTION_WORKSPACE_STALE',
            'The last decision changed before undo was persisted.',
          );
        }
        return store.undoLastLocalWorkspaceDecision({
          batchId: batchRef.current.batchId,
          expectedOperationId: last.operationId,
          sessionId: session.sessionId,
        });
      });
      if (nextBatch !== null) {
        capturePreviewScroll();
        armPreviewScrollRestore(nextBatch.cursorIndex);
        setBatch(nextBatch);
        batchRef.current = nextBatch;
        setNotice(`Cofnięto zakres ${last.rangeStart}–${last.rangeEnd}.`);
        await persistOperatorLocalManifest(nextBatch);
        await refreshLocalState();
      }
    } catch (cause) {
      setError(localErrorMessage(cause));
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }

  async function toggleFullscreen() {
    if (document.fullscreenElement === fullscreen.current) {
      await document.exitFullscreen();
    } else {
      await fullscreen.current?.requestFullscreen();
    }
  }

  async function persistOperatorLocalManifest(
    currentBatch: RemoteSelectionLocalBatchRecord,
  ) {
    const state = remoteSelectionWorkspaceState(currentBatch);
    await writeOperatorLocalManifest(outputDirectory, {
      batchId: currentBatch.batchId,
      currentIndex: state.currentIndex,
      decisions: state.decisions,
      direction: currentBatch.direction,
      fileCount: currentBatch.fileCount,
      firstLayout: currentBatch.firstLayout,
      nextRangeStart: state.nextRangeStart,
      sessionId: session.sessionId,
      sourceDirectoryName: currentBatch.sourceDirectoryName,
      sourceManifestChecksumSha256: currentBatch.sourceManifestChecksumSha256,
    });
  }

  return (
    <section
      className="remoteManualWorkspace manualImageSelectionWorkspace manualImageSelectionActive"
      aria-live="polite"
    >
      <p className="remoteWorkspaceBanner">
        Tryb lokalny operatora: zdjęcia, decyzje, pozycja i ustawienia widoku
        pozostają na tym urządzeniu. Folder wynikowy:{' '}
        {session.outputDirectoryName}.
      </p>
      <header className="remoteManualWorkspaceHeader manualImageSelectionHeader">
        <div>
          <p className="eyebrow">
            {batch.sourceDirectoryName} · {batch.collectionName} /{' '}
            {batch.batchName}
          </p>
          <h1>Ręczna selekcja zdjęć</h1>
          <p>
            Zakres{' '}
            <strong>
              {workspace.nextRangeStart}–{workspace.nextRangeStart + 8}
            </strong>{' '}
            · zdjęcie {workspace.currentIndex + 1} / {batch.fileCount}
          </p>
        </div>
        <div className="manualImageSelectionCounters">
          <span>zatwierdzone: {acceptedCount}</span>
          <span>decyzje: {workspace.decisions.length}</span>
          <span
            className={`remoteSyncBadge remoteSyncBadge--${currentStatus.kind}`}
          >
            {currentStatus.label}
          </span>
        </div>
      </header>

      <div className="manualImageSelectionViewerToolbar">
        <label className="manualImageSelectionStep">
          Skok strzałki
          <select
            id="remote-navigation-step"
            onChange={(event) => {
              const value = Number(event.target.value);
              const next = {
                ...batchRef.current,
                navigationStep: value,
                updatedAt: new Date().toISOString(),
              };
              void store.saveBatch(next).then(() => {
                setBatch(next);
                batchRef.current = next;
              });
            }}
            value={workspace.navigationStep}
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
        <div
          className="manualImageSelectionZoom"
          aria-label="Powiększenie zdjęcia"
        >
          <button
            aria-label="Pomniejsz zdjęcie"
            className="secondaryButton"
            disabled={zoom <= 100 || busy}
            onClick={() => changeZoom(-25)}
            type="button"
          >
            −
          </button>
          <span>{zoom}%</span>
          <button
            aria-label="Powiększ zdjęcie"
            className="secondaryButton"
            disabled={zoom >= 3000 || busy}
            onClick={() => changeZoom(25)}
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
          Pełny ekran
        </button>
      </div>

      <div className="remoteManualWorkspaceGrid">
        <div
          className="remoteManualPreview manualImageSelectionViewer"
          ref={fullscreen}
        >
          <div
            className="manualImageSelectionFullscreenInfo"
            aria-live="polite"
          >
            <strong>
              Zakres {workspace.nextRangeStart}–{workspace.nextRangeStart + 8}
            </strong>
            <span>
              zdjęcie {workspace.currentIndex + 1} / {batch.fileCount}
            </span>
            <span>skok strzałki: {workspace.navigationStep}</span>
            <span>{current?.relativePath ?? 'brak zdjęcia'}</span>
          </div>
          <button
            aria-label="Poprzednie zdjęcie"
            className="manualImageSelectionNav"
            disabled={workspace.currentIndex === 0 || busy}
            onClick={() => void moveImage(-workspace.navigationStep)}
            type="button"
          >
            ←
          </button>
          <div className="manualImageSelectionImageFrame">
            <div
              className="remoteManualPreviewViewport manualImageSelectionImageViewport"
              onScroll={(event) => {
                if (pendingScrollRestoreOrdinal.current === null) {
                  savedScrollLeft.current = event.currentTarget.scrollLeft;
                  savedScrollTop.current = event.currentTarget.scrollTop;
                }
              }}
              ref={viewport}
            >
              {previewUrl === null ? (
                <p>Ładowanie lokalnego JPEG-a…</p>
              ) : (
                <div
                  className="remoteManualPreviewCanvas manualImageSelectionImageCanvas"
                  style={
                    zoomedImageSize === null
                      ? undefined
                      : {
                          height: `${zoomedImageSize.height}px`,
                          width: `${zoomedImageSize.width}px`,
                        }
                  }
                >
                  <img
                    alt={`Lokalny podgląd ${current?.name ?? 'JPEG'}`}
                    draggable={false}
                    ref={previewImage}
                    src={previewUrl}
                    onLoad={(event) =>
                      captureNaturalImageSize(event.currentTarget)
                    }
                  />
                </div>
              )}
            </div>
            <p className="manualImageSelectionFilename">
              {current?.relativePath ?? 'brak zdjęcia'}
            </p>
            <p className="remoteManualShortcutHelp">
              ←/→ zdjęcie · ↑/↓ skok · Enter/F zatwierdź · Tab pomiń · A/Ctrl+Z
              cofnij
            </p>
          </div>
          <button
            aria-label="Następne zdjęcie"
            className="manualImageSelectionNav"
            disabled={workspace.currentIndex >= batch.fileCount - 1 || busy}
            onClick={() => void moveImage(workspace.navigationStep)}
            type="button"
          >
            →
          </button>
        </div>
      </div>

      <footer className="remoteManualActions manualImageSelectionActions">
        <button
          className="secondaryButton"
          disabled={
            !canEdit || busy || hasConflict || workspace.decisions.length === 0
          }
          onClick={() => void undoLast()}
          type="button"
        >
          Cofnij A / Ctrl+Z
        </button>
        <button
          className="secondaryButton"
          disabled={!canEdit || busy || hasConflict}
          onClick={() => void skipCurrent()}
          type="button"
        >
          Pomiń Tab
        </button>
        <button
          className="primaryButton"
          disabled={!canEdit || hasConflict || sourceReader === null}
          onClick={() => void acceptCurrent()}
          type="button"
        >
          {`Zapisz Enter/F jako seq_${workspace.nextRangeStart}-${workspace.nextRangeStart + 8}.jpg`}
        </button>
      </footer>
      {notice ? <p>{notice}</p> : null}
      {error ? (
        <p className="reviewerAccessError" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  );
}

function scrollPositionKey(sessionId: string, batchId: string): string {
  return viewStateKey(SCROLL_POSITION_KEY_PREFIX, sessionId, batchId);
}

export function clearRemoteManualSelectionScroll(
  sessionId: string,
  batchId: string,
): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(scrollPositionKey(sessionId, batchId));
  } catch {
    // A blocked localStorage cannot prevent a safe restart of file decisions.
  }
}

function viewStateKey(prefix: string, sessionId: string, batchId: string) {
  return `${prefix}:${sessionId}:${batchId}`;
}

function readStoredZoom(sessionId: string, batchId: string): number {
  if (typeof window === 'undefined') return 100;
  try {
    const parsed = Number.parseInt(
      window.localStorage.getItem(
        viewStateKey(ZOOM_POSITION_KEY_PREFIX, sessionId, batchId),
      ) ?? '100',
      10,
    );
    return Number.isFinite(parsed)
      ? Math.min(3000, Math.max(100, parsed))
      : 100;
  } catch {
    return 100;
  }
}

function readStoredScrollPosition(
  sessionId: string,
  batchId: string,
): { readonly left: number; readonly top: number } {
  if (typeof window === 'undefined') return { left: 0, top: 0 };
  try {
    const raw = window.localStorage.getItem(
      scrollPositionKey(sessionId, batchId),
    );
    if (raw === null) return { left: 0, top: 0 };
    const value = JSON.parse(raw) as { left?: unknown; top?: unknown };
    return {
      left: storedScrollOffset(value.left),
      top: storedScrollOffset(value.top),
    };
  } catch {
    return { left: 0, top: 0 };
  }
}

function storeScrollPosition(
  sessionId: string,
  batchId: string,
  left: number,
  top: number,
): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(
      scrollPositionKey(sessionId, batchId),
      JSON.stringify({
        left: storedScrollOffset(left),
        top: storedScrollOffset(top),
      }),
    );
  } catch {
    // Scroll persistence is best effort and cannot block photo decisions.
  }
}

function storedScrollOffset(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0
    ? Math.round(value)
    : 0;
}

function localErrorMessage(cause: unknown): string {
  if (cause instanceof RemoteSelectionStoreError)
    return `${cause.message} (${cause.code})`;
  return cause instanceof Error
    ? cause.message
    : 'Nie udało się wykonać lokalnej operacji.';
}
