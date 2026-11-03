# Audyt TASK-1149: kontrola czasu przy strumieniowym blokowaniu siatek

Werdykt: PASS
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6-astra, high
Zakres: HEAD...a3064372d3f33fcc6b0d3f708696d617051839aa oraz zmiany niezacommitowane, data 2026-11-03
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Sprawdziłem nowy helper `_budgeted_rows`, jego użycie w pięciu strumieniach `_lock_inputs`, nowe testy jednostkowe oraz rozszerzony test PostgreSQL. Porównałem je z kodem `CohortDeadline` i z zainstalowanymi wersjami SQLAlchemy 2.0.51 oraz psycopg 3.3.4. Zmiana robi to, czego wymaga task. Dla `yield_per=200` jedno wywołanie `Result.fetchmany(200)` daje dokładnie jeden DBAPI `fetchmany`, czyli jeden FETCH. Kontrola SQL przed tym pobraniem ustawia `statement_timeout`, który obowiązuje następny FETCH. Treść SQL, kolejność, `FOR UPDATE`, strażnicy i limity 60/30/5 s pozostały bez zmian. Kursor zamyka się również przy błędzie konsumenta. Główne ryzyko jest procesowe: w worktree leżą niezwiązane zmiany TASK-1150, które mogą trafić do osobnego commita TASK-1149.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `services/api/tests/integration/test_grid_cohort_freeze_selection_postgres.py:200` — Test PG sprawdza blokady tylko w trzech tabelach z `TABLES`. Nie sprawdza, że `source_images` wybranych źródeł (`selected_source`, `second_source`) są zablokowane po `_lock_inputs`. Nie sprawdza też, że obce źródło pozostaje wolne. Strumień źródeł przechodzi przez nowy helper, a w teście widać go tylko pośrednio, przez liczbę 11 kontroli budżetu. Kryterium „komplet blokad” jest więc dla źródeł pokryte słabiej niż dla plansz, review i komórek. Ta luka istniała przed taskiem i nie wskazuje na błąd w kodzie. Proponowana poprawka: dopisać `_assert_lock(probe, "source_images", game, selected_source, blocked=True)` oraz to samo dla `second_source`, a także `blocked=False` dla `foreign_source` w sesji obcej gry.
- [P2-2] `ai_docs/tasks/1149-grid-freeze-batched-lock-reads.md:49` — Kryterium wymaga osobnego commita. Tymczasem worktree zawiera niezwiązane zmiany TASK-1150: zmodyfikowany `services/worker/src/game_predictor_worker/images/grid_training_child.py` i nieśledzony `services/worker/tests/test_grid_training_atomic_json.py`. Do tego `CODE_MAP.md` i `CODE_MAP_SYMBOLS.md` są oznaczone jako zmienione, choć `git diff HEAD` nie pokazuje w nich żadnej różnicy treści, tylko ostrzeżenia LF→CRLF. Zbiorcze `git add` wciągnęłoby TASK-1150 do commita TASK-1149. Proponowana poprawka: przy commicie jawnie podać ścieżki TASK-1149 (moduł freeze, dwa pliki testów, `VISION_LAB.md`, raport weryfikacji, task i plan). Pliki workera zostawić dla TASK-1150, a mapy nie commitować, jeśli zmieniło się w niej tylko EOL.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Timeout odświeżany przed każdym pobraniem najwyżej 200 wierszy, bez SQL po każdym wierszu | spełnione | `services/api/src/game_predictor_api/application/grid_training_cohort_freeze.py:36-38`. Pętle konsumentów w liniach 71-74, 87-89 i 107-109 nie mają już `check(session)`. W SQLAlchemy `BufferedRowCursorFetchStrategy.fetchmany` (`.venv/.../sqlalchemy/engine/cursor.py`) przy buforze `yield_per` wykonuje jeden DBAPI `fetchmany(size - len(buffer))`. Pierwszy FETCH(1) przy `create()` zachodzi jeszcze w `execute`, z timeoutem ustawionym przez hook przed DECLARE (`SET LOCAL` obowiązuje dalej). |
| Wszystkie wiersze konsumowane raz, w tej samej kolejności; blokady i zakresy bez zmian | spełnione | `grid_training_cohort_freeze.py:41` (`yield from batch`). Literały SQL są identyczne z `5cfe292b`: `artifacts/task1149-sql-preservation.log` („identical … 7”). Test PG: `test_grid_cohort_freeze_selection_postgres.py:191,199,204`. |
| Wygaśnięcie przed albo po fetch zatrzymuje etap, zamyka kursor, zachowuje rollback | spełnione | `grid_training_cohort_freeze.py:36-44`. Wyjątek przechodzi do transakcji `freeze` (linie 151-153), której wykonawca nie zmieniał. psycopg 3 `ServerCursor._close_gen` pomija CLOSE w stanie INERROR, więc zamknięcie nie przykrywa pierwotnego błędu. Testy: `services/api/tests/test_grid_training_cohort_core.py:58-71,74-86`. |
| Unit 0/1/200/201/401 (kolejność, liczba kontroli, błędy, zamknięcie); PG ponad 200 komórek, komplet blokad, izolacja, rollback | spełnione (zastrzeżenie: P2-1) | `test_grid_training_cohort_core.py:48-55`. PG: `test_grid_cohort_freeze_selection_postgres.py:89-93,192-198,200-215`. Logi: `task1149-unit.log` („57 passed”), `task1149-selection.log` („1 passed”). |
| Scoped testy, ruff/mypy, docs/map i Opus przed osobnym commitem/task-close | niezweryfikowane (otwarte z założenia: ten audyt, commit i task-close należą do prowadzącego; zastrzeżenie: P2-2) | Logi `task1149-lint.log` („All checks passed!”), `task1149-format.log` („3 files already formatted”), `task1149-types.log` („Success”), `task1149-registry.log` („1 passed”). Commit jeszcze nie istnieje. |

## Listy zamknięte i otwarte

Zamknięte: nie dotyczy (runda 1).

Otwarte: P2-1, P2-2.

## Proponowane testy

- Rozszerzyć `services/api/tests/integration/test_grid_cohort_freeze_selection_postgres.py` o asercje blokad `source_images` (P2-1). Komenda: `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_grid_cohort_freeze_selection_postgres.py`.
- Opcjonalny wariant PG z deadline'em, który wygasa po pierwszej partii komórek, czyli `TracedDeadline` rzucający przy drugim `check(session)`. Powinien potwierdzić na prawdziwym kursorze nazwanym psycopg, że `GRID_COHORT_TIMEOUT` przechodzi bez przykrycia przez CLOSE, a po rollbacku blokady znikają. Dziś to zachowanie pokrywają tylko testy jednostkowe na atrapie wyniku.
- Opcjonalnie w tym samym teście PG: odczytać `current_setting('statement_timeout')` w podmienionym `Rows.fetchmany` i sprawdzić, że przed każdym FETCH ma wartość z zakresu 1…30000 ms, mniejszą lub równą pozostałemu budżetowi.

## Zakres przeglądu i ograniczenia

Przeczytałem:
- brief audytu, task i fragment planu;
- pełny moduł `grid_training_cohort_freeze.py` (linie 1-180);
- `CohortDeadline.check` i `apply_statement_timeout` w `grid_training_cohort_repository.py`;
- `acquire_image_sequence_locks`;
- pełny zmieniony test PG oraz diff testów jednostkowych;
- `VISION_LAB.md` (diff) i raport `TASK-1149_VERIFICATION.md`;
- źródła zainstalowanych bibliotek: SQLAlchemy 2.0.51 (`BufferedRowCursorFetchStrategy`, `FilterResult.close`) i psycopg 3.3.4.

Wyniki testów, lintu, typów i porównania SQL odczytałem z istniejących logów w `artifacts/task1149-*.log`. Niczego nie uruchamiałem ponownie. Czasu freeze na danych operatora nie zmierzyłem i nie dało się tego ocenić statycznie. Nie oceniałem zmian w `services/worker`, bo należą do TASK-1150 i są spoza pathspec briefu.
