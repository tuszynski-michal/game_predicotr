import type {
  GridReinferenceResponse,
  GridReinferenceTargetPage,
} from '@game-predictor/admin-api-client';
import { buildPreparedLocalReviewUrl } from '../reviewer-access/reviewer-local-window';
import { serializeAdminNavigation } from '../catalog/admin-navigation-state';
import { gridReinferenceStateLabels } from './grid-reinference-state';

const outcomes: Record<string, string> = {
  proposal_ready: 'Propozycja do oceny człowieka',
  automatically_written: 'Zapis automatyczny',
  automatic_written: 'Zapis automatyczny',
  protected: 'Chronione',
  unchanged: 'Bez zmiany',
  conflict: 'Konflikt celu',
  binding_required: 'Wymaga przypisania',
  source_missing: 'Brak źródła',
};

export function GridReinferenceReport({
  operation,
  targets,
  onNext,
  busy,
}: {
  operation: GridReinferenceResponse;
  targets: GridReinferenceTargetPage | null;
  onNext: () => void;
  busy: boolean;
}) {
  const scope = operation.scopeStats;
  const effect = operation.effectStats;
  const unfinishedStatistics =
    operation.statsPolicy === 'grid-reinference-stats-v1' &&
    operation.manifestSha256 === null;
  const reviewer =
    typeof window === 'undefined'
      ? null
      : buildPreparedLocalReviewUrl(window.location.href, {
          gameId: operation.gameId,
        });
  const jobs = serializeAdminNavigation('', {
    workspace: 'jobs',
    gameId: operation.gameId,
    section: null,
    seriesId: null,
  });
  return (
    <section aria-label="Podgląd i raport operacji">
      <h4>Operacja</h4>
      <p>
        Stan: {gridReinferenceStateLabels[operation.state] ?? operation.state};
        etap:{' '}
        {operation.phase === 'prepare'
          ? 'przygotowanie zakresu'
          : 'rozpoznawanie siatek'}
        .
      </p>
      <p>
        Postęp operacji: {operation.processedSources} / {operation.sourceCount}{' '}
        wystąpień zdjęć.
      </p>
      <details>
        <summary>Szczegóły operacji i przypięty model</summary>
        <p>
          Operacja {operation.operationId}; rewizja: {operation.revision};
          zadanie: {operation.jobId}.
        </p>
        <pre>{JSON.stringify(operation.modelSnapshot, null, 2)}</pre>
        <p>
          {operation.runtimePolicy}; {operation.acceptancePolicy}
        </p>
      </details>
      <p>
        Wybrano zdjęcia: {operation.membershipCapturedAt ?? 'nie zapisano'}.
      </p>
      <p>
        Okno przygotowania: {operation.preparationStartedAt} —{' '}
        {operation.preparationFinishedAt ?? 'w toku'}. Dane poszczególnych zdjęć
        utrwalano w tym oknie przygotowania.
      </p>
      {operation.state === 'preparing' ? (
        <p>
          Przygotowanie zakresu. Liczniki ukończonego zakresu są niedostępne.
        </p>
      ) : unfinishedStatistics ? (
        <p>Statystyki zakresu są niedostępne: zakres nie został ukończony.</p>
      ) : scope == null ? (
        <p>Statystyki zakresu: nie zapisano.</p>
      ) : (
        <dl>
          {(
            [
              ['Wystąpienia zdjęć', scope.sourceOccurrenceCount],
              ['Wybrane pozycje plansz', scope.selectedSlotCount],
              ['Istniejące plansze', scope.existingBoardCount],
              ['Odroczone pozycje plansz', scope.deferredSlotCount],
              ['Istniejące komórki', scope.existingCellCount],
              ['Dostępne komórki', scope.availableCellCount],
              ['Potencjalne komórki', scope.potentialCellCount],
              ['Wyłącznie propozycje', scope.proposalOnlySlotCount],
              ['Chronione pozycje plansz', scope.protectedSlotCount],
              [
                'Kandydaci do zapisu automatycznego',
                scope.automaticCandidateSlotCount,
              ],
            ] as const
          ).map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      )}
      <p>
        Potencjalne komórki opisują pojemność wybranych pozycji plansz. Nie
        obiecują zapisu ani zmiany pikseli.
      </p>
      <h4>Wykonane działania</h4>
      {unfinishedStatistics ? (
        <p>Statystyki efektów są niedostępne: zakres nie został ukończony.</p>
      ) : effect == null ? (
        <p>Statystyki efektów: nie zapisano.</p>
      ) : (
        <dl>
          {(
            [
              ['Pozycje z zapisaną statystyką', effect.recordedTargetCount],
              [
                'Automatycznie zapisane plansze',
                effect.automaticWrittenBoardCount,
              ],
              ['Nowe plansze', effect.createdBoardCount],
              ['Nowe komórki', effect.createdCellCount],
              [
                'Istniejące komórki ze zmienionymi pikselami',
                effect.changedExistingPixelCellCount,
              ],
              [
                'Istniejące komórki bez zmiany pikseli',
                effect.unchangedExistingPixelCellCount,
              ],
              [
                'Komórki ponownie wymagające oceny',
                effect.newlyRequiresReviewCellCount,
              ],
              [
                'Komórki bez porównania pikseli',
                effect.pixelComparisonUnavailableCellCount,
              ],
              [
                'Pozycje bez zapisanych statystyk',
                effect.notRecordedTargetCount,
              ],
            ] as const
          ).map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      )}
      <p>
        Ponowna ocena może obejmować komórki ze zmienionymi pikselami. Tych
        liczników nie należy sumować.
      </p>
      <ul>
        {Object.entries(operation.outcomes).map(([name, count]) => (
          <li key={name}>
            {outcomes[name] ?? name}: {count} celów
          </li>
        ))}
      </ul>
      <ul>
        {Object.entries(operation.sourceStatusCounts ?? {}).map(
          ([name, count]) => (
            <li key={name}>
              Status źródła {name}: {count} wystąpień zdjęć
            </li>
          ),
        )}
      </ul>
      <details>
        <summary>Identyfikatory zakresu i raportu</summary>
        <p>
          Manifest:{' '}
          <code>{operation.manifestSha256 ?? 'jeszcze niegotowy'}</code>
        </p>
        <p>
          Raport: <code>{operation.reportSha256 ?? 'jeszcze niegotowy'}</code>
        </p>
      </details>
      {operation.pilotAcknowledgement != null ? (
        <details>
          <summary>
            Potwierdzenie pilota — {operation.pilotAcknowledgement.actor},{' '}
            {operation.pilotAcknowledgement.at}
          </summary>
          <p>
            Operacja pilota: {operation.pilotAcknowledgement.pilotOperationId};
            raport: {operation.pilotAcknowledgement.reportSha256}. Potwierdzenie
            nie oznacza pozytywnej oceny jakości.
          </p>
        </details>
      ) : null}
      {operation.executionQuarantine != null ? (
        <p role="alert">
          Kwarantanna: {JSON.stringify(operation.executionQuarantine)}.
          Przygotuj nową operację; tej operacji nie można wznowić.
        </p>
      ) : null}
      <p>
        <a href={jobs}>Otwórz monitor zadań</a>
      </p>
      {reviewer !== null ? (
        <p>
          <a href={reviewer} target="_blank" rel="noreferrer">
            Oceń zapisane propozycje w Korekcie cięcia siatki
          </a>
        </p>
      ) : null}
      <ol>
        {targets?.items.map((target) => (
          <li key={target.targetResultId}>
            Pozycja planszy {target.positionIndex};{' '}
            {outcomes[target.outcome ?? ''] ?? target.outcome ?? 'oczekuje'}
            {target.result != null ? (
              <details>
                <summary>Szczegóły wyniku i przyczyny</summary>
                <p>
                  Cel {target.targetResultId}; zdjęcie {target.sourceImageId}.
                </p>
                <pre>{JSON.stringify(target.result, null, 2)}</pre>
              </details>
            ) : null}
          </li>
        ))}
      </ol>
      {targets?.nextCursor ? (
        <button type="button" disabled={busy} onClick={onNext}>
          Następna strona celów
        </button>
      ) : null}
    </section>
  );
}
