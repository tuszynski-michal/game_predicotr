# Audyt TASK-1190 - Szybkie wyszukiwanie członkostwa kohort w wyzwalaczu

Werdykt: REVISE
Audytor: gpt-6.1-sol, high
Wykonawca: claude-opus-5-5, high
Zakres: HEAD...33e9197ef95f7f45abcf980a20af91b9e466c95a oraz zmiany niezacommitowane wskazane w briefie, data 2026-11-12
Runda: 1
SHA pakietu: 875741ff99e4a41363844712c42272f2b46b5f07dd6736cf1a8b6c9bfa3b6efd
Otwarte P0: 2
Otwarte P1: 2

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano migrację, utrzymywanie par, równoważność wyzwalaczy, manifest v23 oraz testy i deklarowane wyniki. Wyszukiwanie zachowuje liczność zdarzeń na pasującego członka, a migracja porównuje pary w obu kierunkach. Commit blokują brak izolacji przy bezpośrednim odczycie nowych partycji, niedozwolone zmiany kohort `retired` oraz niepełne dowody wymaganej weryfikacji.

## Znaleziska

### P0

- [P0-1] `services/api/src/game_predictor_api/storage/game_partition_lifecycle.py:227` — lista tabel otrzymujących RLS podczas tworzenia partycji nowej gry nie zawiera `grid_training_cohort_member_refs`. Dodanie tabeli do manifestu zapewnia utworzenie partycji, ale pozostawia ją bez `ENABLE/FORCE ROW LEVEL SECURITY` i polityki `game_scope_v1`. Rola aplikacji otrzymuje uprawnienia do partycji przez granty i domyślne uprawnienia (`services/api/src/game_predictor_api/storage/database_roles.py:203`, `:242`). Bezpośredni SELECT z partycji refs ujawni więc dane także przy ustawionym zakresie innej gry. Dodać refs do konfiguracji zabezpieczanych partycji oraz test odczytu bezpośrednio z partycji jako rola aplikacji. Obecna asercja w `services/api/tests/integration/test_grid_cohort_member_refs_postgres.py:206` sprawdza wyłącznie tabelę nadrzędną.

- [P0-2] `services/api/src/game_predictor_api/storage/grid_cohort_member_refs_migration.py:259` — ogólna gałąź aktualizacji nagłówka wyklucza `frozen`, `failed` i `canceled`, lecz przepuszcza `retired`. Po poprawnym `frozen → retired` można wykonać `retired → failed`, `retired → canceled` albo pozostawić `retired` i zmienić `summary`, zwiększając rewizję o jeden. Narusza to zaakceptowaną regułę przejść wyłącznie `frozen ↔ retired` i ochronę historii. Wykluczyć `retired` z ogólnej gałęzi oraz dodać testy niedozwolonych zmian wychodzących z tego stanu. Aktualny test negatywny zaczyna się już po powrocie do `frozen` (`services/api/tests/integration/test_grid_cohort_member_refs_postgres.py:364`).

### P1

- [P1-1] `services/api/tests/integration/test_grid_cohort_member_refs_postgres.py:140` — test równoważności instaluje wyzwalacze na sztucznych tabelach dla dziewięciu klasyfikacji. Nie pokrywa wymaganego przez zaakceptowany plan porównania rzeczywistego `save_review_item` przy co najmniej trzech kohortach ani operacji na wszystkich tabelach produkcyjnych z wyzwalaczem. Podczas porównania istnieją dwie kohorty; trzecia powstaje dopiero dla EXPLAIN. Test nie wykryje błędnego podpięcia klasyfikacji do rzeczywistej tabeli ani różnic wynikających ze współdziałania jej wyzwalaczy. Uzupełnić test integracyjny wymagany w sekcji TASK-1190 planu, porównując multizbiory zdarzeń v1/v2 pod rolą aplikacji.

- [P1-2] `ai_docs/tasks/1190-grid-cohort-member-refs.md:160` — wynik wymaganej regresji pozostaje jako `REGRESSION_PLACEHOLDER`. Pakiet deklaruje wyniki trzech nowych testów i testów jednostkowych, ale nie zawiera rozliczenia wymaganych testów integracyjnych kohort, mostu ocen i routingu. Nie ma zatem dowodu spełnienia kryterium „Istniejące testy kohort i mostu ocen bez regresji”. Uzupełnić Outcome rzeczywistym wynikiem wymaganej regresji, osobno wskazując potwierdzone błędy zastane i ewentualne nowe niepowodzenia.

### P2

Brak.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Identyczny multizbiór zdarzeń dla dziewięciu klasyfikacji pod RLS | niezweryfikowane | Test porównuje liczniki zdarzeń: `services/api/tests/integration/test_grid_cohort_member_refs_postgres.py:261`. Wynik wykonawcy deklaruje PASS; audyt nie uruchamiał testów. |
| Równoważność rzeczywistego zapisu geometrii i pokrycie tabel wymagane planem | niespełnione | Test używa tabel próbnych: `services/api/tests/integration/test_grid_cohort_member_refs_postgres.py:140`; P1-1. |
| Indeksowane wyszukiwanie refs oraz wykazanie ograniczenia starego zapytania | niezweryfikowane | Asercje planu: `services/api/tests/integration/test_grid_cohort_member_refs_postgres.py:318`; stare zapytanie: `:334`. Brak własnego wykonania EXPLAIN. |
| Pary zgodne z tablicami po capture i backfillu | niezweryfikowane | Kontrola migracji przez EXCEPT w obu kierunkach: `services/api/src/game_predictor_api/storage/grid_cohort_member_refs_migration.py:325`; asercje testowe: `services/api/tests/integration/test_grid_cohort_member_refs_postgres.py:201`, `:438`. |
| Izolacja par między grami, również dla nowo tworzonych partycji | niespełnione | Brak konfiguracji RLS dla refs w lifecycle: `services/api/src/game_predictor_api/storage/game_partition_lifecycle.py:227`; P0-1. |
| Odrzucenie bezpośredniego INSERT/UPDATE/DELETE refs | niezweryfikowane | Strażnik: `services/api/src/game_predictor_api/storage/grid_cohort_member_refs_migration.py:137`; test: `services/api/tests/integration/test_grid_cohort_member_refs_postgres.py:349`. |
| Wyłącznie przejścia `frozen ↔ retired`, z zachowaniem historii | niespełnione | Ogólna gałąź dopuszcza dodatkowe aktualizacje `retired`: `services/api/src/game_predictor_api/storage/grid_cohort_member_refs_migration.py:259`; P0-2. |
| Odmowa downgrade przy `retired`, przywrócenie v1 i manifestu v22, ponowny backfill | niezweryfikowane | Implementacja downgrade: `services/api/src/game_predictor_api/storage/grid_cohort_member_refs_migration.py:388`; test cyklu: `services/api/tests/integration/test_grid_cohort_member_refs_postgres.py:409`. |
| Istniejące testy kohort i mostu ocen bez regresji | niezweryfikowane | Brak wyniku w pakiecie: `ai_docs/tasks/1190-grid-cohort-member-refs.md:160`; P1-2. |

## Listy zamknięte i otwarte

Zamknięte: Brak.

Otwarte: P0-1, P0-2, P1-1, P1-2.

## Proponowane testy

- W `services/api/tests/integration/test_grid_cohort_member_refs_postgres.py` dodać kontrolę flag RLS i polityki partycji refs nowej gry oraz bezpośredni odczyt tej partycji w zakresie innej gry.
- W tym samym pliku dodać negatywne scenariusze `retired → failed`, `retired → canceled` i zmiany `summary` przy pozostawieniu `retired`, z poprawnym zwiększeniem rewizji.
- Uzupełnić rzeczywisty scenariusz zapisu geometrii wymagany planem. Testy nowego pionu uruchomić poleceniem: `.\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_grid_cohort_member_refs_postgres.py -q`.
- Po ustawieniu `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'` wykonać i rozliczyć wymaganą regresję: `.\.venv\Scripts\python.exe -m pytest services/api/tests/integration -k "cohort or grid_model_evaluation_bridge or game_storage_routing or gate_noise" -q`.

## Zakres przeglądu i ograniczenia

Przeczytano brief, task, zaakceptowany plan, wskazane fragmenty architektury, decyzję D-605 oraz wszystkie pliki implementacji i testów objęte briefem. Sprawdzono także zależne fragmenty tworzenia partycji, grantów roli aplikacji i wyzwalacza v1. Statyczne porównanie potwierdziło zgodność mapy 14 tabel z migracją 0163 oraz zgodność pięciu nowych plików z treścią zamrożonego pakietu.

Nie uruchamiano testów, migracji, usług ani zapytań do bazy. Deklarowane wyniki wykonawcy nie zostały niezależnie odtworzone. Nie oceniano operacyjnego czasu zapisu ani prac TASK-1191–1192.