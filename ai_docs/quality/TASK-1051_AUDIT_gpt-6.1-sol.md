# Audyt TASK-1051 — Kwalifikacja przycinania dla importów oczekujących na przegląd

Werdykt: REVISE
Audytor: gpt-6.1-sol / high
Wykonawca: claude-opus-5-5 / high
Zakres: HEAD...dda8ed3b5e2e6ccc4a258054ce88c007487b1132 oraz niezacommitowane zmiany wskazane w briefie, data 2026-10-18
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano kwalifikację domenową, odczyt statusu importu przez repozytorium PostgreSQL, testy, etykiety Admina oraz zgodność z D-563 i planem. Implementacja dopuszcza właściwe dwa statusy i zachowuje pozostałe warunki kwalifikacji. Werdykt blokują brak pełnego pokrycia PostgreSQL, wymagana aktualizacja dokumentacji API oraz brak udokumentowanej weryfikacji odbiorczej.

## Znaleziska

### P0

Brak.

### P1

- [P1-1] `services/api/tests/integration/test_source_image_crops_postgres.py:405` — Test PostgreSQL obejmuje `waiting_for_review`, `cancelled` oraz domyślne `completed`, ale pomija importy `created`, `processing` i `failed`. Testy domenowe tych statusów nie zastępują wymaganego pokrycia integracyjnego. Należy dodać przypadki dla wszystkich sześciu statusów i sprawdzać obecność `IMPORT_NOT_SETTLED` dla czterech wykluczanych. Przypadki aktywnych importów należy izolować, aby ich wpływ na `ACTIVE_IMAGE_JOB` nie przesłaniał badanego warunku.

- [P1-2] `services/api/src/game_predictor_api/domain/source_crop_eligibility.py:36` — Zmieniono emitowany kod wykluczenia, ale nie zaktualizowano wymaganej dokumentacji `API_CONTRACT.md`. Sekcja opisująca `exclusionCounts` (`ai_docs/architecture/API_CONTRACT.md:3033`) nie dokumentuje `IMPORT_NOT_SETTLED`, dopuszczanych statusów ani znaczenia historycznego `IMPORT_NOT_COMPLETED`. Należy uzupełnić kontrakt zgodnie z zakresem taska. Pole odpowiedzi pozostaje słownikiem, więc sam brak zmiany schematu OpenAPI nie stanowi tutaj błędu.

- [P1-3] `ai_docs/tasks/1051-crop-eligibility-waiting-imports.md:72` — `Outcome` pozostaje pusty, a brief nie przekazuje wyników weryfikacji. Brakuje zwłaszcza wymaganego porównania 40 blobów P1 na bazie testowej oraz wyników lint, mypy i testów. Nie można potwierdzić odbioru zmiany wpływającej na kwalifikację do usuwania oryginałów. Przed commitem należy wykonać wymagane kontrole i zapisać komendy, wyniki oraz porównanie P1 z powodami ewentualnych wykluczeń. To brak dowodu weryfikacji, nie stwierdzenie, że testy zakończyły się błędem.

### P2

Brak.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Testy domenowe każdego statusu importu | spełnione | Cztery statusy wykluczane: `services/api/tests/test_source_crop_eligibility.py:76`; dwa dopuszczane: `services/api/tests/test_source_crop_eligibility.py:160`. Potwierdzono obecność testów, bez uruchamiania. |
| Testy PostgreSQL każdego statusu importu | niespełnione | `services/api/tests/integration/test_source_image_crops_postgres.py:401` — brak przypadków importu `created`, `processing`, `failed`; P1-1. |
| 40 blobów P1 przechodzi albo otrzymuje powód inny niż status importu | niezweryfikowane | `ai_docs/tasks/1051-crop-eligibility-waiting-imports.md:55` i pusty `Outcome` pod linią 70; P1-3. |
| Lint, mypy i testy ukierunkowane przechodzą | niezweryfikowane | Brak wyników w `ai_docs/tasks/1051-crop-eligibility-waiting-imports.md:72` i briefie. |
| Audyt zamknięty | niespełnione | Otwarte P1-1, P1-2 i P1-3. |

## Listy zamknięte i otwarte

Zamknięte (tylko w rundzie 2 lub później): Brak.

Otwarte: P1-1, P1-2, P1-3.

## Proponowane testy

- Uzupełnić `services/api/tests/integration/test_source_image_crops_postgres.py` o brakujące statusy importu. Uruchomić na izolowanych bazach testowych: `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'`, następnie `D:\game_predicotr\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_source_image_crops_postgres.py`.
- Uruchomić testy domeny: `D:\game_predicotr\.venv\Scripts\python.exe -m pytest services/api/tests/test_source_crop_eligibility.py`.
- Wykonać porównanie 40 blobów P1 wymagane w `ai_docs/tasks/1051-crop-eligibility-waiting-imports.md:55`: odczyt kwalifikacji na przygotowanej bazie testowej, z wynikiem dla każdego bloba. Brief nie zawiera gotowej komendy tego porównania.

## Zakres przeglądu i ograniczenia

Przeczytano brief, aktywny task, właściwe fragmenty planu i decyzji D-562/D-563, dokumentację procesu, kontraktu i modelu danych oraz zmienione pliki. Prześledzono przekazywanie statusu z PostgreSQL do kwalifikacji domenowej i wyszukano użycia starego oraz nowego kodu.

Nie uruchamiano testów, lint, mypy, usług ani operacji bazodanowych. Nie potwierdzono wyników na 40 blobach P1. Wznowienie importu z TASK-1052 i operacje na danych operatora pozostają poza zakresem audytu.