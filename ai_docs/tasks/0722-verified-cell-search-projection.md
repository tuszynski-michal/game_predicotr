# TASK-0722 — Zweryfikowane komórki w projekcji wyszukiwania

## Status

todo

## Goal

Każda zweryfikowana komórka jest widoczna w `Wyszukaj planszę` i
„Przybliżonej wygranej” natychmiast po zapisie decyzji (pojedynczej lub z
joba), bez rozstrzygnięcia planszy.

## Context

Odczyt 2026-09-29: 22 340 zweryfikowanych komórek na 18 478 planszach
`pending` gry `7` jest ignorowanych, bo projekcja dla `pending` bierze tylko
predykcję, a synchronizacja następuje tylko przy rozstrzygnięciu planszy
(B1, B2 planu). D-462 R3, R8.

## Dependencies / entry conditions

TASK-0721 done.

## Recommended execution

claude-opus-5-5, high — projekcja współdzielona przez dwa widoki i
synchronizacja w transakcji mutacji. Audyt: claude-opus-5-5, high.

## Relevant docs

- `AGENTS.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md` D-462
- `ai_docs/requirements/ADMIN_APP.md` (Wyszukiwanie plansz z niepełnym wzorem,
  Przybliżona wygrana)
- `ai_docs/architecture/DATA_MODEL.md` (Projekcja wyszukiwania plansz)
- `ai_docs/delivery/CELL_LEVEL_VERIFICATION_EXECUTION_PLAN.md`

## Scope

- Czysta reguła nakładki decyzji komórek na dowód planszy `pending`.
- Odczyt bieżących komórek w `_payloads_from_rows` (jedno ograniczone
  zapytanie na partię, filtr gry, planszy i bieżącej rewizji geometrii).
- Synchronizacja projekcji po każdej zmianie wierszy komórek: mutacja
  operatora (`apply_board_mutations`), write-through
  `SymbolCellReviewWriteThroughCoordinator._synchronize` (geometria,
  predykcja, rozstrzygnięcie, ponowne otwarcie) i
  `virtual_grid_geometry_repository.py::_replace_current_cells`. Dziś
  wywołujący synchronizują projekcję przed zapisem komórek
  (`image_review_repository.py` ~1762, `board_cell_geometry_pending_repository.py`
  ~658, `pending_grid_reinference.py` ~254/612, `pipeline_store.py` ~899/1145).
- Admin: brak ponownego użycia wyniku „Przybliżonej wygranej” przy ponownym
  otwarciu sekcji.
- Aktualizacja `ADMIN_APP.md` i `DATA_MODEL.md` dla tego zachowania.

## Out of scope

- Backfill istniejących dokumentów (TASK-0728, wymaga zgody).
- Zmiana rankingu, kontraktu API, statusów, archiwum legacy.
- Plansze `accepted`/`corrected` (nadal `resolved_value`).

## Acceptance criteria

- [ ] Plansza `pending`: komórka `approved` z bieżącymi zatwierdzonymi
      pikselami (albo bez tożsamości pikseli akceptacji) i symbolem → ten
      symbol jako primary bez alternatyw; taka komórka bez symbolu (`?`) →
      brak dowodu; `approved` z innymi zatwierdzonymi pikselami niż bieżące →
      traktowana jak niezweryfikowana (R10), niezależnie od numeru rewizji.
- [ ] `pending` z `quality_issue` `grid_issue`, `unreadable` albo
      `partial_visibility` → brak dowodu; pozostałe komórki → predykcja.
- [ ] Pojedyncza decyzja i job masowy aktualizują fast document w tej samej
      transakcji, także gdy plansza zostaje `pending`.
- [ ] Cofnięcie weryfikacji (`Zła siatka`) usuwa symbol z dokumentu.
- [ ] Zmiana geometrii i odświeżenie predykcji zostawiają dokument zgodny z
      komórkami po zapisie.
- [ ] Ponowne otwarcie sekcji „Przybliżona wygrana” wysyła nowe żądanie.
- [ ] Testy jednostkowe + integracyjny PostgreSQL przechodzą; lint, mypy.

## Technical notes

Źródło decyzji: `image_symbol_review_cells` z `review_item_id = item.id`,
`recognized_board_id = board.id`, `geometry_revision = board.geometry_revision`,
`game_id = job.game_id`. Kod symbolu przez `symbols.code`. Nakładka dotyczy
wyłącznie gałęzi `pending`; gdy predykcje są niekompletne i payload i tak jest
`None`, zachowanie bez zmian. Decyzja per indeks komórki:

| Stan komórki | primary | alternatywy |
|---|---|---|
| `approved`, piksele akceptacji = bieżące lub brak tożsamości, symbol X | X | `()` |
| `approved`, piksele akceptacji = bieżące lub brak tożsamości, brak symbolu | `None` | `()` |
| `pending` + `grid_issue`/`unreadable`/`partial_visibility` | `None` | `()` |
| `approved` z innymi pikselami akceptacji albo `pending` bez problemu | predykcja | predykcja |

Pozycje z `source_available = false`, które nie są `outside`, pozostają bez
dowodu (jak dziś w `_qualified_pending_predictions`). Pozycja `outside` z
ręcznym przypisaniem (D-451) jest dowodem. Tożsamość pikseli: `virtual_source` porównuje
`approved_rendered_pixel_checksum_sha256` z `rendered_pixel_checksum_sha256`
(gdy oba są znane), w pozostałych przypadkach
`approved_crop_checksum_sha256` z `crop_checksum_sha256`; brak obu tożsamości
akceptacji = dowód. `crop_sample_id` i rewizja geometrii nie decydują.
Reguła jest jedną czystą funkcją domeny
`symbol_cell_approval_pixels_changed`, wspólną z TASK-0723.

Synchronizacja: `SqlAlchemyBoardSearchProjectionRepository(session)
.sync_review_item(item.id)` (idempotentne) w trzech miejscach: na końcu
`apply_board_mutations`, gdy którakolwiek komórka się zmieniła; na końcu
`_synchronize`, gdy `changed` i plansza jest aktywna; po
`_replace_current_cells`. Klient Admina: zwinięcie sekcji „Przybliżona
wygrana” resetuje stan do `idle` w `board-search-approximate-win.tsx`, więc
ponowne otwarcie zawsze liczy od nowa; komentarz `shouldRequestApproximateWin`
i opisy testów `reuses a ready result on reopen`
(`apps/admin/test/board-search-approximate-win-state.test.mjs`) zmieniają
kontrakt świadomie.

## Expected files

- `services/api/src/game_predictor_api/domain/board_search.py` — proponowana
  czysta funkcja nakładki i typ decyzji komórki.
- `services/api/src/game_predictor_api/storage/board_search_projection_repository.py`
  — `_payloads_from_rows`, `_payload_from_records`.
- `services/api/src/game_predictor_api/storage/image_symbol_review_repository.py`
  — `SqlAlchemySymbolCellReviewMutationRepository.apply_board_mutations`,
  `SymbolCellReviewWriteThroughCoordinator._synchronize`.
- `services/api/src/game_predictor_api/storage/virtual_grid_geometry_repository.py`
  — po `_replace_current_cells`.
- `apps/admin/src/features/board-search/board-search-approximate-win.tsx`.
- `apps/admin/src/features/board-search/board-search-approximate-win-state.ts`
  — `shouldRequestApproximateWin` (+ test).
- Testy: `services/api/tests/test_board_search_projection_repository.py`,
  `services/api/tests/test_board_search_domain.py`, proponowany nowy
  `services/api/tests/integration/test_verified_cell_search_projection.py`,
  testy Admina stanu i interakcji „Przybliżonej wygranej”.

## Test cases

- Jedna komórka zatwierdzona, reszta `pending` → dokument ma nowy kod na tej
  pozycji, pozostałe z predykcji (scenariusz 1).
- `grid_issue` na innej komórce → ta pozycja pusta, zatwierdzone zachowane
  (scenariusz 2).
- Mutacja przez serwis i przez job masowy → fast document zaktualizowany bez
  rozstrzygnięcia planszy.
- Zmiana geometrii planszy z zatwierdzoną komórką → dokument zgodny z
  komórkami po recropie.
- Interakcja Admina: zwinięcie i ponowne otwarcie sekcji → drugie żądanie.

## Verification

Katalog: root repozytorium; każdy krok z timeoutem 120 s.

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_board_search_projection_repository.py services/api/tests/test_board_search_domain.py -q
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_verified_cell_search_projection.py -q
npm run python:lint
npm run python:typecheck
npm run test --workspace @game-predictor/admin
npm run test:geometry --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
```

## Risks / open questions

- Plik stanu klienta ma niezacommitowane zmiany TASK-0720; commit zawiera
  wyłącznie hunk tego taska.
- Dodatkowe zapytanie o komórki w partii przebudowy (400 plansz) — indeks
  `game_data_v2` sprawdzić planem zapytania.

## Outcome

Wypełnia agent po pracy.
