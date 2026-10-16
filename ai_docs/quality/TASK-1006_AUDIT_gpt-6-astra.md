# Audyt TASK-1006 - Kandydat wspólnej geometrii Mumii i 777a2

Werdykt: PASS
Audytor: Codex `gpt-6-astra`, reasoning `high`
Wykonawca: Claude Code `claude-opus-5-5`, reasoning `high`
Zakres: HEAD...88b2ab823d466ad5f43f27c2653fc04bb2f6d0b9 oraz zmiany niezacommitowane wskazane w briefie, data 2026-10-16
Runda: 1

Przegląd statyczny, bez zmian w plikach.

## Streszczenie

Sprawdzono politykę wspólnej kohorty, tworzenie runu, nadzorcę, sampler, ocenę oraz powiązane testy i dokumentację. Nie stwierdzono otwartych problemów P0 ani P1. Pozostają dwa ograniczenia dotyczące kompletności przypięcia planu i bezpośredniego testowania nowej odmowy API. Werdykt dotyczy implementacji, nie jakości modelu na danych operatora.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `services/api/src/game_predictor_api/domain/shared_grid_model_candidate.py:134` — SHA planu obejmuje manifesty oraz liczby zdjęć i nagrań, ale nie przypisanie źródeł do nagrań przekazywane osobno trenerowi. Zmiana tego przypisania zachowująca liczby nie zmieni SHA, mimo że zmieni działanie samplera. Niezmienność rekordów kohorty i kontrola kwalifikacji ograniczają ryzyko w normalnym przepływie. Zalecane jest dodanie do planu skrótu uporządkowanego przypisania `sourceId → groupId` albo jawne odnotowanie, że jego integralność zapewnia baza, a nie SHA planu.

- [P2-2] `services/api/tests/test_shared_grid_model_candidate.py:193` — Test zakresu oceny sprawdza wyłącznie wynik pomocniczej metody `_trained_cohorts`. Nie wywołuje `create`, więc nie chroni bezpośrednio nowego warunku odrzucającego pominięcie lub podmianę dodatkowej kohorty. Sama kontrola w implementacji jest poprawna. Zalecane jest uzupełnienie testu o odmowę `GRID_EVALUATION_GAME_COHORT_REQUIRED` oraz brak utworzonego joba.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Duża gra nie dominuje | spełnione | Równa częstość próbkowania gier i nagrań: `services/worker/src/game_predictor_worker/training_core/grid_training.py:72`; test: `services/worker/tests/test_shared_grid_model_candidate.py:34`. |
| Alias kontrolny nie trafia do treningu drugiej gry | spełnione | Kontrola grup, bajtów i pikseli: `services/api/src/game_predictor_api/domain/shared_grid_model_candidate.py:95`; przypadek między grami: `services/worker/tests/test_shared_grid_model_candidate.py:226`. |
| Regresja blokuje publikację | spełnione | Wymaganie kohort treningowych: `services/api/src/game_predictor_api/application/grid_model_evaluation.py:241`; regresja drugiej gry daje REVISE: `services/worker/tests/test_grid_model_evaluation.py:278`; zachowana kontrola dowodów w usłudze publikacji. |
| Wynik nie przełącza gier automatycznie | spełnione | Rejestracja z `admission="not_evaluated"`: `services/worker/src/game_predictor_worker/images/grid_training_handler.py:858`; kontrola braku automatycznych operacji: `services/worker/tests/test_shared_grid_model_candidate.py:242`. |
| Kontrole, audyt i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu | niezweryfikowane | Outcome opisuje wyniki i niewykonany eksperyment. Wynik bieżącego audytu oczekuje na zapis przez wykonawcę; deklarowanych kontroli nie uruchamiano ponownie. |

## Listy zamknięte i otwarte

Zamknięte: Brak. Pierwsza runda audytu.

Otwarte: P2-1, P2-2. Mogą zostać poprawione albo odnotowane w Outcome jako zaakceptowane ryzyka.

## Proponowane testy

- W `services/worker/tests/test_shared_grid_model_candidate.py` dodać zmianę przypisania źródeł do istniejących nagrań bez zmiany ich liczby. Po wzmocnieniu przypięcia oczekiwać `GRID_SHARED_PLAN_DRIFT` przed uruchomieniem trenera.
- W `services/api/tests/test_shared_grid_model_candidate.py` sprawdzić `create` dla pominiętej i podmienionej kohorty dodatkowej oraz poprawnego pełnego zestawu.
- Uruchomienie po dodaniu przypadków: `.\.venv\Scripts\python.exe -m pytest services/api/tests/test_shared_grid_model_candidate.py services/worker/tests/test_shared_grid_model_candidate.py`, z limitem 120 sekund.

## Zakres przeglądu i ograniczenia

Przeczytano brief, wskazany zakres taska i planu, odpowiednie wymagania i decyzje, zmienione moduły API i workera oraz testy. Uzupełniająco sprawdzono kontrolę kwalifikacji kohort, ochronę nagrań, bramkę publikacji, wygenerowane typy klienta i zapisany artefakt GPU E2E.

Nie uruchamiano testów, usług, treningu ani operacji na bazie. Wyniki wykonawcy pozostają deklarowanymi wynikami weryfikacji; artefakt GPU dokumentuje przebieg syntetyczny, nie eksperyment na danych Mumii i 777a2. Raportu nie zapisano do pliku zgodnie z poleceniem przeglądu tylko do odczytu.