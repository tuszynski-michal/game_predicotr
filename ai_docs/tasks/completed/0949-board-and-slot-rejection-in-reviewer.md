# TASK-0949 — Odrzucanie przyciętej planszy i slotu odroczonego w Reviewerze

## Status

`done`

## Goal

Operator odrzuca w Reviewerze przyciętą planszę albo slot odroczony z powodem; odrzucony element nie jest cięty na symbole, znika z kolejki korekty, a zdjęcie czeka na zamiennik (bramka D-484 bez zmian).

## Context

Plan `ai_docs/delivery/GEOMETRY_CORRECTION_REVERT_EXECUTION_PLAN.md`, sekcja „Odrzucanie przyciętych plansz i zdjęcie zastępcze”, decyzje 1–4, wymagania W7–W8.

## Dependencies / entry conditions

- TASK-0945 (migracja `0153` ze statusem `rejected` slotu), TASK-0947 (lista „Ostatnie korekty” w API), TASK-0948 (sekcja w Reviewerze).

## Recommended execution

`claude-sonnet-5-5`, reasoning `high`: pion API + UI według istniejących wzorców rozstrzygnięcia, z wpływem na bramkę i kolejkę. Eskalacja: potrzeba zmiany reguły bramki → zatrzymaj (W8 zakazuje). Review: Codex `gpt-6-astra`, `medium`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/GEOMETRY_CORRECTION_REVERT_EXECUTION_PLAN.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/process/decisions/DECISION_LOG_2026.md` — D-484, D-485

## Scope

- Slot odroczony: serwis i trasa (proponowana) `POST /api/v1/admin/games/{gameId}/image-imports/{importJobId}/board-cell-geometry-pending/{pendingId}/rejection` (`rejectPendingBoardCellGeometry`), body `{idempotencyKey, reason, note?, expectedGeometryRevision}`; tylko z `pending`; blokady jak przy rozstrzygnięciu slotu; przeliczenie bramki zdjęcia; usunięcie z widoku `correction` i liczników (`storage/image_grid_review_repository.py` `_pending_statement`, `grid_review_counts`).
- Plansza istniejąca: przycisk w Reviewerze wywołujący istniejące `POST /admin/image-review-items/{id}/resolution` z `action = rejected` i powodem (`api/image_reviews.py:613`); odmowa 409 `BOARD_REJECT_CANONICAL` dla kanonicznego właściciela.
- Cofnięcie odrzucenia: wpisy w `listGeometryCorrections` (rodzaj `rejection`) i akcja „Cofnij” przez `revertGeometryCorrection` (slot → `pending`; pozycja → nowe zdarzenie rozstrzygnięcia przywracające `pending`), dopóki sekwencji nie przejął zamiennik (kod `GEOMETRY_REVERT_REPLACED`).
- UI: w „Korekta cięcia siatki” przycisk „Odrzuć planszę” z wyborem powodu („Plansza przycięta”, „Rozmyta”, „Inny” z opisem) i potwierdzeniem; ten sam przycisk na ekranie operacyjnym pozycji.
- OpenAPI, klient, wrapper, allowlisty (`security/local_admin.py`, `reviewer-proxy-policy.ts`), testy żądań.

## Out of scope

- Przejęcie sekwencji przez nowe zdjęcie (TASK-0950), zmiana bramki kompletności, odrzucanie w Adminie.

## Acceptance criteria

- [ ] Test PG: odrzucony slot ma status `rejected` z powodem, znika z kolejki i liczników, zdjęcie pozostaje `geometry_incomplete`, pozostałe plansze bez komórek (W8).
- [ ] Test PG: odrzucona plansza poza weryfikacją symboli i wyszukiwarką; kanoniczny właściciel → 409.
- [ ] Cofnięcie odrzucenia przywraca slot/pozycję do `pending`; po przejęciu przez zamiennik → 409 `GEOMETRY_REVERT_REPLACED`.
- [ ] Testy UI: wybór powodu, potwierdzenie, jedno żądanie, odświeżenie kolejki i listy.

## Technical notes

- Kolejność blokad jak przy rozstrzygnięciu slotu (sekwencje → zdjęcie → slot).
- Odrzucenie nie tworzy planszy ani komórek; nie zmienia rewizji geometrii źródła.

## Expected files

- Zmieniane: `api/board_cell_geometry_pending.py`, `application/board_cell_geometry_pending.py`, `storage/board_cell_geometry_pending_repository.py`, `storage/image_grid_review_repository.py`, serwis cofania z TASK-0945, Reviewer `board-geometry-correction-workspace.tsx`, `geometry-correction-history.tsx`, ekran operacyjny, klient API.
- Nowe (proponowane): `services/api/tests/integration/test_pending_slot_rejection_postgres.py`, test UI.

## Test cases

- Slot `pending` → odrzucenie → kolejka bez slotu; ponowne odrzucenie z tym samym kluczem → ten sam wynik; inny klucz → 409.
- Slot `resolved` → odrzucenie → 409 (najpierw cofnięcie korekty).
- Plansza `pending_partial` → odrzucenie → `rejected`, komórki poza weryfikacją.

## Verification

```powershell
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
..\..\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_pending_slot_rejection_postgres.py services/api/tests/integration/test_image_geometry_completeness_gate.py -q
npm run openapi:check
npm run test --workspace @game-predictor/reviewer
npm run typecheck --workspace @game-predictor/reviewer
npm run python:lint
npm run python:typecheck
```

## Risks / open questions

- Odrzucona plansza z komórkami już zweryfikowanymi: weryfikacje zostają w historii, ale wypadają z wyszukiwarki — komunikat potwierdzenia musi to mówić.

## Outcome

Wykonawca: claude-sonnet-5-5 (high), 2026-10-09. Bez commita (commit i audyt należą do leada).

### Changed

- **Odrzucenie slotu** (`rejectPendingBoardCellGeometry`, `POST .../board-cell-geometry-pending/{pendingId}/rejection`, body `{idempotencyKey, reason, note?, expectedGeometryRevision}`): domena (`BoardCellGeometryPendingStatus.REJECTED`, `BoardRejectionReason`, pola odrzucenia w `ImageBoardGeometryPending`, licznik `rejected`), `SqlAlchemyBoardCellGeometryPendingRepository.reject` (blokady jak przy rozstrzygnięciu slotu: sekwencja, zdjęcie, slot; blokada doradcza na kluczu żądania), serwis, router, schematy. W tej samej transakcji przeliczana jest bramka zdjęcia (`recompute_source_image_geometry_completeness`) i status zdjęcia (`settle_source_status_after_slot_rejection`). Bramka bez zmian: odrzucona pozycja jest luką, zdjęcie zostaje `geometry_incomplete`. Slot znika z kolejki `correction` i liczników bez zmian w `image_grid_review_repository` (filtr `status = 'pending'`). `manual-resolution` odrzuconego slotu daje `IMAGE_BOARD_CELL_PENDING_NOT_EDITABLE`.
- **Odrzucenie planszy**: istniejące `POST /admin/image-review-items/{id}/resolution` (`action = rejected`). Nowa odmowa `409 BOARD_REJECT_CANONICAL` w `SqlAlchemyOperationalImageReviewRepository.save_resolution` (`_require_not_canonical_owner`, po kontroli idempotencji i rewizji). Powód planszy to jeden tekst `cropped` / `blurred` / `other: <opis>` (`encode/decode_board_rejection_reason`).
- **Cofnięcie odrzucenia** w istniejącej usłudze i trasach cofania (bez nowych endpointów): `GeometryCorrectionKind.REJECTION`, `RejectionTarget`, `RevertBlockingReason.REPLACED` (`GEOMETRY_REVERT_REPLACED`), nowy `storage/geometry_rejection_revert.py` (lista, podgląd, cofnięcie; delegowane z `SqlAlchemyGeometryCorrectionRevertRepository`). Slot wraca do `pending`; pozycja wraca do `pending` przez nowe zdarzenie rozstrzygnięcia `reopened` (klucz idempotencji zapisany przy zdarzeniu). Odmowa `REPLACED`, gdy numer sekwencji ma żywą pozycję (`pending`/`accepted`/`corrected`) na innym zdjęciu; `NOT_LATEST`, gdy odrzucenie nie jest już aktualne albo pozycję slotu zajęto; `STALE` przy niezgodnych tokenach CAS. Pola nullable w kontrakcie: `recognizedBoardId`, `reviewItemId`, `revertedSourceGeometryRevisionId`, `restoredSourceGeometryRevisionId` oraz nowe `rejectionTarget`, `rejectionReason`, `rejectionNote`.
- **Allowlisty**: `security/local_admin.py` (`POST .../rejection` dla Origin Reviewera), `reviewer-proxy-policy.ts` (to samo; `resolution` było już dopuszczone).
- **OpenAPI i klient**: `openapi.json`, `src/generated/*`, wrapper `rejectPendingBoardCellGeometry`, eksporty typów.
- **Reviewer**: `reject-board-control.tsx` (przycisk „Odrzuć planszę”, wybór powodu „Plansza przycięta” / „Rozmyta” / „Inny” z opisem, potwierdzenie „Potwierdź odrzucenie”, jeden klucz na otwarcie, zamrożony szkic po nieznanym wyniku, fokus, Tab, Escape), `board-rejection-state.ts`, `board-rejection-actions.ts`, `mutation-outcome.ts` (klasyfikacja wyniku wydzielona z `geometry-correction-history.tsx`). Przycisk w „Korekta cięcia siatki” (slot: trasa slotu; plansza: trasa rozstrzygnięcia) i na ekranie operacyjnym (`OperationalReviewBoard`); skróty symboli ekranu operacyjnego ignorują teraz też `[aria-modal="true"]`. „Ostatnie korekty” pokazuje odrzucenia (rodzaj, powód, opis) i cofa je z podglądem; CSS w `reviewer.css`.
- **Dokumentacja**: `API_CONTRACT.md`, `ADMIN_APP.md`, `CODE_MAP*.md` (regeneracja).

### Decyzje wykonawcy (do audytu)

- **Brak nowej migracji** (plan: jedna migracja `0153`). Konsekwencje: (1) klucz idempotencji odrzucenia slotu nie jest zapisany przy slocie; idempotencją jest cykl życia slotu (ten sam powód i opis → `created=false`, inny powód → `IMAGE_BOARD_CELL_PENDING_REJECTION_CONFLICT`; „inny klucz z tym samym powodem” zwraca ten sam wynik zamiast 409). Opóźnione ponowienie odrzucenia po jego cofnięciu odrzuciłoby slot ponownie. (2) Cofnięcie odrzucenia slotu nie zostawia wiersza w `image_geometry_correction_reverts` (tabela wymaga planszy, pozycji i rewizji źródła); po cofnięciu pola odrzucenia slotu są czyszczone (wymóg CHECK), więc historia odrzucenia slotu nie jest przechowywana. Dla planszy historia zostaje w `image_review_resolution_events` (`rejected`, `reopened`). Powtórzenie cofnięcia slotu po sukcesie daje `GEOMETRY_REVERT_NOT_LATEST`. Jeśli lead chce trwałego klucza i audytu, wystarczy dodatkowa kolumna i rozszerzenie CHECK-ów w migracji `0153` przed jej wykonaniem przez operatora.
- Komórki już pocięte odrzuconej planszy zostają w `image_symbol_review_cells` (D-485 pkt 3: istniejące komórki nie są usuwane); odrzucenie usuwa dokument wyszukiwarki. Plansza odrzucona na zdjęciu wstrzymanym nie ma komórek. Potwierdzenie mówi o tym wprost.
- Odrzucenie istniejącej planszy jest możliwe też dla `accepted`/`corrected`, ale kanoniczny właściciel zawsze dostaje `BOARD_REJECT_CANONICAL`; lista cofania pokazuje odrzucenia pozycji tylko dopóki zdarzenie odrzucenia jest bieżącą rewizją pozycji.
- Zmieniona asercja istniejącego testu (zmiana kontraktu: lista zawiera teraz wpisy `rejection`): `test_a_resolved_review_item_refuses_the_revert` wybiera wpis korekty po rodzaju; `test_board_cell_geometry_pending.py::test_api_lists_pages_counts_and_scopes_single_item` dostał `rejected: 0` w licznikach.

### Verification results

Z katalogu worktree, `PYTHONPATH` = `services/api/src;services/worker/src;services/test_support`, `..\..\.venv\Scripts\python.exe`, `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`:

- PG `test_pending_slot_rejection_postgres.py` (nowy) — 5 passed: W8 (slot odrzucony znika z kolejki i liczników, zdjęcie `geometry_incomplete`, plansze bez komórek), idempotencja i odmowy, lista/podgląd/cofnięcie slotu (pełne porównanie stanu gry przed odrzuceniem i po cofnięciu), `REPLACED`, odrzucona plansza poza wyszukiwarką, `BOARD_REJECT_CANONICAL`, cofnięcie planszy z powtórzeniem klucza, trasy HTTP.
- PG regresja: `test_image_geometry_completeness_gate.py` + `test_virtual_deferred_resolution_postgres.py` — 16 passed; `test_pending_slot_rejection_postgres.py`, `test_geometry_correction_revert_{pending,refusals,board}_postgres.py`, `test_reviewer_operational_geometry_postgres.py`, `test_image_geometry_completeness_repository.py` — 56 passed i 1 failed (`test_a_resolved_review_item_refuses_the_revert`: lista ma nowy wpis `rejection`); po poprawce testu ten test — 1 passed.
- `pytest services/api/tests/test_board_cell_geometry_pending.py` — 22 passed; `test_geometry_correction_reverts.py test_geometry_correction_revert_api.py test_local_admin_security.py` — 70 passed; `test_openapi_contract.py` — przechodzi.
- `python -m ruff check services/api services/worker services/test_support scripts` — All checks passed; `ruff format --check` zmienionych plików — czyste.
- `python -m mypy services/api/src services/worker/src scripts` — Success: no issues found in 865 source files.
- `python scripts/export_admin_openapi.py --check` i `npm run check:generated --workspace @game-predictor/admin-api-client` — current.
- `npm run test --workspace @game-predictor/admin-api-client` — 107 pass; `typecheck` admin-api-client i admin — czyste.
- `npm run test --workspace @game-predictor/reviewer` — 251 pass, 0 fail; `test:geometry` — 58 pass, 0 fail; `typecheck` — czysty; `lint` — 0 błędów, 1 istniejące ostrzeżenie (`board-search-share-data-source.ts`); `npm run reviewer:build` — sukces; `npx prettier --check apps/reviewer/src apps/reviewer/test apps/reviewer/test-interactions` oraz pliki klienta — czysto.
- `python scripts/generate_code_map.py` wykonane.

### Not completed

- Przejęcie sekwencji przez zdjęcie zastępcze i przejście starego slotu w `superseded` (TASK-0950): `REPLACED` opiera się na istnieniu żywej pozycji innego zdjęcia.
- Brak ręcznej weryfikacji w przeglądarce; `CURRENT_STATE.md` i `DECISION_LOG.md` (D-539) zostawione leadowi. Zadanie pozostaje `in_progress`.

### Runda poprawek audytu

Audyt Codex (`gpt-6-astra`, `medium`) runda 1: `REVISE`, 4 × P0; raport zachowany bez zmian w `ai_docs/quality/TASK-0949_AUDIT_gpt-6-astra_round1.md`. Decyzja leada: wolno rozszerzyć migrację `0153` (nikt jej nie wdrożył; baza operatora jest na `0152`), więc trwała tożsamość odrzucenia slotu trafia do `0153`. Punkt „Brak nowej migracji” z sekcji „Decyzje wykonawcy” jest tym samym nieaktualny.

- **P0-1 (odrzucona plansza została w weryfikacji symboli)** — zarzut potwierdzony (lista pokazywała 30 komórek po odrzuceniu pozycji z pociętymi komórkami). `_logical_cell_visible_clause()` (jedyny predykat widoczności, używany przez listy, nasienie kursora, liczniki z SQL, blokowane wiersze, operacje zbiorcze i zakresy list plansz) wyklucza teraz komórki pozycji w statusie `rejected` (`NOT EXISTS` na aliasie `image_review_items`); wiersze i zdarzenia zostają jako historia. Liczniki wykładnicze (`count_projection`): `SymbolCellReviewWriteThroughCoordinator.release_cells_of_rejected_board` odejmuje komórki w chwili przejścia pozycji w `rejected` (`save_resolution`), `restore_cells_of_reopened_board` dolicza je przy cofnięciu odrzucenia (przed zwykłą synchronizacją), pełna przebudowa liczników (`rebuild_count_projection_next_batch`) pomija komórki odrzuconych pozycji, a następca sekwencji nie odejmuje drugi raz komórek odrzuconego poprzednika (`_synchronize`). Zakres filtra: tylko `rejected` (nie `superseded`, bo komórki zastąpionej pozycji przechodzą do nowego właściciela).
- **P0-2 / P0-3 (trwała tożsamość odrzucenia slotu)** — migracja `0153` tworzy tabelę gry `image_board_geometry_pending_events` (append-only, partycja `LIST (game_id)`, RLS, UNIQUE `(game_id, idempotency_key)` i `(game_id, pending_geometry_id, rejection_revision, action)`, CHECK kształtu; bez FK do slotu), dopisaną do manifestu v7 (`ADDED_GAME_TABLES`), ORM `ImageBoardGeometryPendingEventModel`, strażnik downgrade’u odmawia przy jej wierszach. Odrzucenie slotu (`reject`): ten sam klucz i polecenie (suma kontrolna `rejection_command_sha256`) → zapisany wynik z `created=false` i tym samym `rejectionId`, także po cofnięciu (opóźnione ponowienie nie odrzuca slotu ponownie); ten sam klucz z innym poleceniem → `409 IMAGE_BOARD_CELL_PENDING_IDEMPOTENCY_CONFLICT`; inny klucz dla odrzuconego slotu → `409 IMAGE_BOARD_CELL_PENDING_ALREADY_REJECTED` (zastąpiło `..._REJECTION_CONFLICT`). Wpis „Ostatnie korekty” slotu to id zdarzenia odrzucenia (`boardGeometryRevisionId` = `rejectionId`); cofnięcie zapisuje zdarzenie `rejection_reverted` z kluczem i numerem odrzucenia, zwraca jego id jako `revertId`, powtórzenie klucza zwraca ten sam wynik (`created=false`), a klucz użyty do innego polecenia daje `GEOMETRY_REVERT_IDEMPOTENCY_CONFLICT`. Stare żądanie cofnięcia skierowane do wcześniejszego odrzucenia nie cofa nowszego (`GEOMETRY_REVERT_NOT_LATEST`).
- **P0-4 (500 z nieaktualnej listy)** — wpis slotu budowany jest z trwałego zdarzenia (czas i aktor zawsze ustawione); podgląd i cofnięcie odrzucenia, które nie jest już bieżące (cofnięte w innej karcie, nowsze odrzucenie), kończą się kontrolowanym `409 GEOMETRY_REVERT_NOT_LATEST` (także dla odrzucenia planszy).
- Zmiany kontraktu: `BoardCellGeometryRejectionResponse.rejectionId`; asercje w `test_game_data_v2_schema.py` (`GAME_TABLES` 69 → 70, v7 = v6 + dwie tabele); migracyjny test `0153` sprawdza też zdarzenia slotu (odmowa downgrade’u, brak tabeli po downgrade, partycja po upgrade).
- Testy PG (`test_pending_slot_rejection_postgres.py`, 5 testów): odrzucona, wcześniej pocięta plansza jest niewidoczna i niepoliczona (lista, liczniki wykładnicze, pełna przebudowa) i wraca po cofnięciu; inny klucz z tym samym powodem → 409; odrzucenie, cofnięcie i opóźnione ponowienie → slot zostaje `pending`; powtórzenie cofnięcia z utraconą odpowiedzią → ten sam wynik i `revertId`; stare żądanie cofnięcia nie cofa nowego odrzucenia; HTTP `revert-preview` po cofnięciu → 409, nie 500.

Weryfikacja po poprawkach (`PYTHONPATH` worktree, `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`):

- PG: `test_pending_slot_rejection_postgres.py` — 5 passed; `test_geometry_correction_revert_pending_postgres.py` (w tym migracja `0153` w górę, w dół i ponownie w górę) — 6 passed; `..._refusals_postgres.py` — 10 passed; `..._board_postgres.py` — 6 passed; `test_image_geometry_completeness_gate.py` — 7 passed; `test_virtual_deferred_resolution_postgres.py` — 9 passed; `test_image_geometry_completeness_repository.py` — 26 passed; `test_reviewer_operational_geometry_postgres.py` — 4 passed; `test_outside_current_owner_postgres.py` — 1 passed; `test_symbol_review_bulk_start_locking_postgres.py` — 4 passed.
- PG pozostałe, dotknięte manifestem v7 i widocznością komórek: `test_game_partition_lifecycle_postgres.py` — 6 passed; `test_postgres_baseline.py` — 5 passed; `test_application_role_isolation_postgres.py` — 25 passed; `test_game_storage_routing_postgres.py` + `test_grid_shadow_rls_postgres.py` — 12 passed, 4 skipped (jeden błąd teardownu `DROP DATABASE` przy przebiegu łańcuchowym zniknął po osobnym uruchomieniu); `test_per_game_isolation_new_game.py` — 12 passed; `test_board_render_manifests_postgres.py` — 3 passed; `test_superseded_import_image_removal.py` — 6 passed; `test_image_batch_store.py` — 16 passed; `test_super_game_series_postgres.py` — 27 passed, 1 failed: `test_real_operations_cover_every_write_point_source` (rejestr `SUPER_GAME_INPUT_WRITE_POINTS` zawiera źródło `geometry_correction_revert` dodane w TASK-0945, a lista `REAL_OPERATIONS` testu go nie pokrywa). Błąd nie wynika z tej rundy (nie dotykam rejestru ani testu), ale warto go domknąć w osobnym zadaniu (dodać operację cofnięcia slotu do `REAL_OPERATIONS`).
- Testy jednostkowe API: `test_board_cell_geometry_pending.py`, `test_geometry_correction_reverts.py`, `test_geometry_correction_revert_api.py`, `test_local_admin_security.py`, `test_game_data_v2_schema.py`, `test_openapi_contract.py` — 115 passed.
- `ruff check services/api services/worker services/test_support scripts` — czysto; `ruff format --check` zmienionych plików — czysto; `mypy services/api/src services/worker/src scripts` — Success, 865 plików; `export_admin_openapi.py --check` i `npm run check:generated --workspace @game-predictor/admin-api-client` — current; `generate_code_map.py --check` — up to date.
- Klient: `npm run test --workspace @game-predictor/admin-api-client` — 107 pass; typecheck — czysty. Reviewer: `test` — 251 pass; `test:geometry` — 58 pass; typecheck czysty; lint — 0 błędów, 1 istniejące ostrzeżenie; `reviewer:build` — sukces; prettier — czysto.
- Nowe pliki/zmiany tej rundy: `storage/geometry_rejection_revert.py` (zdarzenia slotu), `storage/geometry_correction_revert_models.py` (`ImageBoardGeometryPendingEventModel`), migracja `0153`, manifest v7, `image_symbol_review_repository.py`, `image_review_repository.py`, schematy/OpenAPI/klient, `API_CONTRACT.md`, `DATA_MODEL.md`, `GAME_DATA_V2_OWNERSHIP.md`.

### Poprawka regresji z TASK-0945/0946 (wykonana w tym tasku)

`test_super_game_series_postgres.py::test_real_operations_cover_every_write_point_source` padał, bo rejestr `SUPER_GAME_INPUT_WRITE_POINTS` ma źródło `geometry_correction_revert` (cofnięcie slotu, TASK-0945, i planszy, TASK-0946), a `REAL_OPERATIONS` go nie pokrywały. Test nie został osłabiony: `REAL_OPERATIONS` dostały operacje `geometry_revert_slot` (przypadek B) i `geometry_revert_board` (przypadek A), wykonujące produkcyjne cofnięcie zapisanej korekty (`GeometryCorrectionRevertService`) i sprawdzane tym samym testem „jedno podbicie wersji wejścia, wycofanie przy rollbacku”. Fixture `real_board` zakłada przed pomiarem dwie korekty przez produkcyjne ścieżki zapisu (slot: `resolve_manual`, wyjątek zdjęcia; plansza: `_import` i `_correct`); operacja `board_source_cleanup` usuwa teraz zakresy wszystkich zdjęć gry. Odrzucenia slotów nie zmieniają komórek, więc nie podbijają wersji; odrzucenie i cofnięcie odrzucenia planszy podbijają ją źródłem `symbol_cells` (już pokrytym). Weryfikacja: `test_super_game_series_postgres.py` + `tests/test_super_game_input_version.py` — 45 passed.

### Druga runda poprawek (decyzja leada)

Audyt Codex (`gpt-6-astra`, `medium`) runda 2: wcześniejsze P0-1…P0-4 zamknięte, nowe P0-5 i P0-6; raport zachowany bez zmian w `ai_docs/quality/TASK-0949_AUDIT_gpt-6-astra_round2.md`.

- **P0-5 (bezpośrednie `rejected → accepted/corrected`)** — jedna reguła zwalniania i przywracania liczników przy każdym przejściu z `rejected` i do niego: `save_resolution` (`image_review_repository.py`) woła `release_cells_of_rejected_board` przy wejściu w `rejected` oraz `restore_cells_of_reopened_board` przy każdym wyjściu ze `rejected` (accepted, corrected, superseded), przed zwykłą synchronizacją, która traktuje komórki aktywnej pozycji jako policzone; ścieżka cofnięcia odrzucenia używa tego samego `restore_cells_of_reopened_board`. Test PG `test_a_rejected_board_resolved_directly_restores_the_counters_exactly_once`: odrzucenie pociętej planszy, potem bezpośrednie `accepted` — lista i liczniki wykładnicze wracają do 30 (przed odrzuceniem 30, po odrzuceniu 15), brak `COUNT_PROJECTION_NEGATIVE`, pełna przebudowa zgodna (test sprawdzony: bez poprawki pada na `15 == 30`).
- **P0-6 (tożsamość polecenia cofnięcia planszy)** — powtórzenie cofnięcia pozycji porównuje teraz `command_sha256` zapisanego zdarzenia `reopened` (zawiera `rejectionEventId`) z poleceniem żądania; klucz użyty do cofnięcia innego odrzucenia daje `409 GEOMETRY_REVERT_IDEMPOTENCY_CONFLICT`. Ścieżka slotu już porównywała sumę kontrolną i `pending_geometry_id` (`_replayed_slot_revert`). Testy PG (slot i plansza): odrzucenie A, cofnięcie kluczem K, odrzucenie B, cofnięcie B kluczem K → 409 bez zmian w bazie; powtórzenie cofnięcia A kluczem K po odrzuceniu B zwraca zapisany wynik (`created=false`, ten sam `revertId`) i nie cofa B.
- Skutek uboczny filtra widoczności z rundy 1: testowy schemat SQLite `test_image_symbol_review_query_storage.py::test_confidence_seek_preserves_rows_counts_and_cursor_order` tworzył tylko tabelę komórek (12 testów padało na `NOT EXISTS image_review_items`). Fixture dostał minimalną tabelę `image_review_items` i kolumnę `review_item_id`; asercje się nie zmieniły, a przypadek komórek odrzuconej pozycji jest nowym wierszem testowym (wykluczony z listy).

Weryfikacja (`PYTHONPATH` worktree, `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`): `test_pending_slot_rejection_postgres.py` — 6 passed; `test_geometry_correction_revert_{pending,refusals,board}_postgres.py` — 6, 10, 6 passed; `test_image_geometry_completeness_gate.py` — 7 passed; `test_virtual_deferred_resolution_postgres.py` — 9 passed; testy dotykające `count_projection`: `test_cell_level_verification_migration` 1, `test_neural_automatic_import_postgres` 2, `test_outside_current_owner_postgres` 1, `test_symbol_review_bulk_start_locking_postgres` 4, `test_image_batch_store` 16, `test_exact_symbol_review_counts_migration` 1, `test_image_symbol_review_query_storage` 51 (po poprawce fixture), `test_partial_board_reconciliation_cli` 5, `test_qualified_cell_reconciliation` 2, `test_symbol_cell_source_visibility` 26, `test_symbol_count_rebuild_interleaving` 6 — wszystkie passed; testy API: `test_board_cell_geometry_pending` 22, `test_geometry_correction_reverts` 40, `test_geometry_correction_revert_api` 24, `test_local_admin_security` 6, `test_openapi_contract` 18 — passed; `ruff check` czysto, `ruff format --check` zmienionych plików czysto, `mypy` — Success (865 plików).

### Trzecia runda poprawek (decyzja leada)

Audyt Codex (`gpt-6-astra`, `medium`) runda 3: P0-7; raport zachowany bez zmian w `ai_docs/quality/TASK-0949_AUDIT_gpt-6-astra_round3.md`.

- **P0-7 (klucz cofnięcia unikalny w grze)** — klucz idempotencji cofnięcia jest jedną przestrzenią kluczy w grze: tabela audytu cofnięć korekt, zdarzenia slotów (`image_board_geometry_pending_events`) i wszystkie zdarzenia rozstrzygnięcia pozycji (`image_review_resolution_events`, każda akcja i pozycja). `GeometryRejectionRevertOperations.key_uses` czyta to jednym wspólnym wywołaniem w `SqlAlchemyGeometryCorrectionRevertRepository.revert` pod istniejącą blokadą doradczą `(game_id, klucz)`, przed jakimkolwiek zapisem. To samo polecenie (ta sama pozycja, akcja i `command_sha256`, albo audyt tej samej korekty) odtwarza zapisany wynik (`created=false`); każde inne użycie klucza, także klucz własnego zdarzenia `rejected` tej planszy (wcześniej wyjątek UNIQUE `(review_item_id, idempotency_key)`), daje `409 GEOMETRY_REVERT_IDEMPOTENCY_CONFLICT`. Cofnięcie korekty (A/B) z kluczem użytym w zdarzeniach slotu lub rozstrzygnięcia także kończy się 409.
- Test PG `test_the_key_of_a_revert_is_unique_within_the_game_across_every_store`: cofnięcie A kluczem K, potem B i slot tym samym K → 409 bez zmian w bazie; powtórzenie A kluczem K → ten sam wynik; klucz własnego odrzucenia planszy i klucz odrzucenia innej planszy → 409 (bez `IntegrityError`); klucz cofnięcia slotu zajęty dla planszy; wolny klucz cofa pozostałą planszę.
- Weryfikacja: `test_pending_slot_rejection_postgres.py` — 7 passed; `test_geometry_correction_revert_{pending,refusals,board}_postgres.py` — 6, 10, 6 passed; testy API: `test_board_cell_geometry_pending` 22, `test_geometry_correction_reverts` 40, `test_geometry_correction_revert_api` 24, `test_local_admin_security` 6, `test_openapi_contract` 18 — passed; `ruff check` czysto, `ruff format --check` zmienionych plików czysto, `mypy` — Success (865 plików), `generate_code_map.py --check` — up to date.

### Czwarta runda (decyzja leada): test pending_partial

Audyt Codex (`gpt-6-astra`, `medium`) runda 4: brak P0, jedno P1 (brak testu PG `pending_partial → rejected`); raport zachowany bez zmian w `ai_docs/quality/TASK-0949_AUDIT_gpt-6-astra_round4.md`.

- Dodano test PG `test_a_rejected_pending_partial_board_leaves_verification_with_its_outside_cells` (`test_pending_slot_rejection_postgres.py`). Plansza zdjęcia zaimportowanego z 15 pociętymi komórkami jest zamieniana w kwalifikowaną `pending_partial` (kwalifikacja geometrii, przypięty slot źródła z kwadrami komórek, częściowa rewizja renderu i write-through: komórki 0 i 1 stają się komórkami „outside”). Po odrzuceniu planszy test sprawdza: status planszy `rejected` (kwalifikacja `pending_partial` zachowana), 30 wierszy komórek zostaje jako historia, lista weryfikacji 30 → 15 i zakres „outside” 2 → 0, liczniki wykładnicze zgodne z listą (także zakres „outside”) i z pełną przebudową, a po cofnięciu odrzucenia 30 i 2. Test nie ujawnił błędu; kod bez zmian.
- Weryfikacja: `test_pending_slot_rejection_postgres.py` — 8 passed; `ruff check` czysto, `ruff format --check` czysto.

### Poprawka testów jednostkowych po pełnym przebiegu API

Pełny przebieg testów API pokazał 5 niepowodzeń w `test_symbol_review_extended_filters.py` (kontrakt testów zachowany):

- `test_source_filter_compiles_in_statements_that_join_the_revision[...]` (4 przypadki) liczy `EXISTS` w zapytaniu i wymaga jednego na alias rewizji predykcji. Predykat widoczności z TASK-0949 dodał własny `EXISTS`. Wariant (a): wykluczenie odrzuconych pozycji jest teraz niezależnym od wiersza `cell.review_item_id NOT IN (SELECT id FROM image_review_items WHERE status = 'rejected')` (zbiór odrzuconych pozycji jest mały, plan z haszowaną podkwerendą; `review_item_id` jest NOT NULL, więc reguła NULL w `NOT IN` nie ma zastosowania). Test nie został zmieniony ani osłabiony.
- `test_cell_paths_bind_the_game_store` wymaga dokładnie 9 wywołań `_bind_game_store` w `image_symbol_review_repository.py`; nowy pomocnik `_cells_of_item` dodał dziesiąte. Wywołanie usunięto (obie ścieżki wołające działają w transakcji, która już związała sklep gry); asercja bez zmian.
- Fixture SQLite w `test_image_symbol_review_query_storage.py` daje komórkom domyślny `review_item_id` żywej pozycji (kolumna jest NOT NULL).
- Weryfikacja: `test_symbol_review_extended_filters.py`, `test_image_symbol_review_query_storage.py`, `test_exact_symbol_review_counts_migration.py`, `test_symbol_cell_source_visibility.py`, `test_symbol_count_rebuild_interleaving.py`, `test_qualified_cell_reconciliation.py`, `test_partial_board_reconciliation_cli.py` — 114 passed; PG `test_pending_slot_rejection_postgres.py` — 8 passed; `test_outside_current_owner_postgres.py`, `test_symbol_review_bulk_start_locking_postgres.py`, `test_neural_automatic_import_postgres.py` — passed; ruff i mypy czysto.

### Zamknięcie (lead)

- Audyt Codex `gpt-6-astra`: runda 1 (`medium`) REVISE 4×P0; rundy 2–4 (`high`, migracja) REVISE kolejno 2×P0, 1×P0, 1×P1 (test `pending_partial`); wszystkie domknięte. Raporty: `ai_docs/quality/TASK-0949_AUDIT_gpt-6-astra*.md`. Dodatkowe rundy poprawek decyzją leada (operator polecił samodzielne rozwiązywanie problemów); po ostatniej rundzie (wyłącznie test) audytu nie powtarzano.
- Weryfikacja leada: pełny `pytest services/api/tests` (bez PG) → 2621 passed, 5 failed (regresja filtra widoczności w `test_symbol_review_extended_filters.py`) → naprawione bez zmiany testów; plik → 23 passed.
- Commit: v1.7.295.
