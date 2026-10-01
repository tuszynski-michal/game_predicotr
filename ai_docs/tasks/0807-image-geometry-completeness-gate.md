---
title: TASK-0807 — bramka kompletności geometrii zdjęcia w pipeline
status: todo
last_updated: 2026-10-01
---

# TASK-0807 — bramka kompletności geometrii zdjęcia w pipeline

## Status

`todo`

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
- [ ] Test PG: zapis brakującej dziewiątej siatki (ręczna geometria albo
      rozwiązanie odroczonej) → stan `geometry_complete` i 135 komórek w tej
      samej operacji; ponowienie operacji nie tworzy duplikatów.
- [ ] Test PG: wyjątek operatora na zdjęciu 8/9 → `geometry_exception`,
      komórki dla 8 plansz (120); wycofanie wyjątku przed jakąkolwiek
      decyzją człowieka przywraca `geometry_incomplete` i nie usuwa danych.
- [ ] Test PG: zdjęcie 9/9 zachowuje się jak przed zmianą (regresja).
- [ ] Plansza `uncertain` albo `partial` wstrzymuje zdjęcie tak samo jak
      brakująca; zatwierdzenie geometrii przez człowieka odblokowuje.
- [ ] Backfill nadaje stan wszystkim zdjęciom, jest wznawialny po
      przerwaniu, nie usuwa żadnego wiersza i raportuje liczbę zdjęć
      niekompletnych, które już mają komórki.
- [ ] Migracja ma `downgrade`, przechodzi `npm run db:baseline:verify`.
- [ ] Kontrakt pionem (OpenAPI, klient, wrapper, test żądania).
- [ ] Osobny commit, `Outcome`, `CURRENT_STATE.md`.

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

Wypełnia agent po pracy.

### Changed

- Do uzupełnienia po wykonaniu.

### Verification results

- Do uzupełnienia po wykonaniu.

### Not completed

- Do uzupełnienia po wykonaniu.

### Documentation updates

- Do uzupełnienia po wykonaniu.

### Recommended next task

- Do uzupełnienia po wykonaniu.
