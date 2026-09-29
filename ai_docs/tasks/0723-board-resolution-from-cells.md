# TASK-0723 — Rozstrzygnięcie planszy wyłącznie z komórek

## Status

todo

## Goal

Plansza z kompletem zweryfikowanych komórek, pełną widocznością i
jednoznaczną sekwencją domyka się automatycznie bez zatwierdzenia geometrii,
a automatyczne przecięcie nie dotyka plansz z decyzją człowieka.

## Context

`derive_symbol_cell_board_resolution(geometry_approved=...)` wymaga
`approved_geometry_revision == geometry_revision` (B3); 361 813 plansz gry `7`
nie ma tej akceptacji. `pending_grid_reinference` chroni plansze tylko przez
`approved_geometry_revision IS NULL` (B6). D-462 R2, R9.

## Dependencies / entry conditions

TASK-0722 done (projekcja synchronizowana po mutacji).

## Recommended execution

claude-opus-5-5, high — zmiana bramki domenowej wpływa na layouty i snapshot.
Audyt: claude-opus-5-5, high.

## Relevant docs

- `AGENTS.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md` D-462, D-451
- `ai_docs/requirements/ADMIN_APP.md` (Weryfikacja symboli)
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/delivery/CELL_LEVEL_VERIFICATION_EXECUTION_PLAN.md`

## Scope

- Usunięcie parametru `geometry_approved` z
  `derive_symbol_cell_board_resolution` i z dwóch wywołań repozytorium.
  `pending_partial`, widoczność i sekwencja pozostają warunkami.
- Reguła R10: komórka `approved`, której zatwierdzone piksele różnią się od
  bieżących (definicja jak w TASK-0722), nie domyka planszy.
- Ochrona `pending_grid_reinference` w `_run_v1` i `_run_v2`: pomijanie plansz
  z jakąkolwiek decyzją człowieka w komórkach (`approved`, `grid_issue`,
  źródło `human`/`board_decision`), także przy ponownej walidacji snapshotu
  przed zapisem.
- Aktualizacja wymagań i modelu danych.

## Out of scope

- Usunięcie endpointów szybkiej akceptacji siatki (TASK-0727).
- Domknięcie istniejących plansz 15/15 (TASK-0728).
- Zmiana kalibracji geometrii.

## Acceptance criteria

- [ ] 15/15 zatwierdzonych komórek bez zatwierdzonej geometrii → plansza
      `accepted`/`corrected`, wiersz kanoniczny i staging layoutu (scenariusz 7).
- [ ] `pending_partial` nadal nie domyka się jako pełny layout.
- [ ] 15 komórek `approved`, z czego jedna ma inne zatwierdzone piksele niż
      bieżące → brak domknięcia; inna rewizja przy tych samych pikselach →
      domknięcie.
- [ ] Reinferencja siatki (v1 i v2) pomija planszę z decyzją człowieka na
      komórce.
- [ ] Istniejąca szybka akceptacja geometrii nadal działa technicznie, ale nie
      jest wymagana.
- [ ] Testy domeny, integracyjny PostgreSQL, lint, mypy.

## Technical notes

`derive_symbol_cell_board_resolution` traci parametr `geometry_approved`;
warunek `completeness_status != "pending_partial"` pozostaje w istniejących
sprawdzeniach wywołujących (`synchronize_board_from_cells` już zwraca `False`
dla `pending_partial`; w `apply_board_mutations` warunek przenieść jawnie).
Domena dodatkowo wymaga, aby zatwierdzone piksele każdej komórki były
bieżącymi (porównanie checksum pikseli, nie `crop_approval_state`, bo ten
uwzględnia rewizję geometrii). `SymbolCellReview` nie niesie checksum renderu,
więc repozytorium liczy `symbol_cell_approval_pixels_changed` (TASK-0722) z
wiersza komórki i przekazuje wynik do domeny jako jawne pole lub zbiór
indeksów.
Ochrona reinferencji: warunek SQL `NOT EXISTS` na
`image_symbol_review_cells` bieżącej planszy z decyzją człowieka oraz ten sam
warunek w walidacji snapshotu (`pending_grid_reinference.py`).

## Expected files

- `services/api/src/game_predictor_api/domain/image_symbol_reviews.py` —
  `derive_symbol_cell_board_resolution`.
- `services/api/src/game_predictor_api/storage/image_symbol_review_repository.py`
  — `apply_board_mutations`, `synchronize_board_from_cells`.
- `services/worker/src/game_predictor_worker/images/pending_grid_reinference.py`.
- Testy domeny, workera i integracyjny.

## Test cases

- Domena: 15 zatwierdzonych, geometria niezatwierdzona → rozstrzygnięcie.
- Integracja: zatwierdzenie 15 komórek bez `approve_current_geometry` →
  `corrected`, kanoniczny wiersz, staging.
- Worker: plansza z jedną komórką `approved` nie jest kandydatem reinferencji
  v1 ani v2.
- Integracja: `approve_current_geometry` pozostaje możliwe, ale plansza bez
  niego też się domyka.

## Verification

Katalog: root repozytorium; każdy krok z timeoutem 120 s.

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_image_symbol_reviews_domain.py -q
.\.venv\Scripts\python.exe -m pytest services/worker/tests -k "grid_reinference" -q
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_verified_cell_search_projection.py -q
npm run python:lint
npm run python:typecheck
```

## Risks / open questions

- Więcej plansz trafi do layoutów bez akceptacji siatki — zamierzone (D-462).
- A4 planu (reset komórek przy ponownym otwarciu z walidacji ciągłości) poza
  zakresem.

## Outcome

Wypełnia agent po pracy.
