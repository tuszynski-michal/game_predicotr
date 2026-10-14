'use client';

import type {
  BoardImportCoverageResponse,
  createAdminApiClient,
} from '@game-predictor/admin-api-client';
import { useEffect, useRef, useState } from 'react';

import {
  geometryImageStateLabel,
  geometryPositionStateLabel,
  geometryReasonLabel,
} from './geometry-completeness-state';
import { missingReasonLabel } from './missing-boards-state';

const STATUS_LABELS: Readonly<Record<string, string>> = {
  pending: 'Oczekujące',
  accepted: 'Zaakceptowane',
  corrected: 'Poprawione',
  rejected: 'Odrzucone',
  superseded: 'Zastąpione',
};
const INTERSECTION_LABELS: Readonly<Record<string, string>> = {
  unknown_pending: 'Nieznane i oczekujące',
  unreadable_pending: 'Nieczytelne i oczekujące',
  unknown_low: 'Nieznane z niską pewnością',
};

type DiagnosticsClient = Pick<
  ReturnType<typeof createAdminApiClient>,
  'getBoardImportCoverage'
>;

export function GridDiagnosticsControl({
  api,
  gameId,
}: {
  readonly api: DiagnosticsClient;
  readonly gameId: string;
}) {
  const [report, setReport] = useState<BoardImportCoverageResponse | null>(
    null,
  );
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(false);
  const requestId = useRef(0);
  useEffect(
    () => () => {
      requestId.current += 1;
    },
    [],
  );
  async function load() {
    const request = ++requestId.current;
    setLoading(true);
    setError(false);
    try {
      const result = await api.getBoardImportCoverage({
        gameId,
        includeDiagnostics: true,
        limit: 1,
      });
      if (request !== requestId.current) return;
      if (
        result.error ||
        !result.data?.diagnostics ||
        result.data.gameId !== gameId
      ) {
        setError(true);
      } else {
        setReport(result.data);
      }
    } catch {
      if (request === requestId.current) setError(true);
    } finally {
      if (request === requestId.current) setLoading(false);
    }
  }
  return (
    <div aria-busy={loading}>
      <button
        className="secondaryButton"
        type="button"
        disabled={loading}
        onClick={() => void load()}
      >
        {loading
          ? 'Uzgadnianie liczników…'
          : report
            ? 'Odśwież uzgodnienie liczników'
            : 'Uzgodnij liczniki gry'}
      </button>
      {error ? (
        <p role="alert">
          Nie udało się uzgodnić liczników. Poprzedni pomiar może być
          nieaktualny.
        </p>
      ) : null}
      {report ? <GridDiagnosticsPanel report={report} /> : null}
    </div>
  );
}

export function GridDiagnosticsPanel({
  report,
}: {
  readonly report: BoardImportCoverageResponse;
}) {
  const data = report.diagnostics;
  if (!data) return null;
  const number = (value: number) => value.toLocaleString('pl-PL');
  return (
    <section aria-label="Uzgodnienie liczników gry">
      <h4>Uzgodnienie liczników całej gry</h4>
      <p>
        Pomiar: {new Date(report.computedAt).toLocaleString('pl-PL')}. Zakres:
        cała gra, niezależnie od filtra numerów.
      </p>
      <p>
        Kategorie przecinają się. Nie sumuj zdjęć, slotów, plansz i komórek jako
        brakujących plansz.
      </p>
      <dl className="importMetrics">
        <div>
          <dt>Odroczone sloty zdjęć</dt>
          <dd>{number(data.deferredSlotsByStatus.pending ?? 0)}</dd>
        </div>
        <div>
          <dt>Zgłoszone błędne siatki (plansze)</dt>
          <dd>{number(data.flaggedGridBoards)}</dd>
        </div>
        <div>
          <dt>Niepotwierdzona geometria (plansze)</dt>
          <dd>{number(data.unconfirmedGeometryBoards)}</dd>
        </div>
        <div>
          <dt>Nieznane symbole (komórki)</dt>
          <dd>{number(data.symbolCells.unknown ?? 0)}</dd>
        </div>
        <div>
          <dt>Oczekujące symbole (komórki)</dt>
          <dd>{number(data.symbolCells.pending ?? 0)}</dd>
        </div>
        <div>
          <dt>Nieczytelne symbole (komórki)</dt>
          <dd>{number(data.symbolCells.unreadable ?? 0)}</dd>
        </div>
        <div>
          <dt>
            Niska pewność &lt; {number(data.lowConfidenceThreshold * 100)}%
            (oczekujące komórki)
          </dt>
          <dd>{number(data.symbolCells.low_confidence ?? 0)}</dd>
        </div>
      </dl>
      <p>
        Automatyczne cięcie V3 umożliwia weryfikację symboli bez ręcznej
        akceptacji geometrii. Brak akceptacji nie dowodzi błędu pikseli.
        Nieznany symbol nie oznacza brakującej planszy.
      </p>
      <p>
        Dodane sekwencje: {number(data.qualifyingReviewSequences)} z
        kwalifikujących się plansz + {number(data.canonicalSequences)}{' '}
        kanonicznych − {number(data.canonicalReviewOverlap)} wspólnych ={' '}
        {number(report.counts.added)}. Nadmiar kwalifikujących się rekordów:{' '}
        {number(data.duplicateQualifyingReviewRows)}.
      </p>
      <details>
        <summary>Szczegóły populacji i przecięć</summary>
        <p>
          Stan zapisany bramki zdjęć:{' '}
          {number(data.sourceGate.geometry_incomplete ?? 0)} niekompletnych,{' '}
          {number(data.sourceGate.geometry_complete ?? 0)} kompletnych,{' '}
          {number(data.sourceGate.geometry_exception ?? 0)} wyjątków,{' '}
          {number(data.sourceGate.outside_gate ?? 0)} poza bramką;{' '}
          {number(data.sourceGate.not_evaluated ?? 0)} jeszcze nie oceniono.
          Wstrzymane plansze: {number(data.sourceGate.withheld_boards ?? 0)}.
          Stan zapisany może różnić się od bieżącej klasyfikacji poniżej.
        </p>
        <p>
          Pozycje na zdjęciach:{' '}
          {Object.entries(data.sourcePositions)
            .map(
              ([state, count]) =>
                `${geometryPositionStateLabel(state)}: ${number(count)}`,
            )
            .join(' · ')}
          . Pozycje różnych zdjęć mogą wskazywać ten sam numer sekwencji.
        </p>
        <p>
          Odroczone sloty z już dodaną sekwencją:{' '}
          {number(data.deferredSlotCoverage.already_added ?? 0)}. Sloty bez
          planszy w oczekiwanym zakresie:{' '}
          {number(data.deferredSlotCoverage.missing_slots ?? 0)}, obejmujące{' '}
          {number(data.deferredSlotCoverage.missing_unique_sequences ?? 0)}{' '}
          unikalnych brakujących sekwencji. Sloty poza zakresem:{' '}
          {number(data.deferredSlotCoverage.out_of_range ?? 0)}; bez numeru:{' '}
          {number(data.deferredSlotCoverage.unnumbered ?? 0)}.
        </p>
        <p>
          Statusy zapisanych plansz:{' '}
          {Object.entries(data.reviewRowsByStatus)
            .map(
              ([status, count]) =>
                `${STATUS_LABELS[status] ?? 'Pozostałe'}: ${number(count)}`,
            )
            .join(' · ')}
          . Liczby rekordów nie są liczbami unikalnych sekwencji.
        </p>
        <p>
          Zdjęcia:{' '}
          {Object.entries(data.sourceImages)
            .map(
              ([status, count]) =>
                `${status === 'total' ? 'Wszystkie' : geometryImageStateLabel(status)}: ${number(count)}`,
            )
            .join(' · ')}
          .
        </p>
        <p>
          Odroczone sloty według przyczyny:{' '}
          {Object.entries(data.deferredSlotsByReason)
            .map(
              ([reason, count]) =>
                `${geometryReasonLabel(reason) === reason ? 'Inna przyczyna' : geometryReasonLabel(reason)}: ${number(count)}`,
            )
            .join(' · ') || 'brak'}
          .
        </p>
        <p>
          Odrzucone sloty: {number(data.deferredSlotsByStatus.rejected ?? 0)}.
          Zgłoszone siatki z niepotwierdzoną geometrią:{' '}
          {number(data.flaggedUnconfirmedBoards)}.
        </p>
        <p>
          Przecięcia problemów symboli (komórki):{' '}
          {Object.entries(data.symbolCellIntersections)
            .map(
              ([key, count]) =>
                `${INTERSECTION_LABELS[key] ?? 'Pozostałe'}: ${number(count)}`,
            )
            .join(' · ')}
          .
        </p>
        <p>
          Dodatkowe sygnały przy brakujących sekwencjach:{' '}
          {Object.entries(data.missingReasonSignals)
            .map(
              ([reason, count]) =>
                `${missingReasonLabel(reason)}: ${number(count)}`,
            )
            .join(' · ') || 'brak'}
          .
        </p>
        <p>
          Przecięcia przyczyn braków (unikalne sekwencje):{' '}
          {Object.entries(data.missingReasonIntersections)
            .map(
              ([key, count]) =>
                `${key.split('&').map(missingReasonLabel).join(' ∩ ')}: ${number(count)}`,
            )
            .join(' · ') || 'brak'}
          .
        </p>
      </details>
    </section>
  );
}
