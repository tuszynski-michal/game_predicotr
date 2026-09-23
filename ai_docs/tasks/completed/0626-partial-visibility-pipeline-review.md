---
title: TASK-0626 — GeometryQualification v3 i podłączenie pipeline'u workera (T2, sekcje A–D)
status: done
last_updated: 2026-09-23
---

# TASK-0626 — GeometryQualification v3 i podłączenie pipeline'u workera (T2, sekcje A–D)

## Status

`done` — sekcje A–D ukończone i zweryfikowane. Sekcje E (wymuszony
„nierozpoznany" przy zapisie recenzji) i F (rekoncyliacja) okazały się
znacznie większe niż ten plik zakładał (patrz Outcome) i zostały wydzielone
do `ai_docs/tasks/0627-partial-visibility-review-cell-reconciliation.md` na
osobne polecenie użytkownika.

## Goal

Komórka oznaczona przez T1 jako `partially_visible` trafia do Weryfikacji
symboli jako wymuszony „nierozpoznany" (`assignedSymbolId = null`,
niezależnie od predykcji modelu), nigdy automatycznie klasyfikowana, trwale
wykluczona z treningu — i przeżywa rekoncylację (korektę geometrii, ponowne
otwarcie planszy) bez błędów integralności.

## Context

T1 (TASK-0625, `v0.10.392`) dodał zdolność techniczną: `derive_virtual_cells`
renderuje komórki z 1–3 rogami poza kadrem (`VirtualCell.partially_visible`),
zamiast całkowicie je wykluczać. T1 świadomie nie zmienił zachowania
końcowego — `production_workflow.py` ma własny, redundantny filtr, który
nadal usuwa wszystkie zamaskowane komórki przed renderowaniem.

Podczas researchu do T2 (przed napisaniem kodu) odkryto, że założenie
„`unavailable_cell_indices` = kompletnie wykluczone" jest zakodowane
**niezależnie w trzech miejscach**, nie tylko w pipeline importu:

1. `production_workflow.py` — redundantny filtr crop-generation (do usunięcia
   w T2).
2. `SqlAlchemySymbolCellReviewQueryRepository._synchronize`
   ([image_symbol_review_repository.py:2172](../../services/api/src/game_predictor_api/storage/image_symbol_review_repository.py))
   — `expected_cell_indices = range(15) - unavailable_cell_indices`,
   rzuca błąd integralności przy niezgodności.
3. `materialize_current_image_review_cells` /
   `_virtual_current_cells_from_records`
   ([image_review_repository.py:2647](../../services/api/src/game_predictor_api/storage/image_review_repository.py))
   — jawnie udokumentowana jako **jedyna** implementacja wyboru „aktualnych"
   15 komórek (Reviewer + backfille); `available_indices` z tego samego
   wzoru, `len(observations) == len(available_indices)` jako twardy
   warunek.

Naprawienie tylko (1) sprawiłoby, że świeży import zacząłby zapisywać
obserwacje dla częściowo widocznych komórek, ale (2) i (3) rzucałyby błąd
integralności przy pierwszej korekcie geometrii lub ponownym otwarciu takiej
planszy. Użytkownik potwierdził rozszerzenie zakresu T2 na wszystkie trzy
miejsca (opcja B: nowe pole w `GeometryQualification`, liczone raz,
persystowane, z migracją Alembic — zamiast przeliczania geometrii na żywo w
każdym miejscu osobno).

## Dependencies / entry conditions

- T1 / TASK-0625 ukończony i zacommitowany (`v0.10.392`,
  `ai_docs/tasks/completed/0625-partial-visibility-domain-renderer.md`).
- Potwierdzone decyzje z wcześniejszego planu: DA-1 (próg 1–3/4 rogów),
  DA-2 (predykcja modelu nadal liczona jako podpowiedź, `assignedSymbolId`
  zawsze `null`), DA-3 (nowa, jawna wartość `quality_issue`/
  `assignmentSource`, nie reużycie `unreadable`), DA-4 (tylko
  `virtual_source`).
- Potwierdzone podczas researchu T2: rozszerzenie zakresu na `_synchronize`
  i `materialize_current_image_review_cells`; opcja B (persystowane pole,
  migracja) zamiast opcji A (przeliczanie na żywo).

## Recommended execution

`claude-sonnet-5`, reasoning `xhigh`. Uzasadnienie: zmiana obejmuje migrację
Alembic modyfikującą CHECK CONSTRAINT na dwóch tabelach, nowy wariant
kontraktu `GeometryQualification` (v3) z redundantną walidacją JSON↔kolumny
na poziomie bazy, oraz trzy niezależne miejsca w kodzie, które muszą się
zgodzić co do znaczenia „dostępna komórka". Błąd w którymkolwiek z nich
kończy się realną awarią integralności danych (nie tylko złym wynikiem
testu) przy korekcie geometrii na produkcyjnych danych. Eskalacja: jeśli
migracja wymagałaby przepisania istniejących wierszy (backfill) zamiast
czystego dodania nowego, opcjonalnego pola.
Dodatkowy review: tak — `claude-opus-5-5` / `xhigh`, review migracji i
wszystkich trzech miejsc rekoncyliacji przed commitem.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md` (D-434)
- `ai_docs/requirements/IMAGE_INGESTION.md` (sekcja „Kontrakt ręcznej
  kompletności i kwalifikacji", TASK-0505–0509, sprostowanie D-434)
- `ai_docs/tasks/completed/0625-partial-visibility-domain-renderer.md`

## Scope

### A. Domena — `GeometryQualification` v3

- `services/api/src/game_predictor_api/domain/geometry_qualification.py`:
  nowa stała `GEOMETRY_QUALIFICATION_VERSION_V2` (zamrożenie dzisiejszego
  „current" jako historycznego, wzorem `_V1`); `GEOMETRY_QUALIFICATION_VERSION`
  wskazuje na nową `"manual-geometry-qualification-v3"`; nowe pole
  `fully_unavailable_cell_indices: tuple[int, ...] = ()` — podzbiór
  `unavailable_cell_indices`, ten sam kształt walidacji (posortowane,
  unikalne, 0–14), niepusty tylko dla `version == V3`. `to_dict`/`from_dict`
  z per-wersyjną tabelą dozwolonych kluczy (V1/V2/V3), zamiast dzisiejszego
  dwuwariantowego `if version == GEOMETRY_QUALIFICATION_VERSION`.

### B. Migracja Alembic

- Nowy plik w `services/api/alembic/versions/`, wzorowany 1:1 na
  `0111_partial_grid_training_qualification.py` (ten sam wzorzec
  `_qualification_expression(guard: bool)`/`_v2_expression(guard: bool)` dla
  upgrade/downgrade), rozszerzający `ck_recognized_boards_qualification`
  (`recognized_boards`) i `ck_guard_decisions_qualification`
  (`image_import_geometry_guard_decisions`) o trzecią gałąź wersji v3
  (`includeInPartialGridTraining` boolean + `fullyUnavailableCellIndices`
  jako `jsonb_typeof(...) = 'array'`). `services/api/src/game_predictor_api/storage/models.py`
  — te same dwa `CheckConstraint` w kodzie zsynchronizowane z migracją.

### C. Wypełnianie nowego pola

- `services/api/src/game_predictor_api/domain/image_geometry_v2.py`:
  `resolve_manual_geometry_qualification` — w gałęzi `if missing:` liczy
  `fully_unavailable_source_cell_indices(quad, source=source,
  topology=topology)` i zwraca `GeometryQualification` w wersji V3 z
  wypełnionym `fully_unavailable_cell_indices`. Gałąź `else: return
  qualification` (brak brakujących komórek) bez zmian.

### D. Pipeline workera

- `services/worker/src/game_predictor_worker/images/production_workflow.py`:
  usunięcie/zmiana redundantnego filtra przy `derive_virtual_cells` (już
  poprawnie filtruje po T1 — nie trzeba go duplikować); predykcja modelu
  nadal liczona dla `partially_visible` komórek (DA-2); payload cropu
  niesie `partiallyVisible: bool` do etapu inferencji i dalej.

### E. Zapis rekordu recenzji

- `services/api/src/game_predictor_api/domain/image_symbol_reviews.py`:
  nowa wartość `SymbolCellQualityIssue` (DA-3, np. `PARTIAL_VISIBILITY`) i
  nowa wartość `SymbolCellAssignmentSource` (np. `GEOMETRY_PARTIAL`).
- `services/api/src/game_predictor_api/storage/image_symbol_review_repository.py`:
  ścieżka tworzenia `ImageSymbolReviewCellModel` — gdy przychodzący cel jest
  `partiallyVisible`, wymuszony `assigned_symbol_id = None`,
  `quality_issue = PARTIAL_VISIBILITY`, `assignment_source =
  GEOMETRY_PARTIAL`, `review_state = PENDING`, predykcja modelu (kod +
  pewność) nadal zapisana w `prediction_symbol_code`/`prediction_confidence`
  jako podpowiedź (DA-2).
- Trwałe wykluczenie z treningu: potwierdzić, że istniejąca bramka
  `is_symbol_cell_training_eligible` (wymaga `quality_issue is None`) już
  wystarcza — nowy `quality_issue` automatycznie blokuje trening nawet po
  ręcznym przypisaniu symbolu przez operatora.

### F. Rekoncyliacja

- `_synchronize` ([image_symbol_review_repository.py](../../services/api/src/game_predictor_api/storage/image_symbol_review_repository.py)):
  `expected_cell_indices` liczone z `fully_unavailable_cell_indices`, gdy
  qualification jest V3 i pole obecne; fallback do dzisiejszego
  `unavailable_cell_indices` dla V1/V2 (bezpieczne, zachowuje dzisiejsze
  zachowanie dla historycznych wierszy).
- `_virtual_current_cells_from_records`
  ([image_review_repository.py](../../services/api/src/game_predictor_api/storage/image_review_repository.py)):
  `available_indices` analogicznie.

### G. Testy i dokumentacja

- Nowe testy: domena (`test_geometry_qualification.py` — V3 round-trip,
  walidacja podzbioru, tabela kluczy per wersja), migracja (uruchomienie na
  lokalnym Postgresie: `npm run db:migrate`, potwierdzenie że istniejące
  wiersze V1/V2 nadal przechodzą constraint), `image_geometry_v2.py`
  (`resolve_manual_geometry_qualification` zwraca V3 z poprawnym
  `fully_unavailable_cell_indices`), `production_workflow.py` (crop +
  inferencja dla `partially_visible`), `image_symbol_review_repository.py`
  (`_synchronize` z mieszanką w pełni/częściowo niedostępnych komórek —
  test porównawczy z i bez nowego pola), `image_review_repository.py`
  (`_virtual_current_cells_from_records` analogicznie).
- `ai_docs/process/DECISION_LOG.md` (nowy wpis), `ai_docs/requirements/IMAGE_INGESTION.md`,
  `ai_docs/process/CURRENT_STATE.md`.

## Out of scope

- **Sekcje E, F, G tego pliku (zapis rekordu recenzji, rekoncyliacja,
  testy/dokumentacja tych dwóch) — wydzielone do
  `ai_docs/tasks/0627-partial-visibility-review-cell-reconciliation.md`.**
  Research przed implementacją E/F ujawnił, że „unavailable = w pełni
  wykluczone" jest zakodowane niezależnie w co najmniej 9 miejscach (nie 3,
  jak zakładał ten plik), i że trwałe przeniesienie `partiallyVisible` do
  `CellObservationModel` wymaga nowej kolumny + migracji Alembic
  (nieprzewidzianej tutaj). Zdecydowano nie mieszać tego dużo większego,
  osobno wycenionego zakresu z już ukończonym i przetestowanym A–D w jednym
  commicie.
- T3 (Admin UI — oznaczenie kart w Weryfikacji symboli jako „ramka wychodzi
  poza kadr") — osobne polecenie.
- `render_image_geometry_guard_preview` — potwierdzone w T1 jako
  niezależne narzędzie operatora, bez zmian.
- `image_page_geometry_overrides.slot_qualifications` — ma własny,
  płytszy `CheckConstraint` (`ck_page_override_slot_qualifications`,
  tylko długość tablicy) bez walidacji kształtu wersji per-element; nie
  wymaga zmian.
- Backfill istniejących wierszy V1/V2 na V3 — świadomie nie wykonywany;
  historyczne plansze zachowują dzisiejsze zachowanie (fallback do pełnej
  maski) aż do ponownej korekty/ponownego przeliczenia geometrii.
- `PageRegistrationThresholds`, `_relaxed_red_edge_accepted`,
  `page_geometry_registration.py` (D-420/D-430/D-431 — osobny, niezależny
  obszar: geometria stron, nie geometria komórek).

## Acceptance criteria

- [x] `GeometryQualification` V3: round-trip `to_dict`/`from_dict`
      zachowuje `fully_unavailable_cell_indices`; V1/V2 nadal parsowalne
      bez zmian (żadnych nowych wymaganych kluczy dla starych wersji).
- [x] `fully_unavailable_cell_indices` musi być podzbiorem
      `unavailable_cell_indices`; niepuste tylko dla V3; walidacja rzuca
      dla naruszeń (analogicznie do istniejących reguł dla
      `unavailable_cell_indices`).
- [x] Migracja: `ck_recognized_boards_qualification` i
      `ck_guard_decisions_qualification` akceptują V1, V2 i V3;
      `npm run db:migrate` przechodzi lokalnie bez błędu; istniejące wiersze
      (jeśli jakieś V1/V2 istnieją w lokalnej bazie) nadal spełniają
      constraint po migracji.
- [x] `resolve_manual_geometry_qualification` dla quadu z częściowo
      przesuniętą kolumną zwraca V3 z `fully_unavailable_cell_indices`
      równym dokładnie w pełni niedostępnym indeksom (nie całej masce).
- [ ] ~~Import (worker, `virtual_source`) tworzy realny rekord
      `ImageSymbolReviewCellModel` dla `partially_visible` komórki: ...~~ —
      przeniesione do TASK-0627 (sekcja E).
- [ ] ~~`symbolId=unknown` w Weryfikacji symboli zwraca taką komórkę.~~ —
      przeniesione do TASK-0627.
- [ ] ~~`is_symbol_cell_training_eligible` zwraca `False` dla takiej
      komórki...~~ — przeniesione do TASK-0627.
- [ ] ~~`_synchronize` i `_virtual_current_cells_from_records` poprawnie
      rekoncyliują...~~ — przeniesione do TASK-0627 (sekcja F), rozszerzone
      o 7 dodatkowych miejsc odkrytych podczas researchu (patrz Outcome).
- [x] Wszystkie istniejące testy dotknięte przez A–D pozostają zielone; 8
      przedwcześnie zdiagnozowanych jako „zielone" testów z T1 (sprzed tego
      taska) okazało się być cichą, nieprzetestowaną regresją T1 — naprawione
      tutaj (patrz Outcome).
- [x] `ruff`, `mypy` czyste (bez nowych błędów) dla zmienionych plików.

## Technical notes

Zob. sekcje Scope A–F powyżej — precyzyjny podział pracy odpowiada
kolejności zależności (domena → migracja → wypełnianie pola → pipeline →
zapis → rekoncyliacja). Kluczowy przykład wejście→wynik dla `_synchronize`:
plansza V3 z `unavailable_cell_indices=(0,1,5,6,10,11)`,
`fully_unavailable_cell_indices=(0,5,10)` → `expected_cell_indices =
{1,2,3,4,6,7,8,9,11,12,13,14}` (12 elementów, nie 9).

## Expected files

- Istniejące: pliki wymienione w sekcjach Scope A–F.
- Nowe: migracja Alembic w `services/api/alembic/versions/`.

## Test cases

Zob. sekcja Scope G.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_geometry_qualification.py services/api/tests/test_image_geometry_v2.py -q
npm run db:migrate
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_production_image_workflow.py services/api/tests/test_image_symbol_reviews_api.py services/api/tests/test_image_symbol_reviews_domain.py services/api/tests/test_image_symbol_review_query_storage.py services/api/tests/test_virtual_grid_geometry_repository.py -q
.\.venv\Scripts\python.exe -m ruff check <zmienione pliki>
.\.venv\Scripts\python.exe -m mypy <zmienione pliki źródłowe>
```

Timeout 120 s na krok (poza `db:migrate`, jeśli przewidywalnie krótsze —
zgłosić, jeśli dłuższe).

## Risks / open questions

- Migracja modyfikuje CHECK CONSTRAINT na produkcyjnie już używanych
  tabelach — `postgresql_not_valid=True` (wzorem 0111) unika pełnego
  skanu przy `ADD CONSTRAINT`, ale wymaga potwierdzenia, że to
  wystarczające dla lokalnej bazy dev (nie ma tu prawdziwego ruchu
  produkcyjnego równoległego do migracji).
- Jeśli w lokalnej bazie istnieją już wiersze V2 (`includeInPartialGridTraining`),
  upewnić się, że migracja i domena nadal je poprawnie odczytują
  (regresja, nie tylko nowe testy).

## Outcome

### Changed

- **A — domena:** `GeometryQualification` v3
  (`services/api/src/game_predictor_api/domain/geometry_qualification.py`):
  nowa stała `GEOMETRY_QUALIFICATION_VERSION_V3` (backend-only, request/
  response schema i Admin frontend zostają na v1/v2), nowe pole
  `fully_unavailable_cell_indices: tuple[int, ...] = ()` (ostatnie w
  dataclass, dla zgodności pozycyjnej), per-wersyjna tabela dozwolonych
  kluczy w `to_dict`/`from_dict`. Nowa metoda `to_client_dict()` — rzutuje
  v3 z powrotem na kontrakt v1/v2 (usuwa `fullyUnavailableCellIndices`) do
  użycia w każdej odpowiedzi HTTP, która echo'uje zapisaną kwalifikację.
- **B — migracja:** `services/api/alembic/versions/0120_fully_unavailable_cell_qualification.py`
  — rozszerza `ck_recognized_boards_qualification` i
  `ck_guard_decisions_qualification` o gałąź v3 (`postgresql_not_valid=True`
  wzorem 0111); `services/api/src/game_predictor_api/storage/models.py` —
  oba `CheckConstraint` zsynchronizowane z migracją (zweryfikowane
  bajt-po-bajcie skryptem AST). `npm run db:migrate` wykonane lokalnie, bez
  błędu.
- **C — wypełnianie pola:** `resolve_manual_geometry_qualification`
  (`image_geometry_v2.py`) liczy `fully_unavailable_source_cell_indices` i
  zwraca v3 zawsze, gdy `missing` (automatyczne ∪ zadeklarowane) jest
  niepuste. Zweryfikowano wszystkich 8 wywołujących; 3 z nich robiły pełne
  porównanie `resolved != qualification` (integralność „maska operatora
  pokrywa to, co geometria wykrywa automatycznie") — takie porównanie
  zawsze zawodziło po przejściu na v3, bo `resolved.version` różni się od
  wersji wejścia. Naprawione w `services/worker/.../qualified_manual_geometry.py`,
  `services/api/.../image_geometry_v2_repository.py` (porównanie zawężone
  do `unavailable_cell_indices`) — patrz „Not completed"/regresje niżej.
- **D — pipeline workera:** `production_workflow.py`'s `_virtual_renders`
  usunięty redundantny filtr po `unavailableCellIndices` — `derive_virtual_cells`
  (z T1) już poprawnie filtruje po `fully_unavailable_source_cell_indices`
  liczonym na żywo z quada, więc podwójne filtrowanie było nie tylko
  zbędne, ale i błędne (wykluczało też komórki częściowo widoczne, które T1
  miał zacząć renderować). `VirtualCellRender` ma nowe pole
  `partially_visible: bool` (nieczeckowane w `render_spec`, więc bez
  bumpu `VIRTUAL_CELL_RENDER_SPEC_VERSION`); `_virtual_board_payload`
  eksportuje `"partiallyVisible"` per komórka do payloadu `board_crops` —
  gotowe do konsumpcji przez TASK-0627/E.
  `pipeline_execution.py::_available_cell_indices` (walidacja payloadu
  `board_crops`/`symbol_inference`) zaktualizowana: dla `assetMode ==
  "virtual_source"` z kwalifikacją v3 liczy oczekiwaną liczbę komórek z
  `fully_unavailable_cell_indices`, nie z pełnej maski; dla wszystkich
  innych (legacy, brak kwalifikacji, v1/v2) — bez zmian. `assetMode`
  dopisany do payloadu etapu `symbol_inference` (wcześniej go tam nie było,
  więc walidacja nie mogła rozróżnić virtual_source od legacy na tym
  etapie).

### Verification results

```
.venv\Scripts\python.exe -m pytest services/api/tests/test_geometry_qualification.py services/api/tests/test_image_geometry_v2.py services/api/tests/test_image_geometry_v2_persistence.py -q
  → 51 passed
.venv\Scripts\python.exe -m pytest services/worker/tests -q
  → 34 failed (identyczne z `git stash` baseline — lokalny korpus/fixture
    niedostępne, niezwiązane), 1708 passed, 9 skipped
.venv\Scripts\python.exe -m pytest services/api/tests -q --ignore=services/api/tests/integration
  → 21 failed (identyczne z `git stash` baseline, niezwiązane), 1358
    passed, 3 skipped
npm run db:migrate → OK
ruff check <wszystkie zmienione pliki> → czysto
npm run python:typecheck → 69 błędów, identyczny zestaw plików jak przed
  zmianami (żaden z dotkniętych przeze mnie plików); 1 nowy błąd
  (geometry_qualification.py:159, arg-type) naprawiony castem.
```

Odkryto i naprawiono podczas weryfikacji (regresje **T1**, nie T2 — testy
nigdy nie zostały zaktualizowane po zmianie zachowania
`derive_virtual_cells` w v0.10.392, więc cicho fałszywie „przechodziły" na
starym, teraz nieaktualnym zachowaniu):
- `test_manual_partial_geometry.py::test_missing_cells_keep_indices_and_never_render`
  (5 wariantów) — asercja zakładała, że KAŻDA zamaskowana komórka jest
  wykluczona; T1 celowo to zmienił dla komórek częściowo widocznych.
  Przemianowany na `test_partially_visible_cells_render_but_fully_outside_cells_never_do`,
  asercje liczone z `fully_unavailable_source_cell_indices`.
- `test_structured_lattice_refinement_v4.py::test_only_available_cells_render_after_manual_confirmation`
  (3 warianty) — ten sam wzorzec; dodatkowo ujawnił odrębny, wąski,
  przedT2-owy brak w rendererze T1: komórka 0 (róg 0,0) po 8% paddingu
  outward traci całe realne wsparcie mimo że surowy quad miał 1 róg w
  kadrze — `_require_partial_source_support` poprawnie to odrzuca (to
  zamierzony bezpiecznik T1, nie błąd), test to teraz jawnie dokumentuje
  zamiast cicho nie sprawdzać.
- `test_production_image_workflow.py::test_qualified_manual_page_keeps_all_slots_without_detector_or_missing_pixel_inference`
  — przepisany na liczenie oczekiwanych masek z rzeczywistych funkcji
  domenowych zamiast twardych literałów, bo geometria testu (mały
  przesunięty quad) nigdy nie dawała w pełni niedostępnych komórek.

### Not completed

- Sekcje E, F, G — wydzielone do
  `ai_docs/tasks/0627-partial-visibility-review-cell-reconciliation.md`
  (osobne polecenie użytkownika po ujawnieniu, że zakres jest ~3x większy
  niż tu założono — patrz ten plik dla szczegółów).

### Documentation updates

- `ai_docs/process/DECISION_LOG.md`: D-435.
- `ai_docs/process/CURRENT_STATE.md`: nowy wpis TASK-0626.
- `ai_docs/requirements/IMAGE_INGESTION.md`: brak zmian — A–D nie zmienia
  udokumentowanego kontraktu „niepełnej planszy" widocznego przez API/UI
  (v3 jest wyłącznie wewnętrznym wzbogaceniem backendu); D-434 pozostaje
  aktualnym opisem korekty TASK-0505–0509.

### Recommended next task

- `ai_docs/tasks/0627-partial-visibility-review-cell-reconciliation.md`
  (sekcje E/F/G, poprawiony zakres: nowa kolumna + migracja na
  `CellObservationModel`, 9 niezależnych miejsc do synchronizacji zamiast
  3).

- ...
