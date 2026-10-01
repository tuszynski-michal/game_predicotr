'use client';

import type {
  ApproximateWinResponse,
  ApproximateWinRowResponse,
  BoardSearchResultResponse,
  SymbolResponse,
} from '@game-predictor/admin-api-client';
import {
  type KeyboardEvent,
  type MouseEvent,
  type PointerEvent,
  useEffect,
  useId,
  useRef,
  useState,
} from 'react';

import { apiErrorMessage } from './api-error';
import type { BoardSearchDataSource } from './board-search-data-source';

import {
  APPROXIMATE_WIN_CHART_LABEL,
  APPROXIMATE_WIN_CHART_LABEL_LAYOUT,
  APPROXIMATE_WIN_CHART_WIDTH,
  APPROXIMATE_WIN_IDLE_STATE,
  APPROXIMATE_WIN_PIN_LIMIT,
  APPROXIMATE_WIN_RANGE_DEFAULT,
  APPROXIMATE_WIN_RANGE_MAX,
  type ApproximateWinChartPoint,
  type ApproximateWinState,
  approximateWinAxisTicks,
  approximateWinChartPoints,
  approximateWinExtremes,
  approximateWinPointKey,
  approximateWinMachineCashAtPoint,
  approximateWinStakeToPoint,
  approximateWinRequestKey,
  filterApproximateWinRows,
  layoutApproximateWinPinLabels,
  moveApproximateWinHighlight,
  parseApproximateWinRange,
  shouldRequestApproximateWin,
  toggleApproximateWinPinnedPoint,
  visibleApproximateWinResult,
} from './board-search-approximate-win-state';
import {
  BoardSearchBoardLinesModal,
  type BoardLinesClient,
} from './board-search-board-lines-modal';
import { boardSearchResultIdentity } from './board-search-results-state';
import {
  type ApproximateWinAmountUnit,
  type ApproximateWinDisplay,
  approximateWinDisplayValue,
  approximateWinStakeMultiplier,
  approximateWinStakeOptions,
  effectiveApproximateWinStakeGrosze,
  formatApproximateWinAmount,
  formatApproximateWinAxisValue,
  formatZloty,
  loadApproximateWinDisplay,
  saveApproximateWinDisplay,
  scaleApproximateWinAmountAtStake,
} from './board-search-stake';

type ApproximateWinClient = Pick<
  BoardSearchDataSource,
  'getBoardSearchApproximateWin'
> &
  BoardLinesClient;

interface BoardSearchApproximateWinProps {
  readonly client: ApproximateWinClient;
  readonly gameId: string;
  /** Replay (D-472): open with this range and optionally one board. */
  readonly replay?: {
    readonly id: string;
    readonly spinCount: number;
    readonly boardSequenceNumber: number | null;
  } | null;
  readonly onReplayNotice?: (notice: string) => void;
  /**
   * Identity of the current search pattern (D-476): a new pattern clears the
   * chosen stake, so an old stake is never applied to a new search.
   */
  readonly searchKey: string;
  readonly selectedResult: BoardSearchResultResponse | null;
  /** Game symbols for the fallback board schema in the payline modal. */
  readonly symbols?: readonly SymbolResponse[];
}

/** The chosen stake for one search pattern; `null` until the operator picks. */
type StakeChoice = {
  readonly searchKey: string;
  readonly stakeGrosze: number | null;
};

/** Debounce for the calculation while browsing results (D-476). */
const CALCULATION_DELAY_MS = 400;

export function BoardSearchApproximateWin({
  client: api,
  gameId,
  onReplayNotice,
  replay = null,
  searchKey,
  selectedResult,
  symbols = [],
}: BoardSearchApproximateWinProps) {
  const appliedReplayId = useRef<string | null>(null);
  const [boardRequest, setBoardRequest] = useState<{
    readonly id: string;
    readonly sequenceNumber: number;
  } | null>(null);
  const [rangeInput, setRangeInput] = useState(
    String(APPROXIMATE_WIN_RANGE_DEFAULT),
  );
  const [range, setRange] = useState(APPROXIMATE_WIN_RANGE_DEFAULT);
  const [rangeError, setRangeError] = useState<string | null>(null);
  const [state, setState] = useState<ApproximateWinState>(
    APPROXIMATE_WIN_IDLE_STATE,
  );
  const requestIdRef = useRef(0);
  const [unit, setUnit] = useState<ApproximateWinAmountUnit>(
    () => loadApproximateWinDisplay().unit,
  );
  const [stakeChoice, setStakeChoice] = useState<StakeChoice | null>(null);
  // The spin cost of the last result keeps the stake list usable while a
  // new calculation is loading.
  const [knownSpinCost, setKnownSpinCost] = useState<number | null>(null);
  // With no spin cost there is no stake to choose: złote are credits / 10.
  const stakeChosen =
    (knownSpinCost !== null && knownSpinCost <= 0) ||
    (stakeChoice !== null && stakeChoice.searchKey === searchKey);
  const display: ApproximateWinDisplay = {
    stakeGrosze:
      stakeChoice !== null && stakeChoice.searchKey === searchKey
        ? stakeChoice.stakeGrosze
        : null,
    unit,
  };

  function changeUnit(next: ApproximateWinAmountUnit) {
    setUnit(next);
    saveApproximateWinDisplay({ stakeGrosze: null, unit: next });
  }

  const resultIdentity = selectedResult
    ? boardSearchResultIdentity(selectedResult)
    : null;
  const requestKey =
    resultIdentity !== null
      ? approximateWinRequestKey({
          gameId,
          resultIdentity,
          spinCount: range,
        })
      : null;

  function runCalculation(key: string, sequenceNumber: number) {
    const requestId = ++requestIdRef.current;
    setState({ key, kind: 'loading' });
    void api
      .getBoardSearchApproximateWin(gameId, {
        spinCount: range,
        startSequenceNumber: sequenceNumber,
      })
      .then((result) => {
        if (requestId !== requestIdRef.current) {
          return;
        }
        const data = result.data;
        if (result.error !== undefined || data === undefined) {
          setState({
            key,
            kind: 'error',
            message: apiErrorMessage(
              result.error,
              'Nie udało się obliczyć przybliżonej wygranej.',
            ),
          });
          return;
        }
        setKnownSpinCost(data.rules.spinCost);
        setState({ key, kind: 'ready', result: data });
      })
      .catch(() => {
        if (requestId === requestIdRef.current) {
          setState({
            key,
            kind: 'error',
            message:
              'Połączenie z lokalnym Admin API zostało przerwane podczas obliczania.',
          });
        }
      });
  }

  useEffect(() => {
    if (!shouldRequestApproximateWin({ isOpen: true, requestKey, state })) {
      return;
    }
    if (requestKey === null || selectedResult === null) {
      return;
    }
    const key = requestKey;
    const sequenceNumber = selectedResult.sequenceNumber;
    // The section is always open (D-476): browsing results must not fire a
    // calculation per keystroke, so the request waits for the selection to
    // settle; a superseded request is dropped by its id.
    const timeout = window.setTimeout(
      () => runCalculation(key, sequenceNumber),
      CALCULATION_DELAY_MS,
    );
    return () => window.clearTimeout(timeout);
    // Re-run only when the (board, range) key changes; `state` is read for
    // the guard above but must not itself retrigger this effect, or every
    // setState here would immediately refire it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestKey]);

  useEffect(() => {
    if (replay === null || appliedReplayId.current === replay.id) return;
    appliedReplayId.current = replay.id;
    const request = replay;
    queueMicrotask(() => {
      setRangeInput(String(request.spinCount));
      setRange(request.spinCount);
      setRangeError(null);
      // The recipient's stake is not recorded (D-472): show the base stake.
      setStakeChoice({ searchKey, stakeGrosze: null });
      setBoardRequest(
        request.boardSequenceNumber === null
          ? null
          : { id: request.id, sequenceNumber: request.boardSequenceNumber },
      );
    });
    // The search key of the replayed pattern is already current here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [replay]);

  function commitRange() {
    const parsed = parseApproximateWinRange(rangeInput);
    if (!parsed.ok) {
      setRangeError(parsed.error);
      return;
    }
    setRangeError(null);
    setRangeInput(String(parsed.value));
    setRange(parsed.value);
  }

  const visibleResult = visibleApproximateWinResult(state, requestKey);
  const showError = state.kind === 'error' && state.key === requestKey;
  const showLoading = state.kind === 'loading' && state.key === requestKey;
  const spinCost = visibleResult?.rules.spinCost ?? knownSpinCost;

  return (
    <section
      aria-labelledby="approximateWinHeading"
      className="boardSearchApproximateWin"
    >
      <h2 id="approximateWinHeading">
        {visibleResult
          ? `Plansza startowa #${visibleResult.startSequenceNumber} · ${visibleResult.evaluatedSpinCount.toLocaleString('pl-PL')} spinów`
          : 'Przybliżona wygrana'}
      </h2>
      <div className="boardSearchApproximateWinBody">
        <div className="boardSearchApproximateWinControls">
          <label>
            <span>Zakres wygranej</span>
            <input
              aria-label="Zakres wygranej — liczba kolejnych spinów"
              disabled={state.kind === 'loading'}
              inputMode="numeric"
              max={APPROXIMATE_WIN_RANGE_MAX}
              min={1}
              onBlur={commitRange}
              onChange={(event) => setRangeInput(event.currentTarget.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault();
                  commitRange();
                }
              }}
              type="number"
              value={rangeInput}
            />
          </label>
          <ApproximateWinDisplayControls
            display={display}
            onStakeChange={(stakeGrosze) =>
              setStakeChoice({ searchKey, stakeGrosze })
            }
            onUnitChange={changeUnit}
            spinCost={spinCost}
            stakeChosen={stakeChosen}
          />
          <small className="boardSearchApproximateWinControlsHint">
            Liczba kolejnych spinów po wybranej planszy (S+1…S+N), niezależna od
            „Liczby wyników”. Stawka jest wybierana osobno dla każdego
            wyszukanego wzoru.
          </small>
        </div>
        {rangeError ? (
          <p className="feedbackBanner feedbackBannerError" role="alert">
            {rangeError}
          </p>
        ) : null}

        {selectedResult === null ? (
          <p className="boardSearchEmptyPalette">
            Najpierw wybierz wynik wyszukiwania.
          </p>
        ) : null}

        {selectedResult !== null && showLoading ? (
          <p className="boardSearchFeedback" role="status">
            Obliczanie dla planszy #{selectedResult.sequenceNumber} ·{' '}
            {range.toLocaleString('pl-PL')} spinów…
          </p>
        ) : null}

        {showError ? (
          <>
            <p className="feedbackBanner feedbackBannerError" role="alert">
              {state.kind === 'error' ? state.message : ''}
            </p>
            <button
              className="secondaryButton"
              onClick={() =>
                requestKey !== null && selectedResult !== null
                  ? runCalculation(requestKey, selectedResult.sequenceNumber)
                  : undefined
              }
              type="button"
            >
              Spróbuj ponownie
            </button>
          </>
        ) : null}

        {visibleResult && !stakeChosen ? (
          <p className="boardSearchApproximateWinStakePrompt" role="status">
            Wybierz stawkę, aby zobaczyć wynik dla planszy #
            {visibleResult.startSequenceNumber}.
          </p>
        ) : null}

        {visibleResult && stakeChosen ? (
          <ApproximateWinResultView
            api={api}
            display={display}
            gameId={gameId}
            onRecalculate={() =>
              requestKey !== null && selectedResult !== null
                ? runCalculation(requestKey, selectedResult.sequenceNumber)
                : undefined
            }
            boardRequest={boardRequest}
            onBoardRequestHandled={(found, sequenceNumber) => {
              setBoardRequest(null);
              if (!found) {
                onReplayNotice?.(
                  `Plansza #${sequenceNumber} nie ma wygranej w tym zakresie, więc jej okna nie otwarto.`,
                );
              }
            }}
            result={visibleResult}
            symbols={symbols}
          />
        ) : null}
      </div>
    </section>
  );
}

/** Formats base-stake credits in the chosen stake and unit (D-470). */
function approximateWinAmountFormatter(
  display: ApproximateWinDisplay,
  spinCost: number,
) {
  const stake = effectiveApproximateWinStakeGrosze(display, spinCost);
  return (baseCredits: number) =>
    formatApproximateWinAmount(
      scaleApproximateWinAmountAtStake(baseCredits, stake, spinCost),
      display.unit,
    );
}

function unitNoun(unit: ApproximateWinAmountUnit): string {
  return unit === 'credits' ? ' kredytów' : '';
}

function ApproximateWinResultView({
  api,
  boardRequest,
  display,
  gameId,
  onBoardRequestHandled,
  onRecalculate,
  result,
  symbols,
}: {
  readonly api: BoardLinesClient;
  readonly boardRequest: {
    readonly id: string;
    readonly sequenceNumber: number;
  } | null;
  readonly onBoardRequestHandled: (
    found: boolean,
    sequenceNumber: number,
  ) => void;
  readonly display: ApproximateWinDisplay;
  readonly gameId: string;
  readonly onRecalculate: () => void;
  readonly result: ApproximateWinResponse;
  readonly symbols: readonly SymbolResponse[];
}) {
  const [minimumPayoutCredits, setMinimumPayoutCredits] = useState(0);
  const [linesRow, setLinesRow] = useState<ApproximateWinRowResponse | null>(
    null,
  );
  const linesTriggerRef = useRef<HTMLButtonElement | null>(null);
  useEffect(() => {
    if (boardRequest === null) return;
    const request = boardRequest;
    const row =
      result.rows.find(
        (item) => item.sequenceNumber === request.sequenceNumber,
      ) ?? null;
    queueMicrotask(() => {
      if (row !== null) setLinesRow(row);
      onBoardRequestHandled(row !== null, request.sequenceNumber);
    });
    // Handled once per request; the callback identity does not matter.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [boardRequest?.id, result]);
  const closeLines = (edited: boolean) => {
    setLinesRow(null);
    if (edited) {
      // A saved cell correction changed the payouts: recalculate the range.
      onRecalculate();
      return;
    }
    // Return focus to the row button that opened the modal.
    linesTriggerRef.current?.focus();
  };
  const spinCost = result.rules.spinCost;
  const amount = approximateWinAmountFormatter(display, spinCost);
  const hasIncompleteData =
    result.completeness.partialBoardCount > 0 ||
    result.completeness.missingBoardCount > 0;
  const visibleRows = filterApproximateWinRows(
    result.rows,
    minimumPayoutCredits,
  );

  return (
    <>
      <div className="boardSearchApproximateWinSummaryHeader">
        {result.startBoardStatus === 'pending' ? (
          <p className="feedbackBanner" role="status">
            Plansza startowa #{result.startSequenceNumber} nie jest jeszcze
            zatwierdzona — jej pozycja w sekwencji może się jeszcze zmienić.
          </p>
        ) : null}
        {result.wrappedAtSequenceEnd ? (
          <p className="feedbackBanner" role="status">
            Zakres przechodzi przez koniec sekwencji (
            {result.sequenceLength.toLocaleString('pl-PL')}) i zawija się do
            pozycji 1.
          </p>
        ) : null}
      </div>

      <p className="importSubsectionHeader">
        {result.completeness.completeBoardCount.toLocaleString('pl-PL')} plansz
        kompletnych,{' '}
        {result.completeness.partialBoardCount.toLocaleString('pl-PL')}{' '}
        częściowych,{' '}
        {result.completeness.missingBoardCount.toLocaleString('pl-PL')}{' '}
        brakujących
      </p>

      {hasIncompleteData ? (
        <p className="feedbackBanner" role="status">
          Wynik opiera się wyłącznie na dostępnych i rozpoznanych symbolach.
          Brakujące lub niepotwierdzone wygrane nie są doliczane, ale koszt
          każdego spinu pozostaje uwzględniony. To ostrożne oszacowanie według
          zapisanych danych, a nie statystyczna prognoza ani gwarancja
          rzeczywistej wygranej.
        </p>
      ) : null}

      {result.rows.length === 0 ? (
        <>
          <p className="importEmptyState">
            W analizowanym zakresie nie ma rozpoznanej wygranej.
            {hasIncompleteData
              ? ' Przy niepełnych danych nie można wykluczyć niewykrytej wygranej.'
              : ''}
          </p>
          <ApproximateWinBalanceChart
            display={display}
            key={`${result.startSequenceNumber}:${result.requestedSpinCount}:${result.dataFingerprintSha256}`}
            result={result}
          />
        </>
      ) : (
        <>
          <ApproximateWinBalanceChart
            display={display}
            key={`${result.startSequenceNumber}:${result.requestedSpinCount}:${result.dataFingerprintSha256}`}
            result={result}
          />
          <ApproximateWinTableFilter
            formatAmount={(credits) =>
              `${amount(credits)}${unitNoun(display.unit)}`
            }
            maximumPayoutCredits={
              approximateWinExtremes(
                result.rows.map((row) => row.payoutCredits),
              ).maximum
            }
            minimumPayoutCredits={minimumPayoutCredits}
            onMinimumPayoutCreditsChange={setMinimumPayoutCredits}
          />
          <div className="importRowsTableWrap">
            <table className="importRowsTable">
              <thead>
                <tr>
                  <th>Spin</th>
                  <th>Plansza</th>
                  <th>Wygrana</th>
                  <th>Kasa na czysto</th>
                  <th>
                    <span className="boardSearchVisuallyHidden">Akcje</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {visibleRows.map((row) => (
                  <tr key={row.sequenceNumber}>
                    <td>{row.spinNumber.toLocaleString('pl-PL')}</td>
                    <td>#{row.sequenceNumber}</td>
                    <td>
                      {amount(row.payoutCredits)}
                      {row.payoutKind === 'confirmed_minimum'
                        ? ' · częściowa (potwierdzone minimum)'
                        : ''}
                    </td>
                    <td>{amount(row.cumulativeBalanceCredits)}</td>
                    <td>
                      <button
                        aria-label={`Pokaż planszę #${row.sequenceNumber} z liniami wypłat`}
                        className="textButton"
                        onClick={(event) => {
                          linesTriggerRef.current = event.currentTarget;
                          setLinesRow(row);
                        }}
                        type="button"
                      >
                        Pokaż planszę
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {visibleRows.length === 0 ? (
            <p className="importEmptyState">
              Brak wygranych spełniających wybrany próg.
            </p>
          ) : null}
          {linesRow !== null ? (
            <BoardSearchBoardLinesModal
              api={api}
              formatAmount={(credits) =>
                `${amount(credits)}${unitNoun(display.unit)}`
              }
              gameId={gameId}
              key={linesRow.sequenceNumber}
              onClose={closeLines}
              onRecalculate={onRecalculate}
              row={linesRow}
              rulesVersionId={result.rules.rulesVersionId}
              symbols={symbols}
            />
          ) : null}
        </>
      )}
    </>
  );
}

function ApproximateWinDisplayControls({
  display,
  onStakeChange,
  onUnitChange,
  spinCost,
  stakeChosen,
}: {
  readonly display: ApproximateWinDisplay;
  readonly onStakeChange: (stakeGrosze: number | null) => void;
  readonly onUnitChange: (unit: ApproximateWinAmountUnit) => void;
  /** Unknown until the first result of this game arrived. */
  readonly spinCost: number | null;
  readonly stakeChosen: boolean;
}) {
  const options = spinCost === null ? [] : approximateWinStakeOptions(spinCost);
  const stakeDisabled = spinCost === null || spinCost <= 0;
  const stake =
    spinCost === null
      ? null
      : effectiveApproximateWinStakeGrosze(display, spinCost);
  return (
    <>
      <label>
        <span>Stawka</span>
        <select
          aria-describedby={
            stakeDisabled ? undefined : 'approximateWinStakeHint'
          }
          aria-label="Stawka"
          disabled={stakeDisabled}
          onChange={(event) => {
            const grosze = Number(event.currentTarget.value);
            const option = options.find((item) => item.grosze === grosze);
            if (option === undefined) return;
            // The base option follows the game's spin cost, not a fixed amount.
            onStakeChange(option.isBase ? null : grosze);
          }}
          value={stakeDisabled || !stakeChosen ? '' : String(stake)}
        >
          <option disabled={!stakeDisabled} value="">
            {stakeDisabled ? '—' : 'wybierz stawkę'}
          </option>
          {options.map((option) => (
            <option key={option.grosze} value={String(option.grosze)}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span>Jednostka</span>
        <select
          aria-label="Jednostka"
          onChange={(event) =>
            onUnitChange(
              event.currentTarget.value === 'pln' ? 'pln' : 'credits',
            )
          }
          value={display.unit}
        >
          <option value="pln">złote</option>
          <option value="credits">kredyty</option>
        </select>
      </label>
      {spinCost !== null && spinCost <= 0 ? (
        <p className="feedbackBanner" role="status">
          Koszt spinu opublikowanych reguł wynosi 0, więc stawki nie da się
          przeliczyć. Złote są liczone jako kredyty / 10.
        </p>
      ) : null}
      {stakeChosen && stake !== null && spinCost !== null && spinCost > 0 ? (
        <small id="approximateWinStakeHint">
          Stawka {formatZloty(stake)} · mnożnik{' '}
          {approximateWinStakeMultiplier(display, spinCost)} · 1 zł = 10
          kredytów
        </small>
      ) : null}
    </>
  );
}

function ApproximateWinTableFilter({
  formatAmount,
  maximumPayoutCredits,
  minimumPayoutCredits,
  onMinimumPayoutCreditsChange,
}: {
  readonly formatAmount: (baseCredits: number) => string;
  readonly maximumPayoutCredits: number;
  readonly minimumPayoutCredits: number;
  readonly onMinimumPayoutCreditsChange: (value: number) => void;
}) {
  const value = Math.min(minimumPayoutCredits, maximumPayoutCredits);
  return (
    <label className="boardSearchApproximateWinFilter">
      <span>
        Pokaż wygrane od <output>{formatAmount(value)}</output>
      </span>
      <input
        aria-label="Minimalna wygrana w tabeli"
        max={maximumPayoutCredits}
        min={0}
        onChange={(event) =>
          onMinimumPayoutCreditsChange(Number(event.currentTarget.value))
        }
        step={1}
        type="range"
        value={value}
      />
    </label>
  );
}

/**
 * The cumulative balance chart. `compact` drops the heading and the
 * explanation for places that show many charts (the share query log).
 */
export function ApproximateWinBalanceChart({
  compact = false,
  display,
  result,
}: {
  readonly compact?: boolean;
  readonly display: ApproximateWinDisplay;
  readonly result: ApproximateWinResponse;
}) {
  const rows = result.rows;
  // Several charts can be on one page, so the ids are per instance.
  const instanceId = useId();
  const headingId = `${instanceId}-heading`;
  const descriptionId = `${instanceId}-description`;
  const labelling = compact
    ? { 'aria-label': 'Kasa na czysto według liczby spinów' }
    : { 'aria-labelledby': headingId };
  const [hoveredPoint, setHoveredPoint] =
    useState<ApproximateWinChartPoint | null>(null);
  const [pinnedPoints, setPinnedPoints] = useState<
    readonly ApproximateWinChartPoint[]
  >([]);
  const [pinLimitReached, setPinLimitReached] = useState(false);
  const svgRef = useRef<SVGSVGElement>(null);
  if (rows.length === 0) {
    return (
      <section {...labelling} className="boardSearchApproximateWinChart">
        {compact ? null : (
          <h3 id={headingId}>Kasa na czysto według liczby spinów</h3>
        )}
        <p className="importEmptyState">
          Wykres pojawi się po rozpoznaniu pierwszej wygranej w tym zakresie.
        </p>
      </section>
    );
  }

  const points = approximateWinChartPoints(rows, {
    balanceCredits: result.summary.balanceCredits,
    spinNumber: result.evaluatedSpinCount,
  });
  // The point just before a payout draws the drop; only real states get a label.
  const labelPoints = points.filter((point) => point.kind !== 'before_payout');
  const finalPoint = points.at(-1);
  if (finalPoint === undefined) {
    return null;
  }
  const { maximum: maximumBalance, minimum: minimumBalance } =
    approximateWinExtremes(
      points.map((point) => point.cumulativeBalanceCredits),
    );
  const spinCost = result.rules.spinCost;
  const amount = approximateWinAmountFormatter(display, spinCost);
  // The plot works in the chosen unit so its ticks stay round there too.
  const stake = effectiveApproximateWinStakeGrosze(display, spinCost);
  const plotValue = (baseCredits: number) =>
    approximateWinDisplayValue(
      scaleApproximateWinAmountAtStake(baseCredits, stake, spinCost),
      display.unit,
    );
  // A chart label or pin is read on its own, so it always names the unit.
  const labelAmount = (baseCredits: number) =>
    `${amount(baseCredits)}${unitNoun(display.unit)}`;
  // What must be in hand from zero to get as far as this point (TASK-0778).
  const stakeLabel = (point: ApproximateWinChartPoint) =>
    labelAmount(approximateWinStakeToPoint(rows, spinCost, point));
  // Stake plus net cash: what is on the machine at this point (TASK-0784).
  const machineLabel = (point: ApproximateWinChartPoint) =>
    labelAmount(approximateWinMachineCashAtPoint(rows, spinCost, point));
  const yTicks = approximateWinAxisTicks(
    plotValue(minimumBalance),
    plotValue(maximumBalance),
    5,
  );
  const xTicks = approximateWinAxisTicks(0, finalPoint.spinNumber, 6, {
    integerStep: true,
  });
  const yLow = yTicks[0] ?? plotValue(minimumBalance);
  const yHigh = yTicks.at(-1) ?? plotValue(maximumBalance);
  const xHigh = Math.max(1, xTicks.at(-1) ?? finalPoint.spinNumber);
  const { chartBottom, chartLeft, chartRight, chartTop } = CHART_FRAME;
  const chartWidth = chartRight - chartLeft;
  const chartHeight = chartBottom - chartTop;
  const toX = (spinNumber: number) =>
    chartLeft + (spinNumber / xHigh) * chartWidth;
  const toPlotY = (value: number) =>
    chartBottom - ((value - yLow) / Math.max(1e-9, yHigh - yLow)) * chartHeight;
  const toY = (balanceCredits: number) => toPlotY(plotValue(balanceCredits));
  const polylinePoints = points
    .map(
      (point) =>
        `${toX(point.spinNumber)},${toY(point.cumulativeBalanceCredits)}`,
    )
    .join(' ');

  const pinnedKeys = new Set(pinnedPoints.map(approximateWinPointKey));
  const layoutOptions = APPROXIMATE_WIN_CHART_LABEL_LAYOUT;
  const pinPlacements = layoutApproximateWinPinLabels(
    pinnedPoints.map((point) => ({
      key: approximateWinPointKey(point),
      x: toX(point.spinNumber),
    })),
    layoutOptions,
  );
  const hoverPlacement =
    hoveredPoint !== null &&
    !pinnedKeys.has(approximateWinPointKey(hoveredPoint))
      ? layoutApproximateWinPinLabels(
          [
            {
              key: approximateWinPointKey(hoveredPoint),
              x: toX(hoveredPoint.spinNumber),
            },
          ],
          { ...layoutOptions, reserved: pinPlacements },
        )[0]
      : undefined;
  const pointByKey = new Map(
    labelPoints.map((point) => [approximateWinPointKey(point), point]),
  );

  const closestPoint = (pointerX: number) =>
    labelPoints.reduce((best, point) =>
      Math.abs(toX(point.spinNumber) - pointerX) <
      Math.abs(toX(best.spinNumber) - pointerX)
        ? point
        : best,
    );
  const pointerToViewBoxX = (event: MouseEvent<SVGSVGElement>) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    return bounds.width === 0
      ? null
      : ((event.clientX - bounds.left) / bounds.width) * CHART_WIDTH;
  };
  const togglePin = (point: ApproximateWinChartPoint) => {
    const next = toggleApproximateWinPinnedPoint(pinnedPoints, point);
    setPinLimitReached(next.limitReached);
    setPinnedPoints(next.pins);
  };
  // An unpin control unmounts itself; keep keyboard focus on the chart.
  const unpin = (point: ApproximateWinChartPoint) => {
    togglePin(point);
    svgRef.current?.focus();
  };
  const handlePointerMove = (event: PointerEvent<SVGSVGElement>) => {
    const pointerX = pointerToViewBoxX(event);
    if (pointerX === null) return;
    const closest = closestPoint(pointerX);
    setHoveredPoint((current) =>
      current !== null &&
      approximateWinPointKey(current) === approximateWinPointKey(closest)
        ? current
        : closest,
    );
  };
  const handleClick = (event: MouseEvent<SVGSVGElement>) => {
    const pointerX = pointerToViewBoxX(event);
    if (pointerX === null) return;
    togglePin(closestPoint(pointerX));
  };
  const handleKeyDown = (event: KeyboardEvent<SVGSVGElement>) => {
    if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
      event.preventDefault();
      setHoveredPoint(
        moveApproximateWinHighlight(
          points,
          hoveredPoint === null ? null : approximateWinPointKey(hoveredPoint),
          event.key === 'ArrowRight' ? 1 : -1,
        ),
      );
      return;
    }
    if (event.key === 'Enter' || event.key === ' ') {
      if (event.key === ' ') event.preventDefault();
      if (hoveredPoint !== null) {
        event.preventDefault();
        togglePin(hoveredPoint);
      }
      return;
    }
    if (event.key === 'Escape' && hoveredPoint !== null) {
      event.preventDefault();
      setHoveredPoint(null);
    }
  };

  const labels = [
    ...pinPlacements.map((placement) => ({ pinned: true, placement })),
    ...(hoverPlacement === undefined
      ? []
      : [{ pinned: false, placement: hoverPlacement }]),
  ].flatMap(({ pinned, placement }) => {
    const point = pointByKey.get(placement.key);
    return point === undefined ? [] : [{ pinned, placement, point }];
  });
  // Leaders and markers are drawn first so no leader crosses a label box.
  const renderLeader = ({
    pinned,
    placement,
    point,
  }: (typeof labels)[number]) => {
    const top = chartLabelTop(placement.row);
    const pointY = toY(point.cumulativeBalanceCredits);
    return (
      <g key={`leader:${pinned ? 'pin' : 'hover'}:${placement.key}`}>
        <polyline
          className="boardSearchApproximateWinChartLeader"
          fill="none"
          points={`${placement.x},${top + CHART_LABEL.height} ${placement.pointX},${chartTop} ${placement.pointX},${pointY}`}
        />
        <circle
          className="boardSearchApproximateWinChartMarker"
          cx={placement.pointX}
          cy={pointY}
          r={4}
        />
      </g>
    );
  };
  const renderLabel = ({
    pinned,
    placement,
    point,
  }: (typeof labels)[number]) => {
    const top = chartLabelTop(placement.row);
    const left = placement.x - CHART_LABEL.width / 2;
    const description = `${point.spinNumber.toLocaleString('pl-PL')} spinów, kasa na czysto ${labelAmount(point.cumulativeBalanceCredits)}, wkład ${stakeLabel(point)}, kasa na maszynie ${machineLabel(point)}`;
    return (
      <g
        className={
          pinned
            ? 'boardSearchApproximateWinChartLabel boardSearchApproximateWinChartLabelPinned'
            : 'boardSearchApproximateWinChartLabel'
        }
        key={`${pinned ? 'pin' : 'hover'}:${placement.key}`}
        // A shifted label sits above another point; clicking it must not
        // toggle whichever point is nearest to the pointer.
        onClick={(event) => event.stopPropagation()}
      >
        <rect
          height={CHART_LABEL.height}
          rx={5}
          width={CHART_LABEL.width}
          x={left}
          y={top}
        />
        <text x={left + 7} y={top + 12}>
          {point.spinNumber.toLocaleString('pl-PL')} spinów
        </text>
        <text
          className="boardSearchApproximateWinChartLabelValue"
          x={left + 7}
          y={top + 25}
        >
          Kasa na czysto: {labelAmount(point.cumulativeBalanceCredits)}
        </text>
        <text
          className="boardSearchApproximateWinChartLabelStake"
          x={left + 7}
          y={top + 38}
        >
          Wkład: {stakeLabel(point)}
        </text>
        <text
          className="boardSearchApproximateWinChartLabelMachine"
          x={left + 7}
          y={top + 51}
        >
          Kasa na maszynie: {machineLabel(point)}
        </text>
        {pinned ? (
          <g
            aria-label={`Odepnij punkt: ${description}`}
            className="boardSearchApproximateWinChartUnpin"
            onClick={(event) => {
              event.stopPropagation();
              unpin(point);
            }}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                event.stopPropagation();
                unpin(point);
              }
            }}
            role="button"
            tabIndex={0}
          >
            <rect
              height={16}
              width={16}
              x={left + CHART_LABEL.width - 19}
              y={top + 3}
            />
            <text
              x={left + CHART_LABEL.width - 11}
              y={top + 15}
              textAnchor="middle"
            >
              ×
            </text>
          </g>
        ) : null}
      </g>
    );
  };
  const drawsZeroLine = yLow < 0 && yHigh > 0;

  return (
    <section {...labelling} className="boardSearchApproximateWinChart">
      <div hidden={compact}>
        <h3 id={headingId}>Kasa na czysto według liczby spinów</h3>
        <p>
          Kasa na czysto: rozpoznane wygrane minus koszt wszystkich spinów.
          Między wygranymi spada o koszt każdego spinu; wykres kończy się na
          ostatnim spinie zakresu. Kliknij punkt albo użyj strzałek i Enter, aby
          go przypiąć. „Wkład” to kwota potrzebna od zera, by opłacić spiny do
          tego punktu; „Kasa na maszynie” to wkład plus kasa na czysto.
        </p>
      </div>
      <div className="boardSearchApproximateWinChartCanvas">
        <svg
          ref={svgRef}
          aria-describedby={descriptionId}
          aria-label="Wykres kasy na czysto według liczby spinów"
          onClick={handleClick}
          onKeyDown={handleKeyDown}
          onPointerLeave={() => setHoveredPoint(null)}
          onPointerMove={handlePointerMove}
          aria-roledescription="wykres"
          role="group"
          tabIndex={0}
          viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
        >
          <desc id={descriptionId}>
            Od zera do {finalPoint.spinNumber.toLocaleString('pl-PL')} spinów,
            kasa na czysto na końcu{' '}
            {amount(finalPoint.cumulativeBalanceCredits)}
            {unitNoun(display.unit)}, minimum {amount(minimumBalance)}, maksimum{' '}
            {amount(maximumBalance)}.
          </desc>
          <g className="boardSearchApproximateWinChartGrid">
            {yTicks
              // The dashed zero line replaces the grid line at 0.
              .filter((tick) => !(drawsZeroLine && tick === 0))
              .map((tick) => (
                <line
                  key={`y:${tick}`}
                  x1={chartLeft}
                  x2={chartRight}
                  y1={toPlotY(tick)}
                  y2={toPlotY(tick)}
                />
              ))}
            {xTicks.map((tick) => (
              <line
                key={`x:${tick}`}
                x1={toX(tick)}
                x2={toX(tick)}
                y1={chartTop}
                y2={chartBottom}
              />
            ))}
          </g>
          <line
            className="boardSearchApproximateWinChartAxis"
            x1={chartLeft}
            x2={chartRight}
            y1={chartBottom}
            y2={chartBottom}
          />
          <line
            className="boardSearchApproximateWinChartAxis"
            x1={chartLeft}
            x2={chartLeft}
            y1={chartTop}
            y2={chartBottom}
          />
          {drawsZeroLine ? (
            <line
              className="boardSearchApproximateWinChartZero"
              x1={chartLeft}
              x2={chartRight}
              y1={toPlotY(0)}
              y2={toPlotY(0)}
            />
          ) : null}
          <polyline
            className="boardSearchApproximateWinChartSeries"
            fill="none"
            points={polylinePoints}
          />
          {yTicks.map((tick) => (
            <text
              key={`yl:${tick}`}
              textAnchor="end"
              x={chartLeft - 6}
              y={toPlotY(tick) + 4}
            >
              {formatApproximateWinAxisValue(tick, display.unit)}
            </text>
          ))}
          {xTicks.map((tick) => (
            <text
              key={`xl:${tick}`}
              textAnchor="middle"
              x={toX(tick)}
              y={chartBottom + 16}
            >
              {tick.toLocaleString('pl-PL')}
            </text>
          ))}
          <text textAnchor="end" x={chartRight} y={CHART_HEIGHT - 4}>
            spiny
          </text>
          {display.unit === 'pln' ? (
            <text textAnchor="end" x={chartLeft - 6} y={chartBottom + 16}>
              zł
            </text>
          ) : null}
          {labels.map(renderLeader)}
          {labels.map(renderLabel)}
        </svg>
      </div>
      {pinLimitReached ? (
        <p className="boardSearchApproximateWinChartNotice" role="status">
          Można przypiąć najwyżej {APPROXIMATE_WIN_PIN_LIMIT} punktów. Odepnij
          któryś, aby przypiąć kolejny.
        </p>
      ) : null}
      {pinnedPoints.length > 0 ? (
        <div className="boardSearchApproximateWinChartPins">
          <ul aria-label="Przypięte punkty wykresu">
            {pinnedPoints.map((point) => (
              <li key={approximateWinPointKey(point)}>
                <span>
                  {point.spinNumber.toLocaleString('pl-PL')} spinów · kasa na
                  czysto {labelAmount(point.cumulativeBalanceCredits)} ·{' '}
                  <span className="boardSearchApproximateWinStake">
                    wkład {stakeLabel(point)}
                  </span>{' '}
                  · kasa na maszynie {machineLabel(point)}
                </span>
                <button
                  aria-label={`Odepnij punkt ${point.spinNumber.toLocaleString('pl-PL')} spinów`}
                  className="textButton"
                  onClick={() => unpin(point)}
                  type="button"
                >
                  Odepnij
                </button>
              </li>
            ))}
          </ul>
          <button
            className="secondaryButton"
            onClick={() => {
              setPinnedPoints([]);
              setPinLimitReached(false);
              svgRef.current?.focus();
            }}
            type="button"
          >
            Wyczyść punkty
          </button>
        </div>
      ) : null}
    </section>
  );
}

const CHART_WIDTH = APPROXIMATE_WIN_CHART_WIDTH;
const CHART_LABEL = APPROXIMATE_WIN_CHART_LABEL;
const CHART_LABEL_BAND =
  CHART_LABEL.rows * (CHART_LABEL.height + CHART_LABEL.rowGap) + 8;
const CHART_FRAME = {
  chartBottom: CHART_LABEL_BAND + 190,
  chartLeft: 72,
  chartRight: CHART_WIDTH - 18,
  chartTop: CHART_LABEL_BAND,
} as const;
const CHART_HEIGHT = CHART_FRAME.chartBottom + 36;

/** Top of a label box; row 0 sits directly above the plot. */
function chartLabelTop(row: number): number {
  return (
    CHART_LABEL_BAND -
    8 -
    (row + 1) * (CHART_LABEL.height + CHART_LABEL.rowGap) +
    CHART_LABEL.rowGap
  );
}
