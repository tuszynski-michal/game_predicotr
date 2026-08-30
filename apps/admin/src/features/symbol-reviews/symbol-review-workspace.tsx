'use client';

/* Symbol-cell assets are checksum-bound local Admin API responses. */
/* eslint-disable @next/next/no-img-element */

import type {
  GameResponse,
  SymbolCellReviewFilterState,
  SymbolCellReviewListItemResponse,
  SymbolCellReviewBulkOperationResponse,
  SymbolCellReviewBulkPreviewResponse,
  SymbolCellReviewPageResponse,
  SymbolCellReviewProjectionStatusResponse,
  SymbolResponse,
} from '@game-predictor/admin-api-client';
import {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';

import {
  loadSymbolReviewGames,
  loadSymbolReviewPage,
  loadSymbolReviewProjection,
  loadSymbolReviewSymbols,
  startSymbolReviewProjection,
  type LoadSymbolReviewPageOptions,
  type SymbolReviewClient,
} from './symbol-review-actions';
import {
  createSymbolReviewBulkCommand,
  getSymbolReviewBulkOperation,
  isSymbolReviewBulkOperationTerminal,
  previewSymbolReviewBulkOperation,
  startSymbolReviewBulkOperation,
  type SymbolReviewBulkClient,
  type SymbolReviewBulkCommand,
} from './symbol-review-bulk-actions';
import {
  applySingleSymbolReviewDecision,
  type SymbolReviewMutationClient,
} from './symbol-review-mutation-actions';
import {
  createAllMatchingFilterSymbolReviewSelection,
  createEmptySymbolReviewSelection,
  isSymbolReviewItemSelected,
  selectVisibleSymbolReviewItems,
  selectedSymbolReviewCount,
  symbolReviewSelectionCurrentItemIds,
  toggleSymbolReviewItem,
  type SymbolReviewSelection,
} from './symbol-review-selection-state';
import {
  createSymbolReviewWorkspaceState,
  DEFAULT_SYMBOL_REVIEW_PAGE_SIZE,
  findCachedSymbolReviewPage,
  symbolReviewConfidenceRange,
  symbolReviewPageRange,
  symbolReviewWorkspaceReducer,
  type SymbolReviewFilters,
  type SymbolReviewPagePosition,
} from './symbol-review-state';
import {
  loadSymbolReviewVirtualPreviews,
  type SymbolReviewVirtualPreviewTile,
} from './symbol-review-virtual-previews.ts';
import { SymbolReviewVirtualGrid } from './symbol-review-virtual-grid.tsx';
import { shouldApplyVirtualPreviewResult } from './symbol-review-virtual-window.ts';
import styles from './symbol-review-workspace.module.css';

type LoadState = 'error' | 'loading' | 'ready';

type SymbolReviewWorkspaceClient = SymbolReviewClient & SymbolReviewBulkClient;
type SymbolReviewFullClient = SymbolReviewWorkspaceClient &
  SymbolReviewMutationClient;

type SymbolReviewOperationDialog =
  | {
      readonly command: SymbolReviewBulkCommand;
      readonly gameId: string;
      readonly kind: 'loading';
    }
  | {
      readonly command: SymbolReviewBulkCommand;
      readonly gameId: string;
      readonly idempotencyKey: string;
      readonly kind: 'ready';
      readonly preview: SymbolCellReviewBulkPreviewResponse;
    }
  | { readonly error: string; readonly kind: 'error' };

const INITIAL_FILTERS: SymbolReviewFilters = {
  confidence: 'all',
  gameId: null,
  pageSize: DEFAULT_SYMBOL_REVIEW_PAGE_SIZE,
  state: 'pending',
  symbolId: null,
};

interface SymbolReviewWorkspaceProps {
  readonly apiBaseUrl: string;
  readonly client?: SymbolReviewFullClient;
}

interface SymbolReviewToast {
  readonly kind: 'error' | 'success';
  readonly message: string;
}

interface TrackedSymbolReviewOperation {
  readonly operation: SymbolCellReviewBulkOperationResponse;
  readonly submittedCellIds: readonly string[];
}

export function SymbolReviewWorkspace({
  apiBaseUrl,
  client,
}: SymbolReviewWorkspaceProps) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const [workspace, dispatch] = useReducer(
    symbolReviewWorkspaceReducer,
    INITIAL_FILTERS,
    createSymbolReviewWorkspaceState,
  );
  const [games, setGames] = useState<readonly GameResponse[]>([]);
  const [symbols, setSymbols] = useState<readonly SymbolResponse[]>([]);
  const [gamesState, setGamesState] = useState<LoadState>('loading');
  const [symbolsState, setSymbolsState] = useState<LoadState>('ready');
  const [pageState, setPageState] = useState<LoadState>('ready');
  const [error, setError] = useState('');
  const [projectionStatus, setProjectionStatus] =
    useState<SymbolCellReviewProjectionStatusResponse | null>(null);
  const [projectionState, setProjectionState] = useState<LoadState>('ready');
  const [projectionStarting, setProjectionStarting] = useState(false);
  const [paging, setPaging] = useState(false);
  const [reloadRevision, setReloadRevision] = useState(0);
  const [directPendingCellIds, setDirectPendingCellIds] = useState<
    ReadonlySet<string>
  >(() => new Set());
  const [hiddenCellIds, setHiddenCellIds] = useState<ReadonlySet<string>>(
    () => new Set(),
  );
  const [selection, setSelection] = useState<SymbolReviewSelection>(
    createEmptySymbolReviewSelection,
  );
  const [pendingFilters, setPendingFilters] =
    useState<SymbolReviewFilters | null>(null);
  const [operationDialog, setOperationDialog] =
    useState<SymbolReviewOperationDialog | null>(null);
  const [activeOperations, setActiveOperations] = useState<
    Readonly<Record<string, TrackedSymbolReviewOperation>>
  >({});
  const [isStartingOperation, setIsStartingOperation] = useState(false);
  const [toast, setToast] = useState<SymbolReviewToast | null>(null);
  const [reassignTargetSymbolId, setReassignTargetSymbolId] = useState<
    string | null
  >(null);
  const [filtersConfirmed, setFiltersConfirmed] = useState(false);
  const [visibleItems, setVisibleItems] = useState<
    readonly SymbolCellReviewListItemResponse[]
  >([]);
  const [virtualPreviewTiles, setVirtualPreviewTiles] = useState<
    Readonly<Record<string, SymbolReviewVirtualPreviewTile>>
  >({});
  const gamesRequestId = useRef(0);
  const symbolsRequestId = useRef(0);
  const pageRequestId = useRef(0);
  const projectionRequestId = useRef(0);
  const filtersRef = useRef<SymbolReviewFilters>(INITIAL_FILTERS);
  const filtersConfirmedRef = useRef(false);
  const pagingRef = useRef(false);
  const pagePositionRef = useRef<SymbolReviewPagePosition>({ number: 1 });
  const virtualPreviewRequestId = useRef(0);

  const filters = workspace.filters;
  const currentPage = workspace.currentPage?.page ?? null;
  const currentPageNumber = workspace.currentPage?.position.number ?? 1;
  const currentItems = (currentPage?.items ?? []).filter(
    (item) => !hiddenCellIds.has(item.id),
  );
  const activeGame = games.find((game) => game.id === filters.gameId) ?? null;
  const trackedOperations = useMemo(
    () => Object.values(activeOperations),
    [activeOperations],
  );
  const pendingCellIds = useMemo(() => {
    const ids = new Set(directPendingCellIds);
    for (const tracked of trackedOperations) {
      for (const cellId of tracked.submittedCellIds) ids.add(cellId);
    }
    return ids;
  }, [directPendingCellIds, trackedOperations]);
  const selectedCount =
    currentPage === null ? 0 : selectedSymbolReviewCount(selection);
  const currentFilteredCount =
    currentPage === null
      ? 0
      : filteredSymbolReviewCount(currentPage, filters.state);
  const currentPageRange = symbolReviewPageRange(
    currentPageNumber,
    currentPage?.items.length ?? 0,
    filters.pageSize,
    currentFilteredCount,
  );
  const hasLoadError =
    gamesState === 'error' ||
    symbolsState === 'error' ||
    projectionState === 'error' ||
    pageState === 'error';
  const interactionBusy =
    directPendingCellIds.size > 0 ||
    isStartingOperation ||
    operationDialog !== null ||
    paging;

  const applyFilters = useCallback((nextFilters: SymbolReviewFilters) => {
    const previousFilters = filtersRef.current;
    filtersRef.current = nextFilters;
    pageRequestId.current += 1;
    pagePositionRef.current = { number: 1 };
    setError('');
    setSelection(createEmptySymbolReviewSelection());
    setHiddenCellIds(new Set());
    setVisibleItems([]);
    setVirtualPreviewTiles({});
    setReassignTargetSymbolId(null);
    if (previousFilters.gameId !== nextFilters.gameId) {
      setSymbols([]);
      setSymbolsState(nextFilters.gameId === null ? 'ready' : 'loading');
      setProjectionStatus(null);
      setProjectionState(nextFilters.gameId === null ? 'ready' : 'loading');
    }
    setPageState(
      asPageFilters(nextFilters) === null || !filtersConfirmedRef.current
        ? 'ready'
        : 'loading',
    );
    dispatch({ filters: nextFilters, type: 'filters_changed' });
  }, []);

  const reloadWorkspace = useCallback(() => {
    const currentFilters = filtersRef.current;
    setError('');
    setGamesState('loading');
    setSymbolsState(currentFilters.gameId === null ? 'ready' : 'loading');
    setProjectionState(currentFilters.gameId === null ? 'ready' : 'loading');
    setProjectionStatus(null);
    setPageState('ready');
    filtersConfirmedRef.current = false;
    setFiltersConfirmed(false);
    pagePositionRef.current = { number: 1 };
    dispatch({ type: 'clear_page' });
    setReloadRevision((revision) => revision + 1);
  }, []);

  const requestFilterChange = useCallback(
    (nextFilters: SymbolReviewFilters) => {
      if (selectedCount > 0) {
        setPendingFilters(nextFilters);
        return;
      }
      applyFilters(nextFilters);
    },
    [applyFilters, selectedCount],
  );

  const confirmFilters = useCallback(() => {
    if (
      filters.gameId === null ||
      filters.symbolId === null ||
      interactionBusy
    ) {
      return;
    }
    pageRequestId.current += 1;
    pagePositionRef.current = { number: 1 };
    setError('');
    setSelection(createEmptySymbolReviewSelection());
    setHiddenCellIds(new Set());
    setVisibleItems([]);
    setVirtualPreviewTiles({});
    dispatch({ type: 'clear_page' });
    filtersConfirmedRef.current = true;
    setFiltersConfirmed(true);
    setPageState(projectionStatus?.status === 'ready' ? 'loading' : 'ready');
  }, [
    filters.gameId,
    filters.symbolId,
    interactionBusy,
    projectionStatus?.status,
  ]);

  const unlockFilters = useCallback(() => {
    if (interactionBusy || selectedCount > 0) return;
    pageRequestId.current += 1;
    pagePositionRef.current = { number: 1 };
    setError('');
    setSelection(createEmptySymbolReviewSelection());
    setHiddenCellIds(new Set());
    setVisibleItems([]);
    setVirtualPreviewTiles({});
    dispatch({ type: 'clear_page' });
    filtersConfirmedRef.current = false;
    setFiltersConfirmed(false);
    setPageState('ready');
  }, [interactionBusy, selectedCount]);

  useEffect(() => {
    if (toast === null) return;
    const timerId = window.setTimeout(() => setToast(null), 4_000);
    return () => window.clearTimeout(timerId);
  }, [toast]);

  useEffect(() => {
    const requestId = ++gamesRequestId.current;
    void loadSymbolReviewGames(api).then((result) => {
      if (requestId !== gamesRequestId.current) return;
      if (!result.ok) {
        setGamesState('error');
        setError(result.error);
        return;
      }
      setGames(result.games);
      setGamesState('ready');
      const currentFilters = filtersRef.current;
      const selectedGameId = result.games.some(
        (game) => game.id === currentFilters.gameId,
      )
        ? currentFilters.gameId
        : (result.games[0]?.id ?? null);
      if (selectedGameId !== currentFilters.gameId) {
        applyFilters({
          ...currentFilters,
          gameId: selectedGameId,
          symbolId: null,
        });
      }
    });
    return () => {
      gamesRequestId.current += 1;
    };
  }, [api, applyFilters, reloadRevision]);

  useEffect(() => {
    if (filters.gameId === null) return;
    const gameId = filters.gameId;
    const requestId = ++symbolsRequestId.current;
    void loadSymbolReviewSymbols(api, gameId).then((result) => {
      if (requestId !== symbolsRequestId.current) return;
      if (!result.ok) {
        setSymbolsState('error');
        setError(result.error);
        return;
      }
      setSymbols(result.symbols);
      setSymbolsState('ready');
      const currentFilters = filtersRef.current;
      if (currentFilters.gameId !== gameId) return;
      const selectedSymbolId = result.symbols.some(
        (symbol) => symbol.id === currentFilters.symbolId,
      )
        ? currentFilters.symbolId
        : (result.symbols[0]?.id ?? null);
      if (selectedSymbolId !== currentFilters.symbolId) {
        applyFilters({ ...currentFilters, symbolId: selectedSymbolId });
      }
    });
    return () => {
      symbolsRequestId.current += 1;
    };
  }, [api, applyFilters, filters.gameId, reloadRevision]);

  useEffect(() => {
    if (filters.gameId === null) return;
    const gameId = filters.gameId;
    const requestId = ++projectionRequestId.current;
    void loadSymbolReviewProjection(api, gameId).then((result) => {
      if (requestId !== projectionRequestId.current) return;
      if (!result.ok) {
        setProjectionState('error');
        setError(result.error);
        return;
      }
      if (result.status.status === 'ready' && filtersConfirmedRef.current) {
        setPageState('loading');
      }
      setProjectionStatus(result.status);
      setProjectionState('ready');
    });
    return () => {
      projectionRequestId.current += 1;
    };
  }, [api, filters.gameId, reloadRevision]);

  useEffect(() => {
    if (
      filters.gameId === null ||
      (projectionStatus?.status !== 'rebuilding' &&
        projectionStatus?.activeJobId === null)
    ) {
      return;
    }
    const gameId = filters.gameId;
    let cancelled = false;
    let inFlight = false;
    let timerId: number | null = null;
    const poll = async () => {
      if (cancelled || inFlight) return;
      inFlight = true;
      const result = await loadSymbolReviewProjection(api, gameId);
      inFlight = false;
      if (cancelled) return;
      if (!result.ok) {
        setError(result.error);
        timerId = window.setTimeout(() => void poll(), 2_000);
        return;
      }
      if (result.status.status === 'ready' && filtersConfirmedRef.current) {
        setPageState('loading');
      }
      setProjectionStatus(result.status);
      if (result.status.status === 'rebuilding') {
        timerId = window.setTimeout(() => void poll(), 2_000);
      }
    };
    timerId = window.setTimeout(() => void poll(), 2_000);
    return () => {
      cancelled = true;
      if (timerId !== null) window.clearTimeout(timerId);
    };
  }, [
    api,
    filters.gameId,
    projectionStatus?.activeJobId,
    projectionStatus?.status,
  ]);

  useEffect(() => {
    const pageFilters = asPageFilters(filters);
    if (
      !filtersConfirmed ||
      pageFilters === null ||
      projectionStatus?.status !== 'ready'
    ) {
      return;
    }
    const requestId = ++pageRequestId.current;
    const position = pagePositionRef.current;
    void loadSymbolReviewPage(api, {
      ...pageFilters,
      ...symbolReviewPageCursorOptions(position),
    }).then((result) => {
      if (requestId !== pageRequestId.current) return;
      if (!result.ok) {
        setPageState('error');
        setError(result.error);
        return;
      }
      dispatch({ page: result.page, position, type: 'page_loaded' });
      setHiddenCellIds(new Set());
      setPageState('ready');
    });
  }, [
    api,
    filters,
    filtersConfirmed,
    projectionStatus?.status,
    reloadRevision,
  ]);

  useEffect(() => {
    const pageFilters = asPageFilters(filters);
    if (
      !filtersConfirmed ||
      pageFilters === null ||
      currentPage === null ||
      currentPage.nextCursor === null
    ) {
      return;
    }
    const position: SymbolReviewPagePosition = {
      afterCursor: currentPage.nextCursor,
      number: currentPageNumber + 1,
    };
    if (findCachedSymbolReviewPage(workspace, position.number) !== null) {
      return;
    }
    let cancelled = false;
    void loadSymbolReviewPage(api, {
      ...pageFilters,
      ...symbolReviewPageCursorOptions(position),
    }).then((result) => {
      if (cancelled || !result.ok) return;
      dispatch({ page: result.page, position, type: 'page_prefetched' });
    });
    return () => {
      cancelled = true;
    };
  }, [
    api,
    currentPage,
    currentPageNumber,
    filters,
    filtersConfirmed,
    workspace,
  ]);

  useEffect(() => {
    if (filters.gameId === null) {
      return;
    }
    const requestId = ++virtualPreviewRequestId.current;
    let cancelled = false;
    void loadSymbolReviewVirtualPreviews(
      api,
      filters.gameId,
      visibleItems,
    ).then((result) => {
      if (
        cancelled ||
        !shouldApplyVirtualPreviewResult(
          requestId,
          virtualPreviewRequestId.current,
        )
      ) {
        return;
      }
      setVirtualPreviewTiles(result.ok ? result.tilesByCellReviewId : {});
    });
    return () => {
      cancelled = true;
    };
  }, [api, filters.gameId, visibleItems]);

  const movePage = useCallback(
    async (direction: -1 | 1) => {
      const pageFilters = asPageFilters(filters);
      if (
        !filtersConfirmed ||
        pagingRef.current ||
        pageFilters === null ||
        currentPage === null
      ) {
        return;
      }
      const cursor =
        direction === 1 ? currentPage.nextCursor : currentPage.previousCursor;
      if (cursor === null) return;
      const position: SymbolReviewPagePosition =
        direction === 1
          ? { afterCursor: cursor, number: currentPageNumber + 1 }
          : {
              beforeCursor: cursor,
              number: Math.max(1, currentPageNumber - 1),
            };
      const cached = findCachedSymbolReviewPage(workspace, position.number);
      if (cached !== null) {
        pagePositionRef.current = position;
        dispatch({
          page: cached.page,
          position: cached.position,
          type: 'page_loaded',
        });
        return;
      }
      pagingRef.current = true;
      setPaging(true);
      setError('');
      const result = await loadSymbolReviewPage(api, {
        ...pageFilters,
        ...symbolReviewPageCursorOptions(position),
      });
      pagingRef.current = false;
      setPaging(false);
      if (!result.ok) {
        setError(result.error);
        return;
      }
      pagePositionRef.current = position;
      dispatch({ page: result.page, position, type: 'page_loaded' });
    },
    [api, currentPage, currentPageNumber, filters, filtersConfirmed, workspace],
  );

  async function prepareProjection() {
    if (filters.gameId === null || projectionStarting) return;
    setProjectionStarting(true);
    setError('');
    const result = await startSymbolReviewProjection(api, filters.gameId);
    setProjectionStarting(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setProjectionStatus(result.value.projection);
    setProjectionState('ready');
  }

  function selectVisiblePage() {
    const change = selectVisibleSymbolReviewItems(selection, currentItems);
    setSelection(change.selection);
    if (change.rejectedCount > 0) {
      setError(
        `Można wybrać najwyżej 10 000 cropów jawnie. Pominięto: ${change.rejectedCount}.`,
      );
    }
  }

  function selectAllMatchingFilter() {
    if (
      filters.gameId === null ||
      filters.symbolId === null ||
      currentPage === null
    ) {
      return;
    }
    const confidenceRange = symbolReviewConfidenceRange(filters.confidence);
    setSelection(
      createAllMatchingFilterSymbolReviewSelection({
        catalogRevision: currentPage.catalogRevision,
        gameId: filters.gameId,
        matchedCount: currentFilteredCount,
        maxConfidence: confidenceRange.maxConfidence ?? null,
        minConfidence: confidenceRange.minConfidence ?? null,
        state: filters.state,
        symbolId: filters.symbolId,
      }),
    );
  }

  function toggleItem(item: SymbolCellReviewListItemResponse) {
    const change = toggleSymbolReviewItem(selection, item);
    setSelection(change.selection);
    if (change.rejectedCount > 0) {
      setError('Lista wykluczeń może zawierać najwyżej 10 000 cropów.');
    }
  }

  async function previewOperation(
    action: 'approve' | 'mark_grid_issue' | 'mark_unreadable' | 'reassign',
  ) {
    if (filters.gameId === null || selectedCount === 0) return;
    const gameId = filters.gameId;
    const targets =
      selection.kind === 'explicit' ? Object.values(selection.targetsById) : [];
    if (selection.kind === 'explicit' && targets.length === 1) {
      const target = targets[0]!;
      setDirectPendingCellIds(new Set([target.cellReviewId]));
      const result = await applySingleSymbolReviewDecision(
        api,
        gameId,
        action,
        target,
        action === 'reassign' ? reassignTargetSymbolId : null,
      );
      setDirectPendingCellIds(new Set());
      if (!result.ok) {
        setToast({ kind: 'error', message: result.error });
        return;
      }
      setSelection(createEmptySymbolReviewSelection());
      setHiddenCellIds((current) => new Set([...current, target.cellReviewId]));
      setToast({
        kind: 'success',
        message:
          action === 'reassign'
            ? 'Symbol został zmieniony.'
            : action === 'approve'
              ? 'Symbol został zatwierdzony.'
              : action === 'mark_grid_issue'
                ? 'Symbol został oznaczony jako problem siatki.'
                : 'Symbol został oznaczony jako nieczytelny.',
      });
      return;
    }
    const command = createSymbolReviewBulkCommand(
      action,
      selection,
      action === 'reassign' ? reassignTargetSymbolId : null,
    );
    if (command === null) {
      setError('Wybierz docelowy aktywny symbol przed zmianą przypisania.');
      return;
    }
    setOperationDialog({ command, gameId, kind: 'loading' });
    const result = await previewSymbolReviewBulkOperation(api, gameId, command);
    if (!result.ok) {
      setOperationDialog({ error: result.error, kind: 'error' });
      return;
    }
    setOperationDialog({
      command,
      gameId,
      idempotencyKey: crypto.randomUUID(),
      kind: 'ready',
      preview: result.value,
    });
  }

  const finishOperation = useCallback(
    (
      tracked: TrackedSymbolReviewOperation,
      operation: SymbolCellReviewBulkOperationResponse,
    ) => {
      const completelyApplied =
        operation.status === 'completed' &&
        operation.appliedCount === operation.targetCount &&
        operation.conflictCount === 0 &&
        operation.failedCount === 0;
      if (completelyApplied) {
        setHiddenCellIds(
          (current) => new Set([...current, ...tracked.submittedCellIds]),
        );
      }
      setActiveOperations((current) => {
        const next = { ...current };
        delete next[operation.id];
        return next;
      });
      setToast(
        completelyApplied
          ? {
              kind: 'success',
              message: `Operacja zakończona: ${operation.appliedCount} symboli.`,
            }
          : {
              kind: 'error',
              message: `Operacja zakończona częściowo: zastosowano ${operation.appliedCount}, konflikty ${operation.conflictCount}, błędy ${operation.failedCount}.`,
            },
      );
    },
    [],
  );

  async function startPreviewedOperation() {
    if (
      operationDialog === null ||
      operationDialog.kind !== 'ready' ||
      isStartingOperation
    ) {
      return;
    }
    const submittedCellIds =
      selection.kind === 'explicit'
        ? Object.keys(selection.targetsById)
        : symbolReviewSelectionCurrentItemIds(selection, currentItems);
    setIsStartingOperation(true);
    const result = await startSymbolReviewBulkOperation(
      api,
      operationDialog.gameId,
      operationDialog.command,
      operationDialog.idempotencyKey,
    );
    setIsStartingOperation(false);
    if (!result.ok) {
      setOperationDialog({ error: result.error, kind: 'error' });
      return;
    }
    const tracked: TrackedSymbolReviewOperation = {
      operation: result.value,
      submittedCellIds,
    };
    setOperationDialog(null);
    setSelection(createEmptySymbolReviewSelection());
    if (isSymbolReviewBulkOperationTerminal(result.value)) {
      finishOperation(tracked, result.value);
      return;
    }
    setActiveOperations((current) => ({
      ...current,
      [result.value.id]: tracked,
    }));
    setToast({
      kind: 'success',
      message: 'Operacja została przekazana do przetwarzania w tle.',
    });
  }

  return (
    <section aria-label="Weryfikacja symboli" className={styles.workspace}>
      <header className="pageHeader">
        <div>
          <p className="eyebrow">Lokalny workflow · cropy symboli</p>
          <h1>Weryfikacja symboli</h1>
          <p className="lead">
            Przeglądaj, zaznaczaj i masowo weryfikuj aktualne cropy wybranego
            symbolu.
          </p>
        </div>
      </header>

      {toast !== null ? (
        <div
          aria-live="polite"
          className={`${styles.toast} ${toast.kind === 'success' ? styles.toastSuccess : styles.toastError}`}
          role="status"
        >
          {toast.message}
        </div>
      ) : null}

      <div className={styles.filters}>
        <label>
          Gra
          <select
            disabled={
              gamesState !== 'ready' || interactionBusy || filtersConfirmed
            }
            onChange={(event) =>
              requestFilterChange({
                ...filters,
                gameId: event.target.value || null,
                symbolId: null,
              })
            }
            value={filters.gameId ?? ''}
          >
            {games.length === 0 ? <option value="">Brak gier</option> : null}
            {games.map((game) => (
              <option key={game.id} value={game.id}>
                {game.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Symbol
          <select
            disabled={
              filters.gameId === null ||
              symbolsState !== 'ready' ||
              interactionBusy ||
              filtersConfirmed
            }
            onChange={(event) =>
              requestFilterChange({
                ...filters,
                symbolId: event.target.value || null,
              })
            }
            value={filters.symbolId ?? ''}
          >
            {symbols.length === 0 ? (
              <option value="">Brak aktywnych symboli</option>
            ) : null}
            {symbols.map((symbol) => (
              <option key={symbol.id} value={symbol.id}>
                {symbol.name}
              </option>
            ))}
            <option value="unknown">Nierozpoznany (?)</option>
          </select>
        </label>
        <label>
          Pewność predykcji
          <select
            disabled={interactionBusy || filtersConfirmed}
            onChange={(event) =>
              requestFilterChange({
                ...filters,
                confidence: event.target
                  .value as SymbolReviewFilters['confidence'],
              })
            }
            value={filters.confidence}
          >
            <option value="all">Wszystkie</option>
            <option value="low">Niska (poniżej 50%)</option>
            <option value="medium">Średnia (50–79%)</option>
            <option value="high">Wysoka (80%+)</option>
          </select>
        </label>
        <div className={styles.filterActions}>
          <button
            className="primaryButton"
            disabled={
              interactionBusy ||
              (filtersConfirmed
                ? selectedCount > 0
                : filters.gameId === null || filters.symbolId === null)
            }
            onClick={() => {
              if (filtersConfirmed) {
                unlockFilters();
                return;
              }
              confirmFilters();
            }}
            type="button"
          >
            {filtersConfirmed ? 'Zmień wybór' : 'Zatwierdź wybór'}
          </button>
          {filtersConfirmed && selectedCount > 0 ? (
            <span>Wyczyść zaznaczenie, aby zmienić filtry.</span>
          ) : null}
        </div>
        <fieldset
          disabled={
            filters.gameId === null ||
            symbolsState !== 'ready' ||
            interactionBusy ||
            filtersConfirmed
          }
        >
          <legend>Stan</legend>
          <SymbolReviewStateOption
            checked={filters.state === 'all'}
            label="Wszystkie"
            onChange={() => requestFilterChange({ ...filters, state: 'all' })}
            value="all"
          />
          <SymbolReviewStateOption
            checked={filters.state === 'approved'}
            label="Zatwierdzone"
            onChange={() =>
              requestFilterChange({ ...filters, state: 'approved' })
            }
            value="approved"
          />
          <SymbolReviewStateOption
            checked={filters.state === 'pending'}
            label="Oczekujące"
            onChange={() =>
              requestFilterChange({ ...filters, state: 'pending' })
            }
            value="pending"
          />
        </fieldset>
      </div>

      {projectionStatus?.status === 'ready' && currentPage !== null ? (
        <SymbolReviewSelectionToolbar
          busy={interactionBusy}
          canApprove={filters.symbolId !== 'unknown'}
          canSelectVisible={currentItems.length > 0}
          hasActiveSymbols={symbols.length > 0}
          onApprove={() => void previewOperation('approve')}
          onClear={() => setSelection(createEmptySymbolReviewSelection())}
          onMarkGridIssue={() => void previewOperation('mark_grid_issue')}
          onMarkUnreadable={() => void previewOperation('mark_unreadable')}
          onReassign={() => void previewOperation('reassign')}
          onSelectAllMatchingFilter={selectAllMatchingFilter}
          onSelectVisible={selectVisiblePage}
          onTargetSymbolChange={setReassignTargetSymbolId}
          reassignTargetSymbolId={reassignTargetSymbolId}
          selectedCount={selectedCount}
          selectionKind={selection.kind}
          symbols={symbols}
        />
      ) : null}

      {trackedOperations.length > 0 ? (
        <section
          aria-label="Operacje masowe w tle"
          className={styles.operations}
        >
          {trackedOperations.map((tracked) => (
            <SymbolReviewBackgroundOperation
              api={api}
              key={tracked.operation.id}
              onFinish={finishOperation}
              tracked={tracked}
            />
          ))}
        </section>
      ) : null}

      {gamesState === 'loading' ||
      symbolsState === 'loading' ||
      projectionState === 'loading' ||
      (projectionStatus?.status === 'ready' && pageState === 'loading') ? (
        <SymbolReviewStatus
          text="Wczytywanie bounded strony cropów…"
          title="Wczytywanie"
        />
      ) : null}
      {hasLoadError ? (
        <SymbolReviewStatus
          action={reloadWorkspace}
          error
          text={error}
          title="Nie udało się pobrać danych weryfikacji"
        />
      ) : null}
      {projectionState === 'ready' &&
      projectionStatus !== null &&
      projectionStatus.status !== 'ready' ? (
        <SymbolReviewProjectionStatus
          onStart={() => void prepareProjection()}
          starting={projectionStarting}
          status={projectionStatus}
        />
      ) : null}
      {projectionStatus?.status === 'ready' && !filtersConfirmed ? (
        <SymbolReviewStatus
          text="Wybierz grę, symbol, stan i liczbę cropów, a następnie zatwierdź wybór. Lista nie została jeszcze pobrana."
          title="Ustaw parametry widoku"
        />
      ) : null}
      {projectionStatus?.status === 'ready' &&
      pageState === 'ready' &&
      currentPage !== null ? (
        <>
          <div className={styles.summary}>
            <span>
              {activeGame?.name ?? 'Gra'} · {stateLabel(filters.state)} ·{' '}
              {symbolLabel(filters.symbolId, symbols)}
            </span>
            <div className={styles.summaryActions}>
              <span>
                Strona {currentPageNumber} · zakres{' '}
                {currentPageRange === null
                  ? 'brak wyników'
                  : `${currentPageRange.start}–${currentPageRange.end}`}{' '}
                · zatwierdzone: {currentPage.counts.approvedCount} · oczekujące:{' '}
                {currentPage.counts.pendingCount}
              </span>
              <button
                className="secondaryButton"
                disabled={
                  projectionStarting || projectionStatus.activeJobId !== null
                }
                onClick={() => void prepareProjection()}
                type="button"
              >
                {projectionStarting
                  ? 'Uruchamianie…'
                  : projectionStatus.activeJobId !== null
                    ? 'Uzupełnianie oczekuje w kolejce'
                    : 'Uzupełnij brakujące symbole'}
              </button>
            </div>
          </div>
          <div className={styles.pageWorkspace}>
            {currentItems.length === 0 ? (
              <SymbolReviewEmpty />
            ) : (
              <SymbolReviewVirtualGrid
                items={currentItems}
                onVisibleItemsChange={setVisibleItems}
                pageNumber={currentPageNumber}
                renderCard={(item) => (
                  <SymbolReviewCard
                    api={api}
                    disabled={interactionBusy || pendingCellIds.has(item.id)}
                    gameId={filters.gameId!}
                    item={item}
                    key={item.id}
                    onToggle={() => toggleItem(item)}
                    pending={pendingCellIds.has(item.id)}
                    previewTile={virtualPreviewTiles[item.id]}
                    selected={isSymbolReviewItemSelected(selection, item)}
                  />
                )}
                scopeKey={`${filters.gameId ?? ''}:${filters.symbolId ?? ''}:${filters.state}:${filters.confidence}`}
              />
            )}
            <div className={styles.pagination}>
              <button
                className="secondaryButton"
                disabled={
                  interactionBusy || currentPage.previousCursor === null
                }
                onClick={() => void movePage(-1)}
                type="button"
              >
                Poprzednia strona
              </button>
              <span>
                {paging
                  ? 'Wczytywanie strony…'
                  : `Strona ${currentPageNumber} · maks. ${filters.pageSize} symboli`}
              </span>
              <button
                className="secondaryButton"
                disabled={interactionBusy || currentPage.nextCursor === null}
                onClick={() => void movePage(1)}
                type="button"
              >
                Następna strona
              </button>
            </div>
          </div>
        </>
      ) : null}

      {pendingFilters !== null ? (
        <SymbolReviewFilterChangeDialog
          onCancel={() => setPendingFilters(null)}
          onConfirm={() => {
            applyFilters(pendingFilters);
            setPendingFilters(null);
          }}
          selectedCount={selectedCount}
        />
      ) : null}
      {operationDialog !== null ? (
        <SymbolReviewOperationDialog
          dialog={operationDialog}
          isStarting={isStartingOperation}
          onCancel={() => setOperationDialog(null)}
          onConfirm={() => void startPreviewedOperation()}
        />
      ) : null}
    </section>
  );
}

function SymbolReviewStateOption({
  checked,
  label,
  onChange,
  value,
}: {
  readonly checked: boolean;
  readonly label: string;
  readonly onChange: () => void;
  readonly value: SymbolCellReviewFilterState;
}) {
  return (
    <label>
      <input
        checked={checked}
        name="symbol-review-state"
        onChange={onChange}
        type="radio"
        value={value}
      />
      {label}
    </label>
  );
}

function SymbolReviewCard({
  api,
  disabled,
  gameId,
  item,
  onToggle,
  pending,
  previewTile,
  selected,
}: {
  readonly api: SymbolReviewClient;
  readonly disabled: boolean;
  readonly gameId: string;
  readonly item: SymbolCellReviewListItemResponse;
  readonly onToggle: () => void;
  readonly pending: boolean;
  readonly previewTile: SymbolReviewVirtualPreviewTile | undefined;
  readonly selected: boolean;
}) {
  const [imageFailed, setImageFailed] = useState(false);
  const imageUrl = api.symbolCellReviewAssetUrl(
    gameId,
    item.id,
    item.cropChecksumSha256,
  );
  const isVirtualSource = item.assetMode === 'virtual_source';
  return (
    <article
      className={`${styles.card}${selected ? ` ${styles.cardSelected}` : ''}${pending ? ` ${styles.cardPending}` : ''}`}
    >
      <button
        aria-label={`${selected ? 'Odznacz' : 'Zaznacz'} crop z planszy ${item.sequenceNumber}, pozycja ${item.rowIndex + 1}/${item.columnIndex + 1}`}
        aria-pressed={selected}
        className={styles.cardToggle}
        disabled={disabled}
        onClick={onToggle}
        type="button"
      >
        {previewTile !== undefined ? (
          <span
            aria-label={`Wirtualny podgląd: ${item.assignedSymbolName ?? 'nierozpoznany'}`}
            className={styles.virtualPreview}
            role="img"
            style={{
              backgroundImage: `url(${previewTile.atlasUrl})`,
              backgroundPosition: `-${previewTile.tile.x}px -${previewTile.tile.y}px`,
            }}
          />
        ) : isVirtualSource ? (
          <span
            aria-label="Ładowanie wirtualnego podglądu cropa"
            className={styles.assetFallback}
            role="status"
          >
            …
          </span>
        ) : imageFailed ? (
          <span
            aria-label="Brak aktualnego cropa"
            className={styles.assetFallback}
            role="img"
          >
            ?
          </span>
        ) : (
          <img
            alt={`Crop ${item.assignedSymbolName ?? 'nierozpoznany'} z planszy ${item.sequenceNumber}`}
            loading="lazy"
            onError={() => setImageFailed(true)}
            src={imageUrl}
          />
        )}
        {pending ? (
          <span
            aria-label="Zapisywanie zmiany"
            className={styles.cardLoader}
            role="status"
          />
        ) : null}
        {item.qualityIssue === 'grid_issue' ? (
          <span className={styles.cardBadge}>Zła siatka</span>
        ) : item.qualityIssue === 'unreadable' ? (
          <span className={styles.cardBadge}>Nieczytelny</span>
        ) : item.cropApprovalState === 'changed_since_approval' ? (
          <span className={styles.cardBadge}>Nowy crop</span>
        ) : item.isUnknown ? (
          <span className={styles.cardBadge}>?</span>
        ) : null}
      </button>
    </article>
  );
}

function SymbolReviewSelectionToolbar({
  busy,
  canApprove,
  canSelectVisible,
  hasActiveSymbols,
  onApprove,
  onClear,
  onMarkGridIssue,
  onMarkUnreadable,
  onReassign,
  onSelectAllMatchingFilter,
  onSelectVisible,
  onTargetSymbolChange,
  reassignTargetSymbolId,
  selectedCount,
  selectionKind,
  symbols,
}: {
  readonly busy: boolean;
  readonly canApprove: boolean;
  readonly canSelectVisible: boolean;
  readonly hasActiveSymbols: boolean;
  readonly onApprove: () => void;
  readonly onClear: () => void;
  readonly onMarkGridIssue: () => void;
  readonly onMarkUnreadable: () => void;
  readonly onReassign: () => void;
  readonly onSelectAllMatchingFilter: () => void;
  readonly onSelectVisible: () => void;
  readonly onTargetSymbolChange: (symbolId: string | null) => void;
  readonly reassignTargetSymbolId: string | null;
  readonly selectedCount: number;
  readonly selectionKind: SymbolReviewSelection['kind'];
  readonly symbols: readonly SymbolResponse[];
}) {
  const actionsDisabled = busy || selectedCount === 0;
  return (
    <aside
      aria-label="Masowa weryfikacja zaznaczonych cropów"
      className={styles.toolbar}
    >
      <div className={styles.toolbarSelection}>
        <strong>Wybrane: {selectedCount}</strong>
        <button
          className="secondaryButton"
          disabled={busy || !canSelectVisible}
          onClick={onSelectVisible}
          type="button"
        >
          Zaznacz stronę
        </button>
        <button
          className="secondaryButton"
          disabled={
            busy || !canSelectVisible || selectionKind === 'all_matching_filter'
          }
          onClick={onSelectAllMatchingFilter}
          type="button"
        >
          Zaznacz wyniki filtra
        </button>
        <button
          className="secondaryButton"
          disabled={actionsDisabled}
          onClick={onClear}
          type="button"
        >
          Wyczyść zaznaczenie
        </button>
      </div>
      <div className={styles.toolbarActions}>
        <button
          className="primaryButton"
          disabled={actionsDisabled || !canApprove}
          onClick={onApprove}
          type="button"
        >
          Zatwierdź
        </button>
        <label>
          Zmień symbol
          <select
            disabled={actionsDisabled || !hasActiveSymbols}
            onChange={(event) =>
              onTargetSymbolChange(event.target.value || null)
            }
            value={reassignTargetSymbolId ?? ''}
          >
            <option value="">Wybierz symbol</option>
            {symbols.map((symbol) => (
              <option key={symbol.id} value={symbol.id}>
                {symbol.name}
              </option>
            ))}
          </select>
        </label>
        <button
          className="secondaryButton"
          disabled={actionsDisabled || reassignTargetSymbolId === null}
          onClick={onReassign}
          type="button"
        >
          Zastosuj zmianę
        </button>
        <button
          className="secondaryButton"
          disabled={actionsDisabled}
          onClick={onMarkGridIssue}
          type="button"
        >
          Zła siatka
        </button>
        <button
          className="secondaryButton"
          disabled={actionsDisabled}
          onClick={onMarkUnreadable}
          type="button"
        >
          Nieczytelny symbol
        </button>
      </div>
    </aside>
  );
}

function SymbolReviewBackgroundOperation({
  api,
  onFinish,
  tracked,
}: {
  readonly api: SymbolReviewBulkClient;
  readonly onFinish: (
    tracked: TrackedSymbolReviewOperation,
    operation: SymbolCellReviewBulkOperationResponse,
  ) => void;
  readonly tracked: TrackedSymbolReviewOperation;
}) {
  const [operation, setOperation] = useState(tracked.operation);
  const [pollingError, setPollingError] = useState<string | null>(null);

  useEffect(() => {
    if (isSymbolReviewBulkOperationTerminal(operation)) {
      onFinish(tracked, operation);
      return;
    }
    let cancelled = false;
    let inFlight = false;
    let timerId: number | null = null;
    const poll = async () => {
      if (cancelled || inFlight) return;
      inFlight = true;
      const result = await getSymbolReviewBulkOperation(
        api,
        operation.gameId,
        operation.id,
      );
      inFlight = false;
      if (cancelled) return;
      if (!result.ok) {
        setPollingError(result.error);
        timerId = window.setTimeout(() => void poll(), 2_000);
        return;
      }
      setPollingError(null);
      setOperation(result.value);
    };
    timerId = window.setTimeout(() => void poll(), 2_000);
    return () => {
      cancelled = true;
      if (timerId !== null) window.clearTimeout(timerId);
    };
  }, [api, onFinish, operation, tracked]);

  return (
    <SymbolReviewOperationProgress
      operation={operation}
      pollingError={pollingError}
    />
  );
}

function SymbolReviewOperationProgress({
  operation,
  pollingError,
}: {
  readonly operation: SymbolCellReviewBulkOperationResponse;
  readonly pollingError: string | null;
}) {
  const processing = !isSymbolReviewBulkOperationTerminal(operation);
  return (
    <section aria-live="polite" className={styles.operationProgress}>
      <div className={styles.operationHeading}>
        {processing ? (
          <span aria-hidden className={styles.operationLoader} />
        ) : null}
        <strong>Operacja masowa: {operationLabel(operation.action)}</strong>
      </div>
      <span>
        {operationStatusLabel(operation.status)} · zastosowano{' '}
        {operation.appliedCount} / {operation.targetCount} · konflikty{' '}
        {operation.conflictCount} · błędy {operation.failedCount}
      </span>
      {pollingError ? <p>{pollingError}</p> : null}
      {operation.errorMessage ? <p>{operation.errorMessage}</p> : null}
    </section>
  );
}

function SymbolReviewFilterChangeDialog({
  onCancel,
  onConfirm,
  selectedCount,
}: {
  readonly onCancel: () => void;
  readonly onConfirm: () => void;
  readonly selectedCount: number;
}) {
  return (
    <div className={styles.modalBackdrop} role="presentation">
      <section aria-modal="true" className={styles.modal} role="dialog">
        <h2>Zmienić filtr?</h2>
        <p>
          Zmiana filtra wyczyści bieżące zaznaczenie ({selectedCount} cropów).
          Żadna decyzja ani plik nie zostaną zmienione.
        </p>
        <div className={styles.modalActions}>
          <button className="secondaryButton" onClick={onCancel} type="button">
            Anuluj
          </button>
          <button className="primaryButton" onClick={onConfirm} type="button">
            Zmień filtr
          </button>
        </div>
      </section>
    </div>
  );
}

function SymbolReviewOperationDialog({
  dialog,
  isStarting,
  onCancel,
  onConfirm,
}: {
  readonly dialog: SymbolReviewOperationDialog;
  readonly isStarting: boolean;
  readonly onCancel: () => void;
  readonly onConfirm: () => void;
}) {
  const preview = dialog.kind === 'ready' ? dialog.preview : null;
  return (
    <div className={styles.modalBackdrop} role="presentation">
      <section aria-modal="true" className={styles.modal} role="dialog">
        <h2>Podgląd operacji masowej</h2>
        {dialog.kind === 'loading' ? (
          <p>Sprawdzanie aktualnych cropów…</p>
        ) : null}
        {dialog.kind === 'error' ? <p role="alert">{dialog.error}</p> : null}
        {preview !== null ? (
          <>
            <p>
              <strong>{operationLabel(preview.action)}</strong> obejmie{' '}
              {preview.targetCount} cropów z {preview.boardCount} plansz.
            </p>
            <p>
              Snapshot katalogu: {preview.catalogRevision} · tryb:{' '}
              {preview.selectionKind}
            </p>
          </>
        ) : null}
        <div className={styles.modalActions}>
          <button
            className="secondaryButton"
            disabled={isStarting}
            onClick={onCancel}
            type="button"
          >
            Anuluj
          </button>
          {preview !== null ? (
            <button
              className="primaryButton"
              disabled={isStarting}
              onClick={onConfirm}
              type="button"
            >
              {isStarting ? 'Uruchamianie…' : 'Uruchom operację'}
            </button>
          ) : null}
        </div>
      </section>
    </div>
  );
}

function SymbolReviewEmpty() {
  return (
    <div className={styles.empty}>
      <h2>Brak cropów dla wybranego filtra</h2>
      <p>Zmień symbol albo stan, aby zobaczyć inne bieżące wyniki.</p>
    </div>
  );
}

function SymbolReviewProjectionStatus({
  onStart,
  starting,
  status,
}: {
  readonly onStart: () => void;
  readonly starting: boolean;
  readonly status: SymbolCellReviewProjectionStatusResponse;
}) {
  const canStart =
    status.status === 'not_started' || status.status === 'failed';
  const title =
    status.status === 'not_started'
      ? 'Przygotuj weryfikację symboli'
      : status.status === 'failed'
        ? 'Przygotowanie wymaga uwagi'
        : 'Trwa przygotowanie weryfikacji symboli';
  return (
    <section
      aria-live="polite"
      className={styles.projectionStatus}
      role={status.status === 'failed' ? 'alert' : 'status'}
    >
      <div>
        <h2>{title}</h2>
        <p>
          Plansze: {status.processedBoardCount.toLocaleString('pl-PL')} /{' '}
          {status.expectedBoardCount.toLocaleString('pl-PL')} · komórki:{' '}
          {status.persistedCellCount.toLocaleString('pl-PL')} /{' '}
          {status.expectedCellCount.toLocaleString('pl-PL')}
        </p>
        {status.activeJobId ? <p>Job: {status.activeJobId}</p> : null}
        {status.failureMessage ? <p>{status.failureMessage}</p> : null}
        {status.sampleProblemReviewItemIds.length > 0 ? (
          <p>
            Przykładowe plansze wymagające naprawy:{' '}
            {status.sampleProblemReviewItemIds.slice(0, 5).join(', ')}
          </p>
        ) : null}
        <p>
          Tabela: {formatBytes(status.tableBytesCurrent)} · indeksy:{' '}
          {formatBytes(status.indexBytesCurrent)} · wolne miejsce bazy:{' '}
          {formatBytes(status.databaseFreeBytesCurrent)}
        </p>
      </div>
      {canStart ? (
        <button
          className="primaryButton"
          disabled={starting}
          onClick={onStart}
          type="button"
        >
          {starting
            ? 'Uruchamianie…'
            : status.status === 'failed'
              ? 'Wznów przygotowanie'
              : 'Przygotuj weryfikację symboli'}
        </button>
      ) : null}
    </section>
  );
}

function SymbolReviewStatus({
  action,
  error = false,
  text,
  title,
}: {
  readonly action?: () => void;
  readonly error?: boolean;
  readonly text: string;
  readonly title: string;
}) {
  return (
    <div
      className={
        error ? 'feedbackBanner feedbackBannerError' : 'feedbackBanner'
      }
      role={error ? 'alert' : 'status'}
    >
      <div>
        <strong>{title}</strong>
        <p>{text}</p>
      </div>
      {action ? (
        <button className="secondaryButton" onClick={action} type="button">
          Spróbuj ponownie
        </button>
      ) : null}
    </div>
  );
}

function stateLabel(state: SymbolCellReviewFilterState): string {
  if (state === 'approved') return 'zatwierdzone';
  if (state === 'pending') return 'oczekujące';
  return 'wszystkie';
}

function filteredSymbolReviewCount(
  page: SymbolCellReviewPageResponse,
  state: SymbolCellReviewFilterState,
): number {
  if (state === 'approved') return page.counts.approvedCount;
  if (state === 'pending') return page.counts.pendingCount;
  return page.counts.allCount;
}

function formatBytes(value: number | null | undefined): string {
  if (value === null || value === undefined) return 'niedostępne';
  if (value < 1024) return `${value} B`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KiB`;
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MiB`;
  return `${(value / 1024 ** 3).toFixed(1)} GiB`;
}

function operationLabel(
  action: 'approve' | 'mark_grid_issue' | 'mark_unreadable' | 'reassign',
): string {
  if (action === 'approve') return 'Zatwierdzenie';
  if (action === 'reassign') return 'Zmiana symbolu';
  if (action === 'mark_grid_issue') return 'Oznaczenie złej siatki';
  return 'Oznaczenie nieczytelnego symbolu';
}

function operationStatusLabel(
  status: SymbolCellReviewBulkOperationResponse['status'],
): string {
  if (status === 'created') return 'Oczekuje w kolejce';
  if (status === 'processing') return 'Przetwarzanie w toku';
  if (status === 'completed') return 'Zakończono';
  if (status === 'cancelled') return 'Anulowano';
  return 'Niepowodzenie';
}

function symbolLabel(
  symbolId: string | 'unknown' | null,
  symbols: readonly SymbolResponse[],
): string {
  if (symbolId === 'unknown') return 'Nierozpoznany (?)';
  return symbols.find((symbol) => symbol.id === symbolId)?.name ?? 'Symbol';
}

function asPageFilters(
  filters: SymbolReviewFilters,
): LoadSymbolReviewPageOptions | null {
  if (filters.gameId === null || filters.symbolId === null) {
    return null;
  }
  return {
    ...symbolReviewConfidenceRange(filters.confidence),
    gameId: filters.gameId,
    limit: filters.pageSize,
    state: filters.state,
    symbolId: filters.symbolId,
  };
}

function symbolReviewPageCursorOptions(
  position: SymbolReviewPagePosition,
): Pick<LoadSymbolReviewPageOptions, 'afterCursor' | 'beforeCursor'> {
  return {
    ...(position.afterCursor === undefined
      ? {}
      : { afterCursor: position.afterCursor }),
    ...(position.beforeCursor === undefined
      ? {}
      : { beforeCursor: position.beforeCursor }),
  };
}
