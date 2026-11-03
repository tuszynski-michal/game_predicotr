# TASK-1149 — Kontrola czasu przy strumieniowym blokowaniu siatek

## Status

`in_progress`

## Goal

Usunąć tysiące zbędnych zapytań ustawiających timeout podczas blokowania wejść, zachowując pełen zakres, kolejność i trwałość blokad oraz limity 60/30/5 sekund.

## Context

Odbiór TASK-1147 ujawnił GRID_COHORT_TIMEOUT dla 788 źródeł, w tym 124 użytych zdjęć. Kontrolowane ponowienie tego samego freeze:163 z oryginalnym kluczem prawidłowo zamroziło kohortę w 53,515 s; samo _lock_inputs zajęło 33,641 s, etykiety 7,990 s, rejestr 7,156 s, pliki 0,252 s. Per-row deadline.check(session) wykonuje SQL dla każdego z tysięcy wierszy blokowanych komórek. Ciepła powtórka nie jest trwałą naprawą.

## Dependencies / entry conditions

Gałąź codex/grid-correction-growth, HEAD5cfe292b. Main operatora na tym samym kodzie, DB0178; bez pushu naszego zakresu przed odbiorem. Istniejący parent cc7e739e-027c-4f44-87d8-8088c0d86bb1 wznowiono normalnym resume po prawidłowym freeze kohorty8c4d3ab4-4d01-59fe-a826-46883b72ddfe, bez nowego parenta i odnowienia budżetu. Prowadzący ma wyłączność usług/main/bazy. Wykonawca zmienia wyłącznie worktree.

## Recommended execution

Wykonawca gpt-6-astra / high; niezależny Claude Code claude-opus-5-5 / high przed commitem. Eskalacja przy zmianie zakresu lub kolejności blokad, limitów, ochron pochodzenia albo schematu. Potwierdzony obecny zakres nie wymaga migracji ani zmiany API.

## Relevant docs

- AGENTS.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/delivery/GRID_CORRECTION_GROWTH_PLAN_20261103.md — TASK-1147 i TASK-1149
- ai_docs/requirements/VISION_LAB.md
- ai_docs/architecture/VISION_LAB.md
- ai_docs/architecture/CODE_MAP.md
- ai_docs/quality/TASK-1147_VERIFICATION.md
- ai_docs/quality/GRID_CORRECTION_GROWTH_DEPLOYMENT_20261103.md
- Dowody lokalne: D:/game_predicotr/artifacts/grid-growth-deploy-20261103/freeze-profile-result.json oraz member-readonly-timings.json (tylko niezbędne metryki, nie dodatkowy dataset).

## Scope

Mały helper strumienia w grid_training_cohort_freeze.py; użycie go w źródłach, sekwencjach, planszach, review i komórkach. Kontrola SQL przed każdym fetchmany(200), zwykła kontrola zegara po partii, zamknięcie kursora także przy błędzie. Wszystkie SELECT, ORDER BY, FOR UPDATE i wywołania istniejących strażników pozostają. Sekwencje nadal blokowane rosnąco, osobno; before_cursor_execute chroni każdy ich SQL.

## Out of scope

Bez zwiększania limitów, ograniczania danych, pomijania wierszy, zmiany ról/aliasów/buforów, etykiet, publikacji modeli, nowych migracji i kontraktu HTTP. Wykonawca nie dotyka root/main, usług ani bazy operatora. Bez nowych dużych benchmarków i sztucznych korpusów.

## Acceptance criteria

- [x] Timeout jest odświeżany przed każdym pobraniem najwyżej200 wierszy, a nie osobnym SQL po każdym wierszu.
- [x] Wszystkie wiersze są konsumowane raz w tej samej kolejności; wszystkie dotychczasowe blokady i zakresy pozostają.
- [x] Wygaśnięcie przed albo po fetch zatrzymuje etap, zamyka kursor i zachowuje rollback transakcji; żadnego pomijania ani sukcesu po timeout.
- [x] Unit0/1/200/201/401 sprawdza kolejność i liczbę kontroli oraz błędy/zamknięcie; PG sprawdza ponad200 komórek, komplet blokad, izolację obcych/nieużytych i rollback.
- [ ] Scoped testy, ruff/mypy, docs/map i Opus rozliczone przed osobnym commitem/task-close.

## Technical notes

Proponowany prywatny _budgeted_rows(result,session,deadline): pętla deadline.check(session), batch=result.fetchmany(200), deadline.check() bez SQL; koniec przy pustej partii, yield zachowuje porządek. finally result.close(). Pamięć maksymalnie200 wyników. Przed każdym SQL sekwencji zwykły deadline.check(); istniejący event nadaje pozostały timeout. Nie zmieniać stałych ani SQL strażników. To zmiana implementacji, nie decyzja domenowa.

## Expected files

- services/api/src/game_predictor_api/application/grid_training_cohort_freeze.py — _lock_inputs i nowy prywatny helper.
- services/api/tests/test_grid_training_cohort_core.py — testy strumienia/deadline.
- services/api/tests/integration/test_grid_cohort_freeze_selection_postgres.py — rzeczywiste blokady, tracing fetchmany/close.
- Mapa kodu, VISION_LAB, raport TASK-1149_VERIFICATION.md, plan i Outcome.

## Test cases / Verification

Bezpośredni pytest na trzech wskazanych plikach (dwa pliki testów) oraz istniejący test registry/restart, disposable PostgreSQL, właściwy PYTHONPATH worktree. Każda komenda timeout do120s; najpierw unit, lint/types, potem PG. Test nie opiera się wyłącznie na czasie: sprawdza liczbę wywołań, kolejność, blokady i rollback. Nie powtarzać UI/build, bo produktowy frontend/kontrakt nie zmieniają się.

## Risks / open questions

Named cursor może pobierać dalsze partie po początkowym SELECT; dlatego timeout musi być ustawiony przed każdym fetch. Samo usunięcie check(session) i zostawienie zegara jest niedopuszczalne. Prowadzący może po audycie zmierzyć tę samą fazę na istniejącej kohorcie w transakcji kończonej rollbackiem; nie jest to nowy trening ani zmiana historii.

## Outcome

### Changed

Prywatny `_budgeted_rows` pobiera maksymalnie 200 wierszy, ustawia pozostały
timeout przed FETCH i sprawdza zegar po partii. Wszystkie strumienie wejść
korzystają z helpera. Kursory zamykają się również przy błędzie konsumenta.
Zachowano treść SQL, pełny zakres i kolejność blokad oraz limity 60/30/5 s.

### Verification results

Unit 57 PASS; ruff check/format 3 pliki PASS; scoped mypy zmienionego modułu
PASS. PG selection 1 PASS (270 komórek, komplet blokad, 11 odświeżeń budżetu,
izolacja i rollback); PG registry/restart 1 PASS. Porównanie siedmiu literałów
SELECT z `5cfe292b` potwierdza identyczność. Docs PASS 44820/45000 B,
mapa zregenerowana i sprawdzona. Szczegóły: `quality/TASK-1149_VERIFICATION.md`.

### Not completed

Niezależny audyt, commit i task-close pozostają po stronie prowadzącego.
Bez operacji na main, usługach i bazie operatora, bez nowego treningu lub
dużego benchmarku. Nie zmierzono jeszcze czasu poprawionego freeze operatora.

### Documentation updates

Krótka nota techniczna VISION_LAB, raport weryfikacji oraz regeneracja mapy.
Dokumenty TASK-1147 i CURRENT_STATE pozostawiono prowadzącemu.

### Recommended next task

Focused Opus 5.5/high, następnie wdrożenie poprawki i kontynuacja odbioru
TASK-1147 przez prowadzącego. Bez ponownego startu parenta lub odnowienia budżetu.
