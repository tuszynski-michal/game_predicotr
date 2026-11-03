Werdykt: PASS

# Audyt TASK-1128 — Strażnicy własności i historii wymiany źródeł (B2a)

Werdykt: PASS
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6-astra, high
Zakres: 8b361ca4606d5a6c0e56fa3c497c99d64550254d (v1.7.524) oraz zmiany niezacommitowane TASK-1128, data 2026-11-03
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików i nie uruchamiał komend, testów ani usług.

## Streszczenie

Sprawdziłem granice o najwyższym ryzyku:
- funkcje SQL 0175 i fence w recording wrapper/photo,
- wspólne predykaty i binding,
- pierwszeństwo rezerwacji w ownership,
- guardy w API i workerze (receipt → guard → CAS),
- filtry wyszukiwarki w trybie incremental i rebuild,
- cleanup, recovery, GC oraz resume treningu.

Nie znalazłem otwartych błędów P0 ani P1. Główne kryteria mają odzwierciedlenie w kodzie, a niejasne przypadki kończą się odmową (fail-closed). Główne ryzyka są uśpione. Ponowna projekcja tego samego numeru w zarezerwowanym slocie może zostawić dwa robocze review. Predykat traktuje nowe źródło jako bieżące po usunięciu jego slotów. To drugie jest istotne dla przyszłego restore w B2b/C2.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `services/api/src/game_predictor_api/storage/pending_sequence_ownership.py:133-206`, `services/api/src/game_predictor_api/storage/source_replacement_binding.py:177-178`
  - **Problem:** gdy numer ma rezerwację, `decide_sequence_claim` zwraca `CLAIM_RESERVED` bez oceny incumbenta. Zapytanie o incumbentów odfiltrowuje review robocze przez `current_review_clause`. Dlatego drugie wywołanie `create_owned_pending_review_item` dla tego samego źródła, joba i numeru nie zamyka (superseded) poprzedniego roboczego review. Takie wywołanie robi np. ścieżka korekty geometrii `virtual_grid_geometry_repository.py:2165`.
  - **Skutek:** powstają dwa żywe `pending` dla jednego numeru. `bind_complete_source` trwale zgłasza wtedy `SOURCE_REPLACEMENT_RESERVED` („Niejednoznaczne plansze”), więc finalizacja zdjęcia jest zablokowana, ale nie dochodzi do wycieku. Nie sprawdziłem statycznie, czy wcześniejszy kod geometrii sam zamyka poprzednie review.
  - **Propozycja:** w gałęzi `CLAIM_RESERVED` zamykać wcześniejsze robocze review tego samego entry/źródła dla danego numeru. Dodać test PG: korekta roboczej geometrii przed kompletnością, a potem bind. Zakres ograniczony, można to zrobić w B2b lub C2.
- [P2-2] `services/api/alembic/versions/0175_source_replacement_guards.py:28-31`
  - **Problem:** `source_replacement_current_v1` uznaje źródło za bieżące, gdy nie ma żadnego slotu z `new_source_id = s`.
  - **Skutek:** po zwolnieniu slotów (restored/porzucona wymiana) robocze review nowego źródła, które nigdy nie zostały związane, staną się widoczne w kolejce, licznikach i wyszukiwarce. Przejdą też `require_sequence_binding`, czyli mogą trafić do canonical. B2a nie usuwa slotów, więc ryzyko jest dziś uśpione.
  - **Propozycja:** w B2b/C2 operacja restore musi w tej samej transakcji zamykać lub wycofywać robocze review przed zwolnieniem slotów. Alternatywnie predykat może konsultować `source_replacement_sources` lub admission entry dla roli „nowe źródło”. Potrzebny test „restore → provisional nadal niewidoczne”.
- [P2-3] `services/api/alembic/versions/0175_source_replacement_guards.py:100,106-114`
  - **Problem:** wstawienie guardu i filtra opiera się na `str.replace(..., 1)` bez sprawdzenia, że podstawienie nastąpiło. Migracja importuje stałe `WRAPPER_SQL` i `PHOTO_SQL` z modułów runtime.
  - **Skutek:** dziś wzorce istnieją (`source_recording_sql_v5.py:11`, `source_recording_sql_v4.py:68,91`). Przyszła zmiana tych modułów po cichu utworzyłaby jednak funkcje bez fence na świeżej bazie, a historyczna migracja zmieniałaby wynik.
  - **Propozycja:** przed `op.execute` sprawdzić, że każdy wzorzec występuje dokładnie raz (`count == 1`), inaczej `RuntimeError`. Docelowo zamrozić literał SQL w migracji.
- [P2-4] `services/api/src/game_predictor_api/storage/storage_gc_repository.py:99-113`
  - **Problem:** guard otwiera i trzyma jednocześnie jedną sesję (połączenie) na każdą grę przez cały `yield` (deadline ok. 60 s).
  - **Skutek:** przy liczbie gier większej niż pula połączeń checkout blokuje się do `pool_timeout`, a GC kończy się odmową. Jest to fail-closed, więc problem dotyczy dostępności, nie bezpieczeństwa. Do tego dochodzi presja na pulę dla zwykłych odczytów.
  - **Propozycja:** udokumentować limit i zmierzyć go przy realnej liczbie gier albo ograniczyć zbiór gier do tych, których dotyczą ścieżki. Akceptowalne jako odnotowane ryzyko.
- [P2-5] `services/api/src/game_predictor_api/application/cleanup.py:232-233`
  - **Problem:** bez wstrzykniętego guardu `finalize` używa `nullcontext(False)`, czyli dopuszcza usunięcie (fail-open).
  - **Skutek:** produkcja ma wstrzykiwać guard (`main.py`, którego nie czytałem w tej rundzie), ale błąd konstrukcji po cichu ominąłby retencję.
  - **Propozycja:** jawna flaga „legacy filesystem” dla konsumentów standalone, a domyślnie odmowa (`CLEANUP_ARTIFACT_RETENTION_UNVERIFIED`). Alternatywnie akceptacja ryzyka z testem, który sprawdza wstrzyknięcie w `main.py`.

## Pokrycie kryteriów akceptacji

| Kryterium | Status | Dowód |
|---|---|---|
| Retired przed canonical, też po restored i przy późnym numerze; historia bez zmian | spełnione | `source_replacement_guards.py:42-62,87-99`; worker `pipeline_store.py:462,944,972`; API `image_review_repository.py:861-874,1186-1194`; `pending_sequence_ownership.py:110`. Receipt jest sprawdzany przed guardem (`pipeline_store.py:926-938`, `image_review_repository.py:861-873`) |
| Reservation tylko z dokładnym bindingiem serwera; import i override nie przejmują luki | spełnione | `sequence_takeover.py:82-97,157-163` (rezerwacja przed canonical); dowód serwerowy `source_replacement_binding.py:36-103` (pin = `document.sequence_numbers` = sloty, `importJobId`, SHA, revision); override `image_review_repository.py:361-364`; bez publicznego force |
| Provisional INSERT/flush bez łamania FK i bez widoczności; kompletne zdjęcie wiązane atomowo | spełnione (z P2-1) | `pending_sequence_ownership.py:132,250-276` (uuid przed bindingiem, slot dostaje ID dopiero w finalizerze); `0175:23-36` (reserved wyklucza); `source_replacement_binding.py:153-209` (komplet, `FOR UPDATE`, idempotentne `bound_review_id IS NULL`); finalizer przed projekcją `pipeline_store.py:785-802` |
| Current reads, counts, search incremental/rebuild, bulk i recovery mają zgodne guardy | spełnione | search `board_search_projection_repository.py:439,538,574,601,832`; ranking rebuild 3/2/1 (`:788-796`) zgodny z `domain/board_search.py:414-437`; liczniki z fallbackiem `image_symbol_review_repository.py:217,737-738`; reinference `pending_symbol_reinference.py:310`; projekcja zbioru wykluczeń startuje od retired/slots (`0175:37-64`); niezwiązana gra → `GAME_STORAGE_SCOPE_REQUIRED` (fail-closed) |
| Nowe użycie treningowe blokuje retired (photo-only SQL, freeze); frozen GET zostaje | spełnione / historyczny GET niezweryfikowany statycznie | `0175:66-115` (receipt → istniejący dispatch, inaczej RETIRED/RESERVED; filtr photo); `grid_correction_split.py:55`; `grid_training_cohort_currentness.py:48-52`; resume przez `run_preview` (`grid_training_runs.py:193-196`); `grid_correction_learning.py:409-411`; trening symboli `symbol_cell_training_source_repository.py:105,161,219,387` |
| Cleanup/reset/release/GC/cropy/staging odmawiają przed skutkami, też dla aliasów i cross-game | spełnione / cross-game crop niezweryfikowany statycznie | `cleanup_repository.py:142,264,287-288,355-363,708-794`; `application/cleanup.py:232-248,592-598`; GC `storage_gc_repository.py:82-113` + `source_replacement_guards.py:157-190` (namespace modeli/datasetów chroniony); staging `browser_staging_retention_repository.py:314-319`; crop `source_crop_eligibility.py:136` |
| Regresje zwykłego reject canonical i legacy fallback zielone | niezweryfikowane statycznie (deklaracja wykonawcy) | fallback accepted/corrected zachowany w rebuild (`:790`); wykonawca deklaruje m.in. przebiegi 319 PASS i PG 8 PASS |
| Testy, scoped lint/typecheck, docs/mapa, audyt i commit rozliczone | częściowo | wyniki według wykonawcy; commit v1.7.525 oczekuje. Uwaga: `ai_docs/tasks/1128-source-replacement-ownership.md:109` nadal mówi „Docs check … w toku” — zaktualizować przed commitem |

P2-2 z audytu B1 jest zamknięte:
- Kodowany `SOURCE_REPLACEMENT_REFERENCED` w preview i execute działa przed detach i operacjami na plikach.
- Retencja obejmuje wszystkie aliasy i nowe źródło przez znormalizowane `source_replacement_sources`, niezależnie od fazy.
- Kohorty i modele są sprawdzane w faktycznym zakresie usuwania (`cleanup_repository.py:766-794`).
- Konflikt zakresu tego samego SHA blokuje preview (`source_replacement.py:136-145`).

## Listy zamknięte i otwarte

Zamknięte: nie dotyczy (runda 1). Po stronie B1 zamknięte jest P2-2, dowód powyżej.

Otwarte: P2-1, P2-2, P2-3, P2-4, P2-5.

## Proponowane testy

- `services/api/tests/integration/test_source_replacement_guards_postgres.py`: korekta roboczej geometrii tego samego numeru przed kompletnością, potem `bind_complete_source` (P2-1).
- Ten sam plik: usunięcie lub zwolnienie slotów, potem robocze review nadal niewidoczne i bez prawa do canonical (P2-2; docelowo w B2b/C2).
- Unit migracji: każdy wzorzec podstawienia w 0175 występuje dokładnie raz (P2-3).
- `services/api/tests/test_source_replacement_cleanup_recovery.py`: produkcyjna konstrukcja z `main.py` zawsze ma guard retencji (P2-5).

## Zakres przeglądu i ograniczenia

Przeczytałem (24 odczyty plus Grep):
- task 1128 i szablon raportu,
- migracje 0175 (całość) i 0174 (DDL),
- `source_replacement_guards.py` i `source_replacement_binding.py` (całość),
- `pending_sequence_ownership.py:60-307`, `sequence_takeover.py:60-99` (+ Grep),
- `pipeline_store.py:440-499,760-989`,
- `image_review_repository.py:340-369,833-892,1173-1202`,
- projekcję wyszukiwarki `:588-659,785-834` i domenę `select_board_search_document`,
- `cleanup_repository.py:90-149,250-374,700-809` oraz `_count`,
- `storage_gc_repository.py:70-124`, `grid_training_runs.py:188-207`,
- `application/cleanup.py:200-269,560-599`, `source_recording_sql_v4.py:55-99`,
- `image_symbol_review_repository.py:200-229`, `virtual_grid_geometry_repository.py:2120-2179`.

Nie przeczytałem: `source_replacement_selection.py`, UI i klienta admin (pozycja 21), `main.py`, `page_geometry_overrides.py`, repozytoriów revert/approval/proposal, `source_image_crop_repository.py`, rejestru cropów cross-game ani testów PG poza nazwami funkcji. Kolejność receipt → guard w geometrii i stronie przyjmuję na podstawie nazw testów i deklaracji wykonawcy.

Wyniki testów, ruff, mypy, OpenAPI i docs pochodzą od wykonawcy — nie uruchamiałem ich. Brak hasha commita przed audytem nie jest defektem. Retirement i import operatora pozostają w B2b/C2 i nie były wymagane.
