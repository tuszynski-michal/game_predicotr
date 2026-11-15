# Audyt TASK-1209 - Akceptacja V3 dla wiązań z brakującymi slotami

Werdykt: REVISE
Audytor: Codex, reasoning high według zlecenia
Wykonawca: Claude Opus 5.5, reasoning high
Zakres: 08c3a4db...3abece5808add4fb49eb095256560bf9f9b90f1a oraz zmiany niezacommitowane wskazane w briefie, data 2026-11-15
Runda: 1
SHA pakietu: 023341D434360871B4BC7E8FA8E900636A7305519FB417937B06C4DBA12A2145
Otwarte P0: 1
Otwarte P1: 0

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Sprawdzono kwalifikację V3, jej trzy repozytoria, powiązaną bramkę cięcia oraz testy i dokumentację D-615. Rozróżnienie pozycji przypisanych i brakujących jest zaimplementowane poprawnie w kwalifikacji. Pozostaje jednak sprzeczność z decyzją operatora o zachowaniu D-484: niekompletne zdjęcie może otrzymać nowe komórki do weryfikacji symboli przed uzupełnieniem brakującej planszy.

## Znaleziska

### P0

- [P0-1] `services/api/tests/integration/test_v3_engine_acceptance_postgres.py:817` — test utrwala materializację 15 komórek symboli przy brakującym slocie, mimo że poprzednia asercja potwierdza `geometry_incomplete`. `after[6]` zawiera rekordy `ImageSymbolReviewCellModel` (`services/api/tests/integration/test_v3_engine_acceptance_postgres.py:443`); fixture rozpoczyna od odroczonych pozycji, bez wcześniejszych plansz i komórek. Przyczyną jest dopuszczenie częściowego wiązania w `services/api/src/game_predictor_api/domain/neural_crop_policy.py:113`, które przez `full_neural_prediction_geometry` uruchamia istniejące pominięcie blokady w `services/api/src/game_predictor_api/storage/image_geometry_completeness_state_repository.py:499`. Przypisana plansza omija więc bramkę niekompletnego zdjęcia. Narusza to doprecyzowanie D-615 w `ai_docs/process/decisions/DECISION_LOG_2026.md:39`: całe zdjęcie ma przejść do cięcia i symboli dopiero po zapisaniu brakującej planszy. Należy zachować akceptację przypisanych pozycji, ale zablokować nową materializację symboli dla tego niekompletnego zdjęcia. Test powinien oczekiwać zera nowych komórek przed ręcznym uzupełnieniem oraz ich utworzenia po uzupełnieniu, z zachowaniem istniejących danych przy ponowieniu.

### P1

Brak.

### P2

Brak.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Przypisane pozycje akceptowane, rewizja `accepted`, brakująca pozycja pozostaje `pending` | spełnione | Statycznie: `services/api/src/game_predictor_api/domain/v3_engine_acceptance.py:178`; asercje integracyjne: `services/api/tests/integration/test_v3_engine_acceptance_postgres.py:813` oraz `:832`. |
| Odroczona pozycja przypisana nadal blokuje akceptację | spełnione | `services/api/src/game_predictor_api/domain/v3_engine_acceptance.py:190`; test: `services/api/tests/test_partial_slot_binding.py:346`. |
| Pełne wiązania zachowują dotychczasową kwalifikację | spełnione | Dla pustego zbioru braków warunki pozostają równoważne: `services/api/src/game_predictor_api/domain/v3_engine_acceptance.py:178`; testy: `services/api/tests/test_v3_engine_acceptance.py:63` oraz `:93`. |
| Zachowanie D-484 zgodnie z doprecyzowaniem operatora | niespełnione | P0-1; `services/api/tests/integration/test_v3_engine_acceptance_postgres.py:817`. |
| Wykonanie wymaganych testów jednostkowych i PostgreSQL | niezweryfikowane | Brief nie zawiera wyników weryfikacji wykonawcy; audyt nie uruchamiał testów. |

## Listy zamknięte i otwarte

Zamknięte: Brak.

Otwarte: P0-1.

## Proponowane testy

- W `services/api/tests/integration/test_v3_engine_acceptance_postgres.py` rozszerzyć scenariusz brakującego slotu: akceptacja przypisanej planszy, brak nowych komórek symboli przed uzupełnieniem, ręczne zapisanie brakującej planszy, następnie kompletność i materializacja wszystkich pozycji. Sprawdzić ponowienie przez nową sesję po utracie odpowiedzi. Polecenie po poprawce: `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_v3_engine_acceptance_postgres.py`.
- Uruchomić regresje domenowe: `.\.venv\Scripts\python.exe -m pytest services/api/tests/test_partial_slot_binding.py services/api/tests/test_v3_engine_acceptance.py services/api/tests/test_neural_auto_crop_v2.py`.

## Zakres przeglądu i ograniczenia

Przeczytano brief, aktywne zadanie, plan, wymagane dokumenty procesu, D-615, właściwe fragmenty wymagań i architektury oraz kod i testy objęte zmianą. Prześledzono również konsumenta bramki kompletności, wywołanie finalizacji w pipeline i fixture PostgreSQL w celu oceny P0-1.

Nie uruchamiano testów, usług, migracji ani operacji na bazie. Ocena kryteriów oznaczonych jako spełnione dotyczy analizy statycznej; nie potwierdza wykonania testów ani działania po restarcie procesu.