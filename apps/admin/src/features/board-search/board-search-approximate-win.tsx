'use client';

import type {
  ApproximateWinResponse,
  BoardSearchResultResponse,
} from '@game-predictor/admin-api-client';
import {
  type KeyboardEvent,
  type MouseEvent,
  type PointerEvent,
  type SyntheticEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';
import { apiErrorMessage } from '@/features/catalog/catalog-api-error';

import {
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
  approximateWinRequestKey,
  filterApproximateWinRows,
  formatApproximateWinCredits,
  layoutApproximateWinPinLabels,
  moveApproximateWinHighlight,
  parseApproximateWinRange,
  shouldRequestApproximateWin,
  toggleApproximateWinPinnedPoint,
  visibleApproximateWinResult,
} from './board-search-approximate-win-state';
import { boardSearchResultIdentity } from './board-search-results-state';

type ApproximateWinClient = Pick<
  ReturnType<typeof createConfiguredAdminApiClient>,
  'getBoardSearchApproximateWin'
>;

interface BoardSearchApproximateWinProps {
  readonly apiBaseUrl: string;
  readonly client?: ApproximateWinClient;
  readonly gameId: string;
  readonly selectedResult: BoardSearchResultResponse | null;
}

export function BoardSearchApproximateWin({
  apiBaseUrl,
  client,
  gameId,
  selectedResult,
}: BoardSearchApproximateWinProps) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const [isOpen, setIsOpen] = useState(false);
  const [rangeInput, setRangeInput] = useState(
    String(APPROXIMATE_WIN_RANGE_DEFAULT),
  );
  const [range, setRange] = useState(APPROXIMATE_WIN_RANGE_DEFAULT);
  const [rangeError, setRangeError] = useState<string | null>(null);
  const [state, setState] = useState<ApproximateWinState>(
    APPROXIMATE_WIN_IDLE_STATE,
  );
  const requestIdRef = useRef(0);

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
    if (!shouldRequestApproximateWin({ isOpen, requestKey, state })) {
      return;
    }
    if (requestKey === null || selectedResult === null) {
      return;
    }
    const key = requestKey;
    const sequenceNumber = selectedResult.sequenceNumber;
    queueMicrotask(() => runCalculation(key, sequenceNumber));
    // Re-run only when the open state or the (board, range) key changes;
    // `state` is read for the guard above but must not itself retrigger
    // this effect, or every setState here would immediately refire it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, requestKey]);

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

  function handleToggle(event: SyntheticEvent<HTMLDetailsElement>) {
    const open = event.currentTarget.open;
    if (!open) {
      // D-462: a verified symbol changes the payout without a new selection,
      // so collapsing drops the result and reopening always recalculates.
      // Bumping the request id also discards a response still in flight.
      requestIdRef.current += 1;
      setState(APPROXIMATE_WIN_IDLE_STATE);
    }
    setIsOpen(open);
  }

  const visibleResult = visibleApproximateWinResult(state, requestKey);
  const showError = state.kind === 'error' && state.key === requestKey;
  const showLoading = state.kind === 'loading' && state.key === requestKey;

  return (
    <details className="boardSearchApproximateWin" onToggle={handleToggle}>
      <summary>Przybliżona wygrana</summary>
      <div className="boardSearchApproximateWinBody">
        <div className="boardSearchApproximateWinRange">
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
          <small>
            Liczba kolejnych spinów po wybranej planszy (S+1…S+N), niezależna od
            „Liczby wyników”.
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

        {visibleResult ? (
          <ApproximateWinResultView result={visibleResult} />
        ) : null}
      </div>
    </details>
  );
}

function ApproximateWinResultView({
  result,
}: {
  readonly result: ApproximateWinResponse;
}) {
  const [minimumPayoutCredits, setMinimumPayoutCredits] = useState(0);
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
        <p className="eyebrow">
          Plansza startowa #{result.startSequenceNumber} ·{' '}
          {result.evaluatedSpinCount.toLocaleString('pl-PL')} spinów (#
          {result.startSequenceNumber + 1}…#
          {result.startSequenceNumber + result.evaluatedSpinCount})
        </p>
        <p>
          Reguły v{result.rules.rulesVersion} · koszt spinu{' '}
          {formatApproximateWinCredits(result.rules.spinCost)} kredytów
        </p>
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

      <dl className="importMetrics">
        <div className="importMetric">
          <dt>Rozpoznane wypłaty</dt>
          <dd>
            {formatApproximateWinCredits(
              result.summary.recognizedPayoutCredits,
            )}
          </dd>
        </div>
        <div className="importMetric">
          <dt>Koszt spinów</dt>
          <dd>{formatApproximateWinCredits(result.summary.spinCostCredits)}</dd>
        </div>
        <div className="importMetric">
          <dt>Bilans</dt>
          <dd>{formatApproximateWinCredits(result.summary.balanceCredits)}</dd>
        </div>
      </dl>

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
          Brakujące lub niepotwierdzone wypłaty nie są doliczane, ale koszt
          każdego spinu pozostaje uwzględniony. To ostrożne oszacowanie według
          zapisanych danych, a nie statystyczna prognoza ani gwarancja
          rzeczywistej wygranej.
        </p>
      ) : null}

      {result.rows.length === 0 ? (
        <>
          <p className="importEmptyState">
            W analizowanym zakresie nie ma rozpoznanej wypłaty.
            {hasIncompleteData
              ? ' Przy niepełnych danych nie można wykluczyć niewykrytej wygranej.'
              : ''}
          </p>
          <ApproximateWinBalanceChart
            key={`${result.startSequenceNumber}:${result.requestedSpinCount}:${result.dataFingerprintSha256}`}
            result={result}
          />
        </>
      ) : (
        <>
          <ApproximateWinTableFilter
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
                  <th>Wypłata</th>
                  <th>Bilans narastająco</th>
                </tr>
              </thead>
              <tbody>
                {visibleRows.map((row) => (
                  <tr key={row.sequenceNumber}>
                    <td>{row.spinNumber.toLocaleString('pl-PL')}</td>
                    <td>#{row.sequenceNumber}</td>
                    <td>
                      {formatApproximateWinCredits(row.payoutCredits)}
                      {row.payoutKind === 'confirmed_minimum'
                        ? ' · częściowa (potwierdzone minimum)'
                        : ''}
                    </td>
                    <td>
                      {formatApproximateWinCredits(
                        row.cumulativeBalanceCredits,
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {visibleRows.length === 0 ? (
            <p className="importEmptyState">
              Brak wypłat spełniających wybrany próg.
            </p>
          ) : null}
          <ApproximateWinBalanceChart
            key={`${result.startSequenceNumber}:${result.requestedSpinCount}:${result.dataFingerprintSha256}`}
            result={result}
          />
        </>
      )}
    </>
  );
}

function ApproximateWinTableFilter({
  maximumPayoutCredits,
  minimumPayoutCredits,
  onMinimumPayoutCreditsChange,
}: {
  readonly maximumPayoutCredits: number;
  readonly minimumPayoutCredits: number;
  readonly onMinimumPayoutCreditsChange: (value: number) => void;
}) {
  const value = Math.min(minimumPayoutCredits, maximumPayoutCredits);
  return (
    <label className="boardSearchApproximateWinFilter">
      <span>
        Pokaż wypłaty od{' '}
        <output>{formatApproximateWinCredits(value)} kredytów</output>
      </span>
      <input
        aria-label="Minimalna wypłata w tabeli"
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

function ApproximateWinBalanceChart({
  result,
}: {
  readonly result: ApproximateWinResponse;
}) {
  const rows = result.rows;
  const [hoveredPoint, setHoveredPoint] =
    useState<ApproximateWinChartPoint | null>(null);
  const [pinnedPoints, setPinnedPoints] = useState<
    readonly ApproximateWinChartPoint[]
  >([]);
  const [pinLimitReached, setPinLimitReached] = useState(false);
  const svgRef = useRef<SVGSVGElement>(null);
  if (rows.length === 0) {
    return (
      <section
        aria-labelledby="approximateWinChartHeading"
        className="boardSearchApproximateWinChart"
      >
        <h3 id="approximateWinChartHeading">Bilans według liczby spinów</h3>
        <p className="importEmptyState">
          Wykres pojawi się po rozpoznaniu pierwszej wypłaty w tym zakresie.
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
  const yTicks = approximateWinAxisTicks(minimumBalance, maximumBalance, 5);
  const xTicks = approximateWinAxisTicks(0, finalPoint.spinNumber, 6, {
    integerStep: true,
  });
  const yLow = yTicks[0] ?? minimumBalance;
  const yHigh = yTicks.at(-1) ?? maximumBalance;
  const xHigh = Math.max(1, xTicks.at(-1) ?? finalPoint.spinNumber);
  const { chartBottom, chartLeft, chartRight, chartTop } = CHART_FRAME;
  const chartWidth = chartRight - chartLeft;
  const chartHeight = chartBottom - chartTop;
  const toX = (spinNumber: number) =>
    chartLeft + (spinNumber / xHigh) * chartWidth;
  const toY = (balanceCredits: number) =>
    chartBottom -
    ((balanceCredits - yLow) / Math.max(1e-9, yHigh - yLow)) * chartHeight;
  const polylinePoints = points
    .map(
      (point) =>
        `${toX(point.spinNumber)},${toY(point.cumulativeBalanceCredits)}`,
    )
    .join(' ');

  const pinnedKeys = new Set(pinnedPoints.map(approximateWinPointKey));
  const layoutOptions = {
    labelWidth: CHART_LABEL.width,
    maxX: CHART_WIDTH - 4,
    minX: 4,
    rows: CHART_LABEL.rows,
  };
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
    const description = `${point.spinNumber.toLocaleString('pl-PL')} spinów, bilans ${formatApproximateWinCredits(point.cumulativeBalanceCredits)}`;
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
          Bilans: {formatApproximateWinCredits(point.cumulativeBalanceCredits)}
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
    <section
      aria-labelledby="approximateWinChartHeading"
      className="boardSearchApproximateWinChart"
    >
      <div>
        <h3 id="approximateWinChartHeading">Bilans według liczby spinów</h3>
        <p>
          Narastający bilans: rozpoznane wypłaty minus koszt wszystkich spinów.
          Między wypłatami bilans spada o koszt każdego spinu; wykres kończy się
          na ostatnim spinie zakresu. Kliknij punkt albo użyj strzałek i Enter,
          aby go przypiąć.
        </p>
      </div>
      <div className="boardSearchApproximateWinChartCanvas">
        <svg
          ref={svgRef}
          aria-describedby="approximateWinChartDescription"
          aria-label="Wykres narastającego bilansu według liczby spinów"
          onClick={handleClick}
          onKeyDown={handleKeyDown}
          onPointerLeave={() => setHoveredPoint(null)}
          onPointerMove={handlePointerMove}
          aria-roledescription="wykres"
          role="group"
          tabIndex={0}
          viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
        >
          <desc id="approximateWinChartDescription">
            Od zera do {finalPoint.spinNumber.toLocaleString('pl-PL')} spinów,
            bilans końcowy{' '}
            {formatApproximateWinCredits(finalPoint.cumulativeBalanceCredits)}{' '}
            kredytów, minimum {formatApproximateWinCredits(minimumBalance)},
            maksimum {formatApproximateWinCredits(maximumBalance)}.
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
                  y1={toY(tick)}
                  y2={toY(tick)}
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
              y1={toY(0)}
              y2={toY(0)}
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
              y={toY(tick) + 4}
            >
              {formatApproximateWinCredits(tick)}
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
                  {point.spinNumber.toLocaleString('pl-PL')} spinów · bilans{' '}
                  {formatApproximateWinCredits(point.cumulativeBalanceCredits)}
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

const CHART_WIDTH = 800;
const CHART_LABEL = { height: 30, rowGap: 4, rows: 3, width: 124 } as const;
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
