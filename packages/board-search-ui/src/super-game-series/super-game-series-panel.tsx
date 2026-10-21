'use client';

/* Board crops are checksum-verified API assets, not Next static media. */
/* eslint-disable @next/next/no-img-element */

import type {
  SuperGameSeriesResponse,
  SuperGameStateResponse,
  SymbolResponse,
} from '@game-predictor/admin-api-client';
import {
  type RefObject,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import { BoardSearchBoardLinesModal } from '../board-search-board-lines-modal';
import type { BoardSearchModalDetail } from '../board-search-data-source';
import type { BoardSearchRulesVersionOption } from '../board-search-rules-versions';

import type { SuperGameSeriesViewClient } from './super-game-series-client.ts';
import {
  isSuperGameSeriesShortcutBlocked,
  resolveSuperGameSeriesKeyboardCommand,
  superGameSeriesShortcutLabel,
} from './super-game-series-keyboard.ts';
import {
  DEFAULT_SERIES_FILTERS,
  type SeriesBadge,
  type SeriesFilters,
  type SeriesPositionCard,
  type SeriesViewState,
  activeSeriesCard,
  advanceRetriggerReview,
  applySeriesRefresh,
  applySuperSymbolConflict,
  applySuperSymbolFailure,
  applySuperSymbolSaved,
  beginSuperSymbolSave,
  blockSuperSymbolSave,
  cancelSuperSymbolCandidate,
  createSeriesViewState,
  goToSeriesPosition,
  isSeriesNotFound,
  isSeriesRevisionConflict,
  isSuperSymbolCandidateDirty,
  missingCardLabel,
  moveSeriesPosition,
  noUndefinedSeriesLeftMessage,
  ordinarySuperSymbols,
  pickNextUndefinedSeries,
  selectSuperSymbolCandidate,
  seriesBadges,
  seriesCardIndexOf,
  seriesNeighbourIndexes,
  seriesPositionCardLabel,
  seriesRangeLabel,
  setSeriesNotice,
  superGameSeriesErrorMessage,
  superSymbolSaveBlock,
  superSymbolSaveLabel,
  superSymbolSavedMessage,
  triggerCellIndexes,
  triggerSymbols,
  UNSAVED_SUPER_SYMBOL_NOTICE,
  undefinedSeriesWrappedMessage,
} from './super-game-series-state.ts';

/**
 * The opened super game series (TASK-0934, shared since TASK-1058): the
 * carousel of positions with the trigger cells marked, the compare-and-set
 * super symbol choice with the retrigger review (TASK-1053), the lines
 * window of a board and the jump to the next series without a super symbol.
 * The Admin mounts it under its list; the online share shows it in a modal
 * (D-564). The host keeps the list, the symbols, the rules version and the
 * polling of the generation's freshness.
 */
export interface SuperGameSeriesPanelProps {
  readonly client: SuperGameSeriesViewClient;
  readonly gameId: string;
  readonly seriesId: string;
  /** The symbol catalog of the game (ordinary symbols are the candidates). */
  readonly symbols: readonly SymbolResponse[];
  /** The list filters the "next series" search respects; none by default. */
  readonly filters?: SeriesFilters;
  /**
   * The rules version the board symbols are read with: `null` is the latest
   * published version, `undefined` means the host has not chosen one yet
   * (the boards are read once it has).
   */
  readonly rulesVersionId?: string | null;
  /** Admin-only draft preview of the lines window; `null` shows no select. */
  readonly rulesVersions?: readonly BoardSearchRulesVersionOption[] | null;
  /** A change makes the panel read the opened series again (same position). */
  readonly refreshToken?: number;
  /** The position the carousel opens at; the trigger when absent or unknown. */
  readonly initialSequenceNumber?: number | null;
  readonly formatAmount?: (baseCredits: number) => string;
  /** Opens another series (the host owns which series is open). */
  readonly onSeriesChange: (seriesId: string) => void;
  /** With it the header shows „← Lista serii”. */
  readonly onBack?: () => void;
  /** The series as read (or re-read); the Admin refreshes its list row. */
  readonly onSeriesLoaded?: (series: SuperGameSeriesResponse) => void;
  /** The series after a saved super symbol (also a cleared one). */
  readonly onSeriesSaved?: (series: SuperGameSeriesResponse) => void;
  /** The freshness that came with the last read. */
  readonly onSuperGameStateChange?: (state: SuperGameStateResponse) => void;
  /** A symbol correction was saved in the lines window. */
  readonly onBoardEdited?: () => void;
  /** A super symbol save started or ended (a host blocks closing meanwhile). */
  readonly onSavingChange?: (saving: boolean) => void;
  /**
   * After a saved (not cleared) symbol open the next series without one
   * (TASK-1053; also the share's modal, TASK-1075). `false` keeps the saved
   * series open; `N` still works by hand.
   */
  readonly advanceAfterSave?: boolean;
}

type Toast = { readonly kind: 'success' | 'error'; readonly text: string };

type DetailEntry =
  | { readonly kind: 'ready'; readonly detail: BoardSearchModalDetail }
  | { readonly kind: 'error'; readonly message: string };

const TOAST_DURATION_MS = 6000;
const CONNECTION_LOST = 'Połączenie z API zostało przerwane.';

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
  api: Pick<SuperGameSeriesViewClient, 'boardSearchBoardViewUrl'>,
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
      ? 'superGameSeriesBadgeOk'
      : badge.tone === 'warning'
        ? 'superGameSeriesBadgeWarning'
        : 'superGameSeriesBadgeNeutral';
  return `superGameSeriesBadge ${tone}`;
}

export function SeriesBadges({
  series,
  symbols,
}: {
  readonly series: Parameters<typeof seriesBadges>[0];
  readonly symbols: readonly SymbolResponse[];
}) {
  return (
    <div className="superGameSeriesBadges">
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

export function SuperGameSeriesPanel({
  advanceAfterSave = true,
  client: api,
  filters = DEFAULT_SERIES_FILTERS,
  formatAmount = (credits) => `${credits} kr.`,
  gameId,
  initialSequenceNumber = null,
  onBack,
  onBoardEdited,
  onSavingChange,
  onSeriesChange,
  onSeriesLoaded,
  onSeriesSaved,
  onSuperGameStateChange,
  refreshToken = 0,
  rulesVersionId = null,
  rulesVersions = null,
  seriesId,
  symbols,
}: SuperGameSeriesPanelProps) {
  const [view, setView] = useState<SeriesViewState | null>(null);
  const [viewError, setViewError] = useState<string | null>(null);
  const [viewToken, setViewToken] = useState(0);
  const [details, setDetails] = useState<Readonly<Record<string, DetailEntry>>>(
    {},
  );
  const [linesSequence, setLinesSequence] = useState<number | null>(null);
  // The search for the next series without a super symbol is in flight.
  const [findingNext, setFindingNext] = useState(false);
  const findingNextRef = useRef(false);
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
  // After the host unmounts the panel (a closed modal) every answer is late.
  const mounted = useRef(true);
  useEffect(
    () => () => {
      mounted.current = false;
    },
    [],
  );
  const detailRequests = useRef(new Set<string>());
  const linesTrigger = useRef<HTMLButtonElement>(null);
  const lastRefreshToken = useRef(refreshToken);
  // The host callbacks are read through a ref so that effects do not re-run
  // when a host renders a new function.
  const callbacks = useRef({
    onBoardEdited,
    onSavingChange,
    onSeriesLoaded,
    onSeriesSaved,
    onSuperGameStateChange,
  });
  useEffect(() => {
    callbacks.current = {
      onBoardEdited,
      onSavingChange,
      onSeriesLoaded,
      onSeriesSaved,
      onSuperGameStateChange,
    };
  });
  const saving = view?.saving === true;
  useEffect(() => {
    callbacks.current.onSavingChange?.(saving);
  }, [saving]);
  const rulesLoaded = rulesVersionId !== undefined;
  const rulesVersion = rulesVersionId ?? null;

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

  // Any change of the opened series (also through browser history, which
  // does not call openSeries) ends the save in flight: its response is a
  // late answer for a closed cycle.
  useEffect(() => {
    openSeriesId.current = seriesId;
    saveOperation.current = null;
  }, [seriesId]);

  // The host asks for a fresh reading of the opened series (same position).
  useEffect(() => {
    if (refreshToken === lastRefreshToken.current) return;
    lastRefreshToken.current = refreshToken;
    refreshRequested.current = true;
    setDetails({});
    setViewToken((token) => token + 1);
  }, [refreshToken]);

  // The opened series with its positions.
  useEffect(() => {
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
        callbacks.current.onSuperGameStateChange?.(data.superGameState);
        callbacks.current.onSeriesLoaded?.(data.series);
        setView((previous) => {
          if (
            refresh &&
            previous !== null &&
            previous.series.id === data.series.id
          ) {
            return applySeriesRefresh(previous, data);
          }
          const created = createSeriesViewState(data);
          const index =
            initialSequenceNumber === null
              ? null
              : seriesCardIndexOf(created, initialSequenceNumber);
          return index === null ? created : goToSeriesPosition(created, index);
        });
      })
      .catch(() => {
        if (!cancelled) setViewError(CONNECTION_LOST);
      });
    return () => {
      cancelled = true;
    };
    // The initial position applies to the first reading of a series only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, gameId, seriesId, viewToken]);

  const activeCard =
    view !== null && view.series.id === seriesId
      ? activeSeriesCard(view)
      : null;
  const detailKey =
    activeCard === null ? null : detailKeyOf(activeCard, rulesVersion);

  // Board cells (to mark the trigger symbol cells) of the active card and of
  // its neighbours, so that the next card opens with its marks.
  const detailTargets = useMemo(() => {
    if (view === null || view.series.id !== seriesId) return [];
    return [view.activeIndex, ...seriesNeighbourIndexes(view)].flatMap(
      (index) => {
        const card = view.cards[index];
        const key = card === undefined ? null : detailKeyOf(card, rulesVersion);
        return card === undefined || key === null
          ? []
          : [{ key, sequenceNumber: card.sequenceNumber }];
      },
    );
  }, [rulesVersion, seriesId, view]);

  useEffect(() => {
    if (!rulesLoaded) return;
    for (const { key, sequenceNumber } of detailTargets) {
      if (details[key] !== undefined || detailRequests.current.has(key)) {
        continue;
      }
      detailRequests.current.add(key);
      void (
        rulesVersion === null
          ? api.getBoardSearchBoardDetail(gameId, sequenceNumber)
          : api.getBoardSearchBoardDetail(gameId, sequenceNumber, {
              rulesVersionId: rulesVersion,
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
  }, [api, detailTargets, details, gameId, rulesLoaded, rulesVersion]);

  // Neighbour crops are fetched ahead (with the revision of their reading).
  useEffect(() => {
    if (view === null || view.series.id !== seriesId) return;
    for (const index of seriesNeighbourIndexes(view)) {
      const card = view.cards[index];
      const key = card === undefined ? null : detailKeyOf(card, rulesVersion);
      const entry = key === null ? undefined : details[key];
      if (card === undefined || card.board === null || entry === undefined) {
        continue;
      }
      const image = new Image();
      image.src = boardImageUrl(api, gameId, card, entry);
    }
  }, [api, details, gameId, rulesVersion, seriesId, view]);

  /** Reads the opened series again, keeping the position. */
  const refreshSeries = useCallback(() => {
    refreshRequested.current = true;
    setViewToken((token) => token + 1);
    setDetails({});
  }, []);

  function openSeries(id: string) {
    saveOperation.current = null;
    setView(null);
    setViewError(null);
    onSeriesChange(id);
  }

  function save() {
    if (view === null || view.series.id !== seriesId) return;
    // A chosen symbol is saved only after every retrigger board was shown
    // and confirmed with Enter (TASK-1053); until then Enter walks them.
    if (superSymbolSaveBlock(view, symbols) === null) {
      const review = advanceRetriggerReview(view);
      if (review !== null) {
        setView(review);
        return;
      }
    }
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
      mounted.current &&
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
        // The symbol changed on the server whatever the view shows now.
        callbacks.current.onSeriesSaved?.(updated);
        if (!isCurrent()) return;
        saveOperation.current = null;
        onOpenSeries((state) => applySuperSymbolSaved(state, updated, symbols));
        // A chosen symbol moves on to the next series without one (TASK-1053);
        // a cleared symbol, or a host without the advance, keeps the series
        // open (the saved-symbol notice is already shown).
        if (updated.superSymbolId !== null && advanceAfterSave) {
          findNextUndefinedSeries(
            updated,
            superSymbolSavedMessage(updated, symbols),
          );
        }
      })
      .catch(() => {
        if (!isCurrent()) return;
        saveOperation.current = null;
        onOpenSeries((state) =>
          applySuperSymbolFailure(state, CONNECTION_LOST),
        );
      });
  }

  /**
   * Opens the next series without a super symbol after the trigger of the
   * opened one (TASK-1053), from the beginning of the list when none is left
   * after it. An unsaved choice blocks it.
   */
  function openNextUndefinedSeries() {
    if (view === null || view.series.id !== seriesId || view.saving) return;
    if (isSuperSymbolCandidateDirty(view)) {
      setView((state) =>
        state === null
          ? state
          : setSeriesNotice(state, {
              kind: 'error',
              text: UNSAVED_SUPER_SYMBOL_NOTICE,
            }),
      );
      return;
    }
    findNextUndefinedSeries(view.series, null);
  }

  /**
   * The search behind `openNextUndefinedSeries` and the jump after a saved
   * symbol. `savedText` (the confirmation of that save) leads every message,
   * because the opened series and its notice are replaced. An answer that
   * arrives after the opened series changed is a late answer and opens
   * nothing.
   */
  function findNextUndefinedSeries(
    from: SuperGameSeriesResponse,
    savedText: string | null,
  ) {
    if (findingNextRef.current) return;
    const searchFilters = filters;
    const isCurrent = () => mounted.current && openSeriesId.current === from.id;
    const withSaved = (text: string) =>
      savedText === null ? text : `${savedText} ${text}`;
    const onOpenedSeries = (
      update: (state: SeriesViewState) => SeriesViewState,
    ) =>
      setView((state) =>
        state !== null && state.series.id === from.id ? update(state) : state,
      );
    const fail = (error: unknown) =>
      onOpenedSeries((state) =>
        setSeriesNotice(state, {
          kind: 'error',
          text: withSaved(
            superGameSeriesErrorMessage(
              error,
              'Nie udało się znaleźć następnej serii bez super symbolu.',
            ),
          ),
        }),
      );
    const find = async (afterTrigger: number | null) => {
      const result = await api.listNextUndefinedSuperGameSeries(gameId, {
        afterTrigger,
        filters: searchFilters,
      });
      return result.error !== undefined || result.data === undefined
        ? ({ failed: true, error: result.error, next: null } as const)
        : ({
            failed: false,
            error: undefined,
            next: pickNextUndefinedSeries(
              result.data.items,
              from.id,
              searchFilters,
            ),
          } as const);
    };
    findingNextRef.current = true;
    setFindingNext(true);
    void (async () => {
      try {
        const after = await find(from.triggerSequenceNumber);
        if (!isCurrent()) return;
        if (after.failed) {
          fail(after.error);
          return;
        }
        if (after.next !== null) {
          if (savedText !== null)
            showToast({ kind: 'success', text: savedText });
          openSeries(after.next.id);
          return;
        }
        const wrapped = await find(null);
        if (!isCurrent()) return;
        if (wrapped.failed) {
          fail(wrapped.error);
          return;
        }
        if (wrapped.next !== null) {
          showToast({
            kind: 'success',
            text: withSaved(
              undefinedSeriesWrappedMessage(
                from.triggerSequenceNumber,
                wrapped.next,
              ),
            ),
          });
          openSeries(wrapped.next.id);
          return;
        }
        onOpenedSeries((state) =>
          setSeriesNotice(state, {
            kind: savedText === null ? 'info' : 'success',
            text: withSaved(noUndefinedSeriesLeftMessage(searchFilters)),
          }),
        );
      } catch {
        if (isCurrent()) {
          fail(null);
        }
      } finally {
        findingNextRef.current = false;
        setFindingNext(false);
      }
    })();
  }

  // Keyboard: always reads the latest values through this ref.
  const latest = useRef<{
    readonly cancel: () => void;
    readonly linesOpen: boolean;
    readonly move: (direction: -1 | 1) => void;
    readonly nextUndefined: () => void;
    readonly ordinary: readonly SymbolResponse[];
    readonly save: () => void;
    readonly select: (symbolId: string) => void;
    readonly viewOpen: boolean;
  }>({
    cancel: () => undefined,
    linesOpen: false,
    move: () => undefined,
    nextUndefined: () => undefined,
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
      nextUndefined: openNextUndefinedSeries,
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
        case 'next_undefined_series':
          if (!event.repeat) current.nextUndefined();
          break;
        case 'select_symbol':
          current.select(command.symbolId);
          break;
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  const viewReady = view !== null && view.series.id === seriesId;

  return (
    <>
      <SeriesView
        activeCard={activeCard}
        api={api}
        detailEntry={detailKey === null ? undefined : details[detailKey]}
        findingNext={findingNext}
        gameId={gameId}
        linesTrigger={linesTrigger}
        onBack={onBack}
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
        onNextUndefined={openNextUndefinedSeries}
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

      {linesSequence !== null ? (
        <BoardSearchBoardLinesModal
          api={api}
          formatAmount={formatAmount}
          gameId={gameId}
          onClose={(edited) => {
            setLinesSequence(null);
            if (edited) {
              refreshSeries();
              callbacks.current.onBoardEdited?.();
              return;
            }
            linesTrigger.current?.focus();
          }}
          onRecalculate={() => {
            refreshSeries();
            callbacks.current.onBoardEdited?.();
          }}
          requestedRulesVersionId={rulesVersion}
          row={null}
          rulesVersionId={null}
          rulesVersions={rulesVersions}
          sequenceNumber={linesSequence}
          symbols={symbols}
        />
      ) : null}

      {toast !== null ? (
        <p
          className={`superGameSeriesToast ${
            toast.kind === 'success'
              ? 'superGameSeriesToastSuccess'
              : 'superGameSeriesToastError'
          }`}
          role="status"
        >
          {toast.text}
        </p>
      ) : null}
    </>
  );
}

function SeriesView({
  activeCard,
  api,
  detailEntry,
  findingNext,
  gameId,
  linesTrigger,
  onBack,
  onCancel,
  onClear,
  onGo,
  onMove,
  onNextUndefined,
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
  readonly api: SuperGameSeriesViewClient;
  readonly detailEntry: DetailEntry | undefined;
  readonly findingNext: boolean;
  readonly gameId: string;
  readonly linesTrigger: RefObject<HTMLButtonElement | null>;
  readonly onBack: (() => void) | undefined;
  readonly onCancel: () => void;
  readonly onClear: () => void;
  readonly onGo: (index: number) => void;
  readonly onMove: (direction: -1 | 1) => void;
  readonly onNextUndefined: () => void;
  readonly onOpenLines: (sequenceNumber: number) => void;
  readonly onSave: () => void;
  readonly onSelect: (symbolId: string | null) => void;
  readonly ordinary: readonly SymbolResponse[];
  readonly symbols: readonly SymbolResponse[];
  readonly triggerCodes: readonly string[];
  readonly view: SeriesViewState | null;
  readonly viewError: string | null;
}) {
  const back =
    onBack === undefined ? null : (
      <button className="secondaryButton" onClick={onBack} type="button">
        ← Lista serii
      </button>
    );

  if (view === null) {
    return (
      <>
        {back === null ? null : (
          <div className="superGameSeriesViewHeader">{back}</div>
        )}
        {viewError !== null ? (
          <p className="superGameSeriesError" role="alert">
            {viewError}
          </p>
        ) : (
          <p className="superGameSeriesEmpty">Wczytuję serię…</p>
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
  const confirmed = new Set(view.confirmedRetriggers);
  const candidateListed =
    view.candidateSymbolId === null ||
    ordinary.some((symbol) => symbol.id === view.candidateSymbolId);

  return (
    <>
      <div className="superGameSeriesViewHeader">
        {back}
        <h3>Seria od #{series.triggerSequenceNumber}</h3>
        <span>
          {seriesRangeLabel(series)} · {series.length} pozycji · rewizja{' '}
          {series.revision}
        </span>
        <SeriesBadges series={series} symbols={symbols} />
        <button
          className="primaryButton superGameSeriesViewHeaderNext"
          disabled={findingNext || view.saving}
          onClick={onNextUndefined}
          title="Otwiera następną serię bez super symbolu (zakres plansz i filtry kompletności oraz przebiegu jak na liście)."
          type="button"
        >
          {findingNext ? 'Szukam…' : 'Następna bez symbolu (N) →'}
        </button>
      </div>

      {viewError !== null ? (
        <p className="superGameSeriesError" role="alert">
          {viewError}
        </p>
      ) : null}
      {view.notice !== null ? (
        <p
          className={
            view.notice.kind === 'error'
              ? 'superGameSeriesError'
              : 'superGameSeriesNotice'
          }
          role={view.notice.kind === 'error' ? 'alert' : 'status'}
        >
          {view.notice.text}
        </p>
      ) : null}

      <div className="superGameSeriesViewLayout">
        <section
          aria-label="Karuzela pozycji serii"
          className="superGameSeriesCarousel"
        >
          {activeCard !== null ? (
            <>
              <header className="superGameSeriesCardHeader">
                <h4>{seriesPositionCardLabel(activeCard)}</h4>
                <span>
                  {view.activeIndex + 1} z {view.cards.length}
                </span>
                {activeCard.role === 'retrigger' ? (
                  <span className="superGameSeriesTag">Retrigger</span>
                ) : null}
                {activeCard.role === 'trigger' ? (
                  <span className="superGameSeriesTag">
                    Plansza wyzwalająca
                  </span>
                ) : null}
              </header>

              {activeCard.missing ? (
                <div
                  className="superGameSeriesMissingCard"
                  data-testid="missing-card"
                >
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
                  selectedSymbol={candidate}
                  triggerCodes={triggerCodes}
                />
              )}
            </>
          ) : null}

          <ol aria-label="Pozycje serii" className="superGameSeriesStrip">
            {view.cards.map((card, index) => {
              const classes = ['superGameSeriesChip'];
              if (index === view.activeIndex)
                classes.push('superGameSeriesChipActive');
              if (card.role === 'retrigger')
                classes.push('superGameSeriesChipRetrigger');
              if (card.missing) classes.push('superGameSeriesChipMissing');
              return (
                <li key={card.sequenceNumber}>
                  <button
                    aria-current={
                      index === view.activeIndex ? 'true' : undefined
                    }
                    aria-label={`${seriesPositionCardLabel(card)}${card.missing ? ' · brak planszy' : ''}${confirmed.has(card.sequenceNumber) ? ' · potwierdzony' : ''}`}
                    className={classes.join(' ')}
                    onClick={() => onGo(index)}
                    type="button"
                  >
                    {card.sequenceNumber}
                    {card.role === 'retrigger' ? ' R' : ''}
                    {confirmed.has(card.sequenceNumber) ? ' ✓' : ''}
                  </button>
                </li>
              );
            })}
          </ol>

          <footer className="superGameSeriesNavigation">
            <button
              className="secondaryButton"
              disabled={view.activeIndex === 0}
              onClick={() => onMove(-1)}
              type="button"
            >
              ← Poprzednia
            </button>
            <span className="superGameSeriesHint">
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

        <section
          aria-label="Super symbol serii"
          className="superGameSeriesSymbolPanel"
        >
          <h4>Super symbol</h4>
          <label className="superGameSeriesSymbolField">
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
          <p className="superGameSeriesHint">
            Na liście są tylko zwykłe symbole (bez Wild i symboli
            uruchamiających). Skróty: <kbd>1</kbd>–<kbd>9</kbd>, <kbd>0</kbd>{' '}
            wybiera symbol, <kbd>Enter</kbd> pokazuje kolejno retriggery serii
            do potwierdzenia, a po ostatnim zapisuje i otwiera następną serię
            bez symbolu, <kbd>Esc</kbd> anuluje, <kbd>N</kbd> otwiera następną
            serię bez symbolu bez zapisu.
          </p>
          {saveBlock !== null && saveBlock.reason === 'not_ordinary' ? (
            <p className="superGameSeriesError" role="alert">
              {saveBlock.message}
            </p>
          ) : null}
          <div className="superGameSeriesActions">
            <button
              className="primaryButton"
              disabled={saveBlock !== null}
              onClick={onSave}
              type="button"
            >
              {superSymbolSaveLabel(view)}
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
            <p className="superGameSeriesHint">
              Symbol zostanie wyczyszczony po zapisie, a seria zostanie otwarta.
              Zapis nie zmienia kompletności ani wiarygodności przebiegu.
            </p>
          ) : (
            <p className="superGameSeriesHint">
              Po zapisie symbolu otwiera się następna seria bez symbolu. Zapis
              nie zmienia kompletności ani wiarygodności przebiegu.
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
  selectedSymbol,
  triggerCodes,
}: {
  readonly api: SuperGameSeriesViewClient;
  readonly card: SeriesPositionCard;
  readonly entry: DetailEntry | undefined;
  readonly gameId: string;
  readonly linesTrigger: RefObject<HTMLButtonElement | null>;
  readonly onOpenLines: (sequenceNumber: number) => void;
  readonly selectedSymbol: SymbolResponse | undefined;
  readonly triggerCodes: readonly string[];
}) {
  const [imageFailed, setImageFailed] = useState(false);
  const board = card.board;
  const checksum = board?.boardChecksumSha256 ?? null;
  const detail = entry?.kind === 'ready' ? entry.detail : null;
  const marked =
    detail === null ? [] : triggerCellIndexes(detail.symbolCodes, triggerCodes);
  const selected =
    detail?.symbolCodes.flatMap((code, index) =>
      selectedSymbol !== undefined && code === selectedSymbol.code
        ? [index]
        : [],
    ) ?? [];
  const polygons = detail?.view?.cellPolygons ?? null;

  if (board === null || checksum === null) {
    return (
      <div className="superGameSeriesMissingCard">{missingCardLabel(card)}</div>
    );
  }

  return (
    <>
      {entry === undefined ? (
        <div className="superGameSeriesMissingCard">Odczytuję planszę…</div>
      ) : imageFailed ? (
        <div className="superGameSeriesMissingCard" role="alert">
          Kadr tej planszy nie jest obecnie dostępny. Układ symboli poniżej jest
          odczytany z bazy.
        </div>
      ) : (
        <div className="superGameSeriesBoardFrame">
          <img
            alt={`Plansza #${card.sequenceNumber}`}
            className="superGameSeriesBoardImage"
            onError={() => setImageFailed(true)}
            src={boardImageUrl(api, gameId, card, entry)}
          />
          {polygons !== null && (marked.length > 0 || selected.length > 0) ? (
            <svg
              aria-hidden="true"
              className="superGameSeriesBoardOverlay"
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
              {selected.map((index) => (
                <polygon
                  className="superGameSeriesSelectedOutline"
                  data-cell={index}
                  key={`selected-${index}`}
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
            className="superGameSeriesSymbolGrid"
          >
            {detail.symbolCodes.map((code, index) => (
              <li
                className={
                  [
                    marked.includes(index) ? 'superGameSeriesTriggerCell' : '',
                    selected.includes(index)
                      ? 'superGameSeriesSelectedCell'
                      : '',
                  ]
                    .filter(Boolean)
                    .join(' ') || undefined
                }
                key={index}
                title={
                  selected.includes(index)
                    ? 'Symbol serii'
                    : marked.includes(index)
                      ? 'Symbol uruchamiający'
                      : undefined
                }
              >
                {code ?? '?'}
                {selected.includes(index) ? (
                  <span aria-label="Symbol serii"> ★</span>
                ) : null}
              </li>
            ))}
          </ol>
          <p className="superGameSeriesHint">
            Symbole uruchamiające supergrę na tej planszy: {marked.length}
            {marked.length > 0 ? ' (wyróżnione)' : ''}.
          </p>
          {selectedSymbol !== undefined ? (
            <p className="superGameSeriesHint">
              Symbol serii: {selectedSymbol.name} ({selectedSymbol.code}) ·
              wystąpienia: {selected.length}. Pola z ★ mają złote tło; na
              zdjęciu oznacza je fioletowe obramowanie.
              {polygons === null
                ? ' Brak geometrii pól — oznaczenia dostępne tylko w układzie symboli.'
                : ''}
            </p>
          ) : null}
        </>
      ) : entry?.kind === 'error' ? (
        <p className="superGameSeriesHint">
          Nie oznaczono symboli uruchamiających: {entry.message}
        </p>
      ) : (
        <p className="superGameSeriesHint">Odczytuję symbole planszy…</p>
      )}

      <div className="superGameSeriesActions">
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
