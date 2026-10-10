# TASK-0950 — Przejęcie sekwencji przez zdjęcie zastępcze i sprzątanie starego zdjęcia

## Status

`done`

## Goal

Zwykły import lepszego zdjęcia (`seq_*`) przejmuje wyłącznie sekwencje odrzucone albo bez żywego właściciela, zamyka odrzucony slot starego zdjęcia i przelicza jego bramkę; dobre plansze starego zdjęcia zostają.

## Context

Plan `ai_docs/delivery/GEOMETRY_CORRECTION_REVERT_EXECUTION_PLAN.md`, sekcja „Odrzucanie przyciętych plansz i zdjęcie zastępcze”, decyzje 5–6, wymaganie W9. Zmienia D-238 (proponowana D-539, wpis w TASK-0951).

## Dependencies / entry conditions

- TASK-0949 ukończony (status `rejected` slotu i odrzucanie planszy).

## Recommended execution

`claude-opus-5-5`, reasoning `high`: zmiana reguły własności sekwencji w API i workerze oraz przeliczanie bramki starego zdjęcia; błąd gubi plansze. Eskalacja: reguła koliduje z ponownym przetwarzaniem tej samej checksumy albo z `has_protected_lateral_owner` → zatrzymaj i zapytaj operatora. Review: Codex `gpt-6-astra`, `high`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/GEOMETRY_CORRECTION_REVERT_EXECUTION_PLAN.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/process/decisions/DECISION_LOG_2026.md` — D-238, D-484, D-485

## Scope

- Reguła własności w `storage/pending_sequence_ownership.py` (`create_owned_pending_review_item`, `_supersede`) i ścieżce workera (`services/worker/src/game_predictor_worker/images/pipeline_store.py` ~440–540, ~668–710):
  - nowa plansza przejmuje sekwencję, gdy brak żywego właściciela albo właściciel jest odrzucony (pozycja `rejected` lub slot `rejected` tej sekwencji);
  - żywa pozycja `pending` innego zdjęcia zostaje; nowa plansza `superseded` + `image_sequence_alternatives` z powodem `superseded_existing_owner_kept` (nowa wartość CHECK, jeśli wymagana — wtedy w migracji `0153`, przed jej wykonaniem przez operatora);
  - kanoniczny właściciel wygrywa jak dotąd; ta sama checksuma zdjęcia — dotychczasowa ścieżka;
  - pojedyncza implementacja reguły jako czysta funkcja domenowa (proponowana `domain/sequence_takeover.py`) używana przez API i workera albo przez wspólne SQL; bez rozbieżnych kopii.
- Sprzątanie po przejęciu w tej samej transakcji: odrzucony slot starego zdjęcia → `superseded` (`superseded_at`); przeliczenie bramki starego zdjęcia (`recompute_source_image_geometry_completeness`, `sequence_live_elsewhere`) — gdy zdjęcie zostaje dopuszczone, cięcie pozostałych plansz istniejącą ścieżką `materialize_admitted_source_image`.
- Raport importu w Adminie: liczby „Zastąpione sekwencje” i „Pominięte — sekwencja ma właściciela” z listą numerów (rozszerzenie istniejącego raportu; OpenAPI i klient, jeśli zmienia się kontrakt).

## Out of scope

- Przejęcie kanonicznego właściciela (TASK-0305), osobny upload „Podmień zdjęcie”, zmiana nazewnictwa plików `seq_*`.

## Acceptance criteria

- [ ] Test PG: zdjęcie A z odrzuconym slotem sekwencji S i ośmioma dobrymi planszami; import zdjęcia B (zakres obejmuje S i sekwencje A) → B przejmuje tylko S; pozostałe sekwencje A zostają przy A; plansze B dla nich `superseded` z alternatywą.
- [ ] Odrzucony slot A → `superseded`; bramka A przeliczona; A dopuszczone i pocięte, gdy pozostałe pozycje są poprawne.
- [ ] Ponowne przetworzenie tej samej checksumy działa jak przed zmianą (istniejące testy bez zmian asercji).
- [ ] Raport importu pokazuje zastąpione i pominięte sekwencje.

## Technical notes

- Blokady sekwencji jak w `create_owned_pending_review_item`; kolejność: sekwencje → zdjęcie nowe → zdjęcie stare.
- Alternatywa i zdarzenia `superseded` zachowują audyt; nic nie jest usuwane.

## Expected files

- Zmieniane: `storage/pending_sequence_ownership.py`, `services/worker/src/game_predictor_worker/images/pipeline_store.py`, `storage/image_geometry_completeness_state_repository.py`, raport importu (API + Admin).
- Nowe (proponowane): `domain/sequence_takeover.py`, `services/api/tests/integration/test_replacement_photo_takeover_postgres.py`, testy workera.

## Test cases

- Scenariusz z kryteriów; sekwencja bez właściciela (wcześniej odrzucona przed importem w Adminie) → przejęcie.
- Właściciel `pending` tej samej checksumy → dotychczasowa ścieżka.
- Kanoniczny właściciel → nowa plansza `superseded`, alternatywa `superseded_first_save_wins` jak dotąd.

## Verification

```powershell
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
..\..\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_replacement_photo_takeover_postgres.py services/api/tests/integration/test_image_geometry_completeness_gate.py services/api/tests/integration/test_virtual_deferred_resolution_postgres.py -q
npm run python:test -- -Suite Worker
npm run python:lint
npm run python:typecheck
```

## Risks / open questions

- D-539 zmienia D-238; operator, który chce zastąpić żywą pozycję `pending`, musi ją najpierw odrzucić.

## Outcome

Wykonawca: claude-opus-5-5 (high), 2026-10-09. Bez commita (commit, audyt,
`CURRENT_STATE.md` i wpis D-539 należą do leada / TASK-0951).

### Changed

- **Reguła D-539 jako czysta funkcja domenowa** `domain/sequence_takeover.py`
  (`decide_sequence_claim`, `SequenceClaimOutcome`): kanoniczny właściciel
  wygrywa (`canonical_sequence_already_resolved`); brak żywego właściciela
  (także tylko odrzucony) → przejęcie; żywa pozycja `pending` innego zdjęcia
  (inna checksuma źródła) → nowa pozycja `superseded` z powodem i alternatywą
  `superseded_existing_owner_kept`; ta sama checksuma → porządek D-238
  (`pending_sequence_owned_by_newer_import` / `..._replaced_by_newer_import`).
  Jedyne miejsce stosowania: `storage/pending_sequence_ownership.create_owned_pending_review_item`,
  wołane przez API (`virtual_grid_geometry_repository`, rozwiązanie slotu) i
  workera (`pipeline_store._upsert_review_item`) — bez kopii reguły. Ścieżka
  first-save-wins workera (`superseded_first_save_wins`) i ścieżka odroczonych
  slotów tej samej checksumy (`pipeline_store.py` ~668) bez zmian;
  `has_protected_lateral_owner` działa przed regułą i z nią nie koliduje.
- **Sprzątanie po przejęciu (ta sama transakcja)**: fakty czytane pod blokadą
  sekwencji (odrzucone sloty innych zdjęć `FOR UPDATE`, kandydaci bramki);
  odrzucony slot → `superseded` (`superseded_at`, pola odrzucenia zostają) i
  zdarzenie `superseded` w `image_board_geometry_pending_events` (z
  `successor_review_item_id`, numerem odrzucenia i deterministycznym kluczem);
  przeliczenie bramki (`recompute_source_image_geometry_completeness`,
  `materialize=True`) zdjęć z odrzuconą pozycją/slotem tej sekwencji oraz zdjęć
  `geometry_incomplete`, których rewizja źródła obejmuje numer (luka staje się
  `superseded`); zdjęcie dopuszczone jest cięte istniejącą ścieżką. Odrzucona
  pozycja zostaje `rejected` (brak przejścia z `rejected`, więc liczniki nie są
  liczone podwójnie).
- **Migracja `0153` (niewdrożona, decyzja leada)**: kolumna
  `image_board_geometry_pending_events.successor_review_item_id` i akcja
  `superseded` w CHECK kształtu (+ ORM). Kolumna powodu alternatyw nie ma CHECK
  (`String(50)`), więc bez zmian.
- **Przejęcie komórek pociętej, odrzuconej planszy** (znaleziony błąd): import
  zastępczy padał w write-through (`SYMBOL_CELL_REVIEW_GEOMETRY_REVISION_INVALID`),
  bo komórki logiczne są unikalne per `(game, sequence, cell)`, a nowa plansza
  importu ma rewizję 0. `invalidate_symbol_cell_reviews_for_geometry` dostał
  `handoff_from_rejected_board` (pomija tylko kontrolę ciągłości rewizji, reszta
  reguł recropu bez zmian — decyzje zostają jako sugestie dla nowych pikseli);
  `_synchronize` włącza go, gdy wszystkie istniejące komórki sekwencji należą do
  odrzuconej pozycji innej planszy.
- **Cofnięcie rozstrzygnięcia slotu** (`geometry_correction_revert_repository`,
  `superseded_others`): blokada `GEOMETRY_REVERT_SEQUENCE_OWNERSHIP` także, gdy
  korekta zamknęła odrzucony slot (zdarzenie `superseded`) albo inne zdjęcie ma
  odrzuconą pozycję tej sekwencji (bramka tamtego zdjęcia zależy od tej pozycji).
- **Raport importu**: `GeometryCompletenessReport.sequence_ownership` /
  `ImageGeometryCompletenessResponse.sequenceOwnership` (tylko z `importJobId`):
  `replacedCount/replacedSequenceNumbers` (żywa pozycja importu, a inne zdjęcie
  ma odrzuconą pozycję albo odrzucony/zastąpiony slot) i
  `skippedCount/skippedSequenceNumbers` (alternatywy importu
  `superseded_existing_owner_kept` i `superseded_first_save_wins`); listy
  posortowane, maks. 500. OpenAPI, wygenerowany klient, eksport typu
  `ImportSequenceOwnershipResponse` w wrapperze, test żądania klienta. Admin
  (`geometry-completeness-section.tsx`): liczniki „Zastąpione sekwencje” i
  „Pominięte — sekwencja ma właściciela” z listą `#N` (`formatSequenceNumbers`).
- Dokumentacja: `IMAGE_INGESTION.md` (reguła D-539), `ADMIN_APP.md`,
  `API_CONTRACT.md`, `DATA_MODEL.md`, `CODE_MAP*.md` (regeneracja).

### Zmienione istniejące testy (zmiana kontraktu D-238 → D-539)

- `integration/test_image_batch_store.py::test_pending_sequence_owner_is_always_the_newest_import`
  → sparametryzowany `..._is_the_newest_import_of_the_same_photo_only`: wariant
  tej samej checksumy ma dawne asercje; wariant różnych zdjęć oczekuje
  zachowania pierwszej pozycji, `superseded_existing_owner_kept` i dwóch alternatyw.
- `integration/test_virtual_deferred_resolution_postgres.py::test_manual_resolution_continues_the_canonical_crop_revision`:
  przed rozwiązaniem slotu drugiego zdjęcia pierwsza plansza jest odrzucana
  (przejęcie tylko od odrzuconego właściciela); asercje handoffu rewizji bez zmian.
- `integration/test_geometry_correction_revert_refusals_postgres.py`: fixture
  `_ownership_game` odrzuca planszę starszego zdjęcia; test
  `test_a_correction_that_superseded_the_sequence_owner_refuses_the_revert`
  przemianowany na `..._took_over_a_rejected_owner_...` (zamiast liczby zdarzeń
  `superseded` sprawdza `rejected: 1, pending: 1`); w
  `test_cells_re_owned_from_the_previous_owner_refuse_the_revert` usunięto
  izolujące `DELETE` zdarzeń `superseded` (już nie powstają); asercje
  `re_owned == 15` i `SEQUENCE_OWNERSHIP` bez zmian.
- `test_lateral_lock_order.py::test_pending_owner_does_not_lock_immutable_incumbent_job`:
  sztuczna plansza dostała `source_image_id` (asercje bez zmian).

### Verification results

Z katalogu worktree, `PYTHONPATH` = `services/api/src;services/worker/src;services/test_support`,
`..\..\.venv\Scripts\python.exe`, testy PG z `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`:

- Nowy PG `test_replacement_photo_takeover_postgres.py` — 5 passed: scenariusz
  akceptacyjny (A: odrzucony slot 100 + 8 plansz; B 100–108 przejmuje tylko
  100, 8 pozycji B `superseded` z alternatywą, slot A `superseded` + zdarzenie,
  A `geometry_complete` ze 120 komórkami, liczniki 135 = lista = przebudowa,
  raport i HTTP `sequenceOwnership`), odrzucona pocięta plansza (komórki
  przechodzą do B, liczniki 30 bez podwójnego liczenia), sekwencja bez
  właściciela po odrzuceniu przed importem, właściciel kanoniczny bez zmian,
  ścieżka API slotu zachowuje żywego właściciela innego zdjęcia.
- PG: `test_image_geometry_completeness_gate.py`, `test_virtual_deferred_resolution_postgres.py`,
  `test_pending_slot_rejection_postgres.py`, `test_geometry_correction_revert_{pending,refusals,board}_postgres.py`
  i nowy plik — 48 passed, 3 failed (kontrakt D-238) → po zmianie testów 3 passed.
  `test_image_batch_store.py`, `test_superseded_import_image_removal.py`,
  `test_neural_automatic_import_postgres.py`, `test_neural_manual_slot_symbols_postgres.py`,
  `test_cell_render_specs_postgres.py`, `test_reviewer_operational_geometry_postgres.py` — 31 passed.
  `test_super_game_series_postgres.py`, `test_image_geometry_completeness_repository.py`,
  `test_outside_current_owner_postgres.py`, `test_symbol_review_bulk_start_locking_postgres.py`,
  `test_game_partition_lifecycle_postgres.py`, `test_postgres_baseline.py` — 72 passed
  i 1 błąd teardownu `DROP DATABASE` w przebiegu łańcuchowym; plik lifecycle osobno — 6 passed.
- `pytest services/worker/tests` — 2822 passed, 43 skipped (w tym nowy
  `test_replacement_sequence_takeover.py`, 2 testy).
- `pytest services/api/tests` (bez PG, z `-p no:logging`) — 2633 passed, 351 skipped,
  1 error (fixture `caplog` wyłączona tą flagą); `test_operational_image_reviews.py`
  bez flagi — 16 passed. Nowy `test_sequence_takeover.py` — 7 passed.
- `ruff check services/api services/worker services/test_support scripts` — czysto;
  `mypy services/api/src services/worker/src scripts` — Success (866 plików).
- `export_admin_openapi.py --check` i `check:generated` klienta — current; klient:
  `test` 108 pass, `typecheck` czysty; Admin: `test` 734 pass, `typecheck` czysty,
  `lint` 0 błędów (5 istniejących ostrzeżeń w innych plikach); prettier czysto;
  `generate_code_map.py --check` — up to date; `git diff --check` — czysto.

### Ryzyka i uwagi dla leada

- Kandydaci bramki są czytani przy każdej nowej pozycji ze znanym numerem
  (skan `source_images` gry po `geometry_completeness_status`, bez indeksu);
  koszt rzędu milisekund na planszę.
- Alternatywy `superseded_existing_owner_kept` chronią zdjęcia przed
  `superseded_import_image_removal` (`PROTECTED_ROWS:image_sequence_alternatives`) —
  zachowawczo, bez utraty danych.
- Przejęte komórki odrzuconej planszy niosą jej decyzje jako sugestie (reguła
  recropu D-462 R6); historia zostaje w zdarzeniach komórek.
- Podgląd cofnięcia odrzuconego i już zastąpionego slotu zwraca
  `GEOMETRY_REVERT_NOT_LATEST` (slot nie jest `rejected`), nie `REPLACED`.

### Runda poprawek audytu

Audyt Codex (`gpt-6-astra`, `high`) runda 1: `REVISE`, 3 × P0; raport
zachowany bez zmian w `ai_docs/quality/TASK-0950_AUDIT_gpt-6-astra_round1.md`.

- **P0-1 (ochrona lateral, konflikt wskazany w tasku) — decyzja leada**:
  `has_protected_lateral_owner` nadal chroni właściciela. Nowa funkcja
  `lateral_reprocess_protection.protected_owner_is_another_photo` (pod tą samą
  blokadą sekwencji) rozpoznaje, że ochronę dają wyłącznie wiersze innego
  zdjęcia (inna checksuma) i że zachowywany właściciel jest pewny (wiersz
  kanoniczny albo wszystkie chronione wiersze są `pending`). Wtedy worker
  (`pipeline_store.py`) nie robi `continue`, tylko przechodzi przez wspólną
  regułę: kanon → first-save-wins z alternatywą, żywa pozycja → nowa plansza
  `superseded` + alternatywa `superseded_existing_owner_kept` (licznik
  „Pominięte”). Ochrona tego samego zdjęcia (ta sama checksuma) — dotychczasowe
  pominięcie bez zmian. Test PG `test_a_protected_owner_of_another_photo_skips_a_neural_import_with_an_alternative`
  (import z `neural-auto-crop-v1`, właściciel z ręcznie narysowaną siatką).
- **P0-2 (przejęcie od odrzuconej planszy częściowej)**: przy
  `handoff_from_rejected_board` domena nie wymaga kompletnej starej historii
  cropów (pozycje `outside` bez `crop_sample_id`), nadal sprawdza unikalność
  indeksów i komplet nowych komórek (`map_current_symbol_cell_reviews`);
  decyzje logiczne pozycji bez obrazu przechodzą jako sugestie istniejącą
  gałęzią repozytorium. Test wykazał też drugi błąd: przejęte komórki `outside`
  zostawały z `source_available = false` — `_synchronize` ustawia teraz
  dostępność `true` dla każdej bieżącej komórki planszy niekwalifikowanej.
  Test PG `test_a_rejected_partial_board_with_outside_cells_is_replaced_by_a_full_photo`
  (import przechodzi, 15 dostępnych komórek B, decyzja człowieka komórki 0
  zachowana jako sugestia `pending`, liczniki 30 = lista = przebudowa, zakres
  outside 0) oraz test domenowy w `test_sequence_takeover.py`.
- **P0-3 (proweniencja zatwierdzenia między planszami)**: przepięcie
  zatwierdzenia rozpoznawane wyłącznie po tożsamości cropa
  (`_approval_matches_current_crop`: ten sam `crop_sample_id` i
  `crop_checksum_sha256`), nie po numerze rewizji. Inne piksele → komórka
  `pending` z sugestią, stare `approved_*` (w tym rewizja źródła, specyfikacja
  i checksuma renderu) zostają bez zmian. Test PG
  `test_an_old_approval_of_other_pixels_keeps_its_provenance_across_boards`
  (rewizja 0 → 0).

Weryfikacja rundy (`PYTHONPATH` worktree, PG z `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`):

- `test_replacement_photo_takeover_postgres.py` — 8 passed.
- `test_image_geometry_completeness_gate.py`, `test_virtual_deferred_resolution_postgres.py`,
  `test_pending_slot_rejection_postgres.py`, `test_geometry_correction_revert_{pending,refusals,board}_postgres.py` — 46 passed.
- `test_image_batch_store.py`, `test_superseded_import_image_removal.py`,
  `test_neural_automatic_import_postgres.py`, `test_neural_manual_slot_symbols_postgres.py`,
  `test_cell_render_specs_postgres.py`, `test_reviewer_operational_geometry_postgres.py`,
  `test_outside_current_owner_postgres.py`, `test_symbol_review_bulk_start_locking_postgres.py` — 36 passed.
- Worker: `test_replacement_sequence_takeover.py`, `test_virtual_only_import_writers.py`,
  `test_image_pipeline_execution.py` — 28 passed (pierwszy przebieg: 1 failed —
  mój własny test wykrył nazwę powodu w komentarzu workera; komentarz poprawiony).
- API: `test_sequence_takeover.py`, `test_image_symbol_reviews_domain.py`,
  `test_lateral_lock_order.py`, `test_lateral_reprocess_protection.py`,
  `test_symbol_review_extended_filters.py`, `test_image_symbol_review_query_storage.py` — 128 passed;
  `test_symbol_cell_source_visibility.py`, `test_qualified_cell_reconciliation.py`,
  `test_partial_board_reconciliation{,_cli}.py`, `test_symbol_count_rebuild_interleaving.py` — 53 passed.
- `ruff check` — czysto; `ruff format --check` zmienionych plików — czysto;
  `mypy services/api/src services/worker/src scripts` — Success (866 plików);
  `generate_code_map.py` — zregenerowane; `git diff --check` — czysto.
  Pełnych zestawów API i workera w tej rundzie nie powtarzano.

### Druga runda poprawek (decyzja leada)

Audyt Codex (`gpt-6-astra`) runda 2: P0-1…P0-3 zamknięte, nowe P0-4
(zakleszczenie równoległych przejęć: każda transakcja blokuje własne zdjęcie, a
potem przez `FOR UPDATE` przeliczenia bramki zdjęcie kandydata, druga w
odwrotnej kolejności); raport zachowany bez zmian w
`ai_docs/quality/TASK-0950_AUDIT_gpt-6-astra_round2.md`.

- **Wybrany wariant: wspólna blokada gry** (wariant zapasowy leada). Wariant
  preferowany (wyliczenie i zablokowanie zbioru zdjęć przed własnym źródłem)
  odrzucony jako nieproporcjonalny: zbiór kandydatów zależy od numerów
  sekwencji wszystkich pozycji pliku i od stanu bramki innych zdjęć, który może
  się zmienić między wyliczeniem a blokadą (nowe zdjęcie `geometry_incomplete`
  znów złamałoby kolejność), a ścieżka workera blokuje dziś źródło przed
  sekwencjami.
- `image_review_repository.acquire_sequence_ownership_lock(session, game_id=…)`:
  transakcyjna blokada doradcza `(game_id, 'sequence-ownership')`
  (re-entrant w transakcji). Bierze ją każdy zapis, który może przejąć
  sekwencję albo przeliczyć bramkę innego zdjęcia, po blokadzie klucza
  idempotencji i dzierżawie joba, a przed `_ensure_projection_state`,
  blokadami sekwencji i wierszami źródeł: zapis siatki w API
  (`save_virtual_source_geometry_revision` — rozwiązanie slotu i korekta
  planszy), worker `project_recognition` (upsert pozycji) i `resolve_board`,
  rozstrzygnięcia pozycji (`_acquire_review_sequence_locks`, w tym odrzucenie
  planszy i first-save-wins), odrzucenie slotu, cofnięcie korekty (przypadek B)
  i cofnięcie odrzucenia. Mutacje komórek symboli (nie blokują drugiego
  zdjęcia) jej nie biorą.
- Wpływ na przepustowość: serializuje per gra wyłącznie krótkie transakcje
  zapisu projekcji (jeden plik importu, jedno rozwiązanie slotu albo
  rozstrzygnięcie, rzędu dziesiątek ms); ciężkie etapy importu (detekcja,
  cropy, inferencja) działają poza tą transakcją, więc równoległe workery
  czekają tylko na krok projekcji. Inne gry nie są blokowane. Pomiaru
  obciążeniowego nie wykonywano (zakaz benchmarków bez zgody).
- Test PG `test_concurrent_takeovers_of_crossed_images_never_deadlock`: A
  (9 slotów, zaimportowane 102–108) i B (sloty 100–101), oba
  `geometry_incomplete`; dwa wątki z barierą jednocześnie rozwiązują A/100 i
  B/101, przeliczenie bramki spowolnione o 1 s. Wynik: oba kończą się bez
  błędu, A jest właścicielem 100, B — 101, oba zdjęcia `geometry_complete`
  (120 i 15 komórek). Sprawdzone, że bez blokady (tymczasowo wyłączonej w
  zapisie siatki) test pada na `DeadlockDetected`.
- Zmieniona asercja istniejącego testu (nowy protokół blokad):
  `test_lateral_lock_order.py::test_editor_entrypoint_reserves_sequence_before_source_row_query`
  oczekuje `["ownership", "sequence", "source"]` zamiast `["sequence", "source"]`.

Weryfikacja (`PYTHONPATH` worktree, PG z `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`):

- `test_replacement_photo_takeover_postgres.py` (9), `test_image_geometry_completeness_gate.py`,
  `test_virtual_deferred_resolution_postgres.py`, `test_pending_slot_rejection_postgres.py`,
  `test_geometry_correction_revert_pending_postgres.py` — 39 passed.
- `test_geometry_correction_revert_{refusals,board}_postgres.py`, `test_image_batch_store.py`,
  `test_superseded_import_image_removal.py`, `test_neural_automatic_import_postgres.py` — 41 passed.
- `test_neural_manual_slot_symbols_postgres.py`, `test_cell_render_specs_postgres.py`,
  `test_reviewer_operational_geometry_postgres.py`, `test_outside_current_owner_postgres.py`,
  `test_symbol_review_bulk_start_locking_postgres.py` — 11 passed.
- Worker (`test_replacement_sequence_takeover.py`, `test_virtual_only_import_writers.py`,
  `test_image_pipeline_execution.py`) i `test_lateral_lock_order.py` — 33 passed;
  dodatkowo `test_lateral_reprocess_protection.py`, `test_board_cell_geometry_pending.py`,
  `test_geometry_correction_reverts.py`, `test_operational_image_reviews.py` — razem 119 passed.
- `ruff check` — czysto; `ruff format --check` zmienionych plików — czysto
  (przypadkowe formatowanie 26 niezwiązanych plików cofnięte przez
  `git checkout --` tych plików); `mypy` — Success (866 plików);
  `generate_code_map.py` — zregenerowane. Pełne zestawy API i workera uruchamia lead.

### Trzecia runda poprawek (decyzja leada)

Audyt Codex (`gpt-6-astra`) runda 3: P0-5 (decyzja komórki trzyma blokadę
sekwencji, a ponowne otwarcie / rozstrzygnięcie planszy pobiera blokadę gry
później; równoległy import trzyma blokadę gry i czeka na sekwencję; tak samo
zapis geometrii istniejącej planszy); raport zachowany bez zmian w
`ai_docs/quality/TASK-0950_AUDIT_gpt-6-astra_round3.md`.

- **Protokół czytelnik/pisarz** w nowym module `storage/sequence_ownership_lock.py`
  (`image_review_repository` re-eksportuje `acquire_sequence_ownership_lock`):
  tryb `EXCLUSIVE` (`pg_advisory_xact_lock`) i `SHARED`
  (`pg_advisory_xact_lock_shared`) na kluczu `(game_id, 'sequence-ownership')`.
  Rejestr w `session.info` per transakcja główna: zagnieżdżone żądanie tego
  samego lub słabszego trybu nic nie robi; żądanie `EXCLUSIVE` przy trzymanym
  `SHARED` nigdy nie podnosi blokady i kończy się `409
  SEQUENCE_OWNERSHIP_LOCK_UPGRADE`. Kolejność dla wszystkich uczestników:
  blokada klucza idempotencji / dzierżawa joba → własność → stan projekcji →
  sekwencje → źródła → wiersze.
- **EXCLUSIVE na starcie**: projekcja workera i `resolve_board`, zapis siatki
  zdjęcia (`save_virtual_source_geometry_revision`, w tym rozwiązanie slotu),
  zapis siatki istniejącej planszy (`save_virtual_geometry_revision` — wskazany
  w audycie; może ponownie otworzyć pozycję), konwersja legacy
  (`legacy_conversion_plan` z `lock`), odrzucenie slotu, oba cofnięcia,
  bezpośrednie rozstrzygnięcie pozycji (`_acquire_review_sequence_locks` jako
  punkt wejścia przez `ensure_sequence_ownership_lock`) oraz zbiorcze operacje
  na komórkach (zadania w tle, `_apply_board_targets`).
- **SHARED na starcie decyzji komórki**: `enter_cell_decision` przed blokadą
  sekwencji w `apply_board_mutations`, `save_board` (zapis planszy
  nieczytelnej), korekcie z udostępnionej wyszukiwarki (`_cells`), adapterze
  zarządzania (`correct`) i migracji weryfikacji komórek (`apply_board`).
  Wywołania zagnieżdżone (`reopen_for_symbol_cell_issue`, `resolve_item` →
  `save_resolution`, `synchronize_board_from_cells`, `assign` w zapisie siatki)
  zachowują blokadę wejścia.
- **Dowód / wyjątek**: ponowne otwarcie dotyka tylko własnej pozycji, planszy i
  zdjęcia. Rozstrzygnięcie może zastąpić cudzą pozycję `pending` tej samej
  sekwencji (`_supersede_pending_sequence_occurrences`, first-save-wins) i
  przeliczyć bramkę innego zdjęcia — dlatego nie da się udowodnić, że zawsze
  wystarcza `SHARED`. Rozwiązanie: `cell_decision_lock_mode` (odczyt przed
  blokadami) wybiera `EXCLUSIVE` od początku, gdy istnieje inna pozycja
  `pending` z planszą o numerze sekwencji tej planszy (po D-539 tylko po
  korekcie numeru), inaczej `SHARED`. Strażnik `require_exclusive_sequence_ownership`
  tuż przed zastąpieniem cudzej pozycji przerywa wyścig (nowa pozycja między
  odczytem a blokadą) kontrolowanym 409 zamiast odwróconej kolejności.
- Testy: jednostkowe `test_sequence_ownership_lock.py` (3: re-entrancja,
  brak podniesienia, rejestr per transakcja i gra); PG
  `test_a_cell_decision_and_a_concurrent_import_of_its_sequence_never_deadlock`
  (oznaczenie problemu siatki na zaakceptowanej planszy 101 trzyma sekwencję
  1,5 s w `reopen_for_symbol_cell_issue`, w tym czasie import neural tej
  sekwencji; oba kończą się poprawnie, pozycja ponownie otwarta, import
  `superseded` z alternatywą; sprawdzone, że bez `enter_cell_decision` test
  pada na `DeadlockDetected`) i `test_shared_ownership_holders_never_block_each_other`
  (dwa `SHARED` naraz, `EXCLUSIVE` czeka — `lock_timeout`).

Weryfikacja (`PYTHONPATH` worktree, PG z `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`):

- `test_replacement_photo_takeover_postgres.py` (11), `test_image_geometry_completeness_gate.py`,
  `test_virtual_deferred_resolution_postgres.py` — 27 passed;
  `test_pending_slot_rejection_postgres.py`, `test_geometry_correction_revert_pending_postgres.py` — 14 passed;
  `test_geometry_correction_revert_{refusals,board}_postgres.py`, `test_image_batch_store.py`,
  `test_superseded_import_image_removal.py`, `test_neural_automatic_import_postgres.py` — 41 passed;
  `test_neural_manual_slot_symbols_postgres.py`, `test_cell_render_specs_postgres.py`,
  `test_reviewer_operational_geometry_postgres.py` — 6 passed.
- Zestawy PG z mutacjami komórek: `test_board_search_share_corrections.py`,
  `test_board_search_super_game_postgres.py`, `test_cell_level_verification_migration.py`,
  `test_management_stakes_postgres.py`, `test_outside_current_owner_postgres.py`,
  `test_partial_board_reconciliation_postgres.py`, `test_symbol_review_bulk_start_locking_postgres.py`,
  `test_symbol_visibility_groups_postgres.py`, `test_verified_cell_search_projection.py` —
  27 passed, 1 failed: `test_symbol_visibility_groups_postgres.py::test_all_eight_symbols_unknown_and_outside_partition_real_rows`
  (`relation "image_review_items" does not exist` w tabeli sondy testu przy
  predykacie widoczności `NOT IN (… status = 'rejected')` z TASK-0949; ta runda
  nie zmienia tego predykatu — do osobnej poprawki, zgłoszone leadowi).
- Jednostkowe: worker (`test_replacement_sequence_takeover.py`, `test_virtual_only_import_writers.py`,
  `test_image_pipeline_execution.py`), `test_lateral_lock_order.py`, `test_sequence_ownership_lock.py`,
  `test_sequence_takeover.py` — 45 passed; wcześniej w rundzie `test_symbol_review_extended_filters.py`,
  `test_image_symbol_review_query_storage.py`, `test_board_cell_geometry_pending.py`,
  `test_geometry_correction_reverts.py` + lock order — 141 passed.
- `ruff check` — czysto; `ruff format --check` zmienionych plików — czysto;
  `mypy` — Success (867 plików); `generate_code_map.py` — zregenerowane.

### Naprawa regresji TASK-0949 (predykat widoczności)

- **Diagnoza**: `test_symbol_visibility_groups_postgres.py::test_all_eight_symbols_unknown_and_outside_partition_real_rows`
  podstawia kolumny komórek tabelą tymczasową sondy na zwykłym połączeniu (bez
  ścieżki gry), a predykat `_logical_cell_visible_clause` z TASK-0949 czyta
  `image_review_items` (`NOT IN` pozycji `rejected`) — relacja nie istniała w
  sondzie. Predykat jest poprawny (w produkcji tabela jest kierowana przez
  routing gry), więc poprawiony został fixture: druga tabela sondy
  `visibility_groups_item_probe (id, status)` z pozycjami `pending` wszystkich
  komórek i podstawienie kolumn aliasu `ImageReviewItemModel`. Fixture dostał
  też komórkę odrzuconej pozycji, która nie należy do żadnego zakresu (pokrycie
  reguły W7); asercje bez zmian (pętla kluczy liczników obejmuje jak dotąd
  wiersze `rows`, komórka odrzucona jest poza nią, bo jej liczniki zwalnia
  przejście w `rejected`).
- **Znaleziony przy przeglądzie drugi błąd (TASK-0950)**:
  `test_per_game_isolation_new_game.py::test_plan_of_the_completeness_report_path_names_only_the_new_games_partitions`
  padał, bo nowe zapytania raportu `sequenceOwnership` łączyły podzapytania
  przez `game_id` skorelowane (`= ri.game_id`), co nie przycina partycji;
  wszystkie relacje filtrowane są teraz stałą `:game_id`. To samo zastosowano
  w zapytaniu kandydatów bramki w `pending_sequence_ownership.py`.
- Przebiegi (PG, wszystkie pliki `services/api/tests/integration` z
  `_logical_cell_visible_clause`, `symbol_visibility`, `visibility_groups`,
  `count_projection` lub `symbol_review` — 39 plików; część już zielona w
  rundach 2–3 bez zmian w predykacie): `test_symbol_visibility_groups_postgres.py` — 2 passed;
  `test_board_search_approximate_win_repository.py`, `test_convert_legacy_boards_postgres.py`,
  `test_drop_cell_render_spec_postgres.py`, `test_grid_correction_cell_symbols_postgres.py`,
  `test_image_geometry_completeness_repository.py`, `test_symbol_review_query_cancellation.py`,
  `test_symbol_rgb_v2_writer_postgres.py`, `test_slim_prediction_revisions_postgres.py` — 33 passed, 2 skipped;
  `test_game_data_v2_postgres.py`, `test_game_data_v2_qualification_migration.py`,
  `test_game_storage_routing_postgres.py`, `test_per_game_isolation_new_game.py`,
  `test_protected_control_promotion_postgres.py`, `test_rls_policy_function_parallel_postgres.py`,
  `test_symbol_source_visibility_migration.py`, `test_vision_lab_geometry_export_postgres.py` —
  43 passed, 1 failed (izolacja, naprawione → plik 12 passed);
  `test_game_partition_lifecycle_postgres.py`, `test_super_game_series_postgres.py`,
  `test_v09_schema_migration.py`, `test_v09_storage_cleanup_migration.py`,
  `test_per_game_isolation_new_game.py` — 50 passed; po zmianach SQL ponownie
  `test_replacement_photo_takeover_postgres.py` + `test_image_geometry_completeness_repository.py` — 37 passed.
  Pozostałe pliki z listy (rewerty, odrzucenia, bramka, import, nadpisanie,
  mutacje komórek, `test_verified_cell_search_projection.py`,
  `test_board_search_share_corrections.py`, `test_cell_level_verification_migration.py`,
  `test_outside_current_owner_postgres.py`, `test_partial_board_reconciliation_postgres.py`,
  `test_symbol_review_bulk_start_locking_postgres.py`, `test_cell_render_specs_postgres.py`)
  zielone w trzeciej rundzie.
- `ruff check` — czysto; `ruff format --check` — czysto; `mypy` — Success (867 plików).

### Czwarta runda poprawek (decyzja leada)

Audyt Codex (`gpt-6-astra`) runda 4: P0-6 (po blokadzie własności
`get_item(for_update)` i zastępowanie pozycji blokowały wiersz joba, który
worker tego samego importu trzyma od dzierżawy) i P0-7 (`_revert_item` i
`_revert_board_revision` bez blokady własności; pętla przeliczeń blokowała
kolejne źródło po stanie liczników); raport zachowany bez zmian w
`ai_docs/quality/TASK-0950_AUDIT_gpt-6-astra_round4.md`.

**Globalna kolejność blokad** (opis w `storage/sequence_ownership_lock.py` i
`DATA_MODEL.md`): blokada klucza idempotencji albo wiersz dzierżawy joba
workera (`FOR NO KEY UPDATE`) → własność (`SHARED`/`EXCLUSIVE`) → wiersz gry
(strażnik projekcji) → blokady sekwencji → wiersze `source_images` (kilka naraz
rosnąco, jednym zapytaniem) → plansze, pozycje, sloty, wiersze kanoniczne i
kolejki → `image_symbol_review_states` → komórki. Każda transakcja, która
blokuje źródło, a później stan liczników albo drugie źródło, jest uczestnikiem
protokołu.

Poprawki klasy:

- P0-6: `get_item(for_update)` i `_supersede_pending_sequence_occurrences`
  blokują `FOR UPDATE OF` tabel faktycznie zmienianych (bez `jobs`). Test
  wykazał trzecie źródło tego samego cyklu: kontrola klucza obcego wstawień
  odwołujących się do joba (`FOR KEY SHARE`) czekała na dzierżawę `FOR UPDATE`
  workera — dzierżawa w `_require_candidate_lease` to teraz `FOR NO KEY UPDATE`
  (zmienia tylko kolumny niekluczowe).
- P0-7: `SqlAlchemyGeometryCorrectionRevertRepository.revert` bierze
  `EXCLUSIVE` zaraz po blokadzie klucza, przed rozdzieleniem na rodzaje — więc
  cofnięcie slotu, rewizji planszy (`_revert_board_revision`) i obu odrzuceń
  (`_revert_slot`, `_revert_item`) zaczyna od własności.
- Pętla przeliczeń: `lock_source_images` (rosnąco, jedno zapytanie) i
  `recompute_source_images` — wszystkie źródła blokowane przed jakimkolwiek
  przeliczeniem, cięcia dopiero po wszystkich; używane przez sprzątanie po
  przejęciu i `recompute_source_images_of_{boards,review_items}`. W
  `create_owned_pending_review_item` kandydaci (w tym zdjęcia odrzuconych
  slotów) są blokowani przed slotami i pozycjami. Projekcja workera odkłada
  cięcia zdjęć dopuszczonych przez przejęcia na koniec transakcji
  (`start/finish_deferred_gate_materializations`), po ostatniej blokadzie źródła.
- Projekcja workera blokuje wszystkie sekwencje pliku przed własnym źródłem
  (`lock_projection_sequences`; dawniej tylko rollout lateral) — sekwencje przed
  źródłami.
- Wyjątek geometrii (`set_exception`: źródło → cięcie, czyli stan → komórki)
  bierze `EXCLUSIVE`: `SHARED` mają wyłącznie decyzje komórek, które blokują
  komórki przed stanem, więc dwie kolejności stan/komórki nigdy nie działają
  równolegle.

Punkty wejścia TASK-0945–0950 i kolejność pobierania blokad:

| Punkt wejścia | Kolejność |
|---|---|
| Projekcja workera (`project_recognition`) | dzierżawa joba (NO KEY UPDATE) → własność X → wszystkie sekwencje pliku → własne źródło → (na planszę) źródła kandydatów rosnąco → sloty, pozycje, plansze → (koniec) źródła innych zdjęć rosnąco → stan (odłożone cięcia, write-through) → komórki |
| Worker `resolve_board` | dzierżawa joba → własność X → sekwencje pozycji → wiersze → stan |
| Rozwiązanie slotu / zapis siatki zdjęcia (`save_virtual_source_geometry_revision`) | własność X → wiersz gry → sekwencje → źródło → slot, plansza, pozycja → przejęcie: źródła kandydatów rosnąco → sloty, pozycje → przeliczenia → cięcia (stan) → komórki |
| Zapis siatki istniejącej planszy (`save_virtual_geometry_revision`), konwersja legacy | własność X → wiersz gry → sekwencje → wiersze (`OF` pozycji, planszy, źródła) → stan → komórki |
| Odrzucenie slotu | klucz → własność X → sekwencja → źródło → slot → zdarzenie → bramka własnego zdjęcia |
| Cofnięcia (korekta slotu, rewizja planszy, odrzucenie slotu i planszy) | klucz → własność X → sekwencja → źródło → slot/pozycja/plansza → stan → komórki |
| Bezpośrednie rozstrzygnięcie (`save_resolution`) | własność X → sekwencje → pozycja, plansza, źródło, kolejka (`OF`, bez joba) → wiersz kanoniczny → pozycje i źródła innych zdjęć (`OF`) → stan |
| Decyzje komórek (`apply_board_mutations`, `save_board`, korekta z wyszukiwarki, adapter zarządzania, migracja weryfikacji) | własność S (X, gdy możliwe zastąpienie cudzej pozycji) → sekwencja → pozycja → komórki → stan (TASK-0885); zagnieżdżone reopen/resolve (pozycja, plansza, własne źródło, wiersz kanoniczny) zachowują blokadę; zastąpienie cudzej pozycji pod S → `409 SEQUENCE_OWNERSHIP_LOCK_UPGRADE` |
| Operacje zbiorcze (`_apply_board_targets`) | własność X → wiersz operacji i cele → na planszę (zagnieżdżone `apply_board_mutations`): sekwencja → pozycja → komórki → stan |
| Przeliczenia i cięcia wielu zdjęć | wszystkie źródła rosnąco jednym zapytaniem → przeliczenia → cięcia (stan); w workerze cięcia na końcu transakcji |
| Wyjątek geometrii (`set_exception`) | własność X → źródło → przeliczenie → stan → komórki (cięcie) |

Pozostałe odstępstwa (świadome, wszystkie pod `EXCLUSIVE`, więc żaden inny
uczestnik nie działa równolegle; stan liczników nigdy przed źródłem):

- źródła kandydatów przejęcia są blokowane po wierszach własnej planszy i
  pozycji (rozwiązanie slotu) albo po wierszach wcześniejszych plansz pliku
  (projekcja workera, plansza po planszy) — kandydaci zależą od numeru
  sekwencji planszy;
- w bezpośrednim rozstrzygnięciu i na końcu projekcji workera źródła innych
  zdjęć (zastąpione pozycje `pending`) są blokowane po wierszach własnej
  pozycji;
- write-through blokuje stan przed komórkami, decyzja komórki komórki przed
  stanem (patrz wyżej).

Testy:

- `services/api/tests/integration/_lock_order_probe.py`: lekki rejestr blokad
  per transakcja (zdarzenie `before_cursor_execute`; blokady doradcze po
  kluczu, wiersze po tabelach `FOR UPDATE OF` / `FROM`) z regułami: wiersz joba
  po własności, własność po sekwencji/źródle/wierszach/stanie, nowa sekwencja
  po źródle, źródło po stanie, źródło i stan bez własności.
- Nowy plik PG `test_sequence_ownership_lock_order_postgres.py`:
  `test_a_decision_and_the_projection_of_the_next_photo_of_its_job_never_deadlock`
  (P0-6: drugie zdjęcie przeniesione do tego samego joba; rozstrzygnięcie
  trzyma własność 1,5 s, worker bierze dzierżawę joba; przed zmianą dzierżawy
  test kończył się `DeadlockDetected` na `FOR KEY SHARE` joba),
  `test_a_multi_image_takeover_and_a_board_rejection_revert_never_deadlock`
  (P0-7: C i A z odrzuconym slotem 100, A z odrzuconą planszą 102; import B
  przejmuje 100 i tnie C, równolegle cofnięcie odrzucenia 102) i
  `test_the_main_entry_points_follow_the_global_lock_order` (rejestr na
  imporcie, odrzuceniu slotu, przejęciu, decyzji komórki, odrzuceniu planszy i
  cofnięciu odrzucenia — zero naruszeń).
- Zmiana istniejącego testu: `test_concurrent_takeovers_of_crossed_images_never_deadlock`
  spowalnia teraz `recompute_source_images` (nowy pomocnik zamiast
  pojedynczego przeliczenia); asercje bez zmian.

Weryfikacja (`PYTHONPATH` worktree i katalog główny, PG z `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`):

- Partia 1: `test_replacement_photo_takeover_postgres.py`, `test_sequence_ownership_lock_order_postgres.py`,
  `test_image_geometry_completeness_gate.py`, `test_virtual_deferred_resolution_postgres.py` —
  29 passed, 1 failed (test skrzyżowanych przejęć łatał nieistniejącą już nazwę; poprawiony).
- Partia 2: `test_pending_slot_rejection_postgres.py`, `test_geometry_correction_revert_{pending,refusals,board}_postgres.py` — 30 passed.
- Partia 3: `test_image_batch_store.py`, `test_superseded_import_image_removal.py`,
  `test_neural_automatic_import_postgres.py`, `test_neural_manual_slot_symbols_postgres.py`,
  `test_cell_render_specs_postgres.py`, `test_reviewer_operational_geometry_postgres.py` — 31 passed.
- Partia 4 (zestawy weryfikacji symboli i izolacji): `test_board_search_share_corrections.py`,
  `test_board_search_super_game_postgres.py`, `test_cell_level_verification_migration.py`,
  `test_management_stakes_postgres.py`, `test_outside_current_owner_postgres.py`,
  `test_partial_board_reconciliation_postgres.py`, `test_symbol_review_bulk_start_locking_postgres.py`,
  `test_symbol_visibility_groups_postgres.py`, `test_verified_cell_search_projection.py`,
  `test_per_game_isolation_new_game.py`, `test_image_geometry_completeness_repository.py` — 66 passed.
- Po ostatnich zmianach (wyjątek geometrii `EXCLUSIVE`, poprawiony test):
  test skrzyżowanych przejęć, `test_image_geometry_completeness_gate.py`,
  `test_sequence_ownership_lock_order_postgres.py`, `test_super_game_series_postgres.py` — 41 passed;
  `test_super_game_input_version.py` — 15 passed (błąd z pełnego przebiegu leada
  wystąpił w trakcie edycji; na stanie końcowym zielony).
- Jednostkowe: worker (`test_replacement_sequence_takeover.py`, `test_image_pipeline_execution.py`,
  `test_virtual_only_import_writers.py`), `test_lateral_lock_order.py`, `test_sequence_ownership_lock.py`,
  `test_image_geometry_completeness_api.py` — 73 passed.
- `ruff check` — czysto; `ruff format --check` — czysto; `mypy` — Success (867 plików);
  `generate_code_map.py` — zregenerowane; `git diff --check` — czysto.

### Zamknięcie (lead)

- Audyt Codex `gpt-6-astra`/`high`: rundy 1–4 REVISE, wszystkie P0-1…P0-7 poprawione (raporty `ai_docs/quality/TASK-0950_AUDIT_gpt-6-astra*.md`). Operator 2026-10-10: limit Codex wyczerpany, bez kolejnych rund Codex.
- Audyt zastępczy Claude `claude-sonnet-5-5`/`high` (inny model niż wykonawca, tylko odczyt): PASS (`ai_docs/quality/TASK-0950_AUDIT_claude-sonnet-5-5.md`). Przyjęte ryzyka P2: (1) ponowna akceptacja odrzuconej planszy po przejęciu kończy się nieczytelnym `SYMBOL_CELL_REVIEW_GEOMETRY_REVISION_INVALID` (rollback, bez utraty danych); (2) `pipeline_store.py:353` bez blokady własności i `_recompute_liveness_changes` blokujące źródło po stanie liczników — odstępstwo od opisanej kolejności; (3) inne `FOR UPDATE` na wierszach joba mogą tworzyć trójstronne zakleszczenie; (4) rejestr blokad ignoruje savepointy; (5) skan kandydatów bramki bez indeksu. Wszystkie do ponownego audytu Codex.
- Weryfikacja leada: pełne `pytest services/api/tests` → 2638 passed, 360 skipped; `pytest services/worker/tests` → 2822 passed.
- Pozostałość: testowa baza `game_predictor_task0760_e7d125df587d_test` z przebiegu audytora (DROP przekroczył czas) — do usunięcia przez operatora.
- Commit: v1.7.296.
