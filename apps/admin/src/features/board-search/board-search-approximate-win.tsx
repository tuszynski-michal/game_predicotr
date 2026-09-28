'use client';

import type {
  ApproximateWinResponse,
  BoardSearchResultResponse,
} from '@game-predictor/admin-api-client';
import {
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
  APPROXIMATE_WIN_RANGE_DEFAULT,
  APPROXIMATE_WIN_RANGE_MAX,
  type ApproximateWinState,
  approximateWinChartPoints,
  approximateWinRequestKey,
  formatApproximateWinCredits,
  parseApproximateWinRange,
  shouldRequestApproximateWin,
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
    setIsOpen(event.currentTarget.open);
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
  const hasIncompleteData =
    result.completeness.partialBoardCount > 0 ||
    result.completeness.missingBoardCount > 0;

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
          <ApproximateWinPayoutChart rows={result.rows} />
        </>
      ) : (
        <>
          <div className="importRowsTableWrap">
            <table className="importRowsTable">
              <thead>
                <tr>
                  <th>Spin</th>
                  <th>Plansza</th>
                  <th>Wypłata</th>
                  <th>Wypłaty narastająco</th>
                  <th>Koszt narastająco</th>
                  <th>Bilans narastająco</th>
                </tr>
              </thead>
              <tbody>
                {result.rows.map((row) => (
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
                      {formatApproximateWinCredits(row.cumulativePayoutCredits)}
                    </td>
                    <td>
                      {formatApproximateWinCredits(row.cumulativeCostCredits)}
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
          <ApproximateWinPayoutChart rows={result.rows} />
        </>
      )}
    </>
  );
}

function ApproximateWinPayoutChart({
  rows,
}: {
  readonly rows: ApproximateWinResponse['rows'];
}) {
  if (rows.length === 0) {
    return (
      <section
        aria-labelledby="approximateWinChartHeading"
        className="boardSearchApproximateWinChart"
      >
        <h3 id="approximateWinChartHeading">Wypłaty według liczby spinów</h3>
        <p className="importEmptyState">
          Wykres pojawi się po rozpoznaniu pierwszej wypłaty w tym zakresie.
        </p>
      </section>
    );
  }

  const points = approximateWinChartPoints(rows);
  const finalPoint = points.at(-1);
  if (finalPoint === undefined) {
    return null;
  }
  const width = 800;
  const height = 240;
  const padding = { bottom: 34, left: 54, right: 18, top: 18 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;
  const maximumSpin = finalPoint.spinNumber;
  const maximumPayout = finalPoint.cumulativePayoutCredits;
  const toX = (spinNumber: number) =>
    padding.left + (spinNumber / maximumSpin) * chartWidth;
  const toY = (payoutCredits: number) =>
    padding.top + chartHeight - (payoutCredits / maximumPayout) * chartHeight;
  const polylinePoints = points
    .map(
      (point) =>
        `${toX(point.spinNumber)},${toY(point.cumulativePayoutCredits)}`,
    )
    .join(' ');

  return (
    <section
      aria-labelledby="approximateWinChartHeading"
      className="boardSearchApproximateWinChart"
    >
      <div>
        <h3 id="approximateWinChartHeading">Wypłaty według liczby spinów</h3>
        <p>
          Narastające rozpoznane wypłaty; punkty odpowiadają wyłącznie spinom z
          dodatnią wypłatą.
        </p>
      </div>
      <svg
        aria-describedby="approximateWinChartDescription"
        aria-label="Wykres narastających rozpoznanych wypłat według liczby spinów"
        role="img"
        viewBox={`0 0 ${width} ${height}`}
      >
        <desc id="approximateWinChartDescription">
          Od zera do {finalPoint.spinNumber.toLocaleString('pl-PL')} spinów,
          łączna rozpoznana wypłata wynosi{' '}
          {formatApproximateWinCredits(finalPoint.cumulativePayoutCredits)}{' '}
          kredytów.
        </desc>
        <line
          x1={padding.left}
          x2={width - padding.right}
          y1={padding.top + chartHeight}
          y2={padding.top + chartHeight}
        />
        <line
          x1={padding.left}
          x2={padding.left}
          y1={padding.top}
          y2={padding.top + chartHeight}
        />
        <polyline fill="none" points={polylinePoints} />
        <text x={padding.left} y={height - 10}>
          0
        </text>
        <text textAnchor="end" x={width - padding.right} y={height - 10}>
          {maximumSpin.toLocaleString('pl-PL')} spinów
        </text>
        <text x={padding.left - 8} y={padding.top + 4} textAnchor="end">
          {formatApproximateWinCredits(maximumPayout)}
        </text>
      </svg>
    </section>
  );
}
