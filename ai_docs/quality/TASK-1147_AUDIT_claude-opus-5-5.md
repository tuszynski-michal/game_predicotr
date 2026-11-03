# Audyt TASK-1147 — Integracja przyrostu korekt i wymiany źródeł

Werdykt: PASS
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6-astra, high
Zakres: HEAD...7881711b51388bf24b7fea7320782cfe69dc600e oraz zmiany niezacommitowane, data 2026-11-03
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Sprawdziłem przepięcie migracji 0178 na rodzica 0177, nowy wspólny moduł `source_recording_replacement_sql.py` i jego użycie w SQL v6 oraz w downgrade 0178. Przejrzałem też readiness i testy, a także dokumentację planu, taska i weryfikacji. Strażnik z 0175 jest przeniesiony bez zmian. W pamięci procesu porównałem złożony tekst SQL z treścią 0175: wrapper i funkcja photo przywracane przy downgrade do 0177 są identyczne z tym, co instaluje 0175. SQL v6 zawiera strażnika i filtr aktualnej populacji dokładnie raz, a polityka v2 pozostaje zachowana. Nie znalazłem błędów P0 ani P1. Główne ryzyko jest procesowe: część dowodów testowych powstała przed ostatnimi zmianami bajtów (autofix ruff i późniejsza edycja 0178), a build Admina przeszedł tylko z tymczasowymi aliasami.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `services/api/src/game_predictor_api/storage/source_recording_sql_v6.py:229` — Kolejność zdarzeń według czasów modyfikacji plików i logów:
  - Testy PG zakończyły się między 11:10 a 11:12: guarded migration, replacement guards i registry.
  - Testy API i workera zakończyły się o 11:08.
  - O 11:13:40 skrypt lint uruchomił `ruff format` i `ruff check --fix`. Log `artifacts/task1147-python-lint.log` pokazuje „1 file reformatted” oraz „3 fixed”. Zmieniły się wtedy `source_recording_sql_v6.py` i `_grid_growth_replacement_fence.py`.
  - Plik `0178_grid_correction_growth.py` zmieniono jeszcze później, o 11:15:36, czyli po wszystkich testach Pythona, lincie i mypy.

  `ai_docs/quality/TASK-1147_VERIFICATION.md:30` raportuje jednak lint jako PASS, a testy PG jako dowód dla stanu końcowego. Mój tylko-odczytowy `ruff check --no-cache` i `ruff format --check` na 7 plikach z zakresu dają PASS. Zmiany wyglądają na neutralne semantycznie (autofix i komentarz). Mimo to dowód testowy nie odpowiada bajtom, które trafią do commita. Proponowana poprawka: przed commitem powtórzyć na stanie końcowym `test_grid_correction_growth_migration_postgres.py`, `test_source_replacement_guards_postgres.py`, test registry i `test_schema_readiness.py`. Ruff i mypy uruchomić w trybie check, bez `--fix`, a wynik dopisać do weryfikacji.

- [P2-2] `ai_docs/quality/TASK-1147_VERIFICATION.md:38` — Typecheck i build Admina przeszły dzięki tymczasowym aliasom. Wspólne `node_modules` w worktree wskazują na starszy root. To jawnie oznaczone obejście sesyjne, więc nie dowodzi, że build przejdzie przy normalnym rozwiązywaniu workspace’ów. Proponowana poprawka: w kroku po fast-forward `main` uruchomić `npm run typecheck --workspace @game-predictor/admin` oraz build Admina, najlepiej `npm run quality`, bez aliasów. Zapisać to w odbiorze, tak jak wymaga reguła trwałości z `AGENTS.md`.

- [P2-3] `services/api/tests/integration/_grid_growth_replacement_fence.py:50` — Test ochrony sprawdza tylko kohortę z polityką `application-grid-corrections-v1` i ścieżkę `validate_cohort_use`. Nie ma też szybkiego testu bez PG, który pilnowałby, że złożony SQL jest identyczny z SQL 0175. Teraz potwierdza to tylko moje porównanie w pamięci, a w repozytorium nic tego nie chroni. Dotyczy to stałych z `services/api/src/game_predictor_api/storage/source_recording_replacement_sql.py:61-68`. Skutek: przyszła zmiana kotwic v4/v5/v6 albo kolejności `.replace` mogłaby niezauważenie rozjechać downgrade z 0175. Proponowana poprawka: dodać test jednostkowy, który:
  - porównuje `REPLACEMENT_V5_WRAPPER` i odcinek photo z `REPLACEMENT_V4_SQL` z wynikiem przekształceń 0175;
  - sprawdza, że w `PHOTO_SQL` i `WRAPPER_SQL` z v6 strażnik oraz filtr `source_replacement_source_current_v1` występują dokładnie raz.

  Opcjonalnie dodać do testu ochrony wariant kohorty v2.

- [P2-4] `ai_docs/quality/TASK-1147_VERIFICATION.md:47` — Dwie porażki w `test_grid_cohort_asset_retention.py` są odtworzone również na `60f50c64` i udokumentowane tylko w weryfikacji tego taska. Nie ma ich w `CURRENT_STATE.md` ani w osobnym tasku. Jedna dotyczy styku retencji kohort z nowym `source_replacement_gc_guard`, czyli obu integrowanych pionów. Proponowana poprawka: zapisać znany problem w stanie bieżącym albo założyć task naprawczy. Druga możliwość to akceptacja ryzyka przez prowadzącego, odnotowana w `Outcome`.

- [P2-5] `services/api/src/game_predictor_api/storage/schema_readiness.py:50` — Readiness porównuje tylko `version_num`. Zdarzy się to tylko wtedy, gdy jakaś baza została wcześniej podbita do 0178 w starym grafie, z rodzicem 0171. Wtedy `upgrade head` nic nie zrobi, a readiness przepuści schemat bez 0172–0177. Plan i TASK-1145 twierdzą, że 0178 nigdy nie wdrożono, a baza operatora jest na 0171, więc ryzyko jest niskie. Proponowana poprawka: w kroku wdrożenia (`ai_docs/delivery/GRID_CORRECTION_GROWTH_PLAN_20261103.md:168`) przed migracją jawnie zapisać i sprawdzić, że rewizja bazy to 0171 albo 0177, nigdy 0178. Można też zaakceptować ryzyko na podstawie istniejących zapisów.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Jedyny head 0178, parent 0177, zachowane starsze rewizje | spełnione | `services/api/alembic/versions/0178_grid_correction_growth.py:24-25`; `services/api/src/game_predictor_api/storage/schema_readiness.py:18`; `services/api/tests/test_schema_readiness.py:15-21` oraz lista odmów `:72-79`; katalog `versions` zawiera 0172–0177 bez zmian (grep: tylko 0175 modyfikuje funkcje recording) |
| SQL chroni wycofane i zarezerwowane źródła po upgrade oraz downgrade; historia i replay bezpieczne | spełnione | `services/api/src/game_predictor_api/storage/source_recording_replacement_sql.py:6-68`; `source_recording_sql_v6.py:229-230`; `0178_grid_correction_growth.py:10-15,71-85`. Porównanie w pamięci: strażnik, wrapper i photo przy downgrade są identyczne z 0175, a kontekst v4 jest bez zmian. Test ochrony przed downgrade, po downgrade i po ponownym upgrade: `test_grid_correction_growth_migration_postgres.py:25-27,48` (log: 1 passed). Replay na head: `test_source_replacement_guards_postgres.py:489-566` (log: 1 passed). Zastrzeżenie: P2-1 |
| Zachowane funkcje obu gałęzi, kontrakty, partial v1/v2 i UI | niezweryfikowane (statycznie częściowo) | Polityka v2 we wrapperze i photo v6 zachowana: `source_recording_sql_v6.py:161-228`. Populacja w Pythonie jest spójna z filtrem SQL: `storage/grid_correction_split.py:101`. Logi wykonawcy: evaluator 5 passed, API/worker 104 passed, UI i requesty PASS. OpenAPI, SDK i UI są poza pathspec briefu |
| Dokumenty obu historii zachowane, okna i budżety przechodzą kontrolę | niezweryfikowane (na podstawie logów) | `artifacts/task1147-docs.log`: decyzje, okno stanu i budżet 44765 B OK. `artifacts/task1147-preservation.log`: `notExact: []`. Treści archiwów są poza pathspec briefu |
| Wymagane testy, lint/types/build i focused audyt rozliczone przed commitem | niezweryfikowane | Zgodnie ze stanem taska kryterium jest otwarte. Ten raport jest focused audytem. Przed zamknięciem patrz P2-1 i P2-2 |
| Skoordynowane wdrożenie i odbiór operatora | niespełnione (zgodnie z deklaracją, BLOCKED) | `ai_docs/quality/TASK-1147_VERIFICATION.md:69-76`; task słusznie nie oznacza tego kryterium |

## Listy zamknięte i otwarte

Zamknięte: nie dotyczy, runda 1.

Otwarte: P2-1, P2-2, P2-3, P2-4, P2-5.

## Proponowane testy

- Ponowne uruchomienie na końcowych bajtach z `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'`: `.\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_grid_correction_growth_migration_postgres.py services/api/tests/integration/test_source_replacement_guards_postgres.py services/api/tests/test_schema_readiness.py`, a także test registry korekt.
- Nowy test jednostkowy bez PG, np. `services/api/tests/test_source_recording_replacement_sql.py`. Sprawdza on:
  - równość `GUARD_SQL` z treścią strażnika 0175;
  - równość `REPLACEMENT_V5_WRAPPER` i odcinka photo z `REPLACEMENT_V4_SQL` z przekształceniami 0175;
  - jednokrotne wystąpienie `SOURCE_REPLACEMENT_RESERVED` i filtra `source_replacement_source_current_v1(wanted,s.id` w `PHOTO_SQL`/`WRAPPER_SQL` z v6.

  Uruchomienie: `.\.venv\Scripts\python.exe -m pytest services/api/tests/test_source_recording_replacement_sql.py`.
- Wariant `assert_replacement_fence` z kohortą `application-grid-corrections-v2` w `services/api/tests/integration/_grid_growth_replacement_fence.py`.
- Po fast-forward `main`: `npm run quality` albo co najmniej typecheck i build Admina bez aliasów. Przed migracją operatora warto też uruchomić `npm run db:baseline:verify` oraz `test_recording_migration_lifecycle_postgres.py`, który robi downgrade z nowego head przez cały łańcuch 0178–0172.

## Zakres przeglądu i ograniczenia

Przeczytane:

- brief z taskiem, fragmentem planu i diffem;
- `0178_grid_correction_growth.py`, `0175_source_replacement_guards.py` oraz grep migracji 0172–0177 pod kątem funkcji recording;
- `source_recording_replacement_sql.py`, `source_recording_sql_v6.py`, odpowiednie fragmenty `source_recording_sql_v4.py`/`v5.py` i `schema_readiness.py`;
- `test_schema_readiness.py`, `test_grid_correction_growth_migration_postgres.py`, `_grid_growth_replacement_fence.py` oraz fragment `test_source_replacement_guards_postgres.py`;
- populacja w `grid_correction_split.py`, reguły z `AGENTS.md` i ogony logów `artifacts/task1147-*.log`.

Polecenia tylko do odczytu:

- `ruff check --no-cache` i `ruff format --check --no-cache` na 7 plikach z zakresu: PASS;
- `python -B`: porównanie złożonych stałych SQL z przekształceniami 0175 wykonane w pamięci, bez zapisu bajtkodu.

Czego nie zrobiłem:

- nie uruchamiałem testów PG, testów UI, mypy ani buildu;
- nie przeglądałem zregenerowanego OpenAPI/SDK, kodu UI ani pełnej treści rozwiązanych konfliktów dokumentacji, bo są poza pathspec briefu;
- tych obszarów nie da się w pełni potwierdzić statycznie, więc opieram się na logach wykonawcy.
