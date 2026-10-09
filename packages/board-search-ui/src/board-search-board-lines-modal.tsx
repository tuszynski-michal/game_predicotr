'use client';

import type {
  ApproximateWinRowResponse,
  SymbolResponse,
} from '@game-predictor/admin-api-client';
import { type ReactNode, useEffect, useRef, useState } from 'react';

import { apiErrorMessage } from './api-error';
import {
  formatApproximateWinAmount,
  loadApproximateWinDisplay,
  type ApproximateWinAmountUnit,
  scaleApproximateWinAmountAtStake,
} from './board-search-stake';
import type {
  BoardSearchDataSource,
  BoardSearchEditableCell,
  BoardSearchModalDetail,
  BoardSearchCorrectionContext,
} from './board-search-data-source';

import {
  type BoardCellCorrectionChoice,
  applyBoardCellCorrection,
  boardCellCorrectionPalette,
} from './board-search-board-cell-correction';
import { BoardSearchRulesVersionSelect } from './board-search-rules-version-select';
import {
  type BoardSearchRulesVersionOption,
  boardCountMatchLabel,
} from './board-search-rules-versions';
import {
  BOARD_SCHEMA_CELL,
  type BoardLinePoint,
  type BoardLineVisibility,
  boardCountMatches,
  boardCountedCells,
  boardExpandedCells,
  boardExpansionLabel,
  boardLineKey,
  boardLineOffset,
  boardLineStyles,
  boardLinesConsistency,
  boardLinesPolygonCentroid,
  boardSchemaCellPolygon,
  initialBoardLineVisibility,
  setAllBoardLinesVisibility,
  toggleBoardLineVisibility,
} from './board-search-board-lines-state';

/**
 * Without a local or public correction port the modal is read-only;
 * without `refreshBoardSearchBoardDocument` a stale reading is
 * only explained, not refreshed.
 */
export type BoardLinesClient = Pick<
  BoardSearchDataSource,
  | 'applySymbolCellReviewDecision'
  | 'correctBoardSearchCell'
  | 'hasPendingBoardSearchCell'
  | 'retryBoardSearchCell'
  | 'boardSearchBoardViewUrl'
  | 'getBoardSearchBoardDetail'
  | 'refreshBoardSearchBoardDocument'
  | 'symbolImageAssetUrl'
>;

type CorrectionNotice =
  | { readonly kind: 'ok'; readonly text: string }
  | { readonly kind: 'error'; readonly text: string };

type DetailState =
  | { readonly kind: 'loading' }
  | { readonly kind: 'error'; readonly message: string }
  | {
      readonly kind: 'ready';
      readonly detail: BoardSearchModalDetail;
    };

/** The table values of an approximate-win row the modal is opened from. */
export type BoardLinesTableRow = Pick<
  ApproximateWinRowResponse,
  | 'boardStatus'
  | 'payoutCredits'
  | 'payoutKind'
  | 'sequenceNumber'
  | 'spinNumber'
>;

export function BoardSearchBoardLinesModal({
  api,
  formatAmount,
  gameId,
  onClose,
  onRecalculate,
  row,
  rulesVersionId,
  sequenceNumber,
  symbols,
  correctionContext,
  startInEditMode = false,
  reviewPanel,
  onCorrectionSaved,
  changedCellIndices = [],
  fixedStakeGrosze,
  fixedStakeUnit = loadApproximateWinDisplay().unit,
  rulesVersions = null,
  requestedRulesVersionId = null,
}: {
  readonly api: BoardLinesClient;
  readonly formatAmount: (baseCredits: number) => string;
  readonly gameId: string;
  /** `edited` is true when a cell correction was saved in this modal. */
  readonly onClose: (edited: boolean) => void;
  readonly onRecalculate: () => void;
  /**
   * `null` when opened from the search results, which have no table row: the
   * header and the line check then use the board's own freshly read values.
   */
  readonly row: BoardLinesTableRow | null;
  readonly rulesVersionId: string | null;
  readonly sequenceNumber: number;
  readonly symbols: readonly SymbolResponse[];
  readonly correctionContext?: BoardSearchCorrectionContext;
  readonly startInEditMode?: boolean;
  readonly reviewPanel?:
    | ReactNode
    | ((state: {
        saving: boolean;
        refreshing: boolean;
        ready: boolean;
      }) => ReactNode);
  readonly onCorrectionSaved?: () => void;
  readonly changedCellIndices?: readonly number[];
  /** Optional management stake, scaled using this modal's fresh rules. */
  readonly fixedStakeGrosze?: number;
  readonly fixedStakeUnit?: ApproximateWinAmountUnit;
  /**
   * Admin-only draft preview (D-535): the game's draft and published rules
   * versions for the „Wersja reguł” select. `null` (online share, management
   * panel) shows no select and always reads the latest published rules.
   */
  readonly rulesVersions?: readonly BoardSearchRulesVersionOption[] | null;
  /**
   * The rules version the table was calculated with when it was chosen
   * explicitly; `null` is the latest published version.
   */
  readonly requestedRulesVersionId?: string | null;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<DetailState>({ kind: 'loading' });
  const [visibility, setVisibility] = useState<BoardLineVisibility>(new Set());
  const [imageFailed, setImageFailed] = useState(false);
  const [editMode, setEditMode] = useState(startInEditMode);
  const [selectedCell, setSelectedCell] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<CorrectionNotice | null>(null);
  const [edited, setEdited] = useState(false);
  // Whether the header's fresh values follow a cell correction or only a
  // refresh of a stale reading.
  const [correctionSaved, setCorrectionSaved] = useState(false);
  // The refresh left no search reading at this position: nothing more to do
  // here but close (the table is recalculated then).
  const [documentRemoved, setDocumentRemoved] = useState(false);
  // Between a save and the refetch the shown board is outdated: no header
  // "after correction" values and no cell targets with old revisions.
  const [refreshing, setRefreshing] = useState(false);
  // The rules version this modal evaluates; changing it away from the
  // table's version shows the board's own reading, never the table row.
  const [selectedRulesVersionId, setSelectedRulesVersionId] = useState<
    string | null
  >(requestedRulesVersionId);
  const tableComparable =
    row !== null && selectedRulesVersionId === requestedRulesVersionId;

  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, []);

  useEffect(() => {
    // A late answer for an earlier attempt or board must never be shown.
    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) return;
      // After a correction the previous board stays visible until the fresh
      // one arrives, so the photo and the notice do not disappear.
      setState((previous) =>
        previous.kind === 'ready' ? previous : { kind: 'loading' },
      );
      setImageFailed(false);
      void (
        selectedRulesVersionId === null
          ? api.getBoardSearchBoardDetail(gameId, sequenceNumber)
          : api.getBoardSearchBoardDetail(gameId, sequenceNumber, {
              rulesVersionId: selectedRulesVersionId,
            })
      )
        .then((result) => {
          if (cancelled) return;
          if (result.error !== undefined || result.data === undefined) {
            setState({
              kind: 'error',
              message: apiErrorMessage(
                result.error,
                'Nie udało się pobrać planszy z liniami wypłat.',
              ),
            });
            return;
          }
          setVisibility(initialBoardLineVisibility(result.data.matches));
          setState({ detail: result.data, kind: 'ready' });
          setRefreshing(false);
        })
        .catch(() => {
          if (!cancelled) {
            setState({
              kind: 'error',
              message:
                'Połączenie z lokalnym Admin API zostało przerwane podczas pobierania planszy.',
            });
          }
        });
    });
    return () => {
      cancelled = true;
    };
  }, [api, gameId, sequenceNumber, attempt, selectedRulesVersionId]);

  // Close the native modal first: while it is open everything else is
  // inert, so the parent could not move focus back to the row button.
  const requestClose = () => {
    // A write still in flight must finish first: its result decides whether
    // the table is recalculated.
    if (saving) return;
    dialog.current?.close();
    onClose(edited);
  };

  const detail = state.kind === 'ready' ? state.detail : null;
  const displayAmount =
    fixedStakeGrosze === undefined || detail === null
      ? formatAmount
      : (credits: number) =>
          formatApproximateWinAmount(
            scaleApproximateWinAmountAtStake(
              credits,
              fixedStakeGrosze,
              detail.rules.spinCost,
            ),
            fixedStakeUnit,
          ) + (fixedStakeUnit === 'credits' ? ' kredytów' : '');
  // After a saved correction the table row is known to be stale, so only the
  // lines themselves must still add up to the board payout.
  const consistency =
    detail === null
      ? null
      : edited || row === null || !tableComparable || rulesVersionId === null
        ? boardLinesConsistency(
            detail,
            detail.payoutCredits,
            detail.rules.rulesVersionId,
          )
        : boardLinesConsistency(detail, row.payoutCredits, rulesVersionId);
  // The header shows the table's values until a save or a refresh replaced
  // them; opened from the search results there is no table, so the board's
  // own reading is the only source.
  const freshReading =
    detail !== null && !refreshing && (!tableComparable || edited);
  const headerValues =
    freshReading && detail !== null
      ? {
          boardStatus: detail.boardStatus,
          payoutCredits: detail.payoutCredits,
          payoutKind: detail.payoutKind,
          prefix:
            row === null
              ? 'Wygrana '
              : correctionSaved
                ? 'Po poprawce: wygrana '
                : edited
                  ? 'Po odświeżeniu: wygrana '
                  : 'Dla wybranej wersji reguł: wygrana ',
          staleTableCredits: row === null ? null : row.payoutCredits,
          tableNote: edited ? 'do przeliczenia' : 'dla innej wersji reguł',
        }
      : row !== null
        ? {
            boardStatus: row.boardStatus,
            payoutCredits: row.payoutCredits,
            payoutKind: row.payoutKind,
            prefix: 'Wygrana ',
            staleTableCredits: null,
            tableNote: '',
          }
        : null;
  const editableCells = new Map(
    (detail?.cells ?? []).map((cell) => [cell.cellIndex, cell]),
  );
  const applyDecision = api.applySymbolCellReviewDecision;
  const refreshDocument = api.refreshBoardSearchBoardDocument;
  const canEdit =
    (applyDecision !== undefined || api.correctBoardSearchCell !== undefined) &&
    detail?.cells !== null &&
    detail?.cells !== undefined;
  const palette = boardCellCorrectionPalette(symbols);

  async function saveCorrection(
    cell: BoardSearchEditableCell,
    choice: BoardCellCorrectionChoice,
  ) {
    if (saving || !canEdit) return;
    setSaving(true);
    setNotice(null);
    const result = await applyBoardCellCorrection(
      api,
      gameId,
      cell,
      choice,
      symbols,
      sequenceNumber,
      correctionContext ?? { startSequenceNumber: sequenceNumber },
    );
    setSaving(false);
    const label =
      choice.kind === 'symbol'
        ? (symbols.find((symbol) => symbol.code === choice.symbolCode)?.name ??
          choice.symbolCode)
        : choice.kind === 'unreadable'
          ? 'nieczytelne (?)'
          : 'zła siatka';
    if (result.ok) {
      setEdited(true);
      setCorrectionSaved(true);
      onCorrectionSaved?.();
      setSelectedCell(null);
      setNotice({
        kind: 'ok',
        text: `Zapisano: pole ${cell.cellIndex + 1} → ${label}.`,
      });
    } else {
      setNotice({
        kind: 'error',
        text: result.conflict
          ? `Pole ${cell.cellIndex + 1} zmieniło się w międzyczasie — plansza została odświeżona, wybierz symbol jeszcze raz.`
          : result.error,
      });
    }
    // Fresh revisions and lines after a save, and after a conflict too.
    if (result.ok || result.conflict) {
      setRefreshing(true);
      setAttempt((value) => value + 1);
    }
  }

  async function refreshStaleBoard() {
    if (saving || refreshDocument === undefined) return;
    setSaving(true);
    setNotice(null);
    try {
      const result = await refreshDocument(gameId, sequenceNumber);
      if (result.error !== undefined || result.data === undefined) {
        setNotice({
          kind: 'error',
          text: apiErrorMessage(
            result.error,
            'Nie udało się odświeżyć odczytu planszy.',
          ),
        });
        return;
      }
      // The rebuilt document may change the payout: the table is stale now.
      setEdited(true);
      if (result.data.documentRemoved || result.data.detail === null) {
        setDocumentRemoved(true);
        setNotice({
          kind: 'ok',
          text: 'Po odświeżeniu ta plansza nie ma już odczytu w wyszukiwarce; tabela zostanie przeliczona po zamknięciu okna.',
        });
        return;
      }
      const fresh = result.data.detail;
      setImageFailed(false);
      setVisibility(initialBoardLineVisibility(fresh.matches));
      setState({ detail: fresh, kind: 'ready' });
      setNotice({
        kind: 'ok',
        text: 'Odczyt planszy odświeżony z bieżącej siatki i symboli.',
      });
    } catch {
      setNotice({
        kind: 'error',
        text: 'Połączenie z lokalnym Admin API zostało przerwane.',
      });
    } finally {
      setSaving(false);
    }
  }

  const staleWarning: ReactNode =
    detail !== null && detail.documentStale && !documentRemoved ? (
      <div className="boardSearchBoardLinesStale" role="status">
        {refreshDocument !== undefined ? (
          <>
            <p className="feedbackBanner">
              Siatka tej planszy zmieniła się po zapisaniu odczytu wyszukiwarki.
              Linie i wygrana pochodzą ze starego odczytu (tak samo liczy
              tabela), dlatego pokazano je na schemacie bez zdjęcia. Odśwież
              odczyt, aby policzyć planszę z bieżącej siatki i móc poprawiać
              pola.
            </p>
            <button
              className="primaryButton"
              disabled={saving}
              onClick={() => void refreshStaleBoard()}
              type="button"
            >
              {saving ? 'Odświeżanie…' : 'Odśwież odczyt tej planszy'}
            </button>
          </>
        ) : (
          <p className="feedbackBanner">
            Siatka tej planszy zmieniła się po zapisaniu odczytu wyszukiwarki.
            Linie i wygrana pochodzą ze starego odczytu (tak samo liczy tabela),
            dlatego pokazano je na schemacie bez zdjęcia.
          </p>
        )}
      </div>
    ) : null;

  const selected =
    selectedCell === null ? undefined : editableCells.get(selectedCell);
  const correctionPanel: ReactNode = !canEdit ? (
    (applyDecision !== undefined || api.correctBoardSearchCell !== undefined) &&
    detail !== null &&
    detail.dataSource === 'operational_review' &&
    !detail.documentStale &&
    !edited ? (
      <p className="boardSearchBoardLinesNote">
        Ta plansza nie ma kompletu aktualnych rekordów weryfikacji pól, więc nie
        można jej poprawiać z tego okna.
      </p>
    ) : null
  ) : (
    <div className="boardSearchBoardCellCorrection">
      <button
        aria-pressed={editMode}
        className={editMode ? 'primaryButton' : 'secondaryButton'}
        onClick={() => {
          setEditMode((value) => !value);
          setSelectedCell(null);
        }}
        type="button"
      >
        {editMode ? 'Zakończ poprawianie' : 'Popraw symbole'}
      </button>
      {editMode && selected === undefined ? (
        <p className="boardSearchBoardLinesNote">
          Kliknij pole na planszy, aby wybrać właściwy symbol.
        </p>
      ) : null}
      {editMode && selected !== undefined ? (
        <div
          aria-label={`Popraw pole ${selected.cellIndex + 1}`}
          className="boardSearchBoardCellPalette"
          role="group"
        >
          <p>
            Pole {selected.cellIndex + 1} (wiersz{' '}
            {Math.floor(selected.cellIndex / 5) + 1}, kolumna{' '}
            {(selected.cellIndex % 5) + 1}) · teraz:{' '}
            <strong>
              {cellSymbolName(
                detail?.symbolCodes[selected.cellIndex] ?? null,
                symbols,
              )}
            </strong>
          </p>
          <div className="boardSearchBoardCellPaletteGrid">
            {palette.map((symbol) => (
              <button
                aria-pressed={symbol.code === selected.assignedSymbolCode}
                className="boardSearchSymbolButton"
                disabled={saving}
                key={symbol.id}
                onClick={() =>
                  void saveCorrection(selected, {
                    kind: 'symbol',
                    symbolCode: symbol.code,
                  })
                }
                title={symbol.name}
                type="button"
              >
                {symbol.imagePath ? (
                  // eslint-disable-next-line @next/next/no-img-element -- local Admin API asset
                  <img
                    alt=""
                    src={api.symbolImageAssetUrl(gameId, symbol.id)}
                  />
                ) : null}
                <span>{symbol.name}</span>
              </button>
            ))}
          </div>
          <div className="boardSearchBoardCellPaletteActions">
            <button
              className="secondaryButton"
              disabled={saving}
              onClick={() =>
                void saveCorrection(selected, { kind: 'unreadable' })
              }
              type="button"
            >
              Nieczytelny (?)
            </button>
            <button
              className="secondaryButton"
              disabled={saving}
              onClick={() =>
                void saveCorrection(selected, { kind: 'grid_issue' })
              }
              type="button"
            >
              Zła siatka
            </button>
            <button
              className="textButton"
              disabled={saving}
              onClick={() => setSelectedCell(null)}
              type="button"
            >
              Anuluj
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
  // Outside the editing branch: the last correction may close the board, and
  // its confirmation must still be visible.
  const correctionMessages: ReactNode = (
    <>
      {saving ? <p role="status">Zapisywanie poprawki…</p> : null}
      {notice !== null ? (
        <p
          className={
            notice.kind === 'ok'
              ? 'feedbackBanner'
              : 'feedbackBanner feedbackBannerError'
          }
          role={notice.kind === 'ok' ? 'status' : 'alert'}
        >
          {notice.text}
        </p>
      ) : null}
      {edited ? (
        <p className="boardSearchBoardLinesNote">
          Tabela i kasa na czysto zostaną przeliczone po zamknięciu okna.
        </p>
      ) : null}
    </>
  );

  return (
    <dialog
      aria-labelledby="board-lines-title"
      className="symbolImagePickerDialog boardSearchBoardLinesDialog"
      onCancel={(event) => {
        event.preventDefault();
        requestClose();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) requestClose();
      }}
      ref={dialog}
    >
      <div className="symbolImagePickerCard">
        <header className="symbolImagePickerHeader">
          <div>
            <h2 id="board-lines-title">
              Plansza #{sequenceNumber}
              {row !== null
                ? ` · spin ${row.spinNumber.toLocaleString('pl-PL')}`
                : ''}
            </h2>
            {headerValues !== null ? (
              <p>
                {headerValues.prefix}
                {displayAmount(headerValues.payoutCredits)}
                {headerValues.payoutKind === 'confirmed_minimum'
                  ? ' · częściowa (potwierdzone minimum)'
                  : ''}
                {headerValues.payoutKind === 'provisional'
                  ? ' · prowizoryczny (supergra: może wzrosnąć albo zmaleć)'
                  : ''}
                {detail?.mode === 'super' ? ' · darmowy spin' : ''} ·{' '}
                {boardStatusLabel(headerValues.boardStatus)}
                {headerValues.staleTableCredits !== null
                  ? ` (w tabeli ${displayAmount(headerValues.staleTableCredits)} ${headerValues.tableNote})`
                  : ''}
                . Linia liczy się tylko od lewej krawędzi i kończy na pierwszym
                nieznanym polu.
              </p>
            ) : null}
          </div>
          {rulesVersions !== null ? (
            <BoardSearchRulesVersionSelect
              disabled={saving || state.kind === 'loading'}
              onChange={setSelectedRulesVersionId}
              options={rulesVersions}
              value={selectedRulesVersionId}
            />
          ) : null}
          <button
            className="secondaryButton"
            disabled={saving}
            onClick={requestClose}
            type="button"
          >
            Zamknij
          </button>
        </header>

        {state.kind === 'loading' ? (
          <p role="status">Wczytywanie planszy…</p>
        ) : null}
        {state.kind === 'error' ? (
          <div role="alert">
            <p className="feedbackBanner feedbackBannerError">
              {state.message}
            </p>
            <button
              className="secondaryButton"
              onClick={() => setAttempt((value) => value + 1)}
              type="button"
            >
              Spróbuj ponownie
            </button>
          </div>
        ) : null}
        {detail !== null && consistency?.kind === 'inconsistent' ? (
          <div role="alert">
            <p className="feedbackBanner feedbackBannerError">
              {consistency.reason === 'rules'
                ? 'Reguły wypłat zmieniły się od obliczenia tabeli.'
                : 'Wygrana tej planszy zmieniła się od obliczenia tabeli.'}{' '}
              Linie nie zostały narysowane, aby nie pokazać niespójnego wyniku.
            </p>
            <button
              className="primaryButton"
              onClick={() => {
                // After an edit, closing already recalculates the range.
                if (!edited) onRecalculate();
                requestClose();
              }}
              type="button"
            >
              Przelicz ponownie
            </button>
          </div>
        ) : null}
        {detail !== null && consistency?.kind === 'consistent' ? (
          <BoardLinesView
            api={api}
            detail={detail}
            formatAmount={displayAmount}
            gameId={gameId}
            imageFailed={imageFailed}
            onImageError={() => setImageFailed(true)}
            correctionPanel={
              <>
                {staleWarning}
                {correctionPanel}
                {correctionMessages}
                {api.hasPendingBoardSearchCell?.(gameId, sequenceNumber) ? (
                  <button
                    type="button"
                    className="secondaryButton"
                    disabled={saving}
                    onClick={async () => {
                      if (saving || api.retryBoardSearchCell === undefined)
                        return;
                      setSaving(true);
                      try {
                        const result = await api.retryBoardSearchCell(
                          gameId,
                          sequenceNumber,
                        );
                        if (result.data !== undefined) {
                          setEdited(true);
                          setCorrectionSaved(true);
                          setNotice({
                            kind: 'ok',
                            text: 'Zapis potwierdzony.',
                          });
                          setRefreshing(true);
                          setAttempt((value) => value + 1);
                        } else {
                          setNotice({
                            kind: 'error',
                            text: apiErrorMessage(
                              result.error,
                              'Nie udało się potwierdzić zapisu.',
                            ),
                          });
                          if (
                            typeof result.error === 'object' &&
                            result.error !== null &&
                            'code' in result.error &&
                            result.error.code ===
                              'BOARD_SEARCH_SHARE_CORRECTION_CONFLICT'
                          ) {
                            setRefreshing(true);
                            setAttempt((value) => value + 1);
                          }
                        }
                      } catch {
                        setNotice({
                          kind: 'error',
                          text: 'Połączenie przerwane. Ponów sprawdzenie zapisu.',
                        });
                      } finally {
                        setSaving(false);
                      }
                    }}
                  >
                    Sprawdź ostatni zapis
                  </button>
                ) : null}
              </>
            }
            editableCells={editMode && !refreshing ? editableCells : null}
            onSelectCell={setSelectedCell}
            onVisibilityChange={setVisibility}
            selectedCell={selectedCell}
            changedCellIndices={changedCellIndices}
            symbols={symbols}
            visibility={visibility}
          />
        ) : null}
        {typeof reviewPanel === 'function'
          ? reviewPanel({
              saving,
              refreshing,
              ready: state.kind === 'ready' && !refreshing,
            })
          : reviewPanel}
      </div>
    </dialog>
  );
}

function BoardLinesView({
  api,
  correctionPanel,
  detail,
  editableCells,
  formatAmount,
  gameId,
  imageFailed,
  onImageError,
  onSelectCell,
  onVisibilityChange,
  selectedCell,
  symbols,
  visibility,
  changedCellIndices,
}: {
  readonly api: BoardLinesClient;
  readonly correctionPanel: ReactNode;
  readonly detail: BoardSearchModalDetail;
  /** Cells that can be corrected; `null` outside the correction mode. */
  readonly editableCells: ReadonlyMap<number, BoardSearchEditableCell> | null;
  readonly onSelectCell: (cellIndex: number) => void;
  readonly selectedCell: number | null;
  readonly changedCellIndices: readonly number[];
  readonly formatAmount: (baseCredits: number) => string;
  readonly gameId: string;
  readonly imageFailed: boolean;
  readonly onImageError: () => void;
  readonly onVisibilityChange: (visibility: BoardLineVisibility) => void;
  readonly symbols: readonly SymbolResponse[];
  readonly visibility: BoardLineVisibility;
}) {
  const view = detail.view;
  const polygons = view?.cellPolygons ?? null;
  const usePhoto = view !== null && polygons !== null && !imageFailed;
  const width = usePhoto ? view.width : 5 * BOARD_SCHEMA_CELL;
  const height = usePhoto ? view.height : 3 * BOARD_SCHEMA_CELL;
  const cells: readonly (readonly BoardLinePoint[])[] =
    usePhoto && polygons !== null
      ? polygons.map((polygon) =>
          polygon.map((point) => ({
            x: point.x * view.width,
            y: point.y * view.height,
          })),
        )
      : Array.from({ length: 15 }, (_, index) => boardSchemaCellPolygon(index));
  const centroids = cells.map(boardLinesPolygonCentroid);
  const cellHeight = (index: number) => {
    const ys = (cells[index] ?? []).map((point) => point.y);
    return ys.length === 0 ? 0 : Math.max(...ys) - Math.min(...ys);
  };
  const styles = boardLineStyles(detail.matches);
  const countMatches = boardCountMatches(detail);
  const countedCells = boardCountedCells(countMatches);
  const symbolByCode = new Map(symbols.map((symbol) => [symbol.code, symbol]));
  // A super game series board (TASK-0936): lines were evaluated on the board
  // with the super symbol expanded over whole columns.
  const expansion = detail.expansion ?? null;
  const expandedCells = boardExpandedCells(detail);
  const expansionName =
    expansion === null
      ? ''
      : (symbolByCode.get(expansion.symbolCode)?.name ?? expansion.symbolCode);
  const visibleMatches = detail.matches.filter((match) =>
    visibility.has(boardLineKey(match)),
  );
  const imageUrl =
    view === null
      ? null
      : api.boardSearchBoardViewUrl(
          gameId,
          detail.sequenceNumber,
          detail.boardChecksumSha256,
          view.revision,
        );

  return (
    <div className="boardSearchBoardLines">
      <div className="boardSearchBoardLinesCanvas">
        <svg
          aria-label={`Plansza ${detail.sequenceNumber} z ${visibleMatches.length} widocznymi liniami wypłat`}
          role={editableCells === null ? 'img' : 'group'}
          viewBox={`0 0 ${width} ${height}`}
        >
          {usePhoto && imageUrl !== null ? (
            <image
              height={height}
              href={imageUrl}
              onError={onImageError}
              preserveAspectRatio="none"
              width={width}
              x={0}
              y={0}
            />
          ) : (
            cells.map((cell, index) => {
              const code = detail.symbolCodes[index] ?? null;
              const symbol = code === null ? undefined : symbolByCode.get(code);
              const centre = centroids[index] ?? { x: 0, y: 0 };
              return (
                <g className="boardSearchBoardLinesSchemaCell" key={index}>
                  <polygon points={pointsText(cell)} />
                  {symbol?.imagePath ? (
                    <image
                      height={BOARD_SCHEMA_CELL * 0.62}
                      href={api.symbolImageAssetUrl(gameId, symbol.id)}
                      width={BOARD_SCHEMA_CELL * 0.62}
                      x={centre.x - BOARD_SCHEMA_CELL * 0.31}
                      y={centre.y - BOARD_SCHEMA_CELL * 0.4}
                    />
                  ) : null}
                  {code !== null ? (
                    <text
                      textAnchor="middle"
                      x={centre.x}
                      y={centre.y + BOARD_SCHEMA_CELL * 0.38}
                    >
                      {symbol?.name ?? code}
                    </text>
                  ) : null}
                </g>
              );
            })
          )}
          {cells.map((cell, index) =>
            detail.symbolCodes[index] === null ? (
              <g
                className="boardSearchBoardLinesUnknown"
                key={`unknown:${index}`}
              >
                <polygon points={pointsText(cell)} />
                <text
                  fontSize={cellHeight(index) * 0.42}
                  textAnchor="middle"
                  x={centroids[index]?.x ?? 0}
                  y={(centroids[index]?.y ?? 0) + cellHeight(index) * 0.15}
                >
                  ?
                </text>
              </g>
            ) : null,
          )}
          {cells.map((cell, index) =>
            expandedCells.has(index) ? (
              <g
                aria-label={`Pole ${index + 1}: rozwinięty super symbol ${expansionName}`}
                className="boardSearchBoardLinesExpanded"
                key={`expanded:${index}`}
                pointerEvents="none"
                role="img"
              >
                <polygon
                  points={pointsText(cell)}
                  vectorEffect="non-scaling-stroke"
                />
                <text
                  fontSize={cellHeight(index) * 0.34}
                  textAnchor="middle"
                  x={centroids[index]?.x ?? 0}
                  y={(centroids[index]?.y ?? 0) + cellHeight(index) * 0.12}
                >
                  {expansionName}
                </text>
              </g>
            ) : null,
          )}
          {cells.map((cell, index) =>
            countedCells.has(index) ? (
              <polygon
                aria-label={`Pole ${index + 1}: liczone w sztukach na planszy`}
                className="boardSearchBoardLinesCount"
                key={`count:${index}`}
                points={pointsText(cell)}
                pointerEvents="none"
                vectorEffect="non-scaling-stroke"
              />
            ) : null,
          )}
          {visibleMatches.map((match) => {
            const style = styles.get(boardLineKey(match));
            const color = style?.color ?? '#ffffff';
            // Offsets use the position among all lines, so hiding one line
            // never moves the others.
            const offset = boardLineOffset(
              detail.matches.indexOf(match),
              detail.matches.length,
            );
            const path = match.matchedCells.map((cellIndex) => {
              const centre = centroids[cellIndex] ?? { x: 0, y: 0 };
              return {
                x: centre.x,
                y: centre.y + offset * cellHeight(cellIndex),
              };
            });
            return (
              <g
                className="boardSearchBoardLinesMatch"
                data-line={boardLineKey(match)}
                key={boardLineKey(match)}
              >
                {match.matchedCells.map((cellIndex) => (
                  <polygon
                    fill={color}
                    fillOpacity={0.12}
                    key={cellIndex}
                    points={pointsText(cells[cellIndex] ?? [])}
                    stroke={color}
                    strokeWidth={2}
                    vectorEffect="non-scaling-stroke"
                  />
                ))}
                <polyline
                  fill="none"
                  points={pointsText(path)}
                  stroke={color}
                  strokeDasharray={style?.dashArray}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={4}
                  vectorEffect="non-scaling-stroke"
                />
                {match.jokerCells.map((cellIndex) => {
                  const centre = path[match.matchedCells.indexOf(cellIndex)];
                  return centre === undefined ? null : (
                    <g className="boardSearchBoardLinesJoker" key={cellIndex}>
                      <circle
                        cx={centre.x}
                        cy={centre.y}
                        r={cellHeight(cellIndex) * 0.14}
                        stroke={color}
                      />
                      <text
                        fontSize={cellHeight(cellIndex) * 0.17}
                        textAnchor="middle"
                        x={centre.x}
                        y={centre.y + cellHeight(cellIndex) * 0.06}
                      >
                        W
                      </text>
                    </g>
                  );
                })}
              </g>
            );
          })}
          {cells.map((cell, index) =>
            changedCellIndices.includes(index) ? (
              <polygon
                key={`changed:${index}`}
                points={pointsText(cell)}
                fill="none"
                stroke="#ffd23f"
                strokeWidth={3}
                strokeDasharray="6 4"
                pointerEvents="none"
                vectorEffect="non-scaling-stroke"
                aria-label={`Zmienione pole ${index + 1}`}
              />
            ) : null,
          )}
          {editableCells !== null
            ? cells.map((cell, index) => {
                const record = editableCells.get(index);
                if (record === undefined) return null;
                const name = cellSymbolName(
                  detail.symbolCodes[index] ?? null,
                  symbols,
                );
                return (
                  <polygon
                    aria-label={`Pole ${index + 1}: ${name} — popraw symbol`}
                    aria-pressed={selectedCell === index}
                    className={
                      selectedCell === index
                        ? 'boardSearchBoardCellTarget boardSearchBoardCellTargetSelected'
                        : 'boardSearchBoardCellTarget'
                    }
                    key={`target:${index}`}
                    onClick={() => onSelectCell(index)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        onSelectCell(index);
                      }
                    }}
                    points={pointsText(cell)}
                    role="button"
                    tabIndex={0}
                    vectorEffect="non-scaling-stroke"
                  />
                );
              })
            : null}
        </svg>
        {!usePhoto ? (
          <p className="boardSearchBoardLinesNote">
            {detail.documentStale
              ? 'Odczyt wyszukiwarki jest nieaktualny względem siatki — linie pokazano na schemacie 3 × 5.'
              : view === null || imageFailed
                ? 'Zdjęcie tej planszy jest niedostępne — linie pokazano na schemacie 3 × 5.'
                : 'Plansza archiwalna nie ma zapisanej siatki pól — linie pokazano na schemacie 3 × 5.'}
          </p>
        ) : null}
      </div>

      <aside
        aria-label="Legenda linii wypłat"
        className="boardSearchBoardLinesLegend"
      >
        {correctionPanel}
        <div className="boardSearchBoardLinesLegendActions">
          <button
            className="textButton"
            onClick={() =>
              onVisibilityChange(
                setAllBoardLinesVisibility(detail.matches, true),
              )
            }
            type="button"
          >
            Pokaż wszystkie
          </button>
          <button
            className="textButton"
            onClick={() =>
              onVisibilityChange(
                setAllBoardLinesVisibility(detail.matches, false),
              )
            }
            type="button"
          >
            Ukryj wszystkie
          </button>
        </div>
        {expansion !== null ? (
          <section
            aria-label="Rozwinięcie super symbolu"
            className="boardSearchBoardLinesExpansion"
          >
            <h3>Supergra: rozwinięcie</h3>
            <p data-testid="board-lines-expansion">
              <span
                aria-hidden="true"
                className="boardSearchBoardLinesExpansionSwatch"
              />
              <strong>
                {boardExpansionLabel(expansion, expansionName, formatAmount)}
              </strong>
            </p>
            <p className="boardSearchBoardLinesNote">
              Kolumny z super symbolem są wypełnione w całości i przykrywają
              symbole pod spodem; linie liczone są na planszy rozwiniętej, a
              sztuki na planszy oryginalnej.
            </p>
          </section>
        ) : null}
        {detail.matches.length === 0 ? (
          <p>
            {expansion !== null
              ? 'Poza rozwinięciem ta plansza nie ma wygrywającej linii.'
              : 'Ta plansza nie ma wygrywającej linii.'}
          </p>
        ) : (
          <ul>
            {detail.matches.map((match) => {
              const key = boardLineKey(match);
              const style = styles.get(key);
              const symbol = symbolByCode.get(match.symbolCode);
              return (
                <li key={key}>
                  <label>
                    <input
                      checked={visibility.has(key)}
                      onChange={() =>
                        onVisibilityChange(
                          toggleBoardLineVisibility(visibility, key),
                        )
                      }
                      type="checkbox"
                    />
                    <span
                      aria-hidden="true"
                      className="boardSearchBoardLinesSwatch"
                      style={{
                        borderColor: style?.color,
                        borderStyle:
                          style?.dashArray === undefined
                            ? 'solid'
                            : style.dashArray === '8 5'
                              ? 'dashed'
                              : 'dotted',
                      }}
                    />
                    <span>
                      <strong>{match.paylineName}</strong> ·{' '}
                      {symbol?.name ?? match.symbolCode} × {match.matchedLength}
                      {match.jokerCells.length > 0
                        ? ` (Wild: ${match.jokerCells.length})`
                        : ''}{' '}
                      · {formatAmount(match.payoutCredits)}
                    </span>
                  </label>
                </li>
              );
            })}
          </ul>
        )}
        {countMatches.length > 0 ? (
          <section
            aria-label="Sztuki na planszy"
            className="boardSearchBoardLinesCounts"
          >
            <h3>Sztuki na planszy</h3>
            <ul>
              {countMatches.map((match) => (
                <li key={match.symbolCode}>
                  <span
                    aria-hidden="true"
                    className="boardSearchBoardLinesCountSwatch"
                  />
                  <span>
                    <strong>{boardCountMatchLabel(match, symbols)}</strong> →{' '}
                    {formatAmount(match.payoutCredits)}
                  </span>
                </li>
              ))}
            </ul>
            <p className="boardSearchBoardLinesNote">
              Sztuki liczą się w dowolnym miejscu planszy; nieznane pole (?) nie
              jest liczone.
            </p>
          </section>
        ) : null}
      </aside>
    </div>
  );
}

/** Name of the symbol a cell currently counts as (`?` when unknown). */
function cellSymbolName(
  code: string | null,
  symbols: readonly SymbolResponse[],
): string {
  if (code === null) return '?';
  return symbols.find((symbol) => symbol.code === code)?.name ?? code;
}

function boardStatusLabel(status: string): string {
  switch (status) {
    case 'accepted':
      return 'plansza zatwierdzona';
    case 'corrected':
      return 'plansza poprawiona';
    case 'pending':
      return 'plansza oczekuje';
    default:
      return `status ${status}`;
  }
}

function pointsText(points: readonly BoardLinePoint[]): string {
  return points.map((point) => `${point.x},${point.y}`).join(' ');
}
