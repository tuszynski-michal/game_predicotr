import type {
  GameResponse,
  GridCohortHeader,
  GridModelEvaluationView,
  GridModelManifest,
  GridModelVersionResponse,
  GridTrainingRunView,
} from '@game-predictor/admin-api-client';

/** TASK-1000: readable reasons; an unknown code is never hidden, only labelled. */
export const REASON_LABELS: Readonly<Record<string, string>> = {
  GRID_MODEL_ELIGIBLE: 'Wersja może być użyta',
  GRID_MODEL_ARTIFACT_AVAILABLE: 'Pliki modelu są dostępne',
  GRID_MODEL_NOT_PUBLISHED: 'Wersja nie jest opublikowana',
  GRID_MODEL_EVALUATION_REQUIRED:
    'Brak zaliczonej oceny albo aktualnego dowodu dla każdej gry',
  GRID_MODEL_EVALUATION_STALE:
    'Dowód oceny jest nieaktualny — sprawdź aktualność',
  GRID_MODEL_PUBLICATION_STALE: 'Dowód publikacji nie zgadza się z wersją',
  GRID_MODEL_ARTIFACT_UNAVAILABLE: 'Pliki modelu są niedostępne',
  GRID_MODEL_ARTIFACT_MISSING: 'Brakuje plików modelu',
  GRID_MODEL_TRAINING_ARTIFACT_MISSING: 'Brakuje plików bazy treningu',
  GRID_MODEL_TRAINING_RECEIPT_INVALID:
    'Potwierdzenie bazy treningu jest niezgodne',
  GRID_MODEL_STORE_UNCONFIGURED: 'Magazyn modeli nie jest skonfigurowany',
  GRID_MODEL_PATH_INVALID: 'Ścieżka modelu jest nieprawidłowa',
  GRID_MODEL_CONTRACT_UNSUPPORTED: 'Nieobsługiwany kontrakt modelu',
  GRID_MODEL_DEFAULT_REQUIRED: 'Brak domyślnej wersji geometrii',
  GRID_MODEL_GAME_INCOMPATIBLE: 'Gra nie może używać tej wersji',
  GRID_MODEL_ROLLBACK_TARGET_INVALID: 'Tej wersji nie było wcześniej w grze',
  GRID_MODEL_REVISION_CONFLICT: 'Stan zmienił się w międzyczasie — odśwież',
  GRID_MODEL_IDEMPOTENCY_CONFLICT: 'Klucz polecenia użyto dla innej treści',
  GRID_MODEL_HISTORICAL_BASE_INVALID:
    'Historyczna baza nie dostaje nowej oceny',
  GRID_MODEL_REGISTRY_CORRUPT: 'Zapis katalogu modeli jest niespójny',
  GRID_RUN_COHORT_NOT_FROZEN: 'Kohorta nie jest zamrożona',
  GRID_RUN_COHORT_NOT_QUALIFIED: 'Kohorta nie kwalifikuje się do treningu',
  GRID_RUN_PRESET_NOT_APPROVED: 'Brak zatwierdzonego presetu dla trybu',
  GRID_RUN_COHORT_EMPTY: 'Kohorta nie ma danych TRAIN',
  GRID_RUN_COHORT_COST_EXCEEDS_BUDGET: 'Koszt przekracza budżet runu',
  GRID_RUN_LEASE_BUSY: 'GPU jest zajęte — run poczeka w kolejce',
  GRID_RUN_LEASE_UNKNOWN: 'Stan GPU jest nieustalony — run poczeka w kolejce',
  GRID_RUN_NOT_FOUND: 'Nie znaleziono runu',
  GRID_RUN_NOT_RESUMABLE: 'Wznowić można tylko run przerwany lub z błędem',
  GRID_RUN_IDEMPOTENCY_CONFLICT: 'Klucz runu użyto dla innej treści',
  GRID_RUN_GPU_UNAVAILABLE: 'Brak dostępnego GPU',
  GRID_TRAINING_COHORT_DRIFT: 'Kohorta zmieniła się od zlecenia runu',
  GRID_TRAINING_CHECKPOINT_CORRUPT: 'Wskazany checkpoint jest uszkodzony',
  GRID_TRAINING_FAILED: 'Trening zakończył się bez kandydata',
  GRID_SHARED_SCOPE_INVALID: 'Wybierz po jednej kohorcie w innych grach',
  GRID_SHARED_COHORT_MISMATCH:
    'Kohorty muszą mieć tę samą rodzinę, bazę i tryb',
  GRID_SHARED_COHORT_EMPTY_ROLE: 'Każda kohorta potrzebuje TRAIN i VALIDATION',
  GRID_SHARED_ROLE_CONFLICT: 'Nagranie ma różne role w kohortach',
  GRID_SHARED_CONTROL_ALIAS:
    'Zdjęcie kontrolne jednej gry byłoby treningowym w drugiej',
  GRID_SHARED_PLAN_DRIFT: 'Plan wspólnego treningu zmienił się',
  GRID_SHARED_UNAVAILABLE: 'Wspólny trening nie jest skonfigurowany',
  GRID_EVALUATION_GAME_COHORT_REQUIRED:
    'Ocena musi objąć kohortę każdej wymaganej gry',
  GRID_EVALUATION_COHORT_BASE_MISMATCH:
    'Kohorta ma inną rodzinę lub bazę niż kandydat',
  GRID_EVALUATION_CANDIDATE_UNAVAILABLE: 'Kandydat lub baza są niedostępne',
  GRID_EVALUATION_SCOPE_INVALID: 'Wybierz jedną kohortę na grę',
  GRID_EVALUATION_IDEMPOTENCY_CONFLICT: 'Klucz oceny użyto dla innej treści',
  GRID_EVALUATION_GAME_UNAVAILABLE: 'Magazyn gry jest nieaktywny',
  GRID_EVALUATION_COHORT_CHANGED: 'Kohorta zmieniła się od oceny',
  GRID_EVALUATION_DETAIL_CHANGED: 'Plik wyników oceny zmienił się',
  GRID_COHORT_LABEL_STALE: 'Etykieta człowieka zmieniła się lub wycofano ją',
  GRID_COHORT_LABEL_UNRESOLVED: 'Zdjęcie nie ma potwierdzonej etykiety',
  GRID_COHORT_SOURCE_CHANGED: 'Zdjęcie źródłowe zmieniło się',
  GRID_COHORT_MINIMUM_NOT_MET: 'Za mało danych w którejś roli',
  GRID_COHORT_DEPENDENCY_UNRESOLVED:
    'Nie udało się odczytać zależności kohorty',
  GRID_COHORT_TIMEOUT: 'Polecenie przekroczyło limit czasu',
  COHORT_NOT_FROZEN: 'Kohorta nie jest zamrożona',
  COHORT_NO_USED_TARGETS: 'Kohorta nie ma użytych etykiet',
  SOURCE_REMOVED_NEW_USE_BLOCKED: 'Usunięte zdjęcie blokuje nowe użycie',
  SOURCE_RETENTION_POLICY_PENDING:
    'Polityka przechowywania kopii czeka na decyzję',
  SOURCE_GEOMETRY_IDENTITY_UNRESOLVED:
    'Nie potwierdzono tożsamości geometrii zdjęcia',
  RECORDING_ROLE_REQUIRED: 'Nagranie nie ma przypisanej roli',
  RECORDING_MEMBERSHIP_REQUIRED: 'Zdjęcie nie należy do wybranego nagrania',
  RECORDING_MEMBERSHIP_AMBIGUOUS: 'Zdjęcie należy do kilku nagrań',
  RECORDING_SELECTION_REQUIRED: 'Wybierz nagrania z rolami',
  RECORDING_ROLE_CONFLICT: 'Role powiązanych nagrań są sprzeczne',
  RECORDING_PROTECTED: 'Nagranie podlega ochronie danych kontrolnych',
  RECORDING_COHORT_PROOF_STALE: 'Dowód nagrania zmienił się',
  RECORDING_BINDING_INVALID: 'Powiązanie z nagraniem jest niezgodne',
  CAPTURE_REQUIRED: 'Zdjęcie czeka na odczyt metadanych',
};

const METRIC_LABELS: Readonly<Record<string, string>> = {
  photo_complete_correct: 'zdjęcia kompletne i poprawne',
  boards_correct: 'plansze poprawne',
  boards_matched: 'plansze wykryte',
  false_boards: 'fałszywe plansze',
  duplicate_predictions: 'zdublowane detekcje',
  image_macro: 'błąd image-macro',
};

export function reasonLabel(code: string | null | undefined): string {
  if (!code) return '';
  const known = REASON_LABELS[code];
  if (known) return known;
  // Per-game evaluation reasons of grid-model-per-game-gate-v1 (D-559).
  const [head, detail = ''] = code.split(':', 2);
  const metric = METRIC_LABELS[detail] ?? detail;
  const pattern: Record<string, string> = {
    VALIDATION_REGRESSED: `Pogorszenie na VALIDATION: ${metric}`,
    REGRESSION_REGRESSED: `Pogorszenie na REGRESSION: ${metric}`,
    VALIDATION_NOT_IMPROVED: `Brak poprawy gry treningowej: ${metric}`,
    COVERAGE_PHOTOS_BELOW_MINIMUM: `Za mało zdjęć kontrolnych: ${detail}`,
    COVERAGE_INCOMPLETE: `Nie oceniono wszystkich zdjęć: ${detail}`,
    CANDIDATE_PARITY_FAILED: 'Eksport kandydata nie przeszedł parity',
  };
  return pattern[head] ?? `Inny powód (${code})`;
}

export function reasonList(
  codes: readonly string[] | null | undefined,
): string {
  return (codes ?? []).map(reasonLabel).join('; ');
}

export const MODE_LABELS: Readonly<Record<string, string>> = {
  'grid-only': 'tylko siatki',
  'screen+grid': 'ekran i siatki',
};

export const RUN_STATUS_LABELS: Readonly<Record<string, string>> = {
  created: 'w kolejce',
  processing: 'w toku',
  waiting_for_review: 'czeka na przegląd',
  completed: 'ukończony',
  failed: 'błąd',
  cancelled: 'anulowany',
};

export const COHORT_STATUS_LABELS: Readonly<Record<string, string>> = {
  preparing: 'przygotowanie',
  preview_ready: 'podgląd gotowy',
  materializing: 'kopiowanie',
  ready_to_freeze: 'gotowa do zamrożenia',
  frozen: 'zamrożona',
  failed: 'błąd',
  canceled: 'anulowana',
};

export function shortDate(value: string | null | undefined): string {
  if (!value) return 'data nieustalona';
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? 'data nieustalona'
    : date.toLocaleString('pl-PL', { dateStyle: 'short', timeStyle: 'short' });
}

export function versionLabel(manifest: GridModelManifest): string {
  return `${manifest.familyLabel} · ${manifest.version}`;
}

export function versionName(
  versions: readonly GridModelVersionResponse[],
  versionId: string | null | undefined,
): string {
  if (!versionId) return 'brak';
  const found = versions.find((item) => item.manifest.versionId === versionId);
  return found ? versionLabel(found.manifest) : 'wersja spoza katalogu';
}

export function cohortLabel(header: GridCohortHeader): string {
  return `Kohorta z ${shortDate(header.createdAt)} · ${MODE_LABELS[header.mode] ?? header.mode} · ${COHORT_STATUS_LABELS[header.status] ?? header.status}`;
}

export function runLabel(
  run: GridTrainingRunView,
  versions: readonly GridModelVersionResponse[],
): string {
  const shared = run.sharedCohorts?.length
    ? ` · wspólny z ${run.sharedCohorts.length} grą/grami`
    : '';
  const candidate = run.candidateVersionId
    ? ` · kandydat ${versionName(versions, run.candidateVersionId)}`
    : '';
  return `Trening z ${shortDate(run.createdAt)} · ${MODE_LABELS[run.mode] ?? run.mode} · ${RUN_STATUS_LABELS[run.status] ?? run.status}${shared}${candidate}`;
}

export function gameLabel(game: Pick<GameResponse, 'name' | 'code'>): string {
  return `${game.name} (${game.code})`;
}

export function gameName(
  games: readonly Pick<GameResponse, 'id' | 'name' | 'code'>[],
  gameId: string,
): string {
  const found = games.find((game) => game.id === gameId);
  return found ? gameLabel(found) : 'gra spoza katalogu';
}

/** Publication is offered only for a measured PASS whose every cohort proof is current. */
export function publishBlocker(
  view: GridModelEvaluationView | null,
): string | null {
  if (!view) return 'Wybierz ocenę kandydata';
  if (!view.report) return 'Ocena nie ma jeszcze raportu';
  if (view.report.verdict !== 'PASS')
    return view.report.verdict === 'REVISE'
      ? 'Kandydat wymaga poprawy — regresja albo brak poprawy'
      : 'Nie można ocenić — brak danych lub parity';
  if (view.currentness.some((state) => state.state !== 'current'))
    return reasonLabel('GRID_MODEL_EVALUATION_STALE');
  return null;
}

export interface PendingModelCommand {
  readonly kind: 'run' | 'publish' | 'activate' | 'set_default' | 'rollback';
  readonly target: string;
  readonly body: Readonly<Record<string, unknown>>;
}

export function modelCommandKey(
  api: string,
  game: string,
  scope: string,
): string {
  return `game-predictor:grid-model:${scope}:${api}:${game}`;
}

export function readModelCommand(
  storage: Pick<Storage, 'getItem'>,
  key: string,
): PendingModelCommand | null {
  const raw = storage.getItem(key);
  if (raw === null) return null;
  const value = JSON.parse(raw) as PendingModelCommand;
  if (
    !value ||
    typeof value !== 'object' ||
    typeof value.kind !== 'string' ||
    typeof value.target !== 'string' ||
    typeof value.body !== 'object' ||
    typeof value.body.idempotencyKey !== 'string'
  )
    throw new Error('Zapisane polecenie jest nieczytelne.');
  return value;
}

export function saveModelCommand(
  storage: Pick<Storage, 'setItem'>,
  key: string,
  command: PendingModelCommand,
): void {
  storage.setItem(key, JSON.stringify(command));
}

export function clearModelCommand(
  storage: Pick<Storage, 'getItem' | 'removeItem'>,
  key: string,
  idempotencyKey: string,
): void {
  const current = readModelCommand(storage, key);
  if (current?.body.idempotencyKey === idempotencyKey) storage.removeItem(key);
}

/**
 * The backend answered and refused the command (4xx): retrying the same key cannot
 * change the answer. A thrown request or a 5xx stays unconfirmed and keeps the command.
 */
export function answeredRefusal(result: {
  readonly response?: { readonly status: number } | null;
}): boolean {
  const status = result.response?.status ?? 0;
  return status >= 400 && status < 500;
}

const PAGE_LIMIT = 50;

// Largest page each list endpoint accepts (OpenAPI `maximum`; a test keeps them in sync).
export const COHORT_PAGE_LIMIT = 50;
export const RECORDING_PAGE_LIMIT = 100;

/** Reads every page of a cursor list; any failed page fails the whole read. */
export async function readAllPages<T>(
  read: (cursor: string | undefined) => Promise<{
    readonly data?: {
      readonly items: readonly T[];
      readonly nextCursor?: string | null;
    };
  }>,
): Promise<T[] | undefined> {
  const items: T[] = [];
  let cursor: string | undefined;
  for (let page = 0; page < PAGE_LIMIT; page += 1) {
    const result = await read(cursor);
    if (!result.data) return undefined;
    items.push(...result.data.items);
    if (!result.data.nextCursor) return items;
    cursor = result.data.nextCursor;
  }
  throw new Error('Lista ma więcej stron, niż panel może odczytać.');
}
