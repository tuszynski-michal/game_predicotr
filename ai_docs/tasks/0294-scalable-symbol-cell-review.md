---
title: TASK-0294 — Masowa weryfikacja pojedynczych symboli
status: in_progress
last_updated: 2026-08-26
---

# TASK-0294 — Masowa weryfikacja pojedynczych symboli

## Goal

Udostępnić lokalny, skalowalny workflow masowej weryfikacji cropów symboli,
który synchronizuje stan pojedynczych komórek z kanoniczną decyzją całej planszy.

## Context

Istniejący Reviewer zapisuje wyłącznie kompletne decyzje 15 komórek. Właściciel
zaakceptował nowy model: stan review jest trwały per crop, błąd siatki jest
flagą komórki, a pełna plansza domyka się automatycznie tylko po zatwierdzeniu
wszystkich bieżących cropów. Szczegółowy, zaakceptowany plan wykonania znajduje
się w historii zadania Codex z 2026-08-26.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/quality/TEST_STRATEGY.md`

## Scope

- domena, migracje i resumowalny backfill stanów komórek,
- transakcyjna synchronizacja pełnej planszy i 15 cropów,
- bounded API oraz lokalny workspace Admina,
- durable operacje masowe w istniejącym general worker lane,
- filtr `Do poprawy siatki` w Reviewerze,
- benchmark 2 mln komórek i odbiór dokumentacyjny.

## Out of scope

- automatyczne trenowanie klasyfikatora symboli lub croppera,
- nowy worker lane, Redis, Celery, usługa zewnętrzna albo przechowywanie binariów
  cropów w PostgreSQL,
- rozwiązanie przyczyny tworzenia duplikatów pending z TASK-0291.

## Acceptance criteria

- [ ] Stan pojedynczej komórki jest checksum-bound i audytowalny.
- [ ] Wszystkie zatwierdzone plansze otrzymują po 15 zatwierdzonych komórek.
- [ ] Zatwierdzenie 15 komórek bez `?` domyka planszę przez istniejący canonical flow.
- [ ] Zła siatka jest flagą komórki i zasila filtr Reviewera bez drugiego źródła prawdy.
- [ ] Listowanie działa keysetowo po 60 elementów i nie materializuje pełnego wyniku.
- [ ] Masowe operacje są idempotentne, resumowalne i raportują konflikty jawnie.

## Technical notes

- `?` jest technicznym brakiem przypisania i nie może zostać zatwierdzony.
- Aktywna plansza bez `sequence_number` blokuje gotowość feature'u stabilnym błędem.
- Operacja wielotysięczna jest atomowa per plansza, nie globalnie; targety mają
  jawne wyniki `applied/conflict/failed/pending`.
- Nowy read path pokazuje tylko właściciela z `image_board_search_fast_documents`.

## Expected files

- `services/api/src/game_predictor_api/domain/image_symbol_reviews.py`
- `services/api/src/game_predictor_api/storage/models.py`
- `services/api/src/game_predictor_api/storage/image_symbol_review_repository.py`
- `services/api/alembic/versions/0066_*` i kolejne
- `apps/admin/src/features/symbol-reviews/`
- `apps/reviewer/src/features/operational-reviews/`

## Verification

Każdy pion uruchamia własne testy API/UI/worker oraz kontrolę typów. Końcowy
odbiór uruchamia `npm run quality`, build Admina i Reviewera oraz benchmark
skalowy z izolowaną PostgreSQL.

## Risks / open questions

- TASK-0291 nadal odpowiada za zapobieganie źródłowym duplikatom pending.
- Po rozpoczęciu częściowego review rollback kodu nie może automatycznie usuwać
  nowych tabel, ponieważ utraciłby niedomknięte decyzje komórek.

## Outcome

### TASK 1 — ukończony w `v0.8.19`

- Dodano czystą domenę pojedynczego cropa: identity, przejścia `approve`,
  `reassign`, `mark_grid_issue`, unieważnianie po geometrii i agregację
  `accepted/corrected` pełnej planszy.
- Dodano testy przejść, zakazu zatwierdzania `?`, unieważnienia 15 cropów,
  kompletności i agregacji planszy.
- Weryfikacja: test domenowy, trzy istniejące testy decyzji pełnej planszy,
  Ruff i izolowany mypy nowego modułu przeszły. Pełny mypy katalogu API ma
  istniejące, niezwiązane błędy brakujących stubs `game_predictor_worker`; nowy
  moduł jest czysty przy `--follow-imports=skip`.
- Nie dodano migracji, modelu ORM, endpointów, jobów ani UI — to pozostaje
  zakresem TASK 2+.

### TASK 2 — ukończony w `v0.8.20`

- Migracja `0066_image_symbol_review_cells` dodaje stan przebudowy per gra,
  trwałe komórki review z constraintami i indeksami oraz append-only historię
  zdarzeń. Cropy pozostają wyłącznie artefaktami filesystemu.
- Dodano wznawialny, keysetowy backfill oraz skrypt
  `scripts/rebuild_symbol_cell_reviews.py`. Backfill czyta wyłącznie bieżącego
  właściciela logicznej planszy, korzysta ze wspólnego mappera cropów
  Reviewera, rozróżnia geometrię bazową od poprawionej i fail-closed raportuje
  brak `sequence_number`, niepełne cropy oraz drift rewizji.
- Backfill nie generuje sztucznych eventów. Zabezpieczenie usuwania symbolu
  uwzględnia już przypisania komórek i historyczne eventy.
- Weryfikacja obejmuje migrację offline upgrade/downgrade, testy katalogu oraz
  izolowany PostgreSQL: accepted/corrected tworzą po 15 `approved`, poprawiona
  geometria wybiera aktualne `crop_artifacts`, restart wznawia po zapisanym
  kursorze, a
  aktywna plansza bez sekwencji kończy stanem kontrolowanego błędu.
- Brak HTTP, jobów, mutacji komórek i UI pozostaje zakresem TASK 3+.

### TASK 3 — ukończony w `v0.8.21`

- Dodano wspólny koordynator write-through działający w transakcji istniejącego
  Reviewera. Aktualizuje 15 bieżących komórek po pełnej decyzji, korekcie
  geometrii, ręcznym rozwiązaniu odroczonej geometrii, reinferencji symboli i
  siatki oraz przy utworzeniu/zmianie projekcji pipeline’u. Rezygnacja albo
  `superseded` pozostawia komórki audytowalne, ale istniejący read model ukrywa
  je poza aktualnym właścicielem.
- Geometria zawsze unieważnia wszystkie 15 pozycji na nowe cropy `pending` bez
  flagi siatki. Reinferencja aktualizuje sugestię i rewizję predykcji, ale nie
  nadpisuje przypisania ani zatwierdzenia człowieka. Pełna decyzja zapisuje 15
  `approved` z pochodzeniem `board_decision` i append-only eventami.
- Migracja `0067_symbol_cell_review_catalog_revision` dodaje monotoniczną
  rewizję katalogu per gra. Koordynator zwiększa ją najwyżej raz na transakcję,
  również gdy synchronizowanych jest kilka plansz.
- Weryfikacja: migracja lokalnej bazy do `0067` przeszła; statyczne upgrade /
  downgrade migracji daje `50 passed`; izolowany PostgreSQL potwierdził pełną
  decyzję, reinferencję bez nadpisania człowieka, geometrię resetującą 15
  cropów i wykluczenie `superseded` (`3 passed`).
- Operacje pojedynczych cropów, API i UI pozostają zakresem TASK 4+.

### Checkpoint po TASK 3 — ukończony

- Izolowany PostgreSQL potwierdził, że równoległe decyzje pełnej planszy
  zapisują jednego właściciela kanonicznego, a przegrana pozycja jest
  `superseded`. Review kolejności blokad potwierdził, że canonical, staging i
  fast-document są aktualizowane w tej samej transakcji co write-through 15
  komórek; nie znaleziono blokera przed odczytem TASK 4.

### TASK 4 — ukończony w `v0.8.22`

- Dodano lokalny, read-only kontrakt `symbol-cell-reviews` z keysetową stroną
  60 (maks. 100), filtrami symbolu lub `unknown`, stanu i scope-bound
  cursorami. Lista zwraca liczniki oraz rewizję katalogu bez materializowania
  pełnej listy cropów.
- Repozytorium zawsze łączy `image_symbol_review_cells` z aktualnym
  `image_board_search_fast_documents` i bieżącą geometrią, więc superseded,
  alternatywny właściciel i stale crop nie mogą wyciec do listy. Endpoint assetu
  wymaga oczekiwanej checksumy oraz ponownie weryfikuje aktualność, bezpieczną
  ścieżkę i bajty pliku.
- Weryfikacja obejmuje HTTP: filtry, `unknown`, keyset next/previous bez
  duplikatów, scope cursorów, gotowość projekcji i checksum-bound asset;
  izolowany PostgreSQL potwierdza wykluczenie komórek po usunięciu ich
  fast-document ownera. OpenAPI i wygenerowany klient zostały odświeżone.
- Nie dodano mutacji komórki, endpointów operacji masowych, workerów ani UI —
  pozostają wyłącznie zakresami TASK 5, 6 i 8+.

### TASK 5 — ukończony w `v0.8.23`

- Dodano wewnętrzny command path dla pojedynczego, checksum-bound cropa:
  `approve`, `reassign` oraz `mark_grid_issue`. Adapter blokuje w stałej
  kolejności sekwencję, planszę i komórkę, ponownie waliduje aktualnego
  właściciela, rewizję i tożsamość cropa, po czym zapisuje append-only event.
- Jedna transakcja obejmuje zmianę komórki, agregację kompletu 15 aktualnych
  cropów, pełną decyzję, canonical, staging, fast-document, kolejkę review i
  status joba. Komplet zatwierdzeń domyka planszę jako `accepted` lub
  `corrected`; przypisanie innego symbolu aktualizuje istniejącą decyzję.
- `mark_grid_issue` na zamkniętej planszy otwiera ją i usuwa canonical/staging,
  zachowując pozostałe 14 zatwierdzeń niezmienionych cropów. Tylko nowa
  geometria resetuje wszystkie 15 pozycji.
- Weryfikacja izolowanym PostgreSQL obejmuje domknięcie ostatniej komórki,
  korektę symbolu, kontrolowany konflikt checksumy, ponowne otwarcie ze stanem
  joba/kolejki oraz zachowanie 14 decyzji; istniejący test geometrii nadal
  potwierdza reset 15 cropów. Nie dodano endpointu mutacji, joba masowego ani
  UI: to pozostaje wyłącznie w TASK 6 i TASK 8+.

### TASK 6 — ukończony w `v0.8.24`

- Migracja `0068_image_symbol_review_bulk_operations` dodaje trwałe operacje
  masowe i ich zamrożone, checksum-bound targety oraz wiąże append-only event
  z operacją. `image_symbol_review_bulk` działa w istniejącym general lane;
  nie dodano nowego workera, Redisa ani Celery.
- Lokalne Admin API udostępnia preview, start i status. Zaznaczenie jest albo
  jawne (maksymalnie 10 000 cropów), albo filtrowane z rewizją katalogu i
  wykluczeniami. Start jest idempotentny względem gry, klucza i canonicalnej
  komendy; filter snapshot zapisuje targety przez SQL bez pobierania pełnej
  listy do procesu. `approve` na filtrze `unknown` jest blokowane.
- Worker przetwarza najwyżej 100 plansz na checkpoint. Każda plansza
  rewaliduje właściciela, rewizję, geometrię, checksumę i aktywność symbolu
  docelowego, a następnie zapisuje wszystkie jej cropy, pełną decyzję,
  canonical, staging, kolejkę oraz projekcję wyszukiwania w jednej transakcji.
  Wynik targetu jest jawny: `applied`, `conflict`, `failed` albo `pending`;
  retry po awarii wznawia wyłącznie pending.
- Test izolowanego PostgreSQL potwierdza exact retry, konflikt idempotency,
  snapshot filtra z wykluczeniem, wznowienie świeżym workerem po checkpointcie,
  atomowe oznaczenie 14 cropów jednej planszy oraz kontrolowany konflikt całej
  drugiej planszy po symulowanym drifcie geometrii. API, OpenAPI/generowany
  klient, lint oraz istniejący test pojedynczej mutacji pozostają zgodne.
- Nie dodano jeszcze filtra `Do poprawy siatki` Reviewerowi ani workspace’u
  Admina z kartami, zaznaczeniem i toolbar: to pozostaje TASK 7–9.

### TASK 7 — ukończony w `v0.8.25`

- Operacyjny endpoint Reviewera przyjmuje `gridIssueView = all | needs_grid_fix`
  i zwraca niezależny `needsGridFixCount`. Widok wymagający korekty używa
  skorelowanego `EXISTS` po bieżących komórkach `pending` z
  `has_grid_issue = true`, dlatego wiele flag jednej planszy nie powoduje
  duplikatów, a rejected/superseded nie trafiają do listy.
- Keyset cursor schema v3 wiąże filtr złej siatki. Użycie kursora z innego
  widoku kończy się kontrolowanym `IMAGE_REVIEW_CURSOR_SCOPE_INVALID`; scope
  zdalnego Reviewera nadal jest ograniczony przez istniejący `gameId` i
  `importJobId`.
- Reviewer pokazuje przełącznik `Wszystkie / Do poprawy siatki` wraz z liczbą
  plansz. Po rozwiązaniu lub zapisaniu geometrii w tym widoku odświeża kolejkę;
  nowa geometria resetuje flagi wszystkich 15 komórek, więc plansza natychmiast
  znika z listy.
- Weryfikacja obejmuje test API cursorów i remote scope, test integracyjny
  PostgreSQL dla wielu flag jednej planszy oraz jej usunięcia z filtra po
  korekcie geometrii, a także testy Reviewera, typecheck i OpenAPI.
- Workspace Admina z kartami cropów, zaznaczeniem i masowymi akcjami pozostaje
  wyłącznie zakresem TASK 8–9.
