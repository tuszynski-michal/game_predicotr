'use client';

import type {
  AdminApiClient,
  SemiAutomaticSelectionRangeResponse,
  SemiAutomaticSelectionRunResponse,
  V7SourceDiagnosticsResponse,
  V7OutputDecisionRequest,
} from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { apiErrorMessage } from '@/features/catalog/catalog-api-error';
import { preferredV7Source } from './v7-review-navigation.ts';
import {
  ManualImageViewer,
  useManualImageViewer,
} from '@/features/manual-image-selection/manual-image-viewer';
import type { SemiAutomaticReviewSourceFile } from './semi-automatic-selection-actions.ts';
import type { SemiAutomaticSelectionLocalUiState } from './semi-automatic-selection-output-storage.ts';
import {
  IndexedDbV7DecisionStore,
  type V7DecisionStore,
  type V7SavedDecision,
} from './v7-selection-decision-storage.ts';

type ReviewClient = Pick<
  AdminApiClient,
  | 'listSemiAutomaticImageSelectionRanges'
  | 'listSemiAutomaticImageSelectionSources'
  | 'acknowledgeSemiAutomaticImageSelectionOutput'
  | 'getSemiAutomaticImageSelection'
>;
interface Props {
  readonly feedbackTraceReady?: boolean;
  readonly client: ReviewClient;
  readonly decisionStore?: V7DecisionStore;
  readonly initialUi: SemiAutomaticSelectionLocalUiState | null;
  readonly onPersistUi: (
    ui: SemiAutomaticSelectionLocalUiState,
  ) => Promise<void>;
  readonly onRunUpdated?: (run: SemiAutomaticSelectionRunResponse) => void;
  readonly run: SemiAutomaticSelectionRunResponse;
  readonly sourceFiles: readonly SemiAutomaticReviewSourceFile[];
}
const PAGE_SIZE = 50;
const pendingState = (item: SemiAutomaticSelectionRangeResponse | null) =>
  item?.outputOperation?.state === 'reserved' ||
  item?.outputOperation?.state === 'recovery_required';

export function V7SelectionReviewWorkspace({
  feedbackTraceReady = false,
  client,
  decisionStore,
  initialUi,
  onPersistUi,
  onRunUpdated,
  run,
  sourceFiles,
}: Props) {
  const store = useMemo(
    () => decisionStore ?? new IndexedDbV7DecisionStore(),
    [decisionStore],
  );
  const maximumExpectedIndex = Math.max(
    0,
    Math.ceil((run.lastSequenceNumber - run.firstSequenceNumber + 1) / 9) - 1,
  );
  const traversalStep = run.direction === 'descending' ? -1 : 1;
  const firstExpectedIndex = traversalStep === -1 ? maximumExpectedIndex : 0;
  const [sourceIndex, setSourceIndex] = useState(() =>
    clampSourceIndex(initialUi?.viewSourceIndex ?? 0, sourceFiles.length),
  );
  const [activeIndex, setActiveIndex] = useState(
    initialUi?.activeExpectedIndex ?? firstExpectedIndex,
  );
  const [pageStart, setPageStart] = useState(
    () =>
      Math.floor(
        (initialUi?.activeExpectedIndex ?? firstExpectedIndex) / PAGE_SIZE,
      ) * PAGE_SIZE,
  );
  const [ranges, setRanges] = useState<
    readonly SemiAutomaticSelectionRangeResponse[]
  >([]);
  const [nextPage, setNextPage] = useState<number | null>(null);
  const [diagnostics, setDiagnostics] =
    useState<V7SourceDiagnosticsResponse | null>(null);
  const [sourceSha, setSourceSha] = useState<string | null>(null);
  const [sourceRelativePath, setSourceRelativePath] = useState<string | null>(
    null,
  );
  const [saved, setSaved] = useState<V7SavedDecision | null>(null);
  const [storageReady, setStorageReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [refreshError, setRefreshError] = useState('');
  const [storageError, setStorageError] = useState('');
  const [sourceError, setSourceError] = useState('');
  const [sourceRefreshAttempt, setSourceRefreshAttempt] = useState(0);
  const [viewerError, setViewerError] = useState('');
  const [previewAttempt, setPreviewAttempt] = useState(0);
  const [notice, setNotice] = useState('');
  const [confirmedIdentity, setConfirmedIdentity] = useState<string | null>(
    null,
  );
  const [incomplete, setIncomplete] = useState(false);
  const [withoutOcr, setWithoutOcr] = useState(false);
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [correctionReason, setCorrectionReason] = useState<
    NonNullable<V7OutputDecisionRequest['correctionReason']> | ''
  >('');
  const restoredUiRef = useRef(initialUi);
  const restoredViewAppliedRef = useRef(initialUi !== null);
  const formIdentityRef = useRef('');
  const openedRangeRef = useRef<string | null>(null);
  const sendInFlightRef = useRef(false);
  const settledOperationRef = useRef<string | null>(null);
  const pendingViewRef = useRef<SemiAutomaticSelectionLocalUiState | null>(
    null,
  );
  const persistingViewRef = useRef(false);
  const active =
    ranges.find((item) => item.expectedIndex === activeIndex) ?? null;
  const pending = saved !== null || pendingState(active);
  const hasOwner = active?.v7OutputOwnerOperationId != null;
  const sourceProven =
    active?.v7Review?.provenSources.some(
      (proof) => proof.sourceIndex === sourceIndex,
    ) ?? false;
  const partial = Number(end) - Number(start) + 1 < 9;
  const decisionIdentity = JSON.stringify([
    run.id,
    active?.id,
    active?.revision,
    active?.v7OutputOwnerOperationId,
    sourceIndex,
    sourceSha,
    start,
    end,
    incomplete,
    withoutOcr,
  ]);
  const confirmed = confirmedIdentity === decisionIdentity;
  function setConfirmed(value: boolean) {
    setConfirmedIdentity(value ? decisionIdentity : null);
  }
  const moveSource = useCallback(
    (index: number) => {
      setConfirmedIdentity(null);
      setIncomplete(false);
      setWithoutOcr(false);
      setCorrectionReason('');
      setDiagnostics(null);
      setSourceSha(null);
      setSourceRelativePath(null);
      setSourceIndex(clampSourceIndex(index, sourceFiles.length));
    },
    [sourceFiles.length],
  );
  const moveRange = useCallback((index: number) => {
    setConfirmedIdentity(null);
    setIncomplete(false);
    setWithoutOcr(false);
    setCorrectionReason('');
    setActiveIndex(index);
    setPageStart(Math.floor(index / PAGE_SIZE) * PAGE_SIZE);
  }, []);
  const lastExpectedIndex =
    run.direction === 'descending'
      ? 0
      : (run.lastSequenceNumber - run.firstSequenceNumber + 1) / 9 - 1;
  const rangeValid =
    active !== null &&
    Number.isSafeInteger(Number(start)) &&
    Number.isSafeInteger(Number(end)) &&
    Number(start) >= active.rangeStart &&
    Number(end) <= active.rangeEnd &&
    Number(end) >= Number(start) &&
    (!partial ||
      (activeIndex === lastExpectedIndex &&
        incomplete &&
        (withoutOcr || hasOwner)));
  const sourceDecisionReady =
    active?.v7Review != null &&
    ['analysis_complete', 'review_mode'].includes(run.status) &&
    storageReady &&
    storageError === '' &&
    sourceError === '' &&
    sourceSha !== null &&
    diagnostics !== null &&
    diagnostics.sourceIndex === sourceIndex &&
    diagnostics.sourceChecksumSha256 === sourceSha &&
    diagnostics.sourceErrorCode == null &&
    rangeValid;

  const settleDecision = useCallback(
    async (
      command: V7SavedDecision,
      row: SemiAutomaticSelectionRangeResponse,
    ) => {
      const receipt = row.acknowledgementReceipt;
      if (
        row.expectedIndex !== command.expectedIndex ||
        receipt?.operationId !== command.body.operationId
      )
        return;
      if (settledOperationRef.current === receipt.operationId) return;
      settledOperationRef.current = receipt.operationId;
      try {
        await store.clear(run.id, command.body.operationId);
      } catch (failure) {
        settledOperationRef.current = null;
        throw failure;
      }
      setSaved(null);
      setConfirmedIdentity(null);
      if (receipt.state === 'committed') {
        setNotice(`Zapisano na dysku: ${receipt.targetName}.`);
        const nextIndex = command.expectedIndex + traversalStep;
        if (
          command.advanceAfterCommit &&
          nextIndex >= 0 &&
          nextIndex <= maximumExpectedIndex
        )
          moveRange(nextIndex);
      } else {
        setNotice('');
        setError(
          `Nie zapisano zdjęcia (${receipt.errorCode ?? receipt.state}). Pozostajesz na tym zakresie. Po usunięciu błędu możesz zatwierdzić ponownie.`,
        );
      }
      try {
        const updated = await client.getSemiAutomaticImageSelection(run.id);
        if (updated.data !== undefined) onRunUpdated?.(updated.data);
      } catch {
        setRefreshError(
          'Decyzja rozliczona. Nie udało się odświeżyć podsumowania; odśwież ekran.',
        );
      }
    },
    [
      client,
      maximumExpectedIndex,
      moveRange,
      onRunUpdated,
      run.id,
      store,
      traversalStep,
    ],
  );

  const refresh = useCallback(async () => {
    const result = await client.listSemiAutomaticImageSelectionRanges(
      run.id,
      pageStart === 0 ? undefined : pageStart - 1,
      PAGE_SIZE,
    );
    if (result.error !== undefined || result.data === undefined)
      throw new Error(
        apiErrorMessage(result.error, 'Nie udało się odświeżyć zakresów.'),
      );
    setRanges(result.data.items);
    setNextPage(result.data.nextAfterExpectedIndex ?? null);
    setRefreshError('');
    let local: V7SavedDecision | null;
    try {
      local = await store.load(run.id);
    } catch (failure) {
      setStorageReady(false);
      setStorageError(message(failure));
      throw failure;
    }
    if (local !== null) {
      const matching = result.data.items.find(
        (row) => row.outputOperation?.operationId === local.body.operationId,
      );
      if (
        matching?.acknowledgementReceipt?.operationId === local.body.operationId
      ) {
        await settleDecision(local, matching);
      } else setSaved(local);
    }
  }, [client, pageStart, run.id, settleDecision, store]);
  useEffect(() => {
    if (active === null || !storageReady) return;
    const identity = `${active.id}:${active.revision}`;
    if (formIdentityRef.current !== identity) {
      formIdentityRef.current = identity;
      setConfirmedIdentity(null);
      setIncomplete(false);
      setWithoutOcr(false);
      setCorrectionReason('');
      setStart(String(active.v7ConfirmedRange?.start ?? active.rangeStart));
      setEnd(String(active.v7ConfirmedRange?.end ?? active.rangeEnd));
    }
    if (openedRangeRef.current === active.id) return;
    const firstView = openedRangeRef.current === null;
    openedRangeRef.current = active.id;
    const restored =
      firstView && initialUi?.activeExpectedIndex === active.expectedIndex
        ? initialUi.viewSourceIndex
        : null;
    const index =
      saved?.expectedIndex === active.expectedIndex
        ? saved.body.sourceIndex
        : (restored ?? preferredV7Source(active) ?? sourceIndex);
    if (index !== sourceIndex) moveSource(index);
  }, [active, initialUi, moveSource, saved, sourceIndex, storageReady]);
  useEffect(() => {
    let cancelled = false;
    void store
      .load(run.id)
      .then((command) => {
        if (cancelled) return;
        setSaved(command);
        if (command !== null) {
          moveRange(command.expectedIndex);
          moveSource(command.body.sourceIndex);
        }
        setStorageReady(true);
      })
      .catch(() => {
        if (!cancelled)
          setStorageError(
            'Nie można trwale zapisać decyzji w tej przeglądarce. Zapis jest zablokowany.',
          );
      });
    return () => {
      cancelled = true;
    };
  }, [moveRange, moveSource, run.id, store]);
  useEffect(() => {
    void Promise.resolve()
      .then(refresh)
      .catch((failure: unknown) => setRefreshError(message(failure)));
  }, [refresh, run.revision]);
  useEffect(() => {
    let cancelled = false;
    void client
      .listSemiAutomaticImageSelectionSources(
        run.id,
        sourceIndex === 0 ? undefined : sourceIndex - 1,
        1,
      )
      .then((result) => {
        if (cancelled) return;
        const source = result.data?.items[0];
        if (result.error !== undefined || source?.sourceIndex !== sourceIndex) {
          setSourceError(
            apiErrorMessage(
              result.error,
              result.error instanceof Error
                ? `Nie udało się odczytać badanego zdjęcia: ${result.error.message}`
                : 'Nie udało się odczytać badanego zdjęcia.',
            ),
          );
          return;
        }
        setDiagnostics(source.v7Diagnostics ?? null);
        setSourceSha(source.checksumSha256);
        setSourceRelativePath(source.relativePath);
        setSourceError('');
      })
      .catch((failure: unknown) => {
        if (!cancelled)
          setSourceError(
            `Nie udało się odczytać badanego zdjęcia: ${message(failure)}`,
          );
      });
    return () => {
      cancelled = true;
    };
  }, [client, run.id, sourceIndex, run.revision, sourceRefreshAttempt]);
  useEffect(() => {
    if (!pending) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let remaining = 900; // Bounded wait; only the current page, never a full checkpoint.
    let fastPollsRemaining = 4;
    const pollDelay = () => (fastPollsRemaining-- > 0 ? 500 : 2000);
    const deadline = Date.now() + 30 * 60 * 1000;
    const poll = async () => {
      if (cancelled) return;
      if (remaining-- <= 0 || Date.now() >= deadline) {
        setNotice(
          'Oczekiwanie na zapis trwa ponad 30 minut. Odśwież stan lub ponów tę samą decyzję; nie zatwierdzaj jej drugi raz.',
        );
        return;
      }
      await refresh().catch((failure: unknown) =>
        setRefreshError(message(failure)),
      );
      if (!cancelled) timer = setTimeout(() => void poll(), pollDelay());
    };
    timer = setTimeout(() => void poll(), pollDelay());
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [pending, refresh]);

  const viewerFiles = useMemo(
    () =>
      sourceFiles.map((source) => ({
        handle: source.handle,
        relativePath: source.relativePath,
      })),
    [sourceFiles],
  );
  const onViewerError = useCallback(
    (value: string) => setViewerError(value),
    [],
  );
  const persistView = useCallback(
    (view: {
      readonly scrollLeft: number;
      readonly scrollTop: number;
      readonly zoom: number;
    }) => {
      const ui: SemiAutomaticSelectionLocalUiState = {
        activeExpectedIndex: activeIndex,
        mode: 'review',
        scanSourceIndex: restoredUiRef.current?.scanSourceIndex ?? null,
        sequenceExpectedIndex:
          restoredUiRef.current?.sequenceExpectedIndex ?? null,
        scrollLeft: view.scrollLeft,
        scrollTop: view.scrollTop,
        viewSourceIndex: sourceIndex,
        zoomPercent: Math.round(view.zoom * 100),
      };
      restoredUiRef.current = ui;
      // Keep one in-flight write and only the newest pending view. A slow
      // IndexedDB response cannot overwrite a newer range/photo after restart.
      pendingViewRef.current = ui;
      if (!persistingViewRef.current) {
        persistingViewRef.current = true;
        void (async () => {
          try {
            while (pendingViewRef.current !== null) {
              const next = pendingViewRef.current;
              pendingViewRef.current = null;
              await onPersistUi(next);
            }
          } catch (failure) {
            setError(message(failure));
          } finally {
            persistingViewRef.current = false;
          }
        })();
      }
    },
    [activeIndex, onPersistUi, sourceIndex],
  );
  const nextRangeSourceIndexes = useMemo(() => {
    const activeSource = preferredV7Source(active);
    // Range and source update in separate effects. Keep the newly opened
    // proposal warm until moveSource applies, rather than evicting it first.
    const opening =
      activeSource != null && activeSource !== sourceIndex
        ? [activeSource]
        : [];
    return [
      ...opening,
      ...[1, 2].flatMap((offset) => {
        const next = ranges.find(
          (item) => item.expectedIndex === activeIndex + offset * traversalStep,
        );
        const index = preferredV7Source(next ?? null);
        return index == null ? [] : [index];
      }),
    ].slice(0, 2);
  }, [active, activeIndex, ranges, sourceIndex, traversalStep]);
  const viewer = useManualImageViewer(
    viewerFiles,
    sourceIndex,
    onViewerError,
    {
      scrollLeft: initialUi?.scrollLeft ?? 0,
      scrollTop: initialUi?.scrollTop ?? 0,
      zoom: (initialUi?.zoomPercent ?? 100) / 100,
    },
    persistView,
    `${run.id}:${previewAttempt}`,
    nextRangeSourceIndexes,
  );
  const photoReady =
    sourceDecisionReady &&
    viewer.visibleImageUrl !== null &&
    viewer.sourceImageSize !== null &&
    viewer.sourceImageSize.width > 0 &&
    viewer.sourceImageSize.height > 0;
  const quickReady =
    photoReady &&
    !hasOwner &&
    !withoutOcr &&
    !partial &&
    Number(start) === active?.rangeStart &&
    Number(end) === active?.rangeEnd;
  const ready =
    photoReady && confirmed && (sourceProven || withoutOcr || hasOwner);
  useEffect(() => {
    if (initialUi === null || restoredViewAppliedRef.current) return;
    restoredUiRef.current = initialUi;
    restoredViewAppliedRef.current = true;
    setConfirmedIdentity(null);
    setIncomplete(false);
    setWithoutOcr(false);
    setDiagnostics(null);
    setSourceSha(null);
    setSourceIndex(
      clampSourceIndex(initialUi.viewSourceIndex ?? 0, sourceFiles.length),
    );
    setActiveIndex(initialUi.activeExpectedIndex ?? firstExpectedIndex);
    setPageStart(
      Math.floor(
        (initialUi.activeExpectedIndex ?? firstExpectedIndex) / PAGE_SIZE,
      ) * PAGE_SIZE,
    );
  }, [firstExpectedIndex, initialUi, sourceFiles.length]);

  async function send(command: V7SavedDecision) {
    if (sendInFlightRef.current) return;
    sendInFlightRef.current = true;
    setBusy(true);
    setError('');
    try {
      try {
        await store.save(command);
      } catch (failure) {
        setStorageReady(false);
        setStorageError(message(failure));
        throw failure;
      }
      setSaved(command);
      const result = await client.acknowledgeSemiAutomaticImageSelectionOutput(
        run.id,
        command.expectedIndex,
        command.body,
      );
      if (result.error !== undefined || result.data === undefined) {
        const code = result.error?.code;
        if (
          code === 'SEMI_AUTOMATIC_SELECTION_CURSOR_STALE' ||
          code === 'V7_OUTPUT_OWNER_CHANGED'
        ) {
          await store.clear(run.id, command.body.operationId);
          setSaved(null);
          setConfirmed(false);
        }
        throw new Error(
          apiErrorMessage(
            result.error,
            'Nie otrzymano potwierdzenia. Ponów tę samą decyzję.',
          ),
        );
      }
      const acknowledged = result.data;
      setRanges((current) =>
        current.map((row) =>
          row.expectedIndex === acknowledged.expectedIndex ? acknowledged : row,
        ),
      );
      if (
        acknowledged.acknowledgementReceipt?.operationId ===
        command.body.operationId
      ) {
        await settleDecision(command, acknowledged);
      } else
        setNotice(
          'Zapis w toku. Potwierdzenie pojawi się po zakończeniu zapisu.',
        );
      setConfirmed(false);
      // A reservation is not a published JPEG. Pending polling checks receipts.
      // Refreshing the entire run/checkpoint is unnecessary on an immediate receipt.
    } catch (failure) {
      setError(message(failure));
    } finally {
      sendInFlightRef.current = false;
      setBusy(false);
    }
  }
  function confirm(advanceAfterCommit = false, quick = false) {
    if (
      !(quick ? quickReady : ready) ||
      active === null ||
      sourceSha === null ||
      busy ||
      pending
    )
      return;
    void send({
      runId: run.id,
      expectedIndex: active.expectedIndex,
      ...(advanceAfterCommit ? { advanceAfterCommit: true } : {}),
      body: {
        workflowMode: 'v7_selection',
        operationId: crypto.randomUUID(),
        expectedRevision: active.revision,
        sourceIndex,
        expectedSourceChecksumSha256: sourceSha,
        kind: hasOwner
          ? 'manual_replace'
          : withoutOcr || (quick && !sourceProven)
            ? 'manual_no_ocr'
            : 'manual_first',
        confirmedRange: { start: Number(start), end: Number(end) },
        operatorConfirmedRange: true,
        operatorConfirmedIncompletePage: incomplete,
        expectedTargetChecksumSha256: hasOwner
          ? active.outputChecksumSha256
          : null,
        expectedOwnerOperationId: hasOwner
          ? active.v7OutputOwnerOperationId
          : null,
        ...(!feedbackTraceReady || correctionReason === ''
          ? {}
          : { correctionReason }),
      },
    });
  }
  useEffect(() => {
    function handleKey(event: KeyboardEvent) {
      if (
        event.repeat ||
        event.ctrlKey ||
        event.metaKey ||
        event.altKey ||
        event.shiftKey ||
        busy ||
        pending
      )
        return;
      const target = event.target;
      if (
        target instanceof Element &&
        target.closest(
          'input, select, textarea, button, summary, a, [contenteditable="true"], [role="textbox"]',
        )
      )
        return;
      if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
        event.preventDefault();
        moveSource(sourceIndex + (event.key === 'ArrowLeft' ? -1 : 1));
      } else if (event.key === 'PageUp' || event.key === 'PageDown') {
        event.preventDefault();
        moveRange(
          Math.max(
            0,
            Math.min(
              maximumExpectedIndex,
              activeIndex +
                (event.key === 'PageUp' ? -traversalStep : traversalStep),
            ),
          ),
        );
      } else if (event.key === 'Enter' && (quickReady || ready)) {
        event.preventDefault();
        confirm(true, quickReady);
      }
    }
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  });
  if (sourceFiles.length === 0) return null;
  return (
    <section className="semiAutomaticSelectionReview" aria-label="Podgląd V7">
      <div className="semiAutomaticSelectionReviewHeading">
        <div>
          <p className="eyebrow">ZATWIERDZANIE ZDJĘĆ V7</p>
          <h2>
            Zakres {active?.rangeStart ?? '…'}–{active?.rangeEnd ?? '…'}
          </h2>
          <p>
            Sprawdź zdjęcie i numery. Zatwierdzenie zapisuje oryginalny JPEG.
          </p>
        </div>
      </div>
      {storageError !== '' ||
      error !== '' ||
      refreshError !== '' ||
      sourceError !== '' ||
      viewerError !== '' ? (
        <p className="feedbackBanner feedbackBannerError" role="alert">
          {storageError || error || refreshError || sourceError || viewerError}
        </p>
      ) : null}
      {notice !== '' ? <p role="status">{notice}</p> : null}
      <p>
        Katalog wynikowy:{' '}
        <strong>
          {run.outputDirectory ??
            (run.source?.displayName
              ? `${run.source.displayName} cut (obok źródła)`
              : 'sąsiedni katalog źródła z końcówką „ cut”')}
        </strong>
        . Nazwa pliku:{' '}
        <strong>
          seq_{start || '…'}-{end || '…'}.jpg
        </strong>
        .{' '}
        {active?.status === 'output_synced'
          ? 'Zdjęcie zapisane. Możesz obejrzeć je lub zastąpić.'
          : pending
            ? 'Trwa zapis. Plik nie został jeszcze potwierdzony.'
            : active?.v7Review?.draft != null
              ? 'Kopia propozycji jest już zapisana. Sprawdź ją i zatwierdź lub wybierz sąsiada.'
              : active?.v7Review?.candidate != null
                ? 'Propozycja czeka na Twoje zatwierdzenie; nie jest jeszcze plikiem wynikowym.'
                : 'Brak gotowej propozycji dla tego zakresu. Po skanie możesz wybrać zdjęcie ręcznie.'}
      </p>
      {active?.v7Review?.draft != null ? (
        <p role="status">
          {active.v7Review.draft.estimated
            ? 'Numer oszacowany przez podział między rozpoznanymi grupami. Sprawdź zakres na zdjęciu.'
            : 'Propozycja z niepełnego odczytu. Sprawdź zakres na zdjęciu.'}{' '}
          Kopia: <strong>{active.v7Review.draft.directory}</strong>. Możesz
          wybrać sąsiednie zdjęcie i zatwierdzić poprawny zakres.
        </p>
      ) : null}
      {!['analysis_complete', 'review_mode', 'completed'].includes(
        run.status,
      ) ? (
        <p role="status">
          Analiza katalogu trwa. Zatwierdzanie propozycji będzie dostępne po
          zakończeniu skanu.
        </p>
      ) : null}
      <div className="v7ReviewNavigation">
        <button
          type="button"
          style={{ minHeight: 44 }}
          disabled={activeIndex === firstExpectedIndex || busy || pending}
          onClick={() => moveRange(activeIndex - traversalStep)}
        >
          Poprzedni zakres
        </button>
        <button
          type="button"
          style={{ minHeight: 44 }}
          disabled={activeIndex === lastExpectedIndex || busy || pending}
          onClick={() => moveRange(activeIndex + traversalStep)}
        >
          Następny zakres
        </button>
        <button
          type="button"
          style={{ minHeight: 44 }}
          disabled={pageStart === 0 || busy || pending}
          onClick={() => {
            const previous = Math.max(0, pageStart - PAGE_SIZE);
            setPageStart(previous);
            moveRange(previous);
          }}
        >
          Poprzednie zakresy
        </button>
        <label>
          Oczekiwany zakres
          <select
            style={{ minHeight: 44 }}
            value={activeIndex}
            disabled={busy || pending}
            onChange={(event) => {
              moveRange(Number(event.target.value));
            }}
          >
            {ranges.map((item) => (
              <option key={item.id} value={item.expectedIndex}>
                {item.rangeStart}–{item.rangeEnd} ·{' '}
                {item.status === 'proposed'
                  ? 'propozycja'
                  : item.status === 'output_synced'
                    ? 'zapisany'
                    : item.v7Review?.draft != null
                      ? item.v7Review.draft.estimated
                        ? 'numer oszacowany'
                        : 'propozycja do sprawdzenia'
                      : 'brak propozycji'}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          style={{ minHeight: 44 }}
          disabled={nextPage === null || busy || pending}
          onClick={() => {
            setPageStart((nextPage ?? pageStart) + 1);
            moveRange((nextPage ?? pageStart) + 1);
          }}
        >
          Następne zakresy
        </button>
        <button
          type="button"
          style={{ minHeight: 44 }}
          disabled={busy}
          onClick={() => {
            if (sourceError !== '')
              setSourceRefreshAttempt((attempt) => attempt + 1);
            void refresh().catch((failure: unknown) =>
              setRefreshError(message(failure)),
            );
          }}
        >
          Odśwież stan
        </button>
      </div>
      <p>
        Propozycja:{' '}
        {preferredV7Source(active) === null
          ? 'brak propozycji'
          : 'zdjęcie ' + (preferredV7Source(active)! + 1)}{' '}
        · zdjęcie {sourceIndex + 1}:{' '}
        {sourceRelativePath ?? sourceFiles[sourceIndex]?.relativePath}.
      </p>
      {preferredV7Source(active) !== null ? (
        <button
          type="button"
          style={{ minHeight: 44 }}
          disabled={busy || pending}
          onClick={() => moveSource(preferredV7Source(active)!)}
          className="secondaryButton"
        >
          Pokaż proponowane zdjęcie
        </button>
      ) : null}
      {diagnostics?.slots.some(
        (slot) =>
          slot.readability === 'unknown' || slot.visibility === 'unknown',
      ) ? (
        <p>
          Jakość symboli: nieustalona. Sprawdź ich czytelność i widoczność przed
          zapisem.
        </p>
      ) : null}
      {pending ? (
        <div role="status">
          <strong>Zapis w toku — czekamy na plik na dysku</strong>
          <p>
            {active?.outputOperation?.errorCode ??
              'Oczekujemy na potwierdzenie serwera. Możesz odświeżyć stan.'}
          </p>
          {saved !== null ? (
            <button
              type="button"
              style={{ minHeight: 44 }}
              disabled={busy}
              onClick={() => void send(saved)}
            >
              Ponów tę samą decyzję
            </button>
          ) : null}
        </div>
      ) : null}
      {diagnostics !== null ? (
        <details className="v7ReviewDiagnostics">
          <summary>
            Szczegóły odczytu i jakości —{' '}
            {
              diagnostics.slots.filter((slot) => slot.sequenceNumber !== null)
                .length
            }
            /9 numerów odczytanych
          </summary>
          <p>
            Dowód odczytu:{' '}
            {diagnostics.proof.kind === 'none'
              ? 'brak'
              : diagnostics.proof.kind === 'strong_five_label'
                ? '5 etykiet z jednego zdjęcia'
                : diagnostics.proof.kind === 'multi_frame_three_plus_three'
                  ? '3 + 3 z niezależnych zdjęć'
                  : 'pełny odczyt'}
            . Zdjęcia wspierające:{' '}
            {diagnostics.proof.supportingSourceIds.length}.{' '}
            {diagnostics.proof.reasonCodes.join(', ')}
          </p>
          {active?.v7Review?.provenSources
            .filter((proof) =>
              diagnostics.proof.supportingSourceIds.includes(proof.sourceId),
            )
            .map((proof) => (
              <button
                key={proof.sourceId}
                type="button"
                style={{ minHeight: 44 }}
                disabled={busy || pending}
                onClick={() => moveSource(proof.sourceIndex)}
              >
                Pokaż zdjęcie wspierające {proof.sourceIndex + 1}
              </button>
            ))}
          <p>
            Sprawdź znaki i brzegi każdej planszy. „Nieustalone” wymaga ręcznej
            oceny.
          </p>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
              gap: 8,
            }}
            aria-label="Dziewięć pozycji etykiet"
          >
            {diagnostics.slots.map((slot) => (
              <div
                key={slot.positionIndex}
                style={{ padding: 8, border: '1px solid currentColor' }}
              >
                <strong>
                  Pozycja {slot.positionIndex + 1}:{' '}
                  {slot.sequenceNumber ?? 'brak numeru'}
                </strong>
                <p>
                  {slot.state === 'not_observed'
                    ? 'Etykieta niewykryta'
                    : slot.state === 'observed_without_number'
                      ? 'Etykieta wykryta, numer nieodczytany'
                      : 'Numer odczytany'}
                </p>
                <p>
                  Pewność odczytu numeru:{' '}
                  {confidenceLabel(slot.recognitionConfidence)}
                  {' · '}przypisania pozycji:{' '}
                  {confidenceLabel(slot.positionConfidence)}
                </p>
                <p>
                  Jakość symboli — czytelność: {qualityLabel(slot.readability)}{' '}
                  · widoczność: {qualityLabel(slot.visibility)} · rozmycie:{' '}
                  {qualityLabel(slot.blur)} · zasłonięcie:{' '}
                  {qualityLabel(slot.occlusion)} · utrata znaków:{' '}
                  {qualityLabel(slot.symbolContentLoss)} · ramka:{' '}
                  {qualityLabel(slot.decoration)}
                </p>
              </div>
            ))}
          </div>
        </details>
      ) : (
        <p>
          Diagnostyka tego zdjęcia jeszcze niedostępna. Potwierdzenie zapisu
          jest zablokowane.
        </p>
      )}
      {viewerError !== '' &&
      (viewer.visibleImageUrl === null || viewer.sourceImageSize === null) ? (
        <button
          type="button"
          style={{ minHeight: 44 }}
          disabled={busy}
          onClick={() => {
            setConfirmedIdentity(null);
            setViewerError('');
            setPreviewAttempt((attempt) => attempt + 1);
          }}
        >
          Ponów wczytanie zdjęcia
        </button>
      ) : null}
      <ManualImageViewer
        busy={busy || pending}
        currentLabel={
          active?.status === 'output_synced' &&
          active.sourceIndex === sourceIndex
            ? 'Zapisane zdjęcie'
            : 'Zdjęcie do zatwierdzenia'
        }
        currentPosition={sourceIndex + 1}
        currentRelativePath={
          sourceRelativePath ?? sourceFiles[sourceIndex]?.relativePath ?? null
        }
        imageCount={sourceFiles.length}
        navigationStepLabel="←/→: sąsiednie zdjęcie · podgląd nie zatwierdza wyboru"
        nextDisabled={busy || pending || sourceIndex >= sourceFiles.length - 1}
        onNext={() =>
          moveSource(Math.min(sourceFiles.length - 1, sourceIndex + 1))
        }
        onPrevious={() => moveSource(Math.max(0, sourceIndex - 1))}
        previousDisabled={busy || pending || sourceIndex <= 0}
        state={viewer}
      />
      <div className="v7ReviewSaveBar" aria-label="Szybkie zatwierdzanie">
        <div>
          <strong>
            Zdjęcie {sourceIndex + 1} → zakres {start || '…'}–{end || '…'}
          </strong>
          <p>
            Enter: zatwierdź i zapisz · ←/→: inne zdjęcie · Page Up/Down: zakres
          </p>
          {!sourceProven && !hasOwner ? (
            <p>Bez dowodu OCR. Przycisk zatwierdza widoczny zakres ręcznie.</p>
          ) : null}
        </div>
        <button
          type="button"
          className="primaryButton"
          style={{ minHeight: 44 }}
          disabled={!(quickReady || ready) || busy || pending}
          onClick={() => confirm(true, quickReady)}
        >
          {hasOwner ? 'Zastąp' : 'Zatwierdź'} {start || '…'}–{end || '…'} i
          zapisz →
        </button>
        {quickReady ? (
          <button
            type="button"
            className="secondaryButton"
            style={{ minHeight: 44 }}
            disabled={busy || pending}
            onClick={() => confirm(false, true)}
          >
            Zapisz i pozostań
          </button>
        ) : null}
      </div>
      <details
        open={hasOwner || withoutOcr || partial}
        className="v7ReviewConfirmation"
      >
        <summary>
          {hasOwner
            ? 'Podmiana zapisanego zdjęcia'
            : 'Ręczny zakres i dodatkowe opcje'}
        </summary>
        <fieldset disabled={busy || pending || active === null}>
          <legend>
            {hasOwner
              ? 'Potwierdź zastąpienie zapisanego zdjęcia'
              : 'Potwierdź zapis zdjęcia'}
          </legend>
          <label>
            Pierwszy numer
            <input
              style={{ minHeight: 44 }}
              type="number"
              value={start}
              disabled={hasOwner}
              onChange={(event) => {
                setStart(event.target.value);
                setConfirmed(false);
              }}
            />
          </label>
          <label>
            Ostatni numer
            <input
              style={{ minHeight: 44 }}
              type="number"
              value={end}
              disabled={hasOwner}
              onChange={(event) => {
                setEnd(event.target.value);
                setConfirmed(false);
              }}
            />
          </label>
          {!hasOwner ? (
            <label style={{ display: 'block', minHeight: 44 }}>
              <input
                type="checkbox"
                checked={withoutOcr}
                onChange={(event) => {
                  setWithoutOcr(event.target.checked);
                  setConfirmed(false);
                }}
              />
              Znam zakres zdjęcia i potwierdzam go bez dowodu OCR.
            </label>
          ) : (
            <p>
              Zastąpienie zachowuje pierwszy zatwierdzony zakres{' '}
              {active?.v7ConfirmedRange?.start}–{active?.v7ConfirmedRange?.end}.
            </p>
          )}
          {partial ? (
            <label style={{ display: 'block', minHeight: 44 }}>
              <input
                type="checkbox"
                checked={incomplete}
                onChange={(event) => {
                  setIncomplete(event.target.checked);
                  setConfirmed(false);
                }}
              />
              Potwierdzam, że ostatnia oczekiwana strona jest rzeczywiście
              niepełna; niewidoczna etykieta nie wystarcza.
            </label>
          ) : null}
          {feedbackTraceReady ? (
            <label style={{ display: 'block', minHeight: 44 }}>
              Powód wyboru innego zdjęcia (opcjonalnie)
              <select
                style={{ minHeight: 44 }}
                value={correctionReason}
                onChange={(event) =>
                  setCorrectionReason(
                    event.target.value as typeof correctionReason,
                  )
                }
              >
                <option value="">Bez podania powodu</option>
                <option value="blur">Poprzednie zdjęcie było rozmyte</option>
                <option value="occlusion">
                  Poprzednie zdjęcie było zasłonięte
                </option>
                <option value="range_error">
                  Propozycja miała błędny zakres
                </option>
                <option value="framing">Lepsze kadrowanie</option>
                <option value="other">Inny powód</option>
              </select>
            </label>
          ) : (
            <p>
              Pełny ślad uczenia oczekuje na aktualizację serwera. Dotychczasowa
              historia decyzji pozostaje zapisywana.
            </p>
          )}
          <label style={{ display: 'block', minHeight: 44 }}>
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(event) => setConfirmed(event.target.checked)}
            />
            Sprawdziłem zdjęcie {sourceIndex + 1} i potwierdzam zakres {start}–
            {end}.
          </label>
          <button
            type="button"
            className="primaryButton"
            style={{ minHeight: 44 }}
            disabled={!ready || busy || pending}
            onClick={() => confirm()}
          >
            {hasOwner
              ? 'Zastąp zapisane zdjęcie'
              : 'Zapisz potwierdzone zdjęcie'}
          </button>
        </fieldset>
      </details>
    </section>
  );
}
function qualityLabel(value: string): string {
  return (
    (
      {
        unknown: 'nieustalone',
        none: 'brak',
        clear: 'czytelne',
        full: 'pełna',
        complete: 'pełna',
        partial: 'częściowa',
        missing: 'brak',
        minor: 'małe',
        major: 'duże',
        severe: 'duże',
        mild: 'małe',
        unreadable: 'nieczytelne',
      } as Record<string, string>
    )[value] ?? value
  );
}
function confidenceLabel(value: number | null | undefined): string {
  return typeof value === 'number' &&
    Number.isFinite(value) &&
    value >= 0 &&
    value <= 1
    ? `${(value * 100).toFixed(1).replace('.', ',')}%`
    : 'brak pomiaru';
}
function message(failure: unknown): string {
  return failure instanceof Error
    ? failure.message
    : 'Nie udało się sprawdzić decyzji.';
}
function clampSourceIndex(index: number, count: number): number {
  return !Number.isSafeInteger(index) || index < 0
    ? 0
    : Math.min(Math.max(0, count - 1), index);
}
