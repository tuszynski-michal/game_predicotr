# Audyt TASK-0997 — Ocena per gra i bramka kandydata

Werdykt: REVISE
Audytor: Codex, etykieta briefu `gpt-6-astra`, reasoning `high`
Wykonawca: `claude-opus-5-5`, reasoning `xhigh`
Zakres: HEAD...6397bc517e787271b76fa7d49425fef40fd6b785 oraz zmiany niezacommitowane wskazane w briefie, data 2026-10-16
Runda: 1

Przegląd statyczny, bez zmian w plikach. Audytor nie uruchamiał testów, migracji ani usług.

## Streszczenie

Sprawdzono raport v2, pomiar obu modeli, bramkę publikacji, most aktualności, wznowienie workera oraz API i panel porównawczy. Wykryto dwie luki: usunięcie partycji gry nie unieważnia jej dowodu, a dodatkowe detekcje będące duplikatami nie pogarszają bramki. Oba przypadki pozwalają zachować kwalifikację mimo niespełnienia wymaganego warunku.

## Znaleziska

### P0

- [P0-1] `services/api/src/game_predictor_api/storage/grid_model_evaluation_repository.py:64` — **Dowód usuniętej gry pozostaje aktualny.** `cohort_currentness` porównuje wyłącznie licznik notices z zapisanym proof. Tymczasem usunięcie całej gry wykonuje `DETACH PARTITION` i `DROP TABLE` (`services/api/src/game_predictor_api/storage/game_partition_lifecycle.py:279`), bez wywołania wierszowych triggerów notices. Współdzielone marks i proofs pozostają. Po usunięciu jednej gry wspólnego raportu jej kohorta i binding już nie istnieją, lecz raport nadal może przejść publikację lub ustawienie default dla pozostałych gier. Należy uwzględnić stan lifecycle w barierze albo trwale unieważniać zależne raporty przed usuwaniem partycji. Rozwiązanie powinno zachować historię i korzystać wyłącznie z dozwolonych danych współdzielonych.

- [P0-2] `services/worker/src/game_predictor_worker/training_core/grid_evaluation.py:67` — **Regresja liczby nadmiarowych duplikatów nie blokuje PASS.** Do raportu trafia `false_boards`, ale pomijany jest `duplicate_predictions`. Metryka bazowa klasyfikuje dodatkową detekcję dopasowaną do już zajętej planszy jako duplikat, nie fałszywą planszę (`services/worker/src/game_predictor_worker/geometry_core/metrics.py:186`). Dziewięć poprawnych plansz plus duplikat zachowuje więc liczniki poprawności i image-macro; bramka `NON_REGRESSION` nie wykrywa pogorszenia. Jest to sprzeczne z kontraktem nadmiarowych detekcji w `ai_docs/tasks/0997-grid-model-evaluation.md:91`. Należy uwzględnić duplikaty w wersjonowanym raporcie i bramce, zachowując znaczenie istniejących metryk.

### P1

Brak.

### P2

- [P2-1] `services/worker/src/game_predictor_worker/images/grid_model_evaluation_handler.py:307` — Wznowienie pomija ukończone jednostki bez sprawdzenia istnienia i SHA plików `detail`. Usunięty lub uszkodzony plik wyników może pozostać wskazany przez raport ukończony po restarcie. Warto weryfikować zapisane artefakty przed ich ponownym użyciem albo jawnie odnotować brak takiej gwarancji.

- [P2-2] `apps/admin/src/features/model-quality/grid-model-comparison.tsx:77` — Odpowiedzi `refresh` i `open` nie są związane z aktualnym wyborem kandydata. Opóźniona odpowiedź dla A może nadpisać listę lub szczegół po wybraniu B; reset stanu w efekcie tego nie zabezpiecza. Należy odrzucać nieaktualne odpowiedzi według generacji żądania lub identyfikatora wyboru.

- [P2-3] `apps/admin/src/features/model-quality/grid-model-comparison.tsx:115` — Klucz idempotencji pozostaje po utraconej odpowiedzi, również po zmianie kandydata lub kohort. Jeśli pierwsze żądanie zostało zapisane, zmieniony formularz stale otrzymuje `GRID_EVALUATION_IDEMPOTENCY_CONFLICT` aż do ponownego zamontowania panelu. Klucz należy powiązać z dokładną treścią polecenia: zachowywać przy ponowieniu tej samej treści i zmieniać dla nowej.

- [P2-4] `apps/admin/src/features/model-quality/grid-model-evaluation-state.ts:18` — Etykieta PASS „Kandydat lepszy we wszystkich grach” zawyża wynik. Polityka wymaga poprawy tylko gry treningowej; pozostałe gry mogą zachować identyczny wynik. Należy opisać PASS jako poprawę gry treningowej bez regresji pozostałych.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Regresja dowolnej gry blokuje wspólny PASS | niespełnione | Bramka agreguje gry w `services/api/src/game_predictor_api/domain/grid_model_evaluation.py:218`, ale pomija regresję duplikatów — P0-2. |
| Brak detekcji ma koszt | spełnione | `services/worker/src/game_predictor_worker/geometry_core/metrics.py:163`: koszt 1 dla niedopasowanej etykiety; pomiar wywoływany w `training_core/grid_evaluation.py:99`. |
| Brak danych, parity lub aktualnych dowodów blokuje publikację | niespełnione | Pokrycie i parity sprawdzane w `domain/grid_model_evaluation.py:179`; brak aktualnego bindingu po usunięciu partycji nie jest wykrywany — P0-1. |
| Dobór checkpointu nie używa REGRESSION | spełnione | `services/worker/src/game_predictor_worker/images/grid_training_child.py:391`: dane TRAIN i VALIDATION; REGRESSION występuje w odrębnym evaluatorze. |
| Wyniki kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu | niezweryfikowane | `ai_docs/tasks/0997-grid-model-evaluation.md:164` zawiera deklarowane wyniki; pełne zestawy pozostają zapowiedziane w linii 169. Testów nie uruchamiano niezależnie. |

## Listy zamknięte i otwarte

Zamknięte: Brak. Pierwsza runda.

Otwarte: P0-1, P0-2, P2-1, P2-2, P2-3, P2-4.

## Proponowane testy

- W `services/api/tests/integration/test_grid_model_evaluation_e2e_postgres.py` dodać dwie rzeczywiste kohorty różnych gier i wspólny raport. Po usunięciu jednej gry przez lifecycle sprawdzić blokadę publikacji, default i nowej aktywacji. W tej samej izolowanej konfiguracji PostgreSQL sprawdzić brak drugiego bindingu oraz restart między bindingami. Komenda: `.\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_grid_model_evaluation_e2e_postgres.py`.
- W `services/worker/tests/test_grid_model_evaluation.py` dodać poprawę gry treningowej oraz dodatkowy duplikat detekcji w REGRESSION drugiej gry. Oczekiwany wynik: brak PASS. Dodać też wznowienie po usunięciu lub zmianie pliku `detail`. Komenda: `.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_grid_model_evaluation.py`.
- W testach interakcji panelu odtworzyć odwróconą kolejność odpowiedzi A/B oraz utratę odpowiedzi po zapisaniu joba i późniejszą zmianę formularza. Komenda: `npm run test:geometry --workspace @game-predictor/admin`.

## Zakres przeglądu i ograniczenia

Przeczytano brief, task, wskazane reguły oceny i decyzje D-483/D-559, nowe moduły domeny, aplikacji, storage, workera, migrację 0166, API, schematy, panel oraz testy. Sprawdzono zależne mechanizmy metryk, kwalifikacji kohort, SQL bindingu i usuwania partycji.

`git diff --check` zakończył się kodem 0; wystąpiły ostrzeżenia o konwersji LF/CRLF. Nie wykonywano testów, rzeczywistego inference, migracji ani kontroli w przeglądarce. Wyniki zapisane przez wykonawcę pozostają deklaracjami z Outcome; opisane przypadki błędne wynikają z analizy statycznej.