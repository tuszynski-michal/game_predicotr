import type {
  AdminApiClient,
  GridModelEvaluationCurrentness,
  GridModelEvaluationMetrics,
  GridModelEvaluationView,
} from '@game-predictor/admin-api-client';

export type GridModelEvaluationClient = Pick<
  AdminApiClient,
  | 'listGridTrainingRuns'
  | 'listGames'
  | 'listGridModelVersions'
  | 'listGridTrainingCohorts'
  | 'createGridModelEvaluation'
  | 'listGridModelEvaluations'
  | 'getGridModelEvaluation'
  | 'verifyGridModelEvaluationCurrentness'
>;

export const evaluationVerdictLabels: Readonly<Record<string, string>> = {
  PASS: 'Poprawa gry treningowej bez regresji w pozostałych grach',
  REVISE: 'Kandydat wymaga poprawy',
  NOT_EVALUABLE: 'Nie można ocenić',
};

export const evaluationDecisionLabels: Readonly<Record<string, string>> = {
  pass: 'zaliczone',
  fail: 'niezaliczone',
  not_evaluable: 'brak oceny',
};

export const currentnessLabels: Readonly<Record<string, string>> = {
  current: 'Aktualny dowód',
  stale: 'Dowód nieaktualny — sprawdź aktualność',
  missing: 'Brak dowodu — sprawdź aktualność',
  unavailable: 'Gra niedostępna lub usunięta — model zablokowany',
};

/** Rows of the comparison table; ``better`` says which direction improves. */
export const comparisonMetrics: readonly {
  readonly key: keyof GridModelEvaluationMetrics;
  readonly label: string;
  readonly better: 'higher' | 'lower' | null;
}[] = [
  { key: 'photos', label: 'Zdjęcia', better: null },
  {
    key: 'photo_complete_correct',
    label: 'Zdjęcia kompletne i poprawne',
    better: 'higher',
  },
  { key: 'boards_expected', label: 'Plansze oczekiwane', better: null },
  { key: 'boards_matched', label: 'Plansze wykryte', better: 'higher' },
  { key: 'boards_correct', label: 'Plansze poprawne', better: 'higher' },
  { key: 'false_boards', label: 'Fałszywe plansze', better: 'lower' },
  {
    key: 'duplicate_predictions',
    label: 'Zdublowane detekcje',
    better: 'lower',
  },
  { key: 'image_macro', label: 'Błąd image-macro', better: 'lower' },
  { key: 'nme_p95', label: 'NME p95', better: 'lower' },
];

export type MetricChange = 'better' | 'worse' | 'same' | 'info';

export function metricChange(
  base: GridModelEvaluationMetrics,
  candidate: GridModelEvaluationMetrics,
  key: keyof GridModelEvaluationMetrics,
  better: 'higher' | 'lower' | null,
): MetricChange {
  if (better === null) return 'info';
  // An unknown quality is never a zero error: a missing value costs the maximum.
  const value = (metrics: GridModelEvaluationMetrics) =>
    metrics[key] ?? (key === 'image_macro' ? 1 : Number.NaN);
  const left = value(base),
    right = value(candidate);
  if (Number.isNaN(left) || Number.isNaN(right)) return 'info';
  const difference = better === 'higher' ? right - left : left - right;
  if (Math.abs(difference) <= 1e-9) return 'same';
  return difference > 0 ? 'better' : 'worse';
}

export function formatMetric(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return Number.isInteger(value) ? String(value) : value.toFixed(4);
}

export interface PendingEvaluationCommand {
  readonly key: string;
  readonly signature: string;
}

/** Reuse the idempotency key only for a retry of exactly the same command. */
export function evaluationCommand(
  previous: PendingEvaluationCommand | null,
  body: {
    readonly versionId: string;
    readonly cohorts: readonly { gameId: string; cohortId: string }[];
  },
  newKey: () => string,
): PendingEvaluationCommand {
  const signature = JSON.stringify({
    versionId: body.versionId,
    cohorts: [...body.cohorts]
      .map((entry) => `${entry.gameId}:${entry.cohortId}`)
      .sort(),
  });
  return previous?.signature === signature
    ? previous
    : { key: newKey(), signature };
}

export function needsCurrentnessCheck(
  states: readonly GridModelEvaluationCurrentness[],
): boolean {
  return states.some((state) => state.state !== 'current');
}

export function evaluationFinished(view: GridModelEvaluationView): boolean {
  return ['completed', 'failed', 'cancelled'].includes(view.status);
}
