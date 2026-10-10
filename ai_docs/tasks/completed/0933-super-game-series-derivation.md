# TASK-0933 — Wyprowadzanie serii supergry i API serii

## Status

`done`

## Goal

Dla gry z rodzajem `wild_super_spins` system wyprowadza z pociętych plansz
serie supergry (trigger, długość z retriggerami, status, weryfikacja
triggera) do tabeli `super_game_series`, odświeża je po korektach symboli i
udostępnia API listy, plansz serii i zapisu super symbolu.

## Context

Super symbol jest widoczny tylko na zdjęciach, więc operator definiuje go
ręcznie; system musi najpierw wskazać, gdzie zaczyna się i kończy seria.
Plan: etap S-B, sekcja „Supergra jako stan sekwencji”.

## Dependencies / entry conditions

- TASK-0931 (role, rejestr rodzajów) i TASK-0932 (ewaluator) zacommitowane.
- Fakt: tabele gry są partycjonowane `LIST (game_id)` z RLS
  (`ai_docs/architecture/GAME_DATA_V2_OWNERSHIP.md`); nowa tabela musi być
  sklasyfikowana w bramce własności.
- Decyzja operatora: do progu liczą się komórki z przypisanym symbolem
  (predykcja albo człowiek); plansza musi być pocięta.

## Recommended execution

claude-opus-5-5 / high. Tabela partycjonowana, wyprowadzanie z przypadkami
brzegowymi, durable job, API pionem. Eskalacja do claude-fable-5-1 / high
przy problemach z RLS lub wydajnością przejścia po 500 000 pozycji. Audyt:
gpt-6-astra / high; do czasu CLI zamiennik claude-fable-5-1 / high.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/MUMIE_SUPER_GAME_EXECUTION_PLAN_20261008.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/GAME_DATA_V2_OWNERSHIP.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

- Migracja: `super_game_series` (partycja per gra): `id`, `game_id`,
  `trigger_sequence_number`, `start_sequence_number`, `length`,
  `retrigger_sequence_numbers integer[]` (numery do 500 000; test z numerem
  > 32 767), `completeness` (`complete|incomplete`), `run_verification`
  (`verified|unverified`, obejmuje trigger i wszystkie retriggery),
  `super_symbol_id` FK symbols null, `defined_by`, `defined_at`, `revision`,
  `generation_id`, `updated_at`; unikalność `(game_id, trigger_sequence_number)`;
  tabela robocza generacji i tabela audytu zmian super symbolu.
- Use case `derive_super_game_series(game_id)`: strumieniowe przejście po
  pozycjach `1…expected_layout_count` (partie, bez ładowania wszystkich
  plansz do pamięci); reguły z rejestru rodzaju; stan `base/super` i licznik
  pozostałych spinów; brak planszy = pusta, spin zużyty; seria wychodząca
  poza ostatnią znaną planszę → `completeness = incomplete`.
- Generacja i podmiana: job zapisuje serie do tabeli roboczej z nowym
  `generation_id`; po przejściu całej sekwencji podmienia zawartość gry w
  **jednej transakcji** (usuń serie nieobecne w generacji z audytem; wstaw
  nowe; dla istniejącej tożsamości `(game_id, trigger)` zaktualizuj przedział,
  `completeness`, `run_verification`, zachowując `super_symbol_id`, `revision`
  i `defined_*`). Przedłużenie przez nowy retrigger **nie** kasuje symbolu.
  Restart joba kasuje tabelę roboczą tej generacji i zaczyna od nowa; żaden
  stan pośredni nie jest widoczny w API.
- Źródło wejścia: komórki z przypisanym symbolem (decyzja człowieka albo
  predykcja, także plansze `pending`) z projekcji weryfikacji komórek, nie
  z kanonicznej projekcji `accepted/corrected`; plansza liczy się tylko po
  pocięciu siatką (komplet komórek z geometrią). Zbiór wejścia = te komórki
  + katalog ról symboli + `super_game_kind` + aktywna wersja reguł.
- Wersja wejścia (zamiast maksimum rewizji/`updated_at`, które nie wykrywa
  każdej zmiany ani usunięcia): tabela `super_game_derivation_state`
  (`game_id` PK, `input_version bigint`, `current_generation_id`,
  `input_version_of_generation`, `updated_at`; nieaktualność **nie jest
  osobną kolumną**, lecz wynika zawsze z porównania
  `input_version != input_version_of_generation`, więc jest widoczna od
  pierwszej zmiany wejścia, także przed startem joba i w trakcie jego
  pracy). Każdy zapis
  zmieniający zbiór wejścia (zapis/usunięcie predykcji, korekta symbolu,
  korekta i unieważnienie siatki, import plansz, zmiana roli symbolu,
  zmiana rodzaju gry, publikacja reguł) inkrementuje `input_version` **w tej
  samej transakcji** co zapis; lista punktów zapisu jest wyliczona w kodzie
  i pokryta testem. Job odczytuje `input_version` na starcie; transakcja
  publikacji blokuje wiersz stanu (`FOR UPDATE`) i porównuje wersję
  atomowo z podmianą.
- Kandydat nieaktualny: jeżeli wersja się zmieniła, generacja robocza jest
  **odrzucana** (nie podmienia obowiązujących serii), a job kolejkuje
  dokładnie jeden ponowny przebieg (deduplikacja na grę). Do zakończenia
  przeliczenia API serwuje ostatnią opublikowaną generację, a każda
  odpowiedź kalkulacji i wyszukiwania niesie na **poziomie odpowiedzi**
  pole `superGameState: { fresh: boolean, inputVersion,
  generationInputVersion }` wyliczone z porównania wersji, niezależnie od
  tego, czy dana plansza ma `superGame`; konsumenci (TASK-0935, TASK-0936)
  pokazują ostrzeżenie i liczą wszystkie plansze gry jako `provisional`,
  gdy `fresh = false` (nowy trigger mógł powstać tam, gdzie poprzednia
  generacja miała tryb bazowy). Podział (decyzja leada 2026-10-09 po
  audycie Codex): TASK-0933 dostarcza trasę `GET …/super-game-series/state`
  i pole `superGameState` w odpowiedziach serii; pole na poziomie odpowiedzi
  wyszukiwania plansz i przybliżonej wygranej (kalkulacji) dostarcza
  TASK-0935, właściciel projekcji wyszukiwania. CAS zapisu symbolu sprawdza
  `revision` i tożsamość serii; zapis w stanie `stale` jest dozwolony i
  przenosi się po tożsamości.
- Wyzwalanie: durable job lane `general` po: zakończeniu importu (nowe
  plansze), zapisie predykcji symboli, korekcie symboli, korekcie siatki,
  zmianie roli symbolu lub rodzaju gry, publikacji wersji reguł; z
  deduplikacją na grę; ręcznie z API.
- API: `GET /api/v1/games/{gameId}/super-game-series?status&verification&cursor`,
  `POST …/super-game-series/derive`, `GET …/super-game-series/{seriesId}/boards`
  (plansze `trigger…start+length-1` w formacie widoku wyszukiwania plansz,
  z `missing: true` dla brakujących), `PUT …/super-game-series/{seriesId}/super-symbol`
  (`symbolId | null`, `expectedRevision`; konflikt → 409). OpenAPI, klient,
  wrappery, request testy.

## Out of scope

- UI (TASK-0934, TASK-0935), wypłaty serii (TASK-0936).
- Gry z rodzajem `none` (zero serii, job kończy się natychmiast).

## Acceptance criteria

- [x] Łańcuch: trigger na 100, retrigger na 105 → seria 101–120; trigger na
      110 w serii nie otwiera nowej.
- [x] Brak planszy 103 → seria bez zmian długości; plansza oznaczona `missing`.
- [x] Ostatnia znana plansza 108 przy serii 101–110 → `incomplete`.
- [x] Trigger albo retrigger z komórką bez decyzji człowieka → `unverified`.
- [x] Ponowne wyprowadzenie bez zmian plansz nie zmienia `revision` ani
      `super_symbol_id`; nowy retrigger przedłuża serię i zachowuje symbol;
      utrata triggera usuwa serię z wpisem audytu; pochłonięcie triggera przez
      wcześniejszą serię usuwa późniejszą, wcześniejsza zachowuje swój symbol.
- [x] Retrigger o numerze 40 000 zapisuje się i odczytuje poprawnie.
- [x] Restart joba w połowie: API nie pokazuje stanu pośredniego; po
      ponownym przebiegu wynik identyczny z przebiegiem bez restartu.
- [x] Korekta symbolu w trakcie joba: kandydat odrzucony, obowiązujące serie
      bez zmian, `superGameState.fresh = false`, dokładnie jeden ponowny
      przebieg, wynik uwzględnia korektę; po nim `fresh = true`.
- [x] Nowy trigger zapisany przed startem joba: `superGameState.fresh =
      false` w `GET …/super-game-series/state` i w odpowiedziach serii; w
      trakcie pracy joba nadal `false`; po publikacji `true` i seria z tym
      triggerem na liście. Ta sama asercja dla odpowiedzi wyszukiwania (brak
      `superGame` przed publikacją, `superGame.kind = trigger` po niej)
      przechodzi do TASK-0935 (decyzja leada 2026-10-09 po audycie Codex).
- [x] Każdy punkt zapisu z listy wejścia inkrementuje `input_version` w tej
      samej transakcji (test parametryczny po liście); usunięcie predykcji
      też.
- [x] Zmiana rekordu o niskiej rewizji przy innym rekordzie o wyższej
      (scenariusz 100 / 1→2) jest wykrywana.
- [x] `PUT super-symbol` z nieaktualnym `expectedRevision` → 409, bez zapisu.
- [x] Bramka własności tabel V2 klasyfikuje nową tabelę.

## Technical notes

- Źródło prawdy komórek: wyłącznie kontrakt z sekcji Scope (projekcja
  weryfikacji komórek z przypisanym symbolem, także plansze `pending`,
  pocięte siatką); kanoniczna projekcja `accepted/corrected`
  (`image_sequence_canonical.py`) **nie** jest źródłem wyprowadzania.
- Sekwencja startuje w trybie bazowym na pozycji 1; zawinięcie `N → 1` nie
  przenosi serii (plan, Z-1 poprzedniej rewizji).
- Granice transakcji: tabela robocza zapisywana partiami (osobne
  transakcje), podmiana w jednej transakcji końcowej razem z porównaniem
  `input_version` pod blokadą wiersza stanu; rozmiar partii i pomiar
  pamięci w Outcome.

## Expected files

- Nowe: migracja `015x_super_game_series.py`,
  `services/api/src/game_predictor_api/domain/super_game_series.py`,
  `application/super_game_series.py`, `storage/super_game_series_repository.py`,
  `api/super_game_series.py`, `schemas/super_game_series.py`,
  handler joba w `services/worker`.
- Istniejące: rejestr jobów, bramka własności V2, `DATA_MODEL.md`,
  `API_CONTRACT.md`, `packages/admin-api-client` (generowany).

## Test cases

- Jak w kryteriach; dodatkowo test PG (opcjonalny, `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`)
  na 2 000 pozycji z 30 seriami: czas i pamięć w granicach partii.

## Verification

```powershell
# katalog worktree, timeout 120 s każda
.\.venv\Scripts\python.exe -m pytest services/api/tests -k "super_game" -q
.\.venv\Scripts\python.exe -m pytest services/worker/tests -k "super_game" -q
npm run openapi:generate; npm run openapi:check
npm run python:lint; npm run python:typecheck
```

## Risks / open questions

- Fałszywe triggery z predykcji Mumia↔Sarkofag; pole `trigger_verification`
  i ponowne wyprowadzanie po korektach ograniczają skutki.
- Wydajność na 500 000 pozycji: wymagany pomiar w Outcome.
- Super symbolem może być tylko zwykły symbol (nie Wild, nie uruchamiający);
  walidacja w `PUT super-symbol`.

## Outcome

Wykonawca: claude-opus-5-5 (subagent sesji prowadzącej). Commit, audyt
krzyżowy, `CURRENT_STATE.md` i ewentualny wpis `DECISION_LOG.md` wykonuje
sesja prowadząca.

### Changed

- Commit v1.7.276 / 221e43ed0c645c218e84b2bee34785608ef04f1d (zapis dodany po commicie przez leada).

- **Schemat i manifest.** Migracja `0152_super_game_series` (po
  `0151_super_game_roles`) tworzy w `game_data_v2` cztery tabele
  partycjonowane `LIST (game_id)` z wymuszonym RLS `game_scope_v1`:
  `super_game_series` (tożsamość `(game_id, trigger_sequence_number)`,
  `retrigger_sequence_numbers integer[]`, `completeness`, `run_verification`,
  `super_symbol_id` z FK `(game_id, id)` do `symbols`, `defined_by/at`,
  `revision`, `generation_id`), `super_game_series_generation_rows` (tabela
  robocza generacji), `super_game_derivation_state` (`input_version`,
  `current_generation_id`, `input_version_of_generation`, bez kolumny
  nieaktualności) i `super_game_series_audit_events`. Dodaje wartość
  `super_game_series_derive` do enumu `job_type`, partycje istniejących gier,
  wiersze manifestu i przestawia lokalizacje z manifestu v5 na v6. Nowy
  zamrożony moduł `storage/game_data_v2_manifest_v6.py` klasyfikuje cztery
  tabele jako `game` (ten sam mechanizm co 0142/v5); bieżące moduły
  (routing, cykl życia partycji, katalog, `scripts/delete_archived_v2_game.py`)
  i testy bieżącego manifestu importują v6. Strażnik startowy wymaga
  `0152_super_game_series`. Downgrade odmawia przy zdefiniowanym super
  symbolu, wpisie audytu albo aktywnym jobie wyprowadzania, inaczej usuwa
  tabele i wraca do v5 (etykieta enumu zostaje, jak w 0083).
- **Wybór tabeli roboczej.** Partycja gry, nie wspólny staging: wiersze są
  danymi jednej gry (RLS, usuwanie z grą przez cykl życia partycji), a
  podmiana czyta je w tym samym zakresie gry co serie.
- **Wersja wejścia.** `storage/super_game_input_version.py`:
  `SUPER_GAME_INPUT_WRITE_POINTS` (10 punktów po rundzie poprawek) i
  `record_super_game_input_change` (upsert `input_version + 1` w transakcji
  zapisu, raz na transakcję i grę; potem kolejkowanie joba). Punkty:
  `SymbolCellReviewWriteThroughCoordinator._touch_catalog_revision`
  (wspólny punkt wszystkich zapisów komórek: zapis i odświeżenie predykcji,
  korekty człowieka, decyzje planszy, korekty i unieważnienia siatki,
  materializacja plansz importu), `finalize_backfill`,
  `_delete_board_source_graph` (usunięcie plansz, komórek i predykcji),
  `reset_game`, `save_symbol`, `add_symbol`, `add_manual_symbol` (zmiana ról
  `is_wildcard`, `super_game_trigger_count`), `save_game` (zmiana
  `super_game_kind`), `save_rules_version` (publikacja i archiwizacja).
  Zapisy workera przechodzą przez koordynatora w tej samej sesji. Kolejność
  blokad w cleanupie jest zgodna z koordynatorem (wiersz stanu weryfikacji
  symboli, potem wiersz stanu supergry). Reset gry usuwa serie, audyt i
  wiersze robocze przed usunięciem symboli; wiersz stanu zostaje, więc
  licznik tylko rośnie.
- **Domena.** `domain/super_game_series.py`: `SuperGameSeriesDeriver`
  (strumieniowy, trzyma tylko bieżącą serię), `evaluate_board_trigger`
  (co najmniej N komórek symbolu uruchamiającego; `verified`, gdy próg
  osiąga sam podzbiór komórek z decyzją człowieka), `series_positions` (bez
  pozycji poza `expected_layout_count`), `SuperGameState.fresh`
  (`input_version == input_version_of_generation`; gra `none` zawsze
  świeża), walidacja super symbolu (aktywny, nie Wild, nie uruchamiający).
- **Aplikacja i storage.** `application/super_game_series.py`
  (`SuperGameSeriesDerivation`, `SuperGameSeriesService`) i
  `storage/super_game_series_repository.py`. Wejście: komórki z przypisanym
  symbolem aktywnych elementów przeglądu (`pending`, `accepted`,
  `corrected`); na pozycję plansza kanoniczna, a bez niej element o
  najmniejszym id; plansza liczy się tylko przy 15 komórkach z geometrią w
  bieżącej rewizji geometrii planszy. Okna odczytu startują od następnej
  pozycji z komórką symbolu uruchamiającego (puste odcinki są pomijane
  indeksem); każde okno i każda partia wierszy roboczych to osobna
  transakcja. Publikacja w jednej transakcji: `FOR UPDATE` wiersza stanu,
  porównanie `input_version`, audyt i usunięcie serii nieobecnych w
  generacji, aktualizacja istniejących tożsamości bez zmiany `id`,
  `super_symbol_id`, `revision` i `defined_*`, wstawienie nowych, zapis
  wersji generacji. Przy niezgodności kandydat jest odrzucany, wiersze
  robocze usuwane, a ponowny przebieg kolejkowany z deduplikacją (jeden job
  `created` na grę, serializacja przez blokadę wiersza stanu; globalny
  `input_key` pozostaje unikalny dzięki `request_id`). Start joba usuwa
  wiersze robocze wcześniejszych generacji.
- **Job.** `JobType.SUPER_GAME_SERIES_DERIVE` (lane `general`), handler
  `services/worker/src/game_predictor_worker/super_game_series.py` w
  rejestrze `cli.py`, checkpoint postępu i raport generacji; odrzucony
  kandydat kończy job jako `completed` z `status = rejected` i
  `rerun_job_id`. Gra `none` publikuje pustą generację (stare serie usuwa z
  audytem). Schemat payloadu `SuperGameSeriesDeriveJobPayload`, etykieta w
  `apps/admin/src/features/jobs/job-state.ts`.
- **API.** Trasy `/api/v1/admin/games/{gameId}/super-game-series…`
  (`listSuperGameSeries`, `getSuperGameSeriesState`, `deriveSuperGameSeries`,
  `listSuperGameSeriesBoards`, `setSuperGameSeriesSuperSymbol`), schematy
  `schemas/super_game_series.py`, błędy 404/409/422, OpenAPI i klient
  zregenerowane, wrappery w `packages/admin-api-client/src/index.ts`, test
  żądań w `test/client.test.mjs`.

Rozmiar partii: 5 000 pozycji na okno odczytu i 500 serii na partię
wierszy roboczych (`DEFAULT_POSITION_BATCH_SIZE`,
`DEFAULT_GENERATION_WRITE_BATCH_SIZE`). Granice transakcji: odczyty i
zapisy robocze są osobnymi krótkimi transakcjami, które nie trzymają blokad
na komórkach ani na wierszu stanu dłużej niż jedno okno; jedynym zapisem
widocznym dla API jest końcowa transakcja publikacji, porównująca wersję pod
`FOR UPDATE`. Dlatego przerwanie przed nią nie zmienia opublikowanych serii,
a zapis wejścia równoległy do joba zawsze kończy się odrzuceniem kandydata.

### Verification results

- `.\.venv\Scripts\python.exe -m pytest services/api/tests -k "super_game or schema_readiness or game_data_v2_schema or jobs" -q`:
  134 passed, 12 skipped (testy PG bez zmiennej), 107 s.
- `.\.venv\Scripts\python.exe -m pytest services/api/tests -k "catalog or rules or cleanup or image_symbol_review or symbol_cell or grid_correction or unreadable or virtual_grid or jobs" -q`:
  471 passed, 16 skipped (ścieżki zapisu z nowym podbiciem wersji).
- `.\.venv\Scripts\python.exe -m pytest services/worker/tests -k "super_game" -q`:
  8 passed; `services/worker/tests/test_worker_cli.py`: 6 passed.
- PostgreSQL (`$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'`, bazy `*_test`):
  - `test_postgres_baseline.py`, `test_super_game_series_postgres.py`,
    `test_image_geometry_completeness_repository.py`,
    `test_board_import_coverage_repository.py`, `test_catalog_repository.py`,
    `test_cleanup_repository.py`: 56 passed (393 s).
  - `test_grid_correction_cell_symbols_postgres.py`,
    `test_board_search_share_corrections.py`, `test_management_postgres.py`,
    `test_symbol_review_bulk_start_locking_postgres.py`,
    `test_game_partition_lifecycle_postgres.py`,
    `test_per_game_isolation_new_game.py`,
    `test_application_role_isolation_postgres.py`,
    `test_game_storage_routing_postgres.py`: 61 passed, 1 failed.
    `test_public_write_retry_review_and_rollback` uruchamia podproces
    `python -c` bez `PYTHONPATH`, który w worktree importuje kod głównego
    checkoutu (manifest v5); z `PYTHONPATH` wskazującym worktree: 1 passed.
    Artefakt środowiska worktree, nie błąd kodu.
  - Po ostatnich zmianach: `test_super_game_series_postgres.py`,
    `test_cleanup_repository.py`, `test_image_batch_store.py`,
    `test_neural_manual_slot_symbols_postgres.py`, `test_review_repository.py`,
    `test_partial_board_reconciliation_postgres.py`,
    `test_symbol_rgb_v2_writer_postgres.py` i `test_grid_shadow_rls_postgres.py`
    (z `GAME_PREDICTOR_RUN_GRID_SHADOW_POSTGRES_TESTS=1`): 39 passed,
    1 failed. `test_existing_games_upgrade_and_nonempty_downgrade_refusal`
    zatrzymuje się na istniejącej odmowie downgrade migracji 0150
    („destructive downgrade is disabled”) już po poprawnym downgrade 0152;
    błąd sprzed tego taska (TASK-0940: migracje 0148–0150 bez downgrade).
  - Nowy test cyklu migracji 0152 (odmowa przy decyzji operatora, downgrade
    do 0151 i powrót do v5, upgrade do v6 z partycjami RLS) i test CAS:
    2 passed.
  - `test_super_game_series_postgres.py` (11 testów, rola aplikacyjna z
    RLS): łańcuch 100/105/110, brak planszy 103, plansza niepocięta,
    `incomplete`, `unverified`, zachowanie symbolu i `revision` przy
    ponownym wyprowadzeniu, przedłużenie retriggerem, pochłonięcie triggera
    i utrata triggera z audytem, retrigger 40 000, restart w połowie bez
    stanu pośredniego i z identycznym wynikiem, korekta w trakcie joba z
    odrzuceniem kandydata i dokładnie jednym jobem `created`,
    `fresh = false` od zapisu do publikacji, transakcyjność podbicia
    (rollback cofa, dwa wywołania w transakcji liczą się raz), scenariusz
    100 / 1→2, CAS 409 bez zapisu, rodzaj `none` daje zero serii.
  - Pomiar: 2 000 pozycji, 30 serii, okno 500 pozycji, partia 8 serii:
    0,85–1,05 s, szczyt pamięci Pythona (tracemalloc) 0,27 MB, 4 okna
    (`SUPER_GAME_DERIVATION_2000: seconds=0.848 peak_bytes=269205 batches=4
    series=30`). Pomiaru na 500 000 pozycji nie wykonano (benchmark wymaga
    zgody); koszt rośnie z liczbą okien zawierających komórki symbolu
    uruchamiającego, puste odcinki są pomijane.
- `.\.venv\Scripts\python.exe -m alembic heads`: `0152_super_game_series (head)`.
- `npm run openapi:generate` (13 plików `generated/client/*`,
  `generated/core/*` i `client.gen.ts` przywrócone `git checkout`, różniły
  się tylko końcami linii), `npm run openapi:check`: PASS.
- `npm run test --workspace @game-predictor/admin-api-client`: 103 pass.
- `npm run typecheck` (w tym mypy na 846 plikach): PASS; `npm run lint`
  (w tym ruff): PASS; `npm run format:check`: PASS; `ruff format` i
  `mypy --strict` na zmienionych modułach: PASS.

### Not completed

- Pole `superGameState` na poziomie odpowiedzi wyszukiwania plansz i
  przybliżonej wygranej oraz asercja kryterium dla odpowiedzi wyszukiwania
  przeszły do TASK-0935 (decyzja leada 2026-10-09 po audycie Codex,
  zapisana w Scope, kryteriach i planie). TASK-0933 dostarcza
  `superGameState` w odpowiedziach serii, trasę `…/super-game-series/state`
  i test PG nieaktualności przed startem joba i w jego trakcie.
- Trasy mutujące (`derive`, `super-symbol`) nie mają nagłówków
  potwierdzenia: niedestrukcyjne trasy katalogu (`PATCH` gry, symbole) ich
  nie używają, a `confirmedTargetHeaders` służy operacjom destrukcyjnym.
- Ścieżka z taska (`/api/v1/games/…?status&verification`) zastąpiona
  konwencją Admina `/api/v1/admin/games/…` i nazwami pól (`completeness`,
  `runVerification`, `defined`).
- `apply_board_repoint` nie podbija wersji (zaakceptowane przez leada):
  przepina komórki na nowszy identyfikator rewizji geometrii tego samego
  źródła i nie zmienia ani przypisanych symboli, ani tego, czy plansza jest
  pocięta; uzasadnienie jest też w komentarzu przy
  `SUPER_GAME_INPUT_WRITE_POINTS`.
- Bez UI (TASK-0934), znacznika w wyszukiwaniu (TASK-0935) i wypłat
  (TASK-0936). Brak wpisu `DECISION_LOG.md` (manifest v6, licznik wejścia) i
  aktualizacji `CURRENT_STATE.md`: decyzja i numeracja po stronie sesji
  prowadzącej.

### Audyt i runda poprawek

Audyt krzyżowy Codex (gpt-6-astra, high), runda 1: REVISE, 2 × P0 i 2 × P1
(`ai_docs/quality/TASK-0933_AUDIT_gpt-6-astra.md`). Jedna runda poprawek:

- **P0-1 — `expected_layout_count` jako wejście.** `save_game` porównuje
  oba pola przed przypisaniem i podbija wersję (z kolejkowaniem joba) także
  przy zmianie `expected_layout_count`; nowy punkt
  `expected_layout_count` w `SUPER_GAME_INPUT_WRITE_POINTS`. Testy: jednostkowy
  (`test_save_game_bumps_on_layout_count_and_kind_changes_only`: brak
  podbicia przy zmianie nazwy i statusu, podbicie przy zmianie liczby i
  rodzaju) oraz PG (`test_expected_layout_count_change_invalidates_and_rejects`:
  zmniejszenie 1000 → 500 przed jobem daje `fresh = false` i job w kolejce,
  następny przebieg usuwa serię z triggerem 700 z wpisem audytu; zmiana w
  trakcie joba odrzuca kandydata, kolejny przebieg uwzględnia nową wartość).
- **P0-2 — kompletność na końcu sekwencji.** `finish` porównuje rzeczywisty
  koniec serii (`trigger + length`) z ostatnią znaną pociętą planszą, bez
  obcinania do `expected_layout_count`. Trigger 995 przy N = 1000 i długości
  10 daje koniec 1005 i `incomplete`; trigger na pozycji 3 nie jest
  retriggerem serii 995 (brak przeniesienia na początek sekwencji).
- **P1-1 — testy rzeczywistych operacji.** Statyczny test w obie strony
  został; w `integration/test_super_game_series_postgres.py` doszedł
  parametryczny `test_real_write_operation_bumps_once_and_rolls_back` (12
  operacji na jednej planszy zaimportowanej kodem produkcyjnym, rola
  aplikacyjna z RLS): zapis predykcji (nowa rewizja i
  `synchronize_after_prediction_refresh`, ścieżka handlerów inferencji i
  importu), korekta symbolu człowieka
  (`SqlAlchemyGridCorrectionSymbolRepository.assign`), korekta siatki
  (`save_manual_virtual_geometry`, skutki zapisu geometrii na poziomie
  storage, bo ścieżka renderu wymaga prawdziwych pikseli), finalizacja
  backfillu, zmiana roli istniejącego symbolu, nowy symbol i symbol ręczny z
  rolą, zmiana rodzaju gry (dwie zmiany w jednej transakcji = jedno podbicie),
  zmiana `expected_layout_count`, publikacja reguł
  (`SqlAlchemyRulesRepository.save_rules_version`), usunięcie zakresu źródeł
  przez `CleanupService` (usunięcie plansz, komórek i predykcji) oraz reset
  danych gry. Każda operacja: rollback nie zmienia wersji, commit podbija ją
  dokładnie o 1 w tej samej transakcji, a `fresh` przechodzi na `false`.
  Test `test_real_operations_cover_every_write_point_source` pilnuje, że
  operacje pokrywają każde źródło z listy.
- **P1-2 — `superGameState` w wyszukiwaniu.** Przesunięte do TASK-0935
  decyzją leada; zapisane w Scope i kryteriach tego taska oraz w planie
  (etap S-B, TASK-0935). Trasa `/state` i pole w odpowiedziach serii
  zostają.
- **Cleanup a job wyprowadzania (stan końcowy po rundzie 3).** Job
  wyprowadzania blokuje czyszczenie jak każdy inny job; po czyszczeniu
  podbicie licznika kolejkuje nowe wyprowadzenie. Zapytania
  `ACTIVE_GAME_JOB` w resecie gry, usuwaniu zakresu źródeł i usuwaniu
  zastąpionych zdjęć są niezmienione względem stanu sprzed taska. Test
  operacji rzeczywistych dla `board_source_cleanup` i `game_layout_reset`
  najpierw symuluje zakończenie zakolejkowanych jobów przez worker, a po
  commicie sprawdza, że w kolejce jest dokładnie jeden nowy job
  wyprowadzania.

Runda 2 audytu Codex zamknęła cztery powyższe uwagi i zgłosiła dwie nowe
uwagi P0 dotyczące współbieżności; poprawione celowo, bez innych zmian:

- **P0-3 — kolejność odczytów w `begin_generation`.** Wcześniej parametry
  gry (rodzaj, `expected_layout_count`) były czytane przed blokadą wiersza
  stanu i odczytem `input_version`, więc zapis katalogu zatwierdzony między
  tymi odczytami dawał nową wersję ze starym zakresem i publikacja
  przyjmowała nieaktualnego kandydata. Teraz najpierw `FOR UPDATE` wiersza
  stanu, potem odczyt wersji i parametrów (rodzaj, długość sekwencji, role
  symboli) zwykłymi odczytami w tej samej transakcji
  (`_read_input_parameters`). Jedna kolejność blokad: zapis katalogu blokuje
  swój wiersz `games`/`symbols`, potem wiersz stanu; wyprowadzanie i
  publikacja blokują najpierw wiersz stanu i nie czekają na blokady
  `games`/`symbols`; cleanup podbija wiersz stanu po swoich usunięciach
  (komentarz w kodzie). Test PG
  `test_catalog_write_during_begin_generation_rejects_the_candidate`: zapis
  `expected_layout_count` startuje między blokadą a odczytem parametrów,
  czeka na blokadę wiersza stanu, job czyta stary zakres ze starą wersją, a
  publikacja odrzuca kandydata; następny przebieg publikuje nowy zakres.
- **P0-4 — wyjątek `ACTIVE_GAME_JOB`.** W rundzie 2 zawężony do
  zakolejkowanego joba, w rundzie 3 usunięty całkowicie (decyzja leada):
  wyścigu między sprawdzeniem statusu a przejęciem joba przez worker nie da
  się tanio zamknąć, a cleanup jest rzadką operacją operatora, która może
  poczekać na wyprowadzenie (sekundy do minut). Działająca publikacja
  blokuje wiersz stanu przed seriami, a reset usuwa serie przed podbiciem
  wiersza stanu, więc równoczesne wykonanie mogłoby się zakleszczyć.
  Testy wyjątku usunięto; nowy test PG
  `test_a_queued_super_game_derive_job_blocks_and_the_reset_queues_a_new_one`
  (`test_cleanup_repository.py`): zakolejkowany job daje `ACTIVE_GAME_JOB`,
  po jego zakończeniu reset przechodzi, a jego podbicie kolejkuje nowy job
  wyprowadzania.

Runda 3 audytu Codex zamknęła P0-3; poprawki rundy 3:

- **P0-4** — jak wyżej: brak wyjątku, job wyprowadzania blokuje cleanup.
- **P0-5 — spójny odczyt.** `SuperGameSeriesService.list()`, `boards()` i
  `state()` zaczynają transakcję żądania od
  `SqlAlchemySuperGameSeriesRepository.begin_read_snapshot()`: połączenie
  roli aplikacyjnej z izolacją `REPEATABLE READ` i `SET TRANSACTION READ
  ONLY`, bez blokad (ten sam rodzaj migawki co odczyt stawek zarządzania z
  TASK-0922, ale na połączeniu sesji żądania zamiast osobnego silnika).
  Serie, dokumenty plansz i stan pochodzą z jednej migawki, więc `fresh` i
  `generationInputVersion` zawsze opisują generację zwróconych serii.
  Migawka musi być pierwszym użyciem transakcji; inaczej (izolacja inna niż
  `REPEATABLE READ`) repozytorium zgłasza błąd zamiast cicho czytać w READ
  COMMITTED. Projekcja dokumentów plansz działa w tej samej sesji, więc
  ścieżka zapasowa (ponowny odczyt stanu) nie była potrzebna. Test PG
  `test_list_and_boards_never_pair_old_series_with_a_new_fresh_state`
  publikuje nową generację w środku odczytu (`board_documents` dla
  `boards()`, `list_series` dla `list()`) i sprawdza, że odpowiedź jest w
  całości nowa albo oznaczona jako nieaktualna; ten sam test z wyłączoną
  migawką kończy się błędem asercji (sprawdzone jednorazowo). Test
  `test_read_snapshot_must_start_the_transaction` sprawdza odmowę po
  wcześniejszym zapytaniu.

Wyniki po rundzie poprawek (runda 1):

- `.\.venv\Scripts\python.exe -m pytest services/api/tests -k "super_game or schema_readiness or game_data_v2_schema or jobs or catalog" -q`:
  171 passed, 32 skipped (PG bez zmiennej), 128 s.
- PG `integration/test_super_game_series_postgres.py` i
  `integration/test_postgres_baseline.py` z
  `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'`: 30 passed (305 s); pomiar
  `SUPER_GAME_DERIVATION_2000: seconds=1.043 peak_bytes=271955 batches=4
  series=30`. PG `test_cleanup_repository.py`,
  `test_superseded_import_image_removal.py`, `test_catalog_repository.py`:
  12 passed.
- `pytest services/api/tests -k "cleanup or superseded"`: 36 passed,
  17 skipped; `pytest services/worker/tests -k super_game`: 8 passed.
- `npm run openapi:check`: PASS (bez zmian kontraktu w tej rundzie);
  `npm run typecheck` (mypy 846 plików): PASS; `npm run lint`: PASS
  (0 błędów; ostrzeżenia ESLint sprzed tej zmiany); `npm run format:check`:
  PASS; `ruff check`, `ruff format` i `mypy --strict` na zmienionych
  modułach: PASS.

Wyniki po rundzie 2:

- PG (`$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'`, `PYTHONPATH` na
  worktree) `test_super_game_series_postgres.py`, `test_cleanup_repository.py`,
  `test_superseded_import_image_removal.py`: 36 passed (259 s); pomiar
  `SUPER_GAME_DERIVATION_2000: seconds=0.819 peak_bytes=286499 batches=4
  series=30`.
- `.\.venv\Scripts\python.exe -m pytest services/api/tests -k "super_game or cleanup or superseded" -q`:
  85 passed, 45 skipped (PG bez zmiennej).
- `npm run typecheck` (mypy 846 plików): PASS; `npm run lint`: PASS
  (0 błędów); `npm run format:check`: PASS; `ruff check`, `ruff format` i
  `mypy --strict` na zmienionych modułach: PASS.

Wyniki po rundzie 3:

- PG (`$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'`, `PYTHONPATH` na
  worktree) `test_super_game_series_postgres.py`, `test_cleanup_repository.py`,
  `test_superseded_import_image_removal.py`: 37 passed (296 s; jedyne
  ostrzeżenie to oczekiwany `SAWarning` testu odmowy migawki); pomiar
  `SUPER_GAME_DERIVATION_2000: seconds=0.915 peak_bytes=288412 batches=4
  series=30`.
- `.\.venv\Scripts\python.exe -m pytest services/api/tests -k "super_game or cleanup or superseded" -q`:
  85 passed, 46 skipped (PG bez zmiennej).
- `npm run typecheck` (mypy 846 plików): PASS; `npm run lint`: PASS
  (0 błędów); `npm run format:check`: PASS; `ruff check`, `ruff format` i
  `mypy --strict` na zmienionych modułach: PASS.

### Documentation updates

- `ai_docs/architecture/DATA_MODEL.md`: sekcja „Serie supergry” (cztery
  tabele, kontrakt wejścia, licznik wejścia).
- `ai_docs/architecture/API_CONTRACT.md`: sekcja „Serie supergry” (pięć
  tras, filtry, kursor, `superGameState`, kody błędów).
- `ai_docs/architecture/GAME_DATA_V2_OWNERSHIP.md`: sekcja „Manifest v6” i
  cztery wiersze pełnej mapy.

### Recommended next task

TASK-0934 (sekcja „Supergry” w Adminie: lista, karuzela plansz z
`listSuperGameSeriesBoards`, zapis CAS super symbolu). Wdrożenie u
operatora: zatrzymać API, worker i Admin, `npm run db:migrate` (0152,
przejście manifestu v5 na v6), restart, a potem `POST
…/super-game-series/derive` dla Mumii, bo komórki zapisane przed migracją
nie podbiły licznika.
