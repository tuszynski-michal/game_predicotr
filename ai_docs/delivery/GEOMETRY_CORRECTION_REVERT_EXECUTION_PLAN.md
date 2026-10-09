---
title: Cofnięcie ostatniej korekty cięcia siatki, odrzucanie przyciętych plansz i zdjęcie zastępcze (plan wykonawczy)
status: proposed
last_updated: 2026-10-09
---

# Cofnięcie ostatniej korekty cięcia siatki

Plan przygotowany 2026-10-09 na prośbę operatora („cofnij ostatnie
zatwierdzenie z korekty cięcia siatki”). Analiza bez zmian w aplikacji i
danych. Uzupełniony tego samego dnia o odrzucanie przyciętych plansz i
zdjęcie zastępcze (W7–W9). Proponowane decyzje: D-538 (cofanie) i D-539
(odrzucanie i zamiennik, zmienia D-238), zapisywane w TASK-0951.

## Wymagania operatora (2026-10-09, rozstrzygnięte)

| # | Wymaganie | Źródło |
|---|---|---|
| W1 | Cofnięcie przywraca stan sprzed korekty: geometrię, decyzje komórek (w tym `grid_issue`) i obecność planszy w kolejce „Korekta cięcia siatki”. Symbole narzucone przy korekcie (D-488) są wycofane. | odpowiedź „Przywróć stan sprzed” |
| W2 | Cofnąć można tylko najnowszą ręczną korektę planszy i tylko gdy po niej nic się nie zmieniło (CAS). Drugie cofnięcie nie działa jak „redo”. | odpowiedź „Tylko ostatnią” |
| W3 | Reviewer ma sekcję „Ostatnie korekty” bieżącego importu z przyciskiem „Cofnij”, podglądem skutków i potwierdzeniem. | odpowiedź „Lista ostatnich korekt” |
| W4 | Migracja `0153` z nową akcją `geometry_reverted`; migrację wykonuje operator (stop usług → `db:migrate` → start). | odpowiedź „Tak, z migracją” |
| W5 | Obsługiwane oba rodzaje korekt: (B) rozstrzygnięcie odroczonego slotu, (A) korekta istniejącej planszy. | odpowiedź „Oba” |
| W6 | Cofnięcie korekty slotu może fizycznie usunąć wiersze utworzone przez cofany zapis; audyt zostaje w osobnej tabeli z migawką. | odpowiedź „Tak, z audytem” |
| W7 | Po imporcie operator odrzuca w Reviewerze przyciętą planszę albo slot odroczony (np. ucięty górny rząd); odrzucona plansza nie jest cięta na symbole. | prośba operatora 2026-10-09 |
| W8 | Odrzucenie nie dopuszcza reszty zdjęcia: pozostałe plansze czekają (bramka D-484 bez zmian) na zamiennik albo ręczny wyjątek. | odpowiedź „Całe zdjęcie czeka” |
| W9 | Lepsze zdjęcie wgrywa się zwykłym importem (`seq_*`); przejmuje tylko sekwencje odrzucone albo bez właściciela, nie rusza dobrych plansz starego zdjęcia; stary slot zostaje zamknięty, a stare zdjęcie przeliczone. | odpowiedź „Zwykły import + sprzątanie” |

## Stan obecny (fakty z kodu i bazy, 2026-10-09)

Ścieżki względem `services/api/src/game_predictor_api/`.

- Brak jakiejkolwiek operacji cofnięcia ręcznej rewizji geometrii. Wzorce
  „rollback przez nowy wpis”: `storage/grid_calibration_repository.py:392`
  (aktywacja profilu siatki), `storage/symbol_model_registry_repository.py:250`.
- **Przypadek B (slot odroczony).** Reviewer woła
  `resolvePendingBoardCellGeometryManually`
  (`api/board_cell_geometry_pending.py:295` →
  `application/board_cell_geometry_pending.py:360` `resolve_manual` →
  `application/virtual_grid_geometry.py:697` `save_pending_slot` →
  `storage/virtual_grid_geometry_repository.py:367`
  `save_virtual_source_geometry_revision` → `_materialize_pending_source_slot`
  `:1515`). Jedna transakcja:
  - dopisuje rewizję `image_source_geometry_revisions` (`manual_v1`,
    `accepted`, `revision = max + 1`, deduplikacja po
    `(source_image_id, geometry_checksum_sha256)` — UNIQUE);
  - tworzy `recognized_boards` (`id = pending.id`), `image_review_items`
    (`id = uuid4()`, zapisane w `pending.review_item_id`), rewizję
    `image_board_geometry_revisions`, `board_render_manifests`, zdarzenie
    `geometry_saved`;
  - ustawia slot `status = 'resolved'`, `resolved_geometry_revision`,
    `resolved_at`, `recognized_board_id`, `review_item_id`;
  - przepina sąsiednie plansze `geometry_revision = 0` na nową rewizję źródła
    (`repoint_live_boards_to_newest_source_revision`,
    `storage/image_geometry_completeness_state_repository.py:680`);
  - przelicza bramkę kompletności zdjęcia (D-484/D-485); jeśli zdjęcie zostaje
    dopuszczone, tnie komórki wszystkich plansz zdjęcia;
  - tworzy komórki planszy (bez zdarzenia utworzenia) albo **przejmuje**
    istniejące komórki sekwencji poprzedniego właściciela (`board_synchronized`);
  - może zastąpić (`superseded`) starszą pozycję oczekującą tej samej
    sekwencji (`storage/pending_sequence_ownership.py:154`);
  - przez wyzwalacze aktualizuje kolejkę przeglądu i status joba; aktualizuje
    projekcję wyszukiwarki, liczniki `image_symbol_review_states` i wersję
    wejścia supergry.
- **Przypadek A (istniejąca plansza).** Reviewer (lista zgłoszonych plansz)
  woła `createImageGridReviewGeometryRevision`
  (`api/image_grid_reviews.py:316`), a ekran operacyjny
  `createOperationalImageReviewGeometryRevision` (`api/image_reviews.py:536`).
  Oba kończą w `save_virtual_geometry_revision`
  (`storage/virtual_grid_geometry_repository.py:201`): nowa rewizja planszy
  `N = geometry_revision + 1`, nowa rewizja źródła, nadpisanie projekcji
  planszy, `_replace_current_cells` (zdarzenia `geometry_invalidated` z
  kolumnami `previous_*`), opcjonalnie symbole D-488 (`reassign`,
  `mark_unreadable`), ponowne otwarcie rozstrzygniętej pozycji
  (`_reopen_resolved_revision`) i automatyczne rozstrzygnięcie
  (`synchronize_board_from_cells`).
- Historia: rewizje geometrii planszy i źródła są append-only; numer rewizji
  planszy tylko rośnie (UNIQUE, CHECK `approved <= geometry_revision`, PK
  manifestu). Stan komórek jest nadpisywany w miejscu; zdarzenia komórek nie
  zapisują `previous_assignment_source`.
- „Bieżąca” rewizja źródła = najwyższa `revision` (zapytania wymienione w
  TASK-0945). Akcje: `ck_image_board_geometry_review_events_action`
  (`approved`, `geometry_saved`, `backfilled`),
  `ck_image_symbol_review_events_action` (bez akcji cofnięcia),
  `ck_image_source_geometry_revisions_state` (`pending`, `accepted`,
  `needs_review`, `rejected`). Head migracji: `0152_super_game_series`.
- Przykład z bazy (powód planu): gra Mumie
  `fea55cc1-ebf4-4cee-b3ab-a520017ed1be`, import `092ff7a4-…`, slot
  `378a273f-…` (sekwencja 69004, pozycja 0) rozstrzygnięty 2026-10-09
  08:39:41 UTC; utworzył rewizję źródła 1 nad rewizją 0 (`neural_grid_v1`,
  `needs_review`), planszę, pozycję `d54372d9-…` i 15 komórek bez zdarzeń;
  przepiął plansze 69006–69012; zdjęcie zostało `geometry_incomplete` (slot
  pozycji 1 nadal `pending`).

## Model domenowy (decyzje planu)

### Jednostka cofnięcia

Jednostką jest **jeden zapis korekty**, identyfikowany rewizją geometrii
planszy (`image_board_geometry_revisions.id`) i zdarzeniem `geometry_saved`.
Zapis źródła z wieloma slotami naraz (korekta całego zdjęcia) jest poza
zakresem: cofnięcie odmawia, gdy rewizja źródła cofanego zapisu jest wskazana
przez rewizję innej planszy niż cofana (poza przepiętymi sąsiadami
`geometry_revision = 0`).

### Warunki dopuszczenia (wspólne, fail-closed)

Cofnięcie jest dozwolone wyłącznie, gdy wszystkie warunki są spełnione.
Każdy niespełniony warunek ma własny kod błędu (409) i komunikat po polsku;
lista korekt pokazuje pierwszy niespełniony warunek zamiast przycisku.

| Kod | Warunek |
|---|---|
| `GEOMETRY_REVERT_NOT_LATEST` | cofana rewizja nie jest bieżącą rewizją planszy albo po niej jest inne zdarzenie geometrii planszy (w tym wcześniejsze cofnięcie) |
| `GEOMETRY_REVERT_STALE` | CAS: `expectedGeometryRevision` lub `expectedResolutionRevision` różni się od stanu |
| `GEOMETRY_REVERT_SOURCE_ADVANCED` | rewizja źródła cofanego zapisu nie jest najwyższą nie-cofniętą rewizją zdjęcia (później poprawiono inny slot) |
| `GEOMETRY_REVERT_SHARED_SOURCE_REVISION` | rewizję źródła wskazuje inna plansza z `geometry_revision > 0` |
| `GEOMETRY_REVERT_CELLS_CHANGED` | komórki planszy mają zdarzenia późniejsze niż transakcja korekty (np. weryfikacja symboli) |
| `GEOMETRY_REVERT_RESOLVED` | pozycja przeglądu jest rozstrzygnięta (`accepted`/`corrected`/`rejected`/`superseded`) albo ma zdarzenia rozstrzygnięcia z transakcji korekty lub późniejsze |
| `GEOMETRY_REVERT_SEQUENCE_OWNERSHIP` | korekta zastąpiła inną pozycję sekwencji albo przejęła jej komórki (B) |
| `GEOMETRY_REVERT_IMAGE_ADMITTED` | korekta dopuściła zdjęcie przez bramkę kompletności (stan zdjęcia `geometry_complete`/`geometry_exception`, a przed korektą był inny) — cofnięcie nie „odcina” sąsiadów |
| `GEOMETRY_REVERT_PINNED` | planszę lub komórki wskazują `verified_training_cohort_*`, `symbol_reference_images`, `image_symbol_review_bulk_targets` albo `image_symbol_prediction_revisions` |
| `GEOMETRY_REVERT_REOPENED_RESOLUTION` | (A) korekta ponownie otworzyła rozstrzygniętą pozycję (`reopened` w transakcji korekty) — przywrócenie roszczenia kanonicznego jest poza zakresem |

„Transakcja korekty” jest wyznaczana strukturalnie, nie zegarem aplikacji:
zdarzenia komórek z `geometry_revision = N` i najwcześniejszym `created_at`
tej planszy (wartość `now()` jednej transakcji PostgreSQL). TASK-0946
weryfikuje to założenie na kodzie i bazie; jeśli nie zachodzi, warunek
`GEOMETRY_REVERT_CELLS_CHANGED` odmawia przy jakimkolwiek zdarzeniu z
`geometry_revision = N` innym niż `geometry_invalidated`, `reassign`,
`mark_unreadable` aktora korekty.

### Przypadek B — cofnięcie rozstrzygnięcia slotu (W6)

W jednej transakcji, z blokadami jak przy zapisie (sekwencje → zdjęcie →
slot):

1. Migawka JSON wszystkich usuwanych wierszy (plansza, pozycja, komórki,
   zdarzenia komórek, rewizja planszy, manifest, zdarzenie geometrii) do
   `image_geometry_correction_reverts.snapshot` z checksumą.
2. Liczniki: `_apply_count_deltas(before = komórki, after = ())`,
   snapshot/reconcile `cell_count` jak `_availability_snapshot`.
3. Usunięcie w kolejności FK (wzorzec `_delete_board_source_graph`,
   `storage/cleanup_repository.py:754`): zdarzenia komórek → komórki →
   zdarzenia geometrii planszy → rewizje geometrii planszy → `NULL` w
   `pending.recognized_board_id`/`review_item_id` → `image_review_items`
   (wyzwalacz i CASCADE czyszczą kolejkę, kandydata i dokument wyszukiwarki)
   → `recognized_boards` (CASCADE manifestów).
4. Slot: `status = 'pending'`, `resolved_geometry_revision`, `resolved_at`,
   `superseded_at` = `NULL`, `updated_at = now` (CHECK lifecycle).
5. Rewizja źródła cofanego zapisu: `status = 'reverted'`.
6. Odwrotne przepięcie sąsiadów (`geometry_revision = 0`, wskazują cofaną
   rewizję, identyczny wpis slotu w obu rewizjach) na poprzednią rewizję —
   nowy planner, zapisy przez istniejące `apply_board_repoint`; potem
   `sync_review_items` przepiętych pozycji.
7. `reconcile_sequence` sekwencji, `recompute_source_image_geometry_completeness`,
   `source_images.status` według reguły: `waiting_for_review`, gdy zdjęcie ma
   oczekujący slot albo pozycję `pending`; w przeciwnym razie bez zmiany.
8. `synchronize_after_cell_mutation` (catalog revision i wersja wejścia
   supergry; nowy punkt zapisu w `SUPER_GAME_INPUT_WRITE_POINTS`, źródło
   `geometry_correction_revert`).
9. Wiersz audytu i zdarzenie nie są wiązane FK z usuniętymi wierszami.

Wynik: slot wraca do kolejki „Korekta cięcia siatki” z propozycją z
poprzedniej rewizji źródła (dla 69004: `neural_grid_v1`).

### Przypadek A — cofnięcie korekty istniejącej planszy

1. Nowa rewizja planszy `N + 1` z geometrią rewizji `N − 1`:
   - `N − 1 ≥ 1`: `geometry`, `corners`, `virtual_render_spec` z wiersza
     `image_board_geometry_revisions` rewizji `N − 1`;
   - `N − 1 = 0`: wpis slotu `board_geometries[position_index]` z rewizji
     źródła, którą plansza wskazywała przed korektą (manifest rewizji 0 lub
     `previous_source_geometry_revision_id` zdarzeń komórek).
   Rewizja `N + 1` wskazuje poprzednią rewizję źródła (bez dopisywania nowej);
   nowy manifest renderu dla `N + 1`.
2. Rewizja źródła korekty: `status = 'reverted'`; odwrotne przepięcie
   sąsiadów jak w B.6.
3. Projekcja planszy: geometria, kwalifikacja, checksum, silnik z rewizji
   `N − 1`; `approved_geometry_revision` = `previous_approved_geometry_revision`
   ze zdarzenia korekty (może być `NULL`); `geometry_approved_at/by` ze
   zdarzenia, które zatwierdziło tę wartość, albo `NULL`.
4. Komórki: przeliczenie renderu dla `N + 1`, potem przywrócenie decyzji z
   najwcześniejszego zdarzenia transakcji korekty dla każdej komórki
   (`previous_assigned_symbol_id`, `previous_review_state`,
   `previous_quality_issue`, `previous_verification_outcome`,
   `previous_verified_symbol_id_v2`, `previous_approved_*`). Zatwierdzenie
   wraca tylko, gdy piksele nowego renderu = `previous_approved_rendered_pixel_checksum`
   (zasada D-462); inaczej komórka jest `pending` z dawnym symbolem jako
   podpowiedzią. `assignment_source`: z `previous_assignment_source`, gdy
   zdarzenie je ma (nowa kolumna); dla starszych zdarzeń reguła:
   poprzednio `approved` → `human`; `partial_visibility` → `geometry_partial`;
   w pozostałych przypadkach `model`. Zdarzenie komórki `geometry_reverted`.
5. Zdarzenie planszy `geometry_reverted` (`geometry_revision = N + 1`,
   `previous_approved_geometry_revision = N`).
6. Liczniki, wyszukiwarka, wersja supergry, bramka kompletności jak w B.

Przywrócenie `grid_issue` na komórkach przywraca planszę do kolejki korekty
(widok `correction`, `storage/image_grid_review_repository.py:446`).

### Rewizja źródła `reverted`

- Nowy status w CHECK. „Bieżąca” rewizja = najwyższa `revision` ze statusem
  różnym od `reverted` we wszystkich zapytaniach „latest” (lista w TASK-0945).
  Numeracja (`max + 1`) nadal liczy wiersze `reverted` (UNIQUE revision).
- UNIQUE `(source_image_id, geometry_checksum_sha256)` staje się indeksem
  częściowym `WHERE status <> 'reverted'`; deduplikacja w `append` (API i
  worker `pipeline_store.py`) pomija wiersze `reverted`. Ponowny zapis tej
  samej geometrii po cofnięciu tworzy nową rewizję.
- Ostrzeżenie `rejected`/`needs_review` bez zmian.

### Audyt i powtórzenia

- Nowa tabela `game_data_v2.image_geometry_correction_reverts`: `id`,
  `game_id`, `import_job_id`, `source_image_id`, `sequence_number`,
  `position_index`, `kind` (`pending_slot`/`board_revision`),
  `pending_geometry_id`, `recognized_board_id`, `review_item_id` (bez FK dla
  B), `reverted_geometry_revision`, `reverted_board_geometry_revision_id`,
  `reverted_source_geometry_revision_id`, `restored_source_geometry_revision_id`,
  `restored_geometry_revision` (A), `reverted_idempotency_key`,
  `idempotency_key` (UNIQUE per gra), `snapshot` JSONB, `snapshot_checksum_sha256`,
  `actor`, `created_at`. Wiersze tylko dopisywane.
- Powtórzenie żądania cofnięcia z tym samym kluczem zwraca zapisany wynik.
- Powtórzenie starego zapisu korekty z kluczem cofniętego zapisu
  (`_find_replay`, `application/virtual_grid_geometry.py:911`) zwraca 409
  `GEOMETRY_CORRECTION_REVERTED` zamiast wykonać zapis od nowa.
- `image_symbol_review_events` dostaje kolumnę `previous_assignment_source`
  (nullable), zapisywaną od TASK-0945 przez każde przejście komórki.

## Odrzucanie przyciętych plansz i zdjęcie zastępcze (W7–W9)

Fakty z kodu (2026-10-09):

- Odrzucenie slotu istnieje tylko przed importem (Admin, panel strażnika
  geometrii, `apps/admin/src/features/imports/geometry-guard-resolution-panel.tsx:1088`).
- Slot odroczony ma statusy `pending`, `resolved`, `superseded`
  (`storage/models.py:3705`); jedyną akcją jest narysowanie siatki.
- Pozycję przeglądu można odrzucić tylko gołym API
  (`POST /admin/image-review-items/{id}/resolution`, `action = rejected`,
  `api/image_reviews.py:613`); Reviewer nie ma przycisku.
- Odrzucona pozycja nie trafia do weryfikacji symboli, wyszukiwarki ani
  treningu. Brak żywej planszy na pozycji daje zdjęciu `INCOMPLETE_MISSING`
  (`domain/image_geometry_completeness.py:110`), chyba że sekwencja ma żywą
  planszę gdzie indziej (`sequence_live_elsewhere`, `:113`).
- Własność sekwencji przy imporcie: D-238 „najnowszy import zastępuje
  nierozwiązaną planszę” (`storage/pending_sequence_ownership.py:78`);
  kanoniczny właściciel zawsze wygrywa (first-save-wins, alternatywy).
- Slot odroczony z inną checksumą zdjęcia nie jest zamykany przez nowy import
  (`services/worker/src/game_predictor_worker/images/pipeline_store.py:668`).

Decyzje planu:

1. **Odrzucenie slotu odroczonego:** nowy status `rejected` w
   `image_board_geometry_pending` (kolumny `rejection_reason`, `rejected_at`,
   `rejected_by`; CHECK lifecycle), migracja `0153`. Slot znika z kolejki
   korekty. Powód wybierany z listy: `cropped` („Plansza przycięta”),
   `blurred`, `other` (z opisem).
2. **Odrzucenie istniejącej planszy:** istniejąca akcja rozstrzygnięcia
   `rejected` z powodem; przycisk w Reviewerze w „Korekta cięcia siatki” i na
   ekranie operacyjnym. Pozycja rozstrzygnięta `accepted`/`corrected` też
   może być odrzucona tylko, jeśli nie jest kanonicznym właścicielem; inaczej
   409 `BOARD_REJECT_CANONICAL` (przejęcie kanonu to TASK-0305, poza zakresem).
3. **Bramka:** odrzucona pozycja liczy się jak brak planszy (W8). Zdjęcie
   czeka, dopóki sekwencja nie dostanie żywej planszy z innego zdjęcia albo
   operator nie ustawi wyjątku.
4. **Cofnięcie odrzucenia:** odrzucenie pojawia się w „Ostatnie korekty” i
   można je cofnąć (slot wraca do `pending`, pozycja wraca do `pending` przez
   nowe zdarzenie rozstrzygnięcia), dopóki zamiennik nie przejął sekwencji.
5. **Zamiennik (D-539, zmienia D-238):** nowa plansza przejmuje sekwencję,
   gdy nie ma ona żywego właściciela albo właściciel jest odrzucony
   (pozycja `rejected` lub slot `rejected`). Gdy właścicielem jest żywa
   pozycja `pending` innego zdjęcia, nowa plansza dostaje `superseded` i
   alternatywę `superseded_existing_owner_kept` (dotąd wygrywał najnowszy
   import). Wyjątek bez zmian: ta sama checksuma zdjęcia (ponowne
   przetworzenie) zachowuje dotychczasową ścieżkę.
6. **Sprzątanie po przejęciu:** odrzucony slot starego zdjęcia przechodzi do
   `superseded` (`superseded_at`), stare zdjęcie jest przeliczane przez bramkę
   (`sequence_live_elsewhere`) i — gdy wszystkie pozostałe pozycje są
   poprawne — dopuszczone do cięcia; raport importu pokazuje „Zastąpione
   sekwencje”.

## API (TASK-0947)

Kontrakt definiuje backend; trasy w zakresie gry z `game_storage_scope`
(D-442), dodane do `security/local_admin.py` i
`apps/reviewer/src/security/reviewer-proxy-policy.ts`.

- `GET /api/v1/admin/games/{gameId}/image-imports/{importJobId}/geometry-corrections?limit=20`
  (`listGeometryCorrections`): ostatnie zdarzenia `geometry_saved` importu,
  najnowsze najpierw, maks. 50. Pola: `boardGeometryRevisionId`, `kind`,
  `sequenceNumber`, `positionIndex`, `createdAt`, `actor`,
  `geometryRevision`, `resolutionRevision`, `revertable`,
  `blockingReasonCode`, `blockingReasonMessage`.
- `GET …/geometry-corrections/{boardGeometryRevisionId}/revert-preview`
  (`previewGeometryCorrectionRevert`): skutki bez zapisu — rodzaj, liczba
  usuwanych komórek, czy usuwana jest plansza, liczba przepinanych sąsiadów,
  liczba komórek z przywracaną decyzją, poprzednia rewizja źródła (silnik,
  status), tokeny CAS.
- `POST …/geometry-corrections/{boardGeometryRevisionId}/revert`
  (`revertGeometryCorrection`), body `{idempotencyKey,
  expectedGeometryRevision, expectedResolutionRevision}` → wynik z
  identyfikatorem audytu i stanem po cofnięciu. Błędy: kody z tabeli warunków.

## UI Reviewera (TASK-0948)

Sekcja „Ostatnie korekty” pod kolejką w `BoardGeometryCorrectionWorkspace`
(`apps/reviewer/src/features/operational-reviews/board-geometry-correction-workspace.tsx`):
lista (godzina lokalna, sekwencja, pozycja, rodzaj, autor), przycisk „Cofnij”
tylko dla `revertable`, inaczej komunikat blokady. „Cofnij” otwiera
potwierdzenie z podglądem skutków; „Potwierdź cofnięcie” wysyła żądanie z
nowym kluczem idempotencji; po sukcesie odświeża kolejkę i listę. Błąd 409
pokazuje komunikat i odświeża listę. Lista odświeża się po każdym zapisie
korekty.

## Etapy i zadania

### Etap R1 — backend (bez UI)

- TASK-0945 — migracja `0153`, status `reverted`, audyt, cofnięcie slotu (B).
- TASK-0946 — cofnięcie korekty istniejącej planszy (A).
- TASK-0947 — API listy, podglądu i cofnięcia; OpenAPI, klient, allowlisty.

### Etap R2 — Reviewer

- TASK-0948 — sekcja „Ostatnie korekty” z podglądem i potwierdzeniem.

### Etap R3 — odrzucanie i zdjęcie zastępcze

- TASK-0949 — odrzucanie przyciętej planszy i slotu w Reviewerze (API, UI,
  cofnięcie odrzucenia).
- TASK-0950 — przejęcie sekwencji przez zdjęcie zastępcze i sprzątanie.

### Etap R4 — dokumentacja i odbiór

- TASK-0951 — D-538, D-539, dokumenty, scalenie po migracji operatora,
  odbiór na slocie 69004 i na jednym zdjęciu zastępczym.

Migracja `0153` (TASK-0945) zawiera także status `rejected` slotu (W7), żeby
wdrożenie miało jedną migrację.

Kod wymagający `0153` nie może trafić do gałęzi integracyjnej przed
wykonaniem migracji przez operatora (API 8000 z `--reload` w głównym
checkoucie nie wystartuje). Scalenie i push tylko za zgodą operatora.

## Mapa wymaganie → zadanie → kryterium

| Wymaganie | Task | Kryterium / test |
|---|---|---|
| W1 (B) | 0945 | test PG: po cofnięciu slot `pending` w widoku `correction`, brak planszy/pozycji/komórek, sąsiedzi na rewizji 0, liczniki jak przed zapisem |
| W1 (A) | 0946 | test PG: komórki `grid_issue`/symbole/zatwierdzenia jak przed korektą; symbole D-488 wycofane |
| W2 | 0945, 0946 | testy każdego kodu blokady; drugie cofnięcie → `GEOMETRY_REVERT_NOT_LATEST` |
| W3 | 0947, 0948 | testy żądań klienta, testy UI listy/podglądu/potwierdzenia |
| W4 | 0945 | test migracji up/down na `*_test`; operator wykonuje `db:migrate` |
| W5 | 0945, 0946 | oba rodzaje w liście i w cofnięciu |
| W6 | 0945 | migawka z checksumą zawiera każdy usunięty wiersz; brak FK z audytu do usuniętych wierszy |
| W7 | 0945, 0949 | test PG: odrzucony slot znika z kolejki, nie ma komórek; odrzucona plansza poza weryfikacją; testy UI przycisku |
| W8 | 0949 | test PG: zdjęcie z odrzuconym slotem zostaje `geometry_incomplete`, pozostałe plansze bez komórek |
| W9 | 0950 | test PG: import zastępczy przejmuje tylko odrzucone/puste sekwencje, żywa pozycja `pending` zostaje; stary slot `superseded`, stare zdjęcie dopuszczone |

## Założenia i niewiadome

- Z1: zdarzenia komórek jednej transakcji mają wspólne `created_at`
  (`server_default now()`); weryfikuje TASK-0946 (fallback w tabeli warunków).
- Z2: render rewizji `N − 1` w `N + 1` daje identyczne piksele, jeśli wersja
  croppera się nie zmieniła; inaczej zatwierdzenia wracają jako `pending`
  (D-462), co jest zgodne z regułą, nie błędem.
- Z3: poprzedni `source_images.status` nie jest zapisany; reguła z B.7.
- N1: liczba korekt w istniejących danych odrzucanych przez warunki — do
  zmierzenia w TASK-0951 (odczyt).

## Ryzyka

- Złożony graf zapisów; częściowe cofnięcie byłoby gorsze niż brak cofnięcia.
  Mitigacja: jedna transakcja, fail-closed, testy PG porównujące pełny stan
  przed zapisem i po cofnięciu (projekcje, liczniki, kolejka, job, wyszukiwarka).
- Zmiana semantyki „latest” rewizji źródła dotyka bramki kompletności i
  propozycji kolejki; testy istniejących zestawów
  `test_image_geometry_completeness_repository.py` muszą przejść bez zmian.
- D-539 zmienia D-238: ponowny import innego zdjęcia nie zastąpi już żywej
  pozycji `pending`; operator musi ją najpierw odrzucić. Raport importu
  musi to pokazywać, żeby brak przejęcia nie był cichy.
- Fizyczne usuwanie (B) jest operacją destrukcyjną na danych operatora;
  wykonuje ją wyłącznie operator z UI po podglądzie. Agenci nie cofają korekt
  na bazie operatora (także 69004) bez osobnej zgody.

## Zakres wyłączony

- Cofanie korekt wielu slotów jednym zapisem źródła, cofanie dowolnej
  starszej rewizji, „redo”.
- Przywracanie roszczenia kanonicznego i alternatyw sekwencji.
- Cofanie wyjątku bramki (`geometry_exception`) i korekt geometrii strony.
- Panel Admin (tylko Reviewer), poza raportem importu w TASK-0950.
- Przejęcie sekwencji z kanonicznym właścicielem (TASK-0305).
- Osobny przycisk „Podmień zdjęcie” z uploadem przy planszy.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0945 | claude-opus-5-5 | high | Migracja, zmiana semantyki „latest” w wielu zapytaniach i fizyczne usuwanie grafu wierszy; błąd uszkadza dane. | tak: Codex `gpt-6-astra`, `high` (migracja i dane) |
| TASK-0946 | claude-opus-5-5 | high | Odtwarzanie decyzji komórek z historii zdarzeń i render nowej rewizji; ryzyko utraty zatwierdzeń. | tak: Codex `gpt-6-astra`, `high` (dane dowodowe) |
| TASK-0947 | claude-sonnet-5-5 | medium | Pion API według istniejącego wzorca (router, schematy, OpenAPI, klient, allowlisty) nad gotowym serwisem. | tak: Codex `gpt-6-astra`, `medium` |
| TASK-0948 | claude-sonnet-5-5 | medium | Komponent UI z listą, modalem i testami w istniejącym ekranie. | tak: Codex `gpt-6-astra`, `medium` |
| TASK-0949 | claude-sonnet-5-5 | high | Pion API + UI według istniejących wzorców rozstrzygnięcia, ale z wpływem na bramkę kompletności i kolejkę. | tak: Codex `gpt-6-astra`, `medium` |
| TASK-0950 | claude-opus-5-5 | high | Zmiana reguły własności sekwencji (D-238) w API i workerze oraz przeliczanie bramki starego zdjęcia; błąd gubi plansze. | tak: Codex `gpt-6-astra`, `high` (dane dowodowe) |
| TASK-0951 | claude-sonnet-5-5 | low | Dokumentacja, wpisy decyzji i odczytowy odbiór; operacje danych wykonuje operator. | tak: Codex `gpt-6-astra`, `medium` |
