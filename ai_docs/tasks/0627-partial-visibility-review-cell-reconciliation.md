---
title: TASK-0627 — wymuszony „nierozpoznany" dla częściowo widocznych komórek (T2, sekcje E–G)
status: todo
last_updated: 2026-09-23
---

# TASK-0627 — wymuszony „nierozpoznany" dla częściowo widocznych komórek (T2, sekcje E–G)

## Status

`todo`

## Goal

Komórka oznaczona jako `partially_visible` (T1: TASK-0625; T2/A–D:
TASK-0626) trafia do Weryfikacji symboli jako wymuszony „nierozpoznany"
(`assignedSymbolId = null`, niezależnie od predykcji modelu), nigdy
automatycznie klasyfikowana, trwale wykluczona z treningu — i przeżywa
każdą rekoncylację (korektę geometrii, ponowne otwarcie planszy, backfill)
bez błędu integralności, na WSZYSTKICH ścieżkach kodu, nie tylko na
ścieżce świeżego importu.

## Context

TASK-0625 (T1, `v0.10.392`) dodał zdolność techniczną: `derive_virtual_cells`
renderuje komórki z 1–3 rogami poza kadrem zamiast całkowicie je wykluczać.
TASK-0626 (T2/A–D, `v0.10.393`) podłączył to do `production_workflow.py`
(crop generation), dodał `GeometryQualification` v3 z polem
`fully_unavailable_cell_indices` (podzbiór `unavailable_cell_indices`,
policzony raz z rzeczywistej geometrii przez
`resolve_manual_geometry_qualification`, persystowany) i przeprowadził
migrację CHECK CONSTRAINT na `recognized_boards`/
`image_import_geometry_guard_decisions`.

**Ten plik zastępuje pierwotne sekcje E/F z TASK-0626.** Research
przeprowadzony podczas próby implementacji E/F w ramach TASK-0626 ujawnił,
że pierwotny plan (3 miejsca: `production_workflow.py` — już naprawione w
TASK-0626 — plus `_synchronize` i `_virtual_current_cells_from_records`)
poważnie nie doszacował zakresu. Rzeczywisty inwentarz niezależnych miejsc
kodujących „unavailable_cell_indices = w pełni wykluczone" (czyli
wymagających tej samej korekty na `fully_unavailable_cell_indices`, z
fallbackiem do pełnej maski dla V1/V2):

1. `services/api/src/game_predictor_api/storage/image_symbol_review_repository.py`
   `_synchronize` (ok. l. 2176-2178): `expected_cell_indices =
   set(range(topology.cell_count)) - set(board.unavailable_cell_indices)`.
   **Główna ścieżka tworzenia i rekoncyliacji `ImageSymbolReviewCellModel`
   — tu też trafia sekcja E (wymuszony null).**
2. Tamże, ok. l. 1571-1580: `expected_indices = set(range(topology.cell_count))
   - set(board.unavailable_cell_indices)` w zapytaniu szczegółów planszy
   nieczytelnej (`SYMBOL_CELL_REVIEW_PROJECTION_INCOMPLETE`).
3. Tamże, ok. l. 4207-4210 (`_selected_items_without_exactly_fifteen_cells`):
   czyste SQL `expected_count = grid_rows*grid_columns -
   cardinality(unavailable_cell_indices)` — bramka kompletności recenzji.
4. Tamże, ok. l. 4384: `tuple(board.unavailable_cell_indices) ==
   tuple(range(15))` — test „plansza w pełni nieczytelna"; semantyka do
   przemyślenia względem `fully_unavailable_cell_indices`.
5. `services/api/src/game_predictor_api/storage/image_review_repository.py`
   `_virtual_current_cells_from_records` (ok. l. 2664-2712) — jawnie
   udokumentowana jako jedyna implementacja wyboru „aktualnych" 15 komórek
   (Reviewer + backfille); `available_indices` z tego samego wzoru,
   `len(observations) == len(available_indices)` jako twardy warunek.
6. Tamże, `_virtual_geometry_cells` (ok. l. 2858-2860): `expected_indices
   -= set(board.unavailable_cell_indices)`,
   `IMAGE_REVIEW_GEOMETRY_PROJECTION_INVALID` przy niezgodności.
7. `services/api/src/game_predictor_api/storage/virtual_grid_geometry_repository.py`
   (ok. l. 1295-1297) — ten sam wzór, bramkuje czy potrzebne są początkowe
   konfiguracje renderu.
8. `services/worker/src/game_predictor_worker/images/pending_symbol_reinference.py`
   `_available_indices` (def ok. l. 650-658, użycie ok. l. 339-344) —
   `IMAGE_SYMBOL_REINFERENCE_CELLS_INCOMPLETE` przy niezgodności.
9. `services/worker/src/game_predictor_worker/images/pipeline_store.py`
   (ok. l. 1344-1355) — walidacja workera porównująca
   `board.unavailable_cell_indices` z zadeklarowanym `unavailableCellIndices`
   payloadu crop przed zapisem.

**Dodatkowo, w pełni nowy problem nieprzewidziany w TASK-0626:**
`partiallyVisible` (dopisane w TASK-0626/D do payloadu `board_crops` per
komórka, sąsiad `renderSpec`, nie jego pole) **nigdzie nie jest dziś
trwale zapisywane.** `CellObservationModel`
(`services/api/src/game_predictor_api/storage/models.py:2161-2233`) nie ma
kolumny na tę flagę — jej kolumny to: `id, recognized_board_id, row_index,
column_index, asset_mode, source_geometry_revision_id, logical_cell_key,
logical_cell_key_v2, render_identity_v2_sha256, render_spec (JSONB),
render_spec_checksum_sha256, rendered_pixel_checksum_sha256,
extractor_version, crop_relative_path, crop_checksum_sha256,
cropper_version, prediction (JSONB), created_at`. Pierwszy zapis
(`services/worker/src/game_predictor_worker/images/pipeline_store.py`,
`project_recognition` → `_upsert_cell`, ok. l. 324-343, 612-621,
1399-1461) dziś czyta z payloadu crop tylko konkretne, wybiałolistowane
klucze — `partiallyVisible` jest cicho odrzucane. Wymaga to: nowej kolumny
+ migracji Alembic (wzorem `0120_fully_unavailable_cell_qualification.py`)
ORAZ przekazania jej przez `_upsert_cell` i drugiego, łatwego do przeoczenia
zapisywacza — sub-dicta `"virtualCell"` budowanego w `pipeline_store.py`
(ok. l. 1580-1662) dla plansz `board_cell_geometry`/pending-partial.

`ImageReviewCell` (`services/api/src/game_predictor_api/domain/image_reviews.py:72-97`)
też nie ma pola `partially_visible` — ma `render_spec: Mapping[str, object]
| None`, ale `partiallyVisible` to sąsiad `renderSpec` w payloadzie, nie
jego zagnieżdżone pole, więc `render_spec` samo w sobie go nie niesie.
`materialize_current_image_review_cells`/`_virtual_current_cells_from_records`
(`image_review_repository.py`) mają DWA miejsca budujące `ImageReviewCell`
(legacy_file, l. ~2531 — nieistotne, brak render danych; virtual_source,
l. ~2809 — tu trzeba dociągnąć nową kolumnę po jej dodaniu).

**Alternatywa do rozważenia zamiast nowej kolumny:** skoro
`fully_unavailable_cell_indices` jest już trwale zapisane w
`GeometryQualification` v3 na poziomie planszy (nie komórki), można
wyliczać „czy ta konkretna komórka jest partially_visible" w locie jako
`cell_index in unavailable_cell_indices and cell_index not in
fully_unavailable_cell_indices` — bez żadnej nowej kolumny na komórce. To
wymaga tylko, żeby każde z 9 miejsc miało dostęp do obu list z planszy
(zwykle już mają dostęp do `board.unavailable_cell_indices`; potrzebują
też `fully_unavailable_cell_indices` z `board.geometry_qualification`).
**To prawdopodobnie tańsze niż nowa kolumna — zweryfikować jako pierwszy
krok tego taska**, zanim projektuje się migrację.

## Dependencies / entry conditions

- TASK-0625 (T1) i TASK-0626 (T2/A–D) ukończone i zacommitowane.
- Potwierdzone decyzje z wcześniejszego planu: DA-1 (próg 1–3/4 rogów),
  DA-2 (predykcja modelu nadal liczona jako podpowiedź, `assignedSymbolId`
  zawsze `null`), DA-3 (nowa, jawna wartość `quality_issue`/
  `assignmentSource`, nie reużycie `unreadable`), DA-4 (tylko
  `virtual_source`).
- **Nowe, do potwierdzenia z użytkownikiem przed startem:** czy
  `fully_unavailable_cell_indices` z planszy wystarczy (bez nowej kolumny
  na komórce) — patrz „Alternatywa" wyżej — czy jednak potrzebna jest
  osobna, trwała flaga per-komórka (np. jeśli w przyszłości komórka miałaby
  być `partially_visible` niezależnie od aktualnej maski planszy).

## Recommended execution

`claude-sonnet-5`, reasoning `xhigh`. Uzasadnienie: 9 niezależnych miejsc
kodujących tę samą, subtelną granicę dostępności komórki; błąd w
którymkolwiek kończy się realną awarią integralności danych (nie testu) na
produkcyjnych danych przy korekcie geometrii, backfillu lub ponownym
otwarciu planszy. Rozstrzygnięcie „nowa kolumna vs. liczenie w locie" ma
realny wpływ na rozmiar zmiany i wymaga przemyślenia przed kodowaniem.
Dodatkowy review: tak — `claude-opus-5-5` / `xhigh`, review wszystkich 9
miejsc + logiki zapisu (`_synchronize`) przed commitem; ryzyko cichej
niezgodności między miejscami jest wysokie.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md` (D-434, D-435)
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/tasks/completed/0625-partial-visibility-domain-renderer.md`
- `ai_docs/tasks/completed/0626-partial-visibility-pipeline-review.md`
  (sekcje E/F oryginalnego planu — historyczny kontekst, zakres tutaj jest
  poprawiony i rozszerzony)

## Scope

### E. Zapis rekordu recenzji

- `services/api/src/game_predictor_api/domain/image_symbol_reviews.py`:
  nowa wartość `SymbolCellQualityIssue` (DA-3, np. `PARTIAL_VISIBILITY`) i
  nowa wartość `SymbolCellAssignmentSource` (np. `GEOMETRY_PARTIAL`).
- `services/api/src/game_predictor_api/storage/image_symbol_review_repository.py`
  `_synchronize` — w gałęziach tworzenia/domyślnej (`geometry_changed or
  reason == "board_reopened"` i domyślny `else`, ok. l. 2400-2437): gdy
  komórka jest `partiallyVisible`, wymuszony `assigned_symbol_id = None`,
  `quality_issue = PARTIAL_VISIBILITY`, `assignment_source =
  GEOMETRY_PARTIAL`, `review_state = PENDING`; `prediction_symbol_code`/
  `prediction_confidence` nadal zapisane jako podpowiedź (DA-2, już działa
  bez zmian — te pola są ustawiane bezwarunkowo z `review_cell`).
- Trwałe wykluczenie z treningu: potwierdzić testem, że istniejąca bramka
  `is_symbol_cell_training_eligible` (wymaga `quality_issue is None`) już
  wystarcza.

### F. Rekoncyliacja — wszystkie 9 miejsc z sekcji Context

Dla każdego z 9 miejsc: użyć `fully_unavailable_cell_indices` (z
`GeometryQualification` v3 na planszy, jeśli obecna) zamiast pełnej
`unavailable_cell_indices` przy liczeniu „ile/które komórki plansza
powinna mieć"; fallback do dzisiejszego zachowania (pełna maska) dla
V1/V2 lub braku kwalifikacji — bezpieczne, zachowuje dzisiejsze testy dla
historycznych wierszy. Wzorem już zastosowanej poprawki w
`services/worker/src/game_predictor_worker/images/pipeline_execution.py::_available_cell_indices`
(TASK-0626/D) — dodatkowo ograniczonej do `assetMode == "virtual_source"`
(DA-4).

### G. Trwałość `partiallyVisible` (nowy problem, patrz Context)

Rozstrzygnąć „nowa kolumna vs. liczenie w locie z planszy" (patrz
Context), potem zaimplementować wybrane podejście — jeśli nowa kolumna:
migracja Alembic na `CellObservationModel` + `_upsert_cell` +
`"virtualCell"` sub-dict w `pipeline_store.py` + `ImageReviewCell.partially_visible`
+ oba miejsca budujące `ImageReviewCell` w `image_review_repository.py`.

### H. Testy i dokumentacja

- Nowe testy dla wszystkich 9 miejsc z sekcji F (mieszanka w pełni/
  częściowo niedostępnych komórek — porównawczo z i bez `fully_unavailable_cell_indices`).
- `image_symbol_review_repository.py` — `_synchronize` tworzy realny
  rekord z wymuszonym `null`/nowym `quality_issue`/`assignment_source` dla
  komórki `partiallyVisible`.
- `ai_docs/process/DECISION_LOG.md` (nowy wpis), `ai_docs/requirements/IMAGE_INGESTION.md`,
  `ai_docs/process/CURRENT_STATE.md`.

## Out of scope

- T3 (Admin UI — oznaczenie kart w Weryfikacji symboli jako „ramka wychodzi
  poza kadr") — osobne polecenie.
- Backfill istniejących wierszy V1/V2 na V3 lub istniejących
  `CellObservationModel` wierszy na nową kolumnę (jeśli wybrana) —
  świadomie nie wykonywany bez osobnej zgody (AGENTS.md: nigdy nie
  uruchamiaj destrukcyjnych operacji na danych bez wyraźnej zgody).

## Acceptance criteria

- [ ] Rozstrzygnięcie „nowa kolumna vs. liczenie w locie" udokumentowane w
      Outcome z uzasadnieniem.
- [ ] Wszystkie 9 miejsc z sekcji F poprawnie rekoncyliują planszę z
      mieszanką w pełni i częściowo niedostępnych komórek — bez błędu
      integralności — dla wierszy V3; zachowują dzisiejsze zachowanie (i
      dzisiejsze testy) dla V1/V2.
- [ ] Import (worker, `virtual_source`) tworzy realny rekord
      `ImageSymbolReviewCellModel` dla `partially_visible` komórki:
      `assignedSymbolId = null`, `qualityIssue` = nowa wartość,
      `assignmentSource` = nowa wartość, `reviewState = pending`,
      `predictionSymbolCode`/`predictionConfidence` nadal wypełnione.
- [ ] `symbolId=unknown` w Weryfikacji symboli zwraca taką komórkę.
- [ ] `is_symbol_cell_training_eligible` zwraca `False` dla takiej komórki
      nawet po ręcznym przypisaniu symbolu przez operatora.
- [ ] Wszystkie istniejące testy wymienionych plików pozostają zielone bez
      zmiany istniejących asercji (poza jawnie udokumentowanymi
      korektami stale'owych testów, analogicznie do TASK-0626).
- [ ] `ruff`, `mypy` czyste (bez nowych błędów) dla zmienionych plików.

## Technical notes

Kluczowy przykład wejście→wynik (niezmieniony z pierwotnego planu):
plansza V3 z `unavailable_cell_indices=(0,1,5,6,10,11)`,
`fully_unavailable_cell_indices=(0,5,10)` → `expected_cell_indices =
{1,2,3,4,6,7,8,9,11,12,13,14}` (12 elementów, nie 9).

## Expected files

- Istniejące: 9 plików z sekcji Context/F, `image_symbol_reviews.py`,
  `image_symbol_review_repository.py`.
- Nowe: migracja Alembic (tylko jeśli wybrano „nową kolumnę" w sekcji G).

## Test cases

Zob. sekcja Scope H.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_image_symbol_reviews_api.py services/api/tests/test_image_symbol_reviews_domain.py services/api/tests/test_image_symbol_review_query_storage.py services/api/tests/test_virtual_grid_geometry_repository.py services/api/tests/test_reviews.py -q
npm run db:migrate  # tylko jeśli nowa kolumna
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_pending_symbol_reinference.py services/worker/tests -q
.\.venv\Scripts\python.exe -m ruff check <zmienione pliki>
.\.venv\Scripts\python.exe -m mypy <zmienione pliki źródłowe>
```

Timeout 120 s na krok (poza pełnymi przebiegami `pytest services/worker/tests`
i `services/api/tests`, które trwają ok. 3-9 minut — zgłosić jeśli dłuższe).

## Risks / open questions

- 9 niezależnych miejsc oznacza 9 szans na cichą niezgodność — rozważyć,
  czy da się wydzielić jedną, współdzieloną funkcję pomocniczą
  (`available_cell_indices(board) -> frozenset[int]`) w miejscu dostępnym
  zarówno dla `services/api` jak i `services/worker`, zamiast powielać
  logikę 9 razy.
- Jeśli wybrana zostanie nowa kolumna na `CellObservationModel`: migracja
  modyfikuje tabelę już używaną produkcyjnie — sprawdzić czy potrzebny
  `postgresql_not_valid`/`SET NOT NULL` w dwóch krokach czy wystarczy
  nullable + default.

## Outcome

Wypełnia agent po pracy.

### Changed

- ...

### Verification results

- ...

### Not completed

- ...

### Documentation updates

- ...

### Recommended next task

- ...
