import type {
  ContentReadinessResponse,
  ContentReadinessSummary,
} from '@game-predictor/admin-api-client';
import { reasonLabel } from './grid-model-state';
import { contentRoleLabel } from './grid-content-state';

export function GridContentReadiness({
  value,
}: {
  readonly value: ContentReadinessResponse;
}) {
  function table(summary: ContentReadinessSummary, label: string) {
    return (
      <section aria-label={label}>
        <h4>{label}</h4>
        <p>
          {summary.state === 'evaluable'
            ? 'Dostępny zakres etykiet spełnia wymagania tego odczytu.'
            : 'Etykiety nie wystarczają do oceny tego zakresu.'}
        </p>
        {Object.entries(summary.games).map(([game, roles]) => (
          <table key={game}>
            <caption>
              Zakres etykiet wybranej gry{' '}
              <details>
                <summary>Identyfikator gry</summary>
                {game}
              </details>
            </caption>
            <thead>
              <tr>
                <th>Rola</th>
                <th>Plansze / pola</th>
                <th>Nieznane / niezatwierdzone</th>
                <th>Niepełne zdjęcia</th>
                <th>Pełne zdjęcia</th>
                <th>Przyczyna</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(roles).map(([role, counts]) => (
                <tr key={role}>
                  <th>{contentRoleLabel(role)}</th>
                  <td>
                    {counts.boards} / {counts.slots}
                  </td>
                  <td>
                    {counts.states.unknown} / {counts.unapprovedSlots}
                  </td>
                  <td>{counts.unresolvedPhotos}</td>
                  <td>
                    {counts.fullPhotos}
                    {counts.missingFullPhotos
                      ? ` (brak ${counts.missingFullPhotos})`
                      : ''}
                  </td>
                  <td>
                    {counts.reasonCodes.map(reasonLabel).join('; ') ||
                      'Brak braków w tym zakresie'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ))}
      </section>
    );
  }
  return (
    <section aria-label="Gotowość zawartości">
      <h3>Pokrycie etykietami zawartości</h3>
      <p>
        Postęp bieżącego etykietowania i etykiety przypięte do kohorty są
        osobne. Nowe etykiety nie zmieniają zamrożonej kohorty i nie kwalifikują
        automatu.
      </p>
      {table(value.annotationProgress, 'Bieżący postęp etykietowania')}
      {table(value.frozenPinCoverage, 'Etykiety przypięte do kohorty')}
    </section>
  );
}
