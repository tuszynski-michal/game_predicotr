'use client';

/* Local symbol assets are protected Admin API responses, not Next static media. */
/* eslint-disable @next/next/no-img-element */

import type {
  BoardSearchResponse,
  BoardSearchScope,
  SymbolResponse,
} from '@game-predictor/admin-api-client';
import { useEffect, useMemo, useRef, useState } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';
import { apiErrorMessage } from '@/features/catalog/catalog-api-error';

import {
  BOARD_SEARCH_COLUMNS,
  BOARD_SEARCH_ROWS,
  BOARD_SEARCH_UNKNOWN,
  boardSearchPatternCellCount,
  createBoardSearchEditorState,
  placeBoardSearchUnknown,
  placeBoardSearchSymbol,
  resetBoardSearchEditor,
  selectBoardSearchCell,
  selectedBoardSearchCells,
  undoBoardSearchEdit,
} from './board-search-editor-state';
import { BoardSearchResults } from './board-search-results';

type LoadState = 'loading' | 'ready' | 'error';
type SearchState =
  | { readonly kind: 'idle' }
  | { readonly kind: 'loading' }
  | { readonly kind: 'ready'; readonly result: BoardSearchResponse }
  | { readonly kind: 'error'; readonly message: string };

type BoardSearchClient = Pick<
  ReturnType<typeof createConfiguredAdminApiClient>,
  | 'listSymbols'
  | 'searchGameBoards'
  | 'symbolImageAssetUrl'
  | 'operationalImageReviewBoardAssetUrl'
>;

interface BoardSearchWorkspaceProps {
  readonly apiBaseUrl: string;
  readonly client?: BoardSearchClient;
  readonly gameId: string;
}

export function BoardSearchWorkspace({
  apiBaseUrl,
  client,
  gameId,
}: BoardSearchWorkspaceProps) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const [symbols, setSymbols] = useState<readonly SymbolResponse[]>([]);
  const [symbolsState, setSymbolsState] = useState<LoadState>('loading');
  const [symbolsError, setSymbolsError] = useState('');
  const [editor, setEditor] = useState(createBoardSearchEditorState);
  const [scope, setScope] = useState<BoardSearchScope>('all_searchable');
  const [searchState, setSearchState] = useState<SearchState>({ kind: 'idle' });
  const symbolsRequestId = useRef(0);
  const searchRequestId = useRef(0);

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

  function selectCell(cellIndex: number) {
    setEditor((current) => selectBoardSearchCell(current, cellIndex));
  }

  function placeSymbol(symbolCode: string) {
    setEditor((current) => placeBoardSearchSymbol(current, symbolCode));
    setSearchState({ kind: 'idle' });
  }

  function placeUnknown() {
    setEditor((current) => placeBoardSearchUnknown(current));
    setSearchState({ kind: 'idle' });
  }

  function undo() {
    setEditor((current) => undoBoardSearchEdit(current));
    setSearchState({ kind: 'idle' });
  }

  function reset() {
    setEditor((current) => resetBoardSearchEditor(current));
    setSearchState({ kind: 'idle' });
  }

  function changeScope(nextScope: BoardSearchScope) {
    setScope(nextScope);
    setSearchState({ kind: 'idle' });
  }

  function runSearch() {
    if (selectedCells.length === 0 || searchState.kind === 'loading') {
      return;
    }
    const requestId = ++searchRequestId.current;
    setSearchState({ kind: 'loading' });
    void api
      .searchGameBoards(gameId, { cells: selectedCells, scope })
      .then((result) => {
        if (requestId !== searchRequestId.current) {
          return;
        }
        if (result.error !== undefined || result.data === undefined) {
          setSearchState({
            kind: 'error',
            message: apiErrorMessage(
              result.error,
              'Nie udało się wyszukać plansz dla podanego wzoru.',
            ),
          });
          return;
        }
        setSearchState({ kind: 'ready', result: result.data });
      })
      .catch(() => {
        if (requestId === searchRequestId.current) {
          setSearchState({
            kind: 'error',
            message:
              'Połączenie z lokalnym Admin API zostało przerwane podczas wyszukiwania.',
          });
        }
      });
  }

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
      </header>

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
        <div className="boardSearchComposer">
          <aside className="boardSearchPalette" aria-label="Paleta symboli">
            <header>
              <h2>Symbole</h2>
              <p>Kliknij symbol, aby wstawić go do zaznaczonego pola.</p>
            </header>
            {activeSymbols.length === 0 ? (
              <p className="boardSearchEmptyPalette">
                Ta gra nie ma aktywnych symboli do wyszukania.
              </p>
            ) : (
              <div className="boardSearchPaletteGrid">
                {activeSymbols.map((symbol) => (
                  <button
                    className="boardSearchSymbolButton"
                    key={symbol.id}
                    onClick={() => placeSymbol(symbol.code)}
                    title={symbol.name}
                    type="button"
                  >
                    {symbol.imagePath ? (
                      <img
                        alt=""
                        src={api.symbolImageAssetUrl(gameId, symbol.id)}
                      />
                    ) : null}
                    <span>{symbol.name}</span>
                  </button>
                ))}
                <button
                  className="boardSearchSymbolButton boardSearchUnknownButton"
                  onClick={placeUnknown}
                  title="Nieznany symbol — brak dowodu"
                  type="button"
                >
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
                onClick={runSearch}
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

      {searchState.kind === 'error' ? (
        <p className="feedbackBanner feedbackBannerError" role="alert">
          {searchState.message}
        </p>
      ) : null}
      {searchState.kind === 'ready' ? (
        <BoardSearchResults
          apiBaseUrl={apiBaseUrl}
          client={api}
          gameId={gameId}
          response={searchState.result}
        />
      ) : null}
    </section>
  );
}
