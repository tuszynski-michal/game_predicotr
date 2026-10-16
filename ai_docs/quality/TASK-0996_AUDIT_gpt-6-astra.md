# Audyt TASK-0996 - Trwały trening V3 w aplikacji

Werdykt: PASS
Audytor: Codex, etykieta briefu `gpt-6-astra`, reasoning `high`
Wykonawca: `claude-opus-5-5`, reasoning `high`
Zakres: HEAD...9b6b25dce9a2670afb3b4abcbe8b3e1b88d1a6f5 oraz zmiany niezacommitowane wskazane w briefie, data 2026-10-16
Runda: 5

Przegląd statyczny, bez zmian w plikach.

## Streszczenie

Sprawdzono poprawki po R4 oraz powiązane ścieżki treningu, rozliczania budżetu, wznowienia i odzyskiwania eksportu. Poprawki zamykają P0-2 i P0-4: licznik uwzględnia zakończone kroki, a odzyskiwanie eksportu sprawdza preset względem przypiętej receptury. Nie stwierdzono otwartych P0 ani P1 w przejrzanym zakresie. Integracja `SqlGridTrainingStore` z PostgreSQL pozostaje ograniczeniem weryfikacji odnotowanym przez wykonawcę.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

Brak.

## Pokrycie kryteriów akceptacji

Ocena „spełnione” oznacza zgodność stwierdzoną statycznie w kodzie i testach; wyników testów nie odtwarzano.

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Restart odtwarza RNG, sampler i optymalizator | spełnione | `services/worker/src/game_predictor_worker/training_core/grid_training.py:333`; test przerwania przed pierwszą oceną i po niej: `services/worker/tests/test_durable_v3_grid_training.py:109`. |
| Crash po eksporcie nie dubluje wersji | spełnione | Deterministyczne identyfikatory i utrwalony deskryptor: `services/worker/src/game_predictor_worker/images/grid_training_handler.py:154`, `services/worker/src/game_predictor_worker/images/grid_training_handler.py:854`; test: `services/worker/tests/test_grid_training_handler.py:302`. |
| Uszkodzony wskazany checkpoint nie daje kandydata | spełnione | `services/worker/src/game_predictor_worker/images/grid_training_handler.py:510`; test: `services/worker/tests/test_grid_training_handler.py:321`. |
| Odzyskiwany eksport zachowuje integralność | spełnione | Kontrola presetu, odcisków i sum plików: `services/worker/src/game_predictor_worker/images/grid_training_handler.py:443`; regresja: `services/worker/tests/test_grid_training_handler.py:666`. |
| Budżet pozostaje trwały po błędzie i wznowieniu | spełnione | Aktualizacja licznika po kroku: `services/worker/src/game_predictor_worker/images/grid_training_child.py:184`; rozliczenie potwierdzonego wyniku: `services/worker/src/game_predictor_worker/images/grid_training_handler.py:685`. |
| Cancel zostaje potwierdzony po zatrzymaniu trenera | spełnione | `services/worker/src/game_predictor_worker/images/grid_training_handler.py:666`; test magazynu: `services/api/tests/integration/test_grid_training_lane_migration_postgres.py:163`. |
| Grid-only zamraża detektor i BatchNorm | spełnione | `services/worker/src/game_predictor_worker/training_core/grid_training.py:82`; regresja: `services/worker/tests/test_durable_v3_grid_training.py:230`. |
| Laboratorium i aplikacja używają zgodnej logiki | spełnione | Reeksport wspólnej sieci: `services/worker/src/game_predictor_worker/vision_lab/neural_grid_model.py:3`; regresje strat i przygotowania danych: `services/worker/tests/test_durable_v3_grid_training.py:256`, `services/worker/tests/test_durable_v3_grid_training.py:345`. |
| Wyniki kontroli i ograniczenia zapisano w Outcome | spełnione | Poprawki R4 i wynik 29 testów: `ai_docs/tasks/0996-durable-v3-grid-training.md:126`; dowody wcześniejszego E2E: `ai_docs/tasks/0996-durable-v3-grid-training.md:148`. |
| Dokumentacja opisuje trwały run bez automatycznej publikacji lub aktywacji | spełnione | `ai_docs/architecture/VISION_LAB.md:769`; rejestracja `not_evaluated`: `services/worker/src/game_predictor_worker/images/grid_training_handler.py:792`. |

## Listy zamknięte i otwarte

Zamknięte:

- **P0-2 z R4:** `progress()` aktualizuje licznik przed ograniczeniem częstotliwości zapisu postępu, a publikacja checkpointu również go aktualizuje. Wynik błędu otrzymuje ten licznik. Dowody: `services/worker/src/game_predictor_worker/images/grid_training_child.py:179`, `services/worker/src/game_predictor_worker/images/grid_training_child.py:330`; test: `services/worker/tests/test_grid_training_child.py:314`.
- **P0-4 z R4:** odzyskiwanie eksportu bez wyniku wymaga identycznych bajtów `preset.json` i przypiętej receptury oraz zgodnych odcisków w bundle i provenance. Dowód: `services/worker/src/game_predictor_worker/images/grid_training_handler.py:443`; test odrzucenia zmienionego presetu: `services/worker/tests/test_grid_training_handler.py:684`.

Otwarte: Brak.

## Proponowane testy

- Opcjonalnie rozszerzyć `services/worker/tests/test_grid_training_child.py` o wymuszony błąd parity po N rzeczywistych krokach i sprawdzenie `steps=N` w zapisanym wyniku. Obecny test sprawdza aktualizację licznika bez pełnej ścieżki błędu eksportu. Komenda: `.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_grid_training_child.py services/worker/tests/test_grid_training_handler.py`.

## Zakres przeglądu i ograniczenia

Przeczytano brief, raport R4, task i Outcome, fragment planu, właściwe wymagania i architekturę. Przejrzano nadzorcę, trenera, rdzeń treningowy, checkpointy, adaptery danych, API, migrację, zmiany obsługi jobów, wrapper klienta i powiązane testy. Odczytano również artefakt wcześniejszego E2E GPU.

Nie uruchamiano testów, treningu, migracji ani usług. Wyniki wykonawcy nie zostały niezależnie odtworzone. Test E2E korzysta z zastępczego magazynu katalogu; nie potwierdza pełnej integracji `SqlGridTrainingStore` z PostgreSQL. PASS dotyczy przeglądu statycznego wskazanych zmian.