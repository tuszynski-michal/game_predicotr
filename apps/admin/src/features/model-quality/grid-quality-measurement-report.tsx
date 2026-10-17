import type { QualityMeasurementResponse } from '@game-predictor/admin-api-client';

function object(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}
const count = (value: unknown) =>
  typeof value === 'number' && Number.isFinite(value)
    ? String(value)
    : 'nieznane';
const rate = (value: unknown) =>
  typeof value === 'number' && Number.isFinite(value)
    ? `${(100 * value).toFixed(1)}%`
    : 'niezmierzone';

export function GridQualityMeasurementReport({
  measurement,
}: {
  readonly measurement: QualityMeasurementResponse;
}) {
  return (
    <section aria-label="Raport pomiaru">
      <p>
        Populacja zamrożona: {measurement.frozenPopulationCount}. Całkowicie
        zastąpione źródła wyłączone: {measurement.excludedSupersededCount}.
      </p>
      <p>
        Seed: {measurement.seed}. Polityka: {measurement.policy}. Populacja:{' '}
        {measurement.populationPolicy}.
      </p>
      <details>
        <summary>Identyfikatory dowodów</summary>
        <p>Manifest: {measurement.manifestSha256}</p>
        <p>Populacja SHA-256: {measurement.populationSha256}</p>
        <time>{measurement.capturedAt}</time>
      </details>
      {(['random', 'hard'] as const).map((sample) => {
        const report = object(measurement.report[sample]);
        const axes = object(report.axes),
          symbols = object(report.symbols);
        return (
          <section key={sample} aria-label={`Raport ${sample}`}>
            <h4>
              {sample === 'random'
                ? 'Próba losowa — częstości opisowe'
                : 'Trudne przykłady — osobny zbiór'}
            </h4>
            <p>
              Zdjęcia: {count(report.sampleCount)}. Oczekiwane pozycje:{' '}
              {count(report.expectedPositionCount)}. Pełna kontrola geometrii:{' '}
              {count(report.fullyReviewedCount)}. W pełni ocenialne:{' '}
              {count(report.fullyAssessableCount)}.
            </p>
            <p>
              Całe zdjęcia poprawne: {count(report.completeCorrectCount)}.
              Błędne: {count(report.completeIncorrectCount)}. Nieznane:{' '}
              {count(report.completeUnknownCount)}. Dodatkowe detekcje:{' '}
              {count(report.unexpectedDetectionCount)}.
            </p>
            <div style={{ overflowX: 'auto' }}>
              <table>
                <caption>Odrębne mianowniki i pokrycie próby</caption>
                <thead>
                  <tr>
                    <th>Obszar</th>
                    <th>Poprawne / ocenione</th>
                    <th>Częstość poprawnych</th>
                    <th>Pokrycie</th>
                    <th>Błędne</th>
                    <th>Nieznane / niedostępne</th>
                    <th>Nieocenione</th>
                  </tr>
                </thead>
                <tbody>
                  {(['geometry', 'detection', 'sequence'] as const).map(
                    (axis) => {
                      const a = object(axes[axis]);
                      return (
                        <tr key={axis}>
                          <th>
                            {
                              {
                                geometry: 'Geometria',
                                detection: 'Detekcja',
                                sequence: 'Sekwencja',
                              }[axis]
                            }
                          </th>
                          <td>
                            {count(a.correct)} / {count(a.assessedCount)}
                          </td>
                          <td>{rate(a.correctRate)}</td>
                          <td>
                            {count(a.assessedCount)} / {count(a.expectedCount)}{' '}
                            ({rate(a.coverage)})
                          </td>
                          <td>{count(a.incorrect)}</td>
                          <td>
                            {count(a.unknown)} / {count(a.not_assessable)}
                          </td>
                          <td>{count(a.unreviewed)}</td>
                        </tr>
                      );
                    },
                  )}
                </tbody>
              </table>
            </div>
            <p>
              Symbole: {count(symbols.currentManualConfirmationCount)} /{' '}
              {count(symbols.currentCellCount)} aktualnych ręcznych potwierdzeń.
              Skuteczność klasyfikatora: niezmierzona.
            </p>
          </section>
        );
      })}
      <p>
        Brak pełnych anotacji nie oznacza poprawnego wyniku. Trudne przykłady
        nie zmieniają częstości próby losowej. Niezależność nagrań wymaga
        osobnych dowodów.
      </p>
    </section>
  );
}
