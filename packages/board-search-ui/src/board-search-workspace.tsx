'use client';

/* Local symbol assets are protected Admin API responses, not Next static media. */
/* eslint-disable @next/next/no-img-element */

import type {
  BoardSearchResponse,
  BoardSearchScope,
  SymbolResponse,
  SearchGameBoardsOptions,
} from '@game-predictor/admin-api-client';
import { type ReactNode, useEffect, useMemo, useRef, useState } from 'react';

import { apiErrorMessage } from './api-error';
import type { BoardSearchDataSource } from './board-search-data-source';
import {
  digitShortcutLabel,
  isTextEntryKeyboardTarget,
} from './keyboard-shortcuts';

import {
  BOARD_SEARCH_COLUMNS,
  BOARD_SEARCH_ROWS,
  BOARD_SEARCH_UNKNOWN,
  type BoardSearchEntryOrder,
  boardSearchEditorFromPattern,
  boardSearchPatternCellCount,
  createBoardSearchEditorState,
  placeBoardSearchUnknown,
  placeBoardSearchSymbol,
  resetBoardSearchEditor,
  selectBoardSearchCell,
  selectBoardSearchEntryStart,
  patternBoardSearchCells,
  selectedBoardSearchCells,
  undoBoardSearchEdit,
} from './board-search-editor-state';
import { BoardSearchApproximateWin } from './board-search-approximate-win';
import { BoardSearchBoardLinesModal } from './board-search-board-lines-modal';
import { useBoardSearchRulesVersions } from './board-search-rules-version-select';
import { APPROXIMATE_WIN_RANGE_DEFAULT } from './board-search-approximate-win-state';
import {
  boardSearchDraftKey,
  type BoardSearchDraft,
  type BoardSearchSavedSelection,
} from './board-search-saved-selection';
import { BoardSearchSavedBoard } from './board-search-saved-board';
import { formatApproximateWinAmount } from './board-search-stake';
import {
  BOARD_SEARCH_UNKNOWN_SHORTCUT,
  resolveBoardSearchKeyboardCommand,
} from './board-search-keyboard';
import { BoardSearchResults } from './board-search-results';
import {
  BOARD_SEARCH_LIMIT_DEFAULT,
  activeBoardSearchResult,
  createBoardSearchResultsState,
  parseBoardSearchLimit,
  reconcileBoardSearchResultsState,
  selectBoardSearchResultBySequence,
  type BoardSearchResultsState,
} from './board-search-results-state';

type LoadState = 'loading' | 'ready' | 'error';

/** A host cancelled its save confirmation without attempting a mutation. */
export class BoardSearchSaveCancelled extends Error {}
type SearchState =
  | { readonly kind: 'idle' }
  | { readonly kind: 'loading' }
  | { readonly kind: 'ready'; readonly result: BoardSearchResponse }
  | { readonly kind: 'error'; readonly message: string };

/**
 * A recorded query to reproduce (D-472): the pattern, scope and limit to
 * search with, then optionally the range to open from its start board and
 * the board whose payline modal to show. A new `id` replays again.
 */
export type BoardSearchReplayRequest = {
  readonly id: string;
  readonly cells: readonly {
    readonly cellIndex: number;
    readonly symbolCode: string | null;
  }[];
  readonly scope: BoardSearchScope;
  readonly limit: number;
  readonly approximateWin: {
    readonly startSequenceNumber: number;
    readonly spinCount: number;
  } | null;
  readonly boardSequenceNumber: number | null;
};

export type BoardSearchApproximateWinReplay = {
  readonly id: string;
  readonly spinCount: number;
  readonly boardSequenceNumber: number | null;
};

export interface BoardSearchWorkspaceProps {
  /** Must keep its identity between renders (the Admin memoises it). */
  readonly client: BoardSearchDataSource;
  readonly gameId: string;
  /** Host-specific controls in the section header (Admin: share panel). */
  readonly headerActions?: ReactNode;
  /** Admin replay of a share link's query (D-472). */
  readonly replay?: BoardSearchReplayRequest | null;
  /**
   * Called once the replay was taken over, so the host drops it and a later
   * remount of the section does not replay again.
   */
  readonly onReplayApplied?: (id: string) => void;
  /** Stable machine/game/stake identity; change only for intentional navigation. */
  readonly scopeKey?: string;
  readonly fixedStakeGrosze?: number;
  /** Initial selection; background updates never replace the mounted draft. */
  readonly savedSelection?: BoardSearchSavedSelection | null;
  readonly onDraftChange?: (draft: BoardSearchDraft) => void;
  readonly onDirtyChange?: (dirty: boolean) => void;
  /** Resolve only after a successful durable receipt; throw on failure. */
  readonly onSave?: (draft: BoardSearchDraft) => Promise<void>;
  /** Management presentation only; ordinary search/share retain their controls. */
  readonly compact?: boolean;
  readonly saveLabel?: string;
}

export function BoardSearchWorkspace(props: BoardSearchWorkspaceProps) {
  return (
    <BoardSearchWorkspaceContent
      key={`${props.gameId}:${props.scopeKey ?? props.savedSelection?.id ?? ''}`}
      {...props}
    />
  );
}

function BoardSearchWorkspaceContent({
  client: api,
  gameId,
  headerActions,
  onReplayApplied,
  replay = null,
  fixedStakeGrosze,
  savedSelection = null,
  onDraftChange,
  onDirtyChange,
  onSave,
  compact = false,
  saveLabel = 'Zapisz układ',
}: BoardSearchWorkspaceProps) {
  const managed =
    onSave !== undefined ||
    savedSelection !== null ||
    fixedStakeGrosze !== undefined;
  const [query, setQuery] = useState<SearchGameBoardsOptions>(
    savedSelection?.query ?? {
      cells: [],
      limit: BOARD_SEARCH_LIMIT_DEFAULT,
      scope: 'all_searchable',
    },
  );
  const [searchContextId, setSearchContextId] = useState<string | null>(
    savedSelection?.searchContextId ?? null,
  );
  const [savedSequence, setSavedSequence] = useState<number | null>(
    savedSelection?.startSequenceNumber ?? null,
  );
  const [spinCount, setSpinCount] = useState(
    savedSelection?.spinCount ?? APPROXIMATE_WIN_RANGE_DEFAULT,
  );
  const [pins, setPins] = useState<readonly number[]>(
    savedSelection?.pinnedSpinPositions ?? [],
  );
  const [savedBoardOpen, setSavedBoardOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const saveInFlight = useRef(false);
  const mounted = useRef(true);
  const hostCallbacks = useRef({ onDraftChange, onDirtyChange });
  useEffect(() => {
    hostCallbacks.current = { onDraftChange, onDirtyChange };
  });
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveNotice, setSaveNotice] = useState<string | null>(null);
  const [baseline, setBaseline] = useState<string | null>(
    savedSelection === null ? null : boardSearchDraftKey(savedSelection),
  );
  const [symbols, setSymbols] = useState<readonly SymbolResponse[]>([]);
  // Admin-only draft preview (D-535); `null` for share and management sources.
  const rulesVersions = useBoardSearchRulesVersions(api, gameId);
  const [symbolsState, setSymbolsState] = useState<LoadState>('loading');
  const [symbolsError, setSymbolsError] = useState('');
  const [editor, setEditor] = useState(() =>
    savedSelection === null
      ? createBoardSearchEditorState()
      : boardSearchEditorFromPattern(
          savedSelection.query.cells,
          new Set(
            savedSelection.query.cells.flatMap((cell) =>
              cell.symbolCode === null ? [] : [cell.symbolCode],
            ),
          ),
        ).state,
  );
  const [entryOrder, setEntryOrder] =
    useState<BoardSearchEntryOrder>('columns');
  const [searchState, setSearchState] = useState<SearchState>({ kind: 'idle' });
  const [resultsState, setResultsState] =
    useState<BoardSearchResultsState | null>(null);
  const [limit, setLimit] = useState(
    savedSelection?.query.limit ?? BOARD_SEARCH_LIMIT_DEFAULT,
  );
  const [limitInput, setLimitInput] = useState(
    String(savedSelection?.query.limit ?? BOARD_SEARCH_LIMIT_DEFAULT),
  );
  const [limitError, setLimitError] = useState<string | null>(null);
  // Identity of the last searched pattern; the approximate win keeps its
  // stake per pattern (D-476).
  const [searchKey, setSearchKey] = useState(
    savedSelection === null ? '' : `saved:${savedSelection.id}`,
  );
  const symbolsRequestId = useRef(0);
  const searchRequestId = useRef(0);
  const composerRef = useRef<HTMLDivElement>(null);
  const keyboardHandlerRef = useRef<(event: KeyboardEvent) => void>(() => {});
  const appliedReplayId = useRef<string | null>(null);
  const [replayNotices, setReplayNotices] = useState<readonly string[]>([]);
  const [approximateReplay, setApproximateReplay] =
    useState<BoardSearchApproximateWinReplay | null>(null);

  const draft: BoardSearchDraft = {
    query:
      searchContextId === null
        ? { ...query, cells: patternBoardSearchCells(editor), limit }
        : query,
    searchContextId,
    startSequenceNumber:
      savedSequence ??
      (resultsState === null
        ? null
        : (activeBoardSearchResult(resultsState)?.sequenceNumber ?? null)),
    spinCount,
    pinnedSpinPositions: pins,
  };
  const draftKey = boardSearchDraftKey(draft);
  const dirty =
    managed &&
    (baseline === null
      ? draft.query.cells.length > 0 ||
        draft.startSequenceNumber !== null ||
        pins.length > 0 ||
        spinCount !== APPROXIMATE_WIN_RANGE_DEFAULT ||
        limit !== BOARD_SEARCH_LIMIT_DEFAULT
      : baseline !== draftKey);
  useEffect(() => {
    if (managed) hostCallbacks.current.onDraftChange?.(draft);
  }, [draftKey, managed]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    hostCallbacks.current.onDirtyChange?.(dirty);
  }, [dirty]);
  useEffect(() => {
    const prevent = (event: BeforeUnloadEvent) => {
      if (dirty) {
        event.preventDefault();
        event.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', prevent);
    return () => window.removeEventListener('beforeunload', prevent);
  }, [dirty]);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  async function saveDraft() {
    if (
      onSave === undefined ||
      saveInFlight.current ||
      draft.startSequenceNumber === null ||
      draft.searchContextId === null
    )
      return;
    saveInFlight.current = true;
    setSaving(true);
    setSaveError(null);
    setSaveNotice(null);
    try {
      await onSave(draft);
      if (mounted.current) setBaseline(draftKey);
    } catch (error) {
      if (mounted.current && error instanceof BoardSearchSaveCancelled)
        setSaveNotice(error.message);
      else if (mounted.current)
        setSaveError(
          apiErrorMessage(
            error,
            'Nie udało się zapisać układu. Zachowano niezapisane zmiany. Spróbuj ponownie.',
          ),
        );
    } finally {
      saveInFlight.current = false;
      if (mounted.current) setSaving(false);
    }
  }

  function invalidateDraft() {
    searchRequestId.current += 1;
    if (managed) {
      setSearchContextId(null);
      setSavedSequence(null);
      setQuery({ cells: [], limit, scope: 'all_searchable' });
    }
  }

  const selectedCells = selectedBoardSearchCells(editor);
  const patternCellCount = boardSearchPatternCellCount(editor);
  const unknownCellCount = patternCellCount - selectedCells.length;
  const activeSymbols = useMemo(
    () =>
      [...symbols]
        .filter((symbol) => symbol.status === 'active')
        .sort(
          (left, right) =>
            left.displayOrder - right.displayOrder ||
            left.mobileCode - right.mobileCode ||
            left.id.localeCompare(right.id),
        ),
    [symbols],
  );
  const symbolByCode = useMemo(
    () => new Map(activeSymbols.map((symbol) => [symbol.code, symbol])),
    [activeSymbols],
  );

  useEffect(() => {
    const requestId = ++symbolsRequestId.current;

    void api
      .listSymbols(gameId)
      .then((result) => {
        if (requestId !== symbolsRequestId.current) {
          return;
        }
        if (result.error !== undefined) {
          setSymbolsError(
            apiErrorMessage(result.error, 'Nie udało się pobrać symboli gry.'),
          );
          setSymbolsState('error');
          return;
        }
        setSymbols(result.data ?? []);
        setSymbolsState('ready');
      })
      .catch(() => {
        if (requestId === symbolsRequestId.current) {
          setSymbolsError(
            'Połączenie z lokalnym Admin API zostało przerwane podczas pobierania symboli.',
          );
          setSymbolsState('error');
        }
      });

    return () => {
      symbolsRequestId.current += 1;
      searchRequestId.current += 1;
    };
  }, [api, gameId]);

  useEffect(() => {
    const listener = (event: KeyboardEvent) =>
      keyboardHandlerRef.current(event);
    window.addEventListener('keydown', listener);
    return () => window.removeEventListener('keydown', listener);
  }, []);

  function selectCell(cellIndex: number) {
    setEditor((current) => selectBoardSearchCell(current, cellIndex));
  }

  function placeSymbol(symbolCode: string) {
    invalidateDraft();
    setEditor((current) =>
      placeBoardSearchSymbol(current, symbolCode, entryOrder),
    );
    setSearchState({ kind: 'idle' });
    setResultsState(null);
  }

  function placeUnknown() {
    invalidateDraft();
    setEditor((current) => placeBoardSearchUnknown(current, entryOrder));
    setSearchState({ kind: 'idle' });
    setResultsState(null);
  }

  function changeEntryOrder(nextEntryOrder: BoardSearchEntryOrder) {
    setEntryOrder(nextEntryOrder);
    setEditor((current) =>
      selectBoardSearchEntryStart(current, nextEntryOrder),
    );
  }

  function undo() {
    invalidateDraft();
    setEditor((current) => undoBoardSearchEdit(current));
    setSearchState({ kind: 'idle' });
    setResultsState(null);
  }

  function reset() {
    invalidateDraft();
    setEditor((current) => resetBoardSearchEditor(current));
    setSearchState({ kind: 'idle' });
    setResultsState(null);
    if (compact && managed) {
      setPins([]);
      setSpinCount(APPROXIMATE_WIN_RANGE_DEFAULT);
    }
  }

  function runSearch(
    options: {
      readonly limit?: number;
      readonly preserveSelection?: boolean;
      /** Replay: the pattern to search with right away. */
      readonly editor?: typeof editor;
      readonly onResults?: (state: BoardSearchResultsState) => void;
    } = {},
  ) {
    const searchEditor = options.editor ?? editor;
    if (
      selectedBoardSearchCells(searchEditor).length === 0 ||
      (searchState.kind === 'loading' && options.editor === undefined)
    ) {
      return;
    }
    const effectiveLimit = options.limit ?? limit;
    const preserveSelection = options.preserveSelection ?? false;
    const requestId = ++searchRequestId.current;
    const patternCells = patternBoardSearchCells(searchEditor);
    const patternKey = patternCells
      .map((cell) => `${cell.cellIndex}:${cell.symbolCode ?? '?'}`)
      .join('|');
    setSearchState({ kind: 'loading' });
    void api
      .searchGameBoards(gameId, {
        // `?` cells are sent too: scoring ignores them, the share log keeps
        // the whole pattern (D-472).
        cells: patternCells,
        limit: effectiveLimit,
        // Always every searchable board (TASK-0784): the scope choice is gone.
        scope: 'all_searchable',
      })
      .then((result) => {
        if (requestId !== searchRequestId.current) {
          return;
        }
        const data = result.data;
        if (result.error !== undefined || data === undefined) {
          setSearchState({
            kind: 'error',
            message: apiErrorMessage(
              result.error,
              'Nie udało się wyszukać plansz dla podanego wzoru.',
            ),
          });
          setResultsState(null);
          return;
        }
        setSearchState({ kind: 'ready', result: data });
        if (managed) {
          setQuery({
            cells: patternCells,
            limit: effectiveLimit,
            scope: 'all_searchable',
          });
          setSearchContextId(result.searchContextId ?? null);
          if (!preserveSelection) setSavedSequence(null);
        }
        setSearchKey(managed ? `${patternKey}:${requestId}` : patternKey);
        if (options.onResults !== undefined) {
          const fresh = createBoardSearchResultsState(data.results);
          setResultsState(fresh);
          options.onResults(fresh);
          return;
        }
        setResultsState((previous) =>
          preserveSelection && previous !== null
            ? reconcileBoardSearchResultsState(previous, data.results)
            : createBoardSearchResultsState(data.results),
        );
      })
      .catch(() => {
        if (requestId === searchRequestId.current) {
          setSearchState({
            kind: 'error',
            message:
              'Połączenie z lokalnym Admin API zostało przerwane podczas wyszukiwania.',
          });
          setResultsState(null);
        }
      });
  }

  function commitLimit() {
    const parsed = parseBoardSearchLimit(limitInput);
    if (!parsed.ok) {
      setLimitError(parsed.error);
      return;
    }
    setLimitError(null);
    setLimitInput(String(parsed.value));
    const changed = parsed.value !== limit;
    setLimit(parsed.value);
    if (managed && changed) {
      invalidateDraft();
      setResultsState(null);
      setSearchState({ kind: 'idle' });
      return;
    }
    if (
      changed &&
      resultsState !== null &&
      searchState.kind !== 'loading' &&
      selectedCells.length > 0
    ) {
      runSearch({ limit: parsed.value, preserveSelection: true });
    }
  }

  function handleKeyboardShortcut(event: KeyboardEvent) {
    if (
      event.defaultPrevented ||
      symbolsState !== 'ready' ||
      isTextEntryKeyboardTarget(event.target)
    ) {
      return;
    }
    const command = resolveBoardSearchKeyboardCommand(event, activeSymbols);
    if (command === null) return;
    if (command.kind === 'search') {
      // Enter on a focused result or other control outside the editor keeps
      // its native meaning.
      const target = event.target;
      const outsideComposer =
        target instanceof Node &&
        target !== document.body &&
        !(composerRef.current?.contains(target) ?? false);
      if (
        outsideComposer ||
        selectedCells.length === 0 ||
        searchState.kind === 'loading'
      ) {
        return;
      }
      event.preventDefault();
      runSearch();
      return;
    }
    if (command.kind === 'undo') {
      if (editor.history.length === 0) return;
      event.preventDefault();
      undo();
      return;
    }
    event.preventDefault();
    if (command.kind === 'place_unknown') {
      placeUnknown();
    } else {
      placeSymbol(command.symbolCode);
    }
  }

  useEffect(() => {
    keyboardHandlerRef.current = handleKeyboardShortcut;
  });

  function applyReplay(request: BoardSearchReplayRequest) {
    const { state: nextEditor, inactiveCodes } = boardSearchEditorFromPattern(
      request.cells,
      new Set(activeSymbols.map((symbol) => symbol.code)),
    );
    const notices: string[] = inactiveCodes.map(
      (code) =>
        `Symbol „${code}” nie jest już aktywny — w jego miejscu jest ?.`,
    );
    setEditor(nextEditor);
    setLimit(request.limit);
    setLimitInput(String(request.limit));
    setLimitError(null);
    setApproximateReplay(null);
    setReplayNotices(notices);
    if (selectedBoardSearchCells(nextEditor).length === 0) {
      setSearchState({ kind: 'idle' });
      setResultsState(null);
      setReplayNotices([
        ...notices,
        'Wzór nie ma żadnego aktywnego symbolu, więc wyszukiwania nie uruchomiono.',
      ]);
      return;
    }
    runSearch({
      editor: nextEditor,
      limit: request.limit,
      onResults: (results) => {
        const range = request.approximateWin;
        if (range === null) {
          if (request.boardSequenceNumber !== null) {
            setReplayNotices((current) => [
              ...current,
              `Ten link nie wykonał wcześniej udanego obliczenia przybliżonej wygranej, więc okna planszy #${request.boardSequenceNumber} nie otwarto.`,
            ]);
          }
          return;
        }
        const selected = selectBoardSearchResultBySequence(
          results,
          range.startSequenceNumber,
        );
        if (selected === null) {
          setReplayNotices((current) => [
            ...current,
            `Planszy startowej #${range.startSequenceNumber} nie ma w wynikach tego wyszukiwania, więc przybliżonej wygranej nie otwarto.`,
          ]);
          return;
        }
        setResultsState(selected);
        setApproximateReplay({
          boardSequenceNumber: request.boardSequenceNumber,
          id: request.id,
          spinCount: range.spinCount,
        });
      },
    });
  }

  useEffect(() => {
    if (
      replay === null ||
      symbolsState !== 'ready' ||
      appliedReplayId.current === replay.id
    ) {
      return;
    }
    appliedReplayId.current = replay.id;
    const request = replay;
    queueMicrotask(() => {
      applyReplay(request);
      onReplayApplied?.(request.id);
    });
    // Applied once per replay id, as soon as the symbols are known.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [replay?.id, symbolsState]);

  return (
    <section
      aria-label="Wyszukaj plansze"
      className={`boardSearchWorkspace${compact ? ' boardSearchWorkspaceCompact' : ''}`}
    >
      <header className="pageHeader boardSearchHeader">
        <div>
          {compact ? (
            <h3>Wyszukaj plansze</h3>
          ) : (
            <>
              <p className="eyebrow">Plansze · częściowy układ 3 × 5</p>
              <h1>Wyszukaj plansze</h1>
            </>
          )}
          <p className="lead" hidden={compact}>
            Wstaw tylko symbole, które znasz. Wyszukiwanie ocenia pozycje
            niezależnie, dlatego nie wymaga pełnej planszy.
          </p>
        </div>
        {headerActions !== undefined ? (
          <div className="boardSearchHeaderActions">{headerActions}</div>
        ) : null}
      </header>
      {onSave !== undefined ? (
        <div className="boardSearchActions">
          <button
            className="primaryButton"
            type="button"
            disabled={
              saving ||
              !dirty ||
              draft.startSequenceNumber === null ||
              draft.searchContextId === null ||
              searchState.kind === 'loading'
            }
            onClick={() => void saveDraft()}
          >
            {saving ? 'Zapisywanie…' : saveLabel}
          </button>
          <span role="status">
            {dirty ? 'Niezapisane zmiany układu' : 'Układ zapisany'}
          </span>
        </div>
      ) : null}
      {saveError === null ? null : (
        <p role="alert" className="feedbackBanner feedbackBannerError">
          {saveError}
        </p>
      )}
      {saveNotice === null ? null : <p role="status">{saveNotice}</p>}

      <div className="boardSearchResultLimit">
        <label>
          <span>Liczba wyników</span>
          <input
            aria-label="Liczba wyników wyszukiwania"
            disabled={searchState.kind === 'loading'}
            inputMode="numeric"
            max={100}
            min={1}
            onBlur={commitLimit}
            onChange={(event) => setLimitInput(event.currentTarget.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault();
                commitLimit();
              }
            }}
            type="number"
            value={limitInput}
          />
        </label>
      </div>
      {limitError ? (
        <p className="feedbackBanner feedbackBannerError" role="alert">
          {limitError}
        </p>
      ) : null}

      {symbolsState === 'loading' ? (
        <p className="boardSearchFeedback" role="status">
          Wczytywanie aktywnych symboli…
        </p>
      ) : null}
      {symbolsState === 'error' ? (
        <p className="feedbackBanner feedbackBannerError" role="alert">
          {symbolsError}
        </p>
      ) : null}

      {symbolsState === 'ready' ? (
        <div className="boardSearchComposer" ref={composerRef}>
          <aside className="boardSearchPalette" aria-label="Paleta symboli">
            <header>
              <h2>Symbole</h2>
              <p>Kliknij symbol, aby wstawić go do zaznaczonego pola.</p>
              <p className="boardSearchShortcutHint">
                Klawiatura: <kbd>1</kbd>–<kbd>9</kbd> symbol · <kbd>0</kbd>{' '}
                nieznany (?) · <kbd>Backspace</kbd> cofnij · <kbd>Enter</kbd>{' '}
                szukaj
              </p>
            </header>
            {activeSymbols.length === 0 ? (
              <p className="boardSearchEmptyPalette">
                Ta gra nie ma aktywnych symboli do wyszukania.
              </p>
            ) : (
              <div className="boardSearchPaletteGrid">
                {activeSymbols.map((symbol, index) => {
                  const shortcut = digitShortcutLabel(index);
                  return (
                    <button
                      aria-keyshortcuts={shortcut ?? undefined}
                      className="boardSearchSymbolButton"
                      key={symbol.id}
                      onClick={() => placeSymbol(symbol.code)}
                      title={symbol.name}
                      type="button"
                    >
                      {shortcut !== null ? (
                        <kbd className="boardSearchSymbolShortcut">
                          {shortcut}
                        </kbd>
                      ) : null}
                      {symbol.imagePath ? (
                        <img
                          alt=""
                          src={api.symbolImageAssetUrl(gameId, symbol.id)}
                        />
                      ) : null}
                      <span>{symbol.name}</span>
                    </button>
                  );
                })}
                <button
                  aria-keyshortcuts={BOARD_SEARCH_UNKNOWN_SHORTCUT}
                  className="boardSearchSymbolButton boardSearchUnknownButton"
                  onClick={placeUnknown}
                  title="Nieznany symbol — brak dowodu"
                  type="button"
                >
                  <kbd className="boardSearchSymbolShortcut">
                    {BOARD_SEARCH_UNKNOWN_SHORTCUT}
                  </kbd>
                  <strong>?</strong>
                  <span>Nieznany</span>
                </button>
              </div>
            )}
          </aside>

          <div className="boardSearchPattern">
            <header>
              <h2>Twój wzór</h2>
              <p>
                {patternCellCount === 0
                  ? 'Wybierz pole albo symbol, aby rozpocząć.'
                  : `${selectedCells.length} z 15 znanych pozycji${unknownCellCount > 0 ? ` · ${unknownCellCount} bez dowodu (?)` : ''}.`}
              </p>
            </header>
            <fieldset className="boardSearchEntryOrder">
              <legend>Kolejność wpisywania</legend>
              <label>
                <input
                  checked={entryOrder === 'columns'}
                  name="board-search-entry-order"
                  onChange={() => changeEntryOrder('columns')}
                  type="radio"
                />
                Kolumnami
              </label>
              <label>
                <input
                  checked={entryOrder === 'rows'}
                  name="board-search-entry-order"
                  onChange={() => changeEntryOrder('rows')}
                  type="radio"
                />
                Wierszami
              </label>
              <small>
                {entryOrder === 'columns'
                  ? 'Od góry do dołu, następnie kolejna kolumna.'
                  : 'Od lewej do prawej, następnie kolejny wiersz.'}
              </small>
            </fieldset>
            <div
              aria-label="Częściowy układ planszy 3 na 5"
              className="boardSearchGrid"
              role="grid"
            >
              {Array.from({ length: BOARD_SEARCH_ROWS }, (_, rowIndex) =>
                Array.from(
                  { length: BOARD_SEARCH_COLUMNS },
                  (_, columnIndex) => {
                    const cellIndex =
                      rowIndex * BOARD_SEARCH_COLUMNS + columnIndex;
                    const symbolCode = editor.cells[cellIndex];
                    const isUnknown = symbolCode === BOARD_SEARCH_UNKNOWN;
                    const symbol =
                      symbolCode && !isUnknown
                        ? symbolByCode.get(symbolCode)
                        : undefined;
                    const isSelected = editor.selectedCellIndex === cellIndex;
                    return (
                      <button
                        aria-label={`Wiersz ${rowIndex + 1}, kolumna ${columnIndex + 1}${symbol ? `: ${symbol.name}` : isUnknown ? ': nieznany symbol, bez dowodu' : ', puste'}`}
                        aria-pressed={isSelected}
                        className={
                          isSelected
                            ? 'boardSearchCell boardSearchCellSelected'
                            : 'boardSearchCell'
                        }
                        key={cellIndex}
                        onClick={() => selectCell(cellIndex)}
                        type="button"
                      >
                        {symbol?.imagePath ? (
                          <img
                            alt=""
                            src={api.symbolImageAssetUrl(gameId, symbol.id)}
                          />
                        ) : null}
                        <strong>
                          {isUnknown ? '?' : (symbol?.name ?? '—')}
                        </strong>
                        <small>{symbolCode ?? `Pole ${cellIndex + 1}`}</small>
                      </button>
                    );
                  },
                ),
              )}
            </div>
            <footer className="boardSearchActions">
              <button
                className="secondaryButton"
                disabled={editor.history.length === 0}
                onClick={undo}
                type="button"
              >
                Cofnij
              </button>
              <button
                className="secondaryButton"
                disabled={patternCellCount === 0}
                onClick={reset}
                type="button"
              >
                Resetuj
              </button>
              <button
                className="primaryButton"
                disabled={
                  selectedCells.length === 0 || searchState.kind === 'loading'
                }
                onClick={() => runSearch()}
                type="button"
              >
                {searchState.kind === 'loading'
                  ? 'Wyszukiwanie…'
                  : 'Szukaj plansz'}
              </button>
            </footer>
          </div>
        </div>
      ) : null}

      {replayNotices.length > 0 ? (
        <div className="boardSearchReplayNotices" role="status">
          {replayNotices.map((notice) => (
            <p className="feedbackBanner" key={notice}>
              {notice}
            </p>
          ))}
        </div>
      ) : null}
      {searchState.kind === 'error' ? (
        <p className="feedbackBanner feedbackBannerError" role="alert">
          {searchState.message}
        </p>
      ) : null}
      {searchState.kind === 'ready' && resultsState !== null ? (
        <>
          <BoardSearchResults
            compact={compact}
            client={api}
            gameId={gameId}
            rulesVersions={rulesVersions}
            superGameState={searchState.result.superGameState ?? null}
            onBoardEdited={() => runSearch({ preserveSelection: true })}
            onStateChange={(state) => {
              setSavedSequence(null);
              setResultsState(state);
            }}
            state={resultsState}
            symbols={symbols}
            fixedStakeGrosze={fixedStakeGrosze}
            correctionContext={
              managed && draft.startSequenceNumber !== null
                ? {
                    startSequenceNumber: draft.startSequenceNumber,
                    spinCount,
                    stakeGrosze: fixedStakeGrosze,
                  }
                : undefined
            }
          />
          {!managed ? (
            <BoardSearchApproximateWin
              client={api}
              gameId={gameId}
              rulesVersions={rulesVersions}
              searchKey={searchKey}
              onReplayNotice={(notice) =>
                setReplayNotices((current) => [...current, notice])
              }
              replay={approximateReplay}
              selectedResult={activeBoardSearchResult(resultsState)}
              symbols={symbols}
            />
          ) : null}
        </>
      ) : null}
      {managed && draft.startSequenceNumber !== null ? (
        <>
          {savedSequence === null ? null : (
            <BoardSearchSavedBoard
              key={`${savedSequence}:${searchKey}`}
              client={api}
              gameId={gameId}
              sequenceNumber={savedSequence}
              onOpen={() => setSavedBoardOpen(true)}
            />
          )}
          <BoardSearchApproximateWin
            compact={compact}
            client={api}
            gameId={gameId}
            searchKey={searchKey}
            selectedResult={
              resultsState === null
                ? null
                : activeBoardSearchResult(resultsState)
            }
            selectedSequenceNumber={draft.startSequenceNumber}
            fixedStakeGrosze={fixedStakeGrosze}
            spinCount={spinCount}
            onSpinCountChange={setSpinCount}
            pinnedSpinPositions={pins}
            onPinsChange={setPins}
            symbols={symbols}
          />
          {savedBoardOpen ? (
            <BoardSearchBoardLinesModal
              api={api}
              gameId={gameId}
              sequenceNumber={draft.startSequenceNumber}
              symbols={symbols}
              row={null}
              rulesVersionId={null}
              correctionContext={{
                startSequenceNumber: draft.startSequenceNumber,
                spinCount,
                stakeGrosze: fixedStakeGrosze,
              }}
              fixedStakeGrosze={fixedStakeGrosze}
              formatAmount={(credits) =>
                formatApproximateWinAmount(credits * 10, 'pln')
              }
              onClose={(edited) => {
                setSavedBoardOpen(false);
                if (edited) setSearchKey((key) => `${key}:edited`);
              }}
              onRecalculate={() => {
                setSavedBoardOpen(false);
                setSearchKey((key) => `${key}:refresh`);
              }}
            />
          ) : null}
        </>
      ) : null}
    </section>
  );
}
