'use client';

/* Local symbol assets are protected Admin API responses, not Next static media. */
/* eslint-disable @next/next/no-img-element */

import type {
  BoardSearchResponse,
  BoardSearchScope,
  SymbolResponse,
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

interface BoardSearchWorkspaceProps {
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
}

export function BoardSearchWorkspace({
  client: api,
  gameId,
  headerActions,
  onReplayApplied,
  replay = null,
}: BoardSearchWorkspaceProps) {
  const [symbols, setSymbols] = useState<readonly SymbolResponse[]>([]);
  const [symbolsState, setSymbolsState] = useState<LoadState>('loading');
  const [symbolsError, setSymbolsError] = useState('');
  const [editor, setEditor] = useState(createBoardSearchEditorState);
  const [entryOrder, setEntryOrder] =
    useState<BoardSearchEntryOrder>('columns');
  const [scope, setScope] = useState<BoardSearchScope>('all_searchable');
  const [searchState, setSearchState] = useState<SearchState>({ kind: 'idle' });
  const [resultsState, setResultsState] =
    useState<BoardSearchResultsState | null>(null);
  const [limit, setLimit] = useState(BOARD_SEARCH_LIMIT_DEFAULT);
  const [limitInput, setLimitInput] = useState(
    String(BOARD_SEARCH_LIMIT_DEFAULT),
  );
  const [limitError, setLimitError] = useState<string | null>(null);
  // Identity of the last searched pattern; the approximate win keeps its
  // stake per pattern (D-476).
  const [searchKey, setSearchKey] = useState('');
  const symbolsRequestId = useRef(0);
  const searchRequestId = useRef(0);
  const composerRef = useRef<HTMLDivElement>(null);
  const keyboardHandlerRef = useRef<(event: KeyboardEvent) => void>(() => {});
  const appliedReplayId = useRef<string | null>(null);
  const [replayNotices, setReplayNotices] = useState<readonly string[]>([]);
  const [approximateReplay, setApproximateReplay] =
    useState<BoardSearchApproximateWinReplay | null>(null);

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
    setEditor((current) =>
      placeBoardSearchSymbol(current, symbolCode, entryOrder),
    );
    setSearchState({ kind: 'idle' });
    setResultsState(null);
  }

  function placeUnknown() {
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
    setEditor((current) => undoBoardSearchEdit(current));
    setSearchState({ kind: 'idle' });
    setResultsState(null);
  }

  function reset() {
    setEditor((current) => resetBoardSearchEditor(current));
    setSearchState({ kind: 'idle' });
    setResultsState(null);
  }

  function changeScope(nextScope: BoardSearchScope) {
    if (nextScope === scope) return;
    setScope(nextScope);
    // The scope lives with the results (D-476): changing it repeats the
    // search for the same pattern and keeps the selected board when it is
    // still among the results.
    if (
      resultsState !== null &&
      searchState.kind !== 'loading' &&
      selectedCells.length > 0
    ) {
      runSearch({ preserveSelection: true, scope: nextScope });
      return;
    }
    setSearchState({ kind: 'idle' });
    setResultsState(null);
  }

  function runSearch(
    options: {
      readonly limit?: number;
      readonly preserveSelection?: boolean;
      /** Replay: the pattern and scope to search with right away. */
      readonly editor?: typeof editor;
      readonly scope?: BoardSearchScope;
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
    const effectiveScope = options.scope ?? scope;
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
        scope: effectiveScope,
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
        setSearchKey(patternKey);
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
    setScope(request.scope);
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
      scope: request.scope,
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

  const scopeControls = (
    <fieldset
      className="boardSearchScope"
      disabled={searchState.kind === 'loading'}
    >
      <legend>Zakres wyszukiwania</legend>
      <label>
        <input
          checked={scope === 'all_searchable'}
          name="board-search-scope"
          onChange={() => changeScope('all_searchable')}
          type="radio"
        />
        Wszystkie plansze
      </label>
      <span>zatwierdzone, oczekujące i niepełne</span>
      <label>
        <input
          checked={scope === 'approved_only'}
          name="board-search-scope"
          onChange={() => changeScope('approved_only')}
          type="radio"
        />
        Tylko zatwierdzone
      </label>
      <span>accepted i corrected</span>
    </fieldset>
  );

  return (
    <section aria-label="Wyszukaj plansze" className="boardSearchWorkspace">
      <header className="pageHeader boardSearchHeader">
        <div>
          <p className="eyebrow">Plansze · częściowy układ 3 × 5</p>
          <h1>Wyszukaj plansze</h1>
          <p className="lead">
            Wstaw tylko symbole, które znasz. Wyszukiwanie ocenia pozycje
            niezależnie, dlatego nie wymaga pełnej planszy.
          </p>
        </div>
        {headerActions !== undefined ? (
          <div className="boardSearchHeaderActions">{headerActions}</div>
        ) : null}
      </header>

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
            client={api}
            filters={scopeControls}
            gameId={gameId}
            onStateChange={setResultsState}
            state={resultsState}
          />
          <BoardSearchApproximateWin
            client={api}
            gameId={gameId}
            searchKey={searchKey}
            onReplayNotice={(notice) =>
              setReplayNotices((current) => [...current, notice])
            }
            replay={approximateReplay}
            selectedResult={activeBoardSearchResult(resultsState)}
            symbols={symbols}
          />
        </>
      ) : null}
    </section>
  );
}
