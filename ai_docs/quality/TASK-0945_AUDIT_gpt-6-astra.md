# Audyt TASK-0945 - Migracja 0153, status `reverted` i cofnięcie korekty slotu odroczonego

Werdykt: REVISE
Audytor: Codex (`gpt-6-astra`, `high` — oznaczenie briefu)
Wykonawca: `claude-opus-5-5`, `high`
Zakres: HEAD...3879af42cc96fca5f8526e99d030700945ff801d oraz zmiany niezacommitowane, data 2026-10-09
Runda: 2

Przegląd statyczny, bez zmian w plikach. Audytor nie uruchamiał testów ani migracji.

## Streszczenie

Poprawki zamykają trzy znaleziska P0 z pierwszej rundy: obsługę historycznych korekt, współbieżną idempotencję i zniknięcie korekty podczas listowania. Uzupełniono większość brakujących testów odmowy. P1-1 pozostaje częściowo otwarte: nadal brakuje wymaganego scenariusza odmowy z powodu powiązania z kohortą treningową.

## Znaleziska

### P0

Brak.

### P1

- [P1-1] `services/api/tests/integration/test_geometry_correction_revert_refusals_postgres.py:388` — **Niepełne zamknięcie wymaganych testów odmowy.** Nowy test `test_a_pinned_board_refuses_the_revert` tworzy wyłącznie `image_symbol_prediction_revisions`. Żaden test cofnięcia nie tworzy powiązania z `verified_training_cohort_items` ani `verified_training_cohort_cells`, mimo scenariusza „kohorta” wymaganego w `ai_docs/tasks/0945-geometry-correction-revert-pending-slot.md:92` i wskazanego w pierwszym raporcie. Test predykcji nie sprawdza odrębnych zapytań chroniących kohortę oraz przepinanych sąsiadów. Należy dodać test PostgreSQL z rzeczywistym powiązaniem kohorty, sprawdzeniem kodu odmowy i porównaniem stanu przed operacją oraz po niej, obejmującym także rekordy kohorty.

### P2

Brak.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Upgrade/downgrade 0153 i odmowa utraty historii | niezweryfikowane | Strażniki migracji oraz test `services/api/tests/integration/test_geometry_correction_revert_pending_postgres.py:508`. Wynik wykonawcy nie był odtwarzany. |
| Odtworzenie slotu, grafu danych, sąsiadów, liczników, wyszukiwarki, joba i bramki | spełnione | Statycznie: porównanie migawek w `services/api/tests/integration/test_geometry_correction_revert_pending_postgres.py:342`, z jawnym wyłączeniem pól czasowych i liczników monotonicznych. |
| Powrót do `correction` z poprzednią propozycją geometrii | spełnione | `services/api/tests/integration/test_geometry_correction_revert_pending_postgres.py:364`. |
| Wymagane odmowy bez zapisu | niespełnione | P1-1: brak scenariusza kohorty. Pozostałe uzupełnienia obejmują rozstrzygnięcie pozycji, przejęcie sekwencji i komórek, predykcję oraz odmowę przypadku A. |
| Ponowny zapis identycznej geometrii tworzy nową rewizję | spełnione | `services/api/tests/integration/test_geometry_correction_revert_pending_postgres.py:411`; sprawdzana jest również deduplikacja workera. |
| Idempotencja cofnięcia i odmowa ponowienia starego zapisu | spełnione | Blokada przed odczytem audytu: `services/api/src/game_predictor_api/storage/geometry_correction_revert_repository.py:502`; test współbieżności: `services/api/tests/integration/test_geometry_correction_revert_refusals_postgres.py:182`; stary zapis: `services/api/tests/integration/test_geometry_correction_revert_pending_postgres.py:406`. |
| Dotychczasowe testy kompletności i korekty przechodzą bez zmian asercji | niezweryfikowane | Diff zachowuje asercje. `Outcome` deklaruje 42 passed; audyt nie uruchamiał testów. |

## Listy zamknięte i otwarte

Zamknięte:

- **P0-1:** historyczna korekta bez rewizji źródła otrzymuje `NOT_SUPPORTED`, zachowując pozostałe wpisy listy — `services/api/src/game_predictor_api/storage/geometry_correction_revert_repository.py:455`. Test regresyjny: `services/api/tests/integration/test_geometry_correction_revert_refusals_postgres.py:74`.
- **P0-2:** żądania z tym samym kluczem są serializowane przed pierwszym odczytem — `services/api/src/game_predictor_api/storage/geometry_correction_revert_repository.py:502`. Test dwóch połączeń: `services/api/tests/integration/test_geometry_correction_revert_refusals_postgres.py:182`.
- **P0-3:** korekta usunięta między odczytami jest pomijana — `services/api/src/game_predictor_api/storage/geometry_correction_revert_repository.py:453`. Test regresyjny: `services/api/tests/integration/test_geometry_correction_revert_refusals_postgres.py:237`.

Otwarte: **P1-1**, ograniczone do brakującego scenariusza kohorty.

`REOPENED_RESOLUTION` pozostaje pokryte testem domenowym. Odroczenie testu operacji PostgreSQL do TASK-0946 jest zgodne z wyłączeniem implementacji przypadku A; obecne `revert` odmawia tego przypadku przez `NOT_SUPPORTED`.

## Proponowane testy

W `services/api/tests/integration/test_geometry_correction_revert_refusals_postgres.py` dodać scenariusz powiązania cofanej planszy lub jej komórki z kohortą. Sprawdzić odmowę bez usunięcia danych i bez wpisu audytu. Uwzględnić także kohortę komórki sąsiada, która blokuje odwrotne przepięcie.

Po uzupełnieniu uruchomić na bazie `*_test`, z konfiguracją `PYTHONPATH` opisaną w tasku i limitem 120 sekund:

```powershell
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
..\..\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_geometry_correction_revert_refusals_postgres.py -q
```

## Zakres przeglądu i ograniczenia

Sprawdzono brief, wcześniejszy raport, opis poprawek, właściwe fragmenty planu i dokumentacji, migrację 0153, manifest v7, modele, domenę, serwis, repozytorium, zmiany zapytań „latest”, strażnik ponowień oraz testy cofnięcia.

Ocena zamknięcia uwag wynika z analizy kodu i testów. Wyniki wykonawcy, w tym 55 passed po poprawkach, nie zostały niezależnie odtworzone. Nie wykonywano zmian plików, operacji na bazie ani uruchamiania usług.