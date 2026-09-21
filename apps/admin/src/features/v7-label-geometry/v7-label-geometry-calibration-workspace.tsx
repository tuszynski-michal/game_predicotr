'use client';

// Canonical PNGs are checksum-bound API assets, never browser-stored originals.

import type {
  AdminApiClient,
  V7LabelGeometrySessionResponse,
  V7LabelGeometrySlotResponse,
} from '@game-predictor/admin-api-client';
import {
  type MouseEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';
import { apiErrorMessage } from '@/features/catalog/catalog-api-error';

import {
  acknowledgeV7LabelGeometryOperation,
  discardPendingV7LabelGeometryOperations,
  enqueueV7LabelGeometryOperation,
  isV7LabelGeometryPointInsideServerBounds,
  nextV7LabelGeometryOperation,
  normaliseV7LabelGeometryPoint,
  resumeV7LabelGeometryQueue,
  stopV7LabelGeometryQueue,
  type V7LabelGeometryQueueState,
  toV7LabelGeometrySessionMutation,
  v7LabelGeometryAssetKey,
} from './v7-label-geometry-calibration-queue.ts';
import {
  type V7LabelGeometryCalibrationLocalView,
  type V7LabelGeometryCropAssessment,
  V7LabelGeometryCalibrationLocalStore,
} from './v7-label-geometry-calibration-store.ts';
import {
  calculateV7LabelGeometryCalibrationReadiness,
  V7_LABEL_GEOMETRY_MINIMUM_CAPTURE_GROUPS_PER_POSITION,
  V7_LABEL_GEOMETRY_MINIMUM_SOURCES_PER_POSITION,
} from './v7-label-geometry-calibration-readiness.ts';

const GEOMETRY_FAMILY_ID = 'standard_3x3_numeric_labels_v1';
const CALIBRATION_CASES = [
  { id: 'small_777', label: '777 — grupy bazowe' },
  { id: 'occluded_777', label: '777 — częściowo zasłonięte plansze' },
] as const;

const EMPTY_QUEUE: V7LabelGeometryQueueState = {
  confirmedRevision: 0,
  pending: [],
  stoppedReason: null,
};

type CalibrationClient = Pick<
  AdminApiClient,
  | 'createV7LabelGeometryCalibrationSession'
  | 'createV7LabelGeometryProfile'
  | 'exportV7LabelGeometryCalibrationSession'
  | 'getV7LabelGeometryCalibrationSession'
  | 'getV7LabelGeometryCalibrationSourceAsset'
  | 'mutateV7LabelGeometryCalibrationSession'
>;
type CalibrationLocalStore = Pick<
  V7LabelGeometryCalibrationLocalStore,
  | 'appendOperation'
  | 'discardPending'
  | 'load'
  | 'loadMostRecent'
  | 'removeHead'
  | 'saveView'
>;

export interface V7LabelGeometryCalibrationWorkspaceProps {
  readonly apiBaseUrl: string;
  readonly client?: CalibrationClient;
  /** Test seam; production always uses the durable IndexedDB implementation. */
  readonly localStore?: CalibrationLocalStore;
}

export function V7LabelGeometryCalibrationWorkspace({
  apiBaseUrl,
  client,
  localStore,
}: V7LabelGeometryCalibrationWorkspaceProps) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const store = useMemo(
    () => localStore ?? new V7LabelGeometryCalibrationLocalStore(),
    [localStore],
  );
  const [session, setSession] = useState<V7LabelGeometrySessionResponse | null>(
    null,
  );
  const sessionRef = useRef<V7LabelGeometrySessionResponse | null>(null);
  const [selectedCaseIds, setSelectedCaseIds] = useState<readonly string[]>(
    CALIBRATION_CASES.map((item) => item.id),
  );
  const [view, setView] = useState<V7LabelGeometryCalibrationLocalView | null>(
    null,
  );
  const viewRef = useRef<V7LabelGeometryCalibrationLocalView | null>(null);
  const [queue, setQueue] = useState<V7LabelGeometryQueueState>(EMPTY_QUEUE);
  const queueRef = useRef<V7LabelGeometryQueueState>(EMPTY_QUEUE);
  const queueTransitionRef = useRef<Promise<void>>(Promise.resolve());
  const viewTransitionRef = useRef<Promise<void>>(Promise.resolve());
  const [storageReady, setStorageReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [asset, setAsset] = useState<{
    readonly key: string;
    readonly url: string;
  } | null>(null);
  const assetRef = useRef<{ readonly key: string; readonly url: string } | null>(
    null,
  );
  const [assetError, setAssetError] = useState('');
  const [feedback, setFeedback] = useState('');
  const [error, setError] = useState('');
  const flushingRef = useRef(false);
  const discardingRef = useRef(false);
  const [captureGroupDrafts, setCaptureGroupDrafts] = useState<
    ReadonlyMap<string, string>
  >(new Map());

  const replaceSession = useCallback(
    (next: V7LabelGeometrySessionResponse | null) => {
      sessionRef.current = next;
      setSession(next);
    },
    [],
  );

  const replaceQueue = useCallback((next: V7LabelGeometryQueueState) => {
    queueRef.current = next;
    setQueue(next);
  }, []);

  const replaceAsset = useCallback(
    (next: { readonly key: string; readonly url: string } | null) => {
      assetRef.current = next;
      setAsset(next);
    },
    [],
  );

  const makeDefaultView = useCallback(
    (
      current: V7LabelGeometrySessionResponse,
    ): V7LabelGeometryCalibrationLocalView => ({
      activePositionIndex: 0,
      activeSourceId: current.sources[0]?.sourceId ?? null,
      cropAssessment: 'contained',
      manifestFingerprint: current.manifestFingerprint,
      queueStoppedReason: null,
      sessionId: current.sessionId,
      updatedAt: new Date().toISOString(),
    }),
    [],
  );

  const persistView = useCallback(
    async (next: V7LabelGeometryCalibrationLocalView): Promise<void> => {
      viewRef.current = next;
      setView(next);
      const write = viewTransitionRef.current.then(
        () => store.saveView(next),
        () => store.saveView(next),
      );
      viewTransitionRef.current = write.then(
        () => undefined,
        () => undefined,
      );
      await write;
    },
    [store],
  );

  const withQueueTransition = useCallback(
    async (action: () => Promise<void>): Promise<void> => {
      const transition = queueTransitionRef.current.then(action, action);
      queueTransitionRef.current = transition.then(
        () => undefined,
        () => undefined,
      );
      await transition;
    },
    [],
  );

  const persistQueueStoppedReason = useCallback(
    async (nextQueue: V7LabelGeometryQueueState): Promise<void> => {
      const currentView = viewRef.current;
      if (currentView === null) return;
      await persistView({
        ...currentView,
        queueStoppedReason: nextQueue.stoppedReason,
        updatedAt: new Date().toISOString(),
      });
    },
    [persistView],
  );

  const flushQueue = useCallback(async () => {
    if (
      flushingRef.current ||
      discardingRef.current ||
      sessionRef.current === null
    ) {
      return;
    }
    setError('');
    setSyncing(true);
    flushingRef.current = true;
    try {
      while (true) {
        const currentSession = sessionRef.current;
        const currentQueue = queueRef.current;
        const head = nextV7LabelGeometryOperation(currentQueue);
        if (currentSession === null || head === null) return;
        if (currentSession.sessionId !== head.sessionId) {
          const message =
            'Lokalna kolejka należy do innej sesji. Odrzuć ją przed wznowieniem.';
          await withQueueTransition(async () => {
            const stopped = stopV7LabelGeometryQueue(queueRef.current, message);
            replaceQueue(stopped);
            await persistQueueStoppedReason(stopped);
          });
          setError(message);
          return;
        }
        const result = await api.mutateV7LabelGeometryCalibrationSession(
          currentSession.sessionId,
          toV7LabelGeometrySessionMutation(head),
        );
        if (result.error !== undefined || result.data === undefined) {
          const message = apiErrorMessage(
            result.error,
            'Nie udało się zapisać kliknięcia. Możesz bezpiecznie ponowić synchronizację.',
          );
          const code =
            typeof result.error === 'object' &&
            result.error !== null &&
            'code' in result.error &&
            typeof result.error.code === 'string'
              ? result.error.code
              : null;
          if (
            code === 'V7_CALIBRATION_SESSION_REVISION_CONFLICT' ||
            code === 'V7_CALIBRATION_SESSION_SOURCE_DRIFT' ||
            code === 'V7_CALIBRATION_SESSION_BLOCKED'
          ) {
            await withQueueTransition(async () => {
              const stopped = stopV7LabelGeometryQueue(queueRef.current, message);
              replaceQueue(stopped);
              await persistQueueStoppedReason(stopped);
            });
            setError(message);
          } else {
            setFeedback(message);
          }
          return;
        }
        try {
          await withQueueTransition(async () => {
            const latestHead = nextV7LabelGeometryOperation(queueRef.current);
            if (
              latestHead === null ||
              latestHead.operationId !== head.operationId ||
              latestHead.sequence !== head.sequence
            ) {
              throw new Error('V7_LABEL_GEOMETRY_LOCAL_QUEUE_HEAD_CHANGED');
            }
            const acknowledged = acknowledgeV7LabelGeometryOperation(
              queueRef.current,
              head.operationId,
              result.data.receipt.revision,
            );
            await store.removeHead(
              head.sessionId,
              head.sequence,
              head.operationId,
            );
            replaceSession(result.data.session);
            replaceQueue(acknowledged);
            if (
              head.kind === 'set_capture_group' &&
              head.captureGroupId !== undefined
            ) {
              setCaptureGroupDrafts((current) => {
                if (current.get(head.sourceId) !== head.captureGroupId) {
                  return current;
                }
                const next = new Map(current);
                next.delete(head.sourceId);
                return next;
              });
            }
          });
        } catch (cause) {
          setError(
            cause instanceof Error
              ? `Serwer potwierdził operację, ale przeglądarka nie potrafi trwale rozliczyć kolejki. Ponów synchronizację tym samym wpisem. ${cause.message}`
              : 'Serwer potwierdził operację, ale przeglądarka nie potrafi trwale rozliczyć kolejki. Ponów synchronizację tym samym wpisem.',
          );
          return;
        }
        setFeedback('Zapisano punkt kalibracji.');
      }
    } finally {
      flushingRef.current = false;
      setSyncing(false);
    }
  }, [
    api,
    persistQueueStoppedReason,
    replaceQueue,
    replaceSession,
    store,
    withQueueTransition,
  ]);

  const loadSession = useCallback(
    async (sessionId: string, resumePending = true) => {
      setBusy(true);
      setError('');
      try {
        const result = await api.getV7LabelGeometryCalibrationSession(sessionId);
        if (result.error !== undefined || result.data === undefined) {
          setError(
            apiErrorMessage(result.error, 'Nie udało się odczytać sesji kalibracji.'),
          );
          return;
        }
        const current = result.data;
        replaceSession(current);
        const local = await store.load(sessionId, current.revision);
        const fingerprintMatches =
          local?.view.manifestFingerprint === current.manifestFingerprint;
        const localView = fingerprintMatches
          ? local!.view
          : makeDefaultView(current);
        let restoredQueue =
          local === null
            ? resumeV7LabelGeometryQueue(EMPTY_QUEUE, current.revision)
            : local.queue;
        if (!fingerprintMatches && local !== null) {
          restoredQueue = stopV7LabelGeometryQueue(
            restoredQueue,
            'Lokalny widok ma inny fingerprint manifestu. Odrzuć kolejkę przed wznowieniem.',
          );
        }
        if (current.status === 'blocked_source_drift') {
          restoredQueue = stopV7LabelGeometryQueue(
            restoredQueue,
            'Źródła sesji zmieniły się po jej utworzeniu. Serwer zablokował dalszą kalibrację.',
          );
        }
        replaceQueue(restoredQueue);
        await persistView({
          ...localView,
          activePositionIndex: clampPosition(localView.activePositionIndex),
          activeSourceId: sourceExists(current, localView.activeSourceId)
            ? localView.activeSourceId
            : current.sources[0]?.sourceId ?? null,
          manifestFingerprint: current.manifestFingerprint,
          queueStoppedReason: restoredQueue.stoppedReason,
          updatedAt: new Date().toISOString(),
        });
        if (restoredQueue.stoppedReason !== null) {
          setError(restoredQueue.stoppedReason);
          return;
        }
        if (resumePending && restoredQueue.pending.length > 0) {
          void flushQueue();
        }
      } catch (cause) {
        setError(
          cause instanceof Error
            ? cause.message
            : 'Nie udało się przywrócić lokalnego stanu kalibracji.',
        );
      } finally {
        setBusy(false);
      }
    },
    [
      api,
      flushQueue,
      makeDefaultView,
      persistView,
      replaceQueue,
      replaceSession,
      store,
    ],
  );

  useEffect(() => {
    let cancelled = false;
    if (globalThis.indexedDB === undefined) {
      queueMicrotask(() => {
        if (!cancelled) {
          setError(
            'Ta przeglądarka nie udostępnia IndexedDB. Zapis punktów jest wyłączony.',
          );
        }
      });
      return;
    }
    void store
      .loadMostRecent()
      .then((saved) => {
        if (cancelled) return;
        setStorageReady(true);
        if (saved !== null) void loadSession(saved.sessionId);
      })
      .catch((cause) => {
        if (!cancelled) {
          setError(
            cause instanceof Error
              ? cause.message
              : 'Nie udało się otworzyć trwałej kolejki przeglądarki.',
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [loadSession, store]);

  const activeSource =
    session?.sources.find((source) => source.sourceId === view?.activeSourceId) ??
    null;
  const activeAssetKey =
    session === null || activeSource === null
      ? null
      : v7LabelGeometryAssetKey(
          session.sessionId,
          activeSource.sourceId,
          activeSource.sourceChecksumSha256,
        );
  const activeAssetUrl =
    asset !== null && asset.key === activeAssetKey ? asset.url : null;

  useEffect(() => {
    let cancelled = false;
    const sessionId = session?.sessionId ?? null;
    const sourceId = activeSource?.sourceId ?? null;
    const sourceChecksumSha256 = activeSource?.sourceChecksumSha256 ?? null;
    const assetKey = activeAssetKey;
    if (
      sessionId === null ||
      sourceId === null ||
      sourceChecksumSha256 === null ||
      assetKey === null
    ) {
      queueMicrotask(() => {
        if (!cancelled) replaceAsset(null);
      });
      return () => {
        cancelled = true;
      };
    }
    let currentUrl: string | null = null;
    queueMicrotask(() => {
      if (!cancelled) setAssetError('');
    });
    void api
      .getV7LabelGeometryCalibrationSourceAsset(
        sessionId,
        sourceId,
        sourceChecksumSha256,
      )
      .then((result) => {
        if (cancelled) return;
        if (
          result.error !== undefined ||
          result.data === undefined ||
          !(result.data instanceof Blob)
        ) {
          setAssetError(
            apiErrorMessage(
              result.error,
              'Nie udało się pobrać kanonicznego PNG źródła.',
            ),
          );
          replaceAsset(null);
          return;
        }
        currentUrl = URL.createObjectURL(result.data);
        replaceAsset({ key: assetKey, url: currentUrl });
      })
      .catch(() => {
        if (!cancelled) {
          replaceAsset(null);
          setAssetError('Nie udało się pobrać kanonicznego PNG źródła.');
        }
      });
    return () => {
      cancelled = true;
      if (currentUrl !== null) URL.revokeObjectURL(currentUrl);
    };
  }, [activeAssetKey, activeSource, api, replaceAsset, session]);

  const createSession = async () => {
    if (!storageReady || selectedCaseIds.length === 0) return;
    setBusy(true);
    setError('');
    try {
      const result = await api.createV7LabelGeometryCalibrationSession({
        corpusCaseIds: [...selectedCaseIds],
        geometryFamilyId: GEOMETRY_FAMILY_ID,
      });
      if (result.error !== undefined || result.data === undefined) {
        setError(
          apiErrorMessage(result.error, 'Nie udało się utworzyć sesji kalibracji.'),
        );
        return;
      }
      const current = result.data;
      await persistView(makeDefaultView(current));
      replaceSession(current);
      replaceQueue(resumeV7LabelGeometryQueue(EMPTY_QUEUE, current.revision));
      setFeedback('Utworzono nową sesję kalibracji.');
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : 'Nie udało się zapisać lokalnego widoku sesji.',
      );
    } finally {
      setBusy(false);
    }
  };

  const updateView = async (
    patch: Partial<
      Omit<
        V7LabelGeometryCalibrationLocalView,
        'sessionId' | 'manifestFingerprint' | 'updatedAt'
      >
    >,
  ) => {
    const currentSession = sessionRef.current;
    const currentView = viewRef.current;
    if (currentSession === null || currentView === null) return;
    try {
      await persistView({
        ...currentView,
        ...patch,
        manifestFingerprint: currentSession.manifestFingerprint,
        updatedAt: new Date().toISOString(),
      });
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : 'Nie udało się zapisać widoku lokalnego.',
      );
    }
  };

  const enqueue = async (
    input: Omit<
      Parameters<typeof enqueueV7LabelGeometryOperation>[1],
      'operationId' | 'sessionId'
    >,
  ) => {
    if (!storageReady) return;
    if (discardingRef.current) {
      setError('Trwa porzucanie lokalnej kolejki. Poczekaj na odświeżenie sesji.');
      return;
    }
    try {
      await withQueueTransition(async () => {
        const currentSession = sessionRef.current;
        if (currentSession === null) {
          throw new Error('V7_LABEL_GEOMETRY_SESSION_UNAVAILABLE');
        }
        const next = enqueueV7LabelGeometryOperation(queueRef.current, {
          ...input,
          operationId: globalThis.crypto.randomUUID(),
          sessionId: currentSession.sessionId,
        });
        const operation = next.pending.at(-1);
        if (operation === undefined) {
          throw new Error('V7_LABEL_GEOMETRY_QUEUE_APPEND_FAILED');
        }
        await store.appendOperation(operation);
        replaceQueue(next);
      });
      setFeedback('Punkt zapisano do trwałej kolejki.');
      void flushQueue();
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : 'Nie udało się zapisać kliknięcia w trwałej kolejce.',
      );
    }
  };

  const annotate = async (event: MouseEvent<HTMLImageElement>) => {
    const currentSession = sessionRef.current;
    const currentView = viewRef.current;
    if (currentSession === null || currentView === null) return;
    if (queueRef.current.stoppedReason !== null) {
      setError(queueRef.current.stoppedReason);
      return;
    }
    try {
      const source = currentSession.sources.find(
        (candidate) => candidate.sourceId === currentView.activeSourceId,
      );
      if (source === undefined) {
        throw new Error('V7_LABEL_GEOMETRY_ACTIVE_SOURCE_UNAVAILABLE');
      }
      const expectedAssetKey = v7LabelGeometryAssetKey(
        currentSession.sessionId,
        source.sourceId,
        source.sourceChecksumSha256,
      );
      if (assetRef.current?.key !== expectedAssetKey) {
        throw new Error('V7_LABEL_GEOMETRY_ACTIVE_ASSET_CHANGED');
      }
      const point = normaliseV7LabelGeometryPoint(
        event.clientX,
        event.clientY,
        event.currentTarget.getBoundingClientRect(),
      );
      if (!isV7LabelGeometryPointInsideServerBounds(point)) {
        throw new Error(
          'Kliknij wewnątrz obrazu, nie na jego krawędzi. Punkt na granicy nie może zostać zapisany.',
        );
      }
      await enqueue({
        centerX: point.centerX,
        centerY: point.centerY,
        cropAssessment: currentView.cropAssessment,
        kind: 'annotated',
        positionIndex: currentView.activePositionIndex,
        sourceId: source.sourceId,
      });
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : 'Kliknięcie nie może zostać zapisane.',
      );
    }
  };

  const markUnavailable = () => {
    const currentSession = sessionRef.current;
    const currentView = viewRef.current;
    const source = currentSession?.sources.find(
      (candidate) => candidate.sourceId === currentView?.activeSourceId,
    );
    if (source === undefined || currentView === null) return;
    void enqueue({
      kind: 'unavailable',
      positionIndex: currentView.activePositionIndex,
      sourceId: source.sourceId,
    });
  };

  const assignCaptureGroup = (sourceId: string, captureGroupId: string) => {
    const currentSession = sessionRef.current;
    if (
      currentSession === null ||
      captureGroupId.trim() === '' ||
      currentSession.captureGroups[sourceId] === captureGroupId.trim()
    ) {
      return;
    }
    void enqueue({
      captureGroupId: captureGroupId.trim(),
      kind: 'set_capture_group',
      sourceId,
    });
  };

  const discardPending = async () => {
    const currentSession = sessionRef.current;
    if (
      currentSession === null ||
      queueRef.current.pending.length === 0 ||
      flushingRef.current ||
      !globalThis.confirm(
        'Porzucić wyłącznie niepotwierdzone kliknięcia zapisane w tej przeglądarce?',
      )
    ) {
      return;
    }
    discardingRef.current = true;
    setSyncing(true);
    try {
      await withQueueTransition(async () => {
        if (sessionRef.current?.sessionId !== currentSession.sessionId) {
          throw new Error('V7_LABEL_GEOMETRY_SESSION_CHANGED');
        }
        await store.discardPending(currentSession.sessionId);
        const discarded = discardPendingV7LabelGeometryOperations(queueRef.current);
        replaceQueue(discarded);
        await persistQueueStoppedReason(discarded);
      });
      setFeedback(
        'Porzucono lokalne, niepotwierdzone kliknięcia. Dane serwera nie zostały zmienione.',
      );
      await loadSession(currentSession.sessionId, false);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : 'Nie udało się porzucić lokalnej kolejki.',
      );
    } finally {
      discardingRef.current = false;
      setSyncing(false);
    }
  };

  const exportSession = async (profile: boolean) => {
    if (
      session === null ||
      queue.pending.length > 0 ||
      queue.stoppedReason !== null
    ) {
      setError('Najpierw zsynchronizuj albo jawnie porzuć lokalną kolejkę.');
      return;
    }
    setBusy(true);
    const result = profile
      ? await api.createV7LabelGeometryProfile(session.sessionId, {
          expectedRevision: session.revision,
        })
      : await api.exportV7LabelGeometryCalibrationSession(session.sessionId, {
          expectedRevision: session.revision,
        });
    setBusy(false);
    if (result.error !== undefined || result.data === undefined) {
      setError(
        apiErrorMessage(
          result.error,
          profile
            ? 'Profil nie przeszedł bramek kalibracji.'
            : 'Nie udało się wyeksportować sesji.',
        ),
      );
      return;
    }
    setFeedback(
      profile
        ? 'Utworzono immutable profil kalibracji.'
        : 'Wyeksportowano immutable snapshot sesji.',
    );
  };

  const slots =
    session === null || activeSource === null
      ? []
      : session.slots.filter((slot) => slot.sourceId === activeSource.sourceId);
  const activeSlot = slots.find(
    (slot) => slot.positionIndex === view?.activePositionIndex,
  );
  const readiness = useMemo(
    () =>
      session === null
        ? null
        : calculateV7LabelGeometryCalibrationReadiness({
            captureGroups: session.captureGroups,
            slots: session.slots,
            sources: session.sources,
          }),
    [session],
  );

  return (
    <section
      aria-label="Kalibracja etykiet V7"
      className="v7LabelGeometryWorkspace"
    >
      <header className="v7LabelGeometryHeader">
        <div>
          <p className="eyebrow">KALIBRACJA V7</p>
          <h2>Położenie etykiet numerycznych</h2>
          <p>
            Oznacz środek numeru dla każdej pozycji 3 × 3. To nie uruchamia
            selekcji V7 ani nie zapisuje zdjęć do katalogu cut.
          </p>
        </div>
        <span className="semiAutomaticSelectionCapability loading">
          {session === null ? 'Nowa sesja' : `Rewizja ${session.revision}`}
        </span>
      </header>

      {error !== '' ? (
        <p className="feedbackBanner feedbackBannerError" role="alert">
          {error}
        </p>
      ) : null}
      {feedback !== '' ? (
        <p className="feedbackBanner" role="status">
          {feedback}
        </p>
      ) : null}

      {session === null ? (
        <div className="v7LabelGeometrySetup">
          <h3>Materiały do kalibracji</h3>
          <p>
            Dostępne są wyłącznie materiały calibration 777. Holdout reels_test
            pozostaje niewidoczny i zarezerwowany do późniejszego odbioru.
          </p>
          <div className="v7LabelGeometryCaseList">
            {CALIBRATION_CASES.map((item) => (
              <label key={item.id}>
                <input
                  checked={selectedCaseIds.includes(item.id)}
                  disabled={busy || !storageReady}
                  onChange={(event) =>
                    setSelectedCaseIds((current) =>
                      event.target.checked
                        ? [...current, item.id]
                        : current.filter((candidate) => candidate !== item.id),
                    )
                  }
                  type="checkbox"
                />
                {item.label}
              </label>
            ))}
          </div>
          <button
            className="primaryButton"
            disabled={busy || !storageReady || selectedCaseIds.length === 0}
            onClick={() => void createSession()}
            type="button"
          >
            {busy ? 'Przygotowuję…' : 'Utwórz sesję kalibracji'}
          </button>
          {!storageReady ? (
            <p className="v7LabelGeometryNotice">
              Trwała kolejka przeglądarki jest wymagana przed pierwszym kliknięciem.
            </p>
          ) : null}
        </div>
      ) : null}

      {session !== null && view !== null ? (
        <div className="v7LabelGeometryEditor">
          <div className="v7LabelGeometryControls">
            <label>
              Zdjęcie źródłowe
              <select
                onChange={(event) =>
                  void updateView({ activeSourceId: event.target.value })
                }
                value={activeSource?.sourceId ?? ''}
              >
                {session.sources.map((source, index) => (
                  <option key={source.sourceId} value={source.sourceId}>
                    {source.corpusCaseId} · źródło {index + 1}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Grupa ujęć
              <input
                onChange={(event) => {
                  const sourceId = activeSource?.sourceId;
                  if (sourceId === undefined) return;
                  const value = event.currentTarget.value;
                  setCaptureGroupDrafts((current) => {
                    const next = new Map(current);
                    next.set(sourceId, value);
                    return next;
                  });
                }}
                onBlur={(event) => {
                  const sourceId = activeSource?.sourceId;
                  if (sourceId === undefined) return;
                  assignCaptureGroup(sourceId, event.currentTarget.value);
                }}
                value={
                  activeSource === null
                    ? ''
                    : captureGroupDrafts.get(activeSource.sourceId) ??
                      session.captureGroups[activeSource.sourceId] ??
                      ''
                }
                key={activeSource?.sourceId ?? 'none'}
                placeholder="np. przejście-A"
              />
            </label>
            <div className="v7LabelGeometryQueueStatus">
              <strong>Trwała kolejka: {queue.pending.length}</strong>
              <span>
                {queue.stoppedReason ?? 'Operacje są wysyłane po kolei.'}
              </span>
              <button
                className="secondaryButton"
                disabled={
                  queue.pending.length === 0 ||
                  queue.stoppedReason !== null ||
                  busy ||
                  syncing
                }
                onClick={() => void flushQueue()}
                type="button"
              >
                Ponów synchronizację
              </button>
              <button
                className="secondaryButton"
                disabled={queue.pending.length === 0 || busy || syncing}
                onClick={() => void discardPending()}
                type="button"
              >
                Porzuć niepotwierdzone
              </button>
            </div>
          </div>

          <div
            className="v7LabelGeometrySlots"
            aria-label="Pozycje etykiet 3 na 3"
          >
            {Array.from({ length: 9 }, (_, positionIndex) => {
              const slot = slots.find(
                (item) => item.positionIndex === positionIndex,
              );
              return (
                <button
                  aria-pressed={view.activePositionIndex === positionIndex}
                  className={
                    view.activePositionIndex === positionIndex
                      ? 'v7LabelGeometrySlot v7LabelGeometrySlotActive'
                      : 'v7LabelGeometrySlot'
                  }
                  key={positionIndex}
                  onClick={() =>
                    void updateView({ activePositionIndex: positionIndex })
                  }
                  type="button"
                >
                  <strong>{positionIndex + 1}</strong>
                  <span>{slotLabel(slot)}</span>
                </button>
              );
            })}
          </div>

          {readiness !== null ? (
            <section
              aria-label="Gotowość kalibracji profilu"
              className="v7LabelGeometryReadiness"
            >
              <h3>Gotowość do sprawdzenia profilu</h3>
              <p>
                Każda pozycja potrzebuje co najmniej{' '}
                {V7_LABEL_GEOMETRY_MINIMUM_SOURCES_PER_POSITION} różnych zdjęć
                i {V7_LABEL_GEOMETRY_MINIMUM_CAPTURE_GROUPS_PER_POSITION} grup
                ujęć z pełnym cropem. Serwer sprawdzi jeszcze residual p95.
              </p>
              <div className="v7LabelGeometryReadinessGrid">
                {readiness.positions.map((position) => (
                  <div
                    className={
                      position.readyForProfileCheck
                        ? 'v7LabelGeometryReadinessItem ready'
                        : 'v7LabelGeometryReadinessItem'
                    }
                    key={position.positionIndex}
                  >
                    <strong>Pozycja {position.positionIndex + 1}</strong>
                    <span>
                      Zdjęcia: {position.sourceCount}/
                      {V7_LABEL_GEOMETRY_MINIMUM_SOURCES_PER_POSITION}
                    </span>
                    <span>
                      Grupy: {position.captureGroupCount}/
                      {V7_LABEL_GEOMETRY_MINIMUM_CAPTURE_GROUPS_PER_POSITION}
                    </span>
                    <span>Pełne cropy: {position.containedAnnotationCount}</span>
                    {position.incompleteAnnotationCount > 0 ? (
                      <span>Niepełne: {position.incompleteAnnotationCount}</span>
                    ) : null}
                    {position.unavailableCount > 0 ? (
                      <span>Niewidoczne: {position.unavailableCount}</span>
                    ) : null}
                    <span>
                      {position.readyForProfileCheck
                        ? 'Gotowa do kontroli serwera'
                        : 'Potrzebne kolejne pełne oznaczenia'}
                    </span>
                  </div>
                ))}
              </div>
            </section>
          ) : null}

          <div className="v7LabelGeometryAssessment">
            <label>
              Ocena cropa wybranej etykiety
              <select
                onChange={(event) =>
                  void updateView({
                    cropAssessment: event.target
                      .value as V7LabelGeometryCropAssessment,
                  })
                }
                value={view.cropAssessment}
              >
                <option value="contained">Pełny, czytelny crop</option>
                <option value="clipped">Przycięty crop</option>
                <option value="uncertain">Niepewna widoczność</option>
              </select>
            </label>
            <button
              className="secondaryButton"
              disabled={
                busy ||
                syncing ||
                activeSource === null ||
                queue.stoppedReason !== null
              }
              onClick={markUnavailable}
              type="button"
            >
              Numer zasłonięty / nieczytelny
            </button>
            <span>
              Pozycja {view.activePositionIndex + 1}: {slotLabel(activeSlot)}.
              Kliknij środek numeru na obrazie, aby zapisać punkt.
            </span>
          </div>

          <div className="v7LabelGeometryImageFrame">
            {activeAssetUrl !== null ? (
              <div className="v7LabelGeometryImageCanvas">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  alt="Kanoniczny obraz do kalibracji etykiety"
                  className="v7LabelGeometryImage"
                  onClick={(event) => void annotate(event)}
                  src={activeAssetUrl}
                />
                <div
                  aria-hidden="true"
                  className="v7LabelGeometryPointOverlay"
                >
                  {slots
                    .filter(
                      (slot) =>
                        slot.state === 'annotated' &&
                        slot.centerX !== null &&
                        slot.centerY !== null,
                    )
                    .map((slot) => (
                      <span
                        className="v7LabelGeometryPoint"
                        key={slot.positionIndex}
                        style={{
                          left: `${slot.centerX! * 100}%`,
                          top: `${slot.centerY! * 100}%`,
                        }}
                      >
                        {slot.positionIndex + 1}
                      </span>
                    ))}
                </div>
              </div>
            ) : (
              <p>
                {assetError !== '' ? assetError : 'Wczytuję kanoniczny PNG…'}
              </p>
            )}
          </div>

          <div className="v7LabelGeometryFinalization">
            <button
              className="secondaryButton"
              disabled={
                busy ||
                syncing ||
                queue.pending.length > 0 ||
                queue.stoppedReason !== null
              }
              onClick={() => void exportSession(false)}
              type="button"
            >
              Eksportuj snapshot
            </button>
            <button
              className="primaryButton"
              disabled={
                busy ||
                syncing ||
                queue.pending.length > 0 ||
                queue.stoppedReason !== null ||
                readiness?.readyForProfileCheck !== true
              }
              onClick={() => void exportSession(true)}
              type="button"
            >
              Sprawdź i utwórz profil
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function clampPosition(value: number): number {
  return Number.isSafeInteger(value) ? Math.min(8, Math.max(0, value)) : 0;
}

function sourceExists(
  session: V7LabelGeometrySessionResponse,
  sourceId: string | null,
): sourceId is string {
  return (
    sourceId !== null &&
    session.sources.some((source) => source.sourceId === sourceId)
  );
}

function slotLabel(slot: V7LabelGeometrySlotResponse | undefined): string {
  switch (slot?.state) {
    case 'annotated':
      return 'oznaczony';
    case 'unavailable':
      return 'niewidoczny';
    default:
      return 'do oznaczenia';
  }
}
