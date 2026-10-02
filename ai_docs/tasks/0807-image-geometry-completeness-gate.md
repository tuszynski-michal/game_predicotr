---
title: TASK-0807 — bramka kompletności geometrii zdjęcia w pipeline
status: in_progress
last_updated: 2026-10-02
---

# TASK-0807 — bramka kompletności geometrii zdjęcia w pipeline

## Status

`in_progress` — kod, testy i dokumentacja gotowe; do decyzji orkiestratora:
adaptacja dokumentów wyszukiwarki (kryterium 1) i niezielony
`db:baseline:verify` (wyłącznie błędy sprzed zadania). Szczegóły w `Outcome`.

## Goal

Zdjęcie źródłowe ma trwały stan kompletności geometrii, a komórki
weryfikacji symboli i projekcja wyszukiwarki powstają wyłącznie dla plansz
zdjęć kompletnych albo objętych wyjątkiem operatora; test PG dowodzi, że
import zdjęcia z 8/9 siatek nie tworzy żadnej komórki, a dorysowanie
dziewiątej tworzy wszystkie 135 jedną operacją.

## Context

D-484. Dziś plansza z siatką idzie dalej niezależnie od pozostałych plansz
zdjęcia, a plansza bez siatki staje się wierszem
`image_board_geometry_pending`. TASK-0806 dał raport tylko do odczytu; to
zadanie egzekwuje regułę.

## Dependencies / entry conditions

- TASK-0806 ukończony: klasyfikacja pozycji i zdjęcia w
  `domain/image_geometry_completeness.py` jest jedynym źródłem definicji —
  to zadanie jej używa, nie kopiuje.
- Fakt: po scaleniu `v1.7.137` head Alembic na gałęzi i na bazie
  deweloperskiej to `0138_rls_policy_function_parallel_safe`; nowa migracja
  dostaje numer `0139`. Przed commitem sprawdź numer na
  `v1.1-vision-lab-hybrid-geometry` (inny tor mógł zająć `0139`).
- TASK-0808 ukończony: stany `superseded` i `import_failed` oraz odczyt
  pliku po `source_image_id` już istnieją; to zadanie ich nie powtarza.
  Mapowanie stanu trwałego: `complete` → `geometry_complete`;
  `incomplete_*` → `geometry_incomplete`; `superseded`, `import_failed`,
  `no_source_geometry` → `NULL` (zdjęcie poza bramką: nie ma żywych plansz
  do cięcia).
- Decyzja operatora 2026-10-02 („przepnij i tak powinno się dziać”): 449
  żywych plansz na 79 zdjęciach wskazuje starą automatyczną rewizję źródła
  `needs_review`, choć konwersja legacy (2026-10-01,
  `system:legacy-board-conversion-v1`,
  `storage/virtual_grid_geometry_repository.py`) zapisała zdjęciu nowszą
  ręczną rewizję `accepted`. To zadanie:
  1. wprowadza regułę: zapis nowej rewizji geometrii źródła zdjęcia
     przepina na nią (`recognized_boards.source_geometry_revision_id`)
     wszystkie żywe plansze tego zdjęcia, których pozycja jest w nowej
     rewizji — w tej samej transakcji; prześledź wszystkie miejsca
     zapisujące `ImageSourceGeometryRevisionModel` i ustal, które już to
     robią;
  2. w backfillu przepina istniejące żywe plansze wskazujące rewizję
     starszą niż najnowsza rewizja zdjęcia.
  Przepięcie jest dozwolone tylko wtedy, gdy geometria planszy (quad i
  siatka komórek, z których powstał manifest renderu) jest identyczna z
  wpisem tej pozycji w nowej rewizji; inaczej plansza zostaje bez zmian i
  trafia do raportu rozbieżności — przepięcie nie może zmienić cropów ani
  unieważnić decyzji człowieka. Zanim zakodujesz, sprawdź na bazie
  deweloperskiej (tylko `SELECT`), ile z 449 plansz spełnia ten warunek, co
  dokładnie zapisała konwersja legacy dla pozycji nieobjętych konwersją i
  jakie kolumny komórek (`source_geometry_revision_id`,
  `approved_source_geometry_revision_id`, manifest renderu) muszą pójść
  razem z planszą, żeby nie złamać CHECK-ów i kluczy obcych. Jeżeli
  identyczności nie da się wykazać dla większości, zatrzymaj się i zgłoś.
  1 254 plansze `rejected` na starych rewizjach zostają bez zmian.
- Fakt: SQL liczników w
  `storage/image_geometry_completeness_repository.py` powiela reguły
  klasyfikatora domenowego (testy PG pilnują zgodności). Przeliczanie stanu
  jednego zdjęcia ma używać klasyfikatora domenowego na pozycjach tego
  zdjęcia; backfill może używać agregacji SQL.
- Fakt: wykonawca zadania **nie** uruchamia migracji ani backfillu na bazie
  deweloperskiej. Zadanie kończy się migracją i backfillem zweryfikowanymi
  na bazach `*_test`, trybem podglądu backfillu (bez zapisu, z licznikami)
  i opisanym krokiem operatorskim. Operator zgodził się 2026-10-02 na
  migrację, backfill i zatrzymanie usług; przejście wykonuje orkiestrator
  po commicie zadania (zatrzymanie API i workerów wszystkich checkoutów →
  merge → migracja → podgląd backfillu → backfill → start;
  `ai_docs/guides/LOCAL_OPERATION_GUIDE.md`).

## Recommended execution

`claude-opus-5-5`, reasoning `high`. Zmiana przepływu importu i
materializacji komórek, migracja stanu zdjęcia i backfill na 56 tys. zdjęć;
błąd oznacza ciche pominięcie albo utratę pracy operatora. Zatrzymaj zadanie
i zgłoś, jeżeli materializacja komórek ma ścieżkę, której nie da się objąć
jednym predykatem bez zmiany kontraktu D-462/D-467. Audyt zawieszony decyzją
operatora (2026-10-01).

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md` (sekcja planu V3, sekcje D-462 i D-467)
- `ai_docs/delivery/GRID_ENGINE_V3_HYBRID_EXECUTION_PLAN.md`
- `ai_docs/process/DECISION_LOG.md` (D-484, D-449, D-462, D-467)
- `ai_docs/requirements/IMAGE_INGESTION.md` (sekcja D-484, odroczona
  geometria, `pending_partial`)
- `ai_docs/architecture/DATA_MODEL.md`,
  `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`
- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md` (przejścia migracyjne)
- `ai_docs/tasks/completed/0806-image-geometry-completeness-report.md`

## Scope

- Migracja Alembic: stan kompletności i wyjątek operatora na zdjęciu.
- Przeliczanie stanu w transakcji każdego zapisu, który zmienia geometrię
  plansz zdjęcia.
- Bramka w materializacji komórek weryfikacji symboli i w projekcji
  wyszukiwarki; dołączenie plansz po skompletowaniu.
- Wyjątek operatora per zdjęcie (Admin API, operacja wysokiego wpływu) i
  jego wycofanie.
- Backfill stanu dla zdjęć istniejących, wznawialny, bez cofania
  materializacji; raport rozbieżności.
- Admin: lista z TASK-0806 staje się kolejką zdjęć (akcja wyjątku, link do
  istniejącej korekty siatki, stan z bazy zamiast wyliczanego w locie).
- Dokumentacja: `DATA_MODEL.md`, `API_CONTRACT.md`, `ADMIN_APP.md`,
  `LOCAL_OPERATION_GUIDE.md` (krok migracji).

## Out of scope

- Uruchomienie migracji i backfillu na bazie deweloperskiej.
- Usuwanie albo unieważnianie istniejących komórek, decyzji człowieka,
  dokumentów wyszukiwarki dla zdjęć historycznie niekompletnych.
- Zmiana silnika geometrii, progów akceptacji rewizji źródła, Reviewera
  zdalnego, labu wizji.
- Nowa kolejka zadań, nowe lane'y workera.

## Acceptance criteria

- [ ] Test PG: import zdjęcia z 8/9 poprawnych siatek → stan
      `geometry_incomplete`, 0 komórek weryfikacji i 0 dokumentów
      wyszukiwarki dla tego zdjęcia; raport importu podaje jawny powód.
      (Spełnione z adaptacją: 0 komórek, 0 kandydatów i 0 dokumentów z
      dowodami symboli, jawny powód w raporcie; dokument sekwencji bez
      dowodów zostaje — patrz „Odstępstwa”.)
- [x] Test PG: zapis brakującej dziewiątej siatki (ręczna geometria albo
      rozwiązanie odroczonej) → stan `geometry_complete` i 135 komórek w tej
      samej operacji; ponowienie operacji nie tworzy duplikatów.
- [x] Test PG: wyjątek operatora na zdjęciu 8/9 → `geometry_exception`,
      komórki dla 8 plansz (120); wycofanie wyjątku przed jakąkolwiek
      decyzją człowieka przywraca `geometry_incomplete` i nie usuwa danych.
- [x] Test PG: zdjęcie 9/9 zachowuje się jak przed zmianą (regresja).
- [x] Plansza `uncertain` albo `partial` wstrzymuje zdjęcie tak samo jak
      brakująca; zatwierdzenie geometrii przez człowieka odblokowuje.
- [x] Backfill nadaje stan wszystkim zdjęciom, jest wznawialny po
      przerwaniu, nie usuwa żadnego wiersza i raportuje liczbę zdjęć
      niekompletnych, które już mają komórki.
- [ ] Migracja ma `downgrade`, przechodzi `npm run db:baseline:verify`.
      (`downgrade` jest i przechodzi własny test cyklu; pełny
      `db:baseline:verify` jest czerwony przez 19 testów czerwonych także na
      `HEAD` — patrz „Verification results”.)
- [x] Kontrakt pionem (OpenAPI, klient, wrapper, test żądania).
- [ ] Osobny commit, `Outcome`, `CURRENT_STATE.md`. (`Outcome` wypełniony;
      commit i `CURRENT_STATE.md` należą do orkiestratora.)

## Technical notes

### Stan (rozstrzygnięte)

Kolumny na `source_images` (tabela gry), migracja kolejnym numerem:

- `geometry_completeness_status` — `geometry_complete`,
  `geometry_incomplete`, `geometry_exception`; `NULL` = nieocenione
  (zdjęcie sprzed backfillu albo bez rewizji geometrii źródła);
- `geometry_completeness_evaluated_at`;
- `geometry_exception_reason` (tekst, wymagany), `geometry_exception_by`,
  `geometry_exception_at` — wszystkie trzy niepuste wtedy i tylko wtedy,
  gdy status to `geometry_exception` (CHECK).

Sprawdź, czy dodanie kolumn do tabeli gry wymaga zmiany manifestu magazynu
(`storage/game_data_v2_manifest_v4.py`) i partycji/RLS; jeżeli tak, opisz
w `Outcome` i w przewodniku pełną kolejność przejścia. Jeżeli kolumny na
`source_images` okażą się niemożliwe bez przebudowy manifestu, a osobna
tabela gry jest tańsza, zatrzymaj się i zgłoś wybór przed implementacją.

Mapowanie z klasyfikacji TASK-0806/0808: `complete` → `geometry_complete`;
każdy `incomplete_*` → `geometry_incomplete`; `superseded`,
`import_failed`, `no_source_geometry` → `NULL`.
`geometry_exception` ustawia wyłącznie operator.

### Przeliczanie

Jedna funkcja repozytorium `recompute_source_image_geometry_completeness(
session, game_id, source_image_id)`, wywoływana w tej samej transakcji co
zapis w każdym miejscu, które tworzy albo zmienia planszę, jej geometrię,
zatwierdzenie geometrii, kompletność albo wiersz odroczony. Znane punkty
wejścia do prześledzenia przed kodowaniem (lista do potwierdzenia i
uzupełnienia w `Outcome`):

- `services/worker/src/game_predictor_worker/images/pipeline_store.py`
  (writer importu, `RecognizedBoardModel(`),
- `storage/virtual_grid_geometry_repository.py` (ręczna geometria),
- `storage/board_cell_geometry_pending_repository.py` (odroczona geometria),
- `storage/image_grid_review_repository.py` (rewizje i zatwierdzenia siatki),
- `storage/partial_board_reconciliation_repository.py`,
- reweryfikacja siatek 777 (`system:grid-reverify-777-v1`).

Wyjątek operatora nie jest nadpisywany przez przeliczenie, chyba że
zdjęcie stało się kompletne (wtedy `geometry_complete`, pola wyjątku
czyszczone).

### Bramka

Predykat „zdjęcie dopuszczone” = status `geometry_complete` albo
`geometry_exception`. Zastosuj go w:

1. materializacji komórek weryfikacji symboli
   (`storage/image_symbol_review_repository.py` — wszystkie ścieżki
   tworzące `ImageSymbolReviewCellModel`, w tym backfill i ścieżka importu),
2. projekcji wyszukiwarki (`storage/board_search_projection_repository.py`).

Plansze zdjęć niedopuszczonych są pomijane z jawnym licznikiem i powodem
`SOURCE_IMAGE_GEOMETRY_INCOMPLETE` w wyniku operacji, nigdy po cichu.
Przejście zdjęcia do stanu dopuszczonego uruchamia materializację
wszystkich jego plansz istniejącym mechanizmem (ta sama transakcja albo
istniejący trwały job — wybierz to, czego już używa dana ścieżka; nie
dodawaj nowej kolejki). Operacje muszą być idempotentne (konflikt klucza
komórki = brak duplikatu).

Zdjęcia ze statusem `NULL` (nieocenione) zachowują dotychczasowe
zachowanie do czasu backfillu — bramka nie może zatrzymać pracy na danych
historycznych przed nadaniem stanu. Zdjęcia historyczne, które po backfillu
są `geometry_incomplete`, a mają już komórki: istniejące komórki i decyzje
pozostają dostępne bez zmian; bramka blokuje tylko tworzenie nowych.

### Wyjątek operatora

`POST`/`DELETE` w Admin API jako operacja wysokiego wpływu (nagłówki
potwierdzenia i audyt jak istniejące operacje tego typu). Wymagany powód.
Dozwolony tylko dla zdjęcia `geometry_incomplete`. Po wyjątku do cięcia idą
plansze w stanie `ok` oraz `partial` z zatwierdzoną kwalifikacją (D-449);
pozycje `missing`/`deferred`/`uncertain` pozostają bez komórek.

### Backfill

Wznawialny, partiami (≤ 500 zdjęć na transakcję), kursor po `id`; wzorzec
istniejących backfilli (`image_geometry_rollout_backfill_repository.py`).
Tylko ustawia status zdjęć z `NULL`. Raport: liczba zdjęć per status oraz
liczba zdjęć `geometry_incomplete` z istniejącymi komórkami.

### Niedozwolone skróty

- Nie filtruj w UI zamiast w zapisie.
- Nie usuwaj komórek przy przejściu do `geometry_incomplete`.
- Nie łap ogólnych wyjątków wokół przeliczenia — błąd przeliczenia ma
  wycofać transakcję zapisu geometrii.

## Expected files

- Istniejące: pliki z listy punktów wejścia, `storage/models.py`
  (`SourceImageModel`), `services/api/alembic/versions/` (nowa migracja),
  router importu/przeglądu siatek, `packages/admin-api-client`,
  `apps/admin/src/features/imports/geometry-completeness-section.tsx`
  (z TASK-0806).
- Nowe (proponowane):
  `storage/image_geometry_completeness_state_repository.py`,
  `services/api/tests/integration/test_image_geometry_completeness_gate.py`.

## Test cases

- 8/9 → brak komórek i dokumentów; 9/9 → jak dotąd; 8/9 + dorysowanie →
  135 komórek; 8/9 + wyjątek → 120; wycofanie wyjątku.
- Plansza `uncertain` blokuje; zatwierdzenie odblokowuje.
- Zakres 4 plansz: 4/4 kompletne.
- Restart w połowie backfillu → kontynuacja bez podwójnego liczenia.
- Zdjęcie `NULL` (nieocenione) → zachowanie sprzed zmiany.
- Ponowny import tego samego SHA nie zmienia stanu innego zdjęcia.
- Druga gra nie widzi stanu pierwszej (RLS / routing).

## Verification

```powershell
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_image_geometry_completeness_gate.py
npm run db:baseline:verify
npm run python:lint; npm run python:typecheck
npm run openapi:generate; npm run openapi:check
npm run typecheck --workspace @game-predictor/admin; npm run test --workspace @game-predictor/admin
```

Każda komenda z limitem (PG i `db:baseline:verify` do 600 s — znany czas
cyklu migracji; pozostałe 120 s). Testy PG pojedynczo. Testy są planowane,
nie zaliczone.

## Risks / open questions

- Liczba ścieżek tworzących komórki jest duża (ponad 100 odwołań w
  `image_symbol_review_repository.py`); pominięta ścieżka = dziura w bramce.
  Test powinien sprawdzać niezmiennik na poziomie bazy (brak komórek dla
  zdjęcia niedopuszczonego) po każdej publicznej operacji.
- Migracja tabeli gry wymaga okna bez zapisów i zgody operatora.
- Wycofanie wyjątku po decyzjach człowieka na komórkach: proponowane
  odrzucenie z błędem domenowym; do potwierdzenia przez operatora przy
  odbiorze.

## Outcome

Status: `in_progress`. Kod, migracja, backfill, kontrakt API, Admin, testy i
dokumentacja są gotowe i zweryfikowane na bazach `*_test`. Do decyzji
orkiestratora zostają dwie rzeczy: adaptacja dokumentów wyszukiwarki
(kryterium 1, „Odstępstwa”) i pełny `db:baseline:verify`, który jest czerwony
wyłącznie przez testy czerwone także na `HEAD`. Commit, `CURRENT_STATE.md`,
`DECISION_LOG.md` i przeniesienie pliku należą do orkiestratora.

### Prześledzone ścieżki zapisu i gdzie działa reguła

Zapis nowej rewizji geometrii źródła: tylko
`SqlAlchemyImageSourceGeometryRepository.append`, wołane z czterech miejsc —
worker `project_source_geometry`, `save_virtual_geometry_revision` (korekta
jednej planszy), `save_virtual_source_geometry_revision` (korekta całego
zdjęcia, rozwiązanie odroczonego slotu, reweryfikacja 777
`system:grid-reverify-777-v1` przez `VirtualGridGeometryService.save_source`)
i `convert_legacy_source`. Żadne z nich nie przepinało pozostałych plansz
zdjęcia. Teraz każde (gdy rewizja jest nowa) woła
`repoint_live_boards_to_newest_source_revision`, a potem
`recompute_source_image_geometry_completeness` (w API przez
`_settle_source_geometry`).

Przeliczanie stanu (ta sama transakcja, bez łapania wyjątków):

- worker `project_source_geometry` (po rewizji) i `project_recognition` (po
  zapisie plansz, przed synchronizacją wyszukiwarki i komórek; obrazy plansz,
  które straciły własność sekwencji, przez
  `recompute_source_images_of_review_items`), worker `resolve_board` przy
  odrzuceniu planszy;
- trzy zapisy ręczne i konwersja legacy w `virtual_grid_geometry_repository.py`
  (także obrazy plansz zmienionych przez `create_owned_pending_review_item`);
- `board_cell_geometry_pending_repository.py` `defer` i `resolve`;
- `image_review_repository.py`: rozstrzygnięcie, które zmienia żywość planszy
  (`rejected` ↔ żywa, w tym `superseded` innych wystąpień numeru), przez
  `_apply_review_outcome` → `_recompute_liveness_changes`;
- `partial_board_reconciliation_repository.py` nie zmienia geometrii ani
  żywości (tylko komórki istniejącego właściciela) — bez przeliczenia;
  `image_grid_review_repository.py` jest tylko do odczytu; zatwierdzenie
  geometrii zapisują wyłącznie zapisy ręczne wyżej.

Bramka (jeden predykat `withheld_review_item_ids`, decyzja w czystej
`geometry_gate_withholds_board`): `SymbolCellReviewWriteThroughCoordinator._synchronize`
(wszystkie `synchronize_after_*`, w tym backfill-rekoncyliacja),
`synchronize_board_from_cells`, `SqlAlchemyImageSymbolReviewRepository.backfill_next_batch`
i sprawdzenie kompletności backfillu (`_selected_items_without_exactly_fifteen_cells`),
projekcja wyszukiwarki `_payloads_from_rows` (więc `sync_review_item`,
`rebuild_game`, `stale_review_item_ids`), `_replace_current_cells` korekty
ręcznej (plansza wstrzymana nie ma czego przecinać). Materializacja po
dopuszczeniu: `materialize_admitted_source_image` (wyszukiwarka, potem komórki
istniejącym write-through) w tej samej transakcji.

### Changed

- Migracja `services/api/alembic/versions/0139_source_image_geometry_completeness.py`:
  pięć kolumn na rodzicu `game_data_v2.source_images`, trzy CHECK-i, dwa indeksy
  częściowe; `downgrade` odmawia `SOURCE_IMAGE_GEOMETRY_EXCEPTION_PRESENT`, gdy
  istnieje wyjątek operatora. `EXPECTED_ALEMBIC_HEAD` = `0139`. Manifest magazynu
  v4 i lifecycle partycji bez zmian (lifecycle porównuje kolumny z rodzicem).
- Domena `domain/image_geometry_completeness.py`: `SourceImageGeometryStatus`,
  `persisted_status_for`, `recomputed_status` (wyjątek zostaje do kompletu),
  `geometry_gate_withholds_board`, `require_geometry_exception_reason`,
  `SOURCE_IMAGE_GEOMETRY_INCOMPLETE`.
- Nowy `storage/image_geometry_completeness_state_repository.py`: przeliczanie,
  bramka, materializacja po dopuszczeniu, plan i wykonanie przepięcia plansz,
  wyjątek operatora (ustaw/wycofaj), wznawialny backfill
  (`SourceImageGeometryCompletenessBackfill`) z podsumowaniem z bazy.
- `storage/image_geometry_completeness_repository.py`: `classify_source_images`
  (klasyfikator domenowy na partii zdjęć; jedyna definicja dla przeliczenia i
  backfillu), w raporcie `gate` (liczniki stanu z bazy, plansze wstrzymane z
  powodem), w liście stan z bazy, wyjątek, `gateReasonCode` i filtr
  `completenessStatus`.
- Bramka i przeliczanie w `image_symbol_review_repository.py`,
  `board_search_projection_repository.py`, `virtual_grid_geometry_repository.py`,
  `board_cell_geometry_pending_repository.py`, `image_review_repository.py`,
  worker `images/pipeline_store.py`; `models.py` (`SourceImageModel`).
- API: `POST`/`DELETE .../geometry-completeness/{gameId}/images/{sourceImageId}/exception`
  (operacje wysokiego wpływu w `security/local_admin.py`), filtr
  `completenessStatus`, schematy w `schemas/image_geometry_completeness.py`,
  serwis `OperationalImageReviewService`, wiring w `main.py`.
- Skrypt `scripts/backfill_image_geometry_completeness.py` (npm
  `images:geometry-completeness:backfill`), liczniki wstrzymanych plansz w
  `scripts/rebuild_board_search_projection.py` i `scripts/rebuild_symbol_cell_reviews.py`.
- OpenAPI, wygenerowany klient, wrapper (`setSourceImageGeometryException`,
  `withdrawSourceImageGeometryException`, `completenessStatus`) i test żądania.
- Admin: sekcja „Kompletność siatek zdjęć” jako kolejka siatek (zakładki
  „Kolejka siatek”/„Wyjątki operatora” ze stanu w bazie, liczniki bramki, powód
  wstrzymania, „Dopuść wyjątkiem…”, „Wycofaj wyjątek”, „Popraw siatki w
  Reviewerze”), helpery w `geometry-completeness-state.ts`, `globals.css`.
- Testy nowe: `services/api/tests/integration/test_image_geometry_completeness_gate.py`
  (7 przypadków), domena i API rozszerzone, Admin, klient.

### Odstępstwa od specyfikacji (adaptacje)

1. **Dokument wyszukiwarki planszy wstrzymanej zostaje, bez dowodów symboli.**
   Tabela dokumentów sekwencji jest też rejestrem właściciela sekwencji:
   korekta siatki Reviewera (`_current_row`), lista kolejki siatek Reviewera
   (`_visible_statement`) i wybór backfillu komórek łączą się z nią. Brak
   dokumentu uniemożliwiłby poprawienie siatki właśnie tych zdjęć, które bramka
   wstrzymuje (Reviewer jest poza zakresem). Dlatego projekcja zapisuje
   kandydata i dokument z pustymi dowodami (`primary` same `null`,
   `knownEvidencePositions` puste): wyszukiwanie wymaga dowodu, więc plansza
   nie jest znajdowana, a przybliżona wygrana widzi ją jako nieznaną. Dotyczy
   tylko elementów `pending` (decyzja człowieka na całej planszy nie jest
   wynikiem cięcia). Licznik i powód: `gate.withheldBoards` z
   `SOURCE_IMAGE_GEOMETRY_INCOMPLETE` w raporcie i liście,
   `geometryWithheldReviewItemCount` w wynikach przebudowy.
2. **Korekta ręczna planszy bez komórek.** `_replace_current_cells` wymagał 15
   istniejących komórek; dla planszy wstrzymanej (zero komórek, zdjęcie
   niedopuszczone) korekta pomija przecinanie, a komórki powstają z nowej
   rewizji po dopuszczeniu. Inne przypadki braku komórek nadal kończą się
   `IMAGE_GRID_REVIEW_CELLS_INCOMPLETE`.
3. **„Zmaterializowana” = ma komórki.** Bramka blokuje tylko planszę bez
   żadnej komórki; plansza z komórkami (także na zdjęciu niekompletnym po
   backfillu) jest dalej utrzymywana. Na bazie 777 każdy aktywny element ma
   komórki, więc nic historycznego nie jest wstrzymywane.
4. **Przepięcie przenosi razem z planszą** `geometry_checksum_sha256` planszy,
   `source_geometry_revision_id` manifestu bieżącej rewizji i komórek oraz
   `approved_source_geometry_revision_id` (gdy wskazywał starą rewizję). Bez
   tego endpoint zasobu komórki (`SYMBOL_CELL_REVIEW_CROP_DRIFT`), kandydaci
   wzorców symboli i kontekst korekty Reviewera przestałyby działać. Piksele,
   specyfikacje renderu, `crop_sample_id`, decyzje, rewizje komórek i zdarzenia
   bez zmian. Warunek identyczności: wpis pozycji w obu rewizjach równy
   (`jsonb`), ta sama topologia i suma źródła, `geometry_revision = 0` (rekord
   rewizji geometrii planszy przypina własną rewizję źródła), manifest i komórki
   wskazują starą rewizję, brak komórek w kohortach treningowych.
5. **Przeliczanie przy zmianie żywości planszy** (rozstrzygnięcia review) —
   poza listą zadania, ale zadanie wymaga przeliczenia przy każdej zmianie
   planszy; tylko gdy plansza przechodzi `rejected` ↔ żywa.
6. **Wycofanie wyjątku po decyzji człowieka** odmawia
   `IMAGE_GEOMETRY_EXCEPTION_HUMAN_DECISIONS_PRESENT` (propozycja z „Risks”;
   do potwierdzenia przez operatora).

### Verification results

Wszystkie komendy z katalogu worktree, wyniki rzeczywiste.

- `pytest services/api/tests/test_image_geometry_completeness_domain.py` — 80
  passed; `test_image_geometry_completeness_api.py` — 37 passed; razem z
  `test_game_data_v2_schema.py`, `test_schema_readiness.py`,
  `test_lateral_lock_order.py`, `test_qualified_cell_reconciliation.py`,
  `test_local_admin_security.py` — 144 passed. Worker
  `test_image_pipeline_execution.py`, `test_virtual_only_import_writers.py` —
  26 passed.
- Szersze testy jednostkowe API (pliki `board_search|local_admin|openapi|
  board_cell_geometry|virtual|symbol_review|image_review|grid_review|
  geometry_completeness`): 592 passed; czerwone tylko testy czerwone
  także na `HEAD` (sprawdzone na kopii `git archive HEAD`):
  `test_openapi_contract.py::test_grid_review_openapi_is_topology_aware_and_checksum_bound`,
  `test_virtual_grid_geometry.py::test_qualified_partial_preview_keeps_slots_without_rendering_missing_pixels`
  (2), `test_image_symbol_reviews_api.py::test_list_endpoint_uses_keyset_cursors_without_duplicates`;
  `test_operational_image_reviews.py::test_asset_resolution_logs_missing_file_with_asset_kind_and_relative_path`
  zależy od kolejności (osobno przechodzi).
- PostgreSQL (`GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`, pojedynczo, bazy `*_test`):
  `test_image_geometry_completeness_gate.py` — 7 passed (import 8/9 →
  `geometry_incomplete`, 0 komórek, 0 dokumentów z dowodami, powód w raporcie;
  rozwiązanie 9. odroczonej → 135 komórek w jednym żądaniu, ponowienie bez
  duplikatów; 9/9 i 4/4 jak dotąd; wyjątek → 120 komórek, wycofanie →
  `geometry_incomplete` bez usuwania, odmowa po decyzji człowieka; 9 plansz
  `uncertain` → 0 komórek, korekta jednej planszy przepina 8 pozostałych na
  nową rewizję i tnie 135 komórek; backfill: podgląd bez zapisu, dwa przebiegi
  bez podwójnego liczenia, brak zmian liczby wierszy, przepięcie 17 plansz z
  komórką zatwierdzoną, 1 plansza z innym wpisem zostaje z powodem
  `GEOMETRY_ENTRY_DIFFERS`, druga gra nie widzi stanu; migracja `0139`:
  `downgrade` odmawia przy wyjątku, po wycofaniu cykl downgrade/upgrade).
  Istniejące: `test_image_geometry_completeness_repository.py` 26 passed,
  `test_image_batch_store.py` 16, `test_virtual_deferred_resolution_postgres.py`
  + `test_reviewer_operational_geometry_postgres.py` 13, `test_convert_legacy_boards_postgres.py`,
  `test_drop_cell_render_spec_postgres.py`, `test_board_render_manifests_postgres.py`,
  `test_drop_cell_observations_postgres.py`, `test_rls_policy_function_parallel_postgres.py`,
  `test_slim_prediction_revisions_postgres.py`, `test_partial_board_reconciliation_postgres.py`,
  `test_outside_current_owner_postgres.py`, `test_symbol_visibility_groups_postgres.py`,
  `test_verified_cell_search_projection.py`, `test_cell_level_verification_migration.py`,
  `test_board_search_approximate_win_repository.py`, `test_cell_render_specs_postgres.py`,
  `test_game_storage_routing_postgres.py` (12), `test_game_data_v2_postgres.py`,
  `test_game_partition_lifecycle_postgres.py`, `test_application_role_isolation_postgres.py`,
  `test_game_data_v2_qualification_migration.py`, `test_symbol_source_visibility_migration.py`,
  `test_unbound_game_route_probe_postgres.py`, `test_worker_job_store.py` — passed.
- `npm run db:baseline:verify` (cały katalog integracyjny, 18 min): 192
  passed, 21 failed, 1 error. 19 z nich jest czerwonych także na `HEAD`
  (`test_board_import_coverage_migration.py` 4,
  `test_board_import_coverage_repository.py` 8, `test_postgres_baseline.py` 3 —
  m.in. sztywne `0065` jako head, `test_layout_import_report_repository.py`,
  `test_m2_admin_acceptance.py`, `test_review_repository.py`,
  `test_v010_virtual_geometry_migration.py`). Pozostałe:
  `test_cell_render_specs_postgres.py` (zmieniony kontrakt — poprawiony,
  przechodzi), `test_release_workflow_integration.py` i błąd teardown w
  `test_game_storage_routing_postgres.py` (wyścig `pg_stat_activity`; oba osobno
  przechodzą). Pełnego przebiegu nie powtarzałem.
- `ruff check` i `ruff format --check` zmienionych plików Pythona: czysto.
  `mypy --strict` (z `MYPYPATH`) zmienionych modułów i skryptu: 0 błędów w
  nich (27 znanych błędów w 6 niezwiązanych plikach).
- `npm run openapi:generate`, `npm run openapi:check`: exit 0. Klient:
  `tsc --noEmit` czysto, `tsx --test test/client.test.mjs` 69 pass.
  Admin: `typecheck` czysto, `lint` 0 błędów (4 istniejące ostrzeżenia),
  `test` 619 pass. Prettier zmienionych plików TS/TSX/MJS/CSS: czysto.
- Podgląd backfillu na bazie deweloperskiej — te same funkcje
  (`plan_board_repoint`, `classify_source_images`) w transakcjach `READ ONLY`,
  bez kolumn `0139`, gra 777, 91 s: 56 812 zdjęć → `geometry_complete` 55 499,
  `geometry_incomplete` 60 (wszystkie `incomplete_partial`, wszystkie z
  komórkami), `NULL` 1 253 (`superseded`); do przepięcia 449 plansz na 79
  zdjęciach, nieprzepinalnych żywych plansz 0. Zgodne z niezależnym zapytaniem
  kontrolnym SQL (te same liczby). 1 254 plansze `rejected` na starych
  rewizjach nie są dotykane.

### Not completed

- Migracja i backfill na bazie deweloperskiej (poza zakresem; krok
  orkiestratora — `LOCAL_OPERATION_GUIDE.md`, sekcja „Migracja `0139`”).
- Widok Admina nie był oglądany w przeglądarce (zakaz uruchamiania serwerów);
  sprawdzone typy, lint i testy stanu/źródła.
- Przypadek „ponowny import tego samego SHA nie zmienia stanu innego zdjęcia”
  nie ma osobnego testu PG; własność sekwencji przy nowym imporcie przelicza
  stan zdjęć, które ją straciły (`recompute_source_images_of_review_items`).
- Zielony pełny `db:baseline:verify` — wymaga naprawy 19 testów czerwonych na
  `HEAD` (osobne zadanie).
- Zmienione istniejące testy (kontrakt zmienił się świadomie): PG
  `test_virtual_deferred_resolution_postgres.py::test_reviewer_resolution_writes_virtual_boards_through_the_application`,
  `test_drop_cell_render_spec_postgres.py`, `test_convert_legacy_boards_postgres.py`,
  `test_cell_render_specs_postgres.py` (zdjęcie z planszą odroczoną albo
  częściową jest teraz wstrzymane — test dopuszcza je wyjątkiem i dalej
  sprawdza komórki); w `test_convert_legacy_boards_postgres.py`,
  `test_drop_cell_render_spec_postgres.py` i `test_drop_cell_observations_postgres.py`
  schemat sprzed `0137`/`0134` dostaje dodatkowo kolumny `0139` (jak wcześniej
  `legacy_predictions_sha256`); jednostkowe `test_lateral_lock_order.py`
  (import przelicza bramkę przed stanem komórek), `test_qualified_cell_reconciliation.py`
  (atrapa zdjęcia ma `geometry_completeness_status=None`),
  `test_image_geometry_completeness_api.py` (nowe pola, filtr i wyjątek),
  `test_schema_readiness.py` (head `0139`).

### Documentation updates

- `ai_docs/architecture/DATA_MODEL.md` — kolumny bramki, CHECK-i, indeksy,
  przeliczanie, bramka, przepięcie.
- `ai_docs/architecture/API_CONTRACT.md` — `gate`, pola listy, filtr
  `completenessStatus`, `POST`/`DELETE .../exception`.
- `ai_docs/requirements/ADMIN_APP.md` — sekcja jako kolejka siatek.
- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md` — migracja `0139`, backfill,
  dokładne kroki przejścia i wycofania.
- `GAME_DATA_V2_OWNERSHIP.md` bez zmian (manifest się nie zmienia).
- Do decyzji orkiestratora: wpis w `DECISION_LOG.md` (adaptacje 1–6, w
  szczególności dokument wyszukiwarki bez dowodów zamiast braku dokumentu) i
  ewentualne doprecyzowanie `IMAGE_INGESTION.md` (D-484).

### Recommended next task

- Przejście na bazie deweloperskiej według `LOCAL_OPERATION_GUIDE.md`
  (migracja `0139`, podgląd, backfill); oczekiwany podgląd wyżej. Po nim
  kolejka siatek 777 to 60 zdjęć z planszami częściowymi (108 plansz
  `pending_partial`) — wszystkie mają komórki; dopuszczenie wymaga wyjątku
  operatora (D-449), bo klasyfikator nie uznaje planszy częściowej za `ok`.
- Osobne zadanie: naprawa 19 testów PG czerwonych na `HEAD`.
