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
  GRID_LEARNING_HISTORY_COHORT_UNVERIFIED:
    'Wybrana historyczna kohorta nie ma dowodu w publikacji bazy. Wybierz potwierdzoną kohortę tej gry.',
  GRID_LEARNING_HISTORY_BASE_MISMATCH:
    'Baza historycznej kohorty nie jest przodkiem modelu domyślnego. Przygotuj zgodną kohortę.',
  GRID_LEARNING_IMPORT_SCOPE_INVALID:
    'Wybierz od 1 do 100 importów z dostępnymi źródłami; większego zakresu system nie pomniejsza sam.',
  GRID_LEARNING_BASE_MISSING:
    'Nie znaleziono przypiętej wersji domyślnej. Przywróć jej wpis lub wybierz dostępną opublikowaną bazę.',
  GRID_LEARNING_BASE_UNPUBLISHED:
    'Baza nie ma potwierdzonej publikacji. Wybierz opublikowaną wersję domyślną.',
  GRID_LEARNING_RECOMMENDED_POINTS:
    'Ten cel uczy położenia siatki na zatwierdzonych planszach.',
  GRID_LEARNING_RECOMMENDED_DETECTOR:
    'Pełne dane pozwalają uczyć także wykrywania położenia plansz na zdjęciu.',
  GRID_LEARNING_PARTIAL_TRAIN_PRESENT:
    'Zbiór zawiera częściowo opisane zdjęcia. Uczenie punktów zachowuje także te pojedyncze korekty; detektor wymaga pełnych zdjęć.',
  GRID_CORRECTION_SPLIT_MINIMA:
    'Za mało zatwierdzonych plansz lub zdjęć do trzech osobnych ról. Uzupełnij braki pokazane w licznikach.',
  GRID_CORRECTION_SPLIT_INFEASIBLE:
    'Nie można zachować osobnych kontroli i buforów przy obecnych danych. Dodaj korekty na innych zdjęciach lub nowy import.',
  GRID_CORRECTION_SPLIT_WORK_LIMIT:
    'Podział przekroczył limit obliczeń. Nie wybrano mniejszego zbioru; zakres wymaga sprawdzenia.',
  GRID_LEARNING_HISTORY_STALE:
    'Ponownie używana kohorta ma nieaktualne etykiety. Przygotuj świeżą kohortę wymaganej gry.',
  GRID_LEARNING_HISTORY_UNAVAILABLE:
    'Brak dostępnej, zgodnej kohorty wymaganej innej gry. Sprawdź zakres i jej dane.',
  GRID_LEARNING_HISTORY_COHORT_REQUIRED:
    'Wymagana gra nie ma przypiętej kohorty do nowej oceny. Uzupełnij ją w szczegółach zakresu.',
  GRID_LEARNING_DEFAULT_REQUIRED:
    'Nie wybrano wspólnego modelu bazowego. Ustaw opublikowaną wersję domyślną.',
  GRID_LEARNING_BASE_UNAVAILABLE:
    'Pliki modelu bazowego są niedostępne. Przywróć je przed uczeniem.',
  GRID_LEARNING_TRAINING_ARTIFACTS_REQUIRED:
    'Baza nie ma wszystkich oryginalnych plików potrzebnych do doszkalania.',
  GRID_RUN_COHORT_COST_EXCEEDS_BUDGET:
    'Ten zakres przekracza budżet treningu. System nie zmniejszył zbioru ani nie zwiększył limitu.',
  GRID_COHORT_TIMEOUT:
    'Odczyt danych przekroczył limit czasu. Odśwież po zakończeniu bieżących zapisów; powtarzający się błąd wymaga diagnozy.',
  SOURCE_METADATA_MISSING:
    'Brakuje kanonicznej tożsamości części zdjęć. Uzupełnij metadane przed bezpiecznym podziałem.',
  SCREEN_FULL_PHOTOS_REQUIRED:
    'Do uczenia detektora potrzeba co najmniej 15 zdjęć z zatwierdzoną geometrią wszystkich dziewięciu plansz.',
  SCREEN_FULL_TRAIN_REQUIRED:
    'Detektor wymaga 10 pełnych zdjęć w TRAIN. Pojedyncze korekty mogą uczyć punkty siatki.',
  SCREEN_FULL_VALIDATION_REQUIRED:
    'Detektor wymaga 5 pełnych zdjęć walidacyjnych. Kontrole pozostają oddzielne od TRAIN.',
  SCREEN_PARTIAL_PHOTO_EXCLUDED:
    'Częściowe zdjęcie nie uczy detektora; jego nieopisane plansze nie są traktowane jako tło.',
  CONTENT_SEQUENCE_CONFLICT:
    'Bieżąca etykieta dotyczy innego numeru planszy. Plansza pozostaje nieoznaczona w tym odczycie; zamrożone etykiety są sprawdzane osobno.',
  CONTENT_SEQUENCE_UNRESOLVED:
    'Nie ustalono jednoznacznego numeru planszy. Cel pozostaje zablokowany.',
  CONTENT_FRAME_CONFLICT:
    'Bieżąca etykieta dotyczy innej ramy źródła. Jej pola są nierozstrzygnięte; nie zmienia to przypiętych etykiet.',
  CONTENT_ROLE_MEMBERSHIP_INCOMPLETE:
    'Część zdjęć lub plansz tej roli nie ma kompletnego przypisania.',
  CONTENT_LABELS_MISSING: 'Brak etykiet zawartości w tym zakresie.',
  CONTENT_UNKNOWN_LIMIT:
    'Zbyt wiele pól ma nieznaną zawartość, aby ocenić ten zakres.',
  CONTENT_REG_FULL_PHOTOS_MISSING:
    'Kontrola REG wymaga co najmniej pięciu pełnych opisanych zdjęć.',
  CONTENT_RENDER_REFERENCE_MISSING:
    'Brak przypiętych ustawień produkcyjnego wycinka.',
  CONTENT_MEASUREMENT_NOT_EVALUABLE:
    'Pomiar powtarzalności nie spełnia wymagań oceny.',
  CONTENT_MEASUREMENT_UNIQUE_REFERENCE_REQUIRED:
    'Brak jednego spójnego pomiaru powtarzalności dla gry.',
  CONTENT_UNCERTAINTY_MISSING: 'Nie ustalono niepewności niezależnego pomiaru.',
  CONTENT_REFERENCE_NOT_EVALUABLE:
    'Etykiety zawartości nie pozwalają na ocenę jakości.',
  CONTENT_FRESH_REGRESSION_REQUIRED: 'Brak wymaganej świeżej kontroli REG.',
  CONTENT_BANK_MEASUREMENT:
    'Pomiar banku błędów wyłącznie na dopuszczalnych zdjęciach TRAIN.',
  EXPERIMENT_ARM_FEASIBILITY:
    'Pomiar wykonalności wariantów w ograniczonym budżecie workera.',
  NEURAL_GRID_STATUS_STORAGE_UNAVAILABLE:
    'Odczyt kwalifikacji jest chwilowo niedostępny. Przypisanie modelu pozostaje zachowane; odśwież stan.',
  NEURAL_GRID_STATUS_DATA_UNAVAILABLE:
    'Dane kwalifikacji nie mogły zostać odczytane. Przypisanie pozostaje zachowane.',
  GRID_VALIDATION_PURPOSE_CONFLICT:
    'Wcześniejsze użycie chroni rolę lub przeznaczenie tych zdjęć. Zachowaj przydział rejestru.',
  GRID_VALIDATION_SELECTION_EXPOSED:
    'Te zdjęcia już wybierały ustawienia modelu. Mogą pozostać w A; nie mogą zostać niezależnym testem B ani buforem.',
  GRID_VALIDATION_DIAGNOSTIC_EXPOSED:
    'Te zdjęcia były użyte do diagnostyki. Nie mogą być niezależnym testem B ani kontrolą regresji.',
  GRID_VALIDATION_COMPONENT_CONFLICT:
    'Powiązane zdjęcia muszą mieć jedno wspólne przeznaczenie A, B albo bufor.',
  GRID_VALIDATION_ASSIGNMENT_INVALID:
    'Wybrane zdjęcia lub przeznaczenie nie pasują do tego podglądu. Odczytaj komponenty ponownie.',
  GRID_CORRECTION_PROTECTION_CONFLICT:
    'Rejestr zawiera sprzeczną lub nierozstrzygniętą ochronę zdjęć. Wymaga ona wyjaśnienia przed podziałem.',
  SCREEN_HISTORY_CORRECTION_POLICY_REQUIRED:
    'Historyczna kohorta nie ma zgodnego podziału kontroli. Przygotuj i zamroź nową kohortę z istniejących etykiet geometrii.',
  SCREEN_HISTORY_COHORT_REQUIRED:
    'Wymagana inna gra potrzebuje zgodnej zamrożonej kohorty pełnych zdjęć. Wybierz ją w szczegółach zakresu.',
  GRID_CORRECTION_CONTROL_NOT_PENDING:
    'Chronione zdjęcie kontrolne bez etykiet nie oczekuje na korektę',
  GRID_CORRECTION_BUFFER:
    'Zdjęcia buforowe oddzielają uczenie od danych kontrolnych',
  GRID_CORRECTION_PROTECTED_NEIGHBORHOOD:
    'Zdjęcia są zbyt blisko chronionych kontroli albo nie mają bezpiecznego przydziału',
  GRID_APPLY_ALREADY_DEFAULT:
    'Kandydat jest już wersją domyślną. Sprawdź historię i wznów zapisany przebieg, jeśli wymaga dokończenia.',
  GRID_APPLY_PUBLICATION_EVIDENCE_CONFLICT:
    'Kandydat ma publikację z innym dowodem. Zastosowanie z tego raportu jest zablokowane.',
  GRID_APPLY_BUSY:
    'Trwa już zastosowanie tego kandydata. Sprawdź postęp w historii.',
  GRID_MODEL_EVALUATION_SCOPE_STALE:
    'Wersja domyślna zmieniła się. Zakres starej oceny nie potwierdza nowej bazy — przygotuj nowy przebieg.',
  GRID_LEARNING_BUSY:
    'Trwa zapis kroku uczenia. Odczekaj chwilę i ponów polecenie.',
  GRID_LEARNING_CANCELLATION_PENDING:
    'Anulowanie trwa. Poczekaj na zatrzymanie treningu lub oceny, zanim wznowisz uczenie.',
  GPU_AVAILABLE: 'dostępność karty graficznej',
  RUNTIME_COMPATIBLE: 'zgodność środowiska treningu',
  VRAM_SUFFICIENT: 'dostępną pamięć karty graficznej',
  GPU_LEASE_FREE: 'dostępny slot karty graficznej',
  BUDGET_AVAILABLE: 'dostępny budżet przebiegu',
  'Session independence is not proven by photo-only evidence.':
    'Podział po zdjęciach nie potwierdza niezależności sesji.',
  'Unknown ancestor training use cannot be excluded.':
    'Nie można wykluczyć nieznanego użycia tych danych w uczeniu wcześniejszych modeli.',
  'Partial photos measure labelled targets only; unlabelled detections are not assessed.':
    'Częściowe zdjęcia oceniają tylko oznaczone plansze, bez oceny nieoznaczonych detekcji.',
  'Improvement thresholds are product gates, not statistical significance.':
    'Progi poprawy są warunkiem produktu; nie dowodzą istotności statystycznej.',
  GRID_APPLY_DEFAULT_CHANGED:
    'Wersja domyślna zmieniła się. Odśwież podgląd. Inna baza wymaga nowego przebiegu uczenia.',
  GRID_APPLY_PREVIEW_CHANGED:
    'Dane lub przypisania zmieniły się. Odśwież podgląd i ponownie potwierdź zakres.',
  GRID_APPLY_LIMITED_EVIDENCE_REQUIRED:
    'Potwierdź ograniczenie dowodu opartego na zdjęciach.',
  GRID_APPLY_LIMITATIONS_CONFIRMATION_REQUIRED:
    'Potwierdź ograniczenie dowodu opartego na zdjęciach.',
  GRID_APPLY_LEARNING_INCOMPLETE: 'Najpierw ukończ uczenie i ocenę kandydata.',
  GRID_APPLY_EVIDENCE_REQUIRED: 'Brak aktualnej zaliczonej oceny kandydata.',
  GRID_APPLY_SCOPE_INVALID: 'Zakres zastosowania jest nieprawidłowy.',
  GRID_APPLY_SCOPE_NOT_EVALUATED:
    'Wybrana gra nie ma zaliczonej oceny tego kandydata.',
  GRID_APPLY_IDEMPOTENCY_CONFLICT:
    'Klucz polecenia wskazuje inne zastosowanie.',
  GRID_APPLY_NOT_FOUND: 'Nie znaleziono przebiegu zastosowania.',
  GRID_APPLY_NOT_RESUMABLE: 'Ten przebieg nie może być teraz wznowiony.',
  GRID_APPLY_ASSIGNMENT_CHANGED:
    'Przypisana wersja gry zmieniła się. Odśwież podgląd.',
  GRID_APPLY_ASSIGNED_EVIDENCE_REQUIRED:
    'Brak aktualnego porównania z przypisaną wersją gry.',
  GRID_APPLY_ASSIGNED_NONREGRESSION_REQUIRED:
    'Kandydat nie zaliczył kontroli względem przypisanej wersji gry.',
  GRID_APPLY_COMPARISON_BLOCKED: 'Porównanie z przypisaną wersją wymaga uwagi.',
  GRID_APPLY_EVIDENCE_CHANGED:
    'Dowody oceny zmieniły się. Odśwież podgląd zastosowania.',
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
