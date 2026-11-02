---
title: Audyt krzyżowy TASK-1121
status: active
last_updated: 2026-11-02
---

# Audyt TASK-1121 — Trening i ocena częściowych zdjęć

Werdykt: REVISE
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6-astra, high
Zakres: HEAD...e1fcae27dace97c5dea102a05c512b9bf77ec94c oraz zmiany niezacommitowane (śledzone i nowe pliki z listy briefu), data 2026-11-02
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Sprawdziłem cały pion T2: czyste metryki korekt i wybór checkpointu, raport v3 i bramkę `grid-model-per-game-gate-v2`, adaptery datasetu, treningu i oceny w workerze, trwałego rodzica (serwis, handler, filtr claim, odroczenie), migrację 0171 z binderem SQL i uprawnieniami, router i schematy HTTP, rozdzielenie czytników publikacji oraz renderer w Adminie. Jakość jest wysoka. Częściowe kontrole przechodzą cały pion bez cichego filtrowania. Bramka liczy decyzje od nowa i odrzuca sfałszowane pola. Rodzic poprawnie zwalnia slot, a deterministyczne klucze adoptują dzieci. Główne ryzyko leży w ścieżce publikacji i defaultu. Raport z zawężonym zakresem pomija sprawdzenie całej rodziny przy publish, ale `set_default` nie sprawdza, że zakres oceny obejmuje zakres aktualnie zastępowanego defaultu. Ta gałąź nie ma też testu.

## Znaleziska

### P0

Brak.

### P1

- [P1-1] `services/api/src/game_predictor_api/application/grid_model_publication.py:112` (oraz `:252`, `:266`): po zmianie `if publishing and not evidence.scoped` publikacja z raportem v3 nie wymaga oceny całej rodziny. Zakres takiego raportu to gra bieżąca, gry TRAIN i zweryfikowany scope **bazy kandydata**, czyli defaultu z chwili preview. Polecenie `set_default` (`eligible(...)` z `game_id=None`) nie sprawdza jednak, że `manifest.baseVersionId` nadal jest bieżącym defaultem ani że `requiredGameIds` obejmuje zweryfikowany scope bieżącego defaultu. Scenariusz: D1 ma scope {A,B}, kandydat C1 z D1 ma PASS v3 na {A,B} i zostaje opublikowany. W międzyczasie operator ustawia default D2, którego zweryfikowany scope obejmuje grę C. Następnie `set_default(C1)` z poprawną rewizją przechodzi, choć gry C nigdy nie oceniono. Plan T2 wymaga zakresu „zweryfikowany scope poprzedniego defaultu” i każe spójnie zmienić „publish/activate/default”. Przed tą zmianą starsze v2 chroniło default wymogiem PASS całej rodziny, więc zmiana osłabia istniejącą ochronę. Istniejąca kontrola wersji jest już osiągalna obecnym API, niezależnie od apply z T3. Proponowana poprawka: w `execute` dla `kind == "set_default"` przy `evidence.scoped` wymagać, żeby `manifest["baseVersionId"]` równało się `self.repository.default().version_id`, albo żeby `verified_history(bieżący default).gameIds ⊆ requiredGameIds ∪ potwierdzone exclusions`. W przeciwnym razie zwracać stabilny kod, np. `GRID_MODEL_EVALUATION_SCOPE_STALE`. Opisać to w D-578.
- [P1-2] `services/api/src/game_predictor_api/application/grid_model_publication.py:112`: zmieniona gałąź bramki publikacji nie ma testu. Brakuje sprawdzenia, że publish z raportem v3 pomija tylko sprawdzenie rodziny, a nadal wymaga currentness. Brakuje też testów, że `set_default` i `activate` z dowodem scoped działają zgodnie z regułami zakresu (aktywacja gry spoza `requiredGameIds` odrzucona, `domain/grid_model_publication.py:166`). `test_grid_correction_workflow.py:345` sprawdza tylko flagę `evidence.scoped` w parserze. Według AGENTS.md i DoD zmieniony pion wymaga testu. Proponowana poprawka: testy jednostkowe `GridModelPublicationService.execute` dla publish, set_default (razem z P1-1) i activate z raportem v3.

### P2

- [P2-1] `ai_docs/tasks/1121-grid-correction-training-evaluation.md:162`: scoped mypy pomija zmienione moduły `services/api/src/game_predictor_api/main.py` i `services/worker/src/game_predictor_worker/cli.py`. DoD (`ai_docs/process/DEFINITION_OF_DONE.md:48`) wymaga typecheck dla zmienionych modułów. Ograniczenie opisano jawnie, a kod tych modułów to proste wiązanie zależności, więc ryzyko jest niskie. Proponowana poprawka: przed commitem uruchomić ten sam scoped mypy (`--follow-imports=silent`, wyjątek `torch.*`) także na tych dwóch plikach albo zapisać akceptację ryzyka do TASK-1123.
- [P2-2] `services/worker/src/game_predictor_worker/images/grid_model_evaluation_handler.py:273` i `services/worker/src/game_predictor_worker/images/grid_training_data.py:366`: `full_geometry` wynika z samego `screenEligible`, a dataset definiuje pełne zdjęcie jako `screenEligible` plus komplet pozycji 0–8 (`grid_cohort_dataset.py:433`). Dla źródła z `screenEligible=True` i mniej niż 9 celami w kontroli korekt `evaluate_photo` rzuca zwykły `ValueError` (`grid_correction_metrics.py:53`) zamiast stabilnego `JobHandlerError`. To działa fail-closed, ale bez czytelnego kodu. Proponowana poprawka: użyć tej samej definicji `full` co dataset albo mapować błąd na stabilny kod (np. `FULL_PHOTO_REQUIRED`).
- [P2-3] `services/api/src/game_predictor_api/application/grid_correction_learning.py:501-523` i `:532-550` (lock `:562`): `advance` trzyma advisory step lock przez całe `training.create` i `evaluations.create`. Te wywołania mogą czytać kohorty, artefakty i parity dłużej niż 5 s. `cancel` i `resume` czekają na ten sam lock z `lock_timeout='5s'`. Po przekroczeniu limitu operator dostaje błąd bazy (500) zamiast stabilnego 409. Proponowana poprawka: mapować `LockNotAvailable` na `GridCohortError("GRID_LEARNING_BUSY", ..., 409)` albo zawęzić sekcję krytyczną.
- [P2-4] `services/api/src/game_predictor_api/application/grid_correction_learning.py:392-395` z `:569-576`: anulowanie podczas `PROCESSING` dziecka, a potem natychmiastowe `resume`, wznawia rodzica, ale nie dziecko, bo to wciąż ma status processing. Gdy dziecko potwierdzi anulowanie (`CANCELLED`), rodzic przechodzi w `FAILED` przez `_waiting` i potrzebne jest drugie `resume`. Danych to nie psuje, ale jest mylące. Proponowana poprawka: `resume` odrzuca stan z aktywnym dzieckiem z `cancel_requested`, albo `_waiting` traktuje anulowane dziecko po wznowieniu jako ponowne kolejkowanie.
- [P2-5] `services/api/src/game_predictor_api/schemas/grid_correction_learning.py:43-50` wobec `services/api/src/game_predictor_api/domain/grid_correction_evaluation.py:261`: domena wymaga posortowanych exclusions, a schemat HTTP tylko sprawdza unikalność. Poprawne polecenie z dwoma wyłączeniami w innej kolejności kończy się 422 `GRID_LEARNING_SCOPE_INVALID`. Proponowana poprawka: kanonicznie sortować exclusions po `gameId` w walidatorze schematu (preview, start i create oceny) przed liczeniem `previewSha256`.
- [P2-6] `ai_docs/tasks/1121-grid-correction-training-evaluation.md:3` i `:117`: front matter i sekcja Status mówią `blocked`, a Outcome mówi, że task „pozostaje `in_progress`”. `ai_docs/process/CURRENT_STATE.md` nadal opisuje audyt jako przerwany limitem. Proponowana poprawka: po tym audycie ujednolicić status i wpis CURRENT_STATE.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Częściowe VALIDATION i REGRESSION przechodzą cały pion bez filtrowania | spełnione | `services/worker/src/game_predictor_worker/images/grid_cohort_dataset.py:433-445`, `images/grid_training_child.py:397,421-423`, `images/grid_model_evaluation_handler.py:264-275`, `training_core/grid_correction_metrics.py:33-37,74-103` |
| Checkpoint deterministyczny (board_correct, potem błąd, potem wcześniejszy krok; tylko VALIDATION; gry z równą wagą) | spełnione | `services/worker/src/game_predictor_worker/training_core/grid_training.py:249-265`, `training_core/grid_correction_metrics.py:116-137`, `images/grid_training_data.py:325-372`, `services/api/src/game_predictor_api/domain/grid_correction_evaluation.py:269-291` |
| Raport v3 i gate v2 (progi, epsilon, full-only miary, scope, exclusions) | spełnione | `services/api/src/game_predictor_api/domain/grid_correction_evaluation.py:153-210,222-266,410-494` |
| Spójne publish/activate/default dla raportu scoped (plan T2) | niespełnione | P1-1, P1-2: `services/api/src/game_predictor_api/application/grid_model_publication.py:112,252,266` |
| Legacy bez zmian | spełnione | `services/api/src/game_predictor_api/domain/grid_model_publication.py:155-160`, `application/grid_model_evaluation.py:306-309`, `worker/training_core/grid_training_admission.py:216-230`, `images/grid_cohort_dataset.py:157-166` |
| Właściwe testy, lint/typecheck i dokumentacja | niezweryfikowane | Nie uruchamiałem testów. Wyniki wykonawcy: `ai_docs/quality/TASK-1121_VERIFICATION.md`. Luka testowa P1-2, luka mypy P2-1. |
| Audyt Opus 5.5/high bez otwartych P0/P1 | niespełnione | Ten raport: REVISE (P1-1, P1-2) |
| Outcome, task-close, osobny commit, record-hash | niespełnione | Oczekuje na zamknięcie P1 |

## Listy zamknięte i otwarte

Zamknięte (tylko w rundzie 2 lub później): nie dotyczy.

Otwarte: P1-1, P1-2, P2-1, P2-2, P2-3, P2-4, P2-5, P2-6.

## Proponowane testy

- `services/api/tests/test_grid_correction_workflow.py` (albo nowy `test_grid_model_publication_scoped.py`): publish z raportem v3 pomija sprawdzenie rodziny, ale odrzuca nieaktualną kohortę. `set_default` kandydata scoped jest odrzucany, gdy bieżący default różni się od `baseVersionId` (lub gdy jego scope nie mieści się w `requiredGameIds`). `activate` gry spoza `requiredGameIds` jest odrzucany. Polecenie: `.\.venv\Scripts\python.exe -m pytest services/api/tests/test_grid_correction_workflow.py -k "publication or default"`.
- `services/worker/tests/test_grid_correction_evaluation_pipeline.py`: kontrola korekt ze `screenEligible=True` i mniej niż 9 celami kończy się stabilnym kodem `JobHandlerError`. Polecenie: `.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_grid_correction_evaluation_pipeline.py`.
- `services/api/tests/test_grid_correction_learning_api.py`: dwa exclusions w odwrotnej kolejności dają ten sam `previewSha256` i nie dają 422.
- `services/api/tests/integration/test_grid_correction_learning_postgres.py` (z `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`): cancel w czasie trzymanego step locka zwraca stabilny 409. Cancel przy dziecku processing, potem natychmiastowy resume, kończy się bez drugiego ręcznego resume (albo jest jawnie odrzucony).

## Zakres przeglądu i ograniczenia

Przeczytane w całości: `domain/grid_correction_evaluation.py`, `domain/grid_assigned_comparison.py`, `application/grid_correction_learning.py`, `application/grid_correction_history.py`, `api/grid_correction_learning.py`, `schemas/grid_correction_learning.py`, migracja `0171_grid_correction_learning.py`, `storage/source_recording_sql_v5.py`, `storage/source_recording_permissions_v5.py`, worker `grid_correction_learning_handler.py` i `training_core/grid_correction_metrics.py`. Przeczytane jako diff względem HEAD: `application/grid_model_evaluation.py`, `application/grid_model_publication.py`, `domain/grid_model_publication.py`, `domain/jobs.py`, `schemas/jobs.py`, `storage/grid_correction_split.py`, `domain/grid_correction_split.py`, `storage/grid_model_registry.py`, `schema_readiness.py`, `database_roles.py`, `main.py`, `api/grid_model_evaluations.py`, worker `jobs/runtime.py`, `jobs/store.py`, `cli.py`, `grid_model_evaluation_handler.py`, `grid_training.py`, `grid_training_admission.py`, `grid_training_child.py`, `grid_training_data.py`, `grid_cohort_dataset.py`, `grid_training_handler.py`, zmiany Admina i dokumentacji z briefu, plan T2–T4 oraz `TASK-1121_VERIFICATION.md`. Kontekstowo przeczytałem dopasowanie z `geometry_core/metrics.py` i `EarlyStopping` (patience 2 i min_evaluations 2 dają zgodność `stopped` z walidatorem).

Nie analizowałem linia po linii wygenerowanego OpenAPI i SDK (`openapi.json`, `types.gen.ts`, `sdk.gen.ts`) ani treści nowych plików testowych poza nazwami testów. Nie uruchamiałem testów, lintu, typechecku, migracji ani usług. Nie dało się statycznie potwierdzić zachowania PostgreSQL (advisory locki, `lock_timeout`, granty kolumnowe bindera) ani faktycznego przebiegu treningu na GPU. Funkcję `POST /grid-model-evaluations/assigned-comparison` przeniesiono z zakresu T3 do T2. Opisuje ją D-578. Sprawdziłem ją pod kątem poprawności, ale wiązanie z receipt apply i końcowy CAS należą do audytu T3.
