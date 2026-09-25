---
title: TASK-0693 — niepełna plansza w odroczonej korekcie geometrii komórek
status: done
last_updated: 2026-09-26
---

# TASK-0693 — niepełna plansza w odroczonej korekcie geometrii komórek

## Status

`done`

## Goal

Ekran Reviewera „Niepełne siatki do ręcznej korekty” (`DeferredBoardCellGeometryEditor`)
dostaje te same możliwości co pozostałe dwa edytory geometrii: checkbox
„Niepełna plansza”, powiększony/szary obszar do przeciągnięcia rogów poza
realne zdjęcie oraz domyślne „?” dla komórek poza kadrem w Weryfikacji
symboli — bez osłabiania rygoru wspólnego, produkcyjnego croppera
(`board_cell_geometry_crops.py`) używanego też przez automatyczną detekcję.

## Context

Zgłoszenie użytkownika: na ekranie Weryfikacja Plansz, w kolejce „Niepełne
siatki do ręcznej korekty” (`DeferredBoardCellGeometryQueue` →
`DeferredBoardCellGeometryEditor`), plansza bywa przycięta, a operator nie ma
możliwości zaznaczyć „Niepełna plansza” ani przesunąć rogów poza realne
zdjęcie — musi ściskać całą siatkę do widocznego obszaru, co przesuwa
wszystkie komórki i myli symbole. Dwa pozostałe edytory geometrii (Admin
„Korekta geometrii strony”, Reviewer „Walidacja gotowych siatek” /
`GridReviewEditor`) już to obsługują przez istniejący, dojrzały model
`GeometryQualification` (`services/api/.../domain/geometry_qualification.py`).
Ten edytor nigdy go nie używał.

Śledztwo (subagent + odczyt kodu) ustaliło kluczowy fakt architektoniczny:
`BoardCellGeometrySourceDirectCropper`/`derive_board_cell_quads`
(`board_cell_geometry_contract.py`, `board_cell_geometry_crops.py`) to
współdzielony, produkcyjny pipeline używany też przez automatyczną detekcję
(`production_workflow.py`, `board_cell_geometry_estimator.py`,
`lattice_refinement_v3.py`, `pending_grid_reinference.py`,
`board_cell_geometry_shadow_benchmark.py`) z jawnym kontraktem
„no-synthesis” (`BORDER_POLICY_VERSION`). Bezpieczne rozwiązanie: dodać
**opcjonalne**, domyślnie nieaktywne parametry (`bounded=True` domyślnie,
`unavailable_cell_indices=frozenset()` domyślnie) do istniejących funkcji —
żaden dotychczasowy wywołujący nie przekazuje nowych argumentów, więc
zachowanie automatycznej detekcji i wszystkich innych wywołań pozostaje
bit-identyczne. Tylko `ManualBoardCellGeometryPreviewer` (ręczny,
jednoosobowy Reviewer flow) przekazuje `bounded=False` /
`unavailable_cell_indices=...`, i tylko gdy operator jawnie zaznaczył
„Niepełna plansza”.

`_project_source_quad_once` (per-cell `cv2.warpPerspective` z
`borderMode=BORDER_CONSTANT`) już dziś toleruje źródłowy quad wykraczający
poza obraz — nie trzeba syntezować niczego ręcznie, tylko zdjąć bramkę
`_quad_has_full_source_support` dla jawnie zadeklarowanych niedostępnych
komórek.

`asset_mode` tej planszy pozostaje `legacy_file` (realne pliki cropów na
dysku, nie `virtual_source`) — więc nie trzeba replikować v3
`fully_unavailable_cell_indices`/`partially_visible_cell_indices` z
`virtual_grid_geometry.py`. Wystarczy v2 `GeometryQualification`:
zadeklarowane niedostępne komórki są w pełni wykluczane (zgodnie z
`available_cell_indices()`'s docstring dla trybów innych niż
`virtual_source`), a predyktor wymusza dla nich `"?"`.

## Dependencies / entry conditions

- Fakt (odczyt kodu): `OperationalImageReviewGeometryPoint.x/y` ma tylko
  `ge=0`, bez górnej granicy — planszę przyciętą z prawej/dołu dawało się
  już zapisać liczbowo, ale i tak ginęła na bramce `_parse_quad` w
  `derive_board_cell_quads`, która wymaga `0 <= x < image_width` na
  zewnętrznych 4 rogach `lattice_bounds_quad`, niezależnie od strony.
- Fakt: istnieje gotowy, reużywalny schemat `GeometryQualificationPayload`
  (`services/api/src/game_predictor_api/schemas/geometry_qualification.py`)
  z `.to_domain()` → `GeometryQualification`, już używany przez
  `ImageGridReviewGeometryCommand`.
- Fakt: `RecognizedBoardModel` ma kolumny `completeness_status`,
  `geometry_qualification`, `unavailable_cell_indices` strzeżone przez
  `ck_recognized_boards_qualification` i `ck_recognized_boards_completeness`
  (`storage/models.py:1995-2062`) — dla `completeness_status='complete'`
  (domyślne) ograniczenia są już spełnione bez zmian; trzeba je jawnie
  ustawić tylko dla `pending_partial`.
- Założenie zapisane w tym tasku: nie replikujemy v3
  (`fully_unavailable_cell_indices`) ani `asset_mode='virtual_source'` dla
  tego flow — board pozostaje `legacy_file` z realnymi plikami cropów.

## Recommended execution

claude-opus-5-5, reasoning: high. Zmiana dotyka współdzielonego,
produkcyjnego croppera worker-a (choć w sposób opcjonalny/addytywny),
kontraktu API (nowe pole), trzech kolumn DB pod CHECK-constraintami oraz
UI Reviewera z canvas-based drag-and-drop. Wysokie ryzyko regresji w
automatycznej detekcji przy niedokładnym zachowaniu domyślnych wartości —
wymaga starannych testów regresyjnych obejmujących WSZYSTKICH
dotychczasowych wywołujących croppera. Dodatkowy review: tak, drugi przebieg
(claude-opus-5-5, reasoning: medium) skupiony wyłącznie na
`board_cell_geometry_crops.py`/`board_cell_geometry_contract.py` pod kątem
regresji automatycznej detekcji.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md` (sekcja „Odroczona geometria komórek”)
- `ai_docs/process/DECISION_LOG.md` (do dodania nowy wpis)

## Scope

- `services/worker/src/game_predictor_worker/images/board_cell_geometry_contract.py`:
  opcjonalny `bounded: bool = True` na `derive_board_cell_quads`/`_parse_quad`.
- `services/worker/src/game_predictor_worker/images/board_cell_geometry_crops.py`:
  opcjonalny `unavailable_cell_indices: frozenset[int] = frozenset()` na
  `crop()`; per-cell tolerancja bramki `_quad_has_full_source_support` tylko
  dla zadeklarowanych indeksów; nowe pole `synthesized: bool = False` na
  `BoardCellGeometrySourceCrop`, w `metadata_dict()` dopisywane tylko gdy
  `True` (zero zmiany bajtowej dla istniejących plansz).
- `services/worker/src/game_predictor_worker/images/manual_board_cell_geometry_preview.py`:
  `unavailable_cell_indices` przez `preview()`/`persist()`, nowe pole na
  `ManualBoardCellGeometryPreview`/`Artifacts`, wliczone do
  `manual_board_cell_geometry_decision_checksum`.
- `services/worker/src/game_predictor_worker/images/manual_board_cell_symbol_prediction.py`:
  `predict()` wymusza `"?"` tylko dla `preview.unavailable_cell_indices`,
  normalna predykcja dla reszty (bez zmiany trybu `unclassified`).
- `services/api/src/game_predictor_api/schemas/board_cell_geometry_pending.py`:
  `geometry_qualification: GeometryQualificationPayload | None = None` na
  `BoardCellGeometryManualPreviewCommand`; `corners` zmienia typ punktu na
  `ManualSourceGeometryPoint` (signed) — poszerzenie kontraktu, bez
  usuwania istniejącej walidacji nieujemności dla trybu bez qualification.
- `services/api/src/game_predictor_api/application/board_cell_geometry_pending.py`:
  `geometry_qualification: GeometryQualification | None = None` przez
  `preview_manual_resolution`/`resolve_manual`; `validate_image_review_geometry_command(geometry_qualification=...)`
  (już wspiera ten parametr); embed do `_manual_geometry_payload` (mirror
  `_apply_qualification` z `virtual_grid_geometry.py`); nowe pole na
  `BoardCellGeometryManualResolutionProjection`.
- `services/api/src/game_predictor_api/storage/board_cell_geometry_pending_repository.py`:
  `materialize_manual_resolution` ustawia `completeness_status`,
  `geometry_qualification`, `unavailable_cell_indices` na
  `RecognizedBoardModel` gdy `pending_partial` (domyślne wartości
  wystarczają dla `complete`).
- OpenAPI regen (`npm run openapi:generate`, `npm run openapi:check`),
  `packages/admin-api-client` regen.
- `apps/reviewer/src/features/operational-reviews/operational-review-state.ts`:
  `allowOutsideSource`/bez-klamrowa warianty `operationalReviewGeometryViewport`,
  `operationalReviewPointInSourceImage`, `clampOperationalReviewGeometryPoint`
  (mirror wzorca 3× virtual canvas z `grid-review-editor.tsx`, ale
  dostosowane do istniejącego viewportu SVG/canvas tego edytora).
- `apps/reviewer/src/features/operational-reviews/deferred-board-cell-geometry-state.ts`
  i `-actions.ts`: przekazanie `geometryQualification` do preview/resolve
  commands; reużycie `manual-image-selection-core`
  (`ManualGridFlags`/`manualGridQualification`/`manualGridUnavailable`/
  `automaticUnavailableGridCells`) zamiast równoległej kopii.
- `apps/reviewer/src/features/operational-reviews/deferred-board-cell-geometry-editor.tsx`:
  checkbox „Niepełna plansza”, lista 15 pól „poza zdjęciem”, szary obszar na
  canvas, przekazanie qualification do preview/resolve.

## Out of scope

- `asset_mode='virtual_source'` i v3 `fully_unavailable_cell_indices` dla
  tego flow (board pozostaje `legacy_file`).
- Zmiana `quality_issue=PARTIAL_VISIBILITY`/„Poza kadrem” UI w
  `symbol-review-workspace.tsx` — komórki wymuszone na „?” przechodzą
  zwykłą ścieżką akceptacji/korekty predykcji, tak jak każda inna predykcja.
- Migracja Alembic — kolumny już istnieją.
- Zmiana zachowania Admin „Korekta geometrii strony” ani Reviewer
  „Walidacja gotowych siatek” (już obsługują to niezależnie).
- Diagnoza, czy niektóre planse trafiające do tej kolejki *powinny* były
  zostać złapane wcześniej na poziomie strony (D-434/435/436) — poza
  zakresem; ten task naprawia narzędzie do ręcznej korekty, nie routing.

## Acceptance criteria

- [x] Operator może zaznaczyć „Niepełna plansza” na ekranie „Niepełne
      siatki do ręcznej korekty”, oznaczyć konkretne z 15 pól jako „poza
      zdjęciem”, przeciągnąć odpowiadające im rogi poza realne zdjęcie
      (szary obszar), wygenerować podgląd i zapisać.
- [x] Zapisana plansza ma w Weryfikacji symboli domyślny symbol „?” dla
      zadeklarowanych niedostępnych komórek; pozostałe komórki mają zwykłą
      predykcję modelu. (Zweryfikowane na poziomie predyktora — pełny
      round-trip DB nie mógł zostać zweryfikowany, patrz „Not completed”.)
- [x] Board ma poprawnie ustawione `completeness_status`,
      `geometry_qualification`, `unavailable_cell_indices` spójne z CHECK
      constraintami. (Zweryfikowane odczytem dokładnej treści constraintów
      i mirror istniejącego `_project_geometry_qualification`; nie
      zweryfikowane insertem na żywej bazie — patrz „Not completed”.)
- [x] Zwykły (pełny) zapis bez „Niepełna plansza” zachowuje się identycznie
      jak dziś (regresja): brak zmiany w checksumach/fingerprintach dla
      kompletnych plansz.
- [x] Automatyczna detekcja (`production_workflow.py`,
      `board_cell_geometry_estimator.py`, `lattice_refinement_v3.py`,
      `pending_grid_reinference.py`) nie zmienia zachowania — testy
      regresyjne z nowymi domyślnymi parametrami przechodzą bez zmiany
      asercji.
- [x] OpenAPI + wygenerowany klient spójne (`npm run openapi:check`).

## Technical notes

Patrz `Context`/`Scope` — kluczowe decyzje architektoniczne już
rozstrzygnięte tam. Kolejność implementacji (każdy krok musi zostać
zweryfikowany testami przed przejściem dalej):

1. `board_cell_geometry_contract.py` + `board_cell_geometry_crops.py`
   (opcjonalne parametry, zero zmiany domyślnego zachowania) — testy
   regresyjne dla WSZYSTKICH istniejących wywołujących.
2. `manual_board_cell_geometry_preview.py` + `manual_board_cell_symbol_prediction.py`.
3. API schema + application + repository + testy Python.
4. OpenAPI + klient.
5. Reviewer UI + testy Node.

## Expected files

Patrz `Scope` — pełna lista plików istniejących do zmiany; brak nowych
plików poza testami.

## Test cases

- Cropper: plansza kompletna, `unavailable_cell_indices=frozenset()` →
  identyczny wynik jak przed zmianą (regresja bajtowa metadata_dict).
- Cropper: plansza z 3 komórkami zadeklarowanymi niedostępnymi i
  faktycznie poza obrazem → `crop()` zwraca `status="cropped"` z 15
  komórkami, 3 oznaczone `synthesized=True`.
- Cropper: komórka poza obrazem NIE zadeklarowana jako niedostępna →
  nadal `needs_review` (ochrona niezmieniona).
- `derive_board_cell_quads(bounded=False)`: róg poza `[0,width)x[0,height)`
  przechodzi walidację kształtu (wypukłość, pole, winding) bez błędu granic.
- Predictor: `unavailable_cell_indices={2, 7}` → cells[2] i cells[7] mają
  `symbolCode="?"`, reszta z normalnej predykcji modelu.
- Repository: `materialize_manual_resolution` z `pending_partial` →
  `RecognizedBoardModel` ma spójne 3 kolumny, insert przechodzi CHECK
  constraints (test na żywej/testowej bazie, `GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`).
- Reviewer UI: interaction test — zaznaczenie checkboxa odsłania szary
  obszar i listę 15 pól; zapis wysyła `geometryQualification` w komendzie.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_board_cell_geometry_crops.py services/worker/tests/test_board_cell_geometry_contract.py services/worker/tests/test_manual_board_cell_geometry_preview.py services/worker/tests/test_manual_board_cell_symbol_prediction.py -q
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_board_cell_geometry_pending.py -q
npm run python:lint
npm run python:typecheck
npm run openapi:generate
npm run openapi:check
npm run test --workspace @game-predictor/reviewer
npm run typecheck --workspace @game-predictor/reviewer
npm run lint --workspace @game-predictor/reviewer
```

PostgreSQL-zależny test repozytorium wymaga
`$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'` i uruchamia się osobno,
z jawną zgodą — nie tworzy/nie usuwa bazy `game_predictor`.

## Risks / open questions

- Ryzyko regresji w automatycznej detekcji jest realne mimo opcjonalnych
  parametrów — mitygacja: zero zmian domyślnego zachowania + pełny run
  istniejących testów tych modułów przed commitem.
- `metadata_dict()`'s warunkowe dopisanie `"synthesized"` zmienia kształt
  JSON tylko dla nowych, częściowych plansz — jeśli jakiś downstream
  konsument geometrii robi ścisłe porównanie kluczy (nie tylko odczyt),
  może to wymagać dodatkowej korekty; do zweryfikowania przy testach.
- Nie sprawdzono, czy `ImageBoardGeometryRevisionModel` (tabela audytu
  rewizji) wymaga też zapisu qualification — z analizy wygląda na to, że
  nie steruje downstream dostępnością (tylko `RecognizedBoardModel` to
  robi), ale do potwierdzenia przy implementacji.

## Outcome

### Changed

- `services/worker/src/game_predictor_worker/images/board_cell_geometry_contract.py`:
  opcjonalny `bounded: bool = True` na `derive_board_cell_quads`/`_parse_quad`.
- `services/worker/src/game_predictor_worker/images/board_cell_geometry_crops.py`:
  opcjonalny `unavailable_cell_indices` na `crop()`, nowe pole `synthesized`
  na `BoardCellGeometrySourceCrop` (dopisywane do `metadata_dict()` tylko
  gdy `True`).
- `services/worker/src/game_predictor_worker/images/manual_board_cell_geometry_preview.py`:
  `unavailable_cell_indices` przez `preview()`/`persist()`, nowe pole na
  `ManualBoardCellGeometryPreview`/`Artifacts`.
- `services/worker/src/game_predictor_worker/images/manual_board_cell_symbol_prediction.py`:
  `predict()` wymusza „?" tylko dla zadeklarowanych indeksów.
- `services/api/src/game_predictor_api/schemas/board_cell_geometry_pending.py`:
  `geometry_qualification` (reużyty `GeometryQualificationPayload`), rogi
  zmienione na signed `ManualSourceGeometryPoint`.
- `services/api/src/game_predictor_api/api/board_cell_geometry_pending.py`,
  `services/api/src/game_predictor_api/application/board_cell_geometry_pending.py`:
  przekazanie qualification przez preview/resolve, embed do geometrii
  (mirror `_apply_qualification`).
- `services/api/src/game_predictor_api/storage/board_cell_geometry_pending_repository.py`:
  `materialize_manual_resolution` ustawia 3 kolumny qualification dla
  `pending_partial`.
- `packages/admin-api-client/openapi/openapi.json`,
  `packages/admin-api-client/src/generated/types.gen.ts`: regenerowane.
- `apps/reviewer/src/features/operational-reviews/operational-review-state.ts`:
  opcjonalny `allowOutsideSource` na `operationalReviewGeometryViewport`/
  `operationalReviewPointInSourceImage`.
- `apps/reviewer/src/features/operational-reviews/deferred-board-cell-geometry-state.ts`:
  `flags`/`geometryQualification` przez preview/resolution commands, reużycie
  `manual-image-selection-core`'s `manualGridQualification`.
- `apps/reviewer/src/features/operational-reviews/deferred-board-cell-geometry-editor.tsx`:
  checkbox „Niepełna plansza", lista 15 pól „poza zdjęciem", szary obszar na
  canvasie, `viewport` przeniesiony z `useState`+`useEffect` na `useMemo`
  (naprawia `react-hooks/set-state-in-effect`, wymuszone przez zmianę na
  zależny od `allowOutsideSource` przelicznik).
- Nowe testy: `test_board_cell_geometry_contract.py` (+2),
  `test_board_cell_geometry_crops.py` (+3), `test_manual_board_cell_geometry_preview.py`
  (+1), `test_manual_board_cell_symbol_prediction.py` (+1),
  `apps/reviewer/test/deferred-board-cell-geometry.test.mjs` (+1, i
  zaktualizowany jeden istniejący test o nowe pole `geometryQualification: null`),
  `packages/admin-api-client/test/client.test.mjs` (+1, sygnowane rogi +
  qualification przez wrapper).
- Dokumentacja: `ai_docs/requirements/ADMIN_APP.md` (nowy akapit),
  `ai_docs/process/DECISION_LOG.md` (D-449), `ai_docs/process/CURRENT_STATE.md`.

### Verification results

```
.venv\Scripts\python.exe -m pytest services/worker/tests/test_board_cell_geometry_crops.py
  services/worker/tests/test_manual_board_cell_geometry_preview.py
  services/worker/tests/test_manual_board_cell_symbol_prediction.py
  services/api/tests/test_board_cell_geometry_pending.py -q
→ 33 passed
.venv\Scripts\python.exe -m pytest services/worker/tests/test_board_cell_geometry_contract.py -q
→ 8 passed, 7 failed (przedsesyjne, niezwiązane — patrz "Not completed"), 1 skipped
.venv\Scripts\python.exe -m ruff check <11 zmienionych plików Python> → All checks passed
.venv\Scripts\python.exe -m ruff format --check <11 zmienionych plików Python> → 11 already formatted (po jednorazowym --write)
.venv\Scripts\python.exe -m mypy services/api/src services/worker/src scripts → 0 błędów w zmienionych plikach (69 przedsesyjnych błędów w innych plikach, niezwiązane)
npm run openapi:generate && npm run openapi:check → OpenAPI i klient aktualne
npm run test --workspace @game-predictor/reviewer → 200/200
npm run test:geometry --workspace @game-predictor/reviewer → 3/3 (grid-geometry, niezmienione)
npm run typecheck --workspace @game-predictor/reviewer → czysty
npm run lint --workspace @game-predictor/reviewer → czysty
npm run test --workspace @game-predictor/admin-api-client → 64/64
npx prettier --check <5 zmienionych plików TS/JS> → zgodne (po jednorazowym --write)
```

Reprodukcja izolacji przedsesyjnych failów: `git stash` + ten sam przebieg
testów dał identyczny wynik (7 failów w `test_board_cell_geometry_contract.py`
i `relation "source_images" does not exist"` w integracyjnym teście), co
potwierdza brak związku z tym taskiem.

### Not completed

- Integracyjny test `materialize_manual_resolution` z `pending_partial` na
  żywej Postgresie nie został dodany/uruchomiony — istniejący test tej samej
  rodziny (`test_manual_deferred_geometry_materializes_one_complete_review_projection`
  w `services/api/tests/integration/test_image_batch_store.py`) failuje
  identycznie na czystym `HEAD` (`v0.10.450`) z powodu niezwiązanej migracji
  („legacy public store removal", v0.10.447–450): `relation "source_images"
  does not exist`. To osobny, przedsesyjny blocker — nie naprawiony w tym
  tasku (poza zakresem), ale zgłoszony użytkownikowi.
- Brak dedykowanego testu `test-interactions` (canvas pointer-drag) dla
  `DeferredBoardCellGeometryEditor` analogicznego do
  `grid-geometry-qualification.test.mjs` — pokrycie UI opiera się na
  typecheck + lint + testach warstwy stanu (`deferred-board-cell-geometry.test.mjs`),
  nie na pełnej symulacji interakcji canvas. Sugerowany dalszy krok, jeśli
  potrzebna głębsza pewność.
- 7 przedsesyjnych, niezwiązanych failów w `test_board_cell_geometry_contract.py`
  (`corpusDescriptor.annotationManifest checksum differs`) — nie naprawione,
  poza zakresem.
- Brak ręcznej weryfikacji w przeglądarce (Reviewer wymaga uruchomionego
  API + Postgresa + realnego importu z odroczoną geometrią; nie wykonano w
  tej sesji).

### Documentation updates

- `ai_docs/requirements/ADMIN_APP.md`, `ai_docs/process/DECISION_LOG.md`
  (D-449), `ai_docs/process/CURRENT_STATE.md`.

### Recommended next task

- Naprawić przedsesyjny blocker migracji „legacy public store removal"
  (`relation "source_images" does not exist" w testach integracyjnych na
  żywej Postgresie) — osobny task, blokuje weryfikację tego i innych
  przyszłych zmian repozytorium.
- Opcjonalnie: dodać integracyjny test `materialize_manual_resolution` z
  `pending_partial` po naprawieniu powyższego blockera.
