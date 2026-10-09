# Audyt TASK-0933 — Wyprowadzanie serii supergry i API serii

Werdykt: REVISE
Audytor: Codex (etykieta briefu: gpt-6-astra, high)
Wykonawca: claude-opus-5-5, high
Zakres: HEAD...190644853b2db51d8e53137cc5704c6d0cb6ab99 oraz zmiany niezacommitowane wskazane w briefie, data 2026-10-09
Runda: 2

Przegląd statyczny, bez zmian w plikach. Audytor nie uruchamiał testów ani operacji zmieniających stan.

## Streszczenie

Poprawiono cztery znaleziska poprzedniej rundy: wersjonowanie długości sekwencji, kompletność ostatniej serii, testy rzeczywistych operacji oraz rozliczenie zakresu `superGameState`. Pozostają dwa problemy współbieżności: niespójny odczyt parametrów przy starcie generacji oraz możliwość deadlocka między resetem gry a publikacją. Oba wymagają poprawy przed commitem.

## Znaleziska

### P0

- [P0-3] `services/api/src/game_predictor_api/storage/super_game_series_repository.py:471` — `begin_generation` odczytuje `super_game_kind` i `expected_layout_count` przed zablokowaniem wiersza stanu i odczytem `input_version` w linii 484. Przy izolacji READ COMMITTED zapis katalogu może zatwierdzić zmianę pomiędzy tymi odczytami. Przykładowo job odczytuje zakres 1000, operator zmniejsza go do 500 i podbija wersję, a job następnie zapamiętuje już nową wersję wraz ze starym zakresem. Publikacja zaakceptuje kandydata zawierającego trigger 700 i oznaczy go jako świeży. Należy odczytywać parametry gry oraz wersję wejścia pod wspólną synchronizacją, z zachowaniem zgodnej kolejności blokad. Test w `services/api/tests/integration/test_super_game_series_postgres.py:679` zmienia zakres dopiero po zakończeniu `begin_generation`, więc nie pokrywa tego przeplotu.

- [P0-4] `services/api/src/game_predictor_api/storage/cleanup_repository.py:127` — Nowy wyjątek pomija również job wyprowadzania w stanie `processing`, choć reset i publikacja mają przeciwną kolejność blokad. Reset usuwa wiersze generacji i serii przed podbiciem wersji (`:271`, `:1299`), natomiast publikacja najpierw blokuje stan, a następnie aktualizuje serie i usuwa wiersze generacji (`services/api/src/game_predictor_api/storage/super_game_series_repository.py:642`, `:662`, `:664`). Reset może zatem trzymać blokady usuwanych wierszy i czekać na stan, podczas gdy publikacja trzyma stan i czeka na te wiersze. PostgreSQL przerwie jedną transakcję jako deadlock. Jeśli ofiarą będzie reset, dodatkowym ryzykiem jest wcześniejsze usunięcie plików przez `services/api/src/game_predictor_api/application/cleanup.py:332`, którego rollback bazy nie cofnie. Najmniejsza poprawka to zachowanie blokady cleanupu dla działającego joba i pomijanie wyłącznie zakolejkowanego. Alternatywa wymaga uzgodnienia kolejności blokad i zabezpieczenia operacji plikowych. Obecne testy cleanupu obejmują job zakolejkowany, nie równoległą publikację.

### P1

Brak.

### P2

Brak.

## Pokrycie kryteriów akceptacji

Ocena „spełnione” oznacza zgodność stwierdzoną statycznie, bez uruchamiania testów.

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Trigger 100, retrigger 105; brak nowej serii wewnątrz bieżącej | spełnione | `services/api/tests/test_super_game_series_domain.py:43`, `services/api/tests/test_super_game_series_domain.py:52` |
| Brak planszy 103 nie skraca serii; API zwraca `missing` | spełnione | `services/api/tests/test_super_game_series_domain.py:71`, `services/api/tests/test_super_game_series_api.py:216` |
| Koniec poza ostatnią znaną planszą oznacza `incomplete` | spełnione | `services/api/src/game_predictor_api/domain/super_game_series.py:255`, `services/api/tests/test_super_game_series_domain.py:99` |
| Trigger lub retrigger wymagający predykcji oznacza `unverified` | spełnione | `services/api/tests/test_super_game_series_domain.py:85` |
| Zachowanie symbolu i rewizji; audyt usunięcia lub pochłonięcia serii | spełnione | `services/api/tests/integration/test_super_game_series_postgres.py:380` |
| Retrigger 40 000 zapisuje się i odczytuje | spełnione | `services/api/tests/integration/test_super_game_series_postgres.py:420` |
| Restart nie ujawnia częściowej generacji | spełnione | `services/api/tests/integration/test_super_game_series_postgres.py:447` |
| Zmiana wejścia podczas joba nie dopuszcza publikacji nieaktualnego kandydata | niespełnione | P0-3; istniejący test `services/api/tests/integration/test_super_game_series_postgres.py:479` obejmuje zmianę po inicjalizacji |
| Nowy trigger powoduje nieaktualność przed jobem i do publikacji | spełnione | `services/api/src/game_predictor_api/storage/super_game_input_version.py:254`, `services/api/src/game_predictor_api/application/super_game_series.py:383`; zakres wyszukiwania przeniesiony w tasku `:98` |
| Punkty zapisu transakcyjnie podbijają wersję, także przy usunięciu predykcji | spełnione | `services/api/tests/integration/test_super_game_series_postgres.py:989`, `services/api/tests/integration/test_super_game_series_postgres.py:1010` |
| Zmiana rekordu o niskiej rewizji jest wykrywana | spełnione | `services/api/tests/integration/test_super_game_series_postgres.py:501` |
| Nieaktualne `expectedRevision` daje 409 bez zapisu | spełnione | `services/api/tests/test_super_game_series_api.py:243`, `services/api/tests/integration/test_super_game_series_postgres.py:536` |
| Bramka własności klasyfikuje nowe tabele | niezweryfikowane | Element oceniony w rundzie 1; pełnej bramki manifestu nie powtarzano w ograniczonym zakresie tej rundy |

## Listy zamknięte i otwarte

Zamknięte:

- **P0-1** — `save_game` wykrywa zmianę `expected_layout_count` i podbija wersję: `services/api/src/game_predictor_api/storage/catalog_repository.py:230`, `:245`. Dodano regresję PostgreSQL w `services/api/tests/integration/test_super_game_series_postgres.py:679`. Osobny wyścig inicjalizacji opisuje P0-3.
- **P0-2** — Kompletność porównuje rzeczywisty koniec serii z ostatnią znaną pozycją: `services/api/src/game_predictor_api/domain/super_game_series.py:255`. Regresja końca sekwencji: `services/api/tests/test_super_game_series_domain.py:99`.
- **P1-1** — Dodano parametryczne wywołania rzeczywistych operacji oraz sprawdzenia podbicia wersji i rollbacku: `services/api/tests/integration/test_super_game_series_postgres.py:864`, `:1010`.
- **P1-2** — Przesunięcie kontraktu wyszukiwania do TASK-0935 zapisano zgodnie w zakresie taska i planie: `ai_docs/tasks/0933-super-game-series-derivation.md:98`, `ai_docs/delivery/MUMIE_SUPER_GAME_EXECUTION_PLAN_20261008.md:282`.

Otwarte: **P0-3, P0-4**.

## Proponowane testy

- W `services/api/tests/integration/test_super_game_series_postgres.py` dodać test dwóch sesji: zatrzymać inicjalizację po odczycie parametrów gry, zatwierdzić zmianę zakresu 1000 → 500, następnie wznowić inicjalizację. Generacja nie może opublikować triggera 700 ze stanem `fresh = true`.
- W tym samym pliku dodać test resetu przy jobie `processing`. Przy zachowaniu blokady cleanup powinien odmówić przed usunięciem plików. Jeśli równoległość pozostanie dozwolona, test powinien wymusić przeplot resetu i publikacji oraz potwierdzić brak deadlocka i spójność bazy z artefaktami.
- Po poprawkach uruchomić na jednorazowej bazie PostgreSQL: `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'`, następnie `.\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_super_game_series_postgres.py -q`, z jawnym limitem czasu.

## Zakres przeglądu i ograniczenia

Przeczytano brief, poprzedni raport, task z Outcome, odpowiednie fragmenty planu i dokumentacji architektury. Sprawdzono pliki objęte briefem oraz powiązane granice transakcji, blokady cleanupu, konfigurację sesji i obsługę jobów potrzebne do oceny współbieżności.

Brief nie zawierał fragmentu planu; odczytano go bezpośrednio ze wskazanego dokumentu. Wyników testów zapisanych przez wykonawcę nie odtwarzano. Nie wykonywano migracji, benchmarków, operacji na danych ani zmian plików. Wydajność dla 500 000 pozycji pozostaje niezweryfikowana.