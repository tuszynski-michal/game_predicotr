# Audyt TASK-0933 - Wyprowadzanie serii supergry i API serii

Werdykt: REVISE
Audytor: Codex (etykieta briefu: gpt-6-astra, high)
Wykonawca: claude-opus-5-5, high
Zakres: HEAD...190644853b2db51d8e53137cc5704c6d0cb6ab99 oraz zmiany niezacommitowane wskazane w briefie, data 2026-10-09
Runda: 1

Przegląd statyczny, bez zmian w plikach. Audytor nie uruchamiał testów ani operacji zmieniających stan.

## Streszczenie

Sprawdzono wyprowadzanie serii, publikację generacji, wersjonowanie wejścia, migrację, API i testy. Implementacja zachowuje tożsamość serii oraz decyzje operatora podczas publikacji. Wykryto brak unieważniania wyników po zmianie długości sekwencji, błędną kompletność na jej końcu oraz braki w wymaganych testach i rozliczeniu zakresu kontraktu API.

## Znaleziska

### P0

- [P0-1] `services/api/src/game_predictor_api/storage/catalog_repository.py:236` — `save_game` podbija wersję wejścia wyłącznie po zmianie `super_game_kind`, mimo że zapisuje także `expected_layout_count`. Wyprowadzanie używa tej drugiej wartości jako granicy przejścia. Przykładowo zmniejszenie zakresu z 1000 do 500 pozostawia opublikowaną serię z triggerem 700 i stan `fresh = true`; nie powstaje również job usuwający tę serię. Zmiana podczas przeliczania nie powoduje odrzucenia kandydata. Należy objąć zmianę `expected_layout_count` transakcyjnym podbiciem wersji i kolejkowaniem, dopisać punkt wejścia oraz regresję.

- [P0-2] `services/api/src/game_predictor_api/domain/super_game_series.py:253` — Ocena kompletności obcina koniec serii do `expected_layout_count`. Dla triggera 995, długości 10 i ostatniej znanej planszy 1000 wynik ma `end_sequence_number = 1005`, lecz `completeness = complete`. Task i zaakceptowany plan wymagają `incomplete`, gdy koniec serii wykracza poza ostatnią znaną planszę. Brak przenoszenia serii przez zawinięcie nie oznacza znajomości brakujących spinów. Należy porównywać rzeczywisty koniec serii z ostatnią znaną pozycją oraz poprawić oczekiwanie w `services/api/tests/test_super_game_series_domain.py:99`.

### P1

- [P1-1] `services/api/tests/test_super_game_input_version.py:55` — Wymagany test parametryczny transakcyjności punktów zapisu został zastąpiony sprawdzeniem AST, czy funkcja zawiera wywołanie helpera. Test PostgreSQL w `services/api/tests/integration/test_super_game_series_postgres.py:466` wywołuje helper bezpośrednio; korekty w tym pliku również wykonują SQL i ręczne podbicie wersji. Nie sprawdza to rzeczywistych ścieżek zapisu predykcji, ich usunięcia, korekty siatki, importu, zmiany ról i publikacji reguł. Należy dodać parametryczne testy wywołujące rzeczywiste operacje i sprawdzające wersję, nieaktualność oraz rollback razem ze zmianą danych.

- [P1-2] `ai_docs/tasks/0933-super-game-series-derivation.md:350` — Outcome przenosi `superGameState` w odpowiedziach wyszukiwania i kalkulacji do TASK-0935/0936, podczas gdy Scope i kryteria TASK-0933 nadal wymagają tego kontraktu. `services/api/src/game_predictor_api/schemas/board_search.py:37` oraz `services/api/src/game_predictor_api/schemas/board_search_approximate_win.py:79` nie zawierają tego pola. Osobna trasa stanu nie spełnia wymagania pola na poziomie odpowiedzi. Outcome powołuje się na polecenie „bez znacznika w wyszukiwaniu”, ale nie rozstrzyga jednoznacznie wyłączenia kontraktu świeżości. Przed zamknięciem taska należy udokumentować zatwierdzone przesunięcie tego wymagania w tasku i planie albo dostarczyć wymagany pion API wraz z testem.

### P2

Brak.

## Pokrycie kryteriów akceptacji

Ocena „spełnione” oznacza zgodność stwierdzoną statycznie; testów nie uruchamiano.

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Trigger 100, retrigger 105, brak nowej serii wewnątrz bieżącej | spełnione | `services/api/tests/test_super_game_series_domain.py:43`, `:52` |
| Brak planszy 103 nie skraca serii; API zwraca `missing` | spełnione | `services/api/tests/test_super_game_series_domain.py:71`; `services/api/tests/test_super_game_series_api.py:216` |
| Koniec poza ostatnią znaną planszą oznacza `incomplete` | niespełnione | Zwykły przypadek obejmuje test domenowy `:78`; przypadek końca sekwencji narusza P0-2 |
| Predykcja niezbędna do triggera lub retriggera oznacza `unverified` | spełnione | `services/api/tests/test_super_game_series_domain.py:85` |
| Zachowanie symbolu i rewizji; audyt usunięcia i pochłonięcia serii | spełnione | `services/api/tests/integration/test_super_game_series_postgres.py:345` |
| Retrigger 40 000 zapisuje się i odczytuje | spełnione | `services/api/tests/integration/test_super_game_series_postgres.py:385` |
| Restart nie ujawnia częściowej generacji | spełnione | `services/api/tests/integration/test_super_game_series_postgres.py:412` |
| Korekta podczas joba odrzuca kandydata i pozostawia jeden ponowny przebieg | spełnione | `services/api/tests/integration/test_super_game_series_postgres.py:444` |
| Nowy trigger przed jobem jest sygnalizowany w odpowiedzi wyszukiwania przez `superGameState` | niespełnione | P1-2; `services/api/src/game_predictor_api/schemas/board_search.py:37` |
| Każdy punkt zapisu transakcyjnie podbija wersję; test parametryczny obejmuje usunięcia | niespełnione | P0-1 i P1-1 |
| Zmiana rekordu o niskiej rewizji jest wykrywana | spełnione | `services/api/tests/integration/test_super_game_series_postgres.py:466` |
| Nieaktualne `expectedRevision` daje 409 bez zapisu | spełnione | `services/api/tests/test_super_game_series_api.py:243`; `services/api/tests/integration/test_super_game_series_postgres.py:501` |
| Bramka własności klasyfikuje nowe tabele | spełnione | `services/api/tests/test_game_data_v2_schema.py:53`; `services/api/src/game_predictor_api/storage/game_data_v2_manifest_v6.py:19` |

## Listy zamknięte i otwarte

Zamknięte: Brak. Runda 1.

Otwarte: P0-1, P0-2, P1-1, P1-2.

## Proponowane testy

- W `services/api/tests/integration/test_super_game_series_postgres.py` dodać zmianę `expected_layout_count` przez repozytorium katalogu przed jobem i podczas joba. Sprawdzić podbicie wersji, `fresh = false`, odrzucenie starego kandydata i poprawny wynik kolejnego przebiegu. Komenda: `.\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_super_game_series_postgres.py -q`, z `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`.
- W `services/api/tests/test_super_game_series_domain.py` sprawdzić trigger 995 przy końcu sekwencji 1000: długość 10, koniec 1005, `incomplete`, bez przeniesienia na pozycję 1. Komenda: `.\.venv\Scripts\python.exe -m pytest services/api/tests/test_super_game_series_domain.py -q`.
- Rozszerzyć testy integracyjne o rzeczywiste operacje wymienione w `SUPER_GAME_INPUT_WRITE_POINTS`, w tym usunięcie predykcji oraz rollback. Samo wywołanie helpera przez fixture nie stanowi dowodu.
- Po rozstrzygnięciu P1-2 dodać test odpowiedzi wyszukiwania przed przeliczeniem, podczas niego i po publikacji; sprawdzić stan także dla pozycji bez opublikowanej serii.

## Zakres przeglądu i ograniczenia

Przeczytano instrukcje briefu, task z Outcome, odpowiednie fragmenty zaakceptowanego planu i dokumentacji, migrację 0152, manifest v6, domenę, aplikację, repozytorium, wersjonowanie wejścia, router i schematy API, integrację workera oraz testy. Sprawdzono także zmienione punkty zapisu i obecność pól w wygenerowanym kontrakcie klienta.

Brief nie zawierał fragmentu planu; odczytano odpowiednie sekcje bezpośrednio z dokumentu wskazanego przez task. Wyniki testów i pomiary zapisane przez wykonawcę w Outcome nie zostały niezależnie odtworzone. Nie wykonywano migracji, testów, benchmarków ani zmian plików. Wydajność dla 500 000 pozycji pozostaje niezweryfikowana.