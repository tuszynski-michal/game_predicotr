# TASK-0047 — Import integrity and duplicate reports

## Status

`done`

## Goal

Udostępnić deterministyczny raport integralności dla zakończonego stagingu
walidacji importu layoutów, bez tworzenia ani publikowania datasetu.

## Scope

- dokładne statystyki poprawnych i błędnych wierszy,
- wykrywanie luk w ciągu `sequence_number` liczonym od `1`,
- wykrywanie duplikatów `sequence_number`,
- raportowanie dozwolonych duplikatów sygnatur layoutów,
- jawna ocena gotowości stagingu do przyszłej publikacji,
- ograniczone, deterministyczne próbki luk i duplikatów,
- stronicowany odczyt znormalizowanych wierszy do przyszłego podglądu i
  filtrowania błędów w panelu administratora,
- Admin API i kontrakt OpenAPI dla raportu oraz listy wierszy.

## Out of scope

- publikowanie datasetu,
- odrzucanie lub usuwanie stagingu,
- interfejs użytkownika panelu administratora,
- zmiana zawartości znormalizowanych wierszy,
- fizyczna walidacja M3/G3.

## Assumptions and decisions

- Raport można utworzyć wyłącznie dla zakończonego zadania walidacji importu
  layoutów.
- Integralność numeracji jest liczona wyłącznie na poprawnych,
  znormalizowanych wierszach. Wiersz błędny blokuje gotowość publikacji i nie
  wypełnia luki w przyszłym zbiorze poprawnych layoutów.
- Oczekiwany ciąg numerów zaczyna się od `1` i kończy na największym poprawnym
  `sequence_number`.
- Brak poprawnych layoutów, dowolny błędny wiersz, luka albo duplikat numeru
  sekwencji blokują gotowość do publikacji.
- Duplikat sygnatury layoutu jest raportowany jako ostrzeżenie i nie blokuje
  gotowości do publikacji.
- Liczniki są dokładne. Próbki służą tylko prezentacji i mają jawny znacznik
  obcięcia.
- Obliczenia raportu korzystają z agregacji SQL i ograniczonych próbek, aby nie
  ładować całego importu do pamięci procesu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/README.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/MANUAL_DATA_IMPORT.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/delivery/MILESTONE_04_EXECUTION_PLAN.md`

## Acceptance criteria

- Raport podaje dokładne liczniki wierszy poprawnych i błędnych.
- Raport wykrywa luki od `1` do największego poprawnego numeru sekwencji.
- Raport wykrywa zduplikowane numery sekwencji i traktuje je jako błąd
  blokujący.
- Raport wykrywa zduplikowane sygnatury, ale traktuje je jako dozwolone
  ostrzeżenie.
- Raport ma deterministyczną kolejność i jawnie oznacza obcięte próbki.
- Raport nie powstaje dla trwającego, nieudanego ani niewłaściwego typu zadania.
- API pozwala stronicować wiersze według `line_number` oraz filtrować je po
  statusie i kodzie błędu.
- Implementacja ma testy jednostkowe i testy integracyjne PostgreSQL.

## Verification

```powershell
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'
.\.venv\Scripts\python.exe -m pytest --basetemp .tmp/pytest-task0047-full -q
.\.venv\Scripts\python.exe -m ruff check services/api services/worker scripts
.\.venv\Scripts\python.exe -m mypy services/api/src services/worker/src scripts
.\.venv\Scripts\python.exe scripts/export_admin_openapi.py --check
node packages/admin-api-client/scripts/check-generated-client.mjs
tsc --noEmit -p packages/admin-api-client/tsconfig.json
tsc --noEmit -p apps/admin/tsconfig.json
tsx --test packages/admin-api-client/test/*.test.mjs
next build
git diff --check
```

## Outcome

Zadanie ukończono. Backendowa część M4.3 jest gotowa do wykorzystania przez
panel w TASK-0048.

### Changed

- Dodano czyste kontrakty raportu, stabilne checki
  `NORMALIZED_ROW_COUNT_MISMATCH`, `NO_VALID_IMPORT_ROWS`,
  `INVALID_IMPORT_ROW`, `MISSING_SEQUENCE_NUMBER`,
  `DUPLICATE_SEQUENCE_NUMBER` i `DUPLICATE_SIGNATURE`.
- Dodano repozytorium PostgreSQL liczące dokładne agregaty oraz bounded,
  deterministyczne próbki bez materializacji pełnego stagingu w procesie API.
- Luki są liczone na poprawnych dodatnich numerach od `1`; błędny wiersz
  pozostaje blokadą i nie wypełnia pozycji przyszłego datasetu.
- Dodano endpoint raportu integralności oraz keysetową listę znormalizowanych
  wierszy z filtrami statusu i kodu błędu.
- Zregenerowano OpenAPI i klient TypeScript oraz dodano metody fasady klienta
  dla przyszłego panelu.
- Nie dodano migracji ani cache raportu; źródłem pozostaje istniejący,
  zakończony staging TASK-0046.

### Verification results

- `346 passed, 1 skipped` w pełnym zestawie Python z włączonymi 11 testami
  integracyjnymi PostgreSQL. Skip dotyczy braku uprawnienia Windows do
  utworzenia symlinka.
- Ruff: wszystkie moduły API, workera i skrypty przeszły.
- mypy: `Success` dla 109 plików źródłowych.
- OpenAPI i generowany klient: aktualne, bez driftu.
- Klient TypeScript: build/typecheck oraz `12 passed`.
- Panel: TypeScript typecheck i produkcyjny build Next.js przeszły.

### Not completed

- Nie dodano UI raportu, odrzucania stagingu ani publikacji datasetu; należą do
  TASK-0048–TASK-0050.
- Nie wykonywano Android builda ani dowodów urządzeniowych G3; pozostają
  odroczone zgodnie z D-041.

### Documentation updates

- Zaktualizowano wymagania importu, architekturę systemu, model danych, API,
  strategię testów, plan M4 i `CURRENT_STATE.md`.
- Dodano zaakceptowaną decyzję D-046.

### Recommended next task

- `TASK-0048 — Manual import administration UI`.
