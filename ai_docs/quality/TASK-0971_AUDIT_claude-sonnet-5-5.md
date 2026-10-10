# Audyt TASK-0971 — Przejęcie sekwencji przez zdjęcie zastępcze i sprzątanie starego zdjęcia

Werdykt: PASS
Audytor: Claude, claude-sonnet-5-5, audyt zastępczy (Codex niedostępny), szybki przegląd skupiony na P0/P1
Wykonawca: claude-opus-5-5, high
Zakres: HEAD a7f9fe27d9a726dc220117d274e4fa52aa8eb273 oraz zmiany niezacommitowane (czwarta runda poprawek wykonawcy), data 2026-10-10
Runda: 1 (audytor zastępczy; weryfikacja zamknięcia P0-1 … P0-7 z rund Codex 1–4)

Przegląd statyczny (z ograniczonym uruchomieniem testów), bez zmian w plikach poza raportem; audyt zastępczy Claude (Codex niedostępny).

## Streszczenie

Zbadano regułę D-543 (`decide_sequence_claim` i jej jedyne miejsce użycia `create_owned_pending_review_item`), sprzątanie po przejęciu, protokół blokad własności (`sequence_ownership_lock.py`) wraz ze wszystkimi punktami wejścia z tabeli Outcome oraz poprawki czwartej rundy. Wszystkie znaleziska P0-1 … P0-7 z raportów Codex są zamknięte w kodzie, a dwa ostatnie (P0-6, P0-7) mają działające regresje; nie znalazłem otwartego P0 ani P1. Pozostałe ryzyko to ścieżki spoza protokołu (uczestnicy bez blokady własności i inne blokady wiersza joba), które mogą dać rzadkie zakleszczenie albo nieczytelny błąd, ale nie utratę danych; opisano je jako P2.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- **[P2-1] `services/api/src/game_predictor_api/storage/image_review_repository.py:1062` (rozstrzygnięcie), `:1185` (przywrócenie komórek) — bezpośrednie ponowne zatwierdzenie odrzuconej planszy po przejęciu jej sekwencji kończy się nieczytelnym błędem.** Sprawdziłem eksperymentalnie (test pomocniczy poza repozytorium, scenariusz z `test_a_rejected_cut_board_is_replaced_without_double_counting_its_cells` plus `ImageReviewAction.ACCEPTED` na odrzuconej pozycji starego zdjęcia po tym, jak import B przejął sekwencję): operacja kończy się `SYMBOL_CELL_REVIEW_GEOMETRY_REVISION_INVALID` ("A new geometry must advance one shared revision…"). Transakcja jest wycofana, dane są spójne, ale operator dostaje błąd techniczny zamiast kontrolowanego konfliktu. Ścieżka cofnięcia odrzucenia ma analogiczną ochronę (`REPLACED` przez `_live_elsewhere`), a ścieżka bezpośredniego rozstrzygnięcia jej nie ma. Poprawka: przed `restore_cells_of_reopened_board` odmówić z kodem w rodzaju `IMAGE_REVIEW_SEQUENCE_OWNED_ELSEWHERE`, gdy inna pozycja `pending` albo kanoniczna trzyma tę sekwencję; dodać test PG. Przed D-543 import B w tym scenariuszu w ogóle padał, więc nie jest to regresja.

- **[P2-2] `services/worker/src/game_predictor_worker/images/pipeline_store.py:353` oraz `services/api/src/game_predictor_api/storage/image_review_repository.py:1532` — dokumentowana niezmienna reguła protokołu ("każda transakcja blokująca źródło, a później stan liczników, jest uczestnikiem") nie jest w pełni prawdziwa.** Etap `project_source_geometry` (dzierżawa → źródło → zapis geometrii → `recompute_source_image_geometry_completeness` z domyślnym `materialize=True`, czyli stan liczników po źródle) nie bierze blokady własności; to samo dotyczy `board_cell_geometry_pending_repository.py:179` i `:333`. Z drugiej strony `_recompute_liveness_changes` przelicza kolejne zdjęcia pojedynczo z natychmiastowym cięciem, więc po cięciu pierwszego zdjęcia (stan) blokuje źródło drugiego, wbrew regule "źródła przed stanem" zapisanej w `sequence_ownership_lock.py:35-39`. Cykl wymaga równoczesnego etapu geometrii na zdjęciu, które właśnie jest przeliczane, więc jest rzadki. Poprawka: `acquire_sequence_ownership_lock` na początku `project_source_geometry` (po dzierżawie) oraz użycie `recompute_source_images` w `_recompute_liveness_changes`; do czasu poprawki doprecyzować komentarz niezmiennika.

- **[P2-3] `services/api/src/game_predictor_api/storage/image_job_repository.py:311`, `layout_import_report_repository.py:302`, `:394`, `image_review_repository.py:757` — inne blokady `FOR UPDATE` na wierszu joba import.** Poprawka P0-6 (dzierżawa `FOR NO KEY UPDATE`, brak joba w `FOR UPDATE OF`) usuwa cykl pary worker/rozstrzygnięcie. Trójstronny cykl (worker z dzierżawą czeka na własność trzymaną przez zapis, który wstawia wiersz z kluczem obcym do joba i czeka na `FOR UPDATE` joba trzymany przez operację na jobie, która czeka na dzierżawę) pozostaje teoretycznie możliwy, np. przy anulowaniu importu w trakcie projekcji. Przed zmianą ryzyko było takie samo, więc nie blokuje. Poprawka: ewentualnie `FOR NO KEY UPDATE` w `_image_job(for_update=True)`, jeśli operacja nie zmienia kolumn kluczowych; w przeciwnym razie akceptacja ryzyka.

- **[P2-4] `services/api/src/game_predictor_api/storage/sequence_ownership_lock.py:77-89` i `:119-127` — rejestr blokad per transakcja nie uwzględnia punktów zapisu.** Blokada doradcza transakcyjna zdobyta po `SAVEPOINT` jest zwalniana przy wycofaniu do tego punktu, a rejestr nadal uznaje ją za trzymaną. Obecnie żaden punkt wejścia z blokadą własności nie działa w `begin_nested()`, więc nie ma skutku. Poprawka: zapisać w komentarzu ograniczenie albo rejestrować zagnieżdżoną transakcję i czyścić wpisy przy jej wycofaniu.

- **[P2-5] `services/api/src/game_predictor_api/storage/pending_sequence_ownership.py:49-70` — kandydaci bramki czytani skanem `source_images` przy każdej nowej pozycji ze znanym numerem.** Trzeci człon `UNION` filtruje `geometry_completeness_status = 'geometry_incomplete'` bez dedykowanego indeksu. Przy dużym imporcie koszt rośnie liniowo z liczbą zdjęć gry razy liczbą plansz; wykonawca oszacował go na milisekundy. Poprawka (opcjonalna): indeks częściowy po `(game_id)` z `WHERE geometry_completeness_status = 'geometry_incomplete'`, po pomiarze na dużej grze.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| B przejmuje tylko odrzucony S, pozostałe sekwencje A zostają przy A, plansze B dla nich `superseded` z alternatywą | spełnione | `test_replacement_photo_takeover_postgres.py:168`; reguła w `domain/sequence_takeover.py:98-137`, zastosowanie w `pending_sequence_ownership.py:189-263`; test przeszedł w moim przebiegu (14 passed razem z plikiem blokad) |
| Odrzucony slot A → `superseded`, bramka A przeliczona, A dopuszczone i pocięte | spełnione | `pending_sequence_ownership.py:343-395`, `image_geometry_completeness_state_repository.py:285-321`; ten sam test PG |
| Ta sama checksuma działa jak przed zmianą | spełnione | `domain/sequence_takeover.py:119-137` zachowuje porządek D-238 (`<=` jak w kodzie z HEAD); wariant `same-photo` w `test_image_batch_store.py`; ścieżka kanoniczna workera niezmieniona (`pipeline_store.py:490-574`) |
| Raport importu pokazuje zastąpione i pominięte sekwencje | spełnione | `image_geometry_completeness_repository.py:418-456`, `:704-726`; asercje `_ownership(...)` w teście PG; UI `geometry-completeness-section.tsx` |
| Przejęcia zachowują poprawność przy współbieżności | spełnione | `test_sequence_ownership_lock_order_postgres.py` (3 testy), `test_concurrent_takeovers_of_crossed_images_never_deadlock`, `test_a_cell_decision_and_a_concurrent_import_of_its_sequence_never_deadlock`: wszystkie przeszły; luki poza protokołem opisano w P2-2 i P2-3 |

## Listy zamknięte i otwarte

Zamknięte (weryfikacja w kodzie, nie tylko w Outcome):

- **P0-1** (ochrona lateral) — `pipeline_store.py:464-476` i `lateral_reprocess_protection.py:105-153`: wiersze tej samej checksumy dają dotychczasowe pominięcie, ochrona innego zdjęcia przechodzi przez wspólną regułę; test `test_a_protected_owner_of_another_photo_skips_a_neural_import_with_an_alternative`.
- **P0-2** (przejęcie od odrzuconej planszy częściowej) — `image_symbol_review_repository.py` około `:2745` (`handoff_from_rejected_board`), około `:3133` (`source_available = True`); test planszy częściowej z komórkami `outside`.
- **P0-3** (proweniencja zatwierdzenia) — `_approval_matches_current_crop` (definicja około `:3560`, użycie około `:2789`), rozpoznanie po tożsamości cropa, nie po numerze rewizji.
- **P0-4** (zakleszczenie skrzyżowanych przejęć) — blokada własności `EXCLUSIVE` przed źródłami (`virtual_grid_geometry_repository.py:222`, `:411`, `pipeline_store.py:415`); kandydaci blokowani rosnąco jednym zapytaniem (`image_geometry_completeness_state_repository.py:221-233`, `pending_sequence_ownership.py:142-143`).
- **P0-5** (decyzja komórki kontra import) — protokół czytelnik/pisarz `sequence_ownership_lock.py:99-142`, `enter_cell_decision` (`image_symbol_review_repository.py:1136`); żądanie `EXCLUSIVE` przy trzymanym `SHARED` nigdy nie podnosi blokady, kończy się 409 (`:113-118`). Przeszukałem wszystkich wywołujących: żadna ścieżka z `SHARED` nie wywołuje zapisu geometrii (`EXCLUSIVE`), a rozstrzygnięcie zastępujące cudzą pozycję ma strażnika `require_exclusive_sequence_ownership` (`image_review_repository.py:1425`) i wybór trybu z wyprzedzeniem (`cell_decision_lock_mode`, predykat zgodny z `_supersede_pending_sequence_occurrences`: numer sekwencji planszy).
- **P0-6** (blokada własności przed blokadą joba) — `get_item(for_update)` używa `FOR UPDATE OF` bez `JobModel` (`image_review_repository.py:709-720`), tak samo `_supersede_pending_sequence_occurrences` (`:1419`), a dzierżawa to `FOR NO KEY UPDATE` (`pipeline_store.py:1303-1307`; skompilowałem zapytanie SQLAlchemy: `with_for_update(key_share=True)` daje `FOR NO KEY UPDATE`, `read=True` dałoby `FOR KEY SHARE`). Test `test_a_decision_and_the_projection_of_the_next_photo_of_its_job_never_deadlock` używa tego samego joba i przeszedł. `virtual_grid_geometry_repository.py:2215-2222` (`_current_row`) również pomija job.
- **P0-7** (cofnięcie odrzucenia kontra przeliczanie wielu zdjęć) — `revert()` bierze `EXCLUSIVE` zaraz po blokadzie klucza idempotencji, przed rozdzieleniem na rodzaje (`geometry_correction_revert_repository.py:771`; `_revert_item` i `_revert_board_revision` są dostępne wyłącznie z `revert()`, co sprawdziłem po wywołaniach); przeliczenia wielu zdjęć blokują wszystkie źródła przed pierwszym przeliczeniem (`pending_sequence_ownership.py:388-395`, `image_geometry_completeness_state_repository.py:285-321`); worker odkłada cięcia na koniec transakcji (`pipeline_store.py:418`, `:743`) i rezerwuje wszystkie sekwencje pliku przed własnym źródłem (`:419`). Test `test_a_multi_image_takeover_and_a_board_rejection_revert_never_deadlock` przeszedł.

Otwarte: P2-1, P2-2, P2-3, P2-4, P2-5 (żadne nie blokuje commita).

## Analiza kolejności blokad (cel 1)

Dla każdego punktu wejścia z tabeli Outcome sprawdziłem w kodzie kolejność: klucz idempotencji albo dzierżawa joba → własność → wiersz gry → sekwencje → źródła → wiersze → stan liczników → komórki. Potwierdzone: projekcja workera (`pipeline_store.py:395-429`), `resolve_board` (`:851-858`, własność przed sekwencjami), zapis siatki zdjęcia i istniejącej planszy, konwersja legacy (`virtual_grid_geometry_repository.py:717`), odrzucenie slotu (`board_cell_geometry_pending_repository.py:404`), oba cofnięcia, `set_exception` (`image_geometry_completeness_state_repository.py:837`), operacje zbiorcze (`image_symbol_review_bulk_operation_repository.py:524`). Zagnieżdżone wywołania `reopen_for_symbol_cell_issue`, `save_resolution`, `recompute` i `materialize` zachowują tryb wejścia (`ensure_sequence_ownership_lock`, `held_sequence_ownership_lock`). Możliwe podniesienie `SHARED` → `EXCLUSIVE` jest zablokowane i kończy się kontrolowanym 409, nie zakleszczeniem. Odstępstwa wewnątrz `EXCLUSIVE` (źródła kandydatów po wierszach własnej planszy, `FOR UPDATE` bez `OF` w `has_protected_lateral_owner` blokujący źródła innych zdjęć) są bezpieczne wobec uczestników protokołu, bo `EXCLUSIVE` wyklucza ich wzajemnie; jedyna otwarta luka to nie-uczestnicy (P2-2).

## Poprawność reguły D-543 (cel 2) i sprzątania (cel 3)

`decide_sequence_claim` jest czystą funkcją i jedynym miejscem reguły; API (rozwiązanie slotu) i worker (`_upsert_review_item`) używają tej samej funkcji magazynu. Porównanie ze starym kodem z HEAD: porządek tej samej checksumy (`(created_at, id)`, `<=` → nowa pozycja `superseded`) jest identyczny, ścieżka kanoniczna workera i `superseded_first_save_wins` bez zmian, `has_protected_lateral_owner` działa przed regułą (ochrona tej samej checksumy nadal pomija). Sprzątanie: zdarzenie `superseded` slotu ma deterministyczny klucz idempotencji i zachowuje pola odrzucenia; ponowne wywołanie nie powiela go, bo slot opuszcza stan `rejected`; odrzucona pozycja pozostaje `rejected`, więc liczniki nie są liczone podwójnie (potwierdzone testem 30 = 30 po przebudowie). Bramka starego zdjęcia jest przeliczana z `exclude_source_image_id` dla zdjęcia nowego, a cięcia są odroczone po ostatniej blokadzie źródła (worker) albo wykonywane po wszystkich przeliczeniach (API).

## Proponowane testy

- P2-1: w `services/api/tests/integration/test_replacement_photo_takeover_postgres.py` scenariusz "odrzucona plansza A, import B przejmuje sekwencję, bezpośrednie `ACCEPTED` na A" z oczekiwanym kontrolowanym konfliktem i niezmienionym stanem świata (`_world`). Test pomocniczy, na którym oparłem opis, leży poza repozytorium (katalog scratchpad sesji audytu).
- P2-2: rozszerzyć `_lock_order_probe.py` o ścieżkę `project_source_geometry` przy zdjęciu przeliczanym równolegle przez przejęcie (dwa wątki, bariera); komenda: `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'; ..\..\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_sequence_ownership_lock_order_postgres.py -q`.
- P2-3: scenariusz trójstronny (anulowanie importu podczas projekcji workera i równoległego rozstrzygnięcia) tylko jeśli operator zdecyduje o poprawce `FOR NO KEY UPDATE`.
- Regresja po poprawkach P2: te same komendy co w sekcji Verification taska oraz `services/api/tests/integration/test_sequence_ownership_lock_order_postgres.py`.

## Zakres przeglądu i ograniczenia

Przeczytano w całości: brief wraz z Outcome, wszystkie raporty Codex (rundy 1–4), `sequence_ownership_lock.py`, `domain/sequence_takeover.py`, `pending_sequence_ownership.py`, `_lock_order_probe.py`, różnice względem HEAD dla `image_geometry_completeness_state_repository.py`, `lateral_reprocess_protection.py`, `pipeline_store.py`, migracji 0154 i modeli zdarzeń slotów, `image_review_repository.py`, `image_symbol_review_repository.py`, repozytoriów cofnięć, odrzucenia slotu i zapisu siatki oraz fragmenty raportu importu. Nie czytano szczegółowo UI Admina, klienta OpenAPI ani dokumentacji (poza streszczeniem w Outcome).

Uruchomione testy (tylko bazy `*_test`): `test_sequence_ownership_lock.py`, `test_sequence_takeover.py`, `test_lateral_lock_order.py`, `test_replacement_sequence_takeover.py` — 19 passed; `test_sequence_ownership_lock_order_postgres.py` i `test_replacement_photo_takeover_postgres.py` — 14 passed. Dodatkowy test pomocniczy (P2-1) uruchomiono dwukrotnie z katalogu scratchpad. Szerszej regresji (bramka, rozwiązywanie odroczone, cofnięcia, `test_image_batch_store.py`) nie powtarzano; opieram się tu na deklaracjach wykonawcy. Nie uruchamiano migracji ani usług.

Uwaga operacyjna: pierwszy przebieg testu pomocniczego zakończył się błędem teardownu fixtury (`DROP DATABASE` przekroczył `statement_timeout` 10 s), więc została baza testowa `game_predictor_task0760_e7d125df587d_test`. Próba jej usunięcia została odrzucona przez klasyfikator uprawnień, więc pozostaje do ręcznego usunięcia przez operatora (nazwa pasuje do wzorca `*_test`; baza deweloperska `game_predictor` nie była dotykana). Podobny błąd teardownu zgłosił wykonawca w Outcome, co sugeruje przeciążenie hosta podczas równoległych testów, a nie wadę kodu.
