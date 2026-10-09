---
title: Pending board quad past the image edge blocks manual correction
status: done
last_updated: 2026-10-09
---

# TASK-0944 — Szkic planszy wychodzący poza krawędź obrazu blokuje ręczną korektę

## Status

`done`

## Goal

Każda plansza odłożona do ręcznej korekty geometrii (`image_board_geometry_pending`),
której wykryty czworokąt wychodzi poza krawędź obrazu w granicach ręcznej edycji,
otwiera się w Reviewerze zamiast błędu `IMAGE_BOARD_CELL_PENDING_DETECTION_INVALID`.

## Context

Zgłoszenie operatora 2026-10-09: w imporcie Mumie
`d82d9aba-d59c-46f7-9ee8-8a7415565e3d` (gra `fea55cc1-…`) Reviewer
(`/?mode=local&gameId=…&importJobId=…`) pokazuje „nie udało się wczytać korekty”
z komunikatem „The pinned board quad is outside the immutable source bounds.”

Diagnoza (odczyt bazy, bez zmian): wszystkie 4 odłożone plansze tego importu
mają `positionIndex = 8` (prawa dolna plansza strony 3×3), a dolne narożniki
wykrytego czworokąta leżą 0,1–1,75 px poniżej obrazu 1520×904. W całej bazie
wszystkie 25 odłożonych plansz (`reason_code = incomplete_lattice`, pozycje 0, 1
i 8) mają narożnik poza obrazem, maksymalnie 56 px. `_validated_detected_board_geometry`
wymagała `0 ≤ x ≤ width`, `0 ≤ y ≤ height`, więc kontekst korekty nie powstawał i
ręczna korekta była niemożliwa dla każdej z nich.

Domena już dopuszcza takie położenie: `SourceQuad.require_manual_edit_bounds` i
`SourceLatticeNodes.require_manual_edit_bounds` przyjmują narożniki do jednej
szerokości i wysokości źródła poza każdą krawędzią, komórki częściowo widoczne
obsługuje D-436, a propozycja sieci (`lattice_cell_quads`) jest walidowana tymi
samymi granicami. Kontekst korekty był jedynym miejscem z ostrzejszą granicą.

## Dependencies / entry conditions

- Fakty: kod gałęzi integracyjnej `v1.1-vision-lab-hybrid-geometry` na `v1.7.285`.
- Brak migracji i zmian danych.

## Recommended execution

Claude Opus 5.5, reasoning medium: mała poprawka walidacji i kontraktu odpowiedzi
w jednym pionie. Task poza planem; brak wiersza `Dodatkowy review`, więc audyt
krzyżowy nie jest wymagany.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md` (D-436)

## Scope

- `_validated_detected_board_geometry` przyjmuje narożniki w granicach ręcznej
  edycji (`-W ≤ x ≤ 2W`, `-H ≤ y ≤ 2H`) zamiast granic obrazu.
- Odpowiedź kontekstu korekty (`board_quad`, `suggested_corners`) używa punktu
  ze znakiem (`ManualSourceGeometryPoint`), aby narożnik nad lub na lewo od
  obrazu nie kończył się błędem serializacji.
- OpenAPI, wygenerowany klient i wrapper klienta (alias typu
  `OperationalImageReviewGeometryPoint` dla Reviewera).

## Out of scope

- Przycinanie szkicu do obrazu (odrzucone: zniekształca planszę i rozjeżdża ją
  z węzłami siatki propozycji).
- Zmiany w zapisie korekty, w detektorze planszy i w danych.

## Acceptance criteria

- [x] Szkic z narożnikiem 1,75 px poniżej obrazu i szkic z narożnikami nad i na
      lewo od obrazu przechodzą walidację kontekstu.
- [x] Narożnik dalej niż jedna szerokość/wysokość źródła nadal daje
      `IMAGE_BOARD_CELL_PENDING_DETECTION_INVALID`.
- [x] Odpowiedź kontekstu serializuje ujemne współrzędne.
- [x] OpenAPI i klient są aktualne; typecheck Reviewera przechodzi.

## Technical notes

Zachowanie chronione: zapis ręcznej korekty waliduje geometrię niezależnie
(`require_manual_edit_bounds`, deklaracja `pending_partial` dla komórek poza
źródłem według D-436). Szkic tylko zasila edytor. Usunięta klasa
`schemas.image_reviews.OperationalImageReviewGeometryPoint` (`x, y ≥ 0`) nie
miała innych użyć; `image_grid_reviews.py` już wcześniej używał pod tą nazwą
punktu ze znakiem.

## Expected files

- `services/api/src/game_predictor_api/storage/board_cell_geometry_pending_repository.py` (`_validated_detected_board_geometry`)
- `services/api/src/game_predictor_api/schemas/board_cell_geometry_pending.py` (`BoardCellGeometryCorrectionContextResponse`, `_quad`)
- `services/api/src/game_predictor_api/schemas/image_reviews.py` (usunięcie nieużywanej klasy)
- `services/api/tests/test_board_cell_geometry_pending.py`
- `packages/admin-api-client/openapi/openapi.json`, `packages/admin-api-client/src/generated/types.gen.ts`, `packages/admin-api-client/src/index.ts`

## Test cases

- Przypadek ze zgłoszenia (pozycja 8, y = 905,75 przy wysokości 904) → szkic przyjęty.
- Narożniki ujemne (−40, −56,2) → szkic przyjęty, odpowiedź zachowuje (−40, −56).
- x = −1521 albo y = 1809 przy 1520×904 → `IMAGE_BOARD_CELL_PENDING_DETECTION_INVALID`.

## Verification

```powershell
# z worktree, PYTHONPATH na services/api/src i services/worker/src, timeout 120 s
..\..\.venv\Scripts\python.exe -m pytest services/api/tests/test_board_cell_geometry_pending.py -q
..\..\.venv\Scripts\python.exe -m ruff check <zmienione pliki>
..\..\.venv\Scripts\python.exe -m mypy --strict <zmienione pliki>
..\..\.venv\Scripts\python.exe scripts/export_admin_openapi.py --check
npm run check:generated --workspace @game-predictor/admin-api-client
npm run typecheck --workspace @game-predictor/reviewer
```

## Risks / open questions

- Weryfikacja na żywych danych (zbudowanie kontekstu dla 25 odłożonych plansz
  odczytem) wymaga działającej bazy; w chwili pracy Docker Desktop zwracał 500,
  a PostgreSQL nie przyjmował połączeń.

## Outcome

### Changed

- `_validated_detected_board_geometry` (`storage/board_cell_geometry_pending_repository.py`)
  przyjmuje narożniki szkicu w granicach ręcznej edycji (`-W..2W`, `-H..2H`)
  zamiast granic obrazu; komunikat błędu poza nimi: „exceeds the manual edit
  bounds of the source”.
- `BoardCellGeometryCorrectionContextResponse.board_quad` i `suggested_corners`
  oraz `_quad` używają `ManualSourceGeometryPoint` (współrzędne ze znakiem).
  Nieużywana klasa `schemas.image_reviews.OperationalImageReviewGeometryPoint`
  (`x, y ≥ 0`) usunięta.
- OpenAPI i `types.gen.ts` zregenerowane; `packages/admin-api-client/src/index.ts`
  eksportuje `ManualSourceGeometryPoint as OperationalImageReviewGeometryPoint`,
  więc Reviewer nie wymaga zmian.
- Testy: `test_detected_quad_past_the_image_edge_seeds_manual_correction`
  (przypadek ze zgłoszenia, narożniki ujemne, odrzucenie poza granicą) i
  `test_correction_context_api_returns_corners_past_the_image_edge` (HTTP).

### Verification results

- Stary kod na przypadku ze zgłoszenia (pozycja 8, y = 905,75 przy 1520×904):
  `IMAGE_BOARD_CELL_PENDING_DETECTION_INVALID` „The pinned board quad is outside
  the immutable source bounds.” — odtworzony; nowy kod przyjmuje szkic.
- `pytest services/api/tests/test_board_cell_geometry_pending.py`: 15 passed.
- `ruff check`, `ruff format --check`, `mypy --strict` (4 zmienione pliki): OK.
- `export_admin_openapi.py --check`, `check:generated` klienta: aktualne.
- `npm run typecheck --workspace @game-predictor/reviewer`: OK;
  `npm run test --workspace @game-predictor/admin-api-client`: 105 pass, 0 fail.
- `check_decision_links.py`, `check_current_state_window.py`: OK.
- `pytest services/api/tests -k "board_cell or image_review or grid_review or openapi or reviewer or virtual_grid"`: 204 passed, 11 skipped (PostgreSQL), 4 min 34 s.

### Not completed

- Weryfikacja na żywej bazie (kontekst korekty dla 25 odłożonych plansz,
  odczyt): Docker Desktop zwracał 500, PostgreSQL nie przyjmował połączeń.
- Audyt krzyżowy: task poza planem, brak wymogu `Dodatkowy review`.

### Documentation updates

- `CURRENT_STATE.md`: sekcja `done`, sekcja TASK-0930 przeniesiona do
  `ai_docs/archive/CURRENT_STATE_2026Q4.md`. Brak wpisu `DECISION_LOG.md`:
  zmiana wyrównuje walidację szkicu do istniejącego kontraktu ręcznej edycji
  (D-436), bez nowej decyzji.

### Recommended next task

- Po scaleniu: `npm run reviewer:build`, restart Reviewera przez operatora i
  otwarcie importu `d82d9aba-…` w Reviewerze po przywróceniu bazy.
