# Audyt TASK-1244 — Nadzór postępu istniejącego treningu korekt

Werdykt: PASS
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6.1-sol, high
Zakres: HEAD...041002571fc029eb66c82bae19bcad66ec4bfd63 oraz zmiany niezacommitowane, data 2026-11-17
Runda: 2
SHA pakietu: ecdecdc375744f64f70871e9c488b59fa7898b018383aadb12e4a77235ce7cd8
Otwarte P0: 0
Otwarte P1: 0

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

W rundzie 2 sprawdzono poprawki wszystkich znalezisk z rundy 1. Ponownie przejrzano też zmienione ścieżki: `run_activity.py`, `ChildControl` i `Watchdog` w `grid_training_child.py`, pętlę `_supervise` w handlerze, `validation_crops`, `CorrectionEvaluator.measure`, `RunBudget.charge`/`from_payload` oraz nowe testy. Oba znaleziska P1 zostały naprawione. Wycinki walidacyjne publikują teraz postęp po każdym zdjęciu. Testy obejmują zastój wykryty przez watchdog dziecka, jawne anulowanie i odnawianie okna przez kolejne przebiegi walidacji. Poprawki P2-1 do P2-6 są widoczne w kodzie albo w dołączonym dowodzie. Zostały dwie drobne uwagi P2, które nie blokują commitu.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-7] `services/worker/tests/test_grid_correction_consistency_wiring.py:207-216` — Fixture `result` (SimpleNamespace) nie ma `beats_baseline` ani `baseline_floor`. Niezmieniony kod dziecka odczytuje te pola w `grid_training_child.py:622-625`, więc oba przypadki parametryzacji `test_train_routes_correction_evaluator_only_to_grid_only_export` kończą się błędem. Tak wykonawca opisał błąd odtworzony na HEAD, a odczyt kodu to potwierdza. Wykonawca zgłosił go jawnie, zgodnie z kryterium akceptacji. Ten plik jest jednak częścią zakresowej grupy testów, która pozostaje czerwona. Skutek: przyszła regresja w kierowaniu ewaluatora korekt do eksportu nie zostanie wykryta. Propozycja: zapisać osobny task albo znany problem w `CURRENT_STATE.md`/notatce taska i uzupełnić fixture poza TASK-1244. Ryzyko można zaakceptować w tym tasku.
- [P2-8] `services/worker/src/game_predictor_worker/images/grid_training_child.py:350` (oraz `services/worker/src/game_predictor_worker/training_core/run_activity.py:23-24`) — `Watchdog(...)` jest tworzony w `run()` poza blokiem `try`. `progress_supervised` rzuca tam `ValueError("GRID_RUN_SUPERVISION_INVALID")`, gdy spec nie jest spójny. Proces dziecka kończy się wtedy bez pliku wyniku, a supervisor pokazuje ogólny kod `GRID_TRAINING_CHILD_EXITED` zamiast konkretnego. Spec generuje handler i jest chroniony SHA (`grid_training_child.py:116-123`), więc ta ścieżka pojawi się tylko przy błędzie wewnętrznym. Propozycja: zaakceptować ryzyko albo w przyszłości walidować politykę przed startem watchdoga i zapisywać wynik `failed` z tym kodem.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Polityka przetrwa serializację i nowy proces; ponad 7200 s nie wyczerpuje budżetu ani nie odnawia kroków | spełnione | `grid_training_admission.py:528-531,554-565,594-596`; `test_grid_progress_supervision.py:69` (podproces), `test_grid_training_handler.py:288` |
| Starsze budżety i tożsamości wire bez zmian | spełnione | `grid_training_handler.py:579-594` (`timePolicy` tylko dla nowej polityki); `grid_training_admission.py:503-516,567-571`; `run_budget_extension.py:114-116`; `test_grid_training_child.py` sparametryzowany dla obu polityk |
| Rzeczywisty postęp stron, walidacji i kroków podtrzymuje nadzór; heartbeat, poprzednia próba, uszkodzone dane i powtórki nie; zastój, anulowanie i utrata supervisora kończą się widocznie; prawdziwe błędy zostają błędami | spełnione | Strony: `grid_cohort_dataset.py:369-370`. Wycinki: `grid_training_data.py:543-544`, `grid_training_child.py:473-475`. Pomiary: `grid_correction_consistency.py:157-158`. Kroki: `grid_training_child.py:209-210`. Eksport: `:786-787,792-793,929-930`. Testy: `test_grid_progress_supervision.py:152,177,195,233,265,285`, `test_grid_correction_consistency.py:113`, `test_grid_training_handler.py:330`. Zachowanie kodu błędu: `grid_training_handler.py:932-939` |
| Podgląd i zastosowanie zgody zachowują tożsamość i stan, sprawdzają wiązania, odrzucają aktywne i zmienione joby, są idempotentne (także PostgreSQL) | spełnione statycznie | `run_progress_supervision.py:18-143`; `extend_grid_training_run.py:114-167,177-208`; `test_grid_progress_supervision.py:109,133,140`; `test_grid_run_budget_extension_postgres.py:26` (testów nie uruchamiano) |
| Indeksowanie bajtowo, etykietami i rolami równoważne, bez wielokrotnych kopii manifestu; bieżący przebieg monitorowany | spełnione statycznie | `grid_cohort_dataset.py:541-561`; `grid_correction_consistency.py:142`; `grid_training_data.py:124-128`; `test_grid_cohort_dataset.py:171`. Monitorowania operacyjnego nie da się sprawdzić statycznie (Outcome: trening zakończony bez interwencji) |
| Backend, OpenAPI, klient, wrapper i panel zgodne co do null | spełnione | `grid_training_cohorts.py:334`; `openapi.json:23022-23031`; `types.gen.ts:12744`; `index.ts:1697`; `grid-correction-learning-panel.tsx:1339-1345`; `grid-model-state.ts:288-293`; testy `test_grid_training_runs.py:206`, `grid-training-run-request.test.mjs:5`, `grid-correction-learning-panel.test.mjs:790` |
| Zakresowe testy, lint, typy, dokumentacja, mapy i audyt Claude przed commitem | niezweryfikowane | Wyniki pochodzą tylko z Outcome taska. Dwa błędy sprzed zmiany są jawnie zgłoszone (P2-7). Audyt w tej rundzie: PASS |
| Wynik i bezpieczne przekazanie przedstawione do akceptacji; bez aktywacji i nowego przebiegu | niezweryfikowane | Outcome opisuje zakończony przebieg bez zgody i bez aktywacji. Status taska to `in_progress`, a prezentacja do akceptacji wdrożenia jest jeszcze przed nami |

## Listy zamknięte i otwarte

Zamknięte: P1-1 (`grid_training_data.py:532-544`, `grid_training_child.py:473-475`, test `test_grid_progress_supervision.py:285`), P1-2 (`test_grid_progress_supervision.py:233,265`, `test_grid_correction_consistency.py:113`), P2-1 (`run_activity.py:63-77`, testy `:335,:353`), P2-2 (`grid_correction_consistency.py:142`, `grid_training_data.py:124-128`), P2-3 (`grid_training_handler.py:932-939`, test `test_grid_training_handler.py:322-374`), P2-4 (`grid-model-state.ts:288-289`, test `test_grid_progress_supervision.py:324`), P2-5 (`grid_training_child.py:786-793,929-930`), P2-6 (`TASK-1244_GENERATED_EOL.json`; w `git status` nie ma zmian w pozostałych wygenerowanych plikach klienta).

Otwarte: P2-7, P2-8.

## Proponowane testy

- `services/worker/tests/test_grid_correction_consistency_wiring.py`: uzupełnić fixture `result` o `beats_baseline=True` i `baseline_floor` w osobnym tasku (P2-7). Uruchomienie: `.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_grid_correction_consistency_wiring.py`.
- `services/worker/tests/test_grid_training_handler.py`: przypadek, w którym zastój zostaje wykryty, a potem przychodzi anulowanie operatora. Test powinien sprawdzić, który kod (anulowanie czy zastój) trafia do historii i do błędu joba, i że checkpoint zostaje zachowany.
- `services/worker/tests/test_grid_progress_supervision.py`: spec z `timePolicy` i liczbowym `remainingSeconds` (niespójny). Test powinien potwierdzić zachowanie `run()`, czyli konkretny kod albo jawnie zaakceptowany `GRID_TRAINING_CHILD_EXITED` (P2-8).

## Zakres przeglądu i ograniczenia

Przeczytano zamrożony pakiet (diff, nowe moduły i testy, plik taska, raport rundy 1 i dowód EOL) oraz kod potrzebny do weryfikacji poprawek. Były to: `grid_training_child.py` (`read_spec`, `ChildControl`, `Watchdog`, `run`, `_train` w liniach 116-670), `grid_training_handler.py` (`_set_budget`, `_recover_previous_attempt`, `_spec`, `_train`, `_supervise`, linie 240-300 i 576-940), `grid_training_admission.py` (`RunBudget`, linie 495-615), `grid_training_data.py` (`CohortPhotos`, `validation_crops`), fragmenty `grid_cohort_dataset.py` (`manifest`, `_verify_index`, `_sources`) oraz `test_grid_correction_consistency_wiring.py`. Nie uruchamiano testów, lintu, mypy, PostgreSQL ani treningu. Wyniki „PASS” i liczby testów w Outcome to deklaracje wykonawcy, których tu nie potwierdzono. Nie mierzono czasu faz przygotowania danych dla rzeczywistej kohorty, więc ocena odporności na zastój opiera się na odczycie ścieżek publikacji aktywności. Nie porównywano bajtowo wygenerowanych plików klienta. Ich brak w liście zmian `git status` z początku sesji to jedyny dowód dla P2-6.