import type {
  GridCorrectionLearningStartCommand,
  GridCorrectionLearningView,
  GridModelAssignmentCommand,
} from '@game-predictor/admin-api-client';

export type LearningCommand =
  | {
      kind: 'start';
      key: string;
      target: string;
      body: GridCorrectionLearningStartCommand;
    }
  | { kind: 'cancel'; key: string; target: string }
  | { kind: 'resume'; key: string; target: string }
  | {
      kind: 'rollback';
      key: string;
      target: string;
      body: GridModelAssignmentCommand;
    };

export function learningCommandKey(api: string, game: string): string {
  return `game-predictor:grid-correction-learning:${api}:${game}`;
}

export function readLearningCommand(
  storage: Pick<Storage, 'getItem'>,
  key: string,
): LearningCommand | null {
  const raw = storage.getItem(key);
  if (raw === null) return null;
  const value: unknown = JSON.parse(raw);
  if (
    !value ||
    typeof value !== 'object' ||
    !('kind' in value) ||
    !['start', 'cancel', 'resume', 'rollback'].includes(String(value.kind)) ||
    !('key' in value) ||
    typeof value.key !== 'string' ||
    !('target' in value) ||
    typeof value.target !== 'string'
  )
    throw new Error(
      'Zapisane polecenie jest nieczytelne. Zachowaj je przed ponowieniem.',
    );
  if (
    (value.kind === 'start' || value.kind === 'rollback') &&
    (!('body' in value) ||
      !value.body ||
      typeof value.body !== 'object' ||
      !('idempotencyKey' in value.body) ||
      value.body.idempotencyKey !== value.key)
  )
    throw new Error(
      'Zapisane polecenie ma niezgodny klucz. Zachowaj je przed ponowieniem.',
    );
  return value as LearningCommand;
}

export function clearLearningCommand(
  storage: Pick<Storage, 'getItem' | 'removeItem'>,
  key: string,
  commandKey: string,
): void {
  if (readLearningCommand(storage, key)?.key === commandKey)
    storage.removeItem(key);
}

export function archiveLearningCommand(
  storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>,
  key: string,
): void {
  const raw = storage.getItem(key);
  if (raw !== null)
    storage.setItem(`${key}:archive:${crypto.randomUUID()}`, raw);
  storage.removeItem(key);
}

export const learningStatus: Readonly<Record<string, string>> = {
  created: 'W kolejce',
  processing: 'W toku',
  waiting_for_review: 'Wymaga uwagi',
  completed: 'Ukończono',
  failed: 'Błąd',
  cancelled: 'Anulowano',
};

export const learningRole: Readonly<Record<string, string>> = {
  TRAIN: 'Uczenie',
  VALIDATION: 'Dobór modelu',
  REGRESSION: 'Kontrola końcowa',
};

export function learningActive(status: string): boolean {
  return status === 'created' || status === 'processing';
}

export function preparationStageLabel(stage: string): string {
  return (
    (
      {
        queued: 'Oczekiwanie na workera',
        preparing_data: 'Przygotowanie danych',
        source_inventory: 'Sprawdzanie listy zdjęć',
        recording_context: 'Sprawdzanie historii i podziału nagrań',
        geometry_evidence: 'Weryfikacja zapisanych korekt',
        data_prepared: 'Podział przygotowany',
        cohort_capture: 'Utrwalanie dowodów korekt',
        cohort_materialization: 'Przygotowanie zdjęć do treningu',
        freeze_inputs: 'Zabezpieczanie wejść kohorty',
        freeze_members: 'Końcowa kontrola aktualności danych',
      } as Record<string, string>
    )[stage] ?? 'Przygotowanie danych'
  );
}

export function learningStage(view: GridCorrectionLearningView): string {
  if (view.verdict) return 'Ocena ukończona';
  if (view.evaluationId) return 'Porównanie kandydata z bazą';
  if (view.trainingRunId)
    return view.contentExperiment
      ? 'Kontrolowany eksperyment pełnych symboli'
      : 'Trening modelu';
  if (view.cohortId) return 'Przygotowanie i sprawdzenie danych';
  if (view.preparation)
    return preparationStageLabel(view.stage ?? view.preparation.stage);
  return 'Sprawdzanie gotowości';
}
