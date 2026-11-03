# Audyt TASK-1152 — Zachowanie postępu między etapami zastosowania modelu

Werdykt: PASS
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6-astra, high
Zakres: HEAD...a0712896b8ca722250d840898f96672f43b1db9a oraz zmiany niezacommitowane, data 2026-11-03
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Przejrzałem poprawkę w `GridCorrectionApplyJobHandler`, dwa nowe testy z prawdziwym `checkpoint_job` i `requeue_job` oraz zmiany w dokumentacji. Sprawdziłem je względem domenowej walidacji monotoniczności w `services/api/src/game_predictor_api/domain/jobs.py:342-358` i względem `GridCorrectionApplyService.advance`. Poprawka jest wąska i poprawna. Pierwszy checkpoint nowego lease przepisuje teraz zapisane liczniki zamiast je zerować, a końcowy `success_count` nadal pochodzi z liczby ukończonych kroków. Kroki przechodzą tylko w kierunku `pending → waiting → completed`, a `resume` nie zmienia checkpointu. Dlatego wartość wyliczona z `steps` nie może spaść poniżej zapisanego licznika. Nie znalazłem P0 ani P1. Główne ryzyko resztkowe dotyczy testu: odroczenie i ponowny claim są symulowane przez `dataclasses.replace`, a nie przez domenowe przejścia stanu.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `services/worker/tests/test_grid_correction_apply_handler.py:108` — `CheckedContext.wait_for_dependency` tylko sprawdza payload i rzuca `Released`. Job zostaje w `PROCESSING`, a nowy lease powstaje przez `replace(job, lease_token=uuid4())` (`:156`, `:183`). Prawdziwe przejścia `defer_job_for_dependency` (`jobs.py:476-495`) i claim nie są więc ćwiczone. Dziś obie ścieżki zachowują liczniki (`jobs.py:462-473`), więc ryzyko jest niskie. Gdyby jednak defer albo claim zaczęły kiedyś resetować postęp, test tego nie wykryje. Propozycja: w pętli wywoływać `defer_job_for_dependency` z lease i checkpointem, a potem domenowy odpowiednik claimu, jeśli taki istnieje. Można też zaakceptować to ryzyko i opisać je w `Outcome`.
- [P2-2] `services/worker/tests/test_grid_correction_apply_handler.py:176` — zakres taska wymienia wprost „waiting/comparison”. Test oczekiwania używa jednak stanu z jednym ukończonym krokiem `publish` i fałszywego `advance`, który zwraca stan bez zmian. Nie ma w nim kroku `comparison` o statusie `waiting` ani `waitingForJobId`, czyli dokładnie tej postaci, którą produkcyjny `advance` zapisuje w `grid_correction_apply.py:594-602`. Skutek: liczniki przy prawdziwym kształcie oczekiwania na porównanie nie są przypięte testem. Propozycja: dodać do parametryzacji przypadek z `{"kind": "comparison", "status": "waiting"}` i `waitingForJobId`, a następnie sprawdzić, że `success_count` się nie zmienia.
- [P2-3] `ai_docs/DOC_INDEX.md:281` — nowy wpis dopisano na samym końcu pliku, po zamykającym akapicie sekcji „Historia”, jako ścieżkę w kodzie zamiast linku. Nagłówek katalogu (`ai_docs/DOC_INDEX.md:12`) każe umieszczać plany w odpowiedniej podsekcji, głównie w „Dostarczanie” (`:67`). Skutek: plan jest trudny do znalezienia i niespójny z mapą. Propozycja: przenieść wpis do „Dostarczanie” jako `[Naprawa postępu zastosowania modelu](delivery/GRID_APPLY_PROGRESS_FIX_20261103.md)`.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Regresja odtworzona rzeczywistą walidacją domeny, test czerwony przed poprawką | spełnione (analiza statyczna, testów nie uruchomiono) | `services/worker/tests/test_grid_correction_apply_handler.py:105-106` używa `checkpoint_job`. Przy starym `success_count=0` drugi lease w `:147-163` i pierwszy lease w `:182-187` trafiają na `JOB_PROGRESS_REGRESSION` z `jobs.py:349-353`. To zgadza się z deklarowanym wynikiem 3FAIL/3PASS: 3 nowe przypadki i 3 stare testy. |
| Trzy etapy i ponowne waiting zachowują monotoniczne liczniki po odtworzeniu kontekstu | spełnione | `grid_correction_apply_handler.py:33-35`, `:46-48`. Test trzech etapów z restartem przez FAILED i `requeue_job` oraz przywracaniem JSON: `test_grid_correction_apply_handler.py:131-172`. Dwukrotne waiting z niezerowymi failure/review: `:176-190`. Pokrycie częściowe, zob. P2-1 i P2-2. |
| Lint/types, właściwe regresje, docs/map i Opus bez P0/P1 | niezweryfikowane (lint, typy, regresje); spełnione (docs, ten audyt) | Ruff i scoped mypy znam tylko z deklaracji w `Outcome`. `ai_docs/architecture/VISION_LAB.md:19`, `ai_docs/process/CURRENT_STATE.md:85`, `ai_docs/DOC_INDEX.md:281` (zob. P2-3). Ten audyt: brak P0/P1. |
| Osobny commit task-close; wdrożenie i restart general worker dopiero po osobnej zgodzie | niezweryfikowane (etap po audycie) | Task ma status `in_progress`. Brak commitów na gałęzi poza HEAD. Sekcja „Not completed” w tasku poprawnie zastrzega osobną zgodę. |

## Listy zamknięte i otwarte

Zamknięte: brak, to runda 1.

Otwarte: P2-1, P2-2, P2-3.

## Proponowane testy

- W `services/worker/tests/test_grid_correction_apply_handler.py` dodać do `test_waiting_lease_preserves_existing_counters_and_receipts` przypadek z krokiem `comparison` o statusie `waiting` i z `waitingForJobId`. Uruchomienie: `.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_grid_correction_apply_handler.py -k waiting`.
- W teście trzech etapów zastąpić ręczne `replace(..., status=PROCESSING)` domenowymi przejściami `defer_job_for_dependency` i claim, tak aby pętla przechodziła przez te same funkcje co `WorkerJobStore`.
- Opcjonalnie dodać integracyjny test PostgreSQL (`services/api/tests/integration/`, wymaga `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'`) na `LocalJobWorker.run_once` z handlerem apply i fałszywym serwisem, który przechodzi przez dwa lease z defer, aby sprawdzić liczniki zapisane w bazie.

## Zakres przeglądu i ograniczenia

Przeczytałem:
- brief audytu,
- `services/worker/src/game_predictor_worker/images/grid_correction_apply_handler.py` w całości,
- `services/worker/tests/test_grid_correction_apply_handler.py`,
- w `services/api/src/game_predictor_api/domain/jobs.py`: `update_job_progress`, `checkpoint_job`, `defer_job_for_storage`, `defer_job_for_dependency`, `requeue_job` i `requeue_job_with_fresh_progress`,
- w `services/worker/src/game_predictor_worker/jobs/runtime.py`: `JobExecutionContext.checkpoint` i `wait_for_dependency`,
- w `services/api/src/game_predictor_api/application/grid_correction_apply.py`: `resume`, `_view` i `advance`,
- `grid_correction_learning_handler.py` dla porównania (ten sam wzorzec zerowania nie powoduje tam błędu, bo sukces wynosi 1 dopiero na końcu),
- diff `VISION_LAB.md`, `DOC_INDEX.md` i `CURRENT_STATE.md`, nowy plan w `ai_docs/delivery/` oraz plik taska.

Nie uruchamiałem testów, ruff ani mypy. Wyniki 3FAIL/3PASS, 8PASS i 4PASS oraz logi w `artifacts/grid-applied-comparison-20261103/` znam tylko z deklaracji wykonawcy. Nie sprawdzałem stanu operacyjnego apply `a2eeba17-405a-42d1-952f-1a469a1fcfce` w bazie ani zachowania wdrożonego general workera.
