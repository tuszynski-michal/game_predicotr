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
  type RemoteSelectionOutboxRecord,
  type RemoteSelectionSourceItemRecord,
  type RemoteSelectionTransferCheckpointRecord,
  type RemoteSelectionWorkspaceDecision,
} from './remote-selection-store';
import {
  FetchRemoteSelectionControlTransport,
  nextRemoteSelectionPollDelay,
  RemoteSelectionControlApiError,
  RemoteSelectionSyncCoordinator,
  type RemoteSelectionFinalizePreview,
  type RemoteSelectionStateDeltaResponse,
  RemoteSelectionOutboxSynchronizer,
} from './remote-selection-sync';
import {
  FetchRemoteSelectionTransferTransport,
  RemoteSelectionTransferHttpError,
  RemoteSelectionTransferScheduler,
} from './remote-selection-transfer-scheduler';
import {
  advanceRemoteTransferScanCursor,
  buildRemoteWorkspaceCommand,
  clampRemoteWorkspaceIndex,
  remoteOutputName,
  remoteWorkspaceItemStatus,
  sha256File,
} from './remote-selection-workspace-model';

const PREVIEW_RADIUS = 3;

export function RemoteManualSelectionWorkspace({
  batch: initialBatch,
  canWrite,
  clientInstanceId,
  session,
  sourceReader,
  store,
}: {
  readonly batch: RemoteSelectionLocalBatchRecord;
  readonly canWrite: boolean;
  readonly clientInstanceId: string;
  readonly session: RemoteSelectionLocalSessionRecord;
  readonly sourceReader: RemoteSourceFileReader | null;
  readonly store: RemoteSelectionIndexedDbStore;
}) {
  const [batch, setBatch] = useState(initialBatch);
  const [items, setItems] = useState<
    readonly RemoteSelectionSourceItemRecord[]
  >([]);
  const [outbox, setOutbox] = useState<readonly RemoteSelectionOutboxRecord[]>(
    [],
  );
  const [currentOutbox, setCurrentOutbox] =
    useState<RemoteSelectionOutboxRecord | null>(null);
  const [currentCheckpoint, setCurrentCheckpoint] =
    useState<RemoteSelectionTransferCheckpointRecord | null>(null);
  const [pendingCount, setPendingCount] = useState(0);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewOrdinal, setPreviewOrdinal] = useState<number | null>(null);
  const [zoom, setZoom] = useState(100);
  const [naturalImageSize, setNaturalImageSize] =
    useState<ManualImageSize | null>(null);
  const [previewViewportSize, setPreviewViewportSize] =
    useState<ManualImageSize | null>(null);
  const [decoded, setDecoded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [backpressure, setBackpressure] = useState(false);
  const [finalizePreview, setFinalizePreview] =
    useState<RemoteSelectionFinalizePreview | null>(null);
  const [finalizing, setFinalizing] = useState(false);
  const [remoteStatus, setRemoteStatus] =
    useState<RemoteSelectionStateDeltaResponse | null>(null);
  const [transferSnapshot, setTransferSnapshot] = useState({
    active: 0,
    pendingBytes: 0,
    queued: 0,
  });
  const batchRef = useRef(batch);
  const pendingCountRef = useRef(0);
  const transferPendingRef = useRef(0);
  const busyRef = useRef(false);
  const finalizingRef = useRef(false);
  const finalizationRequestedRef = useRef(false);
  const resumeTransferAfterOrdinal = useRef(-1);
  const operationQueue = useRef(Promise.resolve());
  const previewUrls = useRef(new Map<number, string>());
  const viewport = useRef<HTMLDivElement>(null);
  const savedScrollLeft = useRef(0);
  const savedScrollTop = useRef(0);
  const pendingScrollRestore = useRef(false);
  const viewStartedAt = useRef(performance.now());
  const viewedKey = useRef('');
  const fullscreen = useRef<HTMLDivElement>(null);

  const controlTransport = useMemo(
    () => new FetchRemoteSelectionControlTransport(clientInstanceId),
    [clientInstanceId],
  );
  const synchronizer = useMemo(
    () => new RemoteSelectionOutboxSynchronizer(store, controlTransport),
    [controlTransport, store],
  );
  const transferScheduler = useMemo(
    () =>
      new RemoteSelectionTransferScheduler(
        new FetchRemoteSelectionTransferTransport(clientInstanceId),
        store,
      ),
    [clientInstanceId, store],
  );
  const interactionQueue = useMemo(
    () => new RemoteSelectionInteractionQueue(),
    [],
  );
  const syncCoordinator = useMemo(
    () => new RemoteSelectionSyncCoordinator(),
    [],
  );
  const workspace = remoteSelectionWorkspaceState(batch);
  const current =
    items.find((item) => item.ordinal === workspace.currentIndex) ?? null;
  const currentStatus = current
    ? remoteWorkspaceItemStatus({
        decisions: workspace.decisions,
        item: current,
        outbox: currentOutbox === null ? outbox : [currentOutbox],
        checkpoint: currentCheckpoint,
      })
    : { kind: 'unselected' as const, label: 'Ładowanie podglądu' };
  const hasConflict = outbox.some(
    (operation) => operation.state === 'conflict',
  );
  const completed = batch.status === 'completed';
  const canEdit = canWrite && !completed && !finalizing;
  const acceptedCount = workspace.decisions.filter(
    (decision) => decision.action === 'accepted',
  ).length;
  const zoomedImageSize = fitManualImageToViewport(
    naturalImageSize,
    previewViewportSize,
    zoom / 100,
  );

  useEffect(() => {
    batchRef.current = batch;
  }, [batch]);

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
    setOutbox(restored.pendingOperations);
    setPendingCount(restored.pendingOperationCount);
    pendingCountRef.current = restored.pendingOperationCount;
    const restoredWorkspace = remoteSelectionWorkspaceState(restored.batch);
    const restoredCurrent = nextItems.find(
      (item) => item.ordinal === restoredWorkspace.currentIndex,
    );
    const currentDecision = [...restoredWorkspace.decisions]
      .reverse()
      .find(
        (decision) =>
          decision.action === 'accepted' &&
          decision.fileId === restoredCurrent?.fileId,
      );
    setCurrentOutbox(
      currentDecision === undefined
        ? null
        : await store.loadOutboxOperation(
            session.sessionId,
            restored.batch.batchId,
            currentDecision.operationId,
          ),
    );
    setCurrentCheckpoint(
      currentDecision?.fileId === null || currentDecision === undefined
        ? null
        : await store.loadTransferCheckpoint(
            session.sessionId,
            restored.batch.batchId,
            currentDecision.fileId,
            currentDecision.selectionGeneration,
          ),
    );
  }, [session.sessionId, store]);

  const enqueueConfirmedTransfer = useCallback(
    async (decision: RemoteSelectionWorkspaceDecision) => {
      if (
        decision.action !== 'accepted' ||
        decision.fileId === null ||
        decision.imageChecksumSha256 === null ||
        sourceReader === null
      )
        return true;
      const item = await store.loadSourceItem(
        session.sessionId,
        batchRef.current.batchId,
        decision.sourceIndex,
      );
      if (
        item === null ||
        item.fileId !== decision.fileId ||
        item.desiredSelected !== true ||
        item.selectionGeneration !== decision.selectionGeneration ||
        item.serverStatus === 'synced'
      )
        return true;
      try {
        await transferScheduler.enqueue({
          batchId: batchRef.current.batchId,
          expectedChecksumSha256: decision.imageChecksumSha256,
          expectedLastModifiedMs: item.lastModifiedMs,
          expectedSizeBytes: item.sizeBytes,
          fileId: item.fileId,
          generation: decision.selectionGeneration,
          loadBlob: async () => sourceReader.fileForEntry(item),
          priority: Math.abs(item.ordinal - batchRef.current.cursorIndex),
          sessionId: session.sessionId,
          sourceRelativePath: item.relativePath,
        });
        setBackpressure(false);
      } catch (cause) {
        if (
          cause instanceof RemoteSelectionTransferHttpError &&
          cause.code === 'REMOTE_SELECTION_TRANSFER_BACKPRESSURE'
        ) {
          setBackpressure(true);
          return false;
        }
        throw cause;
      } finally {
        setTransferSnapshot(transferScheduler.snapshot());
      }
      return true;
    },
    [session.sessionId, sourceReader, store, transferScheduler],
  );

  const synchronizePass = useCallback(async () => {
    setSyncing(true);
    try {
      const currentBatch = batchRef.current;
      const result = await synchronizer.drain(
        session.sessionId,
        currentBatch.batchId,
        clientInstanceId,
      );
      if (result.conflictCode !== null) {
        setError(`Synchronizacja wymaga uwagi: ${result.conflictCode}.`);
      } else {
        await synchronizer.reconcile(
          session.sessionId,
          currentBatch.batchId,
          clientInstanceId,
        );
        setRemoteStatus(synchronizer.status());
        if (typeof navigator === 'undefined' || navigator.onLine) setError('');
      }
      await refreshLocalState();
      const latest = await store.loadBatch(
        session.sessionId,
        currentBatch.batchId,
      );
      if (latest !== null) {
        const acceptedByFile = new Map(
          remoteSelectionWorkspaceState(latest)
            .decisions.filter(
              (
                decision,
              ): decision is RemoteSelectionWorkspaceDecision & {
                readonly fileId: string;
              } => decision.action === 'accepted' && decision.fileId !== null,
            )
            .map((decision) => [decision.fileId, decision]),
        );
        const scanStartCursor = resumeTransferAfterOrdinal.current;
        const page = await store.listSourceItemsPage(
          session.sessionId,
          latest.batchId,
          scanStartCursor,
          500,
        );
        let scannedThroughOrdinal = scanStartCursor;
        for (const item of page) {
          const decision = acceptedByFile.get(item.fileId);
          if (
            decision !== undefined &&
            !(await enqueueConfirmedTransfer(decision))
          )
            break;
          scannedThroughOrdinal = item.ordinal;
        }
        resumeTransferAfterOrdinal.current = advanceRemoteTransferScanCursor({
          currentCursor: resumeTransferAfterOrdinal.current,
          scannedThroughOrdinal,
          scanStartCursor,
        });
      }
    } catch (cause) {
      setError(syncErrorMessage(cause));
    } finally {
      const snapshot = transferScheduler.snapshot();
      transferPendingRef.current = snapshot.active + snapshot.queued;
      setTransferSnapshot(snapshot);
      setSyncing(false);
    }
  }, [
    clientInstanceId,
    enqueueConfirmedTransfer,
    refreshLocalState,
    session.sessionId,
    store,
    synchronizer,
    transferScheduler,
  ]);
  const syncNow = useCallback(
    () => syncCoordinator.run(synchronizePass),
    [syncCoordinator, synchronizePass],
  );

  useEffect(() => {
    void refreshLocalState().catch((cause) =>
      setError(syncErrorMessage(cause)),
    );
  }, [refreshLocalState]);

  useEffect(() => {
    let cancelled = false;
    let timer = 0;
    let idlePolls = 0;
    let polling = false;
    const poll = async () => {
      if (cancelled || polling) return;
      polling = true;
      const revision = batchRef.current.serverRevision;
      try {
        await syncNow();
      } finally {
        polling = false;
        if (cancelled) return;
        const pending =
          pendingCountRef.current > 0 || transferPendingRef.current > 0;
        idlePolls =
          pending || batchRef.current.serverRevision !== revision
            ? 0
            : idlePolls + 1;
        timer = window.setTimeout(
          () => void poll(),
          nextRemoteSelectionPollDelay({
            idlePolls,
            online: navigator.onLine,
            pending,
          }),
        );
      }
    };
    const online = () => {
      idlePolls = 0;
      window.clearTimeout(timer);
      void poll();
    };
    window.addEventListener('online', online);
    void poll();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      window.removeEventListener('online', online);
    };
  }, [syncNow]);

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
        if (!cancelled) setPreviewUrl(null);
      });
      return;
    }
    void (async () => {
      const ordered = [...items].sort(
        (left, right) =>
          Math.abs(left.ordinal - workspace.currentIndex) -
          Math.abs(right.ordinal - workspace.currentIndex),
      );
      for (const item of ordered) {
        if (cancelled || previewUrls.current.has(item.ordinal)) continue;
        const file = await sourceReader.fileForEntry(item);
        if (cancelled) return;
        previewUrls.current.set(item.ordinal, URL.createObjectURL(file));
        if (item.ordinal === workspace.currentIndex) {
          setDecoded(false);
          setPreviewOrdinal(item.ordinal);
          setPreviewUrl(previewUrls.current.get(item.ordinal) ?? null);
        }
      }
      const selected = previewUrls.current.get(workspace.currentIndex) ?? null;
      if (!cancelled) {
        setDecoded(false);
        setNaturalImageSize(null);
        setPreviewOrdinal(workspace.currentIndex);
        setPreviewUrl(selected);
      }
    })().catch((cause) => {
      if (!cancelled) setError(syncErrorMessage(cause));
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
    if (!decoded || current === null || previewOrdinal !== current.ordinal)
      return;
    viewStartedAt.current = performance.now();
    const key = `${current.fileId}:${workspace.nextRangeStart}`;
    const timer = window.setTimeout(() => {
      if (viewedKey.current === key) return;
      viewedKey.current = key;
      enqueueOperation(async () => {
        const clock = await store.operationClock(
          session.sessionId,
          batchRef.current.batchId,
          clientInstanceId,
        );
        await store.appendOutboxOperation(
          buildRemoteWorkspaceCommand({
            batchId: batchRef.current.batchId,
            clientInstanceId,
            clientSequence: clock.clientSequence,
            decoded: true,
            expectedServerRevision: clock.expectedServerRevision,
            fileId: current.fileId,
            imageChecksumSha256: null,
            imagePath: current.relativePath,
            operationId: crypto.randomUUID(),
            operationType: 'viewed',
            outputName: null,
            rangeStart: workspace.nextRangeStart,
            selectionGeneration: current.selectionGeneration ?? 0,
            sessionId: session.sessionId,
            sourceIndex: current.ordinal,
            visibleMilliseconds: performance.now() - viewStartedAt.current,
          }),
        );
        await refreshLocalState();
        void syncNow();
      });
    }, 300);
    return () => window.clearTimeout(timer);
  }, [
    clientInstanceId,
    current,
    decoded,
    previewOrdinal,
    refreshLocalState,
    session.sessionId,
    store,
    syncNow,
    workspace.nextRangeStart,
  ]);

  useEffect(() => {
    if (
      !pendingScrollRestore.current ||
      previewUrl === null ||
      previewOrdinal !== workspace.currentIndex ||
      zoomedImageSize === null
    ) {
      return;
    }
    const animationFrame = window.requestAnimationFrame(() => {
      if (viewport.current === null) return;
      viewport.current.scrollLeft = savedScrollLeft.current;
      viewport.current.scrollTop = savedScrollTop.current;
      pendingScrollRestore.current = false;
    });
    return () => window.cancelAnimationFrame(animationFrame);
  }, [previewOrdinal, previewUrl, workspace.currentIndex, zoomedImageSize]);

  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      const transfer = transferScheduler.snapshot();
      if (pendingCount === 0 && transfer.active === 0 && transfer.queued === 0)
        return;
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [pendingCount, transferScheduler]);

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
      (cause) => setError(syncErrorMessage(cause)),
    );
    return result;
  }

  async function persistCursor(nextIndex: number) {
    capturePreviewScrollForTransition();
    const currentBatch = batchRef.current;
    const next = {
      ...currentBatch,
      cursorIndex: nextIndex,
      updatedAt: new Date().toISOString(),
    };
    await store.saveBatch(next);
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

  function capturePreviewScrollForTransition() {
    if (viewport.current !== null) {
      savedScrollLeft.current = viewport.current.scrollLeft;
      savedScrollTop.current = viewport.current.scrollTop;
    }
    pendingScrollRestore.current = true;
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
    if (
      !canEdit ||
      finalizingRef.current ||
      finalizationRequestedRef.current ||
      hasConflict ||
      current === null ||
      sourceReader === null
    )
      return;
    if (!decoded || previewOrdinal !== current.ordinal) {
      setNotice('Poczekaj, aż bieżące zdjęcie zostanie w pełni załadowane.');
      return;
    }
    const requestedCurrent = current;
    const requestedRangeStart = workspace.nextRangeStart;
    void interactionQueue
      .enqueue(() =>
        acceptRequestedImage(requestedCurrent, requestedRangeStart),
      )
      .catch((cause) => setError(syncErrorMessage(cause)));
  }

  async function acceptRequestedImage(
    requestedCurrent: RemoteSelectionSourceItemRecord,
    requestedRangeStart: number,
  ) {
    const requestedWorkspace = remoteSelectionWorkspaceState(batchRef.current);
    if (
      finalizingRef.current ||
      batchRef.current.status === 'completed' ||
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
    busyRef.current = true;
    setBusy(true);
    setError('');
    capturePreviewScrollForTransition();
    try {
      if (sourceReader === null) return;
      const file = await sourceReader.fileForEntry(requestedCurrent);
      const checksum = await sha256File(file);
      const { nextBatch, outputName } = await enqueueOperation(async () => {
        const latest = remoteSelectionWorkspaceState(batchRef.current);
        if (
          latest.currentIndex !== requestedCurrent.ordinal ||
          latest.nextRangeStart !== requestedRangeStart
        ) {
          throw new RemoteSelectionStoreError(
            'REMOTE_SELECTION_WORKSPACE_STALE',
            'The local workspace changed before the requested selection was persisted.',
          );
        }
        const clock = await store.operationClock(
          session.sessionId,
          batchRef.current.batchId,
          clientInstanceId,
        );
        const generation = (requestedCurrent.selectionGeneration ?? 0) + 1;
        const operationId = crypto.randomUUID();
        const outputName = remoteOutputName(requestedRangeStart);
        const command = buildRemoteWorkspaceCommand({
          batchId: batchRef.current.batchId,
          clientInstanceId,
          clientSequence: clock.clientSequence,
          decoded: true,
          expectedServerRevision: clock.expectedServerRevision,
          fileId: requestedCurrent.fileId,
          imageChecksumSha256: checksum,
          imagePath: requestedCurrent.relativePath,
          operationId,
          operationType: 'select',
          outputName,
          rangeStart: requestedRangeStart,
          selectionGeneration: generation,
          sessionId: session.sessionId,
          sourceIndex: requestedCurrent.ordinal,
          visibleMilliseconds: performance.now() - viewStartedAt.current,
        });
        const nextBatch = await store.appendWorkspaceDecision({
          command,
          decision: {
            action: 'accepted',
            fileId: requestedCurrent.fileId,
            imageChecksumSha256: checksum,
            imagePath: requestedCurrent.relativePath,
            operationId,
            outputName,
            rangeEnd: requestedRangeStart + 8,
            rangeStart: requestedRangeStart,
            selectionGeneration: generation,
            sourceIndex: requestedCurrent.ordinal,
          },
          nextCursorIndex:
            batchRef.current.direction === 'ascending'
              ? Math.min(
                  requestedCurrent.ordinal + 1,
                  batchRef.current.fileCount - 1,
                )
              : Math.max(requestedCurrent.ordinal - 1, 0),
        });
        return { nextBatch, outputName };
      });
      setBatch(nextBatch);
      batchRef.current = nextBatch;
      setFinalizePreview(null);
      resumeTransferAfterOrdinal.current = Math.min(
        resumeTransferAfterOrdinal.current,
        requestedCurrent.ordinal - 1,
      );
      setNotice(
        `Zapisano lokalnie ${outputName}. Synchronizacja i JPEG idą w tle.`,
      );
      await refreshLocalState();
      void syncNow();
    } catch (cause) {
      setError(syncErrorMessage(cause));
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }

  function skipCurrent() {
    if (!canEdit || finalizingRef.current || hasConflict || current === null)
      return;
    if (finalizationRequestedRef.current) return;
    const requestedCurrent = current;
    const requestedRangeStart = workspace.nextRangeStart;
    void interactionQueue
      .enqueue(() => skipRequestedRange(requestedCurrent, requestedRangeStart))
      .catch((cause) => setError(syncErrorMessage(cause)));
  }

  async function skipRequestedRange(
    requestedCurrent: RemoteSelectionSourceItemRecord,
    requestedRangeStart: number,
  ) {
    const requestedWorkspace = remoteSelectionWorkspaceState(batchRef.current);
    if (
      finalizingRef.current ||
      batchRef.current.status === 'completed' ||
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
    capturePreviewScrollForTransition();
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
        const clock = await store.operationClock(
          session.sessionId,
          batchRef.current.batchId,
          clientInstanceId,
        );
        const operationId = crypto.randomUUID();
        const command = buildRemoteWorkspaceCommand({
          batchId: batchRef.current.batchId,
          clientInstanceId,
          clientSequence: clock.clientSequence,
          decoded,
          expectedServerRevision: clock.expectedServerRevision,
          fileId: null,
          imageChecksumSha256: null,
          imagePath: null,
          operationId,
          operationType: 'skip',
          outputName: null,
          rangeStart: requestedRangeStart,
          selectionGeneration: 0,
          sessionId: session.sessionId,
          sourceIndex: requestedCurrent.ordinal,
          visibleMilliseconds: performance.now() - viewStartedAt.current,
        });
        return store.appendWorkspaceDecision({
          command,
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
        });
      });
      setBatch(nextBatch);
      batchRef.current = nextBatch;
      setFinalizePreview(null);
      setNotice(
        `Pominięto zakres ${requestedRangeStart}–${requestedRangeStart + 8}.`,
      );
      await refreshLocalState();
      void syncNow();
    } catch (cause) {
      setError(syncErrorMessage(cause));
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }

  function undoLast() {
    if (
      !canEdit ||
      finalizingRef.current ||
      finalizationRequestedRef.current ||
      hasConflict
    )
      return;
    const latest = remoteSelectionWorkspaceState(batchRef.current);
    const last = latest.decisions.at(-1);
    if (last === undefined) return;
    void interactionQueue
      .enqueue(() => undoRequestedDecision(last.operationId))
      .catch((cause) => setError(syncErrorMessage(cause)));
  }

  async function undoRequestedDecision(targetOperationId: string) {
    const latest = remoteSelectionWorkspaceState(batchRef.current);
    const last = latest.decisions.at(-1);
    if (
      finalizingRef.current ||
      batchRef.current.status === 'completed' ||
      last === undefined ||
      last.operationId !== targetOperationId
    ) {
      setNotice(
        'Cofnięcie nie zostało wykonane, ponieważ ostatnia decyzja zdążyła się zmienić.',
      );
      return;
    }
    busyRef.current = true;
    setBusy(true);
    setError('');
    capturePreviewScrollForTransition();
    try {
      let command = null;
      if (last.action === 'accepted' && last.fileId !== null) {
        const source = await store.loadSourceItem(
          session.sessionId,
          batchRef.current.batchId,
          last.sourceIndex,
        );
        const generation =
          Math.max(last.selectionGeneration, source?.selectionGeneration ?? 0) +
          1;
        command = { generation };
        await transferScheduler.cancelOlderGenerations(last.fileId, generation);
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
        let undoCommand = null;
        if (command !== null && last.fileId !== null) {
          const clock = await store.operationClock(
            session.sessionId,
            batchRef.current.batchId,
            clientInstanceId,
          );
          undoCommand = buildRemoteWorkspaceCommand({
            batchId: batchRef.current.batchId,
            clientInstanceId,
            clientSequence: clock.clientSequence,
            decoded: true,
            expectedServerRevision: clock.expectedServerRevision,
            fileId: last.fileId,
            imageChecksumSha256: null,
            imagePath: last.imagePath,
            operationId: crypto.randomUUID(),
            operationType: 'undo',
            outputName: last.outputName,
            rangeStart: last.rangeStart,
            selectionGeneration: command.generation,
            sessionId: session.sessionId,
            sourceIndex: last.sourceIndex,
            targetOperationId: last.operationId,
            visibleMilliseconds: 0,
          });
        }
        return store.undoLastWorkspaceDecision({
          batchId: batchRef.current.batchId,
          command: undoCommand,
          sessionId: session.sessionId,
        });
      });
      if (nextBatch !== null) {
        setBatch(nextBatch);
        batchRef.current = nextBatch;
        setFinalizePreview(null);
        setNotice(`Cofnięto zakres ${last.rangeStart}–${last.rangeEnd}.`);
        await refreshLocalState();
        if (command !== null) void syncNow();
      }
    } catch (cause) {
      setError(syncErrorMessage(cause));
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

  function previewFinalization() {
    if (!canEdit || finalizing || finalizationRequestedRef.current) return;
    finalizationRequestedRef.current = true;
    void interactionQueue
      .enqueue(runFinalizationPreview)
      .catch((cause) => setError(syncErrorMessage(cause)));
  }

  async function synchronizeFinalizationBarrier() {
    await operationQueue.current;
    await syncNow();
    const pending = await store.countPendingOperations(
      session.sessionId,
      batchRef.current.batchId,
    );
    if (pending > 0) {
      throw new RemoteSelectionStoreError(
        'REMOTE_SELECTION_LOCAL_OUTBOX_PENDING',
        `Finalizacja jest zablokowana: ${pending} lokalnych operacji nadal oczekuje na synchronizację.`,
      );
    }
  }

  async function runFinalizationPreview() {
    finalizingRef.current = true;
    setFinalizing(true);
    setError('');
    try {
      await synchronizeFinalizationBarrier();
      const preview = await controlTransport.finalizePreview(
        batchRef.current.batchId,
      );
      setFinalizePreview(preview);
      setNotice(
        preview.ready
          ? 'Wszystkie decyzje i pliki są uzgodnione. Możesz zakończyć partię.'
          : 'Partia nie jest jeszcze gotowa. Szczegóły są widoczne poniżej.',
      );
    } catch (cause) {
      setError(syncErrorMessage(cause));
    } finally {
      finalizingRef.current = false;
      finalizationRequestedRef.current = false;
      setFinalizing(false);
    }
  }

  function finalizeBatch() {
    if (
      !canEdit ||
      finalizing ||
      finalizationRequestedRef.current ||
      finalizePreview?.ready !== true
    )
      return;
    finalizationRequestedRef.current = true;
    void interactionQueue
      .enqueue(runFinalization)
      .catch((cause) => setError(syncErrorMessage(cause)));
  }

  async function runFinalization() {
    finalizingRef.current = true;
    setFinalizing(true);
    setError('');
    try {
      await synchronizeFinalizationBarrier();
      const currentPreview = await controlTransport.finalizePreview(
        batchRef.current.batchId,
      );
      if (!currentPreview.ready) {
        setFinalizePreview(currentPreview);
        setNotice(
          'Partia nie jest jeszcze gotowa. Szczegóły są widoczne poniżej.',
        );
        return;
      }
      const result = await controlTransport.finalizeBatch({
        batchId: batchRef.current.batchId,
        expectedServerRevision: currentPreview.serverRevision,
        sessionId: session.sessionId,
      });
      const next: RemoteSelectionLocalBatchRecord = {
        ...batchRef.current,
        serverRevision: result.batch.serverRevision,
        status: 'completed',
        updatedAt: result.finalizedAt,
      };
      await store.saveBatch(next);
      setBatch(next);
      batchRef.current = next;
      setFinalizePreview(null);
      setNotice(
        `Partia zakończona. Manifest ${result.finalManifestChecksumSha256.slice(0, 12)}… został zapisany na hoście.`,
      );
    } catch (cause) {
      setFinalizePreview(null);
      setError(syncErrorMessage(cause));
    } finally {
      finalizingRef.current = false;
      finalizationRequestedRef.current = false;
      setFinalizing(false);
    }
  }

  return (
    <section
      className="remoteManualWorkspace manualImageSelectionWorkspace manualImageSelectionActive"
      aria-live="polite"
    >
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

      {typeof navigator !== 'undefined' && !navigator.onLine ? (
        <p className="remoteWorkspaceBanner">
          Tryb offline — decyzje są bezpieczne lokalnie i zostaną wysłane po
          odzyskaniu sieci.
        </p>
      ) : null}
      {backpressure ? (
        <p className="remoteWorkspaceBanner remoteWorkspaceBanner--warning">
          Kolejka transferu osiągnęła limit. Możesz pracować dalej; pliki ruszą
          po zwolnieniu miejsca.
        </p>
      ) : null}
      {transferSnapshot.active + transferSnapshot.queued > 0 ? (
        <p className="remoteWorkspaceBanner">
          JPEG-i są wysyłane w tle. Nawigacja i kolejne decyzje pozostają
          dostępne.
        </p>
      ) : null}
      {completed ? (
        <p className="remoteWorkspaceBanner">
          Partia została zakończona. Manifesty i pliki są tylko do odczytu;
          ponowne otwarcie wymaga działania hosta.
        </p>
      ) : null}

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
            onClick={() => setZoom((value) => Math.max(100, value - 25))}
            type="button"
          >
            −
          </button>
          <span>{zoom}%</span>
          <button
            aria-label="Powiększ zdjęcie"
            className="secondaryButton"
            disabled={zoom >= 3000 || busy}
            onClick={() => setZoom((value) => Math.min(3000, value + 25))}
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
                if (!pendingScrollRestore.current) {
                  savedScrollLeft.current = event.currentTarget.scrollLeft;
                  savedScrollTop.current = event.currentTarget.scrollTop;
                }
              }}
              ref={viewport}
            >
              {previewUrl === null ||
              previewOrdinal !== workspace.currentIndex ? (
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
                    src={previewUrl}
                    onLoadCapture={(event) => {
                      setNaturalImageSize({
                        height: event.currentTarget.naturalHeight,
                        width: event.currentTarget.naturalWidth,
                      });
                      setDecoded(true);
                    }}
                  />
                </div>
              )}
            </div>
            <p className="manualImageSelectionFilename">
              {current?.relativePath ?? 'brak zdjęcia'}
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

        <aside className="remoteManualSyncPanel">
          <h3>Stan pracy</h3>
          <dl>
            <div>
              <dt>Zatwierdzone</dt>
              <dd>{acceptedCount}</dd>
            </div>
            <div>
              <dt>Decyzje razem</dt>
              <dd>{workspace.decisions.length}</dd>
            </div>
            <div>
              <dt>Outbox</dt>
              <dd>{pendingCount}</dd>
            </div>
            <div>
              <dt>Transfery</dt>
              <dd>
                {transferSnapshot.active} aktywne / {transferSnapshot.queued} w
                kolejce
              </dd>
            </div>
            <div>
              <dt>Dane w tle</dt>
              <dd>{formatBytes(transferSnapshot.pendingBytes)}</dd>
            </div>
            {remoteStatus !== null ? (
              <>
                <div>
                  <dt>Serwer: oczekujące decyzje</dt>
                  <dd>{remoteStatus.queue.pendingOperationCount}</dd>
                </div>
                <div>
                  <dt>Serwer: upload</dt>
                  <dd>
                    {remoteStatus.queue.uploadingTransferCount} /{' '}
                    {formatBytes(remoteStatus.queue.pendingTransferBytes)}
                  </dd>
                </div>
                <div>
                  <dt>Serwer: materializacja</dt>
                  <dd>
                    {remoteStatus.queue.materializingActionCount} /{' '}
                    {remoteStatus.queue.pendingHostActionCount} akcji
                  </dd>
                </div>
                <div>
                  <dt>Serwer: zsynchronizowane</dt>
                  <dd>{remoteStatus.queue.syncedFileCount}</dd>
                </div>
                <div>
                  <dt>Konflikty</dt>
                  <dd>{remoteStatus.queue.conflictFileCount}</dd>
                </div>
                <div>
                  <dt>Heartbeat writera</dt>
                  <dd>
                    {remoteStatus.lastHeartbeatAt === null
                      ? 'brak aktywnego writera'
                      : new Date(remoteStatus.lastHeartbeatAt).toLocaleString(
                          'pl-PL',
                        )}
                  </dd>
                </div>
              </>
            ) : null}
          </dl>
          {remoteStatus?.queue.recoveryFindings.length ? (
            <ul className="remoteManualRecoveryFindings">
              {remoteStatus.queue.recoveryFindings.map((finding) => (
                <li key={finding.code}>
                  {finding.code}: {finding.count}
                </li>
              ))}
            </ul>
          ) : null}
          <button
            className="secondaryButton"
            disabled={syncing}
            onClick={() => void syncNow()}
            type="button"
          >
            {syncing ? 'Synchronizacja…' : 'Ponów synchronizację'}
          </button>
          {!completed ? (
            <div className="remoteManualFinalizePanel">
              <h3>Zakończenie partii</h3>
              <button
                className="secondaryButton"
                disabled={!canEdit || syncing || finalizing}
                onClick={() => void previewFinalization()}
                type="button"
              >
                {finalizing ? 'Sprawdzanie…' : 'Sprawdź gotowość'}
              </button>
              {finalizePreview !== null ? (
                finalizePreview.ready ? (
                  <button
                    className="primaryButton"
                    disabled={finalizing}
                    onClick={() => void finalizeBatch()}
                    type="button"
                  >
                    Zakończ partię i zapisz manifesty
                  </button>
                ) : (
                  <ul>
                    {finalizePreview.blockers.map((blocker) => (
                      <li key={blocker.code}>
                        {finalizationBlockerLabel(blocker.code)}:{' '}
                        {blocker.count}
                      </li>
                    ))}
                  </ul>
                )
              ) : null}
            </div>
          ) : null}
          <p className="remoteManualShortcutHelp">
            ←/→ zdjęcie · ↑/↓ skok · Enter/F zatwierdź · Tab pomiń · A/Ctrl+Z
            cofnij
          </p>
        </aside>
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
          disabled={!canEdit || busy || hasConflict || sourceReader === null}
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

function syncErrorMessage(cause: unknown): string {
  if (
    cause instanceof RemoteSelectionControlApiError ||
    cause instanceof RemoteSelectionStoreError ||
    cause instanceof RemoteSelectionTransferHttpError
  )
    return `${cause.message} (${cause.code})`;
  if (cause instanceof TypeError)
    return 'Brak połączenia z hostem. Decyzje pozostają w lokalnym outboxie.';
  return cause instanceof Error
    ? cause.message
    : 'Nie udało się wykonać operacji.';
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KiB`;
  return `${(value / 1024 ** 2).toFixed(1)} MiB`;
}

function finalizationBlockerLabel(code: string): string {
  const labels: Record<string, string> = {
    REMOTE_SELECTION_HOST_ACTION_PENDING: 'Operacje plikowe hosta',
    REMOTE_SELECTION_OPERATION_PENDING: 'Niezsynchronizowane decyzje',
    REMOTE_SELECTION_REMOVAL_PENDING: 'Pliki oczekujące na usunięcie',
    REMOTE_SELECTION_SELECTED_FILE_NOT_SYNCED: 'Niezapisane wybrane JPEG-i',
    REMOTE_SELECTION_TRANSFER_PENDING: 'Transfery JPEG-ów',
  };
  return labels[code] ?? code;
}
