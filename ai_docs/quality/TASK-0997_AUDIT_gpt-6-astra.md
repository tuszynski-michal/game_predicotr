# Audyt TASK-0997 — Ocena per gra i bramka kandydata

Werdykt: PASS
Audytor: Codex, etykieta briefu `gpt-6-astra`, reasoning `high`
Wykonawca: `claude-opus-5-5`, reasoning `xhigh`
Zakres: HEAD...6397bc517e787271b76fa7d49425fef40fd6b785 oraz zmiany niezacommitowane wskazane w briefie, data 2026-10-16
Runda: 2

Przegląd statyczny, bez zmian w plikach. Audytor nie uruchamiał testów, migracji ani usług.

## Streszczenie

Poprawki zamykają oba znaleziska P0 z pierwszej rundy: dowód wymaga aktywnego magazynu gry o przypiętej generacji, a bramka uwzględnia regresję duplikatów detekcji. Sprawdzono również kontrolę plików wynikowych po wznowieniu, idempotencję polecenia i poprawioną etykietę PASS. Pozostaje częściowo usunięta uwaga P2 dotycząca spóźnionych odpowiedzi panelu; nie stwierdzono otwartych P0 ani P1.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-2] `apps/admin/src/features/model-quality/grid-model-comparison.tsx:150` — **Ochrona przed odpowiedzią poprzedniego kandydata pozostaje niepełna.** `refresh` i `open` sprawdzają aktualny wybór, ale `start` bezwarunkowo wykonuje `setSelected(result.data)`. Podczas oczekiwania na utworzenie oceny A można wybrać kandydata B, ponieważ selektor pozostaje aktywny. Późniejsza odpowiedź A ponownie wyświetli jego ocenę pod wyborem B. Należy sprawdzać generację żądania i aktualnego kandydata także przed aktualizacją stanu w `start`, albo blokować zmianę wyboru podczas polecenia. Test powinien odtwarzać kolejność zdarzeń, zamiast sprawdzać jedynie obecność warunków w kodzie.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Regresja dowolnej gry blokuje wspólny PASS | spełnione | `services/api/src/game_predictor_api/domain/grid_model_evaluation.py:51` uwzględnia duplikaty; agregacja wszystkich gier w linii 221. Scenariusz regresji duplikatów drugiej gry: `services/worker/tests/test_grid_model_evaluation.py:294`. |
| Brak detekcji ma koszt | spełnione | `services/worker/src/game_predictor_worker/geometry_core/metrics.py:163` inicjalizuje koszt brakujących plansz wartością 1; scenariusz pomiaru: `services/worker/tests/test_grid_model_evaluation.py:248`. |
| Brak danych, parity lub aktualnych dowodów blokuje publikację | spełnione | `services/api/src/game_predictor_api/domain/grid_model_evaluation.py:177` sprawdza pokrycie i parity, a linia 408 uwzględnia stan oraz generację magazynu. Test bariery po usunięciu lub zmianie magazynu: `services/api/tests/test_grid_model_evaluation_report.py:406`. |
| Dobór checkpointu nie używa REGRESSION | spełnione | `services/worker/src/game_predictor_worker/images/grid_training_child.py:392` korzysta z VALIDATION; strażnik rozdziału ról: `services/worker/tests/test_grid_model_evaluation.py:384`. |
| Wyniki kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu | niezweryfikowane | Wyniki po poprawkach zapisano w `ai_docs/tasks/0997-grid-model-evaluation.md:167`, ale pełne zestawy pozostają zapowiedziane w linii 171. Opis naprawy panelu w linii 153 wymaga uwzględnienia pozostającego P2-2. |

## Listy zamknięte i otwarte

Zamknięte:

- **P0-1:** stan i generacja magazynu są sprawdzane w `services/api/src/game_predictor_api/domain/grid_model_evaluation.py:425`. Test rzeczywistego usunięcia gry przez lifecycle znajduje się w `services/api/tests/integration/test_grid_model_evaluation_bridge_postgres.py:164`.
- **P0-2:** `duplicate_predictions` należy do metryk bez regresji w `services/api/src/game_predictor_api/domain/grid_model_evaluation.py:56`; test workera w `services/worker/tests/test_grid_model_evaluation.py:294`.
- **P2-1:** kontrola ścieżki i SHA plików `detail` przed budową raportu w `services/worker/src/game_predictor_worker/images/grid_model_evaluation_handler.py:287`; test brakującego i zmienionego pliku w `services/worker/tests/test_grid_model_evaluation.py:309`.
- **P2-3:** klucz idempotencji związano z treścią polecenia w `apps/admin/src/features/model-quality/grid-model-evaluation-state.ts:113`.
- **P2-4:** etykieta PASS odpowiada polityce w `apps/admin/src/features/model-quality/grid-model-evaluation-state.ts:18`.

Otwarte: **P2-2**, częściowo poprawione. Wymaga poprawki albo jawnego odnotowania ryzyka w Outcome.

## Proponowane testy

- Dodać test interakcji panelu: rozpocząć tworzenie oceny A, wybrać B, rozwiązać odpowiedź A i sprawdzić, że nie zastępuje aktualnego widoku. Objąć również przełączenie A → B → A z odpowiedziami w odwrotnej kolejności. Plik: `apps/admin/test/grid-model-evaluation-state.test.mjs` lub dedykowany test komponentu. Komenda: `npm run test --workspace @game-predictor/admin`.
- Rozszerzyć `services/api/tests/integration/test_grid_model_evaluation_e2e_postgres.py` o dwie rzeczywiste kohorty i przerwanie między bindingami. Obecny E2E sprawdza jedną grę; scenariusz wielogrowy rozłożono między test workera z atrapą storage i testy bariery. Komenda w izolowanym środowisku PostgreSQL: `.\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_grid_model_evaluation_e2e_postgres.py`.

## Zakres przeglądu i ograniczenia

Przeczytano brief, raport R1, task, fragment planu, decyzje D-483/D-559 oraz odpowiednie zmiany wymagań i architektury. Przejrzano raport v2, bramkę publikacji, migrację 0166, repozytorium dowodów, protokół proof, worker, API, schematy, panel i powiązane testy. Sprawdzono obecność nowych tras i pól w wygenerowanym kliencie.

`git diff --check` nie zgłosił błędów białych znaków; wystąpiły ostrzeżenia LF/CRLF. Odczytany artefakt E2E zawiera wynik PASS oraz późniejszą odmowę `GRID_COHORT_LABEL_STALE`. Nie uruchamiano niezależnie testów ani rzeczywistego inference. PASS oznacza brak otwartych P0/P1 w przeglądzie statycznym, nie potwierdzenie zakończenia wszystkich kontroli wykonawcy.