# TASK-1121 — implementacja i kontrole przed audytem

Data: 2026-11-02. Worktree: `D:/game_predicotr/worktrees/grid-corrections-learning`.
Wykonawca: gpt-6-astra/high; pomocnik tego samego modelu: czyste metrics/gate,
schemas/router i assigned-report reader. Jeden wspólny audyt T2 wykonuje root.

## Wyniki

### Jedna runda poprawek audytu R1

Raporty audytora R1 pozostawiono bez zmian. Nie uruchomiono dodatkowego audytu ani
commita; focused R2 prowadzi root. Dyspozycja wszystkich findings:

- P1-1: `GridModelPublicationService.execute` przekazuje kontekst set_default do
  już zweryfikowanego readera dowodu. Przy scoped wymagany bieżący head równy bazie
  kandydata albo samemu kandydatowi. Sprawdzenie następuje pod istniejącym registry
  lock, po replay i CAS. Błąd `GRID_MODEL_EVALUATION_SCOPE_STALE` ma status409.
  Nie zmieniono canonical evidence zapisanych publikacji ani legacy.
- P1-2: nowy `test_grid_model_publication_scoped.py` wykonuje rzeczywiste control
  execute i zapis SQLite, prawdziwy parser raportu v3 i artifact inspector fixture.
  Publish przechodzi z niebadaną grą rodziny, ale odrzuca stale/missing/unavailable
  currentness; set_default przyjmuje właściwą bazę i ponowienie head, odrzuca zmianę
  bazy przy poprawnej nowej rewizji oraz odtwarza receipt po kolejnej zmianie head;
  activate przyjmuje grę ze scope i odrzuca inną. Nie jest to pomiar jakości modelu.
- P2-1: ten sam scoped strict mypy z tymczasowym wyjątkiem torch.* uruchomiono
  również dla `main.py` i `cli.py`: 2 pliki PASS. Pełny project gate pozostaje T4.
- P2-2: wspólne `has_full_geometry` w adapterze datasetu wymaga kwalifikacji i
  wszystkich dziewięciu pozycji. Dataset, checkpoint evaluator i końcowy evaluator
  używają tej samej definicji. Pipeline test obejmuje screenEligible=True z trzema
  targets; źródło pozostaje partial i nie deklaruje FP/complete, bez ValueError.
- P2-3: SQLSTATE55P03 przy step lock mapuje się na GRID_LEARNING_BUSY/409; inne
  błędy bazy nie są ukrywane. Test PG trzyma rzeczywisty lock w osobnej transakcji,
  wywołuje cancel i sprawdza stabilny błąd po pięciu sekundach oraz rollback.
- P2-4: resume najpierw sprawdza wszystkie dzieci pod lockiem. Aktywne dziecko
  z cancel_requested daje GRID_LEARNING_CANCELLATION_PENDING/409 bez mutacji.
  Test PG następnie potwierdza anulowanie checkpointem i sprawdza jeden skuteczny
  resume tych samych ID, bez nowego budżetu/child i bez drugiego wymaganego resume.
- P2-5: walidatory HTTP preview/start/create-evaluation sortują exclusions po
  gameId i odrzucają duplikaty. Test request porównuje obie kolejności, identyczny
  previewSha256 oraz kanoniczne komendy przekazane do wszystkich trzech serwisów.
- P2-6: status taska i CURRENT_STATE: in_progress, poprawki R1 gotowe do R2.
  Usunięto nieaktualny opis trwającego limitu/heartbeat; historia infrastruktury
  pozostała w oddzielnym AUDIT_BLOCKED. Nie zmieniono raportów audytora.

Wyniki rundy: 38 PASS (29.59 s): `test_grid_correction_learning_postgres.py`,
`test_grid_model_publication_scoped.py`, `test_grid_correction_learning_api.py`.
Pierwszy zestaw dodatkowo potwierdził 24 legacy control tests i 3 worker pipeline
tests PASS; dwie porażki nowych fixtures poprawiono (rejestracja drugiego historycznego
baseline i oczekiwany stabilny błąd poza scope), a sześć scoped tests jest w 38 PASS.
Każdy pytest był opakowany `subprocess.run(..., timeout=110)`; nowe PG używało
`GAME_PREDICTOR_RUN_POSTGRES_TESTS=1` oraz basetemp `D:/game_predicotr/artifacts/t1121-r1-final`.
Końcowy zestaw `test_grid_model_publication_scoped.py` + `test_grid_cohort_dataset.py`:
24 PASS (10.58 s), także nowy przypadek braku current default. Ruff format/check
11 plików PASS; scoped mypy 7 modułów produkcyjnych PASS oraz osobno main/cli2 PASS,
z tym samym udokumentowanym wyjątkiem wnętrza torch.*. OpenAPI artifact current,
code-map zregenerowany, docs:check PASS (startup44148/45000 B; CURRENT_STATE15351 B),
git diff --check PASS. Schemat JSON się nie zmienił, więc ponowna generacja SDK
nie była potrzebna. Dokładne ścieżki rundy: `artifacts/task1121-r1-fix-paths.txt`.
Oczekiwany R2 obejmuje zamknięcie P1-1/P1-2 i wpływ tych poprawek P2, nie cały
poprzedni zakres75plików. R1 z sufiksem `_R1` pozostaje niezmienionym kontekstem.

Uzupełnienie `dataAvailability` przed audytem: 58 PASS (9.45 s), solver, adapter,
workflow/preview i żądania HTTP. Liczby deduplikowane także dla MINIMA/INFEASIBLE;
przy sukcesie obejmują kwalifikujące buforowe zdjęcia przed odjęciem buforów.
Test potwierdza jeden odczyt populacji i brak podwójnego liczenia kopii. `null`
oznacza brak pomiaru; zerowe deficyty nie znoszą ograniczeń ochrony i podziału.
Zmiana nie modyfikuje persisted split/SHA ani polityki/algorytmu przydziału.
Kontrole uzupełnienia: Ruff siedmiu zmienionych plików PASS; scoped mypy czterech
modułów produkcyjnych PASS (ten sam tymczasowy wyjątek torch.*); TypeScript klienta
PASS; dwa testy wrappera PASS; OpenAPI i generated-client drift checks PASS.
docs:check PASS: startup44177/45000 B, CURRENT_STATE15380 B. Code-map zregenerowany.
Testy: `pytest -q --tb=short services/api/tests/test_grid_correction_split.py
services/api/tests/test_grid_correction_split_adapter.py
services/api/tests/test_grid_correction_workflow.py
services/api/tests/test_grid_correction_learning_api.py --basetemp
D:/game_predicotr/artifacts/t1121-availability` (timeout110 s). Klient: `npm run
typecheck`, `tsx --test test/grid-correction-learning-request.test.mjs` oraz
`npm run check:generated` (każda komenda timeout55 s). Brak ponownego PG/GPU:
uzupełnienie nie zmienia zapisu, migracji ani wykonywania treningu.

- Dataset i durable training: 31 PASS. Partial evaluation/admission/schema: 66 PASS.
- Composition/history/legacy/shared/runs: 45 PASS; nowe handler/history/pipeline:
  8 PASS; końcowy preview/history: 5 PASS (nakładające się zestawy, nie sumować).
- Czyste metryki/gate: 38 PASS; assigned report/schema: 30 PASS (wyniki pomocnika).
- PG registry/report-v3 binding: 1 PASS, 30.48 s. Realny app-role, disposable DB,
  migracja do0171, pełne role/bufory/freeze, replay binding i konflikt command.
- PG parent z publicznym HTTP startem + API contracts: 29 PASS, 18.95 s.
  Test obejmuje rzeczywiste start/replay/CAS, tworzenie evaluation child przez
  GridModelEvaluationService przy parent=processing, claim/release, restart,
  resume tego samego child/budgetPin i cancel z terminalnym dzieckiem.
  W tym teście metadata/artifact facts są kontrolowane, nie używa danych operatora.
- Klient: 135 PASS, build/typecheck PASS, check:generated PASS.
- Admin: tsc PASS; 35 testów renderer/workspace/evaluation/job-state PASS;
  ESLint trzech zmienionych plików PASS. Nowe report unions mają własną ścieżkę
  odczytu, partial FP/complete pozostają `—`; assigned PASS nie obiecuje poprawy.
- Ruff zmienionych Pythonów PASS; scoped mypy 38 src PASS, ograniczenie poniżej.
- Końcowe docs:check PASS (startup 44092/45000 B, CURRENT_STATE 15295 B),
  OpenAPI artifact current, generated client current, git diff --check PASS.
  Code-map zregenerowany; 75 ścieżek zakresu w `artifacts/task1121-audit-paths.txt`.

## Odtworzenie kontroli

PowerShell; przed Pythonem ustawić:

```powershell
$env:PYTHONPATH='D:/game_predicotr/worktrees/grid-corrections-learning/services/api/src;D:/game_predicotr/worktrees/grid-corrections-learning/services/worker/src;D:/game_predicotr/worktrees/grid-corrections-learning/services/test_support'
```

Interpreter: `D:/game_predicotr/.venv/Scripts/python.exe`. Każde wywołanie testowe
było opakowane w Python `subprocess.run(argv, timeout=55)` albo `timeout=110`
dla PG/generatora, z propagacją exit code. Zestawy wykonywano bez usług/watchera.

Główne argv (ścieżki względem worktree):

```text
python -m pytest -q services/worker/tests/test_grid_cohort_dataset.py services/worker/tests/test_durable_v3_grid_training.py
python -m pytest -q services/worker/tests/test_grid_correction_evaluation_pipeline.py services/worker/tests/test_grid_training_resource_admission.py services/api/tests/test_schema_readiness.py
python -m pytest -q services/api/tests/test_grid_correction_workflow.py services/api/tests/test_shared_grid_model_candidate.py services/api/tests/test_grid_model_evaluation_report.py services/api/tests/test_grid_training_runs.py
python -m pytest -q services/worker/tests/test_grid_correction_learning_handler.py services/worker/tests/test_grid_correction_evaluation_pipeline.py services/api/tests/test_grid_correction_workflow.py
python -m pytest -q --tb=short services/api/tests/integration/test_grid_correction_registry_postgres.py --basetemp D:/game_predicotr/artifacts/t1121-binding2
python -m pytest -q --tb=short services/api/tests/integration/test_grid_correction_learning_postgres.py services/api/tests/test_grid_correction_learning_api.py --basetemp D:/game_predicotr/artifacts/t1121-http-pg
```

PG wymaga `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1` i istniejącego lokalnego PostgreSQL;
fixture tworzy/usuwa wyłącznie własną bazę testową. TestClient i lokalne sockety
testowe wymagały wykonania poza ograniczeniami środowiska agenta. Nie uruchomiono API.

W `packages/admin-api-client`: `npm run typecheck`, `npm test`,
`npm run check:generated`. W `apps/admin`: `node D:/game_predicotr/node_modules/typescript/bin/tsc --noEmit`;
`node D:/game_predicotr/node_modules/tsx/dist/cli.mjs --tsconfig tsconfig.json --test test-interactions/grid-model-workspace.test.mjs test/grid-model-evaluation-state.test.mjs test/job-state.test.mjs`.
ESLint: `src/features/jobs/job-state.ts`, `src/features/model-quality/grid-model-comparison.tsx`,
`test-interactions/grid-model-workspace.test.mjs`. Prettier tylko zmienione pliki TS/MJS.
Root: `python scripts/export_admin_openapi.py --check`, `python scripts/generate_code_map.py`,
`npm run docs:check`. Nie wykonywano builda całego Admina; należy do odbioru T4.

## Ograniczenie mypy

Globalny `pyproject.toml` nie zmieniony. Tymczasowy `artifacts/t1121-mypy.toml`
kopiuje go i dodaje wyłącznie:

```toml
[[tool.mypy.overrides]]
module = ["torch", "torch.*"]
follow_imports = "skip"
```

Polecenie: `python -m mypy --config-file artifacts/t1121-mypy.toml --follow-imports=silent`
oraz 38 zmienionych plików `services/*/src/**/*.py`, bez `main.py` i `cli.py`.
`artifacts/task1121_checks.py` zapisuje lokalny wybór; pliki artifacts są ignorowane.
Próba bez wyjątku analizowała masowo zewnętrzny PyTorch i nie mieściła się w limicie;
diagnostyka: `artifacts/t1121-mypy-parent.log`, `artifacts/t1121-mypy-diagnostic.log`.
Nie deklarujemy pełnego mypy PASS. T4 ma pełny project gate przed merge.

## Granice dowodu

Nie ma GPU smoke/treningu ani pomiaru jakości na zdjęciach operatora. Inference w
testach używa kontrolowanych modeli, ale rzeczywistego readera częściowych źródeł,
matchingu, agregacji i serializacji raportu. Parent orchestration composition ma
kontrolowane granice kosztownych dzieci; PG osobno sprawdza realną trwałość kolejki
i service-entry. Legacy tekstowe dataset labels nie stanowią historical scope.
Photo-only nigdy nie jest dowodem niezależności sesji. T3 dopiero buduje apply receipt
i końcowy CAS; assigned comparison nie publikuje modelu ani nie zmienia przypisania.

P2-5/P2-7 audytu1120 zaadresowane przez history composer i evaluator nowej polityki.
P2-6/P2-8/P2-9 pozostają jawnie w T4. Root wykonuje niezależny audyt przed commitem.

## Odbiór przez leada

Focused R2 Opus5.5/high: PASS, bez P0/P1. Dwa P2: tabela planów poprawiona przy
task-close; etykieta scope-stale pozostaje jawnym zakresem T3. Dodatkowo
`test_new_game_default_v3_geometry.py` + `test_dynamic_grid_snapshots.py`:41 PASS,
16.26s, timeout110. Log `artifacts/t1121-new-game-regression.log`.
