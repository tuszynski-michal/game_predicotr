import type {
  GameResponse,
  GridModelEvaluationView,
} from '@game-predictor/admin-api-client';
import { gameName, reasonLabel } from './grid-model-state';

type ContentReport = Extract<
  NonNullable<GridModelEvaluationView['report']>,
  { schemaVersion: 'grid-model-evaluation-read-v6' }
>;

export type ContentOutcome =
  'improvement' | 'no-improvement' | 'regression' | 'not-evaluable';

/**
 * Read-only projection of the persisted content-v6 verdict. A regression of any
 * measurement dominates; a missing usable-board gain alone is no improvement.
 */
export function contentOutcome(report: ContentReport): ContentOutcome {
  if (report.verdict === 'NOT_EVALUABLE') return 'not-evaluable';
  if (report.verdict === 'PASS') return 'improvement';
  const regressed =
    report.games.some((game) =>
      game.reasons.some((reason) => reason.includes('_REGRESSED:')),
    ) ||
    report.contentEvaluation.some((game) =>
      Object.values(game.roles).some((role) => role.degradedInstances > 0),
    );
  return regressed ? 'regression' : 'no-improvement';
}

const outcomeLabels: Record<ContentOutcome, string> = {
  improvement:
    'Poprawa — kandydat spełnia bramkę zawartości bez nowych uszkodzeń.',
  'no-improvement':
    'Brak poprawy — nie wykryto pogorszenia, ale kandydat nie dał wymaganego zysku.',
  regression:
    'Pogorszenie — co najmniej jeden pomiar lub symbol jest gorszy niż w bazie.',
  'not-evaluable':
    'Nie da się ocenić — brakuje pełnych, aktualnych danych odniesienia.',
};

export function GridContentEvaluationSummary({
  report,
  games,
}: {
  readonly report: ContentReport;
  readonly games: readonly GameResponse[];
}) {
  return (
    <section aria-label="Ocena końcowych wycinków symboli">
      <h4>Zawartość końcowych wycinków: {report.verdict}</h4>
      <p>Wynik: {outcomeLabels[contentOutcome(report)]}</p>
      <p>
        To wynik rzeczywistych wycinków klasyfikatora. Kompletność wejścia sieci
        geometrii jest oceniana osobno. Szerszy podgląd zdjęcia nie zmienia
        żadnego z tych wejść.
      </p>
      {report.contentEvaluation.map((game) => (
        <section key={game.gameId}>
          <h5>
            {gameName(games, game.gameId)} —{' '}
            {game.state === 'ready'
              ? 'dostępny pomiar'
              : 'brak pełnego pomiaru'}
          </h5>
          {game.reasonCodes.length ? (
            <p>{game.reasonCodes.map(reasonLabel).join('; ')}</p>
          ) : null}
          <table>
            <caption>Pełna zawartość pól — baza i kandydat</caption>
            <thead>
              <tr>
                <th>Zakres</th>
                <th>Zdjęcia / pola</th>
                <th>Zachowane</th>
                <th>Graniczne</th>
                <th>Ucięte / brak</th>
                <th>Błędne pole / remis / obcy symbol</th>
                <th>Użyteczne plansze</th>
                <th>Nowe pogorszenia</th>
              </tr>
            </thead>
            <tbody>
              {(['VALIDATION', 'REGRESSION'] as const).map((role) => {
                const r = game.roles[role];
                return (
                  <tr key={role}>
                    <th>
                      {role === 'VALIDATION'
                        ? 'Wybór modelu'
                        : 'Końcowe zdjęcia testowe'}
                    </th>
                    <td>
                      {r.photos} / {r.slots} ({r.unknown} nieznanych)
                    </td>
                    <td>
                      {r.base.preserved} / {r.candidate.preserved}
                    </td>
                    <td>
                      {r.base.borderline} / {r.candidate.borderline}
                    </td>
                    <td>
                      {r.base.clipped}+{r.base.missing} / {r.candidate.clipped}+
                      {r.candidate.missing}
                    </td>
                    <td>
                      {r.base.wrongCells}/{r.base.ties}/{r.base.foreignSymbols}{' '}
                      → {r.candidate.wrongCells}/{r.candidate.ties}/
                      {r.candidate.foreignSymbols}
                    </td>
                    <td>
                      {r.base.usableBoards} / {r.candidate.usableBoards}
                    </td>
                    <td>
                      {r.degradedInstances};{' '}
                      {r.reasonCodes.map(reasonLabel).join('; ')}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p>
            Nowe błędy pojedynczych pól nie są kompensowane poprawą innych
            plansz.{' '}
            {game.freshRegression
              ? 'Zdjęcia końcowej kontroli pochodzą z zamrożonego świeżego wyboru.'
              : 'Brak dowodu świeżych zdjęć końcowej kontroli.'}
          </p>
          <details>
            <summary>
              Niepewność pomiaru i przypięte ustawienia wycinków
            </summary>
            <p>
              u: {game.u ?? 'nieustalone'}; δ: {game.delta ?? 'nieustalona'}.
            </p>
            <p>
              Pomiar: {game.measurementSha256 ?? 'brak'}. Ustawienia renderu:{' '}
              {game.renderConfigurationSha256s.join(', ') || 'brak'}.
              Klasyfikator:{' '}
              {game.classifierSnapshotSha256s.join(', ') || 'brak'}.
            </p>
          </details>
        </section>
      ))}
      <details>
        <summary>Historyczna ocena samej geometrii</summary>
        <p>
          Wynik: {report.rawQuality.verdict}. Nie zastępuje wyniku zawartości
          ani kwalifikacji automatu.
        </p>
      </details>
    </section>
  );
}
