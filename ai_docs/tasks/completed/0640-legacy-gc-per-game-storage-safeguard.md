---
title: TASK-0640 — bezpiecznik skryptu legacy GC (T4, D-442)
status: done
last_updated: 2026-09-24
---

# TASK-0640 — bezpiecznik skryptu legacy GC (T4, D-442)

## Status

`done`

## Goal

`scripts/preview_legacy_game_managed_asset_gc.py` nie może zakwalifikować
oryginałów/managed assetów gier na `game_data_v2` do usunięcia — odmawia
zarówno preview, jak i `--execute`, zanim powstanie jakikolwiek plik lub
zacznie się skan.

## Context

T4 przekazanego planu D-442. Wykonane na wyraźną, osobną zgodę użytkownika
("Tak, dawaj T4") po ukończeniu T1–T3. Skrypt (jednorazowe narzędzie z
TASK-0517 dla usuniętej gry legacy) skanuje referencje wyłącznie w
`public` (`_collect_live_paths`); od D-374 nowe gry są w `game_data_v2`,
więc dziś uznałby cały `data/originals` za nieużywany.

## Dependencies / entry conditions

- Niezależne od T1–T3 (fix routingu), ale wykonane po nich w tej samej
  sesji na jawne polecenie użytkownika.
- Fakt: `_operation_guard` (`scripts/preview_legacy_game_managed_asset_gc.py:181`)
  jest jedynym wspólnym punktem wejścia obu ścieżek — preview
  (`_create_preview`, linia ok. 1070) i `--execute` (`_execute_preview`,
  linia ok. 914) — sprawdzone w kodzie.
- Fakt: brak istniejącego testu tego skryptu odnoszącego się do
  `game_storage_locations` przed tą zmianą (`rg preview_legacy_game_managed_asset_gc
  services/api/tests scripts` → tylko `services/api/tests/test_legacy_game_managed_asset_gc_preview.py`,
  bez takiego testu).

## Recommended execution

claude-sonnet-5, reasoning: high. Jedno wczesne sprawdzenie w skrypcie
destrukcyjnym; test na fałszywym połączeniu. Dodatkowy review:
claude-opus-5-5, reasoning: medium — potwierdzenie, że odmowa następuje
przed skanem i zapisem plików (nie wykonany w tej sesji — brak dostępu do
osobnego modelu recenzenta; ryzyko ograniczone przez mutation-checked test
i ręczny przegląd diffu poniżej).

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md` (D-442, D-443)

## Scope

- `scripts/preview_legacy_game_managed_asset_gc.py`: `_operation_guard`
  jako pierwszy krok wykonuje `SELECT count(*) FROM
  public.game_storage_locations WHERE store_schema <> 'public'`; wynik > 0
  → `PreviewBlocked("LEGACY_GC_REFUSED_PER_GAME_STORAGE_PRESENT: …")`.
- `services/api/tests/test_legacy_game_managed_asset_gc_preview.py`: 2
  nowe testy z fałszywym połączeniem (odmowa przed jakimkolwiek innym
  zapytaniem; brak odmowy, gdy wszystkie gry są legacy).
- `ai_docs/process/DECISION_LOG.md`: nowy wpis D-443.

## Out of scope

- Reszta logiki skryptu, fraza potwierdzenia, `PROTECTED_OPERATOR_ROOT` —
  bez zmian.
- Przepisanie skryptu na skan obejmujący V2 (świadomie odłożone — patrz
  D-443 "warunek ponownego dopuszczenia").
- Uruchomienie skryptu na `artifacts/` lub bazie `game_predictor` — nie
  wykonane w tym tasku, zgodnie z jego własną instrukcją.

## Acceptance criteria

- [x] Test zielony: odmowa następuje przed jakimkolwiek innym zapytaniem
      (fałszywe połączenie rzuca `AssertionError`, gdyby druga kwerenda
      została wykonana — nie została).
- [x] Test zielony: brak odmowy z tego powodu, gdy `store_schema`
      wszystkich gier to `'public'` (kontrola przechodzi do
      istniejącej logiki).
- [x] Mutation check: pierwszy test czerwony bez poprawki (dowodzi, że
      przed zmianą druga kwerenda faktycznie była osiągana).
- [x] `python:lint`, `python:typecheck` czyste dla zmienionych plików.
- [x] Wpis DECISION_LOG (D-443).

## Technical notes

`_operation_guard(connection)` — nowy pierwszy blok:

```python
per_game_storage_count = int(
    connection.scalar(
        text("""
SELECT count(*) FROM public.game_storage_locations WHERE store_schema <> 'public'
""")
    ) or 0
)
if per_game_storage_count:
    raise PreviewBlocked("LEGACY_GC_REFUSED_PER_GAME_STORAGE_PRESENT: …")
```

Ponieważ `_create_preview` woła `_operation_guard` PRZED
`_collect_live_paths` i przed jakimkolwiek zapisem pliku preview/detail
(`scripts/preview_legacy_game_managed_asset_gc.py:1070-1075`), odmowa
następuje zanim skan referencji się zacznie i zanim powstanie jakikolwiek
plik. Dla `--execute` (`_execute_preview`) ten sam guard biegnie w tej
samej pozycji względem pozostałych kontroli bazy (operacja usunięcia,
tożsamość gier, aktywne joby) — przed nimi.

## Expected files

- Istniejące: `scripts/preview_legacy_game_managed_asset_gc.py` —
  `_operation_guard`.
- Istniejące: `services/api/tests/test_legacy_game_managed_asset_gc_preview.py`
  — 2 nowe testy + `_FakeGuardConnection`.
- Istniejące: `ai_docs/process/DECISION_LOG.md` — D-443.

## Test cases

- Fałszywe połączenie z `per_game_storage_count=1`: `_operation_guard`
  rzuca `PreviewBlocked` z `LEGACY_GC_REFUSED_PER_GAME_STORAGE_PRESENT`;
  dokładnie 1 zapytanie (`scalar`) zostało wykonane.
- Fałszywe połączenie z `per_game_storage_count=0`: `_operation_guard`
  przechodzi do kolejnej (pre-existing) kwerendy — fałszywka rzuca
  `AssertionError` dopiero tam, dowodząc, że nowy check nie blokuje.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_legacy_game_managed_asset_gc_preview.py -q
npm run python:lint
npm run python:typecheck
```

Uruchomione i zielone: pytest (19/19, w tym 2 nowe), `python:lint` (0
błędów w zmienionych plikach — 1 pre-existing, niezwiązany błąd w innym
pliku), `python:typecheck` (0 nowych błędów w zmienionych plikach — 3
pre-existing "unused type: ignore" na liniach importu, potwierdzone
niezwiązane przez porównanie z czystym checkout).

## Risks / open questions

- Skrypt pozostaje nieużywalny do czasu przepisania na skan
  wieloschematowy (świadome, akceptowane w D-443).
- Niezależny review (claude-opus-5-5, medium) wykonany — werdykt **SAFE**.
  Potwierdził: nowa kontrola jest dosłownie pierwszą instrukcją
  `_operation_guard`; przed nią w ścieżce preview nie ma żadnego zapisu na
  dysk (pierwszy `mkdir`/zapis pliku detail jest już po guardzie); w
  ścieżce execute `_lock_reference_tables` dotyka wyłącznie
  `information_schema`/blokad DB, żaden rename/delete managed assetów nie
  następuje przed guardem. Dwie drobne, niskiego ryzyka uwagi: (1) brak
  osobnego testu wprost sprawdzającego, że `_create_preview`/`_execute_preview`
  faktycznie wołają `_operation_guard` we właściwym miejscu (zweryfikowane
  tylko czytaniem kodu); (2) `game_storage_locations` nie jest w zbiorze
  tabel blokowanych przez `_lock_reference_tables` — wąskie okno wyścigu
  przy tworzeniu nowej gry w trakcie działania skryptu, ale błąd w stronę
  bezpieczną (odmowa, nie przeoczenie). Żadna z uwag nie wymagała zmiany
  kodu.

## Outcome

### Changed

- [scripts/preview_legacy_game_managed_asset_gc.py](../../scripts/preview_legacy_game_managed_asset_gc.py):
  `_operation_guard` refuses first when any game uses per-game (V2)
  storage.
- [services/api/tests/test_legacy_game_managed_asset_gc_preview.py](../../services/api/tests/test_legacy_game_managed_asset_gc_preview.py):
  2 new tests + `_FakeGuardConnection`.
- `ai_docs/process/DECISION_LOG.md`: D-443.
- `ai_docs/process/CURRENT_STATE.md`: new entry.

### Verification results

- `pytest services/api/tests/test_legacy_game_managed_asset_gc_preview.py`:
  19/19 green.
- Mutation check: `test_operation_guard_refuses_before_any_scan_when_per_game_storage_exists`
  confirmed red on the pre-fix script (reaches the pre-existing
  deletion-operation query instead of refusing).
- `npm run python:lint`: clean for changed files (1 pre-existing,
  unrelated error in `services/worker/tests/test_page_geometry_preflight.py`,
  confirmed present before this task's changes too).
- `npm run python:typecheck`: clean for changed files (3 pre-existing
  "unused type: ignore" warnings on unrelated import lines, confirmed
  present on a clean checkout).

### Not completed

- Independent opus-5-5 review from the plan's model table was not run in
  this session.
- Did not run the script itself (preview or execute) against `artifacts/`
  or the `game_predictor` database — out of scope per the script's own
  destructive-operation rules and this task's Out of scope section.

### Documentation updates

- `ai_docs/process/DECISION_LOG.md` — D-443.
- `ai_docs/process/CURRENT_STATE.md` — new entry, prepended.
- This task file moved to `ai_docs/tasks/completed/`.

### Recommended next task

- None from the D-442 plan — T1–T4 are all complete. If the legacy GC
  script is ever needed again, it requires a rewrite to scan references
  across every game schema first (see D-443's re-admission condition).
