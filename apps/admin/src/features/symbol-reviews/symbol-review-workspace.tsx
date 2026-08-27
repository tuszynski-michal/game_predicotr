'use client';

/* Symbol-cell assets are checksum-bound local Admin API responses. */
/* eslint-disable @next/next/no-img-element */

import type {
  GameResponse,
  SymbolCellReviewFilterState,
  SymbolCellReviewListItemResponse,
  SymbolCellReviewBulkOperationResponse,
  SymbolCellReviewBulkPreviewResponse,
  SymbolCellReviewProjectionStatusResponse,
  SymbolResponse,
} from '@game-predictor/admin-api-client';
import {
  useCallback,
  useEffect,
  useLayoutEffect,
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
  createEmptySymbolReviewSelection,
  createSymbolReviewFilterSelection,
  isSymbolReviewItemSelected,
  selectVisibleSymbolReviewItems,
  selectedSymbolReviewCount,
  toggleSymbolReviewItem,
  type SymbolReviewSelection,
} from './symbol-review-selection-state';
import {
  createSymbolReviewWorkspaceState,
  symbolReviewBufferedPages,
  symbolReviewWorkspaceReducer,
  type SymbolReviewFilters,
} from './symbol-review-state';
import styles from './symbol-review-workspace.module.css';

type LoadState = 'error' | 'loading' | 'ready';

type SymbolReviewWorkspaceClient = SymbolReviewClient & SymbolReviewBulkClient;

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
  gameId: null,
  state: 'all',
  symbolId: null,
};

interface SymbolReviewWorkspaceProps {
  readonly apiBaseUrl: string;
  readonly client?: SymbolReviewWorkspaceClient;
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
  const [selection, setSelection] = useState<SymbolReviewSelection>(
    createEmptySymbolReviewSelection,
  );
  const [pendingFilters, setPendingFilters] =
    useState<SymbolReviewFilters | null>(null);
  const [operationDialog, setOperationDialog] =
    useState<SymbolReviewOperationDialog | null>(null);
  const [activeOperation, setActiveOperation] =
    useState<SymbolCellReviewBulkOperationResponse | null>(null);
  const [isStartingOperation, setIsStartingOperation] = useState(false);
  const [reassignTargetSymbolId, setReassignTargetSymbolId] = useState<
    string | null
  >(null);
  const gamesRequestId = useRef(0);
  const symbolsRequestId = useRef(0);
  const pageRequestId = useRef(0);
  const projectionRequestId = useRef(0);
  const filtersRef = useRef<SymbolReviewFilters>(INITIAL_FILTERS);
  const pagingRef = useRef(false);
  const scrollViewportRef = useRef<HTMLDivElement | null>(null);
  const topSentinelRef = useRef<HTMLDivElement | null>(null);
  const bottomSentinelRef = useRef<HTMLDivElement | null>(null);
  const pageElementsRef = useRef(new Map<string, HTMLElement>());
  const scrollAnchorRef = useRef<{
    readonly key: string;
    readonly top: number;
  } | null>(null);
  const lastScrollTopRef = useRef(0);
  const scrollDirectionRef = useRef<-1 | 1>(1);

  const filters = workspace.filters;
  const currentPage = workspace.pages.current;
  const bufferedPages = symbolReviewBufferedPages(workspace);
  const currentItems = bufferedPages.flatMap((page) => page.items);
  const activeGame = games.find((game) => game.id === filters.gameId) ?? null;
  const activeOperationId = activeOperation?.id ?? null;
  const activeOperationGameId = activeOperation?.gameId ?? null;
  const activeOperationIsTerminal =
    activeOperation === null ||
    isSymbolReviewBulkOperationTerminal(activeOperation);
  const selectedCount =
    currentPage === null
      ? 0
      : selectedSymbolReviewCount(selection, currentPage.counts);
  const hasLoadError =
    gamesState === 'error' ||
    symbolsState === 'error' ||
    projectionState === 'error' ||
    pageState === 'error';

  const applyFilters = useCallback((nextFilters: SymbolReviewFilters) => {
    const previousFilters = filtersRef.current;
    filtersRef.current = nextFilters;
    pageRequestId.current += 1;
    setError('');
    setSelection(createEmptySymbolReviewSelection());
    setReassignTargetSymbolId(null);
    if (previousFilters.gameId !== nextFilters.gameId) {
      setSymbols([]);
      setSymbolsState(nextFilters.gameId === null ? 'ready' : 'loading');
      setProjectionStatus(null);
      setProjectionState(nextFilters.gameId === null ? 'ready' : 'loading');
    }
    setPageState(asPageFilters(nextFilters) === null ? 'ready' : 'loading');
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
    dispatch({ type: 'clear_pages' });
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
      if (result.status.status === 'ready') setPageState('loading');
      setProjectionStatus(result.status);
      setProjectionState('ready');
    });
    return () => {
      projectionRequestId.current += 1;
    };
  }, [api, filters.gameId, reloadRevision]);

  useEffect(() => {
    if (filters.gameId === null || projectionStatus?.status !== 'rebuilding') {
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
      if (result.status.status === 'ready') setPageState('loading');
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
  }, [api, filters.gameId, projectionStatus?.status]);

  useEffect(() => {
    const pageFilters = asPageFilters(filters);
    if (pageFilters === null || projectionStatus?.status !== 'ready') return;
    const requestId = ++pageRequestId.current;
    void loadSymbolReviewPage(api, pageFilters).then((result) => {
      if (requestId !== pageRequestId.current) return;
      if (!result.ok) {
        setPageState('error');
        setError(result.error);
        return;
      }
      dispatch({ page: result.page, type: 'initial_page_loaded' });
      setPageState('ready');
    });
  }, [api, filters, projectionStatus?.status, reloadRevision]);

  const movePage = useCallback(
    async (direction: -1 | 1) => {
      const pageFilters = asPageFilters(filters);
      if (pagingRef.current || pageFilters === null || currentPage === null) {
        return;
      }
      const cached =
        direction === 1 ? workspace.pages.next : workspace.pages.previous;
      const anchorKey = symbolReviewPageKey(currentPage);
      const anchorElement = pageElementsRef.current.get(anchorKey);
      scrollAnchorRef.current =
        anchorElement === undefined
          ? null
          : { key: anchorKey, top: anchorElement.offsetTop };
      if (cached !== null) {
        dispatch({
          page: cached,
          type: direction === 1 ? 'next_page_loaded' : 'previous_page_loaded',
        });
        return;
      }
      const cursor =
        direction === 1 ? currentPage.nextCursor : currentPage.previousCursor;
      if (cursor === null) {
        scrollAnchorRef.current = null;
        return;
      }
      pagingRef.current = true;
      setPaging(true);
      setError('');
      const result = await loadSymbolReviewPage(api, {
        ...pageFilters,
        ...(direction === 1
          ? { afterCursor: cursor }
          : { beforeCursor: cursor }),
      });
      pagingRef.current = false;
      setPaging(false);
      if (!result.ok) {
        setError(result.error);
        scrollAnchorRef.current = null;
        return;
      }
      dispatch({
        page: result.page,
        type: direction === 1 ? 'next_page_loaded' : 'previous_page_loaded',
      });
    },
    [api, currentPage, filters, workspace.pages.next, workspace.pages.previous],
  );

  useLayoutEffect(() => {
    const anchor = scrollAnchorRef.current;
    const viewport = scrollViewportRef.current;
    if (anchor === null || viewport === null) return;
    const element = pageElementsRef.current.get(anchor.key);
    scrollAnchorRef.current = null;
    if (element !== undefined) {
      viewport.scrollTop += element.offsetTop - anchor.top;
      lastScrollTopRef.current = viewport.scrollTop;
    }
  }, [bufferedPages]);

  useEffect(() => {
    const viewport = scrollViewportRef.current;
    const topSentinel = topSentinelRef.current;
    const bottomSentinel = bottomSentinelRef.current;
    if (viewport === null || topSentinel === null || bottomSentinel === null) {
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          if (
            entry.target === bottomSentinel &&
            scrollDirectionRef.current === 1
          ) {
            void movePage(1);
          }
          if (
            entry.target === topSentinel &&
            scrollDirectionRef.current === -1
          ) {
            void movePage(-1);
          }
        }
      },
      { root: viewport, rootMargin: '180px 0px' },
    );
    observer.observe(topSentinel);
    observer.observe(bottomSentinel);
    return () => observer.disconnect();
  }, [movePage]);

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

  function selectAllFilteredResults() {
    if (currentPage === null) return;
    const next = createSymbolReviewFilterSelection(filters, currentPage);
    if (next !== null) setSelection(next);
  }

  function toggleItem(item: SymbolCellReviewListItemResponse) {
    const change = toggleSymbolReviewItem(selection, item);
    setSelection(change.selection);
    if (change.rejectedCount > 0) {
      setError('Lista wykluczeń może zawierać najwyżej 10 000 cropów.');
    }
  }

  async function previewOperation(
    action: 'approve' | 'mark_grid_issue' | 'reassign',
  ) {
    if (filters.gameId === null || selectedCount === 0) return;
    const gameId = filters.gameId;
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

  async function startPreviewedOperation() {
    if (
      operationDialog === null ||
      operationDialog.kind !== 'ready' ||
      isStartingOperation
    ) {
      return;
    }
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
    setActiveOperation(result.value);
    setOperationDialog(null);
  }

  useEffect(() => {
    if (
      activeOperationId === null ||
      activeOperationGameId === null ||
      activeOperationIsTerminal
    ) {
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
        activeOperationGameId,
        activeOperationId,
      );
      inFlight = false;
      if (cancelled) return;
      if (!result.ok) {
        setError(result.error);
        timerId = window.setTimeout(() => void poll(), 2_000);
        return;
      }
      setActiveOperation(result.value);
      if (isSymbolReviewBulkOperationTerminal(result.value)) {
        setSelection(createEmptySymbolReviewSelection());
        reloadWorkspace();
        return;
      }
      timerId = window.setTimeout(() => void poll(), 2_000);
    };
    void poll();
    return () => {
      cancelled = true;
      if (timerId !== null) window.clearTimeout(timerId);
    };
  }, [
    activeOperationGameId,
    activeOperationId,
    activeOperationIsTerminal,
    api,
    reloadWorkspace,
  ]);

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

      <div className={styles.filters}>
        <label>
          Gra
          <select
            disabled={gamesState !== 'ready'}
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
            disabled={filters.gameId === null || symbolsState !== 'ready'}
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
        <fieldset
          disabled={filters.gameId === null || symbolsState !== 'ready'}
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
          canApprove={filters.symbolId !== 'unknown'}
          canSelectVisible={currentItems.length > 0}
          hasActiveSymbols={symbols.length > 0}
          onApprove={() => void previewOperation('approve')}
          onClear={() => setSelection(createEmptySymbolReviewSelection())}
          onMarkGridIssue={() => void previewOperation('mark_grid_issue')}
          onReassign={() => void previewOperation('reassign')}
          onSelectAll={selectAllFilteredResults}
          onSelectVisible={selectVisiblePage}
          onTargetSymbolChange={setReassignTargetSymbolId}
          reassignTargetSymbolId={reassignTargetSymbolId}
          selectedCount={selectedCount}
          symbols={symbols}
        />
      ) : null}

      {activeOperation !== null ? (
        <SymbolReviewOperationProgress operation={activeOperation} />
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
                Wyniki: {currentPage.counts.allCount} · zatwierdzone:{' '}
                {currentPage.counts.approvedCount} · oczekujące:{' '}
                {currentPage.counts.pendingCount}
              </span>
              <button
                className="secondaryButton"
                disabled={projectionStarting}
                onClick={() => void prepareProjection()}
                type="button"
              >
                {projectionStarting
                  ? 'Uruchamianie…'
                  : 'Uzupełnij brakujące symbole'}
              </button>
            </div>
          </div>
          {currentItems.length === 0 ? (
            <SymbolReviewEmpty />
          ) : (
            <div
              className={styles.scrollViewport}
              onScroll={(event) => {
                const nextTop = event.currentTarget.scrollTop;
                if (nextTop !== lastScrollTopRef.current) {
                  scrollDirectionRef.current =
                    nextTop > lastScrollTopRef.current ? 1 : -1;
                  lastScrollTopRef.current = nextTop;
                }
              }}
              ref={scrollViewportRef}
            >
              <div
                aria-hidden="true"
                className={styles.sentinel}
                ref={topSentinelRef}
              />
              {bufferedPages.map((page) => {
                const key = symbolReviewPageKey(page);
                return (
                  <section
                    className={styles.bufferedPage}
                    data-page-key={key}
                    key={key}
                    ref={(element) => {
                      if (element === null) pageElementsRef.current.delete(key);
                      else pageElementsRef.current.set(key, element);
                    }}
                  >
                    <div className={styles.grid}>
                      {page.items.map((item) => (
                        <SymbolReviewCard
                          api={api}
                          gameId={filters.gameId!}
                          item={item}
                          key={item.id}
                          onToggle={() => toggleItem(item)}
                          selected={isSymbolReviewItemSelected(selection, item)}
                        />
                      ))}
                    </div>
                  </section>
                );
              })}
              <div
                aria-hidden="true"
                className={styles.sentinel}
                ref={bottomSentinelRef}
              />
              <div className={styles.streamStatus}>
                {paging
                  ? 'Wczytywanie kolejnych cropów…'
                  : `W pamięci: ${currentItems.length} / maks. 180 cropów`}
              </div>
            </div>
          )}
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
  gameId,
  item,
  onToggle,
  selected,
}: {
  readonly api: SymbolReviewClient;
  readonly gameId: string;
  readonly item: SymbolCellReviewListItemResponse;
  readonly onToggle: () => void;
  readonly selected: boolean;
}) {
  const [imageFailed, setImageFailed] = useState(false);
  const imageUrl = api.symbolCellReviewAssetUrl(
    gameId,
    item.id,
    item.cropChecksumSha256,
  );
  return (
    <article
      className={
        selected ? `${styles.card} ${styles.cardSelected}` : styles.card
      }
    >
      <button
        aria-label={`${selected ? 'Odznacz' : 'Zaznacz'} crop z planszy ${item.sequenceNumber}, pozycja ${item.rowIndex + 1}/${item.columnIndex + 1}`}
        aria-pressed={selected}
        className={styles.cardToggle}
        onClick={onToggle}
        type="button"
      >
        {imageFailed ? (
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
      </button>
      <div className={styles.cardBody}>
        <strong>{item.assignedSymbolName ?? 'Nierozpoznany (?)'}</strong>
        <span>
          Plansza #{item.sequenceNumber} · R{item.rowIndex + 1}/K
          {item.columnIndex + 1}
        </span>
        <span>
          {item.reviewState === 'approved' ? 'Zatwierdzony' : 'Oczekuje'}
        </span>
        {item.hasGridIssue ? <em>Zła siatka</em> : null}
      </div>
    </article>
  );
}

function SymbolReviewSelectionToolbar({
  canApprove,
  canSelectVisible,
  hasActiveSymbols,
  onApprove,
  onClear,
  onMarkGridIssue,
  onReassign,
  onSelectAll,
  onSelectVisible,
  onTargetSymbolChange,
  reassignTargetSymbolId,
  selectedCount,
  symbols,
}: {
  readonly canApprove: boolean;
  readonly canSelectVisible: boolean;
  readonly hasActiveSymbols: boolean;
  readonly onApprove: () => void;
  readonly onClear: () => void;
  readonly onMarkGridIssue: () => void;
  readonly onReassign: () => void;
  readonly onSelectAll: () => void;
  readonly onSelectVisible: () => void;
  readonly onTargetSymbolChange: (symbolId: string | null) => void;
  readonly reassignTargetSymbolId: string | null;
  readonly selectedCount: number;
  readonly symbols: readonly SymbolResponse[];
}) {
  const actionsDisabled = selectedCount === 0;
  return (
    <aside
      aria-label="Masowa weryfikacja zaznaczonych cropów"
      className={styles.toolbar}
    >
      <div className={styles.toolbarSelection}>
        <strong>Wybrane: {selectedCount}</strong>
        <button
          className="secondaryButton"
          disabled={!canSelectVisible}
          onClick={onSelectVisible}
          type="button"
        >
          Zaznacz widoczną stronę
        </button>
        <button
          className="secondaryButton"
          disabled={!canSelectVisible}
          onClick={onSelectAll}
          type="button"
        >
          Zaznacz wszystkie wyniki filtra
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
          Oznacz złą siatkę
        </button>
      </div>
    </aside>
  );
}

function SymbolReviewOperationProgress({
  operation,
}: {
  readonly operation: SymbolCellReviewBulkOperationResponse;
}) {
  return (
    <section aria-live="polite" className={styles.operationProgress}>
      <strong>Operacja masowa: {operationLabel(operation.action)}</strong>
      <span>
        {operation.status} · zastosowano {operation.appliedCount} /{' '}
        {operation.targetCount} · konflikty {operation.conflictCount} · błędy{' '}
        {operation.failedCount}
      </span>
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

function symbolReviewPageKey(page: {
  readonly items: readonly { readonly id: string }[];
}): string {
  const first = page.items[0]?.id ?? 'empty';
  const last = page.items.at(-1)?.id ?? 'empty';
  return `${first}:${last}`;
}

function formatBytes(value: number | null | undefined): string {
  if (value === null || value === undefined) return 'niedostępne';
  if (value < 1024) return `${value} B`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KiB`;
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MiB`;
  return `${(value / 1024 ** 3).toFixed(1)} GiB`;
}

function operationLabel(
  action: 'approve' | 'mark_grid_issue' | 'reassign',
): string {
  if (action === 'approve') return 'Zatwierdzenie';
  if (action === 'reassign') return 'Zmiana symbolu';
  return 'Oznaczenie złej siatki';
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
    gameId: filters.gameId,
    state: filters.state,
    symbolId: filters.symbolId,
  };
}
