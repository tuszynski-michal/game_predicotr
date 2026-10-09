'use client';

/* Board crops are checksum-verified API assets, not Next static media. */
/* eslint-disable @next/next/no-img-element */

import type {
  AdminApiClient,
  BoardSearchBoardDetailResponse,
  SuperGameStateResponse,
  SymbolResponse,
} from '@game-predictor/admin-api-client';
import { BoardSearchBoardLinesModal } from '@game-predictor/board-search-ui';
import {
  type RefObject,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';

import {
  isSuperGameSeriesShortcutBlocked,
  resolveSuperGameSeriesKeyboardCommand,
  superGameSeriesShortcutLabel,
} from './super-game-series-keyboard';
import {
  COMPLETENESS_FILTER_OPTIONS,
  DEFINED_FILTER_OPTIONS,
  RUN_VERIFICATION_FILTER_OPTIONS,
  SERIES_STATE_POLL_INTERVAL_MS,
  type CompletenessFilter,
  type DefinedFilter,
  type RunVerificationFilter,
  type SeriesBadge,
  type SeriesFilters,
  type SeriesPositionCard,
  type SeriesViewState,
  activeSeriesCard,
  applySeriesListPage,
  applySeriesListUndefinedCount,
  applySeriesRefresh,
  applySuperSymbolConflict,
  applySuperSymbolFailure,
  applySuperSymbolSaved,
  beginSuperSymbolSave,
  blockSuperSymbolSave,
  cancelSuperSymbolCandidate,
  changeSeriesFilters,
  createSeriesListState,
  createSeriesViewState,
  deriveResultMessage,
  failSeriesList,
  goToSeriesPosition,
  isSeriesNotFound,
  isSeriesRevisionConflict,
  isSuperSymbolCandidateDirty,
  missingCardLabel,
  moveSeriesPosition,
  ordinarySuperSymbols,
  pickSeriesRulesVersion,
  reloadSeriesList,
  replaceSeriesInList,
  selectSuperSymbolCandidate,
  seriesBadges,
  seriesListQuery,
  seriesNeighbourIndexes,
  seriesPositionCardLabel,
  seriesRangeLabel,
  seriesRulesVersionOptions,
  shouldPollSeriesState,
  startLoadingMoreSeries,
  superGameSeriesErrorMessage,
  superGameStateBanner,
  superSymbolSaveBlock,
  triggerCellIndexes,
  triggerSymbols,
  undefinedSeriesCount,
  undefinedSeriesCountLabel,
  undefinedSeriesCountQuery,
} from './super-game-series-state';
import styles from './super-game-series-workspace.module.css';

export type SuperGameSeriesClient = Pick<
  AdminApiClient,
  | 'applySymbolCellReviewDecision'
  | 'boardSearchBoardViewUrl'
  | 'deriveSuperGameSeries'
  | 'getBoardSearchBoardDetail'
  | 'getSuperGameSeriesState'
  | 'listRulesVersions'
  | 'listSuperGameSeries'
  | 'listSuperGameSeriesBoards'
  | 'listSymbols'
  | 'refreshBoardSearchBoardDocument'
  | 'setSuperGameSeriesSuperSymbol'
  | 'symbolImageAssetUrl'
>;

interface SuperGameSeriesWorkspaceProps {
  readonly apiBaseUrl: string;
  readonly client?: SuperGameSeriesClient;
  readonly gameId: string;
  /** The opened series (`?series=`); `null` shows the list. */
  readonly seriesId: string | null;
  readonly onSeriesChange: (seriesId: string | null) => void;
}

type Toast = { readonly kind: 'success' | 'error'; readonly text: string };

type DetailEntry =
  | { readonly kind: 'ready'; readonly detail: BoardSearchBoardDetailResponse }
  | { readonly kind: 'error'; readonly message: string };

const TOAST_DURATION_MS = 6000;

/** Key of the cached board reading of one carousel card. */
function detailKeyOf(
  card: SeriesPositionCard,
  rulesVersionId: string | null,
): string | null {
  const checksum = card.board?.boardChecksumSha256;
  return checksum
    ? `${card.sequenceNumber}:${checksum}:${rulesVersionId ?? ''}`
    : null;
}

/**
 * The crop of a card. With a reading it is bound to that reading's checksum and
 * view revision (as the lines window does), so the image and the polygons of
 * the trigger marks come from the same revision.
 */
function boardImageUrl(
  api: Pick<SuperGameSeriesClient, 'boardSearchBoardViewUrl'>,
  gameId: string,
  card: SeriesPositionCard,
  entry: DetailEntry | undefined,
): string {
  const detail = entry?.kind === 'ready' ? entry.detail : null;
  return api.boardSearchBoardViewUrl(
    gameId,
    card.sequenceNumber,
    detail?.boardChecksumSha256 ?? card.board?.boardChecksumSha256 ?? '',
    detail?.view?.revision,
  );
}

function badgeClass(badge: SeriesBadge): string {
  const tone =
    badge.tone === 'ok'
      ? styles.badgeOk
      : badge.tone === 'warning'
        ? styles.badgeWarning
        : styles.badgeNeutral;
  return `${styles.badge} ${tone}`;
}

function SeriesBadges({
  series,
  symbols,
}: {
  readonly series: Parameters<typeof seriesBadges>[0];
  readonly symbols: readonly SymbolResponse[];
}) {
  return (
    <div className={styles.badges}>
      {seriesBadges(series, symbols).map((badge) => (
        <span
          className={badgeClass(badge)}
          data-badge={badge.id}
          key={badge.id}
          title={badge.title}
        >
          {badge.label}
        </span>
      ))}
    </div>
  );
}

export function SuperGameSeriesWorkspace({
  apiBaseUrl,
  client,
  gameId,
  onSeriesChange,
  seriesId,
}: SuperGameSeriesWorkspaceProps) {
  const api = useMemo<SuperGameSeriesClient>(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );

  const [symbols, setSymbols] = useState<readonly SymbolResponse[]>([]);
  const [rules, setRules] = useState<{
    readonly loaded: boolean;
    readonly versionId: string | null;
    readonly options: ReturnType<typeof seriesRulesVersionOptions>;
  }>({ loaded: false, options: [], versionId: null });
  const [filters, setFilters] = useState<SeriesFilters>(
    () => createSeriesListState().filters,
  );
  const [list, setList] = useState(() => createSeriesListState());
  const [reloadToken, setReloadToken] = useState(0);
  const [symbolsToken, setSymbolsToken] = useState(0);
  const [symbolsError, setSymbolsError] = useState<string | null>(null);
  const [generation, setGeneration] = useState<SuperGameStateResponse | null>(
    null,
  );
  const [deriving, setDeriving] = useState(false);
  const [view, setView] = useState<SeriesViewState | null>(null);
  const [viewError, setViewError] = useState<string | null>(null);
  const [viewToken, setViewToken] = useState(0);
  const [details, setDetails] = useState<Readonly<Record<string, DetailEntry>>>(
    {},
  );
  const [linesSequence, setLinesSequence] = useState<number | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);
  const toastTimer = useRef<number | null>(null);
  const refreshRequested = useRef(false);
  // The save in flight; a response of any other operation is a late answer.
  const saveOperation = useRef<{
    readonly id: number;
    readonly seriesId: string;
  } | null>(null);
  const operationCounter = useRef(0);
  const openSeriesId = useRef(seriesId);
  const listRef = useRef(list);
  useEffect(() => {
    listRef.current = list;
  });
  const detailRequests = useRef(new Set<string>());
  const linesTrigger = useRef<HTMLButtonElement>(null);

  const ordinary = useMemo(() => ordinarySuperSymbols(symbols), [symbols]);
  const triggerCodes = useMemo(
    () => triggerSymbols(symbols).map((symbol) => symbol.code),
    [symbols],
  );

  const showToast = useCallback((next: Toast) => {
    setToast(next);
    if (toastTimer.current !== null) window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(
      () => setToast(null),
      TOAST_DURATION_MS,
    );
  }, []);

  useEffect(
    () => () => {
      if (toastTimer.current !== null) window.clearTimeout(toastTimer.current);
    },
    [],
  );

  // Symbols (ordinary list, trigger symbols); a failure is shown and retried.
  useEffect(() => {
    let cancelled = false;
    void api
      .listSymbols(gameId)
      .then((result) => {
        if (cancelled) return;
        if (result.error !== undefined || result.data === undefined) {
          setSymbolsError(
            superGameSeriesErrorMessage(
              result.error,
              'Nie udało się pobrać katalogu symboli.',
            ),
          );
          return;
        }
        setSymbolsError(null);
        setSymbols(result.data);
      })
      .catch(() => {
        if (!cancelled) {
          setSymbolsError(
            'Połączenie z lokalnym Admin API zostało przerwane podczas pobierania symboli.',
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [api, gameId, symbolsToken]);

  // The rules version used to read the cells of a board.
  useEffect(() => {
    let cancelled = false;
    void api
      .listRulesVersions(gameId)
      .then((result) => {
        if (cancelled) return;
        const versions = result.data ?? [];
        setRules({
          loaded: true,
          options: seriesRulesVersionOptions(versions),
          versionId: pickSeriesRulesVersion(versions),
        });
      })
      .catch(() => {
        if (!cancelled)
          setRules({ loaded: true, options: [], versionId: null });
      });
    return () => {
      cancelled = true;
    };
  }, [api, gameId]);

  // First page of the list for the current filters.
  useEffect(() => {
    let cancelled = false;
    const loadGeneration = listRef.current.generation;
    void api
      .listSuperGameSeries(gameId, seriesListQuery(filters, null))
      .then((result) => {
        if (cancelled) return;
        if (result.error !== undefined || result.data === undefined) {
          setList((state) =>
            failSeriesList(
              state,
              loadGeneration,
              superGameSeriesErrorMessage(
                result.error,
                'Nie udało się pobrać listy serii.',
              ),
            ),
          );
          return;
        }
        const page = result.data;
        if (listRef.current.generation !== loadGeneration) return;
        setGeneration(page.superGameState);
        setList((state) =>
          applySeriesListPage(state, {
            cursor: null,
            generation: loadGeneration,
            response: page,
          }),
        );
      })
      .catch(() => {
        if (!cancelled) {
          setList((state) =>
            failSeriesList(
              state,
              loadGeneration,
              'Połączenie z lokalnym Admin API zostało przerwane.',
            ),
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [api, filters, gameId, reloadToken]);

  // Counter of series without a super symbol, whatever the list filters.
  useEffect(() => {
    let cancelled = false;
    void api
      .listSuperGameSeries(gameId, undefinedSeriesCountQuery())
      .then((result) => {
        if (cancelled || result.data === undefined) return;
        const count = undefinedSeriesCount(result.data);
        setList((state) => applySeriesListUndefinedCount(state, count));
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [api, gameId, reloadToken]);

  // Any change of the opened series (also through browser history, which
  // does not call openSeries / closeSeries) ends the save in flight: its
  // response is a late answer for a closed cycle.
  useEffect(() => {
    openSeriesId.current = seriesId;
    saveOperation.current = null;
  }, [seriesId]);

  // The opened series with its positions.
  useEffect(() => {
    if (seriesId === null) return;
    let cancelled = false;
    const refresh = refreshRequested.current;
    refreshRequested.current = false;
    void api
      .listSuperGameSeriesBoards(gameId, seriesId)
      .then((result) => {
        if (cancelled) return;
        if (result.error !== undefined || result.data === undefined) {
          setViewError(
            superGameSeriesErrorMessage(
              result.error,
              'Nie udało się pobrać serii.',
            ),
          );
          if (isSeriesNotFound(result.error)) setView(null);
          return;
        }
        const data = result.data;
        setViewError(null);
        setGeneration(data.superGameState);
        setList((state) => replaceSeriesInList(state, data.series));
        setView((previous) =>
          refresh && previous !== null && previous.series.id === data.series.id
            ? applySeriesRefresh(previous, data)
            : createSeriesViewState(data),
        );
      })
      .catch(() => {
        if (!cancelled) {
          setViewError('Połączenie z lokalnym Admin API zostało przerwane.');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [api, gameId, seriesId, viewToken]);

  const activeCard =
    view !== null && view.series.id === seriesId
      ? activeSeriesCard(view)
      : null;
  const detailKey =
    activeCard === null ? null : detailKeyOf(activeCard, rules.versionId);

  // Board cells (to mark the trigger symbol cells) of the active card and of
  // its neighbours, so that the next card opens with its marks.
  const detailTargets = useMemo(() => {
    if (view === null || view.series.id !== seriesId) return [];
    return [view.activeIndex, ...seriesNeighbourIndexes(view)].flatMap(
      (index) => {
        const card = view.cards[index];
        const key =
          card === undefined ? null : detailKeyOf(card, rules.versionId);
        return card === undefined || key === null
          ? []
          : [{ key, sequenceNumber: card.sequenceNumber }];
      },
    );
  }, [rules.versionId, seriesId, view]);

  useEffect(() => {
    if (!rules.loaded) return;
    for (const { key, sequenceNumber } of detailTargets) {
      if (details[key] !== undefined || detailRequests.current.has(key)) {
        continue;
      }
      detailRequests.current.add(key);
      void (
        rules.versionId === null
          ? api.getBoardSearchBoardDetail(gameId, sequenceNumber)
          : api.getBoardSearchBoardDetail(gameId, sequenceNumber, {
              rulesVersionId: rules.versionId,
            })
      )
        .then((result) => {
          const entry: DetailEntry =
            result.data !== undefined && result.error === undefined
              ? { detail: result.data, kind: 'ready' }
              : {
                  kind: 'error',
                  message: superGameSeriesErrorMessage(
                    result.error,
                    'Nie udało się odczytać symboli planszy.',
                  ),
                };
          setDetails((current) => ({ ...current, [key]: entry }));
        })
        .catch(() => {
          setDetails((current) => ({
            ...current,
            [key]: {
              kind: 'error',
              message: 'Nie udało się odczytać symboli planszy.',
            },
          }));
        })
        .finally(() => detailRequests.current.delete(key));
    }
  }, [api, detailTargets, details, gameId, rules]);

  // Neighbour crops are fetched ahead (with the revision of their reading).
  useEffect(() => {
    if (view === null || view.series.id !== seriesId) return;
    for (const index of seriesNeighbourIndexes(view)) {
      const card = view.cards[index];
      const key =
        card === undefined ? null : detailKeyOf(card, rules.versionId);
      const entry = key === null ? undefined : details[key];
      if (card === undefined || card.board === null || entry === undefined) {
        continue;
      }
      const image = new Image();
      image.src = boardImageUrl(api, gameId, card, entry);
    }
  }, [api, details, gameId, rules.versionId, seriesId, view]);

  const stale = shouldPollSeriesState(generation);

  // A new load generation: pages and errors of earlier requests are dropped.
  const reloadList = useCallback(() => {
    setList((state) => reloadSeriesList(state));
    setReloadToken((token) => token + 1);
  }, []);

  const reloadAll = useCallback(() => {
    reloadList();
    refreshRequested.current = true;
    setViewToken((token) => token + 1);
    setDetails({});
  }, [reloadList]);

  // While the generation is stale, its freshness is polled; when it becomes
  // fresh the list and the opened series are read again.
  useEffect(() => {
    if (!stale) return;
    const timer = window.setInterval(() => {
      void api
        .getSuperGameSeriesState(gameId)
        .then((result) => {
          if (result.data === undefined) return;
          setGeneration(result.data);
          if (result.data.fresh) {
            reloadAll();
            showToast({
              kind: 'success',
              text: 'Serie zostały przeliczone. Lista jest odświeżona.',
            });
          }
        })
        .catch(() => undefined);
    }, SERIES_STATE_POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [api, gameId, reloadAll, showToast, stale]);

  function changeFilters(next: SeriesFilters) {
    setFilters(next);
    setList((state) => changeSeriesFilters(state, next));
  }

  function loadMore() {
    if (list.status === 'loading' || list.nextCursor === null) return;
    const cursor = list.nextCursor;
    const loadGeneration = list.generation;
    const currentFilters = list.filters;
    setList((state) => startLoadingMoreSeries(state));
    void api
      .listSuperGameSeries(gameId, seriesListQuery(currentFilters, cursor))
      .then((result) => {
        if (listRef.current.generation !== loadGeneration) return;
        if (result.error !== undefined || result.data === undefined) {
          setList((state) =>
            failSeriesList(
              state,
              loadGeneration,
              superGameSeriesErrorMessage(
                result.error,
                'Nie udało się pobrać kolejnych serii.',
              ),
            ),
          );
          return;
        }
        const page = result.data;
        setGeneration(page.superGameState);
        setList((state) =>
          applySeriesListPage(state, {
            cursor,
            generation: loadGeneration,
            response: page,
          }),
        );
      })
      .catch(() => {
        setList((state) =>
          failSeriesList(
            state,
            loadGeneration,
            'Połączenie z lokalnym Admin API zostało przerwane.',
          ),
        );
      });
  }

  function derive() {
    setDeriving(true);
    void api
      .deriveSuperGameSeries(gameId)
      .then((result) => {
        if (result.error !== undefined || result.data === undefined) {
          showToast({
            kind: 'error',
            text: superGameSeriesErrorMessage(
              result.error,
              'Nie udało się zakolejkować przeliczania serii.',
            ),
          });
          return;
        }
        setGeneration(result.data.superGameState);
        showToast({ kind: 'success', text: deriveResultMessage(result.data) });
      })
      .catch(() =>
        showToast({
          kind: 'error',
          text: 'Połączenie z lokalnym Admin API zostało przerwane.',
        }),
      )
      .finally(() => setDeriving(false));
  }

  function openSeries(id: string) {
    saveOperation.current = null;
    setView(null);
    setViewError(null);
    onSeriesChange(id);
  }

  function closeSeries() {
    saveOperation.current = null;
    setView(null);
    setViewError(null);
    setLinesSequence(null);
    onSeriesChange(null);
  }

  function save() {
    if (view === null || view.series.id !== seriesId) return;
    const begun = beginSuperSymbolSave(view, symbols);
    if (begun === null) {
      const block = superSymbolSaveBlock(view, symbols);
      if (block !== null) setView(blockSuperSymbolSave(view, block));
      return;
    }
    setView(begun.state);
    const savedSeriesId = view.series.id;
    // The response is applied only while this very operation is the current
    // one and the same series is still open (leaving the series ends it).
    operationCounter.current += 1;
    const operation = { id: operationCounter.current, seriesId: savedSeriesId };
    saveOperation.current = operation;
    // Valid only while the series open cycle it started in is still on.
    const isCurrent = () =>
      saveOperation.current === operation &&
      openSeriesId.current === savedSeriesId;
    const onOpenSeries = (
      update: (state: SeriesViewState) => SeriesViewState,
    ) =>
      setView((state) =>
        state !== null && state.series.id === savedSeriesId
          ? update(state)
          : state,
      );
    void api
      .setSuperGameSeriesSuperSymbol(gameId, savedSeriesId, begun.request)
      .then((result) => {
        if (result.error !== undefined || result.data === undefined) {
          if (!isCurrent()) return;
          saveOperation.current = null;
          if (isSeriesRevisionConflict(result.error)) {
            // Nothing was written: show the current state, never overwrite.
            onOpenSeries(applySuperSymbolConflict);
            refreshRequested.current = true;
            setViewToken((token) => token + 1);
            return;
          }
          const message = superGameSeriesErrorMessage(
            result.error,
            'Nie udało się zapisać super symbolu.',
          );
          onOpenSeries((state) => applySuperSymbolFailure(state, message));
          return;
        }
        const updated = result.data;
        // The symbol changed on the server whatever the view shows now: the
        // list is read again with its filters, which also refreshes the counter.
        reloadList();
        if (!isCurrent()) return;
        saveOperation.current = null;
        onOpenSeries((state) => applySuperSymbolSaved(state, updated, symbols));
      })
      .catch(() => {
        if (!isCurrent()) return;
        saveOperation.current = null;
        onOpenSeries((state) =>
          applySuperSymbolFailure(
            state,
            'Połączenie z lokalnym Admin API zostało przerwane.',
          ),
        );
      });
  }

  // Keyboard: always reads the latest values through this ref.
  const latest = useRef<{
    readonly cancel: () => void;
    readonly linesOpen: boolean;
    readonly move: (direction: -1 | 1) => void;
    readonly ordinary: readonly SymbolResponse[];
    readonly save: () => void;
    readonly select: (symbolId: string) => void;
    readonly viewOpen: boolean;
  }>({
    cancel: () => undefined,
    linesOpen: false,
    move: () => undefined,
    ordinary: [],
    save: () => undefined,
    select: () => undefined,
    viewOpen: false,
  });
  useEffect(() => {
    latest.current = {
      cancel: () =>
        setView((state) => state && cancelSuperSymbolCandidate(state)),
      linesOpen: linesSequence !== null,
      move: (direction) =>
        setView((state) => state && moveSeriesPosition(state, direction)),
      ordinary,
      save,
      select: (symbolId) =>
        setView(
          (state) => state && selectSuperSymbolCandidate(state, symbolId),
        ),
      viewOpen: view !== null && view.series.id === seriesId,
    };
  });
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const current = latest.current;
      if (!current.viewOpen || current.linesOpen || event.isComposing) return;
      if (isSuperGameSeriesShortcutBlocked(event.target, event.key)) return;
      const command = resolveSuperGameSeriesKeyboardCommand(
        event,
        current.ordinary,
      );
      if (command === null) return;
      event.preventDefault();
      switch (command.kind) {
        case 'save':
          if (!event.repeat) current.save();
          break;
        case 'cancel':
          current.cancel();
          break;
        case 'previous':
          current.move(-1);
          break;
        case 'next':
          current.move(1);
          break;
        case 'select_symbol':
          current.select(command.symbolId);
          break;
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  const banner = superGameStateBanner(generation);
  const seriesOpen = seriesId !== null;
  const viewReady = view !== null && view.series.id === seriesId;

  return (
    <section
      aria-label="Supergry"
      className={styles.workspace}
      data-testid="super-game-series-workspace"
    >
      <header className={styles.header}>
        <div>
          <p className="eyebrow">Supergry</p>
          <h3>Serie supergry</h3>
          <p>
            Serie są wyprowadzane z pociętych plansz. Super symbol widać tylko
            na zdjęciach (złota ramka), więc wybiera go operator.
          </p>
        </div>
        <button
          className="primaryButton"
          disabled={deriving}
          onClick={derive}
          type="button"
        >
          {deriving ? 'Kolejkuję…' : 'Przelicz serie'}
        </button>
      </header>

      {banner !== null ? (
        <p className={styles.banner} role="status">
          {banner}
        </p>
      ) : null}

      {symbolsError !== null ? (
        <div className={styles.error} role="alert">
          <p>{symbolsError}</p>
          <button
            className="secondaryButton"
            onClick={() => setSymbolsToken((token) => token + 1)}
            type="button"
          >
            Spróbuj ponownie
          </button>
        </div>
      ) : null}

      {seriesOpen ? (
        <SeriesView
          activeCard={activeCard}
          api={api}
          closeSeries={closeSeries}
          detailEntry={detailKey === null ? undefined : details[detailKey]}
          gameId={gameId}
          linesTrigger={linesTrigger}
          onCancel={() =>
            setView((state) => state && cancelSuperSymbolCandidate(state))
          }
          onClear={() =>
            setView((state) => state && selectSuperSymbolCandidate(state, null))
          }
          onGo={(index) =>
            setView((state) => state && goToSeriesPosition(state, index))
          }
          onMove={(direction) =>
            setView((state) => state && moveSeriesPosition(state, direction))
          }
          onOpenLines={setLinesSequence}
          onSave={save}
          onSelect={(symbolId) =>
            setView(
              (state) => state && selectSuperSymbolCandidate(state, symbolId),
            )
          }
          ordinary={ordinary}
          symbols={symbols}
          triggerCodes={triggerCodes}
          view={viewReady ? view : null}
          viewError={viewError}
        />
      ) : (
        <SeriesList
          list={list}
          onChangeFilters={changeFilters}
          onLoadMore={loadMore}
          onOpen={openSeries}
          onReload={() => {
            // The list refresh also retries a failed symbol catalog.
            if (symbolsError !== null) setSymbolsToken((token) => token + 1);
            reloadList();
          }}
          symbols={symbols}
        />
      )}

      {linesSequence !== null ? (
        <BoardSearchBoardLinesModal
          api={api}
          formatAmount={(credits) => `${credits} kr.`}
          gameId={gameId}
          onClose={(edited) => {
            setLinesSequence(null);
            if (edited) {
              setDetails({});
              reloadAll();
              return;
            }
            linesTrigger.current?.focus();
          }}
          onRecalculate={() => {
            setDetails({});
            reloadAll();
          }}
          requestedRulesVersionId={rules.versionId}
          row={null}
          rulesVersionId={null}
          rulesVersions={rules.options}
          sequenceNumber={linesSequence}
          symbols={symbols}
        />
      ) : null}

      {toast !== null ? (
        <p
          className={`${styles.toast} ${
            toast.kind === 'success' ? styles.toastSuccess : styles.toastError
          }`}
          role="status"
        >
          {toast.text}
        </p>
      ) : null}
    </section>
  );
}

function SeriesList({
  list,
  onChangeFilters,
  onLoadMore,
  onOpen,
  onReload,
  symbols,
}: {
  readonly list: ReturnType<typeof createSeriesListState>;
  readonly onChangeFilters: (filters: SeriesFilters) => void;
  readonly onLoadMore: () => void;
  readonly onOpen: (seriesId: string) => void;
  readonly onReload: () => void;
  readonly symbols: readonly SymbolResponse[];
}) {
  const { filters } = list;
  return (
    <>
      <div className={styles.toolbar}>
        <div className={styles.counter} data-testid="undefined-series-count">
          <strong>{undefinedSeriesCountLabel(list.undefinedCount)}</strong>
          <span>serii bez super symbolu</span>
        </div>
        <button className="secondaryButton" onClick={onReload} type="button">
          Odśwież listę
        </button>
        <div className={styles.filters}>
          <label>
            <span>Kompletność</span>
            <select
              onChange={(event) =>
                onChangeFilters({
                  ...filters,
                  completeness: event.currentTarget.value as CompletenessFilter,
                })
              }
              value={filters.completeness}
            >
              {COMPLETENESS_FILTER_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Wiarygodność przebiegu</span>
            <select
              onChange={(event) =>
                onChangeFilters({
                  ...filters,
                  runVerification: event.currentTarget
                    .value as RunVerificationFilter,
                })
              }
              value={filters.runVerification}
            >
              {RUN_VERIFICATION_FILTER_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Super symbol</span>
            <select
              onChange={(event) =>
                onChangeFilters({
                  ...filters,
                  defined: event.currentTarget.value as DefinedFilter,
                })
              }
              value={filters.defined}
            >
              {DEFINED_FILTER_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      {list.error !== null ? (
        <p className={styles.error} role="alert">
          {list.error}
        </p>
      ) : null}

      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Wyzwalacz</th>
              <th>Pozycje</th>
              <th>Długość</th>
              <th>Retriggery</th>
              <th>Oznaczenia</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {list.items.map((series) => (
              <tr key={series.id}>
                <td>#{series.triggerSequenceNumber}</td>
                <td>{seriesRangeLabel(series)}</td>
                <td>{series.length}</td>
                <td>{series.retriggerSequenceNumbers.length}</td>
                <td>
                  <SeriesBadges series={series} symbols={symbols} />
                </td>
                <td>
                  <button
                    className="secondaryButton"
                    onClick={() => onOpen(series.id)}
                    type="button"
                  >
                    Otwórz
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {list.status === 'loading' && list.items.length === 0 ? (
          <p className={styles.empty}>Wczytuję serie…</p>
        ) : null}
        {list.status !== 'loading' && list.items.length === 0 ? (
          <p className={styles.empty}>
            Brak serii dla wybranych filtrów. Użyj „Przelicz serie”, jeśli
            plansze zostały dodane lub zmienione.
          </p>
        ) : null}
      </div>

      <footer className={styles.listFooter}>
        <span>Wczytano: {list.items.length}</span>
        {list.nextCursor !== null ? (
          <button
            className="secondaryButton"
            disabled={list.status === 'loading'}
            onClick={onLoadMore}
            type="button"
          >
            {list.status === 'loading'
              ? 'Wczytuję…'
              : list.status === 'error'
                ? 'Ponów wczytanie'
                : 'Wczytaj kolejne'}
          </button>
        ) : null}
      </footer>
    </>
  );
}

function SeriesView({
  activeCard,
  api,
  closeSeries,
  detailEntry,
  gameId,
  linesTrigger,
  onCancel,
  onClear,
  onGo,
  onMove,
  onOpenLines,
  onSave,
  onSelect,
  ordinary,
  symbols,
  triggerCodes,
  view,
  viewError,
}: {
  readonly activeCard: SeriesPositionCard | null;
  readonly api: SuperGameSeriesClient;
  readonly closeSeries: () => void;
  readonly detailEntry: DetailEntry | undefined;
  readonly gameId: string;
  readonly linesTrigger: RefObject<HTMLButtonElement | null>;
  readonly onCancel: () => void;
  readonly onClear: () => void;
  readonly onGo: (index: number) => void;
  readonly onMove: (direction: -1 | 1) => void;
  readonly onOpenLines: (sequenceNumber: number) => void;
  readonly onSave: () => void;
  readonly onSelect: (symbolId: string | null) => void;
  readonly ordinary: readonly SymbolResponse[];
  readonly symbols: readonly SymbolResponse[];
  readonly triggerCodes: readonly string[];
  readonly view: SeriesViewState | null;
  readonly viewError: string | null;
}) {
  if (view === null) {
    return (
      <>
        <div className={styles.viewHeader}>
          <button
            className="secondaryButton"
            onClick={closeSeries}
            type="button"
          >
            ← Lista serii
          </button>
        </div>
        {viewError !== null ? (
          <p className={styles.error} role="alert">
            {viewError}
          </p>
        ) : (
          <p className={styles.empty}>Wczytuję serię…</p>
        )}
      </>
    );
  }

  const { series } = view;
  const dirty = isSuperSymbolCandidateDirty(view);
  const saveBlock = superSymbolSaveBlock(view, symbols);
  const candidate = symbols.find(
    (symbol) => symbol.id === view.candidateSymbolId,
  );
  const candidateListed =
    view.candidateSymbolId === null ||
    ordinary.some((symbol) => symbol.id === view.candidateSymbolId);

  return (
    <>
      <div className={styles.viewHeader}>
        <button className="secondaryButton" onClick={closeSeries} type="button">
          ← Lista serii
        </button>
        <h3>Seria od #{series.triggerSequenceNumber}</h3>
        <span>
          {seriesRangeLabel(series)} · {series.length} pozycji · rewizja{' '}
          {series.revision}
        </span>
        <SeriesBadges series={series} symbols={symbols} />
      </div>

      {viewError !== null ? (
        <p className={styles.error} role="alert">
          {viewError}
        </p>
      ) : null}
      {view.notice !== null ? (
        <p
          className={
            view.notice.kind === 'error' ? styles.error : styles.notice
          }
          role={view.notice.kind === 'error' ? 'alert' : 'status'}
        >
          {view.notice.text}
        </p>
      ) : null}

      <div className={styles.viewLayout}>
        <section
          aria-label="Karuzela pozycji serii"
          className={styles.carousel}
        >
          {activeCard !== null ? (
            <>
              <header className={styles.cardHeader}>
                <h4>{seriesPositionCardLabel(activeCard)}</h4>
                <span>
                  {view.activeIndex + 1} z {view.cards.length}
                </span>
                {activeCard.role === 'retrigger' ? (
                  <span className={styles.tag}>Retrigger</span>
                ) : null}
                {activeCard.role === 'trigger' ? (
                  <span className={styles.tag}>Plansza wyzwalająca</span>
                ) : null}
              </header>

              {activeCard.missing ? (
                <div className={styles.missingCard} data-testid="missing-card">
                  {missingCardLabel(activeCard)}
                </div>
              ) : (
                <SeriesBoardView
                  api={api}
                  card={activeCard}
                  entry={detailEntry}
                  gameId={gameId}
                  key={activeCard.sequenceNumber}
                  linesTrigger={linesTrigger}
                  onOpenLines={onOpenLines}
                  triggerCodes={triggerCodes}
                />
              )}
            </>
          ) : null}

          <ol aria-label="Pozycje serii" className={styles.strip}>
            {view.cards.map((card, index) => {
              const classes = [styles.chip];
              if (index === view.activeIndex) classes.push(styles.chipActive);
              if (card.role === 'retrigger') classes.push(styles.chipRetrigger);
              if (card.missing) classes.push(styles.chipMissing);
              return (
                <li key={card.sequenceNumber}>
                  <button
                    aria-current={
                      index === view.activeIndex ? 'true' : undefined
                    }
                    aria-label={`${seriesPositionCardLabel(card)}${card.missing ? ' · brak planszy' : ''}`}
                    className={classes.join(' ')}
                    onClick={() => onGo(index)}
                    type="button"
                  >
                    {card.sequenceNumber}
                    {card.role === 'retrigger' ? ' R' : ''}
                  </button>
                </li>
              );
            })}
          </ol>

          <footer className={styles.navigation}>
            <button
              className="secondaryButton"
              disabled={view.activeIndex === 0}
              onClick={() => onMove(-1)}
              type="button"
            >
              ← Poprzednia
            </button>
            <span className={styles.hint}>
              Użyj ← / →, aby przejść o jedną pozycję.
            </span>
            <button
              className="secondaryButton"
              disabled={view.activeIndex >= view.cards.length - 1}
              onClick={() => onMove(1)}
              type="button"
            >
              Następna →
            </button>
          </footer>
        </section>

        <section aria-label="Super symbol serii" className={styles.symbolPanel}>
          <h4>Super symbol</h4>
          <label className={styles.symbolField}>
            <span>Symbol serii</span>
            <select
              disabled={view.saving}
              onChange={(event) => {
                const value = event.currentTarget.value;
                onSelect(value === '' ? null : value);
                event.currentTarget.blur();
              }}
              value={view.candidateSymbolId ?? ''}
            >
              <option value="">— do zdefiniowania —</option>
              {ordinary.map((symbol, index) => {
                const shortcut = superGameSeriesShortcutLabel(index);
                return (
                  <option key={symbol.id} value={symbol.id}>
                    {shortcut === null ? '' : `${shortcut} · `}
                    {symbol.name} ({symbol.code})
                  </option>
                );
              })}
              {!candidateListed && candidate !== undefined ? (
                <option value={candidate.id}>
                  {candidate.name} ({candidate.code}) · nie zwykły symbol
                </option>
              ) : null}
            </select>
          </label>
          <p className={styles.hint}>
            Na liście są tylko zwykłe symbole (bez Wild i symboli
            uruchamiających). Skróty: <kbd>1</kbd>–<kbd>9</kbd>, <kbd>0</kbd>{' '}
            wybiera symbol, <kbd>Enter</kbd> zapisuje, <kbd>Esc</kbd> anuluje.
          </p>
          {saveBlock !== null && saveBlock.reason === 'not_ordinary' ? (
            <p className={styles.error} role="alert">
              {saveBlock.message}
            </p>
          ) : null}
          <div className={styles.actions}>
            <button
              className="primaryButton"
              disabled={saveBlock !== null}
              onClick={onSave}
              type="button"
            >
              {view.saving ? 'Zapisuję…' : 'Zapisz (Enter)'}
            </button>
            <button
              className="secondaryButton"
              disabled={!dirty || view.saving}
              onClick={onCancel}
              type="button"
            >
              Anuluj (Esc)
            </button>
            <button
              className="secondaryButton"
              disabled={
                view.saving ||
                (series.superSymbolId === null &&
                  view.candidateSymbolId === null)
              }
              onClick={onClear}
              type="button"
            >
              Wyczyść symbol
            </button>
          </div>
          {view.candidateSymbolId === null && series.superSymbolId !== null ? (
            <p className={styles.hint}>
              Symbol zostanie wyczyszczony po zapisie. Zapis nie zmienia
              kompletności ani wiarygodności przebiegu.
            </p>
          ) : (
            <p className={styles.hint}>
              Zapis nie zmienia kompletności ani wiarygodności przebiegu.
            </p>
          )}
        </section>
      </div>
    </>
  );
}

function SeriesBoardView({
  api,
  card,
  entry,
  gameId,
  linesTrigger,
  onOpenLines,
  triggerCodes,
}: {
  readonly api: SuperGameSeriesClient;
  readonly card: SeriesPositionCard;
  readonly entry: DetailEntry | undefined;
  readonly gameId: string;
  readonly linesTrigger: RefObject<HTMLButtonElement | null>;
  readonly onOpenLines: (sequenceNumber: number) => void;
  readonly triggerCodes: readonly string[];
}) {
  const [imageFailed, setImageFailed] = useState(false);
  const board = card.board;
  const checksum = board?.boardChecksumSha256 ?? null;
  const detail = entry?.kind === 'ready' ? entry.detail : null;
  const marked =
    detail === null ? [] : triggerCellIndexes(detail.symbolCodes, triggerCodes);
  const polygons = detail?.view?.cellPolygons ?? null;

  if (board === null || checksum === null) {
    return <div className={styles.missingCard}>{missingCardLabel(card)}</div>;
  }

  return (
    <>
      {entry === undefined ? (
        <div className={styles.missingCard}>Odczytuję planszę…</div>
      ) : imageFailed ? (
        <div className={styles.missingCard} role="alert">
          Kadr tej planszy nie jest obecnie dostępny. Układ symboli poniżej jest
          odczytany z bazy.
        </div>
      ) : (
        <div className={styles.boardFrame}>
          <img
            alt={`Plansza #${card.sequenceNumber}`}
            className={styles.boardImage}
            onError={() => setImageFailed(true)}
            src={boardImageUrl(api, gameId, card, entry)}
          />
          {polygons !== null && marked.length > 0 ? (
            <svg
              aria-hidden="true"
              className={styles.boardOverlay}
              preserveAspectRatio="none"
              viewBox="0 0 1 1"
            >
              {marked.map((index) => (
                <polygon
                  data-cell={index}
                  key={index}
                  points={(polygons[index] ?? [])
                    .map((point) => `${point.x},${point.y}`)
                    .join(' ')}
                />
              ))}
            </svg>
          ) : null}
        </div>
      )}

      {detail !== null ? (
        <>
          <ol
            aria-label={`Układ symboli planszy #${card.sequenceNumber}`}
            className={styles.symbolGrid}
          >
            {detail.symbolCodes.map((code, index) => (
              <li
                className={
                  marked.includes(index) ? styles.triggerCell : undefined
                }
                key={index}
                title={
                  marked.includes(index) ? 'Symbol uruchamiający' : undefined
                }
              >
                {code ?? '?'}
              </li>
            ))}
          </ol>
          <p className={styles.hint}>
            Symbole uruchamiające supergrę na tej planszy: {marked.length}
            {marked.length > 0 ? ' (wyróżnione)' : ''}.
          </p>
        </>
      ) : entry?.kind === 'error' ? (
        <p className={styles.hint}>
          Nie oznaczono symboli uruchamiających: {entry.message}
        </p>
      ) : (
        <p className={styles.hint}>Odczytuję symbole planszy…</p>
      )}

      <div className={styles.actions}>
        <button
          className="secondaryButton"
          onClick={() => onOpenLines(card.sequenceNumber)}
          ref={linesTrigger}
          type="button"
        >
          Pokaż planszę z liniami
        </button>
      </div>
    </>
  );
}
