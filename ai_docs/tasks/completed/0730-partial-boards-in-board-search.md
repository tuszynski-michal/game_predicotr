# TASK-0730 — Plansze niepełne w „Wyszukaj planszę” i „Przybliżonej wygranej”

## Status

done

## Goal

Każda plansza `pending_partial` z sekwencją ma dokument wyszukiwania z
widocznymi polami jako dowodem i polami wyciętymi jako nieznanymi, więc
„Przybliżona wygrana” liczy jej potwierdzoną wygraną zamiast traktować ją
jak brakującą.

## Context

Odbiór TASK-0729 (2026-09-30) wykazał, że 108 plansz `pending_partial` gry
`777` nie ma dokumentu wyszukiwania (499 892 dokumentów na 500 000 pozycji).
Kalkulator liczy za nie koszt spinu i wypłatę 0. Operator potrzebuje tych
plansz w wyliczeniach, także gdy są niepełne: plansza przycięta z prawej z
widoczną wygraną ma pokazać wygraną co najmniej potwierdzoną
(`payout-v3-unknown-prefix-stop`, `confirmed_minimum`). To zgodne z D-462 R3
(nieznane pola obsługuje prefix-stop) i D-451 (plansza niepełna nie tworzy
pełnego layoutu, ale jej pozycje logiczne zostają).

Przyczyna (`storage/board_search_projection_repository.py::_qualified_pending_predictions`):
- 105 plansz `virtual_source` rewizji 0 ma obserwacje także dla pól
  zamaskowanych, a warunek wymagał obserwacji wyłącznie dla pól dostępnych;
- 3 plansze `legacy_file` po ręcznej rewizji geometrii nie mają manifestu
  wirtualnego, a kod wymagał go dla każdej rewizji > 0 (ich obserwacje są
  bieżące: sumy kontrolne zgadzają się z cropami rewizji).

## Dependencies / entry conditions

- TASK-0729 done. Projekcja wyszukiwania gry gotowa.

## Recommended execution

claude-opus-5-5, high — reguła dowodu w projekcji wyszukiwania i odświeżenie
dokumentów na żywych danych. Audyt: claude-opus-5-5, high (subagent, poziom
warunkowy).

## Relevant docs

- `AGENTS.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md` D-451, D-462
- `ai_docs/delivery/CELL_LEVEL_VERIFICATION_EXECUTION_PLAN.md` (R3)

## Scope

- `_qualified_pending_predictions`: obserwacje pól zamaskowanych są
  ignorowane (zastępuje je nieznane pole), każde pole dostępne nadal wymaga
  obserwacji; bieżąca ręczna rewizja `legacy_file` używa własnych
  obserwacji, jeśli ich sumy kontrolne zgadzają się z `crop_artifacts`
  rewizji (`_legacy_revision_crops`), w przeciwnym razie brak dokumentu.
- Testy jednostkowe projekcji.
- Odświeżenie dokumentów tych plansz na żywych danych istniejącym, audytowanym
  narzędziem `scripts/migrate_cell_level_verification.py` (preview → apply);
  preview musi zawierać wyłącznie pozycje `refreshProjection` tych plansz.

## Out of scope

- Snapshot mobilny i layout z plansz niepełnych (osobny plan, zmiana D-462/P4).
- Plansze przycięte z lewej: prefix-stop nie potwierdza dla nich wygranej
  (brak widocznego początku linii) — zachowanie bez zmian.

## Acceptance criteria

- [x] Plansza `pending_partial` rewizji 0 z obserwacjami wszystkich 15 pól ma
      dokument z nieznanymi polami zamaskowanymi.
- [x] Ręczna rewizja `legacy_file` z bieżącymi cropami ma dokument; obserwacja
      innych pikseli niż crop rewizji na polu dostępnym — brak dokumentu.
- [x] Plansze pełne bez zmian (warunek identyczny dla pustej maski).
- [x] Preview na grze `777` zawiera tylko 108 pozycji `refreshProjection`;
      po apply 500 000 dokumentów na 500 000 pozycji.

## Technical notes

Kwalifikacja z pustą maską daje `available = 0..14`, więc warunek
`available ⊆ obserwacje` jest równoważny poprzedniemu dla plansz pełnych.
Obserwacja pola zamaskowanego nigdy nie jest dowodem — na wyjściu to pole
jest zawsze `None` bez alternatyw. Dla rewizji `legacy_file` predykcje z
`prediction_override` są używane jak dla plansz bez kwalifikacji (bez
manifestu wirtualnego); żywe plansze nie mają takich rewizji predykcji.

## Expected files

- Istniejące: `services/api/src/game_predictor_api/storage/board_search_projection_repository.py`
  (`_qualified_pending_predictions`, nowe `_legacy_revision_crops`),
  `services/api/tests/test_board_search_projection_repository.py`.

## Test cases

- Obserwacje wszystkich 15 pól przy masce (4, 9, 14) → dokument; brak
  obserwacji pola dostępnego → brak dokumentu.
- Rewizja `legacy_file` z maską (0, 5, 10) i bieżącymi cropami → dokument;
  jedna obserwacja pola dostępnego z inną sumą → brak dokumentu.
- Istniejące testy planszy częściowej i rewizji wirtualnej bez zmian.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_board_search_projection_repository.py services/api/tests/test_board_search_approximate_win_domain.py -q
.\.venv\Scripts\python.exe scripts/migrate_cell_level_verification.py preview --game-id bfc4f949-5c14-4850-b02a-db99610bcfa5 --output artifacts/cell-level-migration/partial-777.json
```

## Risks / open questions

- Nowe dokumenty zmieniają wyniki wyszukiwania i „Przybliżonej wygranej” dla
  tych 108 pozycji: z „brakującej” na „niepełną”, a plansza z ręcznie
  zweryfikowanymi polami zamaskowanymi — na pełną.

## Outcome

### Changed

- `_qualified_pending_predictions`: obserwacje pól zamaskowanych są
  ignorowane (pole zostaje nieznane, bez alternatyw), każde pole dostępne
  nadal wymaga obserwacji; bieżąca ręczna rewizja `legacy_file` planszy
  `legacy_file` używa własnych obserwacji, gdy ich sumy kontrolne zgadzają się
  z `crop_artifacts` rewizji (`_legacy_revision_crops`), inaczej brak
  dokumentu. Predykcje z rewizji predykcji nadpisują tylko pola dostępne, tak
  jak dla planszy `legacy_file` bez kwalifikacji.
- Testy: obserwacje pól zamaskowanych, rewizja `legacy_file` z bieżącymi i
  nieaktualnymi cropami, nadpisanie predykcji, brak tej ścieżki dla planszy
  `virtual_source`.

### Verification results

- `test_board_search_projection_repository.py` +
  `test_board_search_approximate_win_domain.py`: 61 passed. Testy
  wyszukiwania/przybliżonej wygranej/projekcji/kwalifikacji: 258 passed, 3
  failed (2 × `test_virtual_grid_geometry` z listy HEAD, 1 z niezacommitowanej
  zmiany limitu spinów operatora). PostgreSQL: projekcja i migracja 5
  passed. Ruff PASS; mypy bez błędów w pliku.
- Odczyt przed zmianą: 499 892 dokumenty na 500 000 pozycji; brakowało
  wyłącznie 108 plansz `pending_partial` gry `777` (105 `virtual_source`
  rewizji 0, 3 `legacy_file` rewizji 1: 62287, 62404, 62440).
- Preview (`artifacts/cell-level-migration/partial-777.json`,
  `previewSha256 c33bd162690843a807e15f919765fd3976f29150dc1f53b5f624c0b2345f434f`,
  tylko odczyt, 402 s): 108 pozycji, wyłącznie `refreshProjection`, dokładnie
  zbiór plansz niepełnych.
- Apply (`partial-apply-777.json`, 10 s): 108 `applied`, 0 dryfu i błędów.
  Po apply: 500 000 dokumentów na 500 000 pozycji; 44 plansze niepełne mają
  pola nieznane (wygrana liczona regułą prefix-stop jako potwierdzone
  minimum), 64 mają komplet symboli, bo pola zamaskowane zweryfikował
  operator (D-462 R1/R3), więc „Przybliżona wygrana” liczy je jak pełne.
- Audyt claude-opus-5-5 (subagent, poziom rozumowania dziedziczony): „Brak
  uwag P0–P2”; plansze pełne i istniejące dokumenty bez zmian, pola
  zamaskowane nigdy nie dają dowodu z modelu. Zastosowane P3: warunek
  `board.asset_mode == "legacy_file"`, test nadpisania predykcji; P3
  informacyjne (plansze z ręcznie zweryfikowanymi polami zamaskowanymi liczone
  jak pełne) zapisane wyżej.

### Not completed

- Snapshot mobilny z plansz niepełnych i niezweryfikowanych — osobny plan
  (zmiana D-462/P4).
- Plansze przycięte z lewej nie potwierdzają wygranej (prefix-stop) —
  zachowanie zamierzone.

### Documentation updates

- `CURRENT_STATE.md`.

### Recommended next task

- Plan snapshotu mobilnego z plansz niepełnych i niezweryfikowanych.
