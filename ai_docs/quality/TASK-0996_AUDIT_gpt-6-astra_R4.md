# Audyt TASK-0996 — Trwały trening V3 w aplikacji

Werdykt: REVISE
Audytor: Codex, etykieta briefu `gpt-6-astra`, reasoning `high`
Wykonawca: `claude-opus-5-5`, reasoning `high`
Zakres: HEAD...9b6b25dce9a2670afb3b4abcbe8b3e1b88d1a6f5 oraz zmiany niezacommitowane wskazane w briefie, data 2026-10-16
Runda: 4

Przegląd statyczny, bez zmian w plikach.

## Streszczenie

Sprawdzono poprawki po R3 oraz ich powiązania z trenerem, checkpointami, magazynem jobów i rejestracją kandydata. Naprawiono przedwczesne potwierdzanie anulowania, zapis początku naliczania czasu i odzyskiwanie eksportu bez pliku wyniku. Pozostają dwa błędy: zaniżony licznik kroków po obsłużonym błędzie trenera oraz przyjmowanie uszkodzonego presetu podczas odzyskiwania eksportu.

## Znaleziska

### P0

- **[P0-2] `services/worker/src/game_predictor_worker/images/grid_training_child.py:328` — Końcowy licznik przy błędzie nadal może zwracać wykonany krok do budżetu.** `counter["step"]` jest aktualizowany wyłącznie przed krokiem (`:137`). `progress()` i publikacja checkpointu nie aktualizują go. Po wykonaniu N kroków licznik pozostaje więc równy N−1, dopóki nie rozpocznie się następna iteracja. Jeśli eksport zgłosi obsługiwany `ChildError`, np. `GRID_TRAINING_ONNX_PARITY_FAILED`, wynik błędu otrzyma `steps=N−1`. Nadzorca uzna tę wartość za wiarygodną i zmniejszy rezerwację (`images/grid_training_handler.py:680`). Przykładowo po 40 wykonanych krokach i błędzie parity budżet zostanie rozliczony do 39, mimo checkpointu kroku 40. Należy aktualizować licznik po każdym zakończonym kroku, niezależnie od ograniczania częstotliwości zapisu postępu, i zwalniać rezerwację tylko na podstawie potwierdzonego końcowego licznika.

- **[P0-4] `services/worker/src/game_predictor_worker/images/grid_training_handler.py:437` — Nowe odzyskiwanie eksportu pomija weryfikację integralności `preset.json`.** `bundle["files"]` zawiera sumy tylko `screen.onnx`, `board.onnx` i `weights.pt` (`images/grid_training_child.py:501`). Funkcja dodaje kontrolę checkpointu, ale dla `preset.json` jedynie oblicza nową sumę zastanego pliku (`images/grid_training_handler.py:456`). Po awarii przed zapisem wyniku zmieniony lub uszkodzony preset może zatem zostać przyjęty, zainstalowany i zarejestrowany z nową sumą jako poprawny artefakt. Inspektor katalogu porównuje plik z tym nowo utworzonym deskryptorem, więc nie wykryje pierwotnej zmiany. Jest to regresja ochrony P0-4 w nowej ścieżce odzyskiwania. Należy sprawdzać preset względem niezależnie przypiętej receptury i jej odcisku, analogicznie do `_verify_recovered()`, przed utworzeniem deskryptora eksportu.

### P1

Brak.

### P2

Brak.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Restart odtwarza RNG, sampler i optymalizator | spełnione | `services/worker/src/game_predictor_worker/training_core/grid_training.py:333`; test porównawczy `services/worker/tests/test_durable_v3_grid_training.py:109`. Ocena statyczna. |
| Crash po eksporcie nie dubluje wersji | spełnione | Deterministyczne identyfikatory i utrwalony deskryptor: `services/worker/src/game_predictor_worker/images/grid_training_handler.py:152`, `:855`. |
| Uszkodzony wskazany checkpoint nie daje kandydata | spełnione | `services/worker/src/game_predictor_worker/images/grid_training_handler.py:505`; kontrola zawartości i bindingu w `training_core/grid_training.py:334`. |
| Integralność odzyskiwanego eksportu | niespełnione | P0-4: pominięta kontrola presetu w odzyskiwaniu bez pliku wyniku. |
| Trwały budżet kroków i czasu | niespełnione | Początek naliczania czasu utrwalany w `services/worker/src/game_predictor_worker/images/grid_training_handler.py:523`; pozostaje P0-2. |
| Cancel potwierdzany po zatrzymaniu trenera | spełnione | `services/worker/src/game_predictor_worker/images/grid_training_handler.py:663`, `:687`; test magazynu `services/api/tests/integration/test_grid_training_lane_migration_postgres.py:163`. |
| Zamrożenie detektora i BatchNorm w grid-only | spełnione | `services/worker/src/game_predictor_worker/training_core/grid_training.py:82`, `:380`. |
| Zgodna logika laboratorium i aplikacji | spełnione | Wspólne moduły i reeksporty; regresje `services/worker/tests/test_durable_v3_grid_training.py:256`, `:345`. |
| Wyniki kontroli i ograniczenia zapisane w Outcome | spełnione | `ai_docs/tasks/0996-durable-v3-grid-training.md:143`; aktualny artefakt `artifacts/audits/TASK-0996_GPU_E2E.json:7`. |
| Dokumentacja odpowiada zachowaniu | niespełnione | Deklaracje trwałego budżetu i integralności ograniczają P0-2 oraz P0-4. |
| Brak automatycznej publikacji i aktywacji | spełnione | Rejestracja `not_evaluated`: `services/worker/src/game_predictor_worker/images/grid_training_handler.py:787`. |

## Listy zamknięte i otwarte

Zamknięte:

- **P0-6:** wynik jest zapisywany przed zwolnieniem GPU (`images/grid_training_child.py:329`); kompletny eksport można odzyskać bez wyniku i nowego budżetu (`images/grid_training_handler.py:267`). Odrębny brak kontroli presetu opisuje ponownie otwarte P0-4.
- **P0-7:** zapis postępu zachowuje oczekujący cancel; potwierdzenie następuje po zatrzymaniu dziecka (`images/grid_training_handler.py:663`, `:687`).
- **P0-8:** `chargedAt` zostaje utrwalone przed uruchomieniem dziecka (`images/grid_training_handler.py:523`).
- **P2-1:** Outcome rozdziela kolejne przebiegi E2E; dane ostatniego przebiegu odpowiadają aktualnemu artefaktowi (`ai_docs/tasks/0996-durable-v3-grid-training.md:145`).
- **P0-1, P0-3, P0-5, P1-1, P1-2, P1-3:** zachowano wcześniejsze poprawki: utrwalony deskryptor, watchdog, kolejność odzyskiwania, checkpoint przy przerwaniu, przypiętą recepturę i dokładną idempotencję tworzenia runu.

Otwarte: **P0-2, P0-4**.

## Proponowane testy

- W `services/worker/tests/test_grid_training_child.py` wymusić błąd eksportu po N rzeczywiście wykonanych krokach. Wynik błędu musi zawierać `steps=N`. W teście nadzorcy sprawdzić, że rozliczenie i wznowienie zachowują pełne zużycie.
- W `services/worker/tests/test_grid_training_handler.py` rozszerzyć odzyskiwanie eksportu bez wyniku o uszkodzony oraz poprawny składniowo, lecz zmieniony `preset.json`. Oba przypadki muszą zakończyć się bez rejestracji kandydata.

Komenda po poprawkach:

`.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_grid_training_child.py services/worker/tests/test_grid_training_handler.py`

## Zakres przeglądu i ograniczenia

Przeczytano brief, task, raporty wcześniejszych rund, właściwe fragmenty planu i dokumentacji oraz kod nadzorcy, trenera, rdzenia treningowego, checkpointów, API, migracji, magazynu jobów i inspektora katalogu. Sprawdzono testy poprawek, test żądań klienta oraz aktualny artefakt E2E.

Nie uruchamiano testów, treningu, migracji ani usług. Wyniki wykonawcy nie zostały niezależnie odtworzone. Integracja `SqlGridTrainingStore` z PostgreSQL pozostaje ograniczeniem zapisanym w Outcome; test E2E używa zastępczego magazynu katalogu.