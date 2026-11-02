# Audyt TASK-1135 — Naprawa timeoutu zamrażania korekt siatek

Werdykt: PASS
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6.1-sol, high
Zakres: a31e8adbc026f1bc17c7ffee97499d0b6f856157...a31e8adbc026f1bc17c7ffee97499d0b6f856157 oraz zmiany niezacommitowane, data 2026-11-03
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Przejrzałem zmianę zapytania wybierającego wiersze w `_lock_inputs`, nowy test integracyjny PostgreSQL, aktualizacje dokumentacji oraz artefakty dowodowe wykonawcy. Nowe zapytanie najpierw rozwija tablice identyfikatorów użytych członków kohorty (`unnest` z `DISTINCT`), a potem łączy je z tabelą docelową. Daje to ten sam zbiór wierszy co poprzedni skorelowany `EXISTS` z `@>`. Zachowane są: filtr gry, kohorty i `used`, polityka RLS, sortowanie rosnące, `FOR UPDATE OF r`, kolejność wszystkich wcześniejszych blokad i limity czasu. Nie znalazłem błędów P0 ani P1. Pozostałe ryzyko jest proceduralne: żaden automatyczny test nie wykryłby powrotu wolnego planu, a dowód wydajności nie zapisuje dokładnego SQL ani planu nowego wariantu.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `services/api/tests/integration/test_grid_cohort_freeze_selection_postgres.py:155` — Test sprawdza wyłącznie semantykę: dokładny zbiór, kolejność, duplikaty i blokady. Przeszedłby także na starym zapytaniu z `m.{identifier_column} @> ARRAY[r.id]`. Nic więc nie chroni przed ponownym wprowadzeniem skorelowanego warunku, który był przyczyną timeoutu (`services/api/src/game_predictor_api/application/grid_training_cohort_freeze.py:72-77`). Reguła „naprawa regresji dostaje test odtwarzający przypadek” jest tu ograniczona przez zakaz syntetycznego obciążenia, więc pełna reprodukcja wydajnościowa w teście nie jest wymagana. Proponowana poprawka: tani strażnik strukturalny, na przykład `EXPLAIN (FORMAT JSON)` wybranego zapytania na małym fixture z asercją, że żaden węzeł nie ma `Join Filter` z `@>` na relacji `r`. Alternatywnie można świadomie zaakceptować ryzyko i zapisać to w `Outcome`.
- [P2-2] `ai_docs/tasks/1135-grid-learning-freeze-query.md:62` — Dowód wydajności nie mówi, które dokładnie zapytanie zmierzono. `artifacts/task1135-readonly-reproduction.json` zawiera tylko czasy i liczby wierszy, bez tekstu SQL ani skrótu wariantu „flattened”. Zapisane plany `artifacts/task1135-plan-*.json` dotyczą wyłącznie starego zapytania: widać w nich Seq Scan po 106 380 komórkach z `Join Filter: m.cell_ids @> ARRAY[r.id]`. Pomiar w transakcji READ ONLY z natury pomija `FOR UPDATE` i nie obejmuje tabel plansz ani review. Nie da się więc statycznie potwierdzić, że 0,343 s dotyczy finalnego SQL z `r.game_id=:game` i `ORDER BY r.id`. Proponowana poprawka: dołączyć do artefaktów tekst lub skrót zmierzonego SQL oraz `EXPLAIN` (bez ANALYZE i bez `FOR UPDATE`) finalnego zapytania dla trzech tabel. Można też zaakceptować ryzyko, bo zmiana jest wąska, a e2e z rzeczywistym freeze przeszedł.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Potwierdzony błąd ma reprodukcję na istniejących danych | spełnione | `artifacts/task1135-postgres-failure.log` (statement timeout przy `FETCH FORWARD 200`), `artifacts/task1135-readonly-reproduction.json` (old: 3,157 s, SQLSTATE 57014), `artifacts/task1135-plan-image_symbol_review_cells.json` (Seq Scan + `Join Filter` z `@>`) |
| Nowy wybór obejmuje dokładnie te same wiersze użytych członków, bez wycieku między grami i kohortami, bez duplikatów | spełnione | `services/api/src/game_predictor_api/application/grid_training_cohort_freeze.py:72-77`: `DISTINCT unnest` jest równoważny semi-joinowi `EXISTS`; NULL i puste tablice dają brak dopasowania w obu wariantach; filtry gry, kohorty i `used` są te same, a `r.game_id=:game` pozostał. Test: `services/api/tests/integration/test_grid_cohort_freeze_selection_postgres.py:120-131` (odwrócone tablice, duplikat, identyfikatory obcej gry, drugi użyty członek, nieużyty członek, obca kohorta) i asercja `:155`. Wynik testu wziąłem z logu wykonawcy (`artifacts/task1135-postgres-selection-final.log`, 1 passed), nie uruchamiałem go sam |
| PostgreSQL potwierdza blokady wybranych wierszy i brak blokady niepowiązanych; blokady znikają po transakcji | spełnione | `services/api/tests/integration/test_grid_cohort_freeze_selection_postgres.py:156-165` (NOWAIT → 55P03 dla wybranych, sukces dla nieużytych i obcej gry), `:166-171` (po rollbacku wiersz można zablokować); wynik z logu wykonawcy |
| Limity czasu i kolejność blokad bez zmian; stare polityki kohort przechodzą regresję | spełnione | `services/api/src/game_predictor_api/application/grid_training_cohort_freeze.py:35-62` bez zmian, `:77` `ORDER BY r.id FOR UPDATE OF r`, `:80-81` `deadline.check` na każdym wierszu; `CohortDeadline` nie zmieniony; e2e bez mockowania `_lock_inputs` (grep: jedyne użycie w testach to nowy test) — `artifacts/task1135-e2e.log` (1 passed / 102,25 s) |
| Testy zmienionego pionu, scoped lint/typecheck, docs/map i audyt Opus rozliczone | niezweryfikowane (w toku) | Mój odczyt: `ruff format --check --no-cache` („2 files already formatted”), `ruff check --no-cache` („All checks passed!”), `git diff --check HEAD` rc=0. Mypy, docs i mapa tylko z logów wykonawcy (`artifacts/task1135-mypy.log`, `task1135-docs.log`, `task1135-map-check.log`). Ten raport jest rozliczanym audytem |
| Outcome, task-close, osobny wersjonowany commit i record-hash | niespełnione (oczekuje) | `ai_docs/tasks/1135-grid-learning-freeze-query.md:58` niezaznaczone; zgodnie z procesem commit następuje po audycie |

## Listy zamknięte i otwarte

Zamknięte: nie dotyczy (runda 1).

Otwarte: P2-1, P2-2.

## Proponowane testy

- Strażnik planu: w `services/api/tests/integration/test_grid_cohort_freeze_selection_postgres.py` wykonać `EXPLAIN (FORMAT JSON)` na SQL z `_lock_inputs`, bez `FOR UPDATE` lub w transakcji testowej, dla trzech tabel. Asercja: brak `Join Filter` z operatorem `@>` na relacji `r`. Komenda: `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_grid_cohort_freeze_selection_postgres.py --basetemp artifacts/t1135p6` z timeoutem ≤ 120 s.
- Po scaleniu i jawnym wznowieniu zadania operatora (poza zakresem tego taska) potwierdzić w logu PostgreSQL brak `canceling statement due to statement timeout` dla freeze kohorty `862f79ce-5a3b-51b1-9280-ab324a1e865e`.

## Zakres przeglądu i ograniczenia

Przeczytałem:
- brief audytu;
- pełny `services/api/src/game_predictor_api/application/grid_training_cohort_freeze.py`;
- nowy test integracyjny;
- definicje kolumn tablicowych w `grid_training_cohort_models.py` (typ `ARRAY(Uuid())`, zgodny z `r.id`);
- helper `_save_source` w teście e2e;
- reguły `AGENTS.md` (zasady nadrzędne, testy, timeouty, cykl zadania);
- diff `CODE_MAP.md`, `VISION_LAB.md` i `CURRENT_STATE.md`;
- artefakty `artifacts/task1135-*`: log błędu, reprodukcję, plany starego zapytania, logi testów, ruff, mypy, docs i mapy.

Uruchomiłem tylko polecenia niezmieniające stanu: `git status`, `git diff`, `ruff format --check --no-cache`, `ruff check --no-cache` i `git diff --check`.

Nie uruchamiałem testów PostgreSQL ani mypy i nie łączyłem się z bazą operatora. Wyniki testów, czasy i reprodukcja pochodzą z artefaktów wykonawcy. Nie mogłem statycznie sprawdzić planu nowego zapytania z `FOR UPDATE` na danych produkcyjnych ani indeksów na tabelach partycji per gra.

Wcześniej istniejący błąd `test_shared_candidate_rejects_correction_policy_before_creating_plan` (`artifacts/task1135-unit-final.log`) dotyczy plików identycznych z `main`. Wykonawca prawidłowo zostawił go poza zakresem, zgodnie z `AGENTS.md:160-161`. Warto go podjąć w osobnym tasku.
