Mam już komplet dowodów: handler, domenę checkpointu, runtime/store workera, oba testy i logi wykonawcy. Piszę raport.

# Audyt TASK-0999 — Backend ponownego rozpoznania wybranego zakresu

Werdykt: PASS
Audytor: claude-fable-5-1, reasoning high
Wykonawca: gpt-6.1-sol, reasoning high
Zakres: d078938b18abdff5d6e1f99795f9d4aca09716b1...d078938b18abdff5d6e1f99795f9d4aca09716b1 oraz zmiany niezacommitowane, data 2026-10-15
Runda: 3

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano ograniczoną poprawkę R2-P1-1 w trzech plikach: `cancellation_boundary` handlera, test jednostkowy workera i dwa scenariusze PG anulowania. Handler buduje teraz payload checkpointu w kontrakcie v1 (`schema_version`, `workflow`, `phase`, `cursor`), który rzeczywisty `checkpoint_job` akceptuje; produkcyjny `SqlAlchemyWorkerJobStore.checkpoint` w jednej transakcji odnawia lease, utrwala stage/postęp/payload, potwierdza anulowanie przez `acknowledge_job_cancellation` i synchronizuje operację, a `JobExecutionContext.checkpoint` zgłasza typowane `_ExecutionStopped(CANCELLED)` bez `_fail_handler` i bez `_reconcile_board_search`. Test workera deleguje do rzeczywistych funkcji domenowych i według logu czerwonego przebiegu odtwarza dokładnie `UNSUPPORTED_JOB_CHECKPOINT_VERSION` na implementacji R2; testy PG mają pułapki na `store.fail` i reconciliation oraz asercje utrwalonego payloadu. R2-P1-1 uznaję za zamknięte. Pozostałe ryzyko: zachowany „identyczny” poprzedni checkpoint v1 i faza wyprowadzana ze `stage` mogą po wznowieniu dać nieaktualny, czysto diagnostyczny payload; nic go nie konsumuje.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [R3-P2-1] `services/worker/src/game_predictor_worker/images/grid_reinference_handler.py:103-109` z `services/api/src/game_predictor_api/storage/grid_reinference.py:288` — istniejący payload z `schema_version == 1` jest przekazywany bez zmian, a `resume` używa `requeue_job`, które zachowuje `checkpoint_payload`. Po sekwencji cancel w prepare → resume → freeze/start → cancel w infer drugi checkpoint utrwali `phase: "prepare"` i `cursor` z pierwszego anulowania, podczas gdy `stage` będzie `grid_reinference:infer`. Analogicznie cancel na pierwszej granicy `infer()` (`:142`), zanim `progress(..., "infer")` zaktualizuje stage, zapisze `phase: "prepare"` mimo `operation.phase == "infer"`. Skutek wyłącznie diagnostyczny: trwały cursor/receipts należą do dokumentu operacji, wznowienie czyta `processedSources`/`prepareCursor`, a Admin API nie zwraca `checkpointPayload` (`ai_docs/architecture/API_CONTRACT.md:2788`). Zachowanie odpowiada jawnemu zapisowi w Technical notes („Istniejący poprawny checkpoint pozostaje identyczny”), więc dopuszczalna jest akceptacja ryzyka. Propozycja na przyszłość: dla kontraktu grid-reinference zawsze odświeżać `phase`/`cursor` (z zachowaniem pozostałych kluczy) albo wyprowadzać fazę z dokumentu operacji odczytanego już w `__call__`, i dodać asercję PG dla podwójnego anulowania.

- [R2-P2-1, nadal otwarte] `services/worker/src/game_predictor_worker/jobs/store.py:119-121` — niespójny kandydat lub niedostępny magazyn nadal może przerwać claim; poza zakresem tej rundy, zapisane jako jawne ograniczenie.

- [R2-P2-2, nadal otwarte] `services/api/src/game_predictor_api/storage/grid_reinference.py:750-757` — konserwatywna ochrona obcego żywego item; fail-closed, bez utraty danych; poza zakresem tej rundy.

- [R1 P2-1, nadal otwarte] `services/api/tests/integration/test_grid_reinference_postgres.py:144` — wcześniejszy FAIL pełnego layout-data reset przez kolejność `_GAME_RESET_STATEMENTS`; bez xfail, bez zmiany, zgodnie z decyzją leada.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Aktualna baza działa bez treningu | spełnione | Niezmienione od R2; pliki zamrożone w `artifacts/audits/TASK-0999_R3_SCOPE.json` (`storage/grid_reinference.py`, `test_grid_reinference_models_and_cursor.py` w `unchangedOtherSourceFiles` w `TASK-0999_R3_SOURCE_SCOPE_PROOF.json:22,43`). |
| Chronione decyzje pozostają identyczne | spełnione | Niezmienione od R2 (`storage/grid_reinference.py` zamrożone, `TASK-0999_R3_SOURCE_SCOPE_PROOF.json:43`); ograniczenie R2-P2-2 pozostaje. |
| Brak środkowego slotu nie przesuwa sekwencji | spełnione | Niezmienione od R2: `grid_reinference_handler.py:303-304` (`binding_required`), test `services/worker/tests/test_grid_reinference_handler.py:116-157`. |
| Restart nie dubluje zapisu; identyczny wynik nie jest „naprawą” | spełnione | `grid_reinference_handler.py:210-216` (niezmienny checkpoint źródła), `:225-226` (pominięcie przetworzonego ordinal), `:305-308` (`unchanged`); PG `cancel_between_sources` `test_grid_reinference_postgres.py:647-654, 677-684` (receipts pierwszego źródła identyczne po resume, drugie źródło bez wyniku przed resume). Anulowanie nie cofa receipts: `store.py:189-211` utrwala payload w tej samej transakcji co potwierdzenie. |
| Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu | spełnione | `ai_docs/tasks/0999-grid-reinference-backend.md:498-511, 755-776` (Technical notes i Outcome R3), `ai_docs/process/CURRENT_STATE.md:197-200`, `ai_docs/quality/TASK-0999_R2_CORRECTION_CODEX.md`; opis `API_CONTRACT.md:3951-3954` („potwierdzane istniejącym cancellation checkpoint”) odpowiada teraz `grid_reinference_handler.py:97-118` + `store.py:189-206`. Wyniki 1 FAIL/1 PASS, 9 PASS, 2 PASS, Ruff/mypy pochodzą z logów wykonawcy (`TASK-0999_R3_RED_REGRESSION.txt`, `TASK-0999_R3_WORKER_TESTS.txt`, `TASK-0999_R3_PG_CANCEL.txt`), nieodtworzone przez audytora. |

## Listy zamknięte i otwarte

Zamknięte (tylko w rundzie 2 lub później): R2-P1-1 — `grid_reinference_handler.py:101-109` buduje payload `schema_version: 1` tylko gdy brak poprawnego checkpointu, przekazuje zachowany `stage` i liczniki (`:110-118`); `domain/jobs.py:351-355` akceptuje go, `store.py:183-206` renew → `checkpoint_job` → `acknowledge_job_cancellation` w jednej transakcji, `runtime.py:262-263` zgłasza `_ExecutionStopped(CANCELLED)`, `runtime.py:364-367` zwraca CANCELLED bez `_fail_handler`, `__call__` zamyka runner w `finally` (`:90-94`). Dowód testowy: `services/worker/tests/test_grid_reinference_handler.py:256-286` (fake store delegujący do `renew_job_lease`/`request_job_cancellation`/`checkpoint_job`/`acknowledge_job_cancellation`), `:324-339` (typowane zatrzymanie, status `cancelled`, stage, payload v1 albo zachowany identyczny checkpoint z dodatkowym kluczem); log czerwonego przebiegu na R2: `artifacts/audits/TASK-0999_R3_RED_REGRESSION.txt:4-26` (`[None]` FAIL z `UNSUPPORTED_JOB_CHECKPOINT_VERSION`, wariant v1 PASS). PG: `test_grid_reinference_postgres.py:389-413` (`store.fail` i `_reconcile_board_search` zastąpione `AssertionError` i `assert_not_called`; `error_code is None`, `stage`, `checkpoint_payload` v1 z `cursor == progress_current`), użyte w `cancel_prepare` `:437-453` i `cancel_between_sources` `:633-665`; pułapka na `store.fail` wyklucza przejście przez `_fail_handler` (`runtime.py:404-415` nie przechwytuje `AssertionError`), a brak `checkpoint_payload` w ścieżce `store.fail` (`store.py:256-262`) nie spełniłby asercji `:408-413`.

Otwarte: R3-P2-1, R2-P2-1, R2-P2-2, R1 P2-1 (wszystkie jako zaakceptowane albo zapisane ograniczenia).

## Proponowane testy

- `services/api/tests/integration/test_grid_reinference_postgres.py`: scenariusz podwójnego anulowania (cancel w prepare → resume → freeze/start → cancel w infer) z asercją, że utrwalony `checkpoint_payload["phase"] == "infer"` i `cursor == progress_current`, co ujawni R3-P2-1, jeżeli lead zdecyduje o odświeżaniu payloadu. Komenda: `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_grid_reinference_postgres.py -k cancel`.
- `services/worker/tests/test_grid_reinference_handler.py`: wariant parametryzacji z `stage=None` i `progress_current=0` (anulowanie przed pierwszym capture) oraz z istniejącym checkpointem bez `schema_version` (np. `{"legacy": True}`), aby objąć obie gałęzie `:101-109` poza fazą infer. Komenda: `.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_grid_reinference_handler.py -k cancel`.

## Zakres przeglądu i ograniczenia

Przeczytano w całości brief z patchami R2→R3 trzech plików, raport R2, odpowiedź wykonawcy `TASK-0999_R2_CORRECTION_CODEX.md`, `TASK-0999_R3_SCOPE.json`, `TASK-0999_R3_SOURCE_SCOPE_PROOF.json`, logi `R3_RED_REGRESSION`, `R3_WORKER_TESTS`, `R3_PG_CANCEL`, `R3_DIFF`. Źródła: `grid_reinference_handler.py` (cały), `services/worker/tests/test_grid_reinference_handler.py:1-360`, `test_grid_reinference_postgres.py:280-700`, `domain/jobs.py:330-720`, `jobs/runtime.py:60-429`, `jobs/store.py:140-314, 460-550`, `storage/grid_reinference.py:255-335, 803-843`, `API_CONTRACT.md:3925-3964`, `CURRENT_STATE.md:193-200`. Nie uruchamiano testów ani poleceń git; wyniki testów, Ruff, mypy i receipt cleanupu PG są deklaracjami wykonawcy. Nie weryfikowano niezmienności zamrożonych plików poza porównaniem list w `R3_SCOPE.json`/`R3_SOURCE_SCOPE_PROOF.json` z zakresem patchy w briefie. Nie przeglądano ponownie kolejki, admission, kwarantanny, migracji ani wygenerowanego klienta, zgodnie z ograniczeniem rundy 3.
