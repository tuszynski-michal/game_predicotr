'use client';

import type {
  ManagementResultResponse,
  ManagementStake,
  SymbolResponse,
} from '@game-predictor/admin-api-client';
import {
  ApproximateWinBalanceChart,
  ApproximateWinProvisionalSummary,
  BoardSearchBoardLinesModal,
  type BoardSearchDataSource,
} from '../index';
import { useEffect, useState } from 'react';
import {
  type ManagementGameClient,
  managementError,
} from './management-client';
import {
  ManagementBoardPreview,
  managementAmount,
  managementDate,
} from './management-cards';

/** Always reads the immutable version. Current board edits never mutate this view. */
export function ManagementResultView({
  api,
  machineId,
  gameId,
  versionId,
  stake,
  historical,
  pins,
  boardClient,
  writeAllowed,
}: {
  api: ManagementGameClient;
  machineId: string;
  gameId: string;
  versionId: string;
  stake: ManagementStake;
  historical: boolean;
  pins: readonly number[];
  boardClient?: BoardSearchDataSource;
  writeAllowed: boolean;
}) {
  const [result, setResult] = useState<ManagementResultResponse | null>(null);
  const [error, setError] = useState('');
  const [page, setPage] = useState(0);
  const [sequence, setSequence] = useState<number | null>(null);
  const [symbols, setSymbols] = useState<SymbolResponse[]>([]);
  useEffect(() => {
    const controller = new AbortController();
    void api
      .getManagementResult(machineId, gameId, versionId, controller.signal)
      .then((response) => {
        if (controller.signal.aborted) return;
        if (!response.data || response.error !== undefined) {
          setError(
            managementError(
              response.error,
              'Nie udało się wczytać zapisanego wyniku.',
            ),
          );
          return;
        }
        setResult(response.data);
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted)
          setError(
            managementError(cause, 'Nie udało się wczytać zapisanego wyniku.'),
          );
      });
    return () => controller.abort();
  }, [api, machineId, gameId, versionId]);
  const openCurrent = async (next: number) => {
    if (!writeAllowed || !boardClient) return;
    try {
      const response = await boardClient.listSymbols(gameId);
      if (!response.data || response.error !== undefined)
        throw new Error(
          managementError(
            response.error,
            'Nie udało się wczytać symboli do edycji.',
          ),
        );
      setSymbols(response.data);
      setSequence(next);
    } catch (cause) {
      setError(
        managementError(cause, 'Nie udało się otworzyć bieżącej planszy.'),
      );
    }
  };
  if (!result)
    return (
      <section aria-label="Zapisany wynik">
        {error ? (
          <p role="alert">{error}</p>
        ) : (
          <p role="status">Wczytywanie zapisanego wyniku…</p>
        )}
      </section>
    );
  const calculation = result.calculation;
  const amount = (credits: number) =>
    managementAmount(credits, stake, calculation.rules.spinCost);
  const rows = calculation.rows.slice(page * 50, (page + 1) * 50);
  return (
    <section
      aria-label={historical ? 'Historyczny wynik' : 'Ostatni zapisany wynik'}
      className="management-result"
    >
      <h3>
        {historical
          ? 'Historyczny wynik — zapisany stan'
          : 'Ostatni zapisany wynik'}
      </h3>
      <p>
        Plansza startowa #{calculation.startSequenceNumber} ·{' '}
        {managementDate(result.createdAt)} · Reguły{' '}
        {calculation.rules.rulesVersion}
      </p>
      <ManagementBoardPreview codes={result.startSymbolCodes} />
      <p>
        Bilans: {amount(calculation.summary.balanceCredits)} ·{' '}
        {calculation.evaluatedSpinCount.toLocaleString('pl-PL')} spinów
      </p>
      <ApproximateWinProvisionalSummary
        formatAmount={amount}
        result={calculation}
      />
      <ApproximateWinBalanceChart
        compact
        display={{ stakeGrosze: stake, unit: 'pln' }}
        result={calculation}
        pinnedSpinPositions={pins}
      />
      {error ? <p role="alert">{error}</p> : null}
      {writeAllowed && boardClient ? (
        <>
          <p className="feedbackBanner">
            Edycja symboli zmienia bieżące dane gry. Historyczny wykres, tabela
            i reguły pozostają niezmienne.
          </p>
          <button
            onClick={() => void openCurrent(calculation.startSequenceNumber)}
          >
            Edytuj bieżącą planszę startową
          </button>
        </>
      ) : null}
      <div className="boardSearchApproximateWinTableScroll">
        <table className="boardSearchApproximateWinTable">
          <caption>
            Zapisana tabela wypłat —{' '}
            {calculation.rows.length.toLocaleString('pl-PL')} pozycji
          </caption>
          <thead>
            <tr>
              <th>Spin</th>
              <th>Plansza</th>
              <th>Wygrana</th>
              <th>Bilans</th>
              <th>Rodzaj</th>
              {writeAllowed ? <th>Bieżące dane</th> : null}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.spinNumber}>
                <td>{row.spinNumber}</td>
                <td>#{row.sequenceNumber}</td>
                <td>{amount(row.payoutCredits)}</td>
                <td>{amount(row.cumulativeBalanceCredits)}</td>
                <td>
                  {row.payoutKind === 'confirmed_minimum'
                    ? 'Potwierdzone minimum'
                    : row.payoutKind === 'provisional'
                      ? 'Prowizoryczna (supergra)'
                      : 'Dokładna'}
                </td>
                {writeAllowed ? (
                  <td>
                    <button
                      onClick={() => void openCurrent(row.sequenceNumber)}
                    >
                      Edytuj bieżącą planszę #{row.sequenceNumber}
                    </button>
                  </td>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!calculation.rows.length ? (
        <p>Brak wypłat w zapisanym zakresie.</p>
      ) : null}
      {calculation.rows.length > 50 ? (
        <div className="management-actions">
          <button
            disabled={page === 0}
            onClick={() => setPage((current) => current - 1)}
          >
            Poprzednia strona tabeli
          </button>
          <span>
            Strona {page + 1} z {Math.ceil(calculation.rows.length / 50)}
          </span>
          <button
            disabled={(page + 1) * 50 >= calculation.rows.length}
            onClick={() => setPage((current) => current + 1)}
          >
            Następna strona tabeli
          </button>
        </div>
      ) : null}
      {sequence !== null && boardClient ? (
        <BoardSearchBoardLinesModal
          api={boardClient}
          gameId={gameId}
          sequenceNumber={sequence}
          symbols={symbols}
          row={null}
          rulesVersionId={null}
          correctionContext={{
            startSequenceNumber: calculation.startSequenceNumber,
            spinCount: calculation.requestedSpinCount,
            stakeGrosze: stake,
          }}
          fixedStakeGrosze={stake}
          fixedStakeUnit="pln"
          formatAmount={amount}
          onClose={() => setSequence(null)}
          onRecalculate={() => setSequence(null)}
          startInEditMode
          reviewPanel={
            <p role="status">
              Edytujesz bieżące dane gry. Nie zmieniasz historycznego wyniku.
            </p>
          }
        />
      ) : null}
    </section>
  );
}
